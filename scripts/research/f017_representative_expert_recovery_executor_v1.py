#!/usr/bin/env python3
"""Narrow retained-authority executor for representative M1-F0 experts.

There is deliberately no checkpoint path, shard provider, positional reader,
or ledger writer in this module.  It consumes one representative normalized
input and exactly 24 packed expert weights retained by an earlier completed
event.  Real expert computation remains gated by a future single-use release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from f017_canonical_expert_output_production import (
    production_decoder_pair,
    strict_f32_matvec,
    strict_f32_silu,
)


SCHEMA = "pulsarmlx.f017.representative-expert-recovery-authorization"
EVENT_ID = "F017-REPRESENTATIVE-M1F0-EXPERT-OUTPUT-RECOVERY-1"
SELECTED_IDS = (250, 10, 237, 62, 73, 177, 218, 28)
ROLES = ("gate", "up", "down")
EXPERT_INPUT_SHA256 = "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c"
LEDGER = 175


class ExecutorError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExecutorError("JSON_OBJECT_REQUIRED")
    return value


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def atomic_file(path: Path, payload: bytes, *, mode: int = 0o400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(descriptor, view)
            if count <= 0: raise ExecutorError("DURABLE_WRITE")
            view = view[count:]
        os.fsync(descriptor)
    finally: os.close(descriptor)
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    fsync_dir(path.parent)


class OpenOnce:
    def __init__(self, path: Path, expected_sha: str, expected_bytes: int, label: str) -> None:
        self.path = Path(path)
        self.expected_sha = expected_sha
        self.expected_bytes = expected_bytes
        self.label = label
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        self.fd = os.open(self.path, flags)
        metadata = os.fstat(self.fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            self.close()
            raise ExecutorError(f"{label}_OBJECT_IDENTITY")
        if metadata.st_mode & 0o222 or metadata.st_size != expected_bytes:
            self.close()
            raise ExecutorError(f"{label}_MODE_OR_SIZE")
        self.identity = (metadata.st_dev, metadata.st_ino, metadata.st_size)
        self.before = self._hash_fd()
        if self.before != expected_sha:
            self.close()
            raise ExecutorError(f"{label}_BEFORE_SHA")

    def _hash_fd(self) -> str:
        digest = hashlib.sha256()
        offset = 0
        while offset < self.expected_bytes:
            chunk = os.pread(self.fd, min(1024 * 1024, self.expected_bytes - offset), offset)
            if not chunk:
                raise ExecutorError(f"{self.label}_SHORT_READ")
            digest.update(chunk)
            offset += len(chunk)
        return digest.hexdigest()

    def bytes(self) -> bytes:
        payload = bytearray()
        offset = 0
        while offset < self.expected_bytes:
            chunk = os.pread(self.fd, min(1024 * 1024, self.expected_bytes - offset), offset)
            if not chunk:
                raise ExecutorError(f"{self.label}_SHORT_READ")
            payload.extend(chunk)
            offset += len(chunk)
        return bytes(payload)

    def verify_after(self) -> str:
        metadata = os.fstat(self.fd)
        if (metadata.st_dev, metadata.st_ino, metadata.st_size) != self.identity:
            raise ExecutorError(f"{self.label}_OBJECT_REPLACED")
        after = self._hash_fd()
        if after != self.before:
            raise ExecutorError(f"{self.label}_AFTER_SHA")
        return after

    def close(self) -> None:
        if getattr(self, "fd", -1) >= 0:
            os.close(self.fd)
            self.fd = -1


def validate_authorization(document: dict[str, Any], authorization_path: Path) -> None:
    if document.get("schema") != SCHEMA or document.get("schema_version") != "1.0.0":
        raise ExecutorError("AUTHORIZATION_SCHEMA")
    if document.get("status") != "PREPARED_REVIEW_REQUIRED":
        raise ExecutorError("AUTHORIZATION_STATUS")
    if document.get("real_event_authorized") is not False:
        raise ExecutorError("REAL_EVENT_AUTHORITY")
    if document.get("event_id") != EVENT_ID:
        raise ExecutorError("EVENT_ID")
    if document.get("selected_expert_ids") != list(SELECTED_IDS):
        raise ExecutorError("EXPERT_ORDER")
    inventory = document.get("retained_payload_inventory", [])
    if len(inventory) != 24 or [item.get("ordinal") for item in inventory] != list(range(24)):
        raise ExecutorError("INVENTORY_ORDER")
    if [(x.get("expert_id"), x.get("role")) for x in inventory] != [
        (expert, role) for expert in SELECTED_IDS for role in ROLES
    ]:
        raise ExecutorError("INVENTORY_EXPERT_ROLE")
    if len({x.get("checkpoint_key") for x in inventory}) != 24:
        raise ExecutorError("INVENTORY_DUPLICATE")
    accounting = document.get("access_accounting", {})
    expected = {
        "starting_real_payload_ledger": LEDGER,
        "successful_terminal_ledger": LEDGER,
        "new_checkpoint_payload_reads": 0,
        "new_checkpoint_packed_bytes": 0,
        "shard_opens": 0,
        "retained_packed_payloads": 24,
        "retained_packed_bytes": 90_439_680,
    }
    if accounting != expected:
        raise ExecutorError("ACCESS_ACCOUNTING")
    if document.get("executor", {}).get("path") != "scripts/research/f017_representative_expert_recovery_executor_v1.py":
        raise ExecutorError("EXECUTOR_PATH")
    if document["executor"].get("sha256") != sha_file(Path(__file__).resolve()):
        raise ExecutorError("EXECUTOR_SHA")
    if document.get("authorization_file_sha256") not in (None, sha_file(authorization_path)):
        raise ExecutorError("AUTHORIZATION_FILE_SHA")


def open_inputs(document: dict[str, Any], expert_input: Path, packed_root: Path) -> tuple[OpenOnce, list[OpenOnce]]:
    spec = document["representative_expert_input"]
    if spec.get("sha256") != EXPERT_INPUT_SHA256 or spec.get("shape") != [6144] or spec.get("byte_length") != 24576:
        raise ExecutorError("EXPERT_INPUT_CONTRACT")
    normalized = OpenOnce(expert_input, EXPERT_INPUT_SHA256, 24576, "EXPERT_INPUT")
    opened: list[OpenOnce] = []
    try:
        for item in document["retained_payload_inventory"]:
            opened.append(OpenOnce(
                packed_root / item["source_relative_path"], item["packed_sha256"],
                item["packed_bytes"], f"PACKED_{item['ordinal']:02d}",
            ))
    except Exception:
        normalized.close()
        for handle in opened:
            handle.close()
        raise
    return normalized, opened


def compute_outputs(document: dict[str, Any], normalized: OpenOnce, packed: list[OpenOnce], *, synthetic: bool) -> dict[int, bytes]:
    vector = np.frombuffer(normalized.bytes(), dtype="<f4").copy()
    if vector.shape != (6144,) or not np.isfinite(vector).all():
        raise ExecutorError("EXPERT_INPUT_VALUES")
    decoder = None if synthetic else production_decoder_pair(ROOT)
    outputs: dict[int, bytes] = {}
    inventory = document["retained_payload_inventory"]
    for expert_index, expert_id in enumerate(SELECTED_IDS):
        matrices: dict[str, np.ndarray] = {}
        for role_index, role in enumerate(ROLES):
            ordinal = expert_index * 3 + role_index
            item = inventory[ordinal]
            if synthetic:
                shape = tuple(item["logical_shape"])
                matrices[role] = np.zeros(shape, dtype=np.float32)
            else:
                raw = packed[ordinal].bytes()
                first = decoder.decoder_a(raw, {**item, "logical_decoded_shape": item["logical_shape"], "packed_length": item["packed_bytes"]})
                second = decoder.decoder_b(raw, {**item, "logical_decoded_shape": item["logical_shape"], "packed_length": item["packed_bytes"]})
                if first != second or sha_bytes(first) != item["decoded_sha256"]:
                    raise ExecutorError("DUAL_DECODER_DISAGREEMENT")
                matrices[role] = np.frombuffer(first, dtype="<f4").reshape(item["logical_shape"])
        gate = strict_f32_matvec(matrices["gate"], vector)
        up = strict_f32_matvec(matrices["up"], vector)
        hidden = np.multiply(strict_f32_silu(gate), up, dtype=np.float32)
        output = strict_f32_matvec(matrices["down"], hidden)
        payload = np.ascontiguousarray(output, dtype="<f4").tobytes()
        if len(payload) != 24576 or not np.isfinite(output).all():
            raise ExecutorError("EXPERT_OUTPUT_VALUES")
        outputs[expert_id] = payload
    return outputs


def verify_after(normalized: OpenOnce, packed: list[OpenOnce]) -> dict[str, str]:
    result = {"representative_expert_input": normalized.verify_after()}
    for ordinal, handle in enumerate(packed):
        result[f"retained_payload_{ordinal:02d}"] = handle.verify_after()
    return result


def close_all(normalized: OpenOnce, packed: list[OpenOnce]) -> None:
    normalized.close()
    for handle in packed:
        handle.close()


def preflight(document: dict[str, Any], expert_input: Path, packed_root: Path) -> dict[str, Any]:
    normalized, packed = open_inputs(document, expert_input, packed_root)
    try:
        after = verify_after(normalized, packed)
    finally:
        close_all(normalized, packed)
    return {
        "disposition": "PRODUCTION_BINDINGS_RESOLVED",
        "retained_inputs": 25,
        "retained_packed_payloads": 24,
        "new_checkpoint_reads": 0,
        "shard_opens": 0,
        "ledger": LEDGER,
        "expert_executions": 0,
        "after_sha256": after,
    }


def reproduce_once(document: dict[str, Any], expert_input: Path, packed_root: Path) -> dict[str, str]:
    normalized, packed = open_inputs(document, expert_input, packed_root)
    try:
        outputs = compute_outputs(document, normalized, packed, synthetic=False)
        verify_after(normalized, packed)
    finally:
        close_all(normalized, packed)
    return {str(expert): sha_bytes(payload) for expert, payload in outputs.items()}


def execute(document: dict[str, Any], authorization_path: Path, expert_input: Path, packed_root: Path,
            state_root: Path, output_root: Path, token: Path) -> dict[str, Any]:
    grant = load_json(token)
    required = {
        "authorization_sha256": sha_file(authorization_path),
        "event_id": EVENT_ID,
        "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
        "real_event_authorized": True,
    }
    if grant != required:
        raise ExecutorError("FUTURE_SINGLE_USE_RELEASE_REQUIRED")
    if state_root.exists() or output_root.exists():
        raise ExecutorError("PRIOR_EVENT_STATE")
    normalized, packed = open_inputs(document, expert_input, packed_root)
    try:
        state_root.mkdir(parents=True, exist_ok=False)
        fsync_dir(state_root.parent)
        atomic_file(state_root / "attempt-start.json", canonical({
            "schema": "pulsarmlx.f017.representative-expert-recovery-attempt-start",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "authorization_sha256": sha_file(authorization_path), "ledger": LEDGER,
            "checkpoint_reads": 0, "shard_opens": 0, "retry": False,
        }) + b"\n")
        try:
            outputs = compute_outputs(document, normalized, packed, synthetic=False)
            after = verify_after(normalized, packed)
            output_root.mkdir(parents=True, exist_ok=False)
            fsync_dir(output_root.parent)
            records = []
            for ordinal, expert_id in enumerate(SELECTED_IDS):
                path = output_root / f"{ordinal:02d}-expert-{expert_id}-down.f32le"
                atomic_file(path, outputs[expert_id])
                records.append({"ordinal": ordinal, "expert_id": expert_id, "sha256": sha_file(path), "byte_length": 24576})
            manifest = {"schema": "pulsarmlx.f017.representative-expert-output-private-manifest", "schema_version": "1.0.0", "outputs": records}
            atomic_file(output_root / "manifest.json", canonical(manifest) + b"\n")
            environment = {**os.environ, "PULSARMLX_F017_REPRESENTATIVE_EXPERT_INTERNAL": "1"}
            reproduced = []
            for _ in range(2):
                completed = subprocess.run([
                    sys.executable, str(Path(__file__).resolve()), "--authorization", str(authorization_path),
                    "--expert-input", str(expert_input), "--packed-root", str(packed_root), "--internal-reproduce",
                ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
                if completed.returncode: raise ExecutorError("REPRODUCTION_PROCESS")
                reproduced.append(json.loads(completed.stdout))
            expected = {str(item["expert_id"]): item["sha256"] for item in records}
            if reproduced != [expected, expected]: raise ExecutorError("REPRODUCTION_IDENTITY")
            terminal = {"schema":"pulsarmlx.f017.representative-expert-recovery-terminal","schema_version":"1.0.0",
              "event_id":EVENT_ID,"disposition":"COMPLETE","ledger_before":LEDGER,"ledger_after":LEDGER,
              "checkpoint_reads":0,"shard_opens":0,"outputs":records,"fresh_process_reproductions":2,
              "exact_reproduction":True,"after_sha256":after,"retry":False}
            atomic_file(state_root / "terminal.json", canonical(terminal)+b"\n")
            return terminal
        except BaseException as error:
            terminal = {"schema":"pulsarmlx.f017.representative-expert-recovery-terminal","schema_version":"1.0.0",
              "event_id":EVENT_ID,"disposition":"TERMINAL_FAILURE","reason":type(error).__name__,
              "ledger_before":LEDGER,"ledger_after":LEDGER,"checkpoint_reads":0,"shard_opens":0,"retry":False}
            if not (state_root / "terminal.json").exists(): atomic_file(state_root / "terminal.json", canonical(terminal)+b"\n")
            raise
    finally: close_all(normalized, packed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--expert-input", type=Path, required=True)
    parser.add_argument("--packed-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--go-token", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--internal-reproduce", action="store_true")
    args = parser.parse_args()
    document = load_json(args.authorization)
    validate_authorization(document, args.authorization)
    if args.internal_reproduce:
        if os.environ.get("PULSARMLX_F017_REPRESENTATIVE_EXPERT_INTERNAL") != "1":
            raise ExecutorError("INTERNAL_REPRODUCTION_GATE")
        result = reproduce_once(document, args.expert_input, args.packed_root)
    elif args.preflight_only:
        result = preflight(document, args.expert_input, args.packed_root)
    else:
        if args.output_root is None or args.state_root is None or args.go_token is None:
            raise ExecutorError("EXECUTION_BINDINGS_REQUIRED")
        result = execute(document, args.authorization, args.expert_input, args.packed_root, args.state_root, args.output_root, args.go_token)
    print(canonical(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

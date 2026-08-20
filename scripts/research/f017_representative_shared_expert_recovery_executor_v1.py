#!/usr/bin/env python3
"""Retained-only representative layer-3 shared-expert recovery executor.

The interface has no checkpoint or shard path.  It consumes one retained
representative F_norm vector and exactly three retained packed model weights.
Real execution remains gated by a future single-use release token.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts/research") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts/research"))

from prepare_f017_m1f0_real_reference import decode_q5_k_spec
from qualify_f017_m1f0_q5_k_real import decode_q5_k_upstream_spec
from f017_m1f_minus1_dense_prefix_prep import decode_q6_k_independent, decode_q6_k_spec


SCHEMA = "pulsarmlx.f017.representative-shared-expert-recovery-authorization"
EVENT_ID = "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-1"
INPUT_SHA256 = "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c"
LEDGER = 175
OUTPUT_NAME = "representative-shared-expert-output.f32le"
EXPECTED_PARAMETERS = [
    (0, "blk.3.ffn_gate_shexp.weight", "gate", "packed/01-gate.bin", "750b148ada60dbbfc9bd3b2d4c2bbfa70f304c34328b025f912626dea70c1414", "0dbb53a88bae423154f385ec547c9b778afe8127df6a19955dce2b1653d2282b", "Q5_K", 8650752, 50331648, [2048, 6144]),
    (1, "blk.3.ffn_up_shexp.weight", "up", "packed/02-up.bin", "13727df9b9129906538081fcef3a23d4db8ba37235bb96605c46b3ff683c59fe", "86aae8655c565eeed20a3f87fd701fa15aff976600d095694cd163a0303e3000", "Q5_K", 8650752, 50331648, [2048, 6144]),
    (2, "blk.3.ffn_down_shexp.weight", "down", "packed/03-down.bin", "48c5469bf71d1c5291f806a79388901f094d5fd7adaec5c25c0f3391b0d67083", "97e654b6e4903cd35ae8fae15c03e9953b15ef3ad4f5c0c60210a1e7864fe4a3", "Q6_K", 10321920, 50331648, [6144, 2048]),
]


class ExecutorError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExecutorError(message)


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
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"DUPLICATE_JSON_KEY:{key}")
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_exclusive(path: Path, payload: bytes, *, mode: int = 0o400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            require(written > 0, "DURABLE_WRITE")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(temporary, mode)
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.link(temporary.name, path.name, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
        temporary.unlink(missing_ok=True)


class OpenOnce:
    def __init__(self, path: Path, expected_sha: str, expected_bytes: int, label: str) -> None:
        self.path = Path(path)
        self.expected_sha = expected_sha
        self.expected_bytes = expected_bytes
        self.label = label
        self.fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        meta = os.fstat(self.fd)
        try:
            require(stat.S_ISREG(meta.st_mode), f"{label}_REGULAR")
            require(meta.st_nlink == 1, f"{label}_SINGLE_LINK")
            require(meta.st_mode & 0o222 == 0, f"{label}_READ_ONLY")
            require(meta.st_size == expected_bytes, f"{label}_BYTE_LENGTH")
            self.identity = (meta.st_dev, meta.st_ino, meta.st_size)
            self.before = self._hash_fd()
            require(self.before == expected_sha, f"{label}_BEFORE_SHA")
        except Exception:
            self.close()
            raise

    def _read(self) -> bytes:
        chunks: list[bytes] = []
        offset = 0
        while offset < self.expected_bytes:
            chunk = os.pread(self.fd, min(1024 * 1024, self.expected_bytes - offset), offset)
            require(bool(chunk), f"{self.label}_SHORT_READ")
            chunks.append(chunk)
            offset += len(chunk)
        return b"".join(chunks)

    def _hash_fd(self) -> str:
        return sha_bytes(self._read())

    def consume(self) -> bytes:
        raw = self._read()
        require(sha_bytes(raw) == self.before, f"{self.label}_CONSUMED_SHA")
        return raw

    def verify_after(self) -> str:
        meta = os.fstat(self.fd)
        require((meta.st_dev, meta.st_ino, meta.st_size) == self.identity, f"{self.label}_OBJECT_CHANGED")
        after = self._hash_fd()
        require(after == self.before == self.expected_sha, f"{self.label}_AFTER_SHA")
        return after

    def close(self) -> None:
        if getattr(self, "fd", -1) >= 0:
            os.close(self.fd)
            self.fd = -1


def canonical_f32(values: Any) -> bytes:
    array = np.asarray(values, dtype=np.float32).reshape(-1)
    require(np.isfinite(array).all(), "DECODED_NONFINITE")
    return np.ascontiguousarray(array, dtype="<f4").tobytes()


def decode_q5_a(packed: bytes) -> bytes:
    return canonical_f32(decode_q5_k_spec(packed))


def decode_q5_b(packed: bytes) -> bytes:
    return canonical_f32(decode_q5_k_upstream_spec(packed))


def decode_q6(packed: bytes, decoder: Callable[[bytes], list[float]]) -> bytes:
    require(bool(packed) and len(packed) % 210 == 0, "Q6_K_PACKED_LENGTH")
    output: list[float] = []
    for start in range(0, len(packed), 210):
        output.extend(decoder(packed[start:start + 210]))
    return canonical_f32(output)


def decode_q6_a(packed: bytes) -> bytes:
    return decode_q6(packed, decode_q6_k_spec)


def decode_q6_b(packed: bytes) -> bytes:
    return decode_q6(packed, decode_q6_k_independent)


def strict_f32_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    vector = np.asarray(vector, dtype=np.float32)
    require(matrix.ndim == 2 and vector.ndim == 1 and matrix.shape[1] == vector.size, "MATVEC_SHAPE")
    result = np.zeros(matrix.shape[0], dtype=np.float32)
    for column in range(matrix.shape[1]):
        product = np.multiply(matrix[:, column], vector[column], dtype=np.float32)
        result = np.add(result, product, dtype=np.float32)
    require(np.isfinite(result).all(), "MATVEC_NONFINITE")
    return result


def strict_f32_silu(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=np.float32)
    denominator = np.add(np.exp(np.negative(value, dtype=np.float32), dtype=np.float32), np.float32(1.0), dtype=np.float32)
    result = np.divide(value, denominator, dtype=np.float32)
    require(np.isfinite(result).all(), "SILU_NONFINITE")
    return result


def validate_authorization(doc: dict[str, Any]) -> None:
    require(doc.get("schema") == SCHEMA and doc.get("schema_version") == "1.0.0", "AUTHORIZATION_SCHEMA")
    require(doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "AUTHORIZATION_STATE")
    require(doc.get("event_id") == EVENT_ID, "EVENT_ID")
    input_spec = doc.get("representative_input", {})
    require(input_spec.get("sha256") == INPUT_SHA256 and input_spec.get("semantic_role") == "CANONICAL_REPRESENTATIVE_POST_ATTENTION_FFN_NORMALIZED_SHARED_EXPERT_INPUT", "REPRESENTATIVE_INPUT")
    require(input_spec.get("dtype") == "little-endian-f32" and input_spec.get("shape") == [6144] and input_spec.get("byte_length") == 24576, "INPUT_GEOMETRY")
    parameters = doc.get("retained_parameters", [])
    require(len(parameters) == 3 and [x.get("ordinal") for x in parameters] == [0, 1, 2], "PARAMETER_COUNT_ORDER")
    require([x.get("role") for x in parameters] == ["gate", "up", "down"], "PARAMETER_ROLE_ORDER")
    require([x.get("quantization") for x in parameters] == ["Q5_K", "Q5_K", "Q6_K"], "PARAMETER_QUANTIZATION")
    require(sum(x.get("packed_bytes", 0) for x in parameters) == 27_623_424, "PARAMETER_PACKED_TOTAL")
    observed = [(x.get("ordinal"), x.get("checkpoint_key"), x.get("role"), x.get("relative_path"), x.get("packed_sha256"), x.get("decoded_sha256"), x.get("quantization"), x.get("packed_bytes"), x.get("decoded_bytes"), x.get("decoded_shape")) for x in parameters]
    require(observed == EXPECTED_PARAMETERS, "PARAMETER_IDENTITY")
    one_shot = doc.get("one_shot_semantics", {})
    require(all(one_shot.get(key) is True for key in ("durable_attempt_start", "durable_shared_computation_start", "exclusive_attempt_root", "failure_after_attempt_start_consumes_release")), "ONE_SHOT_REQUIRED")
    require(all(one_shot.get(key) is False for key in ("retry", "resume", "second_attempt")), "ONE_SHOT_PROHIBITION")
    accounting = doc.get("access_accounting", {})
    require(accounting == {"ledger_before": 175, "ledger_after": 175, "checkpoint_reads": 0, "shard_opens": 0, "future_shared_expert_executions": 1, "preparation_shared_expert_executions": 0, "routed_aggregate_executions": 0, "ffn_completions": 0, "s2_constructions": 0}, "ACCOUNTING")
    for key in ("checkpoint_access", "checkpoint_fallback", "shard_open", "historical_direct_dprefix_input", "historical_shared_output_substitution", "routed_shared_combination", "ffn_completion", "s2_construction", "gpu", "blas"):
        require(doc.get("prohibitions", {}).get(key) is True, f"PROHIBITION:{key}")


def open_retained(doc: dict[str, Any], input_path: Path, parameter_root: Path) -> tuple[OpenOnce, OpenOnce, list[OpenOnce]]:
    input_spec = doc["representative_input"]
    normalized = OpenOnce(input_path, input_spec["sha256"], input_spec["byte_length"], "REPRESENTATIVE_INPUT")
    manifest_spec = doc["parameter_manifest"]
    manifest = OpenOnce(parameter_root / manifest_spec["relative_path"], manifest_spec["sha256"], manifest_spec["byte_length"], "PARAMETER_MANIFEST")
    parameters: list[OpenOnce] = []
    try:
        manifest_doc = json.loads(manifest.consume())
        require(manifest_doc.get("schema") == "pulsarmlx.f017.representative-shared-expert-weight-reuse-private-manifest", "PARAMETER_MANIFEST_SCHEMA")
        entries = manifest_doc.get("artifacts")
        require(isinstance(entries, list) and len(entries) == 3, "PARAMETER_MANIFEST_COUNT")
        for spec, entry in zip(doc["retained_parameters"], entries, strict=True):
            require(entry.get("role") == spec.get("role") and entry.get("packed_sha256") == spec.get("packed_sha256"), "PARAMETER_MANIFEST_BINDING")
            parameters.append(OpenOnce(parameter_root / spec["relative_path"], spec["packed_sha256"], spec["packed_bytes"], f"PARAMETER_{spec['role'].upper()}"))
    except Exception:
        normalized.close()
        manifest.close()
        for handle in parameters:
            handle.close()
        raise
    return normalized, manifest, parameters


def decode_parameters(doc: dict[str, Any], handles: list[OpenOnce], *, disagreement_role: str | None = None) -> dict[str, np.ndarray]:
    matrices: dict[str, np.ndarray] = {}
    for spec, handle in zip(doc["retained_parameters"], handles, strict=True):
        packed = handle.consume()
        if spec["quantization"] == "Q5_K":
            first, second = decode_q5_a(packed), decode_q5_b(packed)
        else:
            first, second = decode_q6_a(packed), decode_q6_b(packed)
        if disagreement_role == spec["role"]:
            second = second[:-4] + bytes([second[-4] ^ 1]) + second[-3:]
        require(first == second, "DUAL_DECODER_DISAGREEMENT")
        require(sha_bytes(first) == spec["decoded_sha256"], f"DECODED_SHA:{spec['role']}")
        require(len(first) == spec["decoded_bytes"], f"DECODED_BYTES:{spec['role']}")
        matrix = np.frombuffer(first, dtype="<f4").reshape(spec["decoded_shape"])
        require(np.isfinite(matrix).all(), f"DECODED_FINITE:{spec['role']}")
        matrices[spec["role"]] = matrix
    return matrices


def compute(doc: dict[str, Any], normalized: OpenOnce, parameters: list[OpenOnce], *, disagreement_role: str | None = None) -> bytes:
    vector = np.frombuffer(normalized.consume(), dtype="<f4").copy()
    require(vector.shape == (6144,) and np.isfinite(vector).all(), "INPUT_VALUES")
    matrices = decode_parameters(doc, parameters, disagreement_role=disagreement_role)
    gate = strict_f32_matvec(matrices["gate"], vector)
    up = strict_f32_matvec(matrices["up"], vector)
    hidden = np.multiply(strict_f32_silu(gate), up, dtype=np.float32)
    require(np.isfinite(hidden).all(), "HIDDEN_NONFINITE")
    output = strict_f32_matvec(matrices["down"], hidden)
    raw = np.ascontiguousarray(output, dtype="<f4").tobytes()
    require(len(raw) == 24576 and np.isfinite(output).all(), "OUTPUT_VALUES")
    return raw


def verify_after(normalized: OpenOnce, manifest: OpenOnce, parameters: list[OpenOnce]) -> dict[str, str]:
    values = {"representative_input": normalized.verify_after(), "parameter_manifest": manifest.verify_after()}
    for spec, handle in zip(("gate", "up", "down"), parameters, strict=True):
        values[f"parameter_{spec}"] = handle.verify_after()
    return values


def close_all(normalized: OpenOnce, manifest: OpenOnce, parameters: list[OpenOnce]) -> None:
    normalized.close()
    manifest.close()
    for handle in parameters:
        handle.close()


def preflight(doc: dict[str, Any], input_path: Path, parameter_root: Path) -> dict[str, Any]:
    validate_authorization(doc)
    normalized, manifest, parameters = open_retained(doc, input_path, parameter_root)
    try:
        after = verify_after(normalized, manifest, parameters)
    finally:
        close_all(normalized, manifest, parameters)
    return {"disposition": "PRODUCTION_BINDINGS_RESOLVED", "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "shared_expert_executions": 0, "retained_parameters": 3, "retained_packed_bytes": 27_623_424, "after_sha256": after}


def execute(doc: dict[str, Any], authorization_path: Path, input_path: Path, parameter_root: Path, state_root: Path, output_root: Path, token_path: Path) -> dict[str, Any]:
    token = load_json(token_path)
    required = {"authorization_sha256": sha_file(authorization_path), "event_id": EVENT_ID, "disposition": "GO_EXECUTE_ONCE_NO_RETRY", "real_event_authorized": True}
    require(token == required, "FUTURE_SINGLE_USE_RELEASE_REQUIRED")
    require(not state_root.exists() and not output_root.exists(), "PRIOR_EVENT_STATE")
    validate_authorization(doc)
    normalized, manifest, parameters = open_retained(doc, input_path, parameter_root)
    try:
        state_root.mkdir(parents=True, exist_ok=False)
        fsync_dir(state_root.parent)
        atomic_exclusive(state_root / "attempt-start.json", canonical({"schema": "pulsarmlx.f017.representative-shared-expert-attempt-start", "event_id": EVENT_ID, "authorization_sha256": sha_file(authorization_path), "ledger": 175, "retry": False}) + b"\n")
        atomic_exclusive(state_root / "shared-computation-start.json", canonical({"schema": "pulsarmlx.f017.representative-shared-expert-computation-start", "event_id": EVENT_ID, "shared_expert_executions": 1}) + b"\n")
        try:
            raw = compute(doc, normalized, parameters)
            after = verify_after(normalized, manifest, parameters)
            output_root.mkdir(parents=True, exist_ok=False)
            fsync_dir(output_root.parent)
            atomic_exclusive(output_root / OUTPUT_NAME, raw)
            output_sha = sha_file(output_root / OUTPUT_NAME)
            terminal = {"schema": "pulsarmlx.f017.representative-shared-expert-terminal", "disposition": "COMPLETE", "event_id": EVENT_ID, "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "shared_expert_executions": 1, "output_sha256": output_sha, "output_dtype": "little-endian-f32", "output_shape": [6144], "output_bytes": 24576, "input_after_sha256": after, "routed_shared_combination": 0, "ffn_completions": 0, "s2_constructions": 0}
            atomic_exclusive(state_root / "terminal.json", canonical(terminal) + b"\n")
            return terminal
        except Exception as error:
            terminal = {"schema": "pulsarmlx.f017.representative-shared-expert-terminal", "disposition": "TERMINAL_FAILURE", "event_id": EVENT_ID, "reason": type(error).__name__, "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "shared_expert_executions": 1, "routed_shared_combination": 0, "ffn_completions": 0, "s2_constructions": 0, "retry": False}
            atomic_exclusive(state_root / "terminal.json", canonical(terminal) + b"\n")
            raise
    finally:
        close_all(normalized, manifest, parameters)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--representative-input", type=Path, required=True)
    parser.add_argument("--parameter-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--go-token", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    document = load_json(args.authorization)
    if args.preflight_only:
        print(json.dumps(preflight(document, args.representative_input, args.parameter_root), sort_keys=True))
        return 0
    require(args.state_root is not None and args.output_root is not None and args.go_token is not None, "EXECUTION_PATHS")
    print(json.dumps(execute(document, args.authorization, args.representative_input, args.parameter_root, args.state_root, args.output_root, args.go_token), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

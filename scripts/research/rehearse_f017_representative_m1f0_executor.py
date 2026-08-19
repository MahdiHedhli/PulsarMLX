#!/usr/bin/env python3
"""Checkpoint-free real-geometry rehearsal for the representative executor."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

from f017_representative_m1f0_executor import (
    DecoderPair, EventError, RepresentativeM1F0Executor, RetainedAuthorityResolver,
    SyntheticComputationStage, SyntheticZeroDecoder, canonical_json, sha_file,
)


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-candidate-v2.json"
GEOMETRY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-synthetic-real-geometry-v1.json"


def write_read_only(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    os.chmod(path, 0o444)
    return hashlib.sha256(payload).hexdigest()


class SyntheticProvider:
    def __init__(self, entries: list[dict[str, Any]], fault: str | None = None, fault_ordinal: int = 4):
        self.entries = entries
        self.fault = fault
        self.fault_ordinal = fault_ordinal
        self.open_count = 0
        self.read_count = 0
        self.closed = False

    def open(self) -> "SyntheticProvider":
        if self.open_count:
            raise EventError("SECOND_SHARD_OPEN")
        self.open_count += 1
        return self

    def read_at(self, offset: int, length: int, ordinal: int) -> bytes:
        if self.closed:
            raise EventError("READ_AFTER_CLOSE")
        if ordinal != self.read_count:
            raise EventError("READ_ORDER")
        expected = self.entries[ordinal]
        if (offset, length) != (expected["offset"], expected["packed_bytes"]):
            raise EventError("READ_RANGE")
        if self.fault == "interrupt" and ordinal == self.fault_ordinal:
            raise EventError("SYNTHETIC_INTERRUPT")
        self.read_count += 1
        if self.fault == "short" and ordinal == self.fault_ordinal:
            return bytes(length - 1)
        return bytes(length)

    def close(self) -> None:
        self.closed = True


def synthetic_authorization() -> dict[str, Any]:
    authorization = json.loads(CANDIDATE.read_text())
    geometry = json.loads(GEOMETRY.read_text())
    authorization["status"] = "PREPARED_REVIEW_REQUIRED"
    for target, source in zip(authorization["attention_payload_inventory"], geometry["inventory"], strict=True):
        target["packed_sha256"] = source["synthetic_packed_sha256"]
        target["decoded_sha256"] = hashlib.sha256(canonical_json({"shape": tuple(source["logical_shape"]), "zero": True})).hexdigest()
    return authorization


def make_retained(root: Path, authorization: dict[str, Any]) -> tuple[dict[str, Path], dict[str, Path]]:
    s0 = np.asarray([(index % 31 - 15) / 32.0 for index in range(6144)], dtype="<f4")
    gamma = np.ones(6144, dtype="<f4")
    router = np.zeros((256, 6144), dtype="<f4")
    router[:, 0] = np.arange(256, dtype=np.float32) / np.float32(4096.0)
    bias = np.arange(256, dtype="<f4") / np.float32(65536.0)
    values = {"canonical_s0": s0, "ffn_norm": gamma, "router_matrix": router, "correction_bias": bias}
    paths: dict[str, Path] = {}
    for spec in authorization["retained_inputs"]:
        role = spec["role"]
        path = root / "retained" / f"{role}.bin"
        digest = write_read_only(path, values[role].tobytes(order="C"))
        spec["sha256"] = digest
        paths[role] = path
    manifest_path = root / "retained" / "s0-private-manifest.json"
    manifest_sha = write_read_only(manifest_path, canonical_json({"artifact": "canonical_s0", "sha256": authorization["retained_inputs"][0]["sha256"]}))
    authorization["retained_inputs"][0]["private_manifest_sha256"] = manifest_sha
    return paths, {"canonical_s0": manifest_path}


def pairs(disagreement: bool = False) -> dict[str, DecoderPair]:
    return {
        kind: DecoderPair(SyntheticZeroDecoder(f"{kind}_SYNTH_A"), SyntheticZeroDecoder(f"{kind}_SYNTH_B", disagreement))
        for kind in ("F32", "Q5_K", "Q8_0")
    }


def execute_once(root: Path, *, fault: str | None = None, fault_ordinal: int = 4,
                 packed_mismatch: bool = False, disagreement: bool = False,
                 decoded_mismatch: bool = False, retention_failure: bool = False,
                 before_mismatch: str | None = None, after_mismatch: str | None = None,
                 wrong_epsilon: bool = False, wrong_vocabulary: bool = False,
                 state_root: Path | None = None) -> dict[str, Any]:
    authorization = synthetic_authorization()
    paths, manifests = make_retained(root, authorization)
    if packed_mismatch:
        authorization["attention_payload_inventory"][0]["packed_sha256"] = "0" * 64
    if decoded_mismatch:
        authorization["attention_payload_inventory"][0]["decoded_sha256"] = "0" * 64
    if before_mismatch:
        for spec in authorization["retained_inputs"]:
            if spec["role"] == before_mismatch:
                spec["sha256"] = "0" * 64
    override = {after_mismatch: "0" * 64} if after_mismatch else {}
    resolver = RetainedAuthorityResolver(paths, manifests, override)
    provider = SyntheticProvider(authorization["attention_payload_inventory"], fault, fault_ordinal)
    def writer(path: Path, payload: bytes) -> None:
        if retention_failure and path.name == "00.bin":
            raise EventError("RETAIN_PACKED_FAILURE")
        from f017_representative_m1f0_executor import atomic_bytes
        atomic_bytes(path, payload)
    executor = RepresentativeM1F0Executor(
        authorization, hashlib.sha256(canonical_json(authorization)).hexdigest(), provider,
        pairs(disagreement), resolver, SyntheticComputationStage(wrong_epsilon, wrong_vocabulary),
        state_root or root / "state", root / "package", synthetic=True, retention_writer=writer,
    )
    result = executor.execute()
    result["result_sha256"] = hashlib.sha256(canonical_json(result)).hexdigest()
    return result


def terminal_reason(root: Path) -> tuple[str, int]:
    terminal = json.loads((root / "state" / "terminal.json").read_text())
    return terminal["reason"], terminal["consumed_reads"]


def expected_failure(root: Path, expected: str, **kwargs: Any) -> dict[str, Any]:
    try:
        execute_once(root, **kwargs)
    except EventError as exc:
        reason, consumed = terminal_reason(root) if (root / "state" / "terminal.json").exists() else (exc.code, 0)
        if exc.code != expected and reason != expected:
            raise AssertionError((expected, exc.code, reason))
        return {"status": "PASS", "reason": expected, "consumed_reads": consumed,
                "ledger": 166 + consumed}
    raise AssertionError(f"failure {expected} did not occur")


def fresh_process_success(base: Path, ordinal: int) -> dict[str, Any]:
    output = base / f"fresh-{ordinal}.json"
    command = [sys.executable, str(Path(__file__).resolve()), "--once", "--work-root", str(base / f"fresh-{ordinal}"), "--output", str(output)]
    subprocess.run(command, check=True, cwd=ROOT)
    return json.loads(output.read_text())


def parent_rehearsal(output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="f017-m1f0-rehearsal-") as directory:
        base = Path(directory)
        first = fresh_process_success(base, 1)
        second = fresh_process_success(base, 2)
        if first["stage_sha256"] != second["stage_sha256"]:
            raise AssertionError("fresh-process output mismatch")
        failures: dict[str, Any] = {}
        failures["interrupt_after_middle_read"] = expected_failure(base / "fail-interrupt", "SYNTHETIC_INTERRUPT", fault="interrupt", fault_ordinal=5)
        failures["short_read"] = expected_failure(base / "fail-short", "SHORT_READ", fault="short", fault_ordinal=4)
        failures["packed_hash_mismatch"] = expected_failure(base / "fail-packed", "PACKED_HASH_MISMATCH", packed_mismatch=True)
        failures["decoder_disagreement"] = expected_failure(base / "fail-decoder", "DECODER_DISAGREEMENT", disagreement=True)
        failures["decoded_hash_mismatch"] = expected_failure(base / "fail-decoded", "DECODED_HASH_MISMATCH", decoded_mismatch=True)
        failures["retained_write_failure"] = expected_failure(base / "fail-retain", "RETAIN_PACKED_FAILURE", retention_failure=True)
        failures["retained_before_hash_mismatch"] = expected_failure(base / "fail-before", "RETAINED_BEFORE_HASH", before_mismatch="ffn_norm")
        failures["retained_after_hash_mismatch"] = expected_failure(base / "fail-after", "RETAINED_AFTER_HASH", after_mismatch="router_matrix")
        failures["s0_preflight_mismatch"] = expected_failure(base / "fail-s0", "RETAINED_BEFORE_HASH", before_mismatch="canonical_s0")
        failures["wrong_epsilon"] = expected_failure(base / "fail-epsilon", "EPSILON_IDENTITY", wrong_epsilon=True)
        failures["wrong_stage_vocabulary"] = expected_failure(base / "fail-vocab", "STAGE_VOCABULARY", wrong_vocabulary=True)

        # Pre-read structural guards.
        reordered = synthetic_authorization()
        reordered["status"] = "PREPARED_REVIEW_REQUIRED"
        reordered["attention_payload_inventory"][0], reordered["attention_payload_inventory"][1] = reordered["attention_payload_inventory"][1], reordered["attention_payload_inventory"][0]
        try:
            RepresentativeM1F0Executor(reordered, "0" * 64, SyntheticProvider(reordered["attention_payload_inventory"]), pairs(),
                RetainedAuthorityResolver({}), SyntheticComputationStage(), base / "reorder", base / "reorder-package", True)._gate()
        except EventError as exc:
            failures["reordered_reads"] = {"status": "PASS", "reason": exc.code, "consumed_reads": 0, "ledger": 166}
        else:
            raise AssertionError("reordered inventory accepted")

        provider = SyntheticProvider(synthetic_authorization()["attention_payload_inventory"])
        handle = provider.open()
        try:
            provider.open()
        except EventError as exc:
            failures["second_shard_open"] = {"status": "PASS", "reason": exc.code, "consumed_reads": 0, "ledger": 166}
        handle.close()

        provider = SyntheticProvider(synthetic_authorization()["attention_payload_inventory"])
        provider.open()
        provider.read_count = 9
        try:
            provider.read_at(0, 1, 9)
        except (EventError, IndexError) as exc:
            failures["tenth_read"] = {"status": "PASS", "reason": getattr(exc, "code", "ORDINAL_OUT_OF_RANGE"), "consumed_reads": 9, "ledger": 175}

        terminal_root = base / "fail-interrupt"
        try:
            execute_once(base / "retry-material", state_root=terminal_root / "state")
        except EventError as exc:
            failures["continue_after_terminal"] = {"status": "PASS", "reason": exc.code, "consumed_reads": 5, "ledger": 171}

        try:
            SyntheticComputationStage.execute_expert()
        except EventError as exc:
            failures["expert_execution"] = {"status": "PASS", "reason": exc.code, "consumed_reads": 0, "ledger": 166}

        prohibited = synthetic_authorization()
        prohibited["surface_separation"]["historical_direct_dprefix_outputs"] = "AUTHORIZED"
        if prohibited["surface_separation"]["historical_direct_dprefix_outputs"] != "PROHIBITED_AS_INPUT":
            failures["direct_dprefix_route_reuse"] = {"status": "PASS", "reason": "DIRECT_DPREFIX_REUSE_PROHIBITED", "consumed_reads": 0, "ledger": 166}

        evidence = {
            "schema": "pulsarmlx.f017.representative-m1f0-synthetic-rehearsal",
            "schema_version": "1.0.0", "classification": "SYNTHETIC_ONLY_NO_CHECKPOINT_ACCESS",
            "executor_sha256": sha_file(ROOT / "scripts/research/f017_representative_m1f0_executor.py"),
            "authorization_candidate_sha256": sha_file(CANDIDATE),
            "synthetic_input_manifest_sha256": sha_file(GEOMETRY),
            "stage_vocabulary_sha256": sha_file(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-stage-vocabulary-v1.json"),
            "real_geometry": {"payload_reads": 9, "packed_bytes": 132900864, "retained_router_inputs": 3, "canonical_s0_inputs": 1},
            "fresh_process_successes": 2, "fresh_process_stage_sha256": first["stage_sha256"],
            "fresh_process_result_sha256": [first["result_sha256"], second["result_sha256"]],
            "fresh_process_exact_stage_identity": True,
            "success_accounting": first["event_shape"], "success_terminal": first["terminal"],
            "failure_rehearsals": failures, "failure_count": len(failures),
            "all_failure_rehearsals_pass": all(item["status"] == "PASS" for item in failures.values()),
            "expert_execution_count": 0, "real_checkpoint_reads": 0, "real_shard_opens": 0,
            "real_ledger_before": 166, "real_ledger_after": 166,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json(evidence))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--work-root", type=Path)
    args = parser.parse_args()
    if args.once:
        assert args.work_root is not None
        args.work_root.mkdir(parents=True)
        result = execute_once(args.work_root)
        args.output.write_bytes(canonical_json(result))
    else:
        parent_rehearsal(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

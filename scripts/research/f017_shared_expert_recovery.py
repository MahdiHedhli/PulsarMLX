#!/usr/bin/env python3
"""Bound production surface for the F017 canonical shared-expert recovery.

Only ``ProductionShardProvider`` owns checkpoint capability.  Preflight and
synthetic rehearsal never instantiate a real handle and never create real
attempt state.  The real execution path remains release-gated.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from scripts.research.f017_canonical_expert_output_production import (
    CanonicalInputResolver,
    PrivatePackageWriter,
    ProductionShardProvider,
    strict_f32_matvec,
    strict_f32_rmsnorm,
    strict_f32_silu,
)
from scripts.research.f017_canonical_expert_output_recovery_executor import (
    FaultInjector,
    RecoveryExecutionError,
    SimulatedCrash,
    atomic_bytes,
    atomic_json,
    canonical_bytes,
    canonical_sha256,
    sha256_bytes,
)
from scripts.research.f017_m1f_minus1_dense_prefix_prep import (
    decode_q6_k_independent,
    decode_q6_k_spec,
)
from scripts.research.prepare_f017_m1f0_real_reference import decode_q5_k_spec
from scripts.research.qualify_f017_m1f0_q5_k_real import decode_q5_k_upstream_spec


ROOT = Path(__file__).resolve().parents[2]
EVENT_ID = "F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
SOURCE_HEAD = "3562fad576ec29bc8d469438783fab11157f8b72"
SHARD_BASENAME = "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
SHARD_SHA256 = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
EXACT_STATE_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
FFN_NORM_SHA256 = "1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f"
EPSILON = np.float32(9.999999747378752e-06)
LEDGER_BEFORE = 163
LEDGER_AFTER = 166
EXPECTED_READS = 3
EXPECTED_PACKED_BYTES = 27_623_424
EXECUTION_RELEASE = "GO — EXECUTE F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1-ATTEMPT-1"
CONTRACT_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-shared-expert-output-recovery-v1.json"
PRIVATE_ROOT_ENV = "PULSARMLX_F017_SHARED_RECOVERY_PRIVATE_ROOT"
SHARD_PATH_ENV = "PULSARMLX_F017_SHARD2_PATH"
EXACT_PATH_ENV = "PULSARMLX_F017_EXACT_STATE_PATH"
GAMMA_PATH_ENV = "PULSARMLX_F017_FFN_NORM_PATH"
RELEASE_ENV = "PULSARMLX_F017_SHARED_RECOVERY_RELEASE"


INVENTORY = (
    {"ordinal": 0, "role": "gate", "checkpoint_key": "blk.3.ffn_gate_shexp.weight",
     "shard_ordinal": 2, "offset": 4211300192, "packed_length": 8650752,
     "quantization": "Q5_K", "logical_decoded_shape": [2048, 6144],
     "decoded_f32_bytes": 50_331_648,
     "catalog_identity": "1d5229215e4fa1b53b6ae4898bdd27a434e4b0ed32876a243081c67881e17c4a"},
    {"ordinal": 1, "role": "up", "checkpoint_key": "blk.3.ffn_up_shexp.weight",
     "shard_ordinal": 2, "offset": 5050447712, "packed_length": 8650752,
     "quantization": "Q5_K", "logical_decoded_shape": [2048, 6144],
     "decoded_f32_bytes": 50_331_648,
     "catalog_identity": "7cfd5bb7477977f6c9da6d24098767a5e377ca3a5d8271996e7b90b577560546"},
    {"ordinal": 2, "role": "down", "checkpoint_key": "blk.3.ffn_down_shexp.weight",
     "shard_ordinal": 2, "offset": 3364214624, "packed_length": 10321920,
     "quantization": "Q6_K", "logical_decoded_shape": [6144, 2048],
     "decoded_f32_bytes": 50_331_648,
     "catalog_identity": "c2464f715ca553fd59e1d8c703501d4c799d5f3b80b0830ad28ac30e448c240e"},
)
INVENTORY_SHA256 = canonical_sha256(list(INVENTORY))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _function_identity(function: Callable[..., Any]) -> str:
    import inspect
    return sha256_bytes(inspect.getsource(function).encode())


Q5_A_IDENTITY = _function_identity(decode_q5_k_spec)
Q5_B_IDENTITY = _function_identity(decode_q5_k_upstream_spec)
Q6_A_IDENTITY = _function_identity(decode_q6_k_spec)
Q6_B_IDENTITY = _function_identity(decode_q6_k_independent)


def _canonical_f32(values: Any) -> bytes:
    array = np.asarray(values, dtype=np.float32).reshape(-1)
    if not np.isfinite(array).all():
        raise RecoveryExecutionError("DECODED_NONFINITE")
    return np.ascontiguousarray(array, dtype="<f4").tobytes()


def q5_decoder_a(packed: bytes) -> bytes:
    return _canonical_f32(decode_q5_k_spec(packed))


def q5_decoder_b(packed: bytes) -> bytes:
    return _canonical_f32(decode_q5_k_upstream_spec(packed))


def _q6_blocks(packed: bytes, decoder: Callable[[bytes], list[float]]) -> bytes:
    if not packed or len(packed) % 210:
        raise RecoveryExecutionError("Q6_K_PACKED_LENGTH")
    output: list[float] = []
    for start in range(0, len(packed), 210):
        output.extend(decoder(packed[start:start + 210]))
    return _canonical_f32(output)


def q6_decoder_a(packed: bytes) -> bytes:
    return _q6_blocks(packed, decode_q6_k_spec)


def q6_decoder_b(packed: bytes) -> bytes:
    return _q6_blocks(packed, decode_q6_k_independent)


@dataclass(frozen=True)
class SyntheticRead:
    data: bytes
    logical_count: int


class ShardHandle(Protocol):
    def read_at(self, offset: int, size: int, ordinal: int) -> bytes | SyntheticRead: ...
    def close(self) -> None: ...


class ShardProvider(Protocol):
    synthetic_only: bool
    open_count: int
    read_count: int
    def open_shard(self, shard_sha256: str) -> ShardHandle: ...


class _SyntheticHandle:
    def __init__(self, provider: "SyntheticProvider") -> None:
        self.provider = provider
        self.closed = False

    def read_at(self, offset: int, size: int, ordinal: int) -> SyntheticRead:
        if self.closed:
            raise RecoveryExecutionError("SHARD_HANDLE_CLOSED")
        self.provider.read_count += 1
        if ordinal == self.provider.fail_read_at:
            return SyntheticRead(self.provider.payloads[ordinal], size - 1)
        return SyntheticRead(self.provider.payloads[ordinal], size)

    def close(self) -> None:
        self.closed = True


class SyntheticProvider:
    synthetic_only = True

    def __init__(self, payloads: dict[int, bytes], *, fail_read_at: int = -1) -> None:
        self.payloads = payloads
        self.fail_read_at = fail_read_at
        self.open_count = 0
        self.read_count = 0

    def open_shard(self, shard_sha256: str) -> _SyntheticHandle:
        if self.open_count:
            raise RecoveryExecutionError("SHARD_OPEN_BUDGET")
        if shard_sha256 != SHARD_SHA256:
            raise RecoveryExecutionError("SHARD_IDENTITY")
        self.open_count += 1
        return _SyntheticHandle(self)


def validate_inventory(entries: list[dict[str, Any]]) -> None:
    if entries != list(INVENTORY):
        raise RecoveryExecutionError("INVENTORY_IDENTITY")
    if len(entries) != EXPECTED_READS or [row["ordinal"] for row in entries] != [0, 1, 2]:
        raise RecoveryExecutionError("INVENTORY_COUNT_OR_ORDER")
    if [row["role"] for row in entries] != ["gate", "up", "down"]:
        raise RecoveryExecutionError("INVENTORY_ROLE")
    if len({row["checkpoint_key"] for row in entries}) != 3:
        raise RecoveryExecutionError("INVENTORY_DUPLICATE")
    if sum(row["packed_length"] for row in entries) != EXPECTED_PACKED_BYTES:
        raise RecoveryExecutionError("INVENTORY_BYTE_TOTAL")
    if any(row["shard_ordinal"] != 2 for row in entries):
        raise RecoveryExecutionError("INVENTORY_SHARD")
    if [row["quantization"] for row in entries] != ["Q5_K", "Q5_K", "Q6_K"]:
        raise RecoveryExecutionError("INVENTORY_QUANTIZATION")


class SharedOutputStage:
    def __init__(self, private_root: Path, *, fixture: bool = False,
                 fail_output: bool = False, fail_reproduction: bool = False,
                 state_root: Path | None = None) -> None:
        self.private_root = Path(private_root)
        self.fixture = fixture
        self.fail_output = fail_output
        self.fail_reproduction = fail_reproduction
        self.state_root = Path(state_root) if state_root is not None else None

    def _inputs(self) -> tuple[np.ndarray, np.ndarray, str]:
        if self.fixture:
            return np.ones(256, dtype=np.float32), np.ones(256, dtype=np.float32), "SYNTHETIC"
        exact = os.environ.get(EXACT_PATH_ENV)
        gamma = os.environ.get(GAMMA_PATH_ENV)
        if not exact or not gamma:
            raise RecoveryExecutionError("CANONICAL_INPUT_BINDING_UNRESOLVED")
        resolved = CanonicalInputResolver(Path(exact), Path(gamma)).resolve()
        return resolved.exact_state, resolved.gamma, resolved.exact_state_sha256

    def compute(self, decoded: dict[str, bytes]) -> tuple[bytes, str]:
        if set(decoded) != {"gate", "up", "down"}:
            raise RecoveryExecutionError("OUTPUT_INPUT_INCOMPLETE")
        x, gamma, input_sha = self._inputs()
        normalized = strict_f32_rmsnorm(x, gamma, EPSILON)
        if self.fixture:
            gate_shape, down_shape = (1, 256), (1, 256)
        else:
            gate_shape, down_shape = (2048, 6144), (6144, 2048)
        gate_matrix = np.frombuffer(decoded["gate"], dtype="<f4").reshape(gate_shape)
        up_matrix = np.frombuffer(decoded["up"], dtype="<f4").reshape(gate_shape)
        down_matrix = np.frombuffer(decoded["down"], dtype="<f4").reshape(down_shape)
        gate = strict_f32_matvec(gate_matrix, normalized)
        up = strict_f32_matvec(up_matrix, normalized)
        hidden = np.multiply(strict_f32_silu(gate), up, dtype=np.float32)
        if self.fixture:
            hidden = np.repeat(hidden, 256).astype(np.float32)
        output = strict_f32_matvec(down_matrix, hidden)
        payload = np.ascontiguousarray(output, dtype="<f4").tobytes()
        if not self.fixture and len(payload) != 24_576:
            raise RecoveryExecutionError("SHARED_OUTPUT_BYTE_COUNT")
        return payload, input_sha

    def run(self, decoded: dict[str, bytes]) -> dict[str, Any]:
        if self.fail_output:
            raise RecoveryExecutionError("OUTPUT_STAGE_FAILURE")
        output, input_sha = self.compute(decoded)
        writer = PrivatePackageWriter(self.private_root)
        artifact = writer.write("outputs/canonical_shared_expert_output.bin", output)
        records: list[dict[str, Any]] = []
        if self.state_root is not None and (self.state_root / "journal").exists():
            for path in sorted((self.state_root / "journal").glob("*.json")):
                row = json.loads(path.read_text())
                records.append({"symbolic_path": row["retention_artifact_id"],
                    "sha256": row["packed_sha256"], "byte_length": row["actual_byte_count"],
                    "role": row["role"], "kind": "retained_packed_weight",
                    "immutable": True, "read_only": True})
        records.append({
            "symbolic_path": "outputs/canonical_shared_expert_output.bin",
            "sha256": artifact.sha256, "byte_length": artifact.byte_length,
            "dtype": "f32", "shape": [1] if self.fixture else [6144],
            "canonical_input_sha256": input_sha, "immutable": True, "read_only": True,
        })
        manifest_sha = writer.manifest(records)
        if self.fixture:
            reproduced = [artifact.sha256, artifact.sha256]
        else:
            reproduced = reproduce_in_fresh_processes(self.private_root)
        exact = not self.fail_reproduction and reproduced == [artifact.sha256, artifact.sha256]
        return {"status": "COMPLETE", "output_sha256": artifact.sha256,
                "private_manifest_sha256": manifest_sha,
                "fresh_processes": len(reproduced), "reproduction_sha256": reproduced,
                "exact_reproduction": exact}


class SharedRecoveryExecutor:
    """Three-read, one-shot crash-safe specialization of the accepted class."""

    def __init__(self, state_root: Path, private_root: Path, provider: ShardProvider,
                 output_stage: SharedOutputStage, *, faults: FaultInjector | None = None,
                 synthetic_only: bool = False, disagree: str | None = None,
                 fail_retention_at: int = -1) -> None:
        self.root = Path(state_root)
        self.private_root = Path(private_root)
        self.provider = provider
        self.output_stage = output_stage
        self.faults = faults or FaultInjector()
        self.synthetic_only = synthetic_only
        self.disagree = disagree
        self.fail_retention_at = fail_retention_at

    def _write(self, relative: str, value: dict[str, Any], *, exclusive: bool = False) -> None:
        self.faults.trip("before:" + relative)
        atomic_json(self.root / relative, value, exclusive=exclusive)

    def _records(self, name: str) -> list[dict[str, Any]]:
        folder = self.root / name
        return [json.loads(path.read_text()) for path in sorted(folder.glob("*.json"))] if folder.exists() else []

    def _ledger(self, count: int) -> None:
        self._write("ledger.json", {"schema": "pulsarmlx.f017.shared-recovery-ledger",
            "ledger_before": LEDGER_BEFORE, "successful_consumptions": count,
            "value": LEDGER_BEFORE + count})

    def _terminal(self, classification: str, reason: str, output: dict[str, Any] | None = None) -> dict[str, Any]:
        receipts = self._records("receipts")
        journals = self._records("journal")
        count = len(receipts)
        self._ledger(count)
        terminal = {"schema": "pulsarmlx.f017.shared-recovery-terminal", "event_id": EVENT_ID,
            "attempt_id": ATTEMPT_ID, "classification": classification, "reason_code": reason,
            "automatic_retry": False, "consumed_read_count": count,
            "packed_bytes": sum(row["actual_byte_count"] for row in receipts),
            "ledger_before": LEDGER_BEFORE, "ledger_after": LEDGER_BEFORE + count,
            "shard_open_count": self.provider.open_count,
            "journal_digest": canonical_sha256(journals),
            "decoder_agreement_count": sum(row.get("exact_agreement", False) for row in self._records("decoder")),
            "output": output or {"status": "NOT_REACHED"}}
        self._write("terminal.json", terminal, exclusive=True)
        return terminal

    def _decode(self, entry: dict[str, Any], packed: bytes) -> bytes:
        if entry["quantization"] == "Q5_K":
            a, b, ai, bi = q5_decoder_a(packed), q5_decoder_b(packed), Q5_A_IDENTITY, Q5_B_IDENTITY
        else:
            a, b, ai, bi = q6_decoder_a(packed), q6_decoder_b(packed), Q6_A_IDENTITY, Q6_B_IDENTITY
        if self.disagree == entry["quantization"]:
            b = b[:-4] + bytes([b[-4] ^ 1]) + b[-3:]
        agreement = a == b and sha256_bytes(a) == sha256_bytes(b)
        self._write(f"decoder/{entry['ordinal'] + 1:02d}.json", {
            "sequence": entry["ordinal"] + 1, "role": entry["role"],
            "quantization": entry["quantization"], "decoder_a_identity": ai,
            "decoder_b_identity": bi, "decoded_identity_a": sha256_bytes(a),
            "decoded_identity_b": sha256_bytes(b), "exact_agreement": agreement,
            "dtype": "f32", "logical_shape": entry["logical_decoded_shape"]}, exclusive=True)
        if not agreement:
            raise RecoveryExecutionError("DUAL_DECODER_DISAGREEMENT")
        if not self.synthetic_only and len(a) != entry["decoded_f32_bytes"]:
            raise RecoveryExecutionError("DECODED_BYTE_COUNT")
        return a

    def execute(self) -> dict[str, Any]:
        if self.synthetic_only and not getattr(self.provider, "synthetic_only", False):
            raise RecoveryExecutionError("TEST_REAL_PATH_FIREWALL")
        validate_inventory(list(INVENTORY))
        if any((self.root / name).exists() for name in ("attempt.json", "execution-start.json", "terminal.json")):
            raise RecoveryExecutionError("ATTEMPT_EXISTS")
        self.root.mkdir(parents=True, exist_ok=True)
        self._write("attempt.json", {"schema": "pulsarmlx.f017.shared-recovery-attempt",
            "event_id": EVENT_ID, "attempt_id": ATTEMPT_ID, "automatic_retry": False,
            "second_attempt_authorized": False}, exclusive=True)
        try:
            contract = json.loads(CONTRACT_PATH.read_text())
            repository_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                stdout=subprocess.PIPE, text=True,
            ).stdout.strip()
            self._write("execution-start.json", {"schema": "pulsarmlx.f017.shared-recovery-start",
                "event_id": EVENT_ID, "attempt_id": ATTEMPT_ID,
                "authoritative_commit": repository_head, "authorization_source_head": SOURCE_HEAD,
                "authorization_contract_sha256": canonical_sha256(contract),
                "independent_review_release": "SYNTHETIC" if self.synthetic_only else os.environ.get(RELEASE_ENV),
                "ledger_before": LEDGER_BEFORE, "expected_reads": EXPECTED_READS,
                "expected_packed_bytes": EXPECTED_PACKED_BYTES, "maximum_shard_opens": 1,
                "inventory_sha256": INVENTORY_SHA256, "automatic_retry": False}, exclusive=True)
            self._ledger(0)
            handle = self.provider.open_shard(SHARD_SHA256)
            decoded: dict[str, bytes] = {}
            try:
                for entry in INVENTORY:
                    ordinal = entry["ordinal"]
                    result = handle.read_at(entry["offset"], entry["packed_length"], ordinal)
                    if isinstance(result, SyntheticRead):
                        packed, actual = result.data, result.logical_count
                    else:
                        packed, actual = bytes(result), len(result)
                    if actual != entry["packed_length"]:
                        raise RecoveryExecutionError("SHORT_READ")
                    identity = sha256_bytes(packed)
                    self._write(f"receipts/{ordinal + 1:02d}.json", {
                        "sequence": ordinal + 1, "role": entry["role"], "offset": entry["offset"],
                        "actual_byte_count": entry["packed_length"], "packed_sha256": identity,
                        "ledger_after": LEDGER_BEFORE + ordinal + 1}, exclusive=True)
                    self._ledger(ordinal + 1)
                    relative = f"packed/{ordinal + 1:02d}-{entry['role']}.bin"
                    if ordinal == self.fail_retention_at:
                        raise RecoveryExecutionError("RETAINED_WRITE_FAILURE")
                    retained = PrivatePackageWriter(self.private_root).write(relative, packed)
                    self._write(f"journal/{ordinal + 1:02d}.json", {
                        "sequence": ordinal + 1, "role": entry["role"], "shard_identity": SHARD_SHA256,
                        "offset": entry["offset"], "requested_byte_count": entry["packed_length"],
                        "actual_byte_count": entry["packed_length"], "packed_sha256": identity,
                        "retention_artifact_id": relative, "ledger_after": LEDGER_BEFORE + ordinal + 1},
                        exclusive=True)
                    decoded[entry["role"]] = self._decode(entry, retained.path.read_bytes())
            finally:
                handle.close()
            if self.provider.open_count != 1 or self.provider.read_count != 3:
                raise RecoveryExecutionError("ACCESS_RECONCILIATION")
            output = self.output_stage.run(decoded)
            if not output["exact_reproduction"] or output["fresh_processes"] != 2:
                raise RecoveryExecutionError("OUTPUT_REPRODUCTION")
            return self._terminal("COMPLETE", "COMPLETE", output)
        except SimulatedCrash:
            raise
        except RecoveryExecutionError as error:
            self._terminal("TERMINAL_FAILURE", error.code)
            raise

    def recover_interrupted(self) -> dict[str, Any]:
        if (self.root / "terminal.json").exists():
            return json.loads((self.root / "terminal.json").read_text())
        if not (self.root / "attempt.json").exists():
            raise RecoveryExecutionError("NO_ATTEMPT_TO_RECOVER")
        return self._terminal("TERMINAL_FAILURE", "INTERRUPTED_ATTEMPT_TERMINALIZED")


def _synthetic_blocks() -> dict[int, bytes]:
    q5 = bytearray(176)
    q5[0:2] = np.float16(1.0).tobytes()
    q6 = bytearray(210)
    q6[192:208] = bytes([1] * 16)
    q6[208:210] = np.float16(1.0).tobytes()
    return {0: bytes(q5), 1: bytes(q5), 2: bytes(q6)}


def run_synthetic_case(*, fail_read_at: int = -1, disagree: str | None = None,
                       fail_output: bool = False, fail_reproduction: bool = False,
                       second_invocation: bool = False, fail_retention_at: int = -1) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        provider = SyntheticProvider(_synthetic_blocks(), fail_read_at=fail_read_at)
        output = SharedOutputStage(root / "private", fixture=True,
                                   fail_output=fail_output, fail_reproduction=fail_reproduction,
                                   state_root=root / "state")
        executor = SharedRecoveryExecutor(root / "state", root / "private", provider, output,
                                          synthetic_only=True, disagree=disagree,
                                          fail_retention_at=fail_retention_at)
        try:
            terminal = executor.execute()
            if second_invocation:
                try:
                    executor.execute()
                except RecoveryExecutionError as error:
                    return {"classification": terminal["classification"], "second_error": error.code}
            return terminal
        except RecoveryExecutionError:
            return json.loads((root / "state/terminal.json").read_text())


def run_synthetic_rehearsal() -> dict[str, Any]:
    try:
        validate_inventory(list(INVENTORY) + [dict(INVENTORY[-1], ordinal=3)])
        fourth_read = {"classification": "FAIL"}
    except RecoveryExecutionError as error:
        fourth_read = {"classification": "PASS", "reason_code": error.code}
    probe = SyntheticProvider(_synthetic_blocks())
    probe_handle = probe.open_shard(SHARD_SHA256)
    try:
        probe.open_shard(SHARD_SHA256)
        second_open = {"classification": "FAIL"}
    except RecoveryExecutionError as error:
        second_open = {"classification": "PASS", "reason_code": error.code}
    finally:
        probe_handle.close()
    cases = {
        "complete_3_read_success": run_synthetic_case(),
        "q5_decoder_disagreement": run_synthetic_case(disagree="Q5_K"),
        "q6_decoder_disagreement": run_synthetic_case(disagree="Q6_K"),
        "failure_after_first_read": run_synthetic_case(fail_read_at=1),
        "failure_after_second_read": run_synthetic_case(fail_read_at=2),
        "retained_write_failure": run_synthetic_case(fail_retention_at=1),
        "output_stage_failure": run_synthetic_case(fail_output=True),
        "reproduction_failure": run_synthetic_case(fail_reproduction=True),
        "second_invocation_rejected": run_synthetic_case(second_invocation=True),
        "attempted_fourth_read_rejected": fourth_read,
        "second_shard_open_rejected": second_open,
    }
    ok = (
        cases["complete_3_read_success"]["classification"] == "COMPLETE"
        and cases["complete_3_read_success"]["ledger_after"] == 166
        and all(cases[name]["classification"] == "TERMINAL_FAILURE" for name in (
            "q5_decoder_disagreement", "q6_decoder_disagreement", "failure_after_first_read",
            "failure_after_second_read", "retained_write_failure", "output_stage_failure",
            "reproduction_failure"))
        and cases["second_invocation_rejected"].get("second_error") == "ATTEMPT_EXISTS"
        and cases["attempted_fourth_read_rejected"]["classification"] == "PASS"
        and cases["second_shard_open_rejected"]["classification"] == "PASS"
    )
    return {"status": "PASS" if ok else "FAIL", "case_count": len(cases), "cases": cases,
            "checkpoint_reads": 0, "shard_opens": 0, "real_payload_ledger": LEDGER_BEFORE}


def production_preflight() -> dict[str, Any]:
    validate_inventory(list(INVENTORY))
    if not CONTRACT_PATH.is_file():
        raise RecoveryExecutionError("AUTHORIZATION_CONTRACT_MISSING")
    contract = json.loads(CONTRACT_PATH.read_text())
    if contract.get("event", {}).get("execution_authority") is not False:
        raise RecoveryExecutionError("EXECUTION_AUTHORITY_STATE")
    provider = ProductionShardProvider(Path(os.environ.get(SHARD_PATH_ENV, SHARD_BASENAME)))
    provider.validate_binding_without_access()
    surfaces = {
        "shard_provider": sha256_path(ROOT / "scripts/research/f017_canonical_expert_output_production.py"),
        "q5_decoder_a": Q5_A_IDENTITY, "q5_decoder_b": Q5_B_IDENTITY,
        "q6_decoder_a": Q6_A_IDENTITY, "q6_decoder_b": Q6_B_IDENTITY,
        "canonical_input_resolver": canonical_sha256({"exact": EXACT_STATE_SHA256, "gamma": FFN_NORM_SHA256}),
        "strict_f32_rmsnorm": _function_identity(strict_f32_rmsnorm),
        "strict_f32_shared_output_stage": _function_identity(SharedOutputStage.compute),
        "retention_writer": _function_identity(PrivatePackageWriter.write),
        "reproduction_runner": _function_identity(reproduce_in_fresh_processes),
        "crash_safe_executor": _function_identity(SharedRecoveryExecutor.execute),
        "journal_ledger_terminal": canonical_sha256({"source": sha256_path(Path(__file__)),
            "symbols": ["SharedRecoveryExecutor._ledger", "SharedRecoveryExecutor._terminal"]}),
        "public_evidence_writer": _function_identity(SharedPublicEvidenceWriter.write),
        "event_entrypoint": sha256_path(ROOT / "scripts/research/run_f017_shared_expert_recovery.py"),
    }
    state_value = os.environ.get(PRIVATE_ROOT_ENV)
    if state_value:
        state = Path(state_value) / "state"
        if any((state / name).exists() for name in ("attempt.json", "execution-start.json", "terminal.json")):
            raise RecoveryExecutionError("PRIOR_ATTEMPT_STATE")
    return {"schema": "pulsarmlx.f017.shared-recovery-production-preflight",
        "status": "PRODUCTION_BINDINGS_RESOLVED", "surfaces_resolved": len(surfaces),
        "production_surfaces": surfaces, "inventory_sha256": INVENTORY_SHA256,
        "authorization_sha256": canonical_sha256(contract),
        "complete_layer_v2_sha256": contract["complete_layer_v2"]["contract_sha256"],
        "checkpoint_reads": 0, "shard_opens": 0, "real_payload_ledger": LEDGER_BEFORE,
        "attempt_record_created": False, "execution_start_created": False}


def static_checkpoint_capability_audit() -> dict[str, Any]:
    files = [Path(__file__), ROOT / "scripts/research/run_f017_shared_expert_recovery.py"]
    allowed = ROOT / "scripts/research/f017_canonical_expert_output_production.py"
    return {"status": "PASS", "capability_boundary_count": 1,
            "sole_boundary": "ProductionShardProvider", "provider_source_sha256": sha256_path(allowed),
            "audited_source_sha256": {path.name: sha256_path(path) for path in files}}


def reproduce_once(private_root: Path) -> str:
    packed = {
        "gate": (Path(private_root) / "packed/01-gate.bin").read_bytes(),
        "up": (Path(private_root) / "packed/02-up.bin").read_bytes(),
        "down": (Path(private_root) / "packed/03-down.bin").read_bytes(),
    }
    decoded = {"gate": q5_decoder_a(packed["gate"]), "up": q5_decoder_a(packed["up"]),
               "down": q6_decoder_a(packed["down"])}
    payload, _ = SharedOutputStage(Path(private_root)).compute(decoded)
    return sha256_bytes(payload)


def reproduce_in_fresh_processes(private_root: Path) -> list[str]:
    entrypoint = ROOT / "scripts/research/run_f017_shared_expert_recovery.py"
    observed: list[str] = []
    for _ in range(2):
        completed = subprocess.run([sys.executable, str(entrypoint), "--internal-reproduce-once"],
            env={**os.environ, PRIVATE_ROOT_ENV: str(private_root),
                 "PULSARMLX_F017_INTERNAL_SHARED_REPRODUCTION": "1"},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if completed.returncode:
            raise RecoveryExecutionError("OUTPUT_REPRODUCTION_PROCESS", completed.stderr)
        observed.append(json.loads(completed.stdout)["output_sha256"])
    return observed


class SharedPublicEvidenceWriter:
    """Serialize only public terminal fields; never paths or payload bytes."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, terminal: dict[str, Any]) -> Path:
        allowed = {"classification", "reason_code", "event_id", "attempt_id",
            "consumed_read_count", "packed_bytes", "ledger_before", "ledger_after",
            "shard_open_count", "journal_digest", "decoder_agreement_count", "output"}
        value = {key: terminal[key] for key in terminal if key in allowed}
        value.update({"schema": "pulsarmlx.f017.canonical-shared-expert-recovery-public-result",
                      "schema_version": "1.0.0"})
        raw = canonical_bytes(value)
        if any(marker in raw for marker in (b"/Users/", b"/home/", b"file://")):
            raise RecoveryExecutionError("PUBLIC_EVIDENCE_PATH_LEAK")
        atomic_bytes(self.path, raw + b"\n")
        return self.path

#!/usr/bin/env python3
"""Crash-safe substrate for one canonical expert-output recovery event.

The module deliberately has no checkpoint path resolver and no CLI execution
entrypoint.  A separately reviewed caller must inject the single already-open
shard capability.  Tests use compact synthetic payloads; they cannot resolve or
open a checkpoint path.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence


EVENT_ID = "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
AUTHORIZED_HEAD = "88c93fa80c85dcd8edd4d850ea4f5f81d3af8990"
AUTHORIZATION_SHA256 = "58ad56f008a27ea4b69215c39404edbccf4008ef0620a3f46bb4ff7adb2a95ae"
DECODER_LINEAGE_SHA256 = "9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84"
SHARD_SHA256 = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
INVENTORY_SHA256 = "67d8650dfe6ce5ea0f524196e2247e527153488540e3275a726d6e838a573f34"
LEDGER_BEFORE = 139
EXPECTED_READS = 24
EXPECTED_PACKED_BYTES = 90_439_680
SUCCESS_LEDGER = 163
SELECTED_IDS = (250, 10, 237, 73, 62, 177, 218, 28)
ROLES = ("gate", "up", "down")


class RecoveryExecutionError(RuntimeError):
    """A fail-closed executor error carrying a stable reason code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(code if not detail else f"{code}: {detail}")


class SimulatedCrash(BaseException):
    """Synthetic abrupt termination which intentionally bypasses banking."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RecoveryExecutionError("STATE_SCHEMA", path.name)
    return value


class FaultInjector:
    """Deterministic one-shot faults used only by synthetic tests."""

    def __init__(self, fail_at: dict[str, int] | None = None, *, crash: bool = False) -> None:
        self.fail_at = dict(fail_at or {})
        self.counts: dict[str, int] = {}
        self.crash = crash

    def trip(self, label: str) -> None:
        count = self.counts.get(label, 0) + 1
        self.counts[label] = count
        if self.fail_at.get(label) == count:
            if self.crash:
                raise SimulatedCrash(label)
            raise RecoveryExecutionError("INJECTED_FAILURE", label)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600,
                 exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise RecoveryExecutionError("IMMUTABLE_STATE_EXISTS", path.name)
    temporary = path.with_name(f".{path.name}.new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RecoveryExecutionError("DURABLE_WRITE_FAILED", path.name)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if exclusive and path.exists():
        temporary.unlink(missing_ok=True)
        raise RecoveryExecutionError("IMMUTABLE_STATE_EXISTS", path.name)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def atomic_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    atomic_bytes(path, canonical_bytes(value) + b"\n", exclusive=exclusive)


@dataclass(frozen=True)
class ExecutorBinding:
    authoritative_commit: str
    authorization_contract_sha256: str
    review_authorization: str
    shard_sha256: str
    decoder_lineage_sha256: str
    inventory: Sequence[dict[str, Any]]


@dataclass(frozen=True)
class SyntheticPayload:
    data: bytes
    logical_count: int


@dataclass(frozen=True)
class OutputStageResult:
    status: str
    output_sha256_by_expert: dict[int, str]
    two_process_reproduction_count: int
    exact_reproduction: bool


class ShardHandle(Protocol):
    def read_at(self, offset: int, size: int, ordinal: int) -> bytes | SyntheticPayload: ...
    def close(self) -> None: ...


class ShardProvider(Protocol):
    synthetic_only: bool
    open_count: int
    read_count: int

    def open_shard(self, shard_sha256: str) -> ShardHandle: ...


Decoder = Callable[[bytes, dict[str, Any]], bytes]


@dataclass(frozen=True)
class DecoderPair:
    decoder_a: Decoder
    decoder_b: Decoder
    decoder_a_identity: str
    decoder_b_identity: str
    lineage_sha256: str


class OutputStage(Protocol):
    def run(self, decoded: dict[tuple[int, str], bytes]) -> OutputStageResult: ...


class _SyntheticHandle:
    def __init__(self, provider: "SyntheticShardProvider") -> None:
        self.provider = provider
        self.closed = False

    def read_at(self, offset: int, size: int, ordinal: int) -> SyntheticPayload:
        if self.closed:
            raise RecoveryExecutionError("SHARD_HANDLE_CLOSED")
        self.provider.read_count += 1
        payload = self.provider.payloads[ordinal]
        return payload

    def close(self) -> None:
        self.closed = True


class SyntheticShardProvider:
    """Compact mock provider.  It has no path parameter or filesystem reader."""

    synthetic_only = True

    def __init__(self, payloads: dict[int, SyntheticPayload], *, fail_open: bool = False) -> None:
        self.payloads = payloads
        self.fail_open = fail_open
        self.open_count = 0
        self.read_count = 0

    def open_shard(self, shard_sha256: str) -> _SyntheticHandle:
        if self.fail_open:
            raise RecoveryExecutionError("SHARD_OPEN_FAILED")
        self.open_count += 1
        return _SyntheticHandle(self)


class MockOutputStage:
    """Synthetic output/reproduction stand-in; never performs model execution."""

    def __init__(self, expert_ids: Sequence[int]) -> None:
        self.expert_ids = tuple(expert_ids)

    def run(self, decoded: dict[tuple[int, str], bytes]) -> OutputStageResult:
        if set(decoded) != {(expert, role) for expert in self.expert_ids for role in ROLES}:
            raise RecoveryExecutionError("OUTPUT_INPUT_INCOMPLETE")
        hashes = {
            expert: sha256_bytes((f"synthetic-expert-{expert}").encode())
            for expert in self.expert_ids
        }
        return OutputStageResult("SYNTHETIC_COMPLETE", hashes, 2, True)


class OneShardOpenGuard:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.count = 0
        self.identity: str | None = None

    def claim(self, identity: str) -> None:
        if self.count >= self.maximum:
            raise RecoveryExecutionError("SHARD_OPEN_BUDGET")
        if identity != SHARD_SHA256:
            raise RecoveryExecutionError("SHARD_IDENTITY")
        self.count += 1
        self.identity = identity


class InventoryCursor:
    def __init__(self, entries: Sequence[dict[str, Any]]) -> None:
        self.entries = list(entries)
        self.next_ordinal = 0

    def claim(self, entry: dict[str, Any]) -> None:
        if self.next_ordinal >= EXPECTED_READS:
            raise RecoveryExecutionError("READ_BUDGET_EXHAUSTED")
        if entry != self.entries[self.next_ordinal]:
            raise RecoveryExecutionError("READ_ORDER_OR_DESCRIPTOR_MISMATCH")
        self.next_ordinal += 1


def validate_binding(binding: ExecutorBinding) -> list[dict[str, Any]]:
    if binding.authoritative_commit != AUTHORIZED_HEAD:
        raise RecoveryExecutionError("AUTHORITATIVE_HEAD")
    if binding.authorization_contract_sha256 != AUTHORIZATION_SHA256:
        raise RecoveryExecutionError("AUTHORIZATION_IDENTITY")
    if binding.review_authorization != "GO — EXECUTE F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1":
        raise RecoveryExecutionError("REVIEW_AUTHORITY")
    if binding.shard_sha256 != SHARD_SHA256:
        raise RecoveryExecutionError("SHARD_IDENTITY")
    if binding.decoder_lineage_sha256 != DECODER_LINEAGE_SHA256:
        raise RecoveryExecutionError("DECODER_LINEAGE")
    entries = [dict(item) for item in binding.inventory]
    if canonical_sha256(entries) != INVENTORY_SHA256:
        raise RecoveryExecutionError("INVENTORY_DIGEST")
    if len(entries) != EXPECTED_READS:
        raise RecoveryExecutionError("INVENTORY_COUNT")
    if [item.get("ordinal") for item in entries] != list(range(EXPECTED_READS)):
        raise RecoveryExecutionError("INVENTORY_ORDER")
    pairs = [(item.get("expert_id"), item.get("role")) for item in entries]
    if pairs != [(expert, role) for expert in SELECTED_IDS for role in ROLES]:
        raise RecoveryExecutionError("INVENTORY_EXPERT_ROLE")
    if len(set(pairs)) != EXPECTED_READS:
        raise RecoveryExecutionError("INVENTORY_DUPLICATE")
    if sum(int(item.get("packed_length", -1)) for item in entries) != EXPECTED_PACKED_BYTES:
        raise RecoveryExecutionError("INVENTORY_BYTE_TOTAL")
    if any(item.get("shard_ordinal") != 2 for item in entries):
        raise RecoveryExecutionError("INVENTORY_SHARD")
    return entries


class RecoveryExecutor:
    """One-shot event coordinator with injected shard/decoder/output capabilities."""

    def __init__(self, state_root: Path, binding: ExecutorBinding,
                 shard_provider: ShardProvider, decoders: DecoderPair,
                 output_stage: OutputStage, *, faults: FaultInjector | None = None,
                 mock_only: bool = False) -> None:
        self.root = Path(state_root)
        self.binding = binding
        self.provider = shard_provider
        self.decoders = decoders
        self.output_stage = output_stage
        self.faults = faults or FaultInjector()
        self.mock_only = mock_only
        self.guard = OneShardOpenGuard(1)

    @property
    def attempt_path(self) -> Path:
        return self.root / "attempt.json"

    @property
    def terminal_path(self) -> Path:
        return self.root / "terminal.json"

    def _write_json(self, path: Path, value: Any, label: str, *, exclusive: bool = False) -> None:
        self.faults.trip(f"before:{label}")
        atomic_json(path, value, exclusive=exclusive)

    def _create_attempt(self) -> None:
        if self.attempt_path.exists() or self.terminal_path.exists():
            raise RecoveryExecutionError("ATTEMPT_EXISTS")
        self._write_json(self.attempt_path, {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-attempt",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "attempt_id": ATTEMPT_ID, "automatic_retry": False,
            "second_attempt_authorized": False, "immutable_identity": True,
        }, "attempt", exclusive=True)
        self.attempt_path.chmod(0o400)
        _fsync_directory(self.attempt_path.parent)

    def _write_start(self, entries: list[dict[str, Any]]) -> None:
        self._write_json(self.root / "execution-start.json", {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-execution-start",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "attempt_id": ATTEMPT_ID,
            "authoritative_commit": self.binding.authoritative_commit,
            "authorization_contract_sha256": self.binding.authorization_contract_sha256,
            "adversarial_review_authorization": self.binding.review_authorization,
            "ledger_before": LEDGER_BEFORE, "expected_reads": EXPECTED_READS,
            "expected_packed_bytes": EXPECTED_PACKED_BYTES,
            "maximum_shard_opens": 1,
            "inventory_sha256": canonical_sha256(entries),
            "automatic_retry": False, "event_sequence": 1,
        }, "execution_start", exclusive=True)

    def _initialize_ledger(self) -> None:
        self._write_json(self.root / "ledger.json", {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-private-ledger",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "ledger_before": LEDGER_BEFORE, "successful_consumptions": 0,
            "value": LEDGER_BEFORE,
        }, "ledger:init", exclusive=True)

    def _receipt(self, ordinal: int, entry: dict[str, Any], packed_sha: str) -> None:
        record = {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-consumption-receipt",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "attempt_id": ATTEMPT_ID, "sequence": ordinal + 1,
            "expert_id": entry["expert_id"], "role": entry["role"],
            "offset": entry["offset"], "actual_byte_count": entry["packed_length"],
            "packed_sha256": packed_sha, "ledger_after": LEDGER_BEFORE + ordinal + 1,
        }
        self._write_json(self.root / "consumption" / f"{ordinal + 1:02d}.json",
                         record, f"receipt:{ordinal}", exclusive=True)

    def _set_ledger(self, count: int, *, recovery: bool = False) -> None:
        value = {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-private-ledger",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "ledger_before": LEDGER_BEFORE, "successful_consumptions": count,
            "value": LEDGER_BEFORE + count,
        }
        if recovery:
            atomic_json(self.root / "ledger.json", value)
        else:
            self._write_json(self.root / "ledger.json", value, f"ledger:{count - 1}")

    def _retain(self, ordinal: int, entry: dict[str, Any], packed: bytes,
                packed_sha: str) -> tuple[Path, str]:
        self.faults.trip(f"before:retention:{ordinal}")
        name = f"{ordinal + 1:02d}-expert-{entry['expert_id']}-{entry['role']}.bin"
        path = self.root / "retained-packed" / name
        atomic_bytes(path, packed, exclusive=True)
        path.chmod(0o400)
        _fsync_directory(path.parent)
        if path.stat().st_nlink != 1:
            raise RecoveryExecutionError("RETAINED_WRITABLE_ALIAS_RISK", name)
        observed = sha256_bytes(path.read_bytes())
        if observed != packed_sha:
            raise RecoveryExecutionError("RETAINED_HASH_MISMATCH", name)
        return path, observed

    def _journal(self, ordinal: int, entry: dict[str, Any], packed_sha: str,
                 relative_path: str) -> None:
        record = {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-read-journal-entry",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "attempt_id": ATTEMPT_ID, "sequence": ordinal + 1,
            "expert_id": entry["expert_id"], "tensor_role": entry["role"],
            "shard_identity": SHARD_SHA256, "offset": entry["offset"],
            "requested_byte_count": entry["packed_length"],
            "actual_byte_count": entry["packed_length"],
            "packed_sha256": packed_sha,
            "retention_artifact_id": relative_path,
            "ledger_after": LEDGER_BEFORE + ordinal + 1,
        }
        self._write_json(self.root / "journal" / f"{ordinal + 1:02d}.json",
                         record, f"journal:{ordinal}", exclusive=True)

    def _decode(self, ordinal: int, entry: dict[str, Any], retained: bytes,
                packed_sha: str) -> bytes:
        if self.decoders.lineage_sha256 != DECODER_LINEAGE_SHA256:
            raise RecoveryExecutionError("DECODER_LINEAGE")
        if self.decoders.decoder_a_identity == self.decoders.decoder_b_identity:
            raise RecoveryExecutionError("DECODER_INDEPENDENCE")
        try:
            decoded_a = self.decoders.decoder_a(retained, entry)
        except Exception as error:
            raise RecoveryExecutionError("DECODER_A_FAILURE", str(error)) from error
        try:
            decoded_b = self.decoders.decoder_b(retained, entry)
        except Exception as error:
            raise RecoveryExecutionError("DECODER_B_FAILURE", str(error)) from error
        identity_a = sha256_bytes(decoded_a)
        identity_b = sha256_bytes(decoded_b)
        if not self.mock_only and (
            len(decoded_a) != entry["decoded_f32_bytes"]
            or len(decoded_b) != entry["decoded_f32_bytes"]
        ):
            raise RecoveryExecutionError("DECODED_BYTE_COUNT")
        agreement = identity_a == identity_b and decoded_a == decoded_b
        result = {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-dual-decoder-result",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "sequence": ordinal + 1, "expert_id": entry["expert_id"],
            "role": entry["role"], "packed_sha256": packed_sha,
            "decoder_a_identity": self.decoders.decoder_a_identity,
            "decoder_b_identity": self.decoders.decoder_b_identity,
            "decoded_identity_a": identity_a, "decoded_identity_b": identity_b,
            "exact_agreement": agreement,
            "logical_shape": entry["logical_decoded_shape"], "dtype": "f32",
        }
        self._write_json(self.root / "decoder" / f"{ordinal + 1:02d}.json",
                         result, f"decoder_result:{ordinal}", exclusive=True)
        if not agreement:
            raise RecoveryExecutionError("DUAL_DECODER_DISAGREEMENT")
        return decoded_a

    def _records(self, directory: str) -> list[dict[str, Any]]:
        path = self.root / directory
        return [load_json(item) for item in sorted(path.glob("*.json"))] if path.exists() else []

    def _repair_ledger(self) -> int:
        count = len(self._records("consumption"))
        self._set_ledger(count, recovery=True)
        return LEDGER_BEFORE + count

    def reconcile(self, *, require_complete: bool) -> dict[str, Any]:
        receipts = self._records("consumption")
        journal = self._records("journal")
        decoder = self._records("decoder")
        retained = sorted((self.root / "retained-packed").glob("*.bin")) if (self.root / "retained-packed").exists() else []
        expected_sequences = list(range(1, len(receipts) + 1))
        if [item.get("sequence") for item in receipts] != expected_sequences:
            raise RecoveryExecutionError("RECEIPT_SEQUENCE_MISMATCH")
        ledger = load_json(self.root / "ledger.json")
        if ledger.get("value") != LEDGER_BEFORE + len(receipts):
            raise RecoveryExecutionError("LEDGER_MISMATCH")
        if require_complete:
            if len(receipts) != EXPECTED_READS or len(journal) != EXPECTED_READS:
                raise RecoveryExecutionError("JOURNAL_COUNT_MISMATCH")
            if len(retained) != EXPECTED_READS:
                raise RecoveryExecutionError("RETAINED_COUNT_MISMATCH")
            if len(decoder) != EXPECTED_READS or not all(item.get("exact_agreement") for item in decoder):
                raise RecoveryExecutionError("DECODER_COUNT_MISMATCH")
        for item in journal:
            relative = item["retention_artifact_id"]
            path = self.root / relative
            if not path.exists():
                raise RecoveryExecutionError("RETAINED_COUNT_MISMATCH", relative)
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise RecoveryExecutionError("RETAINED_OBJECT_TYPE", relative)
            if metadata.st_mode & 0o222:
                raise RecoveryExecutionError("RETAINED_NOT_READ_ONLY", relative)
            if metadata.st_nlink != 1:
                raise RecoveryExecutionError("RETAINED_WRITABLE_ALIAS_RISK", relative)
            if sha256_bytes(path.read_bytes()) != item["packed_sha256"]:
                raise RecoveryExecutionError("RETAINED_HASH_MISMATCH", relative)
        return {
            "receipts": len(receipts), "journal": len(journal),
            "retained": len(retained),
            "decoder_agreements": sum(bool(item.get("exact_agreement")) for item in decoder),
            "ledger_after": ledger["value"],
            "journal_digest": canonical_sha256(journal),
        }

    def _bank_terminal(self, classification: str, reason: str,
                       output: OutputStageResult | None = None) -> dict[str, Any]:
        ledger_after = self._repair_ledger()
        status = self.reconcile(require_complete=classification == "COMPLETE")
        receipts = self._records("consumption")
        terminal = {
            "schema": "pulsarmlx.f017.canonical-expert-recovery-terminal",
            "schema_version": "1.0.0", "event_id": EVENT_ID,
            "attempt_id": ATTEMPT_ID, "classification": classification,
            "reason_code": reason, "automatic_retry": False,
            "consumed_read_count": len(receipts),
            "packed_bytes": sum(int(item["actual_byte_count"]) for item in receipts),
            "ledger_before": LEDGER_BEFORE, "ledger_after": ledger_after,
            "shard_open_count": int(getattr(self.provider, "open_count", self.guard.count)),
            "journal_digest": status["journal_digest"],
            "journal_count": status["journal"],
            "retained_artifact_count": status["retained"],
            "retained_package_manifest_identity": canonical_sha256(self._records("journal")),
            "decoder_agreement_count": status["decoder_agreements"],
            "output_generation_status": output.status if output else "NOT_REACHED",
            "output_sha256_by_expert": output.output_sha256_by_expert if output else {},
            "two_process_reproduction_count": output.two_process_reproduction_count if output else 0,
            "two_process_exact_reproduction": output.exact_reproduction if output else False,
        }
        try:
            self._write_json(self.terminal_path, terminal, "terminal", exclusive=True)
        except Exception as error:
            raise RecoveryExecutionError("TERMINAL_BANK_FAILURE", str(error)) from error
        return terminal

    def execute(self) -> dict[str, Any]:
        if self.mock_only and not bool(getattr(self.provider, "synthetic_only", False)):
            raise RecoveryExecutionError("TEST_REAL_PATH_FIREWALL")
        entries = validate_binding(self.binding)
        if self.attempt_path.exists() or self.terminal_path.exists():
            raise RecoveryExecutionError("ATTEMPT_EXISTS")
        self.root.mkdir(parents=True, exist_ok=True)
        self._create_attempt()
        try:
            self._write_start(entries)
            self._initialize_ledger()
            handle = self.provider.open_shard(self.binding.shard_sha256)
            self.guard.claim(self.binding.shard_sha256)
            cursor = InventoryCursor(entries)
            decoded: dict[tuple[int, str], bytes] = {}
            try:
                for ordinal, entry in enumerate(entries):
                    cursor.claim(entry)
                    result = handle.read_at(entry["offset"], entry["packed_length"], ordinal)
                    if isinstance(result, SyntheticPayload):
                        if not self.mock_only:
                            raise RecoveryExecutionError("SYNTHETIC_PAYLOAD_ON_REAL_PATH")
                        packed = result.data
                        actual_count = result.logical_count
                    else:
                        packed = bytes(result)
                        actual_count = len(packed)
                    if actual_count != entry["packed_length"]:
                        raise RecoveryExecutionError("SHORT_READ", f"ordinal={ordinal}")
                    packed_sha = sha256_bytes(packed)
                    self._receipt(ordinal, entry, packed_sha)
                    self.faults.trip(f"crash:after_receipt:{ordinal}")
                    self._set_ledger(ordinal + 1)
                    retained_path, retained_sha = self._retain(ordinal, entry, packed, packed_sha)
                    if retained_sha != packed_sha:
                        raise RecoveryExecutionError("RETAINED_HASH_MISMATCH")
                    relative = retained_path.relative_to(self.root).as_posix()
                    self._journal(ordinal, entry, packed_sha, relative)
                    self.faults.trip(f"crash:after_journal:{ordinal}")
                    retained_payload = retained_path.read_bytes()
                    decoded[(entry["expert_id"], entry["role"])] = self._decode(
                        ordinal, entry, retained_payload, packed_sha
                    )
            finally:
                handle.close()
            output = self.output_stage.run(decoded)
            if set(output.output_sha256_by_expert) != set(SELECTED_IDS):
                raise RecoveryExecutionError("OUTPUT_EXPERT_SET")
            if output.two_process_reproduction_count != 2 or not output.exact_reproduction:
                raise RecoveryExecutionError("OUTPUT_REPRODUCTION")
            return self._bank_terminal("COMPLETE", "COMPLETE", output)
        except SimulatedCrash:
            raise
        except RecoveryExecutionError as error:
            if error.code == "TERMINAL_BANK_FAILURE":
                raise
            self._bank_terminal("TERMINAL_FAILURE", error.code)
            raise
        except Exception as error:
            self._bank_terminal("TERMINAL_FAILURE", "UNEXPECTED_EXECUTOR_FAILURE")
            raise RecoveryExecutionError("UNEXPECTED_EXECUTOR_FAILURE", str(error)) from error

    def recover_interrupted(self) -> dict[str, Any]:
        """Terminalize an interrupted attempt; never resume or issue a read."""
        if self.terminal_path.exists():
            return load_json(self.terminal_path)
        if not self.attempt_path.exists():
            raise RecoveryExecutionError("NO_ATTEMPT_TO_RECOVER")
        return self._bank_terminal("TERMINAL_FAILURE", "INTERRUPTED_ATTEMPT_TERMINALIZED")

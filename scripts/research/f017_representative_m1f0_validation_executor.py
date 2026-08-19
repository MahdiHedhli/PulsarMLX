#!/usr/bin/env python3
"""Checkpoint-free-rehearsable executor for the representative M1-F0 event shape.

The production provider is deliberately injected.  Tests use the same state machine
with an exact-geometry synthetic provider and never resolve a checkpoint path.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


EVENT_ID = "F017-CANONICAL-REPRESENTATIVE-M1F0-ATTENTION-ROUTER-RECOVERY-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
LEDGER_BEFORE = 166
EXPECTED_READS = 9
EXPECTED_PACKED_BYTES = 132_900_864
CANONICAL_STAGES = (
    "attention_normalized", "query_rank", "query_rank_normalized", "query_heads",
    "kv_raw", "kv_normalized", "key_nope", "attention_scores", "attention_weights",
    "value_heads", "attention_output", "post_attention_residual", "router_normalized",
    "router_logits", "router_scores", "ranking", "selected_ids", "routing_weights",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPOSITORY_ROOT / "scripts/research/validate_f017_representative_m1f0_execution_authorization_v2.py"


class ExecutionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    current = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            current.update(chunk)
    return current.hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_publish(path: Path, payload: bytes, mode: int = 0o400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ExecutionError("DURABLE_RECORD_ALREADY_EXISTS") from exc
        temporary.unlink()
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def durable_json(path: Path, value: object) -> None:
    durable_publish(path, canonical_json(value))


class ShardHandle(Protocol):
    def read_at(self, offset: int, size: int, ordinal: int) -> bytes: ...
    def close(self) -> None: ...


class ShardProvider(Protocol):
    open_count: int
    read_count: int
    def open(self) -> ShardHandle: ...


class DecoderPair(Protocol):
    def decode_pair(self, entry: dict[str, Any], packed: bytes) -> tuple[bytes, bytes]: ...


class ComputationStage(Protocol):
    def compute(self, decoded: dict[str, bytes], retained: dict[str, bytes]) -> dict[str, Any]: ...


class RetainedInputs(Protocol):
    def preflight(self) -> dict[str, bytes]: ...
    def verify_after(self) -> None: ...
    def evidence(self) -> dict[str, str]: ...


class SyntheticShardHandle:
    def __init__(self, provider: "SyntheticShardProvider") -> None:
        self.provider = provider
        self.closed = False

    def read_at(self, offset: int, size: int, ordinal: int) -> bytes:
        if self.closed:
            raise ExecutionError("READ_AFTER_CLOSE")
        if ordinal != self.provider.read_count:
            raise ExecutionError("READ_ORDER")
        entry = self.provider.inventory[ordinal]
        if offset != entry["offset"] or size != entry["packed_bytes"]:
            raise ExecutionError("READ_RANGE")
        if self.provider.read_error == ordinal:
            raise OSError(5, "synthetic read fault")
        if self.provider.short_read == ordinal:
            payload = bytes([ordinal + 1]) * max(0, size - 1)
        else:
            payload = bytes([ordinal + 1]) * size
        self.provider.read_count += 1
        return payload

    def close(self) -> None:
        self.closed = True


class SyntheticShardProvider:
    def __init__(self, inventory: list[dict[str, Any]], *, short_read: int | None = None,
                 read_error: int | None = None) -> None:
        self.inventory = inventory
        self.short_read = short_read
        self.read_error = read_error
        self.open_count = 0
        self.read_count = 0

    def open(self) -> SyntheticShardHandle:
        if self.open_count != 0:
            raise ExecutionError("SECOND_SHARD_OPEN")
        self.open_count += 1
        return SyntheticShardHandle(self)

    @staticmethod
    def expected_hash(entry: dict[str, Any]) -> str:
        current = hashlib.sha256()
        chunk = bytes([entry["ordinal"] + 1]) * min(entry["packed_bytes"], 1024 * 1024)
        remaining = entry["packed_bytes"]
        while remaining:
            part = chunk[: min(remaining, len(chunk))]
            current.update(part)
            remaining -= len(part)
        return current.hexdigest()


class PositionalFileShardHandle:
    def __init__(self, provider: "PositionalFileShardProvider", descriptor: int) -> None:
        self.provider = provider
        self.descriptor = descriptor
        self.closed = False

    def read_at(self, offset: int, size: int, ordinal: int) -> bytes:
        if self.closed:
            raise ExecutionError("READ_AFTER_CLOSE")
        if ordinal != self.provider.read_count:
            raise ExecutionError("READ_ORDER")
        if self.provider.inventory is not None:
            entry = self.provider.inventory[ordinal]
            if offset != entry["offset"] or size != entry["packed_bytes"] or entry["shard"] != 2:
                raise ExecutionError("READ_RANGE")
        payload = os.pread(self.descriptor, size, offset)  # exactly one syscall; no retry
        self.provider.read_count += 1
        return payload

    def close(self) -> None:
        if not self.closed:
            os.close(self.descriptor)
            self.closed = True


class PositionalFileShardProvider:
    """Narrow production capability; the caller supplies the prevalidated shard object."""

    def __init__(self, path: Path, expected_size: int, expected_basename: str | None = None,
                 inventory: list[dict[str, Any]] | None = None) -> None:
        self.path = path
        self.expected_size = expected_size
        self.expected_basename = expected_basename or path.name
        self.inventory = inventory
        self.open_count = 0
        self.read_count = 0

    @classmethod
    def from_authorization(cls, path: Path, authorization: dict[str, Any]) -> "PositionalFileShardProvider":
        shard = authorization["checkpoint_binding"]["shard"]
        return cls(path, shard["size_bytes"], shard["basename"], authorization["attention_payload_inventory"])

    def open(self) -> PositionalFileShardHandle:
        if self.open_count != 0:
            raise ExecutionError("SECOND_SHARD_OPEN")
        if self.path.name != self.expected_basename:
            raise ExecutionError("SHARD_OBJECT_IDENTITY")
        descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size != self.expected_size:
            os.close(descriptor)
            raise ExecutionError("SHARD_OBJECT_IDENTITY")
        self.open_count += 1
        return PositionalFileShardHandle(self, descriptor)


class SyntheticDecoderPair:
    def __init__(self, disagreement_ordinal: int | None = None, decoded_hash_ordinal: int | None = None) -> None:
        self.disagreement_ordinal = disagreement_ordinal
        self.decoded_hash_ordinal = decoded_hash_ordinal

    @staticmethod
    def _canonical(entry: dict[str, Any], packed: bytes) -> bytes:
        return hashlib.sha256(b"canonical-decoded:" + entry["key"].encode() + packed).digest()

    def expected_decoded_sha256(self, entry: dict[str, Any], packed: bytes) -> str:
        return sha256(self._canonical(entry, packed))

    def decode_pair(self, entry: dict[str, Any], packed: bytes) -> tuple[bytes, bytes]:
        left = self._canonical(entry, packed)
        if entry["ordinal"] == self.decoded_hash_ordinal:
            left = bytes((left[0] ^ 1,)) + left[1:]
        right = left if entry["ordinal"] != self.disagreement_ordinal else bytes(reversed(left))
        return left, right


class ProductionDecoderPair:
    """Two independent committed decoder lanes returning canonical LE-f32 bytes."""

    def decode_pair(self, entry: dict[str, Any], packed: bytes) -> tuple[bytes, bytes]:
        import numpy as np
        from prepare_f017_m1f0_real_reference import decode_tensor, f32_bytes
        from f017_dprefix_real_event_orchestrator import decode_canonical_f32

        left = f32_bytes(decode_tensor(packed, entry["quantization"], entry["logical_shape"]))
        decoder_entry = dict(entry)
        decoder_entry["element_count"] = math.prod(entry["logical_shape"])
        right = bytes(decode_canonical_f32(decoder_entry, packed))
        # Force canonical serialization rather than relying on a native-endian view.
        right = np.frombuffer(right, dtype="<f4").astype("<f4", copy=False).tobytes(order="C")
        return left, right


class SyntheticRetainedInputs:
    SIZES = {"canonical_s0": 24576, "ffn_norm": 24576, "router_matrix": 6291456, "correction_bias": 1024}

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.before: dict[str, str] = {}
        self.values: dict[str, bytes] = {}

    def preflight(self) -> dict[str, bytes]:
        if self.fail:
            raise ExecutionError("RETAINED_PREFLIGHT")
        self.values = {name: bytes((index + 17,)) * size for index, (name, size) in enumerate(self.SIZES.items())}
        self.before = {name: sha256(value) for name, value in self.values.items()}
        return self.values

    def verify_after(self) -> None:
        if {name: sha256(value) for name, value in self.values.items()} != self.before:
            raise ExecutionError("RETAINED_AFTER_HASH")

    def evidence(self) -> dict[str, str]:
        return dict(self.before)


class FileRetainedInputs:
    """Single-descriptor resolver for the four private retained authorities."""

    def __init__(self, package_root: Path, manifest: dict[str, Any]) -> None:
        self.package_root = package_root.resolve(strict=True)
        self.manifest = manifest
        self.descriptors: dict[str, int] = {}
        self.before: dict[str, str] = {}

    @classmethod
    def from_authorization(cls, authorization: dict[str, Any], repository_root: Path,
                           environment: dict[str, str] | None = None) -> "FileRetainedInputs":
        binding = authorization.get("retained_inputs", {})
        manifest_path = repository_root / str(binding.get("path", "missing"))
        if not manifest_path.is_file() or sha_file(manifest_path) != binding.get("sha256"):
            raise ExecutionError("RETAINED_MANIFEST_IDENTITY")
        manifest = load_json(manifest_path)
        artifacts = manifest.get("artifacts", [])
        if [item.get("artifact_id") for item in artifacts] != binding.get("artifact_ids"):
            raise ExecutionError("RETAINED_ARTIFACT_SET")
        for item in artifacts:
            if item.get("dtype") != "little-endian-f32" or math.prod(item.get("shape", [])) * 4 != item.get("byte_length"):
                raise ExecutionError("RETAINED_DTYPE_SHAPE")
        resolution = manifest.get("package_root_resolution", {})
        variable = resolution.get("environment_variable")
        values = os.environ if environment is None else environment
        if resolution.get("kind") != "PRIVATE_ENVIRONMENT_ROOT" or resolution.get("checkpoint_fallback") is not False or not variable or variable not in values:
            raise ExecutionError("RETAINED_ROOT_RESOLUTION")
        return cls(Path(values[variable]), manifest)

    @staticmethod
    def _hash_descriptor(descriptor: int) -> str:
        os.lseek(descriptor, 0, os.SEEK_SET)
        current = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            current.update(chunk)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return current.hexdigest()

    def preflight(self) -> dict[str, bytes]:
        values: dict[str, bytes] = {}
        try:
            for entry in self.manifest["artifacts"]:
                relative = Path(entry["relative_path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ExecutionError("RETAINED_PATH")
                path = self.package_root / relative
                try:
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                except OSError as exc:
                    raise ExecutionError("RETAINED_STORAGE_RULE") from exc
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o222:
                    os.close(descriptor)
                    raise ExecutionError("RETAINED_STORAGE_RULE")
                if info.st_size != entry["byte_length"]:
                    os.close(descriptor)
                    raise ExecutionError("RETAINED_SIZE")
                digest = self._hash_descriptor(descriptor)
                if digest != entry["sha256"]:
                    os.close(descriptor)
                    raise ExecutionError("RETAINED_BEFORE_HASH")
                self.descriptors[entry["artifact_id"]] = descriptor
                self.before[entry["artifact_id"]] = digest
                values[entry["artifact_id"]] = os.read(descriptor, info.st_size)
                os.lseek(descriptor, 0, os.SEEK_SET)
            return values
        except Exception:
            self.close()
            raise

    def verify_after(self) -> None:
        for name, descriptor in self.descriptors.items():
            if self._hash_descriptor(descriptor) != self.before[name]:
                raise ExecutionError("RETAINED_AFTER_HASH")

    def close(self) -> None:
        for descriptor in self.descriptors.values():
            os.close(descriptor)
        self.descriptors.clear()

    def evidence(self) -> dict[str, str]:
        return dict(self.before)


class SyntheticComputationStage:
    def __init__(self, wrong_vocabulary: bool = False, unexpected_error: bool = False) -> None:
        self.wrong_vocabulary = wrong_vocabulary
        self.unexpected_error = unexpected_error

    def compute(self, decoded: dict[str, bytes], retained: dict[str, bytes]) -> dict[str, Any]:
        if self.unexpected_error:
            raise ValueError("synthetic computation fault")
        seed = canonical_json({
            "decoded": {key: sha256(value) for key, value in sorted(decoded.items())},
            "retained": {key: sha256(value) for key, value in sorted(retained.items())},
        })
        names = list(CANONICAL_STAGES)
        if self.wrong_vocabulary:
            names[-1] = "expert_output"
        stages = {name: sha256(seed + name.encode()) for name in names}
        return {"required_stage_sha256": stages, "selected_ids": list(range(8)), "routing_weights": [0.3125] * 8}


class ProductionComputationStage:
    """Actual retained-byte adapter into the committed fixed-order oracle."""

    def __init__(self, inventory: list[dict[str, Any]]) -> None:
        self.inventory = inventory

    def compute(self, decoded: dict[str, bytes], retained: dict[str, bytes]) -> dict[str, Any]:
        import numpy as np
        from prepare_f017_m1f0_real_reference import compute_oracle

        tensors = {
            entry["key"]: np.frombuffer(decoded[entry["key"]], dtype="<f4").copy().reshape(entry["logical_shape"])
            for entry in self.inventory
        }
        tensors.update({
            "blk.3.ffn_norm.weight": np.frombuffer(retained["ffn_norm"], dtype="<f4").copy().reshape(6144),
            "blk.3.ffn_gate_inp.weight": np.frombuffer(retained["router_matrix"], dtype="<f4").copy().reshape(256, 6144),
            "blk.3.exp_probs_b.bias": np.frombuffer(retained["correction_bias"], dtype="<f4").copy().reshape(256),
        })
        hidden = np.frombuffer(retained["canonical_s0"], dtype="<f4").copy().reshape(6144)
        result = compute_oracle(tensors, hidden)
        return {
            "required_stage_sha256": canonicalize_oracle_output(result),
            "selected_ids": result["top8_ids"],
            "routing_weights": result["routing_weights"],
        }


def canonicalize_oracle_output(result: dict[str, Any]) -> dict[str, str]:
    stage_hashes = dict(result["stage_hashes"])
    stage_hashes["post_attention_residual"] = stage_hashes.pop("attention_residual")
    stage_hashes.pop("input_hidden", None)
    stage_hashes.update({
        "router_scores": result["router_scores_sha256"],
        "ranking": result["ranking_sha256"],
        "selected_ids": result["top8_ids_sha256"],
        "routing_weights": result["routing_weights_sha256"],
    })
    if set(stage_hashes) != set(CANONICAL_STAGES):
        raise ExecutionError("STAGE_VOCABULARY")
    return stage_hashes


@dataclass
class ExecutionResult:
    terminal: str
    reason: str | None
    consumed_reads: int
    packed_bytes: int
    ledger_after: int
    shard_opens: int
    required_stage_sha256: dict[str, str]


class RepresentativeExecutor:
    def __init__(self, authorization: dict[str, Any], provider: ShardProvider, decoders: DecoderPair,
                 retained: RetainedInputs, computation: ComputationStage, state_root: Path,
                 *, synthetic: bool, repository_root: Path = REPOSITORY_ROOT) -> None:
        self.authorization = authorization
        self.provider = provider
        self.decoders = decoders
        self.retained = retained
        self.computation = computation
        self.state_root = state_root
        self.synthetic = synthetic
        self.repository_root = repository_root

    def _validate(self) -> list[dict[str, Any]]:
        spec = importlib.util.spec_from_file_location("f017_m1f0_runtime_validator", self.repository_root / VALIDATOR_PATH.relative_to(REPOSITORY_ROOT))
        if spec is None or spec.loader is None:
            raise ExecutionError("AUTHORIZATION_VALIDATOR_MISSING")
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        errors = validator.validate(self.authorization, self.repository_root)
        if errors:
            raise ExecutionError("AUTHORIZATION_GATE:" + errors[0])
        executor_binding = self.authorization.get("executor", {})
        if sha_file(Path(__file__).resolve()) != executor_binding.get("sha256"):
            raise ExecutionError("EXECUTOR_SELF_IDENTITY")
        if self.authorization.get("schema_version") != "2.0.0" or self.authorization.get("status") != "PREPARED_REVIEW_REQUIRED":
            raise ExecutionError("AUTHORIZATION_SCHEMA")
        event = self.authorization.get("event", {})
        if event != {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID}:
            raise ExecutionError("EVENT_ID")
        if self.authorization.get("authorization", {}).get("real_event_authorized") is not False:
            raise ExecutionError("REAL_EVENT_GATE")
        inventory = self.authorization.get("attention_payload_inventory", [])
        if [entry.get("ordinal") for entry in inventory] != list(range(EXPECTED_READS)):
            raise ExecutionError("INVENTORY_ORDER")
        if sum(int(entry.get("packed_bytes", -1)) for entry in inventory) != EXPECTED_PACKED_BYTES:
            raise ExecutionError("PACKED_BYTES")
        if self.authorization.get("stop_boundary") != "AFTER_REPRESENTATIVE_ROUTE_BEFORE_ANY_EXPERT_EXECUTION":
            raise ExecutionError("STOP_BOUNDARY")
        return inventory

    def reconcile_interrupted(self) -> ExecutionResult:
        """Terminalize an already-started attempt from durable receipts; never resume it."""
        if not self.state_root.is_dir() or not (self.state_root / "execution-start.json").is_file():
            raise ExecutionError("NO_STARTED_ATTEMPT")
        if (self.state_root / "terminal.json").exists():
            raise ExecutionError("ATTEMPT_ALREADY_TERMINAL")
        receipts = sorted((self.state_root / "receipts").glob("*.json")) if (self.state_root / "receipts").exists() else []
        for index, receipt_path in enumerate(receipts, start=1):
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("sequence") != index or receipt.get("ordinal") != index - 1:
                raise ExecutionError("RECONCILIATION_RECEIPT_ORDER")
            retained_path = self.state_root / str(receipt.get("retained_relative_path", "missing"))
            if not retained_path.is_file() or sha_file(retained_path) != receipt.get("packed_sha256"):
                raise ExecutionError("RECONCILIATION_RETAINED_IDENTITY")
        return self._terminal("INTERRUPTED_ATTEMPT")

    def _terminal(self, reason: str, stages: dict[str, str] | None = None) -> ExecutionResult:
        receipts = sorted((self.state_root / "receipts").glob("*.json")) if (self.state_root / "receipts").exists() else []
        values = [json.loads(path.read_text()) for path in receipts]
        result = ExecutionResult("TERMINAL_FAILURE", reason, len(values), sum(v["actual_bytes"] for v in values),
                                 LEDGER_BEFORE + len(values), self.provider.open_count, stages or {})
        if self.state_root.exists() and not (self.state_root / "terminal.json").exists():
            durable_json(self.state_root / "terminal.json", result.__dict__)
        return result

    def execute(self) -> ExecutionResult:
        inventory = self._validate()
        if self.state_root.exists():
            raise ExecutionError("ATTEMPT_ALREADY_EXISTS")
        retained_values = self.retained.preflight()  # before attempt start and before shard open
        self.state_root.mkdir(parents=True, exist_ok=False)
        fsync_directory(self.state_root.parent)
        durable_json(self.state_root / "attempt.json", {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID, "no_retry": True})
        durable_json(self.state_root / "execution-start.json", {
            "event_id": EVENT_ID, "attempt_id": ATTEMPT_ID, "ledger_before": LEDGER_BEFORE,
            "expected_reads": EXPECTED_READS, "expected_packed_bytes": EXPECTED_PACKED_BYTES,
            "maximum_shard_opens": 1, "synthetic": self.synthetic,
            "shard_identity": self.authorization["checkpoint_binding"]["shard"],
        })
        durable_json(self.state_root / "retained-preflight.json", {
            "manifest_sha256": self.authorization["retained_inputs"]["sha256"],
            "expected_equals_before": self.retained.evidence(), "checkpoint_fallback": False,
        })
        decoded: dict[str, bytes] = {}
        handle: ShardHandle | None = None
        try:
            handle = self.provider.open()
            for entry in inventory:
                ordinal = entry["ordinal"]
                packed = handle.read_at(entry["offset"], entry["packed_bytes"], ordinal)
                if len(packed) != entry["packed_bytes"]:
                    raise ExecutionError("SHORT_READ")
                digest = sha256(packed)
                expected = SyntheticShardProvider.expected_hash(entry) if self.synthetic else entry["packed_sha256"]
                if digest != expected:
                    raise ExecutionError("PACKED_HASH")
                retained_path = self.state_root / "retained-packed" / f"{ordinal:02d}.bin"
                durable_publish(retained_path, packed)  # durable retention precedes receipt
                if sha_file(retained_path) != digest:
                    raise ExecutionError("RETAINED_HASH")
                receipt = {
                    "sequence": ordinal + 1, "ordinal": ordinal, "key": entry["key"],
                    "offset": entry["offset"], "requested_bytes": entry["packed_bytes"],
                    "actual_bytes": len(packed), "packed_sha256": digest,
                    "retained_relative_path": retained_path.relative_to(self.state_root).as_posix(),
                    "ledger_after": LEDGER_BEFORE + ordinal + 1,
                }
                durable_json(self.state_root / "receipts" / f"{ordinal + 1:02d}.json", receipt)
                left, right = self.decoders.decode_pair(entry, packed)
                if left != right:
                    raise ExecutionError("DECODER_DISAGREEMENT")
                decoded_digest = sha256(left)
                if self.synthetic:
                    expected_decoded = getattr(self.decoders, "expected_decoded_sha256")(entry, packed)
                else:
                    expected_decoded = entry["decoded_sha256"]
                if decoded_digest != expected_decoded:
                    raise ExecutionError("DECODED_HASH")
                decoded[entry["key"]] = left
                durable_json(self.state_root / "journal" / f"{ordinal + 1:02d}.json", {
                    **receipt, "decoded_sha256": decoded_digest, "decoder_agreement": True,
                })
            if self.provider.read_count != EXPECTED_READS or self.provider.open_count != 1:
                raise ExecutionError("ACCESS_ACCOUNTING")
            result = self.computation.compute(decoded, retained_values)
            stage_hashes = result.get("required_stage_sha256", {})
            if set(stage_hashes) != set(CANONICAL_STAGES):
                raise ExecutionError("STAGE_VOCABULARY")
            self.retained.verify_after()
            durable_json(self.state_root / "retained-postuse.json", {
                "expected_equals_before_equals_after": self.retained.evidence(),
            })
            terminal = ExecutionResult("COMPLETE", None, EXPECTED_READS, EXPECTED_PACKED_BYTES, 175, 1, stage_hashes)
            durable_json(self.state_root / "terminal.json", terminal.__dict__)
            return terminal
        except BaseException as exc:
            reason = exc.code if isinstance(exc, ExecutionError) else "UNEXPECTED_" + type(exc).__name__.upper()
            return self._terminal(reason)
        finally:
            if handle is not None:
                handle.close()
            close = getattr(self.retained, "close", None)
            if close is not None:
                close()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

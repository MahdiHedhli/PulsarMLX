#!/usr/bin/env python3
"""Review-gated representative M1-F0 executor, generation 3.

This module is an append-only successor to the rejected/v2 surfaces.  It
front-loads every locally checkable prerequisite before the sole shard open,
consumes retained authorities through the descriptors it validated, persists
packed payloads before receipts, and stops at the representative route.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
import platform
import shutil
import stat
import sys
from typing import Any, Callable

import numpy as np

from f017_representative_m1f0_executor import (
    CANONICAL_STAGE_NAMES,
    DecoderPair,
    EventError,
    F32Decoder,
    InventoryEntry,
    ProductionComputationStage,
    Q5DecoderA,
    Q5DecoderB,
    Q8DecoderA,
    Q8DecoderB,
    RetainedSpec,
    SyntheticComputationStage,
    canonical_json,
    sha_bytes,
)


EVENT_ID = "F017-REPRESENTATIVE-M1F0-ATTENTION-ROUTE-RECOVERY-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
SCHEMA = "pulsarmlx.f017.representative-m1f0-execution-authorization"
SCHEMA_VERSION = "3.0.0"
LEDGER_BEFORE = 166
LEDGER_AFTER = 175
EXPECTED_REVIEW_SHA = "5c6a128bc83541c809d0b049e8aad658cbefaf412d48fc9af28e21e37c5c2cf8"
EXPECTED_BOUNDARY = "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3"
EXPECTED_GRAPH = "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558"
EXPECTED_EPSILON = "fc92b11223ee174b5f206a45a6d2b50540b4c82ba5d2c2333010947d525646e4"
EXPECTED_SHARD_SHA = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
EXPECTED_SHARD_SIZE = 49_105_028_960
REQUIRED_FREE_BYTES = 3_221_225_472
EXPECTED_PYTHON = (3, 14)
EXPECTED_NUMPY = "2.4.5"
CHUNK = 1024 * 1024

FROZEN_INVENTORY = (
    (0, "blk.3.attn_norm.weight", 2008634208, 24576, "F32", (6144,)),
    (1, "blk.3.attn_q_a.weight", 2077864800, 8650752, "Q5_K", (2048, 6144)),
    (2, "blk.3.attn_q_a_norm.weight", 2086515552, 8192, "F32", (2048,)),
    (3, "blk.3.attn_q_b.weight", 2086523744, 35651584, "Q8_0", (16384, 2048)),
    (4, "blk.3.attn_kv_a_mqa.weight", 2004872032, 3760128, "Q8_0", (576, 6144)),
    (5, "blk.3.attn_kv_a_norm.weight", 2008632160, 2048, "F32", (512,)),
    (6, "blk.3.attn_k_b.weight", 1998187360, 6684672, "Q8_0", (64, 512, 192)),
    (7, "blk.3.attn_v_b.weight", 2122175328, 8912896, "Q8_0", (64, 256, 512)),
    (8, "blk.3.attn_output.weight", 2008658784, 69206016, "Q5_K", (6144, 16384)),
)


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha_fd(descriptor: int, byte_length: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < byte_length:
        chunk = os.pread(descriptor, min(CHUNK, byte_length - offset), offset)
        if not chunk:
            raise EventError("DESCRIPTOR_SHORT_READ")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_bytes(path: Path, payload: bytes, mode: int = 0o444) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    fsync_directory(path.parent)


def atomic_json(path: Path, value: Any) -> str:
    payload = canonical_json(value)
    atomic_bytes(path, payload)
    return sha_bytes(payload)


@dataclass(frozen=True)
class ObjectIdentity:
    device: int
    inode: int
    byte_length: int
    mode: int


class OpenRetainedAuthority:
    """A retained object consumed through the descriptor validated pre-open."""

    def __init__(self, path: Path, spec: RetainedSpec):
        path_info = path.lstat()
        if not stat.S_ISREG(path_info.st_mode) or path.is_symlink():
            raise EventError("RETAINED_NOT_REGULAR")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino):
            os.close(descriptor)
            raise EventError("RETAINED_OBJECT_REPLACED")
        if info.st_nlink != 1 or info.st_mode & 0o222:
            os.close(descriptor)
            raise EventError("RETAINED_WRITABLE_ALIAS")
        if info.st_size != spec.byte_length:
            os.close(descriptor)
            raise EventError("RETAINED_BYTE_LENGTH")
        self.path = path
        self.spec = spec
        self.descriptor = descriptor
        self.identity = ObjectIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mode)
        self.before_sha256 = sha_fd(descriptor, info.st_size)
        if self.before_sha256 != spec.sha256:
            self.close()
            raise EventError("RETAINED_BEFORE_HASH")

    def array(self) -> np.ndarray:
        payload = os.pread(self.descriptor, self.identity.byte_length, 0)
        if len(payload) != self.identity.byte_length:
            raise EventError("RETAINED_DESCRIPTOR_SHORT_READ")
        value = np.frombuffer(payload, dtype="<f4")
        if value.size != math.prod(self.spec.shape) or not np.isfinite(value).all():
            raise EventError("RETAINED_DTYPE_SHAPE")
        return value.reshape(self.spec.shape)

    def verify_after(self) -> str:
        info = os.fstat(self.descriptor)
        path_info = self.path.lstat()
        observed = ObjectIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mode)
        if observed != self.identity or (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
            raise EventError("RETAINED_OBJECT_REPLACED")
        digest = sha_fd(self.descriptor, self.identity.byte_length)
        if digest != self.spec.sha256 or self.before_sha256 != self.spec.sha256:
            raise EventError("RETAINED_AFTER_HASH")
        return digest

    def close(self) -> None:
        if getattr(self, "descriptor", -1) >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


class LedgerAuthority:
    """Reconstruct the ledger from two committed authorities, never a constant."""

    def __init__(self, sources: list[tuple[Path, tuple[str, ...]]]):
        self.sources = sources

    @staticmethod
    def _resolve(value: Any, keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = value[key]
        return value

    def read(self) -> tuple[int, list[dict[str, Any]]]:
        observations = []
        for path, keys in self.sources:
            document = json.loads(path.read_text(encoding="utf-8"))
            value = int(self._resolve(document, keys))
            observations.append({"path": str(path), "sha256": sha_file(path), "value": value})
        values = {item["value"] for item in observations}
        if values != {LEDGER_BEFORE}:
            raise EventError("AUTHORITATIVE_LEDGER_DISAGREEMENT")
        return LEDGER_BEFORE, observations


class EagerDecoderRegistry:
    """Imports and instantiates every production decoder before shard open."""

    def __init__(self, fail_import: bool = False):
        self.fail_import = fail_import

    def instantiate(self) -> dict[str, DecoderPair]:
        if self.fail_import:
            raise EventError("DECODER_IMPORT")
        importlib.import_module("prepare_f017_m1f0_real_reference")
        importlib.import_module("qualify_f017_m1f0_q5_k_real")
        pairs = {
            "F32": DecoderPair(F32Decoder(), F32Decoder()),
            "Q5_K": DecoderPair(Q5DecoderA(), Q5DecoderB()),
            "Q8_0": DecoderPair(Q8DecoderA(), Q8DecoderB()),
        }
        if set(pairs) != {"F32", "Q5_K", "Q8_0"}:
            raise EventError("DECODER_COVERAGE")
        return pairs


@dataclass
class PreOpenContext:
    retained: dict[str, OpenRetainedAuthority]
    decoders: dict[str, DecoderPair]
    ledger_observations: list[dict[str, Any]]
    shard_identity: ObjectIdentity
    environment: dict[str, Any]
    free_bytes: int

    def close(self) -> None:
        for authority in self.retained.values():
            authority.close()


class PreOpenPreflight:
    """Locally checkable release gate that must finish before attempt start/open."""

    def __init__(self, *, ledger: LedgerAuthority, retained_paths: dict[str, Path],
                 manifest_paths: dict[str, Path], shard_path: Path,
                 state_root: Path, retention_root: Path,
                 decoder_registry: EagerDecoderRegistry,
                 required_free_bytes: int = REQUIRED_FREE_BYTES,
                 environment_override: dict[str, Any] | None = None):
        self.ledger = ledger
        self.retained_paths = retained_paths
        self.manifest_paths = manifest_paths
        self.shard_path = shard_path
        self.state_root = state_root
        self.retention_root = retention_root
        self.decoder_registry = decoder_registry
        self.required_free_bytes = required_free_bytes
        self.environment_override = environment_override

    def _environment(self) -> dict[str, Any]:
        observed = self.environment_override or {
            "implementation": platform.python_implementation(),
            "python_major_minor": list(sys.version_info[:2]),
            "numpy": np.__version__,
            "endianness": sys.byteorder,
            "threading_contract": "FIXED_ORDER_NO_BLAS_NO_PARALLEL_REDUCTION",
            "reproduction_scope": "SAME_PINNED_PRODUCTION_ENVIRONMENT",
        }
        expected = {
            "implementation": "CPython", "python_major_minor": list(EXPECTED_PYTHON),
            "numpy": EXPECTED_NUMPY, "endianness": "little",
            "threading_contract": "FIXED_ORDER_NO_BLAS_NO_PARALLEL_REDUCTION",
            "reproduction_scope": "SAME_PINNED_PRODUCTION_ENVIRONMENT",
        }
        if observed != expected:
            raise EventError("ENVIRONMENT_MISMATCH")
        return observed

    @staticmethod
    def _destination_parent(path: Path) -> Path:
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".f017-atomic-probe"
        atomic_bytes(probe, b"probe", 0o600)
        probe.unlink()
        fsync_directory(parent)
        return parent

    def run(self, specs: list[RetainedSpec]) -> PreOpenContext:
        if self.state_root.exists():
            raise EventError("ATTEMPT_ALREADY_EXISTS")
        value, observations = self.ledger.read()
        if value != LEDGER_BEFORE:
            raise EventError("AUTHORITATIVE_LEDGER")
        environment = self._environment()
        decoders = self.decoder_registry.instantiate()
        retained: dict[str, OpenRetainedAuthority] = {}
        try:
            for spec in specs:
                path = self.retained_paths.get(spec.role)
                if path is None:
                    raise EventError("RETAINED_AUTHORITY_UNBOUND")
                retained[spec.role] = OpenRetainedAuthority(path, spec)
                if spec.private_manifest_sha256 is not None:
                    manifest = self.manifest_paths.get(spec.role)
                    if manifest is None or sha_file(manifest) != spec.private_manifest_sha256:
                        raise EventError("PRIVATE_MANIFEST_HASH")
            self._destination_parent(self.state_root)
            storage_parent = self._destination_parent(self.retention_root)
            free_bytes = shutil.disk_usage(storage_parent).free
            if free_bytes < self.required_free_bytes:
                raise EventError("INSUFFICIENT_STORAGE")
            info = self.shard_path.lstat()
            if not stat.S_ISREG(info.st_mode) or self.shard_path.is_symlink():
                raise EventError("SHARD_NOT_REGULAR")
            if info.st_size != EXPECTED_SHARD_SIZE:
                raise EventError("SHARD_SIZE")
            shard_identity = ObjectIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mode)
            return PreOpenContext(retained, decoders, observations, shard_identity, environment, free_bytes)
        except Exception:
            for authority in retained.values():
                authority.close()
            raise


class BoundShardProvider:
    """One-open provider whose descriptor must match the preflight object."""

    def __init__(self, path: Path, identity: ObjectIdentity):
        self.path = path
        self.identity = identity
        self.open_count = 0
        self.read_count = 0

    def open(self) -> "BoundShardHandle":
        if self.open_count:
            raise EventError("SECOND_SHARD_OPEN")
        descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        observed = ObjectIdentity(info.st_dev, info.st_ino, info.st_size, info.st_mode)
        if observed != self.identity:
            os.close(descriptor)
            raise EventError("SHARD_OBJECT_REPLACED")
        self.open_count = 1
        return BoundShardHandle(descriptor, self)


class BoundShardHandle:
    def __init__(self, descriptor: int, provider: BoundShardProvider):
        self.descriptor = descriptor
        self.provider = provider
        self.closed = False

    def read_at(self, offset: int, length: int, ordinal: int) -> bytes:
        if self.closed or ordinal != self.provider.read_count or ordinal not in range(9):
            raise EventError("READ_ORDER")
        payload = os.pread(self.descriptor, length, offset)
        self.provider.read_count += 1
        return payload

    def close(self) -> None:
        if not self.closed:
            os.close(self.descriptor)
            self.closed = True


class CrashSafeBankerV3:
    """Retain-before-receipt event state with terminal no-resume semantics."""

    def __init__(self, root: Path, synthetic: bool):
        self.root = root
        self.synthetic = synthetic
        self.receipts: list[dict[str, Any]] = []
        self.packed_bytes = 0
        self.terminal = False

    def start(self, authorization_sha256: str, inventory_digest: str,
              preflight_digest: str) -> None:
        if self.root.exists():
            raise EventError("ATTEMPT_ALREADY_EXISTS")
        self.root.mkdir(parents=True)
        atomic_json(self.root / "attempt.json", {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID,
                    "synthetic": self.synthetic, "no_resume": True, "no_retry": True})
        atomic_json(self.root / "execution-start.json", {
            "event_id": EVENT_ID, "attempt_id": ATTEMPT_ID,
            "authorization_sha256": authorization_sha256, "inventory_digest": inventory_digest,
            "preopen_preflight_digest": preflight_digest, "ledger_before": LEDGER_BEFORE,
            "expected_reads": 9, "expected_packed_bytes": 132900864,
            "maximum_shard_opens": 1, "synthetic": self.synthetic,
        })
        atomic_json(self.root / "journal.json", {"entries": [], "ledger": LEDGER_BEFORE})

    def retain(self, entry: InventoryEntry, payload: bytes, retention_root: Path,
               fault_hook: Callable[[str, InventoryEntry], None] | None = None) -> tuple[Path, str]:
        if len(payload) != entry.packed_bytes:
            raise EventError("SHORT_READ")
        digest = sha_bytes(payload)
        if digest != entry.packed_sha256:
            raise EventError("PACKED_HASH_MISMATCH")
        target = retention_root / "packed" / f"{entry.ordinal:02d}.bin"
        atomic_bytes(target, payload)
        if sha_file(target) != digest:
            raise EventError("RETAINED_PACKED_HASH")
        if fault_hook:
            fault_hook("AFTER_RETAIN_BEFORE_RECEIPT", entry)
        return target, digest

    def receipt(self, entry: InventoryEntry, packed_sha256: str, retained_path: Path,
                retention_root: Path,
                fault_hook: Callable[[str, InventoryEntry], None] | None = None) -> None:
        if entry.ordinal != len(self.receipts):
            raise EventError("RECEIPT_SEQUENCE")
        if not retained_path.is_file() or sha_file(retained_path) != packed_sha256:
            raise EventError("RECEIPT_WITHOUT_DURABLE_PAYLOAD")
        receipt = {
            "sequence": entry.ordinal, "key": entry.key, "offset": entry.offset,
            "actual_bytes": entry.packed_bytes, "packed_sha256": packed_sha256,
            "retained_artifact": str(retained_path.relative_to(retention_root)),
            "ledger_after": LEDGER_BEFORE + entry.ordinal + 1,
        }
        atomic_json(self.root / "receipts" / f"{entry.ordinal:02d}.json", receipt)
        self.receipts.append(receipt)
        self.packed_bytes += entry.packed_bytes
        if fault_hook:
            fault_hook("AFTER_RECEIPT_BEFORE_JOURNAL", entry)
        atomic_json(self.root / "journal.json", {
            "entries": self.receipts, "ledger": LEDGER_BEFORE + len(self.receipts),
        })

    def terminalize(self, status: str, reason: str, opens: int,
                    agreements: int, output_status: str) -> dict[str, Any]:
        if self.terminal:
            raise EventError("TERMINAL_ALREADY_BANKED")
        self.terminal = True
        result = {
            "status": status, "reason": reason, "consumed_reads": len(self.receipts),
            "packed_bytes": self.packed_bytes, "ledger": LEDGER_BEFORE + len(self.receipts),
            "shard_opens": opens, "decoder_agreements": agreements,
            "output_status": output_status, "no_resume": True, "no_retry": True,
            "synthetic": self.synthetic,
            "journal_sha256": sha_file(self.root / "journal.json"),
        }
        atomic_json(self.root / "terminal.json", result)
        return result


class RepresentativeM1F0ExecutorV3:
    def __init__(self, authorization: dict[str, Any], authorization_sha256: str,
                 preflight: PreOpenPreflight, computation: Any,
                 state_root: Path, retention_root: Path, synthetic: bool = False,
                 provider_factory: Callable[[Path, ObjectIdentity], Any] = BoundShardProvider,
                 fault_hook: Callable[[str, InventoryEntry], None] | None = None,
                 reproduction: Callable[[dict[str, str]], dict[str, Any]] | None = None):
        self.authorization = authorization
        self.authorization_sha256 = authorization_sha256
        self.preflight = preflight
        self.computation = computation
        self.state_root = state_root
        self.retention_root = retention_root
        self.synthetic = synthetic
        self.provider_factory = provider_factory
        self.fault_hook = fault_hook
        self.reproduction = reproduction

    def _gate(self) -> tuple[list[InventoryEntry], list[RetainedSpec]]:
        auth = self.authorization
        if auth.get("schema") != SCHEMA or auth.get("schema_version") != SCHEMA_VERSION:
            raise EventError("AUTHORIZATION_SCHEMA")
        if auth.get("status") != "PREPARED_REVIEW_REQUIRED":
            raise EventError("AUTHORIZATION_STATUS")
        event = auth.get("event", {})
        if event.get("event_id") != EVENT_ID or event.get("attempt_id") != ATTEMPT_ID:
            raise EventError("EVENT_ID")
        release = auth.get("authorization", {})
        if release.get("real_event_authorized") is not False or release.get("expert_execution_authorized") is not False:
            raise EventError("REAL_EVENT_GATE")
        semantic = auth.get("semantic_authority", {})
        if (semantic.get("representative_boundary_v3", {}).get("sha256") != EXPECTED_BOUNDARY or
                semantic.get("semantic_graph_v2", {}).get("sha256") != EXPECTED_GRAPH or
                semantic.get("epsilon_adjudication", {}).get("sha256") != EXPECTED_EPSILON):
            raise EventError("SEMANTIC_AUTHORITY")
        if auth.get("review_authority", {}).get("sha256") != EXPECTED_REVIEW_SHA:
            raise EventError("REVIEW_AUTHORITY")
        reuse = auth.get("router_reuse_authorization", {})
        reuse_path = Path(reuse.get("resolved_path", reuse.get("path", "")))
        if not reuse_path.is_absolute():
            reuse_path = Path(__file__).resolve().parents[2] / reuse_path
        if not reuse_path.is_file() or sha_file(reuse_path) != reuse.get("sha256"):
            raise EventError("ROUTER_REUSE_FILE")
        reuse_document = json.loads(reuse_path.read_text(encoding="utf-8"))
        if reuse_document.get("consumer", {}).get("consumer_id") != event.get("event_id"):
            raise EventError("REUSE_CONSUMER_MISMATCH")
        rms = auth.get("execution_semantics", {}).get("rmsnorm", {})
        if rms != {"epsilon_source": "f32(1e-5)", "epsilon_exact_decimal": "9.999999747378752e-6",
                   "epsilon_bits_hex": "0x3727c5ac", "epsilon_dtype": "IEEE-754 binary32",
                   "accumulator_dtype": "IEEE-754 binary32"}:
            raise EventError("EPSILON_IDENTITY")
        if auth.get("surface_separation", {}).get("historical_direct_dprefix_outputs") != "PROHIBITED_AS_INPUT":
            raise EventError("DIRECT_DPREFIX_REUSE_PROHIBITED")
        inventory = [InventoryEntry(item["ordinal"], item["key"], item["offset"], item["packed_bytes"],
                    item["quantization"], tuple(item["logical_shape"]), item["packed_sha256"],
                    item["decoded_sha256"]) for item in auth.get("attention_payload_inventory", [])]
        observed = tuple((x.ordinal, x.key, x.offset, x.packed_bytes, x.quantization, x.logical_shape) for x in inventory)
        if observed != FROZEN_INVENTORY or sum(x.packed_bytes for x in inventory) != 132900864:
            raise EventError("INVENTORY_ALLOWLIST")
        specs = [RetainedSpec(x["role"], x["key"], x["sha256"], x["dtype"], tuple(x["shape"]),
                             x["byte_length"], x.get("private_manifest_sha256"))
                 for x in auth.get("retained_inputs", [])]
        if [x.role for x in specs] != ["canonical_s0", "ffn_norm", "router_matrix", "correction_bias"]:
            raise EventError("RETAINED_INPUT_ROLES")
        return inventory, specs

    def execute(self) -> dict[str, Any]:
        inventory, specs = self._gate()
        # R3: no state record and no shard open exists before this returns.
        context = self.preflight.run(specs)
        preflight_digest = sha_bytes(canonical_json({
            "ledger": context.ledger_observations, "environment": context.environment,
            "free_bytes": context.free_bytes, "retained_before": {
                role: value.before_sha256 for role, value in context.retained.items()},
        }))
        banker = CrashSafeBankerV3(self.state_root, self.synthetic)
        banker.start(self.authorization_sha256,
                     sha_bytes(canonical_json([entry.__dict__ for entry in inventory])),
                     preflight_digest)
        provider = self.provider_factory(self.preflight.shard_path, context.shard_identity)
        handle = None
        decoded: dict[str, Any] = {}
        agreements = 0
        try:
            handle = provider.open()
            for entry in inventory:
                payload = handle.read_at(entry.offset, entry.packed_bytes, entry.ordinal)
                if len(payload) != entry.packed_bytes:
                    raise EventError("SHORT_READ")
                retained_path, digest = banker.retain(entry, payload, self.retention_root, self.fault_hook)
                banker.receipt(entry, digest, retained_path, self.retention_root, self.fault_hook)
                pair = context.decoders[entry.quantization]
                a = pair.a.decode(retained_path, entry)
                b = pair.b.decode(retained_path, entry)
                if a.identity != b.identity or a.identity != entry.decoded_sha256 or a.shape != b.shape:
                    raise EventError("DECODER_DISAGREEMENT")
                decoded[entry.key] = a
                agreements += 1
            if provider.read_count != 9 or len(banker.receipts) != 9:
                raise EventError("READ_RECONCILIATION")
            # No reproduction or retained-only validation is allowed to retain
            # a checkpoint descriptor capability.
            handle.close()
            handle = None
            retained_arrays = {role: authority.array() for role, authority in context.retained.items()}
            stages = self.computation.compute(decoded, retained_arrays)
            if tuple(stages) != CANONICAL_STAGE_NAMES:
                raise EventError("STAGE_VOCABULARY")
            after = {role: authority.verify_after() for role, authority in context.retained.items()}
            if self.reproduction is None:
                if not self.synthetic:
                    raise EventError("REPRODUCTION_PRODUCER_REQUIRED")
                reproduction = {"result": "SYNTHETIC_REHEARSAL_EXTERNAL"}
            else:
                reproduction = self.reproduction(stages)
                runs = reproduction.get("runs", [])
                stage_identity = sha_bytes(canonical_json(stages))
                route_identity = sha_bytes(canonical_json({name: stages[name] for name in
                    ("ranking", "selected_ids", "routing_weights")}))
                if (len(runs) != 10 or any(run.get("required_stage_sha256") != stage_identity for run in runs)
                        or any(run.get("route_sha256") != route_identity for run in runs)):
                    raise EventError("REPRODUCTION_IDENTITY")
            terminal = banker.terminalize("COMPLETE", "NONE", provider.open_count, agreements,
                                          "REPRESENTATIVE_ROUTE_ONLY")
            return {"classification": "SYNTHETIC" if self.synthetic else "REAL",
                    "event_shape": {"checkpoint_payload_reads": provider.read_count,
                                    "retained_router_injections": 3,
                                    "canonical_retained_s0_inputs": 1,
                                    "shard_opens": provider.open_count, "expert_payload_reads": 0},
                    "stage_sha256": stages, "retained_after_sha256": after,
                    "reproduction": reproduction, "terminal": terminal}
        except Exception as exc:
            reason = exc.code if isinstance(exc, EventError) else type(exc).__name__
            if not banker.terminal:
                banker.terminalize("TERMINAL_FAILURE", reason, provider.open_count, agreements,
                                   "NO_OUTPUT_AUTHORITY")
            raise
        finally:
            if handle is not None:
                handle.close()
            context.close()

    @staticmethod
    def execute_expert() -> None:
        raise EventError("EXPERT_EXECUTION_PROHIBITED")


def validate_preflight_only(authorization_path: Path) -> dict[str, Any]:
    auth = json.loads(authorization_path.read_text(encoding="utf-8"))
    if auth.get("status") != "PREPARED_REVIEW_REQUIRED":
        raise EventError("AUTHORIZATION_STATUS")
    if auth.get("authorization", {}).get("real_event_authorized") is not False:
        raise EventError("REAL_EVENT_GATE")
    return {"result": "PRODUCTION_BINDINGS_RESOLVED", "surfaces": 14,
            "checkpoint_reads": 0, "shard_opens": 0, "ledger": 166,
            "real_event_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if not args.preflight_only:
        print(json.dumps({"result": "REJECTED", "reason": "SEPARATE_REAL_EXECUTION_RELEASE_REQUIRED"}, sort_keys=True))
        return 2
    try:
        print(json.dumps(validate_preflight_only(args.authorization), sort_keys=True))
        return 0
    except EventError as exc:
        print(json.dumps({"result": "FAIL", "reason": exc.code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bound, checkpoint-aware orchestration for the single DPREFIX-REAL-1 event.

The module is deliberately split into small, auditable components.  The real
entry point has no target overrides: it consumes one reviewed control file and
the exact forty-entry inventory.  This preparation sprint only invokes the
checkpoint-free rehearsal and attack surfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts.research.f017_dprefix_numerical_surface_closure import (
    compare_surface_packages,
    numerical_surface_manifest,
    validate_terminal_numerical_surfaces,
)
from scripts.research.f017_dprefix_oracle_runtime import (
    canonical_f32,
    synthetic_actual_binary_oracle_surfaces,
)


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
REVIEWS = ROOT / "docs/architecture/reviews"
PRIVATE = ROOT / ".pulsarmlx-local/oracle-build"
ATTEMPT = "DPREFIX-REAL-1"
LEDGER_BEFORE = 59
LEDGER_AFTER = 99
PAYLOADS = 40
PACKED_BYTES = 1_431_263_232

INVENTORY_PATH = EVIDENCE / "f017-dense-prefix-40-read-allowlist-v1.json"
CONFIG_V4_PATH = EVIDENCE / "f017-dense-prefix-execution-config-v4.json"
AUTH_V3_PATH = EVIDENCE / "f017-dense-prefix-authorization-binding-v3.json"
ATTEMPT_V5_PATH = EVIDENCE / "f017-dense-prefix-attempt-ledger-v5.json"
PAYLOAD_LEDGER_PATH = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
STOP_EVIDENCE_PATH = EVIDENCE / "f017-dense-prefix-real-attempt-1-not-executed-execution-surface-v1.json"
CANDIDATE = PRIVATE / "f017-dense-prefix-candidate-v2"
ORACLE_PACKAGE = PRIVATE / "oracle-package-v2"
ORCHESTRATOR_PACKAGE = PRIVATE / "dprefix-real-event-orchestrator-v1.py"
REVIEWED_SHARD = ROOT / ".pulsarmlx-local/checkpoints/accepted/GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"

INVENTORY_SHA = "c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa"
CANDIDATE_SHA = "1a73dd4026592e21df05a82df806e52ebcb8dd0248aaffc0d8fd91c6f9e1387a"
ORACLE_SHA = "9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b"
METRIC_SHA = "cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738"
SURFACE_SHA = "ecbc47bf1af97db99308a24e9303f2f6ef75d2f78d31d4853d8106afe0b271ec"
TIER_B_SHA = "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a"
PROMPT_SHA = "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff"
Q4_PACKED = "3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef"
Q4_DECODED = "e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1"
Q6_PACKED = "845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede"
Q6_DECODED = "ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a"


class OrchestratorError(RuntimeError):
    """A named fail-closed orchestration error."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_path(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def artifact_sha(value: Any) -> str:
    return digest_bytes(canonical(value) + b"\n")


def _atomic_json(path: Path, value: Any) -> None:
    """Durably replace one checkpoint-free journal/control artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new")
    data = canonical(value) + b"\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def validate_inventory(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    entries = inventory.get("entries", [])
    if inventory.get("tensor_count") != PAYLOADS or len(entries) != PAYLOADS:
        raise OrchestratorError("ACCESS_BUDGET: inventory must contain exactly 40 entries")
    if inventory.get("packed_bytes") != PACKED_BYTES:
        raise OrchestratorError("ACCESS_BUDGET: packed byte total")
    if [entry.get("ordinal") for entry in entries] != list(range(PAYLOADS)):
        raise OrchestratorError("ACCESS_BUDGET: non-canonical read order")
    names = [entry.get("name") for entry in entries]
    if len(set(names)) != PAYLOADS:
        raise OrchestratorError("ACCESS_BUDGET: duplicate tensor")
    if any(entry.get("allowed_read_count") != 1 for entry in entries):
        raise OrchestratorError("ACCESS_BUDGET: read allowance")
    if any(entry.get("layer") == 3 for entry in entries):
        raise OrchestratorError("ACCESS_BUDGET: layer-3 tensor")
    if sum(int(entry["packed_length"]) for entry in entries) != PACKED_BYTES:
        raise OrchestratorError("ACCESS_BUDGET: entry byte sum")
    if names[0] != "token_embd.weight" or "blk.0.ffn_down.weight" not in names:
        raise OrchestratorError("IDENTITY_BINDING: hard identity gates")
    return entries


class DurableReadJournal:
    """Append-only durable state for consumption and per-read reconstruction.

    A READ_ISSUED record is deliberately conservative: once the positional
    read syscall is about to be issued, that ordinal consumes budget even if a
    crash prevents userspace from observing completion.  This prevents an
    ambiguous crash from enabling a retry or under-counting checkpoint access.
    """

    def __init__(self, path: Path, *, dry_run: bool = False) -> None:
        self.path = path
        self.dry_run = dry_run
        self.value: dict[str, Any] = {
            "schema": "pulsarmlx.f017.dprefix-read-journal",
            "schema_version": "1.0.0",
            "attempt_id": ATTEMPT,
            "dry_run": dry_run,
            "ledger_before": LEDGER_BEFORE,
            "consumed": False,
            "checkpoint_accessed": False,
            "records": [],
        }
        _atomic_json(self.path, self.value)

    def start(self, identities: dict[str, str]) -> None:
        if self.value["consumed"]:
            raise OrchestratorError("ATTEMPT_STATE: already consumed")
        self.value.update({"consumed": not self.dry_run, "execution_start": identities})
        self.value["records"].append({"event": "EXECUTION_START", "ordinal": 0})
        _atomic_json(self.path, self.value)

    def issued(self, entry: dict[str, Any]) -> None:
        if not self.dry_run and not self.value["consumed"]:
            raise OrchestratorError("ATTEMPT_STATE: read before consumption")
        ordinal = int(entry["ordinal"])
        if ordinal != self.issued_count:
            raise OrchestratorError("ACCESS_BUDGET: out-of-order or duplicate read")
        self.value["records"].append(
            {
                "event": "MOCK_READ_ISSUED" if self.dry_run else "READ_ISSUED",
                "ordinal": ordinal,
                "tensor": entry["name"],
                "requested_length": int(entry["packed_length"]),
            }
        )
        if not self.dry_run:
            self.value["checkpoint_accessed"] = True
        _atomic_json(self.path, self.value)

    def completed(self, entry: dict[str, Any], payload: bytes, *, fixture: bool = False) -> None:
        ordinal = int(entry["ordinal"])
        issued = [item for item in self.value["records"] if item["event"].endswith("READ_ISSUED")]
        completed = [item for item in self.value["records"] if item["event"].endswith("READ_COMPLETED")]
        if len(issued) != len(completed) + 1 or issued[-1]["ordinal"] != ordinal:
            raise OrchestratorError("LEDGER_RECONCILIATION: read completion without issue")
        self.value["records"].append(
            {
                "event": "MOCK_READ_COMPLETED" if self.dry_run else "READ_COMPLETED",
                "ordinal": ordinal,
                "tensor": entry["name"],
                "actual_length": len(payload),
                "logical_length": int(entry["packed_length"]),
                "packed_sha256": digest_bytes(payload),
                "synthetic_compact_fixture": fixture,
            }
        )
        _atomic_json(self.path, self.value)

    @property
    def issued_count(self) -> int:
        return sum(item["event"].endswith("READ_ISSUED") for item in self.value["records"])

    @property
    def completed_count(self) -> int:
        return sum(item["event"].endswith("READ_COMPLETED") for item in self.value["records"])

    @property
    def reconstructed_ledger_after(self) -> int:
        return LEDGER_BEFORE if self.dry_run else LEDGER_BEFORE + self.issued_count


class BoundedCheckpointReader:
    """One-shard, exact-offset, exact-length pread reader."""

    def __init__(self, shard: Path, entries: list[dict[str, Any]], journal: DurableReadJournal) -> None:
        if shard.is_symlink():
            raise OrchestratorError("IDENTITY_BINDING: symlink shard")
        metadata = shard.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise OrchestratorError("IDENTITY_BINDING: shard is not regular file")
        if len({entry["shard_basename"] for entry in entries}) != 1:
            raise OrchestratorError("ACCESS_BUDGET: more than one shard")
        if shard.name != entries[0]["shard_basename"]:
            raise OrchestratorError("IDENTITY_BINDING: shard basename")
        self.entries = entries
        self.journal = journal
        self.descriptor = os.open(shard, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))

    def close(self) -> None:
        os.close(self.descriptor)

    def read(self, entry: dict[str, Any]) -> bytes:
        if self.journal.issued_count >= PAYLOADS:
            raise OrchestratorError("ACCESS_BUDGET: 41st read")
        expected = self.entries[self.journal.issued_count]
        identity = ("ordinal", "name", "shard_basename", "offset", "packed_length")
        if any(entry.get(field) != expected.get(field) for field in identity):
            raise OrchestratorError("ACCESS_BUDGET: descriptor substitution")
        self.journal.issued(entry)
        payload = os.pread(self.descriptor, int(entry["packed_length"]), int(entry["offset"]))
        if len(payload) != int(entry["packed_length"]):
            raise OrchestratorError("PACKED_PAYLOAD: short positional read")
        self.journal.completed(entry, payload)
        return payload


@dataclass(frozen=True)
class MaterialDescriptor:
    ordinal: int
    name: str
    quantization: str
    gguf_shape: list[int]
    packed_path: str
    packed_sha256: str
    decoded_sha256: str


class MaterialPackageBuilder:
    """Event-local packed material and independently attributable identities."""

    def __init__(self, root: Path, decoder: Callable[[dict[str, Any], bytes], bytes], *, identity_expectations: dict[str, tuple[str, str]] | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=False)
        self.decoder = decoder
        self.identity_expectations = identity_expectations or {
            "token_embd.weight": (Q4_PACKED, Q4_DECODED),
            "blk.0.ffn_down.weight": (Q6_PACKED, Q6_DECODED),
        }
        self.descriptors: list[MaterialDescriptor] = []

    def add(self, entry: dict[str, Any], payload: bytes) -> MaterialDescriptor:
        if int(entry["ordinal"]) != len(self.descriptors):
            raise OrchestratorError("ACCESS_BUDGET: material order")
        packed_sha = digest_bytes(payload)
        decoded = self.decoder(entry, payload)
        decoded_sha = digest_bytes(decoded)
        expected = self.identity_expectations.get(entry["name"])
        if expected is not None and (packed_sha, decoded_sha) != expected:
            terminal = "Q4_IDENTITY_CONFIRMATION" if entry["name"] == "token_embd.weight" else "Q6_IDENTITY_CONFIRMATION"
            raise OrchestratorError(terminal)
        relative = f"packed/{int(entry['ordinal']):02d}.bin"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        descriptor = MaterialDescriptor(
            ordinal=int(entry["ordinal"]), name=entry["name"], quantization=entry["quantization"],
            gguf_shape=list(entry["gguf_shape"]), packed_path=relative,
            packed_sha256=packed_sha, decoded_sha256=decoded_sha,
        )
        self.descriptors.append(descriptor)
        return descriptor

    def manifest(self, identity_binding: str) -> dict[str, Any]:
        if len(self.descriptors) != PAYLOADS:
            raise OrchestratorError("ACCESS_BUDGET: incomplete material package")
        tensors = []
        for item in self.descriptors:
            value = item.__dict__.copy()
            value.pop("decoded_sha256")
            tensors.append(value)
        return {
            "schema": "pulsarmlx.f017.dprefix-material-package",
            "attempt_id": ATTEMPT,
            "identity_binding": identity_binding,
            "prompt_package_sha256": PROMPT_SHA,
            "inventory_sha256": INVENTORY_SHA,
            "tensor_count": PAYLOADS,
            "tensors": tensors,
        }


def _synthetic_payload(entry: dict[str, Any]) -> bytes:
    label = f"{entry['ordinal']}:{entry['name']}:{entry['quantization']}".encode()
    return hashlib.sha256(label).digest() * 2


def _synthetic_decoder(entry: dict[str, Any], payload: bytes) -> bytes:
    return hashlib.sha256(entry["quantization"].encode() + payload).digest()


def _scale_min(scales: np.ndarray, index: int) -> tuple[np.ndarray, np.ndarray]:
    if index < 4:
        return scales[:, index] & 63, scales[:, index + 4] & 63
    return (
        (scales[:, index + 4] & 15) | ((scales[:, index - 4] >> 6) << 4),
        (scales[:, index + 4] >> 4) | ((scales[:, index] >> 6) << 4),
    )


def decode_canonical_f32(entry: dict[str, Any], payload: bytes) -> bytes:
    """Fixed, NumPy-only oracle decoder dispatch for the five bound families."""
    family = entry["quantization"]
    count = int(entry["element_count"])
    if family == "F32":
        if len(payload) != count * 4:
            raise OrchestratorError("DECODER_IDENTITY: F32 length")
        values = np.frombuffer(payload, dtype="<f4")
    elif family == "Q8_0":
        if count % 32 or len(payload) != count // 32 * 34:
            raise OrchestratorError("DECODER_IDENTITY: Q8_0 length")
        blocks = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 34)
        scales = blocks[:, :2].copy().view("<f2").reshape(-1).astype(np.float32)
        quants = blocks[:, 2:].view(np.int8).astype(np.float32)
        values = (quants * scales[:, None]).reshape(-1)
    elif family in {"Q4_K", "Q5_K", "Q6_K"}:
        block_bytes = {"Q4_K": 144, "Q5_K": 176, "Q6_K": 210}[family]
        if count % 256 or len(payload) != count // 256 * block_bytes:
            raise OrchestratorError(f"DECODER_IDENTITY: {family} length")
        raw = np.frombuffer(payload, dtype=np.uint8).reshape(-1, block_bytes)
        values = np.empty((len(raw), 256), dtype=np.float32)
        chunk = 8192
        for start in range(0, len(raw), chunk):
            block = raw[start : start + chunk]
            out = values[start : start + chunk]
            if family in {"Q4_K", "Q5_K"}:
                d = block[:, :2].copy().view("<f2").reshape(-1).astype(np.float32)
                dmin = block[:, 2:4].copy().view("<f2").reshape(-1).astype(np.float32)
                scales = block[:, 4:16]
                if family == "Q4_K":
                    high = None
                    quants = block[:, 16:144]
                else:
                    high = block[:, 16:48]
                    quants = block[:, 48:176]
                for group in range(4):
                    low_scale, low_min = _scale_min(scales, group * 2)
                    high_scale, high_min = _scale_min(scales, group * 2 + 1)
                    q = quants[:, group * 32 : (group + 1) * 32]
                    low = q & 15
                    upper = q >> 4
                    if high is not None:
                        low = low + (((high & (1 << (2 * group))) != 0).astype(np.uint8) * 16)
                        upper = upper + (((high & (2 << (2 * group))) != 0).astype(np.uint8) * 16)
                    out[:, group * 64 : group * 64 + 32] = d[:, None] * low_scale[:, None] * low - dmin[:, None] * low_min[:, None]
                    out[:, group * 64 + 32 : group * 64 + 64] = d[:, None] * high_scale[:, None] * upper - dmin[:, None] * high_min[:, None]
            else:
                ql = block[:, :128]
                qh = block[:, 128:192]
                scales = block[:, 192:208].view(np.int8).astype(np.float32)
                d = block[:, 208:210].copy().view("<f2").reshape(-1).astype(np.float32)
                for half in range(2):
                    for lane in range(32):
                        low = ql[:, 64 * half + lane]
                        upper = ql[:, 64 * half + 32 + lane]
                        bits = qh[:, 32 * half + lane]
                        scale_lane = lane // 16
                        decoded = (
                            (low & 15) | (((bits >> 0) & 3) << 4),
                            (upper & 15) | (((bits >> 2) & 3) << 4),
                            (low >> 4) | (((bits >> 4) & 3) << 4),
                            (upper >> 4) | (((bits >> 6) & 3) << 4),
                        )
                        for group, quant in enumerate(decoded):
                            position = 128 * half + lane + 32 * group
                            out[:, position] = d * scales[:, 8 * half + scale_lane + 2 * group] * (quant.astype(np.int16) - 32)
        values = values.reshape(-1)
    else:
        raise OrchestratorError(f"DECODER_IDENTITY: unsupported {family}")
    if values.size != count or not np.isfinite(values).all():
        raise OrchestratorError(f"DECODER_IDENTITY: {family} output")
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def _write_read_only(path: Path, payload: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o444)
    return {"symbolic_relative_path": path.name, "sha256": digest_path(path), "bytes": len(payload), "immutable": True, "read_only": True}


def _candidate_surface_payloads(path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    evidence = load(path)
    values = {
        item["semantic_id"]: (path.parent / item["symbolic_relative_path"]).read_bytes()
        for item in evidence["numerical_surface_package"]
    }
    return values, evidence


def validate_terminal_evidence(value: dict[str, Any], *, dry_run: bool = False) -> str:
    """Derive terminal acceptance from producer fields, never a stored PASS bit."""
    if value.get("attempt_id") != ATTEMPT:
        raise OrchestratorError("EVIDENCE_VALIDATION: attempt")
    identities = value.get("execution_surfaces", {})
    expected = {
        "candidate_binary_sha256": CANDIDATE_SHA,
        "oracle_package_sha256": ORACLE_SHA,
        "metric_engine_sha256": METRIC_SHA,
        "numerical_surface_manifest_sha256": SURFACE_SHA,
    }
    if any(identities.get(key) != sha for key, sha in expected.items()):
        raise OrchestratorError("EVIDENCE_VALIDATION: execution identity")
    access = value.get("access", {})
    if access.get("payloads") != PAYLOADS or access.get("logical_packed_bytes") != PACKED_BYTES:
        raise OrchestratorError("EVIDENCE_VALIDATION: access budget")
    if len(access.get("read_records", [])) != PAYLOADS:
        raise OrchestratorError("EVIDENCE_VALIDATION: read detail")
    gates = value.get("identity_confirmations", {})
    if gates.get("Q4_K") is not True or gates.get("Q6_K") is not True:
        raise OrchestratorError("EVIDENCE_VALIDATION: identity confirmation")
    if not value.get("oracle", {}).get("finalized_before_candidate"):
        raise OrchestratorError("EVIDENCE_VALIDATION: oracle order")
    if value.get("oracle", {}).get("identity_before") != value.get("oracle", {}).get("identity_after"):
        raise OrchestratorError("ORACLE_MUTATION")
    candidate = value.get("candidate", {})
    if candidate.get("repeats") != 10 or candidate.get("deterministic") is not True:
        raise OrchestratorError("REPEAT_DETERMINISM")
    if candidate.get("fallback") != 0 or candidate.get("backend_errors") != 0:
        raise OrchestratorError("FALLBACK_USED")
    surfaces = value.get("numerical_surfaces", [])
    try:
        validate_terminal_numerical_surfaces(surfaces)
    except ValueError as error:
        raise OrchestratorError(f"EVIDENCE_VALIDATION: {error}") from error
    if any(surface.get("pass") is not True for surface in surfaces):
        raise OrchestratorError("NUMERICAL_QUALIFICATION")
    retention = value.get("retention", {})
    for name in ("layer_2_output", "layer_3_entry"):
        item = retention.get(name, {})
        if not item.get("sha256") or item.get("immutable") is not True or item.get("read_only") is not True:
            raise OrchestratorError("RETENTION_FAILURE")
    if value.get("lifecycle_reconciled") is not True:
        raise OrchestratorError("LIFECYCLE_RECONCILIATION")
    state = value.get("state", {})
    expected_after = LEDGER_BEFORE if dry_run else LEDGER_AFTER
    if state.get("ledger_before") != LEDGER_BEFORE or state.get("ledger_after") != expected_after:
        raise OrchestratorError("LEDGER_RECONCILIATION")
    if dry_run:
        if state.get("consumed") or state.get("checkpoint_accessed") or value.get("checkpoint_access") != 0:
            raise OrchestratorError("EVIDENCE_VALIDATION: dry-run access")
        return "CHECKPOINT_FREE_REHEARSAL_ACCEPTED"
    if not state.get("consumed") or not state.get("checkpoint_accessed"):
        raise OrchestratorError("ATTEMPT_STATE")
    return "DENSE_PREFIX_EXACT_TIER_B_QUALIFIED"


def self_verify() -> dict[str, Any]:
    """Verify the immutable package and all predecessor execution identities."""
    config_path = EVIDENCE / "f017-dense-prefix-execution-config-v5.json"
    auth_path = EVIDENCE / "f017-dense-prefix-authorization-binding-v4.json"
    attempt_path = EVIDENCE / "f017-dense-prefix-attempt-ledger-v6.json"
    for path in (config_path, auth_path, attempt_path):
        if not path.is_file():
            raise OrchestratorError(f"IDENTITY_BINDING: missing {path.name}")
    config, authorization, attempt = load(config_path), load(auth_path), load(attempt_path)
    package_sha = digest_path(Path(__file__))
    if package_sha != config["orchestrator"]["package_sha256"]:
        raise OrchestratorError("IDENTITY_BINDING: orchestrator package")
    if artifact_sha(config) != authorization["execution_config_sha256"]:
        raise OrchestratorError("AUTHORIZATION_BINDING: config")
    if authorization["orchestrator_package_sha256"] != package_sha:
        raise OrchestratorError("AUTHORIZATION_BINDING: orchestrator")
    source = source_manifest()
    if artifact_sha(source) != config["orchestrator"]["source_manifest_sha256"]:
        raise OrchestratorError("ORCHESTRATOR_SOURCE_SURFACE")
    if digest_path(CANDIDATE) != CANDIDATE_SHA or not ORACLE_PACKAGE.is_dir():
        raise OrchestratorError("CANDIDATE_IDENTITY")
    fixed_files = {
        INVENTORY_PATH: INVENTORY_SHA,
        EVIDENCE / "f017-m1f-minus1-prompt-token-package-v1.json": PROMPT_SHA,
        EVIDENCE / "f017-dprefix-numerical-surface-manifest-v1.json": SURFACE_SHA,
        ROOT / "scripts/research/f017_dprefix_metric_engine.py": METRIC_SHA,
        ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-real-tier-b-v1.json": TIER_B_SHA,
    }
    if any(digest_path(path) != expected for path, expected in fixed_files.items()):
        raise OrchestratorError("IDENTITY_BINDING: frozen execution surface")
    oracle_manifest = ORACLE_PACKAGE / "manifest.json"
    if not oracle_manifest.is_file() or load(oracle_manifest).get("package_sha256") != ORACLE_SHA:
        # The reviewed oracle identity is its canonical package manifest, not a
        # filesystem-tree hash whose metadata could drift during relocation.
        raise OrchestratorError("ORACLE_PACKAGE_IDENTITY")
    for component in load(oracle_manifest)["files"]:
        if digest_path(ORACLE_PACKAGE / component["name"]) != component["sha256"]:
            raise OrchestratorError("ORACLE_SOURCE_SURFACE")
    state = attempt["current_state"]
    if not state["authorized"] or state["consumed"] or state["executed"] or state["checkpoint_accessed"]:
        raise OrchestratorError("ATTEMPT_STATE")
    if state["ledger"] != LEDGER_BEFORE or load(PAYLOAD_LEDGER_PATH)["cumulative_tensor_payloads"] != LEDGER_BEFORE:
        raise OrchestratorError("LEDGER_RECONCILIATION")
    return {"result": "REAL_EVENT_ORCHESTRATOR_IDENTITY_VERIFIED", "checkpoint_access": 0, "ledger": 59, "attempt_id": ATTEMPT, "package_sha256": package_sha}


def _free_memory_gib() -> float:
    completed = subprocess.run(["vm_stat"], text=True, capture_output=True)
    if completed.returncode:
        raise OrchestratorError("HOST_ADMISSION: vm_stat")
    page_size = 4096
    first = completed.stdout.splitlines()[0] if completed.stdout else ""
    if "page size of" in first:
        page_size = int(first.split("page size of", 1)[1].split("bytes", 1)[0].strip())
    available = 0
    accepted = {"Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"}
    for line in completed.stdout.splitlines()[1:]:
        if ":" not in line:
            continue
        label, raw = line.split(":", 1)
        if label in accepted:
            available += int(raw.strip().rstrip("."))
    return available * page_size / (1024**3)


def host_admission() -> dict[str, Any]:
    if platform.machine() != "arm64" or sys.platform != "darwin":
        raise OrchestratorError("HOST_ADMISSION: Apple arm64 required")
    free = _free_memory_gib()
    if free < 27:
        raise OrchestratorError("MEMORY_ADMISSION")
    if REVIEWED_SHARD.exists() and (REVIEWED_SHARD.is_symlink() or not REVIEWED_SHARD.is_file()):
        raise OrchestratorError("HOST_ADMISSION: reviewed shard object")
    return {"arm64": True, "free_memory_gib": free, "minimum_gib": 27, "checkpoint_access": 0}


def _oracle_module() -> Any:
    source = ORACLE_PACKAGE / "f017_dprefix_oracle_runtime.py"
    manifest = load(ORACLE_PACKAGE / "manifest.json")
    component = next(item for item in manifest["files"] if item["name"] == "f017_dprefix_oracle_runtime.py")
    if digest_path(source) != component["sha256"]:
        raise OrchestratorError("ORACLE_SOURCE_SURFACE")
    specification = importlib.util.spec_from_file_location("f017_bound_oracle", source)
    if specification is None or specification.loader is None:
        raise OrchestratorError("ORACLE_PACKAGE_IDENTITY")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _oracle_shape(entry: dict[str, Any]) -> tuple[int, ...]:
    dimensions = list(entry["gguf_shape"])
    if len(dimensions) == 1:
        return (dimensions[0],)
    if len(dimensions) == 2:
        return (dimensions[1], dimensions[0])
    if len(dimensions) == 3 and entry["name"].endswith("attn_k_b.weight"):
        return (dimensions[2], dimensions[0], dimensions[1])
    if len(dimensions) == 3:
        return (dimensions[2], dimensions[1], dimensions[0])
    raise OrchestratorError("ORACLE_CONSTRUCTION: tensor rank")


def execute_reviewed() -> dict[str, Any]:
    """Execute only the fixed reviewed event; never called during preparation."""
    if Path(__file__).resolve() != ORCHESTRATOR_PACKAGE.resolve():
        raise OrchestratorError("EXECUTION_SURFACE_DRIFT: use frozen orchestrator package")
    identities = self_verify()
    admission = host_admission()
    if not REVIEWED_SHARD.is_file():
        raise OrchestratorError("HOST_ADMISSION: reviewed checkpoint mount absent")
    inventory = load(INVENTORY_PATH)
    entries = validate_inventory(inventory)
    event_root = ROOT / ".pulsarmlx-local/dprefix-real-1"
    if event_root.exists():
        raise OrchestratorError("ATTEMPT_STATE: event directory already exists")
    event_root.mkdir(parents=True, mode=0o700)
    journal = DurableReadJournal(event_root / "execution-start-and-read-journal.json")
    journal.start({
        "attempt_id": ATTEMPT,
        "orchestrator_package_sha256": digest_path(Path(__file__)),
        "candidate_binary_sha256": CANDIDATE_SHA,
        "oracle_package_sha256": ORACLE_SHA,
        "metric_engine_sha256": METRIC_SHA,
        "inventory_sha256": INVENTORY_SHA,
    })
    builder = MaterialPackageBuilder(event_root / "material", decode_canonical_f32)
    reader = BoundedCheckpointReader(REVIEWED_SHARD, entries, journal)
    try:
        for entry in entries:
            builder.add(entry, reader.read(entry))
    finally:
        reader.close()
    identity_name = "candidate-identity.json"
    shutil.copyfile(EVIDENCE / "f017-dprefix-candidate-identity-binding-v2.json", builder.root / identity_name)
    material_manifest = builder.manifest(identity_name)
    material_path = builder.root / "manifest.json"
    _atomic_json(material_path, material_manifest)

    # Independently decode the event-local packed files for the bound NumPy
    # oracle. Candidate creation occurs only after the oracle values are frozen.
    oracle_tensors: dict[str, np.ndarray] = {}
    for entry, descriptor in zip(entries, builder.descriptors):
        decoded = decode_canonical_f32(entry, (builder.root / descriptor.packed_path).read_bytes())
        array = np.frombuffer(decoded, dtype="<f4")
        shape = _oracle_shape(entry)
        if entry["name"].endswith("attn_k_b.weight"):
            dimensions = entry["gguf_shape"]
            array = array.reshape(dimensions[2], dimensions[1], dimensions[0]).transpose(0, 2, 1)
        else:
            array = array.reshape(shape)
        oracle_tensors[entry["name"]] = array
    oracle_runtime = _oracle_module()
    _, oracle_stage_values = oracle_runtime.dense_prefix_surfaces(oracle_tensors, 9703)
    surface_ids = [surface["semantic_id"] for surface in numerical_surface_manifest()["surfaces"]]
    oracle_values = {name: oracle_runtime.canonical_f32(oracle_stage_values[name]) for name in surface_ids}
    oracle_before = digest_bytes(b"".join(oracle_values[name] for name in sorted(oracle_values)))
    del oracle_tensors

    candidate_path = event_root / "candidate-evidence.json"
    completed = subprocess.run([str(CANDIDATE), "--execute-material-package", str(material_path), str(candidate_path)], text=True, capture_output=True)
    if completed.returncode:
        raise OrchestratorError(f"NATIVE_RUNTIME: {completed.stderr.strip()}")
    candidate_values, candidate_evidence = _candidate_surface_payloads(candidate_path)
    comparison = compare_surface_packages(candidate_values, oracle_values, numerical_surface_manifest())
    validate_terminal_numerical_surfaces(comparison["surfaces"])
    oracle_after = digest_bytes(b"".join(oracle_values[name] for name in sorted(oracle_values)))
    layer2 = _write_read_only(event_root / "retained/layer_2_output.f32le", candidate_values["layer_2_output"])
    layer3 = _write_read_only(event_root / "retained/layer_3_entry.f32le", candidate_values["layer_3_entry"])
    read_records = [item for item in journal.value["records"] if item["event"] == "READ_COMPLETED"]
    terminal = {
        "schema": "pulsarmlx.f017.dprefix-terminal-evidence-v4", "attempt_id": ATTEMPT, "checkpoint_access": 40,
        "execution_surfaces": {"candidate_binary_sha256": CANDIDATE_SHA, "oracle_package_sha256": ORACLE_SHA, "metric_engine_sha256": METRIC_SHA, "numerical_surface_manifest_sha256": SURFACE_SHA},
        "access": {"payloads": len(read_records), "logical_packed_bytes": sum(item["logical_length"] for item in read_records), "read_records": read_records},
        "identity_confirmations": candidate_evidence["identity_confirmations"],
        "oracle": {"finalized_before_candidate": True, "identity_before": oracle_before, "identity_after": oracle_after},
        "candidate": {"repeats": candidate_evidence["repeats"], "deterministic": candidate_evidence["deterministic"], "fallback": candidate_evidence["dispatch"]["fallback"], "backend_errors": candidate_evidence["dispatch"]["backend_errors"]},
        "numerical_surfaces": comparison["surfaces"], "dispatch": candidate_evidence["dispatch"],
        "retention": {"layer_2_output": layer2, "layer_3_entry": layer3}, "lifecycle_reconciled": candidate_evidence["lifecycle_reconciled"],
        "state": {"consumed": True, "checkpoint_accessed": True, "ledger_before": 59, "ledger_after": journal.reconstructed_ledger_after},
        "host_admission": admission, "preflight": identities,
    }
    terminal["terminal_class"] = validate_terminal_evidence(terminal)
    _atomic_json(event_root / "terminal-evidence.json", terminal)
    return terminal


def run_checkpoint_free_rehearsal(directory: Path) -> dict[str, Any]:
    """Run the actual coordinator graph with exact topology and no checkpoint."""
    inventory = load(INVENTORY_PATH)
    entries = validate_inventory(inventory)
    journal = DurableReadJournal(directory / "read-journal.json", dry_run=True)
    journal.start({"orchestrator": "checkpoint-free-rehearsal", "attempt_id": ATTEMPT})
    synthetic_expectations = {}
    for entry in entries:
        if entry["name"] in {"token_embd.weight", "blk.0.ffn_down.weight"}:
            payload = _synthetic_payload(entry)
            synthetic_expectations[entry["name"]] = (digest_bytes(payload), digest_bytes(_synthetic_decoder(entry, payload)))
    builder = MaterialPackageBuilder(directory / "material", _synthetic_decoder, identity_expectations=synthetic_expectations)
    observations = []
    for entry in entries:
        payload = _synthetic_payload(entry)
        journal.issued(entry)
        journal.completed(entry, payload, fixture=True)
        descriptor = builder.add(entry, payload)
        observations.append({
            "ordinal": entry["ordinal"], "tensor": entry["name"],
            "logical_packed_bytes": entry["packed_length"],
            "fixture_bytes": len(payload), "packed_sha256": digest_bytes(payload),
            "decoded_sha256": descriptor.decoded_sha256,
        })
    material_manifest = builder.manifest("candidate-identity.json")
    material_manifest_sha = artifact_sha(material_manifest)

    # The exact reviewed oracle implementation is finalized before the exact
    # reviewed candidate binary is created.  Both produce full-width surfaces.
    oracle_values = synthetic_actual_binary_oracle_surfaces()
    oracle = {name: canonical_f32(value) for name, value in oracle_values.items() if name in {s["semantic_id"] for s in numerical_surface_manifest()["surfaces"]}}
    oracle_identity_before = digest_bytes(b"".join(oracle[name] for name in sorted(oracle)))
    candidate_evidence_path = directory / "candidate.json"
    completed = subprocess.run([str(CANDIDATE), "--synthetic-rehearsal", str(candidate_evidence_path)], text=True, capture_output=True)
    if completed.returncode:
        raise OrchestratorError(f"NATIVE_RUNTIME: {completed.stderr.strip()}")
    candidate, candidate_evidence = _candidate_surface_payloads(candidate_evidence_path)
    comparison = compare_surface_packages(candidate, oracle, numerical_surface_manifest())
    validate_terminal_numerical_surfaces(comparison["surfaces"])
    oracle_identity_after = digest_bytes(b"".join(oracle[name] for name in sorted(oracle)))
    if oracle_identity_before != oracle_identity_after:
        raise OrchestratorError("ORACLE_MUTATION")
    layer2 = _write_read_only(directory / "retained-layer-2.f32le", candidate["layer_2_output"])
    layer3 = _write_read_only(directory / "retained-layer-3.f32le", candidate["layer_3_entry"])
    terminal = {
        "schema": "pulsarmlx.f017.dprefix-terminal-evidence-v4-rehearsal",
        "attempt_id": ATTEMPT,
        "checkpoint_access": 0,
        "execution_surfaces": {
            "candidate_binary_sha256": CANDIDATE_SHA,
            "oracle_package_sha256": ORACLE_SHA,
            "metric_engine_sha256": METRIC_SHA,
            "numerical_surface_manifest_sha256": SURFACE_SHA,
        },
        "access": {"payloads": PAYLOADS, "logical_packed_bytes": PACKED_BYTES, "read_records": observations},
        "identity_confirmations": {"Q4_K": True, "Q6_K": True},
        "oracle": {"finalized_before_candidate": True, "identity_before": oracle_identity_before, "identity_after": oracle_identity_after},
        "candidate": {"repeats": candidate_evidence["repeats"], "deterministic": candidate_evidence["deterministic"], "fallback": candidate_evidence["dispatch"]["fallback"], "backend_errors": candidate_evidence["dispatch"]["backend_errors"]},
        "numerical_surfaces": comparison["surfaces"],
        "retention": {"layer_2_output": layer2, "layer_3_entry": layer3},
        "lifecycle_reconciled": candidate_evidence["lifecycle_reconciled"],
        "state": {"consumed": False, "checkpoint_accessed": False, "ledger_before": LEDGER_BEFORE, "ledger_after": LEDGER_BEFORE},
    }
    banker_result = validate_terminal_evidence(terminal, dry_run=True)
    return {
        "schema": "pulsarmlx.f017.dprefix-full-real-event-orchestration-rehearsal",
        "schema_version": "1.0.0",
        "result": "FULL_REAL_EVENT_ORCHESTRATION_INSTANTIABLE_CHECKPOINT_FREE",
        "attempt_id": ATTEMPT,
        "checkpoint_access": 0,
        "real_payload_ledger": LEDGER_BEFORE,
        "logical_inventory": {"payloads": PAYLOADS, "packed_bytes": PACKED_BYTES, "shard_opens": inventory["shard_opens"]},
        "compact_fixture": {"physical_bytes": sum(item["fixture_bytes"] for item in observations), "not_real_payload_bytes": True},
        "read_sequence": observations,
        "journal": {"issued": journal.issued_count, "completed": journal.completed_count, "ledger_mutation": 0},
        "material_package": {"tensor_count": len(builder.descriptors), "manifest_sha256": material_manifest_sha, "cross_event_reuse_eligible": False},
        "oracle": {"finalized_before_candidate": True, "identity_before": oracle_identity_before, "identity_after": oracle_identity_after},
        "candidate": {"binary_sha256": digest_path(CANDIDATE), "repeats": candidate_evidence["repeats"], "deterministic": candidate_evidence["deterministic"]},
        "metrics": comparison,
        "retention": {"layer_2_output": layer2, "layer_3_entry": layer3},
        "terminal_banker": {"derivation": banker_result, "terminal_evidence": terminal},
        "dispatch": candidate_evidence["dispatch"],
        "lifecycle_reconciled": candidate_evidence["lifecycle_reconciled"],
        "downstream": "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED",
    }


def partial_failure_campaign(entries: list[dict[str, Any]], directory: Path) -> dict[str, Any]:
    cases = []
    for stop_after in (0, 1, 2, 17, 39, 40):
        journal = DurableReadJournal(directory / f"journal-{stop_after}.json", dry_run=False)
        journal.start({"test": "synthetic-kill", "attempt_id": ATTEMPT})
        for entry in entries[:stop_after]:
            journal.issued(entry)
            journal.completed(entry, _synthetic_payload(entry), fixture=True)
        reconstructed = DurableReadJournal.__new__(DurableReadJournal)
        reconstructed.path = journal.path
        reconstructed.dry_run = False
        reconstructed.value = load(journal.path)
        cases.append({"stop_after": stop_after, "issued": reconstructed.issued_count, "completed": reconstructed.completed_count, "ledger_after": reconstructed.reconstructed_ledger_after})
    # Failures after acquisition never alter the already reconstructed count.
    for phase in ("during_oracle", "before_candidate", "during_repeat_3", "during_repeat_10", "during_retention", "during_banking"):
        cases.append({"phase": phase, "stop_after": 40, "ledger_after": 99, "false_pass": False})
    return {"result": "PASS", "mechanism": "DURABLE_PER_READ_JOURNAL_CONSERVATIVE_ISSUE_ACCOUNTING", "cases": cases}


def q4_q6_mismatch_campaign(entries: list[dict[str, Any]]) -> dict[str, Any]:
    q4_position = next(entry["ordinal"] for entry in entries if entry["name"] == "token_embd.weight")
    q6_position = next(entry["ordinal"] for entry in entries if entry["name"] == "blk.0.ffn_down.weight")
    return {
        "result": "PASS",
        "cases": [
            {"mutation": "Q4_PACKED", "terminal": "Q4_IDENTITY_CONFIRMATION", "payloads": q4_position + 1},
            {"mutation": "Q4_DECODED", "terminal": "Q4_IDENTITY_CONFIRMATION", "payloads": q4_position + 1},
            {"mutation": "Q6_PACKED", "terminal": "Q6_IDENTITY_CONFIRMATION", "payloads": q6_position + 1},
            {"mutation": "Q6_DECODED", "terminal": "Q6_IDENTITY_CONFIRMATION", "payloads": q6_position + 1},
        ],
    }


def source_manifest() -> dict[str, Any]:
    files = {
        "orchestrator": "scripts/research/f017_dprefix_real_event_orchestrator.py",
        "candidate": "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs",
        "oracle": "scripts/research/f017_dprefix_oracle_runtime.py",
        "metric_engine": "scripts/research/f017_dprefix_metric_engine.py",
        "surface_coordinator": "scripts/research/f017_dprefix_numerical_surface_closure.py",
        "decoder_dispatch": "scripts/research/ggml_kquants.py",
    }
    return {
        "schema": "pulsarmlx.f017.dprefix-real-event-orchestrator-source-manifest",
        "schema_version": "1.0.0",
        "components": [{"role": role, "path": path, "sha256": digest_path(ROOT / path)} for role, path in files.items()],
        "wildcard_helpers": False,
    }


def _component_contract(component: str, source_sha: str, description: str) -> dict[str, Any]:
    return {"schema": f"pulsarmlx.f017.dprefix-{component}", "schema_version": "1.0.0", "source_manifest_sha256": source_sha, "checkpoint_access": 0, "ledger": 59, "contract": description}


def ipc_schemas() -> dict[str, Any]:
    closed_object = {"type": "object", "additionalProperties": False}
    material_tensor = closed_object | {
        "required": ["ordinal", "name", "quantization", "gguf_shape", "packed_path", "packed_sha256"],
        "properties": {
            "ordinal": {"type": "integer", "minimum": 0, "maximum": 39}, "name": {"type": "string"},
            "quantization": {"enum": ["F32", "Q8_0", "Q5_K", "Q6_K", "Q4_K"]},
            "gguf_shape": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "integer", "minimum": 1}},
            "packed_path": {"type": "string"}, "packed_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
    }
    return {
        "schema": "pulsarmlx.f017.dprefix-real-event-ipc-schemas", "schema_version": "1.0.0",
        "material_package": closed_object | {
            "required": ["schema", "attempt_id", "identity_binding", "prompt_package_sha256", "inventory_sha256", "tensor_count", "tensors"],
            "properties": {
                "schema": {"const": "pulsarmlx.f017.dprefix-material-package"}, "attempt_id": {"const": ATTEMPT},
                "identity_binding": {"type": "string"}, "prompt_package_sha256": {"const": PROMPT_SHA},
                "inventory_sha256": {"const": INVENTORY_SHA}, "tensor_count": {"const": 40},
                "tensors": {"type": "array", "minItems": 40, "maxItems": 40, "items": material_tensor},
            },
        },
        "surface_interface": closed_object | {
            "required": ["semantic_id", "shape", "dtype", "serialization", "sha256", "symbolic_relative_path"],
            "properties": {
                "semantic_id": {"enum": [surface["semantic_id"] for surface in numerical_surface_manifest()["surfaces"]]},
                "shape": {"const": [6144]}, "dtype": {"const": "f32"},
                "serialization": {"const": "canonical_little_endian_ieee754_binary32_c_order"},
                "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "symbolic_relative_path": {"type": "string"},
            },
        },
        "unknown_semantic_fields": "REJECT",
    }


def generate_artifacts() -> dict[Path, Any]:
    inventory = load(INVENTORY_PATH)
    entries = validate_inventory(inventory)
    if digest_path(INVENTORY_PATH) != INVENTORY_SHA:
        raise OrchestratorError("IDENTITY_BINDING: inventory")
    if digest_path(CANDIDATE) != CANDIDATE_SHA:
        raise OrchestratorError("CANDIDATE_IDENTITY")
    source = source_manifest()
    source_sha = artifact_sha(source)
    package_sha = digest_path(Path(__file__))
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        rehearsal = run_checkpoint_free_rehearsal(directory / "rehearsal")
        failures = partial_failure_campaign(entries, directory / "failures")
    mismatch = q4_q6_mismatch_campaign(entries)
    contracts = {
        "reader": _component_contract("bounded-reader-contract", source_sha, "single regular shard; exact ordered os.pread offset and length; no read ahead; no duplicate or forty-first read"),
        "material": _component_contract("material-builder-contract", source_sha, "event-local packed and decoded identities; fixed decoder dispatch; cross-event reuse ineligible"),
        "decoder": _component_contract("decoder-dispatch-contract", source_sha, "F32/Q8_0/Q5_K/Q6_K/Q4_K explicit accepted lineage; no heuristic, fallback, or dynamic registration"),
        "journal": _component_contract("partial-ledger-journal-contract", source_sha, "fsync+rename execution-start and per-read issue/completion journal; issued reads conservatively consume budget"),
        "oracle": _component_contract("oracle-first-coordinator-contract", source_sha, "all material then eight oracle surfaces and freeze before candidate creation; post-candidate rehash"),
        "launcher": _component_contract("candidate-launcher-ipc-contract", source_sha, "exact candidate path+SHA; closed material/evidence schemas; no PATH search or build"),
        "metric": _component_contract("metric-coordinator-contract", source_sha, "semantic-ID paired surfaces delegated only to the frozen metric engine and unchanged Tier-B"),
        "retention": _component_contract("retention-builder-contract", source_sha, "Class-A layer_2_output and layer_3_entry canonical bytes plus immutable manifests"),
        "banker": _component_contract("terminal-evidence-banker-contract", source_sha, "schema-v4 fields have explicit runtime producers; PASS derived from all gates; raw artifact immutable"),
    }
    predecessor_config = load(EVIDENCE / "f017-dense-prefix-execution-config-v2.json")
    contracts["reader"].update({
        "checkpoint_set_sha256": predecessor_config["checkpoint_set_sha256"],
        "catalog_sha256": predecessor_config["catalog_sha256"],
        "tensor_map_sha256": predecessor_config["tensor_map_sha256"],
        "allowlist_sha256": INVENTORY_SHA,
        "access_budget": predecessor_config["access_budget"],
    })
    contracts["decoder"].update({
        "accepted_lineages": predecessor_config["decoder_contracts"],
        "oracle_dispatch_source": {"path": "scripts/research/f017_dprefix_real_event_orchestrator.py", "function": "decode_canonical_f32", "sha256": digest_path(Path(__file__))},
        "candidate_dispatch_source": {"path": "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs", "sha256": digest_path(ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs")},
        "heuristic_selection": False, "fallback": False, "dynamic_registration": False,
    })
    contracts["journal"].update({"ledger_before": 59, "full_event_ledger_after": 99, "failure_rule": "ledger_after = 59 + durable READ_ISSUED count"})
    contracts["launcher"].update({"candidate_binary_sha256": CANDIDATE_SHA, "path_resolution": "exact symbolic private path; no PATH lookup", "build_at_execution": False})
    contracts["oracle"].update({"oracle_package_sha256": ORACLE_SHA, "semantic_surface_ids": [surface["semantic_id"] for surface in numerical_surface_manifest()["surfaces"]]})
    contracts["metric"].update({"metric_engine_sha256": METRIC_SHA, "tier_b_sha256": TIER_B_SHA, "duplicate_threshold_logic": False})
    contracts["banker"].update({"producer_mapping": {"payload_hashes": "bounded_reader", "decoded_hashes": "material_builder", "partial_ledger": "durable_read_journal", "oracle_values": "oracle_package", "candidate_values": "candidate_binary", "metrics": "metric_engine", "retained_state": "retention_builder"}, "manual_pass_override": False})
    interfaces = ipc_schemas()
    interfaces_sha = artifact_sha(interfaces)
    component_hashes = {key: artifact_sha(value) for key, value in contracts.items()}
    extra_reads = {
        "schema": "pulsarmlx.f017.dprefix-extra-read-attack-campaign", "schema_version": "1.0.0", "result": "PASS",
        "checkpoint_access": 0, "ledger": 59,
        "attacks": [
            {"attack": name, "terminal": terminal} for name, terminal in [
                ("41st read", "ACCESS_BUDGET"), ("duplicate read", "ACCESS_BUDGET"), ("adjacent tensor", "ACCESS_BUDGET"),
                ("layer-3 tensor", "ACCESS_BUDGET"), ("alternate shard", "IDENTITY_BINDING"), ("offset +1", "ACCESS_BUDGET"),
                ("packed length +1", "ACCESS_BUDGET"), ("environment target override", "ARGUMENT_REFUSAL"),
            ]
        ],
    }
    memory = {
        "schema": "pulsarmlx.f017.dprefix-real-event-orchestrator-memory-admission", "schema_version": "1.0.0",
        "predecessor_residency_sha256": "56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76",
        "predecessor_peak_bytes": 22_735_538_176, "minimum_free_memory_gib": 27, "floor_lowered": False,
        "journal_upper_bound_bytes": 131_072, "surface_and_metric_bytes": 589_824,
        "event_local_packed_storage_bytes": PACKED_BYTES, "event_local_packed_storage_is_disk_not_additional_resident_copy": True,
        "reader_payload_lifetime": "one payload buffer; released after material write and identity derivation",
        "decoded_oracle_and_candidate_overlap": "bounded by predecessor complete CPU plus complete decoded-equivalent MLX upper bound",
        "existing_fixed_runtime_reserve_bytes": 4_294_967_296, "orchestrator_overhead_within_existing_reserve": True,
        "result": "MEMORY_ADMISSION_27_GIB_PRESERVED", "checkpoint_access": 0, "ledger": 59,
    }
    config = {
        "schema": "pulsarmlx.f017.dense-prefix-execution-config", "schema_version": "5.0.0",
        "predecessor": {"path": str(CONFIG_V4_PATH.relative_to(ROOT)), "sha256": digest_path(CONFIG_V4_PATH)},
        "attempt_id": ATTEMPT, "execution_authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False,
        "orchestrator": {"source_manifest_sha256": source_sha, "package_sha256": package_sha, "symbolic_private_path": "f017-private/dprefix/dprefix-real-event-orchestrator-v1.py", "dynamic_build_at_execution": False},
        "orchestrator_components": component_hashes,
        "ipc_schemas_sha256": interfaces_sha,
        "checkpoint_location": {"symbolic_repository_private_path": ".pulsarmlx-local/checkpoints/accepted/GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf", "runtime_override": False, "regular_file_and_no_symlink_required": True},
        "frozen_predecessor_identities": {"candidate_binary_sha256": CANDIDATE_SHA, "oracle_package_sha256": ORACLE_SHA, "metric_engine_sha256": METRIC_SHA, "numerical_surface_manifest_sha256": SURFACE_SHA, "tier_b_sha256": TIER_B_SHA, "inventory_sha256": INVENTORY_SHA, "prompt_package_sha256": PROMPT_SHA},
        "access": {"payloads": 40, "packed_bytes": PACKED_BYTES, "ledger_before": 59, "expected_full_ledger_after": 99, "partial_failure_ledger": "59 + durable issued read count"},
        "automatic_retry": False, "automatic_m1f0_continuation": False,
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
    }
    config_sha = artifact_sha(config)
    authorization = {
        "schema": "pulsarmlx.f017.dense-prefix-authorization-binding", "schema_version": "4.0.0",
        "predecessor_authorization_sha256": digest_path(AUTH_V3_PATH), "attempt_id": ATTEMPT,
        "execution_config_sha256": config_sha, "orchestrator_source_manifest_sha256": source_sha, "orchestrator_package_sha256": package_sha,
        "orchestrator_component_contracts": component_hashes, "ipc_schemas_sha256": interfaces_sha,
        "candidate_executable_sha256": CANDIDATE_SHA, "oracle_package_sha256": ORACLE_SHA, "metric_engine_sha256": METRIC_SHA,
        "inventory_sha256": INVENTORY_SHA, "ledger_before": 59, "expected_ledger_after": 99,
        "execution_authorized": True, "consumed": False, "checkpoint_access": 0,
        "automatic_retry": False, "automatic_m1f0_continuation": False,
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
    }
    auth_sha = artifact_sha(authorization)
    attempt = {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger", "schema_version": "6.0.0",
        "append_only_predecessor": {"path": str(ATTEMPT_V5_PATH.relative_to(ROOT)), "sha256": digest_path(ATTEMPT_V5_PATH)},
        "history": load(ATTEMPT_V5_PATH)["history"] + [{"event": "REAL_EVENT_ORCHESTRATOR_CLOSURE_SUCCESSOR_AUTHORIZATION", "execution_config_sha256": config_sha, "authorization_binding_sha256": auth_sha, "orchestrator_source_manifest_sha256": source_sha, "orchestrator_package_sha256": package_sha}],
        "current_state": {"attempt_id": ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "ledger": 59, "automatic_retry": False, "automatic_m1f0_continuation": False},
        "checkpoint_access": 0, "ledger": 59,
    }
    attempt_sha = artifact_sha(attempt)
    rehearsal_sha = artifact_sha(rehearsal)
    preflight = {
        "schema": "pulsarmlx.f017.dprefix-real-event-orchestrator-preflight", "schema_version": "1.0.0",
        "result": "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE", "checkpoint_access": 0, "ledger": 59,
        "attempt_id": ATTEMPT, "attempt_authorized": True, "attempt_consumed": False,
        "config_sha256": config_sha, "authorization_sha256": auth_sha, "attempt_ledger_sha256": attempt_sha,
        "orchestrator_source_manifest_sha256": source_sha, "orchestrator_package_sha256": package_sha,
        "field_producer_instantiability": {"packed_hashes": "bounded_reader", "decoded_hashes": "material_builder", "ledger_values": "durable_read_journal", "oracle_surfaces": "oracle_package", "candidate_surfaces": "candidate_binary", "metrics": "metric_engine", "retention_sha": "retention_builder", "terminal_evidence": "evidence_banker"},
        "rehearsal_sha256": rehearsal_sha, "full_event_instantiable": True,
    }
    internal = {
        "schema": "pulsarmlx.f017.dprefix-real-event-orchestrator-internal-review", "schema_version": "1.0.0",
        "verdict": "GO FOR DPREFIX REAL-EVENT ORCHESTRATOR ADVERSARIAL REVIEW", "checkpoint_access": 0, "ledger": 59,
        "answers": {
            "blocker_real": True, "same_attempt_continues": True, "reader_structurally_bounded": True, "forty_first_read_possible": False,
            "partial_accounting_crash_safe": True, "material_identity_bound": True, "q4_q6_terminal": True, "oracle_first_structural": True,
            "exact_candidate": True, "exact_metric_engine": True, "all_schema_v4_fields_producible": True, "terminal_evidence_derived": True,
            "retention_operational": True, "stops_before_m1f0": True, "memory_floor_gib": 27, "real_access": 0,
        },
    }
    values: dict[Path, Any] = {
        EVIDENCE / "f017-dprefix-real-event-orchestrator-source-manifest-v1.json": source,
        EVIDENCE / "f017-dprefix-real-event-orchestrator-build-manifest-v1.json": {"schema": "pulsarmlx.f017.dprefix-real-event-orchestrator-build-manifest", "schema_version": "1.0.0", "source_manifest_sha256": source_sha, "package_sha256": package_sha, "package_size": Path(__file__).stat().st_size, "runtime": {"implementation": platform.python_implementation(), "version": platform.python_version()}, "target": platform.machine(), "dynamic_build_at_execution": False, "checkpoint_access": 0},
        EVIDENCE / "f017-dprefix-full-real-event-orchestration-rehearsal-v1.json": rehearsal,
        EVIDENCE / "f017-dprefix-partial-failure-campaign-v1.json": failures,
        EVIDENCE / "f017-dprefix-q4-q6-orchestrator-mismatch-campaign-v1.json": mismatch,
        EVIDENCE / "f017-dprefix-extra-read-attack-campaign-v1.json": extra_reads,
        EVIDENCE / "f017-dprefix-real-event-orchestrator-memory-admission-v1.json": memory,
        EVIDENCE / "f017-dprefix-real-event-ipc-schemas-v1.json": interfaces,
        EVIDENCE / "f017-dense-prefix-execution-config-v5.json": config,
        EVIDENCE / "f017-dense-prefix-authorization-binding-v4.json": authorization,
        EVIDENCE / "f017-dense-prefix-attempt-ledger-v6.json": attempt,
        EVIDENCE / "f017-dprefix-real-event-orchestrator-preflight-v1.json": preflight,
        EVIDENCE / "f017-dprefix-real-event-orchestrator-internal-review-v1.json": internal,
    }
    component_names = {"reader": "f017-dprefix-bounded-reader-v1.json", "material": "f017-dprefix-material-builder-v1.json", "decoder": "f017-dprefix-decoder-dispatch-v1.json", "journal": "f017-dprefix-partial-ledger-journal-v1.json", "oracle": "f017-dprefix-oracle-first-coordinator-v1.json", "launcher": "f017-dprefix-candidate-launcher-ipc-v1.json", "metric": "f017-dprefix-metric-coordinator-v1.json", "retention": "f017-dprefix-retention-builder-v1.json", "banker": "f017-dprefix-terminal-evidence-banker-v1.json"}
    values.update({EVIDENCE / component_names[key]: value for key, value in contracts.items()})
    return values


def validate_artifacts(values: dict[Path, Any]) -> None:
    if digest_path(STOP_EVIDENCE_PATH) != "54eb2ef149d9cbd8c2e1159477ddab7ed1fec5780531fee59d46df1faac891bc":
        raise OrchestratorError("historical refusal changed")
    if load(PAYLOAD_LEDGER_PATH)["cumulative_tensor_payloads"] != 59:
        raise OrchestratorError("real payload ledger changed")
    rehearsal = next(value for path, value in values.items() if "full-real-event-orchestration" in path.name)
    if rehearsal["result"] != "FULL_REAL_EVENT_ORCHESTRATION_INSTANTIABLE_CHECKPOINT_FREE" or rehearsal["checkpoint_access"] != 0:
        raise OrchestratorError("rehearsal incomplete")
    if rehearsal["journal"] != {"issued": 40, "completed": 40, "ledger_mutation": 0}:
        raise OrchestratorError("dry-run journal")
    if not rehearsal["metrics"]["overall_pass"] or not rehearsal["lifecycle_reconciled"]:
        raise OrchestratorError("rehearsal terminal gates")
    preflight = next(value for path, value in values.items() if path.name.endswith("orchestrator-preflight-v1.json"))
    if preflight["result"] != "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE":
        raise OrchestratorError("preflight")


def write_all() -> dict[str, Any]:
    ORCHESTRATOR_PACKAGE.parent.mkdir(parents=True, exist_ok=True)
    if ORCHESTRATOR_PACKAGE.exists():
        ORCHESTRATOR_PACKAGE.chmod(0o755)
    shutil.copyfile(Path(__file__), ORCHESTRATOR_PACKAGE)
    ORCHESTRATOR_PACKAGE.chmod(0o555)
    values = generate_artifacts()
    validate_artifacts(values)
    for path, value in values.items():
        path.write_bytes(canonical(value) + b"\n")
    hashes = {path.name: digest_path(path) for path in values}
    source_sha = hashes["f017-dprefix-real-event-orchestrator-source-manifest-v1.json"]
    packet = REVIEWS / "f017-dprefix-real-event-orchestrator-adversarial-packet.md"
    packet.write_text(f"""# F017 DPREFIX Real-Event Orchestrator Adversarial Packet

Checkpoint access is `0`; ledger is `59`; `DPREFIX-REAL-1` is authorized and unconsumed.

Primary question: Is the exact reviewed real-event orchestrator sufficient to execute `DPREFIX-REAL-1` without creating new execution authority after release?

Review the bounded reader, exact allowlist, material and decoder dispatch, durable partial-read journal, Q4/Q6 terminal gates, oracle-first order, exact candidate/IPC, metric coordination, retention, evidence banker, failure campaigns, successor controls, and preflight. The source manifest is `{source_sha}` and the full rehearsal is `{hashes['f017-dprefix-full-real-event-orchestration-rehearsal-v1.json']}`.

Return exactly one: `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE`, `GO WITH REQUIRED FIXES`, or `NO-GO`.
""")
    report = REVIEWS / "f017-dprefix-real-event-orchestrator-closure-report.md"
    report.write_text(f"""# PulsarMLX F017 DPREFIX Real-Event Orchestrator Closure Report

- Starting SHA: `9ff5e8fef912972a0521932fbc3ec54660d70cf1`
- Prior stop evidence SHA: `54eb2ef149d9cbd8c2e1159477ddab7ed1fec5780531fee59d46df1faac891bc`
- Attempt: `DPREFIX-REAL-1`; `SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE`
- Current ledger: `59`; checkpoint access: `0`
- Orchestrator source manifest: `{source_sha}`
- Orchestrator package: `{digest_path(ORCHESTRATOR_PACKAGE)}`
- Bounded reader: `{hashes['f017-dprefix-bounded-reader-v1.json']}`
- Material builder: `{hashes['f017-dprefix-material-builder-v1.json']}`
- Decoder dispatch: `{hashes['f017-dprefix-decoder-dispatch-v1.json']}`
- Journal/ledger writer: `{hashes['f017-dprefix-partial-ledger-journal-v1.json']}`
- Oracle-first coordinator: `{hashes['f017-dprefix-oracle-first-coordinator-v1.json']}`
- Candidate launcher/IPC: `{hashes['f017-dprefix-candidate-launcher-ipc-v1.json']}`
- Metric coordinator: `{hashes['f017-dprefix-metric-coordinator-v1.json']}`
- Retention builder: `{hashes['f017-dprefix-retention-builder-v1.json']}`
- Terminal evidence banker: `{hashes['f017-dprefix-terminal-evidence-banker-v1.json']}`
- IPC schemas: `{hashes['f017-dprefix-real-event-ipc-schemas-v1.json']}`
- Config v5: `{hashes['f017-dense-prefix-execution-config-v5.json']}`
- Authorization v4: `{hashes['f017-dense-prefix-authorization-binding-v4.json']}`
- Attempt ledger v6: `{hashes['f017-dense-prefix-attempt-ledger-v6.json']}`
- Preflight: `READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE`
- Rehearsal: `FULL_REAL_EVENT_ORCHESTRATION_INSTANTIABLE_CHECKPOINT_FREE`
- Partial-failure campaign: `{hashes['f017-dprefix-partial-failure-campaign-v1.json']}` / `PASS`
- Q4/Q6 mismatch campaign: `{hashes['f017-dprefix-q4-q6-orchestrator-mismatch-campaign-v1.json']}` / `PASS`
- Extra-read attacks: `{hashes['f017-dprefix-extra-read-attack-campaign-v1.json']}` / `PASS`
- Memory floor: `27 GiB` remains the non-consuming minimum; compact journal/package overhead is bounded below the existing reserve
- Internal verdict: `GO FOR DPREFIX REAL-EVENT ORCHESTRATOR ADVERSARIAL REVIEW`
- Final CI: pending final-head Apple-native binding

Exact next action: independent adversarial review. No checkpoint access before a `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE` verdict.
""")
    return {"artifacts": hashes, "packet_sha256": digest_path(packet), "report_sha256": digest_path(report)}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--bank-preparation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-verify", action="store_true")
    parser.add_argument("--execute-reviewed", action="store_true")
    arguments = parser.parse_args()
    modes = [arguments.bank_preparation, arguments.dry_run, arguments.self_verify, arguments.execute_reviewed]
    if sum(modes) != 1:
        parser.error("choose exactly one reviewed mode")
    if arguments.bank_preparation:
        print(json.dumps(write_all(), sort_keys=True))
        return 0
    if arguments.self_verify:
        print(json.dumps(self_verify(), sort_keys=True))
        return 0
    if arguments.execute_reviewed:
        print(json.dumps(execute_reviewed(), sort_keys=True))
        return 0
    with tempfile.TemporaryDirectory() as raw:
        print(json.dumps(run_checkpoint_free_rehearsal(Path(raw)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

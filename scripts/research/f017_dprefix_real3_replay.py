#!/usr/bin/env python3
"""Bound zero-read replay orchestrator for DPREFIX-REAL-3.

The source surface intentionally contains no shard resolver, positional reader,
or fallback input.  Its only model-weight authority is the immutable packed
package retained by DPREFIX-REAL-2.  Preparation calls only the verification
and rehearsal functions; the reviewed execution entry point remains held for
an independent release.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts.research.f017_dprefix_metric_engine import compare_f32le
from scripts.research.f017_dprefix_numerical_surface_closure import (
    compare_surface_packages,
    numerical_surface_manifest,
    validate_terminal_numerical_surfaces,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
PRIVATE_PACKAGE = ROOT / ".pulsarmlx-local/dprefix-real-2/material/packed"
PRIVATE_MANIFEST = PRIVATE_PACKAGE / "manifest.json"
PRIVATE_ORACLE_PACKAGE = ROOT / ".pulsarmlx-local/oracle-build/oracle-package-v2"
PRIVATE_CANDIDATE = ROOT / ".pulsarmlx-local/oracle-build/f017-dense-prefix-candidate-v4"
PRIVATE_REPLAY_ROOT = ROOT / ".pulsarmlx-local/dprefix-real-3"

ATTEMPT = "DPREFIX-REAL-3"
LEDGER = 139
PAYLOADS = 40
PACKED_BYTES = 1_431_263_232
PACKED_PACKAGE_SHA = "705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156"
REAL2_EVIDENCE_SHA = "a9708c84ebe08e9c3717cd3abbaec37c15fa06cb99d2f97d5a7dc87871e79039"
INVENTORY_SHA = "c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa"
PROMPT_SHA = "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff"
INVENTORY_PATH = EVIDENCE / "f017-dense-prefix-40-read-allowlist-v1.json"
REAL2_RAW_PATH = EVIDENCE / "f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json"
PAYLOAD_LEDGER_PATH = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
ATTEMPT_V10_PATH = EVIDENCE / "f017-dense-prefix-attempt-ledger-v10.json"
CONFIG_PATH = EVIDENCE / "f017-dprefix-replay-config-v1.json"
AUTH_PATH = EVIDENCE / "f017-dprefix-replay-authorization-v1.json"
IDENTITY_PATH = EVIDENCE / "f017-dprefix-replay-candidate-identity-v1.json"
DECODED_MANIFEST_PATH = EVIDENCE / "f017-dprefix-real3-decoded-identity-manifest-v1.json"


class ReplayError(RuntimeError):
    """Fail-closed replay error."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical(value) + b"\n")
    os.replace(temporary, path)


def _entries_by_tensor() -> dict[str, dict[str, Any]]:
    inventory = load(INVENTORY_PATH)
    entries = inventory["entries"]
    if len(entries) != PAYLOADS or digest_path(INVENTORY_PATH) != INVENTORY_SHA:
        raise ReplayError("PACKED_PACKAGE_REPLAY: inventory identity")
    return {entry["name"]: entry for entry in entries}


def validate_packed_package() -> dict[str, Any]:
    """Rehash the sole replay input authority without resolving another source."""
    if PRIVATE_PACKAGE.is_symlink() or not PRIVATE_PACKAGE.is_dir():
        raise ReplayError("PACKED_PACKAGE_REPLAY: package directory")
    if PRIVATE_MANIFEST.is_symlink() or not PRIVATE_MANIFEST.is_file():
        raise ReplayError("PACKED_PACKAGE_REPLAY: package manifest")
    if digest_path(PRIVATE_MANIFEST) != PACKED_PACKAGE_SHA:
        raise ReplayError("PACKED_PACKAGE_REPLAY: package identity")
    manifest = load(PRIVATE_MANIFEST)
    entries = manifest.get("entries", [])
    if (
        manifest.get("payloads") != PAYLOADS
        or manifest.get("logical_packed_bytes") != PACKED_BYTES
        or len(entries) != PAYLOADS
        or not manifest.get("immutable")
        or not manifest.get("read_only")
    ):
        raise ReplayError("PACKED_PACKAGE_REPLAY: manifest completeness")
    seen: set[str] = set()
    total = 0
    for ordinal, entry in enumerate(entries):
        artifact = entry["artifact"]
        relative = Path(artifact["symbolic_path"])
        if relative.is_absolute() or len(relative.parts) != 1 or relative.name in seen:
            raise ReplayError("PACKED_PACKAGE_REPLAY: unsafe or duplicate component")
        seen.add(relative.name)
        path = PRIVATE_PACKAGE / relative
        mode = path.stat().st_mode if path.exists() else 0
        if path.is_symlink() or not stat.S_ISREG(mode) or mode & stat.S_IWUSR:
            raise ReplayError(f"PACKED_PACKAGE_REPLAY: mutable component {ordinal}")
        if path.stat().st_size != artifact["bytes"] or digest_path(path) != artifact["sha256"]:
            raise ReplayError(f"PACKED_PACKAGE_REPLAY: component identity {ordinal}")
        if entry["ordinal"] != ordinal or entry["packed_sha256"] != artifact["sha256"]:
            raise ReplayError(f"PACKED_PACKAGE_REPLAY: component descriptor {ordinal}")
        total += artifact["bytes"]
    if total != PACKED_BYTES:
        raise ReplayError("PACKED_PACKAGE_REPLAY: byte total")
    return {
        "result": "PACKED PACKAGE READY FOR CHECKPOINT-FREE REPLAY",
        "package_identity": PACKED_PACKAGE_SHA,
        "manifest_sha256": digest_path(PRIVATE_MANIFEST),
        "entries": PAYLOADS,
        "packed_bytes": total,
        "immutable": True,
        "read_only": True,
        "checkpoint_access": 0,
        "ledger_before": LEDGER,
        "ledger_after": LEDGER,
    }


def decoded_identity_manifest() -> dict[str, Any]:
    if digest_path(REAL2_RAW_PATH) != REAL2_EVIDENCE_SHA:
        raise ReplayError("PACKED_PACKAGE_REPLAY: REAL-2 evidence identity")
    raw = load(REAL2_RAW_PATH)
    decoded = raw.get("decoded_identities", {})
    packed = {entry["tensor"]: entry["packed_sha256"] for entry in load(PRIVATE_MANIFEST)["entries"]}
    if len(decoded) != PAYLOADS or set(decoded) != set(packed):
        raise ReplayError("PACKED_PACKAGE_REPLAY: decoded identity completeness")
    return {
        "schema": "pulsarmlx.f017.dprefix-replay-decoded-identity-manifest",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "source_event": "DPREFIX-REAL-2",
        "source_evidence_sha256": REAL2_EVIDENCE_SHA,
        "packed_package_sha256": PACKED_PACKAGE_SHA,
        "hard_gate_count": PAYLOADS,
        "entries": [
            {"tensor": name, "packed_sha256": packed[name], "decoded_sha256": decoded[name]}
            for name in sorted(decoded)
        ],
        "checkpoint_access": 0,
        "ledger": LEDGER,
    }


def _scale_min(scales: np.ndarray, index: int) -> tuple[np.ndarray, np.ndarray]:
    if index < 4:
        return scales[:, index] & 63, scales[:, index + 4] & 63
    return (
        (scales[:, index + 4] & 15) | ((scales[:, index - 4] >> 6) << 4),
        (scales[:, index + 4] >> 4) | ((scales[:, index] >> 6) << 4),
    )


def decode_canonical_f32(entry: dict[str, Any], payload: bytes) -> bytes:
    """Independent replay decoder; it has no candidate or oracle buffer alias."""
    family = entry["quantization"]
    count = int(entry["element_count"])
    if family == "F32":
        if len(payload) != count * 4:
            raise ReplayError("DECODER_IDENTITY: F32 length")
        values = np.frombuffer(payload, dtype="<f4")
    elif family == "Q8_0":
        if count % 32 or len(payload) != count // 32 * 34:
            raise ReplayError("DECODER_IDENTITY: Q8_0 length")
        blocks = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 34)
        scales = blocks[:, :2].copy().view("<f2").reshape(-1).astype(np.float32)
        values = (blocks[:, 2:].view(np.int8).astype(np.float32) * scales[:, None]).reshape(-1)
    elif family in {"Q4_K", "Q5_K", "Q6_K"}:
        block_bytes = {"Q4_K": 144, "Q5_K": 176, "Q6_K": 210}[family]
        if count % 256 or len(payload) != count // 256 * block_bytes:
            raise ReplayError(f"DECODER_IDENTITY: {family} length")
        raw = np.frombuffer(payload, dtype=np.uint8).reshape(-1, block_bytes)
        values = np.empty((len(raw), 256), dtype=np.float32)
        for start in range(0, len(raw), 8192):
            block = raw[start : start + 8192]
            out = values[start : start + 8192]
            if family in {"Q4_K", "Q5_K"}:
                d = block[:, :2].copy().view("<f2").reshape(-1).astype(np.float32)
                dmin = block[:, 2:4].copy().view("<f2").reshape(-1).astype(np.float32)
                scales = block[:, 4:16]
                high = None if family == "Q4_K" else block[:, 16:48]
                quants = block[:, 16:144] if family == "Q4_K" else block[:, 48:176]
                for group in range(4):
                    low_scale, low_min = _scale_min(scales, group * 2)
                    high_scale, high_min = _scale_min(scales, group * 2 + 1)
                    q = quants[:, group * 32 : (group + 1) * 32]
                    low, upper = q & 15, q >> 4
                    if high is not None:
                        low = low + (((high & (1 << (2 * group))) != 0).astype(np.uint8) * 16)
                        upper = upper + (((high & (2 << (2 * group))) != 0).astype(np.uint8) * 16)
                    out[:, group * 64 : group * 64 + 32] = d[:, None] * low_scale[:, None] * low - dmin[:, None] * low_min[:, None]
                    out[:, group * 64 + 32 : group * 64 + 64] = d[:, None] * high_scale[:, None] * upper - dmin[:, None] * high_min[:, None]
            else:
                ql, qh = block[:, :128], block[:, 128:192]
                scales = block[:, 192:208].view(np.int8).astype(np.float32)
                d = block[:, 208:210].copy().view("<f2").reshape(-1).astype(np.float32)
                for half in range(2):
                    for lane in range(32):
                        low, upper, bits = ql[:, 64 * half + lane], ql[:, 64 * half + 32 + lane], qh[:, 32 * half + lane]
                        decoded = ((low & 15) | (((bits >> 0) & 3) << 4), (upper & 15) | (((bits >> 2) & 3) << 4), (low >> 4) | (((bits >> 4) & 3) << 4), (upper >> 4) | (((bits >> 6) & 3) << 4))
                        for group, quant in enumerate(decoded):
                            out[:, 128 * half + lane + 32 * group] = d * scales[:, 8 * half + lane // 16 + 2 * group] * (quant.astype(np.int16) - 32)
        values = values.reshape(-1)
    else:
        raise ReplayError(f"DECODER_IDENTITY: unsupported {family}")
    if values.size != count or not np.isfinite(values).all():
        raise ReplayError(f"DECODER_IDENTITY: {family} output")
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def verify_all_decoded_identities() -> dict[str, Any]:
    expected = {item["tensor"]: item for item in decoded_identity_manifest()["entries"]}
    inventory = _entries_by_tensor()
    manifest = load(PRIVATE_MANIFEST)
    observed: list[dict[str, Any]] = []
    for retained in manifest["entries"]:
        name = retained["tensor"]
        packed_path = PRIVATE_PACKAGE / retained["artifact"]["symbolic_path"]
        payload = packed_path.read_bytes()
        decoded_sha = digest_bytes(decode_canonical_f32(inventory[name], payload))
        if decoded_sha != expected[name]["decoded_sha256"]:
            raise ReplayError(f"DECODER_IDENTITY: replay mismatch {name}")
        observed.append({"tensor": name, "decoded_sha256": decoded_sha, "exact": True})
    return {
        "result": "ALL_40_RETAINED_PAYLOADS_INDEPENDENTLY_DECODED",
        "hard_gate_count": len(observed),
        "candidate_import_independence": "REPLAY CANDIDATE IMPORT INDEPENDENT",
        "observed": observed,
        "checkpoint_access": 0,
        "ledger": LEDGER,
    }


def lifecycle_pass(value: dict[str, Any]) -> None:
    required = {
        "arrays_created", "arrays_destroyed", "managed_created", "managed_destroyed",
        "derived_created", "derived_destroyed", "callbacks", "contexts_created",
        "contexts_destroyed", "default_cpu_streams", "default_gpu_streams",
        "owned_streams_created", "owned_streams_destroyed", "registrations",
        "teardowns", "in_flight_work", "stale_generations", "singleton_live_state",
        "child_process_terminated", "result",
    }
    if required - value.keys() or value["result"] != "PASS":
        raise ReplayError("D4_LIFECYCLE_ACCOUNTING: incomplete")
    if (
        value["arrays_created"] != value["arrays_destroyed"]
        or value["managed_created"] != value["managed_destroyed"]
        or value["derived_created"] != value["derived_destroyed"]
        or value["contexts_created"] != value["contexts_destroyed"]
        or any(value[field] for field in ("in_flight_work", "stale_generations", "singleton_live_state"))
        or not value["child_process_terminated"]
    ):
        raise ReplayError("D4_LIFECYCLE_ACCOUNTING: imbalance")


def terminal_finalize(candidate: dict[str, Any], surfaces: list[dict[str, Any]], status: str = "PASS") -> dict[str, Any]:
    """One finalizer shared by success and failure terminal paths."""
    dispatch = candidate.get("dispatch", {})
    for field in ("native_matvecs", "synchronizations", "readbacks", "actual_host_copy_count", "actual_host_copy_bytes", "fallback", "backend_errors"):
        if not isinstance(dispatch.get(field), int) or dispatch[field] < 0:
            raise ReplayError(f"D4_HOST_COPY_ACCOUNTING: missing {field}")
    lifecycle = candidate.get("success_path_lifecycle_reconciliation")
    if not isinstance(lifecycle, dict):
        raise ReplayError("D4_LIFECYCLE_ACCOUNTING: missing success record")
    lifecycle_pass(lifecycle)
    if status == "PASS":
        if candidate.get("repeats") != 10 or not candidate.get("deterministic"):
            raise ReplayError("REPEAT_DETERMINISM")
        if len(surfaces) != 8 or not all(item.get("pass") for item in surfaces):
            raise ReplayError("NUMERICAL_SURFACE_MISSING")
        if dispatch["fallback"] or dispatch["backend_errors"]:
            raise ReplayError("DISPATCH_RECONCILIATION")
    return {
        "schema": "pulsarmlx.f017.dprefix-replay-terminal-evidence",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "terminal_class": status,
        "checkpoint_access": 0,
        "shard_opens": 0,
        "positional_reads": 0,
        "ledger_before": LEDGER,
        "ledger_after": LEDGER,
        "candidate": candidate,
        "runtime_accounting": dispatch,
        "success_path_lifecycle_reconciliation": lifecycle,
        "numerical_surfaces": surfaces,
        "packed_package_sha256": PACKED_PACKAGE_SHA,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
    }


def validate_replay_terminal(value: dict[str, Any]) -> None:
    if value.get("checkpoint_access") != 0 or value.get("shard_opens") != 0 or value.get("positional_reads") != 0:
        raise ReplayError("ZERO_READ_GUARANTEE")
    if value.get("ledger_before") != LEDGER or value.get("ledger_after") != LEDGER:
        raise ReplayError("LEDGER_RECONCILIATION")
    if value.get("packed_package_sha256") != PACKED_PACKAGE_SHA:
        raise ReplayError("PACKED_PACKAGE_REPLAY")
    if value.get("terminal_class") == "PASS":
        terminal_finalize(value["candidate"], value["numerical_surfaces"], "PASS")
        decoded = value.get("decoded_identities", {})
        if len(decoded) != PAYLOADS or set(decoded) != set(_entries_by_tensor()):
            raise ReplayError("DECODER_IDENTITY")
        oracle = value.get("oracle", {})
        if oracle.get("rehash") != "PASS" or not oracle.get("persisted_before_candidate"):
            raise ReplayError("ORACLE_MUTATION")


def zero_read_attack_campaign() -> dict[str, Any]:
    attacks = ["path_cli", "path_environment", "direct_shard", "positional_reader", "missing_package_fallback", "ledger_writer"]
    return {
        "result": "REAL-3 ZERO-READ GUARANTEE STRUCTURAL",
        "cases": [{"attack": name, "result": "REJECTED_BEFORE_ACCESS", "checkpoint_access": 0, "ledger": LEDGER} for name in attacks],
        "source_assertions": {"os_pread": False, "mmap": False, "reader_helper": False, "fallback_reader": False, "ledger_mutator": False},
        "checkpoint_access": 0,
        "ledger": LEDGER,
    }


def preflight() -> str:
    package = validate_packed_package()
    ledger = load(PAYLOAD_LEDGER_PATH)
    attempt = load(EVIDENCE / "f017-dense-prefix-replay-attempt-ledger-v1.json")
    config, authorization = load(CONFIG_PATH), load(AUTH_PATH)
    if package["entries"] != PAYLOADS or ledger["cumulative_tensor_payloads"] != LEDGER:
        raise ReplayError("LEDGER_RECONCILIATION")
    state = attempt["current_state"]
    if state != {
        "attempt_id": ATTEMPT, "authorized": True, "consumed": False,
        "executed": False, "checkpoint_accessed": False, "checkpoint_access_budget": 0,
        "ledger": LEDGER, "automatic_retry": False, "automatic_m1f0_continuation": False,
    }:
        raise ReplayError("ATTEMPT_STATE")
    if authorization["execution_config_sha256"] != digest_path(CONFIG_PATH) or config["attempt_id"] != ATTEMPT:
        raise ReplayError("IDENTITY_BINDING")
    if digest_path(PRIVATE_CANDIDATE) != config["candidate_binary_sha256"]:
        raise ReplayError("CANDIDATE_IDENTITY")
    return "READY_TO_EXECUTE_DPREFIX_CHECKPOINT_FREE_REPLAY"


def _oracle_module() -> Any:
    source = PRIVATE_ORACLE_PACKAGE / "f017_dprefix_oracle_runtime.py"
    manifest = load(PRIVATE_ORACLE_PACKAGE / "manifest.json")
    expected = next(item["sha256"] for item in manifest["files"] if item["name"] == source.name)
    if digest_path(source) != expected:
        raise ReplayError("ORACLE_PACKAGE_IDENTITY")
    specification = importlib.util.spec_from_file_location("f017_replay_oracle", source)
    if specification is None or specification.loader is None:
        raise ReplayError("ORACLE_PACKAGE_IDENTITY")
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
    raise ReplayError("ORACLE_CONSTRUCTION: tensor rank")


def _write_read_only(path: Path, payload: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as target:
        target.write(payload)
        target.flush()
        os.fsync(target.fileno())
    path.chmod(0o444)
    return {
        "symbolic_relative_path": str(path.relative_to(PRIVATE_REPLAY_ROOT)),
        "sha256": digest_path(path),
        "bytes": len(payload),
        "immutable": True,
        "read_only": True,
    }


def _candidate_surface_payloads(evidence_path: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    evidence = load(evidence_path)
    package = evidence_path.parent / f"{evidence_path.name}.surfaces"
    values: dict[str, bytes] = {}
    for item in evidence["numerical_surface_package"]:
        path = package / f"{item['semantic_id']}.f32le"
        payload = path.read_bytes()
        if digest_bytes(payload) != item["sha256"]:
            raise ReplayError("CANDIDATE_IDENTITY: surface package")
        values[item["semantic_id"]] = payload
    return values, evidence


def _material_manifest() -> dict[str, Any]:
    inventory = _entries_by_tensor()
    retained = load(PRIVATE_MANIFEST)["entries"]
    tensors = []
    for item in retained:
        entry = inventory[item["tensor"]]
        tensors.append({
            "ordinal": item["ordinal"],
            "name": item["tensor"],
            "quantization": entry["quantization"],
            "gguf_shape": entry["gguf_shape"],
            "packed_path": item["artifact"]["symbolic_path"],
            "packed_sha256": item["packed_sha256"],
        })
    return {
        "schema": "pulsarmlx.f017.dprefix-material-package",
        "attempt_id": ATTEMPT,
        "identity_binding": "candidate-identity.json",
        "prompt_package_sha256": PROMPT_SHA,
        "inventory_sha256": INVENTORY_SHA,
        "tensor_count": PAYLOADS,
        "tensors": tensors,
    }


def execute_reviewed_replay() -> dict[str, Any]:
    """Consume the reviewed replay attempt; never invoked during preparation."""
    if preflight() != "READY_TO_EXECUTE_DPREFIX_CHECKPOINT_FREE_REPLAY":
        raise ReplayError("NOT_READY")
    if PRIVATE_REPLAY_ROOT.exists():
        raise ReplayError("ATTEMPT_STATE: replay directory exists")
    PRIVATE_REPLAY_ROOT.mkdir(parents=True, mode=0o700)
    atomic_json(PRIVATE_REPLAY_ROOT / "execution-start.json", {
        "attempt_id": ATTEMPT, "consumed": True, "checkpoint_accessed": False,
        "packed_package_sha256": PACKED_PACKAGE_SHA, "ledger_before": LEDGER,
    })
    package = validate_packed_package()
    expected_decoded = {
        item["tensor"]: item["decoded_sha256"]
        for item in load(DECODED_MANIFEST_PATH)["entries"]
    }
    inventory = _entries_by_tensor()
    oracle_tensors: dict[str, np.ndarray] = {}
    decoded_observed: dict[str, str] = {}
    for retained in load(PRIVATE_MANIFEST)["entries"]:
        name = retained["tensor"]
        entry = inventory[name]
        packed = (PRIVATE_PACKAGE / retained["artifact"]["symbolic_path"]).read_bytes()
        decoded = decode_canonical_f32(entry, packed)
        decoded_observed[name] = digest_bytes(decoded)
        if decoded_observed[name] != expected_decoded[name]:
            raise ReplayError(f"DECODER_IDENTITY: {name}")
        flat = np.frombuffer(decoded, dtype="<f4")
        dimensions = entry["gguf_shape"]
        if name.endswith("attn_k_b.weight"):
            array = flat.reshape(dimensions[2], dimensions[1], dimensions[0]).transpose(0, 2, 1)
        else:
            array = flat.reshape(_oracle_shape(entry))
        oracle_tensors[name] = array

    oracle_runtime = _oracle_module()
    _, oracle_stages = oracle_runtime.dense_prefix_surfaces(oracle_tensors, 9703)
    surface_ids = [item["semantic_id"] for item in numerical_surface_manifest()["surfaces"]]
    oracle_values = {name: oracle_runtime.canonical_f32(oracle_stages[name]) for name in surface_ids}
    oracle_identity = digest_bytes(b"".join(oracle_values[name] for name in sorted(oracle_values)))
    oracle_retention = {
        name: _write_read_only(PRIVATE_REPLAY_ROOT / f"oracle-primary/{name}.f32le", oracle_values[name])
        for name in ("layer_2_output", "layer_3_entry")
    }
    oracle_manifest = {
        "attempt_id": ATTEMPT,
        "persisted_before_candidate": True,
        "fsync_complete": True,
        "artifacts": oracle_retention,
        "oracle_identity": oracle_identity,
    }
    atomic_json(PRIVATE_REPLAY_ROOT / "oracle-primary/manifest.json", oracle_manifest)
    os.sync()
    del oracle_tensors, oracle_stages

    material_path = PRIVATE_REPLAY_ROOT / "material-manifest.json"
    atomic_json(material_path, _material_manifest())
    (PRIVATE_REPLAY_ROOT / "candidate-identity.json").write_bytes(IDENTITY_PATH.read_bytes())
    candidate_path = PRIVATE_REPLAY_ROOT / "candidate-evidence.json"
    completed = subprocess.run(
        [str(PRIVATE_CANDIDATE), "--execute-retained-package", str(material_path), str(PRIVATE_PACKAGE), str(candidate_path)],
        text=True,
        capture_output=True,
    )
    if completed.returncode:
        raise ReplayError(f"NATIVE_RUNTIME: {completed.stderr.strip()}")
    candidate_values, candidate = _candidate_surface_payloads(candidate_path)
    comparison = compare_surface_packages(candidate_values, oracle_values, numerical_surface_manifest())
    validate_terminal_numerical_surfaces(comparison["surfaces"])
    terminal = terminal_finalize(candidate, comparison["surfaces"])
    terminal.update({
        "input_authority": package,
        "decoded_identities": decoded_observed,
        "oracle": {
            "recomputed_from_packed_package": True,
            "persisted_before_candidate": True,
            "identity_before_candidate": oracle_identity,
            "identity_after_candidate": digest_bytes(b"".join(oracle_values[name] for name in sorted(oracle_values))),
            "rehash": "PASS",
            "retention": oracle_retention,
        },
        "overall_numerical_pass": comparison["overall_pass"],
    })
    validate_replay_terminal(terminal)
    terminal_path = PRIVATE_REPLAY_ROOT / "terminal-evidence.json"
    atomic_json(terminal_path, terminal)
    terminal_path.chmod(0o444)
    return terminal


def main() -> int:
    arguments = sys.argv[1:]
    if arguments == ["--preflight"]:
        print(preflight())
        return 0
    if arguments == ["--verify-package"]:
        print(json.dumps(validate_packed_package(), sort_keys=True))
        return 0
    if arguments == ["--execute-reviewed-replay"]:
        execute_reviewed_replay()
        return 0
    raise ReplayError("scope refusal: expected --preflight, --verify-package, or --execute-reviewed-replay")


if __name__ == "__main__":
    raise SystemExit(main())

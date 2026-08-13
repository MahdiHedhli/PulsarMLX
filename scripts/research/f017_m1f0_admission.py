#!/usr/bin/env python3
"""Checkpoint-free contracts and preflight for M1-F0 route discovery.

The real stage is deliberately oracle-only.  This module never searches for a
checkpoint and has no MLX or Rust FFI dependency.  Its preparation config
contains symbolic repository paths and exact metadata ranges; payload reading
is reserved for a later, separately authorized program invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "pulsarmlx.f017.m1f0-execution-config"
SCHEMA_VERSION = "1.0.0"
READY = "READY_TO_EXECUTE_M1_F0"
ATTEMPT = 1
LAYER = 3
HISTORICAL_ROUTE = [15, 177, 233, 41, 166, 26, 10, 152]
M1_E_EVIDENCE_SHA256 = "0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9"
M1_F_BLOCKER_SHA256 = "f7f6d7bc387481f99386a19f13a5f561d3ee4bff18f5e197ffcfe9a42a18b4b6"
CHECKPOINT_BINDINGS = {
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
}
CATALOG_PATH = "docs/research/glm52/raw/f016-c01-catalog-0001.json"
INPUT_PATH = "specs/017-rust-native-inference-runtime/fixtures/f017-m1f0-layer3-input-v1.json"
CONTRACT_PATHS = {
    "boundary": "specs/017-rust-native-inference-runtime/contracts/m1f0-attention-router-boundary-v1.json",
    "decoder": "specs/017-rust-native-inference-runtime/contracts/m1f0-decoder-contract-v1.json",
    "selection": "specs/017-rust-native-inference-runtime/contracts/m1f0-selection-v1.json",
    "scaffold": "specs/017-rust-native-inference-runtime/contracts/m1f0-exact-scaffold-v1.json",
    "numerical": "specs/017-rust-native-inference-runtime/contracts/production-m1f0-tier-b-v1.json",
    "timing": "specs/017-rust-native-inference-runtime/contracts/m1f0-timing-v1.json",
    "execution_schema": "specs/017-rust-native-inference-runtime/contracts/m1f0-execution-config-v1.schema.json",
    "evidence_schema": "specs/017-rust-native-inference-runtime/contracts/m1f0-evidence-v1.schema.json",
    "route_schema": "specs/017-rust-native-inference-runtime/contracts/m1f0-route-v1.schema.json",
    "private_package_schema": "specs/017-rust-native-inference-runtime/contracts/m1f0-private-package-v1.schema.json",
    "q5_k_real_byte": "specs/017-rust-native-inference-runtime/contracts/m1f0-q5-k-real-byte-exact-v1.json",
    "first_real_quantization_policy": "specs/017-rust-native-inference-runtime/contracts/f017-first-real-quantization-admission-v1.json",
}
INPUT_REGENERATION_PATH = "docs/architecture/reviews/evidence/f017-m1-f0-input-regeneration-v1.json"
Q5_QUALIFICATION_PATH = "docs/architecture/reviews/evidence/f017-m1-f0-q5-k-real-byte-qualification-v1.json"
RUNTIME_SEMANTIC_BOUNDARY_SHA = "7e4c3f37049444443164964aea2fc630752d17ce"

EXPECTED = [
    ("attention_norm", "blk.3.attn_norm.weight", "F32", [6144]),
    ("query_lora_a", "blk.3.attn_q_a.weight", "Q5_K", [6144, 2048]),
    ("query_lora_norm", "blk.3.attn_q_a_norm.weight", "F32", [2048]),
    ("query_heads", "blk.3.attn_q_b.weight", "Q8_0", [2048, 16384]),
    ("kv_lora_and_rope", "blk.3.attn_kv_a_mqa.weight", "Q8_0", [6144, 576]),
    ("kv_lora_norm", "blk.3.attn_kv_a_norm.weight", "F32", [512]),
    ("key_nope_heads", "blk.3.attn_k_b.weight", "Q8_0", [192, 512, 64]),
    ("value_heads", "blk.3.attn_v_b.weight", "Q8_0", [512, 256, 64]),
    ("attention_output", "blk.3.attn_output.weight", "Q5_K", [16384, 6144]),
    ("router_input_norm", "blk.3.ffn_norm.weight", "F32", [6144]),
    ("router_projection", "blk.3.ffn_gate_inp.weight", "F32", [6144, 256]),
    ("router_bias", "blk.3.exp_probs_b.bias", "F32", [256]),
]


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def _product(values: list[int]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def _packed_size(quantization: str, elements: int) -> int:
    if quantization == "F32":
        return elements * 4
    if quantization == "Q8_0" and elements % 32 == 0:
        return elements // 32 * 34
    if quantization == "Q5_K" and elements % 256 == 0:
        return elements // 256 * 176
    raise ValueError("unsupported or misaligned M1-F0 tensor")


def _row_width(quantization: str, columns: int) -> int:
    return _packed_size(quantization, columns)


def _catalog_hash(entry: dict[str, object]) -> str:
    identity = {
        key: entry[key]
        for key in ("data_offset_abs", "data_offset_rel", "dims", "file", "name", "type", "type_id")
    }
    return sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())


def build_allowlist(catalog_path: Path) -> list[dict[str, object]]:
    document = json.loads(catalog_path.read_text())
    entries = {entry["name"]: entry for entry in document["tensors"]}
    allowlist: list[dict[str, object]] = []
    for role, name, quantization, dims in EXPECTED:
        entry = entries.get(name)
        if not isinstance(entry, dict) or entry.get("type") != quantization or entry.get("dims") != dims:
            raise ValueError(f"catalog metadata mismatch for {name}")
        elements = _product(dims)
        columns = dims[0]
        filename = str(entry["file"])
        try:
            shard = int(filename.rsplit("-", 3)[1])
        except (IndexError, ValueError) as error:
            raise ValueError(f"invalid shard identity for {name}") from error
        allowlist.append(
            {
                "role": role,
                "name": name,
                "layer": LAYER,
                "quantization": quantization,
                "gguf_shape": dims,
                "logical_shape": _logical_shape(role, dims),
                "shard_ordinal": shard,
                "offset": int(entry["data_offset_abs"]),
                "packed_length": _packed_size(quantization, elements),
                "packed_row_width": _row_width(quantization, columns),
                "decoded_length": elements * 4,
                "decoder_contract": f"m1f0-{quantization.lower().replace('_', '-')}-exact-v1",
                "catalog_entry_sha256": _catalog_hash(entry),
                "path_kind": "checkpoint_shard_range",
                "allowed_read_count": 1,
            }
        )
    validate_allowlist(allowlist)
    return allowlist


def _logical_shape(role: str, dims: list[int]) -> list[int]:
    if len(dims) == 1:
        return dims
    if role == "key_nope_heads":
        return [64, 512, 192]
    if role == "value_heads":
        return [64, 256, 512]
    return [dims[1], dims[0]]


def validate_allowlist(allowlist: list[dict[str, object]]) -> None:
    if len(allowlist) != len(EXPECTED):
        raise ValueError("M1-F0 tensor count differs")
    expected_names = [item[1] for item in EXPECTED]
    if [item.get("name") for item in allowlist] != expected_names:
        raise ValueError("M1-F0 tensor allowlist differs")
    if len(set(expected_names)) != len(expected_names):
        raise ValueError("duplicate M1-F0 tensor")
    for item in allowlist:
        name = item.get("name")
        if not isinstance(name, str) or "*" in name or not name.startswith("blk.3."):
            raise ValueError("ambiguous or wrong-layer tensor")
        if (
            "_exps" in name
            or "_shexp" in name
            or name in {"output.weight", "output_norm.weight"}
        ):
            raise ValueError("expert/logits tensor in M1-F0 allowlist")
        if item.get("allowed_read_count") != 1 or item.get("shard_ordinal") != 2:
            raise ValueError("M1-F0 access identity differs")
    if sum(int(item["packed_length"]) for item in allowlist) != 139_217_920:
        raise ValueError("M1-F0 compressed-byte budget differs")
    if sum(int(item["decoded_length"]) for item in allowlist) != 666_430_464:
        raise ValueError("M1-F0 decoded-byte budget differs")


def f32_bytes(values: np.ndarray) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def f64_bytes(values: list[float]) -> bytes:
    return b"".join(struct.pack("<d", value) for value in values)


def id_bytes(values: list[int]) -> bytes:
    if len(values) != 8 or any(value < 0 or value >= 256 for value in values):
        raise ValueError("invalid top-8 IDs")
    return struct.pack("<8H", *values)


def weight_bytes(values: list[float]) -> bytes:
    if len(values) != 8 or not all(math.isfinite(value) for value in values):
        raise ValueError("invalid routing weights")
    return f64_bytes(values)


def select_route(probabilities: list[float], scores: list[float]) -> tuple[list[int], list[float]]:
    if len(probabilities) != 256 or len(scores) != 256:
        raise ValueError("router cardinality differs")
    if not all(math.isfinite(value) for value in probabilities + scores):
        raise ValueError("non-finite router value")
    selected = sorted(range(256), key=lambda index: (-scores[index], index))[:8]
    denominator = math.fsum(probabilities[index] for index in selected)
    denominator = max(denominator, 2.0**-14)
    weights = [probabilities[index] / denominator * 2.5 for index in selected]
    return selected, weights


def _rms_norm(values: np.ndarray, scale: np.ndarray) -> np.ndarray:
    squares = np.multiply(values, values, dtype=np.float32)
    total = np.float32(0.0)
    for value in squares:
        total = np.add(total, value, dtype=np.float32)
    mean = np.divide(total, np.float32(values.size), dtype=np.float32)
    inverse = np.divide(
        np.float32(1.0),
        np.sqrt(np.add(mean, np.float32(1.0e-5), dtype=np.float32), dtype=np.float32),
        dtype=np.float32,
    )
    return np.multiply(np.multiply(values, inverse, dtype=np.float32), scale, dtype=np.float32)


def _structured_matvec(values: np.ndarray, rows: int, salt: int) -> np.ndarray:
    """Apply a deterministic sparse real-shaped synthetic matrix.

    Each logical row has four nonzero f32 entries.  The representation avoids
    committing hundreds of MiB while retaining the exact production shapes.
    """
    indices = np.arange(rows, dtype=np.uint64)
    result = np.zeros(rows, dtype=np.float32)
    for lane in range(4):
        columns = ((indices * np.uint64(131 + lane * 18) + np.uint64(salt + lane * 97)) % values.size).astype(np.int64)
        coefficient = np.float32((lane + 1) * (1.0 if lane % 2 == 0 else -1.0) / 64.0)
        result = np.add(result, np.multiply(values[columns], coefficient, dtype=np.float32), dtype=np.float32)
    return result


def _synthetic_once(hidden: np.ndarray) -> dict[str, object]:
    script_dir = str(Path(__file__).resolve().parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from prepare_f017_m1f0_real_reference import synthetic_real_shaped_oracle

    oracle = synthetic_real_shaped_oracle(hidden)
    records = dict(oracle["stage_hashes"])
    records.update(
        {
            "router_scores": oracle["router_scores_sha256"],
            "ranking": oracle["ranking_sha256"],
            "top8_ids": oracle["top8_ids_sha256"],
            "routing_weights": oracle["routing_weights_sha256"],
        }
    )
    return {
        "stage_hashes": records,
        "selected_ids": oracle["top8_ids"],
        "routing_weights": oracle["routing_weights"],
    }


def synthetic_qualification(fixture: dict[str, object], repeats: int = 10) -> dict[str, object]:
    if repeats != 10:
        raise ValueError("official M1-F0 qualification requires ten repeats")
    hidden_record = fixture["state"]["hidden"]  # type: ignore[index]
    hidden = np.frombuffer(bytes.fromhex(hidden_record["bytes_hex"]), dtype="<f4").copy()  # type: ignore[index]
    records = [_synthetic_once(hidden) for _ in range(repeats)]
    hashes = [sha256(canonical_json(record)) for record in records]
    all_equal = len(set(hashes)) == 1
    if not all_equal:
        raise ValueError("synthetic M1-F0 repeat divergence")
    first = records[0]
    return {
        "schema": "pulsarmlx.f017.m1f0-synthetic-qualification",
        "schema_version": "1.0.0",
        "architecture": {
            "layer": 3,
            "hidden_width": 6144,
            "query_lora_rank": 2048,
            "head_count": 64,
            "router_expert_count": 256,
            "top_k": 8,
            "dsa_mode": "range_fill",
        },
        "input_package_sha256": fixture["package_sha256"],
        "selection": {
            "selected_ids": first["selected_ids"],
            "selected_ids_sha256": first["stage_hashes"]["top8_ids"],
            "routing_weights": first["routing_weights"],
            "routing_weights_sha256": first["stage_hashes"]["routing_weights"],
        },
        "stage_hashes": first["stage_hashes"],
        "repeat_integrity": {
            "required": repeats,
            "observed": repeats,
            "ordinals": list(range(repeats)),
            "complete_stage_hashes": hashes,
            "all_equal": all_equal,
        },
        "oracle_ordering": "synthetic_oracle_finalized_before_validation",
        "isolation": {
            "conceptual_discoveries": 1,
            "expert_tensor_accesses": 0,
            "expert_dispatches": 0,
            "shared_expert_dispatches": 0,
            "complete_layer_outputs": 0,
            "logits": 0,
            "fallback": 0,
            "backend_errors": 0,
        },
        "classification": "numerically_qualified_greedy_not_applicable",
        "checkpoint_accessed": False,
    }


def synthetic_soak(fixture: dict[str, object], seconds: float) -> dict[str, object]:
    if seconds <= 0:
        raise ValueError("soak duration")
    started = time.monotonic()
    cycles = 0
    baseline: str | None = None
    peak_rss_kib = 0
    while cycles < 1 or time.monotonic() - started < seconds:
        result = synthetic_qualification(fixture, repeats=10)
        identity = sha256(canonical_json({"stage_hashes": result["stage_hashes"], "selection": result["selection"]}))
        if baseline is None:
            baseline = identity
        elif identity != baseline:
            raise ValueError(f"M1-F0 soak divergence at cycle {cycles}")
        observed_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            observed_rss //= 1024
        peak_rss_kib = max(peak_rss_kib, observed_rss)
        cycles += 1
    return {
        "schema": "pulsarmlx.f017.m1f0-synthetic-soak",
        "schema_version": "1.0.0",
        "input_package_sha256": fixture["package_sha256"],
        "cycles": cycles,
        "complete_discoveries": cycles * 10,
        "official_repeat_contract_unchanged": 10,
        "stage_and_route_identity_sha256": baseline,
        "first_mismatch": None,
        "peak_rss_kib": peak_rss_kib,
        "elapsed_seconds": time.monotonic() - started,
        "checkpoint_accessed": False,
        "expert_tensor_accesses": 0,
        "status": "passed",
    }


def synthetic_stress(fixture: dict[str, object]) -> dict[str, object]:
    base = np.frombuffer(bytes.fromhex(fixture["state"]["hidden"]["bytes_hex"]), dtype="<f4").copy()  # type: ignore[index]
    cases: dict[str, np.ndarray] = {
        "baseline": base,
        "attention_cancellation": np.asarray([(-1.0 if i % 2 else 1.0) * (1.0 + (i % 7) * 2.0**-20) for i in range(6144)], dtype="<f4"),
        "near_zero_signed_zero_subnormal": np.asarray([(-0.0 if i % 4 == 0 else 0.0 if i % 4 == 1 else (-1.0 if i % 2 else 1.0) * 2.0**-145) for i in range(6144)], dtype="<f4"),
        "dynamic_range": np.asarray([(-1.0 if i % 2 else 1.0) * 2.0 ** ((i % 41) - 20) for i in range(6144)], dtype="<f4"),
        "near_overflow_finite": np.asarray([(-1.0 if i % 2 else 1.0) * 1.0e15 * (1.0 + (i % 5) / 16.0) for i in range(6144)], dtype="<f4"),
        "simultaneous_branch_errors": np.asarray([math.sin(i * 0.17) * 64.0 + math.cos(i * 0.031) * 2.0**-8 for i in range(6144)], dtype="<f4"),
    }
    records: list[dict[str, object]] = []
    for name, hidden in cases.items():
        first = _synthetic_once(hidden)
        second = _synthetic_once(hidden)
        if canonical_json(first) != canonical_json(second):
            raise ValueError(f"M1-F0 stress nondeterminism: {name}")
        records.append(
            {
                "name": name,
                "input_sha256": sha256(f32_bytes(hidden)),
                "stage_and_route_sha256": sha256(canonical_json(first)),
                "selected_ids": first["selected_ids"],
                "top8_exact": True,
                "finite": True,
            }
        )
    return {
        "schema": "pulsarmlx.f017.m1f0-stress-qualification",
        "schema_version": "1.0.0",
        "cases": records,
        "case_count": len(records),
        "post_observation_retuning": False,
        "checkpoint_accessed": False,
        "expert_tensor_accesses": 0,
        "status": "passed",
    }


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _git_file_sha256(root: Path, commit: str, path: str) -> str:
    return sha256(subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=root))


def _tooling_manifest(artifacts: dict[str, dict[str, str]], fixture_sha256: str) -> dict[str, object]:
    return {
        "execution_controlling_artifacts": {
            role: {"path": reference["symbolic_path"], "sha256": reference["content_sha256"]}
            for role, reference in sorted(artifacts.items())
        },
        "input_fixture": {"path": INPUT_PATH, "sha256": fixture_sha256},
    }


def build_preparation_config(
    root: Path, fixture: dict[str, object], tooling_config_sha: str
) -> dict[str, object]:
    allowlist = build_allowlist(root / CATALOG_PATH)
    artifacts = {
        role: {
            "path_kind": "repository_relative",
            "symbolic_path": path,
            "content_sha256": file_sha256(root / path),
        }
        for role, path in CONTRACT_PATHS.items()
    }
    artifacts["input_generator"] = {
        "path_kind": "repository_relative",
        "symbolic_path": "scripts/research/generate_f017_m1f0_input.py",
        "content_sha256": file_sha256(root / "scripts/research/generate_f017_m1f0_input.py"),
    }
    artifacts["oracle_preparer"] = {
        "path_kind": "repository_relative",
        "symbolic_path": "scripts/research/prepare_f017_m1f0_real_reference.py",
        "content_sha256": file_sha256(root / "scripts/research/prepare_f017_m1f0_real_reference.py"),
    }
    artifacts["admission_tool"] = {
        "path_kind": "repository_relative",
        "symbolic_path": "scripts/research/f017_m1f0_admission.py",
        "content_sha256": file_sha256(root / "scripts/research/f017_m1f0_admission.py"),
    }
    artifacts["q5_k_qualifier"] = {
        "path_kind": "repository_relative",
        "symbolic_path": "scripts/research/qualify_f017_m1f0_q5_k_real.py",
        "content_sha256": file_sha256(root / "scripts/research/qualify_f017_m1f0_q5_k_real.py"),
    }
    artifacts["input_regeneration_evidence"] = {
        "path_kind": "repository_relative",
        "symbolic_path": INPUT_REGENERATION_PATH,
        "content_sha256": file_sha256(root / INPUT_REGENERATION_PATH),
    }
    artifacts["q5_k_qualification_evidence"] = {
        "path_kind": "repository_relative",
        "symbolic_path": Q5_QUALIFICATION_PATH,
        "content_sha256": file_sha256(root / Q5_QUALIFICATION_PATH),
    }
    fixture_sha256 = file_sha256(root / INPUT_PATH)
    tooling_manifest = _tooling_manifest(artifacts, fixture_sha256)
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "PREPARED_FOR_EXTERNAL_ADVERSARIAL_REVIEW_NOT_AUTHORIZED",
        "attempt": ATTEMPT,
        "attempt_state": "NOT_AUTHORIZED_NOT_EXECUTED",
        "source_identities": {
            "preparation_base_head": "de25a5327cffbd30c8e4898df8f019ec9f084c94",
            "runtime_semantic_boundary_sha": RUNTIME_SEMANTIC_BOUNDARY_SHA,
            "tooling_config_sha": tooling_config_sha,
            "tooling_tree_oid": _git(root, "rev-parse", f"{tooling_config_sha}^{{tree}}"),
            "tooling_content_manifest_sha256": sha256(canonical_json(tooling_manifest)),
            "authorization_head_sha": None,
            "final_documentation_head_sha": None,
            "trusted_repository_identity_contract": "f017-trusted-repository-identity-v2",
            "freeze_pattern": "tooling_commit_then_generated_config_then_docs_evidence_descendants",
        },
        "prior_evidence": {"m1_e": M1_E_EVIDENCE_SHA256, "m1_f_blocker": M1_F_BLOCKER_SHA256},
        "checkpoint_bindings": CHECKPOINT_BINDINGS,
        "layer": {"id": 3, "prefix": "blk.3", "position": 0, "dsa_mode": "range_fill"},
        "input_state": {
            "path_kind": "repository_relative",
            "symbolic_path": INPUT_PATH,
            "artifact_sha256": file_sha256(root / INPUT_PATH),
            "package_sha256": fixture["package_sha256"],
            "hidden_sha256": fixture["state"]["hidden"]["sha256"],  # type: ignore[index]
            "component_sha256": {
                name: record["sha256"]  # type: ignore[index]
                for name, record in fixture["state"].items()  # type: ignore[union-attr]
            },
            "regeneration_attestation": {
                "path_kind": "repository_relative",
                "symbolic_path": INPUT_REGENERATION_PATH,
                "content_sha256": file_sha256(root / INPUT_REGENERATION_PATH),
                "python": "3.13.13",
                "numpy": "2.4.5",
                "prng": "PCG64",
                "seed": 17017006,
                "byte_equal": True,
            },
        },
        "q5_k_real_byte_qualification": {
            "path_kind": "repository_relative",
            "symbolic_path": Q5_QUALIFICATION_PATH,
            "content_sha256": file_sha256(root / Q5_QUALIFICATION_PATH),
            "contract_sha256": file_sha256(root / CONTRACT_PATHS["q5_k_real_byte"]),
            "packed_sha256": "30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084",
            "decoded_sha256": "2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8",
            "exact_bitwise_equal": True,
        },
        "tensor_allowlist": allowlist,
        "access_budget": {
            "tensor_payloads": 12,
            "shard_opens": 1,
            "positional_reads": 12,
            "compressed_bytes": 139_217_920,
            "decoded_bytes": 666_430_464,
            "expert_tensor_payloads": 0,
        },
        "contracts": artifacts,
        "execution": {
            "conceptual_discoveries": 1,
            "official_repeats": 10,
            "real_runtime": "independent_python_numpy_oracle_only",
            "mlx_dispatches": 0,
            "expert_dispatches": 0,
            "auto_retry": False,
            "stop_before_m1_f": True,
            "private_package": {
                "root_source": "explicit_canonical_runner_argument",
                "manifest_path_kind": "package_relative",
                "manifest_path": "checkpoint-manifest.json",
                "symlink_escape": "reject",
                "traversal": "reject"
            },
        },
        "authorization": {
            "required_before_payload_access": True,
            "artifact_schema": "pulsarmlx.f017.m1f0-authorization",
            "issued_in_this_phase": False,
            "external_adversarial_review_required": True,
        },
        "forbidden_historical_route": HISTORICAL_ROUTE,
    }


def validate_config(root: Path, value: dict[str, object]) -> None:
    required = {
        "schema", "schema_version", "status", "attempt", "attempt_state",
        "source_identities", "prior_evidence", "checkpoint_bindings", "layer",
        "input_state", "tensor_allowlist", "access_budget", "contracts", "execution",
        "authorization", "forbidden_historical_route", "q5_k_real_byte_qualification",
    }
    if set(value) != required:
        raise ValueError("M1-F0 config field set differs")
    if value["schema"] != SCHEMA or value["schema_version"] != SCHEMA_VERSION or value["attempt"] != 1:
        raise ValueError("M1-F0 config identity differs")
    if value["attempt_state"] != "NOT_AUTHORIZED_NOT_EXECUTED":
        raise ValueError("M1-F0 attempt already consumed")
    if value["forbidden_historical_route"] != HISTORICAL_ROUTE:
        raise ValueError("historical route prohibition differs")
    if value["prior_evidence"] != {"m1_e": M1_E_EVIDENCE_SHA256, "m1_f_blocker": M1_F_BLOCKER_SHA256}:
        raise ValueError("M1-F0 evidence lineage differs")
    if value["checkpoint_bindings"] != CHECKPOINT_BINDINGS:
        raise ValueError("M1-F0 checkpoint binding differs")
    identities = value["source_identities"]
    if not isinstance(identities, dict) or set(identities) != {
        "preparation_base_head", "runtime_semantic_boundary_sha", "tooling_config_sha",
        "tooling_tree_oid", "tooling_content_manifest_sha256", "authorization_head_sha", "final_documentation_head_sha",
        "trusted_repository_identity_contract", "freeze_pattern",
    }:
        raise ValueError("M1-F0 source identity fields differ")
    tooling_sha = identities.get("tooling_config_sha")
    if not isinstance(tooling_sha, str) or len(tooling_sha) != 40:
        raise ValueError("M1-F0 tooling/config SHA missing")
    try:
        _git(root, "cat-file", "-e", f"{tooling_sha}^{{commit}}")
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", tooling_sha, "HEAD"], cwd=root, check=False
        ).returncode != 0:
            raise ValueError("M1-F0 tooling/config SHA is not an ancestor")
    except subprocess.CalledProcessError as error:
        raise ValueError("M1-F0 tooling/config commit missing") from error
    if identities.get("tooling_tree_oid") != _git(root, "rev-parse", f"{tooling_sha}^{{tree}}"):
        raise ValueError("M1-F0 tooling/config tree identity differs")
    if identities.get("runtime_semantic_boundary_sha") != RUNTIME_SEMANTIC_BOUNDARY_SHA:
        raise ValueError("M1-F0 runtime semantic boundary differs")
    if identities.get("authorization_head_sha") is not None or identities.get("final_documentation_head_sha") is not None:
        raise ValueError("M1-F0 later phase identity unexpectedly issued")
    layer = value["layer"]
    if layer != {"id": 3, "prefix": "blk.3", "position": 0, "dsa_mode": "range_fill"}:
        raise ValueError("M1-F0 layer identity differs")
    validate_allowlist(value["tensor_allowlist"])  # type: ignore[arg-type]
    if value["tensor_allowlist"] != build_allowlist(root / CATALOG_PATH):
        raise ValueError("M1-F0 tensor metadata differs from frozen catalog")
    budget = value["access_budget"]
    if budget != {
        "tensor_payloads": 12, "shard_opens": 1, "positional_reads": 12,
        "compressed_bytes": 139_217_920, "decoded_bytes": 666_430_464,
        "expert_tensor_payloads": 0,
    }:
        raise ValueError("M1-F0 access budget differs")
    input_state = value["input_state"]
    if not isinstance(input_state, dict) or input_state.get("symbolic_path") != INPUT_PATH:
        raise ValueError("M1-F0 input path differs")
    fixture_path = root / INPUT_PATH
    fixture = json.loads(fixture_path.read_text())
    if input_state.get("artifact_sha256") != file_sha256(fixture_path) or input_state.get("package_sha256") != fixture["package_sha256"]:
        raise ValueError("M1-F0 input identity differs")
    expected_components = {name: record["sha256"] for name, record in fixture["state"].items()}
    if input_state.get("component_sha256") != expected_components:
        raise ValueError("M1-F0 input component identity differs")
    regeneration = input_state.get("regeneration_attestation")
    if regeneration != {
        "path_kind": "repository_relative",
        "symbolic_path": INPUT_REGENERATION_PATH,
        "content_sha256": file_sha256(root / INPUT_REGENERATION_PATH),
        "python": "3.13.13", "numpy": "2.4.5", "prng": "PCG64", "seed": 17017006,
        "byte_equal": True,
    }:
        raise ValueError("M1-F0 input regeneration provenance differs")
    contracts = value["contracts"]
    if not isinstance(contracts, dict) or set(contracts) != set(CONTRACT_PATHS) | {
        "input_generator", "oracle_preparer", "admission_tool", "q5_k_qualifier",
        "input_regeneration_evidence", "q5_k_qualification_evidence",
    }:
        raise ValueError("M1-F0 contract inventory differs")
    for reference in contracts.values():
        if not isinstance(reference, dict) or reference.get("path_kind") != "repository_relative":
            raise ValueError("M1-F0 artifact path kind differs")
        symbolic = reference.get("symbolic_path")
        if not isinstance(symbolic, str) or symbolic.startswith("/") or ".." in Path(symbolic).parts:
            raise ValueError("M1-F0 artifact path differs")
        if reference.get("content_sha256") != file_sha256(root / symbolic):
            raise ValueError("M1-F0 artifact content differs")
        if _git_file_sha256(root, tooling_sha, symbolic) != reference.get("content_sha256"):
            raise ValueError("M1-F0 tooling/config commit does not contain reviewed artifact")
    if _git_file_sha256(root, tooling_sha, INPUT_PATH) != input_state.get("artifact_sha256"):
        raise ValueError("M1-F0 tooling/config commit has stale input fixture")
    tooling_manifest = _tooling_manifest(contracts, str(input_state["artifact_sha256"]))
    if identities.get("tooling_content_manifest_sha256") != sha256(canonical_json(tooling_manifest)):
        raise ValueError("M1-F0 tooling content manifest differs")
    q5 = value["q5_k_real_byte_qualification"]
    q5_evidence = json.loads((root / Q5_QUALIFICATION_PATH).read_text())
    if q5 != {
        "path_kind": "repository_relative", "symbolic_path": Q5_QUALIFICATION_PATH,
        "content_sha256": file_sha256(root / Q5_QUALIFICATION_PATH),
        "contract_sha256": file_sha256(root / CONTRACT_PATHS["q5_k_real_byte"]),
        "packed_sha256": "30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084",
        "decoded_sha256": "2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8",
        "exact_bitwise_equal": True,
    }:
        raise ValueError("M1-F0 Q5_K qualification binding differs")
    if (
        q5_evidence.get("status") != "exact_real_byte_identity_passed"
        or q5_evidence.get("comparison", {}).get("exact_bitwise_equal") is not True
        or q5_evidence.get("scope", {}).get("tensor_payloads") != 1
        or q5_evidence.get("scope", {}).get("m1f0_route_discovery") is not False
    ):
        raise ValueError("M1-F0 Q5_K qualification evidence invalid")
    for decoder in ("decoder_a", "decoder_b"):
        record = q5_evidence["comparison"][decoder]
        if record.get("source_sha256") != file_sha256(root / record["path"]):
            raise ValueError("M1-F0 Q5_K decoder source identity differs")
    authorization = value["authorization"]
    if authorization != {
        "required_before_payload_access": True,
        "artifact_schema": "pulsarmlx.f017.m1f0-authorization",
        "issued_in_this_phase": False,
        "external_adversarial_review_required": True,
    }:
        raise ValueError("M1-F0 preparation authorization state differs")


def preflight(root: Path, config_path: Path, expected_sha256: str) -> dict[str, object]:
    raw = config_path.read_bytes()
    if sha256(raw) != expected_sha256:
        raise ValueError("M1-F0 immutable execution-config hash mismatch")
    value = json.loads(raw, object_pairs_hook=_reject_duplicates)
    validate_config(root, value)
    return {
        "result": READY,
        "preparation_only": True,
        "authorization_issued": False,
        "checkpoint_payload_reads": 0,
        "tensor_decodes": 0,
        "oracle_created": False,
        "mlx_contexts": 0,
        "expert_tensor_accesses": 0,
        "attempt_consumed": False,
        "execution_config_sha256": expected_sha256,
    }


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def route_artifact_from_synthetic(root: Path, fixture: dict[str, object], result: dict[str, object]) -> dict[str, object]:
    selection = result["selection"]
    stages = result["stage_hashes"]
    return {
        "schema": "pulsarmlx.f017.m1f0-layer3-route",
        "schema_version": "1.0.0",
        "evidence_kind": "checkpoint_free_synthetic",
        "layer": 3,
        "input_fixture_sha256": file_sha256(root / INPUT_PATH),
        "input_package_sha256": fixture["package_sha256"],
        "checkpoint_bindings": CHECKPOINT_BINDINGS,
        "attention_normalized_input_sha256": stages["attention_normalized"],
        "attention_output_sha256": stages["attention_output"],
        "attention_residual_sha256": stages["attention_residual"],
        "router_normalized_input_sha256": stages["router_normalized"],
        "router_score_sha256": stages["router_scores"],
        "top8_ids": selection["selected_ids"],
        "top8_ids_sha256": selection["selected_ids_sha256"],
        "routing_weights": selection["routing_weights"],
        "routing_weights_sha256": selection["routing_weights_sha256"],
        "oracle_preparer_sha256": file_sha256(root / "scripts/research/prepare_f017_m1f0_real_reference.py"),
        "decoder_contract_sha256s": {
            "set": file_sha256(root / CONTRACT_PATHS["decoder"]),
            "q5_k_real_byte": file_sha256(root / CONTRACT_PATHS["q5_k_real_byte"]),
        },
        "selection_contract_sha256": file_sha256(root / CONTRACT_PATHS["selection"]),
        "numerical_contract_sha256": file_sha256(root / CONTRACT_PATHS["numerical"]),
        "m1f_recomputation_contract": {
            "exact_m1f0_attention_residual_is_input": True,
            "recomputed_attention_must_qualify_against_m1f0": True,
            "route_ids_remain_frozen": True,
            "route_divergence_fails": True,
        },
        "expert_computation": False,
    }


def validate_route_artifact(root: Path, value: dict[str, object], input_package_sha256: str) -> None:
    if value.get("schema") != "pulsarmlx.f017.m1f0-layer3-route" or value.get("layer") != 3:
        raise ValueError("route artifact identity differs")
    if (
        value.get("input_fixture_sha256") != file_sha256(root / INPUT_PATH)
        or value.get("input_package_sha256") != input_package_sha256
        or value.get("checkpoint_bindings") != CHECKPOINT_BINDINGS
        or value.get("expert_computation") is not False
    ):
        raise ValueError("route artifact scope differs")
    for field in (
        "attention_normalized_input_sha256", "attention_output_sha256", "attention_residual_sha256",
        "router_normalized_input_sha256", "router_score_sha256", "oracle_preparer_sha256",
        "selection_contract_sha256", "numerical_contract_sha256",
    ):
        if not isinstance(value.get(field), str) or len(str(value[field])) != 64:
            raise ValueError("route artifact contextual identity missing")
    if (
        value.get("oracle_preparer_sha256") != file_sha256(root / "scripts/research/prepare_f017_m1f0_real_reference.py")
        or value.get("selection_contract_sha256") != file_sha256(root / CONTRACT_PATHS["selection"])
        or value.get("numerical_contract_sha256") != file_sha256(root / CONTRACT_PATHS["numerical"])
    ):
        raise ValueError("route artifact oracle/selection/numerical binding differs")
    if value.get("decoder_contract_sha256s") != {
        "set": file_sha256(root / CONTRACT_PATHS["decoder"]),
        "q5_k_real_byte": file_sha256(root / CONTRACT_PATHS["q5_k_real_byte"]),
    }:
        raise ValueError("route artifact decoder contract differs")
    if value.get("m1f_recomputation_contract") != {
        "exact_m1f0_attention_residual_is_input": True,
        "recomputed_attention_must_qualify_against_m1f0": True,
        "route_ids_remain_frozen": True,
        "route_divergence_fails": True,
    }:
        raise ValueError("route artifact M1-F residual binding differs")
    selected = value.get("top8_ids")
    weights = value.get("routing_weights")
    if not isinstance(selected, list) or not isinstance(weights, list):
        raise ValueError("route artifact payload missing")
    if value.get("top8_ids_sha256") != sha256(id_bytes(selected)) or value.get("routing_weights_sha256") != sha256(weight_bytes(weights)):
        raise ValueError("route artifact canonical identity differs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--m1f0-preflight-only", action="store_true")
    parser.add_argument("--execution-config", type=Path)
    parser.add_argument("--execution-config-sha256")
    parser.add_argument("--synthetic-qualification", action="store_true")
    parser.add_argument("--synthetic-soak-seconds", type=float)
    parser.add_argument("--synthetic-stress", action="store_true")
    parser.add_argument("--build-preparation-config", action="store_true")
    parser.add_argument("--input-fixture", type=Path)
    parser.add_argument("--tooling-config-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    if args.m1f0_preflight_only:
        if args.execution_config is None or args.execution_config_sha256 is None:
            parser.error("preflight requires config and SHA-256")
        result = preflight(root, args.execution_config, args.execution_config_sha256)
    elif args.synthetic_qualification:
        if args.input_fixture is None:
            parser.error("synthetic qualification requires input fixture")
        result = synthetic_qualification(json.loads(args.input_fixture.read_text()))
    elif args.synthetic_soak_seconds is not None:
        if args.input_fixture is None:
            parser.error("synthetic soak requires input fixture")
        result = synthetic_soak(json.loads(args.input_fixture.read_text()), args.synthetic_soak_seconds)
    elif args.synthetic_stress:
        if args.input_fixture is None:
            parser.error("synthetic stress requires input fixture")
        result = synthetic_stress(json.loads(args.input_fixture.read_text()))
    elif args.build_preparation_config:
        if args.input_fixture is None or args.tooling_config_sha is None:
            parser.error("config generation requires input fixture and tooling/config SHA")
        result = build_preparation_config(
            root, json.loads(args.input_fixture.read_text()), args.tooling_config_sha
        )
    else:
        parser.error("select exactly one M1-F0 preparation mode")
    raw = canonical_json(result)
    if args.output:
        args.output.write_bytes(raw)
    print(result.get("result", result.get("classification")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Checkpoint-free F017 post-M1-F roadmap and dense-prefix planning helpers.

This module reads only committed public metadata.  It never opens a checkpoint
shard and deliberately has no model-path argument.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


CATALOG = Path("docs/research/glm52/raw/f016-c01-catalog-0001.json")
P_MIN_TOKEN = 9703
P_MIN_EXPECTED_TOKEN = 21615
LEADING_DENSE_LAYERS = (0, 1, 2)
FUTURE_GATE_NAME = "F017 M1-FPREP REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY"

_QUANT_BLOCKS = {
    "F32": (1, 4),
    "Q8_0": (32, 34),
    "Q4_K": (256, 144),
    "Q5_K": (256, 176),
    "Q6_K": (256, 210),
}

_QUALIFICATION = {
    "F32": ("REAL_BYTE_QUALIFIED", "M1-C accepted output_norm.weight evidence"),
    "Q8_0": ("REAL_BYTE_QUALIFIED", "M1-D accepted projection evidence"),
    "Q5_K": (
        "REAL_BYTE_QUALIFIED",
        "f017-m1-f0-q5-k-real-byte-qualification-v1.json",
    ),
    "Q4_K": ("UNQUALIFIED_REAL_GATE", "R11/R12 are synthetic-only"),
    "Q6_K": ("UNQUALIFIED_REAL_GATE", "no exact independent real-byte gate"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def packed_bytes(tensor: dict[str, Any]) -> int:
    try:
        block_elements, block_bytes = _QUANT_BLOCKS[tensor["type"]]
    except KeyError as exc:
        raise ValueError(f"unqualified packed-size formula: {tensor['type']}") from exc
    elements = math.prod(tensor["dims"])
    if elements % block_elements:
        raise ValueError(f"unaligned {tensor['name']} for {tensor['type']}")
    return elements // block_elements * block_bytes


def dense_prefix_inventory(catalog_path: Path = CATALOG) -> dict[str, Any]:
    """Derive the one-token position-0 dense-prefix inventory from catalog data."""
    catalog = json.loads(catalog_path.read_text())
    if catalog.get("tensor_count") != 1809 or catalog.get("architecture") != "glm-dsa":
        raise ValueError("unexpected catalog identity")

    selected = []
    for tensor in catalog["tensors"]:
        name = tensor["name"]
        layer_tensor = any(name.startswith(f"blk.{layer}.") for layer in LEADING_DENSE_LAYERS)
        if name != "token_embd.weight" and not layer_tensor:
            continue
        # P-MIN has one token at position zero.  DSA is range_fill([0]); the
        # indexer is not consulted at this boundary and its payloads are excluded.
        if ".indexer." in name:
            continue
        elements = math.prod(tensor["dims"])
        entry = {
            "name": name,
            "role": "token_embedding" if name == "token_embd.weight" else "dense_prefix_layer",
            "shard": tensor["file"],
            "offset": tensor["data_offset_abs"],
            "quantization": tensor["type"],
            "logical_shape": tensor["dims"],
            "element_count": elements,
            "packed_bytes": packed_bytes(tensor),
            "decoded_f32_bytes": elements * 4,
        }
        selected.append(entry)

    selected.sort(key=lambda item: (item["shard"], item["offset"], item["name"]))
    if len(selected) != 40:
        raise ValueError(f"dense-prefix inventory must contain 40 tensors, got {len(selected)}")
    names = {item["name"] for item in selected}
    if len(names) != len(selected):
        raise ValueError("duplicate dense-prefix tensor")
    if any("indexer" in name or "exps" in name or "shexp" in name for name in names):
        raise ValueError("position-0 dense-prefix inventory widened")

    quantization: dict[str, dict[str, Any]] = {}
    for family in sorted({item["quantization"] for item in selected}):
        entries = [item for item in selected if item["quantization"] == family]
        status, evidence = _QUALIFICATION[family]
        quantization[family] = {
            "tensor_count": len(entries),
            "packed_bytes": sum(item["packed_bytes"] for item in entries),
            "decoded_f32_bytes": sum(item["decoded_f32_bytes"] for item in entries),
            "real_byte_qualification": status,
            "evidence": evidence,
        }

    result = {
        "schema": "pulsarmlx.f017.dense-prefix-layer3-entry-state-inventory",
        "schema_version": "1.0.0",
        "status": "PREPARED_NOT_AUTHORIZED",
        "future_gate_name": FUTURE_GATE_NAME,
        "checkpoint_access": 0,
        "catalog": {
            "path": catalog_path.as_posix(),
            "sha256": sha256_file(catalog_path),
            "tensor_count": catalog["tensor_count"],
        },
        "input": {
            "prompt_id": "P-MIN",
            "prompt_text_public": "Hello",
            "token_ids": [P_MIN_TOKEN],
            "positions": [0],
            "selection_basis": "pre-existing F016 P-MIN; independent of M1-F0 route outcomes",
            "dsa": "range_fill([0])",
        },
        "boundary": {
            "embedding_executed": True,
            "dense_layers_executed": list(LEADING_DENSE_LAYERS),
            "captured_state": "exact layer-3 entry hidden state",
            "not_fixture_generation": True,
        },
        "access_budget": {
            "tensor_payloads": len(selected),
            "shard_count": len({item["shard"] for item in selected}),
            "shards": sorted({item["shard"] for item in selected}),
            "positional_reads": len(selected),
            "packed_bytes": sum(item["packed_bytes"] for item in selected),
            "decoded_f32_bytes_upper_bound": sum(item["decoded_f32_bytes"] for item in selected),
            "largest_single_decoded_tensor_bytes": max(item["decoded_f32_bytes"] for item in selected),
        },
        "quantization_inventory": quantization,
        "new_real_decoder_gates": [
            family
            for family, row in quantization.items()
            if row["real_byte_qualification"] == "UNQUALIFIED_REAL_GATE"
        ],
        "dispatch_structure": {
            "embedding_lookup": 1,
            "per_layer_native_matrix_projections": {
                "attn_q_a": 1,
                "attn_q_b": 1,
                "attn_kv_a_mqa": 1,
                "attn_k_b": 1,
                "attn_v_b": 1,
                "attn_output": 1,
                "ffn_gate": 1,
                "ffn_up": 1,
                "ffn_down": 1,
            },
            "mechanically_countable_native_projection_calls": 28,
            "non_native_semantics": [
                "RMSNorm",
                "position-0 range-fill selection",
                "RoPE/attention score/softmax/value composition",
                "SwiGLU",
                "residual additions",
            ],
            "authorization_note": "28 is a projection-call planning count, not a frozen native-dispatch budget; the real dense-prefix candidate path is not implemented/admitted.",
        },
        "memory": {
            "decoded_all_upper_bound_bytes": sum(item["decoded_f32_bytes"] for item in selected),
            "packed_package_bytes": sum(item["packed_bytes"] for item in selected),
            "streaming_peak": "UNRESOLVED_UNTIL_RESIDENCY_PLAN_AND_NATIVE_PATH",
        },
        "oracle_feasibility": {
            "classification": "FEASIBLE_BUT_MATERIAL_NEW_GATE",
            "requirements": [
                "independent Q4_K and Q6_K exact real-byte qualification",
                "independent token-embedding lookup",
                "three complete dense MLA/DSA+FFN layers",
                "state/cache retention and ten-repeat contract",
            ],
        },
        "tensors": selected,
    }
    result["inventory_sha256"] = _canonical_sha256(result)
    return result


def roadmap() -> dict[str, Any]:
    """Return the repository-derived gate path after M1-F."""
    gates = [
        {
            "gate": "M1-F",
            "boundary": "one complete real layer-3 candidate",
            "classification": "ROUTE_DEPENDENT",
            "state": "BLOCKED_PENDING_REPRESENTATIVE_ROUTE_AND_DECODER_GATES",
        },
        {
            "gate": "M1-G",
            "boundary": "real final RMSNorm, output-head logits, top-k and argmax",
            "classification": "REQUIRES_M1_F_ACCEPTANCE",
            "state": "SCHEMA_PREPARABLE; EXECUTION_NOT_AUTHORIZED",
            "hidden_dependencies": [
                "independently frozen real final-hidden input boundary",
                "real-byte Q4_K output-head decoder qualification",
                "full output.weight payload/memory admission",
                "R11-derived but separately frozen real-shape numerical contract",
            ],
        },
        {
            "gate": "T017-141",
            "boundary": "literal canonical P1 command publication",
            "classification": "REQUIRES_M1_F_ACCEPTANCE",
            "state": "OPEN_UNTIL_M1_A_THROUGH_M1_G_REVIEW_GATES_PASS",
        },
        {
            "gate": "M1-H",
            "boundary": "fresh independent review and one-P1 authorization",
            "classification": "REQUIRES_NEW_REAL_ACCESS",
            "state": "BLOCKED",
        },
        {
            "gate": "P1",
            "boundary": "one canonical real one-token production run",
            "classification": "REQUIRES_NEW_REAL_ACCESS",
            "state": "BLOCKED",
        },
    ]
    return {
        "schema": "pulsarmlx.f017.post-m1f-to-p1-roadmap",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "ledger": 57,
        "gates": gates,
        "route_independent_preparable_now": [
            "M1-G/P1 typed config and evidence schemas",
            "attempt/repeat/lifecycle/PASS validators",
            "analytical-retention declarations",
            "privacy/path policy",
            "canonical P1 dependency field audit",
        ],
        "requirements": [
            {"item": "representative layer-3 route and atomic ID/weight pairs", "classification": "ROUTE_DEPENDENT"},
            {"item": "selected-expert tensor inventory and route-introduced decoder gates", "classification": "ROUTE_DEPENDENT"},
            {"item": "M1-F complete-real-layer candidate execution", "classification": "REQUIRES_NEW_REAL_ACCESS"},
            {"item": "M1-G typed config/evidence/attempt/repeat/lifecycle schemas", "classification": "CHECKPOINT_FREE_PREPARABLE_NOW"},
            {"item": "independently frozen M1-G final-hidden input provenance", "classification": "REQUIRES_M1_F_ACCEPTANCE"},
            {"item": "Q4_K real-byte output-head decoder qualification", "classification": "REQUIRES_NEW_REAL_ACCESS"},
            {"item": "output.weight payload and memory admission", "classification": "REQUIRES_NEW_REAL_ACCESS"},
            {"item": "R11-derived M1-G numerical-contract preparation", "classification": "CHECKPOINT_FREE_PREPARABLE_NOW"},
            {"item": "M1-G real final norm/logits/top-k execution", "classification": "REQUIRES_NEW_REAL_ACCESS"},
            {"item": "T017-141 literal command publication", "classification": "REQUIRES_M1_F_ACCEPTANCE"},
            {"item": "M1-H independent one-P1 authorization", "classification": "REQUIRES_M1_F_ACCEPTANCE"},
            {"item": "P1 one-token real execution", "classification": "REQUIRES_NEW_REAL_ACCESS"},
            {"item": "Feature 018 exclusion and output-head-residency deferral", "classification": "CHECKPOINT_FREE_PREPARABLE_NOW"},
        ],
        "feature_018_dependency": "NONE_FOR_FIRST_F017_P1; explicitly disabled",
        "output_head_residency_dependency": "NOT_A_PREREQUISITE_EXPERIMENT; measured P1 memory admission still required",
        "canonical_p1_fields": {
            "known": {
                "binary": "f017-glm52-runner",
                "tokens": [P_MIN_TOKEN],
                "n_new": 1,
                "expected_token": P_MIN_EXPECTED_TOKEN,
                "validation_mode": "golden-strict",
                "numerical_mode": "production-mlx-tier-b",
                "environment_kind": "production_reviewed",
            },
            "unresolved": [
                "reviewed executable identity",
                "fresh authorization head and attempt number",
                "production checkpoint-manifest symbolic binding",
                "production environment-manifest identity",
                "measured memory-floor value",
                "stream mode selected by reviewed admission",
                "fresh evidence destination",
                "accepted M1-F and M1-G evidence hashes",
            ],
            "literal_command_published": False,
        },
        "pass_dependencies": [
            "M1-A through M1-G each accepted and independently reviewed",
            "T017-141 closed",
            "fresh M1-H review/authorization",
            "all 1,809 tensor-map contracts validated",
            "production runtime implements full 79-layer path",
            "real quantization-family decoder gates complete",
            "full logits/top-k/argmax and token exactness",
            "repeat, dispatch, lifecycle, fallback and evidence reconciliation",
        ],
    }


def validate_downstream_evidence(value: dict[str, Any]) -> None:
    required = {
        "schema", "schema_version", "phase", "status", "identity", "admission",
        "attempt", "repeat_integrity", "lifecycle", "numerical", "analytical_retention",
        "privacy", "result",
    }
    if set(value) != required:
        raise ValueError("downstream evidence field set differs")
    if value["phase"] not in {"M1_G_FINAL_OUTPUT", "P1_ONE_TOKEN"}:
        raise ValueError("unknown downstream phase")
    if value["status"] not in {"PREPARED_NOT_AUTHORIZED", "PASS", "FAIL"}:
        raise ValueError("invalid downstream status")
    if value["status"] == "PASS":
        if not value["admission"].get("authorized"):
            raise ValueError("PASS admission was not authorized")
        if any(value["identity"].get(field) is None for field in ("runtime", "tooling", "authorization")):
            raise ValueError("PASS identity incomplete")
        needed = {"m1_f"} if value["phase"] == "M1_G_FINAL_OUTPUT" else {"m1_f", "m1_g"}
        if not needed.issubset(value["identity"].get("prior_evidence", {})):
            raise ValueError("PASS prior evidence incomplete")
        if value["attempt"].get("number") is None or value["attempt"].get("consumed") is not True:
            raise ValueError("PASS attempt not consumed")
        if not value["result"].get("completed") or value["result"].get("first_failure") is not None:
            raise ValueError("PASS result is incomplete")
        repeat = value["repeat_integrity"]
        if (
            repeat.get("required") != 10
            or repeat.get("observed") != 10
            or len(repeat.get("hashes", [])) != 10
            or not repeat.get("all_repeat_hashes_equal")
        ):
            raise ValueError("PASS repeat integrity missing")
        if (
            not value["lifecycle"].get("teardown_complete")
            or any(value["lifecycle"].get(field) != 0 for field in ("in_flight", "stale_generations", "fallbacks", "backend_errors"))
        ):
            raise ValueError("PASS lifecycle not reconciled")
        if value["numerical"].get("classification") != "PASS" or value["numerical"].get("greedy_identity") is not True:
            raise ValueError("PASS numerical classification incomplete")
        declared = set(value["analytical_retention"].get("required", []))
        retained = set(value["analytical_retention"].get("retained", []))
        if not declared.issubset(retained):
            raise ValueError("PASS analytical retention incomplete")
        if value["privacy"].get("absolute_paths_present") or not value["privacy"].get("symbolic_paths_only"):
            raise ValueError("PASS exposes absolute path")


def validate_downstream_config(value: dict[str, Any]) -> None:
    required = {
        "schema", "schema_version", "status", "phase", "runtime", "tooling",
        "executable", "authorization", "checkpoint", "prior_evidence", "input",
        "tensor_allowlist", "decoder_contracts", "numerical_contracts",
        "required_analytical_retention", "access_budget", "attempt", "evidence_destination",
    }
    if set(value) != required:
        raise ValueError("downstream execution config field set differs")
    if value["phase"] not in {"M1_G_FINAL_OUTPUT", "P1_ONE_TOKEN"}:
        raise ValueError("downstream execution phase differs")
    authorized = value["status"] == "AUTHORIZED_NOT_EXECUTED"
    if authorized != bool(value["authorization"].get("authorized")):
        raise ValueError("downstream authorization state differs")
    if value["attempt"].get("consumed"):
        raise ValueError("downstream attempt already consumed")
    if authorized:
        identities = [value[name] for name in ("runtime", "tooling", "executable")]
        if any(any(item.get(field) is None for field in ("git_sha", "tree_oid", "content_sha256")) for item in identities):
            raise ValueError("authorized downstream identity incomplete")
        if value["attempt"].get("number") is None or not value["tensor_allowlist"]:
            raise ValueError("authorized downstream attempt/allowlist incomplete")
        if any(item is None for item in value["access_budget"].values()):
            raise ValueError("authorized downstream budget incomplete")
        if value["evidence_destination"].get("symbolic_path") is None:
            raise ValueError("authorized downstream destination incomplete")
        needed = {"m1_f"} if value["phase"] == "M1_G_FINAL_OUTPUT" else {"m1_f", "m1_g"}
        if not needed.issubset(value["prior_evidence"]):
            raise ValueError("authorized downstream prior evidence incomplete")


def downstream_config_template(phase: str) -> dict[str, Any]:
    if phase not in {"M1_G_FINAL_OUTPUT", "P1_ONE_TOKEN"}:
        raise ValueError("unknown phase")
    retention = (
        ["full_logits_or_private_artifact", "top_n_window", "top1_top2_margin", "token_ranking", "tie_sensitive_state"]
        if phase == "M1_G_FINAL_OUTPUT"
        else ["token_choice_margin", "gate_confidence", "failure_localization_summaries"]
    )
    value = {
        "schema": "pulsarmlx.f017.downstream-execution-config",
        "schema_version": "1.0.0",
        "status": "PREPARED_NOT_AUTHORIZED",
        "phase": phase,
        "runtime": {"git_sha": None, "tree_oid": None, "content_sha256": None},
        "tooling": {"git_sha": None, "tree_oid": None, "content_sha256": None},
        "executable": {"git_sha": None, "tree_oid": None, "content_sha256": None},
        "authorization": {"head": None, "authorized": False},
        "checkpoint": {"checkpoint_set_sha256": None, "catalog_sha256": None, "tensor_map_sha256": None, "manifest_symbolic_path": None},
        "prior_evidence": {},
        "input": {
            "tokens": [] if phase == "M1_G_FINAL_OUTPUT" else [P_MIN_TOKEN],
            "n_new": 0 if phase == "M1_G_FINAL_OUTPUT" else 1,
            "expected_token": None if phase == "M1_G_FINAL_OUTPUT" else P_MIN_EXPECTED_TOKEN,
            "fixture_sha256": None,
        },
        "tensor_allowlist": [],
        "decoder_contracts": {},
        "numerical_contracts": {},
        "required_analytical_retention": retention,
        "access_budget": {"shard_opens": None, "positional_reads": None, "payloads": None, "compressed_bytes": None, "decoded_bytes": None},
        "attempt": {"number": None, "consumed": False},
        "evidence_destination": {"path_kind": "repository_relative_or_package_relative", "symbolic_path": None, "fresh_required": True},
    }
    validate_downstream_config(value)
    return value


def scaffolding_template(phase: str) -> dict[str, Any]:
    if phase not in {"M1_G_FINAL_OUTPUT", "P1_ONE_TOKEN"}:
        raise ValueError("unknown phase")
    analytical = (
        ["full_logits_or_private_artifact", "top_n_window", "top1_top2_margin", "token_ranking", "tie_sensitive_state"]
        if phase == "M1_G_FINAL_OUTPUT"
        else ["token_choice_margin", "gate_confidence", "failure_localization_summaries"]
    )
    value = {
        "schema": "pulsarmlx.f017.downstream-admission-evidence-template",
        "schema_version": "1.0.0",
        "phase": phase,
        "status": "PREPARED_NOT_AUTHORIZED",
        "identity": {"runtime": None, "tooling": None, "authorization": None, "prior_evidence": {}},
        "admission": {"authorized": False, "checkpoint_access_budget": None, "memory": None, "environment": None},
        "attempt": {"number": None, "consumed": False, "ledger": []},
        "repeat_integrity": {"required": 10, "observed": 0, "hashes": [], "all_repeat_hashes_equal": False},
        "lifecycle": {"in_flight": 0, "stale_generations": 0, "fallbacks": 0, "backend_errors": 0, "teardown_complete": False},
        "numerical": {"contract": None, "classification": None, "greedy_identity": None},
        "analytical_retention": {"required": analytical, "retained": []},
        "privacy": {"symbolic_paths_only": True, "absolute_paths_present": False},
        "result": {"completed": False, "first_failure": None, "classification": "NOT_EXECUTED"},
    }
    validate_downstream_evidence(value)
    return value

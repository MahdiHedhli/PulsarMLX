#!/usr/bin/env python3
"""Validate the append-only F017 semantic-role correction and M1-F0 v2 boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-layer3-production-semantic-graph-v1.json"
BOUNDARY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-boundary-v2.json"
CORRECTION = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-semantic-role-correction-index-v1.json"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-boundary-v2-freeze.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
HISTORICAL_M1F0 = ROOT / "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-2-v1.json"
DPREFIX = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-exact1-descriptor-v1.json"
ROUTE_V31 = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
ROUTED_V1 = ROOT / "docs/architecture/reviews/evidence/f017-weighted-moe-aggregate-safety-evaluation-v1.json"
COMPLETE_V2 = ROOT / "docs/architecture/reviews/evidence/f017-complete-layer-aggregate-v2-evaluation-v1.json"
REUSE_V2 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-decoded-tensor-reuse-v2.json"

GRAPH_SHA256 = "ece281ecdd7f5d3ad9a06e76304d0d76e63499153960529676ab889059f98a7b"
BOUNDARY_SHA256 = "46a065385b110982cb9f5585b57a2f7910d1e12e01232dcae22d60ac4dbb09a1"
CORRECTION_SHA256 = "fb9c60e5f75ffe4c2100f46bfec179bd02f0872b31e9cd6091f1cd73004e3382"


class SemanticBoundaryValidationError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise SemanticBoundaryValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)


def _check_sources(items: list[dict[str, Any]], root: Path = ROOT) -> None:
    for item in items:
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise SemanticBoundaryValidationError("unsafe source path")
        if sha256_path(root / relative) != item.get("sha256"):
            raise SemanticBoundaryValidationError(f"bound source identity: {relative}")


def _check_isolation(value: dict[str, Any]) -> None:
    expected = {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "payload_reads": 0,
        "candidate_or_model_dispatches": 0,
        "gpu_dispatches": 0,
        "real_payload_ledger_before": 166,
        "real_payload_ledger_after": 166,
    }
    if value != expected:
        raise SemanticBoundaryValidationError("isolation or ledger mutation")


def validate_graph_dict(graph: dict[str, Any], root: Path = ROOT) -> None:
    if graph.get("schema") != "pulsarmlx.f017.layer3-production-semantic-graph" or graph.get("schema_version") != "1.0.0":
        raise SemanticBoundaryValidationError("semantic graph schema")
    if graph.get("status") != "FROZEN_NO_EXECUTION_AUTHORITY" or graph.get("shape") != [6144] or graph.get("layer") != 3:
        raise SemanticBoundaryValidationError("semantic graph status/shape")
    expected_order = ["S0", "A_norm", "A", "S1", "F_norm", "Route", "Routed", "Shared", "FFN", "S2"]
    if graph.get("required_order") != expected_order:
        raise SemanticBoundaryValidationError("production graph order")
    b = graph.get("boundaries", {})
    if b.get("S0", {}).get("authority_sha256") != "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11":
        raise SemanticBoundaryValidationError("S0 authority")
    if b.get("A_norm", {}).get("input") != "S0" or b.get("S1", {}).get("input") != "S0,A":
        raise SemanticBoundaryValidationError("attention residual graph")
    if b.get("F_norm", {}).get("input") != "S1" or b.get("Route", {}).get("input") != "F_norm":
        raise SemanticBoundaryValidationError("router consumes wrong state")
    if b.get("S2", {}).get("input") != "S1,FFN" or b.get("S2", {}).get("formula") != "S2=f32(f64(S1)+FFN)":
        raise SemanticBoundaryValidationError("complete production residual")
    m1f0 = graph.get("representative_m1f0_boundary", {})
    if m1f0.get("formula") != "S0->A_norm->A->S1->F_norm->Route" or any(m1f0.get(k) is not False for k in ("expert_execution", "shared_expert_execution", "complete_layer_output")):
        raise SemanticBoundaryValidationError("representative M1-F0 graph")
    if graph.get("direct_dprefix_ffn_only_boundary", {}).get("representative_m1f0_equivalent") is not False:
        raise SemanticBoundaryValidationError("direct route equivalence")
    _check_sources(graph.get("semantic_sources", []), root)
    _check_isolation(graph.get("isolation", {}))


def _expected_inventory() -> list[tuple[Any, ...]]:
    source = load_json(REUSE_V2)
    return [
        (
            item["ordinal"], item["name"], item["shard_ordinal"], item["offset"],
            item["packed_length"], item["quantization"], item["logical_shape"],
            item["packed_sha256"], item["decoded_sha256"],
        )
        for item in source["tensor_allowlist"][:9]
    ]


def validate_boundary_dict(boundary: dict[str, Any], root: Path = ROOT) -> None:
    if boundary.get("schema") != "pulsarmlx.f017.representative-m1f0-boundary" or boundary.get("schema_version") != "2.0.0":
        raise SemanticBoundaryValidationError("boundary schema")
    if boundary.get("status") != "FROZEN_NO_EXECUTION_AUTHORITY":
        raise SemanticBoundaryValidationError("boundary status")
    auth = boundary.get("authorization", {})
    if auth.get("real_event_authorized") is not False or auth.get("checkpoint_access_authorized") is not False or auth.get("candidate_or_model_dispatch_authorized") is not False:
        raise SemanticBoundaryValidationError("execution authority leaked")
    inp = boundary.get("input_authority", {})
    if (inp.get("sha256"), inp.get("semantic_location"), inp.get("position"), inp.get("dsa")) != (
        "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11",
        "S0_LAYER3_ENTRY_PRE_ATTENTION", 0, "range_fill([0])",
    ):
        raise SemanticBoundaryValidationError("canonical representative input")
    semantic = boundary.get("semantic_boundary", {})
    if "post_attention_residual(S1)->ffn_rmsnorm(F_norm)->router(Route)" not in semantic.get("formula", ""):
        raise SemanticBoundaryValidationError("attention-to-router boundary")
    if semantic.get("ends_before") != ["routed_expert_execution", "shared_expert_execution", "ffn_branch_aggregation", "complete_layer_residual"]:
        raise SemanticBoundaryValidationError("M1-F0 stop boundary")
    attention = boundary.get("attention_semantics", {})
    if attention.get("residual") != "S1 is index-ascending binary32 S0+A, added exactly once":
        raise SemanticBoundaryValidationError("attention residual semantics")
    if attention.get("blas") is not False or attention.get("gpu") is not False or attention.get("backend_dependent_reduction") is not False:
        raise SemanticBoundaryValidationError("unfrozen numerical backend")
    doctrine = boundary.get("reproducibility_doctrine", {})
    if doctrine.get("cross_environment_sha_for_bounded_class") != "FORBIDDEN" or doctrine.get("blas_class_sha_authority") != "FORBIDDEN" or doctrine.get("fresh_process_repeats") != 10:
        raise SemanticBoundaryValidationError("identity-gate doctrine")
    acceptance = boundary.get("route_acceptance", {})
    if acceptance.get("required_repeat_count") != 10 or acceptance.get("non_finite_count") != 0:
        raise SemanticBoundaryValidationError("route acceptance")
    if acceptance.get("expert_execution_required") is not False or acceptance.get("candidate_execution_required") is not False:
        raise SemanticBoundaryValidationError("M1-F0 scope")

    event = boundary.get("future_real_event_shape", {})
    if (event.get("attention_payload_reads"), event.get("packed_bytes"), event.get("shard_index"), event.get("maximum_shard_opens"), event.get("ledger_before"), event.get("ledger_after_success")) != (9, 132900864, 2, 1, 166, 175):
        raise SemanticBoundaryValidationError("future read/ledger budget")
    payloads = event.get("attention_payloads", [])
    actual = [
        (item.get("ordinal"), item.get("key"), item.get("shard"), item.get("offset"), item.get("packed_bytes"), item.get("quantization"), item.get("logical_shape"), item.get("packed_sha256"), item.get("decoded_sha256"))
        for item in payloads
    ]
    if actual != _expected_inventory():
        raise SemanticBoundaryValidationError("nine-payload inventory drift")
    if len({item[1] for item in actual}) != 9 or sum(item[4] for item in actual) != 132900864:
        raise SemanticBoundaryValidationError("inventory duplicate/byte reconciliation")

    router = boundary.get("reusable_router_authorities", [])
    expected_router = {
        "blk.3.ffn_norm.weight": "1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f",
        "blk.3.ffn_gate_inp.weight": "da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a",
        "blk.3.exp_probs_b.bias": "eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491",
    }
    if {item.get("key"): item.get("decoded_sha256") for item in router} != expected_router:
        raise SemanticBoundaryValidationError("router authority identity")
    if any(item.get("future_authority") != "CROSS_EVENT_REUSE_AUTHORIZATION_REQUIRED" for item in router):
        raise SemanticBoundaryValidationError("router reuse authority")
    if boundary.get("future_stability_work", {}).get("direct_dprefix_v31_transfer") != "FORBIDDEN":
        raise SemanticBoundaryValidationError("direct v3.1 transfer")
    ops = boundary.get("operations", {})
    if ops.get("gpu_required_for_future_event") is not False or ops.get("ntfy_topic") != "Mahdi-Dev" or len(ops.get("future_notification_points", [])) != 5:
        raise SemanticBoundaryValidationError("operational binding")
    _check_sources(boundary.get("bound_sources", []), root)
    _check_isolation(boundary.get("isolation", {}))


def validate_correction_dict(correction: dict[str, Any]) -> None:
    if correction.get("schema") != "pulsarmlx.f017.semantic-role-correction-index" or correction.get("status") != "APPEND_ONLY_ROLE_CORRECTION_NO_HISTORICAL_IDENTITY_CHANGE":
        raise SemanticBoundaryValidationError("correction schema/status")
    central = correction.get("central_finding", {})
    if central.get("equivalent_semantic_inputs") is not False or central.get("overlap") != [177]:
        raise SemanticBoundaryValidationError("central route contradiction")
    c = correction.get("corrections", {})
    if c.get("dprefix_exact_1", {}).get("corrected_role") != "CANONICAL_LAYER3_ENTRY_PRE_ATTENTION":
        raise SemanticBoundaryValidationError("DPREFIX role")
    for key in ("direct_dprefix_v31_route", "direct_dprefix_membership_proof", "direct_dprefix_selected_experts", "direct_dprefix_shared_output", "direct_dprefix_routed_aggregate_v1", "e942_complete_layer"):
        if c.get(key, {}).get("validity") != "VALID_BUT_DIFFERENT_SURFACE":
            raise SemanticBoundaryValidationError(f"different-surface preservation: {key}")
    e942 = c.get("e942_complete_layer", {})
    if e942.get("corrected_role") != "CANONICAL_DIRECT_DPREFIX_FFN_MOE_COMPLETION" or e942.get("production_complete_layer3_output") is not False or e942.get("m1f_oracle_authority") is not False:
        raise SemanticBoundaryValidationError("e942 semantic role")
    history = correction.get("historical_immutability", {})
    if history.get("historical_m1f0") != "ACCEPTED_UNCHANGED" or history.get("direct_dprefix_membership") != "1984_OF_1984_PASS_UNCHANGED" or history.get("real_payload_ledger") != 166:
        raise SemanticBoundaryValidationError("historical immutability")
    _check_isolation(correction.get("isolation", {}))


def validate_file_identities() -> None:
    expected = {
        GRAPH: GRAPH_SHA256,
        BOUNDARY: BOUNDARY_SHA256,
        CORRECTION: CORRECTION_SHA256,
        HISTORICAL_M1F0: "0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9",
        DPREFIX: "393bd6f6e933aa8a50e1a836328e91cb3a42b68b08249d723c70190f4fa52256",
        ROUTE_V31: "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4",
        ROUTED_V1: "672884e0c217600f9104d7a4d6fdd27a87e0a73fac686044de86461af98781e7",
        COMPLETE_V2: "aae05b6fed0f8dfe78da24afd38914f603a70b5b7cd3903b4d0a153c9ed2052e",
    }
    for path, digest in expected.items():
        if sha256_path(path) != digest:
            raise SemanticBoundaryValidationError(f"file identity changed: {path.name}")


def validate_evidence() -> None:
    evidence = load_json(EVIDENCE)
    if evidence.get("result") != "REPRESENTATIVE M1-F0 BOUNDARY FROZEN" or evidence.get("starting_head") != "c52837b55c3008aaac45488d63b7e2d18e4ecbcc":
        raise SemanticBoundaryValidationError("freeze disposition")
    artifacts = evidence.get("artifacts", {})
    if artifacts.get("semantic_graph", {}).get("sha256") != GRAPH_SHA256 or artifacts.get("representative_boundary", {}).get("sha256") != BOUNDARY_SHA256 or artifacts.get("role_correction_index", {}).get("sha256") != CORRECTION_SHA256:
        raise SemanticBoundaryValidationError("freeze artifact binding")
    future = evidence.get("future_event", {})
    if future.get("authorization_issued") is not False or (future.get("fresh_attention_payload_reads"), future.get("fresh_packed_bytes"), future.get("ledger_before"), future.get("ledger_after_success")) != (9, 132900864, 166, 175):
        raise SemanticBoundaryValidationError("future event evidence")
    if evidence.get("isolation") != {"checkpoint_reads":0,"shard_opens":0,"payload_reads":0,"candidate_or_model_dispatches":0,"gpu_dispatches":0,"real_payload_ledger":166}:
        raise SemanticBoundaryValidationError("freeze isolation")


def validate_privacy() -> None:
    public = "\n".join(path.read_text() for path in (GRAPH, BOUNDARY, CORRECTION, EVIDENCE))
    if any(token in public for token in ("/Users/", "/home/", "file://", "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf")):
        raise SemanticBoundaryValidationError("private path or checkpoint filename leak")


def validate_all() -> None:
    validate_file_identities()
    validate_graph_dict(load_json(GRAPH))
    validate_boundary_dict(load_json(BOUNDARY))
    validate_correction_dict(load_json(CORRECTION))
    validate_evidence()
    validate_privacy()
    ledger = load_json(LEDGER)
    if ledger.get("cumulative_tensor_payloads") != 166:
        raise SemanticBoundaryValidationError("real-payload ledger changed")
    historical = load_json(HISTORICAL_M1F0)
    if historical.get("verdict") != "M1-F0 ACCEPTED" or historical.get("oracle", {}).get("top8_ids") != [166, 78, 26, 186, 163, 199, 233, 177]:
        raise SemanticBoundaryValidationError("historical M1-F0 changed")
    direct = load_json(ROUTE_V31)
    membership = direct.get("evaluation", {}).get("membership", {})
    if membership.get("evaluated") != 1984 or membership.get("mathematical_pass_count") != 1984:
        raise SemanticBoundaryValidationError("direct-DPREFIX membership changed")


def main() -> int:
    validate_all()
    print("F017_REPRESENTATIVE_M1F0_BOUNDARY_V2_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

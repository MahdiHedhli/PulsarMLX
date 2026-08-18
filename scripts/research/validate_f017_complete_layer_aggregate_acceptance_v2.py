#!/usr/bin/env python3
"""Validate the public F017 complete-layer aggregate v2 freeze package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-complete-layer-aggregate-acceptance-v2.json"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-complete-layer-aggregate-acceptance-v2-freeze.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
V1_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-weighted-moe-aggregate-perturbation-v1.json"
V1_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-weighted-moe-aggregate-safety-evaluation-v1.json"
ROUTE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
REUSE_AUTHORIZATION = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-private-reuse-authorization-v1.json"
STARTING_HEAD = "e16cf8751476b00bd3a7b638b55e0bc5cea8ede8"
CONTRACT_SHA256 = "13896ac22c03d7354c25f4d182de828b44df0d7239dd7e269175f69d597209fe"


class CompleteLayerFreezeValidationError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _validate_bound_sources(items: list[dict[str, Any]], root: Path) -> None:
    for item in items:
        relative = Path(str(item.get("path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise CompleteLayerFreezeValidationError("non-relative bound source")
        if sha256_path(root / relative) != item.get("sha256"):
            raise CompleteLayerFreezeValidationError(f"source identity: {relative}")


def validate_contract_dict(contract: dict[str, Any], root: Path = ROOT) -> None:
    if contract.get("schema") != "pulsarmlx.f017.complete-layer-aggregate-acceptance-contract" or contract.get("schema_version") != "2.0.0":
        raise CompleteLayerFreezeValidationError("contract schema")
    if contract.get("contract_id") != "f017-complete-layer-aggregate-acceptance-v2" or contract.get("status") != "FROZEN_BEFORE_REAL_SHARED_EXPERT_OUTPUT":
        raise CompleteLayerFreezeValidationError("contract version/freeze timing")
    if contract.get("semantic_adjudication") != "COMPLETE LAYER USES R10 FINAL-OUTPUT LIMITS":
        raise CompleteLayerFreezeValidationError("semantic adjudication")

    surface = contract.get("surface", {})
    if surface.get("formula") != "L=f32(f64(R)+(M+f64(S)))" or surface.get("shape") != [6144]:
        raise CompleteLayerFreezeValidationError("complete-layer surface")
    if "added exactly once" not in surface.get("residual", "") or "then one round-to-nearest binary32 cast" not in surface.get("addition_order", ""):
        raise CompleteLayerFreezeValidationError("complete-layer arithmetic order")

    authority = contract.get("r10_final_output_authority", {})
    expected_r10 = {
        "family": "final",
        "max_absolute_error": 0.0625,
        "rmse": 0.03125,
        "cosine_similarity_minimum": 0.999,
        "thresholds_rederived": False,
        "thresholds_changed": False,
    }
    if any(authority.get(key) != value for key, value in expected_r10.items()):
        raise CompleteLayerFreezeValidationError("R10 final threshold family")
    if authority.get("sha256") != "07f6c8556373e7eec5bf326c9aa613680567cbef1d8f3956da7955e7fef3ce75":
        raise CompleteLayerFreezeValidationError("R10 source identity")
    if sha256_path(root / authority["path"]) != authority["sha256"]:
        raise CompleteLayerFreezeValidationError("R10 source changed")
    committed_r10 = load_json(root / authority["path"])
    if committed_r10.get("final") != {
        "max_absolute_error": 0.0625,
        "rmse": 0.03125,
        "cosine_similarity_minimum": 0.999,
    }:
        raise CompleteLayerFreezeValidationError("R10 final contract drift")

    routed = contract.get("routed_uncertainty_reuse", {})
    if routed.get("v1_contract_sha256") != "ff1a15c29b79681458d74452c8c72dde9c9bf5eb44637d05a7e4ea9eb1525fac":
        raise CompleteLayerFreezeValidationError("v1 contract identity")
    if routed.get("v1_evaluation_sha256") != "672884e0c217600f9104d7a4d6fdd27a87e0a73fac686044de86461af98781e7":
        raise CompleteLayerFreezeValidationError("v1 evidence identity")
    if routed.get("v1_sound_intersection_sha256") != "adbbbef090c4d10acc80d0216cc82b5a8dbe299dad4baad1a0d957f661762a50":
        raise CompleteLayerFreezeValidationError("routed interval identity")
    if routed.get("tightening_after_shared_observation") != "forbidden":
        raise CompleteLayerFreezeValidationError("anti-tightening rule")

    shared = contract.get("shared_expert_ambiguity", {})
    if shared.get("point_rule") != "delta_S=0 for this routing-only ambiguity proof after the canonical shared output passes recovery and reuse authorization":
        raise CompleteLayerFreezeValidationError("shared point rule")
    if shared.get("required_future_class") != "EXACT_CLASS plus PERSISTED_AUTHORITY":
        raise CompleteLayerFreezeValidationError("shared authority class")

    theorem = contract.get("perturbation_theorem", {})
    required_theorem = ("nominal", "admissible", "transport", "component_radius", "max_absolute", "rmse", "l2", "nominal_norm", "cosine", "cosine_derivation", "formula_selection", "rounding")
    if any(not theorem.get(key) for key in required_theorem):
        raise CompleteLayerFreezeValidationError("theorem completeness")
    if theorem.get("formula_selection") != "geometric tangent-ball formula only; no post-observation selection or intersection":
        raise CompleteLayerFreezeValidationError("cosine formula selection")

    acceptance = contract.get("acceptance", {})
    if (acceptance.get("max_absolute_error"), acceptance.get("rmse"), acceptance.get("cosine_similarity_minimum")) != (0.0625, 0.03125, 0.999):
        raise CompleteLayerFreezeValidationError("acceptance threshold mutation")
    if acceptance.get("engineering_h2_threshold") != 2.0:
        raise CompleteLayerFreezeValidationError("engineering threshold")

    inventory = contract.get("future_shared_payload_inventory", {})
    if (inventory.get("shard_index"), inventory.get("reads"), inventory.get("packed_bytes"), inventory.get("ledger_before"), inventory.get("ledger_after")) != (2, 3, 27623424, 163, 166):
        raise CompleteLayerFreezeValidationError("future recovery budget")
    payloads = inventory.get("payloads", [])
    if [item.get("role") for item in payloads] != ["gate", "up", "down"] or len({item.get("key") for item in payloads}) != 3:
        raise CompleteLayerFreezeValidationError("future inventory identity")
    if sum(int(item.get("packed_bytes", 0)) for item in payloads) != 27623424:
        raise CompleteLayerFreezeValidationError("future byte reconciliation")
    if sha256_path(root / inventory["source_path"]) != inventory["source_sha256"]:
        raise CompleteLayerFreezeValidationError("inventory source changed")

    _validate_bound_sources(contract.get("implementation_artifacts", []), root)
    _validate_bound_sources(contract.get("semantic_sources", []), root)
    history = contract.get("historical_immutability", {})
    if history.get("routed_v1_result") != "FAIL_UNCHANGED" or history.get("route_disposition") != "ROUTE NOT PROVEN INVARIANT" or history.get("real_payload_ledger") != 163:
        raise CompleteLayerFreezeValidationError("historical state")
    if contract.get("anti_fitting") != {
        "real_shared_output_loaded": False,
        "real_complete_layer_evaluated": False,
        "routed_interval_tightened": False,
        "threshold_changed": False,
        "v1_modified": False,
        "synthetic_inputs_only": True,
    }:
        raise CompleteLayerFreezeValidationError("anti-fitting declaration")
    if contract.get("isolation") != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "payload_reads": 0,
        "candidate_or_model_dispatches": 0,
        "real_payload_ledger_before": 163,
        "real_payload_ledger_after": 163,
    }:
        raise CompleteLayerFreezeValidationError("isolation")


def validate_contract(root: Path = ROOT) -> None:
    if sha256_path(root / CONTRACT.relative_to(ROOT)) != CONTRACT_SHA256:
        raise CompleteLayerFreezeValidationError("contract content identity")
    validate_contract_dict(load_json(root / CONTRACT.relative_to(ROOT)), root)


def validate_history(root: Path = ROOT) -> None:
    if sha256_path(root / V1_CONTRACT.relative_to(ROOT)) != "ff1a15c29b79681458d74452c8c72dde9c9bf5eb44637d05a7e4ea9eb1525fac":
        raise CompleteLayerFreezeValidationError("v1 contract changed")
    if sha256_path(root / V1_EVIDENCE.relative_to(ROOT)) != "672884e0c217600f9104d7a4d6fdd27a87e0a73fac686044de86461af98781e7":
        raise CompleteLayerFreezeValidationError("v1 evidence changed")
    prior = load_json(root / V1_EVIDENCE.relative_to(ROOT))
    if prior["qualifications"]["aggregate_mathematical"] != "FAIL" or prior["qualifications"]["final_route_disposition"] != "ROUTE NOT PROVEN INVARIANT":
        raise CompleteLayerFreezeValidationError("v1 result changed")
    if sha256_path(root / ROUTE_EVIDENCE.relative_to(ROOT)) != "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4":
        raise CompleteLayerFreezeValidationError("route evidence changed")
    if sha256_path(root / REUSE_AUTHORIZATION.relative_to(ROOT)) != "b370d3c3dd938eeadd18f34fabab89077319b979b994b97ffa33afddf2bffa28":
        raise CompleteLayerFreezeValidationError("reuse authorization changed")
    if load_json(root / LEDGER.relative_to(ROOT)).get("cumulative_tensor_payloads") != 163:
        raise CompleteLayerFreezeValidationError("real-payload ledger changed")


def validate_evidence(root: Path = ROOT) -> None:
    evidence = load_json(root / EVIDENCE.relative_to(ROOT))
    if evidence.get("starting_head") != STARTING_HEAD or evidence.get("result") != "COMPLETE-LAYER AGGREGATE V2 FROZEN":
        raise CompleteLayerFreezeValidationError("freeze result")
    if evidence.get("artifacts", {}).get("contract_sha256") != CONTRACT_SHA256:
        raise CompleteLayerFreezeValidationError("freeze contract binding")
    if evidence.get("isolation") != {"checkpoint_reads":0,"shard_opens":0,"payload_reads":0,"real_payload_ledger":163,"real_shared_outputs_loaded":0,"real_complete_layers_evaluated":0}:
        raise CompleteLayerFreezeValidationError("freeze isolation")
    public = json.dumps(evidence, sort_keys=True)
    if any(token in public for token in ("/Users/", "/home/", "file://")):
        raise CompleteLayerFreezeValidationError("private path leak")


def main() -> int:
    validate_contract()
    validate_history()
    validate_evidence()
    print("COMPLETE_LAYER_AGGREGATE_V2_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

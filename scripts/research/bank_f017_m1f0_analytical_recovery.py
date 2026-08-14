#!/usr/bin/env python3
"""Bank public-safe analytical recovery, access-ledger, and retention audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _artifact(name: str, payload: bytes) -> dict[str, Any]:
    return {
        "dtype": name.split(".")[-1],
        "canonical_serialization": name.split(".")[-1],
        "element_count": len(payload) // ({"lef64": 8, "lef32": 4, "leu16": 2}[name.split(".")[-1]]),
        "byte_length": len(payload),
        "sha256": sha256(payload),
        "bytes_hex": payload.hex(),
    }


def bank(private_package: Path, config_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = load(private_package / "recovery-manifest.json")
    config_raw = config_path.read_bytes()
    config = json.loads(config_raw)
    if manifest["execution_config_sha256"] != sha256(config_raw):
        raise ValueError("recovery config binding")
    payloads: dict[str, bytes] = {}
    for name, binding in manifest["private_artifacts"].items():
        raw = (private_package / binding["path"]).read_bytes()
        if sha256(raw) != binding["sha256"] or len(raw) != binding["size_bytes"]:
            raise ValueError("private analytical artifact identity")
        payloads[name] = raw
    analytics = manifest["canonical_analytics"]
    scores = analytics["scores"]
    ranking = analytics["ranking"]
    if ranking != sorted(range(256), key=lambda index: (-scores[index], index)):
        raise ValueError("ranking reconstruction")
    rank8, rank9 = ranking[7], ranking[8]
    margin = scores[rank8] - scores[rank9]
    bounds = analytics["router_score_abs_error_bounds"]
    b8, b9 = bounds[rank8], bounds[rank9]
    denominator = b8 + b9
    safety = margin / denominator if denominator > 0 else math.inf
    qualified = margin > denominator and safety >= 4.0
    top16 = [
        {"rank": ordinal + 1, "expert_id": expert, "score": scores[expert]}
        for ordinal, expert in enumerate(ranking[:16])
    ]
    historical = {15, 177, 233, 41, 166, 26, 10, 152}
    overlap = [expert for expert in analytics["top8_ids"] if expert in historical]
    bias = analytics["bias"]
    bias_ranking = sorted(range(256), key=lambda index: (-bias[index], index))
    bias_rank = {expert: bias_ranking.index(expert) + 1 for expert in overlap}
    canonical = {
        "router_probabilities": _artifact("router-probabilities.lef64", payloads["router-probabilities.lef64"]),
        "router_bias": _artifact("router-bias.lef32", payloads["router-bias.lef32"]),
        "router_scores": _artifact("router-scores.lef64", payloads["router-scores.lef64"]),
        "ranking": _artifact("ranking.leu16", payloads["ranking.leu16"]),
        "top8_ids": _artifact("top8.leu16", payloads["top8.leu16"]),
        "routing_weights": _artifact("routing-weights.lef64", payloads["routing-weights.lef64"]),
        "router_score_bounds": _artifact("router-score-bounds.lef64", payloads["router-score-bounds.lef64"]),
    }
    public = {
        "schema": "pulsarmlx.f017.m1f0-analytical-recovery",
        "schema_version": "1.0.0",
        "accepted_bindings": {
            "route_sha256": config["accepted_bindings"]["route"]["sha256"],
            "attempt_2_evidence_sha256": config["accepted_bindings"]["attempt_2_evidence"]["sha256"],
            "router_margin_blocker_sha256": config["accepted_bindings"]["router_margin_blocker"]["sha256"],
            "execution_config_sha256": sha256(config_raw),
        },
        "reproduced_identities": manifest["accepted_identities_reproduced"],
        "canonical_analytics": {
            "values": analytics,
            "artifacts": canonical,
            "top16": top16,
            "rank8": {"expert_id": rank8, "score": scores[rank8]},
            "rank9": {"expert_id": rank9, "score": scores[rank9]},
            "absolute_margin": margin,
        },
        "route_stability": {
            "contract_sha256": config["contracts"]["route_stability"]["sha256"],
            "B8": b8,
            "B9": b9,
            "B8_plus_B9": denominator,
            "margin": margin,
            "safety_factor": safety,
            "minimum_safety_factor": 4.0,
            "result": "ROUTE_STABILITY_QUALIFIED" if qualified else "ROUTE_STABILITY_NOT_QUALIFIED",
            "post_observation_retuning": False,
        },
        "historical_route_overlap": {
            "historical_route": [15, 177, 233, 41, 166, 26, 10, 152],
            "accepted_route": analytics["top8_ids"],
            "shared_experts": overlap,
            "shared_expert_bias_rank": bias_rank,
            "bias_min": min(bias),
            "bias_max": max(bias),
            "bias_population_stddev": math.sqrt(sum((value - sum(bias) / len(bias)) ** 2 for value in bias) / len(bias)),
            "interpretation": "Overlap is not evidence of contamination. Exact accepted score/ranking hash reproduction and execution-path isolation establish provenance; input-independent exp_probs_b.bias is a plausible recurrence mechanism but does not itself prove independence.",
        },
        "access": manifest["access"],
        "scope": manifest["scope"],
    }
    ledger = {
        "schema": "pulsarmlx.f017.real-tensor-payload-access-ledger-amendment",
        "schema_version": "1.0.0",
        "scope": "M1-F0 admission chain including Q5_K qualification",
        "append_only": True,
        "entries": [
            {"kind": "qualification_only", "artifact_sha256": "13899cdd1d97c65ca0c6cf0ce24cb9fae26e7c1c0d4036ec7c00529af00bc39c", "payloads": 1},
            {"kind": "route_discovery_attempt_1_rejected", "artifact_sha256": "72deffb9d1baffa2378aca18662209a9a49f5da1709c1125f6d662c3af202244", "payloads": 12},
            {"kind": "route_discovery_attempt_2_accepted", "artifact_sha256": "0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9", "payloads": 12},
            {"kind": "accepted_boundary_evidence_recovery", "artifact_sha256": None, "payloads": 12},
        ],
        "payload_count_before_recovery": 25,
        "payload_count_added": 12,
        "payload_count_after_recovery": 37,
        "metadata_or_header_accesses_counted_as_payloads": False,
    }
    audit = {
        "schema": "pulsarmlx.f017.analytical-retention-audit",
        "schema_version": "1.0.0",
        "retention_contract_sha256": config["contracts"]["analytical_retention"]["sha256"],
        "boundaries": [
            {"boundary": "R7", "analytical_quantity": "expert stage vectors", "values_retained": True, "hashes_retained": True, "future_dependency": False, "classification": "SUFFICIENT"},
            {"boundary": "R8", "analytical_quantity": "router IDs/weights and expert aggregation", "values_retained": True, "hashes_retained": True, "future_dependency": False, "classification": "SUFFICIENT"},
            {"boundary": "R9", "analytical_quantity": "attention/DSA vectors", "values_retained": True, "hashes_retained": True, "future_dependency": False, "classification": "SUFFICIENT"},
            {"boundary": "R10", "analytical_quantity": "complete-layer fixture vectors and routing", "values_retained": True, "hashes_retained": True, "future_dependency": False, "classification": "SUFFICIENT"},
            {"boundary": "R11", "analytical_quantity": "norm/logit/top-k vectors", "values_retained": True, "hashes_retained": True, "future_dependency": False, "classification": "SUFFICIENT"},
            {"boundary": "R12", "analytical_quantity": "tiny-model stage vectors", "values_retained": True, "hashes_retained": True, "future_dependency": False, "classification": "SUFFICIENT"},
            {"boundary": "M1-D", "analytical_quantity": "real projection output", "values_retained": False, "hashes_retained": True, "future_dependency": False, "classification": "HASH_ONLY_NO_FUTURE_DEPENDENCY"},
            {"boundary": "M1-E", "analytical_quantity": "real expert stage outputs", "values_retained": False, "hashes_retained": True, "future_dependency": False, "classification": "HASH_ONLY_NO_FUTURE_DEPENDENCY"},
            {"boundary": "M1-F0", "analytical_quantity": "complete router scores/ranking/cutoff/weights", "values_retained": True, "hashes_retained": True, "future_dependency": True, "classification": "SUFFICIENT", "remediation": "f017-m1-f0-router-analytical-recovery-v1.json"},
        ],
    }
    return public, ledger, audit


def write_new(path: Path, value: object) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-package", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--output-recovery", type=Path, required=True)
    parser.add_argument("--output-ledger", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    args = parser.parse_args()
    recovery, ledger, audit = bank(args.private_package, args.execution_config)
    write_new(args.output_recovery, recovery)
    recovery_sha = sha256(canonical_json(recovery))
    ledger["entries"][-1]["artifact_sha256"] = recovery_sha
    write_new(args.output_ledger, ledger)
    write_new(args.output_audit, audit)
    print(recovery_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

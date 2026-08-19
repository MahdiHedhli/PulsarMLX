#!/usr/bin/env python3
"""Validate banked concrete representative M1-F0 route values."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-concrete-route-values-v1.json"
EXECUTION_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"
PRODUCER = ROOT / "scripts/research/f017_representative_m1f0_recover_route_values_from_retention_v1.py"
EXPECTED_EXECUTION_SHA256 = "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190"
EXPECTED_PRODUCER_SHA256 = "794a9dde983cdfe103930fbbd74b137be76b2f79fc549fe3133a42731d1975fa"
EXPECTED_SELECTED_SHA256 = "a0f2e2b59ebc606c43e17eab8f76a5b14c26b678bef2a9b0207c3f7dd15f164f"
EXPECTED_WEIGHTS_SHA256 = "ff1a7127b418b80dce4e4361e314c16ad50e86484cb1861ad27f6f9ee70b8587"
EXPECTED_RANKING_SHA256 = "b2de9d7a4fe2701f0cda51f6b95a5396195e0bf0c44924aa6d46b4a899af549d"
EXPECTED_ROUTE_SHA256 = "03dc2dfbed65848fdcb649f41f98793ca0f8cdd702c76b55d71c762fc5338103"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def validate(document: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    execution_path = root / "docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"
    producer_path = root / "scripts/research/f017_representative_m1f0_recover_route_values_from_retention_v1.py"
    require(sha_file(execution_path) == EXPECTED_EXECUTION_SHA256, "EXECUTION_FILE")
    require(sha_file(producer_path) == EXPECTED_PRODUCER_SHA256, "PRODUCER_FILE")
    execution = json.loads(execution_path.read_text(encoding="utf-8"))

    require(document.get("schema") == "pulsarmlx.f017.representative-m1f0-concrete-route-values", "SCHEMA")
    require(document.get("schema_version") == "1.0.0", "SCHEMA_VERSION")
    require(document.get("status") == "RECOVERED_FROM_RETAINED_REAL_EVENT_AUTHORITY_PENDING_INDEPENDENT_REVIEW", "STATUS")
    authority = document.get("authoritative_execution", {})
    require(authority.get("commit") == "c1cdb07942e62a9b23ff775f0bbb020ba6be733c", "EXECUTION_COMMIT")
    require(authority.get("evidence_sha256") == EXPECTED_EXECUTION_SHA256, "EXECUTION_BINDING")
    require(authority.get("terminal_disposition") == "COMPLETE", "TERMINAL")
    require(authority.get("ledger") == 175, "LEDGER")
    require(authority.get("checkpoint_rereads_after_event") == 0, "CHECKPOINT_REREADS")
    require(authority.get("expert_executions") == 0, "EXPERT_EXECUTION")

    reconstruction = document.get("reconstruction", {})
    require(reconstruction.get("source") == "RETAINED_PAYLOADS_FROM_SINGLE_NINE_READ_REAL_EVENT", "SOURCE")
    require(reconstruction.get("producer_sha256") == EXPECTED_PRODUCER_SHA256, "PRODUCER_BINDING")
    require(reconstruction.get("producer_output_sha256") == "3dadd8fe24f8aa38d84368586c6bd044e02b6c4cae7c1678d7ae5a3b28bfbbfa", "PRODUCER_OUTPUT")
    require(reconstruction.get("retained_payload_count") == 9, "PAYLOAD_COUNT")
    require(reconstruction.get("dual_decoder_agreements") == 9, "DECODER_AGREEMENT")
    require(reconstruction.get("checkpoint_rereads") == 0, "RECONSTRUCTION_REREADS")
    require(reconstruction.get("shard_opens") == 0, "RECONSTRUCTION_OPENS")
    require(reconstruction.get("ledger_delta") == 0, "LEDGER_DELTA")
    require(reconstruction.get("retained_authority_before_after_unchanged") is True, "RETAINED_REHASH")
    require(reconstruction.get("direct_dprefix_route_used") is False, "DIRECT_DPREFIX_REUSE")

    selected = document.get("selected_ids", {})
    try:
        selected_values = selected["values"]
        selected_bytes = bytes.fromhex(selected["bytes_hex"])
        expected_selected_bytes = struct.pack("<8H", *selected_values)
    except (KeyError, TypeError, ValueError, struct.error):
        errors.append("SELECTED_SERIALIZATION")
        selected_values, selected_bytes, expected_selected_bytes = [], b"", b"!"
    require(selected_values == [250, 10, 237, 62, 73, 177, 218, 28], "SELECTED_VALUES")
    require(selected.get("dtype") == "uint16_le" and selected.get("shape") == [8], "SELECTED_TYPE")
    require(selected_bytes == expected_selected_bytes, "SELECTED_BYTES")
    require(hashlib.sha256(selected_bytes).hexdigest() == EXPECTED_SELECTED_SHA256, "SELECTED_HASH")
    require(selected.get("sha256") == EXPECTED_SELECTED_SHA256, "SELECTED_DECLARATION")

    weights = document.get("routing_weights", {})
    try:
        weight_values = weights["values"]
        weight_bytes = bytes.fromhex(weights["bytes_hex"])
        expected_weight_bytes = b"".join(struct.pack("<d", value) for value in weight_values)
        unpacked_weights = list(struct.unpack("<8d", weight_bytes))
    except (KeyError, TypeError, ValueError, struct.error):
        errors.append("WEIGHT_SERIALIZATION")
        weight_values, weight_bytes, expected_weight_bytes, unpacked_weights = [], b"", b"!", []
    require(weights.get("dtype") == "binary64_le" and weights.get("shape") == [8], "WEIGHT_TYPE")
    require(weight_bytes == expected_weight_bytes and unpacked_weights == weight_values, "WEIGHT_BYTES")
    require(hashlib.sha256(weight_bytes).hexdigest() == EXPECTED_WEIGHTS_SHA256, "WEIGHT_HASH")
    require(weights.get("sha256") == EXPECTED_WEIGHTS_SHA256, "WEIGHT_DECLARATION")
    require(len(weight_values) == 8 and all(math.isfinite(value) and value > 0 for value in weight_values), "WEIGHT_DOMAIN")
    require(len(weight_values) == 8 and math.fsum(weight_values) == 2.5, "WEIGHT_SUM")

    pairs = document.get("id_weight_pairs", [])
    require(len(pairs) == 8, "PAIR_COUNT")
    if len(pairs) == 8 and len(weight_values) == 8 and len(selected_values) == 8:
        for index, pair in enumerate(pairs):
            require(pair.get("ordinal") == index, "PAIR_ORDINAL")
            require(pair.get("expert_id") == selected_values[index], "PAIR_ID")
            require(pair.get("routing_weight") == weight_values[index], "PAIR_WEIGHT")
            require(pair.get("routing_weight_ieee754_le_hex") == struct.pack("<d", weight_values[index]).hex(), "PAIR_BITS")
            require(pair.get("routing_weight_float_hex") == weight_values[index].hex(), "PAIR_HEX")

    ranking = document.get("ranking_authority", {})
    require(ranking.get("dtype") == "uint16_le" and ranking.get("shape") == [256], "RANKING_TYPE")
    require(ranking.get("order") == "descending router score; expert id ascending tie-break", "RANKING_ORDER")
    require(ranking.get("sha256") == EXPECTED_RANKING_SHA256, "RANKING_HASH")
    require(ranking.get("concrete_values_required_for_expert_recovery") is False, "RANKING_REQUIREMENT")

    route = document.get("route_identity", {})
    route_input = {
        "ranking": EXPECTED_RANKING_SHA256,
        "selected_ids": EXPECTED_SELECTED_SHA256,
        "routing_weights": EXPECTED_WEIGHTS_SHA256,
    }
    require(hashlib.sha256(canonical_json(route_input)).hexdigest() == EXPECTED_ROUTE_SHA256, "ROUTE_RECOMPUTE")
    require(route.get("sha256") == EXPECTED_ROUTE_SHA256, "ROUTE_DECLARATION")
    require(route.get("matches_ten_retained_only_reproductions") is True, "REPRODUCTION_LINK")

    reproduction = document.get("reproduction_linkage", {})
    require(reproduction.get("bundle_sha256") == execution.get("reproduction", {}).get("bundle_sha256"), "REPRODUCTION_BUNDLE")
    require(reproduction.get("runs") == 10 and reproduction.get("exact_route_identity") == "10/10", "REPRODUCTION_COUNT")
    require(reproduction.get("fresh_processes") == 2, "FRESH_PROCESS_COUNT")
    require(reproduction.get("checkpoint_rereads") == 0 and reproduction.get("additional_shard_opens") == 0, "REPRODUCTION_ACCESS")

    separation = document.get("surface_separation", {})
    require(separation.get("historical_direct_dprefix_route") == "VALID_BUT_DIFFERENT_SURFACE_AND_PROHIBITED_AS_INPUT", "SURFACE_SEPARATION")
    require(separation.get("direct_dprefix_values_consumed") is False, "DIRECT_DPREFIX_VALUES")
    require(separation.get("representative_selected_ids") == selected_values, "REPRESENTATIVE_BINDING")
    require(separation.get("direct_dprefix_selected_ids") != selected_values, "DISTINCT_SURFACE_ROUTE")

    future = document.get("future_use", {})
    require(future.get("allowed_purpose") == "PREPARE_REPRESENTATIVE_EXPERT_RECOVERY_AUTHORIZATION_ONLY_AFTER_INDEPENDENT_ACCEPTANCE", "FUTURE_PURPOSE")
    require(future.get("checkpoint_access_authorized") is False, "FUTURE_CHECKPOINT_GATE")
    require(future.get("expert_execution_authorized") is False, "FUTURE_EXPERT_GATE")
    require(future.get("real_event_authorized") is False, "FUTURE_REAL_GATE")

    if "/Users/" in json.dumps(document, sort_keys=True):
        errors.append("PRIVATE_PATH")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    document = json.loads(args.evidence.read_text(encoding="utf-8"))
    errors = validate(document)
    if errors:
        print(json.dumps({"result": "REJECT", "errors": errors}, sort_keys=True))
        return 1
    print(json.dumps({
        "result": "PASS",
        "evidence_sha256": sha_file(args.evidence),
        "selected_ids_sha256": EXPECTED_SELECTED_SHA256,
        "routing_weights_sha256": EXPECTED_WEIGHTS_SHA256,
        "representative_route_sha256": EXPECTED_ROUTE_SHA256,
        "checkpoint_rereads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "ledger": 175,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

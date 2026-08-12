#!/usr/bin/env python3
"""Fail-closed validator for banked F017 M1-D attempt-3 PASS evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

RUNTIME_SHA = "1c7705c130d5909bb4523d70bc7ec45e974e1b24"
CONFIG_SHA = "42fb54d08c2c8ee8c7b06360e04743e8c8a976df649e1a0b8ef505c94c01a9fa"
REPEAT_SHA = "709789007d3dfca01a9265220fc68cbf79f3583614ce595262f082e2adaee8eb"
ORACLE_SHA = "330522cecbf088a32ce2f54ed932dd34a5db14daa6c880272c61b2eaec3d4fe4"
PREPARER_SHA = "a9474c8f9c5e76fd17beab3f84ab037105f0610dfe8f8972e4f92f52356ebb99"
PRIOR = {
    "m1_a": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def validate(document: dict) -> None:
    require(document.get("schema") == "pulsarmlx.f017.canonical-runner-evidence", "schema mismatch")
    require(document.get("schema_version") == "1.3.0", "schema version mismatch")
    identity = document["identity"]
    require(identity["source_sha"] == RUNTIME_SHA and identity["source_clean"] is True, "runtime identity mismatch")
    require(identity["environment_kind"] == "production_reviewed", "environment kind mismatch")
    require(identity["execution_config_sha256"] == CONFIG_SHA, "execution config mismatch")
    require(identity["prior_evidence"] == PRIOR, "prior evidence mismatch")
    require(identity["checkpoint"]["checkpoint_set_sha256"] == "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee", "checkpoint mismatch")
    require(identity["checkpoint"]["catalog_sha256"] == "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0", "catalog mismatch")
    libraries = identity["loaded_libraries"]
    require(len(libraries) == 2 and all(item["actual_sha256"] == item["expected_sha256"] and item["architecture"] == "arm64" for item in libraries), "loaded library mismatch")

    admission = document["admission"]
    require(admission["telemetry_source"] == "measured_host", "telemetry source mismatch")
    require(admission["available_memory_bytes"] >= admission["memory_floor_bytes"] > 0, "memory admission failed")
    require(admission["memory_pressure"] == "normal", "memory pressure unsafe")
    require(admission["competing_processes_clear"] is True and not admission["competing_processes"], "competing process present")
    require(admission["port_1234_listener"] is False, "port 1234 listener present")
    require(admission["thermal_state"] == "normal" and admission["performance_warning"] is False, "thermal/performance gate failed")

    execution = document["execution"]
    require(execution["storage"] == {"read_bytes": 3760128, "read_count": 1}, "real matrix read count mismatch")
    require(execution["projection_count"] == 1 and execution["quant_decode_count"] == 1, "projection/decode count mismatch")
    require(execution["expert_execution_count"] == 0 and execution["layer_execution_count"] == 0 and execution["logits_count"] == 0 and execution["p1"] is False, "isolation mismatch")
    require(execution["dispatch"] == {"native": 10, "direct": 0, "qualification_scaffold": 0, "explicit_reference": 0, "fallback": 0, "errors": 0}, "dispatch mismatch")
    require(execution["numerical_classification"] == "numerically_qualified_greedy_not_applicable", "classification mismatch")
    numerical = execution["numerical"]
    require(numerical["greedy_applicability"] == "not_applicable", "greedy applicability mismatch")
    require(numerical["oracle_generator_sha"] == PREPARER_SHA, "oracle preparer mismatch")
    require(numerical["deterministic_repeat_count"] == 10, "deterministic count mismatch")
    for field in ("max_abs_error", "rmse", "cosine_similarity"):
        require(math.isfinite(numerical[field]), f"{field} is non-finite")
    require(numerical["max_abs_error"] <= 0.5095961046235974, "max-absolute Tier-B bound failed")
    require(numerical["rmse"] <= 0.1495906979161905, "RMSE Tier-B bound failed")
    require(numerical["cosine_similarity"] >= 0.867507213998622, "cosine Tier-B bound failed")

    repeat = numerical["repeat_integrity"]
    require(repeat["repeat_count_required"] == repeat["repeat_count_observed"] == 10, "repeat count mismatch")
    require([item["ordinal"] for item in repeat["outputs"]] == list(range(10)), "repeat ordinals mismatch")
    require(len(repeat["outputs"]) == 10 and all(item["output_sha256"] == REPEAT_SHA for item in repeat["outputs"]), "repeat hash mismatch")
    require(repeat["all_repeat_hashes_equal"] is True and repeat["selected_output_sha256"] == REPEAT_SHA, "repeat equality/selection mismatch")

    ordering = numerical["oracle_ordering"]
    require(ordering["oracle_package_sha256"] == ORACLE_SHA, "oracle hash mismatch")
    require(ordering["oracle_completion_marker"] == "oracle_finalized_sequence_0", "oracle completion marker mismatch")
    require(ordering["candidate_start_marker"] == "candidate_started_sequence_1", "candidate marker mismatch")
    require(ordering["oracle_validated_before_candidate"] is True and ordering["structural_order_valid"] is True, "oracle ordering invariant failed")
    require(int(ordering["oracle_completed_at"]) < int(ordering["candidate_started_at"]), "oracle completion is not before candidate")

    lifecycle = document["lifecycle"]
    post = lifecycle["post"]
    require(lifecycle["reconciled"] is True, "lifecycle not reconciled")
    require(post["managed_created"] == post["managed_destroyed"] == 2, "managed ownership mismatch")
    require(post["derived_created"] == post["derived_destroyed"] == 10, "derived ownership mismatch")
    require(post["callback_count"] == post["managed_created"], "callback mismatch")
    require(post["default_cpu_stream_created"] == post["default_cpu_stream_freed"] and post["owned_stream_created"] == post["owned_stream_freed"], "stream mismatch")
    require(post["active_contexts"] == 0 and post["singleton_claimed"] is False, "active context/singleton")
    require(document["result"] == {"classification": "PASS", "first_failure": None, "stop_reason": None, "completed": True}, "PASS result mismatch")

    serialized = json.dumps(document, sort_keys=True)
    require("/Users/" not in serialized and "file://" not in serialized, "private path leaked")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    document = json.loads(args.evidence.read_text(), object_pairs_hook=reject_duplicate_keys)
    validate(document)
    print("f017 M1-D attempt-3 PASS evidence valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

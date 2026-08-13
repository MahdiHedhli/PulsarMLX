#!/usr/bin/env python3
"""Fail-closed validator for the accepted F017 M1-E attempt-3 evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {
    "runtime": "7e4c3f37049444443164964aea2fc630752d17ce",
    "authorization": "2f196e9c3de2e8275e8e0844a42270a376d9c519",
    "config": "8213c5fa1c59900a0590977079d0d88f5b55d0faa30e2fa262430271bc3cef2a",
    "m1_a": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
    "m1_d": "dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c",
    "attempt_1": "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119",
    "attempt_2": "8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00",
    "checkpoint_set": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "gate_packed": "3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3",
    "up_packed": "261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af",
    "down_packed": "442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d",
    "gate_decoded": "849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db",
    "up_decoded": "4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10",
    "down_decoded": "f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae",
    "oracle": "e500f0f9edca67ae42b3302bdb4105ded044a8b42c755aa58abee9af7302dbff",
    "final_reference": "ae1fa8e468418c8f0103a772ba4cf1380ed587435ace37d527642f8f0cda5213",
    "final_bound": "05273dc57a7c8822f0cbf988d465debf1f4010004cd10299ff6e607f9ac6a3d4",
}


def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    document = json.loads(raw, object_pairs_hook=reject_duplicates)
    require(document["schema"] == "pulsarmlx.f017.canonical-runner-evidence", "schema")
    require(document["schema_version"] == "1.3.0", "schema version")

    result = document["result"]
    require(result == {"classification": "PASS", "first_failure": None,
                       "stop_reason": None, "completed": True}, "result")

    identity = document["identity"]
    require(identity["compiled_runtime_sha"] == EXPECTED["runtime"], "runtime")
    require(identity["tooling_sha"] == EXPECTED["runtime"], "tooling")
    require(identity["authorization_head_sha"] == EXPECTED["authorization"], "authorization")
    require(identity["source_clean"] is True, "source clean")
    require(identity["execution_config_sha256"] == EXPECTED["config"], "config")
    require(identity["environment_kind"] == "production_reviewed", "environment")
    require(identity["platform"]["architecture"] == "arm64", "architecture")
    for library in identity["loaded_libraries"]:
        require(library["actual_sha256"] == library["expected_sha256"], "loaded library")
        require(library["architecture"] == "arm64", "loaded library architecture")
    checkpoint = identity["checkpoint"]
    require(checkpoint["accessed"] is True, "checkpoint accessed")
    require(checkpoint["checkpoint_set_sha256"] == EXPECTED["checkpoint_set"], "checkpoint set")
    require(checkpoint["catalog_sha256"] == EXPECTED["catalog"], "catalog")
    for key in ("m1_a", "m1_b", "m1_c", "m1_d", "m1_e_attempt_1", "m1_e_attempt_2"):
        expected_key = {"m1_e_attempt_1": "attempt_1", "m1_e_attempt_2": "attempt_2"}.get(key, key)
        require(identity["prior_evidence"][key] == EXPECTED[expected_key], f"prior evidence {key}")

    execution = document["execution"]
    require(execution["attempt_state"] == "execution_started", "attempt state")
    require(execution["attempt_consumed"] is True, "attempt consumed")
    require(execution["progress_state"] == "m1e_one_expert_complete", "progress")
    require(execution["storage"] == {"read_bytes": 11304960, "read_count": 3}, "storage")
    require(execution["dispatch"] == {"native": 30, "direct": 0,
            "qualification_scaffold": 0, "explicit_reference": 0,
            "fallback": 0, "errors": 0}, "dispatch")
    require(execution["expert_execution_count"] == 1, "expert count")
    require(execution["projection_count"] == 3, "projection count")
    require(execution["quant_decode_count"] == 3, "decode count")
    require(execution["layer_execution_count"] == 0 and execution["logits_count"] == 0,
            "layer/logits isolation")
    for key in ("p1", "p2", "golden_eight", "feature_018"):
        require(execution[key] is False, key)

    numerical = execution["numerical"]
    require(execution["numerical_classification"] ==
            "numerically_qualified_greedy_not_applicable", "classification")
    require(numerical["greedy_applicability"] == "not_applicable", "greedy applicability")
    require(numerical["expert_payload_sha256"] == {
        "gate": EXPECTED["gate_packed"], "up": EXPECTED["up_packed"],
        "down": EXPECTED["down_packed"]}, "packed identities")
    require(numerical["expert_decoded_sha256"] == {
        "gate": EXPECTED["gate_decoded"], "up": EXPECTED["up_decoded"],
        "down": EXPECTED["down_decoded"]}, "decoded identities")
    require(numerical["expert_reference_sha256"]["final_output"] ==
            EXPECTED["final_reference"], "final reference")
    require(numerical["expert_bound_sha256"]["final_output"] ==
            EXPECTED["final_bound"], "final bound")
    require(all(stage["passed"] for stage in numerical["expert_stage_metrics"].values()),
            "stage numerical result")
    require(all(stage["signed_zero_mismatch_count"] == 0
                for stage in numerical["expert_stage_metrics"].values()), "signed zero")

    repeat = numerical["expert_repeat_integrity"]
    require(repeat["repeat_count_required"] == repeat["repeat_count_observed"] == 10,
            "repeat count")
    require(repeat["native_dispatch_count_expected"] == 30, "repeat dispatch count")
    require(repeat["conceptual_expert_count"] == 1, "conceptual expert count")
    outputs = repeat["outputs"]
    require(len(outputs) == 10 and [entry["ordinal"] for entry in outputs] == list(range(10)),
            "repeat ordinals")
    for field in ("gate_sha256", "up_sha256", "activated_hidden_sha256", "final_output_sha256"):
        require(len({entry[field] for entry in outputs}) == 1, f"repeat equality {field}")
    for field in ("gate_all_equal", "up_all_equal", "activated_hidden_all_equal",
                  "final_output_all_equal"):
        require(repeat[field] is True, field)

    ordering = numerical["oracle_ordering"]
    require(ordering["oracle_package_sha256"] == EXPECTED["oracle"], "oracle package")
    require(ordering["oracle_validated_before_candidate"] is True, "oracle validation")
    require(ordering["structural_order_valid"] is True, "oracle structural order")
    require(int(ordering["oracle_completed_at"]) < int(ordering["candidate_started_at"]),
            "oracle timestamp order")

    lifecycle = document["lifecycle"]
    require(lifecycle["reconciled"] is True, "lifecycle")
    post = lifecycle["post"]
    require(post["managed_created"] == post["managed_destroyed"], "managed lifecycle")
    require(post["derived_created"] == post["derived_destroyed"], "derived lifecycle")
    require(post["default_cpu_stream_created"] == post["default_cpu_stream_freed"],
            "default stream lifecycle")
    require(post["owned_stream_created"] == post["owned_stream_freed"],
            "owned stream lifecycle")
    require(post["active_contexts"] == 0 and post["singleton_claimed"] is False,
            "terminal context state")

    for forbidden in ("/Users/", "/private/", "/tmp/", "file://"):
        require(forbidden not in raw, f"private path token: {forbidden}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    validate(args.evidence)
    print("F017 M1-E attempt-3 accepted evidence: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

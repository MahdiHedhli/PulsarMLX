#!/usr/bin/env python3
"""Fail-closed validator for the banked F017 M1-E attempt-2 rejection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {
    "runtime": "5c7694d6ba48640279e4725ea96104bc179a62cb",
    "authorization": "f8a9910ca1c9242c2638556b0daee6a11949a090",
    "final_head": "48e30ae4df9c0187bebcd9f6be377331099c86f9",
    "config": "a8905b8709aadf8d36bf94c2cb54c14a9ce5bcd31e7a1b184da33127af300f4e",
    "executable": "13900ecc2ea5b252c4a83b69ae04ee6b20916a7f3c0133c1b87c9a5c720b2bab",
    "attempt_1": "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119",
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
    require(document["schema"] == "pulsarmlx.f017.m1e-attempt-2-closeout", "schema")
    require(document["schema_version"] == "1.0.0", "schema version")
    require(document["verdict"] == "M1-E ATTEMPT 2 REJECTED", "verdict")
    identity = document["identity"]
    require(identity["compiled_runtime_sha"] == EXPECTED["runtime"], "runtime")
    require(identity["tooling_sha"] == EXPECTED["runtime"], "tooling")
    require(identity["authorization_head_sha"] == EXPECTED["authorization"], "authorization")
    require(identity["reviewed_final_head_sha"] == EXPECTED["final_head"], "final head")
    require(identity["execution_config_sha256"] == EXPECTED["config"], "config")
    require(identity["release_executable_sha256"] == EXPECTED["executable"], "executable")
    require(identity["execution_config_schema_version"] == "3.0.0", "config schema")
    require(document["prior_evidence"]["m1_e_attempt_1"] == EXPECTED["attempt_1"], "attempt 1")
    require(document["admission"]["preflight_result"] == "READY_TO_EXECUTE_M1_E", "preflight")
    checkpoint = document["checkpoint_bindings"]
    require(checkpoint["checkpoint_accessed"] is False, "checkpoint access")
    for field in ("real_tensor_payload_count", "shard_open_count", "positional_read_count", "compressed_bytes_read"):
        require(checkpoint[field] == 0, field)
    execution = document["execution"]
    require(execution["attempt"] == 2, "attempt")
    require(execution["attempt_state"] == "EXECUTION_STARTED", "attempt state")
    require(execution["attempt_consumed"] is True, "attempt consumption")
    for field in (
        "conceptual_expert_count", "production_repeat_count", "native_matvec_dispatch_count",
        "qualification_scaffold_dispatch_count", "explicit_reference_dispatch_count",
        "fallback_count", "backend_error_count", "router_execution_count",
        "shared_or_second_expert_count", "layer_execution_count", "logits_execution_count",
    ):
        require(execution[field] == 0, field)
    require(execution["oracle_created"] is False, "oracle")
    require(execution["candidate_decoded_sha256"] == {}, "decoded identities")
    require(execution["repeat_stage_hashes"] == [], "repeats")
    require(execution["numerical_metrics"] is None, "numerical metrics")
    result = document["result"]
    require(result["classification"] == "FAIL_INFRASTRUCTURE_EVIDENCE", "classification")
    require(result["first_failure"]["code"] == "m1e_oracle_execution_config_identity", "failure code")
    require("schema 3.0.0" in result["first_failure"]["root_cause"], "root cause")
    require(result["candidate_started"] is False, "candidate start")
    require(result["retry_performed"] is False, "retry")
    require(result["m1_f_prepared"] is False and result["m1_f_authorized"] is False, "M1-F")
    require(document["privacy"]["absolute_private_paths_present"] is False, "privacy flag")
    for forbidden in ("/Users/", "/private/", "/tmp/", "file://"):
        require(forbidden not in raw, f"private path token: {forbidden}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    validate(args.evidence)
    print("F017 M1-E attempt-2 rejection evidence: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

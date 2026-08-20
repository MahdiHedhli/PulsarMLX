#!/usr/bin/env python3
"""Fail-closed validator for the S1 materialization authorization and release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_S1 = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
EXPECTED_EVENT_EVIDENCE = "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190"
EXPECTED_REPRODUCTION = "7e31865232357b29cfc92c423421d6442e4203a5b39520458346a2b1a827dcbf"
EXPECTED_PRODUCER = "b17f1034688f2cf01243d04380151c1ad5c9f321d19a7bc29907a00a10993cc3"


class ValidationError(RuntimeError): pass
def require(value: bool, message: str) -> None:
    if not value: raise ValidationError(message)
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(authorization: dict[str, Any], release: dict[str, Any]) -> None:
    require(authorization.get("schema") == "pulsarmlx.f017.representative-s1-materialization-authorization", "AUTH_SCHEMA")
    require(authorization.get("status") == "PREPARED_REVIEW_REQUIRED" and authorization.get("real_event_authorized") is False, "AUTH_STATUS")
    target = authorization.get("s1_target", {})
    require(target == {"semantic_role":"LAYER3_POST_ATTENTION_RESIDUAL","stage_name":"post_attention_residual","formula":"f32(S0 + layer3_attention_output)","sha256":EXPECTED_S1,"dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"classification_before_event":"HASH_RETAINED_REPRODUCIBLE_NOT_BYTE_RETAINED"}, "S1_TARGET")
    sources = authorization.get("source_authority", {})
    require(sources.get("real_execution_evidence", {}).get("sha256") == EXPECTED_EVENT_EVIDENCE, "EVENT_EVIDENCE")
    require(sources.get("reproduction_contract", {}).get("sha256") == EXPECTED_REPRODUCTION, "REPRODUCTION_CONTRACT")
    require(sources.get("reproduction_producer", {}).get("sha256") == EXPECTED_PRODUCER, "REPRODUCTION_PRODUCER")
    require(sources.get("canonical_s0", {}).get("sha256") == "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11", "S0")
    require(sources.get("attention_payloads") == {"count":9,"packed_bytes":132900864,"inventory_bound_by_candidate":True,"checkpoint_fallback":False}, "PAYLOADS")
    accounting = authorization.get("accounting")
    require(accounting == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"future_s1_materializations":1,"expert_executions":0,"ffn_compositions":0,"s2_constructions":0}, "AUTH_ACCOUNTING")
    require(authorization.get("stop_boundary") == "AFTER_REPRESENTATIVE_S1_RETENTION_ONLY", "AUTH_BOUNDARY")
    prohibitions = authorization.get("prohibitions", {})
    require(all(prohibitions.get(key) is True for key in ("checkpoint_access","shard_open","new_real_attention_execution","router_execution","expert_execution","ffn_consumption","ffn_composition","s2_construction","retry","resume","second_attempt")), "PROHIBITIONS")

    require(release.get("schema") == "pulsarmlx.f017.representative-s1-materialization-single-use-release", "RELEASE_SCHEMA")
    require(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL" and release.get("real_event_authorized") is False, "RELEASE_STATUS")
    require(release.get("authorization_sha256") == authorization.get("self_sha256"), "AUTH_BINDING")
    require(release.get("accounting") == {"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"s1_materializations":1,"ffn_compositions":0,"s2_constructions":0,"ledger_before":175,"ledger_after":175}, "RELEASE_ACCOUNTING")
    require(release.get("single_use") == {"exclusive_attempt_creation":True,"durable_attempt_start_before_reconstruction":True,"durable_materialization_start_before_reconstruction":True,"attempts":1,"no_retry":True,"no_resume":True,"no_second_attempt":True,"failure_after_attempt_start_consumes_release":True}, "SINGLE_USE")
    require(release.get("output_contract", {}).get("expected_equals_produced_equals_readback") is True, "OUTPUT_IDENTITY")
    require(release.get("output_contract", {}).get("sha256") == EXPECTED_S1, "OUTPUT_SHA")
    require(release.get("output_contract", {}).get("publication") == "DESCRIPTOR_RELATIVE_EXCLUSIVE_TEMP_FSYNC_NO_REPLACE_LINK_PARENT_FSYNC_DESCRIPTOR_READBACK", "PUBLICATION")
    require(release.get("stop_boundary") == "AFTER_REPRESENTATIVE_S1_RETENTION_ONLY", "RELEASE_BOUNDARY")
    require(release.get("s2_interface_exposed") is False and release.get("ffn_input_exposed") is False, "DOWNSTREAM_INTERFACE")
    require(set(release.get("runtime_interface", {})) == {"candidate","canonical_s0","canonical_s0_manifest","attention_retention_root","state_root","output_root","output"}, "RUNTIME_INTERFACE")
    for binding in release.get("bindings", {}).values():
        path = ROOT / binding["path"]
        require(path.is_file() and sha(path) == binding["sha256"], "BINDING_SHA")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--authorization", type=Path, required=True); parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args(); authorization = json.loads(args.authorization.read_text()); release = json.loads(args.release.read_text())
    try: validate(authorization, release)
    except ValidationError as error:
        print(json.dumps({"result":"FAIL","error":str(error)}, sort_keys=True)); return 1
    print(json.dumps({"result":"PASS","ledger":175,"checkpoint_reads":0,"shard_opens":0,"s1_materializations":0,"s2_constructions":0}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())

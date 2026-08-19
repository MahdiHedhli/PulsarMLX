#!/usr/bin/env python3
"""Executable schema plus semantic validator for repaired representative M1-F0 v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v2.json"
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v2.schema.json"
V1 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v1.json"
EXPECTED_V1 = "e46874b05d2f5946f5b6c0dc9ac4beeb50628a2ebc28f16d0b8a2fc1284627dc"
EXPECTED_EXECUTOR = "e34eb6a6d552440c3e72e203268ff003d68ec9229ac5227cb7ac30001d21a3ab"
EXPECTED_RETAINED = "207a096eec6b02f8a3d95911d890f3e4da5fc53ae9cd9a4372d099e3c0b73824"
EXPECTED_VOCABULARY = "ac1e86652dd475ef7c8049faa5eccc838b677497dbda77da570c8ee33cab130f"
EXPECTED_SCHEMA = "15f6273383fc50fcb9d3c1aab0247552b96b1ce8d303b67357b0e743f6453738"
EXPECTED_REHEARSAL = "9dd6e2129a3df1b5a44240ff96e48f5180046b06879bc881a74ec34ef3c11faa"
EVENT_ID = "F017-CANONICAL-REPRESENTATIVE-M1F0-ATTENTION-ROUTER-RECOVERY-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("DUPLICATE_JSON_KEY:" + key)
        value[key] = item
    return value


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_errors(value: Any, schema: dict[str, Any], location: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    actual_type = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}.get(expected_type)
    if actual_type is not None and (not isinstance(value, actual_type) or expected_type == "integer" and isinstance(value, bool)):
        return ["SCHEMA_TYPE:" + location]
    if "const" in schema and value != schema["const"]:
        errors.append("SCHEMA_CONST:" + location)
    if isinstance(value, dict):
        for required in schema.get("required", []):
            if required not in value:
                errors.append("SCHEMA_REQUIRED:" + location + "." + required)
        for key, child in schema.get("properties", {}).items():
            if key in value:
                errors.extend(schema_errors(value[key], child, location + "." + key))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append("SCHEMA_MIN_ITEMS:" + location)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("SCHEMA_MAX_ITEMS:" + location)
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], f"{location}[{index}]"))
    return errors


def validate(document: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    schema_path = root / SCHEMA.relative_to(ROOT)
    require(schema_path.is_file() and sha_file(schema_path) == EXPECTED_SCHEMA, "SCHEMA_IDENTITY")
    if schema_path.is_file():
        errors.extend(schema_errors(document, load(schema_path)))

    require(document.get("event") == {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID}, "EVENT")
    supersedes = document.get("supersedes", {})
    require(supersedes == {"path": V1.relative_to(ROOT).as_posix(), "sha256": EXPECTED_V1}, "SUPERSEDES")
    v1_path = root / supersedes.get("path", "missing")
    require(v1_path.is_file() and sha_file(v1_path) == EXPECTED_V1, "V1_IDENTITY")

    bindings = [
        (document.get("executor", {}), EXPECTED_EXECUTOR, "EXECUTOR"),
        (document.get("retained_inputs", {}), EXPECTED_RETAINED, "RETAINED"),
        (document.get("stage_vocabulary", {}), EXPECTED_VOCABULARY, "VOCABULARY"),
        (document.get("schema_binding", {}), EXPECTED_SCHEMA, "SCHEMA_BINDING"),
    ]
    for binding, digest, code in bindings:
        path = root / str(binding.get("path", "missing"))
        require(binding.get("sha256") == digest and path.is_file() and sha_file(path) == digest, code + "_IDENTITY")
    rehearsal = document.get("synthetic_rehearsal", {})
    rehearsal_path = root / str(rehearsal.get("path", "missing"))
    require(rehearsal.get("sha256") == EXPECTED_REHEARSAL and rehearsal_path.is_file() and sha_file(rehearsal_path) == EXPECTED_REHEARSAL, "REHEARSAL_IDENTITY")
    require({key: rehearsal.get(key) for key in ("real_geometry","checkpoint_reads","shard_opens","real_ledger_delta")} == {"real_geometry":True,"checkpoint_reads":0,"shard_opens":0,"real_ledger_delta":0}, "REHEARSAL_SCOPE")

    expected_inventory = load(v1_path)["attention_payload_inventory"] if v1_path.is_file() else []
    inventory = document.get("attention_payload_inventory", [])
    require(inventory == expected_inventory, "INVENTORY_EXACT")
    require([row.get("ordinal") for row in inventory] == list(range(9)), "INVENTORY_ORDER")
    require(len({row.get("key") for row in inventory}) == 9, "INVENTORY_KEYS")
    require(sum(int(row.get("packed_bytes", -1)) for row in inventory) == 132900864, "INVENTORY_BYTES")
    require(all(row.get("shard") == 2 for row in inventory), "INVENTORY_SHARD")
    require(all(len(str(row.get("packed_sha256", ""))) == 64 and len(str(row.get("decoded_sha256", ""))) == 64 for row in inventory), "INVENTORY_HASHES")
    require(all(row["packed_sha256"] == row["decoded_sha256"] for row in inventory if row.get("quantization") == "F32"), "F32_PACKED_DECODED")

    expected_checkpoint = {
        "catalog":{"path":"docs/research/glm52/raw/f016-c01-catalog-0001.json","sha256":"135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19"},
        "checkpoint_set_sha256":"d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
        "tensor_map_sha256":"ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
        "shard":{"ordinal":2,"basename":"GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf","sha256":"d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"},
        "planning_contract_catalog_disposition":"RETIRED_AS_NONAUTHORITATIVE_FOR_V2; COMMITTED_CATALOG_ABOVE_IS_SOLE_METADATA_AUTHORITY"}
    require(document.get("checkpoint_binding") == expected_checkpoint, "CHECKPOINT_BINDING")
    catalog_path = root / expected_checkpoint["catalog"]["path"]
    require(catalog_path.is_file() and sha_file(catalog_path) == expected_checkpoint["catalog"]["sha256"], "CATALOG_IDENTITY")
    require(document.get("read_contract") == {
        "ordering":"STRICT_ASCENDING_ORDINAL_0_THROUGH_8","read_primitive":"ONE_EXACT_SIZE_POSITIONAL_READ_PER_ENTRY",
        "expected_reads":9,"expected_packed_bytes":132900864,"maximum_shard_opens":1,"retain_before_receipt":True,
        "durable_receipt_before_next_read":True,"dynamic_discovery":False,"additional_reads":False,"fallback":False,"retries":False}, "READ_CONTRACT")
    require(document.get("ledger_contract") == {
        "before":166,"after_success":175,"after_n_durable_receipts":"166+N","increment_unit":"DURABLE_EXACT_SIZE_READ_RECEIPT",
        "shard_open_increment":0,"short_read_increment":0,"partial_failure":"TERMINAL_NO_RESUME_NO_RETRY"}, "LEDGER_CONTRACT")
    require(document.get("failure_contract") == {
        "attempt_count":1,"automatic_retry":False,"automatic_resume":False,"second_attempt_authorized":False,
        "continue_after_failure":False,"decoder_disagreement":"TERMINAL_NO_SELECTION_NO_FURTHER_READ",
        "interrupted_attempt":"RECONCILE_DURABLE_RECEIPTS_TERMINALIZE_NEVER_RESUME"}, "FAILURE_CONTRACT")

    execution = document.get("execution_semantics", {})
    require(execution.get("device") == "CPU_ONLY" and execution.get("gpu_dispatches") == 0 and execution.get("blas") is False and execution.get("backend_dependent_reduction") is False, "EXECUTION_DEVICE")
    require(execution.get("arithmetic") == "STRICT_IEEE754_BINARY32_FIXED_INCREASING_INDEX_PER_OPERATION_ROUNDING", "EXECUTION_ARITHMETIC")
    require(execution.get("rmsnorm") == {"epsilon_source":"f32(1e-5)","epsilon_exact_decimal":"9.999999747378752e-6","epsilon_bits_hex":"0x3727c5ac","epsilon_dtype":"IEEE-754 binary32","accumulator_dtype":"IEEE-754 binary32","reduction_order":"INCREASING_ELEMENT_INDEX"}, "RMSNORM")
    require(execution.get("attention") == {"position":0,"visible_positions":[0],"rope":"POSITION_ZERO_IDENTITY","softmax":"ONE_VISIBLE_VALUE_EXACT_WEIGHT_ONE","residual":"S1_ELEMENTWISE_F32_ADD_S0_PLUS_ATTENTION_OUTPUT_ONCE"}, "ATTENTION")
    require(execution.get("router") == {"probabilities":"BINARY64_SIGMOID_VIA_PINNED_ENVIRONMENT_LIBM_EXP","scores":"P_I + F64(F32_CORRECTION_BIAS_I)","ranking":"SCORE_DESCENDING_EXPERT_ID_ASCENDING_TIE_BREAK","selection":"TOP_8_MEMBERSHIP","weights":"(P_I / MAX(FSUM_SELECTED_P, 2^-14)) * 2.5"}, "ROUTER")
    require(execution.get("environment_scope") == {"platform":"DARWIN_ARM64","cpython":"3.13.13","numpy":"2.4.5","libm":"SAME_PINNED_PRODUCTION_ENVIRONMENT_FOR_ALL_REPRODUCTIONS"}, "ENVIRONMENT")

    output = document.get("output_contract", {})
    require(output == {"stage_vocabulary":"EXACT_BOUND_CANONICAL_SET","finite_checks_required":True,"retained_only_reproduction_runs":10,"minimum_fresh_processes":2,"required_stage_identity":"10_OF_10_EXACT","route_identity":"10_OF_10_EXACT","checkpoint_rereads":0,"retained_before_after_rehash":True}, "OUTPUT_CONTRACT")
    vocabulary_path = root / document.get("stage_vocabulary", {}).get("path", "missing")
    if vocabulary_path.is_file():
        vocabulary = load(vocabulary_path)
        require(vocabulary.get("canonical_stage_sha256_names") == load(v1_path).get("output_contract", {}).get("required_stage_sha256") if v1_path.is_file() else False, "VOCABULARY_SET")

    retained_path = root / document.get("retained_inputs", {}).get("path", "missing")
    if retained_path.is_file():
        retained = load(retained_path)
        artifacts = {row.get("artifact_id"): row for row in retained.get("artifacts", [])}
        require(set(artifacts) == {"canonical_s0","ffn_norm","router_matrix","correction_bias"}, "RETAINED_ARTIFACTS")
        require(artifacts.get("correction_bias", {}).get("sha256") == "eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491", "CORRECTION_BIAS")
        require(retained.get("package_root_resolution", {}).get("checkpoint_fallback") is False, "RETAINED_FALLBACK")

    require(document.get("surface_separation") == {"direct_dprefix_inputs":False,"representative_route_source":"NEW_POST_ATTENTION_RESIDUAL_ONLY","prohibited_identities":["PRE_ATTENTION_ENTRY_TO_FFN_DIRECT_ANALYTICAL_ROUTE","DIRECT_DPREFIX_SELECTED_EXPERT_OUTPUTS","DIRECT_DPREFIX_SHARED_OUTPUT","DIRECT_DPREFIX_ROUTED_AGGREGATE","e9427e22ef86f161786cfcf22a74b92c1cca50e3d601c6c119633d1458904594"]}, "SURFACE_SEPARATION")
    require(document.get("stop_boundary") == "AFTER_REPRESENTATIVE_ROUTE_BEFORE_ANY_EXPERT_EXECUTION", "STOP_BOUNDARY")
    require(document.get("authorization") == {"real_event_authorized":False,"checkpoint_access_authorized":False,"independent_adversarial_review_required":True,"execution_release_required_after_review":True,"expert_execution_authorized":False,"shared_expert_execution_authorized":False,"candidate_or_model_dispatch_authorized":False,"M1_F_authorized":False,"M1_G_authorized":False,"P1_authorized":False}, "AUTHORIZATION_SCOPE")
    require(document.get("isolation") == {"checkpoint_reads":0,"shard_opens":0,"real_ledger_delta":0,"representative_computations":0}, "ISOLATION")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    args = parser.parse_args()
    errors = validate(load(args.contract), args.repository_root.resolve())
    print(json.dumps({"result":"PASS" if not errors else "FAIL","errors":errors,"checkpoint_reads":0,"shard_opens":0,"real_ledger_delta":0}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

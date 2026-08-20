#!/usr/bin/env python3
"""Fail-closed validator for representative S2 authorization and release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-construction-authorization-v1.json"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v1.json"
S1_REUSE_SHA = "5c6437f2ab6ae2d01acc765430880195211e892dfb612fbb3b4125d9038ffe13"
FFN_REUSE_SHA = "983b119970f8d60bddb887d4478455b4d9eb638c3dc90853319cc302f290cd06"
S1_SHA = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
FFN_SHA = "4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a"
ARITHMETIC_SHA = "abbf158320d1fdfade5b8553e9ea1871c34830f541e4186074262fc702776e86"


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "object required")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha(head: str, relative_path: str) -> str:
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "execution head format")
    result = subprocess.run(["git", "-C", str(ROOT), "show", f"{head}:{relative_path}"], capture_output=True, check=False)
    require(result.returncode == 0, f"execution head missing {relative_path}")
    return hashlib.sha256(result.stdout).hexdigest()


def validate_authorization(doc: dict[str, Any], repo: bool = True) -> None:
    require(doc.get("schema") == "pulsarmlx.f017.representative-s2-construction-authorization", "auth schema")
    require(doc.get("schema_version") == "1.0.0" and doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "auth state")
    bindings = doc.get("bindings", {})
    expected = {
        "s1_reuse_authorization": S1_REUSE_SHA,
        "s1_execution_evidence": "ea924afbc8972c194adc9d8a9759e1fca35ae8c2ab362225477cb4c54229fb55",
        "s1_reuse_review": "b4eb3a45a1b50c8030cecb515cd28e411baee6134dd9f058fe2fc97fb282dbef",
        "ffn_reuse_authorization": FFN_REUSE_SHA,
        "ffn_execution_evidence": "946d41a37cb4ae97938eae195c6b665441088c197312474613f8ca4cb282b2df",
        "ffn_reuse_review": "a8ef051865cc5e7e18ef73e40434c6ebecae1b6e118d3230af402d6d2df0a182",
        "semantic_graph": "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558",
        "arithmetic_contract": ARITHMETIC_SHA,
    }
    require(set(bindings) == set(expected), "auth binding census")
    for name, identity in expected.items():
        require(bindings[name]["sha256"] == identity, f"auth binding {name}")
        if repo:
            require(sha(ROOT / bindings[name]["path"]) == identity, f"auth bytes {name}")
    s1, ffn = doc["inputs"]["s1"], doc["inputs"]["ffn"]
    require(s1 == {"semantic_role":"REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL","stage_role":"LAYER3_POST_ATTENTION_RESIDUAL","relative_path":"representative-s1.f32le","private_manifest_relative_path":"representative-s1-private-manifest-v1.json","private_manifest_sha256":"9ddf842ceec92eee3ae51e9386e4774315965654d711b5751d98ad96868d876e","sha256":S1_SHA,"dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"finite":True}, "s1 input")
    require(ffn == {"semantic_role":"REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT","semantic_surface":"CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32","relative_path":"representative-ffn-output.f64le","private_manifest_relative_path":"representative-ffn-output-private-manifest-v1.json","private_manifest_sha256":"0f6a887fed8e0e4a96494f50bf94879ffec74ef6bc1d0fa64f9b0a3771efc04c","sha256":FFN_SHA,"dtype":"little-endian-f64","shape":[6144],"byte_length":49152,"finite":True}, "ffn input")
    require(doc["consume_what_was_validated"] == {"identity_equation":"EXPECTED_SHA256 == BEFORE_SHA256 == CONSUMED_SHA256 == AFTER_SHA256","same_descriptor_consumed":True,"fstat_before_after":True,"regular_file":True,"non_symlink":True,"hard_link_count":1,"read_only":True,"no_writable_alias":True,"exact_manifest":True,"exact_geometry":True,"finite":True}, "consume policy")
    require(doc["arithmetic"] == {"contract_sha256":ARITHMETIC_SHA,"formula":"S2_f32[k]=binary32(binary64(S1_f32[k])+FFN_f64[k])","surface":"CANONICAL_F017_PROOF_REFERENCE_DERIVED_S2_SURFACE_INTENTIONALLY_NOT_CLAIMED_EQUIVALENT_TO_PRODUCTION_SERIAL_F32"}, "auth arithmetic")
    require(doc["future_output"] == {"semantic_role":"REPRESENTATIVE_M1F0_S2_PROOF_REFERENCE_DERIVED","dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"serialization":"contiguous-c-order-ieee754-binary32-little-endian","finite":True,"concrete_sha256":"NOT_COMPUTED_UNTIL_SEPARATELY_APPROVED_REAL_EVENT"}, "future output")
    require(doc["accounting"] == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"s1_materializations":0,"expert_executions":0,"shared_expert_executions":0,"ffn_compositions":0,"preparation_s2_constructions":0,"future_s2_constructions":1}, "auth accounting")
    require(all(value is False for value in doc["fallbacks"].values()), "fallbacks")
    require(doc["stop_boundary"] == "AFTER_REPRESENTATIVE_S2_OUTPUT_ONLY", "auth boundary")


def validate_release(doc: dict[str, Any], repo: bool = True) -> None:
    require(doc.get("schema") == "pulsarmlx.f017.representative-s2-single-use-release" and doc.get("schema_version") == "1.0.0", "release schema")
    require(doc.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL" and doc.get("real_event_authorized") is False and doc.get("approval_asserted") is False, "release state")
    require((doc.get("event_id"),doc.get("release_id"),doc.get("attempt_id")) == ("F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1","F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-RELEASE-1","F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-ATTEMPT-1"), "release identity")
    head = doc.get("authoritative_execution_code_head")
    require(isinstance(head,str) and re.fullmatch(r"[0-9a-f]{40}",head) is not None, "execution head")
    require(doc.get("head_semantics") == "EXACT_LOAD_BEARING_BYTES_AT_CODE_HEAD;APPEND_ONLY_RELEASE_REVIEW_APPROVAL_AND_BANKING_COMMITS_PERMITTED", "head semantics")
    required = {"authorization","arithmetic_contract","s1_reuse_authorization","ffn_reuse_authorization","approval_contract","executor","release_wrapper","terminalizer","validator","tests","synthetic_rehearsal"}
    require(set(doc["bindings"]) == required, "release binding census")
    for name,binding in doc["bindings"].items():
        require(set(binding)=={"path","sha256"} and re.fullmatch(r"[0-9a-f]{64}",binding["sha256"]), f"binding shape {name}")
        if repo:
            require(sha(ROOT/binding["path"])==binding["sha256"],f"binding bytes {name}")
    require(doc["bindings"]["authorization"]["sha256"] == sha(AUTH), "authorization binding")
    require(doc["bindings"]["arithmetic_contract"]["sha256"] == ARITHMETIC_SHA, "arithmetic binding")
    require(doc["bindings"]["s1_reuse_authorization"]["sha256"] == S1_REUSE_SHA and doc["bindings"]["ffn_reuse_authorization"]["sha256"] == FFN_REUSE_SHA, "reuse bindings")
    if repo:
        for name in required - {"synthetic_rehearsal"}:
            binding=doc["bindings"][name]
            require(git_sha(head,binding["path"])==binding["sha256"],f"code head {name}")
        rehearsal=load(ROOT/doc["bindings"]["synthetic_rehearsal"]["path"])
        require(rehearsal.get("result")=="PASS" and rehearsal.get("real_s1_operand_consumptions")==0 and rehearsal.get("real_ffn_operand_consumptions")==0 and rehearsal.get("real_s2_constructions")==0,"rehearsal")
    require(doc["operands"] == {
        "s1":{"reuse_authorization_sha256":S1_REUSE_SHA,"sha256":S1_SHA,"semantic_role":"REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL","dtype":"little-endian-f32","shape":[6144],"byte_length":24576},
        "ffn":{"reuse_authorization_sha256":FFN_REUSE_SHA,"sha256":FFN_SHA,"semantic_role":"REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT","dtype":"little-endian-f64","shape":[6144],"byte_length":49152},
    }, "release operands")
    require(doc["numerical_surface"] == {"classification":"CANONICAL_F017_PROOF_REFERENCE_DERIVED_S2_SURFACE_INTENTIONALLY_NOT_CLAIMED_EQUIVALENT_TO_PRODUCTION_SERIAL_F32","formula":"S2_f32[k]=binary32(binary64(S1_f32[k])+FFN_f64[k])","s1_promotion":"exact IEEE-754 binary32-to-binary64 widening","addition":"one binary64 addition per coordinate, left promoted S1 then right FFN","addition_rounding":"round-to-nearest ties-to-even","final_cast":"one IEEE-754 binary64-to-binary32 conversion per coordinate","final_rounding":"round-to-nearest ties-to-even","coordinate_order":"increasing 0..6143","reduction":False,"fma":False,"blas":False,"gpu":False,"parallel_arithmetic":False,"production_equivalence":"NOT_PROVEN_AND_NOT_CLAIMED"}, "release numerical surface")
    require(doc["single_use"] == {"attempts":1,"s2_constructions":1,"exclusive_attempt_creation":True,"consumed_at":"DURABLE_ATTEMPT_START_BEFORE_S2_ARITHMETIC","s2_counted_at":"DURABLE_S2_START_BEFORE_ARITHMETIC_REGARDLESS_OF_OUTCOME","post_start_failure_consumes_release":True,"retry":False,"resume":False,"second_attempt":False,"concurrent_invocation":False,"terminalizer_required":True}, "single use")
    require(doc["input_preflight"] == {"identity_equation":"EXPECTED_SHA256 == BEFORE_SHA256 == CONSUMED_SHA256 == AFTER_SHA256","same_validated_descriptor_consumed":True,"regular_non_symlink_single_link_read_only":True,"exact_private_manifest":True,"exact_geometry_and_finiteness":True,"all_locally_detectable_failures_before_attempt_start":True}, "input preflight")
    require(doc["output_banking"] == {"semantic_role":"REPRESENTATIVE_M1F0_S2_PROOF_REFERENCE_DERIVED","dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"finite":True,"canonical_serialization":"contiguous-c-order-ieee754-binary32-little-endian","descriptor_relative_exclusive_temp":True,"file_fsync":True,"no_replace_hard_link_publication":True,"parent_fsync":True,"descriptor_readback":True,"output_sha256_recorded":True,"private_manifest":True,"execution_receipt":True,"matching_complete_terminal_required":True,"partial_output_authority":False,"overwrite":False}, "output banking")
    require(doc["machine_local_paths"] == {"resolution":"FIXED_PATHLIB_HOME_AND_REPOSITORY_EXPRESSIONS_NO_CALLER_SELECTION","s1_root":"$HOME/.local/share/pulsarmlx/f017/representative-s1-materialization-release-2/outputs","ffn_root":"$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs","state_root":"$HOME/.local/share/pulsarmlx/f017/representative-s2-release-1/attempt-state","output_root":"$HOME/.local/share/pulsarmlx/f017/representative-s2-release-1/outputs","output":"$HOME/.local/share/pulsarmlx/f017/representative-s2-release-1/outputs/representative-s2.f32le","private_manifest":"$HOME/.local/share/pulsarmlx/f017/representative-s2-release-1/outputs/representative-s2-private-manifest-v1.json","receipt":"$HOME/.local/share/pulsarmlx/f017/representative-s2-release-1/attempt-state/s2-execution-receipt.json","approval":"$REPOSITORY/docs/architecture/reviews/evidence/f017-representative-s2-single-use-release-v1-independent-approval-v1.json","go_token":"$HOME/.local/share/pulsarmlx/f017/representative-s2-release-1/go-token.json"}, "machine paths")
    require(doc["runtime"] == {"cpython":"3.14.6","platform":"Darwin-arm64","endianness":"little","thread_variables_equal_one":["OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","VECLIB_MAXIMUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"],"arithmetic_backend":"CPYTHON_STRUCT_AND_SCALAR_IEEE754_ONLY","numpy_required":False}, "runtime")
    require(doc["accounting"] == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"s1_materializations":0,"expert_executions":0,"shared_expert_executions":0,"ffn_compositions":0,"preparation_s2_constructions":0,"future_s2_constructions":1}, "release accounting")
    expected_prohibitions={"checkpoint_access","shard_open","new_attention_execution","s1_reconstruction","s1_materialization","s1_release_rerun","ffn_recomputation","ffn_release_rerun","routed_aggregate_recomputation","expert_execution","shared_expert_execution","production_serial_f32_substitution","alternate_or_historical_operand","caller_selected_input_paths","output_overwrite","retry","resume","second_attempt","approval_in_this_phase","go_token_in_this_phase","real_s2_construction_in_this_phase"}
    require(set(doc["prohibitions"])==expected_prohibitions and all(doc["prohibitions"].values()), "prohibitions")
    require(doc["future_approval"] == {"separate_committed_independent_approval_required":True,"approval_contract_sha256":"c391d84b4573f49d0be40a75665e3c7b18db6b73f37b6cdad342255c34f7800b","approval_statement":"REPRESENTATIVE S2 SINGLE-USE RELEASE V1 APPROVED","release_review_and_reviewed_head_enforced":True,"reviewer_identity_model_enforced":True,"approval_is_not_go_token":True,"token_binding":"TRANSITIVE_THROUGH_EXACT_APPROVAL_SHA256","authority_chain":"RELEASE_TO_COMMITTED_REVIEW_TARGET_HEAD_TO_INDEPENDENT_REVIEW_TO_SEPARATE_APPROVAL_TO_MACHINE_LOCAL_GO_TOKEN"}, "future approval")
    require(doc.get("storage_required_bytes")==67108864, "storage")
    if repo:
        contract=load(ROOT/doc["bindings"]["approval_contract"]["path"])
        require(len(contract["approval_exact_fields"])==28 and len(set(contract["approval_exact_fields"]))==28,"approval field census")
        require(contract["authority_chain"]==doc["future_approval"]["authority_chain"],"approval chain")
        require(contract["go_token_exact_fields"]==["approval_sha256","attempt_id","authorization_sha256","disposition","event_id","real_event_authorized","release_id","release_sha256"],"token schema")
    require(doc["stop_boundary"] == "AFTER_REPRESENTATIVE_S2_OUTPUT_ONLY", "release boundary")


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--authorization",type=Path,default=AUTH); parser.add_argument("--release",type=Path,default=RELEASE); parser.add_argument("--no-repo",action="store_true"); args=parser.parse_args()
    validate_authorization(load(args.authorization),repo=not args.no_repo)
    validate_release(load(args.release),repo=not args.no_repo)
    print("REPRESENTATIVE_S2_RELEASE_VALID")
    return 0


if __name__=="__main__":
    try: raise SystemExit(main())
    except (ValidationError,FileNotFoundError,KeyError,TypeError) as error:
        print(f"INVALID:{error}"); raise SystemExit(2)

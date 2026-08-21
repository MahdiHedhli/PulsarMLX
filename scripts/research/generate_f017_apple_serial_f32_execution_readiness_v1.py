#!/usr/bin/env python3
"""Generate deterministic public readiness contracts from reviewed local bytes."""

from __future__ import annotations
import hashlib, json, platform, subprocess
from pathlib import Path
from f017_apple_serial_f32_execution_readiness_v1 import (
    REPO, PACKAGE_CENSUS, PACKAGE_JSON, PACKAGE_ROOT, ATTEMPT_ROOT, CAPTURE_ROOT,
    derive_descriptors, package_root_sha, execution_code_head,
)

CONTRACTS = REPO / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = REPO / "docs/architecture/reviews/evidence"
RUNNER_SHA = "fe82ab79f6c1a4798fb1204dd5deee24aa6bfaaa9b2cd7f841cca20afde553e5"
PINNED_RUNNER = Path("/Users/mhedhli/.local/share/pulsarmlx/f017/apple-production-serial-f32-equivalence-readiness-1/bin/f017-apple-serial-f32-capture")


def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(name, value, evidence=False):
    path = (EVIDENCE if evidence else CONTRACTS) / name
    path.write_bytes(canonical(value)); return path
def binding(path): return {"path":str(Path(path).relative_to(REPO)),"sha256":sha(path)}


def main():
    CODE_HEAD = execution_code_head()
    descriptors = derive_descriptors()
    root = package_root_sha(descriptors)
    public_rows = []
    for row in descriptors:
        public_rows.append({key:row[key] for key in row if key != "source_path"} | {"source_authority_machine_path":row["source_path"]})
    root_spec = write("f017-apple-production-serial-f32-package-root-specification-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-package-root-specification","schema_version":"1.0.0",
        "canonicalization":"UTF8_JSON_SORT_KEYS_COMPACT_SEPARATORS_TRAILING_LF_SHA256",
        "root_input_fields":["ordinal","canonical_tensor_id","role","destination_relative_path","sha256","byte_count","encoding","shape","quantization","decoder_binding","source_authority_path","source_authority_sha256","source_result_event"],
        "ordering":"ORDINAL_ASCENDING_0_TO_39","tensor_count":40,"extra_files":"REJECT","missing_files":"REJECT",
        "root_rederived_from_actual_bytes_before_attempt_start":True,"json_root_claim_is_not_authority":True,
    })
    package_manifest = write("f017-apple-production-serial-f32-retained-40-tensor-package-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-retained-package","schema_version":"1.0.0",
        "package_id":"F017-APPLE-SERIAL-F32-RETAINED-40-V1","fixed_machine_local_root":str(PACKAGE_ROOT),
        "tensor_count":40,"total_bytes":sum(r["byte_count"] for r in descriptors),"package_root_sha256":root,
        "package_root_specification":binding(root_spec),"ordered_tensors":public_rows,
        "assembly":{"operation":"BYTE_FOR_BYTE_COPY","numerical_transformations":0,"source_destination_identity":"40/40 REQUIRED","checkpoint_reads":0,"shard_opens":0},
        "consumer_policy":{"rehash_actual_bytes":True,"no_path_only_trust":True,"no_manifest_only_trust":True,"regular":True,"non_symlink":True,"single_link":True,"read_only":True,"no_extra_files":True,"same_descriptor":True,"checkpoint_fallback":False},
    })
    root_result = write("f017-apple-production-serial-f32-package-root-result-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-package-root-result","schema_version":"1.0.0",
        "package_manifest":binding(package_manifest),"machine_census_sha256":sha(PACKAGE_CENSUS),"runner_package_sha256":sha(PACKAGE_JSON),
        "package_root_sha256":root,"tensor_count":40,"total_bytes":sum(r["byte_count"] for r in descriptors),
        "source_destination_byte_identity":"40/40 PASS","checkpoint_reads":0,"shard_opens":0,"numerical_execution":0,
    }, evidence=True)
    code_paths = [
        "crates/f017-runner/src/apple_serial_f32.rs","crates/f017-runner/src/bin/f017-apple-serial-f32-capture.rs","crates/f017-runner/src/json.rs","crates/f017-runner/build.rs","crates/f017-runner/Cargo.toml","crates/f017-runner/src/lib.rs",
        "crates/quant/src/lib.rs","crates/quant/src/cpu_dot.rs","crates/quant/src/cpu_dot_tables.rs","crates/quant/src/iq_ref.rs","crates/quant/src/q6_k_ref.rs","crates/quant/src/q8_0_ref.rs",
        "crates/stream/src/lib.rs","crates/stream/src/apple_mlx_bridge.rs","crates/stream/src/apple_mlx_bridge.mm","Cargo.lock",
        "scripts/research/f017_apple_serial_f32_execution_readiness_v1.py","scripts/research/f017_apple_serial_f32_equivalence_wrapper_v3.py","scripts/research/f017_apple_serial_f32_go_generator_v1.py","scripts/research/f017_apple_serial_f32_ten_process_harness_v1.py","scripts/research/f017_apple_serial_f32_capture_terminalizer_v2.py",
    ]
    code_manifest = write("f017-apple-production-serial-f32-code-manifest-v2.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-code-manifest","schema_version":"2.0.0","execution_code_head":CODE_HEAD,
        "artifacts":[{"path":p,"sha256":sha(REPO/p),"production_reachability":"LOAD_BEARING"} for p in code_paths],
        "decoder_coverage":{"IQ2_XXS":["crates/quant/src/iq_ref.rs","crates/quant/src/cpu_dot_tables.rs"],"IQ3_XXS":["crates/quant/src/iq_ref.rs","crates/quant/src/cpu_dot_tables.rs"],"Q5_K":["crates/quant/src/cpu_dot.rs"],"Q6_K":["crates/quant/src/q6_k_ref.rs"],"Q8_0":["crates/quant/src/q8_0_ref.rs"]},
        "whole_binary_hash_is_additional_not_substitute":True,"native_executable_sha256":RUNNER_SHA,"material_change_requires_new_manifest_release_review":True,
    })
    runtime_v1 = REPO/"specs/017-rust-native-inference-runtime/contracts/f017-apple-production-serial-f32-runtime-binding-v1.json"
    runtime = json.loads(runtime_v1.read_text())
    runtime_rebind = write("f017-apple-production-serial-f32-runtime-rebind-v2.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-runtime-rebind","schema_version":"2.0.0",
        "execution_code_head":CODE_HEAD,"code_manifest":binding(code_manifest),"native_executable":{"path":str(PINNED_RUNNER),"sha256":RUNNER_SHA,"build_command":"PULSAR_REQUIRE_NATIVE_MLX=1 cargo build --release -p f017-runner --bin f017-apple-serial-f32-capture; immutable byte-identical copy to fixed readiness path","target":"aarch64-apple-darwin","mode":"release","regular":True,"non_symlink":True,"single_link":True,"read_only":True},
        "runtime_binding_v1":binding(runtime_v1),"platform":runtime["platform"],"mlx":runtime["mlx"],"mlx_c":runtime["mlx_c"],"linkage":runtime["linkage"],"toolchain":runtime["toolchain"],"thread_limits":runtime["thread_limits"],
        "otool_required_paths":[runtime["mlx_c"]["library"]["path"],runtime["mlx"]["library"]["path"],runtime["linkage"]["metal_framework"]],
        "pre_attempt_rehash_required":True,"runtime_drift_disposition":"FAIL_BEFORE_ATTEMPT_START","portability":"NOT_CLAIMED",
    })
    stage_manifest = REPO/"specs/017-rust-native-inference-runtime/contracts/f017-apple-production-serial-f32-stage-manifest-v1.json"
    capture_manifest = REPO/"specs/017-rust-native-inference-runtime/contracts/f017-apple-production-serial-f32-capture-manifest-v1.json"
    stages = json.loads(stage_manifest.read_text())["stages"]
    result = json.loads((REPO/"docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json").read_text())
    stage_hashes = result["stage_sha256"]
    exact_files = {
        "input_hidden":("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-vocabulary/.pulsarmlx-local/dprefix-exact-1/retained/layer_3_entry.f32le","9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11","BYTE_EQUIVALENCE_REQUIRED","byte_equivalence"),
        "post_attention_residual":("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-s1-materialization-release-2/outputs/representative-s1.f32le","8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd","NUMERICAL_EQUIVALENCE_REQUIRED","r10_intermediate"),
        "router_normalized":("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-expert-input-v1/router_normalized.f32le","687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c","NUMERICAL_EQUIVALENCE_REQUIRED","r10_intermediate"),
        "routed_aggregate":("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/outputs/routed-aggregate.f64le","872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9","INTENTIONAL_DISTINCTION_EXPECTED","routed_aggregate_frozen"),
        "shared_expert_output":("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/outputs/representative-shared-expert-output.f32le","8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b","NUMERICAL_EQUIVALENCE_REQUIRED","r10_intermediate"),
        "production_ffn":("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs/representative-ffn-output.f64le","4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a","INTENTIONAL_DISTINCTION_EXPECTED","r10_intermediate"),
        "production_s2":("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-s2-release-2/outputs/representative-s2.f32le","0341314230654d21fa56506dfe601f90bdb603fc38fd1203b6dd62b1e54c98c1","INTENTIONAL_DISTINCTION_EXPECTED","complete_layer_final"),
    }
    metrics = json.loads((REPO/"specs/017-rust-native-inference-runtime/contracts/f017-production-serial-f32-equivalence-specification-v1.json").read_text())["metrics"]
    comparison_rows=[]
    for ordinal, stage in enumerate(stages):
        sid=stage["id"]
        row={"ordinal":ordinal,"production_stage_id":sid,"production_dtype":stage["output"],"production_source_symbol":stage["symbol"]}
        if sid in exact_files:
            path,expected,relationship,metric=exact_files[sid]
            row.update({"comparison_mode":"RETAINED_EXPECTED_ARTIFACT","expected_path":path,"expected_sha256":expected,"intended_relationship":relationship,"metric":metric})
        elif sid in ("selected_ids","ranking"):
            row.update({"comparison_mode":"COMMITTED_STRUCTURAL_AUTHORITY","expected_evidence":binding(REPO/"docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"),"expected_sha256":stage_hashes[sid],"intended_relationship":"BYTE_EQUIVALENCE_REQUIRED","metric":"EXACT_MEMBERSHIP_AND_ORDER"})
        elif sid=="routing_weights":
            row.update({"comparison_mode":"COMMITTED_STRUCTURAL_AND_NUMERIC_AUTHORITY","expected_evidence":binding(REPO/"docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"),"expected_sha256":stage_hashes[sid],"intended_relationship":"NUMERICAL_EQUIVALENCE_REQUIRED","metric":"routing_weight_frozen"})
        elif sid in stage_hashes:
            row.update({"comparison_mode":"HASH_DIAGNOSTIC_ONLY_NO_EQUIVALENCE_VERDICT","expected_evidence":binding(REPO/"docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"),"expected_sha256":stage_hashes[sid],"intended_relationship":"NUMERICAL_EQUIVALENCE_REQUIRED","metric":"NO_RETAINED_BYTES_NO_POST_HOC_TOLERANCE"})
        else:
            row.update({"comparison_mode":"DETERMINISM_CAPTURE_ONLY_NO_PROOF_ARTIFACT","expected_sha256":None,"intended_relationship":"INTENTIONAL_DISTINCTION_EXPECTED" if sid in ("routed_down_outputs",) else "NUMERICAL_EQUIVALENCE_REQUIRED","metric":"NO_RETAINED_EXPECTED_ARTIFACT"})
        row["observed_result"]=None; row["execution_status"]="NOT_EXECUTED"; comparison_rows.append(row)
    comparison = write("f017-apple-production-serial-f32-comparison-execution-contract-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-comparison-execution-contract","schema_version":"1.0.0","executed":False,
        "specification":binding(REPO/"specs/017-rust-native-inference-runtime/contracts/f017-production-serial-f32-equivalence-specification-v1.json"),
        "stage_manifest":binding(stage_manifest),"capture_manifest":binding(capture_manifest),"stage_count":34,"stage_rows":comparison_rows,
        "metrics":{"byte_equivalence":metrics["byte_equivalence"],"routing_weight_frozen":metrics["routing_weight_frozen"],"r10_intermediate":metrics["r10_intermediate"],"routed_aggregate_frozen":metrics["routed_aggregate_frozen"],"complete_layer_final":metrics["complete_layer_final"],"expert_operand_bound":metrics["expert_operand_bound"]},
        "tolerance_policy":{"post_hoc_changes":False,"enlargement_requires_new_contract_and_review":True,"pass":"EXACT_STRUCTURAL_GATES_THEN_ALL_APPLICABLE_FROZEN_METRICS","nan_inf":"FAIL","relative_error":"DISABLED"},
        "surface_rule":"PROOF_REFERENCE_OUTPUTS_ARE_EXPECTED_AUTHORITIES_NOT_PRODUCTION_OUTPUTS","production_serial_f32_equivalence_executed":False,
    })
    routing = write("f017-apple-production-serial-f32-routing-execution-gates-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-routing-execution-gates","schema_version":"1.0.0","executed":False,
        "ordered_gates":["SELECTED_EXPERT_MEMBERSHIP_EXACT","SELECTED_EXPERT_ORDER_EXACT","TIE_BEHAVIOR_EXACT","ROUTING_WEIGHT_FROZEN_COMPARISON","ROUTED_EXPERT_STAGE_COMPARISONS","ROUTED_AGGREGATE_COMPARISON"],
        "membership_failure":"ROUTING_EQUIVALENCE_FAILURE_NEVER_MASKED_BY_DOWNSTREAM_CLOSENESS","order_canonicalization":False,"diagnostic_downstream_capture":"ONLY_IF_FROZEN_EVIDENCE_POLICY_PERMITS_NO_EQUIVALENCE_PROMOTION","tolerance_cannot_hide_structural_failure":True,
    })
    determinism = write("f017-apple-production-serial-f32-determinism-v2.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-determinism-qualification","schema_version":"2.0.0","executed":False,"fresh_processes":10,"stage_count":34,"comparison":"BYTE_IDENTITY_ALL_STAGES_ALL_RUNS","same_package_root":root,"same_executable_sha256":RUNNER_SHA,
        "run_directory_scheme":"run-01..run-10","invocation_numbering":"1_BASED_FIXED","environment_census":"runtime-rebind-v2 exact","artifact_census":"34 stage files plus capture-manifest each run","hash_algorithm":"SHA-256","earliest_divergence":"FIRST_STAGE_ORDINAL_WITH_MORE_THAN_ONE_HASH","failure":"BANK_ALL_TEN_HASHES_AND_STOP_NO_AVERAGING_NO_TOLERANCE","terminal_states":"TEN_COMPLETE_REQUIRED","freshness":"TEN_DISTINCT_FOREGROUND_PROCESSES_NO_PROCESS_REUSE","representative_runs_this_phase":0,
        "harness":{"path":"scripts/research/f017_apple_serial_f32_ten_process_harness_v1.py","sha256":sha(REPO/"scripts/research/f017_apple_serial_f32_ten_process_harness_v1.py")},
    })
    accounting = write("f017-apple-production-serial-f32-future-real-event-accounting-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-future-real-event-accounting","schema_version":"1.0.0","classification":"RETAINED_ONLY_REAL_EXECUTION_EVENT_ZERO_PAYLOAD_DELTA","ledger_start":175,"ledger_terminal":175,"real_payload_consumption":0,"checkpoint_reads":0,"shard_opens":0,"execution_event_required":True,"attempt_receipt_terminal_required":True,"result_receipts_master_ledger_same_commit":True,"terminal_consumed_reads_derived_from_receipts":True,"terminal_json_not_sole_authority":True,"manual_ledger_increment":False,"master_ledger":binding(REPO/"docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json"),
    })
    auth_schema = write("f017-apple-production-serial-f32-future-authorization-schema-v2.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-future-authorization-schema","schema_version":"2.0.0","live_generation_requires_explicit_operator_only_flag":True,"normal_validation_can_generate_live":False,"issued_live_approvals":0,"issued_live_go_tokens":0,
        "authority_chain":"READINESS_HEAD_TO_FABLE_REVIEW_TO_HUMAN_APPROVAL_TO_MACHINE_LOCAL_GO","approval_fields":["schema","schema_version","event_id","release_id","attempt_id","release_sha256","readiness_head","execution_code_head","native_executable_sha256","code_manifest_sha256","runtime_binding_sha256","package_root_sha256","package_manifest_sha256","stage_manifest_sha256","capture_manifest_sha256","comparison_contract_sha256","determinism_contract_sha256","wrapper_sha256","terminalizer_sha256","reviewed_head","readiness_review_path","readiness_review_sha256","reviewer_model","verdict","approval_statement","approval_does_not_execute","approval_is_not_token","human_approval_identity","real_event_authorized","ledger","stop_boundary"],
        "go_token_fields":["schema","schema_version","event_id","release_id","attempt_id","release_sha256","approval_sha256","readiness_head","execution_code_head","native_executable_sha256","code_manifest_sha256","runtime_binding_sha256","package_root_sha256","package_manifest_sha256","stage_manifest_sha256","capture_manifest_sha256","comparison_contract_sha256","determinism_contract_sha256","wrapper_sha256","terminalizer_sha256","expected_starting_ledger","allowed_real_payload_consumption","allowed_attempt_count","retries","resume","checkpoint_reads","checkpoint_fallback","allowed_stage_range","allowed_output_root","human_approval_identity","disposition","real_event_authorized"],
        "required_disposition":"GO_EXECUTE_ONCE_NO_RETRY","token_reuse":False,"token_generation_tool":{"path":"scripts/research/f017_apple_serial_f32_go_generator_v1.py","sha256":sha(REPO/"scripts/research/f017_apple_serial_f32_go_generator_v1.py")},
    })
    rehearsal_contract = write("f017-apple-production-serial-f32-attempt-lifecycle-rehearsal-v1.json", {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-attempt-lifecycle-rehearsal","schema_version":"1.0.0","payload":"SYNTHETIC_INERT_ONLY","representative_data":False,"ledger_advance":0,
        "required_cases":["clean_preflight_failure","runtime_hash_mismatch","package_root_mismatch","missing_tensor","extra_tensor","wrong_tensor_sha","wrong_executable","lock_collision","stale_owned_attempt","exception_after_durable_attempt_start","receipt_mismatch","orphan_artifact","terminal_mismatch","duplicate_attempt","retry_attempt","wrapper_v1_invocation","authorization_missing","inert_authorization_presented_as_real","malformed_go_schema"],"expected":"ALL_FAIL_CLOSED","terminalizer_authority_unchanged":True,"terminalizer_sha256":sha(REPO/"scripts/research/f017_apple_serial_f32_capture_terminalizer_v2.py"),
    })
    # Wrapper hash is now stable and all preceding contract hashes are known.
    wrapper = REPO/"scripts/research/f017_apple_serial_f32_equivalence_wrapper_v3.py"
    terminalizer = REPO/"scripts/research/f017_apple_serial_f32_capture_terminalizer_v2.py"
    bound=[root_spec,package_manifest,root_result,comparison,routing,determinism,accounting,auth_schema,rehearsal_contract,stage_manifest,capture_manifest]
    release = {
        "schema":"pulsarmlx.f017.apple-production-serial-f32-equivalence-release","schema_version":"3.0.0","status":"PREPARED_REVIEW_REQUIRED","event_id":"F017-APPLE-PRODUCTION-SERIAL-F32-EQUIVALENCE-1","release_id":"F017-APPLE-PRODUCTION-SERIAL-F32-EQUIVALENCE-1-RELEASE-3","attempt_id":"F017-APPLE-PRODUCTION-SERIAL-F32-EQUIVALENCE-1-ATTEMPT-1","execution_code_head":CODE_HEAD,
        "code_manifest":binding(code_manifest),"runtime_binding":binding(runtime_rebind),"runner_path":str(PINNED_RUNNER),"native_executable_sha256":RUNNER_SHA,"wrapper_sha256":sha(wrapper),"terminalizer_sha256":sha(terminalizer),"runtime_required_linkage":["/opt/homebrew/opt/mlx-c/lib/libmlxc.dylib","/opt/homebrew/opt/mlx/lib/libmlx.dylib","/System/Library/Frameworks/Metal.framework/Versions/A/Metal"],
        "package_root_sha256":root,"package_census_sha256":sha(PACKAGE_CENSUS),"runner_package_sha256":sha(PACKAGE_JSON),"stage_manifest_sha256":sha(stage_manifest),"capture_manifest_sha256":sha(capture_manifest),"comparison_contract_sha256":sha(comparison),"determinism_contract_sha256":sha(determinism),
        "bound_contracts":[binding(path) for path in bound],"machine_local_paths":{"package_root":str(PACKAGE_ROOT),"package_manifest":str(PACKAGE_JSON),"package_census":str(PACKAGE_CENSUS),"attempt_root":str(ATTEMPT_ROOT),"capture_root":str(CAPTURE_ROOT),"go_token":"/Users/mhedhli/.local/share/pulsarmlx/f017/apple-production-serial-f32-equivalence-release-1/go-token.json"},
        "environment":{"thread_limits":{"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1","MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1"}},"ledger":{"start":175,"terminal":175,"classification":"RETAINED_ONLY_REAL_EXECUTION_EVENT_ZERO_PAYLOAD_DELTA"},
        "execution_budgets":{"checkpoint_reads":0,"shard_opens":0,"attention_executions":0,"expert_executions":0,"aggregate_executions":0,"shared_expert_executions":0,"ffn_compositions":0,"s1_materializations":0,"s2_constructions":0,"production_equivalence_executions":1,"attempts":1,"retries":0},
        "checkpoint_paths":[],"checkpoint_fallback":False,"resume":False,"second_attempt":False,"approval_schema_fields":json.loads(auth_schema.read_text())["approval_fields"],"go_token_schema_fields":json.loads(auth_schema.read_text())["go_token_fields"],"real_event_authorized":False,"live_go_token_created":False,"stop_boundary":"AFTER_APPLE_PRODUCTION_SERIAL_F32_CAPTURE_COMPARISON_AND_TEN_PROCESS_DETERMINISM_ONLY",
    }
    release_path=write("f017-apple-production-serial-f32-equivalence-single-use-release-v3.json",release)
    inert={field:None for field in release["go_token_schema_fields"]}
    inert.update({"schema":"pulsarmlx.f017.apple-production-serial-f32-inert-go-fixture","schema_version":"1.0.0","event_id":release["event_id"],"release_id":release["release_id"],"attempt_id":release["attempt_id"],"release_sha256":sha(release_path),"readiness_head":"INERT_UNREVIEWED","execution_code_head":CODE_HEAD,"native_executable_sha256":RUNNER_SHA,"code_manifest_sha256":sha(code_manifest),"runtime_binding_sha256":sha(runtime_rebind),"package_root_sha256":root,"package_manifest_sha256":sha(PACKAGE_CENSUS),"stage_manifest_sha256":sha(stage_manifest),"capture_manifest_sha256":sha(capture_manifest),"comparison_contract_sha256":sha(comparison),"determinism_contract_sha256":sha(determinism),"wrapper_sha256":sha(wrapper),"terminalizer_sha256":sha(terminalizer),"expected_starting_ledger":175,"allowed_real_payload_consumption":0,"allowed_attempt_count":0,"retries":0,"resume":False,"checkpoint_reads":0,"checkpoint_fallback":"PROHIBITED","allowed_stage_range":"NONE_INERT","allowed_output_root":"NONE_INERT","human_approval_identity":"INERT","approval_sha256":"0"*64,"disposition":"INERT_NOT_EXECUTABLE","real_event_authorized":False,"inert":True})
    # The inert-only marker is deliberately outside the live exact field set; validator/generator requires it.
    write("f017-apple-production-serial-f32-inert-go-fixture-v1.json",inert)
    print(json.dumps({"package_root":root,"release_sha256":sha(release_path),"code_manifest_sha256":sha(code_manifest),"runtime_rebind_sha256":sha(runtime_rebind),"comparison_sha256":sha(comparison),"determinism_sha256":sha(determinism)},sort_keys=True))

if __name__ == "__main__": main()

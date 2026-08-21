#!/usr/bin/env python3
"""Fail-closed retained-only validator for Apple serial-f32 readiness."""

from __future__ import annotations
import argparse, hashlib, json, os, stat, subprocess
from pathlib import Path

try:
    from .f017_apple_serial_f32_execution_readiness_v1 import derive_descriptors, validate_destination
    from .f017_apple_serial_f32_equivalence_wrapper_v3 import validate_release
except ImportError:
    from f017_apple_serial_f32_execution_readiness_v1 import derive_descriptors, validate_destination
    from f017_apple_serial_f32_equivalence_wrapper_v3 import validate_release

REPO = Path(__file__).resolve().parents[2]
CONTRACTS = REPO / "specs/017-rust-native-inference-runtime/contracts"
RELEASE = CONTRACTS / "f017-apple-production-serial-f32-equivalence-single-use-release-v4.json"

class ValidationError(RuntimeError): pass
def load(path):
    def pairs(rows):
        result={}
        for k,v in rows:
            if k in result: raise ValidationError(f"DUPLICATE:{path}:{k}")
            result[k]=v
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value, reason):
    if not value: raise ValidationError(reason)


def validate_package_contract(doc):
    require(doc["tensor_count"]==40 and len(doc["ordered_tensors"])==40, "PACKAGE_CENSUS")
    require([r["ordinal"] for r in doc["ordered_tensors"]]==list(range(40)), "PACKAGE_ORDER")
    require(len({r["role"] for r in doc["ordered_tensors"]})==40, "PACKAGE_ROLES")
    require(doc["consumer_policy"]=={"rehash_actual_bytes":True,"no_path_only_trust":True,"no_manifest_only_trust":True,"regular":True,"non_symlink":True,"single_link":True,"read_only":True,"no_extra_files":True,"same_descriptor":True,"checkpoint_fallback":False}, "PACKAGE_POLICY")
    require(doc["assembly"]["numerical_transformations"]==0 and doc["assembly"]["checkpoint_reads"]==0, "PACKAGE_TRANSFORM")
    derived=derive_descriptors()
    require([r["sha256"] for r in doc["ordered_tensors"]]==[r["sha256"] for r in derived], "PACKAGE_TENSOR_SHA")
    require([r["destination_relative_path"] for r in doc["ordered_tensors"]]==[r["destination_relative_path"] for r in derived], "PACKAGE_DESTINATION")
    require([r["encoding"] for r in doc["ordered_tensors"]]==[r["encoding"] for r in derived], "PACKAGE_ENCODING")
    require([r["shape"] for r in doc["ordered_tensors"]]==[r["shape"] for r in derived], "PACKAGE_SHAPE")


def validate_code_manifest(doc):
    paths={r["path"] for r in doc["artifacts"]}
    for required in ("crates/quant/src/iq_ref.rs","crates/quant/src/cpu_dot_tables.rs","crates/quant/src/cpu_dot.rs","crates/quant/src/q6_k_ref.rs","crates/quant/src/q8_0_ref.rs","crates/stream/src/apple_mlx_bridge.mm"):
        require(required in paths, f"CODE_SOURCE:{required}")
    head=load(CONTRACTS/"f017-apple-production-serial-f32-execution-code-head-v1.json")["execution_code_head"]
    require(doc["execution_code_head"]==head, "CODE_HEAD")
    for row in doc["artifacts"]:
        require(sha(REPO/row["path"])==row["sha256"], f"CODE_HASH:{row['path']}")


def validate_comparison(doc):
    require(doc["executed"] is False and doc["stage_count"]==34 and len(doc["stage_rows"])==34, "COMPARISON_STATE")
    require([r["ordinal"] for r in doc["stage_rows"]]==list(range(34)), "COMPARISON_ORDER")
    require(all(r["observed_result"] is None and r["execution_status"]=="NOT_EXECUTED" for r in doc["stage_rows"]), "PREMATURE_RESULT")
    require(doc["tolerance_policy"]["post_hoc_changes"] is False and doc["tolerance_policy"]["enlargement_requires_new_contract_and_review"] is True, "TOLERANCE_POLICY")
    m=doc["metrics"]
    require(m["r10_intermediate"]["max_abs_error"]==0.015625 and m["r10_intermediate"]["rmse"]==0.0078125 and m["r10_intermediate"]["cosine_similarity_min"]==0.9999, "R10_TOLERANCE")
    require(m["complete_layer_final"]["max_abs_error"]==0.0625 and m["complete_layer_final"]["rmse"]==0.03125 and m["complete_layer_final"]["cosine_similarity_min"]==0.999, "S2_TOLERANCE")
    require(m["routing_weight_frozen"]["membership_exact"] is True and m["routing_weight_frozen"]["order_exact"] is True, "ROUTING_STRUCTURAL")


def validate_routing(doc):
    require(doc["ordered_gates"]==["SELECTED_EXPERT_MEMBERSHIP_EXACT","SELECTED_EXPERT_ORDER_EXACT","TIE_BEHAVIOR_EXACT","ROUTING_WEIGHT_FROZEN_COMPARISON","ROUTED_EXPERT_STAGE_COMPARISONS","ROUTED_AGGREGATE_COMPARISON"], "ROUTING_ORDER")
    require(doc["order_canonicalization"] is False and doc["tolerance_cannot_hide_structural_failure"] is True, "ROUTING_MASK")


def validate_determinism(doc):
    require(doc["executed"] is False and doc["fresh_processes"]==10 and doc["stage_count"]==34, "DETERMINISM_STATE")
    require(doc["comparison"]=="BYTE_IDENTITY_ALL_STAGES_ALL_RUNS" and doc["freshness"]=="TEN_DISTINCT_FOREGROUND_PROCESSES_NO_PROCESS_REUSE", "DETERMINISM_RULE")
    require(doc["representative_runs_this_phase"]==0 and "NO_AVERAGING_NO_TOLERANCE" in doc["failure"], "DETERMINISM_FAILURE")


def validate_authorization(doc, inert):
    require(doc["issued_live_approvals"]==0 and doc["issued_live_go_tokens"]==0 and doc["normal_validation_can_generate_live"] is False, "LIVE_AUTHORITY")
    require(doc["required_disposition"]=="GO_EXECUTE_ONCE_NO_RETRY" and doc["token_reuse"] is False, "TOKEN_ONE_SHOT")
    require(inert["inert"] is True and inert["real_event_authorized"] is False and inert["disposition"]=="INERT_NOT_EXECUTABLE", "INERT_FIXTURE")


def validate_accounting(doc):
    require(doc["classification"]=="RETAINED_ONLY_REAL_EXECUTION_EVENT_ZERO_PAYLOAD_DELTA", "EVENT_CLASS")
    require(doc["ledger_start"]==175 and doc["ledger_terminal"]==175 and doc["real_payload_consumption"]==0, "LEDGER")
    require(doc["result_receipts_master_ledger_same_commit"] is True and doc["terminal_consumed_reads_derived_from_receipts"] is True and doc["manual_ledger_increment"] is False, "BANKING")


def validate_repo():
    package=load(CONTRACTS/"f017-apple-production-serial-f32-retained-40-tensor-package-v1.json")
    code=load(CONTRACTS/"f017-apple-production-serial-f32-code-manifest-v3.json")
    comparison=load(CONTRACTS/"f017-apple-production-serial-f32-comparison-execution-contract-v1.json")
    routing=load(CONTRACTS/"f017-apple-production-serial-f32-routing-execution-gates-v1.json")
    determinism=load(CONTRACTS/"f017-apple-production-serial-f32-determinism-v2.json")
    accounting=load(CONTRACTS/"f017-apple-production-serial-f32-future-real-event-accounting-v1.json")
    auth=load(CONTRACTS/"f017-apple-production-serial-f32-future-authorization-schema-v3.json")
    inert=load(CONTRACTS/"f017-apple-production-serial-f32-inert-go-fixture-v2.json")
    validate_package_contract(package); validate_code_manifest(code); validate_comparison(comparison); validate_routing(routing); validate_determinism(determinism); validate_accounting(accounting); validate_authorization(auth,inert)
    package_result=validate_destination(derive_descriptors())
    require(package_result["package_root_sha256"]==package["package_root_sha256"], "PACKAGE_ROOT")
    release=validate_release(RELEASE)
    require(release["package_root_sha256"]==package["package_root_sha256"], "RELEASE_PACKAGE")
    ledger=load(REPO/"docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json")
    require(ledger["receipt_chain"]["terminal_count"]==175 and ledger["cumulative_tensor_payloads"]==175, "MASTER_LEDGER")
    for path in (Path(release["machine_local_paths"]["attempt_root"]),Path(release["machine_local_paths"]["capture_root"]),Path(release["machine_local_paths"]["go_token"])):
        require(not path.exists(), f"STATE_PRESENT:{path}")
    tombstone=subprocess.run([str(REPO/"scripts/research/f017_apple_serial_f32_capture_wrapper_v1.py")],capture_output=True,text=True)
    require(tombstone.returncode==78 and "TOMBSTONED" in tombstone.stderr, "WRAPPER_V1")
    runtime=load(CONTRACTS/"f017-apple-production-serial-f32-runtime-rebind-v3.json")
    return {"status":"F017_APPLE_SERIAL_F32_EXECUTION_READINESS_VALID","tensor_count":40,"package_root_sha256":package_result["package_root_sha256"],"ledger":175,"checkpoint_reads":0,"shard_opens":0,"production_equivalence_executions":0,"determinism_runs":0,"live_go_tokens":0,"native_executable_sha256":sha(Path(runtime["native_executable"]["path"])),"mlx_dylib_sha256":sha(Path(runtime["mlx"]["library"]["path"])),"mlx_c_dylib_sha256":sha(Path(runtime["mlx_c"]["library"]["path"]))}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",action="store_true"); parser.add_argument("--write-evidence",type=Path); parser.add_argument("--validated-head"); args=parser.parse_args()
    if not args.repo: raise SystemExit("--repo required")
    result=validate_repo()
    if args.write_evidence:
        if not args.validated_head: raise SystemExit("--validated-head required with --write-evidence")
        evidence={"schema":"pulsarmlx.f017.apple-production-serial-f32-execution-readiness-mechanical-measurement","schema_version":"2.0.0","validated_head":args.validated_head,"measurements":result,"measurement_method":"VALIDATOR_DIRECT_REHASH_OF_ACTUAL_MACHINE_BYTES","numerical_execution":0,"representative_data_consumption":0}
        args.write_evidence.write_text(json.dumps(evidence,sort_keys=True,separators=(",", ":"))+"\n")
    print(json.dumps(result,sort_keys=True,separators=(",", ":")))

if __name__=="__main__": main()

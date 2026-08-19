#!/usr/bin/env python3
"""Fail-closed validator for representative expert recovery authorization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-recovery-authorization-v1.json"
REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-packed-weight-reuse-authorization-v1.json"
COMPUTATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-computation-v1.json"
SOURCE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-recovery-evidence-review-v1.json"
ROUTE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-concrete-route-values-v1.json"
EXECUTION = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"
SELECTED = [250, 10, 237, 62, 73, 177, 218, 28]
WEIGHTS = [0.7487501576296707,0.3348627106807668,0.23863270273063697,0.23688715675086147,0.2514906203405492,0.23059957299763345,0.22915341148588297,0.22962366738399842]


class ValidationError(ValueError): pass


def require(value: bool, code: str) -> None:
    if not value: raise ValidationError(code)


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    require(isinstance(value, dict), "JSON_OBJECT")
    return value


def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def csha(value: Any) -> str: return hashlib.sha256(canonical(value)).hexdigest()


def expected_inventory(source: dict[str, Any]) -> list[dict[str, Any]]:
    by_pair = {(x["expert_id"],x["role"]):x for x in source["payloads"]}
    result=[]
    for ordinal,(expert,role) in enumerate((e,r) for e in SELECTED for r in ("gate","up","down")):
        x=by_pair[(expert,role)]; seq=x["sequence"]
        result.append({"ordinal":ordinal,"expert_id":expert,"role":role,"checkpoint_key":x["checkpoint_key"],
          "shard_ordinal":2,"shard_sha256":source["checkpoint_access"]["shard_sha256"],"offset":x["offset"],
          "packed_bytes":x["packed_bytes"],"quantization":x["quantization"],"logical_shape":x["logical_shape"],
          "packed_sha256":x["packed_sha256"],"decoded_sha256":x["decoded_sha256"],
          "decoder_a_identity":x["decoder_a_identity"],"decoder_b_identity":x["decoder_b_identity"],
          "source_event_sequence":seq,"source_relative_path":f"{seq:02d}-expert-{expert}-{role}.bin",
          "availability":"PERSISTED_PACKED_AUTHORITY","new_checkpoint_read_required":False})
    return result


def validate(root: Path, auth: dict[str, Any] | None = None) -> str:
    document = auth or load(root / AUTH.relative_to(ROOT))
    route = load(root / ROUTE.relative_to(ROOT)); execution=load(root / EXECUTION.relative_to(ROOT)); source=load(root / SOURCE.relative_to(ROOT))
    require(document.get("schema")=="pulsarmlx.f017.representative-expert-recovery-authorization" and document.get("schema_version")=="1.0.0","SCHEMA")
    require(document.get("status")=="PREPARED_REVIEW_REQUIRED" and document.get("real_event_authorized") is False,"STATUS")
    require(document.get("preparation_base_head")=="461617c83986af30b1bb5c93981fa2c5caf29545","BASE_HEAD")
    require(document.get("execution_evidence_sha256")==digest(root/EXECUTION.relative_to(ROOT))=="dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190","EXECUTION")
    require(document.get("route_value_evidence_sha256")==digest(root/ROUTE.relative_to(ROOT))=="6035308cb85a29617abe5dcb18be37ab6d99afb5193d28ed7993d41c2aeb7b49","ROUTE")
    require(document.get("selected_expert_ids")==SELECTED and document.get("routing_weights")==WEIGHTS,"ROUTE_VALUES")
    require(document.get("route_pairs")==[{"ordinal":i,"expert_id":e,"routing_weight":w,"binding":"ATOMIC_ID_WEIGHT_PAIR"} for i,(e,w) in enumerate(zip(SELECTED,WEIGHTS,strict=True))],"PAIR_BINDING")
    require(hashlib.sha256(struct.pack("<8H",*SELECTED)).hexdigest()==document.get("selected_ids_sha256"),"SELECTED_SHA")
    require(hashlib.sha256(b"".join(struct.pack("<d",x) for x in WEIGHTS)).hexdigest()==document.get("routing_weights_sha256"),"WEIGHT_SHA")
    require(document.get("representative_route_sha256")==route["route_identity"]["sha256"],"REP_ROUTE_SHA")
    inp=document.get("representative_expert_input",{})
    require(inp.get("sha256")=="687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c","INPUT_SHA")
    require(inp.get("dtype")=="little-endian-f32" and inp.get("shape")==[6144] and inp.get("byte_length")==24576,"INPUT_GEOMETRY")
    require(inp.get("semantic_role")=="CANONICAL_REPRESENTATIVE_POST_ATTENTION_FFN_NORMALIZED_EXPERT_INPUT" and inp.get("expected_equals_before_equals_after") is True and inp.get("checkpoint_fallback") is False,"INPUT_ROLE")
    for field in ("private_manifest_sha256","materializer_sha256"):
        require(isinstance(inp.get(field),str) and len(inp[field])==64,"INPUT_BINDING")
    require(inp.get("materializer_sha256")==digest(root/inp["materializer_path"]),"MATERIALIZER_SHA")
    inventory=expected_inventory(source)
    require(document.get("retained_payload_inventory")==inventory,"INVENTORY")
    require(len(inventory)==24 and sum(x["packed_bytes"] for x in inventory)==90_439_680,"INVENTORY_TOTAL")
    require(len({x["checkpoint_key"] for x in inventory})==24,"INVENTORY_DUPLICATE")
    reuse=document.get("retained_weight_reuse",{}); reuse_path=root/reuse.get("path","")
    require(reuse.get("sha256")==digest(reuse_path) and reuse.get("consumer_id")==document.get("event_id"),"REUSE_BINDING")
    reuse_doc=load(reuse_path)
    require(reuse_doc.get("consumer_id")==document.get("event_id") and reuse_doc.get("retained_payload_inventory")==inventory,"REUSE_SCOPE")
    require(reuse_doc.get("source_private_manifest_sha256")=="86d577020ad3e5bf6480b774536416145a154104eac643b21df644044a55e99e","SOURCE_MANIFEST")
    require(reuse_doc.get("source_evidence_review_sha256")==digest(root/SOURCE.relative_to(ROOT)),"SOURCE_REVIEW_SHA")
    require(reuse_doc.get("checkpoint_fallback") is False and reuse_doc.get("checkpoint_reads")==0 and reuse_doc.get("shard_opens")==0,"REUSE_ACCESS")
    computation=document.get("computation_contract",{}); computation_path=root/computation.get("path","")
    require(computation.get("sha256")==digest(computation_path),"COMPUTATION_BINDING")
    comp=load(computation_path)
    require(comp.get("per_expert_formula")=="down(strict_f32_silu(gate(input)) * up(input))" and comp.get("blas_permitted") is False and comp.get("gpu_permitted") is False and comp.get("aggregate_permitted") is False,"COMPUTATION")
    require(comp.get("input",{}).get("semantic_role")==inp.get("semantic_role"),"INPUT_ROLE_VOCABULARY")
    authority=comp.get("runtime_decoder_authority",{})
    require(authority.get("decoder_a_identity")==inventory[0]["decoder_a_identity"] and authority.get("decoder_b_identity")==inventory[0]["decoder_b_identity"],"RUNTIME_DECODER_IDENTITY")
    require(authority.get("rust_binary_sha256")=="680a6f67ca6efd571edc5081e8557034f327e71a3e0f4674e21686b703ca6d25" and authority.get("resolve_before_attempt_start") is True,"RUNTIME_DECODER_BINARY")
    for item in comp.get("decoder_source_bindings",[]): require(digest(root/item["path"])==item["sha256"],"DECODER_SOURCE_BINDING")
    executor=document.get("executor",{}); executor_path=root/executor.get("path","")
    require(executor.get("sha256")==digest(executor_path) and executor.get("checkpoint_capability") is False and executor.get("shard_capability") is False,"EXECUTOR")
    accounting=document.get("access_accounting")
    require(accounting=={"starting_real_payload_ledger":175,"successful_terminal_ledger":175,"new_checkpoint_payload_reads":0,"new_checkpoint_packed_bytes":0,"shard_opens":0,"retained_packed_payloads":24,"retained_packed_bytes":90439680},"ACCOUNTING")
    failure=document.get("failure_semantics",{})
    require(failure.get("preflight_all_inputs_before_expert_execution") is True and failure.get("partial_output_failure_is_terminal") is True,"TERMINALIZATION")
    require(all(failure.get(x) is False for x in ("retry","resume","second_attempt")) and failure.get("ledger_change_on_any_outcome")==0,"NO_RETRY")
    output=document.get("output_contract",{})
    require(output.get("individual_outputs")==8 and output.get("canonical_order")==SELECTED and output.get("two_fresh_process_reproductions_required")==2 and output.get("all_eight_output_sha256_exact") is True and output.get("consumer_authority_requires_terminal_complete") is True,"OUTPUT")
    require(all(document.get("prohibitions",{}).get(x) is True for x in ("checkpoint_access","shard_open","historical_direct_dprefix_input","historical_direct_dprefix_outputs","routed_aggregate","shared_expert","ffn_completion","candidate_dispatch","gpu")),"PROHIBITIONS")
    require(document.get("stop_boundary")=="AFTER_EIGHT_INDIVIDUAL_REPRESENTATIVE_EXPERT_OUTPUTS_ARE_BANKED_BEFORE_WEIGHTED_AGGREGATE","STOP_BOUNDARY")
    rehearsal=document.get("synthetic_rehearsal")
    require(isinstance(rehearsal,dict) and rehearsal.get("sha256")==digest(root/rehearsal.get("path","")),"REHEARSAL_BINDING")
    rehearse=load(root/rehearsal["path"])
    require(rehearse.get("fresh_process_runs")==2 and rehearse.get("fresh_process_exact_output_identity") is True,"REHEARSAL_REPRODUCTION")
    decoder_rehearsal=rehearse.get("runtime_decoder_preflight",{})
    require(decoder_rehearsal.get("decoder_a_identity")==authority.get("decoder_a_identity") and decoder_rehearsal.get("decoder_b_identity")==authority.get("decoder_b_identity") and decoder_rehearsal.get("result")=="2/2 EXACT AGREEMENT BEFORE ATTEMPT START","REHEARSAL_DECODER")
    require(rehearse.get("failure_paths_passed")==rehearse.get("failure_paths_required") and rehearse.get("failure_paths_required",0)>=20,"REHEARSAL_FAILURES")
    require(rehearse.get("checkpoint_reads")==0 and rehearse.get("shard_opens")==0 and rehearse.get("real_ledger_delta")==0 and rehearse.get("real_expert_executions")==0,"REHEARSAL_ISOLATION")
    candidate=dict(document); candidate.pop("candidate_semantic_sha256",None); candidate.pop("synthetic_rehearsal",None)
    require(document.get("candidate_semantic_sha256")==csha(candidate),"CANDIDATE_DIGEST")
    require(rehearse.get("candidate_semantic_sha256")==document.get("candidate_semantic_sha256"),"REHEARSAL_CANDIDATE")
    require(execution.get("access_accounting",{}).get("ledger_after")==175 and execution.get("access_accounting",{}).get("expert_executions")==0,"HISTORICAL_STATE")
    return "REPRESENTATIVE_EXPERT_RECOVERY_AUTHORIZATION_VALID"


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--root",type=Path,default=ROOT); parser.add_argument("--authorization",type=Path)
    args=parser.parse_args(); doc=load(args.authorization) if args.authorization else None; print(validate(args.root,doc)); return 0


if __name__=="__main__": raise SystemExit(main())

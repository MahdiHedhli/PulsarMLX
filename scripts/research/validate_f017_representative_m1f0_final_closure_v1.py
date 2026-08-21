#!/usr/bin/env python3
"""Validate the committed representative M1-F0 closure graph without computation."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import sys
from typing import Any
from f017_representative_expert_ledger_adapter_v1 import current_ledger

ROOT=Path(__file__).resolve().parents[2]
PACKAGE=ROOT/"docs/architecture/reviews/evidence/f017-representative-m1f0-final-closure-package-v1.json"
SPEC=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-final-closure-review-spec-v1.json"

class ClosureError(ValueError): pass
def require(value: bool, message: str) -> None:
    if not value: raise ClosureError(message)
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def unique(pairs: list[tuple[str,Any]]) -> dict[str,Any]:
    out={}
    for key,value in pairs:
        require(key not in out,f"DUPLICATE_KEY:{key}"); out[key]=value
    return out
def load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(),object_pairs_hook=unique); require(isinstance(value,dict),"OBJECT_REQUIRED"); return value
def bind(binding: dict[str,Any], label: str) -> None:
    require(set(binding)=={"path","sha256"},f"{label}_CENSUS")
    require(sha(ROOT/binding["path"])==binding["sha256"],f"{label}_SHA")

STAGE_NAMES=["S0","ATTENTION_AND_ROUTE_SURFACE","S1","F_NORM_ROUTER_NORMALIZED","REPRESENTATIVE_ROUTE","ROUTED_EXPERTS","ROUTED_AGGREGATE","SHARED_EXPERT","FFN","S2"]
ATTENTION_HASHES={
"input_hidden":"9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11","attention_normalized":"5a73ca4d2def05d38529365242845d29ae92956e00d770b69694662161d32b9f","query_rank":"17eea937719b3fab96f81252c9076176a0be5e8a2de0c91667a9bb93bd484dce","query_rank_normalized":"9a3db16a46fe88a8e4519434d4084561544be39c4b9132a0e8b0e6e584ee6dd7","query_heads":"88fadaec9db988a5e8f781c43909ccdf016fa390e7d3a6f14e1861a15cacb914","kv_raw":"1d0247977881d9cb7819a79a1a093df74155492f56ff27ac89d371e19c4d1aec","kv_normalized":"252774a4a3c5f26388ca74ef4458f67ec5e521811494d2fe0e7be7bbf4c6ab07","key_nope":"fa5968068d8ac5599ad392198f1348b2bbd118b7ef8b2db2b29c365177a4d87b","attention_scores":"4366bfb68e99caa1f3d26d86efc0042e6aac92a230f405cd7fb760c74ee9ba74","attention_weights":"2f20cd03c9cd392a406c56232b0ff93a15f6d6d7da79086bfa14f55d4a4031b0","value_heads":"0c544940e9747f5aeebe97c27bbe5b47240bd415b5bb9780a3ac9686a027dcbb","attention_output":"7b0948a561a41fb3fdf5ab3f4b7d04d8a3941cfbbb51c54aa0745cb6ec278a6e","post_attention_residual":"8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd","router_normalized":"687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c","router_logits":"62d0f85f0673fa6d964e7573861851e4894f9b7433241083753833fe461d3c6d","router_scores":"bf70b166ac9d8e6119b3920f0f6c4f1e69dece1f45b1904e2d5ef77e8da0d575","ranking":"b2de9d7a4fe2701f0cda51f6b95a5396195e0bf0c44924aa6d46b4a899af549d","selected_ids":"a0f2e2b59ebc606c43e17eab8f76a5b14c26b678bef2a9b0207c3f7dd15f164f","routing_weights":"ff1a7127b418b80dce4e4361e314c16ad50e86484cb1861ad27f6f9ee70b8587"}
IDS=[250,10,237,62,73,177,218,28]
WEIGHTS=[0.7487501576296707,0.3348627106807668,0.23863270273063697,0.23688715675086147,0.2514906203405492,0.23059957299763345,0.22915341148588297,0.22962366738399842]
EXPERT_SHAS=["0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b","d9adb474f64c98349dfe0a6c768b2020b27f62ecc85874975c990b880ef304b3","4ac842afb3b1909f9f0e07013c86bbdca90cd246b6190bf190a60fe9767fdd9b","2550cccf9b2f1a83b2e2f03f090ee135dc525a15eaf1bab18d1a2fb97af16128","9aa5e1dae2619c440c65689154de332da313990b4ba07fdac45e78a65ad3a7d3","18260d4936483b6f7d83d2d0ec72d01fc761f2ac5726fa9b7bda243a4db9a201","f4a8fc1e3bb91a8a5635505f766a07ef2cfb135378d224ed5f545617d781537d","45029a47061c43746344d5b0a9366b8129630019a3196d0be146efc5e1a361f0"]

def validate(document: dict[str,Any]) -> dict[str,Any]:
    require(document["schema"]=="pulsarmlx.f017.representative-m1f0-final-closure-package" and document["schema_version"]=="1.0.0","SCHEMA")
    require(document["status"]=="PREPARED_FOR_INDEPENDENT_FINAL_CLOSURE_REVIEW","STATUS")
    require(document["project_level_m1f0_closure_declared"] is False and document["final_closure_requires_separate_authority"] is True,"AUTHORITY_BOUNDARY")
    graph=document["canonical_graph"]
    require(document["bound_canonical_stage_count"]==len(graph)==10,"STAGE_COUNT")
    require([s["stage"] for s in graph]==STAGE_NAMES and [s["ordinal"] for s in graph]==list(range(10)),"GRAPH_ORDER")
    for stage in graph:
        for key in ("evidence","execution_evidence","reuse_authorization","reuse_review"):
            if key in stage: bind(stage[key],f"{stage['stage']}:{key}")
    require(graph[0]["sha256"]==ATTENTION_HASHES["input_hidden"],"S0")
    require(graph[1]["stage_sha256"]==ATTENTION_HASHES,"ATTENTION_19")
    attention=load(ROOT/graph[1]["evidence"]["path"])
    require(attention["stage_sha256"]==ATTENTION_HASHES,"ATTENTION_SOURCE")
    require(graph[1]["historical_access_accounting"]=={"ledger_before":166,"ledger_after":175,"checkpoint_reads":9,"shard_opens":1,"packed_bytes_consumed":132900864,"checkpoint_rereads":0,"expert_executions":0},"ATTENTION_ACCOUNTING")
    require(graph[2]["sha256"]==ATTENTION_HASHES["post_attention_residual"] and graph[3]["sha256"]==ATTENTION_HASHES["router_normalized"],"S1_FNORM")
    route=graph[4]
    require(route["route_sha256"]=="03dc2dfbed65848fdcb649f41f98793ca0f8cdd702c76b55d71c762fc5338103","ROUTE_SHA")
    require([p["expert_id"] for p in route["ordered_id_weight_pairs"]]==IDS and [p["weight"] for p in route["ordered_id_weight_pairs"]]==WEIGHTS,"ROUTE_ATOMICITY")
    require(route["historical_direct_dprefix_route"]=="VALID_BUT_DIFFERENT_SURFACE_PROHIBITED_FROM_SUBSTITUTION","HISTORICAL_ROUTE_BOUNDARY")
    experts=graph[5]
    require([p["expert_id"] for p in experts["ordered_outputs"]]==IDS and [p["sha256"] for p in experts["ordered_outputs"]]==EXPERT_SHAS,"EXPERT_ATOMICITY")
    require(experts["historical_direct_dprefix_outputs"]=="VALID_BUT_DIFFERENT_SURFACE_PROHIBITED_FROM_SUBSTITUTION","HISTORICAL_EXPERT_BOUNDARY")
    require(graph[6]["sha256"]=="872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9" and graph[7]["sha256"]=="8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b","AGGREGATE_SHARED")
    require(graph[8]["sha256"]=="4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a" and graph[8]["formula"]=="FFN[k] = Routed_f64[k] + binary64(Shared_f32[k])","FFN")
    require(graph[9]["sha256"]=="0341314230654d21fa56506dfe601f90bdb603fc38fd1203b6dd62b1e54c98c1" and graph[9]["formula"]=="S2_f32[k] = binary32(binary64(S1_f32[k]) + FFN_f64[k])","S2")
    require(all("PRODUCTION_SERIAL_F32" in graph[i]["surface"] for i in (6,8,9)),"SURFACE_DISCLOSURE")
    accounting=document["accounting_closure"]
    require(accounting=={"representative_lineage_ledger_start":166,"representative_lineage_ledger_final":175,"only_ledger_consuming_representative_event":"REPRESENTATIVE_M1F0_ATTENTION_ROUTE_EXECUTION","only_ledger_transition":"166_TO_175","historical_checkpoint_reads":9,"historical_shard_opens":1,"post_attention_checkpoint_reads":0,"post_attention_shard_opens":0,"closure_preparation_checkpoint_reads":0,"closure_preparation_shard_opens":0,"final_ledger":175,"hidden_checkpoint_rereads":0,"hidden_shard_opens":0,"unauthorized_second_attempts":0,"historical_direct_dprefix_substitutions":0},"ACCOUNTING_CLOSURE")
    require(all(x["disposition"].startswith("CONSUMED_") or x["disposition"].startswith("SUPERSEDED_") for x in document["single_use_authority_disposition"]),"SINGLE_USE_DISPOSITION")
    for item in document["single_use_authority_disposition"]:
        if "evidence" in item: bind(item["evidence"],f"SUPERSESSION:{item['authority']}")
    require(all(document["replay_closure"].values()),"REPLAY_CLOSURE")
    require(document["reproduction_status"]["s2"]=="SOUND_WITHOUT_ADDITIONAL_POST_EVENT_REPRODUCTION","S2_REPRODUCTION")
    require(document["surface_disposition"]["production_serial_f32_equivalence_claimed"] is False,"PRODUCTION_NONCLAIM")
    require(document["closure_preparation_activity"]=={"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"attention_executions":0,"expert_executions":0,"shared_expert_executions":0,"aggregate_executions":0,"ffn_compositions":0,"s1_materializations":0,"s2_constructions":0},"PREPARATION_ACTIVITY")
    require(document["stop_boundary"]=="AFTER_INDEPENDENT_CLOSURE_PACKAGE_REVIEW_BEFORE_FINAL_PROJECT_LEVEL_M1F0_CLOSURE_DECLARATION","STOP_BOUNDARY")
    require(current_ledger()==175,"CURRENT_LEDGER")
    return {"result":"REPRESENTATIVE_M1F0_FINAL_CLOSURE_PACKAGE_VALID","bound_canonical_stages":10,"attention_stage_hashes":19,"expert_outputs":8,"ledger":175,"checkpoint_reads_this_phase":0,"shard_opens_this_phase":0,"new_numerical_events":0,"final_closure_declared":False}

def validate_spec(spec: dict[str,Any]) -> None:
    require(spec["schema"]=="pulsarmlx.f017.representative-m1f0-final-closure-review-spec" and spec["schema_version"]=="1.0.0","SPEC_SCHEMA")
    require(spec["reviewer_model"]=="claude-fable-5" and spec["review_committed_bytes_only"] is True,"SPEC_REVIEWER")
    bind(spec["closure_package"],"SPEC_PACKAGE")
    require(len(spec["required_attacks"])==16,"SPEC_ATTACKS")
    require(all(spec["acceptance_criteria"].values()),"SPEC_ACCEPTANCE")
    require(spec["finding_policy"]=={"BLOCKING":"REJECT","NON_BLOCKING_REQUIRED":"REJECT","DEFENSE_IN_DEPTH":"ALLOWED_ONLY_WITH_CONCRETE_NON_BLOCKING_DISPOSITION"},"SPEC_FINDINGS")
    require(spec["review_does_not_declare_project_level_closure"] is True and all(spec["hard_prohibitions"].values()),"SPEC_BOUNDARY")

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--package",type=Path,default=PACKAGE); args=parser.parse_args()
    try: result=validate(load(args.package)); validate_spec(load(SPEC)); print(json.dumps(result,sort_keys=True))
    except Exception as error: print(json.dumps({"result":"REJECT","error":str(error)},sort_keys=True),file=sys.stderr); raise SystemExit(1)

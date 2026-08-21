#!/usr/bin/env python3
"""Validate the final representative M1-F0 closure declaration without data-plane access."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
import sys
from typing import Any
from f017_representative_expert_ledger_adapter_v1 import current_ledger

ROOT=Path(__file__).resolve().parents[2]
DECLARATION=ROOT/"docs/architecture/reviews/evidence/f017-representative-m1f0-final-closure-declaration-v1.json"
PACKAGE_SHA="7b6d38d15889a0811bd8a0d54ce0e9e495da7918cea323d7995d9dc35e1c5402"
REVIEW_SHA="1b014af874ca90f30b17c2fac87a66744126067401c76c2386eaf54596662a3a"
S2_SHA="0341314230654d21fa56506dfe601f90bdb603fc38fd1203b6dd62b1e54c98c1"
REVIEWED_HEAD="694879463427dc83f3153a46e8abbf766deb856a"
BASE_HEAD="19206a43818236792f6e366dcf3130e2e990e758"

class DeclarationError(ValueError): pass
def require(value: bool, message: str) -> None:
    if not value: raise DeclarationError(message)
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def unique(pairs: list[tuple[str,Any]]) -> dict[str,Any]:
    result={}
    for key,value in pairs:
        require(key not in result,f"DUPLICATE_KEY:{key}"); result[key]=value
    return result
def load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(),object_pairs_hook=unique); require(isinstance(value,dict),"OBJECT_REQUIRED"); return value
def git(*args: str) -> bytes:
    return subprocess.check_output(["git",*args],cwd=ROOT)

def validate(document: dict[str,Any]) -> dict[str,Any]:
    require(set(document)=={"schema","schema_version","declaration_id","authoritative_branch","declaration_base_head","declaration_status","declaration_statement","closure_statement","accepted_authority","canonical_authority","scope_proven","scope_limit","non_claims","surface_non_claim","defense_in_depth_review_binding","later_committed_evidence_audit","declaration_phase_accounting","new_independent_review_required","independent_review_authority","termination_condition"},"DECLARATION_CENSUS")
    require(document["schema"]=="pulsarmlx.f017.representative-m1f0-final-closure-declaration" and document["schema_version"]=="1.0.0","SCHEMA")
    require(document["authoritative_branch"]=="feat/017-real-checkpoint-runner" and document["declaration_base_head"]==BASE_HEAD,"GIT_AUTHORITY")
    require(document["declaration_status"]=="ACCEPTED" and document["declaration_statement"]=="REPRESENTATIVE_M1F0_FINAL_CLOSURE: ACCEPTED","DECLARATION")
    require(document["closure_statement"]=="The canonical representative M1-F0 S0-to-S2 proof/reference lineage is closed against the accepted committed evidence package.","CLOSURE_STATEMENT")
    authority=document["accepted_authority"]
    package_binding=authority["closure_package"]; review_binding=authority["closure_review"]
    require(package_binding=={"path":"docs/architecture/reviews/evidence/f017-representative-m1f0-final-closure-package-v1.json","sha256":PACKAGE_SHA},"PACKAGE_BINDING")
    require(sha(ROOT/package_binding["path"])==PACKAGE_SHA,"PACKAGE_SHA")
    require(review_binding=={"path":"docs/architecture/reviews/evidence/f017-representative-m1f0-final-closure-cycle-01-independent-review.json","sha256":REVIEW_SHA,"reviewed_head":REVIEWED_HEAD,"reviewer_model":"claude-fable-5","verdict":"ACCEPT","blocking_findings":0,"non_blocking_required_findings":0,"accounting_closure":"PASS"},"REVIEW_BINDING")
    require(sha(ROOT/review_binding["path"])==REVIEW_SHA,"REVIEW_SHA")
    package=load(ROOT/package_binding["path"]); review=load(ROOT/review_binding["path"])
    require(package["project_level_m1f0_closure_declared"] is False and package["final_closure_requires_separate_authority"] is True,"PREVIOUSLY_UNDECLARED")
    require(package["bound_canonical_stage_count"]==10 and len(package["canonical_graph"][1]["stage_sha256"])==19,"STAGE_COUNTS")
    require(package["canonical_graph"][9]["sha256"]==S2_SHA,"S2_IDENTITY")
    require(package["accounting_closure"]["final_ledger"]==175 and package["accounting_closure"]["hidden_checkpoint_rereads"]==0,"PACKAGE_ACCOUNTING")
    require(review["reviewed_head"]==REVIEWED_HEAD and review["closure_package_sha256"]==PACKAGE_SHA,"REVIEW_TARGET")
    require(review["reviewer_model"]=="claude-fable-5" and review["verdict"]=="ACCEPT","REVIEW_VERDICT")
    require(review["blocking_findings"]==[] and review["non_blocking_required_findings"]==[] and review["accounting_closure"]=="PASS","REVIEW_FINDINGS")
    reviewed_bytes=git("show",f"{REVIEWED_HEAD}:{package_binding['path']}")
    require(hashlib.sha256(reviewed_bytes).hexdigest()==PACKAGE_SHA,"REVIEWED_PACKAGE_SHA")
    require(git("merge-base","--is-ancestor",REVIEWED_HEAD,BASE_HEAD)==b"","REVIEW_ANCESTRY")
    require(git("merge-base","--is-ancestor",BASE_HEAD,"HEAD")==b"","BASE_ANCESTRY")
    canonical=document["canonical_authority"]
    require(canonical=={"canonical_stage_count":10,"attention_substage_count":19,"representative_s2_sha256":S2_SHA,"final_real_payload_ledger":175,"accounting_closure":"PASS","proof_reference_surface_disposition":"PRESERVED_WITH_EXPLICIT_NON_CLAIM_OF_PRODUCTION_SERIAL_F32_EQUIVALENCE","single_use_authority_disposition":"ALL_EXECUTION_CAPABLE_AUTHORITIES_CONSUMED_OR_EXPLICITLY_SUPERSEDED;NO_LEGITIMATE_REPLAY_TOKEN"},"CANONICAL_AUTHORITY")
    require(all(document["scope_proven"].values()) and len(document["scope_proven"])==14,"SCOPE_PROVEN")
    require(document["scope_limit"]=="ACCEPTED_REPRESENTATIVE_M1F0_S0_TO_S2_PROOF_REFERENCE_PATH_ONLY","SCOPE_LIMIT")
    require(not any(document["non_claims"].values()) and len(document["non_claims"])==7,"NON_CLAIMS")
    require(document["surface_non_claim"]=="Proof/reference numerical surfaces are not claimed equivalent to production serial-f32 unless separately proven.","SURFACE_NON_CLAIM")
    did=document["defense_in_depth_review_binding"]
    require(did["source_review_sha256"]==REVIEW_SHA and did["count"]==4 and [x["id"] for x in did["findings"]]==["DID-1","DID-2","DID-3","DID-4"],"DEFENSE_IN_DEPTH")
    require(all(x["disposition"].startswith("NON_BLOCKING_ACCEPTED;") for x in did["findings"]),"DEFENSE_DISPOSITION")
    audit=document["later_committed_evidence_audit"]
    require(audit=={"reviewed_head":REVIEWED_HEAD,"declaration_base_head":BASE_HEAD,"closure_package_unchanged_since_review":True,"closure_review_unchanged":True,"contradictory_later_committed_evidence":False,"result":"PASS"},"LATER_EVIDENCE_AUDIT")
    require(document["declaration_phase_accounting"]=={"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"attention_executions":0,"expert_executions":0,"shared_expert_executions":0,"aggregate_executions":0,"s1_materializations":0,"ffn_compositions":0,"s2_constructions":0},"PHASE_ACCOUNTING")
    require(current_ledger()==175,"CURRENT_LEDGER")
    require(document["new_independent_review_required"] is False and document["independent_review_authority"]==REVIEW_SHA,"REVIEW_POLICY")
    require(document["termination_condition"]=="REPRESENTATIVE_M1F0_FINAL_CLOSURE_ACCEPTED","TERMINATION")
    return {"result":"REPRESENTATIVE_M1F0_FINAL_CLOSURE_DECLARATION_VALID","canonical_stages":10,"attention_substages":19,"s2_sha256":S2_SHA,"ledger":175,"checkpoint_reads":0,"shard_opens":0,"numerical_reruns":0,"reviewer_model":"claude-fable-5","review_verdict":"ACCEPT"}

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--declaration",type=Path,default=DECLARATION); args=parser.parse_args()
    try: print(json.dumps(validate(load(args.declaration)),sort_keys=True))
    except Exception as error: print(json.dumps({"result":"REJECT","error":str(error)},sort_keys=True),file=sys.stderr); raise SystemExit(1)

#!/usr/bin/env python3
"""Retained-only validator/authorizer for the corrected oracle event."""
from __future__ import annotations
import argparse, hashlib, json, os, re, stat, sys
from pathlib import Path

SCHEMA="pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0"
HEX=re.compile(r"[0-9a-f]{64}\Z")
AUTH_KEYS={"schema","state","live","authorization_id","branch","implementation_head","contract_sha256","primary_sha256","secondary_sha256","event_coordinator_sha256","geometry_sha256","numerical_contract_sha256","synthetic_qualification_sha256","checkpoint_root","checkpoint_manifest_sha256","checkpoint_catalog_sha256","checkpoint_set_sha256","shards","prompt_token","position","top_n","attempts","retries","resume","consumers","state_root","output_root","historical_master_ledger_sha256","historical_master_terminal","historical_master_delta","oracle_event_delta","p1_authority","operator_approval_sha256"}
SAFE_ID=re.compile(r"[A-Z0-9][A-Z0-9-]{0,126}[A-Z0-9]\Z")

def strict(path):
    def hook(items):
        d={}
        for k,v in items:
            if k in d: raise ValueError(f"duplicate key {k}")
            d[k]=v
        return d
    return json.loads(path.read_text(),object_pairs_hook=hook)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_absent_root(value):
    path=Path(value)
    if not path.is_absolute() or path.exists() or path.is_symlink(): raise ValueError("unused absolute root required")
    parent=path.parent.resolve(strict=True)
    if parent!=path.parent: raise ValueError("root parent canonical")
    for item in (parent,*parent.parents):
        if item.is_symlink(): raise ValueError("root ancestry symlink")
    return path

def validate(auth, contract, repo, require_live=False):
    if set(auth)!=AUTH_KEYS or auth["schema"]!=SCHEMA: raise ValueError("authorization key/schema census")
    if auth["state"] not in {"INERT_FIXTURE","AUTHORIZED"} or bool(auth["live"])!=(auth["state"]=="AUTHORIZED"): raise ValueError("authorization state")
    if not SAFE_ID.fullmatch(auth["authorization_id"]): raise ValueError("authorization identifier")
    if require_live and not auth["live"]: raise ValueError("live authority required")
    if auth["attempts"]!=1 or auth["retries"]!=0 or auth["resume"] or auth["top_n"]!=32: raise ValueError("one-shot policy")
    if auth["branch"]!=contract["branch"] or auth["implementation_head"]!=contract["implementation_head"] or not re.fullmatch(r"[0-9a-f]{40}",auth["implementation_head"]): raise ValueError("Git authority")
    if auth["prompt_token"]!=contract["context"]["prompt_token"] or auth["position"]!=contract["context"]["position"]: raise ValueError("context authority")
    if auth["checkpoint_set_sha256"]!=contract["checkpoint_set_sha256"]: raise ValueError("checkpoint set binding")
    if auth["historical_master_ledger_sha256"]!=contract["accounting"]["historical_master_ledger_sha256"]: raise ValueError("historical ledger binding")
    if auth["p1_authority"]!="PROHIBITED" or auth["historical_master_terminal"]!=175 or auth["historical_master_delta"]!=0 or auth["oracle_event_delta"]!=2: raise ValueError("accounting/P1 boundary")
    if auth["consumers"]!=["INDEPENDENT_CPU_REFERENCE","INDEPENDENT_ACCELERATED_CROSS_CHECK"]: raise ValueError("consumer census")
    for key in ("contract_sha256","primary_sha256","secondary_sha256","event_coordinator_sha256","geometry_sha256","numerical_contract_sha256","synthetic_qualification_sha256","checkpoint_manifest_sha256","checkpoint_catalog_sha256","checkpoint_set_sha256","historical_master_ledger_sha256","operator_approval_sha256"):
        if not HEX.fullmatch(auth[key]): raise ValueError(f"hash {key}")
    for role in ("primary","primary_decoders","secondary","secondary_decoder_authority","event_coordinator","authorizer_validator","geometry","geometry_validator","numerical_contract","forward_evidence","synthetic_qualification","checkpoint_manifest","checkpoint_catalog"):
        binding=contract["bindings"][role];path=repo/binding["path"]
        if not path.is_file() or path.is_symlink() or sha(path)!=binding["sha256"]: raise ValueError(f"binding {role}")
    for group in ("secondary_decoder_dependencies","shared_immutable_codebook_data","independent_known_answer_authorities"):
        for binding in contract.get(group,[]):
            path=repo/binding["path"]
            if not path.is_file() or path.is_symlink() or sha(path)!=binding["sha256"]: raise ValueError(f"transitive binding {binding['path']}")
    if auth["contract_sha256"]!=sha(repo/"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v1.json"): raise ValueError("contract binding")
    for key,role in (("primary_sha256","primary"),("secondary_sha256","secondary"),("event_coordinator_sha256","event_coordinator"),("geometry_sha256","geometry"),("numerical_contract_sha256","numerical_contract"),("synthetic_qualification_sha256","synthetic_qualification")):
        if auth[key]!=contract["bindings"][role]["sha256"]: raise ValueError(f"authority binding {role}")
    if auth["checkpoint_manifest_sha256"]!=contract["bindings"]["checkpoint_manifest"]["sha256"] or auth["checkpoint_catalog_sha256"]!=contract["bindings"]["checkpoint_catalog"]["sha256"]: raise ValueError("checkpoint metadata binding")
    if len(auth["shards"])!=6 or auth["shards"]!=contract["shards"]: raise ValueError("shard census")
    if auth["live"]:
        if auth["operator_approval_sha256"]=="0"*64: raise ValueError("operator approval absent")
        if not Path(auth["checkpoint_root"]).is_absolute(): raise ValueError("checkpoint root absolute")
        resolved=Path(auth["checkpoint_root"]).resolve(strict=True)
        if str(resolved)!=auth["checkpoint_root"]: raise ValueError("checkpoint root canonical")
        for parent in (resolved,*resolved.parents):
            if parent.is_symlink(): raise ValueError("checkpoint ancestry symlink")
        state=safe_absent_root(auth["state_root"]);output=safe_absent_root(auth["output_root"])
        if state!=output: raise ValueError("single owned output/state root required")
    else:
        if auth["checkpoint_root"]!="INERT_NO_CHECKPOINT_PATH" or auth["state_root"]!="INERT_NO_STATE_ROOT" or auth["output_root"]!="INERT_NO_OUTPUT_ROOT": raise ValueError("inert root boundary")
    return True

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    v=sub.add_parser("validate");v.add_argument("authorization",type=Path);v.add_argument("contract",type=Path);v.add_argument("repo",type=Path);v.add_argument("--require-live",action="store_true")
    a=sub.add_parser("authorize-live");a.add_argument("inert",type=Path);a.add_argument("contract",type=Path);a.add_argument("repo",type=Path);a.add_argument("operator_approval",type=Path);a.add_argument("checkpoint_root",type=Path);a.add_argument("state_root",type=Path);a.add_argument("output",type=Path)
    x=p.parse_args()
    if x.cmd=="authorize-live": raise SystemExit("HISTORICAL_ONLY: v1 live mint is permanently retired")
    contract=strict(x.contract)
    if x.cmd=="validate": validate(strict(x.authorization),contract,x.repo.resolve(),x.require_live);print("PASS");return 0
    # Deliberately separate operator-only command; validation cannot mint.
    if os.environ.get("F017_OPERATOR_MINT_CORRECTED_ORACLE")!="I_UNDERSTAND_THIS_OPENS_THE_ORIGINAL_CHECKPOINT_ON_EXECUTION": raise SystemExit("operator mint environment missing")
    auth=strict(x.inert);validate(auth,contract,x.repo.resolve());approval=strict(x.operator_approval)
    if approval.get("decision")!="GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT" or approval.get("contract_sha256")!=auth["contract_sha256"]: raise SystemExit("operator approval mismatch")
    state_root=safe_absent_root(str(x.state_root))
    auth.update(state="AUTHORIZED",live=True,checkpoint_root=str(x.checkpoint_root.resolve(strict=True)),state_root=str(state_root),output_root=str(state_root),operator_approval_sha256=sha(x.operator_approval),implementation_head=contract["implementation_head"])
    validate(auth,contract,x.repo.resolve(),True)
    fd=os.open(x.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    data=(json.dumps(auth,sort_keys=True,separators=(",",":"))+"\n").encode()
    with os.fdopen(fd,"wb") as out: out.write(data);out.flush();os.fsync(out.fileno())
    dfd=os.open(x.output.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(dfd)
    rfd=os.open(x.output.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
    with os.fdopen(rfd,"rb") as source: observed=source.read()
    os.close(dfd)
    if observed!=data: raise SystemExit("authorization readback mismatch")
    strict(x.output)
    return 0
if __name__=="__main__": raise SystemExit(main())

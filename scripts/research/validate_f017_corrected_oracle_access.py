#!/usr/bin/env python3
"""Retained-only validator/authorizer for the corrected oracle event."""
from __future__ import annotations
import argparse, hashlib, json, os, re, stat, sys
from pathlib import Path

SCHEMA="pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0"
HEX=re.compile(r"[0-9a-f]{64}\Z")
AUTH_KEYS={"schema","state","live","authorization_id","branch","implementation_head","contract_sha256","primary_sha256","secondary_sha256","checkpoint_root","checkpoint_manifest_sha256","checkpoint_catalog_sha256","checkpoint_set_sha256","shards","prompt_token","position","top_n","attempts","retries","resume","consumers","output_root","historical_master_ledger_sha256","historical_master_terminal","historical_master_delta","oracle_event_delta","p1_authority","operator_approval_sha256"}

def strict(path):
    def hook(items):
        d={}
        for k,v in items:
            if k in d: raise ValueError(f"duplicate key {k}")
            d[k]=v
        return d
    return json.loads(path.read_text(),object_pairs_hook=hook)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def validate(auth, contract, repo, require_live=False):
    if set(auth)!=AUTH_KEYS or auth["schema"]!=SCHEMA: raise ValueError("authorization key/schema census")
    if auth["state"] not in {"INERT_FIXTURE","AUTHORIZED"} or bool(auth["live"])!=(auth["state"]=="AUTHORIZED"): raise ValueError("authorization state")
    if require_live and not auth["live"]: raise ValueError("live authority required")
    if auth["attempts"]!=1 or auth["retries"]!=0 or auth["resume"] or auth["top_n"]!=32: raise ValueError("one-shot policy")
    if auth["p1_authority"]!="PROHIBITED" or auth["historical_master_terminal"]!=175 or auth["historical_master_delta"]!=0: raise ValueError("accounting/P1 boundary")
    if auth["consumers"]!=["INDEPENDENT_CPU_REFERENCE","INDEPENDENT_ACCELERATED_CROSS_CHECK"]: raise ValueError("consumer census")
    for key in ("contract_sha256","primary_sha256","secondary_sha256","checkpoint_manifest_sha256","checkpoint_catalog_sha256","checkpoint_set_sha256","historical_master_ledger_sha256","operator_approval_sha256"):
        if not HEX.fullmatch(auth[key]): raise ValueError(f"hash {key}")
    for role in ("primary","secondary","checkpoint_manifest","checkpoint_catalog"):
        binding=contract["bindings"][role];path=repo/binding["path"]
        if not path.is_file() or sha(path)!=binding["sha256"]: raise ValueError(f"binding {role}")
    if auth["contract_sha256"]!=sha(repo/"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v1.json"): raise ValueError("contract binding")
    if auth["primary_sha256"]!=contract["bindings"]["primary"]["sha256"] or auth["secondary_sha256"]!=contract["bindings"]["secondary"]["sha256"]: raise ValueError("oracle producer binding")
    if auth["checkpoint_manifest_sha256"]!=contract["bindings"]["checkpoint_manifest"]["sha256"] or auth["checkpoint_catalog_sha256"]!=contract["bindings"]["checkpoint_catalog"]["sha256"]: raise ValueError("checkpoint metadata binding")
    if len(auth["shards"])!=6 or auth["shards"]!=contract["shards"]: raise ValueError("shard census")
    if auth["live"]:
        if not Path(auth["checkpoint_root"]).is_absolute(): raise ValueError("checkpoint root absolute")
        resolved=Path(auth["checkpoint_root"]).resolve(strict=True)
        if str(resolved)!=auth["checkpoint_root"]: raise ValueError("checkpoint root canonical")
        for parent in (resolved,*resolved.parents):
            if parent.is_symlink(): raise ValueError("checkpoint ancestry symlink")
    return True

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    v=sub.add_parser("validate");v.add_argument("authorization",type=Path);v.add_argument("contract",type=Path);v.add_argument("repo",type=Path);v.add_argument("--require-live",action="store_true")
    a=sub.add_parser("authorize-live");a.add_argument("inert",type=Path);a.add_argument("contract",type=Path);a.add_argument("repo",type=Path);a.add_argument("operator_approval",type=Path);a.add_argument("checkpoint_root",type=Path);a.add_argument("output",type=Path)
    x=p.parse_args();contract=strict(x.contract)
    if x.cmd=="validate": validate(strict(x.authorization),contract,x.repo.resolve(),x.require_live);print("PASS");return 0
    # Deliberately separate operator-only command; validation cannot mint.
    if os.environ.get("F017_OPERATOR_MINT_CORRECTED_ORACLE")!="I_UNDERSTAND_THIS_OPENS_THE_ORIGINAL_CHECKPOINT_ON_EXECUTION": raise SystemExit("operator mint environment missing")
    auth=strict(x.inert);validate(auth,contract,x.repo.resolve());approval=strict(x.operator_approval)
    if approval.get("decision")!="GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT" or approval.get("contract_sha256")!=auth["contract_sha256"]: raise SystemExit("operator approval mismatch")
    auth.update(state="AUTHORIZED",live=True,checkpoint_root=str(x.checkpoint_root.resolve(strict=True)),operator_approval_sha256=sha(x.operator_approval))
    validate(auth,contract,x.repo.resolve(),True)
    fd=os.open(x.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,"wb") as out: out.write((json.dumps(auth,sort_keys=True,separators=(",",":"))+"\n").encode());out.flush();os.fsync(out.fileno())
    return 0
if __name__=="__main__": raise SystemExit(main())

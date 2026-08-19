#!/usr/bin/env python3
"""Fail-closed interrupted-attempt adjudicator; never resumes computation."""
from __future__ import annotations
import argparse, hashlib, json, os, tempfile
from pathlib import Path

def sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(path: Path, obj: dict):
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".terminal-")
    with os.fdopen(fd,"w") as f: json.dump(obj,f,sort_keys=True,separators=(",",":")); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path); d=os.open(path.parent,os.O_RDONLY); os.fsync(d); os.close(d)
def reconcile(state: Path, output: Path) -> dict:
    if not state.exists(): return {"result":"NOT_STARTED","ledger":175,"resume":False}
    start=state/"attempt-start.json"; terminal=state/"terminal.json"
    if not start.is_file(): raise RuntimeError("ACCOUNTING_INTEGRITY_NO_DURABLE_START")
    if terminal.is_file(): return json.loads(terminal.read_text())
    artifacts=[]
    if output.exists():
        for p in sorted(output.glob("expert-*.f32le")):
            artifacts.append({"name":p.name,"bytes":p.stat().st_size,"sha256":sha(p),"authority":False})
    result={"status":"TERMINAL_INTERRUPTED","ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"resume":False,"retry":False,"second_attempt":False,"partial_outputs":artifacts,"output_authority":"NONE_UNLESS_PRIOR_COMPLETE_TERMINAL"}
    atomic(terminal,result); return result
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--state-root",type=Path,required=True); ap.add_argument("--output-root",type=Path,required=True); a=ap.parse_args(); print(json.dumps(reconcile(a.state_root,a.output_root),sort_keys=True))
if __name__ == "__main__": main()

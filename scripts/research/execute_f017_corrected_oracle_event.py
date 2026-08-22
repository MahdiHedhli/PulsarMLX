#!/usr/bin/env python3
"""One-shot coordinator for the separately authorized corrected oracle event."""
from __future__ import annotations
import argparse,hashlib,json,os,platform,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def strict(path):
 def hook(items):
  d={}
  for k,v in items:
   if k in d: raise ValueError("duplicate JSON key")
   d[k]=v
  return d
 return json.loads(path.read_text(),object_pairs_hook=hook)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def bank(path,value):
 data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode();fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
 with os.fdopen(fd,"wb") as out: out.write(data);out.flush();os.fsync(out.fileno())
 dfd=os.open(path.parent,os.O_RDONLY);os.fsync(dfd);os.close(dfd)
 observed=path.read_bytes()
 if observed!=data: raise ValueError("exact readback mismatch")
 json.loads(observed);return hashlib.sha256(observed).hexdigest()
def memory_available():
 text=subprocess.run(["/usr/bin/vm_stat"],check=True,text=True,capture_output=True).stdout;page=int(text.splitlines()[0].split()[-1].rstrip("."));rows={}
 for line in text.splitlines()[1:]:
  if ":" in line: rows[line.split(":",1)[0]]=int(line.split(":",1)[1].strip().rstrip("."))*page
 return sum(rows.get(k,0) for k in ("Pages free","Pages inactive","Pages speculative","Pages purgeable"))
def main():
 p=argparse.ArgumentParser();p.add_argument("authorization",type=Path);p.add_argument("contract",type=Path);p.add_argument("catalog",type=Path);p.add_argument("checkpoint_root",type=Path);p.add_argument("geometry",type=Path);p.add_argument("state_root",type=Path);a=p.parse_args()
 subprocess.run([sys.executable,str(ROOT/"scripts/research/validate_f017_corrected_oracle_access.py"),"validate",str(a.authorization),str(a.contract),str(ROOT),"--require-live"],check=True)
 auth=strict(a.authorization);contract=strict(a.contract)
 brand=subprocess.run(["/usr/sbin/sysctl","-n","machdep.cpu.brand_string"],check=True,text=True,capture_output=True).stdout.rstrip("\r\n")
 if brand!="Apple M1 Ultra" or platform.machine()!="arm64" or memory_available()<contract["memory"]["minimum_free_bytes"]: raise SystemExit("machine/memory preflight")
 root=a.state_root.resolve(strict=False)
 if root.exists() or not root.is_absolute(): raise SystemExit("unused absolute state root required")
 root.mkdir(mode=0o700,parents=False);claim={"schema":"pulsarmlx.f017.corrected-oracle-owned-claim/1.0.0","authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"started_ns":time.time_ns(),"attempts":1,"retries":0,"resume":False}
 claim_sha=bank(root/"claim.json",claim);start_sha=bank(root/"durable-start.json",claim)
 geometry=strict(a.geometry);primary=root/"primary-result.json";secondary=root/"secondary-result.json"
 runs=[("primary",ROOT/"scripts/research/f017_corrected_oracle_primary.py",primary),("secondary",ROOT/"scripts/research/f017_corrected_oracle_secondary.py",secondary)]
 result_state="ORACLE_EXECUTION_FAILURE";error=None
 try:
  for consumer,script,output in runs:
   env=os.environ.copy();env["F017_ORACLE_ACCESS_EVENT_DIR"]=str(root/f"{consumer}-access-events")
   command=[sys.executable,str(script),"target",str(a.authorization),str(a.catalog),str(a.checkpoint_root),str(a.geometry),str(output)]
   subprocess.run(command,cwd=ROOT,env=env,check=True)
  first,second=strict(primary),strict(secondary)
  structural=all(x["selected_expert_ids"]==y["selected_expert_ids"] for x,y in zip(first["layers"],second["layers"],strict=True))
  thresholds=contract["bindings"]["synthetic_qualification"]
  qualification=strict(ROOT/thresholds["path"]);bound=qualification["frozen_thresholds"]
  diffs=[abs(float(x)-float(y)) for x,y in zip(first["full_logits"],second["full_logits"],strict=True)];max_abs=max(diffs)
  same_top=first["selected_token"]==second["selected_token"]
  uncertainty=bound["max_abs"]
  if not structural or max_abs>uncertainty: result_state="ORACLE_DISAGREEMENT"
  elif same_top and min(first["top_1_margin"],second["top_1_margin"])>2*uncertainty: result_state="EXACT_EXPECTED_TOKEN_STABLE"
  elif [x["token_id"] for x in first["top"]]==[x["token_id"] for x in second["top"]]: result_state="NUMERICALLY_STABLE_TOP_K_ONLY"
  else: result_state="TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"
 except Exception as exc: error=f"{type(exc).__name__}:{exc}"
 receipt={"schema":"pulsarmlx.f017.corrected-oracle-event-receipt/1.0.0","authorization_id":auth["authorization_id"],"claim_sha256":claim_sha,"start_sha256":start_sha,"primary_result_sha256":sha(primary) if primary.is_file() else None,"secondary_result_sha256":sha(secondary) if secondary.is_file() else None,"primary_access_event_count":len(list((root/"primary-access-events").glob("*.json"))) if (root/"primary-access-events").is_dir() else 0,"secondary_access_event_count":len(list((root/"secondary-access-events").glob("*.json"))) if (root/"secondary-access-events").is_dir() else 0,"classification":result_state,"error":error,"historical_master_before":175,"historical_master_after":175,"historical_master_delta":0,"oracle_event_delta":2,"completed_ns":time.time_ns()}
 receipt_sha=bank(root/"receipt.json",receipt);terminal={"schema":"pulsarmlx.f017.corrected-oracle-terminal/1.0.0","authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"receipt_sha256":receipt_sha,"classification":result_state,"retry_permitted":False,"resume_permitted":False,"terminal_ns":time.time_ns()};bank(root/"terminal.json",terminal)
 return 0 if result_state!="ORACLE_EXECUTION_FAILURE" else 2
if __name__=="__main__": raise SystemExit(main())

#!/usr/bin/env python3
"""One-shot coordinator for a future corrected full-checkpoint oracle event."""
from __future__ import annotations
import argparse,hashlib,json,math,os,platform,stat,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def _pairs(items):
 out={}
 for key,value in items:
  if key in out: raise ValueError(f"duplicate JSON key: {key}")
  out[key]=value
 return out
def strict(path): return json.loads(path.read_text(),object_pairs_hook=_pairs)
def sha(path):
 digest=hashlib.sha256()
 with path.open("rb",buffering=0) as source:
  while chunk:=source.read(8*1024*1024): digest.update(chunk)
 return digest.hexdigest()
def bank(path,value):
 data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode();fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
 with os.fdopen(fd,"wb") as output: output.write(data);output.flush();os.fsync(output.fileno())
 dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(dfd);rfd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
 with os.fdopen(rfd,"rb") as source: observed=source.read()
 os.close(dfd)
 if observed!=data: raise ValueError("exact descriptor-relative readback mismatch")
 json.loads(observed,object_pairs_hook=_pairs)
 return hashlib.sha256(observed).hexdigest()
def memory_available():
 text=subprocess.run(["/usr/bin/vm_stat"],check=True,text=True,capture_output=True).stdout;page=int(text.splitlines()[0].split()[-1].rstrip("."));rows={}
 for line in text.splitlines()[1:]:
  if ":" in line: rows[line.split(":",1)[0]]=int(line.split(":",1)[1].strip().rstrip("."))*page
 return sum(rows.get(key,0) for key in ("Pages free","Pages inactive","Pages speculative","Pages purgeable"))
def bank_event(directory,sequence,auth,kind,authority,result,size=0,digest=None):
 bank(directory/f"{sequence:08}.json",{"schema":"pulsarmlx.f017.corrected-oracle-checkpoint-identity-event/1.0.0","sequence":sequence,"authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"kind":kind,"authority_id":authority,"result":result,"size_bytes":size,"sha256":digest,"timestamp_ns":time.time_ns()})
def verify_checkpoint_identity(checkpoint_root,auth,root):
 event_root=root/"checkpoint-identity-events";event_root.mkdir(mode=0o700);sequence=0;observed=[]
 for expected in auth["shards"]:
  name=expected["filename"];bank_event(event_root,sequence,auth,"SHARD_IDENTITY_OPEN_ATTEMPT",name,"STARTED_READ_ONLY_NOFOLLOW");sequence+=1;descriptor=None
  try:
   descriptor=os.open(checkpoint_root/name,os.O_RDONLY|os.O_NOFOLLOW);info=os.fstat(descriptor)
   if not stat.S_ISREG(info.st_mode) or info.st_size!=expected["size_bytes"]: raise ValueError("shard file/size identity")
   bank_event(event_root,sequence,auth,"SHARD_IDENTITY_OPEN_RESULT",name,"PASS",info.st_size);sequence+=1
   digest=hashlib.sha256();total=0;bank_event(event_root,sequence,auth,"SHARD_IDENTITY_HASH_ATTEMPT",name,"STARTED",info.st_size);sequence+=1
   while total<info.st_size:
    chunk=os.pread(descriptor,min(8*1024*1024,info.st_size-total),total)
    if not chunk: raise ValueError("short shard identity read")
    digest.update(chunk);total+=len(chunk)
   actual=digest.hexdigest()
   if actual!=expected["sha256"]: raise ValueError("shard SHA mismatch")
   bank_event(event_root,sequence,auth,"SHARD_IDENTITY_HASH_RESULT",name,"PASS",total,actual);sequence+=1;observed.append({"filename":name,"size_bytes":total,"sha256":actual})
  except Exception as exc:
   bank_event(event_root,sequence,auth,"SHARD_IDENTITY_FAILURE",name,f"FAIL_{type(exc).__name__}");sequence+=1;raise
  finally:
   if descriptor is not None: os.close(descriptor);bank_event(event_root,sequence,auth,"SHARD_IDENTITY_CLOSE",name,"PASS");sequence+=1
 return bank(root/"checkpoint-identity.json",{"schema":"pulsarmlx.f017.corrected-oracle-checkpoint-identity/1.0.0","authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"shards":observed,"event_count":sequence,"result":"PASS"})
def access_census(root,auth,catalog):
 expected={item["name"] for item in strict(catalog)["tensors"]};consumers={};expected_shards={item["filename"] for item in auth["shards"]}
 for directory,consumer in (("primary-access-events","INDEPENDENT_CPU_REFERENCE"),("secondary-access-events","INDEPENDENT_ACCELERATED_CROSS_CHECK")):
  events=[strict(path) for path in sorted((root/directory).glob("*.json"))]
  if [event["sequence"] for event in events]!=list(range(len(events))): raise ValueError("access sequence discontinuity")
  if any(event["authorization_id"]!=auth["authorization_id"] or event["consumer"]!=consumer for event in events): raise ValueError("access authority mismatch")
  resolved={event["tensor_name"] for event in events if event["kind"]=="TENSOR_RESOLUTION"};opened={event["authority_id"] for event in events if event["kind"]=="SHARD_OPEN_RESULT" and event["result"]=="PASS_READ_ONLY_NOFOLLOW"}
  if resolved!=expected or opened!=expected_shards: raise ValueError(f"access census mismatch {consumer}")
  if any(str(event["result"]).startswith(("FAIL","REJECT")) for event in events): raise ValueError("failed access event")
  consumers[consumer]={"event_count":len(events),"resolved_tensor_count":len(resolved),"opened_shard_count":len(opened),"first_use_count":sum(event["kind"]=="TENSOR_FIRST_USE" for event in events),"repeat_use_count":sum((event.get("repeat_count") or 0) for event in events if event["kind"]=="TENSOR_REUSE_SUMMARY")}
 return {"schema":"pulsarmlx.f017.corrected-oracle-access-census/1.0.0","authorization_id":auth["authorization_id"],"catalog_tensor_count":len(expected),"consumers":consumers,"unexpected_access_count":0,"fallback_attempt_count":0,"alternate_root_attempt_count":0,"result":"PASS"}
def metrics(primary,secondary):
 left=[float(value) for value in primary["full_logits"]];right=[float(value) for value in secondary["full_logits"]]
 if len(left)!=len(right): raise ValueError("logit geometry")
 differences=[abs(a-b) for a,b in zip(left,right,strict=True)];rmse=math.sqrt(sum(value*value for value in differences)/len(differences));dot=sum(a*b for a,b in zip(left,right,strict=True));norm=math.sqrt(sum(a*a for a in left)*sum(b*b for b in right))
 return {"max_abs":max(differences),"rmse":rmse,"cosine_similarity":dot/norm if norm else 1.0}
def main():
 parser=argparse.ArgumentParser();parser.add_argument("authorization",type=Path);parser.add_argument("contract",type=Path);parser.add_argument("catalog",type=Path);parser.add_argument("checkpoint_root",type=Path);parser.add_argument("geometry",type=Path);parser.add_argument("state_root",type=Path);args=parser.parse_args()
 subprocess.run([sys.executable,str(ROOT/"scripts/research/validate_f017_corrected_oracle_access.py"),"validate",str(args.authorization),str(args.contract),str(ROOT),"--require-live"],check=True)
 auth=strict(args.authorization);contract=strict(args.contract)
 for supplied,role in ((args.catalog,"checkpoint_catalog"),(args.geometry,"geometry")):
  expected=(ROOT/contract["bindings"][role]["path"]).resolve(strict=True)
  if supplied.resolve(strict=True)!=expected or sha(expected)!=contract["bindings"][role]["sha256"]: raise SystemExit(f"{role} authority mismatch")
 if args.checkpoint_root.resolve(strict=True)!=Path(auth["checkpoint_root"]): raise SystemExit("checkpoint root mismatch")
 if args.state_root!=Path(auth["state_root"]) or args.state_root!=Path(auth["output_root"]): raise SystemExit("state/output root mismatch")
 brand=subprocess.run(["/usr/sbin/sysctl","-n","machdep.cpu.brand_string"],check=True,text=True,capture_output=True).stdout.rstrip("\r\n")
 if brand!="Apple M1 Ultra" or platform.machine()!="arm64" or memory_available()<contract["memory"]["minimum_free_bytes"]: raise SystemExit("machine/memory preflight")
 root=args.state_root
 if root.exists() or not root.is_absolute(): raise SystemExit("unused absolute state root required")
 root.mkdir(mode=0o700,parents=False);claim={"schema":"pulsarmlx.f017.corrected-oracle-owned-claim/1.0.0","authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"started_ns":time.time_ns(),"attempts":1,"retries":0,"resume":False}
 claim_sha=bank(root/"claim.json",claim);start_sha=bank(root/"durable-start.json",claim);result_state="ORACLE_EXECUTION_FAILURE";error=None;identity_sha=census_sha=None;primary=root/"primary-result.json";secondary=root/"secondary-result.json"
 try:
  identity_sha=verify_checkpoint_identity(args.checkpoint_root,auth,root)
  for consumer,script,output in (("primary",ROOT/"scripts/research/f017_corrected_oracle_primary.py",primary),("secondary",ROOT/"scripts/research/f017_corrected_oracle_secondary.py",secondary)):
   env=os.environ.copy();env["F017_ORACLE_ACCESS_EVENT_DIR"]=str(root/f"{consumer}-access-events");env["F017_ORACLE_CHECKPOINT_IDENTITY"]=str(root/"checkpoint-identity.json")
   subprocess.run([sys.executable,str(script),"target",str(args.authorization),str(args.catalog),str(args.checkpoint_root),str(args.geometry),str(output)],cwd=ROOT,env=env,check=True)
  census_sha=bank(root/"access-census.json",access_census(root,auth,args.catalog));first,second=strict(primary),strict(secondary);observed=metrics(first,second)
  structural=all(a["selected_expert_ids"]==b["selected_expert_ids"] for a,b in zip(first["layers"],second["layers"],strict=True));qualification=strict(ROOT/contract["bindings"]["synthetic_qualification"]["path"]);bound=qualification["frozen_thresholds"]
  within=observed["max_abs"]<=bound["max_abs"] and observed["rmse"]<=bound["rmse"] and observed["cosine_similarity"]>=bound["cosine_min"];same_top=first["selected_token"]==second["selected_token"];same_order=[item["token_id"] for item in first["top"]]==[item["token_id"] for item in second["top"]];uncertainty=bound["max_abs"]
  if not structural or not within: result_state="ORACLE_DISAGREEMENT"
  elif same_top and min(first["top_1_margin"],second["top_1_margin"])>2*uncertainty: result_state="EXACT_EXPECTED_TOKEN_STABLE"
  elif same_order: result_state="NUMERICALLY_STABLE_TOP_K_ONLY"
  else: result_state="TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"
  bank(root/"comparison.json",{"schema":"pulsarmlx.f017.corrected-oracle-comparison/1.0.0","metrics":observed,"frozen_thresholds":bound,"route_structure_exact":structural,"same_top_token":same_top,"same_top_n_order":same_order,"classification":result_state})
 except Exception as exc: error=f"{type(exc).__name__}:{exc}"
 receipt={"schema":"pulsarmlx.f017.corrected-oracle-event-receipt/2.0.0","authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"claim_sha256":claim_sha,"start_sha256":start_sha,"checkpoint_identity_sha256":identity_sha,"access_census_sha256":census_sha,"primary_result_sha256":sha(primary) if primary.is_file() else None,"secondary_result_sha256":sha(secondary) if secondary.is_file() else None,"classification":result_state,"error":error,"historical_master_before":175,"historical_master_after":175,"historical_master_delta":0,"oracle_event_delta":2,"completed_ns":time.time_ns()}
 receipt_sha=bank(root/"receipt.json",receipt);event_sha=bank(root/"oracle-event-ledger-entry.json",{"schema":"pulsarmlx.f017.corrected-oracle-event-ledger-entry/1.0.0","authorization_id":auth["authorization_id"],"delta":2,"receipt_sha256":receipt_sha,"historical_master_terminal":175})
 bank(root/"terminal.json",{"schema":"pulsarmlx.f017.corrected-oracle-terminal/2.0.0","authorization_id":auth["authorization_id"],"owner_pid":os.getpid(),"receipt_sha256":receipt_sha,"event_entry_sha256":event_sha,"classification":result_state,"retry_permitted":False,"resume_permitted":False,"terminal_ns":time.time_ns()})
 return 0 if result_state!="ORACLE_EXECUTION_FAILURE" else 2
if __name__=="__main__": raise SystemExit(main())

#!/usr/bin/env python3
"""Validator and future operator-only authorizer for corrected-oracle v2."""
from __future__ import annotations
import argparse,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path

SCHEMA="pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/2.0.0"
PREFLIGHT_SCHEMA="pulsarmlx.f017.corrected-oracle-memory-preflight/2.0.0"
HEX=re.compile(r"[0-9a-f]{64}\Z")
SAFE_ID=re.compile(r"[A-Z0-9][A-Z0-9-]{0,126}[A-Z0-9]\Z")
AUTH_KEYS={"schema","state","live","authorization_id","branch","implementation_head","contract_sha256","primary_sha256","secondary_sha256","event_coordinator_sha256","memory_observer_sha256","memory_parser_contract_sha256","geometry_sha256","numerical_contract_sha256","synthetic_qualification_sha256","checkpoint_root","checkpoint_manifest_sha256","checkpoint_catalog_sha256","checkpoint_set_sha256","shards","prompt_token","position","top_n","attempts","retries","resume","consumers","state_root","output_root","historical_master_ledger_sha256","historical_master_terminal","historical_master_delta","oracle_event_delta","p1_authority","operator_approval_sha256","memory_preflight_sha256","memory_observed_at_unix_ns","memory_available_bytes"}
CONTRACT_RELATIVE=Path("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v2.json")

def strict(path):
 def hook(items):
  value={}
  for key,item in items:
   if key in value: raise ValueError(f"duplicate key {key}")
   value[key]=item
  return value
 return json.loads(path.read_text(),object_pairs_hook=hook)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def exact_contract(path,repo):
 expected=(repo/CONTRACT_RELATIVE).absolute()
 supplied=(path if path.is_absolute() else repo/path).absolute()
 if supplied!=expected or any(item.is_symlink() for item in (supplied,*supplied.parents)):
  raise ValueError("canonical scientific contract path required")
 canonical=supplied.resolve(strict=True)
 return canonical,strict(canonical)
def safe_absent_root(value):
 path=Path(value)
 if not path.is_absolute() or path.exists() or path.is_symlink(): raise ValueError("unused absolute root required")
 parent=path.parent.resolve(strict=True)
 if parent!=path.parent: raise ValueError("root parent canonical")
 for item in (parent,*parent.parents):
  if item.is_symlink(): raise ValueError("root ancestry symlink")
 return path

def validate(auth,contract,repo,require_live=False):
 if set(auth)!=AUTH_KEYS or auth["schema"]!=SCHEMA: raise ValueError("authorization key/schema census")
 if contract.get("schema")!="pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/2.0.0": raise ValueError("scientific contract generation")
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
 for key in ("contract_sha256","primary_sha256","secondary_sha256","event_coordinator_sha256","memory_observer_sha256","memory_parser_contract_sha256","geometry_sha256","numerical_contract_sha256","synthetic_qualification_sha256","checkpoint_manifest_sha256","checkpoint_catalog_sha256","checkpoint_set_sha256","historical_master_ledger_sha256","operator_approval_sha256","memory_preflight_sha256"):
  if not HEX.fullmatch(auth[key]): raise ValueError(f"hash {key}")
 for role in ("primary","primary_decoders","secondary","secondary_decoder_authority","event_coordinator","authorizer_validator","memory_observer","memory_parser_contract","geometry","geometry_validator","numerical_contract","forward_evidence","synthetic_qualification","checkpoint_manifest","checkpoint_catalog"):
  binding=contract["bindings"][role];path=repo/binding["path"]
  if not path.is_file() or path.is_symlink() or sha(path)!=binding["sha256"]: raise ValueError(f"binding {role}")
 for group in ("secondary_decoder_dependencies","shared_immutable_codebook_data","independent_known_answer_authorities"):
  for binding in contract.get(group,[]):
   path=repo/binding["path"]
   if not path.is_file() or path.is_symlink() or sha(path)!=binding["sha256"]: raise ValueError(f"transitive binding {binding['path']}")
 contract_path=repo/CONTRACT_RELATIVE
 if auth["contract_sha256"]!=sha(contract_path): raise ValueError("contract binding")
 for key,role in (("primary_sha256","primary"),("secondary_sha256","secondary"),("event_coordinator_sha256","event_coordinator"),("memory_observer_sha256","memory_observer"),("memory_parser_contract_sha256","memory_parser_contract"),("geometry_sha256","geometry"),("numerical_contract_sha256","numerical_contract"),("synthetic_qualification_sha256","synthetic_qualification")):
  if auth[key]!=contract["bindings"][role]["sha256"]: raise ValueError(f"authority binding {role}")
 if auth["checkpoint_manifest_sha256"]!=contract["bindings"]["checkpoint_manifest"]["sha256"] or auth["checkpoint_catalog_sha256"]!=contract["bindings"]["checkpoint_catalog"]["sha256"]: raise ValueError("checkpoint metadata binding")
 if len(auth["shards"])!=6 or auth["shards"]!=contract["shards"]: raise ValueError("shard census")
 if auth["live"]:
  if auth["operator_approval_sha256"]=="0"*64 or auth["memory_preflight_sha256"]=="0"*64: raise ValueError("operator/preflight authority absent")
  if type(auth["memory_observed_at_unix_ns"]) is not int or type(auth["memory_available_bytes"]) is not int or auth["memory_available_bytes"]<contract["memory_preflight"]["minimum_free_bytes"]: raise ValueError("memory authority")
  resolved=Path(auth["checkpoint_root"]).resolve(strict=True)
  if str(resolved)!=auth["checkpoint_root"]: raise ValueError("checkpoint root canonical")
  for parent in (resolved,*resolved.parents):
   if parent.is_symlink(): raise ValueError("checkpoint ancestry symlink")
  state=safe_absent_root(auth["state_root"]);output=safe_absent_root(auth["output_root"])
  if state!=output: raise ValueError("single owned output/state root required")
 else:
  if auth["checkpoint_root"]!="INERT_NO_CHECKPOINT_PATH" or auth["state_root"]!="INERT_NO_STATE_ROOT" or auth["output_root"]!="INERT_NO_OUTPUT_ROOT": raise ValueError("inert root boundary")
  if auth["memory_preflight_sha256"]!="0"*64 or auth["memory_observed_at_unix_ns"]!=0 or auth["memory_available_bytes"]!=0: raise ValueError("inert memory boundary")
 return True

def collect_preflight(contract_path,output,contract,repo):
 if output.exists() or output.is_symlink(): raise ValueError("unused preflight output required")
 coordinator=(repo/contract["bindings"]["event_coordinator"]["path"]).resolve(strict=True)
 subprocess.run(
  [sys.executable,str(coordinator),"preflight",str(contract_path),str(output)],
  cwd=repo,
  stdin=subprocess.DEVNULL,
  stdout=subprocess.PIPE,
  stderr=subprocess.PIPE,
  timeout=30,
  check=True,
  shell=False,
 )
 if not output.is_file() or output.is_symlink(): raise ValueError("coordinator preflight report absent")
 report=strict(output);validate_preflight(report,contract,repo)
 return report

def validate_preflight(report,contract,repo):
 expected={"schema","result","branch","implementation_head","git_head","local_remote_parity","worktree_clean","contract_sha256","coordinator_sha256","memory_observer_sha256","machine_brand","architecture","minimum_free_bytes","observation","state_created","authorization_created","checkpoint_shard_opens","checkpoint_payload_reads"}
 if set(report)!=expected or report["schema"]!=PREFLIGHT_SCHEMA or report["result"]!="PASS": raise ValueError("preflight schema/result")
 if report["contract_sha256"]!=sha(repo/"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v2.json"): raise ValueError("preflight contract")
 if report["coordinator_sha256"]!=contract["bindings"]["event_coordinator"]["sha256"] or report["memory_observer_sha256"]!=contract["bindings"]["memory_observer"]["sha256"]: raise ValueError("preflight implementation")
 if report["machine_brand"]!="Apple M1 Ultra" or report["architecture"]!="arm64": raise ValueError("preflight machine")
 if report["branch"]!=contract["branch"] or report["implementation_head"]!=contract["implementation_head"] or report["local_remote_parity"] is not True or report["worktree_clean"] is not True or not re.fullmatch(r"[0-9a-f]{40}",report["git_head"]): raise ValueError("preflight Git authority")
 if report["state_created"] or report["authorization_created"] or report["checkpoint_shard_opens"]!=0 or report["checkpoint_payload_reads"]!=0: raise ValueError("preflight side effect")
 observed=report["observation"];observation_keys={"parser_version","page_size_bytes","pages_free","pages_inactive","pages_speculative","pages_purgeable","available_bytes","canonical_observation","stdout_sha256","observed_at_unix_ns"}
 if set(observed)!=observation_keys or observed["parser_version"]!="F017_MACOS_VM_STAT_V1" or not HEX.fullmatch(observed["stdout_sha256"]): raise ValueError("preflight observation census")
 numeric=("page_size_bytes","pages_free","pages_inactive","pages_speculative","pages_purgeable","available_bytes","observed_at_unix_ns")
 if any(type(observed[key]) is not int for key in numeric) or observed["page_size_bytes"]<=0 or any(observed[key]<0 for key in numeric[1:6]): raise ValueError("preflight observation types")
 calculated=observed["page_size_bytes"]*sum(observed[key] for key in ("pages_free","pages_inactive","pages_speculative","pages_purgeable"))
 if observed["available_bytes"]!=calculated or report["minimum_free_bytes"]!=contract["memory_preflight"]["minimum_free_bytes"]: raise ValueError("preflight formula")
 timestamp=observed["observed_at_unix_ns"];available=observed["available_bytes"]
 if available<contract["memory_preflight"]["minimum_free_bytes"]: raise ValueError("preflight memory")
 age=time.time_ns()-timestamp
 if age<0 or age>contract["memory_preflight"]["sample_freshness_seconds"]*1_000_000_000: raise ValueError("preflight sample stale")
 return timestamp,available

def main():
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="cmd",required=True)
 check=sub.add_parser("validate");check.add_argument("authorization",type=Path);check.add_argument("contract",type=Path);check.add_argument("repo",type=Path);check.add_argument("--require-live",action="store_true")
 mint=sub.add_parser("authorize-live");mint.add_argument("inert",type=Path);mint.add_argument("contract",type=Path);mint.add_argument("repo",type=Path);mint.add_argument("operator_approval",type=Path);mint.add_argument("preflight_report",type=Path);mint.add_argument("checkpoint_root",type=Path);mint.add_argument("state_root",type=Path);mint.add_argument("output",type=Path)
 args=parser.parse_args();repo=args.repo.resolve();contract_path,contract=exact_contract(args.contract,repo)
 if args.cmd=="validate": validate(strict(args.authorization),contract,repo,args.require_live);print("PASS");return 0
 if os.environ.get("F017_OPERATOR_MINT_CORRECTED_ORACLE_V2")!="I_UNDERSTAND_THIS_OPENS_THE_ORIGINAL_CHECKPOINT_ON_EXECUTION": raise SystemExit("operator mint environment missing")
 auth=strict(args.inert);validate(auth,contract,repo);approval=strict(args.operator_approval)
 if approval.get("decision")!="GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_V2" or approval.get("contract_sha256")!=auth["contract_sha256"]: raise SystemExit("operator approval mismatch")
 preflight=collect_preflight(contract_path,args.preflight_report,contract,repo)
 observed_at,available=validate_preflight(preflight,contract,repo);state_root=safe_absent_root(str(args.state_root))
 auth.update(state="AUTHORIZED",live=True,checkpoint_root=str(args.checkpoint_root.resolve(strict=True)),state_root=str(state_root),output_root=str(state_root),operator_approval_sha256=sha(args.operator_approval),memory_preflight_sha256=sha(args.preflight_report),memory_observed_at_unix_ns=observed_at,memory_available_bytes=available)
 validate(auth,contract,repo,True)
 fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400);data=(json.dumps(auth,sort_keys=True,separators=(",",":"))+"\n").encode()
 with os.fdopen(fd,"wb") as out: out.write(data);out.flush();os.fsync(out.fileno())
 dfd=os.open(args.output.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(dfd);rfd=os.open(args.output.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
 with os.fdopen(rfd,"rb") as source: observed=source.read()
 os.close(dfd)
 if observed!=data: raise SystemExit("authorization readback mismatch")
 strict(args.output);return 0
if __name__=="__main__": raise SystemExit(main())

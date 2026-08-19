#!/usr/bin/env python3
"""Release wrapper for one retained-only representative expert recovery."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from f017_representative_expert_ledger_adapter_v1 import current_ledger

ROOT=Path(__file__).resolve().parents[2]
AUTH=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-recovery-authorization-v1.json"
EXECUTOR=ROOT/"scripts/research/f017_representative_expert_recovery_executor_v1.py"
VALIDATOR=ROOT/"scripts/research/validate_f017_representative_expert_recovery_single_use_release_v1.py"
ENV={"expert_input":"PULSARMLX_F017_REP_EXPERT_INPUT","packed_root":"PULSARMLX_F017_REP_EXPERT_PACKED_ROOT","decoder":"PULSARMLX_F017_REP_EXPERT_DECODER_BINARY","state":"PULSARMLX_F017_REP_EXPERT_STATE_ROOT","output":"PULSARMLX_F017_REP_EXPERT_OUTPUT_ROOT","approval":"PULSARMLX_F017_REP_EXPERT_RELEASE_APPROVAL"}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text(),object_pairs_hook=lambda x:_unique(x))
def _unique(pairs):
    d={}
    for k,v in pairs:
        if k in d: raise RuntimeError("DUPLICATE_KEY")
        d[k]=v
    return d
def paths():
    out={}
    for k,e in ENV.items():
        if not os.environ.get(e): raise RuntimeError("UNRESOLVED_ENV:"+e)
        out[k]=Path(os.environ[e])
    return out
def require_environment():
    if sys.version_info[:3] != (3,14,6): raise RuntimeError("ENVIRONMENT_CPYTHON")
    import numpy as np
    if np.__version__ != "2.4.5": raise RuntimeError("ENVIRONMENT_NUMPY")
    if sys.byteorder != "little": raise RuntimeError("ENVIRONMENT_ENDIANNESS")
    for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","VECLIB_MAXIMUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        if os.environ.get(name) != "1": raise RuntimeError("ENVIRONMENT_THREADS:"+name)
def preflight(release: Path):
    if current_ledger()!=175: raise RuntimeError("LEDGER")
    require_environment()
    subprocess.run([sys.executable,str(VALIDATOR),"--release",str(release)],check=True,capture_output=True,text=True)
    p=paths(); state,output=p["state"],p["output"]
    if state.exists() or output.exists(): raise RuntimeError("PRIOR_ATTEMPT")
    for parent in (state.parent,output.parent):
        if not parent.is_dir() or not os.access(parent,os.W_OK): raise RuntimeError("DESTINATION")
        if shutil.disk_usage(parent).free < 3221225472: raise RuntimeError("STORAGE")
    cmd=[sys.executable,str(EXECUTOR),"--authorization",str(AUTH),"--expert-input",str(p["expert_input"]),"--packed-root",str(p["packed_root"]),"--decoder-binary",str(p["decoder"]),"--preflight-only"]
    result=subprocess.run(cmd,check=True,capture_output=True,text=True)
    return p,result.stdout.strip()
def authorize(release: Path, token: Path, approval: Path):
    r,t,a=load(release),load(token),load(approval)
    expected={"approval_sha256":sha(approval),"attempt_id":r["attempt_id"],"authorization_sha256":sha(AUTH),"disposition":"GO_EXECUTE_ONCE_NO_RETRY","event_id":r["event_id"],"real_event_authorized":True,"release_id":r["release_id"],"release_sha256":sha(release)}
    if t!=expected or a.get("verdict")!="ACCEPT" or a.get("release_sha256")!=sha(release) or a.get("release_id")!=r["release_id"]: raise RuntimeError("INDEPENDENT_RELEASE_GATE")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--release",type=Path,required=True); m=ap.add_mutually_exclusive_group(required=True); m.add_argument("--preflight-only",action="store_true"); m.add_argument("--execute",action="store_true"); ap.add_argument("--go-token",type=Path); a=ap.parse_args()
    p,detail=preflight(a.release.resolve())
    if a.preflight_only: print(json.dumps({"result":"PRODUCTION_BINDINGS_RESOLVED","ledger":175,"checkpoint_reads":0,"shard_opens":0,"expert_executions":0,"executor_preflight":detail},sort_keys=True)); return
    if not a.go_token: raise RuntimeError("GO_TOKEN_REQUIRED")
    authorize(a.release.resolve(),a.go_token.resolve(),p["approval"].resolve())
    inner={"authorization_sha256":sha(AUTH),"event_id":load(AUTH)["event_id"],"disposition":"GO_EXECUTE_ONCE_NO_RETRY","real_event_authorized":True}
    fd,tmp=tempfile.mkstemp(prefix="f017-expert-inner-token-"); os.fchmod(fd,0o400)
    with os.fdopen(fd,"w") as f: json.dump(inner,f,sort_keys=True,separators=(",",":")); f.write("\n")
    try:
        cmd=[sys.executable,str(EXECUTOR),"--authorization",str(AUTH),"--expert-input",str(p["expert_input"]),"--packed-root",str(p["packed_root"]),"--decoder-binary",str(p["decoder"]),"--state-root",str(p["state"]),"--output-root",str(p["output"]),"--go-token",tmp,"--execute"]
        raise SystemExit(subprocess.call(cmd))
    finally: os.unlink(tmp)
if __name__=="__main__": main()

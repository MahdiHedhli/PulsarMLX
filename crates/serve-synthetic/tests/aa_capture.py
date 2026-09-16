#!/usr/bin/env python3
"""Bounded AA controller using the unchanged accepted capture implementation."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from q_capture import capture,clean_env
from q_result_validator import read_capture
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cwd',type=Path,required=True);parser.add_argument('--seconds',type=int,required=True);parser.add_argument('--sdk-python');parser.add_argument('argv',nargs=argparse.REMAINDER);args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    env=clean_env(args.root);env.pop('CODEX_HOME',None)
    env.update({'CARGO_HOME':str(args.root/'cache/cargo'),'CARGO_TARGET_DIR':str(args.root/'target'),'RUSTUP_AUTO_INSTALL':'0','PULSARMLX_MODEL_GGUF':'','PATH':'/Users/mhedhli/.rustup/toolchains/stable-aarch64-apple-darwin/bin:/Users/mhedhli/.cargo/bin:'+env['PATH']})
    if args.sdk_python:env['PYTHON']=args.sdk_python
    argv=args.argv[1:] if args.argv and args.argv[0]=='--' else args.argv
    terminal=capture(argv,str(args.cwd),env,args.output,timeout=args.seconds,termination_grace=5)
    reread,_,_=read_capture(args.output)
    if terminal!=reread:raise RuntimeError('CONTROLLER_READBACK_MISMATCH')
    print(json.dumps(terminal,sort_keys=True))
    raise SystemExit(0 if terminal['code']==0 else 1)
if __name__=='__main__':main()

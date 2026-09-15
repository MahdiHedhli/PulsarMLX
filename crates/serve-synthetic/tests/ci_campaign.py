#!/usr/bin/env python3
"""Exclusive source-derived CI admission; full qualification remains fail-closed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import q_capture
from q_matrix import inventory

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def original_json(path,value,mode=0o400):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def layout(source,root):
    source=Path(source).resolve();root=Path(root).absolute()
    if root!=root.resolve() or root.is_symlink() or root.exists():raise RuntimeError('RUN_ROOT_NOT_FRESH')
    if source==root or source.is_relative_to(root) or root.is_relative_to(source):raise RuntimeError('UNSAFE_SOURCE_OUTPUT_ANCESTRY')
    return source,root
def admit_matrix(path,source,expected_digest):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode)&0o222:raise RuntimeError('MATRIX_NOT_IMMUTABLE_REGULAR')
    b=path.read_bytes()
    if not b or hashlib.sha256(b).hexdigest()!=expected_digest:raise RuntimeError('MATRIX_HASH_MISMATCH')
    frozen=json.loads(b)
    if frozen!=inventory(source) or len(frozen['properties'])!=20:raise RuntimeError('MATRIX_SOURCE_MISMATCH')
    return frozen
def tools():
    result={}
    for name in ['cargo','rustc']:
        located=shutil.which(name)
        if not located:raise RuntimeError('TOOLING_NOT_READY: '+name)
        if Path(located).resolve().name=='rustup':
            lookup=subprocess.run([str(Path(located).with_name('rustup')),'which',name],cwd=Path(__file__).parent,env={**os.environ,'RUSTUP_AUTO_INSTALL':'0'},capture_output=True,text=True,timeout=120,check=True)
            located=lookup.stdout.strip()
        path=Path(located).resolve()
        version=subprocess.run([str(path),'--version'],cwd=Path(__file__).parent,capture_output=True,text=True,timeout=120,check=True).stdout.strip()
        result[name]={'path':str(path),'sha256':sha(path),'version':version}
    return result
def launch(command,source,env,output,seconds):
    terminal=q_capture.capture(command,str(source),env,output,timeout=seconds,termination_grace=5)
    if terminal['status']!='CLOSED' or terminal['native_signal'] or terminal['code']!=0 or not terminal['reaped']:
        raise RuntimeError('CAMPAIGN_FAILED: '+json.dumps(terminal,sort_keys=True))
    return terminal
def run(source,root,python,seconds=2700,launcher=launch,tool_provider=tools):
    source,root=layout(source,root)
    python=str(Path(python).absolute())
    if python!=str(Path(sys.executable).absolute()):raise RuntimeError('SDK_INTERPRETER_MISMATCH')
    root.mkdir(mode=0o700)
    for name in ['input','tmp','cache']: (root/name).mkdir(mode=0o700)
    matrix=root/'input/matrix.json';original_json(matrix,inventory(source));digest=sha(matrix)
    admit_matrix(matrix,source,digest)
    selected=tool_provider()
    env=q_capture.clean_env(root)
    if 'CARGO_HOME' not in os.environ:raise RuntimeError('GRAPH_CARGO_HOME_REQUIRED')
    cargo_home=Path(os.environ['CARGO_HOME']).resolve()
    if not cargo_home.is_relative_to(root.parent.resolve()):raise RuntimeError('CARGO_HOME_OUTSIDE_GRAPH')
    env.update({'CARGO_HOME':str(cargo_home),'RUSTUP_AUTO_INSTALL':'0','CI_SELECTED_CARGO':selected['cargo']['path'],'CI_SELECTED_RUSTC':selected['rustc']['path']})
    harness=source/'tests/mutation_guards.py'
    command=[python,str(harness),'--root',str(root),'--evidence',str(root/'evidence'),'--scratch',str(root/'scratch'),'--target',str(root/'target'),'--matrix',str(matrix),'--python',python,'--campaign-seconds',str(seconds)]
    dependencies=[source/'tests'/name for name in ['mutation_guards.py','q_capture.py','q_campaign.py','q_matrix.py','q_result_validator.py','q_sdk_guard_oracle.py','ci_campaign.py']]
    bindings={str(p):sha(p) for p in dependencies}
    git=subprocess.run(['git','-C',str(source),'rev-parse','HEAD','HEAD^{tree}'],cwd=source,capture_output=True,text=True,timeout=120,check=True).stdout.splitlines()
    original_json(root/'input/admission.json',{'source_commit':git[0],'source_tree':git[1],'matrix_sha256':digest,'python':python,'python_sha256':sha(Path(python).resolve()),'script_sha256':bindings,'tools':selected,'argv':command,'environment_keys':sorted(env)})
    admit_matrix(matrix,source,digest)
    terminal=launcher(command,source,env,root/'controller',seconds)
    if any(sha(p)!=expected for p,expected in bindings.items()):raise RuntimeError('HARNESS_SOURCE_DRIFT')
    if terminal.get('code')!=0:raise RuntimeError('CAMPAIGN_NONZERO')
    return terminal
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--root',type=Path,required=True);parser.add_argument('--campaign-seconds',type=int,default=2700);args=parser.parse_args()
    run(args.source,args.root,sys.executable,args.campaign_seconds)
if __name__=='__main__':main()

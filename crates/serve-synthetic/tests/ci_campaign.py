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
def unavailable_diagnostic(error):
    return {'status':'UNAVAILABLE','error_type':error if isinstance(error,str) else type(error).__name__}
def failure_diagnostic(output,terminal=None,excerpt_limit=4096,capacity=q_capture.STREAM_LIMIT):
    """Read capture-owned stderr without letting diagnostics replace the terminal."""
    directory_fd=None;stream_fd=None
    try:
        if not isinstance(excerpt_limit,int) or excerpt_limit<0 or not isinstance(capacity,int) or capacity<0:
            raise ValueError('invalid diagnostic bound')
        output=Path(output)
        absolute=output.absolute()
        resolved=output.resolve(strict=True)
        if absolute!=resolved: return unavailable_diagnostic('OutputNotCanonical')
        flags=os.O_RDONLY|getattr(os,'O_CLOEXEC',0)|getattr(os,'O_DIRECTORY',0)|os.O_NOFOLLOW
        directory_fd=os.open(resolved,flags)
        directory_stat=os.fstat(directory_fd)
        if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_uid!=os.geteuid() or stat.S_IMODE(directory_stat.st_mode)&0o077:
            return unavailable_diagnostic('OutputNotOwnedPrivateDirectory')
        stream_fd=os.open('stderr.raw',os.O_RDONLY|getattr(os,'O_CLOEXEC',0)|os.O_NOFOLLOW,dir_fd=directory_fd)
        before=os.fstat(stream_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid() or stat.S_IMODE(before.st_mode)&0o077:
            return unavailable_diagnostic('ArtifactNotOwnedPrivateRegular')
        if before.st_size>capacity:return unavailable_diagnostic('ArtifactCapacityExceeded')
        digest=hashlib.sha256();head=bytearray();total=0
        while True:
            block=os.read(stream_fd,min(65536,capacity-total+1))
            if not block:break
            total+=len(block)
            if total>capacity:return unavailable_diagnostic('ArtifactCapacityExceeded')
            digest.update(block)
            if len(head)<excerpt_limit:head.extend(block[:excerpt_limit-len(head)])
        after=os.fstat(stream_fd)
        if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino) or after.st_size!=total:
            return unavailable_diagnostic('ArtifactChangedDuringRead')
        sha256=digest.hexdigest()
        if terminal is not None:
            try:
                expected_bytes=terminal['stream_bytes']['stderr'];expected_sha256=terminal['stream_sha256']['stderr']
            except (KeyError,TypeError):
                return unavailable_diagnostic('TerminalEvidenceMissing')
            if expected_bytes!=total or expected_sha256!=sha256:
                return unavailable_diagnostic('TerminalEvidenceMismatch')
        excerpt=bytes(head)
        capture_complete=bool(terminal is None or (terminal.get('status') in {'CLOSED','SPAWN_ERROR'} and not terminal.get('capture_error') and not terminal.get('timeout')))
        return {'status':'AVAILABLE','bytes':total,'sha256':sha256,'digest_complete':True,
                'capture_complete':capture_complete,'excerpt_bytes':len(excerpt),
                'excerpt_sha256':hashlib.sha256(excerpt).hexdigest(),
                'excerpt_truncated':total>len(excerpt),'excerpt_encoding':'utf-8-backslashreplace',
                'excerpt':excerpt.decode('utf-8','backslashreplace')}
    except Exception as error:
        return unavailable_diagnostic(error)
    finally:
        if stream_fd is not None:os.close(stream_fd)
        if directory_fd is not None:os.close(directory_fd)
def launch(command,source,env,output,seconds,diagnostic_provider=failure_diagnostic,capture_limit=None):
    capture_options={'timeout':seconds,'termination_grace':5}
    if capture_limit is not None:capture_options['limit']=capture_limit
    terminal=q_capture.capture(command,str(source),env,output,**capture_options)
    if terminal['status']!='CLOSED' or terminal['native_signal'] or terminal['code']!=0 or not terminal['reaped']:
        try:diagnostic=diagnostic_provider(output,terminal)
        except Exception as error:diagnostic=unavailable_diagnostic(error)
        raise RuntimeError('CAMPAIGN_FAILED: '+json.dumps({'terminal':terminal,'diagnostic':diagnostic},sort_keys=True))
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

"""Exact source-only measurement preparation, deliberately outside fixture seal.

Only the hash-bound stdlib measurement generator executes here. Model/runtime
files are readonly data. This is trusted preparation, NOT OS confidentiality
confinement and NOT qualification or diagnosis of a previously confined Git.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import stat
import sys
import tempfile
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f017_preparation_capture_v1 as cap

SOURCE=Path(__file__).resolve().parents[2]
GENERATOR='scripts/research/generate_f017_v11_measurement_v1.py'
RECORD='docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json'
GENERATOR_SHA='ead39c8a8e1f8be4e0dbcd42121beaf58470dbf7dbcb4d93bcc83ef0f8527ef0'
RECORD_SHA='c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414'
HISTORICAL='f35d341110c67377200ad353ab56a3cf38615a73'
HISTORICAL_TREE='08864e7d529c91c0ec8f4bf9661006503e6d7dc9'
EXPECTED='ValueError: working tree differs from measurement head: scripts/research/f017_corrected_oracle_primary_wrapper_v11.py'
ROLES=('CURRENT_ORIGINAL_CHECK','HISTORICAL_ORIGINAL_CHECK')
SAFE_CONFIG=b'[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n\tbare = true\n\thooksPath = /dev/null\n\tfsmonitor = false\n'
TRUSTED_CONTROLLERS=('scripts/ci/f017_measurement_preparation_v1.py','scripts/ci/f017_preparation_capture_v1.py','scripts/ci/f017_measurement_preparation_tests_v1.py','scripts/research/tests/f017_primary_confined_ci_v1.py')
need=cap.need
def clean_env(area,git):
    # Preserve homes verbatim; discard injection/runtime/config variables.
    env={k:os.environ[k]for k in ('HOME','CODEX_HOME','USER','LOGNAME','SHELL')if k in os.environ}
    env.update(PATH=str(Path(git).parent)+':/usr/bin:/bin',LANG='C',LC_ALL='C',TMPDIR=str(area/'tmp'),XDG_CACHE_HOME=str(area/'cache'),XDG_CONFIG_HOME=str(area/'config'),GIT_CONFIG_SYSTEM='/dev/null',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_ATTR_NOSYSTEM='1',GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1',GIT_CONFIG_COUNT='0',GIT_PROTOCOL_FROM_USER='0')
    return env
def area(path):
    path=Path(path);path.mkdir(mode=0o700)
    for name in ('tmp','cache','config','empty-template'):(path/name).mkdir(mode=0o700)
    return path
def tools(work):
    python=Path(sys.executable).resolve(strict=True)
    # A fixed source-free locator, not a caller-supplied executable override.
    env={k:os.environ[k]for k in ('HOME','CODEX_HOME','USER','LOGNAME','SHELL')if k in os.environ}
    env.update(PATH='/usr/bin:/bin',LANG='C',LC_ALL='C',TMPDIR=str(work/'tmp'),XDG_CACHE_HOME=str(work/'cache'))
    r,out,err=cap.capture(['/usr/bin/xcrun','--find','git'],work,'data-resolve-git',env,timeout=30,limit=4096)
    need(r['capture_integrity']=='PASS'and r['exit_code']==0 and not err,'GIT_UNAVAILABLE')
    value=out.decode().strip();need(value.startswith('/')and '\n'not in value,'GIT_LOCATOR_RESULT')
    git=Path(value).resolve(strict=True)
    need(git.is_file() and python.is_file(),'REGULAR_EXECUTABLES')
    return str(python),str(git)
def safe_source(raw,record):
    tree=ast.parse(raw)
    imports={n.module if isinstance(n,ast.ImportFrom)else alias.name for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))for alias in (n.names if isinstance(n,ast.Import)else [None])}
    need(imports=={'__future__','argparse','hashlib','json','pathlib','subprocess'},'GENERATOR_IMPORT_CLOSURE')
    need(cap.sha(raw)==GENERATOR_SHA,'GENERATOR_IDENTITY')
    paths=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='PATHS'for t in n.targets)))
    need(type(paths)is tuple and len(paths)==len(set(paths))==36,'GENERATOR_PATH_CENSUS')
    need(cap.sha(record)==RECORD_SHA,'RECORD_IDENTITY');m=json.loads(record)
    need(m['implementation_head']==HISTORICAL and m['implementation_tree']==HISTORICAL_TREE and [r['path']for r in m['measured_paths']]==list(paths),'RECORD_ROLES')
    need(not set(paths)&set(TRUSTED_CONTROLLERS),'MEASURED_CONTROLLER_INTERSECTION')
    return paths,m
def validate_setup_command(args,work):
    need(type(args)is list and all(type(x)is str for x in args),'DATA_GIT_ARGV')
    head=lambda v:re.fullmatch('[0-9a-f]{40}',v)is not None
    valid=False
    if args and args[0]=='rev-parse':valid=len(args)==2 and(args[1]=='HEAD' or args[1].endswith('^{tree}')and head(args[1][:-7]))
    if args and args[0]=='show':
        if len(args)==2 and ':'in args[1]:
            h,path=args[1].split(':',1);paths,_=safe_source((SOURCE/GENERATOR).read_bytes(),(SOURCE/RECORD).read_bytes());valid=head(h)and path in paths
    if args and args[0]=='clone':valid=args==['clone','--quiet','--bare','--no-local','--no-hardlinks','--template='+str(work/'empty-template'),str(SOURCE),str(work/'objects.git')]
    if args and args[0]=='update-ref':valid=len(args)==4 and args[:3]==['update-ref','--no-deref','HEAD']and head(args[3])
    if args and args[0]=='init':valid=args==['init','--quiet','--bare','--template='+str(work/'empty-template'),str(work/'tiny.git')]
    if args and args[0]=='hash-object':valid=args==['hash-object','-w',str(work/'fixture.txt')]
    need(valid,'DATA_GIT_COMMAND')
def data_git(git,args,work,env,label):
    """Fixed internal setup calls only; never the tested generator's children."""
    validate_setup_command(args,work)
    # Only the already exact-validated owned source -> owned store clone may
    # use file transport. No network protocol or check-child permission changes.
    clone_policy=['-c','protocol.file.allow=always']if args[0]=='clone'else[]
    result,out,err=cap.capture([git,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','credential.helper=',*clone_policy,*args],work,'data-'+label,env,timeout=60,limit=12*1024**2)
    need(result['capture_integrity']=='PASS' and result['returncode']==0,'SOURCE_DATA_PREPARATION_FAILED:'+label)
    return out
def readonly(path,raw):
    cap.bank(path,raw);path.chmod(0o444)
def validate_store(store,expected_head):
    need(store.is_dir()and not store.is_symlink(),'OWNED_STORE')
    need((store/'config').read_bytes()==SAFE_CONFIG,'OWNED_GIT_CONFIG')
    need((store/'HEAD').read_text()==expected_head+'\n','OWNED_VIEW_HEAD')
    need(not any((store/p).exists()for p in ('commondir','gitdir','objects/info/alternates','modules')),'STORE_INDIRECTION')
    for path in store.rglob('*'):
        st=path.lstat();need(not stat.S_ISLNK(st.st_mode),'STORE_SYMLINK')
        if stat.S_ISREG(st.st_mode):need(st.st_nlink==1,'STORE_HARDLINK')
    return dict(head=expected_head,config_sha256=cap.sha(SAFE_CONFIG),alternates=False,hardlinks=False,symlinks=False,external_worktree=False)
def validate_view(view,role,manifest,paths,raw,record,current_identity):
    need(role in ROLES and manifest['role']==role,'VIEW_ROLE')
    expected=set(paths)|{GENERATOR,RECORD}
    actual=set()
    for p in view.rglob('*'):
        need(not p.is_symlink(),'VIEW_SYMLINK')
        if p.is_file():actual.add(str(p.relative_to(view)))
    need(actual==expected and set(manifest['files'])==expected,'VIEW_EXACT_PATH_CENSUS')
    need(manifest['generator_sha256']==GENERATOR_SHA and manifest['record_sha256']==RECORD_SHA,'VIEW_CONTROL_ROLES')
    for path in sorted(expected):
        p=view/path;need(p.is_file()and not p.is_symlink()and p.stat().st_nlink==1 and not p.stat().st_mode&0o222,'VIEW_READONLY_REGULAR')
        need(cap.sha(p.read_bytes())==manifest['files'][path],'VIEW_SOURCE_BINDING:'+path)
    need((view/GENERATOR).read_bytes()==raw and(view/RECORD).read_bytes()==record,'EXACT_ORIGINAL_CHECK_INPUTS')
    need((manifest['current_head_under_test'],manifest['current_tree_under_test'])==current_identity,'CURRENT_BINDING_CONTEXT')
    if role=='HISTORICAL_ORIGINAL_CHECK':
        need(manifest['source_head']==HISTORICAL and manifest['source_tree']==HISTORICAL_TREE,'HISTORICAL_VIEW_IDENTITY')
        for row in json.loads(record)['measured_paths']:need(manifest['files'][row['path']]==row['sha256'],'HISTORICAL_ROLE_BODY:'+row['path'])
    else:
        need((manifest['source_head'],manifest['source_tree'])==current_identity and manifest['source_head']!=HISTORICAL,'CURRENT_VIEW_NOT_HISTORICAL')
        for path in paths:need(manifest['files'][path]==cap.sha((SOURCE/path).read_bytes()),'CURRENT_ROLE_BODY:'+path)
def validate_original_argv(argv,python,view):
    need(argv==[python,'-I','-S','-B',str(view/GENERATOR),'--check'],'LITERAL_CHECK_ONLY')
def parse_trace(raw,expected):
    need(len(raw)<2*1024**2,'GIT_TRACE_BOUND');rows=[json.loads(x)for x in raw.splitlines()]
    starts=[r for r in rows if r.get('event')=='start'];exits=[r for r in rows if r.get('event')=='exit']
    need(not any(r.get('event') in ('child_start','exec')for r in rows),'UNEXPECTED_GIT_DESCENDANT_COMMAND')
    need(len(starts)==len(exits)==len(expected),'ACTUAL_GIT_QUERY_CENSUS')
    need([r['argv'][1:]for r in starts]==expected,'ACTUAL_GIT_QUERY_ORDER')
    need(len({r['sid']for r in starts})==len(starts),'GIT_SESSION_UNIQUENESS')
    need({r['sid']for r in starts}=={r['sid']for r in exits} and all(r['code']==0 for r in exits),'ALL_GIT_QUERIES_EXITED')
    return dict(actual_git_starts=len(starts),actual_exit_events=len(exits),requested_queries=expected,executing_image_independently_observed=False,evidence='GIT_TRACE2_SELF_REPORT_PLUS_PINNED_CHECK_OUTPUT_WAIT_PATH')
def classify(role,result,out,err,view):
    need(role in ROLES,'CHECK_ROLE');need(result['actual_target_start']and result['reaped']and result['capture_integrity']=='PASS','ORIGINAL_CHECK_CAPTURE')
    need(result['signal']is None and not result['failed_spawn']and not result['timed_out'],'ORIGINAL_CHECK_TOOLING_FAILURE')
    if role=='CURRENT_ORIGINAL_CHECK':
        need(result['exit_code']!=0,'CURRENT_ORIGINAL_UNEXPECTED_PASS')
        lines=err.decode('utf-8').splitlines()
        need(result['exit_code']==1 and out==b'' and lines and lines[-1]==EXPECTED,'CURRENT_EXACT_EXPECTED_EXCEPTION')
        need(lines[0]=='Traceback (most recent call last):' and any(str(view/GENERATOR)in line and 'in generate' in line for line in lines),'CURRENT_EXPECTED_RAISE_SITE')
        return 'EXPECTED_EXACT_VALUEERROR'
    need(result['exit_code']==0 and out==b'' and err==b'','HISTORICAL_ORIGINAL_CHECK_FAILED')
    return 'PASS_CANONICAL_CHECK_ONLY'
def original_queries(paths,role):
    queries=[['rev-parse',HISTORICAL+'^{tree}']]
    for path in paths:
        queries.append(['show',HISTORICAL+':'+path])
        if role=='CURRENT_ORIGINAL_CHECK'and path.endswith('/f017_corrected_oracle_primary_wrapper_v11.py'):break
        queries.append(['rev-parse',HISTORICAL+':'+path])
    return queries
def prepare(parent):
    need(sys.flags.optimize==0,'NO_OPTIMIZE');resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    parent=Path(parent);work=area(parent/'source-preparation');python,git=tools(work);env=clean_env(work,git)
    raw=(SOURCE/GENERATOR).read_bytes();record=(SOURCE/RECORD).read_bytes();paths,m=safe_source(raw,record)
    current=data_git(git,['rev-parse','HEAD'],work,{**env,'GIT_DIR':str(SOURCE/'.git')},'source-head').decode().strip()
    current_tree=data_git(git,['rev-parse',current+'^{tree}'],work,{**env,'GIT_DIR':str(SOURCE/'.git')},'source-tree').decode().strip()
    need(len(current)==len(current_tree)==40 and current!=HISTORICAL,'CURRENT_COMMITTED_IDENTITY')
    expected_historical={r['path']:r['sha256']for r in m['measured_paths']};reports=[]
    # Verify every required historical object before either tested generator
    # starts. These fixed data reads are separately captured setup helpers.
    source_env={**env,'GIT_DIR':str(SOURCE/'.git')}
    need(data_git(git,['rev-parse',HISTORICAL+'^{tree}'],work,source_env,'required-history-tree').decode().strip()==HISTORICAL_TREE,'HISTORY_UNAVAILABLE')
    for number,path in enumerate(paths):
        body=data_git(git,['show',HISTORICAL+':'+path],work,source_env,'required-history-'+str(number))
        need(cap.sha(body)==expected_historical[path],'HISTORY_UNAVAILABLE:'+path)
    for role in ROLES:
        base=area(work/role.lower());view=base/'view';view.mkdir(mode=0o700);store=base/'objects.git';store_env=clean_env(base,git)
        data_git(git,['clone','--quiet','--bare','--no-local','--no-hardlinks','--template='+str(base/'empty-template'),str(SOURCE),str(store)],base,store_env,'owned-nonlocal-clone')
        original_config=(store/'config').read_bytes();cap.bank(base/'initial-owned-config',original_config)
        cap.bank(base/'safe-config',SAFE_CONFIG);os.replace(base/'safe-config',store/'config')
        source_head=HISTORICAL if role=='HISTORICAL_ORIGINAL_CHECK'else current
        git_env={**store_env,'GIT_DIR':str(store),'GIT_WORK_TREE':str(view)}
        data_git(git,['update-ref','--no-deref','HEAD',source_head],base,git_env,'owned-head')
        identity=validate_store(store,source_head)
        observed_head=data_git(git,['rev-parse','HEAD'],base,git_env,'verify-head').decode().strip();need(observed_head==source_head,'ACTUAL_STORE_HEAD')
        source_tree=data_git(git,['rev-parse',source_head+'^{tree}'],base,git_env,'view-tree').decode().strip()
        need(source_tree==(HISTORICAL_TREE if role=='HISTORICAL_ORIGINAL_CHECK'else current_tree),'VIEW_TREE_IDENTITY')
        files={GENERATOR:raw,RECORD:record}
        for number,path in enumerate(paths):
            body=data_git(git,['show',source_head+':'+path],base,git_env,'source-'+str(number))
            if role=='HISTORICAL_ORIGINAL_CHECK':need(cap.sha(body)==expected_historical[path],'HISTORICAL_BODY_IDENTITY')
            else:need(body==(SOURCE/path).read_bytes(),'CURRENT_SOURCE_NOT_COMMITTED:'+path)
            files[path]=body
        for path,body in files.items():readonly(view/path,body)
        manifest=dict(role=role,source_head=source_head,source_tree=source_tree,current_head_under_test=current,current_tree_under_test=current_tree,generator_sha256=GENERATOR_SHA,record_sha256=RECORD_SHA,files={p:cap.sha(b)for p,b in files.items()},composite='FIXED_ORIGINAL_VERIFIER_PLUS_LATER_RECORD_AND_ROLE_SOURCE_BYTES',numerical_execution=False,owned_store=identity)
        cap.bank(base/'source-role-manifest.json',cap.canonical(manifest));validate_view(view,role,manifest,paths,raw,record,(current,current_tree))
        trace=base/'git-trace2.jsonl';argv=[python,'-I','-S','-B',str(view/GENERATOR),'--check']
        validate_original_argv(argv,python,view)
        before_git=cap.image(git);result,out,err=cap.capture(argv,base,'original',dict(git_env,GIT_TRACE2_EVENT=str(trace)))
        need(before_git==cap.image(git),'REQUESTED_GIT_IMAGE_CHANGED')
        outcome=classify(role,result,out,err,view)
        trace_report=parse_trace(trace.read_bytes(),original_queries(paths,role))
        validate_store(store,source_head);validate_view(view,role,manifest,paths,raw,record,(current,current_tree))
        report=dict(role=role,result=outcome,current_head=current,current_tree=current_tree,manifest_sha256=cap.sha((base/'source-role-manifest.json').read_bytes()),trace_sha256=cap.sha(trace.read_bytes()),trace=trace_report,generator_starts=1,generator_capture=result,requested_git_identity=before_git,git_executing_image_independently_observed=False,numerical_modules_imported=0,scope='TRUSTED_FIXED_SOURCE_PREPARATION_NOT_OS_CONFINEMENT')
        cap.bank(base/'report.json',cap.canonical(report));reports.append(report)
    result=dict(result='PASS',scope='TRUSTED_SOURCE_PREPARATION_ONLY_NO_NUMERICAL_IMPORT',current_head=current,current_tree=current_tree,roles=reports,generator_children=2,nested_git_children=sum(r['trace']['actual_git_starts']for r in reports),old_confined_git_root_cause='UNKNOWN_NOT_REDIAGNOSED',old_confined_git_qualification=False)
    cap.bank(work/'result.json',cap.canonical(result));return result
def doctor(parent):
    work=area(Path(parent)/'preparation-doctor');python,git=tools(work);env=clean_env(work,git);records=[]
    # Harmless owned repository with fixed local object-writing setup only.
    data_git(git,['init','--quiet','--bare','--template='+str(work/'empty-template'),str(work/'tiny.git')],work,env,'tiny-init')
    tiny=work/'tiny.git';cap.bank(work/'initial-owned-config',(tiny/'config').read_bytes());cap.bank(work/'safe-config',SAFE_CONFIG);os.replace(work/'safe-config',tiny/'config')
    cap.bank(work/'fixture.txt',b'F017_FIXED_SOURCE_FREE_GIT\n');g={**env,'GIT_DIR':str(tiny)}
    h=data_git(git,['hash-object','-w',str(work/'fixture.txt')],work,g,'tiny-blob').decode().strip()
    # Fixed tree and commit objects are data. No hook-bearing git commit command.
    tree_raw=b'100644 fixture.txt\0'+bytes.fromhex(h);tree_object=b'tree '+str(len(tree_raw)).encode()+b'\0'+tree_raw;tree_sha=hashlib.sha1(tree_object).hexdigest()
    obj=tiny/'objects'/tree_sha[:2];obj.mkdir(exist_ok=True);cap.bank(obj/tree_sha[2:],zlib.compress(tree_object))
    commit_raw=f'tree {tree_sha}\nauthor F017 Fixture <fixture@example.invalid> 0 +0000\ncommitter F017 Fixture <fixture@example.invalid> 0 +0000\n\nfixed source-free doctor\n'.encode();co=b'commit '+str(len(commit_raw)).encode()+b'\0'+commit_raw;head=hashlib.sha1(co).hexdigest();obj=tiny/'objects'/head[:2];obj.mkdir(exist_ok=True);cap.bank(obj/head[2:],zlib.compress(co))
    data_git(git,['update-ref','--no-deref','HEAD',head],work,g,'tiny-head');validate_store(tiny,head)
    for label,args,expected in [('git-version',['--version'],None),('git-head',['rev-parse','HEAD'],(head+'\n').encode()),('git-show',['show','HEAD:fixture.txt'],b'F017_FIXED_SOURCE_FREE_GIT\n')]:
        r,out,err=cap.capture([git,*args],work,label,g,timeout=60);need(r['capture_integrity']=='PASS' and r['exit_code']==0 and not err,'GIT_DOCTOR');need(expected is None or out==expected,'GIT_DOCTOR_OUTPUT');records.append(r)
    for mode in ('io','exit134','signal6','timeout'):
        r,out,err=cap.capture([python,'-I','-S','-B',str(Path(cap.__file__).resolve()),'--doctor-'+mode],work,'python-'+mode,env,timeout=.2 if mode=='timeout'else 60);records.append(r)
        if mode=='io':need(r['exit_code']==0 and r['capture_integrity']=='PASS'and json.loads(out)['fixed_write_read'],'PYTHON_IO_DOCTOR')
        if mode=='exit134':need(r['exit_code']==134 and r['signal']is None and out==b'SOURCE_FREE_STDOUT\n'and err==b'SOURCE_FREE_STDERR\n','EXIT134_DISTINCT')
        if mode=='signal6':need(r['signal']==6 and r['exit_code']is None,'SIGNAL6_DISTINCT')
        if mode=='timeout':need(r['timed_out']and r['reaped']and r['capture_integrity']=='FAIL','TIMEOUT_DISTINCT')
    r,_,_=cap.capture([str(work/'ABSENT_FIXED_PROBE')],work,'missing-spawn',env,missing_probe=True);need(r['failed_spawn']['errno']==2 and not r['actual_target_start'],'FAILED_SPAWN_DISTINCT');records.append(r)
    result=dict(result='PASS',scope='SOURCE_FREE_TRUSTED_PREPARATION_ENVIRONMENT_NOT_TENSOR_SANDBOX',python=cap.image(python),git=cap.image(git),actual_direct_doctor_starts=sum(r['actual_target_start']for r in records),owned_setup_git_starts=3,failed_spawn_probes=1,numerical_modules_imported=0,records=records)
    cap.bank(work/'admission.json',cap.canonical(result));return result
if __name__=='__main__':
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.optimize==0 and sys.argv[1:]in [['--doctor'],['--check']],'FIXED_PREPARATION_ENTRY')
    root=Path(tempfile.mkdtemp(prefix='f017-source-preparation-'));root.chmod(0o700)
    print(json.dumps(doctor(root)if sys.argv[1]=='--doctor'else prepare(root),sort_keys=True))

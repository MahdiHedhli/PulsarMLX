#!/usr/bin/env python3
"""Fixed source-free supervisor for the admitted primary-prefix method.

Only the finite source-free controllers and exact hash-bound stdlib measurement
generator execute before sealing. Model/runtime bodies remain data. A child preloads
stdlib, self-confines, proves real denial fences, verifies readonly source
hashes, then imports the fixed research cases. This is not a live executor.
Artifacts are retained under one fresh temporary root, including on failure.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

SOURCE = Path(__file__).resolve().parents[3]
TESTS = SOURCE/'scripts/research/tests'
RECORD = 'docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json'
GENERATOR = 'scripts/research/generate_f017_v11_measurement_v1.py'
HISTORICAL = 'f35d341110c67377200ad353ab56a3cf38615a73'
SOURCE_BASE = '6f59d9db93e92afed142b543a0e2fc19e0362bb4'
LIMIT = 32768
def need(ok, label):
    if not ok: raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def write(path,raw,readonly=False):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        at=0
        while at<len(raw):n=os.write(fd,raw[at:]);need(n>0,'WRITE');at+=n
        os.fsync(fd)
    finally:os.close(fd)
    if readonly:path.chmod(0o444)
def image(path):
    p=Path(path).resolve(strict=True);a=p.stat();h=sha(p.read_bytes());b=p.stat()
    need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns),'IMAGE_CHANGED')
    return dict(path=str(p),sha256=h,device=a.st_dev,inode=a.st_ino,bytes=a.st_size)
def capture(root,label,argv,cwd,env):
    key=root/'captures'/label;before=image(argv[0]);start=time.monotonic()
    write(key/'attempt.json',encode(dict(argv=argv,cwd=str(cwd),environment=env,image=before,timeout_seconds=180,close_fds=True)))
    child=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,start_new_session=True)
    write(key/'spawn.json',encode(dict(pid=child.pid,actual_target_start=True)))
    selected=selectors.DefaultSelector();kept={'stdout':bytearray(),'stderr':bytearray()};counts={'stdout':0,'stderr':0};timeout=False
    try:
        for name,pipe in [('stdout',child.stdout),('stderr',child.stderr)]:
            os.set_blocking(pipe.fileno(),False);selected.register(pipe,selectors.EVENT_READ,name)
        while selected.get_map() or child.poll() is None:
            if time.monotonic()-start>180:timeout=True;os.killpg(child.pid,signal.SIGKILL);break
            for event,_ in selected.select(.05):
                raw=os.read(event.fileobj.fileno(),4096)
                if not raw:selected.unregister(event.fileobj);event.fileobj.close()
                else:counts[event.data]+=len(raw);kept[event.data].extend(raw[:max(0,LIMIT-len(kept[event.data]))])
        status=child.wait(timeout=30)
    finally:
        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=30)
        for event in list(selected.get_map().values()):event.fileobj.close()
        selected.close()
    raw={name:bytes(value) for name,value in kept.items()}
    for name,value in raw.items():write(key/name,value)
    result=dict(returncode=status,reaped=child.returncode is not None,timed_out=timeout,image_stable=before==image(argv[0]),counts=counts,
                truncated={n:counts[n]>len(raw[n]) for n in raw},stdout_sha256=sha(raw['stdout']),stderr_sha256=sha(raw['stderr']))
    write(key/'result.json',encode(result))
    need(not timeout and result['reaped'] and result['image_stable'] and not any(result['truncated'].values()),'CAPTURE_INTEGRITY_STOP')
    need(status==0,'CHILD_FAILED:'+label+':'+raw['stderr'].decode(errors='replace')[-1200:])
    return raw['stdout']
def git(*args):
    p=subprocess.run(['git','-c','core.hooksPath=/dev/null',*args],cwd=SOURCE,capture_output=True,timeout=30)
    need(p.returncode==0,'GIT_DATA_UNAVAILABLE');need(len(p.stdout)<12*1024*1024,'GIT_DATA_BOUND');return p.stdout
def quote(path):return json.dumps(str(path))
def profile(area,root,prefix,git_binary=None,git_dir=None):
    need(git_binary is None and git_dir is None,'NO_GIT_IN_NUMERICAL_FIXTURE_PROFILE')
    reads=['/System/Library','/usr/lib',str(Path(prefix)/'lib'),str(Path(prefix)/'bin'),str(area/'tooling'),str(area/'work'),str(area/'tmp'),str(area/'cache')]
    literals=['/dev/null','/dev/urandom','/dev/random',str(Path(prefix)/'Python')]
    metadata=set()
    for p in [area,root,Path(prefix)]:metadata.update(str(x) for x in [p,*p.parents])
    rows=['(version 1)','(allow default)','(deny network*)','(deny file-read*)','(deny file-write*)','(deny process-exec)']
    rows+=['(allow file-read* '+ ' '.join('(subpath '+quote(p)+')' for p in reads)+' '+ ' '.join('(literal '+quote(p)+')' for p in literals)+')']
    rows+=['(deny file-read* (subpath '+quote(Path(prefix)/'lib'/('python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor))/'site-packages')+'))']
    rows+=['(allow file-read-metadata '+' '.join('(literal '+quote(p)+')' for p in sorted(metadata))+')']
    rows+=['(allow file-write* (literal "/dev/null") '+' '.join('(subpath '+quote(area/p)+')' for p in ['work','tmp','cache'])+')','(allow file-read-data file-test-existence file-write-data (subpath "/dev/fd"))']
    return ('\n'.join(rows)+'\n').encode()

def main():
    need(sys.argv[1:]==[] and sys.flags.optimize==0 and sys.platform=='darwin','FIXED_MACOS_NO_OPTIMIZE_ENTRY')
    need(not os.environ.get('PULSARMLX_MODEL_GGUF'),'NO_MODEL_INPUT')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=Path(tempfile.mkdtemp(prefix='f017-primary-ci-')).resolve();root.chmod(0o700)
    need(shutil.disk_usage(root).free>=8*1024**3,'STORAGE_HEADROOM')
    python=str(Path(sys.executable).resolve());env=dict(PATH='/usr/bin:/bin',LANG='C',LC_ALL='C',TMPDIR=str(root),XDG_CACHE_HOME=str(root/'cache'))
    (root/'cache').mkdir(mode=0o700)
    current_commit=git('rev-parse','HEAD').decode().strip()
    controller_paths=('scripts/ci/f017_measurement_preparation_v1.py','scripts/ci/f017_preparation_capture_v1.py','scripts/ci/f017_measurement_preparation_tests_v1.py','scripts/research/tests/f017_primary_confined_ci_v1.py')
    controller_rows=[]
    for path in controller_paths:
        body=(SOURCE/path).read_bytes();need(git('show',current_commit+':'+path)==body,'CONTROLLER_NOT_COMMITTED:'+path)
        controller_rows.append(dict(path=path,sha256=sha(body)))
    write(root/'trusted-controller-closure.json',encode(dict(current_commit=current_commit,controllers=controller_rows,only_preseal_research_execution='EXACT_HASH_BOUND_ORIGINAL_SOURCE_MEASUREMENT_GENERATOR',numerical_modules_preseal=0)))
    # Explicit source-only trust boundary. No numerical module is imported by
    # these fixed controllers or by the exact stdlib-only original generator.
    sys.path.insert(0,str(SOURCE/'scripts/ci'))
    import f017_measurement_preparation_v1 as preparation
    import f017_measurement_preparation_tests_v1 as preparation_tests
    need(Path(preparation.__file__).resolve()==SOURCE/'scripts/ci/f017_measurement_preparation_v1.py','FIXED_PREPARATION_MODULE')
    doctor_report=preparation.doctor(root)
    preparation_report=preparation.prepare(root)
    mutation_report=preparation_tests.run(root,preparation_report)
    preparation_summary=dict(result=preparation_report['result'],current_head=preparation_report['current_head'],current_tree=preparation_report['current_tree'],generator_children=preparation_report['generator_children'],nested_git_children=preparation_report['nested_git_children'],roles=[dict(role=r['role'],result=r['result'],manifest_sha256=r['manifest_sha256'],trace_sha256=r['trace_sha256'])for r in preparation_report['roles']],report_sha256=sha((root/'source-preparation/result.json').read_bytes()),doctor_sha256=sha((root/'preparation-doctor/admission.json').read_bytes()),mutation_report=mutation_report)
    write(root/'trusted-preparation-summary.json',encode(preparation_summary))
    bootstrap=(TESTS/'f017_primary_confined_bootstrap_v1.py').read_bytes();dispatch=(TESTS/'f017_primary_ci_dispatch_v1.py').read_bytes()
    write(root/'bootstrap.py',bootstrap)
    description=json.loads(capture(root,'source-free-prefix',[python,'-I','-S','-B',str(root/'bootstrap.py'),'--describe-source-free'],root,env))
    need(description['python']==python,'SOURCE_FREE_EXECUTABLE')
    modules=description['module_closure'];need(type(modules)is list and len(modules)<1024 and len({r['name'] for r in modules})==len(modules),'SOURCE_FREE_MODULE_CENSUS')
    need(all(r['origin'] in ('built-in','frozen') or r['origin'].startswith('@PYTHON_FRAMEWORK@/lib/python') and '/site-packages/' not in r['origin'] for r in modules),'SOURCE_FREE_ORIGINS')
    write(root/'source-free-prefix.json',encode(description))
    policy=json.loads((SOURCE/'scripts/ci/f017_primary_ci_inputs_v1.json').read_bytes());need(policy['source_base']==SOURCE_BASE,'INPUT_POLICY_BASE')
    current={}
    for r in policy['inputs']:
        body=(SOURCE/r['repository_path']).read_bytes();need(sha(body)==r['sha256'],'CURRENT_ACTIVE_SOURCE_DRIFT:'+r['repository_path']);current[r['view_path']]=body
    record=(SOURCE/RECORD).read_bytes();m=json.loads(record)
    need(m['implementation_head']==HISTORICAL and sha(record)=='c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414','MEASUREMENT_RECORD')
    historical={r['path']:git('show',HISTORICAL+':'+r['path']) for r in m['measured_paths']}
    need(len(historical)==36,'HISTORICAL_36')
    for r in m['measured_paths']:need(sha(historical[r['path']])==r['sha256'],'HISTORICAL_OBJECT_SHA')
    generator=(SOURCE/GENERATOR).read_bytes();need(sha(generator)=='ead39c8a8e1f8be4e0dbcd42121beaf58470dbf7dbcb4d93bcc83ef0f8527ef0','GENERATOR_EXACT')
    base_workflow=git('show',SOURCE_BASE+':.github/workflows/macos.yml')
    # Both original-generator claims completed above as trusted preparation.
    # The remaining eight fixture groups never need or permit Git execution.
    cases=('CI_SCOPE_TESTS','BASIC_SUCCESSOR','WRAPPER_SUCCESSOR','FAULTS_SUCCESSOR','INTEGRATION','HISTORICAL_DRIFT_CONTROL','ACTIVE_CENSUS_CONTROL','INTEGRATION')
    reports=[]
    for number,case_id in enumerate(cases,1):
        area=root/('case-'+str(number));denied=root/('denied-'+str(number))
        for p in [area,denied,*[area/n for n in ('tooling','work','tmp','cache')]]:p.mkdir(mode=0o700)
        view=area/'tooling/codeviews/successor';bodies=dict(current)
        if case_id.startswith('CI_'):
            bodies.update({p:(SOURCE/p).read_bytes() for p in historical})
            bodies.update({GENERATOR:generator,RECORD:record})
            for p in ('scripts/ci/f017_measurement_scope_v1.py','scripts/ci/f017_measurement_scope_tests_v1.py'):bodies[p]=(SOURCE/p).read_bytes()
        if case_id=='CI_SCOPE_TESTS':
            bodies.update({'historical-inputs/'+p:b for p,b in historical.items()})
            bodies['scope-inputs/workflow-before.yml']=base_workflow
            bodies['scope-inputs/workflow-current.yml']=(SOURCE/'.github/workflows/macos.yml').read_bytes()
        if case_id in ('HISTORICAL_DRIFT_CONTROL','ACTIVE_CENSUS_CONTROL'):
            target='scripts/research/'+('f017_corrected_oracle_primary_target_source_v10.py' if case_id=='HISTORICAL_DRIFT_CONTROL' else 'f017_primary_observed_descriptor_source_v1.py')
            bodies[target]+=b'\n'
        files={};imports={}
        for p,body in bodies.items():
            write(view/p,body,True);files[p]=sha(body)
            if p.endswith('.py') and not p.startswith('historical-inputs/'):
                name=Path(p).stem;need(name not in imports,'IMPORT_NAME_COLLISION');imports[name]=p
        write(area/'tooling/bootstrap54.py',bootstrap);write(area/'tooling/primary_cases54.py',dispatch,True)
        sb=profile(area,root,description['python_framework'])
        write(area/'tooling/baseline.sb',sb)
        public=b'S53_FIXED_PUBLIC_READ\n';write(denied/'public-read.txt',public);write(area/'work/public-read.txt',public)
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(8);acks=[]
        def serve():
            try:
                connection,_=listener.accept()
                with connection:connection.settimeout(2);raw=connection.recv(128);connection.sendall(raw);acks.append(raw.hex())
            except Exception as error:acks.append(type(error).__name__)
        thread=threading.Thread(target=serve);thread.start()
        row=dict(mode='successor',nonce=os.urandom(16).hex(),read_path=str(denied/'public-read.txt'),write_path=str(denied/'negative-write.txt'),allowed_read_path=str(area/'work/public-read.txt'),allowed_write_path=str(area/'work/allowed-write.txt'),endpoint=list(listener.getsockname()),public_nonce=os.urandom(16).hex(),fixture_expected=dict(read_hex=public.hex(),write_hex=b'S53_FIXED_PUBLIC_WRITE\n'.hex()),fixture_identity={},case_id=case_id,view='successor')
        positive={**row,'mode':'positive','case_id':None,'view':None,'write_path':str(denied/'positive-write.txt')}
        st=area.stat();cat=dict(schema='f017.sequence54.catalogue/1',sequence=54,root=str(area),root_identity=dict(dev=str(st.st_dev),inode=str(st.st_ino)),python=python,python_framework=description['python_framework'],bootstrap_sha256=sha(bootstrap),profile_sha256=sha(sb),module_closure_sha256=sha(encode(modules)),api_provenance=description['api_provenance'],rows={'S54-B01-POSITIVE':positive,'S54-B01-SUCCESSOR':row},code_manifests={'successor':dict(files=files,modules=imports)},dispatch_sha256=sha(dispatch))
        raw=encode(cat);need(len(raw)<=LIMIT,'CATALOGUE_BOUND');write(area/'tooling/catalogue54-B01.json',raw)
        child_env={**env,'TMPDIR':str(area/'tmp'),'XDG_CACHE_HOME':str(area/'cache')}
        try:
            result=capture(root,str(number)+'-positive',[python,'-I','-S','-B',str(area/'tooling/bootstrap54.py'),'S54-B01-POSITIVE'],area/'work',child_env)
            need(json.loads(result)['phase']=='POSITIVE_COMPLETE','POSITIVE_CONTROL');thread.join(3);need(not thread.is_alive() and acks==[row['public_nonce'].encode().hex()],'POSITIVE_ACK')
            result=capture(root,str(number)+'-'+case_id,[python,'-I','-S','-B',str(area/'tooling/bootstrap54.py'),'S54-B01-SUCCESSOR'],area/'work',child_env)
            events=[json.loads(line) for line in result.splitlines()];need([e['phase'] for e in events]==['PRE_SEAL','SEAL_APPLIED','FENCE_PASSED','FIXTURE_COMPLETE'],'SEAL_BEFORE_PROJECT_IMPORT')
            need(all(events[2]['detail'][key]['errno'] in (1,13) for key in ('read','write','network')),'ACTUAL_DENIAL_FENCES')
            report=events[-1]['detail']['case_result'];need(report['result']=='PASS','FIXTURE_RESULT');reports.append(dict(case=case_id,report=report,source_census_sha256=sha(encode(files))))
            write(root/'progress'/(str(number)+'.json'),encode(dict(completed=reports[-1],remaining_cases=list(cases[number:]),scope='QUALIFIED_PREFIX_ONLY_UNTIL_FINAL_RESULT')))
        finally:listener.close();thread.join(9)
    result=dict(result='PASS',scope='TRUSTED_SOURCE_MEASUREMENT_AND_SEALED_CURRENT_PRIMARY_PREFIX_ONLY',trusted_preparation=preparation_summary,cases=reports,sealed_fixture_child_starts=1+2*len(cases),runtime_input_source_base=SOURCE_BASE,current_source_head=preparation_report['current_head'],current_source_tree=preparation_report['current_tree'],root=str(root),original_checkpoint_access=0,live_authority_created=False,full_result_success='NOT_QUALIFIED',retained_for_evidence=True)
    write(root/'result.json',encode(result));print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()

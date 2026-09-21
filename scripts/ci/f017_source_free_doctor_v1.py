"""Reusable source-free admission: fixed capture, dependency and denial probes.

No research code is imported or dispatched. Git preparation and native
compile/link qualification are separate authorities, not inferred here.
"""
import hashlib,json,os,pathlib,resource,socket,sys,tempfile,threading
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import f017_preparation_capture_v1 as cap
import f017_doctor_dependency_census_v1 as dependency_census
HERE=pathlib.Path(__file__).resolve().parent
need=cap.need
def profile(area,root,prefix,dependency_root,dependency_package,libraries):
    # Same accepted fixture read/write/network deny policy, plus only the
    # necessary installed NumPy package for post-seal dependency admission.
    reads=['/System/Library','/usr/lib',str(pathlib.Path(prefix)/'bin'),str(area/'tooling'),str(area/'work'),str(area/'tmp'),str(area/'cache')]
    literals=['/dev/null','/dev/urandom','/dev/random',str(pathlib.Path(prefix)/'Python')]
    metadata=set()
    for p in [area,root,pathlib.Path(prefix),pathlib.Path(dependency_root),pathlib.Path(dependency_package)]:metadata.update(str(x)for x in [p,*p.parents])
    for p in libraries:metadata.update(str(x)for x in pathlib.Path(p).parents)
    q=lambda p:json.dumps(str(p))
    rows=['(version 1)','(allow default)','(deny network*)','(deny file-read*)','(deny file-write*)','(deny process-exec)']
    rows+=['(allow file-read* '+' '.join('(subpath '+q(p)+')'for p in reads)+' '+' '.join('(literal '+q(p)+')'for p in literals)+')']
    # Deny rules override narrower allows even through site-packages symlinks.
    # Exclude packages from the stdlib allow, then admit only fixed NumPy.
    rows+=['(allow file-read* (require-all (subpath '+q(pathlib.Path(prefix)/'lib')+') (require-not (subpath '+q(dependency_root)+')) (require-not (subpath '+q(pathlib.Path(prefix)/'lib'/('python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor))/'site-packages')+'))))']
    rows+=['(allow file-read* (subpath '+q(dependency_package)+') (subpath '+q(pathlib.Path(dependency_package).parent/'numpy.libs')+'))']
    rows+=['(allow file-read* '+' '.join('(literal '+q(p)+')'for p in libraries)+')']
    rows+=['(allow file-read-metadata '+' '.join('(literal '+q(p)+')'for p in sorted(metadata))+')']
    rows+=['(allow file-write* (literal "/dev/null") '+' '.join('(subpath '+q(area/p)+')'for p in ['work','tmp','cache'])+')','(allow file-read-data file-test-existence file-write-data (subpath "/dev/fd"))']
    return ('\n'.join(rows)+'\n').encode()
def classify_capture(mode,r,out,err):
    need(r['image_stable']and r['capture_error']is None and not any(r['truncated'].values()),'CAPTURE_INTEGRITY')
    if mode=='missing':need(r['failed_spawn']['errno']==2 and not r['actual_target_start'],'FAILED_SPAWN');return
    need(r['actual_target_start']and r['reaped'],'DIRECT_REAP')
    if mode=='io':need(r['exit_code']==0 and json.loads(out)['fixed_write_read']and not err,'FIXED_IO')
    elif mode=='exit134':need(r['exit_code']==134 and r['signal']is None and out==b'SOURCE_FREE_STDOUT\n'and err==b'SOURCE_FREE_STDERR\n','ORDINARY_134')
    elif mode=='signal6':need(r['signal']==6 and r['exit_code']is None,'SIGNAL_6')
    elif mode=='timeout':need(r['timed_out']and r['reaped'],'TIMEOUT')
    else:raise ValueError('CLOSED_CAPTURE_MODE')
def check(parent):
    need(sys.platform=='darwin'and sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and sys.flags.optimize==0,'ISOLATED_MACOS_ENTRY')
    need(not os.environ.get('PULSARMLX_MODEL_GGUF'),'NO_MODEL_INPUT')
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    root=pathlib.Path(parent);root.mkdir(mode=0o700)
    env={k:os.environ[k]for k in ('HOME','CODEX_HOME','USER','LOGNAME','SHELL')if k in os.environ}
    env.update(PATH='/usr/bin:/bin',LANG='C',LC_ALL='C',TMPDIR=str(root/'tmp'),XDG_CACHE_HOME=str(root/'cache'),PYTHONDONTWRITEBYTECODE='1')
    for name in ('tmp','cache'):(root/name).mkdir(mode=0o700)
    python=str(pathlib.Path(sys.executable).resolve());captures=[]
    for mode in ('io','exit134','signal6','timeout','missing'):
        argv=[python,'-I','-S','-B',str(HERE/'f017_preparation_capture_v1.py'),'--doctor-'+mode]if mode!='missing'else[str(root/'ABSENT_FIXED_DOCTOR')]
        r,out,err=cap.capture(argv,root,'capture-'+mode,env,timeout=.2 if mode=='timeout'else 60,missing_probe=mode=='missing')
        captures.append(r);classify_capture(mode,r,out,err)
    child=(HERE/'f017_source_free_doctor_child_v1.py').read_bytes()
    r,out,err=cap.capture([python,'-I','-S','-B',str(HERE/'f017_source_free_doctor_child_v1.py'),'--describe-source-free'],root,'describe',env)
    captures.append(r);need(r['capture_integrity']=='PASS'and r['exit_code']==0 and not err,'SOURCE_FREE_DESCRIPTION');description=json.loads(out)
    need(description['python']==python,'ACTUAL_INTERPRETER')
    area=root/'probe';denied=root/'denied'
    for p in [area,denied,*[area/n for n in ('tooling','work','tmp','cache')]]:p.mkdir(mode=0o700)
    cap.bank(area/'tooling/bootstrap54.py',child)
    dependencies=dependency_census.census(description['dependency_package']);cap.bank(root/'dependency-census.json',cap.canonical(dependencies))
    sb=profile(area,root,description['python_framework'],description['dependency_root'],description['dependency_package'],dependencies['literal_paths']);cap.bank(area/'tooling/baseline.sb',sb)
    public=b'S53_FIXED_PUBLIC_READ\n';cap.bank(denied/'public-read.txt',public);cap.bank(area/'work/public-read.txt',public)
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(5);acks=[]
    def serve():
        try:
            connection,_=listener.accept()
            with connection:connection.settimeout(2);raw=connection.recv(128);connection.sendall(raw);acks.append(raw.hex())
        except OSError as e:acks.append(type(e).__name__)
    thread=threading.Thread(target=serve);thread.start()
    row=dict(mode='successor',nonce=os.urandom(16).hex(),read_path=str(denied/'public-read.txt'),write_path=str(denied/'negative-write.txt'),allowed_read_path=str(area/'work/public-read.txt'),allowed_write_path=str(area/'work/allowed-write.txt'),endpoint=list(listener.getsockname()),public_nonce=os.urandom(16).hex(),fixture_expected=dict(read_hex=public.hex(),write_hex=b'S53_FIXED_PUBLIC_WRITE\n'.hex()),fixture_identity={},case_id='SOURCE_FREE_DOCTOR',view=None)
    positive={**row,'mode':'positive','case_id':None,'write_path':str(denied/'positive-write.txt')}
    st=area.stat();cat=dict(schema='pulsarmlx.f017.source-free-doctor-catalogue/1',sequence=54,root=str(area),root_identity=dict(dev=str(st.st_dev),inode=str(st.st_ino)),python=python,python_framework=description['python_framework'],dependency_root=description['dependency_root'],dependency_package=description['dependency_package'],bootstrap_sha256=cap.sha(child),profile_sha256=cap.sha(sb),module_closure_sha256=cap.sha(cap.canonical(description['module_closure'])),api_provenance=description['api_provenance'],rows={'S54-B01-POSITIVE':positive,'S54-B01-SUCCESSOR':row},code_manifests={},dispatch_sha256='0'*64)
    raw=cap.canonical(cat);need(len(raw)<=32768,'CATALOGUE_BOUND');cap.bank(area/'tooling/catalogue54-B01.json',raw)
    child_env={**env,'TMPDIR':str(area/'tmp'),'XDG_CACHE_HOME':str(area/'cache')}
    try:
        for label,selector in [('positive','S54-B01-POSITIVE'),('sealed','S54-B01-SUCCESSOR')]:
            r,out,err=cap.capture([python,'-I','-S','-B',str(area/'tooling/bootstrap54.py'),selector],area,label,child_env);captures.append(r)
            need(r['capture_integrity']=='PASS'and r['exit_code']==0 and not err,'CHILD_'+label.upper())
            events=[json.loads(x)for x in out.splitlines()]
            if label=='positive':
                need(events[0]['phase']=='POSITIVE_COMPLETE','POSITIVE');thread.join(3);need(not thread.is_alive()and acks==[row['public_nonce'].encode().hex()],'POSITIVE_NETWORK_ACK')
            else:
                need([e['phase']for e in events]==['PRE_SEAL','SEAL_APPLIED','FENCE_PASSED','FIXTURE_COMPLETE'],'FENCES_BEFORE_DEPENDENCIES')
                need(all(events[2]['detail'][k]['errno']in (1,13)for k in ('read','write','network')),'DENIALS')
                detail=events[3]['detail'];need(detail['project_modules_imported']==0,'SOURCE_FREE')
    finally:listener.close();thread.join(6)
    # Closed argument/error outcome is measured separately from success.
    r,out,err=cap.capture([python,'-I','-S','-B',str(HERE/'f017_source_free_doctor_child_v1.py'),'NOT_A_DOCTOR_ROW'],root,'invalid-entry',env);captures.append(r)
    need(r['exit_code']==1 and b'fixed isolated argv required'in err and not out,'INVALID_ENTRY_REJECTED')
    need(dependency_census.census(description['dependency_package'])==dependencies,'DEPENDENCY_CENSUS_CHANGED')
    result=dict(result='HARNESS_READY',scope='SOURCE_FREE_CAPTURE_AND_POST_SEAL_NUMPY_DEPENDENCY_ONLY',python=cap.image(python),description=description,child_sha256=cap.sha(child),profile_sha256=cap.sha(sb),dependency=detail,dependency_census=dependencies,captures=captures,actual_direct_target_starts=sum(r['actual_target_start']for r in captures),failed_spawn_probes=1,project_numerical_imports=0,original_checkpoint_access=0,live_authority_created=False,native_compile_link='NOT_QUALIFIED',root=str(root),resources_retained=True)
    cap.bank(root/'result.json',cap.canonical(result));return result
def main():
    need(sys.argv[1:]==['--check'],'FIXED_DOCTOR_ENTRY')
    parent=pathlib.Path(tempfile.mkdtemp(prefix='f017-doctor-')).resolve()
    try:result=check(parent/'run')
    except Exception as e:
        result=dict(result='HARNESS_NOT_READY',exception=type(e).__name__,message=str(e),root=str(parent),retained=True)
        cap.bank(parent/'failure.json',cap.canonical(result));print(json.dumps(result,sort_keys=True));return 1
    print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())

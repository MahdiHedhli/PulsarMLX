"""Primary-only admission using the existing bounded capture supervisor.

Run with python -I -S -B and --check. All project imports occur in a sealed
fixed child. General NumPy/secondary/native readiness is not inferred here.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
import f017_preparation_capture_v1 as cap
import f017_primary_stdlib_inputs_v1 as inputs
import f017_primary_stdlib_resource_v1 as bounded

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1]
need = cap.need
GENERATION_FILE = HERE/'f017_primary_stdlib_fixture_v2.json'
GENERATION_SHA256 = 'fd960e1ddc17a6dfe6a9985f7fd0e15f0c5c73d5b3e852cc0b930ddeb857387c'
MODES = ('positive', 'policy-data', 'admission', 'source-mismatch', 'forbidden-import')
PASSIVE_STARTUP_IMAGES = (
    '/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libBLAS.dylib',
    '/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libSparseBLAS.dylib',
)

def readonly(path, raw):
    cap.bank(path, raw)
    Path(path).chmod(0o444)

def profile(area, parent, prefix):
    # Same inherited read/write/network/exec boundary, with no third-party
    # package or additional native-image permissions.
    reads = ['/System/Library', '/usr/lib', str(Path(prefix)/'bin'),
             *[str(area/n) for n in ('tooling', 'work', 'tmp', 'cache')]]
    literals = ['/dev/null', '/dev/urandom', '/dev/random', str(Path(prefix)/'Python')]
    metadata = set()
    for p in (area, parent, Path(prefix)):
        metadata.update(str(x) for x in (p, *p.parents))
    quote = lambda p: json.dumps(str(p))
    rows = ['(version 1)', '(allow default)', '(deny network*)',
            '(deny file-read*)', '(deny file-write*)', '(deny process-exec)']
    rows += ['(allow file-read* '+' '.join('(subpath '+quote(p)+')' for p in reads)
             +' '+' '.join('(literal '+quote(p)+')' for p in literals)+')']
    packages = Path(prefix)/'lib'/('python'+str(sys.version_info.major)+'.'+str(sys.version_info.minor))/'site-packages'
    rows += ['(allow file-read* (require-all (subpath '+quote(Path(prefix)/'lib')
             +') (require-not (subpath '+quote(packages)+'))))']
    rows += ['(allow file-read-metadata '+' '.join('(literal '+quote(p)+')' for p in sorted(metadata))+')']
    rows += ['(allow file-write* (literal "/dev/null") '
             +' '.join('(subpath '+quote(area/n)+')' for n in ('work','tmp','cache'))+')',
             '(allow file-read-data file-test-existence file-write-data (subpath "/dev/fd"))']
    return ('\n'.join(rows)+'\n').encode()

def classify_capture(mode, result, stdout, stderr):
    need(result['image_stable'] and result['capture_error'] is None
         and not any(result['truncated'].values()), 'CAPTURE_INTEGRITY')
    if mode == 'missing':
        need(result['failed_spawn']['errno'] == 2 and not result['actual_target_start'], 'SPAWN_REFUSAL')
        return
    need(result['actual_target_start'] and result['reaped'], 'CHILD_REAPED')
    if mode == 'io':
        need(result['exit_code'] == 0 and not stderr and json.loads(stdout)['fixed_write_read'], 'FIXED_IO')
    elif mode == 'exit134':
        need(result['exit_code'] == 134 and result['signal'] is None
             and stdout == b'SOURCE_FREE_STDOUT\n' and stderr == b'SOURCE_FREE_STDERR\n', 'ORDINARY_EXIT134')
    elif mode == 'signal6':
        need(result['signal'] == 6 and result['exit_code'] is None, 'ACTUAL_SIGNAL6')
    elif mode == 'timeout':
        need(result['timed_out'] and result['reaped'], 'ACTUAL_TIMEOUT')
    else:
        raise ValueError('CLOSED_CAPTURE_CONTROL')

def check(parent):
    need(sys.platform == 'darwin' and sys.flags.isolated and sys.flags.no_site
         and sys.flags.dont_write_bytecode and not sys.flags.optimize, 'ISOLATED_MACOS_ENTRY')
    need(not os.environ.get('PULSARMLX_MODEL_GGUF'), 'NO_MODEL_INPUT')
    resource.setrlimit(resource.RLIMIT_CORE, (0,0))
    root = Path(parent)
    root.mkdir(mode=0o700)
    need(shutil.disk_usage(root).free >= 8*1024**3, 'STORAGE_FLOOR')
    generation_raw = GENERATION_FILE.read_bytes()
    need(cap.sha(generation_raw) == GENERATION_SHA256, 'PROSPECTIVE_GENERATION_IDENTITY')
    current = inputs.census(SOURCE)
    generation = inputs.require_fixture_generation(json.loads(generation_raw), current)
    need(generation['generation']==2 and generation['criteria']['passive_startup_image_policy']['admitted_identifiers']==list(PASSIVE_STARTUP_IMAGES),'FIXED_G2_IMAGE_POLICY')
    cap.bank(root/'input-census.json', cap.canonical(current))
    cap.bank(root/'fixture-generation.json', generation_raw)
    for n in ('tmp','cache'):
        (root/n).mkdir(mode=0o700)
    env = dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C',
               TMPDIR=str(root/'tmp'), XDG_CACHE_HOME=str(root/'cache'),
               PYTHONDONTWRITEBYTECODE='1')
    python = str(Path(sys.executable).resolve())
    captures = []; controls = []
    # Reserve every potential exec-denial child too, even though denial should
    # prevent its start. This is a finite closed plan, not a dynamic test runner.
    reservation = dict(supervisor=1, capture_controls=4, description=1,
                       exec_positive=1, fixed_children=5, possible_exec_denials=4,
                       invalid_entry=1, maximum_target_starts=17)
    cap.bank(root/'target-reservation.json', cap.canonical(reservation))
    def capture(argv, area, label, **kwargs):
        r,out,err = bounded.capture(argv,area,label,env,**kwargs)
        captures.append(r)
        return r,out,err
    for mode in ('io','exit134','signal6','timeout','missing'):
        argv = [python,'-I','-S','-B',str(HERE/'f017_preparation_capture_v1.py'),'--doctor-'+mode] if mode!='missing' else [str(root/'ABSENT_FIXED_DOCTOR')]
        r,out,err = capture(argv,root,'capture-'+mode,timeout=.2 if mode=='timeout' else 60,missing_probe=mode=='missing')
        classify_capture(mode,r,out,err)
        controls.append(dict(control=mode, result='PASS'))
    child = (HERE/'f017_primary_stdlib_child_v1.py').read_bytes()
    r,out,err = capture([python,'-I','-S','-B',str(HERE/'f017_primary_stdlib_child_v1.py'),'--describe-source-free'],root,'describe',limit=131072)
    need(r['capture_integrity']=='PASS' and r['exit_code']==0 and not err,'SOURCE_FREE_DESCRIPTION')
    description=json.loads(out);need(description['python']==python,'ACTUAL_INTERPRETER')
    need(all(description['environment'].get(k)==v for k,v in env.items())
         and not any(k.startswith(('DYLD_','LD_'))for k in description['environment']),'SCRUBBED_STARTUP_ENVIRONMENT')
    startup_baseline=cap.canonical(dict(images=description['loaded_images'],python=python,
        child_sha256=cap.sha(child),generation_sha256=GENERATION_SHA256,
        environment=description['environment'],module_closure_sha256=cap.sha(cap.canonical(description['module_closure']))))
    need(len(startup_baseline)<=32768,'STARTUP_BASELINE_CONTROL_BOUND')
    cap.bank(root/'startup-baseline.json',startup_baseline)
    escape = b"import sys\nassert sys.flags.isolated and sys.flags.no_site\nprint('FIXED_EXEC_CONTROL')\n"
    cap.bank(root/'escape-control.py',escape)
    r,out,err = capture([python,'-I','-S','-B',str(root/'escape-control.py')],root,'exec-positive')
    need(r['capture_integrity']=='PASS' and r['exit_code']==0 and out==b'FIXED_EXEC_CONTROL\n' and not err,'EXEC_POSITIVE')
    reports=[]
    for mode in MODES:
        trial = root/mode; trial.mkdir(mode=0o700)
        area = trial/'sealed'; denied = trial/'denied'
        for p in (area, denied, *[area/n for n in ('tooling','work','tmp','cache')]):
            p.mkdir(mode=0o700)
        view = area/'tooling/codeview'
        for relative in current['files']:
            raw = (SOURCE/relative).read_bytes()
            need(cap.sha(raw)==current['files'][relative], 'SOURCE_CHANGED_DURING_COPY')
            if mode=='source-mismatch' and relative==current['modules']['f017_primary_stdlib_cases_v1']:
                raw += b'\n# fixed identity mutation\n'
            readonly(view/relative,raw)
        files=dict(current['files']); modules=dict(current['modules'])
        if mode=='forbidden-import':
            relative='qualification/primary_incidental_dependency.py';raw=b'import numpy\n'
            readonly(view/relative,raw);files[relative]=cap.sha(raw);modules['primary_incidental_dependency']=relative
        readonly(area/'tooling/child.py',child)
        readonly(area/'tooling/escape-control.py',escape)
        readonly(area/'tooling/startup-baseline.json',startup_baseline)
        sb = profile(area,trial,description['python_framework'])
        readonly(area/'tooling/profile.sb',sb)
        public = b'S53_FIXED_PUBLIC_READ\n'
        cap.bank(denied/'public-read.txt',public);cap.bank(area/'work/public-read.txt',public)
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(3)
        acknowledgements=[]
        def serve():
            try:
                connection,_=listener.accept()
                with connection:
                    connection.settimeout(2);data=connection.recv(128);connection.sendall(data);acknowledgements.append(data.hex())
            except OSError as error:
                acknowledgements.append(type(error).__name__)
        thread=threading.Thread(target=serve)
        if mode=='positive':thread.start()
        row=dict(read_path=str(denied/'public-read.txt'), write_path=str(denied/'write.txt'),
                 allowed_read_path=str(area/'work/public-read.txt'),allowed_write_path=str(area/'work/allowed-write.txt'),
                 endpoint=list(listener.getsockname()),public_nonce=os.urandom(16).hex(),
                 fixture_expected=dict(read_hex=public.hex(),write_hex=b'S53_FIXED_PUBLIC_WRITE\n'.hex()))
        st=area.stat()
        cat=dict(schema='pulsarmlx.primary-stdlib-doctor-catalogue/1',scope='PRIMARY_STDLIB_ONLY',
                 root=str(area),root_identity=dict(dev=st.st_dev,inode=st.st_ino),python=python,
                 python_framework=description['python_framework'],nonce=os.urandom(16).hex(),
                 child_sha256=cap.sha(child),profile_sha256=cap.sha(sb),
                 module_closure_sha256=cap.sha(cap.canonical(description['module_closure'])),
                 api_provenance=description['api_provenance'],row=row,mode=mode,files=files,modules=modules,
                 fixture_generation_sha256=GENERATION_SHA256,
                 startup_baseline_sha256=cap.sha(startup_baseline),passive_startup_images=list(PASSIVE_STARTUP_IMAGES))
        raw=cap.canonical(cat);need(len(raw)<=32768,'CATALOGUE_BOUND');readonly(area/'tooling/catalogue.json',raw)
        try:
            r,out,err = capture([python,'-I','-S','-B',str(area/'tooling/child.py'),'--run-fixed'],area,'fixed')
            need(r['capture_integrity']=='PASS','FIXED_CAPTURE')
            events=[json.loads(line) for line in out.splitlines()]
            if mode=='positive':
                thread.join(3)
                need(not thread.is_alive() and acknowledgements==[row['public_nonce'].encode().hex()], 'POSITIVE_NETWORK_ACK')
                need(r['exit_code']==0 and not err and events[0]['phase']=='POSITIVE_COMPLETE','POSITIVE_CONTROL')
                need(events[0]['detail']==dict(read_hex=public.hex(),write_hex=row['fixture_expected']['write_hex'],ack_hex=row['public_nonce'].encode().hex()),'POSITIVE_VALUES')
            else:
                need([e['phase'] for e in events[:3]]==['PRE_SEAL','SEAL_APPLIED','FENCE_PASSED'],'FENCES_BEFORE_IMPORT')
                need(all(events[2]['detail'][n]['errno'] in (1,13) for n in ('read','write','network','exec')),'ACTUAL_DENIALS')
                if mode=='policy-data':
                    need(r['exit_code']==0 and not err and len(events)==4 and events[3]['phase']=='FIXTURE_COMPLETE','POLICY_CONTROL_COMPLETE')
                    data=events[3]['detail']['policy_controls']
                    need(data['positive']=='PASS' and len(data['refusals'])==11
                         and all(x['result']=='REFUSED'for x in data['refusals']),'POLICY_MUTATIONS_REFUSED')
                elif mode=='source-mismatch':
                    need(r['exit_code']==1 and b'SOURCE_IDENTITY_MISMATCH' in err and len(events)==3,'SOURCE_MISMATCH_REFUSED')
                else:
                    need(r['exit_code']==0 and not err and len(events)==4 and events[3]['phase']=='FIXTURE_COMPLETE','ADMISSION_COMPLETE')
                    detail=events[3]['detail']
                    if mode=='admission':need(detail['case_result']['result']=='PASS','PRIMARY_IMPORT')
                    else:need(detail['expected_refusal']=='UNDECLARED_POST_SEAL_IMPORT:numpy','INCIDENTAL_IMPORT_REFUSED')
            reports.append(dict(mode=mode,result='PASS',events=events))
            cap.bank(root/('completed-'+mode+'.json'),cap.canonical(reports[-1]))
        finally:
            listener.close()
            if thread.ident is not None:thread.join(4)
    r,out,err = capture([python,'-I','-S','-B',str(HERE/'f017_primary_stdlib_child_v1.py'),'INVALID'],root,'invalid-entry')
    need(r['exit_code']==1 and b'FIXED_ENTRY' in err and not out,'INVALID_ENTRY_REFUSAL')
    need(inputs.census(SOURCE)==current,'POST_RUN_SOURCE_RECENSUS')
    result=dict(result='HARNESS_READY',scope='PRIMARY_STDLIB_ONLY_IMPORT_ADMISSION',
                fixture_generation_sha256=GENERATION_SHA256,description=description,
                input_census_sha256=cap.sha(cap.canonical(current)),child_sha256=cap.sha(child),
                controls=controls,reports=reports,captures=captures,
                actual_nested_target_starts=sum(r['actual_target_start'] for r in captures),
                failed_spawn_probes=sum(r['failed_spawn']is not None for r in captures),
                unexpected_exec_children=sum(e.get('detail',{}).get('exec',{}).get('actual_target_start',False)
                    for report in reports for e in report['events'] if e['phase'] in ('FENCE_PASSED','FENCE_FAILED')),
                full_numpy_doctor='NOT_QUALIFIED',primary_composition='NOT_RUN_BY_CHECK',
                secondary_native_full_result='NOT_QUALIFIED',root=str(root),retained=True)
    cap.bank(root/'result.json',cap.canonical(result))
    return result

def main():
    need(sys.argv[1:]==['--check'],'FIXED_DOCTOR_ENTRY')
    parent=Path(tempfile.mkdtemp(prefix='f017-primary-stdlib-')).resolve()
    try:
        result=check(parent/'run')
    except Exception as error:
        result=dict(result='HARNESS_NOT_READY',scope='PRIMARY_STDLIB_ONLY',
                    exception=type(error).__name__,message=str(error),root=str(parent),retained=True)
        cap.bank(parent/'failure.json',cap.canonical(result));print(json.dumps(result,sort_keys=True));return 1
    print(json.dumps(dict(result=result['result'],scope=result['scope'],root=str(parent),
                         result_sha256=cap.sha(cap.canonical(result)),actual_nested_target_starts=result['actual_nested_target_starts']),sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())

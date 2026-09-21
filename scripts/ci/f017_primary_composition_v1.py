"""Fixed prospective primary composition, reusing the qualified doctor's fences.

Run only after the baseline doctor has passed. This entry never installs live
authority; every descriptor is created from tiny owned synthetic fixtures.
"""
import json
import os
from pathlib import Path
import resource
import shutil
import socket
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import f017_primary_stdlib_doctor_v1 as doctor
import f017_primary_stdlib_inputs_v1 as inputs
import f017_primary_stdlib_resource_v1 as bounded
import f017_preparation_capture_v1 as cap

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1]
GENERATION_SHA256 = 'bc8d4faa5dba71d205d5b271f4bfdc754e90fdafcc0682c5ae7b03275590e7c7'
MODES = ('basic-baseline', 'basic', 'wrapper-baseline', 'wrapper', 'faults', 'edges')


def check(root):
    cap.need(sys.platform == 'darwin' and sys.flags.isolated and sys.flags.no_site
             and sys.flags.dont_write_bytecode and not sys.flags.optimize, 'ISOLATED_ENTRY')
    cap.need(not os.environ.get('PULSARMLX_MODEL_GGUF'), 'NO_MODEL_INPUT')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root.mkdir(mode=0o700)
    cap.need(shutil.disk_usage(root).free >= 8*1024**3, 'STORAGE_FLOOR')
    generation_raw = (HERE/'f017_primary_composition_fixture_v1.json').read_bytes()
    cap.need(cap.sha(generation_raw) == GENERATION_SHA256, 'PROSPECTIVE_GENERATION')
    inputs.ROOTS = ('current_composition_cases',)
    current = inputs.census(SOURCE)
    generation = json.loads(generation_raw)
    cap.need(generation['files'] == current['files'] and generation['modes'] == list(MODES), 'FROZEN_SOURCE')
    cap.bank(root/'input-census.json', cap.canonical(current))
    cap.bank(root/'fixture-generation.json', generation_raw)
    for name in ('tmp', 'cache'): (root/name).mkdir(mode=0o700)
    env = dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C', TMPDIR=str(root/'tmp'),
               XDG_CACHE_HOME=str(root/'cache'), PYTHONDONTWRITEBYTECODE='1')
    python = str(Path(sys.executable).resolve())
    child = (HERE/'f017_primary_composition_child_v1.py').read_bytes()
    cap.bank(root/'target-reservation.json', cap.canonical(dict(supervisor=1, description=1,
        fixed_children=6, possible_exec_denials=6, maximum_target_starts=14)))
    captures = []
    def capture(argv, area, label, **kwargs):
        result, out, err = bounded.capture(argv, area, label, env, **kwargs)
        captures.append(result)
        return result, out, err
    r, out, err = capture([python, '-I', '-S', '-B', str(HERE/'f017_primary_composition_child_v1.py'),
                          '--describe-source-free'], root, 'describe', limit=131072)
    cap.need(r['capture_integrity']=='PASS' and r['exit_code']==0 and not err, 'SOURCE_FREE_DESCRIPTION')
    description = json.loads(out)
    cap.need(description['python']==python and all(description['environment'].get(k)==v for k,v in env.items())
             and not any(k.startswith(('DYLD_', 'LD_')) for k in description['environment']), 'ENVIRONMENT')
    baseline = cap.canonical(dict(images=description['loaded_images'], python=python,
        child_sha256=cap.sha(child), generation_sha256=GENERATION_SHA256,
        environment=description['environment'], module_closure_sha256=cap.sha(cap.canonical(description['module_closure']))))
    cap.need(len(baseline)<=32768, 'STARTUP_BASELINE_BOUND')
    cap.bank(root/'startup-baseline.json', baseline)
    reports = []
    for mode in MODES:
        trial=root/mode; trial.mkdir(mode=0o700)
        area=trial/'sealed'; denied=trial/'denied'
        for path in (area, denied, *[area/n for n in ('tooling', 'work', 'tmp', 'cache')]): path.mkdir(mode=0o700)
        view=area/'tooling/codeview'
        for relative, digest in current['files'].items():
            raw=(SOURCE/relative).read_bytes()
            cap.need(cap.sha(raw)==digest, 'SOURCE_CHANGED_DURING_COPY')
            doctor.readonly(view/relative, raw)
        doctor.readonly(area/'tooling/child.py', child)
        doctor.readonly(area/'tooling/escape-control.py', b"print('FORBIDDEN_EXEC_CONTROL')\n")
        doctor.readonly(area/'tooling/startup-baseline.json', baseline)
        sb=doctor.profile(area, trial, description['python_framework'])
        doctor.readonly(area/'tooling/profile.sb', sb)
        public=b'S53_FIXED_PUBLIC_READ\n'
        cap.bank(denied/'public-read.txt', public); cap.bank(area/'work/public-read.txt', public)
        listener=socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(1)
        row=dict(read_path=str(denied/'public-read.txt'), write_path=str(denied/'write.txt'),
            allowed_read_path=str(area/'work/public-read.txt'), allowed_write_path=str(area/'work/allowed-write.txt'),
            endpoint=list(listener.getsockname()), public_nonce=os.urandom(16).hex(),
            fixture_expected=dict(read_hex=public.hex(), write_hex=b'S53_FIXED_PUBLIC_WRITE\n'.hex()))
        st=area.stat()
        cat=dict(schema='pulsarmlx.primary-stdlib-doctor-catalogue/1', scope='PRIMARY_STDLIB_ONLY',
            root=str(area), root_identity=dict(dev=st.st_dev, inode=st.st_ino), python=python,
            python_framework=description['python_framework'], nonce=os.urandom(16).hex(),
            child_sha256=cap.sha(child), profile_sha256=cap.sha(sb),
            module_closure_sha256=cap.sha(cap.canonical(description['module_closure'])), api_provenance=description['api_provenance'],
            row=row, mode=mode, files=current['files'], modules=current['modules'], fixture_generation_sha256=GENERATION_SHA256,
            startup_baseline_sha256=cap.sha(baseline), passive_startup_images=list(doctor.PASSIVE_STARTUP_IMAGES))
        raw=cap.canonical(cat); cap.need(len(raw)<=32768, 'CATALOGUE_BOUND')
        doctor.readonly(area/'tooling/catalogue.json', raw)
        try:
            r, out, err = capture([python, '-I', '-S', '-B', str(area/'tooling/child.py'), '--run-fixed'],
                                  area, 'fixed', limit=12*1024**2)
        finally: listener.close()
        events=[json.loads(line) for line in out.splitlines()]
        cap.need(r['capture_integrity']=='PASS', 'FIXED_CAPTURE')
        cap.need([e['phase'] for e in events[:3]]==['PRE_SEAL','SEAL_APPLIED','FENCE_PASSED'], 'FENCES_BEFORE_IMPORT')
        cap.need(all(events[2]['detail'][name]['errno'] in (1,13) for name in ('read','write','network','exec')), 'ACTUAL_DENIALS')
        cap.need(r['exit_code']==0 and not err and len(events)==4 and events[3]['phase']=='FIXTURE_COMPLETE', 'COMPOSITION_COMPLETE:'+mode)
        cap.need(events[3]['detail']['case_result']['result']=='PASS', 'CASE_RESULT')
        reports.append(dict(mode=mode, result='PASS', events=events))
        cap.bank(root/('completed-'+mode+'.json'), cap.canonical(reports[-1]))
    cap.need(inputs.census(SOURCE)==current, 'POST_RUN_SOURCE_RECENSUS')
    result=dict(result='PRIMARY_PREFIX_COMPOSITION_PASS', scope='TINY_SYNTHETIC_PRIMARY_PREFIX_ONLY',
        full_result_success='NOT_QUALIFIED_EXPECTED_TINY_GEOMETRY_REFUSAL', reports=reports, captures=captures,
        actual_nested_target_starts=sum(r['actual_target_start'] for r in captures),
        generation_sha256=GENERATION_SHA256, root=str(root), retained=True)
    cap.bank(root/'result.json', cap.canonical(result))
    return result


def main():
    cap.need(sys.argv[1:]==['--check'], 'FIXED_COMPOSITION_ENTRY')
    parent=Path(tempfile.mkdtemp(prefix='f017-primary-composition-')).resolve()
    try: result=check(parent/'run')
    except Exception as error:
        result=dict(result='PRIMARY_COMPOSITION_PARTIAL_FAILURE', type=type(error).__name__, message=str(error), root=str(parent), retained=True)
        cap.bank(parent/'failure.json', cap.canonical(result)); print(json.dumps(result,sort_keys=True)); return 1
    print(json.dumps(dict(result=result['result'], root=str(parent), actual_nested_target_starts=result['actual_nested_target_starts']),sort_keys=True))
    return 0


if __name__=='__main__': raise SystemExit(main())

#!/usr/bin/env python3
"""Prospective copied-only diagnostic parent. Not a full-M1a or timing route.

Freeze/run require the physical Studio and a separately delivered operator grant.
This script imports no native module. Run has exactly one candidate child launch,
300 seconds, create-only intent, no retry. Check launches only the bound host grader.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_checks import CONTRACT, confined, admit_report

REPO = Path(__file__).resolve().parents[3]
EXP = 'experiments/packed-affine-adoption/'
BASE = '190c64213135a756f5e3d61059036b9af2d78d7a'
BASE_TREE = '1bd6cf2f01d5a921fd9c402a109f36072721274f'
SCHEMA = 'pulsarmlx.copied-diagnostic-receipt/1'
MODE = 'copied-diagnostic-v1'
SEQUENCE = ['mlp-d128-h64-m1-e0-default-gate', 'mlp-d128-h64-m1-e1-default-gate', 'mlp-d128-h64-m1-e0-default-gate']
SCOPE = {'children':1, 'timeout_seconds':300, 'retry':False, 'diagnostic_only':True, 'M1a_acceptance':False, 'performance_claim':False}
RAW = {'used':1, 'allowed':1, 'execution_authorized':False}
ORIGINALS = {
    'freeze':'3066d1259eff69f174854f26656ef35980365063710709090939cba2adde668a',
    'failure':'92df14656fc1ba9fee6407e46e5b086d022dbed80e3530a616bee9fc8e0e9607',
    'raw_intent':'3f51c7ec0dbf97f454a8290005eb1810148af1986c33f6d9c13ec9fa26a7d5a2',
    'raw_report':'32bd5be256ee4ee58b62c085527e80e455ce777ae3875aa3f461a7ec29dbc086',
}
FIXTURE = '513b8c800be7f1f491d0bfa08748123066e6ef9369cc907e0a2d8475e733e597'
PORTABLE = '26ae22fdf4d90bd7490e10e2abd96d9b16e295e6fd40e8fde7d91c03908e9d45'
REFERENCE = 'c27a9d51f7e2dee014749078ede961659a81ebe926bff644bfe62b9de058e191'
# Only these existing experiment files may differ from the immutable base.
MUTABLE = {EXP+p for p in ('README.md','build.rs','src/lib.rs','native/adoption_bridge.mm',
    'src/bin/adoption-probe/main.rs','src/bin/adoption-probe/native.rs','src/bin/adoption-probe/ffi.rs')}

def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2)+'\n').encode()

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def read(path, limit=8*1024*1024):
    with Path(path).open('rb') as f:
        raw=f.read(limit+1)
    if len(raw)>limit:
        raise ValueError('receipt size bound')
    return json.loads(raw)

def checked(path, expected):
    # Parse the same bytes whose digest was checked.
    with Path(path).open('rb') as f:
        raw=f.read(8*1024*1024+1)
    if len(raw)>8*1024*1024 or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('original receipt bytes missing/changed (sanitized copies are not originals)')
    return json.loads(raw)

def create(path, value):
    with Path(path).open('xb') as f:
        f.write(canonical(value));f.flush();os.fsync(f.fileno())

def git(*args):
    return subprocess.check_output(['git','-C',str(REPO),*args], text=True).strip()

def studio_only():
    if platform.system()!='Darwin' or platform.machine()!='arm64' or os.environ.get('GITHUB_ACTIONS'):
        raise ValueError('physical Studio route required')
    chip=subprocess.check_output(['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'],text=True).strip()
    if chip!='Apple M1 Ultra':
        raise ValueError('physical M1 Ultra required; no MacBook execution')

def validate_originals(values):
    f, failure, intent, raw = (values[k] for k in ('freeze','failure','raw_intent','raw_report'))
    if f['schema']!='pulsarmlx.adoption-host-freeze/1' or f['source_commit']!=BASE or f['source_tree']!=BASE_TREE or f['host_role']!='m1-ultra-studio' or f['contract_sha256']!=CONTRACT:
        raise ValueError('original freeze/source/host identity')
    if f['raw_probe_budget']!={'allowed':1,'used':0}:
        raise ValueError('original prospective raw state')
    for report in (failure, raw):
        for key in ('source_commit','source_tree','binary_sha256','native_libraries'):
            if report['provenance'][key]!=f[key]:
                raise ValueError('crossed original source/native/binary receipt')
        if report['provenance']['loaded_images_verified'] is not True or report['quarantine'] is not True:
            raise ValueError('original evidence flags')
    if failure['native_qualification']!='FAILED' or failure['error']!='native-status-3; ownership uncertain; terminate child':
        raise ValueError('original copied failure')
    if intent!={'attempt':1,'binary_sha256':f['binary_sha256'],'host_role':'m1-ultra-studio'}:
        raise ValueError('raw intent binding')
    if raw['control']!='P-RAW-LENGTH' or raw['outcome']!='outside-contract-acceptance' or raw['qmm_calls']!=0 or raw['status']!=0:
        raise ValueError('unknown original raw ledger')
    return f

def load_originals(paths):
    if set(paths)!=set(ORIGINALS):
        raise ValueError('all four original receipts required')
    values={name:checked(paths[name],digest) for name,digest in ORIGINALS.items()}
    return validate_originals(values)

def source_inventory(commit, tree):
    if git('rev-parse','HEAD')!=commit or git('rev-parse','HEAD^{tree}')!=tree or git('status','--porcelain=v1','--untracked-files=all'):
        raise ValueError('selected source worktree drift; preserve work')
    if git('rev-parse',BASE+'^{tree}')!=BASE_TREE:
        raise ValueError('historical source identity')
    subprocess.run(['git','-C',str(REPO),'merge-base','--is-ancestor',BASE,commit],check=True)
    base=read(REPO/EXP/'diagnostic-source-base-v1.json')
    if len(base)!=53 or len({r['path'] for r in base})!=53:
        raise ValueError('original 53-path manifest')
    for row in base:
        old=subprocess.check_output(['git','-C',str(REPO),'show',BASE+':'+row['path']])
        if len(old)!=row['bytes'] or hashlib.sha256(old).hexdigest()!=row['sha256']:
            raise ValueError('base manifest drift')
        if row['path'] not in MUTABLE and sha(confined(REPO,row['path']))!=row['sha256']:
            raise ValueError('protected source changed')
    for name in git('diff','--name-only',BASE,commit).splitlines():
        if not name.startswith(EXP):
            raise ValueError('outside experiment repair delta')
        # Existing files not explicitly admitted above remain immutable.
        present=subprocess.run(['git','-C',str(REPO),'cat-file','-e',BASE+':'+name],capture_output=True)
        if present.returncode==0 and name not in MUTABLE:
            raise ValueError('unadmitted existing experiment change')
    paths={r['path'] for r in base}|set(git('ls-files',EXP).splitlines())
    return [{'path':name,'bytes':confined(REPO,name).stat().st_size,'sha256':sha(confined(REPO,name))} for name in sorted(paths)]

def inputs(fixture_root, portable, reference):
    manifest=checked(Path(fixture_root)/'manifest.json',FIXTURE)
    p=checked(portable,PORTABLE);r=checked(reference,REFERENCE)
    if p['fixture_manifest_sha256']!=FIXTURE or r['fixture_manifest_sha256']!=FIXTURE or r['portable_sha256']!=PORTABLE:
        raise ValueError('crossed original reference')
    for name,record in manifest['files'].items():
        path=confined(Path(fixture_root),name)
        if sha(path)!=record['sha256']:
            raise ValueError('fixture payload drift')
    rows={c['id']:c for c in manifest['cases']};pre={c['id']:c for c in p['cases']}
    for name in SEQUENCE:
        c=rows[name]
        if (c['D'],c['H'],c['M'],c['role'],c['bits'][0])!=(128,64,1,'gate',4):
            raise ValueError('fixed diagnostic geometry')
    identities={name:pre[name]['receipt']['metadata_snapshot_sha256'] for name in set(SEQUENCE)}
    return manifest,identities

def linkage(path, host_only):
    lines=subprocess.check_output(['/usr/bin/otool','-L',str(path)],text=True).splitlines()[1:]
    if host_only and any(any(s in line.lower() for s in ('libmlx','metal.framework')) for line in lines):
        raise ValueError('host parent/grader/interpreter has native linkage')
    if not host_only and not all(any(s in line for line in lines) for s in ('libmlx.dylib','libmlxc.dylib')):
        raise ValueError('candidate linkage missing required libraries')
    return lines

def native_inputs(prefix, old):
    prefix=Path(prefix).resolve(strict=True);libs={}
    for name in ('libmlx.dylib','libmlxc.dylib','mlx.metallib'):
        p=confined(prefix/'lib',name);libs[name]=sha(p)
    if libs!=old['native_libraries']:
        raise ValueError('native installation changed; no reinstall authorized')
    return libs

def validate_scope(r):
    # Canonical byte comparison keeps bools distinct from integers.
    for key,want in {'schema':SCHEMA,'mode':MODE,'sequence':SEQUENCE,'scope':SCOPE,'raw_probe':RAW,
                     'contract_sha256':CONTRACT,'host_role':'m1-ultra-studio','shipping_default':'copied'}.items():
        if canonical(r.get(key))!=canonical(want):
            raise ValueError('diagnostic mode/scope/raw ledger')
    if any(k in r for k in ('operations','phase','raw_probe_budget','inherited_root','case_id')):
        raise ValueError('full campaign/timing route not admitted')
    if set(r['originals'])!=set(ORIGINALS):
        raise ValueError('missing original receipt')
    for name,digest in ORIGINALS.items():
        if r['originals'][name]['sha256']!=digest:
            raise ValueError('original receipt pin')

def revalidate(r):
    validate_scope(r)
    old=load_originals({k:v['path'] for k,v in r['originals'].items()})
    if str(REPO)!=r['source_root'] or source_inventory(r['source_commit'],r['source_tree'])!=r['source_manifest']:
        raise ValueError('source manifest changed')
    _,identities=inputs(r['fixture_root'],r['portable_report'],r['reference'])
    if identities!=r['metadata_identities'] or native_inputs(r['native_prefix'],old)!=r['native_libraries']:
        raise ValueError('frozen inputs changed')
    for path,expected in [(r['binary'],r['binary_sha256']),(r['rust_grader'],r['rust_grader_sha256']),
        (r['parent'],r['parent_sha256']),(sys.executable,r['python_sha256']),(r['native_build_receipt'],r['native_build_receipt_sha256'])]:
        if sha(path)!=expected:
            raise ValueError('prospective executable/build receipt changed')
    if Path(r['parent']).resolve()!=Path(__file__).resolve() or Path(r['python']).resolve()!=Path(sys.executable).resolve():
        raise ValueError('different parent/interpreter')
    if r['native_build_receipt_sha256']!=old['native_build_receipt_sha256']:
        raise ValueError('crossed native build receipt')
    linkage(r['rust_grader'],True);linkage(sys.executable,True);linkage(r['binary'],False)
    return old

def freeze(a):
    studio_only()
    originals={k:Path(getattr(a,k)).resolve(strict=True) for k in ORIGINALS}
    old=load_originals(originals);manifest,identities=inputs(a.fixture_root,a.portable,a.reference)
    inventory=source_inventory(a.source_commit,a.source_tree)
    root=a.output.resolve()
    if root.is_relative_to(REPO) or any(root.is_relative_to(p.parent) for p in originals.values()):
        raise ValueError('new diagnostic state must be outside source and old campaign')
    r={'schema':SCHEMA,'mode':MODE,'sequence':SEQUENCE,'scope':SCOPE,'raw_probe':RAW,
       'originals':{k:{'path':str(v),'sha256':ORIGINALS[k]} for k,v in originals.items()},
       'contract_sha256':CONTRACT,'host_role':'m1-ultra-studio','shipping_default':'copied',
       'source_commit':a.source_commit,'source_tree':a.source_tree,'source_root':str(REPO),'source_manifest':inventory,
       'source_manifest_sha256':hashlib.sha256(canonical(inventory)).hexdigest(),
       'binary':str(a.binary.resolve(strict=True)),'binary_sha256':sha(a.binary),
       'parent':str(Path(__file__).resolve()),'parent_sha256':sha(__file__),
       'python':str(Path(sys.executable).resolve()),'python_sha256':sha(sys.executable),
       'rust_grader':str(a.rust_grader.resolve(strict=True)),'rust_grader_sha256':sha(a.rust_grader),
       'native_prefix':str(a.native_prefix.resolve(strict=True)),'native_libraries':native_inputs(a.native_prefix,old),
       'native_build_receipt':str(a.native_build_receipt.resolve(strict=True)),'native_build_receipt_sha256':sha(a.native_build_receipt),
       'mlx_commit':old['mlx_commit'],'mlx_c_commit':old['mlx_c_commit'],
       'fixture_root':str(a.fixture_root.resolve(strict=True)),'fixture_manifest_sha256':FIXTURE,
       'portable_report':str(a.portable.resolve(strict=True)),'portable_report_sha256':PORTABLE,
       'reference':str(a.reference.resolve(strict=True)),'reference_sha256':REFERENCE,
       'generator_hashes':{k:manifest[k] for k in ('generator_sha256','original_full_generator_sha256')},
       'dependency_manifest_sha256':sha(REPO/EXP/'dependency-manifest.json'),'metadata_identities':identities,
       'host':{**old['host'],'os':platform.mac_ver()[0]},'output_root':str(root)}
    revalidate(r)
    root.mkdir() # occupied destination always refused, including symlinks
    create(root/'diagnostic-receipt.json',r)
    return {'receipt_sha256':sha(root/'diagnostic-receipt.json'),'native_executions':0,'raw_probe':RAW}

def config_for(r,path):
    c={k:r[k] for k in ('native_libraries','binary_sha256','source_commit','source_tree','host',
        'generator_hashes','dependency_manifest_sha256','fixture_root','fixture_manifest_sha256','metadata_identities')}
    c.update(mode=MODE,arm='copied',sequence=SEQUENCE,diagnostic_receipt=str(path.resolve()),diagnostic_receipt_sha256=sha(path))
    return c

def launch_child(binary, config, output, prefix, root):
    # Single launch, no shell and no inherited loader/tool overrides.
    env={'MLX_ENABLE_TF32':'0','DYLD_LIBRARY_PATH':str(prefix/'lib'),'PULSAR_F020_NATIVE_PREFIX':str(prefix),
         'PATH':'/usr/bin:/bin','HOME':str(root),'TMPDIR':str(root)}
    started=time.monotonic()
    with (root/'copied.stdout').open('xb') as out,(root/'copied.stderr').open('xb') as err:
        try:
            child=subprocess.Popen([str(binary),str(config),str(output)],cwd=REPO,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
        except OSError as e:
            return {'outcome':'SPAWN_FAILED','error':str(e),'elapsed_ms':int((time.monotonic()-started)*1000)}
        create(root/'process.json',{'pid':child.pid,'native_child_attempt':1})
        try:
            code=child.wait(timeout=300)
            outcome=f'EXIT_STATUS {code}' if code>=0 else f'SIGNAL {-code}'
        except subprocess.TimeoutExpired:
            child.kill();code=child.wait();outcome=f'TIMEOUT (SIGKILL sent; reaped status {code})'
        return {'outcome':outcome,'elapsed_ms':int((time.monotonic()-started)*1000),'child_pid':child.pid}

def run(path):
    if os.environ.get('PULSAR_COPIED_DIAGNOSTIC')!='studio-copied-only-v1' or os.environ.get('PULSAR_ADOPTION_PHASE') is not None:
        raise ValueError('explicit copied-only diagnostic selection required')
    studio_only();receipt_hash=sha(path);r=checked(path,receipt_hash);revalidate(r);root=Path(r['output_root'])
    if path.resolve()!=root/'diagnostic-receipt.json':
        raise ValueError('crossed receipt output root')
    for name in ('copied-child','copied.config.json','copied.stdout','copied.stderr','outcome.json','process.json','launch.intent.json','diagnostic-check.json'):
        if os.path.lexists(root/name):
            raise ValueError('occupied diagnostic claim/output; preserve attempt')
    c=config_for(r,path)
    create(root/'launch.intent.json',{'schema':SCHEMA,'receipt_sha256':sha(path),'scope':SCOPE,'raw_probe':RAW,'diagnostic_attempt':1})
    create(root/'copied.config.json',c)
    # Reconcile source/evidence again after intent. A refusal leaves a spent claim.
    revalidate(r)
    if sha(path)!=receipt_hash:
        raise ValueError('diagnostic receipt changed after admission')
    outcome=launch_child(Path(r['binary']),root/'copied.config.json',root/'copied-child',Path(r['native_prefix']),root)
    outcome.update(binary_sha256=r['binary_sha256'],config_sha256=sha(root/'copied.config.json'),receipt_sha256=sha(path))
    create(root/'outcome.json',outcome)
    if outcome['outcome']!='EXIT_STATUS 0':
        raise ValueError('diagnostic child did not succeed; preserve failure, no retry')
    return {'diagnostic_children':1,'raw_children':0,'M1a_acceptance':False,'outcome':outcome['outcome']}

def check_report(r,path):
    root=Path(r['output_root']);report_path=confined(root,'copied-child/run.json');report=read(report_path)
    config=read(confined(root,'copied.config.json'));outcome=read(confined(root,'outcome.json'))
    if config!=config_for(r,path) or outcome['receipt_sha256']!=sha(path) or report['diagnostic_receipt_sha256']!=sha(path) or report['diagnostic_only'] is not True:
        raise ValueError('diagnostic receipt/output binding')
    outputs=admit_report(r,{'copied':(SEQUENCE,'copied','group')},'copied',report,outcome,sha(root/'copied.config.json'))
    if report['decision']!={'M1a_acceptance':False,'performance_claim':False,'shipping_default':'copied'} or report['io']['range_attempts']!=9:
        raise ValueError('diagnostic scope/read count')
    d=report['bridge_diagnostic']
    for key,want in {'snapshot_status':0,'enabled':True,'bridge_refusal':0,'mlx_error_callbacks':0,
        'qmm_graph_enter':3,'qmm_graph_return':3,'evaluation_attempts':3,'evaluation_completions':3,
        'retirement_enter':1,'retirement_complete':1,'close_complete':1,'evidence_write_failed':False}.items():
        if canonical(d[key])!=canonical(want):raise ValueError('incomplete diagnostic stages')
    if d['synchronization_completions']<3 or d['callback']!={'registration_attempted':False,'completed_callbacks':0}:
        raise ValueError('diagnostic synchronization/callback')
    if report['lifetime']['parent_counts']!=[0,0] or report['lifetime']['output_counts']!=[3,3]:
        raise ValueError('copied-only accounting')
    events=[json.loads(line) for line in confined(root,'copied-child/events.jsonl').read_text().splitlines()]
    reads=[v for v in events if v.get('phase')=='source-read-verified-before-native']
    if [v['id'] for v in reads]!=SEQUENCE:raise ValueError('missing pre-native source receipts')
    portable=checked(r['portable_report'],PORTABLE)
    expected={v['id']:v['receipt'] for v in portable['cases']}
    for record in reads:
        if record['receipt']!=expected[record['id']]:raise ValueError('crossed pre-native source receipt')
    if report['io']['requested_bytes']!=sum(expected[name]['requested_bytes'] for name in SEQUENCE):
        raise ValueError('source read byte accounting')
    check_trace(confined(root,'copied-child/bridge-events.jsonl'),d)
    for index,o in enumerate(outputs):
        if o['file']!=f'output-{index}.f32' or o['shape']!=[1,64] or o['dtype']!='F32' or sha(confined(report_path.parent,o['file']))!=o['sha256']:
            raise ValueError('diagnostic output identity')
    if outputs[0]['sha256']!=outputs[2]['sha256']:
        raise ValueError('A-B-A output identity')
    return report_path

def check_trace(path,snapshot):
    # Bounded durable call entry/return pairs from the actual bridge. An empty or
    # arbitrary file cannot stand in for complete diagnostic call evidence.
    with path.open('rb') as f:raw=f.read(192*1024+1)
    if not raw or len(raw)>192*1024:raise ValueError('missing/oversized FFI trace')
    records=[json.loads(line) for line in raw.splitlines()]
    if len(records)>1024 or len(records)!=snapshot['trace_records']:raise ValueError('FFI trace count')
    pending=None;returned=[]
    for e in records:
        if set(e)!={'function','stage','phase','mlx_status','mlx_status_known','bridge_refusal'}:
            raise ValueError('FFI trace schema')
        if any(type(e[k]) is not int for k in ('function','stage','phase','mlx_status','bridge_refusal')) or type(e['mlx_status_known']) is not bool:
            raise ValueError('FFI trace types')
        if not 1<=e['function']<=12 or not 0<=e['stage']<=42 or e['bridge_refusal'] or e['mlx_status']:
            raise ValueError('FFI trace failure/unknown stage')
        pair=(e['function'],e['stage'])
        if e['phase']==1 and pending is None:
            if e['mlx_status_known']:raise ValueError('return status on call entry')
            pending=pair
        elif e['phase']==2 and pending==pair:
            returned.append(pair);pending=None
        else:raise ValueError('unpaired FFI entry/return')
    if pending is not None:raise ValueError('unfinished FFI call')
    # Function 6 = Project; stages 24/25/8/26/27 = QMM/eval/sync/copy/free.
    project=[stage for fn,stage in returned if fn==6 and stage!=23]
    if project!=[24,25,8,26,27]*3:raise ValueError('projection FFI order/coverage')
    if sum(stage==8 for _,stage in returned)!=snapshot['synchronization_completions']:
        raise ValueError('sync trace/snapshot disagreement')

def check(path):
    r=read(path);revalidate(r);root=Path(r['output_root']);report=check_report(r,path)
    for name in ('diagnostic-check.intent.json','diagnostic-check.json','diagnostic-rust-gates.json'):
        if os.path.lexists(root/name):raise ValueError('occupied diagnostic check; no automatic retry')
    create(root/'diagnostic-check.intent.json',{'receipt_sha256':sha(path),'report_sha256':sha(report),'grader_sha256':r['rust_grader_sha256']})
    with (root/'diagnostic-grader.stdout').open('xb') as out,(root/'diagnostic-grader.stderr').open('xb') as err:
        result=subprocess.run([r['rust_grader'],r['portable_report'],str(REPO/'fixtures/native-composition'),str(report),str(root/'diagnostic-rust-gates.json')],stdout=out,stderr=err,timeout=900)
    if result.returncode:raise ValueError('diagnostic Rust reference gate failed')
    # Exact same original-byte numerical rules, only the three selected outputs.
    # No full-population qualifier, mechanism receipt or M1a acceptance is written.
    import reference_budget
    from reference import grade
    reference_budget.start();gates=grade(Path(r['reference']),report)
    result={'schema':'pulsarmlx.copied-diagnostic-check/1','receipt_sha256':sha(path),'report_sha256':sha(report),
        'sequence':SEQUENCE,'scope':SCOPE,'raw_probe':RAW,'G_QMM_RUST':'PASS','exact_gates':gates,
        'rust_gates_sha256':sha(root/'diagnostic-rust-gates.json'),'native_acceptance':False,'performance_claim':False}
    create(root/'diagnostic-check.json',result);return result

def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest='command',required=True)
    f=subs.add_parser('freeze');f.add_argument('--source-commit',required=True);f.add_argument('--source-tree',required=True)
    for name in ('freeze','failure','raw-intent','raw-report','fixture-root','portable','reference','native-prefix','native-build-receipt','binary','rust-grader','output'):
        f.add_argument('--'+name,type=Path,required=True)
    for name in ('run','check'):
        child=subs.add_parser(name);child.add_argument('receipt',type=Path)
    a=p.parse_args();result=freeze(a) if a.command=='freeze' else run(a.receipt) if a.command=='run' else check(a.receipt)
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
    main()

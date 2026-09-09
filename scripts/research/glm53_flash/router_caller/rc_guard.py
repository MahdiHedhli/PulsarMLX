"""Admission for router-caller-v1; content checks are not OS isolation."""
from pathlib import Path
import hashlib,json,sys
SOURCE=Path(__file__).resolve().parents[4]
ROOT=SOURCE.parents[1]
PHASE=ROOT/'router-caller-v1'
OLD=ROOT/'source-environment-v1'
MAX_GROWTH=8*1024**3
RESERVE=512*1024**2
PRE_MANIFEST='1cdccc96505acedb8bca3035b08ee8479c82ae4c425b53ae2f947be20d1fde60'
PRE_IDENTITY='25d1e07ec9d1934aa3d2ab60b985c378eac4aee23ab6dfe236f1db3a80396006'
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def predecessor_identity():
    manifest=PHASE/'evidence/predecessor/phase-manifest.json'
    identity=PHASE/'evidence/predecessor/evidence/source-identity.json'
    if sha(manifest)!=PRE_MANIFEST or sha(identity)!=PRE_IDENTITY:raise ValueError('predecessor authority mismatch')
    j=json.loads(manifest.read_text());row=next(x for x in j['files'] if x['path']=='evidence/source-identity.json')
    if row['sha256']!=PRE_IDENTITY:raise ValueError('predecessor manifest membership mismatch')
    return json.loads(identity.read_text())
def verify_predecessor():
    rows=predecessor_identity()['files']
    if len(rows)!=48:raise ValueError('predecessor source inventory discrepancy')
    for row in rows:
        p=SOURCE/row['path']
        if not p.is_relative_to(SOURCE) or p.resolve()!=p or sha(p)!=row['sha256']:raise ValueError('predecessor source drift')
verify_predecessor()
sys.path.insert(0,str(SOURCE/'scripts/research/glm53_flash/source_environment'))
import guard as inherited
if Path(inherited.__file__).resolve()!=SOURCE/'scripts/research/glm53_flash/source_environment/guard.py':raise ValueError('inherited helper origin mismatch')
def confined(root,path):return inherited.confined(root,path)
def admit_phase(phase):
    if Path(phase).absolute()!=PHASE:raise ValueError('bound router phase role required')
    inherited.admit_phase(OLD)
    for name in ('source','evidence','scratch','cache','fixtures','runs','archives'):
        if not confined(PHASE,PHASE/name).is_dir():raise ValueError('new phase role absent')
    if (PHASE/'runs/STOP_NUMERICAL.json').exists():raise ValueError('unconfirmed termination latch')
    verify_predecessor();return PHASE
def environment_manifest(phase):return OLD/'evidence/environment-manifest-g1.json'
def wheel_lock(phase):return OLD/'evidence/wheel-lock-g1.json'
def verify_environment(phase):
    if Path(phase)!=PHASE:raise ValueError('phase mismatch')
    for p,d in ((environment_manifest(phase),'a09b29f3e874c070e31e4f41cf17adf3fa2b8d2544a1e0849f59ffcdb3974686'),(wheel_lock(phase),'e55cf27f1dd5f3dd244f869931cf77944a4944b5707beb19c93c7eb55d95c90a')):
        if sha(p)!=d:raise ValueError('retained runtime lock drift')
    return inherited.verify_environment(OLD)
def verify_child_interpreter(phase):
    if Path(phase)!=PHASE:raise ValueError('phase mismatch')
    inherited.verify_child_interpreter(OLD)
    if sha(Path(sys.executable).resolve())!='b502cb4c5b46b8d4192ec6bcb600ce8922f1afc396fcf646e8765c6eba74a0bf':raise ValueError('interpreter content drift')
def verify_origin(module,phase,manifest):return inherited.verify_origin(module,OLD,manifest)
def env_python(phase):return OLD/'env-g1/bin/python'
def manifest_digest(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def input_manifest(phase):
    verify_predecessor();paths=[SOURCE/r['path'] for r in predecessor_identity()['files']]
    for rel in ('docs/glm53-flash/router-caller-v1','fixtures/research/glm53-flash-router-caller-v1','scripts/research/glm53_flash/router_caller'):
        paths.extend(p for p in (SOURCE/rel).rglob('*') if p.is_file())
    paths.extend((SOURCE/'scripts/research/tests').glob('test_glm53_flash_router_caller*.py'))
    paths.extend(p for p in (PHASE/'source').rglob('*') if p.is_file())
    paths.extend(PHASE/'evidence'/n for n in ('admission.json','source-node-admission.json','issuance-review-dispositions.json','predecessor-advisories.json','batch-allocation.json','prospective-corrections.json','helper-corrections.json') if (PHASE/'evidence'/n).is_file())
    paths.extend((environment_manifest(phase),wheel_lock(phase)))
    return [{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(confined(ROOT,p))} for p in sorted(set(paths))]
def resolve_input(row):return confined(ROOT,ROOT/row['path'])
def phase_size(phase):
    roots=[PHASE,ROOT/'repos/PulsarMLX-Prompts/GLM53-Flash/router-caller-v1']
    roots.extend(SOURCE/r for r in ('docs/glm53-flash/router-caller-v1','fixtures/research/glm53-flash-router-caller-v1','scripts/research/glm53_flash/router_caller'))
    return sum(p.stat().st_size for d in roots for p in d.rglob('*') if p.is_file() and not p.is_symlink())+sum(p.stat().st_size for p in (SOURCE/'scripts/research/tests').glob('test_glm53_flash_router_caller*.py'))

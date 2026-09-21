"""Phase-owned admission, preserving the verified predecessor read-only."""
from pathlib import Path
import hashlib,json,os,sys
SOURCE=Path(__file__).resolve().parents[4]
ROOT=SOURCE.parents[1]
OLD=ROOT/'source-environment-v1'
PHASE=ROOT/'boundary-completion-v1'
MAX_GROWTH=8*1024**3
RESERVE=512*1024**2
PREDECESSOR_MANIFEST='92a817cc6b21e996630b110a7ec2b13fadff393306e9cb7e288522d4943b2d94'
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def predecessor_identity():
    path=PHASE/'evidence/predecessor/phase-manifest.json'
    if sha(path)!=PREDECESSOR_MANIFEST:raise ValueError('predecessor manifest mismatch')
    manifest=json.loads(path.read_text());row=next(x for x in manifest['files'] if x['path']=='evidence/source-identity.json')
    identity=PHASE/'evidence/predecessor/evidence/source-identity.json'
    if sha(identity)!=row['sha256']:raise ValueError('predecessor source identity mismatch')
    return json.loads(identity.read_text())
def verify_predecessor():
    identity=predecessor_identity()
    if len(identity['files'])!=35:raise ValueError('predecessor input count discrepancy')
    for row in identity['files']:
        path=SOURCE/row['path']
        if path.resolve()!=path or not path.is_relative_to(SOURCE) or sha(path)!=row['sha256']:
            raise ValueError('predecessor source bytes changed')
verify_predecessor()
sys.path.insert(0,str(SOURCE/'scripts/research/glm53_flash/source_environment'))
import guard as inherited_guard
if Path(inherited_guard.__file__).resolve()!=SOURCE/'scripts/research/glm53_flash/source_environment/guard.py':
    raise ValueError('predecessor helper origin mismatch')
def confined(root,path):return inherited_guard.confined(root,path)
def admit_phase(phase):
    phase=Path(phase).absolute()
    if phase!=PHASE:raise ValueError('existing successor phase role required')
    inherited_guard.admit_phase(OLD)
    for name in ('scratch','cache','evidence','source','fixtures','runs'):
        if not confined(PHASE,PHASE/name).is_dir():raise ValueError('successor role absent')
    if (PHASE/'runs/STOP_NUMERICAL.json').exists():raise ValueError('unconfirmed teardown latch')
    verify_predecessor()
    return PHASE
def verify_environment(phase):
    if Path(phase)!=PHASE:raise ValueError('phase mismatch')
    for name,digest in [('wheel-lock-g1.json','e55cf27f1dd5f3dd244f869931cf77944a4944b5707beb19c93c7eb55d95c90a'),('environment-manifest-g1.json','a09b29f3e874c070e31e4f41cf17adf3fa2b8d2544a1e0849f59ffcdb3974686')]:
        if sha(OLD/'evidence'/name)!=digest:raise ValueError('retained environment authority mismatch')
    return inherited_guard.verify_environment(OLD)
def verify_origin(module,phase,manifest):return inherited_guard.verify_origin(module,OLD,manifest)
def verify_child_interpreter(phase):
    if Path(phase)!=PHASE:raise ValueError('successor phase mismatch')
    return inherited_guard.verify_child_interpreter(OLD)
def env_python(phase):return OLD/'env-g1/bin/python'
def environment_manifest(phase):return OLD/'evidence/environment-manifest-g1.json'
def wheel_lock(phase):return OLD/'evidence/wheel-lock-g1.json'
def manifest_digest(rows):return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def input_manifest(phase):
    verify_predecessor()
    paths=[SOURCE/r['path'] for r in predecessor_identity()['files']]
    for directory in ('scripts/research/glm53_flash/boundary_completion','docs/glm53-flash/boundary-completion-v1','fixtures/research/glm53-flash-boundary-completion-v1'):
        paths += [p for p in (SOURCE/directory).rglob('*') if p.is_file()]
    paths += list((SOURCE/'scripts/research/tests').glob('test_glm53_flash_boundary_completion_*.py'))
    paths += [p for p in (PHASE/'source').rglob('*') if p.is_file()]
    paths += [OLD/'source/group_expert_select.capsule.py',OLD/'source/mlx-vlm/mlx_vlm/models/deepseek_v32/language.py',OLD/'evidence/capsule-binding.json',PHASE/'evidence/new-source-lock.json',PHASE/'evidence/stdlib-json-source-excerpts.json',environment_manifest(phase),wheel_lock(phase)]
    return [{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(confined(ROOT,p))} for p in sorted(set(paths))]
def resolve_input(row):return confined(ROOT,ROOT/row['path'])
def phase_size(phase):
    size=sum(p.stat().st_size for p in PHASE.rglob('*') if p.is_file() and not p.is_symlink())
    for directory in ('scripts/research/glm53_flash/boundary_completion','docs/glm53-flash/boundary-completion-v1','fixtures/research/glm53-flash-boundary-completion-v1'):
        size+=sum(p.stat().st_size for p in (SOURCE/directory).rglob('*') if p.is_file())
    private=ROOT/'repos/PulsarMLX-Prompts/GLM53-Flash/boundary-completion-v1'
    size+=sum(p.stat().st_size for p in private.rglob('*') if p.is_file())
    size+=sum(p.stat().st_size for p in (SOURCE/'scripts/research/tests').glob('test_glm53_flash_boundary_completion_*.py'))
    return size

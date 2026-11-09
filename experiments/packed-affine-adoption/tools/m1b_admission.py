"""Read-only admission for a separately authorized physical M1b run. No grader or child."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

EXP = Path(__file__).resolve().parents[1]
PROFILE = EXP / 'm1b-source-profile-v1.json'
S = EXP.parents[1]
CLAIM = 'f020-studio-m1b-screen.claim.json'
ROLES = {'decision', 'contract', 'handoff', 'acceptance', 'controller', 'controller_build',
         'python', 'child', 'native_install', 'timing', 'claim', 'prompt'}
LIMIT = 64 << 20


def need(ok, why):
    if not ok:
        raise ValueError(why)


def equal(x, y, why):
    need(json.dumps(x, sort_keys=True, allow_nan=False) == json.dumps(y, sort_keys=True, allow_nan=False), why)


def keys(obj, expected):
    need(isinstance(obj, dict) and set(obj) == set(expected), 'unexpected or missing fields')


def path(v, existing=True):
    p = Path(v)
    need(p.is_absolute() and str(p) == v and p.resolve(strict=existing) == p, 'noncanonical path')
    if not existing:
        need(p.parent.is_dir(), 'missing parent')
    return p


def data(p, digest=None, size=None, limit=LIMIT):
    p = path(str(p))
    need(p.is_file() and p.stat().st_size <= limit, 'absent or oversized file')
    with p.open('rb') as f:
        raw = f.read(limit + 1)
    need(len(raw) <= limit and (size is None or size == len(raw)), 'file length')
    if digest is not None:
        equal(hashlib.sha256(raw).hexdigest(), digest, 'file digest: '+p.name)
    return raw


def parse(raw):
    def pairs(items):
        d = dict(items)
        need(len(d) == len(items), 'duplicate JSON key')
        return d
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: need(False, 'non-finite JSON'))


def sealed(p, h):
    equal(data(str(p)+'.sha256', limit=512).decode().split(), [h, p.name], 'sidecar')
    return data(p, h)


def environment():
    need(os.environ.get('PULSAR_ADOPTION_PHASE') == 'm1b', 'explicit m1b phase')
    bad = {'PYTHONHOME','PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','GITHUB_ACTIONS',
           'MLX_PREFIX','MLX_C_PREFIX','PULSAR_REQUIRE_NATIVE_MLX','PULSAR_F020_NATIVE_PREFIX',
           'PULSAR_ADOPTION_HOST_ROLE','PULSAR_ADOPTION_CAMPAIGN','PULSARMLX_MODEL_GGUF'}
    need(not (bad & os.environ.keys() or any(k.startswith(('GIT_', 'DYLD_')) for k in os.environ)), 'unsafe inspector environment')


def authority(a, prof):
    keys(a, 'schema purpose phase host_role launch_authorized shipping_default allowances prompt sources added_files paths identities'.split())
    for k,v in dict(schema='pulsarmlx.studio-m1b-authority/1',purpose='STUDIO_M1B_SCREEN_ONCE',
                    phase='m1b',host_role='m1-ultra-studio',launch_authorized=True,shipping_default='copied',
                    allowances={'campaign':1,'raw':0,'numerical':0}).items():
        equal(a[k], v, 'authority: '+k)
    keys(a['paths'], ROLES); keys(a['identities'], 'contract decision controller controller_build python child native_install acceptance handoff profile'.split())
    for k in ('contract','decision','child','python','acceptance'):
        equal(a['identities'][k], prof[k], k+' pin')
    equal(a['identities']['handoff'],prof['public_handoff'],'handoff pin')
    equal(a['identities']['native_install'],'7c2301eb59c037191cd296e3139a7ca4a93e61e27c5e8b05b1ae717888b16523','install pin')
    keys(a['sources'], ['S','C','Q','R'])
    for role,pin in a['sources'].items():
        keys(pin,['root','commit','tree']); path(pin['root'])
        if role != 'S':
            equal({k:pin[k] for k in ['commit','tree']}, prof['sources'][role], 'immutable source '+role)
        for k in ('commit','tree'):need(re.fullmatch('[0-9a-f]{40}',pin[k]),'git identity')
    for v in a['identities'].values():need(re.fullmatch('[0-9a-f]{64}',v),'artifact digest')
    keys(a['prompt'],['commit','filename','sha256'])
    need(re.fullmatch('[0-9a-f]{64}',a['prompt']['sha256']),'prompt digest')
    need(re.fullmatch('[0-9a-f]{40}',a['prompt']['commit']) and
         re.fullmatch(r'(?:00[5-9]|0[1-9][0-9]|[1-9][0-9]{2})__RUST-ENGINE__Mac-Studio-M1-Ultra__[A-Za-z0-9_-]+__prompt\.md',a['prompt']['filename']), 'later physical-Studio prompt required')
    keys(a['added_files'],prof['additions'])
    for v in a['added_files'].values():need(re.fullmatch('[0-9a-f]{64}',v),'added-file digest')


def disjoint(timing, roots):
    for p in roots:
        need(not timing.is_relative_to(p) and not p.is_relative_to(timing), 'overlapping timing state')


def state_locations(install, old_paths, originals, timing, claim):
    equal(str(install), old_paths['native_install'], 'original installation location')
    for k in ('freeze','diagnostic_receipt'):
        equal(parse(data(originals[k]))['native_build_receipt'], str(install), 'historical installation location')
    need(claim == install.parent / CLAIM,'stable timing claim')
    disjoint(timing, [Path(v).parent for v in originals.values()])


def original_files(handoff, acceptance):
    """Resolve public roster *identities* to original Studio bytes, never to display text."""
    p=acceptance['authority']['paths']; ready=acceptance['readiness']; old=acceptance['authority']['original_custody']
    roots={'<CONTROL_ROOT>':Path(ready['authority_path']).parent,'<STATE_ROOT>':Path(p['state']),
           '<OUTPUT_ROOT>':Path(p['output']),'<CAMPAIGN_ROOT>':Path(p['campaign']),
           '<STUDIO001_STATE>':Path(old['native_install']).parent,'<STUDIO002_STATE>':Path(old['diagnostic_receipt']).parent.parent}
    rows=handoff['all_record_identities']; need(len(rows)==862 and len({r['role'] for r in rows})==862,'record population')
    for r in rows:
        root,rel=r['role'].split('/',1); need(not Path(rel).is_absolute() and '..' not in Path(rel).parts,'record path')
        # Only load scientific and campaign/control chain records. Diagnostic logs
        # in other owners' retained directories are not a new source of authority.
        if root in ('<STATE_ROOT>','<OUTPUT_ROOT>','<CAMPAIGN_ROOT>') or rel in (
                'operator-authority.json','operator-authority.json.sha256','originals-map.json',
                'build-identity.json','parent-completion.json'):
            data(roots[root]/rel,r['original_sha256'],r['original_bytes'])
    return roots


def old_claims(install,h):
    for n in ('f020-m1a-continuation.claim.json','f020-studio-m1a-numerical.claim.json'):
        row=h['terminal']['claims'][n]
        data(install.parent/n,row['original_sha256'],row['original_bytes'])


def evidence(a,h,acc,b,mods):
    equal(acc['verdict'],'PASS','original acceptance'); equal(acc['combined_cross_host_decision'],'PENDING','historical decision')
    equal(acc['counts'],b.COUNTS,'physical gate population')
    old=acc['authority']; p=old['paths'];ready=acc['readiness']; f=acc['native_receipt']
    rr=original_files(h,acc)
    equal(parse(data(rr['<STATE_ROOT>']/'ready.json')),ready,'ready')
    bound=parse(data(rr['<STATE_ROOT>']/'bound.json',acc['bound_sha256']))
    equal(bound['receipt'],f,'bound freeze');equal(parse(data(rr['<CAMPAIGN_ROOT>']/'freeze.json',bound['receipt_sha256'])),f,'original freeze')
    equal(parse(data(ready['authority_path'],bound['authority_sha256'])),old,'original authority')
    equal(parse(data(acc['parent_completion']['path'])),acc['parent_completion']['record'],'parent completion')
    equal([acc['parent_completion']['record'][k] for k in ('bound_sha256','reaped','exit_code')],[acc['bound_sha256'],True,0],'successful parent')
    equal(str(rr['<OUTPUT_ROOT>']/'studio-live-m1a-acceptance.json'),a['paths']['acceptance'],'original acceptance custody')
    for role in 'CQR':equal(old['roots'][role],a['sources'][role]['root'],'retained source root')
    originals=old['original_custody'];equal(parse(data(p['originals'])),originals,'original custody')
    install=path(a['paths']['native_install']); timing=path(a['paths']['timing'],False)
    state_locations(install,p,originals,timing,path(a['paths']['claim'],False))
    old_claims(install,h)
    for row in h['original_inputs']:
        rel=Path(row['path'])
        q=(Path(p['fixture_root']).joinpath(*rel.parts[1:]) if rel.parts[0]=='fixtures' else Path({'portable.json':p['portable'],'reference.json':p['reference']}[str(rel)]))
        data(q,row['sha256'],row['bytes'])
    equal(len(h['original_inputs']),46,'input population')
    expected=mods['report_checks'].expected_population(parse(data(Path(p['fixture_root'])/'manifest.json')),
               parse(data(Path(old['roots']['C'])/'fixtures/native-composition/manifest.json')))
    b.gate_counts(acc['reports'],expected)
    ci=b.ci_prerequisite(old['ci_files'],expected);equal(ci,ready['readiness']['ci_prerequisite'],'historical CI prerequisite')
    live=mods['m1a_continuation'];live.original_input_admission(SimpleNamespace(fixture_root=Path(p['fixture_root']),portable=Path(p['portable']),reference=Path(p['reference'])))
    equal(live.original_studio(originals),f['raw_provenance'],'historical original evidence')
    equal(live.host_facts('m1-ultra-studio'),f['host_facts'],'physical Studio')
    equal(live.native_state(Path(p['native_prefix']),install,'m1-ultra-studio'),f['native_state'],'retained static state')
    equal(live.source_inventory(b.C,b.CT),f['source_inventory'],'C2 inventory')
    return rr,p,ready,f


def check_occupancy(stage,timing,claim):
    if stage=='pre':
        need(not os.path.lexists(timing) and not os.path.lexists(claim),'occupied claim/timing root')
    else:
        need(stage=='live' and timing.is_dir() and claim.is_file(),'missing owned state')


def admission(authority_path,digest,stage,controller):
    environment()
    prof=parse(data(PROFILE));ap=path(authority_path); a=parse(sealed(ap,digest));authority(a,prof)
    p=a['paths']; ids=a['identities'];equal(path(p['prompt']).name,a['prompt']['filename'],'later prompt basename')
    prompt_bytes=sealed(path(p['prompt']),a['prompt']['sha256'])
    need(p['prompt'].endswith('/'+a['prompt']['filename']) and
         b'STUDIO_M1B_SCREEN_ONCE' in prompt_bytes and b'phase=m1b' in prompt_bytes,
         'future prompt must explicitly release the physical M1b screen')
    need(a['prompt']['commit'] not in ('156186951baa912cce3403db7b1647b5dec69cb2','f2d11190f68025223942a2c3edbb2e918d7c4192'), 'prior publication cannot authorize timing')
    d=parse(sealed(path(p['decision']),ids['decision']));sealed(path(p['contract']),ids['contract'])
    need(d['M1a_accepted'] and d['M1b_ready_to_prepare'] and not d['M1b_native_execution_authorized'],'planner scope')
    for k in ('python','child','native_install','controller','controller_build','handoff','acceptance'):data(p[k],ids[k])
    data(PROFILE,ids['profile'])
    equal(str(Path(sys.executable).resolve()),p['python'],'selected interpreter')
    equal(controller,p['controller'],'actual controller'); roots={k:path(v['root']) for k,v in a['sources'].items()};need(S==roots['S'] and len(set(roots.values()))==4,'source origins')
    r=roots['R']/ 'experiments/packed-affine-adoption/tools/studio_bridge.py'
    data(r,prof['profile_pins']['tools/studio_bridge.py'])
    spec=importlib.util.spec_from_file_location('m1b_r2_bridge',r);b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
    guard=b.Guard(roots)
    def observe(event, args):
        if event == 'subprocess.Popen':
            exe, argv, cwd, env = args
            if (exe == 'git' and isinstance(argv,(tuple,list)) and len(argv)==7 and
                    list(argv[:3])==['git','--no-optional-locks','-C'] and argv[3] in guard.roots and
                    list(argv[4:])==['remote','get-url','origin'] and env is None):
                equal(b.sha(guard.git),guard.git_hash,'Git executable drift')
                return
        guard.check(event,args)
    sys.addaudithook(observe)
    for root in roots.values():
        equal(b.git(root,'remote','get-url','origin'),'https://github.com/MahdiHedhli/PulsarMLX.git','repository origin')
    oldroots={k:roots[k] for k in 'CQR'}
    source=b.source_identity(oldroots,prof['sources']['R'])
    equal(source['source_delta'],d['source_equivalence']['exact_proof']['source_delta'],'source proof')
    si=a['sources']['S'];equal([b.git(S,'rev-parse','HEAD'),b.git(S,'rev-parse','HEAD^{tree}'),b.git(S,'status','--porcelain=v1','--untracked-files=all')],[si['commit'],si['tree'],''],'S checkout')
    equal(b.git(S,'merge-base',prof['sources']['R']['commit'],si['commit']),prof['sources']['R']['commit'],'S ancestry')
    base=b.objects(roots['R'],prof['sources']['R']['commit']); inv=b.inventory(S,si['commit'])
    need(len(base)==5095 and all({k:inv[n][k] for k in ('mode','blob')}==v for n,v in base.items()),'protected R2 objects')
    equal(sorted(set(inv)-set(base)),sorted(b.EXP+n for n in prof['additions']),'S scope')
    for n,v in a['added_files'].items():equal([inv[b.EXP+n]['mode'],inv[b.EXP+n]['sha256']],['100644',v],'added source')
    mods,origins=b.load_modules(oldroots)
    h=parse(data(p['handoff'],prof['public_handoff']));acc=parse(data(p['acceptance'],prof['acceptance'],3557122))
    old=acc['authority']; op=old['paths'];prefix=path(op['native_prefix'])
    images={str(prefix/'lib'/n) for n in ('libmlx.dylib','libmlxc.dylib','libjaccl.dylib')}
    guard.load_paths.update(images);guard.link_paths.update(images|{p['controller'],*(v['path'] for v in old['executables'].values())})
    rr,op,ready,f=evidence(a,h,acc,b,mods);equal(origins,ready['readiness']['origins'],'module origins')
    build=parse(data(old['build_identity']['path'],prof['build']))
    equal([build['source_commit'],build['source_tree']],[b.C,b.CT],'retained build')
    for k,v in build['executables'].items():
        data(v['path'],v['sha256']);equal(mods['copied_diagnostic'].linkage(v['path'],k!='binary'),build['linkage'][k],'installed linkage')
    equal(build['executables']['binary']['path'],p['child'],'native executable location')
    equal(build['executables']['python']['path'],p['python'],'original Python location')
    cb=parse(data(p['controller_build']));keys(cb,'schema commit tree binary sha256 linkage features artifact_message_sha256 artifact_message'.split())
    link=mods['copied_diagnostic'].linkage(p['controller'],True)
    equal(cb,dict(schema='pulsarmlx.m1b-controller-build/1',commit=si['commit'],tree=si['tree'],binary=p['controller'],sha256=ids['controller'],linkage=link,features=[],artifact_message=cb['artifact_message'],artifact_message_sha256=cb['artifact_message_sha256']),'controller build')
    msg=parse(data(cb['artifact_message'],cb['artifact_message_sha256']));equal([msg['reason'],msg['target']['name'],msg['features'],msg['executable']],['compiler-artifact','m1b-controller',[],p['controller']],'controller cargo artifact')
    timing=path(p['timing'],stage!='pre'); claim=path(p['claim'],stage!='pre')
    disjoint(timing,[*roots.values(),prefix,*rr.values(),Path(op['fixture_root']),Path(op['portable']).parent,Path(op['reference']).parent,ap.parent,*(Path(p[k]).parent for k in ('controller','controller_build','contract','decision','handoff','prompt'))])
    check_occupancy(stage,timing,claim)
    equal(msg['target']['src_path'],str(EXP/'src/bin/m1b-controller.rs'),'Cargo S source')
    equal(msg['manifest_path'],str(EXP/'Cargo.toml'),'Cargo S manifest')
    equal([msg['target']['kind'],msg['profile']['test'],msg['profile']['opt_level']],[['bin'],False,'3'],'release host artifact')
    templates={}
    for label,cid in [('group-8','full-positive-A-gate'),('group-11','full-positive-B-up')]:
        root=rr['<CAMPAIGN_ROOT>']/'m1a'; config=parse(data(root/(label+'-copied.config.json')))
        ev=[parse(x) for x in data(root/(label+'-copied/events.jsonl')).splitlines()]
        out=[v for v in acc['outputs'] if v['id']==cid]
        need(len(out)==2 and {v['arm'] for v in out}=={'copied','adopted'} and len({v['sha256'] for v in out})==1,'paired qualified output')
        templates[cid]=dict(config=config,output=out[0]['sha256'],preflight=next(v for v in ev if v.get('phase')=='original-preflight'),fill=next(v for v in ev if v.get('phase')=='verified-fill'),setup=next(v for v in ev if v.get('phase')=='setup'))
    return dict(schema='pulsarmlx.m1b-admitted/1',authority=digest,identities=ids,sources=a['sources'],added_files=a['added_files'],native_state=f['native_state'],host=f['host_facts'],source_proof=source['source_delta'],qualified=templates,claim=str(claim),timing=str(timing),prefix=str(prefix),child=p['child'],controller=p['controller'])


if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('authority');pa.add_argument('digest');pa.add_argument('stage',choices=['pre','live']);pa.add_argument('controller')
    args=pa.parse_args()
    print(json.dumps(admission(args.authority,args.digest,args.stage,args.controller),sort_keys=True,allow_nan=False))

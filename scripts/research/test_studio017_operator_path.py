"""Physical operator-path control. The test redirects fixed paths into an empty private fixture.
It substitutes the external evidence and numerical payload at their boundaries. No real model,
review, grant, eligibility result or campaign directory is used. The actual local manifest,
exclusive claim, bootstrap, ACK, monitor, guardian and original exit records are exercised.
"""
import contextlib
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import studio017_supervise as s
import studio017_operator as op


def require_fixture(d):
    d = s.path(d)
    s.need(d.parent.parent == s.USER_HOME / 'LocalWorktrees/PulsarMLX-studio017-state'
           and d.parent.name.startswith('operator-amendment-') and d.name == 'synthetic-operator',
           'only the designated synthetic fixture')
    return d


def worker(cap, peer):
    """A nonnumerical worker with no model reader. It calls the real ACK helper in a child."""
    d = require_fixture(cap.parent.parent)
    s.need(cap == d/'campaign-reference/child-cap.json' and not Path(peer).is_relative_to(cap.parent), 'fixture paths')
    try:
        Path(peer).read_bytes()
    except PermissionError:
        pass
    else:
        raise ValueError('peer data was visible')
    channel = int(os.environ['STUDIO017_ADMIT_CHANNEL'])
    child = subprocess.run([sys.executable, '-I','-B','-S',__file__, 'helper',str(cap)], pass_fds=(channel,),
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=True)
    q = s.parse(child.stdout)
    s.need(q['stage']=='reference' and q['model_root']==str(d/'surrogate-model') and
           not any(k in q for k in ('golden','grant','authorization')), 'fixture helper response')
    print('synthetic operator admitted; peer read denied', flush=True)


def helper(cap):
    d = require_fixture(cap.parent.parent)
    s.need(cap == d/'campaign-reference/child-cap.json', 'fixture helper only')
    with patch.object(s,'STATE',d),patch.object(s,'ANCHORS',{'reference': d/'reference.claim'}):
        sys.stdout.buffer.write(s.enc(s.child(str(cap))))


def refused(fn, types=(ValueError,FileNotFoundError,FileExistsError)):
    try:fn()
    except types as error:return type(error).__name__+': '+str(error)
    raise AssertionError('unexpected acceptance')


def control(root, policy_file):
    root=s.path(root); real_state=s.STATE; repo=SCRIPTS.parents[1]
    d=root/'synthetic-operator';d.mkdir(mode=0o700);require_fixture(d)
    names={r:d/(r+'.claim') for r in s.ROLES}; reals=dict(s.ANCHORS)
    s.need(not any(os.path.lexists(f) for f in reals.values()),'real claim already present')
    py=s.doc(policy_file)['interpreter'];polrow=dict(path=str(policy_file),sha256=s.digest(policy_file))
    real_files=s.doc(real_state/'runtime-files.json');native=s.doc(root/'release-build/artifact.json')
    py_image=s.procpath(os.getpid());prefix=next(Path(i['path']).parent.parent for i in real_files.values()
                                                if i['path'].endswith('/libmlx.dylib'))
    ds=d/'surrogate-model';ds.mkdir(mode=0o700)
    cr=d/'checkpoint-receipts';cr.mkdir(mode=0o700)
    for n in ('receipt','inventory','witnesses'):s.put(cr/(n+'.json'),{})
    peer=d/'peer-golden-sentinel';s.put(peer,{'synthetic':'denied'})
    real_resource=real_state/'resources-with-grade-reserve.json'
    src=s.source(repo)
    rs=dict(program=py,driver=str(SCRIPTS/'studio017_ref_entry.py'),image=py_image,python=py,
            array_roots=[],library_prefix=str(prefix))
    # GitHub, review and the payload are external to this fixture. No affirmative review is manufactured.
    for n in ('ci','unavailable','control'):s.put(d/(n+'.json'),{'id':1} if n=='ci' else {'fixture':n})
    c=dict(schema='studio017-operator-config/1',mode=op.MODE,run=op.RUN,repo=str(repo),source=src,
           checkpoint=str(cr),build_root=str(d/'fixture-build'),input=str(real_state/'frozen-input.json'),
           criteria=str(SCRIPTS/'studio017_ref_criteria.py'),resource=str(real_resource),review=str(d/'unavailable.json'),
           ci=str(d/'ci.json'),controls=str(d/'control.json'),runtime_files=real_files,stages={'reference':rs,'native':
           dict(rs,program=native['binary'],image=native['binary'],driver=None)},prior_claims={},controls_runtime_sha256='0'*64,
           build=str(root/'release-build/artifact.json'),artifacts={'python-policy':polrow,'operator-amendment':
           dict(path=str(root/'amendment.txt'),sha256=s.digest(root/'amendment.txt')),'operator-lifecycle':
           dict(path=str(d/'control.json'),sha256=s.digest(d/'control.json'))})
    (d/'fixture-build').mkdir(mode=0o700)
    f=d/'operator-campaign-config.json';s.put(f,c)
    def facts(cfg,role):
        return dict(stage=role,run=cfg['run'],attempt='initial',source=src,revision=s.MODEL,children=1,
                    one_cold_input=True,input_sha256=s.digest(cfg['input']),criteria_sha256=s.digest(cfg['criteria']),
                    resource_sha256=s.digest(real_resource),config_sha256=s.digest(f),limits=s.doc(real_resource)[role])
    original_profile=s.profile
    def argv(cfg,stage,role,cap,out,operation,binding):
        s.need(role=='reference' and cap.parent.parent==d,'fixture may launch only its own reference surrogate')
        return [py,'-I','-B','-S',__file__,'worker',str(cap),str(peer)]
    def proof_stop(check_dir):
        s.need(Path(check_dir)==cr,'fixture checkpoint')
        raise ValueError('fixture stop after original monitor exit and clean reap')
    def acceptance_gate(cfg):
        # Exercise the real CPU/resource/lease checks below; review coverage is independently tested.
        s.need(cfg==c and cfg['checkpoint']==str(cr),'fixture lifecycle edge')
    reasons={}
    with contextlib.ExitStack() as stack:
        for obj,attribute,value in [(s,'STATE',d),(op,'STATE',d),(s,'ROOT',ds),(s,'ANCHORS',names),
                (s,'facts',facts),(op,'validate_ci',lambda *args,**kwargs:None),(s,'lifecycle_gate',acceptance_gate),
                (s,'ref_entry',argv),(s,'checkpoint',proof_stop)]:
            stack.enter_context(patch.object(obj,attribute,value))
        reasons['explicit-mode']=refused(lambda:s.load_cfg(str(f)))
        s.need(s.load_cfg(str(f),True)==c,'operator mode')
        reasons['reference-before-native']=refused(lambda:s.freeze_operator(c,'native'))
        ref_id=s.freeze_operator(c,'reference');manifest=op.manifest_path('reference')
        expected=s.bound_envelope(c,'reference');s.need(ref_id==op.verified_manifest(c,'reference',expected),'frozen fixture')
        reasons['wrong-source']=refused(lambda:op.verified_manifest(dict(c,source=dict(src,head='0'*40)),'reference',expected))
        reasons['wrong-role']=refused(lambda:op.verified_manifest(c,'native',expected))
        # Lower-level strict paths remain closed even if a correct local manifest exists.
        reasons['strict']=refused(lambda:s.require_external_spend_authority('reference'))
        reasons['strict-lifecycle']=refused(s.physical_lease_hold)
        err=refused(lambda:s.run_numeric(str(f),'reference',True))
        s.need(err.endswith('fixture stop after original monitor exit and clean reap'),err)
        role_dir=d/'campaign-reference'
        end=s.doc(role_dir/'numeric-exit.json');active=s.doc(role_dir/'active.json');admit=s.doc(role_dir/'admitted.json')
        s.need(end['exit']==0 and end['completed'] and end['clean_reap'] and end['child_admitted']
               and not end['residual_group_killed'] and end['guardian_exit']==0 and not s.members(end['pid']),
               'original synthetic monitor or reaping')
        s.audit_consumed_stage(c,'reference')
        claim=s.doc(names['reference']);bytes_before=s.read(names['reference'])
        s.need(claim['authorization']==ref_id and claim['operation']==end['operation']==admit['operation']
               and end['pid']==admit['worker']==active['child'] and not (role_dir/'sealed.json').exists(),
               'bound original fixture claim')
        reasons['duplicate-claim']=refused(lambda:s.run_numeric(str(f),'reference',True))
        reasons['exclusive-create']=refused(lambda:s.spend_operator(c,'reference',expected,ref_id,
                                          uuid.uuid4().hex,role_dir/'child-cap.json'),(FileExistsError,))
        reasons['incomplete-reference']=refused(lambda:s.freeze_operator(c,'native'))
        s.need(s.read(names['reference'])==bytes_before and not names['native'].exists(),'replay changed original fixture')
        s.need((role_dir/'stdout').read_bytes().strip()==b'synthetic operator admitted; peer read denied','read isolation')
        # Read a synthetic golden under the actual native sandbox profile, with its normal read roots.
        gold=role_dir/'output'/'synthetic-golden';s.put(gold,{'never':'visible to native'})
        nd=d/'campaign-native';nd.mkdir();no=nd/'output';no.mkdir();cap=nd/'child-cap.json'
        dest=d/'native-visibility.sb';dest.write_bytes(original_profile(c,'native',cap,no,names['native']))
        code="import pathlib,sys\ntry:pathlib.Path(sys.argv[1]).read_bytes()\nexcept PermissionError:sys.exit(0)\nelse:sys.exit(9)"
        probe=subprocess.run(['/usr/bin/sandbox-exec','-f',str(dest),py,'-I','-B','-S','-c',code,str(gold)],
                             stdin=subprocess.DEVNULL,capture_output=True,timeout=12)
        s.need(probe.returncode==0,repr(probe.stderr))
        samples=[s.parse(z) for z in (role_dir/'monitor.jsonl').read_bytes().splitlines()]
        s.need(any(x['pressure']==1 and x['job_children']>=1 for x in samples),'original physical resource sample')
        limits=expected['limits'];ph=s.pressure()
        s.need(not s.ha_ok(dict(ph,pressure=2),limits,ph,0,0,0) and
               not s.ha_ok(dict(ph,headroom=16*s.GIB-1),limits,ph,0,0,0) and
               not s.ha_ok(ph,limits,ph,0,limits['combined']+1,0),'resource refusals')
    s.need(not any(os.path.lexists(x) for x in reals.values()),'real claims changed')
    s.put(d/'result.json',dict(head=src['head'],tree=src['tree'],real_claims=0,passed=True,
          checks={k:True for k in op.REQUIRED_ADMISSION},refusals=reasons,synthetic_role='reference',claim_sha256=s.digest(names['reference']),
          original_operation=end['operation'],original_pid=end['pid'],monitor_samples=len(samples),original_exit=end,
          no_real_stage=True,scope='Real operator manifest/claim/ACK/monitor path under temporary roots. Review, CI and numerical payload substituted; isolated reference/native computations not run.'))


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='worker':worker(Path(sys.argv[2]),sys.argv[3])
    elif mode=='helper':helper(Path(sys.argv[2]))
    elif mode=='control':control(Path(sys.argv[2]),Path(sys.argv[3]))
    else:raise ValueError('private control command')

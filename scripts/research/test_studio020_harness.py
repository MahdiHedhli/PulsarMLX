"""CLI-only sandboxed synthetic grade gate, guardian, reap and replay controls.

Usage: POLICY POLICY_SHA RESOURCE FRESH_OP32
Creates only STATE/synthetic-grade-OP, never either real claim or pairwise-grade.
Production grade_original claim order has separate mocked unit controls. This
wrapper supplies synthetic cap/claim/intent; it does not establish real admission.
Retained Studio019 physical sampled-harness-to-partial-grade evidence still covers
that unchanged composition; this control targets the changed020 grade gate.
"""
from pathlib import Path
import contextlib
import os
import subprocess
import sys
import time
from unittest.mock import patch


def run(policy_file,policy_sha,resource_file,op):
    import studio020_supervise as s
    import studio020_py_gate as gate
    import studio019_grade as grade
    import test_studio019_grade as synthetic
    s.hexid(op,32);s.checked(Path(policy_file),policy_sha)
    pol=gate.binding(policy_file,policy_sha);gate.validate(pol,True)
    s.need(pol['task']==s.TASK and pol['roots'][3]==str(s.SELF.parent),'fixture policy')
    base=s.STATE/('synthetic-grade-'+op)
    s.need(not os.path.lexists(base),'fresh fixture namespace')
    s.need(s.doc(Path(resource_file))['native']==s.operator.NATIVE_LIMITS,'frozen native resource ledger')
    anchors=dict(s.ANCHORS);before={k:(s.digest(p) if p.exists() else None) for k,p in anchors.items()}
    base.mkdir(mode=0o700);(base/'reference').mkdir();(base/'native').mkdir()
    ref=base/'reference/output';native=base/'native/output'
    # Full557-coordinate geometry from constants. No model/reference files read.
    with patch.object(synthetic,'GEOMETRY',grade.original.REAL):
        synthetic.synthetic(ref,'reference');synthetic.synthetic(native,'native')
    native.chmod(0o700);(native/'00.state.offset.f32').unlink();native.chmod(0o500)
    cfg=dict(artifacts={'python-policy':dict(path=str(policy_file),sha256=policy_sha)},
             source=pol['source'],stages={'reference':{'python':pol['interpreter']}})
    inputs=[str(ref),str(native)]
    intent=dict(operation=op,numeric_operation=s.OPERATIONS['native'],run=s.RUN,source=pol['source'],
                python_policy=str(policy_file),python_policy_sha256=policy_sha,
                python_interpreter=pol['interpreter'],arguments=inputs)
    s.put(base/'grade-intent.json',intent)
    claim=dict(schema='studio020-fixture-grade-claim/1',**intent,intent_sha256=s.digest(base/'grade-intent.json'))
    s.put(base/'fixture-grade-claim.json',claim)
    s.put(base/'fixture-grade-cap.json',dict(schema='studio020-fixture-grade-cap/1',synthetic=True,task=s.TASK,
           source=pol['source'],operation=op,intent_sha256=s.digest(base/'grade-intent.json'),claim_sha256=s.digest(base/'fixture-grade-claim.json')))
    gate.fresh_cache(base/'cache-fixture-grade')
    receipt=gate.rolepath(base,'fixture-grade')
    argv=gate.cli(pol['interpreter'],base/'cache-fixture-grade',gate.SELF,'fixture-grade',policy_file,policy_sha,receipt,op,inputs)
    profile=s.aux_profile_file(cfg,base,'fixture-grade',inputs)
    cl=s.COMPARISON_LIMITS;baseline=s.pressure();s.need(baseline['pressure']==1 and baseline['headroom']>=cl['launch_headroom'],'fixture grade headroom')
    started=time.monotonic();deadline=started+cl['timeout'];proc=lease=None;success=False;clean=False;left=False;bad=0
    r,w=os.pipe()
    with (base/'grade.stdout').open('xb') as so,(base/'grade.stderr').open('xb') as se:
        try:
            proc=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(profile),*argv],stdin=subprocess.DEVNULL,
                    stdout=so,stderr=se,pass_fds=(r,),process_group=0,cwd=str(s.SELF.parents[2]),
                    env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','STUDIO017_GRADE_GATE':str(r),
                         'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1'})
            os.close(r);r=-1
            lease=s.attach_guard(cfg,base,proc,deadline,op,'lease-grade',se)
            os.write(w,b'G');os.close(w);w=-1
            while proc.poll() is None:
                lease.pulse();ph=s.pressure();rows=s.cohort()
                rss=sum(x[3]*1024 for x in rows if x[2]==proc.pid or x[0]==os.getpid())
                bad=bad+1 if ph['swap']-baseline['swap']>cl['swap_growth'] else 0
                s.need(ph['pressure']==1 and ph['headroom']>=cl['headroom'] and rss<=cl['combined'] and
                       bad<cl['swap_samples'] and time.monotonic()<deadline and so.tell()<=cl['log_bytes'] and se.tell()<=cl['log_bytes'],'fixture grade resource/time')
                time.sleep(.25)
            success=proc.returncode==0 and time.monotonic()<deadline
        finally:
            if r>=0:os.close(r)
            if w>=0:os.close(w)
            if proc is not None:left,clean=s.end_owned(proc,lease,success)
            s.put(base/'grade-exit.json',dict(operation=op,pid=proc.pid if proc else None,exit=proc.returncode if proc else None,
                  clean_reap=clean,residual_group_killed=left,guardian_exit=lease.guard.returncode if lease else None))
        s.need(success and clean and not left and so.tell()<=cl['log_bytes'] and se.tell()<=cl['log_bytes'],'fixture grade positive reap/output')
    gate.checked_receipt(base,'fixture-grade',op,proc.pid,policy_sha,pol,os.getpid())
    gate.checked_receipt(base,'lease-grade',op,lease.guard.pid,policy_sha,pol,os.getpid())
    result=s.doc(base/'grade.stdout')
    s.need(result['complete'] is False and result['qualified'] is False and result['stages']['00.state.offset.f32'] is None and
           len(result['stages'])==557 and result['stages']['logits.f32']['outside']==0,'fixture complete partial comparison')
    original=s.digest(base/'fixture-grade-claim.json')
    try:s.put(base/'fixture-grade-claim.json',claim)
    except FileExistsError:pass
    else:raise AssertionError('fixture claim replay accepted')
    s.need(s.digest(base/'fixture-grade-claim.json')==original,'fixture claim changed')
    after={k:(s.digest(p) if p.exists() else None) for k,p in anchors.items()}
    s.need(before==after,'real numerical claims changed')
    s.put(base/'result.json',dict(operation=op,passed=True,synthetic=True,real_claims_created=0,model_reads=0,
          complete=False,qualified=False,seconds=time.monotonic()-started,real_claims_unchanged=True,
          scope='actual020 fixture grade binding, sandbox, unchanged fullgeometry grader and guardian; synthetic authority wrapper; real production claim ordering covered separately',
          grade_sha256=s.digest(base/'grade.stdout')))
    print((base/'result.json').read_text(),end='')


if __name__=='__main__':
    if len(sys.argv)!=5:raise SystemExit('POLICY POLICY_SHA RESOURCE FRESH_OP32')
    run(*sys.argv[1:])

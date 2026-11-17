"""Synthetic-only isolated-runtime discriminators; no checkpoint access, model claim, or grant path."""
import json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import studio019_py_gate as g

def run(policy_path,expected_sha,ledger):
    p=g.binding(policy_path,expected_sha);g.validate(p,True)
    g.need(p["task"]==g.TASK and p["roots"][3]==str(HERE),"Studio019 synthetic runtime source")
    out=Path(ledger);g.real(out.parent);g.need(out.is_absolute() and not os.path.lexists(out),"fresh absolute private synthetic ledger");out.mkdir(0o700)
    def trial(n,doc,path,dig,success,reason,gate_path=None,isolated=True):
        role="control";d=out/n;d.mkdir(0o700);cp=d/'cache-control';g.fresh_cache(cp)
        receipt=g.rolepath(d,role)
        cmd=g.cli(p['interpreter'],cp,gate_path or HERE/'studio019_py_gate.py',role,path,dig,receipt,n,['imports'])
        if not isolated:cmd.remove('-I')
        sbpl=None
        if n=="positive":
            # Exercise the production SBPL compiler with a fake model root and grant-free data.
            # Only this synthetic-only "control" receipt and prefix need additional exact literals.
            import studio019_supervise as sup
            fake=out/'empty-fixture';fake.mkdir(0o700);cap=out/'fixture-cap.json';g.put(cap,{"fixture":True})
            rc=dict(program=p['interpreter'],image=sup.procpath(os.getpid()),python=p['interpreter'],library_prefix='/usr/lib',array_roots=[])
            cfg=dict(artifacts={'python-policy':dict(path=str(path),sha256=dig)},stages={'reference':rc,'native':rc},repo=str(HERE),checkpoint=str(fake),input=str(cap),source=p['source'])
            root=sup.ROOT
            try:
                sup.ROOT=fake;profile=sup.profile(cfg,'native',cap,d,out/'absent-fixture-claim')
            finally:sup.ROOT=root
            extra=(chr(10)+'(allow file-read* (subpath '+json.dumps(str(cp))+'))'+chr(10)+'(allow file-read* file-write* (literal '+json.dumps(str(receipt))+'))'+chr(10)).encode()
            sb=d/'fixture.sb'
            with sb.open('xb') as f:f.write(profile+extra)
            sbpl=g.h(g.raw(sb));cmd=['/usr/bin/sandbox-exec','-f',str(sb),*cmd]
        with (d/'stdout').open('xb') as so,(d/'stderr').open('xb') as se:
            proc=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1'},stdout=so,stderr=se)
            try:ret=proc.wait(timeout=20)
            except BaseException:proc.kill();proc.wait();raise
        msg=g.raw(d/'stderr')
        if success:
            assert ret==0,(ret,msg[-1000:]);sha=g.checked_receipt(d,role,n,proc.pid,dig,doc,os.getpid())
        else:
            assert ret!=0 and reason.encode() in msg and (not receipt.exists() or json.loads(g.raw(receipt))['status']=='refused'),(ret,msg[-1000:])
            sha=g.h(g.raw(receipt)) if receipt.exists() else None
        g.put(d/'decision.json',dict(synthetic=True,operation=n,pid=proc.pid,returncode=ret,sha256=dig,isolated_flags=(["-I"] if isolated else [])+["-B","-S","-X","pycache_prefix="+str(cp)],sbpl_sha256=sbpl,runtime_receipt_sha256=sha,stderr_sha256=g.h(msg),expected_refusal=None if success else reason))
        print('PASS:',n,'closed observed census' if success else 'refused as designed')
    trial("positive",p,policy_path,expected_sha,True,None)
    # Remove the actually loaded BLAS image from a fixture policy before starting its positive-shaped child.
    altered=dict(p,images={k:v for k,v in p['images'].items() if "libopenblas" not in Path(k).name})
    assert len(altered['images'])<len(p['images']);bad=out/'missing-image.json';g.put(bad,altered)
    trial("unlisted-image",altered,bad,g.h(g.wire(altered)),False,"unlisted/changed dyld image")
    # Mutate only a completely private miniature array installation, never the pinned real one.
    arr=out/'array-fixture';(arr/'numpy').mkdir(parents=True,mode=0o700);(arr/'numpy/__init__.py').write_text("# inventory-only fixture\n")
    mini=dict(p,roots=g.layout(p['roots'][0],arr,p['roots'][3]));mini['inventory_sha256'],mini['modules']=g.inventory(mini['roots'])
    mp=out/'mini-policy.json';g.put(mp,mini)
    for n,filename,value in [('stale-cache','outdated.pyc',b'inactive stale cache'),('startup-hook','injected.pth',b'import nonexistent_fixture\n')]:
        pin=arr/filename
        with pin.open('xb') as fd:fd.write(value)
        trial(n,mini,mp,g.h(g.wire(mini)),False,"changed import population")
        pin.unlink() # only owned fixture entry; decision and stderr retained
    # The 019 policy cannot be replaced with a historical task or schema.
    for n,updates in (("wrong-task",dict(task="studio017")),
                      ("old-policy",dict(schema="studio017-python-policy/2"))):
        altered=dict(p,**updates);bad=out/(n+'.json');g.put(bad,altered)
        trial(n,altered,bad,g.h(g.wire(altered)),False,"policy schema")
    trial("policy-digest",p,policy_path,"0"*64,False,"policy digest")
    trial("interpreter-flags",p,policy_path,expected_sha,False,"interpreter flags / cache prefix",isolated=False)
    altered=dict(p,interpreter="/synthetic-unapproved-interpreter")
    bad=out/'interpreter-policy.json';g.put(bad,altered)
    trial("interpreter-identity",altered,bad,g.h(g.wire(altered)),False,"approved interpreter")
    # Copy only this source gate to a private miniature source root. Its original
    # bytes enter the prospective policy before a harmless appended comment changes them.
    src=out/'source-fixture';src.mkdir(0o700)
    entry=src/'studio019_py_gate.py';entry.write_bytes(g.raw(HERE/'studio019_py_gate.py'))
    copied=dict(p,roots=g.layout(p['roots'][0],p['roots'][2],src))
    copied['inventory_sha256'],copied['modules']=g.inventory(copied['roots'])
    cp=out/'source-policy.json';g.put(cp,copied)
    with entry.open('ab') as stream:stream.write(b"\n# private synthetic source-byte mutation\n")
    trial("gate-bytes",copied,cp,g.h(g.wire(copied)),False,"changed import population",entry)
    g.put(out/'suite.json',dict(schema='studio019-runtime-controls/1',task=g.TASK,source=p['source'],policy_sha256=expected_sha,controls={n:g.h(g.raw(out/n/'decision.json')) for n in ('positive','unlisted-image','stale-cache','startup-hook','wrong-task','old-policy','policy-digest','interpreter-flags','interpreter-identity','gate-bytes')}))
if __name__=="__main__":
    if len(sys.argv)!=4:raise SystemExit("POLICY ORIGINAL_SHA256 FRESH_PRIVATE_LEDGER")
    run(*sys.argv[1:])

"""One prospective initial real expert claim. No corrective or replay entry point."""
import json
import os
import re
import resource
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio016_source import bind, need, parse, sha, vector
import f020_policy_native_custody as custody
from f020_staged_weighted_supervise import fetch
from studio016_compare import compare, deserialize, serialize
from studio016_reference import references

ROOT=Path(__file__).resolve().parents[2]
PYTHON=Path('/opt/homebrew/bin/python3')
BASE='2195f711548906d0e40a7335dd081341a6f0ec21'
ANCHOR=Path.home()/'.codex/artifacts/studio016-real-flash-expert-initial.claim.json'
LIMITS=dict(selected=14155776,transport=33734653,receipts=2073600,
            # 1 GiB job RSS, 256 MiB supervisor, 256 MiB verifier/tool children,
            # 64 MiB native allocation plus conservative 448 MiB shared reserve.
            combined_bytes=2<<30,job_rss=1<<30,allocator_bytes=64<<20,
            evidence=512<<20,build=10<<30,headroom=16<<30,
            swap_growth=256<<20,swap_consecutive=3,child_seconds=1800,
            campaign_seconds=7200,reference=1,native=1,grade=1,retries=0)
BINDING=ROOT/'crates/mlx-expert-mlp/src/real_binding.json'
REVIEW='ACCEPT_REAL_FLASH_EXPERT_SOURCE_SCOPE'
OPTS=['-I','-B']
def enc(x):return (json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def read(p,n=16<<20):
    p=Path(p);need(p==p.resolve(strict=True) and p.is_file() and p.stat().st_size<=n,'file admission: '+p.name)
    with p.open('rb') as f:b=f.read(n+1)
    need(len(b)<=n,'size changed');return b
def doc(p,n=16<<20):return parse(read(p,n))
def record(p,x):
    with p.open('xb') as f:f.write(enc(x));f.flush();os.fsync(f.fileno())
    fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def cmd(*a):return subprocess.check_output(a,cwd=ROOT,timeout=45).decode().strip()
def digest(p):return custody.prior.old.hashed(p)
def census(d):
    # Do not follow symlinked directory entries. Target measured separately.
    ev=build=0
    for root,dirs,names in os.walk(d):
        for n in names:
            p=Path(root)/n
            size=p.lstat().st_size
            if p.is_relative_to(d/'target'):build+=size
            else:ev+=size
    return ev,build
def pressure():
    st=cmd('/usr/bin/vm_stat');pages=lambda k:int(re.search(r'^'+k+r':\s+(\d+)\.',st,re.M)[1])
    free=pages('Pages free')+pages('Pages speculative')+min(pages('Pages inactive'),pages('File-backed pages'))
    v=cmd('/usr/sbin/sysctl','-n','vm.swapusage')
    used=re.search(r'used\s*=\s*([\d.]+)([KMGT])',v)
    return dict(headroom=free*os.sysconf('SC_PAGE_SIZE'),pressure=int(cmd('/usr/sbin/sysctl','-n','kern.memorystatus_vm_pressure_level')),
                swap=int(float(used[1])*1024**('KMGT'.index(used[2])+1)))
def basic(d):
    need(d.is_absolute() and d.resolve(strict=True)==d and d.stat().st_uid==os.getuid() and stat.S_IMODE(d.stat().st_mode)==0o700,'private directory')
    cfg=doc(d/'config.json');root=Path(cfg['checkpoint'])
    for protected in (ROOT,root,Path(cfg['prefix'])):
        need(not d.is_relative_to(protected) and not protected.is_relative_to(d),'directory overlap')
    need(re.fullmatch('[0-9a-f]{64}',cfg['run']),'run id')
    source=doc(d/'source.json')
    need({k:v for k,v in source.items() if k!='witnesses'}==doc(BINDING),'source manifest')
    need(read(d/'input.f32le',16384)==vector(),'input')
    return cfg,root,source

def inputs(d):
    cfg,root,src=basic(d);bind(root,previous=src)
    need(not custody._cargo_configs(),'unbound cargo config')
    source=custody.prior.old.source()
    need(cmd('/usr/bin/git','merge-base',BASE,'HEAD')==BASE and source['commit']!=BASE,'base')
    host=custody._host();need(host['page']=='16384','page')
    tools=custody._toolchain();native=custody.prior.installed(cfg)
    hist=custody._history(cfg)
    claim=Path(cfg['installation']).parent/'f020-m4c-staged-policy-native-v1.claim.json'
    need(digest(claim)=='2460f6722c8432ef2d4e23ed750249d305f429c2fc56c51ba7748b717a5b7504','Studio015 claim')
    oldcfg=doc(Path(doc(claim)['config']))
    need(digest(Path(oldcfg['output'])/'result.json')=='28f77c560a467f3af2331e6bc01292a0ae5e03fa7f4cada0b934903005c36eed','Studio015 result')
    return dict(source=source,host=host,tools=tools,native=native,headers=custody._headers(Path(cfg['prefix'])),history=hist,
                source_manifest=digest(d/'source.json'),input_sha256=sha(vector()),run=cfg['run'],config=digest(d/'config.json'),
                interpreter=digest(PYTHON.resolve(strict=True)))

def envelope(d):
    fact=inputs(d);source=fact['source'];cfg=doc(d/'config.json')
    binary=d/'target/release/qualify-real-flash-expert';build=doc(d/'build.json')
    need(build['admission']==fact and build['exit']==0 and build['binary_sha256']==digest(binary)
         and build['cargo_log_sha256']==digest(d/build['cargo_log']),'build custody')
    review=doc(d/'review.json');ci=doc(d/'ci.json')
    need(review['verdict']==REVIEW and review['head']==source['commit'] and review['unresolved_blockers']==[]
         and review['report_sha256']==digest(d/'external-review.json'),'review receipt')
    need(ci['event']=='push' and ci['conclusion']=='success' and ci['head_sha']==source['commit'] and ci['run_attempt']==1,'ordinary CI')
    return dict(schema='studio016-real-expert-initial/1',run=cfg['run'],source=source['commit'],tree=source['tree'],
                input_sha256=fact['input_sha256'],source_manifest_sha256=fact['source_manifest'],binding_sha256=digest(BINDING),
                reference_sha256=digest(ROOT/'scripts/research/studio016_reference.py'),criteria_sha256=digest(ROOT/'scripts/research/studio016_compare.py'),
                build_sha256=digest(d/'build.json'),binary_sha256=digest(binary),admission_sha256=sha(enc(fact)),
                review_sha256=digest(d/'review.json'),ci_sha256=digest(d/'ci.json'),limits=LIMITS,layer=3,expert=0,policy='BufferedRequested')
def verified(d):
    grant=envelope(d);ptr=doc(d/'GRANT_POINTER',8192)
    need(set(ptr)=={'commit','path','sha256'} and re.fullmatch('[0-9a-f]{40}',ptr['commit']),'grant pointer')
    name='016__RUST-ENGINE__Mac-Studio-M1-Ultra__'+grant['run']+'__grant.json'
    need(ptr['path']=='Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/'+name and ptr['sha256']==sha(enc(grant)),'exact prospective grant')
    need(fetch(ptr['commit'],ptr['path'])==enc(grant) and fetch(ptr['commit'],ptr['path']+'.sha256').decode().split()==[ptr['sha256'],name],'published grant or sidecar')
    return grant,ptr

def active(d,kind,worker):
    grant,ptr=verified(d);claim=doc(ANCHOR);intent=doc(d/(kind+'-intent.json'))
    need(claim==dict(dir=str(d),run=grant['run'],grant=ptr,supervisor=intent['supervisor'],limits=LIMITS),'original claim')
    leader=int(cmd('/bin/ps','-p',str(worker),'-o','ppid='))
    need(leader==claim['supervisor'] and intent['kind']==kind and intent['claim_sha256']==digest(ANCHOR),'owned process')
    record(d/(kind+'-start.json'),dict(worker=worker,supervisor=leader,grant_sha256=ptr['sha256']))
    return grant

def work(d,kind,exe=None):
    cfg,root,src=basic(d)
    ident=active(d,kind,os.getppid() if kind=='native' else os.getpid())
    if kind=='native':
        actual=d/'target/release/qualify-real-flash-expert'
        need(Path(exe)==actual and digest(actual)==ident['binary_sha256'],'executable binding')
        return dict(root=str(root),prefix=cfg["prefix"],identity=ident)
    _,parts=bind(root,previous=src,payload=True)
    if kind=='reference':return serialize(references(parts,vector()))
    return compare(doc(d/'native.json'),deserialize(doc(d/'reference.json')),parts,ident)

def observe(d,kind,argv,deadline,swap):
    start=time.monotonic();base=doc(ANCHOR)
    record(d/(kind+'-intent.json'),dict(kind=kind,supervisor=base['supervisor'],claim_sha256=digest(ANCHOR),argv=[str(v) for v in argv]))
    env=dict(PATH='/usr/bin:/bin:/usr/sbin:/sbin',HOME=str(Path.home()),MLX_ENABLE_TF32='0',PYTHONDONTWRITEBYTECODE='1')
    with (d/(kind+'.json')).open('xb') as out,(d/(kind+'.stderr')).open('xb') as err,(d/(kind+'.monitor')).open('xb') as log:
        child=subprocess.Popen(argv,stdout=out,stderr=err,stdin=subprocess.DEVNULL,env=env,cwd=ROOT,start_new_session=True)
        try:
            bad=0
            while child.poll() is None:
                p=pressure();bad=bad+1 if p['swap']-swap>LIMITS['swap_growth'] else 0
                rows=[list(map(int,x.split())) for x in cmd('/bin/ps','-axo','pid=,pgid=,rss=').splitlines()]
                group=sum(v[2]*1024 for v in rows if v[1]==child.pid or v[0]==os.getpid())
                direct=max([v[2]*1024 for v in rows if v[0]==child.pid] or [0])
                ev,build=census(d);log.write(enc(dict(pid=child.pid,elapsed=time.monotonic()-start,group_with_launcher_rss=group,job_rss=direct,**p)));log.flush()
                need(p['pressure']==1 and bad<3 and group<=LIMITS['combined_bytes'] and direct<=LIMITS['job_rss']
                     and ev<LIMITS['evidence'] and build<=LIMITS['build'] and time.monotonic()<min(deadline,start+1800),'observed resource/time gate')
                time.sleep(1)
            need(child.returncode==0,'failed '+kind)
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGKILL);child.wait()
            record(d/(kind+'-exit.json'),dict(pid=child.pid,exit=child.returncode,seconds=time.monotonic()-start))
def launch(d):
    need(not os.path.lexists(ANCHOR),'initial claim occupied')
    deadline=time.monotonic()+7200
    grant,ptr=verified(d);p=pressure()
    need(p['headroom']>=16<<30 and p['pressure']==1,'host headroom')
    for k in ('reference','native','grade'):
        need(not any(d.glob(k+'-*.json')) and not (d/(k+'.json')).exists(),'existing operation')
    ev,build=census(d);need(ev+64*2**20<=LIMITS['evidence'] and build<=LIMITS['build'],'disk envelope')
    record(ANCHOR,dict(dir=str(d),run=grant['run'],grant=ptr,supervisor=os.getpid(),limits=LIMITS))
    for kind in ('reference','native','grade'):
        argv=[PYTHON,*OPTS,__file__,kind,d] if kind!='native' else [d/'target/release/qualify-real-flash-expert',d]
        observe(d,kind,argv,deadline,p['swap'])
    return dict(grade=doc(d/'grade.json'),claim_sha256=digest(ANCHOR))

if __name__=='__main__':
    os.umask(0o077)
    mode=sys.argv[1];d=Path(sys.argv[2])
    if mode=='describe':result=envelope(d)
    elif mode=='launch':result=launch(d)
    elif mode=='verify-child':result=work(d,'native',sys.argv[3])
    elif mode in ('reference','grade'):result=work(d,mode)
    else:raise ValueError('unknown mode')
    sys.stdout.buffer.write(enc(result))

"""One prospective initial real expert claim. No corrective or replay entry point."""
import json
import os
import re
import hashlib
import struct
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio016_source import bind, need, parse, sha, vector, SHARD, SHARD_ID, REVISION
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
    # Kernel system-wide memory estimate and a separate reclaimable-file cap,
    # never the intersection of two overlapping vm_stat categories.
    pct=int(cmd('/usr/sbin/sysctl','-n','kern.memorystatus_level'))
    total=int(cmd('/usr/sbin/sysctl','-n','hw.memsize'))
    pageable=int(cmd('/usr/sbin/sysctl','-n','vm.page_pageable_external_count'))
    free=int(cmd('/usr/sbin/sysctl','-n','vm.page_free_count'))
    need(0<=pct<=100 and pageable>=0 and free>=0,'kernel memory observation')
    estimated=min(max(0,pct-1)*total//100,(free+pageable//2)*os.sysconf('SC_PAGE_SIZE'))
    v=cmd('/usr/sbin/sysctl','-n','vm.swapusage')
    used=re.search(r'used\s*=\s*([\d.]+)([KMGT])',v)
    return dict(headroom=estimated,kernel_available_percent=pct,pageable_external_pages=pageable,pressure=int(cmd('/usr/sbin/sysctl','-n','kern.memorystatus_vm_pressure_level')),
                swap=int(float(used[1])*1024**('KMGT'.index(used[2])+1)))
def configuration(d):
    need(d.is_absolute() and d.resolve(strict=True)==d and d.stat().st_uid==os.getuid() and stat.S_IMODE(d.stat().st_mode)==0o700,'private directory')
    cfg=doc(d/'config.json');root=Path(cfg['checkpoint'])
    for protected in (ROOT,root,Path(cfg['prefix'])):
        need(not d.is_relative_to(protected) and not protected.is_relative_to(d),'directory overlap')
    need(re.fullmatch('[0-9a-f]{64}',cfg['run']),'run id')
    return cfg,root

def binding_receipt(cfg,source):
    return dict(schema='studio016-original-whole-shard/1',run=cfg['run'],revision=REVISION,
                name=SHARD,method='held-descriptor-sha256',bytes=source['witnesses'][SHARD][2],
                checked_sha256=SHARD_ID,witness=source['witnesses'][SHARD],source_sha256=sha(enc(source)),
                public_binding_sha256=digest(BINDING))

def validate_binding(d,cfg,source):
    original=doc(d/'binding-receipt.json')
    need(original==binding_receipt(cfg,source),'missing or crossed original whole-shard receipt')
    return original

def prepare_binding(d):
    cfg,root=configuration(d)
    need(not os.path.lexists(ANCHOR) and not os.path.lexists(d/'binding-receipt.json'),'existing claim or binding')
    # Repeat N1 in reviewed code; adopt earlier originals only on identical bytes.
    source,_=bind(root,whole=True)
    need({k:v for k,v in source.items() if k!='witnesses'}==doc(BINDING),'reviewed range binding')
    if (d/'source.json').exists():need(read(d/'source.json')==enc(source),'earlier original changed')
    else:record(d/'source.json',source)
    inp=d/'input.f32le'
    if inp.exists():need(read(inp,16384)==vector(),'earlier input changed')
    else:
        with inp.open('xb') as f:f.write(vector());f.flush();os.fsync(f.fileno())
    receipt=binding_receipt(cfg,source);record(d/'binding-receipt.json',receipt)
    return receipt

def basic(d):
    cfg,root=configuration(d)
    source=doc(d/'source.json')
    need({k:v for k,v in source.items() if k!='witnesses'}==doc(BINDING),'source manifest')
    validate_binding(d,cfg,source)
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
                source_manifest=digest(d/'source.json'),whole_binding=digest(d/'binding-receipt.json'),input_sha256=sha(vector()),run=cfg['run'],config=digest(d/'config.json'),
                interpreter=digest(PYTHON.resolve(strict=True)))

def build_record(d):
    need(not os.path.lexists(ANCHOR) and not os.path.lexists(d/'build.json'),'existing claim or build')
    fact=inputs(d);cfg=doc(d/'config.json');tools=fact['tools'];root=d/('build-'+fact['source']['commit'])
    root.mkdir(mode=0o700);binary=d/'target/release/qualify-real-flash-expert';log=root/'cargo.jsonl'
    args=[tools['cargo']['path'],'build','--offline','--locked','--release','-j','2','--no-default-features','-p','mlx-expert-mlp','--features','real-flash-expert','--bin',binary.name,'--message-format=json']
    env=dict(HOME=str(Path.home()),PATH=str(Path(tools['rustc']['path']).parent)+':/usr/bin:/bin:/usr/sbin:/sbin',RUSTC=tools['rustc']['path'],CARGO_TARGET_DIR=str(d/'target'),CARGO_NET_OFFLINE='true',CARGO_BUILD_JOBS='2',MLX_PREFIX=cfg['prefix'],MLX_C_PREFIX=cfg['prefix'],PULSAR_REQUIRE_NATIVE_MLX='1')
    record(root/'intent.json',dict(head=fact['source']['commit'],argv=args,environment=env,inputs=sha(enc(fact))))
    start=time.monotonic()
    with log.open('xb') as o,(root/'stderr.txt').open('xb') as err:
        p=subprocess.Popen(args,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=o,stderr=err,start_new_session=True)
        try:
            record(root/'process.json',dict(pid=p.pid))
            while p.poll() is None:
                ev,b=census(d);need(ev<=LIMITS['evidence'] and b<=LIMITS['build'] and time.monotonic()-start<1800,'build resource limit')
                time.sleep(.5)
        finally:
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
            p.wait();record(root/'exit.json',dict(exit=p.returncode,seconds=time.monotonic()-start))
    need(p.returncode==0 and time.monotonic()-start<=1800,'failed or expired build')
    rows=[parse(l) for l in read(log,12<<20).splitlines()]
    arts=[r for r in rows if r.get('reason')=='compiler-artifact' and r.get('executable')==str(binary)]
    need(len(arts)==1 and rows[-1]==dict(reason='build-finished',success=True),'Cargo artifact')
    art=arts[0];need(art['target']['name']==binary.name and art['target']['kind']==['bin'] and 'real-flash-expert' in art['features'] and not art['profile']['test'],'wrong compiled artifact')
    need(inputs(d)==fact,'postbuild custody')
    rec=dict(admission=fact,exit=0,artifact=art,binary_sha256=digest(binary),cargo_log=str(log.relative_to(d)),
             cargo_log_sha256=digest(log),operation=root.name,linkage=cmd('/usr/bin/otool','-L',str(binary)))
    record(d/'build.json',rec);return rec

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

def file_receipt(f):
    st=os.fstat(f.fileno());need(stat.S_ISREG(st.st_mode) and st.st_size<=16<<20,'bounded output')
    f.seek(0);dg=hashlib.file_digest(f,'sha256').hexdigest()
    return dict(dev=st.st_dev,ino=st.st_ino,bytes=st.st_size,mtime_ns=st.st_mtime_ns,sha256=dg)

def sealed(d,kind,prior):
    p=d/(kind+'.json')
    need(p.resolve(strict=True)==p,'output alias')
    with p.open('rb') as f:
        r=file_receipt(f);need(r==prior[kind] and r==doc(d/(kind+'-seal.json')) and os.path.samestat(os.fstat(f.fileno()),p.lstat()),'original output changed')
        f.seek(0);raw=f.read(r['bytes']+1)
        need(len(raw)==r['bytes'] and sha(raw)==r['sha256'],'consumed bytes changed')
    return parse(raw)

def active(d,kind,worker,exe=None):
    grant,ptr=verified(d);claim=doc(ANCHOR);intent=doc(d/(kind+'-intent.json'))
    need(claim==dict(dir=str(d),run=grant['run'],grant=ptr,supervisor=intent['supervisor'],limits=LIMITS),'original claim')
    leader=int(cmd('/bin/ps','-p',str(worker),'-o','ppid='))
    need(leader==claim['supervisor'] and intent['kind']==kind and intent['claim_sha256']==digest(ANCHOR),'owned process')
    if kind=='native':
        actual=d/'target/release/qualify-real-flash-expert'
        need(Path(exe)==actual and digest(actual)==grant['binary_sha256'],'executable binding')
    record(d/(kind+'-start.json'),dict(worker=worker,supervisor=leader,grant_sha256=ptr['sha256']))
    return grant

def work(d,kind,exe=None):
    cfg,root,src=basic(d)
    prior=parse(os.environ['STUDIO016_ORIGINAL_OUTPUTS'].encode())
    need(set(prior)==set({'reference':(), 'native':('reference',),'grade':('reference','native')}[kind]),'predecessor outputs')
    originals={k:sealed(d,k,prior) for k in prior}
    ident=active(d,kind,os.getppid() if kind=='native' else os.getpid(),exe)
    if kind=='native':
        # Consume the actual independent wire grammar before candidate evaluation.
        deserialize(originals['reference'])
        st=src['witnesses']['model-00001.safetensors']
        stamp=b'buffered-window-descriptor/1'+struct.pack('<QQQqqqq',*st[:3],*divmod(st[3],10**9),*divmod(st[4],10**9))
        lib=Path(cfg['prefix'])/'lib';names=('libmlx.dylib','libmlxc.dylib','libjaccl.dylib')
        return dict(root=str(root),prefix=cfg["prefix"],identity=ident,libs={n:digest((lib/n).resolve(strict=True)) for n in names},stamp=list(hashlib.sha256(stamp).digest()))
    _,parts=bind(root,previous=src,payload=True)
    if kind=='reference':return serialize(references(parts,vector()))
    return compare(originals['native'],deserialize(originals['reference']),parts,ident)

def observe(d,kind,argv,deadline,swap,prior):
    start=time.monotonic();base=doc(ANCHOR)
    record(d/(kind+'-intent.json'),dict(kind=kind,supervisor=base['supervisor'],claim_sha256=digest(ANCHOR),argv=[str(v) for v in argv]))
    env=dict(PATH='/usr/bin:/bin:/usr/sbin:/sbin',HOME=str(Path.home()),MLX_ENABLE_TF32='0',PYTHONDONTWRITEBYTECODE='1')
    env['STUDIO016_ORIGINAL_OUTPUTS']=enc(prior).decode()
    if kind=='native':
        prefix=Path(doc(d/'config.json')['prefix'])
        env.update(MLX_C_PREFIX=str(prefix),DYLD_LIBRARY_PATH=str(prefix/'lib'))
    with (d/(kind+'.json')).open('x+b') as out,(d/(kind+'.stderr')).open('xb') as err,(d/(kind+'.monitor')).open('xb') as log:
        child=subprocess.Popen(argv,stdout=out,stderr=err,stdin=subprocess.DEVNULL,env=env,cwd=ROOT,start_new_session=True)
        def alarm(signum,frame):raise TimeoutError('campaign watchdog')
        old=signal.signal(signal.SIGALRM,alarm)
        signal.setitimer(signal.ITIMER_REAL,max(.001,min(deadline,start+1800)-time.monotonic()))
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
            need(time.monotonic()<min(deadline,start+1800) and child.returncode==0,'failed or expired '+kind)
            out.flush();os.fsync(out.fileno());os.fchmod(out.fileno(),0o400)
            receipt=file_receipt(out)
            need(os.path.samestat(os.fstat(out.fileno()),(d/(kind+'.json')).lstat()),'replaced output')
            record(d/(kind+'-seal.json'),receipt);prior[kind]=receipt
            produced=sealed(d,kind,prior)
            if kind=='reference':deserialize(produced)
            if kind=='native':need(produced['outcome']=='executed','incomplete native result')
            if kind=='grade':need(produced['status']=='PASS','grade result')
            need(time.monotonic()<min(deadline,start+1800),'terminal time bound')
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
            # A surviving process group after its leader exits is a failed cleanup.
            try:os.killpg(child.pid,signal.SIGKILL);survived=True
            except ProcessLookupError:survived=False
            child.wait()
            record(d/(kind+'-exit.json'),dict(pid=child.pid,exit=child.returncode,seconds=time.monotonic()-start,residual_group_killed=survived))
            need(not survived,'owned residual group terminated')
def launch(d):
    need(not os.path.lexists(ANCHOR),'initial claim occupied')
    deadline=time.monotonic()+7200
    grant,ptr=verified(d)
    # Do not trust a hand-entered witness even if it has the same form as the
    # preparation receipt: verify the original publisher SHA before consuming the claim.
    cfg,root,original=basic(d);fresh,_=bind(root,whole=True)
    need(fresh==original and validate_binding(d,cfg,fresh)==binding_receipt(cfg,original),'final whole-source revalidation')
    p=pressure()
    need(p['headroom']>=16<<30 and p['pressure']==1,'host headroom')
    for k in ('reference','native','grade'):
        need(not any(d.glob(k+'-*.json')) and not any(os.path.lexists(d/(k+suffix)) for suffix in ('.json','.stderr','.monitor')),'existing operation')
    ev,build=census(d);need(ev+64*2**20<=LIMITS['evidence'] and build<=LIMITS['build'],'disk envelope')
    record(ANCHOR,dict(dir=str(d),run=grant['run'],grant=ptr,supervisor=os.getpid(),limits=LIMITS))
    prior={}
    for kind in ('reference','native','grade'):
        argv=[PYTHON,*OPTS,__file__,kind,d] if kind!='native' else [d/'target/release/qualify-real-flash-expert',d]
        observe(d,kind,argv,deadline,p['swap'],prior)
    for k in prior:sealed(d,k,prior)
    return dict(grade=sealed(d,'grade',prior),originals=prior,claim_sha256=digest(ANCHOR))

if __name__=='__main__':
    os.umask(0o077)
    mode=sys.argv[1];d=Path(sys.argv[2])
    if mode=='prepare-binding':result=prepare_binding(d)
    elif mode=='build-record':result=build_record(d)
    elif mode=='describe':result=envelope(d)
    elif mode=='launch':result=launch(d)
    elif mode=='verify-child':result=work(d,'native',sys.argv[3])
    elif mode in ('reference','grade'):
        try:result=work(d,mode)
        except Exception as error:
            if hasattr(error,'evidence'):record(d/(mode+'-refusal.json'),dict(reason=str(error),evidence=error.evidence))
            raise
    else:raise ValueError('unknown mode')
    sys.stdout.buffer.write(enc(result))

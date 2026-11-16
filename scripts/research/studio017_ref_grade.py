"""Read-only complete Studio017 receipt/grade. Imports no graph, MLX or model loader.

Each numerical output must have been exclusively sealed and made read-only by
the caller. No input to this module can launch a numerical model operation.
Structural errors refuse; finite numerical discrepancies return a negative
result with metrics. No adaptive thresholds or choosing a better input.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import stat

import numpy as np
from studio017_ref_criteria import bf_stage, interval_bf16, golden_margin, route_margin, route_result
from studio017_ref_store import Refusal,finite,require


REAL=(45,4096,154880,288,8,64,128,512,128)
# Recurrence: cold F32 state is a product of three BF16 source values (k,v,beta)
# with two F32 operations. Three one-neighbor BF16 input changes on normal
# operands give (1+2^-7)^3-1 relative. For near-zero take 16 unit-scale F32
# roundoffs absolute. This is a fixed local scientific target, not a proof on
# accumulated errors across 45 layers or a substitute for the BF16 stage gates.
STATE_REL=(1+2.**-7)**3-1+2.**-22
STATE_ABS=16*2.**-24


def witness_scope(layers):
    """Interpret the position-zero comparison independently of its numerical outcome."""
    return dict(
        position=0,
        unobserved_mla_layers=list(range(3, layers, 4)),
        unobserved_mla_projections=['q_a_proj', 'q_b_proj', 'embed_q', 'indexer.wq_b'],
        state_offset='structural count only',
    )


def layout(g):
    n,d,v,e,k,h,kd,latent,index=g
    result={}
    def add(i,name,count,kind):
        result[f'{i:02}.{name}.f32']=i,name,count,kind
    add(0,'input.embedding',d,'embedding')
    for i in range(n):
        for name,mult in [('attention.output',1),('ffn.output',1),('layer.streams',4)]:
            add(i,name,d*mult,'bf')
        add(i,'state.offset',1,'one')
        for b in ('attn','ffn'):add(i,'mhc.'+b,24,'mhc')
        if i%4==3:
            add(i,'mla.latent',latent,'bf')
            add(i,'mla.indexer',2*index+1,'indexer')
        else:
            add(i,'kda.recurrent_state',h*kd*kd,'state')
            add(i,'kda.qkv_beta',3*h*kd+h,'bf')
            add(i,'kda.decay',h*kd,'decay')
            add(i,'kda.conv_state',3*3*h*kd,'conv')
        if i>=3:
            add(i,'moe.corrected',e,'corrected')
            add(i,'moe.routed',d,'bf')
            add(i,'moe.shared',d,'bf')
    add(n,'final.norm',d,'bf')
    result['logits.f32']=(n,'logits',v,'logits')
    return result


def strict_json(b):
    def distinct(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'duplicate JSON key '+k)
            out[k]=v
        return out
    def bad(v): raise Refusal('invalid JSON constant '+v)
    return json.loads(b,object_pairs_hook=distinct,parse_constant=bad)


def pair(x):
    return (x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)


def open_dir(path):
    p=Path(path)
    require(p.is_absolute() and '..' not in p.parts,'canonical absolute directory')
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    fd=os.open('/',flags)
    try:
        for name in p.parts[1:]:
            new=os.open(name,flags,dir_fd=fd)
            os.close(fd);fd=new
        return fd
    except BaseException:
        os.close(fd)
        raise


class Sealed:
    def __init__(self,path,fd,pop,role,g):
        self.fd=fd;self.path=path;self.role=role;self.g=g
        self.pop=pop;self.manifest={};self.inodes=set()
        st=os.fstat(fd)
        require(st.st_uid==os.geteuid() and not(st.st_mode&0o222),'unsealed output directory')
        self.dir_id=pair(st)
        names=set(os.listdir(fd))
        require(names==set(pop)|{'report.json'},'unexpected or missing output files')
        self.report=strict_json(self.bytes('report.json',None))
        r=self.report
        for k in ('input_id','token_id','position','layer_count','generated_token_count'):
            require(type(r.get(k)) is int,'report field '+k)
        require(r['input_id']==154820 and r['position']==0 and r['layer_count']==g[0] and
                r['generated_token_count']==1 and 0<=r['token_id']<g[2],'report population')
        require(type(r.get('routes')) is list and len(r['routes'])==g[0]-3,'routed layer count')
        self.routes={}
        for row in r['routes']:
            require(type(row) is dict and set(row)=={'layer','ids','weights','cutoff_gap'},'route fields')
            i,ids,weights,gap=[row[k] for k in ('layer','ids','weights','cutoff_gap')]
            require(type(i) is int and 3<=i<g[0] and i not in self.routes,'duplicate/invalid route layer')
            require(type(ids) is list and len(ids)==g[4] and all(type(j) is int and 0<=j<g[3] for j in ids)
                    and len(ids)==len(set(ids)),'route ids')
            require(type(weights) is list and len(weights)==g[4] and
                    all(type(x) in (int,float) and math.isfinite(x) and 0<=x<=2.5 for x in weights) and
                    abs(math.fsum(weights)-2.5)<=4e-5,'route weight range/sum')
            require(type(gap) in (int,float) and math.isfinite(gap) and gap>=0,'reported cutoff gap')
            self.routes[i]=row
        require(list(self.routes)==list(range(3,g[0])),'route layer order')
        if 'files' in r:
            require(isinstance(r['files'],dict) and set(r['files'])==set(pop),'embedded file manifest population')
        require(r.get('schema')=='studio017-'+role+'/1' and 'files' in r and
                'runner_up' in r and 'margin' in r,'output exact schema')
        fields={'schema','files','input_id','position','generated_token_count','layer_count',
                'routes','token_id','runner_up','margin'}
        if role=='native':
            fields.update(('native','libraries'))
            t=r.get('native')
            require(type(t) is dict and set(t)=={'logical_bytes','reads','native_allocator_peak',
                    'affine_handles_freed','affine_live'} and all(type(k) is int for k in t.values()) and
                    t['affine_live']==0 and t['affine_handles_freed']>0 and t['reads']>0 and
                    t['logical_bytes']>0 and 0<t['native_allocator_peak']<=512*2**20,'native accounting')
            require(r.get('libraries')==['libjaccl.dylib','libmlx.dylib','libmlxc.dylib'],'native image set')
        require(set(r)==fields,'unrecognized output report fields')
        if 'runner_up' in r:
            require(type(r['runner_up']) is int and 0<=r['runner_up']<g[2] and
                    r['runner_up']!=r['token_id'],'runner up')
        if 'margin' in r:
            require(type(r['margin']) in (int,float) and math.isfinite(r['margin']) and r['margin']>=0,'token margin')

    def bytes(self,name,n):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
        try:
            a=os.fstat(fd)
            require(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and not(a.st_mode&0o222) and
                    a.st_uid==os.geteuid() and (a.st_dev,a.st_ino) not in self.inodes and
                    0<a.st_size<=8*1024**2 and (n==a.st_size if n is not None else a.st_size<=1024**2),
                    'unsealed/duplicate/wrong-sized file '+name)
            self.inodes.add((a.st_dev,a.st_ino))
            with os.fdopen(fd,'rb',closefd=False) as f:b=f.read(a.st_size+1)
            require(len(b)==a.st_size and pair(os.fstat(fd))==pair(a) and
                    pair(os.stat(name,dir_fd=self.fd,follow_symlinks=False))==pair(a),'changed file '+name)
        finally:
            os.close(fd)
        m={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
        if n is not None and 'files' in self.report:
            require(self.report['files'][name]==m,'embedded digest '+name)
        self.manifest[name]=m
        return b

    def arr(self,name,count):
        return finite(np.frombuffer(self.bytes(name,count*4),dtype='<f4'))

    def finish(self):
        current=open_dir(self.path)
        try:
            require(pair(os.fstat(current))==self.dir_id==pair(os.fstat(self.fd)) and
                    set(self.manifest)==set(self.pop)|{'report.json'} and
                    set(os.listdir(current))==set(self.manifest),'source changed during inspection')
        finally:os.close(current)
        b=(json.dumps(self.manifest,sort_keys=True,separators=(',',':'))+'\n').encode()
        return {'files':len(self.manifest),'bytes':sum(v['bytes'] for v in self.manifest.values()),
                'manifest_sha256':hashlib.sha256(b).hexdigest(),'report_sha256':self.manifest['report.json']['sha256']}


@contextmanager
def sealed(path,pop,role,g):
    fd=open_dir(path)
    try:yield Sealed(path,fd,pop,role,g)
    finally:os.close(fd)


def representation(x,kind):
    if kind in ('bf','conv','indexer','embedding','logits'):
        interval_bf16(x)
    if kind=='one':require(x.tolist()==[1.0],'wrong post-cold state offset')
    if kind=='conv':require(not np.any(x[:2*(x.size//3)].view('<u4')),'initial history must be canonical positive zero')
    if kind=='mhc':
        require(x.size==24 and np.all(x[:4]>=0) and np.all(x[:4]<=1.000002) and
                np.all(x[4:8]>=0) and np.all(x[4:8]<=2) and np.all(x[8:]>=0) and
                np.all(x[8:]<=1),'invalid mHC coefficients')
    if kind=='decay':require(np.all(x>=np.nextafter(np.float32(np.exp(-5.)),np.float32(0))) and np.all(x<=1),'invalid decay gates')
    if kind=='indexer':require(x[-1]==1.0,'invalid cold indexer key')


def route_fields(o,i,corrected):
    row=o.routes[i]
    rr=dict(selected=row['ids'],weights=np.asarray(row['weights'],dtype='<f4'),corrected=corrected)
    evidence=route_margin(corrected,rr['selected'])
    chosen=np.zeros(corrected.shape,dtype='?');chosen[rr['selected']]=True
    actual=float(corrected[chosen].min())-float(corrected[~chosen].max())
    # Native reports an F32 subtraction; decimal JSON reference reports exact
    # subtraction of the represented score pair. Accept only these semantics,
    # permitting down-to-f32 JSON text in either provider's report.
    require(np.float32(row['cutoff_gap'])==np.float32(actual),'gap vs original corrected scores')
    return rr,evidence


def token_fields(o,logits):
    m=golden_margin(logits)
    r=o.report
    require(m['winner']==r['token_id'],'recorded ID vs original argmax')
    if 'runner_up' in r:require(r['runner_up']==m['runner_up'],'recorded runner-up vs logits')
    if 'margin' in r:require(np.float32(r['margin'])==np.float32(m['margin']),'reported margin vs logits')
    return m


def inspect_reference(path):
    return _inspect(path,REAL)


def _inspect(path,g):
    pop=layout(g);routes={}
    with sealed(path,pop,'reference',g) as o:
        for name,(i,label,count,kind) in pop.items():
            a=o.arr(name,count);representation(a,kind)
            if kind=='corrected':routes[i]=route_fields(o,i,a)[1]
            if kind=='logits':token=token_fields(o,a)
        seal=o.finish()
    return dict(schema='studio017-reference-eligibility/1',
                eligible=bool(token['eligible'] and all(r['eligible'] for r in routes.values())),
                source=seal,token=token,route_gates=routes,layers=g[0],vocabulary=g[2],
                witness_scope=witness_scope(g[0]))


def grade_pair(ref_dir,native_dir):
    return _grade(ref_dir,native_dir,REAL)


def _grade(ref_dir,native_dir,g):
    pop=layout(g);routes={};stages={};outside=0
    with sealed(ref_dir,pop,'reference',g) as r,sealed(native_dir,pop,'native',g) as c:
        require(r.dir_id[:2]!=c.dir_id[:2],'same reference and candidate directory')
        for name,(i,label,count,kind) in pop.items():
            x,y=r.arr(name,count),c.arr(name,count)
            representation(x,kind);representation(y,kind)
            delta=np.abs(x.astype('f8')-y.astype('f8'))
            metric={'values':count,'max_abs':float(delta.max())}
            if kind=='one' or kind=='embedding':
                # Direct affine row from the same represented inputs: exact
                # BF16 coordinate identity; offset likewise must be exactly 1.
                bad=x.view('<u4')!=y.view('<u4')
            elif kind in ('mhc','decay'):
                # mHC and decay discrepancies count toward the frozen qualifying gate.
                bad=delta>(4e-5+4e-6*np.abs(x.astype('f8')))
            elif kind=='state':
                bad=delta>STATE_ABS+STATE_REL*np.abs(x.astype('f8'))
            elif kind=='corrected':
                refroute,_=route_fields(r,i,x);natroute,_=route_fields(c,i,y)
                gates=route_result(refroute,natroute);routes[i]=gates
                bad=delta>(4e-5+4e-6*np.abs(x.astype('f8')))
            else:
                lo,hi=interval_bf16(x);bad=(y<lo)|(y>hi)
                if kind=='logits':
                    rt=token_fields(r,x);ct=token_fields(c,y)
            n=int(np.count_nonzero(bad));metric['outside']=n
            if n:metric['first_outside']=int(np.flatnonzero(bad)[0])
            outside+=n;stages[name]=metric
        rs,cs=r.finish(),c.finish()
        require(not(r.inodes&c.inodes),'shared original files')
    ok=outside==0 and all(z['pass_all'] for z in routes.values()) and rt['eligible'] and rt['winner']==ct['winner']
    return dict(schema='studio017-full-vector-grade/1',qualified=bool(ok),layers=g[0],vocabulary=g[2],
                reference=rs,native=cs,reference_token=rt,native_token=ct,
                checked_values=sum(m['values'] for m in stages.values()),outside=outside,
                routes=routes,stages=stages,witness_scope=witness_scope(g[0]))

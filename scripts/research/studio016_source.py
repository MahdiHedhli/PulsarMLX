"""Read-only admission of the single frozen Flash expert. Never interpret model code."""
import contextlib
import hashlib
import json
import os
import stat
import struct
from pathlib import Path

CONFIG = '3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d'
INDEX = '5e0a3768db6fb795c4846bed713785a17d336f4cc4494b4f6b28f75082314383'
SHARD = 'model-00001.safetensors'
SHARD_ID = '73a4510722d6a9f0b21f04b72be754148f325490932c9636d815a0dffa333419'
REVISION = 'd43ea8b407ce4e9c25e6ac9baec3feab70d9f5f3'
ROOT = 'GLM-5.3-Flash-MLX-mixed-4_8bit'
ROLE = ('gate', 'up', 'down')
KINDS = ('weight', 'scales', 'biases')
MODULES = tuple('language_model.model.layers.3.mlp.switch_mlp.'+r+'_proj' for r in ROLE)
INDEX_NAME = 'model.safetensors.index.json'
SHARDS = tuple('model-%05d.safetensors' % n for n in range(1,19))
D = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
REG = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

def need(test, why):
    if not test:
        raise ValueError(why)

def pairs(items):
    out = {}
    for k,v in items:
        need(k not in out, 'duplicate '+k)
        out[k] = v
    return out

def reject(s):
    raise ValueError(s)

def parse(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,parse_constant=reject)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def stamp(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def read(fd, offset, count):
    need(0 <= count <= 16*2**20 and offset>=0, 'range cap')
    out = os.pread(fd,count,offset)
    need(len(out)==count,'truncated source')
    return out

@contextlib.contextmanager
def rootfd(path):
    path=Path(path)
    need(path.is_absolute() and path.name==ROOT and '..' not in path.parts,'canonical checkpoint')
    fd=os.open('/',D)
    try:
        for part in path.parts[1:]:
            child=os.open(part,D,dir_fd=fd)
            os.close(fd)
            fd=child
        yield fd
    finally:
        os.close(fd)

@contextlib.contextmanager
def opened(root,name):
    need('/' not in name and name not in ('.','..'),'component')
    fd=os.open(name,REG,dir_fd=root)
    try:
        st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode),'ordinary file required')
        yield fd,stamp(st)
        need(stamp(os.fstat(fd))==stamp(st)==stamp(os.stat(name,dir_fd=root,follow_symlinks=False)),'source changed')
    finally:
        os.close(fd)

def vector():
    # Fixed dense Rademacher input. SHA256 counter bytes determine signs only.
    return b''.join(struct.pack('<f',.25 if v & (1<<i) else -.25)
                    for c in range(16) for v in hashlib.sha256(
                        b'Studio016 expert boundary v1'+bytes([c])).digest() for i in range(8))

def frame(h,b):
    h.update(struct.pack('<Q',len(b)))
    h.update(b)

def geometry(header,base,size):
    ranges=[]
    for name,t in header.items():
        if name=='__metadata__':continue
        a,b=t['data_offsets']
        need(type(a) is int and type(b) is int and 0<=a<=b<=size-base,'invalid offsets')
        ranges.append((a,b))
    end=0
    for a,b in sorted(ranges):
        need(a==end,'gap or overlap');end=b
    need(base+end==size,'unindexed tail')

def bind(path, *, whole=False, payload=False, previous=None):
    """whole establishes publisher identity once. Rebinds require original file witnesses."""
    need(whole or previous is not None,'original selected shard proof required')
    need(not payload or not whole,'distinct reference and binding paths')
    snap=hashlib.sha256()
    frame(snap,b'pulsarmlx.bounded-expert-metadata/1')
    meta={}; witnesses={}; spans=[]; parts={}; total=0
    with rootfd(path) as root:
        for name,digest in [('config.json',CONFIG),(INDEX_NAME,INDEX)]:
            with opened(root,name) as (fd,st):
                raw=read(fd,0,st[2]);need(sha(raw)==digest,'metadata identity '+name)
                frame(snap,name.encode());frame(snap,raw);meta[name]=parse(raw);witnesses[name]=st
        cfg=meta['config.json'];t=cfg['text_config'];q=cfg['quantization']
        need(q==cfg['quantization_config'] and (q['group_size'],q['bits'])==(64,4),'recipe')
        need([t[k] for k in ('hidden_size','moe_intermediate_size','first_k_dense_replace','n_routed_experts','num_experts_per_tok','hidden_act','swiglu_limit')]==[4096,2048,3,288,8,'silu',10],'Flash semantics')
        ix=meta[INDEX_NAME]['weight_map'];need(set(ix.values())==set(SHARDS),'shard set')
        for name in SHARDS:
            with opened(root,name) as (fd,st):
                witnesses[name]=st
                if previous:need(st==previous['witnesses'][name],'stale shard witness')
                prefix=read(fd,0,8);n=struct.unpack('<Q',prefix)[0]
                raw=read(fd,8,n);hdr=parse(raw);base=n+8
                geometry(hdr,base,st[2])
                frame(snap,name.encode());frame(snap,struct.pack('<Q',st[2]));frame(snap,prefix+raw)
                if name!=SHARD:continue
                if whole:
                    dg=hashlib.sha256()
                    for pos in range(0,st[2],4<<20):dg.update(read(fd,pos,min(4<<20,st[2]-pos)))
                    need(dg.hexdigest()==SHARD_ID,'selected whole shard differs from publisher')
                for i,(role,module) in enumerate(zip(ROLE,MODULES)):
                    spec=q.get(module,q)
                    need((spec['bits'],spec['group_size'],spec.get('mode','affine'))==(4,64,'affine'),'module recipe')
                    rows,cols=(4096,2048) if i==2 else (2048,4096)
                    parts[role]=[]
                    for j,kind in enumerate(KINDS):
                        tensor=module+'.'+kind;need(ix[tensor]==SHARD,'unexpected shard')
                        d=hdr[tensor];dtype='BF16' if j else 'U32'
                        shape=[288,rows,cols//(64 if j else 8)]
                        need(d['dtype']==dtype and d['shape']==shape,'typed geometry')
                        a,b=d['data_offsets'];length=rows*shape[-1]*(2 if j else 4)
                        need(b-a==288*length,'byte geometry');total+=length
                        need(total<=64<<20,'selected budget')
                        data=read(fd,base+a,length) if whole or payload else None
                        digest=sha(data) if data is not None else previous["ranges"][len(spans)]["sha256"]
                        spans.append(dict(tensor=tensor,shard=name,begin=base+a,len=length,sha256=digest))
                        if payload:parts[role].append(data)
    need(total==14155776,'incomplete tuple')
    manifest=dict(schema='studio016-source/1',revision=REVISION,selected_shard_sha256=SHARD_ID,
                  config=CONFIG,index=INDEX,metadata_snapshot_sha256=snap.hexdigest(),witnesses=witnesses,
                  expert=0,layer=3,ranges=spans,input_sha256=sha(vector()),selected_bytes=total)
    if previous:need(manifest==previous,'source changed since original binding')
    return manifest,parts

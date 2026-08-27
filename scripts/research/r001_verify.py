#!/usr/bin/env python3
"""Independent R001 GGUF-to-bundle verifier.

This file intentionally does not import the Rust repacker or its generated
types. It parses GGUF and the v1 wire format from literal constants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
HEADER_LEN = 16384
FOOTER_LEN = 16384
ALIGNMENT = 16384
CHUNK = 8 * 1024 * 1024
QUANT = {
    0: ("F32", 1, 4), 1: ("F16", 1, 2), 8: ("Q8_0", 32, 34),
    10: ("Q2_K", 256, 84), 11: ("Q3_K", 256, 110),
    12: ("Q4_K", 256, 144), 13: ("Q5_K", 256, 176),
    14: ("Q6_K", 256, 210), 16: ("IQ2_XXS", 256, 66),
    18: ("IQ3_XXS", 256, 98), 22: ("IQ2_S", 256, 82),
    23: ("IQ4_XS", 256, 136),
}
EXPERT_RE = re.compile(r"^blk\.(\d+)\.ffn_(gate|up|down)_(exps|shexp)\.weight$")


def canonical(value: Any) -> bytes:
    def check(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
            return
        if isinstance(v, str) and all(0x20 <= ord(c) <= 0x7E for c in v):
            return
        if isinstance(v, list):
            for x in v:
                check(x)
            return
        if isinstance(v, dict):
            keys = list(v)
            if keys != sorted(keys) or len(keys) != len(set(keys)):
                raise ValueError("noncanonical object key order")
            for k, x in v.items():
                check(k); check(x)
            return
        raise ValueError(f"value outside CJ-R001-1: {type(v).__name__}")
    # Python dictionaries parsed from JSON retain wire order. For generated
    # projections we normalize through sorted-key serialization first.
    normalized = json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    check(normalized)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def domain_hash(domain: bytes, value: Any) -> str:
    return hashlib.sha256(domain + b"\0" + canonical(value)).hexdigest()


def exact_read(f: BinaryIO, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise EOFError(f"short read {len(b)}/{n}")
    return b


class Reader:
    def __init__(self, path: Path):
        st = path.lstat()
        if not path.is_file() or path.is_symlink() or st.st_nlink != 1:
            raise ValueError(f"source is not an admitted regular file: {path.name}")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        self.fd = os.open(path, flags)
        self.f = os.fdopen(self.fd, "rb", buffering=0)
        self.path = path
    def close(self): self.f.close()
    def read(self, n: int) -> bytes: return exact_read(self.f, n)
    def u32(self) -> int: return struct.unpack("<I", self.read(4))[0]
    def u64(self) -> int: return struct.unpack("<Q", self.read(8))[0]
    def string(self) -> str:
        n = self.u64()
        if n > 1 << 24: raise ValueError("oversized GGUF string")
        return self.read(n).decode("utf-8")
    def skip_value(self, ty: int, keep: bool = True) -> Any:
        fixed = {0:(1,"<B"),1:(1,"<b"),2:(2,"<H"),3:(2,"<h"),4:(4,"<I"),5:(4,"<i"),6:(4,"<f"),7:(1,"<B"),10:(8,"<Q"),11:(8,"<q"),12:(8,"<d")}
        if ty in fixed:
            n, fmt = fixed[ty]; v = struct.unpack(fmt, self.read(n))[0]
            return bool(v) if ty == 7 else v
        if ty == 8: return self.string()
        if ty == 9:
            et = self.u32(); count = self.u64()
            if count > 1 << 26: raise ValueError("oversized GGUF array")
            if keep and count <= 64:
                return [self.skip_value(et, True) for _ in range(count)]
            for _ in range(count): self.skip_value(et, False)
            return {"array_type": et, "count": count}
        raise ValueError(f"unknown GGUF metadata type {ty}")


@dataclass(frozen=True)
class Tensor:
    name: str; dims: tuple[int, ...]; type_id: int; type_name: str
    block_elements: int; block_bytes: int; row_bytes: int; byte_size: int
    shard: str; shard_ordinal: int; shard_sha256: str; offset: int; end: int


@dataclass(frozen=True)
class ExpectedComponent:
    role: str; tensor: Tensor; offset: int; length: int; bundle_offset: int


@dataclass(frozen=True)
class ExpectedObject:
    layer: int; expert_class: str; expert: int; relative_path: str
    components: tuple[ExpectedComponent, ...]


def parse_shard(path: Path, ordinal: int, shard_sha: str) -> tuple[dict[str, Any], list[Tensor], int]:
    r = Reader(path)
    try:
        if r.read(4) != b"GGUF": raise ValueError("bad GGUF magic")
        version = r.u32()
        if version != 3: raise ValueError(f"GGUF version {version}")
        nt, nk = r.u64(), r.u64()
        if nt > 1 << 20 or nk > 1 << 20: raise ValueError("implausible GGUF counts")
        kv: dict[str, Any] = {}
        for _ in range(nk):
            key = r.string()
            if key in kv: raise ValueError(f"duplicate metadata key {key}")
            kv[key] = r.skip_value(r.u32(), key in {"general.architecture","general.alignment","glm-dsa.block_count","glm-dsa.expert_count","glm-dsa.expert_shared_count"})
        raw = []
        seen = set()
        for _ in range(nt):
            name = r.string()
            if name in seen: raise ValueError(f"duplicate tensor {name}")
            seen.add(name)
            nd = r.u32()
            if nd == 0 or nd > 8: raise ValueError("bad tensor rank")
            dims = tuple(r.u64() for _ in range(nd))
            ty, rel = r.u32(), r.u64()
            raw.append((name,dims,ty,rel))
        alignment = kv.get("general.alignment", 32)
        if not isinstance(alignment, int) or alignment <= 0 or alignment & (alignment-1):
            raise ValueError("bad GGUF alignment")
        data_start = (r.f.tell()+alignment-1)//alignment*alignment
        file_size = path.stat().st_size
        tensors=[]
        for name,dims,ty,rel in raw:
            if ty not in QUANT: raise ValueError(f"unsupported live type {ty} {name}")
            type_name,be,bb=QUANT[ty]
            if dims[0] % be: raise ValueError(f"split quant row {name}")
            row=dims[0]//be*bb
            size=row
            for d in dims[1:]: size*=d
            off=data_start+rel; end=off+size
            if end>file_size: raise ValueError(f"tensor outside shard {name}")
            tensors.append(Tensor(name,dims,ty,type_name,be,bb,row,size,path.name,ordinal,shard_sha,off,end))
        byoff=sorted(tensors,key=lambda t:t.offset)
        for a,b in zip(byoff,byoff[1:]):
            if a.end>b.offset: raise ValueError(f"tensor overlap {a.name} {b.name}")
        return kv,tensors,data_start
    finally: r.close()


def load_admission(path: Path, root: Path) -> tuple[dict[str,Any], list[tuple[Path,dict[str,Any]]]]:
    admission=json.loads(path.read_text())
    set_sha=admission.get("checkpoint_set_sha256",admission.get("set_sha256"))
    if set_sha != CHECKPOINT or admission["total_bytes"] != 238458632928:
        raise ValueError("checkpoint admission mismatch")
    shards=[]
    for i,s in enumerate(admission["shards"],1):
        name=s.get("name",s.get("filename")); size=s.get("size",s.get("size_bytes")); sha=s.get("sha256",s.get("destination_sha256"))
        p=root/name
        st=p.lstat()
        if p.is_symlink() or not p.is_file() or st.st_nlink!=1 or st.st_size!=size:
            raise ValueError(f"source stat mismatch {name}")
        dst=s.get("destination_stat")
        if dst:
            got={"size":st.st_size,"mtime_ns":st.st_mtime_ns,"inode":st.st_ino}
            if got!=dst: raise ValueError(f"source changed since admission {name}")
        shards.append((p,{"name":name,"size":size,"sha256":sha,"ordinal":i,"stat":(st.st_size,st.st_mtime_ns,st.st_ino)}))
    return admission,shards


def reconstruct(root: Path, admission_path: Path) -> tuple[dict[tuple[int,str,str],Tensor], dict[str,Any]]:
    _, shards=load_admission(admission_path,root)
    merged={}; tensors=[]; names=set()
    for p,s in shards:
        kv,ts,_=parse_shard(p,s["ordinal"],s["sha256"])
        for k,v in kv.items(): merged.setdefault(k,v)
        for t in ts:
            if t.name in names: raise ValueError(f"duplicate cross-shard tensor {t.name}")
            names.add(t.name); tensors.append(t)
    if merged.get("general.architecture")!="glm-dsa" or merged.get("glm-dsa.block_count")!=79 or merged.get("glm-dsa.expert_count")!=256 or merged.get("glm-dsa.expert_shared_count")!=1:
        raise ValueError("live architecture metadata mismatch")
    expert={}; payload=0
    for t in tensors:
        m=EXPERT_RE.match(t.name)
        if not m: continue
        layer=int(m.group(1)); role=m.group(2); cls="routed" if m.group(3)=="exps" else "shared"
        if cls=="routed" and (len(t.dims)!=3 or t.dims[2]!=256): raise ValueError(f"expert axis {t.name}")
        if cls=="shared" and len(t.dims)!=2: raise ValueError(f"shared dims {t.name}")
        key=(layer,cls,role)
        if key in expert: raise ValueError(f"duplicate expert tensor {key}")
        expert[key]=t; payload+=t.byte_size
    if len(expert)!=456 or payload!=224974307328 or sorted({k[0] for k in expert})!=list(range(3,79)):
        raise ValueError("live expert coverage mismatch")
    return expert,{"architecture":"glm-dsa","expert_tensor_count":len(expert),"expert_payload_bytes":payload}


def expected_object(expert_map: dict[tuple[int,str,str],Tensor], layer:int, cls:str, expert:int) -> ExpectedObject:
    if cls not in {"routed","shared"} or (cls=="shared" and expert!=0) or not 0<=expert<256:
        raise ValueError("bad object key")
    components=[]; cursor=HEADER_LEN
    for role in ("gate","up","down"):
        t=expert_map[(layer,cls,role)]
        count=256 if cls=="routed" else 1
        plane=t.byte_size//count
        if plane*count!=t.byte_size or plane%t.block_bytes: raise ValueError("plane split")
        off=t.offset+expert*plane
        if off+plane>t.end: raise ValueError("expert outside tensor")
        bundle=(cursor+ALIGNMENT-1)//ALIGNMENT*ALIGNMENT
        components.append(ExpectedComponent(role,t,off,plane,bundle))
        cursor=(bundle+plane+ALIGNMENT-1)//ALIGNMENT*ALIGNMENT
    rel=f"objects/layer-{layer:03d}/{cls}/expert-{expert:03d}.pmlxexp"
    return ExpectedObject(layer,cls,expert,rel,tuple(components))


def plan_component(c: ExpectedComponent) -> dict[str,Any]:
    t=c.tensor
    return {"block_bytes":t.block_bytes,"block_elements":t.block_elements,"dims":list(t.dims),"length":c.length,"role":c.role,"row_bytes":t.row_bytes,"source_length":c.length,"source_offset":c.offset,"source_shard":t.shard,"source_shard_ordinal":t.shard_ordinal,"tensor":t.name,"type_id":t.type_id,"type_name":t.type_name}


def plan_projection(inventory_sha:str, objects:list[ExpectedObject], scope:Any)->dict[str,Any]:
    return {"alignment":ALIGNMENT,"architecture":"glm-dsa","checkpoint_set_sha256":CHECKPOINT,"format_major":1,"format_minor":0,"inventory_sha256":inventory_sha,"objects":[{"class":o.expert_class,"components":[plan_component(c) for c in o.components],"expert":o.expert,"layer":o.layer,"relative_path":o.relative_path} for o in objects],"ordering":"layer,class,expert","schema":"pulsarmlx.r001.manifest-plan.v1","scope":scope}


def parse_manifest(path:Path)->tuple[dict[str,Any],list[dict[str,Any]],dict[str,Any],str]:
    raw=path.read_bytes()
    if not raw.endswith(b"\n") or b"\r" in raw: raise ValueError("manifest framing")
    lines=raw.splitlines(keepends=True)
    records=[]
    for line in lines:
        body=line[:-1]
        value=json.loads(body)
        if canonical(value)!=body: raise ValueError("noncanonical manifest record")
        records.append(value)
    if len(records)<2 or records[0].get("record_type")!="manifest_header" or records[-1].get("record_type")!="manifest_footer": raise ValueError("manifest record order")
    if hashlib.sha256(b"".join(lines[:-1])).hexdigest()!=records[-1]["preceding_records_sha256"]: raise ValueError("manifest preceding hash")
    objects=records[1:-1]
    if any(x.get("record_type")!="object" for x in objects) or len(objects)!=records[0]["object_count"] or len(objects)!=records[-1]["object_count"]: raise ValueError("manifest object count")
    keys=[(x["layer"],0 if x["expert_class"]=="routed" else 1,x["expert"]) for x in objects]
    if keys!=sorted(keys) or len(keys)!=len(set(keys)): raise ValueError("manifest object ordering/duplicate")
    return records[0],objects,records[-1],hashlib.sha256(raw).hexdigest()


def read_range(path:Path,offset:int,length:int):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0))
    try:
        pos=0
        while pos<length:
            b=os.pread(fd,min(CHUNK,length-pos),offset+pos)
            if not b: raise EOFError("short pread")
            yield b;pos+=len(b)
    finally: os.close(fd)


def read_one(path:Path,offset:int,length:int)->bytes:
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0))
    try:
        b=os.pread(fd,length,offset)
        if len(b)!=length: raise EOFError("short semantic pread")
        return b
    finally: os.close(fd)


def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb",buffering=0) as f:
        while True:
            b=f.read(CHUNK)
            if not b: break
            h.update(b)
    return h.hexdigest()


def layout_projection(o:ExpectedObject,c:ExpectedComponent)->dict[str,Any]:
    t=c.tensor
    return {"architecture":"glm-dsa","block_bytes":t.block_bytes,"block_elements":t.block_elements,"dims":list(t.dims),"expert_class":o.expert_class,"plane_bytes":c.length,"role":c.role,"row_bytes":t.row_bytes,"schema":"pulsarmlx.r001.layout.v1","type_id":t.type_id,"type_name":t.type_name}


def identity_component(c:ExpectedComponent,sha:str,layout_sha:str)->dict[str,Any]:
    t=c.tensor
    return {"block_bytes":t.block_bytes,"block_elements":t.block_elements,"bundle_offset":c.bundle_offset,"component_sha256":sha,"dims":list(t.dims),"layout_class_sha256":layout_sha,"length":c.length,"role":c.role,"row_bytes":t.row_bytes,"source":{"length":c.length,"offset":c.offset,"sha256":sha,"shard":t.shard,"shard_ordinal":t.shard_ordinal,"shard_sha256":t.shard_sha256},"tensor":t.name,"type_id":t.type_id,"type_name":t.type_name}


def decode_block(type_id:int,block:bytes)->bytes:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    if type_id==16:
        from iq2_xxs_dequant import dequantize_row_iq2_xxs as fn
    elif type_id==18:
        from iq3_xxs_dequant import dequantize_row_iq3_xxs as fn
    elif type_id==22:
        from iq2_s_dequant import dequantize_row_iq2_s as fn
    elif type_id==23:
        from iq4_xs_dequant import dequantize_row_iq4_xs as fn
    elif type_id in (10,11,13,14):
        from ggml_kquants import dequantize_row_q2_k,dequantize_row_q3_k,dequantize_row_q5_k,dequantize_row_q6_k
        fn={10:dequantize_row_q2_k,11:dequantize_row_q3_k,13:dequantize_row_q5_k,14:dequantize_row_q6_k}[type_id]
    elif type_id==8:
        if len(block)!=34: raise ValueError("Q8_0 block")
        d=struct.unpack_from("<e",block)[0]; vals=struct.unpack_from("<32b",block,2)
        return struct.pack("<32f",*(d*x for x in vals))
    else: raise ValueError(f"no semantic decoder {type_id}")
    values=fn(block)
    return struct.pack(f"<{len(values)}f",*values)


def verify_bundle(bundle:Path,record:dict[str,Any],expected:ExpectedObject,checkpoint_root:Path,semantic_seen:set[int])->dict[str,Any]:
    st=bundle.lstat()
    if bundle.is_symlink() or not bundle.is_file() or st.st_nlink!=1: raise ValueError("unsafe bundle file")
    with bundle.open("rb",buffering=0) as f:
        header=exact_read(f,HEADER_LEN)
        if header[:8]!=b"PMLXEX01" or struct.unpack_from("<HH",header,8)!=(1,0): raise ValueError("bundle magic/version")
        preamble,hlen,flags,layer,expert,cls,count,align,res=struct.unpack_from("<IIIIIIIII",header,12)
        if (preamble,hlen,flags,layer,expert,cls,count,align,res)!=(128,HEADER_LEN,0,expected.layer,expected.expert,1 if expected.expert_class=="routed" else 2,3,ALIGNMENT,0): raise ValueError("bundle preamble identity")
        payload_len,physical_len,footer_off,file_len,metadata_len=struct.unpack_from("<QQQQQ",header,48)
        if file_len!=st.st_size or file_len!=footer_off+FOOTER_LEN or metadata_len>HEADER_LEN-128 or any(header[120:128]): raise ValueError("bundle lengths/reserved")
        metadata_bytes=header[128:128+metadata_len]
        if hashlib.sha256(metadata_bytes).digest()!=header[88:120] or any(header[128+metadata_len:]): raise ValueError("metadata hash/padding")
        metadata=json.loads(metadata_bytes)
        if canonical(metadata)!=metadata_bytes: raise ValueError("metadata canonicalization")
        f.seek(footer_off); footer=exact_read(f,FOOTER_LEN)
    if footer[:8]!=b"PMLXEND1" or struct.unpack_from("<HHI",footer,8)!=(1,0,FOOTER_LEN) or struct.unpack_from("<Q",footer,16)[0]!=file_len or any(footer[184:]): raise ValueError("footer")
    if hashlib.sha256(header).digest()!=footer[24:56]: raise ValueError("header block hash")
    z=bytearray(footer);z[152:184]=bytes(32)
    if hashlib.sha256(z).digest()!=footer[152:184]: raise ValueError("footer self hash")
    ph=hashlib.sha256()
    for b in read_range(bundle,HEADER_LEN,footer_off-HEADER_LEN): ph.update(b)
    if ph.digest()!=footer[56:88]: raise ValueError("physical payload hash")
    if metadata["checkpoint_set_sha256"]!=CHECKPOINT or metadata["layer"]!=expected.layer or metadata["expert"]!=expected.expert or metadata["expert_class"]!=expected.expert_class or metadata["canonical_payload_len"]!=payload_len or metadata["physical_payload_region_len"]!=physical_len: raise ValueError("metadata object identity")
    components=metadata["components"]
    if len(components)!=3: raise ValueError("component count")
    canonical_payload=hashlib.sha256(b"PULSARMLX-R001-CANONICAL-PAYLOAD-V1\0")
    identities=[];previous=HEADER_LEN;sem=[]
    for index,(claim,exp) in enumerate(zip(components,expected.components,strict=True)):
        t=exp.tensor
        if claim["role"]!=exp.role or claim["tensor"]!=t.name or claim["bundle_offset"]!=exp.bundle_offset or claim["length"]!=exp.length or claim["type_id"]!=t.type_id or claim["dims"]!=list(t.dims) or claim["source"]["shard"]!=t.shard or claim["source"]["offset"]!=exp.offset or claim["source"]["length"]!=exp.length: raise ValueError("component mapping mismatch")
        if exp.bundle_offset>previous:
            if any(b for chunk in read_range(bundle,previous,exp.bundle_offset-previous) for b in chunk): raise ValueError("nonzero padding")
        source_path=checkpoint_root/t.shard
        sh=hashlib.sha256();bh=hashlib.sha256();pos=0
        source_iter=read_range(source_path,exp.offset,exp.length);bundle_iter=read_range(bundle,exp.bundle_offset,exp.length)
        for sb,bb in zip(source_iter,bundle_iter,strict=True):
            if sb!=bb: raise ValueError("source/bundle byte mismatch")
            sh.update(sb);bh.update(bb)
            pos+=len(sb)
        digest=sh.hexdigest()
        if pos!=exp.length or digest!=bh.hexdigest() or digest!=claim["component_sha256"] or digest!=claim["source"]["sha256"]: raise ValueError("component byte/hash mismatch")
        # Canonical payload framing applies once per component, then exact bytes.
        canonical_payload.update(bytes([index+1]));canonical_payload.update(struct.pack("<Q",exp.length))
        for bb in read_range(bundle,exp.bundle_offset,exp.length): canonical_payload.update(bb)
        layout_sha=domain_hash(b"PULSARMLX-R001-LAYOUT-V1",layout_projection(expected,exp))
        identity=identity_component(exp,digest,layout_sha)
        if claim!=identity: raise ValueError("component identity projection mismatch")
        identities.append(identity);previous=exp.bundle_offset+exp.length
        if t.type_id not in semantic_seen:
            offsets={0,exp.length-t.block_bytes,max(0,exp.length-t.row_bytes)}
            seed=int.from_bytes(hashlib.sha256(f"{CHECKPOINT}:{expected.layer}:{expected.expert}:{exp.role}:R001-semantic-sample-v1".encode()).digest()[:8],"little")
            blocks=exp.length//t.block_bytes
            offsets.update(((seed+i*0x9E3779B97F4A7C15)%blocks)*t.block_bytes for i in range(2))
            for rel in sorted(offsets):
                src=read_one(source_path,exp.offset+rel,t.block_bytes)
                bun=read_one(bundle,exp.bundle_offset+rel,t.block_bytes)
                if src!=bun or decode_block(t.type_id,src)!=decode_block(t.type_id,bun): raise ValueError("semantic block mismatch")
            semantic_seen.add(t.type_id);sem.append(t.type_name)
    payload_sha=canonical_payload.hexdigest()
    if bytes.fromhex(payload_sha)!=footer[88:120] or payload_sha!=metadata["canonical_payload_sha256"]: raise ValueError("canonical payload hash")
    projection={"architecture":"glm-dsa","canonical_payload_sha256":payload_sha,"checkpoint_set_sha256":CHECKPOINT,"components":identities,"expert":expected.expert,"expert_class":expected.expert_class,"inventory_sha256":metadata["inventory_sha256"],"layer":expected.layer,"manifest_plan_id":metadata["manifest_plan_id"],"schema":"pulsarmlx.r001.object-identity.v1"}
    object_id=domain_hash(b"PULSARMLX-R001-OBJECT-V1",projection)
    if object_id!=metadata["object_identity_sha256"] or bytes.fromhex(object_id)!=footer[120:152] or object_id!=record["object_identity_sha256"]: raise ValueError("object identity hash")
    stored=sha256_file(bundle)
    if stored!=record["stored_sha256"] or st.st_size!=record["stored_len"]: raise ValueError("stored representation hash")
    return {"bytes":payload_len,"semantic_types":sem}


def verify_all(args)->dict[str,Any]:
    expert_map,live=reconstruct(args.checkpoint_dir,args.admission)
    header,records,footer,manifest_sha=parse_manifest(args.manifest)
    scope=header["scope"]
    expected=[]
    for s in scope:
        for e in s["routed_experts"]: expected.append(expected_object(expert_map,s["layer"],"routed",e))
        if s["shared"]: expected.append(expected_object(expert_map,s["layer"],"shared",0))
    expected.sort(key=lambda o:(o.layer,0 if o.expert_class=="routed" else 1,o.expert))
    if len(expected)!=len(records): raise ValueError("scope/manifest coverage")
    inventory_sha=header["inventory_sha256"]
    plan_id=domain_hash(b"PULSARMLX-R001-MANIFEST-PLAN-V1",plan_projection(inventory_sha,expected,scope))
    if plan_id!=header["manifest_plan_id"]: raise ValueError("manifest plan identity")
    semantic_seen=set();total=0
    for record,exp in zip(records,expected,strict=True):
        if record["relative_path"]!=exp.relative_path: raise ValueError("manifest relative path")
        p=(args.manifest.parent/record["relative_path"]).resolve()
        root=args.manifest.parent.resolve()
        if root not in p.parents: raise ValueError("manifest path traversal")
        result=verify_bundle(p,record,exp,args.checkpoint_dir,semantic_seen);total+=result["bytes"]
    required={8,10,11,13,14,16,18,22,23}
    if semantic_seen!=required: raise ValueError(f"semantic types incomplete {semantic_seen}")
    return {"schema":"pulsarmlx.r001.independent-verification.v1","status":"passed","manifest_sha256":manifest_sha,"manifest_plan_id":plan_id,"object_count":len(records),"component_count":len(records)*3,"payload_bytes":total,"live_inventory":live,"semantic_type_ids":sorted(semantic_seen),"semantic_classification":"mapping_sanity_not_decoder_qualification"}


def negative_tests(args)->dict[str,Any]:
    expert_map,_=reconstruct(args.checkpoint_dir,args.admission)
    header,records,_,_=parse_manifest(args.manifest)
    rec=records[0];exp=expected_object(expert_map,rec["layer"],rec["expert_class"],rec["expert"])
    source=args.manifest.parent/rec["relative_path"]
    args.scratch.mkdir(parents=True,exist_ok=True)
    if any(args.scratch.iterdir()): raise ValueError("negative scratch must be empty")
    cases=[]
    def expect_fail(name,mutate,wrong_expected=None):
        p=args.scratch/f"{name}.pmlxexp";shutil.copyfile(source,p);mutate(p)
        try: verify_bundle(p,rec,wrong_expected or exp,args.checkpoint_dir,set())
        except Exception as e: cases.append({"case":name,"status":"rejected","error":type(e).__name__});return
        raise AssertionError(f"negative case passed: {name}")
    expect_fail("bad_header",lambda p: _flip(p,0))
    expect_fail("payload_corrupt",lambda p: _flip(p,HEADER_LEN))
    expect_fail("footer_corrupt",lambda p: _flip(p,p.stat().st_size-FOOTER_LEN))
    expect_fail("truncated",lambda p: os.truncate(p,p.stat().st_size-1))
    expect_fail("trailing",lambda p: p.open("ab").write(b"x"))
    wrong=expected_object(expert_map,exp.layer,exp.expert_class,exp.expert+1)
    expect_fail("wrong_expert",lambda p: None,wrong)
    partial=args.scratch/"interrupted.partial";partial.write_bytes(source.read_bytes()[:8192])
    try: verify_bundle(partial,rec,exp,args.checkpoint_dir,set())
    except Exception as e: cases.append({"case":"interrupted_partial","status":"rejected","error":type(e).__name__})
    else: raise AssertionError("interrupted partial passed")
    return {"schema":"pulsarmlx.r001.negative-tests.v1","status":"passed","cases":cases,"count":len(cases)}


def _flip(path:Path,offset:int):
    with path.open("r+b",buffering=0) as f:
        f.seek(offset);b=f.read(1);f.seek(offset);f.write(bytes([b[0]^1]));f.flush();os.fsync(f.fileno())


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="cmd",required=True)
    for name in ("verify","negative"):
        q=sub.add_parser(name);q.add_argument("--checkpoint-dir",type=Path,required=True);q.add_argument("--admission",type=Path,required=True);q.add_argument("--manifest",type=Path,required=True);q.add_argument("--out",type=Path,required=True)
        if name=="negative": q.add_argument("--scratch",type=Path,required=True)
    args=p.parse_args()
    result=verify_all(args) if args.cmd=="verify" else negative_tests(args)
    if args.out.exists(): raise SystemExit(f"refuse existing output {args.out}")
    with args.out.open("x") as f: json.dump(result,f,sort_keys=True,separators=(",",":"));f.write("\n");f.flush();os.fsync(f.fileno())
    print(json.dumps(result,sort_keys=True));return 0


if __name__=="__main__": raise SystemExit(main())

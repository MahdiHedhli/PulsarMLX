#!/usr/bin/env python3
"""Authorization-bound secondary checkpoint source; contains no graph arithmetic."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import numpy as np

AUTH_SCHEMA = 'pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0'


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=_pairs)


def hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class SecondaryTargetSourceV6:
    """Separate target reader/decoder dispatch for the accelerated consumer."""
    def __init__(self, auth: dict, catalog: Path, checkpoint_root: Path,
                 identity_file: Path, event_root: Path):
        if auth["secondary"].get("role") != "INDEPENDENT_ACCELERATED_CROSS_CHECK": raise ValueError("secondary consumer not granted")
        if hash_path(Path(__file__).resolve())!=auth["secondary"].get("target_source_sha256"): raise ValueError("secondary producer identity mismatch")
        if hash_path(catalog.resolve(strict=True))!=auth.get("checkpoint_catalog_sha256"): raise ValueError("catalog identity mismatch")
        root = checkpoint_root.resolve(strict=True)
        if str(root) != auth.get("checkpoint_root") or root.is_symlink():
            raise ValueError("checkpoint root authority mismatch")
        self.root, self.auth = root, auth
        self.records = {item["name"]: item for item in strict(catalog)["tensors"]}
        self.shards = {item["filename"]: item for item in auth["shards"]}
        self.handles = {};self.reads={}
        self.event_root=event_root;self.event_root.mkdir(mode=0o700,parents=False,exist_ok=False);self.sequence=0
        self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_ATTEMPT",str(identity_file),"STARTED_READ_ONLY_NOFOLLOW")
        try:
            descriptor=os.open(identity_file,os.O_RDONLY|os.O_NOFOLLOW)
            try:
                identity_stat=os.fstat(descriptor)
                if not stat.S_ISREG(identity_stat.st_mode) or identity_stat.st_size>1024*1024:
                    raise ValueError("checkpoint identity evidence file")
                identity_bytes=os.read(descriptor,identity_stat.st_size)
                if len(identity_bytes)!=identity_stat.st_size or os.read(descriptor,1):
                    raise ValueError("checkpoint identity evidence readback")
            finally: os.close(descriptor)
            identity=json.loads(identity_bytes,object_pairs_hook=_pairs)
            if identity.get("authorization_id")!=auth["authorization_id"] or identity.get("result")!="PASS" or identity.get("shards")!=auth["shards"]:
                raise ValueError("checkpoint identity evidence mismatch")
            self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT",str(identity_file),"PASS_BOUND",len(identity_bytes))
        except Exception as exc:
            self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT",str(identity_file),f"FAIL_{type(exc).__name__}")
            raise
    def _event(self,kind,authority,result,size=0,tensor=None,offset=None,descriptor=None,expert=None,count=None):
        value={"schema":"pulsarmlx.f017.corrected-oracle-access-event/1.0.0","sequence":self.sequence,
               "authorization_id":self.auth["authorization_id"],"consumer":"INDEPENDENT_ACCELERATED_CROSS_CHECK",
               "process_id":os.getpid(),"kind":kind,"authority_id":authority,"result":result,"size_bytes":size,"tensor_name":tensor,
               "offset_bytes":offset,"descriptor_identity":descriptor,"expert_ordinal":expert,"repeat_count":count}
        data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode();path=self.event_root/f"{self.sequence:08}.json"
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,"wb") as out: out.write(data);out.flush();os.fsync(out.fileno())
        dfd=os.open(self.event_root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(dfd)
        rfd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
        with os.fdopen(rfd,"rb") as source: observed=source.read()
        os.close(dfd)
        if observed!=data: raise ValueError("access event readback")
        strict(path)
        self.sequence+=1
    def _get(self, name, expert, rows, cols, row_start=0):
        from qualify_f017_quantization_matrix_v1 import independent_decode
        record = self.records[name]; fmt = record["type"]
        type_layout={"F32":(1,4),"Q8_0":(32,34),"Q2_K":(256,84),"Q3_K":(256,110),"Q4_K":(256,144),"Q5_K":(256,176),"Q6_K":(256,210),"IQ2_S":(256,82),"IQ2_XXS":(256,66),"IQ3_XXS":(256,98),"IQ4_XS":(256,136)}
        values_per_block,bytes_per_block=type_layout[fmt]
        row_bytes=cols//values_per_block*bytes_per_block; size=rows*row_bytes
        full_rows=int(record["dims"][1]) if len(record["dims"])>1 else 1
        offset=int(record["data_offset_abs"])+(0 if expert is None else expert*full_rows*row_bytes)+row_start*row_bytes
        shard=record["file"]
        if shard not in self.handles:
            expected=self.shards.get(shard)
            if not expected:
                self._event("SHARD_OPEN_ATTEMPT",shard,"REJECT_UNAUTHORIZED_SHARD");raise ValueError("unauthorized shard")
            self._event("SHARD_OPEN_ATTEMPT",shard,"STARTED_READ_ONLY_NOFOLLOW")
            try:
                descriptor=os.open(self.root/shard,os.O_RDONLY|os.O_NOFOLLOW);stat=os.fstat(descriptor)
                identity=f"dev={stat.st_dev};ino={stat.st_ino};mode={stat.st_mode:o}"
                if stat.st_size!=int(expected["size_bytes"]):
                    os.close(descriptor);self._event("SHARD_OPEN_RESULT",shard,"FAIL_SIZE_MISMATCH",stat.st_size,descriptor=identity);raise ValueError("shard size mismatch")
                self.handles[shard]=descriptor;self._event("SHARD_OPEN_RESULT",shard,"PASS_READ_ONLY_NOFOLLOW",stat.st_size,descriptor=identity)
            except ValueError:
                raise
            except Exception as exc:
                if shard not in self.handles: self._event("SHARD_OPEN_RESULT",shard,f"FAIL_{type(exc).__name__}")
                raise
        seen=name in self.reads
        if not seen:
            self._event("TENSOR_RESOLUTION",name,"PASS_CATALOG_BOUND",size,name,offset,expert=expert)
            self._event("PAYLOAD_READ_ATTEMPT",name,"STARTED_EXACT_PREAD",size,name,offset,expert=expert)
        try: raw=os.pread(self.handles[shard],size,offset)
        except Exception as exc:
            self._event("PAYLOAD_READ_RESULT",name,f"FAIL_{type(exc).__name__}",0,name,offset,expert=expert);raise
        if len(raw)!=size:
            self._event("PAYLOAD_READ_RESULT",name,"FAIL_SHORT_READ",len(raw),name,offset,expert=expert);raise ValueError("short tensor read")
        if not seen:
            self._event("PAYLOAD_READ_RESULT",name,"PASS_EXACT_PREAD",len(raw),name,offset,expert=expert)
            self._event("TENSOR_FIRST_USE",name,"PASS_DECODE_INPUT",len(raw),name,offset,expert=expert)
            self.reads[name]={"count":1,"bytes":len(raw)}
        else:
            self.reads[name]["count"]+=1;self.reads[name]["bytes"]+=len(raw)
        values=independent_decode(fmt,raw,rows*cols)
        return np.asarray(values,dtype=np.float32).reshape(rows,cols)
    def vector(self,name,n): return self._get(name,None,1,n).reshape(n)
    def matrix(self,name,rows,cols): return SecondaryTargetMatrixV6(self,name,None,rows,cols)
    def expert(self,name,expert,rows,cols): return SecondaryTargetMatrixV6(self,name,expert,rows,cols)
    def close(self):
        for tensor,summary in sorted(self.reads.items()): self._event("TENSOR_REUSE_SUMMARY",tensor,"PASS_COMPLETE",summary["bytes"],tensor,count=max(0,summary["count"]-1))
        for shard,descriptor in self.handles.items(): os.close(descriptor);self._event("SHARD_TEARDOWN",shard,"PASS_CLOSE")
        self.handles.clear()


class SecondaryTargetMatrixV6:
    def __init__(self,source,name,expert,rows,cols): self.source,self.name,self.expert,self.rows,self.cols=source,name,expert,rows,cols
    def row(self,index): return self.source._get(self.name,self.expert,1,self.cols,index).reshape(self.cols)
    def __getitem__(self,item):
        if isinstance(item,int): return self.row(item)
        raise ValueError("catalog matrix supports row indexing only")

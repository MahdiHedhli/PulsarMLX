#!/usr/bin/env python3
"""Authorization-bound primary checkpoint source; contains no graph arithmetic."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from f017_oracle_primary_decoders import LAYOUT, decode

AUTH_SCHEMA = 'pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0'


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=_pairs)


def _hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class PrimaryTargetSourceV6:
    """Memory-bounded target source, constructed only after live authority.

    Each tensor is read as one encoded row (or a bounded block chunk), decoded,
    returned, and released by the caller. Files are opened read-only with
    O_NOFOLLOW; this class is never instantiated by qualification commands.
    """
    def __init__(self, auth: dict, catalog: Path, checkpoint_root: Path,
                 identity_file: Path, event_root: Path):
        if auth["primary"].get("role") != "INDEPENDENT_CPU_REFERENCE":
            raise ValueError("primary consumer not granted")
        if _hash_path(Path(__file__).resolve()) != auth["primary"].get("target_source_sha256"):
            raise ValueError("primary producer identity mismatch")
        if _hash_path(catalog.resolve(strict=True)) != auth.get("checkpoint_catalog_sha256"):
            raise ValueError("catalog identity mismatch")
        root = checkpoint_root.resolve(strict=True)
        if str(root) != auth.get("checkpoint_root") or root.is_symlink():
            raise ValueError("checkpoint root authority mismatch")
        document = _strict_json(catalog)
        self.records = {item["name"]: item for item in document["tensors"]}
        self.shards = {item["filename"]: item for item in auth["shards"]}
        self.root, self.auth = root, auth
        self.handles: dict[str, int] = {}
        self.reads: dict[str, dict[str, int]] = {}
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
               "authorization_id":self.auth["authorization_id"],"consumer":"INDEPENDENT_CPU_REFERENCE",
               "process_id":os.getpid(),"kind":kind,"authority_id":authority,"result":result,
               "size_bytes":size,"tensor_name":tensor,"offset_bytes":offset,
               "descriptor_identity":descriptor,"expert_ordinal":expert,"repeat_count":count}
        data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode();path=self.event_root/f"{self.sequence:08}.json"
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,"wb") as out: out.write(data);out.flush();os.fsync(out.fileno())
        dfd=os.open(self.event_root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(dfd)
        rfd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
        with os.fdopen(rfd,"rb") as source: observed=source.read()
        os.close(dfd)
        if observed!=data: raise ValueError("access event readback")
        _strict_json(path)
        self.sequence+=1

    def _raw(self, record: dict, expert: int | None, rows: int, columns: int, row_start: int = 0) -> bytes:
        fmt = record["type"]
        block_values, block_bytes = LAYOUT[fmt]
        if columns % block_values:
            raise ValueError("partial encoded row prohibited")
        row_bytes = columns // block_values * block_bytes
        matrix_bytes = row_bytes * rows
        full_rows = int(record["dims"][1]) if len(record["dims"]) > 1 else 1
        full_matrix_bytes = row_bytes * full_rows
        offset = int(record["data_offset_abs"]) + (0 if expert is None else expert * full_matrix_bytes) + row_start * row_bytes
        shard = record["file"]
        if shard not in self.handles:
            expected = self.shards.get(shard)
            if not expected:
                self._event("SHARD_OPEN_ATTEMPT", shard, "REJECT_UNAUTHORIZED_SHARD")
                raise ValueError("unauthorized shard")
            self._event("SHARD_OPEN_ATTEMPT", shard, "STARTED_READ_ONLY_NOFOLLOW")
            try:
                descriptor = os.open(self.root / shard, os.O_RDONLY | os.O_NOFOLLOW)
                stat = os.fstat(descriptor)
                identity = f"dev={stat.st_dev};ino={stat.st_ino};mode={stat.st_mode:o}"
                if stat.st_size != int(expected["size_bytes"]):
                    os.close(descriptor)
                    self._event("SHARD_OPEN_RESULT", shard, "FAIL_SIZE_MISMATCH", stat.st_size,
                                descriptor=identity)
                    raise ValueError("shard size mismatch")
                self.handles[shard] = descriptor
                self._event("SHARD_OPEN_RESULT", shard, "PASS_READ_ONLY_NOFOLLOW", stat.st_size,
                            descriptor=identity)
            except ValueError:
                raise
            except Exception as exc:
                if shard not in self.handles:
                    self._event("SHARD_OPEN_RESULT", shard, f"FAIL_{type(exc).__name__}")
                raise
        seen = record["name"] in self.reads
        if not seen:
            self._event("TENSOR_RESOLUTION",record["name"],"PASS_CATALOG_BOUND",matrix_bytes,record["name"],offset,expert=expert)
            self._event("PAYLOAD_READ_ATTEMPT", record["name"], "STARTED_EXACT_PREAD",
                        matrix_bytes, record["name"], offset, expert=expert)
        try:
            raw = os.pread(self.handles[shard], matrix_bytes, offset)
        except Exception as exc:
            self._event("PAYLOAD_READ_RESULT", record["name"], f"FAIL_{type(exc).__name__}",
                        0, record["name"], offset, expert=expert)
            raise
        if len(raw) != matrix_bytes:
            self._event("PAYLOAD_READ_RESULT", record["name"], "FAIL_SHORT_READ",
                        len(raw), record["name"], offset, expert=expert)
            raise ValueError("short tensor read")
        if not seen:
            self._event("PAYLOAD_READ_RESULT", record["name"], "PASS_EXACT_PREAD",
                        len(raw), record["name"], offset, expert=expert)
            self._event("TENSOR_FIRST_USE",record["name"],"PASS_DECODE_INPUT",len(raw),record["name"],offset,expert=expert)
            self.reads[record["name"]] = {"count": 1, "bytes": len(raw)}
        else:
            self.reads[record["name"]]["count"] += 1
            self.reads[record["name"]]["bytes"] += len(raw)
        return raw

    def _tensor(self, name: str, expert: int | None, rows: int, columns: int) -> list[float]:
        record = self.records.get(name)
        if record is None:
            raise ValueError(f"catalog tensor missing: {name}")
        expected_dims = [columns] if rows == 1 and len(record.get("dims", [])) == 1 else [columns, rows]
        if record["dims"][:len(expected_dims)] != expected_dims:
            raise ValueError(f"catalog tensor mismatch: {name}")
        return decode(record["type"], self._raw(record, expert, rows, columns), rows * columns)

    def vector(self, name: str, length: int) -> list[float]:
        return self._tensor(name, None, 1, length)

    def matrix(self, name: str, rows: int, columns: int) -> list[float]:
        return PrimaryTargetMatrixV6(self, name, None, rows, columns)

    def expert(self, name: str, expert: int, rows: int, columns: int) -> list[float]:
        return PrimaryTargetMatrixV6(self, name, expert, rows, columns)

    def close(self) -> None:
        for tensor, summary in sorted(self.reads.items()):
            self._event("TENSOR_REUSE_SUMMARY", tensor, "PASS_COMPLETE",
                        summary["bytes"], tensor, count=max(0, summary["count"] - 1))
        for shard,descriptor in self.handles.items():
            os.close(descriptor)
            self._event("SHARD_TEARDOWN",shard,"PASS_CLOSE")
        self.handles.clear()


class PrimaryTargetMatrixV6:
    def __init__(self, source: PrimaryTargetSourceV6, name: str, expert: int | None, rows: int, columns: int):
        self.source, self.name, self.expert, self.rows, self.columns = source, name, expert, rows, columns
        record = source.records.get(name)
        if record is None or record["dims"][:2] != [columns, rows]:
            raise ValueError(f"streaming matrix geometry: {name}")
    def row(self, index: int) -> list[float]:
        if not 0 <= index < self.rows: raise IndexError(index)
        record=self.source.records[self.name]
        return decode(record["type"],self.source._raw(record,self.expert,1,self.columns,index),self.columns)
    def __getitem__(self, item):
        if not isinstance(item,slice) or item.step not in (None,1) or item.start is None or item.stop is None:
            raise ValueError("streaming matrix permits one exact row slice")
        if item.stop-item.start!=self.columns or item.start%self.columns:
            raise ValueError("streaming matrix row slice")
        return self.row(item.start//self.columns)

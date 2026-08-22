#!/usr/bin/env python3
"""Independent fixed-order CPU producer for the F017 corrected oracle.

No Rust, FFI, MLX, production graph, production decoder, or checkpoint-reader
module is imported.  Target mode is impossible without a separately issued
scientific-access authorization; qualification mode consumes synthetic JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from f017_oracle_primary_decoders import LAYOUT, decode

ORACLE_ID = "F017_INDEPENDENT_CPU_REFERENCE_V1"
AUTH_SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0"
TOP_N = 32

def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=_pairs)


def _hash_f64(values: list[float]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<d", float(value)))
    return digest.hexdigest()


def _hash_json(value: object) -> str:
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


def _hash_path(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb",buffering=0) as source:
        while chunk:=source.read(1024*1024): digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Geometry:
    layers: int
    hidden: int
    vocab: int
    dense_layers: int
    experts: int
    top_k: int
    dense_ffn: int
    expert_ffn: int
    heads: int
    q_rank: int
    kv_rank: int
    qk_nope: int
    qk_rope: int
    value_dim: int
    rms_epsilon: float
    rope_base: float
    route_scale: float

    @classmethod
    def from_json(cls, value: dict) -> "Geometry":
        expected = set(cls.__annotations__)
        if not expected.issubset(value):
            raise ValueError("geometry key census")
        result = cls(**{key: value[key] for key in expected})
        if result.layers < 1 or result.hidden < 1 or result.vocab < 2 or result.qk_rope % 2:
            raise ValueError("invalid geometry")
        return result


class Source(Protocol):
    def vector(self, name: str, length: int) -> list[float]: ...
    def matrix(self, name: str, rows: int, columns: int) -> list[float]: ...
    def expert(self, name: str, expert: int, rows: int, columns: int) -> list[float]: ...


class JsonSource:
    """Qualification source; structurally has no checkpoint path or file API."""
    def __init__(self, tensors: dict):
        self.tensors = tensors

    def _get(self, key: str, count: int) -> list[float]:
        value = self.tensors.get(key)
        if not isinstance(value, list) or len(value) != count:
            raise ValueError(f"synthetic tensor geometry: {key}")
        output = [float(v) for v in value]
        if not all(math.isfinite(v) for v in output):
            raise ValueError(f"nonfinite synthetic tensor: {key}")
        return output

    def vector(self, name: str, length: int) -> list[float]:
        return self._get(name, length)

    def matrix(self, name: str, rows: int, columns: int) -> list[float]:
        return self._get(name, rows * columns)

    def expert(self, name: str, expert: int, rows: int, columns: int) -> list[float]:
        return self._get(f"{name}#{expert}", rows * columns)


class StreamingCatalogSource:
    """Memory-bounded target source, constructed only after live authority.

    Each tensor is read as one encoded row (or a bounded block chunk), decoded,
    returned, and released by the caller. Files are opened read-only with
    O_NOFOLLOW; this class is never instantiated by qualification commands.
    """
    def __init__(self, authorization: Path, catalog: Path, checkpoint_root: Path):
        auth = _strict_json(authorization)
        if auth.get("schema") != AUTH_SCHEMA or auth.get("state") != "AUTHORIZED" or not auth.get("live"):
            raise ValueError("live scientific-access authorization required")
        if auth.get("attempts") != 1 or auth.get("retries") != 0 or auth.get("resume"):
            raise ValueError("invalid scientific-access lifecycle")
        if "INDEPENDENT_CPU_REFERENCE" not in auth.get("consumers", []):
            raise ValueError("primary consumer not granted")
        if _hash_path(Path(__file__).resolve()) != auth.get("primary_sha256"):
            raise ValueError("primary producer identity mismatch")
        if _hash_path(catalog.resolve(strict=True)) != auth.get("checkpoint_catalog_sha256"):
            raise ValueError("catalog identity mismatch")
        root = checkpoint_root.resolve(strict=True)
        if str(root) != auth.get("checkpoint_root") or root.is_symlink():
            raise ValueError("checkpoint root authority mismatch")
        document = _strict_json(catalog)
        self.records = {item["name"]: item for item in document["tensors"]}
        self.shards = {item["filename"]: item for item in auth.get("shards", [])}
        self.root, self.auth = root, auth
        self.handles: dict[str, int] = {}
        self.reads: dict[str, dict[str, int]] = {}
        event_root=os.environ.get("F017_ORACLE_ACCESS_EVENT_DIR")
        if not event_root: raise ValueError("durable access-event directory required")
        self.event_root=Path(event_root);self.event_root.mkdir(mode=0o700,parents=False,exist_ok=False);self.sequence=0
        identity_path=os.environ.get("F017_ORACLE_CHECKPOINT_IDENTITY")
        if not identity_path: raise ValueError("checkpoint identity evidence required")
        self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_ATTEMPT",identity_path,"STARTED_READ_ONLY_NOFOLLOW")
        try:
            identity_file=Path(identity_path)
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
            if identity.get("authorization_id")!=auth["authorization_id"] or identity.get("result")!="PASS" or identity.get("shards")!=auth.get("shards"):
                raise ValueError("checkpoint identity evidence mismatch")
            self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT",identity_path,"PASS_BOUND",len(identity_bytes))
        except Exception as exc:
            self._event("CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT",identity_path,f"FAIL_{type(exc).__name__}")
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
        return StreamingMatrix(self, name, None, rows, columns)

    def expert(self, name: str, expert: int, rows: int, columns: int) -> list[float]:
        return StreamingMatrix(self, name, expert, rows, columns)

    def close(self) -> None:
        for tensor, summary in sorted(self.reads.items()):
            self._event("TENSOR_REUSE_SUMMARY", tensor, "PASS_COMPLETE",
                        summary["bytes"], tensor, count=max(0, summary["count"] - 1))
        for shard,descriptor in self.handles.items():
            os.close(descriptor)
            self._event("SHARD_TEARDOWN",shard,"PASS_CLOSE")
        self.handles.clear()


class StreamingMatrix:
    def __init__(self, source: StreamingCatalogSource, name: str, expert: int | None, rows: int, columns: int):
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
    def matvec(self, vector: list[float]) -> list[float]:
        if len(vector)!=self.columns: raise ValueError("streaming matvec geometry")
        return [sum(float(a)*float(b) for a,b in zip(self.row(row),vector,strict=True)) for row in range(self.rows)]


def _matvec(matrix: list[float], rows: int, columns: int, vector: list[float]) -> list[float]:
    if isinstance(matrix, StreamingMatrix):
        if matrix.rows != rows or matrix.columns != columns: raise ValueError("streaming matvec shape")
        return matrix.matvec(vector)
    if len(matrix) != rows * columns or len(vector) != columns:
        raise ValueError("matvec shape")
    output = []
    for row in range(rows):
        total = 0.0
        for column in range(columns):
            total += float(matrix[row * columns + column]) * float(vector[column])
        output.append(total)
    return output


def _transpose_matvec(matrix: list[float], rows: int, columns: int,
                      vector: list[float]) -> list[float]:
    """Fixed-order matrix-transpose/vector product.

    The GLM MLA K-B tensor is stored as ``[kv_rank, qk_nope]`` for the
    production contraction.  Constructing the explicit key requires the
    transpose product; keeping this operation visible prevents a one-key
    shortcut from silently deleting K semantics.
    """
    if len(vector) != rows:
        raise ValueError("transpose matvec shape")
    if isinstance(matrix, StreamingMatrix):
        if matrix.rows != rows or matrix.columns != columns:
            raise ValueError("streaming transpose matvec shape")
        output = [0.0] * columns
        for row in range(rows):
            value = float(vector[row])
            for column, weight in enumerate(matrix.row(row)):
                output[column] += float(weight) * value
        return output
    if len(matrix) != rows * columns:
        raise ValueError("transpose matvec shape")
    output = [0.0] * columns
    for row in range(rows):
        for column in range(columns):
            output[column] += float(matrix[row * columns + column]) * float(vector[row])
    return output


def _rms(x: list[float], weight: list[float], epsilon: float) -> list[float]:
    inv = 1.0 / math.sqrt(sum(value * value for value in x) / len(x) + float(epsilon))
    return [value * inv * scale for value, scale in zip(x, weight, strict=True)]


def _silu(value: float) -> float:
    return value / (1.0 + math.exp(-value))


def _residual(left: list[float], right: list[float]) -> list[float]:
    return [a + b for a, b in zip(left, right, strict=True)]


def _projection(source: Source, prefix: str, suffix: str, rows: int, columns: int,
                expert: int | None = None, shared: bool = False) -> list[float]:
    if expert is not None:
        return source.expert(f"{prefix}_{suffix}_exps.weight", expert, rows, columns)
    name = f"{prefix}_{suffix}_shexp.weight" if shared else f"{prefix}_{suffix}.weight"
    return source.matrix(name, rows, columns)


def _swiglu(source: Source, prefix: str, x: list[float], inner: int, hidden: int,
            expert: int | None = None, shared: bool = False, weight: float = 1.0) -> list[float]:
    gate = _matvec(_projection(source, prefix, "gate", inner, len(x), expert, shared), inner, len(x), x)
    up = _matvec(_projection(source, prefix, "up", inner, len(x), expert, shared), inner, len(x), x)
    product = [_silu(g) * u * weight for g, u in zip(gate, up, strict=True)]
    return _matvec(_projection(source, prefix, "down", hidden, inner, expert, shared), hidden, inner, product)


def _route(logits: list[float], bias: list[float], count: int, scale: float) -> tuple[list[int], list[float]]:
    probabilities = [1.0 / (1.0 + math.exp(-value)) for value in logits]
    order = sorted(range(len(logits)), key=lambda i: (-(probabilities[i] + bias[i]), i))[:count]
    denominator = max(sum(probabilities[i] for i in order), 2.0 ** -14)
    return order, [probabilities[i] / denominator * scale for i in order]


def execute(source: Source, geometry: Geometry, token: int, position: int = 0) -> dict:
    if not 0 <= token < geometry.vocab or position < 0:
        raise ValueError("token/position")
    embedding = source.matrix("token_embd.weight", geometry.vocab, geometry.hidden)
    hidden = embedding[token * geometry.hidden:(token + 1) * geometry.hidden]
    captures = []
    for layer in range(geometry.layers):
        layer_input = list(hidden)
        normalized = _rms(hidden, source.vector(f"blk.{layer}.attn_norm.weight", geometry.hidden), geometry.rms_epsilon)
        qa = _matvec(source.matrix(f"blk.{layer}.attn_q_a.weight", geometry.q_rank, geometry.hidden), geometry.q_rank, geometry.hidden, normalized)
        qan = _rms(qa, source.vector(f"blk.{layer}.attn_q_a_norm.weight", geometry.q_rank), geometry.rms_epsilon)
        qdim = geometry.qk_nope + geometry.qk_rope
        q = _matvec(source.matrix(f"blk.{layer}.attn_q_b.weight", geometry.heads * qdim, geometry.q_rank), geometry.heads * qdim, geometry.q_rank, qan)
        kv = _matvec(source.matrix(f"blk.{layer}.attn_kv_a_mqa.weight", geometry.kv_rank + geometry.qk_rope, geometry.hidden), geometry.kv_rank + geometry.qk_rope, geometry.hidden, normalized)
        kvn = _rms(kv[:geometry.kv_rank], source.vector(f"blk.{layer}.attn_kv_a_norm.weight", geometry.kv_rank), geometry.rms_epsilon)
        # The bounded event has one causal key, but it still instantiates the
        # complete Q/K/RoPE/score/softmax surface.  A one-element softmax is
        # exactly one; that fact is an outcome of the frozen context, not a
        # license to omit K or score construction.
        key_rope = list(kv[geometry.kv_rank:])
        for head in range(geometry.heads):
            for lane in range(0, geometry.qk_rope, 2):
                theta = position / geometry.rope_base ** (lane / geometry.qk_rope)
                c, s = math.cos(theta), math.sin(theta)
                base = head * qdim + geometry.qk_nope + lane
                q[base], q[base + 1] = q[base] * c - q[base + 1] * s, q[base] * s + q[base + 1] * c
        for lane in range(0, geometry.qk_rope, 2):
            theta = position / geometry.rope_base ** (lane / geometry.qk_rope)
            c, s = math.cos(theta), math.sin(theta)
            key_rope[lane], key_rope[lane + 1] = (
                key_rope[lane] * c - key_rope[lane + 1] * s,
                key_rope[lane] * s + key_rope[lane + 1] * c,
            )
        values = []
        attention_scores = []
        for head in range(geometry.heads):
            value = _matvec(source.expert(f"blk.{layer}.attn_v_b.weight", head, geometry.value_dim, geometry.kv_rank), geometry.value_dim, geometry.kv_rank, kvn)
            key_nope = _transpose_matvec(
                source.expert(f"blk.{layer}.attn_k_b.weight", head, geometry.kv_rank, geometry.qk_nope),
                geometry.kv_rank, geometry.qk_nope, kvn,
            )
            qbase = head * qdim
            q_nope = q[qbase:qbase + geometry.qk_nope]
            q_rope = q[qbase + geometry.qk_nope:qbase + qdim]
            score = (sum(a * b for a, b in zip(q_nope, key_nope, strict=True))
                     + sum(a * b for a, b in zip(q_rope, key_rope, strict=True))) / math.sqrt(qdim)
            if not math.isfinite(score):
                raise ValueError("attention score")
            attention_scores.append(struct.pack("<d", score).hex())
            softmax_weight = math.exp(score - score)
            softmax_weight /= softmax_weight
            values.extend(component * softmax_weight for component in value)
        attention = _matvec(source.matrix(f"blk.{layer}.attn_output.weight", geometry.hidden, geometry.heads * geometry.value_dim), geometry.hidden, geometry.heads * geometry.value_dim, values)
        hidden = _residual(hidden, attention)
        post_attention = list(hidden)
        router_input = _rms(hidden, source.vector(f"blk.{layer}.ffn_norm.weight", geometry.hidden), geometry.rms_epsilon)
        selected, weights, routed, shared = [], [], [], []
        if layer < geometry.dense_layers:
            ffn = _swiglu(source, f"blk.{layer}.ffn", router_input, geometry.dense_ffn, geometry.hidden)
        else:
            logits = _matvec(source.matrix(f"blk.{layer}.ffn_gate_inp.weight", geometry.experts, geometry.hidden), geometry.experts, geometry.hidden, router_input)
            selected, weights = _route(logits, source.vector(f"blk.{layer}.exp_probs_b.bias", geometry.experts), geometry.top_k, geometry.route_scale)
            routed = [0.0] * geometry.hidden
            for expert, route_weight in zip(selected, weights, strict=True):
                part = _swiglu(source, f"blk.{layer}.ffn", router_input, geometry.expert_ffn, geometry.hidden, expert=expert, weight=route_weight)
                routed = _residual(routed, part)
            shared = _swiglu(source, f"blk.{layer}.ffn", router_input, geometry.expert_ffn, geometry.hidden, shared=True)
            ffn = _residual(routed, shared)
        hidden = _residual(hidden, ffn)
        captures.append({
            "layer": layer, "layer_input_sha256": _hash_f64(layer_input),
            "post_attention_residual_sha256": _hash_f64(post_attention),
            "router_normalized_sha256": _hash_f64(router_input),
            "selected_expert_ids": selected,
            "attention_score_f64_bits": attention_scores,
            "routing_weight_f64_bits": [struct.pack("<d", w).hex() for w in weights],
            "routed_aggregate_sha256": _hash_f64(routed) if routed else None,
            "shared_output_sha256": _hash_f64(shared) if shared else None,
            "layer_output_sha256": _hash_f64(hidden),
        })
    final_norm = _rms(hidden, source.vector("output_norm.weight", geometry.hidden), geometry.rms_epsilon)
    logits = _matvec(source.matrix("output.weight", geometry.vocab, geometry.hidden), geometry.vocab, geometry.hidden, final_norm)
    order = sorted(range(len(logits)), key=lambda index: (-logits[index], index))
    selected = order[0]
    result = {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-primary-oracle-result/1.0.0",
        "oracle": ORACLE_ID, "position": position, "layer_count": geometry.layers,
        "layers": captures, "final_hidden_sha256": _hash_f64(hidden),
        "final_norm_sha256": _hash_f64(final_norm), "full_logits_sha256": _hash_f64(logits),
        "full_logits": logits, "top_n": TOP_N,
        "top": [{"token_id": i, "logit_f64_bits": struct.pack("<d", logits[i]).hex()} for i in order[:TOP_N]],
        "top_1_margin": logits[order[0]] - logits[order[1]], "selected_token": selected,
        "tie_rule": "LOWEST_TOKEN_ID_ON_EQUAL_BINARY64_LOGIT",
    }
    result["result_sha256"] = _hash_json(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    synthetic = sub.add_parser("synthetic")
    synthetic.add_argument("fixture", type=Path)
    synthetic.add_argument("output", type=Path)
    target = sub.add_parser("target")
    target.add_argument("authorization", type=Path)
    target.add_argument("catalog", type=Path)
    target.add_argument("checkpoint_root", type=Path)
    target.add_argument("geometry", type=Path)
    target.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "synthetic":
        fixture = _strict_json(arguments.fixture)
        result = execute(JsonSource(fixture["tensors"]), Geometry.from_json(fixture["geometry"]), fixture["token"], fixture.get("position", 0))
    else:
        authority = _strict_json(arguments.authorization)
        if _hash_path(arguments.geometry.resolve(strict=True)) != authority.get("geometry_sha256"):
            raise ValueError("geometry identity mismatch")
        source = StreamingCatalogSource(arguments.authorization, arguments.catalog, arguments.checkpoint_root)
        try:
            result = execute(source, Geometry.from_json(_strict_json(arguments.geometry)), authority["prompt_token"], authority["position"])
        finally:
            source.close()
    data=(json.dumps(result,indent=2,sort_keys=True)+"\n").encode()
    arguments.output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(arguments.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
    with os.fdopen(fd,"wb") as output: output.write(data);output.flush();os.fsync(output.fileno())
    dfd=os.open(arguments.output.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);os.fsync(dfd)
    rfd=os.open(arguments.output.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=dfd)
    with os.fdopen(rfd,"rb") as source: observed=source.read()
    os.close(dfd)
    if observed!=data: raise ValueError("oracle result exact readback")
    _strict_json(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Independent NumPy/MLX accelerated cross-check for the corrected oracle.

This module intentionally shares neither graph nor decoder implementation with
the primary CPU oracle.  NumPy is used for qualification; target mode requires
MLX and a live scientific-access authority and is therefore unreachable in the
pre-access phase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from pathlib import Path

import numpy as np

TOP_N = 32
ORACLE_ID = "F017_INDEPENDENT_ACCELERATED_CROSS_CHECK_V1"
AUTH_SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0"


def strict(path: Path) -> dict:
    def hook(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=hook)


def digest(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes(order="C")).hexdigest()


class Store:
    def __init__(self, tensors: dict):
        self.tensors = tensors
    def get(self, name: str, shape: tuple[int, ...]) -> np.ndarray:
        value = np.asarray(self.tensors[name], dtype=np.float32)
        if value.size != math.prod(shape) or not np.isfinite(value).all():
            raise ValueError(f"tensor {name}")
        return value.reshape(shape)
    def vector(self, name, n): return self.get(name, (n,))
    def matrix(self, name, rows, cols): return self.get(name, (rows, cols))
    def expert(self, name, expert, rows, cols): return self.get(f"{name}#{expert}", (rows, cols))


class CatalogStore:
    """Separate target reader/decoder dispatch for the accelerated consumer."""
    def __init__(self, authorization: Path, catalog: Path, checkpoint_root: Path):
        auth = strict(authorization)
        if auth.get("schema") != AUTH_SCHEMA or auth.get("state") != "AUTHORIZED" or not auth.get("live"):
            raise ValueError("live scientific-access authorization required")
        root = checkpoint_root.resolve(strict=True)
        if str(root) != auth.get("checkpoint_root") or root.is_symlink():
            raise ValueError("checkpoint root authority mismatch")
        self.root, self.auth = root, auth
        self.records = {item["name"]: item for item in strict(catalog)["tensors"]}
        self.handles = {};self.used=set();event_root=os.environ.get("F017_ORACLE_ACCESS_EVENT_DIR")
        if not event_root: raise ValueError("durable access-event directory required")
        self.event_root=Path(event_root);self.event_root.mkdir(mode=0o700,parents=False,exist_ok=False);self.sequence=0
    def _event(self,kind,authority,result,size=0,tensor=None):
        value={"schema":"pulsarmlx.f017.corrected-oracle-access-event/1.0.0","sequence":self.sequence,
               "authorization_id":self.auth["authorization_id"],"consumer":"INDEPENDENT_ACCELERATED_CROSS_CHECK",
               "process_id":os.getpid(),"kind":kind,"authority_id":authority,"result":result,"size_bytes":size,"tensor_name":tensor}
        data=(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n").encode();path=self.event_root/f"{self.sequence:08}.json"
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,"wb") as out: out.write(data);out.flush();os.fsync(out.fileno())
        dfd=os.open(self.event_root,os.O_RDONLY);os.fsync(dfd);os.close(dfd)
        if path.read_bytes()!=data: raise ValueError("access event readback")
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
            self.handles[shard]=os.open(self.root/shard,os.O_RDONLY|os.O_NOFOLLOW);self._event("SHARD_OPEN",shard,"PASS_READ_ONLY_NOFOLLOW",os.fstat(self.handles[shard]).st_size)
        self._event("TENSOR_RESOLUTION",name,"PASS_CATALOG_BOUND",size,name)
        raw=os.pread(self.handles[shard],size,offset)
        if len(raw)!=size: raise ValueError("short tensor read")
        kind="TENSOR_FIRST_USE" if name not in self.used else "TENSOR_REUSE";self.used.add(name);self._event(kind,name,"PASS_EXACT_PREAD",len(raw),name)
        values=independent_decode(fmt,raw,rows*cols)
        return np.asarray(values,dtype=np.float32).reshape(rows,cols)
    def vector(self,name,n): return self._get(name,None,1,n).reshape(n)
    def matrix(self,name,rows,cols): return CatalogMatrix(self,name,None,rows,cols)
    def expert(self,name,expert,rows,cols): return CatalogMatrix(self,name,expert,rows,cols)
    def close(self):
        for shard,descriptor in self.handles.items(): os.close(descriptor);self._event("SHARD_TEARDOWN",shard,"PASS_CLOSE")
        self.handles.clear()


class CatalogMatrix:
    def __init__(self,source,name,expert,rows,cols): self.source,self.name,self.expert,self.rows,self.cols=source,name,expert,rows,cols
    def row(self,index): return self.source._get(self.name,self.expert,1,self.cols,index).reshape(self.cols)
    def __getitem__(self,item):
        if isinstance(item,int): return self.row(item)
        raise ValueError("catalog matrix supports row indexing only")
    def matvec(self,vector,use_mlx):
        if use_mlx:
            import mlx.core as mx
            output=[]
            for start in range(0,self.rows,16):
                rows=np.stack([self.row(i) for i in range(start,min(self.rows,start+16))])
                value=mx.array(rows)@mx.array(vector);mx.eval(value);output.extend(np.asarray(value,dtype=np.float32))
            return np.asarray(output,dtype=np.float32)
        return np.asarray([np.dot(self.row(i).astype(np.float64),vector.astype(np.float64)) for i in range(self.rows)],dtype=np.float32)


def rms(x, weight, epsilon):
    return (x.astype(np.float64) / np.sqrt(np.mean(x.astype(np.float64) ** 2) + epsilon) * weight.astype(np.float64)).astype(np.float32)


def mv(matrix, vector, use_mlx=False):
    if isinstance(matrix,CatalogMatrix): return matrix.matvec(vector,use_mlx)
    if use_mlx:
        import mlx.core as mx
        result = mx.array(matrix) @ mx.array(vector)
        mx.eval(result)
        return np.asarray(result, dtype=np.float32)
    return (matrix.astype(np.float64) @ vector.astype(np.float64)).astype(np.float32)


def swiglu(store, prefix, x, inner, hidden, use_mlx, expert=None, shared=False, weight=1.0):
    def projection(suffix, rows, cols):
        if expert is not None:
            return store.expert(f"{prefix}_{suffix}_exps.weight", expert, rows, cols)
        name = f"{prefix}_{suffix}_shexp.weight" if shared else f"{prefix}_{suffix}.weight"
        return store.matrix(name, rows, cols)
    gate = mv(projection("gate", inner, len(x)), x, use_mlx)
    up = mv(projection("up", inner, len(x)), x, use_mlx)
    product = (gate / (1.0 + np.exp(-gate, dtype=np.float32)) * up * np.float32(weight)).astype(np.float32)
    return mv(projection("down", hidden, inner), product, use_mlx)


def execute(document: dict, use_mlx=False, store=None) -> dict:
    g = document["geometry"]
    store = store or Store(document["tensors"])
    token, position = int(document["token"]), int(document.get("position", 0))
    h, vocab = g["hidden"], g["vocab"]
    hidden = store.matrix("token_embd.weight", vocab, h)[token].copy()
    layers = []
    for layer in range(g["layers"]):
        layer_input = hidden.copy()
        xn = rms(hidden, store.vector(f"blk.{layer}.attn_norm.weight", h), g["rms_epsilon"])
        qa = mv(store.matrix(f"blk.{layer}.attn_q_a.weight", g["q_rank"], h), xn, use_mlx)
        qan = rms(qa, store.vector(f"blk.{layer}.attn_q_a_norm.weight", g["q_rank"]), g["rms_epsilon"])
        qdim = g["qk_nope"] + g["qk_rope"]
        q = mv(store.matrix(f"blk.{layer}.attn_q_b.weight", g["heads"] * qdim, g["q_rank"]), qan, use_mlx)
        kv = mv(store.matrix(f"blk.{layer}.attn_kv_a_mqa.weight", g["kv_rank"] + g["qk_rope"], h), xn, use_mlx)
        kvn = rms(kv[:g["kv_rank"]], store.vector(f"blk.{layer}.attn_kv_a_norm.weight", g["kv_rank"]), g["rms_epsilon"])
        for head in range(g["heads"]):
            for lane in range(0, g["qk_rope"], 2):
                theta = position / g["rope_base"] ** (lane / g["qk_rope"])
                c, s = np.float32(math.cos(theta)), np.float32(math.sin(theta))
                base = head * qdim + g["qk_nope"] + lane
                a, b = q[base], q[base + 1]
                q[base], q[base + 1] = a * c - b * s, a * s + b * c
        values = []
        for head in range(g["heads"]):
            values.extend(mv(store.expert(f"blk.{layer}.attn_v_b.weight", head, g["value_dim"], g["kv_rank"]), kvn, use_mlx))
            key = mv(store.expert(f"blk.{layer}.attn_k_b.weight", head, g["kv_rank"], g["qk_nope"]), q[head * qdim:head * qdim + g["qk_nope"]], use_mlx)
            if not np.isfinite(np.dot(key, kvn)):
                raise ValueError("attention score")
        attention = mv(store.matrix(f"blk.{layer}.attn_output.weight", h, g["heads"] * g["value_dim"]), np.asarray(values, dtype=np.float32), use_mlx)
        hidden = (hidden + attention).astype(np.float32)
        post_attention = hidden.copy()
        fx = rms(hidden, store.vector(f"blk.{layer}.ffn_norm.weight", h), g["rms_epsilon"])
        selected, weights = [], []
        routed, shared = np.asarray([], dtype=np.float32), np.asarray([], dtype=np.float32)
        if layer < g["dense_layers"]:
            ffn = swiglu(store, f"blk.{layer}.ffn", fx, g["dense_ffn"], h, use_mlx)
        else:
            logits = mv(store.matrix(f"blk.{layer}.ffn_gate_inp.weight", g["experts"], h), fx, use_mlx)
            probabilities = (1.0 / (1.0 + np.exp(-logits, dtype=np.float32))).astype(np.float32)
            bias = store.vector(f"blk.{layer}.exp_probs_b.bias", g["experts"])
            selected = sorted(range(g["experts"]), key=lambda i: (-float(probabilities[i] + bias[i]), i))[:g["top_k"]]
            denominator = max(sum(float(probabilities[i]) for i in selected), 2.0 ** -14)
            weights = [float(probabilities[i]) / denominator * g["route_scale"] for i in selected]
            routed = np.zeros(h, dtype=np.float32)
            for expert, weight in zip(selected, weights, strict=True):
                routed = (routed + swiglu(store, f"blk.{layer}.ffn", fx, g["expert_ffn"], h, use_mlx, expert=expert, weight=weight)).astype(np.float32)
            shared = swiglu(store, f"blk.{layer}.ffn", fx, g["expert_ffn"], h, use_mlx, shared=True)
            ffn = (routed + shared).astype(np.float32)
        hidden = (hidden + ffn).astype(np.float32)
        layers.append({"layer": layer, "layer_input_sha256": digest(layer_input),
                       "post_attention_residual_sha256": digest(post_attention),
                       "router_normalized_sha256": digest(fx), "selected_expert_ids": selected,
                       "routing_weight_f32_bits": [struct.pack("<f", w).hex() for w in weights],
                       "routed_aggregate_sha256": digest(routed) if routed.size else None,
                       "shared_output_sha256": digest(shared) if shared.size else None,
                       "layer_output_sha256": digest(hidden)})
    normalized = rms(hidden, store.vector("output_norm.weight", h), g["rms_epsilon"])
    logits = mv(store.matrix("output.weight", vocab, h), normalized, use_mlx)
    order = sorted(range(vocab), key=lambda i: (-float(logits[i]), i))
    return {"schema":"pulsarmlx.f017.corrected-full-checkpoint-secondary-oracle-result/1.0.0",
            "oracle":ORACLE_ID, "layer_count":g["layers"], "position":position, "layers":layers,
            "final_hidden_sha256":digest(hidden), "final_norm_sha256":digest(normalized),
            "full_logits_sha256":digest(logits), "full_logits":[float(v) for v in logits],
            "top_n":TOP_N, "top":[{"token_id":i,"logit_f32_bits":struct.pack("<f",logits[i]).hex()} for i in order[:TOP_N]],
            "top_1_margin":float(logits[order[0]]-logits[order[1]]), "selected_token":order[0],
            "tie_rule":"LOWEST_TOKEN_ID_ON_EQUAL_BINARY32_LOGIT"}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command")
    synthetic=sub.add_parser("synthetic");synthetic.add_argument("fixture",type=Path);synthetic.add_argument("output",type=Path);synthetic.add_argument("--backend",choices=("numpy","mlx"),default="numpy")
    target=sub.add_parser("target");target.add_argument("authorization",type=Path);target.add_argument("catalog",type=Path);target.add_argument("checkpoint_root",type=Path);target.add_argument("geometry",type=Path);target.add_argument("output",type=Path)
    # Backward-compatible qualification positional form is intentionally gone;
    # an explicit command keeps target and synthetic authority visibly distinct.
    args = parser.parse_args()
    if args.command=="synthetic": result=execute(strict(args.fixture),args.backend=="mlx")
    elif args.command=="target":
        auth=strict(args.authorization);store=CatalogStore(args.authorization,args.catalog,args.checkpoint_root)
        try: result=execute({"geometry":strict(args.geometry),"token":auth["prompt_token"],"position":auth["position"]},True,store)
        finally: store.close()
    else: parser.error("command required")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

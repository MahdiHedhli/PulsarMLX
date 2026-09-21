#!/usr/bin/env python3
"""Pure binary32 numerical core for the corrected oracle cross-check.

This module intentionally shares neither graph nor decoder implementation with
the primary CPU oracle.  It contains only in-memory tensor adapters, independent
binary32 graph arithmetic, and numerical result construction.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol, runtime_checkable

import numpy as np

TOP_N = 32
ORACLE_ID = "F017_INDEPENDENT_ACCELERATED_CROSS_CHECK_V1"

def _pairs(items):
    out={}
    for key,value in items:
        if key in out: raise ValueError("duplicate JSON key")
        out[key]=value
    return out

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




@runtime_checkable
class RowMatrix(Protocol):
    rows: int
    cols: int

    def row(self, index: int) -> np.ndarray: ...




def rms(x, weight, epsilon):
    return (x.astype(np.float64) / np.sqrt(np.mean(x.astype(np.float64) ** 2) + epsilon) * weight.astype(np.float64)).astype(np.float32)


def mv(matrix, vector, use_mlx=False):
    if isinstance(matrix,RowMatrix):
        if use_mlx:
            import mlx.core as mx
            output=[]
            for start in range(0,matrix.rows,16):
                rows=np.stack([matrix.row(i) for i in range(start,min(matrix.rows,start+16))])
                value=mx.array(rows)@mx.array(vector);mx.eval(value);output.extend(np.asarray(value,dtype=np.float32))
            return np.asarray(output,dtype=np.float32)
        return np.asarray([np.dot(matrix.row(i).astype(np.float64),vector.astype(np.float64)) for i in range(matrix.rows)],dtype=np.float32)
    if use_mlx:
        import mlx.core as mx
        result = mx.array(matrix) @ mx.array(vector)
        mx.eval(result)
        return np.asarray(result, dtype=np.float32)
    return (matrix.astype(np.float64) @ vector.astype(np.float64)).astype(np.float32)


def transpose_mv(matrix, vector, use_mlx=False):
    if isinstance(matrix, RowMatrix):
        if len(vector) != matrix.rows:
            raise ValueError("transpose matvec geometry")
        result = np.zeros(matrix.cols, dtype=np.float64)
        for row in range(matrix.rows):
            result += matrix.row(row).astype(np.float64) * float(vector[row])
        return result.astype(np.float32)
    if use_mlx:
        import mlx.core as mx
        value = mx.transpose(mx.array(matrix)) @ mx.array(vector)
        mx.eval(value)
        return np.asarray(value, dtype=np.float32)
    return (matrix.astype(np.float64).T @ vector.astype(np.float64)).astype(np.float32)


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
        key_rope = kv[g["kv_rank"]:].copy()
        for head in range(g["heads"]):
            for lane in range(0, g["qk_rope"], 2):
                theta = position / g["rope_base"] ** (lane / g["qk_rope"])
                c, s = np.float32(math.cos(theta)), np.float32(math.sin(theta))
                base = head * qdim + g["qk_nope"] + lane
                a, b = q[base], q[base + 1]
                q[base], q[base + 1] = a * c - b * s, a * s + b * c
        for lane in range(0, g["qk_rope"], 2):
            theta = position / g["rope_base"] ** (lane / g["qk_rope"])
            c, s = np.float32(math.cos(theta)), np.float32(math.sin(theta))
            a, b = key_rope[lane], key_rope[lane + 1]
            key_rope[lane], key_rope[lane + 1] = a * c - b * s, a * s + b * c
        values = []
        attention_scores = []
        for head in range(g["heads"]):
            value = mv(store.expert(f"blk.{layer}.attn_v_b.weight", head, g["value_dim"], g["kv_rank"]), kvn, use_mlx)
            key_nope = transpose_mv(store.expert(f"blk.{layer}.attn_k_b.weight", head, g["kv_rank"], g["qk_nope"]), kvn, use_mlx)
            base = head * qdim
            score = (np.dot(q[base:base + g["qk_nope"]].astype(np.float64), key_nope.astype(np.float64))
                     + np.dot(q[base + g["qk_nope"]:base + qdim].astype(np.float64), key_rope.astype(np.float64))) / math.sqrt(qdim)
            if not np.isfinite(score):
                raise ValueError("attention score")
            attention_scores.append(struct.pack("<f", np.float32(score)).hex())
            softmax_weight = np.float32(math.exp(float(score) - float(score)))
            softmax_weight = np.float32(softmax_weight / softmax_weight)
            values.extend((value * softmax_weight).astype(np.float32))
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
                       "attention_score_f32_bits": attention_scores,
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

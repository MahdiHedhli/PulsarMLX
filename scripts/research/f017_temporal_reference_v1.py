#!/usr/bin/env python3
"""Independent multi-position reference for the native stateful decoder.

This is a second implementation, not a wrapper: it builds its own key/value
history, its own rotary embedding and its own causal softmax in binary64 and
never calls the Rust runtime. The only things it shares with the producer are
the fixture bytes and the declared semantics:

* absorbed MLA -- `attn_k_b[h]` maps this head's `q_nope` into the latent
  space, `attn_v_b[h]` maps the attention-weighted latent back out;
* the score of key `j` for query position `i` is
  `(W_kb q_nope) . c_j + rope(q_rope, i) . rope(k_rope_j, j)`, scaled by
  `attention_softmax_scale`;
* every key `j <= i` is visible and the current key is included;
* sigmoid routing with an additive bias, top-k by score with a low-id tie
  break, weights renormalised over the selected probabilities and scaled.

It deliberately keeps the whole prefix and recomputes the attention over it
from the stored keys at every position, so a producer bug that drops, reuses
or misorders history cannot be reproduced here by construction.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def rms_norm(x, scale, epsilon):
    total = sum(value * value for value in x)
    inverse = 1.0 / math.sqrt(total / len(x) + epsilon)
    return [value * inverse * weight for value, weight in zip(x, scale)]


def matvec(matrix, vector):
    rows, columns, values = matrix["rows"], matrix["columns"], matrix["values"]
    if len(vector) != columns:
        raise ValueError("matvec shape")
    return [sum(values[row * columns + column] * vector[column] for column in range(columns))
            for row in range(rows)]


def silu(value):
    return value / (1.0 + math.exp(-value))


def rope(values, position, base, pairing):
    n = len(values)
    half = n // 2
    out = list(values)
    for index in range(half):
        theta = position * base ** (-2.0 * index / n)
        sin, cos = math.sin(theta), math.cos(theta)
        low, high = (index, index + half) if pairing == "neox_half_split" else (2 * index, 2 * index + 1)
        a, b = values[low], values[high]
        out[low] = a * cos - b * sin
        out[high] = a * sin + b * cos
    return out


def softmax(scores):
    peak = max(scores)
    exponentials = [math.exp(score - peak) for score in scores]
    total = sum(exponentials)
    return [value / total for value in exponentials]


class Fixture:
    def __init__(self, document: dict):
        self.config = document["config"]
        self.model = self.config["model"]
        self.tokens = document["tokens"]
        self.seed = document["seed"]
        self.vectors = document["vectors"]
        self.matrices = document["matrices"]
        self.experts = {(item["name"], item["expert"]): item["matrix"] for item in document["expert_matrices"]}

    def vector(self, name, length):
        value = self.vectors[name]
        if len(value) != length:
            raise ValueError(f"shape {name}")
        return value

    def matrix(self, name, rows, columns):
        value = self.matrices[name]
        if value["rows"] != rows or value["columns"] != columns:
            raise ValueError(f"shape {name}")
        return value

    def expert(self, name, expert, rows, columns):
        value = self.experts[(name, expert)]
        if value["rows"] != rows or value["columns"] != columns:
            raise ValueError(f"shape {name}")
        return value


def swiglu(fixture, prefix, expert, shared, x, inner, hidden, weight):
    def projection(suffix, rows, columns):
        if expert is not None:
            return fixture.expert(f"{prefix}_{suffix}_exps.weight", expert, rows, columns)
        if shared:
            return fixture.matrix(f"{prefix}_{suffix}_shexp.weight", rows, columns)
        return fixture.matrix(f"{prefix}_{suffix}.weight", rows, columns)

    gate = matvec(projection("gate", inner, len(x)), x)
    up = matvec(projection("up", inner, len(x)), x)
    product = [silu(g) * u * weight for g, u in zip(gate, up)]
    return matvec(projection("down", hidden, inner), product)


def route(logits, bias, k, scale):
    probabilities = [1.0 / (1.0 + math.exp(-value)) for value in logits]
    scores = [p + b for p, b in zip(probabilities, bias)]
    order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))[:k]
    denominator = max(sum(probabilities[index] for index in order), 6.103515625e-5)
    return order, [probabilities[index] / denominator * scale for index in order]


def feed_forward(fixture, model, layer, fx):
    if layer < model["leading_dense_layers"]:
        return swiglu(fixture, f"blk.{layer}.ffn", None, False, fx, model["dense_ffn"], model["hidden"], 1.0), []
    logits = matvec(fixture.matrix(f"blk.{layer}.ffn_gate_inp.weight", model["expert_count"], model["hidden"]), fx)
    bias = fixture.vector(f"blk.{layer}.exp_probs_b.bias", model["expert_count"])
    ids, weights = route(logits, bias, model["expert_top_k"], model["expert_weight_scale"])
    accumulator = [0.0] * model["hidden"]
    for identifier, weight in zip(ids, weights):
        part = swiglu(fixture, f"blk.{layer}.ffn", identifier, False, fx, model["expert_ffn"], model["hidden"], weight)
        accumulator = [a + p for a, p in zip(accumulator, part)]
    shared = swiglu(fixture, f"blk.{layer}.ffn", None, True, fx, model["expert_ffn"], model["hidden"], 1.0)
    return [a + s for a, s in zip(accumulator, shared)], ids


def execute(fixture: Fixture) -> list[dict]:
    model = fixture.model
    scale = fixture.config["attention_softmax_scale"]
    pairing = fixture.config["rope_pairing"]
    qdim = model["qk_nope"] + model["qk_rope"]
    # This reference keeps the entire history explicitly and never mutates a
    # previous entry: history[layer] is a list of (latent, rotated rope key).
    history: list[list[tuple[list[float], list[float]]]] = [[] for _ in range(model["layer_count"])]
    embedding = fixture.matrix("token_embd.weight", model["vocab"], model["hidden"])
    steps = []
    for position, token in enumerate(fixture.tokens):
        if token >= model["vocab"]:
            raise ValueError("token out of range")
        x = embedding["values"][token * model["hidden"]:(token + 1) * model["hidden"]]
        first_head_weights: list[float] = []
        selected_expert_ids = []
        for layer in range(model["layer_count"]):
            xn = rms_norm(x, fixture.vector(f"blk.{layer}.attn_norm.weight", model["hidden"]), model["rms_epsilon"])
            qa = matvec(fixture.matrix(f"blk.{layer}.attn_q_a.weight", model["q_rank"], model["hidden"]), xn)
            qan = rms_norm(qa, fixture.vector(f"blk.{layer}.attn_q_a_norm.weight", model["q_rank"]), model["rms_epsilon"])
            q = matvec(fixture.matrix(f"blk.{layer}.attn_q_b.weight", model["heads"] * qdim, model["q_rank"]), qan)
            kv = matvec(fixture.matrix(f"blk.{layer}.attn_kv_a_mqa.weight", model["kv_rank"] + model["qk_rope"], model["hidden"]), xn)
            latent = rms_norm(kv[:model["kv_rank"]], fixture.vector(f"blk.{layer}.attn_kv_a_norm.weight", model["kv_rank"]), model["rms_epsilon"])
            rope_key = rope(kv[model["kv_rank"]:], position, model["rope_base"], pairing)
            history[layer].append((latent, rope_key))
            if len(history[layer]) != position + 1:
                raise ValueError("history append order")
            values = []
            for head in range(model["heads"]):
                k_b = fixture.expert(f"blk.{layer}.attn_k_b.weight", head, model["kv_rank"], model["qk_nope"])
                q_nope = q[head * qdim:head * qdim + model["qk_nope"]]
                latent_query = matvec(k_b, q_nope)
                rotated_query = rope(q[head * qdim + model["qk_nope"]:(head + 1) * qdim], position, model["rope_base"], pairing)
                scores = []
                for key_latent, key_rope in history[layer]:
                    score = sum(a * b for a, b in zip(latent_query, key_latent))
                    score += sum(a * b for a, b in zip(rotated_query, key_rope))
                    scores.append(score * scale)
                weights = softmax(scores)
                if head == 0 and layer == 0:
                    first_head_weights = weights
                aggregate = [0.0] * model["kv_rank"]
                for weight, (key_latent, _) in zip(weights, history[layer]):
                    aggregate = [a + weight * value for a, value in zip(aggregate, key_latent)]
                v_b = fixture.expert(f"blk.{layer}.attn_v_b.weight", head, model["value_dim"], model["kv_rank"])
                values.extend(matvec(v_b, aggregate))
            attention = matvec(fixture.matrix(f"blk.{layer}.attn_output.weight", model["hidden"], model["heads"] * model["value_dim"]), values)
            x = [a + b for a, b in zip(x, attention)]
            fx = rms_norm(x, fixture.vector(f"blk.{layer}.ffn_norm.weight", model["hidden"]), model["rms_epsilon"])
            ffn, ids = feed_forward(fixture, model, layer, fx)
            # Dense layers contribute an empty selection, so the per-layer
            # list stays aligned with the layer index in both implementations.
            selected_expert_ids.append(ids)
            x = [a + b for a, b in zip(x, ffn)]
        normalized = rms_norm(x, fixture.vector("output_norm.weight", model["hidden"]), model["rms_epsilon"])
        logits = matvec(fixture.matrix("output.weight", model["vocab"], model["hidden"]), normalized)
        selected = max(range(len(logits)), key=lambda index: (logits[index], -index))
        steps.append({
            "position": position,
            "token": token,
            "selected_token": selected,
            "visible_keys": position + 1,
            "first_head_attention_weights": first_head_weights,
            "selected_expert_ids": selected_expert_ids,
            "logits": logits,
        })
    return steps


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    document = json.loads(arguments.fixture.read_text())
    fixture = Fixture(document)
    result = {
        "schema": "pulsarmlx.f017.native-temporal-reference-result/1.0.0",
        "seed": fixture.seed,
        "implementation": "independent binary64 python reference",
        "original_checkpoint_reads": 0,
        "tokens": fixture.tokens,
        "steps": execute(fixture),
    }
    raw = json.dumps(result)
    if arguments.output:
        arguments.output.write_text(raw + "\n")
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

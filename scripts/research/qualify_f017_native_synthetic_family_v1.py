#!/usr/bin/env python3
"""Expanded checkpoint-free full-graph differential fixture family.

The oracle is implemented locally with scalar binary32 operations and imports
no Rust, MLX, FFI, checkpoint, or Pulsar model helper.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import struct
import subprocess
import tempfile
from pathlib import Path


SEEDS = [17018, 17019, 17020, 17021, 17022, 17023]
U = 2.0**-24


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def add(a: float, b: float) -> float:
    return f32(f32(a) + f32(b))


def mul(a: float, b: float) -> float:
    return f32(f32(a) * f32(b))


def matrix(rows: int, columns: int, rng: random.Random, scale: float = 0.18) -> dict:
    return {
        "rows": rows,
        "columns": columns,
        "values": [f32(rng.uniform(-scale, scale)) for _ in range(rows * columns)],
    }


def mv(m: dict, x: list[float]) -> list[float]:
    result = []
    for row in range(m["rows"]):
        total = 0.0
        for column in range(m["columns"]):
            total = add(total, mul(m["values"][row * m["columns"] + column], x[column]))
        result.append(total)
    return result


def rms(x: list[float], scale: list[float], epsilon: float) -> list[float]:
    total = 0.0
    for value in x:
        total = add(total, mul(value, value))
    mean = add(f32(total / len(x)), epsilon)
    inverse = f32(1.0 / math.sqrt(mean))
    return [mul(mul(value, inverse), weight) for value, weight in zip(x, scale, strict=True)]


def silu(value: float) -> float:
    return f32(value / f32(1.0 + f32(math.exp(-value))))


def swiglu(matrices: dict, prefix: str, x: list[float], weight: float = 1.0) -> list[float]:
    gate = mv(matrices[prefix + "gate.weight"], x)
    up = mv(matrices[prefix + "up.weight"], x)
    product = [mul(mul(silu(a), b), weight) for a, b in zip(gate, up, strict=True)]
    return mv(matrices[prefix + "down.weight"], product)


def route(logits: list[float], bias: list[float], k: int, scale: float) -> tuple[list[int], list[float]]:
    probabilities = [f32(1.0 / f32(1.0 + f32(math.exp(-value)))) for value in logits]
    scores = [add(probability, correction) for probability, correction in zip(probabilities, bias, strict=True)]
    selected = sorted(range(len(scores)), key=lambda expert: (-scores[expert], expert))[:k]
    denominator = 0.0
    for expert in selected:
        denominator = add(denominator, probabilities[expert])
    denominator = max(denominator, f32(6.103515625e-5))
    return selected, [mul(f32(probabilities[expert] / denominator), scale) for expert in selected]


def oracle(fixture: dict) -> dict:
    config = fixture["config"]
    vectors = fixture["vectors"]
    matrices = fixture["matrices"]
    experts = {(row["name"], row["expert"]): row["matrix"] for row in fixture["expert_matrices"]}
    hidden = config["hidden"]
    token = fixture["prompt_token"]
    embedding = matrices["token_embd.weight"]["values"]
    x = embedding[token * hidden : (token + 1) * hidden]
    captures = []
    for layer in range(config["layer_count"]):
        layer_input = list(x)
        prefix = f"blk.{layer}"
        xn = rms(x, vectors[prefix + ".attn_norm.weight"], config["rms_epsilon"])
        qa = mv(matrices[prefix + ".attn_q_a.weight"], xn)
        qan = rms(qa, vectors[prefix + ".attn_q_a_norm.weight"], config["rms_epsilon"])
        q = mv(matrices[prefix + ".attn_q_b.weight"], qan)
        kv = mv(matrices[prefix + ".attn_kv_a_mqa.weight"], xn)
        kvn = rms(kv[: config["kv_rank"]], vectors[prefix + ".attn_kv_a_norm.weight"], config["rms_epsilon"])
        values = mv(experts[(prefix + ".attn_v_b.weight", 0)], kvn)
        key = mv(experts[(prefix + ".attn_k_b.weight", 0)], q[: config["qk_nope"]])
        score = 0.0
        for a, b in zip(key, kvn, strict=True):
            score = add(score, mul(a, b))
        assert math.isfinite(score)
        attention = mv(matrices[prefix + ".attn_output.weight"], values)
        x = [add(a, b) for a, b in zip(x, attention, strict=True)]
        post_attention = list(x)
        normalized = rms(x, vectors[prefix + ".ffn_norm.weight"], config["rms_epsilon"])
        selected: list[int] = []
        weights: list[float] = []
        routed: list[float] = []
        shared: list[float] = []
        if layer < config["leading_dense_layers"]:
            ffn = swiglu(matrices, prefix + ".ffn_", normalized)
        else:
            logits = mv(matrices[prefix + ".ffn_gate_inp.weight"], normalized)
            selected, weights = route(
                logits,
                vectors[prefix + ".exp_probs_b.bias"],
                config["expert_top_k"],
                config["expert_weight_scale"],
            )
            accumulator = [0.0] * hidden
            for expert, weight in zip(selected, weights, strict=True):
                local = {
                    prefix + f".ffn_{name}.weight": experts[(prefix + f".ffn_{name}_exps.weight", expert)]
                    for name in ("gate", "up", "down")
                }
                part = swiglu(local, prefix + ".ffn_", normalized, weight)
                accumulator = [add(a, b) for a, b in zip(accumulator, part, strict=True)]
            routed = list(accumulator)
            shared_matrices = {
                prefix + f".ffn_{name}.weight": matrices[prefix + f".ffn_{name}_shexp.weight"]
                for name in ("gate", "up", "down")
            }
            shared = swiglu(shared_matrices, prefix + ".ffn_", normalized)
            ffn = [add(a, b) for a, b in zip(accumulator, shared, strict=True)]
        x = [add(a, b) for a, b in zip(x, ffn, strict=True)]
        captures.append(
            {
                "layer": layer,
                "layer_input": layer_input,
                "post_attention_residual": post_attention,
                "router_normalized_input": normalized,
                "selected_expert_ids": selected,
                "routing_weights": weights,
                "routed_aggregate": routed,
                "shared_expert": shared,
                "layer_output": list(x),
            }
        )
    final_hidden = list(x)
    final_norm = rms(x, vectors["output_norm.weight"], config["rms_epsilon"])
    logits = mv(matrices["output.weight"], final_norm)
    selected_token = max(range(len(logits)), key=lambda index: (logits[index], -index))
    return {"layers": captures, "final_hidden": final_hidden, "final_norm": final_norm, "logits": logits, "selected_token": selected_token}


def build(seed: int) -> tuple[dict, dict, dict]:
    rng = random.Random(seed)
    case = seed - SEEDS[0]
    layers = [1, 2, 3, 4, 3, 4][case]
    leading = [1, 1, 1, 2, 1, 2][case]
    expert_count = [2, 3, 4, 4, 4, 4][case]
    top_k = [1, 2, 2, 3, 2, 2][case]
    hidden = 4
    vocab = 16
    prompt = 3
    config = {
        "layer_count": layers,
        "hidden": hidden,
        "vocab": vocab,
        "leading_dense_layers": leading,
        "expert_count": expert_count,
        "expert_top_k": top_k,
        "dense_ffn": 4,
        "expert_ffn": 4,
        "heads": 1,
        "q_rank": 4,
        "kv_rank": 4,
        "qk_nope": 2,
        "qk_rope": 2,
        "value_dim": 4,
        "rms_epsilon": f32(1.0e-5),
        "rope_base": f32(8_000_000.0),
        "expert_weight_scale": f32(2.5),
    }
    embedding = matrix(vocab, hidden, rng, 0.4)
    vectors = {"output_norm.weight": [f32(0.8 + 0.1 * index) for index in range(hidden)]}
    matrices = {"token_embd.weight": embedding, "output.weight": matrix(vocab, hidden, rng, 0.0)}
    experts = []
    route_modes = []
    for layer in range(layers):
        prefix = f"blk.{layer}"
        for name, shape in {
            "attn_q_a.weight": (4, 4),
            "attn_q_b.weight": (4, 4),
            "attn_kv_a_mqa.weight": (6, 4),
            "attn_output.weight": (4, 4),
        }.items():
            matrices[prefix + "." + name] = matrix(*shape, rng)
        experts.extend(
            [
                {"name": prefix + ".attn_k_b.weight", "expert": 0, "matrix": matrix(4, 2, rng)},
                {"name": prefix + ".attn_v_b.weight", "expert": 0, "matrix": matrix(4, 4, rng)},
            ]
        )
        for suffix, length in (("attn_norm.weight", 4), ("attn_q_a_norm.weight", 4), ("attn_kv_a_norm.weight", 4), ("ffn_norm.weight", 4)):
            vectors[prefix + "." + suffix] = [f32(rng.uniform(0.7, 1.3)) for _ in range(length)]
        if layer < leading:
            for name in ("gate", "up", "down"):
                matrices[prefix + f".ffn_{name}.weight"] = matrix(4, 4, rng)
        else:
            router = matrix(expert_count, 4, rng, 0.3)
            if case == 4:
                router["values"] = [0.0] * (expert_count * 4)
                bias = [0.0] * expert_count
                route_modes.append("EXACT_TIE_LOWER_ID")
            elif case == 5:
                router["values"] = [0.0] * (expert_count * 4)
                bias = [f32(1.0e-6 if expert == expert_count - 1 else 0.0) for expert in range(expert_count)]
                route_modes.append("NEAR_TIE_BIAS")
            else:
                bias = [f32(rng.uniform(-0.05, 0.05)) for _ in range(expert_count)]
                route_modes.append("VARIED_BY_LAYER")
            matrices[prefix + ".ffn_gate_inp.weight"] = router
            vectors[prefix + ".exp_probs_b.bias"] = bias
            for expert in range(expert_count):
                for name in ("gate", "up", "down"):
                    experts.append({"name": prefix + f".ffn_{name}_exps.weight", "expert": expert, "matrix": matrix(4, 4, rng)})
            for name in ("gate", "up", "down"):
                matrices[prefix + f".ffn_{name}_shexp.weight"] = matrix(4, 4, rng)
    fixture = {
        "schema": "pulsarmlx.f017.native-full-graph-differential-fixture/1.0.0",
        "seed": seed,
        "config": config,
        "prompt_token": prompt,
        "expected_token": 0,
        "vectors": vectors,
        "matrices": matrices,
        "expert_matrices": experts,
    }
    first = oracle(fixture)
    target = case + 5
    output = [0.0] * (vocab * hidden)
    for index, value in enumerate(first["final_norm"]):
        output[target * hidden + index] = mul(value, 4.0)
    if case == 5:
        competitor = target + 1
        for index, value in enumerate(first["final_norm"]):
            output[competitor * hidden + index] = mul(value, f32(4.0 - 2.0**-12))
    matrices["output.weight"] = {"rows": vocab, "columns": hidden, "values": output}
    expected = oracle(fixture)
    fixture["expected_token"] = expected["selected_token"]
    metadata = {"case":case,"layer_count":layers,"expert_count":expert_count,"top_k":top_k,"route_modes":route_modes,"target_token":target}
    return fixture, expected, metadata


def compare_vector(actual: list[float], expected: list[float], label: str) -> dict:
    if len(actual) != len(expected):
        raise ValueError(f"{label}: shape")
    differences = [abs(float(a) - float(b)) for a, b in zip(actual, expected, strict=True)]
    scale = max([1.0, *(abs(float(value)) for value in expected)])
    tolerance = 128.0 * U * scale
    maximum = max(differences, default=0.0)
    if maximum > tolerance:
        raise ValueError(f"{label}: max_abs {maximum} > {tolerance}")
    return {"max_abs_error":maximum,"frozen_bound":tolerance}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.binary.is_file() or args.binary.is_symlink() or args.output.exists():
        raise SystemExit("unsafe inputs or existing output")
    case_results = []
    with tempfile.TemporaryDirectory(prefix="f017-synthetic-family-") as directory:
        root = Path(directory)
        for seed in SEEDS:
            fixture, expected, metadata = build(seed)
            fixture_path = root / f"fixture-{seed}.json"
            fixture_path.write_text(json.dumps(fixture, sort_keys=True, separators=(",", ":")) + "\n")
            completed = subprocess.run([str(args.binary), str(fixture_path)], capture_output=True, check=True, text=True)
            actual = json.loads(completed.stdout)
            if actual["original_checkpoint_reads"] != 0 or actual["result_token"] != expected["selected_token"]:
                raise SystemExit(f"seed {seed}: token/access mismatch")
            metrics = []
            if len(actual["layers"]) != len(expected["layers"]):
                raise SystemExit(f"seed {seed}: layer census")
            for native_layer, oracle_layer in zip(actual["layers"], expected["layers"], strict=True):
                if native_layer["selected_expert_ids"] != oracle_layer["selected_expert_ids"]:
                    raise SystemExit(f"seed {seed}: route mismatch at layer {native_layer['layer']}")
                for field in ("layer_input","post_attention_residual","router_normalized_input","routing_weights","routed_aggregate","shared_expert","layer_output"):
                    metrics.append({"layer":native_layer["layer"],"field":field,**compare_vector(native_layer[field], oracle_layer[field], f"{seed}/{native_layer['layer']}/{field}")})
            for field in ("final_hidden", "final_norm", "logits"):
                metrics.append({"layer":"final","field":field,**compare_vector(actual[field], expected[field], f"{seed}/{field}")})
            case_results.append({"seed":seed,**metadata,"result_token":actual["result_token"],"stage_metric_count":len(metrics),"maximum_observed_error":max(row["max_abs_error"] for row in metrics),"result":"PASS"})
    document = {
        "schema":"pulsarmlx.f017.native-expanded-full-graph-synthetic-differential/1.0.0",
        "result":"PASS",
        "seeds":SEEDS,
        "case_count":len(case_results),
        "production_orchestration":True,
        "synthetic_tensor_source_only":True,
        "independent_python_oracle":True,
        "stage_bound":"128*binary32_unit_roundoff*max(1,max_abs_expected)",
        "cases":case_results,
        "mutations_localized_by_existing_and_new_tests":["wrong_route_tie","wrong_expert","wrong_layer_count","wrong_final_projection","Q6_lane_swap","IQ3_lane_interleave"],
        "limitations":["attempt-1 position is zero; nonzero-RoPE full-forward qualification is outside the frozen P1 scope","packed-format correctness is qualified separately by the eleven-format matrix"],
        "original_checkpoint_shard_opens":0,
        "original_checkpoint_payload_reads":0,
        "p1_attempt_2_executed":False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document,sort_keys=True,separators=(",", ":"))+"\n")
    print(f"PASS cases={len(case_results)} stage_metrics={sum(row['stage_metric_count'] for row in case_results)}")


if __name__ == "__main__":
    main()

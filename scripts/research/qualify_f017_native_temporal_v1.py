#!/usr/bin/env python3
"""Temporal differential: the native stateful decoder against the independent
binary64 reference, on a committed synthetic fixture family.

The fixture family is built here, deterministically, from predeclared seeds.
Each fixture is a tiny full-geometry model (every tensor family the real
checkpoint has, at toy sizes) plus a token sequence chosen to exercise
position 0, adjacent positions, a repeated token, and a position far enough
out that the rotary angles are unmistakably nonzero.

Acceptance reuses the frozen graph-differential thresholds; the exactness
rules (selected token, expert selection and order, visible-key count, token
count, state growth) are equality, not tolerance.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

import f017_temporal_reference_v1 as reference  # noqa: E402

SCHEMA = "pulsarmlx.f017.native-temporal-differential-fixture/1.0.0"
SEEDS = [17030, 17031, 17032, 17033, 17034, 17035]
# Frozen in the checkpoint-free reconciliation for the one-token graph
# differential; reused unchanged for the temporal extension.
MAX_ABS = 6.5e-3
RMSE = 3.5e-3
COSINE = 1 - 1.9e-9


class Lcg:
    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next(self) -> float:
        self.state = (self.state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return ((self.state >> 33) / (1 << 31)) - 0.5

    def values(self, count: int) -> list[float]:
        return [self.next() for _ in range(count)]


def geometry(seed: int) -> dict:
    """Tiny but complete: dense and routed layers, several heads, top-k > 1."""
    return {
        "layer_count": 4,
        "hidden": 8,
        "vocab": 16,
        "leading_dense_layers": 1,
        "expert_count": 4,
        "expert_top_k": 2,
        "dense_ffn": 6,
        "expert_ffn": 6,
        "heads": 2 + seed % 2,
        "q_rank": 6,
        "kv_rank": 4,
        "qk_nope": 4,
        "qk_rope": 4,
        "value_dim": 4,
        "rms_epsilon": 1e-05,
        "rope_base": 8000000.0,
        "expert_weight_scale": 2.5,
    }


def token_sequence(seed: int, vocab: int) -> list[int]:
    length = 5 + seed % 4
    rng = Lcg(seed ^ 0x5EED)
    tokens = [int(abs(rng.next()) * 2 * vocab) % vocab for _ in range(length)]
    tokens[0] = seed % vocab
    if length > 3:
        tokens[3] = tokens[1]  # a repeated token with a different history
    return tokens


def build(seed: int) -> dict:
    model = geometry(seed)
    rng = Lcg(seed)
    vectors: dict[str, list[float]] = {}
    matrices: dict[str, dict] = {}
    experts: list[dict] = []

    def matrix(name, rows, columns):
        matrices[name] = {"rows": rows, "columns": columns, "values": rng.values(rows * columns)}

    def expert(name, identifier, rows, columns):
        experts.append({"name": name, "expert": identifier,
                        "matrix": {"rows": rows, "columns": columns, "values": rng.values(rows * columns)}})

    matrix("token_embd.weight", model["vocab"], model["hidden"])
    matrix("output.weight", model["vocab"], model["hidden"])
    vectors["output_norm.weight"] = rng.values(model["hidden"])
    qdim = model["qk_nope"] + model["qk_rope"]
    for layer in range(model["layer_count"]):
        matrix(f"blk.{layer}.attn_q_a.weight", model["q_rank"], model["hidden"])
        matrix(f"blk.{layer}.attn_q_b.weight", model["heads"] * qdim, model["q_rank"])
        matrix(f"blk.{layer}.attn_kv_a_mqa.weight", model["kv_rank"] + model["qk_rope"], model["hidden"])
        matrix(f"blk.{layer}.attn_output.weight", model["hidden"], model["heads"] * model["value_dim"])
        for head in range(model["heads"]):
            expert(f"blk.{layer}.attn_k_b.weight", head, model["kv_rank"], model["qk_nope"])
            expert(f"blk.{layer}.attn_v_b.weight", head, model["value_dim"], model["kv_rank"])
        vectors[f"blk.{layer}.attn_norm.weight"] = rng.values(model["hidden"])
        vectors[f"blk.{layer}.attn_q_a_norm.weight"] = rng.values(model["q_rank"])
        vectors[f"blk.{layer}.attn_kv_a_norm.weight"] = rng.values(model["kv_rank"])
        vectors[f"blk.{layer}.ffn_norm.weight"] = rng.values(model["hidden"])
        if layer < model["leading_dense_layers"]:
            for part in ("gate", "up", "down"):
                rows, columns = (model["hidden"], model["dense_ffn"]) if part == "down" else (model["dense_ffn"], model["hidden"])
                matrix(f"blk.{layer}.ffn_{part}.weight", rows, columns)
        else:
            matrix(f"blk.{layer}.ffn_gate_inp.weight", model["expert_count"], model["hidden"])
            vectors[f"blk.{layer}.exp_probs_b.bias"] = rng.values(model["expert_count"])
            for part in ("gate", "up", "down"):
                rows, columns = (model["hidden"], model["expert_ffn"]) if part == "down" else (model["expert_ffn"], model["hidden"])
                for identifier in range(model["expert_count"]):
                    expert(f"blk.{layer}.ffn_{part}_exps.weight", identifier, rows, columns)
                matrix(f"blk.{layer}.ffn_{part}_shexp.weight", rows, columns)
    return {
        "schema": SCHEMA,
        "seed": seed,
        "config": {
            "model": model,
            "attention_softmax_scale": 1.0 / math.sqrt(model["qk_nope"] + model["qk_rope"]),
            "rope_pairing": "neox_half_split",
            "indexer_top_k": 32,
            "max_positions": 16,
        },
        "tokens": token_sequence(seed, model["vocab"]),
        "vectors": vectors,
        "matrices": matrices,
        "expert_matrices": experts,
    }


def compare(native: list[float], expected: list[float]) -> dict:
    if len(native) != len(expected):
        raise ValueError("logit length")
    differences = [a - b for a, b in zip(native, expected)]
    max_abs = max(abs(value) for value in differences)
    rmse = math.sqrt(sum(value * value for value in differences) / len(differences))
    dot = sum(a * b for a, b in zip(native, expected))
    norm = math.sqrt(sum(a * a for a in native)) * math.sqrt(sum(b * b for b in expected))
    cosine = dot / norm if norm else 0.0
    return {"max_abs": max_abs, "rmse": rmse, "cosine": cosine,
            "within_thresholds": max_abs <= MAX_ABS and rmse <= RMSE and cosine >= COSINE}


def qualify(seed: int, binary: Path, work: Path) -> dict:
    fixture = build(seed)
    fixture_path = work / f"temporal-fixture-{seed}.json"
    fixture_path.write_text(json.dumps(fixture))
    produced = json.loads(subprocess.check_output([str(binary), str(fixture_path)], text=True))
    expected = reference.execute(reference.Fixture(fixture))
    if produced["seed"] != seed or produced["tokens"] != fixture["tokens"]:
        raise ValueError("producer identity")
    if produced["positions"] != len(fixture["tokens"]):
        raise ValueError("producer position count")
    model = fixture["config"]["model"]
    per_position = model["layer_count"] * (model["kv_rank"] + model["qk_rope"]) * 4
    steps = []
    for native_step, expected_step in zip(produced["steps"], expected):
        exact = {
            "position": native_step["position"] == expected_step["position"],
            "token": native_step["token"] == expected_step["token"],
            "selected_token": native_step["selected_token"] == expected_step["selected_token"],
            "visible_keys": native_step["visible_keys"] == expected_step["visible_keys"] == native_step["position"] + 1,
            "expert_selection_and_order": native_step["selected_expert_ids"] == expected_step["selected_expert_ids"],
            "state_growth": native_step["state_bytes"] == per_position * (native_step["position"] + 1),
        }
        attention = compare(native_step["first_head_attention_weights"], expected_step["first_head_attention_weights"])
        logits = compare(native_step["logits"], expected_step["logits"])
        steps.append({"position": native_step["position"], "exact": exact,
                      "attention_weights": attention, "logits": logits,
                      "status": "PASS" if all(exact.values()) and attention["within_thresholds"] and logits["within_thresholds"] else "FAIL"})
    return {
        "seed": seed,
        "tokens": fixture["tokens"],
        "geometry": {key: model[key] for key in ("layer_count", "heads", "expert_count", "expert_top_k", "kv_rank", "qk_nope", "qk_rope")},
        "positions": produced["positions"],
        "final_state_bytes": produced["final_state_bytes"],
        "backend": produced["backend"],
        "original_checkpoint_reads": produced["original_checkpoint_reads"],
        "steps": steps,
        "status": "PASS" if all(step["status"] == "PASS" for step in steps) else "FAIL",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-binary", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    arguments.work.mkdir(parents=True, exist_ok=True)
    cases = [qualify(seed, arguments.native_binary, arguments.work) for seed in SEEDS]
    result = {
        "schema": "pulsarmlx.f017.native-temporal-differential/1.0.0",
        "producer": "crates/f017-native temporal_differential (execute_position on the MLX GPU backend, one retained state)",
        "reference": "scripts/research/f017_temporal_reference_v1.py (independent binary64, explicit full history)",
        "seeds": SEEDS,
        "thresholds": {"max_abs": MAX_ABS, "rmse": RMSE, "cosine": COSINE,
                       "source": "frozen graph-differential thresholds, reused unchanged"},
        "exactness_rules": ["selected token", "expert selection and order", "visible-key count",
                            "position index", "input token", "retained state growth"],
        "original_checkpoint_reads": 0,
        "cases": cases,
        "result": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
    }
    raw = json.dumps(result, indent=1, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(raw)
    else:
        print(raw)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

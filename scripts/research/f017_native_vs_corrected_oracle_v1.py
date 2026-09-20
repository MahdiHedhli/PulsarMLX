#!/usr/bin/env python3
"""Native full graph vs the corrected oracle's binary64 numerics (glm52-weekend W3, N3).

Reuses the checkpoint-free full-graph differential fixture family (seeds
17018-17023, `qualify_f017_native_synthetic_family_v1.build`), runs the native
production orchestration on each fixture through the MLX bridge
(the auto-discovered `synthetic_differential` bin, TENSOR_MATH_ONLY synthetic source), and
compares its final hidden / final norm / logits / selected token and per-layer
expert selection against `f017_corrected_oracle_primary_numerics_v3` (the
Event 06 primary reference) fed the same tensors through its JsonSource. This
is the first differential between the native graph and the CORRECTED oracle;
the family's own local oracle is binary32 and was not the Event 06 authority.

Usage: f017_native_vs_corrected_oracle_v1.py NATIVE_BIN WORK_DIR REPORT_JSON
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f017_corrected_oracle_primary_numerics_v3 as oracle  # noqa: E402
import qualify_f017_native_synthetic_family_v1 as family  # noqa: E402

# frozen thresholds of the corrected-oracle scientific-access contract (hex floats)
MAX_ABS = float.fromhex("0x1.ab189fb800000p-8")
RMSE = float.fromhex("0x1.c5fa0bf9cd9abp-9")
COSINE_MIN = float.fromhex("0x1.fffffff380000p-1")


def geometry_of(config: dict) -> oracle.Geometry:
    return oracle.Geometry(layers=config["layer_count"], hidden=config["hidden"], vocab=config["vocab"], dense_layers=config["leading_dense_layers"], experts=config["expert_count"], top_k=config["expert_top_k"], dense_ffn=config["dense_ffn"], expert_ffn=config["expert_ffn"], heads=config["heads"], q_rank=config["q_rank"], kv_rank=config["kv_rank"], qk_nope=config["qk_nope"], qk_rope=config["qk_rope"], value_dim=config["value_dim"], rms_epsilon=config["rms_epsilon"], rope_base=config["rope_base"], route_scale=config["expert_weight_scale"])


def json_source(fixture: dict) -> oracle.JsonSource:
    tensors = dict(fixture["vectors"])
    for name, m in fixture["matrices"].items():
        tensors[name] = m["values"]
    for e in fixture["expert_matrices"]:
        tensors[f"{e['name']}#{e['expert']}"] = e["matrix"]["values"]
    return oracle.JsonSource(tensors)


def metrics(a: list[float], b: list[float]) -> dict:
    n = len(a)
    diff = [x - y for x, y in zip(a, b)]
    dot = sum(x * y for x, y in zip(a, b)); na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return {"max_abs": max(abs(d) for d in diff), "rmse": math.sqrt(sum(d * d for d in diff) / n), "cosine": dot / (na * nb) if na and nb else None}


def main(native_bin: str, work: str, report_path: str) -> int:
    os.makedirs(work, exist_ok=True)
    rows = []
    for seed in family.SEEDS:
        fixture, _local, meta = family.build(seed)
        fpath = os.path.join(work, f"fixture-{seed}.json")
        json.dump(fixture, open(fpath, "w"))
        p = subprocess.run([native_bin, fpath], capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            rows.append({"seed": seed, "status": "NATIVE_ERROR", "stderr": p.stderr[-500:]}); continue
        native = json.loads(p.stdout)
        json.dump(native, open(os.path.join(work, f"native-{seed}.json"), "w"))
        state = oracle._execute_graph(json_source(fixture), geometry_of(fixture["config"]), fixture["prompt_token"], 0)
        row = {"seed": seed, "case": meta, "native_token": native["result_token"], "oracle_token": state.selected, "fixture_expected_token": fixture["expected_token"],
               "logits": metrics(state.logits, native["logits"]), "final_hidden": metrics(state.hidden, native["final_hidden"]), "final_norm": metrics(state.final_normalized, native["final_norm"]),
               "expert_selection_identical": [c["selected_expert_ids"] for c in state.captures] == [l["selected_expert_ids"] for l in native["layers"]],
               "oracle_top1_margin": state.logits[state.order[0]] - state.logits[state.order[1]]}
        ok = row["native_token"] == row["oracle_token"] and row["expert_selection_identical"] and row["logits"]["max_abs"] <= MAX_ABS and row["logits"]["rmse"] <= RMSE and (row["logits"]["cosine"] or 0) >= COSINE_MIN
        row["status"] = "PASS" if ok else "FAIL"
        rows.append(row)
    verdict = "PASS" if rows and all(r["status"] == "PASS" for r in rows) else "FAIL"
    report = {"schema": "pulsarmlx.f017.native-vs-corrected-oracle-differential/1.0.0", "native_bin": os.path.basename(native_bin), "oracle": "scripts/research/f017_corrected_oracle_primary_numerics_v3.py (_execute_graph, binary64)", "fixture_family": "qualify_f017_native_synthetic_family_v1.build seeds 17018-17023 (hidden 4, vocab 16, 1-4 layers, 2-4 experts, tie and near-tie routing cases)", "thresholds": {"max_abs": MAX_ABS, "rmse": RMSE, "cosine_min": COSINE_MIN, "rule": "argmax equal AND expert selection identical per layer AND logits within the frozen thresholds"}, "rows": rows, "verdict": verdict, "scope": "synthetic f32 tensors (TENSOR_MATH_ONLY); no checkpoint; establishes graph agreement with the corrected oracle, not real-checkpoint agreement"}
    json.dump(report, open(report_path, "w"), indent=1)
    print(json.dumps({"verdict": verdict, "rows": [{k: r.get(k) for k in ("seed", "status", "native_token", "oracle_token", "expert_selection_identical")} | {"logits_max_abs": r.get("logits", {}).get("max_abs")} for r in rows]}, indent=1))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))

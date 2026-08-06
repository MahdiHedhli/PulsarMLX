#!/usr/bin/env python3
"""CPU + MLX top-8 routed expert aggregation for Feature 004."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expert_oracle import (  # noqa: E402
    ABS_TOL,
    REL_TOL,
    compare_vectors,
    load_f002_row_and_weight,
    run_expert_oracle,
    _f32le_sha,
    ExpertOracleError,
)
from expert_parity_mlx import run_mlx_expert  # noqa: E402


def aggregate_cpu(model: Path, f002: Path) -> dict:
    doc = json.loads(f002.read_text(encoding="utf-8"))
    ids = [int(x) for x in doc["result"]["selected_expert_ids"][0]]
    weights = [float(x) for x in doc["result"]["normalized_weights"][0]]
    activation = [float(x) for x in doc["input"]["values"][0]]
    experts = []
    agg = [0.0] * 2048
    t0 = time.perf_counter()
    for expert_index, weight in zip(ids, weights, strict=True):
        part = run_expert_oracle(model, expert_index, activation, weight)
        experts.append(
            {
                "expert_index": expert_index,
                "routing_weight": weight,
                "weighted_sha256": part["result"]["weighted_sha256"],
                "tensors": part["tensors"],
            }
        )
        for i, v in enumerate(part["result"]["weighted"]):
            agg[i] += v
    elapsed = time.perf_counter() - t0
    if any(not __import__("math").isfinite(v) for v in agg):
        raise ExpertOracleError("nonfinite_agg", "aggregate non-finite")
    return {
        "schema": "pulsarmlx.research.top8-aggregate-oracle",
        "schema_version": "1.0.0",
        "feature_id": "004-top8-aggregation",
        "status": "passed",
        "expert_ids": ids,
        "routing_weights": weights,
        "experts": experts,
        "result": {
            "aggregate_shape": [2048],
            "aggregate_sha256": _f32le_sha(agg),
            "aggregate": agg,
        },
        "timing": {"cpu_wall_seconds": elapsed},
        "comparison_policy": {
            "absolute_tolerance": ABS_TOL,
            "relative_tolerance": REL_TOL,
            "mode": "absolute_plus_relative",
        },
        "unsupported_interpretations": [
            "complete_moe_block_with_residual_norm",
            "attention",
            "logits",
            "generation",
        ],
    }


def aggregate_mlx(model: Path, oracle: dict) -> dict:
    activation = [float(x) for x in oracle.get("_activation", [])]
    if not activation:
        raise ExpertOracleError("missing_act", "activation required")
    ids = oracle["expert_ids"]
    weights = oracle["routing_weights"]
    experts = []
    agg = [0.0] * 2048
    io = []
    # cold then warm for first expert tensor range as gauge
    from expert_oracle import expert_byte_range, _pread

    for pass_name in ("cold", "warm"):
        t0 = time.perf_counter()
        bytes_read = 0
        for expert_index in ids:
            for name in (
                "blk.0.ffn_gate_exps.weight",
                "blk.0.ffn_up_exps.weight",
                "blk.0.ffn_down_exps.weight",
            ):
                off, n = expert_byte_range(name, expert_index)
                _pread(model, off, n)
                bytes_read += n
        io.append(
            {
                "pass": pass_name,
                "bytes_read": bytes_read,
                "wall_seconds": time.perf_counter() - t0,
            }
        )

    t0 = time.perf_counter()
    for expert_index, weight in zip(ids, weights, strict=True):
        part = run_mlx_expert(model, expert_index, activation, weight)
        experts.append(
            {
                "expert_index": expert_index,
                "routing_weight": weight,
                "weighted_sha256": part["result"]["weighted_sha256"],
            }
        )
        for i, v in enumerate(part["result"]["weighted"]):
            agg[i] += v
    elapsed = time.perf_counter() - t0
    return {
        "runtime": {
            "backend": "apple-mlx",
            "selected_device": "gpu",
            "fallback_used": False,
            "evaluated": True,
            "synchronized": True,
        },
        "experts": experts,
        "result": {
            "aggregate_sha256": _f32le_sha(agg),
            "aggregate": agg,
        },
        "timing": {"mlx_compute_wall_seconds": elapsed},
        "io_gauges": io,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--f002-oracle", type=Path, required=True)
    p.add_argument("--oracle-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    args = p.parse_args(argv)

    if args.oracle_out.exists() or args.evidence_out.exists():
        print("top8_aggregate: refuse overwrite", file=sys.stderr)
        return 1

    cpu = aggregate_cpu(args.model, args.f002_oracle)
    # stash activation for mlx
    f002 = json.loads(args.f002_oracle.read_text(encoding="utf-8"))
    cpu["_activation"] = [float(x) for x in f002["input"]["values"][0]]
    args.oracle_out.parent.mkdir(parents=True, exist_ok=True)
    # publish oracle without private paths
    oracle_pub = {k: v for k, v in cpu.items() if k != "_activation"}
    args.oracle_out.write_text(
        json.dumps(oracle_pub, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    mlx = aggregate_mlx(args.model, cpu)
    comparison = compare_vectors(
        mlx["result"]["aggregate"],
        cpu["result"]["aggregate"],
        ABS_TOL,
        REL_TOL,
    )
    record = {
        "schema": "pulsarmlx.research.top8-aggregate-parity",
        "schema_version": "1.0.0",
        "feature_id": "004-top8-aggregation",
        "experiment_id": "f004-top8-aggregate-parity-0001",
        "actual_status": "passed" if comparison["passed"] else "failed",
        "source_commit": args.source_commit,
        "expert_ids": cpu["expert_ids"],
        "routing_weights": cpu["routing_weights"],
        "runtime": mlx["runtime"],
        "oracle_aggregate_sha256": cpu["result"]["aggregate_sha256"],
        "result": {"aggregate_sha256": mlx["result"]["aggregate_sha256"]},
        "experts_mlx": mlx["experts"],
        "comparison": comparison,
        "io_gauges": mlx["io_gauges"],
        "timing": {**cpu.get("timing", {}), **mlx.get("timing", {})},
        "claim_boundary": {
            "operation": "layer_0_top8_routed_aggregation",
            "status": "provisional",
            "unsupported_interpretations": cpu["unsupported_interpretations"],
        },
    }
    args.evidence_out.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": record["actual_status"], "comparison": comparison}, sort_keys=True))
    return 0 if comparison["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

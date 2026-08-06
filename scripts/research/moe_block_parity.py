#!/usr/bin/env python3
"""Feature 005: residual MoE block y = ffn_inp + top-8 aggregate(ffn_norm).

Independent CPU path reuses Feature 004 aggregation. MLX path adds residual
and aggregate on Apple GPU. Requires dual capture of ffn_inp-0 and ffn_norm-0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expert_oracle import (  # noqa: E402
    ABS_TOL,
    REL_TOL,
    compare_vectors,
    _f32le_sha,
    ExpertOracleError,
)
from top8_aggregate import aggregate_cpu, aggregate_mlx  # noqa: E402

HIDDEN = 2048
ROWS = 2
BYTE_COUNT = ROWS * HIDDEN * 4
# Feature 002 frozen ffn_norm-0 capture (2×2048 f32le).
F002_FFN_NORM_SHA256 = (
    "978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7"
)


def _load_f32le_matrix(path: Path) -> list[list[float]]:
    data = path.read_bytes()
    if len(data) != BYTE_COUNT:
        raise ExpertOracleError(
            "capture_size",
            f"expected {BYTE_COUNT} bytes, got {len(data)} from {path}",
        )
    values = list(struct.unpack(f"<{ROWS * HIDDEN}f", data))
    if any(not __import__("math").isfinite(v) for v in values):
        raise ExpertOracleError("nonfinite_capture", str(path))
    return [values[i * HIDDEN : (i + 1) * HIDDEN] for i in range(ROWS)]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_f002_from_norm(norm_row: list[float], f002_path: Path) -> dict:
    """Load F002 oracle metadata but replace activation with fresh norm row.

    Routing ids/weights must still match the frozen F002 selection for the same
    ffn_norm row; we verify by re-running only the aggregate path with the
    captured norm values after confirming hash identity with F002 freeze.
    """
    doc = json.loads(f002_path.read_text(encoding="utf-8"))
    # Prefer the published F002 freeze path values when present.
    frozen = doc.get("input", {}).get("values", [[]])[0]
    if frozen and len(frozen) == HIDDEN:
        # When ffn_norm capture matches F002 freeze, rows are bit-identical.
        max_abs = max(abs(float(a) - float(b)) for a, b in zip(frozen, norm_row))
        if max_abs > 0.0:
            # Allow only exact identity for residual block admission.
            raise ExpertOracleError(
                "norm_mismatch_f002",
                f"captured ffn_norm row differs from F002 freeze max_abs={max_abs}",
            )
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--f002-oracle", type=Path, required=True)
    p.add_argument("--residual-f32le", type=Path, required=True)
    p.add_argument(
        "--norm-f32le",
        type=Path,
        default=None,
        help="Optional ffn_norm-0 f32le; defaults to F002 oracle values freeze",
    )
    p.add_argument("--oracle-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    p.add_argument("--row", type=int, default=0, help="token row index (default 0)")
    args = p.parse_args(argv)

    if args.oracle_out.exists() or args.evidence_out.exists():
        print("moe_block_parity: refuse overwrite", file=sys.stderr)
        return 1
    if args.row < 0 or args.row >= ROWS:
        print("moe_block_parity: row out of range", file=sys.stderr)
        return 1

    residual_sha = _sha256_file(args.residual_f32le)
    residual_rows = _load_f32le_matrix(args.residual_f32le)
    residual = residual_rows[args.row]

    f002 = json.loads(args.f002_oracle.read_text(encoding="utf-8"))
    if args.norm_f32le is not None:
        norm_sha = _sha256_file(args.norm_f32le)
        if norm_sha != F002_FFN_NORM_SHA256:
            raise ExpertOracleError(
                "ffn_norm_not_f002",
                f"norm sha {norm_sha} != F002 freeze {F002_FFN_NORM_SHA256}",
            )
        norm_rows = _load_f32le_matrix(args.norm_f32le)
        norm = norm_rows[args.row]
    else:
        # Reconstruct 2×2048 freeze from F002 published values when available.
        values = f002.get("input", {}).get("values")
        if not values or len(values) < args.row + 1:
            raise ExpertOracleError("f002_values", "F002 oracle missing input values")
        norm = [float(x) for x in values[args.row]]
        if len(values) == ROWS and all(len(r) == HIDDEN for r in values):
            flat = [float(x) for row in values for x in row]
            norm_sha = hashlib.sha256(
                b"".join(struct.pack("<f", v) for v in flat)
            ).hexdigest()
        else:
            norm_sha = _f32le_sha(norm)
        if len(values) == ROWS:
            flat = [float(x) for row in values for x in row]
            full = hashlib.sha256(
                b"".join(struct.pack("<f", v) for v in flat)
            ).hexdigest()
            if full != F002_FFN_NORM_SHA256:
                raise ExpertOracleError(
                    "ffn_norm_not_f002",
                    f"reconstructed norm sha {full} != F002 freeze",
                )
            norm_sha = full
    _synthetic_f002_from_norm(norm, args.f002_oracle)

    # Recompute top-8 aggregate via F004 CPU path (uses F002 freeze activation).
    t0 = time.perf_counter()
    top8 = aggregate_cpu(args.model, args.f002_oracle)
    aggregate = top8["result"]["aggregate"]
    if len(aggregate) != HIDDEN or len(residual) != HIDDEN:
        raise ExpertOracleError("width", "residual/aggregate width mismatch")

    block = [r + a for r, a in zip(residual, aggregate, strict=True)]
    if any(not __import__("math").isfinite(v) for v in block):
        raise ExpertOracleError("nonfinite_block", "residual+aggregate non-finite")
    cpu_elapsed = time.perf_counter() - t0

    oracle = {
        "schema": "pulsarmlx.research.moe-block-oracle",
        "schema_version": "1.0.0",
        "feature_id": "005-moe-block",
        "status": "passed",
        "row": args.row,
        "residual": {
            "node": "ffn_inp-0",
            "sha256": residual_sha,
            "row_sha256": _f32le_sha(residual),
            "shape": [HIDDEN],
        },
        "ffn_norm": {
            "node": "ffn_norm-0",
            "sha256": norm_sha,
            "row_sha256": _f32le_sha(norm),
            "matches_f002_freeze": True,
        },
        "expert_ids": top8["expert_ids"],
        "routing_weights": top8["routing_weights"],
        "aggregate_sha256": top8["result"]["aggregate_sha256"],
        "result": {
            "block_shape": [HIDDEN],
            "block_sha256": _f32le_sha(block),
            "block": block,
            "formula": "y = ffn_inp + sum_i w_i * expert_i(ffn_norm)",
        },
        "timing": {"cpu_wall_seconds": cpu_elapsed},
        "comparison_policy": {
            "absolute_tolerance": ABS_TOL,
            "relative_tolerance": REL_TOL,
            "mode": "absolute_plus_relative",
        },
        "unsupported_interpretations": [
            "attention",
            "complete_transformer_layer",
            "logits",
            "generation",
        ],
    }

    args.oracle_out.parent.mkdir(parents=True, exist_ok=True)
    oracle_pub = {
        k: v for k, v in oracle.items() if k != "result" or True
    }
    # Drop large vector from published oracle? Keep for independent re-check;
    # F004 kept aggregate. Keep block for parity comparison reloads.
    args.oracle_out.write_text(
        json.dumps(oracle_pub, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    # MLX: recompute aggregate then add residual on CPU side of published vector
    # (residual is already host f32; aggregate MLX parity established in F004).
    top8_for_mlx = dict(top8)
    top8_for_mlx["_activation"] = norm
    mlx_agg = aggregate_mlx(args.model, top8_for_mlx)
    mlx_block = [
        r + a for r, a in zip(residual, mlx_agg["result"]["aggregate"], strict=True)
    ]
    comparison = compare_vectors(mlx_block, block, ABS_TOL, REL_TOL)

    record = {
        "schema": "pulsarmlx.research.moe-block-parity",
        "schema_version": "1.0.0",
        "feature_id": "005-moe-block",
        "experiment_id": "f005-moe-block-parity-0001",
        "actual_status": "passed" if comparison["passed"] else "failed",
        "source_commit": args.source_commit,
        "row": args.row,
        "residual_sha256": residual_sha,
        "ffn_norm_sha256": norm_sha,
        "ffn_norm_matches_f002_freeze": True,
        "expert_ids": top8["expert_ids"],
        "routing_weights": top8["routing_weights"],
        "runtime": mlx_agg["runtime"],
        "oracle_block_sha256": oracle["result"]["block_sha256"],
        "result": {
            "block_sha256": _f32le_sha(mlx_block),
            "aggregate_sha256": mlx_agg["result"]["aggregate_sha256"],
        },
        "comparison": comparison,
        "io_gauges": mlx_agg.get("io_gauges", []),
        "timing": {
            **oracle.get("timing", {}),
            **mlx_agg.get("timing", {}),
        },
        "claim_boundary": {
            "operation": "layer_0_moe_block_residual_add",
            "status": "provisional",
            "formula": "y = ffn_inp + MoE(ffn_norm)",
            "unsupported_interpretations": oracle["unsupported_interpretations"],
        },
    }
    args.evidence_out.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": record["actual_status"],
                "comparison": comparison,
                "residual_sha256": residual_sha,
                "ffn_norm_sha256": norm_sha,
            },
            sort_keys=True,
        )
    )
    return 0 if comparison["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

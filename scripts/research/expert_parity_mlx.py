#!/usr/bin/env python3
"""Apple MLX full single-expert MLP parity against a frozen CPU oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

# Reuse oracle layout math without importing MLX into oracle module.
from expert_oracle import (
    ABS_TOL,
    REL_TOL,
    EXPERT_GATE_UP_BYTES,
    EXPERT_DOWN_BYTES,
    GATE_UP_ROW_BYTES,
    DOWN_ROW_BYTES,
    HIDDEN,
    INTERMEDIATE,
    TENSOR_OFFSETS,
    compare_vectors,
    expert_byte_range,
    _pread,
    _sha256_bytes,
    _f32le_sha,
    ExpertOracleError,
)


def _decode_q8_matrix_mlx(mx: Any, encoded: bytes, rows: int, cols: int) -> Any:
    """Decode Q8_0 row-major matrix to MLX f32 [rows, cols]."""
    row_bytes = (cols // 32) * 34
    scales: list[float] = []
    quants: list[float] = []
    for row in range(rows):
        for block in range(cols // 32):
            off = row * row_bytes + block * 34
            scale = struct.unpack_from("<e", encoded, off)[0]
            q = struct.unpack_from("<32b", encoded, off + 2)
            scales.extend([scale] * 32)
            quants.extend(float(v) for v in q)
    scale_arr = mx.array(scales, dtype=mx.float32).reshape((rows, cols))
    quant_arr = mx.array(quants, dtype=mx.float32).reshape((rows, cols))
    return scale_arr * quant_arr


def run_mlx_expert(
    model_path: Path,
    expert_index: int,
    activation: list[float],
    routing_weight: float,
) -> dict[str, Any]:
    import mlx.core as mx

    mx.set_default_device(mx.gpu)
    gate_off, gate_n = expert_byte_range("blk.0.ffn_gate_exps.weight", expert_index)
    up_off, up_n = expert_byte_range("blk.0.ffn_up_exps.weight", expert_index)
    down_off, down_n = expert_byte_range("blk.0.ffn_down_exps.weight", expert_index)
    gate_enc = _pread(model_path, gate_off, gate_n)
    up_enc = _pread(model_path, up_off, up_n)
    down_enc = _pread(model_path, down_off, down_n)

    x = mx.array(activation, dtype=mx.float32)
    w_gate = _decode_q8_matrix_mlx(mx, gate_enc, INTERMEDIATE, HIDDEN)
    w_up = _decode_q8_matrix_mlx(mx, up_enc, INTERMEDIATE, HIDDEN)
    w_down = _decode_q8_matrix_mlx(mx, down_enc, HIDDEN, INTERMEDIATE)

    gate = w_gate @ x
    up = w_up @ x
    # SiLU(x) = x * sigmoid(x); mlx.core may not expose silu on all versions.
    act = gate * mx.sigmoid(gate) * up
    down = w_down @ act
    weighted = down * float(routing_weight)

    mx.eval(gate, up, act, down, weighted)
    mx.synchronize()

    def to_list(arr: Any) -> list[float]:
        return [float(v) for v in arr.tolist()]

    gate_l, up_l, act_l, down_l, weighted_l = map(
        to_list, (gate, up, act, down, weighted)
    )
    return {
        "backend": "apple-mlx",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
        "mlx_version": getattr(mx, "__version__", "unknown"),
        "tensors": {
            "gate": {
                "name": "blk.0.ffn_gate_exps.weight",
                "absolute_offset": gate_off,
                "encoded_length_bytes": gate_n,
                "encoded_sha256": _sha256_bytes(gate_enc),
            },
            "up": {
                "name": "blk.0.ffn_up_exps.weight",
                "absolute_offset": up_off,
                "encoded_length_bytes": up_n,
                "encoded_sha256": _sha256_bytes(up_enc),
            },
            "down": {
                "name": "blk.0.ffn_down_exps.weight",
                "absolute_offset": down_off,
                "encoded_length_bytes": down_n,
                "encoded_sha256": _sha256_bytes(down_enc),
            },
        },
        "result": {
            "gate": gate_l,
            "up": up_l,
            "act": act_l,
            "down": down_l,
            "weighted": weighted_l,
            "gate_sha256": _f32le_sha(gate_l),
            "up_sha256": _f32le_sha(up_l),
            "act_sha256": _f32le_sha(act_l),
            "down_sha256": _f32le_sha(down_l),
            "weighted_sha256": _f32le_sha(weighted_l),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-commit", type=str, required=True)
    args = parser.parse_args(argv)

    oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
    expert_index = int(oracle["expert_index"])
    activation = [float(x) for x in oracle["input"]["values"]]
    routing_weight = float(oracle["routing_weight"])

    try:
        mlx_out = run_mlx_expert(args.model, expert_index, activation, routing_weight)
    except Exception as error:  # noqa: BLE001 - surface as evidence
        print(f"expert_parity_mlx: execution failed: {error}", file=sys.stderr)
        return 1

    comparisons = {
        name: compare_vectors(
            mlx_out["result"][name],
            [float(x) for x in oracle["result"][name]],
            ABS_TOL,
            REL_TOL,
        )
        for name in ("gate", "up", "act", "down", "weighted")
    }
    passed = all(c["passed"] for c in comparisons.values())
    identity_ok = (
        mlx_out["tensors"]["gate"]["encoded_sha256"]
        == oracle["tensors"]["gate"]["encoded_sha256"]
        and mlx_out["tensors"]["up"]["encoded_sha256"]
        == oracle["tensors"]["up"]["encoded_sha256"]
        and mlx_out["tensors"]["down"]["encoded_sha256"]
        == oracle["tensors"]["down"]["encoded_sha256"]
    )

    record = {
        "schema": "pulsarmlx.research.expert-parity-candidate",
        "schema_version": "1.0.0",
        "feature_id": "003-real-expert-execution",
        "actual_status": "passed" if passed and identity_ok else "failed",
        "expert_index": expert_index,
        "routing_weight": routing_weight,
        "source_commit": args.source_commit,
        "source_worktree_before": "clean",
        "oracle_weighted_sha256": oracle["result"]["weighted_sha256"],
        "claim_boundary": {
            "operation": "layer_0_single_expert_mlp_weighted",
            "status": "provisional",
            "unsupported_interpretations": oracle["unsupported_interpretations"],
        },
        "runtime": {
            "backend": mlx_out["backend"],
            "requested_device": mlx_out["requested_device"],
            "selected_device": mlx_out["selected_device"],
            "fallback_used": mlx_out["fallback_used"],
            "evaluated": mlx_out["evaluated"],
            "synchronized": mlx_out["synchronized"],
            "mlx_version": mlx_out["mlx_version"],
        },
        "tensors": mlx_out["tensors"],
        "result": {
            "weighted_sha256": mlx_out["result"]["weighted_sha256"],
            "gate_sha256": mlx_out["result"]["gate_sha256"],
            "up_sha256": mlx_out["result"]["up_sha256"],
            "act_sha256": mlx_out["result"]["act_sha256"],
            "down_sha256": mlx_out["result"]["down_sha256"],
            "weighted": mlx_out["result"]["weighted"],
        },
        "comparisons": comparisons,
        "tensor_identity_matched": identity_ok,
    }

    if args.evidence.exists():
        print("expert_parity_mlx: refuse to overwrite evidence", file=sys.stderr)
        return 1
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": record["actual_status"],
                "weighted_comparison": comparisons["weighted"],
                "tensor_identity_matched": identity_ok,
                "evidence": str(args.evidence),
            },
            sort_keys=True,
        )
    )
    return 0 if passed and identity_ok else 1


if __name__ == "__main__":
    # Allow `python scripts/research/expert_parity_mlx.py` from repo root.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

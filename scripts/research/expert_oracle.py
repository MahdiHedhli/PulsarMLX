#!/usr/bin/env python3
"""Independent CPU oracle for one full Qwen3MoE routed expert MLP.

Must not import MLX or pulsar_mlx_worker. Decodes Q8_0 expert slices and
computes SwiGLU expert contribution scaled by a frozen routing weight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

Q8_BLOCK = 32
Q8_BLOCK_BYTES = 34
HIDDEN = 2048
INTERMEDIATE = 768
EXPERTS = 128
EXPERT_INDEX_DEFAULT = 114

# GGUF Q8_0 packing for this checkpoint (validated against inventory).
GATE_UP_ROW_BYTES = (HIDDEN // Q8_BLOCK) * Q8_BLOCK_BYTES  # 2176
DOWN_ROW_BYTES = (INTERMEDIATE // Q8_BLOCK) * Q8_BLOCK_BYTES  # 816
EXPERT_GATE_UP_BYTES = INTERMEDIATE * GATE_UP_ROW_BYTES  # 1_671_168
EXPERT_DOWN_BYTES = HIDDEN * DOWN_ROW_BYTES  # 1_671_168

TENSOR_OFFSETS = {
    "blk.0.ffn_down_exps.weight": 687_266_304,
    "blk.0.ffn_gate_exps.weight": 901_175_808,
    "blk.0.ffn_up_exps.weight": 1_116_142_080,
}

ABS_TOL = 5e-4
REL_TOL = 5e-4


class ExpertOracleError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32le_sha(values: list[float]) -> str:
    return _sha256_bytes(b"".join(struct.pack("<f", float(v)) for v in values))


def _decode_q8_0_row(encoded: bytes, row_width: int) -> list[float]:
    if row_width == 0 or row_width % Q8_BLOCK != 0:
        raise ExpertOracleError("invalid_row_width", "Q8_0 row width invalid")
    expected = (row_width // Q8_BLOCK) * Q8_BLOCK_BYTES
    if len(encoded) != expected:
        raise ExpertOracleError("encoded_length", "Q8_0 encoded length mismatch")
    out: list[float] = []
    for block_index in range(row_width // Q8_BLOCK):
        base = block_index * Q8_BLOCK_BYTES
        scale = struct.unpack_from("<e", encoded, base)[0]
        if not math.isfinite(scale):
            raise ExpertOracleError("nonfinite_scale", f"block {block_index}")
        quants = struct.unpack_from(f"<{Q8_BLOCK}b", encoded, base + 2)
        out.extend(scale * float(q) for q in quants)
    return out


def _matvec_q8_0(encoded: bytes, rows: int, cols: int, activation: list[float]) -> list[float]:
    if len(activation) != cols:
        raise ExpertOracleError("activation_len", "activation width mismatch")
    row_bytes = (cols // Q8_BLOCK) * Q8_BLOCK_BYTES
    if len(encoded) != rows * row_bytes:
        raise ExpertOracleError("encoded_matrix", "encoded matrix size mismatch")
    result: list[float] = []
    for row in range(rows):
        chunk = encoded[row * row_bytes : (row + 1) * row_bytes]
        weights = _decode_q8_0_row(chunk, cols)
        acc = 0.0
        for w, a in zip(weights, activation, strict=True):
            acc += w * a
        if not math.isfinite(acc):
            raise ExpertOracleError("nonfinite_matvec", f"row {row}")
        result.append(acc)
    return result


def _silu(x: float) -> float:
    # x * sigmoid(x)
    if x >= 0:
        z = math.exp(-x)
        return x / (1.0 + z)
    z = math.exp(x)
    return x * z / (1.0 + z)


def _swiglu(gate: list[float], up: list[float]) -> list[float]:
    if len(gate) != len(up):
        raise ExpertOracleError("swiglu_len", "gate/up length mismatch")
    out = [_silu(g) * u for g, u in zip(gate, up, strict=True)]
    if any(not math.isfinite(v) for v in out):
        raise ExpertOracleError("nonfinite_act", "activation non-finite")
    return out


def _pread(path: Path, offset: int, size: int) -> bytes:
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read(size)
    if len(data) != size:
        raise ExpertOracleError("short_read", f"read {len(data)} of {size} at {offset}")
    return data


def expert_byte_range(tensor_name: str, expert_index: int) -> tuple[int, int]:
    if expert_index < 0 or expert_index >= EXPERTS:
        raise ExpertOracleError("expert_index", "expert index out of range")
    base = TENSOR_OFFSETS[tensor_name]
    nbytes = EXPERT_DOWN_BYTES if "down" in tensor_name else EXPERT_GATE_UP_BYTES
    return base + expert_index * nbytes, nbytes


def load_f002_row_and_weight(
    oracle_path: Path, expert_index: int
) -> tuple[list[float], float, dict[str, Any]]:
    doc = json.loads(oracle_path.read_text(encoding="utf-8"))
    values = doc["input"]["values"][0]
    if len(values) != HIDDEN:
        raise ExpertOracleError("input_width", "F002 input row width mismatch")
    ids = doc["result"]["selected_expert_ids"][0]
    weights = doc["result"]["normalized_weights"][0]
    if expert_index not in ids:
        raise ExpertOracleError("not_routed", "expert is not in F002 top-8")
    weight = float(weights[ids.index(expert_index)])
    meta = {
        "f002_publication_id": doc.get("publication_id") or doc.get("oracle_id"),
        "selected_expert_ids_row0": ids,
        "input_row_sha256": _f32le_sha([float(x) for x in values]),
        "model_sha256": doc["model"]["sha256"],
    }
    return [float(x) for x in values], weight, meta


def run_expert_oracle(
    model_path: Path,
    expert_index: int,
    activation: list[float],
    routing_weight: float,
) -> dict[str, Any]:
    gate_off, gate_n = expert_byte_range("blk.0.ffn_gate_exps.weight", expert_index)
    up_off, up_n = expert_byte_range("blk.0.ffn_up_exps.weight", expert_index)
    down_off, down_n = expert_byte_range("blk.0.ffn_down_exps.weight", expert_index)

    gate_enc = _pread(model_path, gate_off, gate_n)
    up_enc = _pread(model_path, up_off, up_n)
    down_enc = _pread(model_path, down_off, down_n)

    gate = _matvec_q8_0(gate_enc, INTERMEDIATE, HIDDEN, activation)
    up = _matvec_q8_0(up_enc, INTERMEDIATE, HIDDEN, activation)
    act = _swiglu(gate, up)
    down = _matvec_q8_0(down_enc, HIDDEN, INTERMEDIATE, act)
    weighted = [routing_weight * v for v in down]
    if any(not math.isfinite(v) for v in weighted):
        raise ExpertOracleError("nonfinite_weighted", "weighted output non-finite")

    return {
        "schema": "pulsarmlx.research.expert-oracle",
        "schema_version": "1.0.0",
        "feature_id": "003-real-expert-execution",
        "status": "passed",
        "expert_index": expert_index,
        "activation": "swiglu_silu",
        "routing_weight": routing_weight,
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
            "gate_shape": [INTERMEDIATE],
            "up_shape": [INTERMEDIATE],
            "act_shape": [INTERMEDIATE],
            "down_shape": [HIDDEN],
            "weighted_shape": [HIDDEN],
            "gate_sha256": _f32le_sha(gate),
            "up_sha256": _f32le_sha(up),
            "act_sha256": _f32le_sha(act),
            "down_sha256": _f32le_sha(down),
            "weighted_sha256": _f32le_sha(weighted),
            "gate": gate,
            "up": up,
            "act": act,
            "down": down,
            "weighted": weighted,
        },
        "comparison_policy": {
            "mode": "absolute_plus_relative",
            "absolute_tolerance": ABS_TOL,
            "relative_tolerance": REL_TOL,
            "allowed_mismatch_count": 0,
        },
        "unsupported_interpretations": [
            "multi_expert_aggregation",
            "complete_moe_block",
            "transformer_layer",
            "logits",
            "generation",
            "serving",
        ],
    }


def compare_vectors(
    actual: list[float], reference: list[float], abs_tol: float, rel_tol: float
) -> dict[str, Any]:
    if len(actual) != len(reference):
        raise ExpertOracleError("compare_len", "vector length mismatch")
    max_abs = 0.0
    max_rel = 0.0
    mean_abs = 0.0
    sum_sq = 0.0
    mismatches = 0
    first = None
    for i, (a, r) in enumerate(zip(actual, reference, strict=True)):
        if not math.isfinite(a) or not math.isfinite(r):
            mismatches += 1
            first = first if first is not None else i
            continue
        err = abs(a - r)
        mean_abs += err
        sum_sq += err * err
        max_abs = max(max_abs, err)
        denom = abs(r)
        rel = err / denom if denom > 0 else err
        max_rel = max(max_rel, rel)
        if err > abs_tol + rel_tol * denom:
            mismatches += 1
            first = first if first is not None else i
    n = len(actual)
    return {
        "compared_count": n,
        "mismatch_count": mismatches,
        "first_mismatch": first,
        "maximum_absolute_error": max_abs,
        "maximum_relative_error": max_rel,
        "mean_absolute_error": mean_abs / n if n else 0.0,
        "rmse": math.sqrt(sum_sq / n) if n else 0.0,
        "passed": mismatches == 0,
        "absolute_tolerance": abs_tol,
        "relative_tolerance": rel_tol,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--f002-oracle", type=Path, required=True)
    parser.add_argument("--expert", type=int, default=EXPERT_INDEX_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    # Independence guard
    forbidden = ("mlx", "pulsar_mlx_worker")
    for name in list(sys.modules):
        if any(f in name for f in forbidden):
            print("expert_oracle: must not import MLX worker modules", file=sys.stderr)
            return 2

    try:
        activation, weight, meta = load_f002_row_and_weight(args.f002_oracle, args.expert)
        doc = run_expert_oracle(args.model, args.expert, activation, weight)
        doc["input"] = {
            "source": "feature_002_ffn_norm0_row0",
            "shape": [HIDDEN],
            "dtype": "float32",
            "sha256": meta["input_row_sha256"],
            "values": activation,
        }
        doc["provenance"] = meta
        payload = json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            print("expert_oracle: refuse to overwrite existing output", file=sys.stderr)
            return 1
        args.output.write_text(payload, encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": "passed",
                    "expert_index": args.expert,
                    "weighted_sha256": doc["result"]["weighted_sha256"],
                    "routing_weight": weight,
                    "output": str(args.output),
                },
                sort_keys=True,
            )
        )
        return 0
    except ExpertOracleError as error:
        print(f"expert_oracle: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bank checkpoint-free descriptors for the already frozen eight fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


LADDER_SHA256 = "59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_lag1_correlation(values: np.ndarray) -> float:
    """Return lag-1 correlation without BLAS reduction-order variability."""
    left = tuple(float(value) for value in values[:-1])
    right = tuple(float(value) for value in values[1:])
    count = len(left)
    if count == 0:
        raise ValueError("lag-1 correlation requires at least two values")
    left_mean = math.fsum(left) / count
    right_mean = math.fsum(right) / count
    numerator = math.fsum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_energy = math.fsum((x - left_mean) ** 2 for x in left)
    right_energy = math.fsum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_energy * right_energy)
    if denominator == 0.0:
        raise ValueError("lag-1 correlation is undefined for a constant vector")
    return numerator / denominator


def build(root: Path) -> dict[str, object]:
    ladder_path = root / "docs/architecture/reviews/evidence/f017-m1-f0-input-ladder-v1.json"
    if sha256(ladder_path) != LADDER_SHA256:
        raise ValueError("frozen ladder mismatch")
    ladder = json.loads(ladder_path.read_text())
    descriptors = []
    for entry in ladder["fixtures"]:
        seed = int(entry["seed"])
        fixture_path = root / f"specs/017-rust-native-inference-runtime/fixtures/f017-m1f0-layer3-input-seed-{seed}-v1.json"
        if sha256(fixture_path) != entry["fixture_sha256"]:
            raise ValueError(f"frozen fixture mismatch for seed {seed}")
        fixture = json.loads(fixture_path.read_text())
        hidden = np.frombuffer(bytes.fromhex(fixture["state"]["hidden"]["bytes_hex"]), dtype="<f4")
        values = hidden.astype(np.float64)
        descriptors.append({
            "ordinal": int(entry["ordinal"]),
            "seed": seed,
            "fixture_sha256": entry["fixture_sha256"],
            "package_sha256": entry["package_sha256"],
            "hidden_sha256": entry["hidden_sha256"],
            "predicted_family_membership": bool(hidden.shape == (6144,) and np.isfinite(hidden).all()),
            "descriptor": {
                "shape": [int(hidden.size)],
                "dtype": "little_endian_f32",
                "mean": float(np.mean(values)),
                "standard_deviation": float(np.std(values)),
                "rms": float(np.sqrt(np.mean(values * values))),
                "minimum": float(np.min(values)),
                "maximum": float(np.max(values)),
                "zero_count": int(np.count_nonzero(hidden == 0.0)),
                "negative_zero_count": int(np.count_nonzero((hidden == 0.0) & np.signbit(hidden))),
                "finite": bool(np.isfinite(hidden).all()),
                "lag1_correlation": deterministic_lag1_correlation(values),
            },
        })
    return {
        "schema": "pulsarmlx.f017.post-v3-frozen-fixture-descriptors",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "real_payload_ledger": 57,
        "frozen_ladder_sha256": LADDER_SHA256,
        "frozen_ladder_generator_sha256": ladder["generator"]["sha256"],
        "seed_order": [item["seed"] for item in descriptors],
        "fixtures": descriptors,
        "actual_route_labels_generated": False,
        "inability_boundary": [
            "attention output and residual require the accepted real tensor package",
            "real router logits, probabilities, scores, ranking, and expert set are unknowable from fixture bytes alone",
            "fixture-specific B_pair surfaces and H=2 qualification require real route antecedents",
            "per-expert candidate routing-weight qualification requires candidate execution",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    payload = json.dumps(build(root), sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

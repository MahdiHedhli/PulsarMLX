#!/usr/bin/env python3
"""Checkpoint-free candidate families for representative M1-F0 research."""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np

WIDTH = 6144
SEED = 170_185_020


def _finish(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    rms = math.sqrt(float(np.mean(values * values, dtype=np.float64)))
    if not math.isfinite(rms) or rms == 0.0:
        raise ValueError("fixture RMS")
    return np.asarray(values / rms, dtype="<f4")


def correlated_low_rank(seed: int = SEED) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(seed))
    coordinate = np.arange(WIDTH, dtype=np.float64) / WIDTH
    values = np.zeros(WIDTH, dtype=np.float64)
    coefficients = rng.normal(0.0, 1.0, size=16)
    phases = rng.uniform(-math.pi, math.pi, size=16)
    for frequency, (coefficient, phase) in enumerate(zip(coefficients, phases, strict=True), start=1):
        values += coefficient * np.sin(2.0 * math.pi * frequency * coordinate + phase)
    values /= math.sqrt(16.0)
    values += 0.15 * rng.normal(0.0, 1.0, size=WIDTH)
    return _finish(values)


def block_ar1(seed: int = SEED + 1, rho: float = 0.85) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(seed))
    innovations = rng.normal(0.0, math.sqrt(1.0 - rho * rho), size=WIDTH)
    values = np.empty(WIDTH, dtype=np.float64)
    values[0] = innovations[0]
    for index in range(1, WIDTH):
        values[index] = rho * values[index - 1] + innovations[index]
    return _finish(values)


def describe() -> dict[str, object]:
    families = {}
    for name, values in (
        ("correlated_low_rank_spectral_v1", correlated_low_rank()),
        ("block_ar1_rho_0_85_v1", block_ar1()),
    ):
        payload = values.tobytes(order="C")
        families[name] = {
            "dtype": "lef32",
            "shape": [WIDTH],
            "sha256": hashlib.sha256(payload).hexdigest(),
            "rms": float(np.sqrt(np.mean(values.astype(np.float64) ** 2))),
            "mean": float(np.mean(values.astype(np.float64))),
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
        }
    return {
        "checkpoint_access": 0,
        "recommended": "correlated_low_rank_spectral_v1",
        "alternative": "block_ar1_rho_0_85_v1",
        "status": "RESEARCH_ONLY_NOT_SELECTED_NOT_AUTHORIZED",
        "families": families,
    }


if __name__ == "__main__":
    print(json.dumps(describe(), sort_keys=True, separators=(",", ":")))

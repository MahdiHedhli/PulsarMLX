#!/usr/bin/env python3
"""Freeze a checkpoint-independent correlated layer-3 input family.

The generator is intentionally blind to real router rows and route outcomes.
It creates a residual-like, norm-calibrated spectral/AR mixture with a fully
precommitted seed order.  Generation does not imply authorization to execute
the family against a checkpoint.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "scripts/research/generate_f017_m1f0_input.py"
SPEC = importlib.util.spec_from_file_location("f017_m1f0_base_input_post_v3", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load accepted input-state generator")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

SEEDS = tuple(range(17_017_201, 17_017_209))
SPECTRAL_FACTORS = 16
AR_RHO = 0.85
AR_MIX = 0.25
TARGET_RMS = 1.125


def hidden_state(seed: int) -> np.ndarray:
    if seed not in SEEDS:
        raise ValueError("seed is outside the precommitted correlated family")
    rng = np.random.Generator(np.random.PCG64(seed))
    coordinate = np.arange(BASE.WIDTH, dtype=np.float64) / BASE.WIDTH
    spectral = np.zeros(BASE.WIDTH, dtype=np.float64)
    coefficients = rng.normal(0.0, 1.0, size=SPECTRAL_FACTORS)
    phases = rng.uniform(-math.pi, math.pi, size=SPECTRAL_FACTORS)
    for frequency, (coefficient, phase) in enumerate(
        zip(coefficients, phases, strict=True), start=1
    ):
        spectral += coefficient * np.sin(2.0 * math.pi * frequency * coordinate + phase)
    spectral /= math.sqrt(SPECTRAL_FACTORS)

    innovations = rng.normal(0.0, math.sqrt(1.0 - AR_RHO * AR_RHO), size=BASE.WIDTH)
    ar = np.empty(BASE.WIDTH, dtype=np.float64)
    ar[0] = innovations[0]
    for index in range(1, BASE.WIDTH):
        ar[index] = AR_RHO * ar[index - 1] + innovations[index]
    values = spectral + AR_MIX * ar
    values -= float(np.mean(values, dtype=np.float64))
    rms = math.sqrt(float(np.mean(values * values, dtype=np.float64)))
    if not math.isfinite(rms) or rms == 0.0:
        raise AssertionError("invalid correlated-family RMS")
    values *= TARGET_RMS / rms
    result = np.asarray(values, dtype="<f4")
    if result.shape != (BASE.WIDTH,) or not np.isfinite(result).all():
        raise AssertionError("invalid correlated-family hidden state")
    return result


def document(seed: int) -> dict[str, object]:
    value = copy.deepcopy(BASE.document())
    hidden = hidden_state(seed).tobytes(order="C")
    value["generator"] = {
        "path": "scripts/research/generate_f017_m1f0_post_v3_correlated_family.py",
        "python": "3.13.13",
        "numpy": "2.4.5",
        "prng": "PCG64",
        "seed": seed,
        "algorithm": "spectral16_plus_ar1_rho085_mix025_rms1125_v1",
        "spectral_factors": SPECTRAL_FACTORS,
        "ar_rho": AR_RHO,
        "ar_mix": AR_MIX,
        "target_rms": TARGET_RMS,
        "checkpoint_router_rows_used": False,
        "route_outcomes_used": False,
    }
    value["state"]["hidden"].update({
        "sha256": BASE.sha256(hidden),
        "bytes_hex": hidden.hex(),
        "byte_length": len(hidden),
    })
    value["package_sha256"] = BASE.package_sha256(value)
    return value


def manifest(root: Path, fixtures: list[dict[str, object]]) -> dict[str, object]:
    if len(fixtures) != len(SEEDS):
        raise ValueError("complete correlated family required")
    entries = []
    for ordinal, (seed, fixture) in enumerate(zip(SEEDS, fixtures, strict=True)):
        if fixture["generator"]["seed"] != seed:
            raise ValueError("correlated-family seed/order mismatch")
        state = fixture["state"]
        payload = BASE.canonical_json(fixture)
        entries.append({
            "ordinal": ordinal,
            "seed": seed,
            "fixture_sha256": hashlib.sha256(payload).hexdigest(),
            "package_sha256": fixture["package_sha256"],
            "hidden_sha256": state["hidden"]["sha256"],
            "component_sha256": {
                name: component["sha256"] for name, component in state.items()
            },
        })
    return {
        "schema": "pulsarmlx.f017.m1f0-post-v3-correlated-family",
        "schema_version": "1.0.0",
        "status": "FROZEN_PLANNING_ONLY_NOT_AUTHORIZED",
        "checkpoint_access": 0,
        "real_payload_ledger": 57,
        "layer": 3,
        "position": 0,
        "dsa": "range_fill([0])",
        "family": "spectral16_plus_ar1_rho085_mix025_rms1125_v1",
        "checkpoint_independent_basis": "fixed residual-like spectral and local-correlation model; no real router rows or route outcomes",
        "generator": {
            "path": "scripts/research/generate_f017_m1f0_post_v3_correlated_family.py",
            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python": "3.13.13",
            "numpy": "2.4.5",
            "prng": "PCG64",
            "parameters": {
                "spectral_factors": SPECTRAL_FACTORS,
                "ar_rho": AR_RHO,
                "ar_mix": AR_MIX,
                "target_rms": TARGET_RMS,
            },
        },
        "seed_order": list(SEEDS),
        "fixtures": entries,
        "qualification_target": "routing-v3 exact membership plus H=2; per-expert candidate weights remain a future execution gate",
        "selection_rule": "first qualifying fixture in precommitted ordinal order",
        "execution_stopping_rule": "evaluate and bank every precommitted fixture if separately authorized",
        "banking_policy": "bank every route, full analytical retention, every failure, and empirical rate; omit no result",
        "best_of_n_selection": "FORBIDDEN",
        "post_real_observation_family_change": "FORBIDDEN",
        "real_execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    fixtures = [document(seed) for seed in SEEDS]
    outputs = [
        output_dir / f"f017-m1f0-layer3-correlated-seed-{seed}-v1.json" for seed in SEEDS
    ]
    expected = [BASE.canonical_json(value) for value in fixtures]
    manifest_bytes = BASE.canonical_json(manifest(root, fixtures))
    if args.check:
        for path, payload in zip(outputs, expected, strict=True):
            if not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"correlated-family regeneration mismatch: {path}")
        if not manifest_path.is_file() or manifest_path.read_bytes() != manifest_bytes:
            raise SystemExit("correlated-family manifest regeneration mismatch")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        for path, payload in zip(outputs, expected, strict=True):
            path.write_bytes(payload)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
    print(hashlib.sha256(manifest_bytes).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

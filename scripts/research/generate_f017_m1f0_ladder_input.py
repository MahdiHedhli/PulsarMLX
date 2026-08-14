#!/usr/bin/env python3
"""Generate precommitted ladder inputs without changing fixture-1 tooling."""

from __future__ import annotations

import argparse
import copy
import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "scripts/research/generate_f017_m1f0_input.py"
SPEC = importlib.util.spec_from_file_location("f017_m1f0_base_input", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load accepted fixture generator")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)


def hidden_state(seed: int) -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(seed))
    values = rng.normal(0.0, 1.125, BASE.WIDTH).astype("<f4")
    tiny = np.finfo(np.float32).tiny
    values[:24] = np.asarray([
        0.0, -0.0, tiny, -tiny, 2.0**-120, -(2.0**-120), 1.0e-7, -1.0e-7,
        0.25, -0.25, 0.5, -0.5, 2.0, -2.0, 8.0, -8.0, 31.75, -31.75,
        63.5, -63.5, 127.0, -127.0, 255.0, -255.0,
    ], dtype="<f4")
    values[24:64:2] = values[25:64:2]
    values[25:64:2] = np.negative(values[25:64:2], dtype=np.float32)
    if values.size != BASE.WIDTH or not np.isfinite(values).all():
        raise AssertionError("invalid generated hidden state")
    return values


def document(seed: int) -> dict[str, object]:
    value = copy.deepcopy(BASE.document())
    hidden = hidden_state(seed).tobytes(order="C")
    value["generator"] = {
        "path": "scripts/research/generate_f017_m1f0_ladder_input.py",
        "python": "3.13.13", "numpy": "2.4.5", "prng": "PCG64", "seed": seed,
        "algorithm": "normal_f32_with_layer_stress_prefix_v1",
        "derived_from_accepted_generator_sha256": "8dd7e9b8a4e4a6bfdb5a71535dabd28b4495209df326a88650b6831efc26d32d",
    }
    value["state"]["hidden"].update({  # type: ignore[index,union-attr]
        "sha256": BASE.sha256(hidden), "bytes_hex": hidden.hex(), "byte_length": len(hidden),
    })
    value["package_sha256"] = BASE.package_sha256(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = BASE.canonical_json(document(args.seed))
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            raise SystemExit("M1-F0 ladder fixture differs from deterministic regeneration")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(expected)
    print(BASE.sha256(expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

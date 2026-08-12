#!/usr/bin/env python3
"""Generate the independent, real-width M1-E activation fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

WIDTH = 6144
SEED = 17017005
SCHEMA = "pulsarmlx.f017.m1e-activation"


def activation() -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(SEED))
    values = rng.normal(0.0, 1.25, WIDTH).astype("<f4")
    # Frozen stress prefix: signed zero, subnormal-adjacent, cancellation,
    # moderate-large magnitude, and mixed sign. No non-finite value is used.
    values[:16] = np.asarray(
        [
            0.0, -0.0, np.finfo(np.float32).tiny, -np.finfo(np.float32).tiny,
            2.0 ** -120, -(2.0 ** -120), 1.0e-7, -1.0e-7,
            0.5, -0.5, 4.0, -4.0, 31.75, -31.75, 127.0, -127.0,
        ],
        dtype="<f4",
    )
    values[16:32:2] = values[17:32:2]
    values[17:32:2] *= np.float32(-1.0)
    assert values.size == WIDTH and np.isfinite(values).all()
    return values


def document() -> dict[str, object]:
    values = activation()
    raw = values.tobytes(order="C")
    return {
        "schema": SCHEMA,
        "schema_version": "1.0.0",
        "generator": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "prng": "PCG64",
            "seed": SEED,
            "algorithm": "normal_f32_with_frozen_stress_prefix_v1",
        },
        "activation": {
            "dtype": "little_endian_f32",
            "shape": [WIDTH],
            "element_count": WIDTH,
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes_hex": raw.hex(),
            "finite": True,
        },
    }


def canonical_bytes(value: dict[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = canonical_bytes(document())
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            print("M1-E activation fixture differs from deterministic regeneration", file=sys.stderr)
            return 1
        print(hashlib.sha256(expected).hexdigest())
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(expected)
    print(hashlib.sha256(expected).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

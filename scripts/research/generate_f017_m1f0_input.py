#!/usr/bin/env python3
"""Generate the independent real-width layer-3 M1-F0 entry state.

The fixture is checkpoint-free.  It deliberately starts at position zero so
GLM-DSA uses its reviewed range-fill path and no indexer-weight payload is part
of the later M1-F0 discovery budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import struct
import sys
from pathlib import Path

import numpy as np


SCHEMA = "pulsarmlx.f017.m1f0-input-state"
SCHEMA_VERSION = "1.0.0"
WIDTH = 6144
SEED = 17017006
OUTPUT_PATH = "specs/017-rust-native-inference-runtime/fixtures/f017-m1f0-layer3-input-v1.json"
HISTORICAL_RESIDUAL_SHA256 = "5c3e4ebc2d5909c5e6f556bdc00f50130b705a3fb3fe7150f4f24bf7c81bbb80"


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hidden_state() -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(SEED))
    values = rng.normal(0.0, 1.125, WIDTH).astype("<f4")
    tiny = np.finfo(np.float32).tiny
    values[:24] = np.asarray(
        [
            0.0,
            -0.0,
            tiny,
            -tiny,
            2.0**-120,
            -(2.0**-120),
            1.0e-7,
            -1.0e-7,
            0.25,
            -0.25,
            0.5,
            -0.5,
            2.0,
            -2.0,
            8.0,
            -8.0,
            31.75,
            -31.75,
            63.5,
            -63.5,
            127.0,
            -127.0,
            255.0,
            -255.0,
        ],
        dtype="<f4",
    )
    # Exact cancellation pairs without introducing non-finite values.
    values[24:64:2] = values[25:64:2]
    values[25:64:2] = np.negative(values[25:64:2], dtype=np.float32)
    if values.size != WIDTH or not np.isfinite(values).all():
        raise AssertionError("invalid generated hidden state")
    return values


def package_sha256(value: dict[str, object]) -> str:
    state = value["state"]
    assert isinstance(state, dict)
    roles = ("hidden", "query_position", "mla_cache", "dsa", "mask")
    payload = bytearray(b"pulsarmlx.f017.m1f0-input-package-v1\0")
    for role in roles:
        component = state[role]
        assert isinstance(component, dict)
        payload.extend(role.encode())
        payload.append(0)
        payload.extend(bytes.fromhex(str(component["sha256"])))
    return sha256(bytes(payload))


def document() -> dict[str, object]:
    hidden = hidden_state().tobytes(order="C")
    position = struct.pack("<Q", 0)
    empty_cache = b""
    dsa = canonical_json(
        {
            "indexer_top_k": 2048,
            "mode": "range_fill",
            "selected_positions_after_append": [0],
            "visible_count_before": 0,
            "visible_count_after": 1,
        }
    )
    mask = bytes([1])
    value: dict[str, object] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "layer": 3,
        "architecture": "glm-dsa",
        "generator": {
            "path": "scripts/research/generate_f017_m1f0_input.py",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "prng": "PCG64",
            "seed": SEED,
            "algorithm": "normal_f32_with_layer_stress_prefix_v1",
        },
        "state": {
            "hidden": {
                "encoding": "ieee754_little_endian_f32",
                "shape": [WIDTH],
                "byte_length": len(hidden),
                "sha256": sha256(hidden),
                "bytes_hex": hidden.hex(),
            },
            "query_position": {
                "encoding": "little_endian_u64",
                "value": 0,
                "byte_length": len(position),
                "sha256": sha256(position),
                "bytes_hex": position.hex(),
            },
            "mla_cache": {
                "encoding": "empty_compact_kv_cache_v1",
                "kv_lora_shape": [0, 512],
                "k_rope_shape": [0, 64],
                "byte_length": 0,
                "sha256": sha256(empty_cache),
                "bytes_hex": "",
            },
            "dsa": {
                "encoding": "canonical_json_utf8",
                "mode": "range_fill",
                "indexer_weights_required": False,
                "byte_length": len(dsa),
                "sha256": sha256(dsa),
                "bytes_hex": dsa.hex(),
            },
            "mask": {
                "encoding": "u8_visible_mask",
                "shape": [1],
                "byte_length": len(mask),
                "sha256": sha256(mask),
                "bytes_hex": mask.hex(),
            },
        },
        "historical_input_substitution_forbidden": True,
        "historical_residual_sha256": HISTORICAL_RESIDUAL_SHA256,
        "checkpoint_accessed": False,
    }
    value["package_sha256"] = package_sha256(value)
    if value["state"]["hidden"]["sha256"] == HISTORICAL_RESIDUAL_SHA256:  # type: ignore[index]
        raise AssertionError("new input unexpectedly equals historical input")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = canonical_json(document())
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != expected:
            print("M1-F0 input differs from deterministic regeneration", file=sys.stderr)
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(expected)
    print(sha256(expected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

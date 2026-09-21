from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from ggml_kquants import dequantize_row_q6_k


def _block() -> tuple[bytes, list[int], list[int]]:
    quants = [((index * 19 + 7) % 64) - 32 for index in range(256)]
    scales = [value for pair in ((i + 1, -(i + 1)) for i in range(8)) for value in pair]
    ql = bytearray(128)
    qh = bytearray(64)
    for half in range(2):
        for lane in range(32):
            base = 128 * half
            packed = [quants[base + 32 * quarter + lane] + 32 for quarter in range(4)]
            ql[64 * half + lane] = (packed[0] & 15) | ((packed[2] & 15) << 4)
            ql[64 * half + 32 + lane] = (packed[1] & 15) | ((packed[3] & 15) << 4)
            qh[32 * half + lane] = (
                (packed[0] >> 4)
                | ((packed[1] >> 4) << 2)
                | ((packed[2] >> 4) << 4)
                | ((packed[3] >> 4) << 6)
            )
    encoded = bytes(ql) + bytes(qh) + struct.pack("<16b", *scales) + struct.pack("<e", 0.5)
    return encoded, quants, scales


def test_q6_python_oracle_uses_official_low_high_nibble_lane_order() -> None:
    encoded, quants, scales = _block()
    actual = dequantize_row_q6_k(encoded)
    expected = [0.5 * scales[index // 16] * quants[index] for index in range(256)]
    assert actual == expected


def test_old_lane_swap_mutation_is_observable() -> None:
    encoded, _, _ = _block()
    correct = dequantize_row_q6_k(encoded)
    mutated = list(correct)
    mutated[32:64], mutated[64:96] = mutated[64:96], mutated[32:64]
    assert mutated != correct
    assert any(a != b for a, b in zip(mutated, correct, strict=True))

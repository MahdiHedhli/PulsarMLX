from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from iq2_xxs_tables import KSIGNS_IQ2XS
from iq3_xxs_dequant import dequantize_row_iq3_xxs
from iq3_xxs_tables import IQ3XXS_GRID


def test_iq3_two_grids_are_four_then_four_not_interleaved() -> None:
    block = bytearray(98)
    block[:2] = struct.pack("<e", 1.0)
    for group in range(8):
        for pair in range(4):
            block[2 + 8 * group + 2 * pair] = pair
            block[3 + 8 * group + 2 * pair] = pair + 17
        block[66 + 4 * group : 70 + 4 * group] = (0).to_bytes(4, "little")
    actual = dequantize_row_iq3_xxs(bytes(block))
    scale = 0.25
    signs = KSIGNS_IQ2XS[0]
    first = IQ3XXS_GRID[0].to_bytes(4, "little")
    second = IQ3XXS_GRID[17].to_bytes(4, "little")
    expected_first_pair = [
        scale * first[index] * (-1.0 if signs & (1 << index) else 1.0)
        for index in range(4)
    ] + [
        scale * second[index] * (-1.0 if signs & (1 << (4 + index)) else 1.0)
        for index in range(4)
    ]
    assert actual[:8] == expected_first_pair
    interleaved = [value for pair in zip(expected_first_pair[:4], expected_first_pair[4:], strict=True) for value in pair]
    assert actual[:8] != interleaved

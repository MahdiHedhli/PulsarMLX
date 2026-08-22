from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_oracle_primary_decoders import decode as primary_decode
from iq4_xs_dequant import dequantize_row_iq4_xs


def _block() -> bytes:
    block = bytearray(136)
    block[:2] = struct.pack("<e", 1.0)
    block[2:4] = struct.pack("<H", 0xAAAA)
    block[4:8] = b"\x11" * 4
    for group in range(8):
        for lane in range(16):
            block[8 + group * 16 + lane] = ((15 - lane) << 4) | lane
    return bytes(block)


def test_iq4_xs_matches_pinned_ggml_low_then_high_known_answer() -> None:
    authority = json.loads((ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-iq4-xs-ggml-known-answer-v1.json").read_text())
    expected = [float(value) for value in authority["expected_first_group"]["values"]]
    block = _block()
    assert primary_decode("IQ4_XS", block, 256)[:32] == expected
    assert dequantize_row_iq4_xs(block)[:32] == expected


def test_old_interleaved_iq4_xs_lane_order_is_rejected() -> None:
    correct = primary_decode("IQ4_XS", _block(), 256)[:32]
    interleaved = [value for pair in zip(correct[:16], correct[16:], strict=True) for value in pair]
    assert interleaved != correct

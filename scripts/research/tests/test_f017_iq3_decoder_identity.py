"""Cross-implementation IQ3_XXS ordering and identity regression."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts" / "research"
sys.path.insert(0, str(RESEARCH))

from iq3_xxs_dequant import (  # noqa: E402
    dequantize_blocks_iq3_xxs_numpy,
    dequantize_row_iq3_xxs,
)
from iq3_xxs_spec_decoder import decode_block_iq3_xxs_spec  # noqa: E402


FIXTURE = (
    ROOT
    / "specs/017-rust-native-inference-runtime/fixtures"
    / "f017-iq3-xxs-order-regression-v1.json"
)
CONTRACT = (
    ROOT
    / "specs/017-rust-native-inference-runtime/contracts"
    / "m1e-decoder-contract-v2.json"
)


def load_fixture() -> tuple[bytes, np.ndarray]:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    block = bytes.fromhex(document["packed_block_hex"])
    expected_bytes = b"".join(bytes.fromhex(bits) for bits in document["decoded_f32_bits"])
    assert hashlib.sha256(block).hexdigest() == document["packed_block_sha256"]
    assert hashlib.sha256(expected_bytes).hexdigest() == document["decoded_f32le_sha256"]
    return block, np.frombuffer(expected_bytes, dtype="<f4")


class IQ3DecoderIdentityTests(unittest.TestCase):
    def test_scalar_and_numpy_match_specification_bits_and_order(self) -> None:
        block, expected = load_fixture()
        third = np.asarray(decode_block_iq3_xxs_spec(block), dtype="<f4")
        scalar = np.asarray(dequantize_row_iq3_xxs(block), dtype="<f4")
        vector = dequantize_blocks_iq3_xxs_numpy(block).astype("<f4", copy=False)
        np.testing.assert_array_equal(third.view("<u4"), expected.view("<u4"))
        np.testing.assert_array_equal(scalar.view("<u4"), expected.view("<u4"))
        np.testing.assert_array_equal(vector.view("<u4"), expected.view("<u4"))

    def test_v2_contract_binds_the_corrected_real_identity_and_sources(self) -> None:
        document = json.loads(CONTRACT.read_text(encoding="utf-8"))
        iq3 = next(
            decoder for decoder in document["decoders"] if decoder["quantization"] == "IQ3_XXS"
        )
        self.assertEqual(
            iq3["logical_subgroup_order"],
            "grid_1_lanes_0_to_3_then_grid_2_lanes_0_to_3",
        )
        self.assertEqual(
            iq3["independent_source_sha256"],
            hashlib.sha256((RESEARCH / "iq3_xxs_dequant.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            iq3["third_specification_decoder_sha256"],
            hashlib.sha256((RESEARCH / "iq3_xxs_spec_decoder.py").read_bytes()).hexdigest(),
        )
        self.assertEqual(
            iq3["authorized_real_down_decoded_f32le_sha256"],
            "f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae",
        )


if __name__ == "__main__":
    unittest.main()

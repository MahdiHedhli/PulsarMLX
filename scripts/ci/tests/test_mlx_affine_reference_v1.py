"""The Python R1 reference, and the golden fixture it underwrites."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.research import mlx_affine_reference_v1 as r1

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = ROOT / "fixtures/safetensors/golden-affine-dequant-v1/golden.json"
GENERATOR = ROOT / "scripts/research/generate_golden_affine_dequant_v1.py"


class MetadataConversions(unittest.TestCase):
    def test_bf16_widening_is_exact(self):
        self.assertEqual(r1.bf16_to_float(0x3F80), 1.0)
        self.assertEqual(r1.bf16_to_float(0xBF80), -1.0)
        self.assertEqual(r1.bf16_to_float(0x0000), 0.0)

    def test_f16_widening_is_exact(self):
        self.assertEqual(r1.f16_to_float(0x3C00), 1.0)
        self.assertEqual(r1.f16_to_float(0x0001), 2.0 ** -24)
        self.assertEqual(r1.f16_to_float(0x0400), 2.0 ** -14)

    def test_bf16_rounding_is_to_nearest_even(self):
        # 1.0 + 2^-9 sits exactly halfway between two bf16 values; ties go to
        # the even one.
        halfway = r1.f32_to_float(0x3F808000)
        self.assertEqual(r1.float_to_bf16_bits(halfway), 0x3F80)
        above = r1.f32_to_float(0x3F808001)
        self.assertEqual(r1.float_to_bf16_bits(above), 0x3F81)


class Packing(unittest.TestCase):
    def test_codes_are_least_significant_bits_first(self):
        words = [0x76543210]
        self.assertEqual(
            [r1.extract_code(words, 4, index) for index in range(8)],
            [0, 1, 2, 3, 4, 5, 6, 7],
        )

    def test_codes_may_straddle_a_word_boundary(self):
        # Three bits do not divide 32, so code 10 spans words 0 and 1.
        codes = list(range(8)) * 4
        words = r1.pack_codes(codes, 3)
        self.assertEqual(len(words), 3)
        self.assertEqual([r1.extract_code(words, 3, i) for i in range(32)], codes)

    def test_packing_round_trips_at_every_admitted_width(self):
        for bits in (2, 3, 4, 6, 8):
            codes = [(index * 7 + 1) % (2 ** bits) for index in range(64)]
            words = r1.pack_codes(codes, bits)
            self.assertEqual(
                [r1.extract_code(words, bits, i) for i in range(64)], codes, bits
            )


class ShapeInvariant(unittest.TestCase):
    def test_the_mlx_invariant_is_enforced(self):
        with self.assertRaises(r1.ReferenceError):
            r1.check_shape_invariant(8, 4, 2, 64)
        r1.check_shape_invariant(8, 4, 1, 64)

    def test_geometry_mismatches_are_refused(self):
        with self.assertRaises(r1.ReferenceError):
            r1.dequantize_rows([0] * 8, [0], [0], bits=4, group_size=16,
                               rows=1, columns=64)
        with self.assertRaises(r1.ReferenceError):
            r1.dequantize_rows([0] * 7, [0], [0], bits=4, group_size=64,
                               rows=1, columns=64)


class Encoder(unittest.TestCase):
    def test_the_signed_edge_snapped_rule_keeps_zero_exact(self):
        # A group straddling zero: the larger-magnitude edge becomes the bias
        # and the scale is snapped so that edge quantizes exactly.
        values = [(index - 32) / 8.0 for index in range(64)]
        codes, scale_bits, bias_bits = r1.quantize_group(values, 4, "F32")
        scale = r1.f32_to_float(scale_bits)
        bias = r1.f32_to_float(bias_bits)
        edge = min(values) if abs(min(values)) > abs(max(values)) else max(values)
        recovered = scale * codes[values.index(edge)] + bias
        self.assertAlmostEqual(recovered, edge, places=12)
        self.assertTrue(all(0 <= code <= 15 for code in codes))

    def test_an_all_zero_group_gets_a_zero_bias(self):
        codes, scale_bits, bias_bits = r1.quantize_group([0.0] * 64, 4, "BF16")
        self.assertEqual(r1.bf16_to_float(bias_bits), 0.0)
        self.assertEqual(set(codes), {0})

    def test_round_trip_error_is_bounded_by_half_a_step(self):
        values = [((index * 37) % 101) / 10.0 - 5.0 for index in range(128)]
        words, scales, biases = r1.quantize_rows(
            values, bits=8, group_size=64, rows=2, columns=64, metadata_dtype="F32"
        )
        out = r1.dequantize_rows(words, scales, biases, bits=8, group_size=64,
                                 rows=2, columns=64, metadata_dtype="F32")
        span = max(values) - min(values)
        self.assertLess(max(abs(a - b) for a, b in zip(values, out)), span / 255.0)


class GoldenFixture(unittest.TestCase):
    def test_the_committed_fixture_checks(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["cases"], 15)

    def test_the_fixture_closes_the_gaps_w1_recorded(self):
        fixture = json.loads(GOLDEN.read_text())
        extended = fixture["extended"]
        self.assertTrue(any(case["cols"] > case["group"] for case in extended.values()))
        self.assertTrue(any(case["group"] == 128 for case in extended.values()))
        self.assertTrue(any(case["bits"] == 8 for case in extended.values()))
        self.assertTrue(
            any(case["metadata_dtype"] == "F32" for case in extended.values())
        )
        self.assertTrue(
            any(case["metadata_dtype"] == "BF16" for case in extended.values())
        )
        negative = 0
        zero_bias = 0
        for case in extended.values():
            negative += sum(1 for bits in case["scales"] if r1.f32_to_float(bits) < 0)
            zero_bias += sum(1 for bits in case["biases"] if r1.f32_to_float(bits) == 0.0)
        self.assertGreater(negative, 0, "MLX writes signed scales; the fixture must show one")
        self.assertGreater(zero_bias, 0, "the encoder's q0 == 0 branch must appear")

    def test_the_adopted_block_records_its_provenance_honestly(self):
        fixture = json.loads(GOLDEN.read_text())
        adopted = fixture["provenance"]["adopted"]
        self.assertIn("sha256", adopted)
        self.assertIn("regression baseline", adopted["authority"])
        self.assertTrue(fixture["provenance"]["extended"]["mlx_was_not_run"])


if __name__ == "__main__":
    unittest.main()

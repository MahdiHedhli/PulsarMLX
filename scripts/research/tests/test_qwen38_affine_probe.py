"""Scalar known-pattern checks; MLX execution is separately explicit."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_affine_probe import fixtures, packed_words, scalar_dequantize


class AffineProbeTests(unittest.TestCase):
    def test_known_words_and_opposite_rows(self):
        four, eight = fixtures()
        self.assertEqual(packed_words(four[2], 4)[0][0], 0x76543210)
        self.assertEqual(packed_words(four[2], 4)[1][0], 0x89ABCDEF)
        self.assertEqual(packed_words(eight[2], 8)[0][0], 0x09060300)
        self.assertEqual(packed_words(eight[2], 8)[1][0], 0xF9FBFDFF)

    def test_scalar_known_endpoints(self):
        for bits, group_size, rows, scales, biases in fixtures():
            dense = scalar_dequantize(packed_words(rows, bits), scales, biases, bits, group_size)
            self.assertEqual(len(dense), 2)
            self.assertEqual(len(dense[0]), group_size * 2)
            self.assertEqual(dense[0][0], biases[0][0])
            self.assertEqual(dense[1][0], scales[1][0] * rows[1][0] + biases[1][0])
            self.assertEqual(dense[0][group_size], scales[0][1] * rows[0][group_size] + biases[0][1])
            self.assertEqual(dense[0][-1], scales[0][1] * rows[0][-1] + biases[0][1])

    def test_rejects_bad_geometry(self):
        with self.assertRaises(ValueError):
            packed_words(((16,) * 32,), 4)
        with self.assertRaises(ValueError):
            packed_words(((1,) * 32, (1,) * 64), 4)
        with self.assertRaises(ValueError):
            scalar_dequantize(((0,),), ((1.0,),), ((0.0,),), 4, 32)


if __name__ == "__main__":
    unittest.main()

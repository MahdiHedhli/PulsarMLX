"""Verify the synthetic expectation from the original implementation round. No real model files."""
import hashlib
from pathlib import Path
import unittest

from studio017_synthetic_fixture import generate


class FrozenFixture(unittest.TestCase):
    def test_generator_matches_original_frozen_bytes(self):
        expected = (Path(__file__).resolve().parents[2] /
                    "crates/mlx-expert-mlp/src/full_flash/native-fixture-golden.json").read_bytes()
        self.assertEqual(hashlib.sha256(expected).hexdigest(),
                         "7b2d0c29963b60a8c16b5582c31b2fd960364f41f0c50f60913ffeb444dbddb5")
        self.assertEqual(generate().encode("ascii"), expected)


if __name__ == "__main__":
    unittest.main()

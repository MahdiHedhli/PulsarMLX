import importlib.util
import hashlib
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_tierb_stress.py"
SPEC = importlib.util.spec_from_file_location("f017_tierb_stress", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TierBStressOracleTests(unittest.TestCase):
    def test_committed_oracle_is_generated_without_drift(self):
        artifact_path = (
            ROOT
            / "specs/017-rust-native-inference-runtime/fixtures/f017-tier-b-stress-oracle-v1.json"
        )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        generator_sha256 = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        self.assertEqual(artifact["generator_sha256"], generator_sha256)
        self.assertEqual(
            artifact,
            MODULE.build_oracle(artifact["source_commit"], generator_sha256),
        )

    def test_oracle_is_deterministic_independent_and_complete(self):
        first = MODULE.build_oracle("0" * 40, "1" * 64)
        second = MODULE.build_oracle("0" * 40, "1" * 64)
        self.assertEqual(first, second)
        self.assertEqual(first["independence"]["classification"], "INDEPENDENT")
        self.assertFalse(first["independence"]["uses_rust_candidate"])
        self.assertFalse(first["independence"]["uses_mlx"])
        self.assertFalse(first["independence"]["uses_checkpoint"])
        self.assertEqual(len(first["cases"]), 9)
        self.assertEqual({case["shape"][0] for case in first["cases"]}, {1, 2, 4, 8, 32})

    def test_every_bound_is_finite_nonnegative_and_hashes_are_frozen(self):
        oracle = MODULE.build_oracle("0" * 40, "1" * 64)
        for case in oracle["cases"]:
            self.assertEqual(len(case["expected"]), case["shape"][0])
            self.assertEqual(len(case["absolute_bounds"]), case["shape"][0])
            self.assertTrue(all(math.isfinite(value) for value in case["expected"]))
            self.assertTrue(all(math.isfinite(value) and value >= 0.0 for value in case["absolute_bounds"]))
            self.assertEqual(len(case["matrix_sha256"]), 64)
            self.assertEqual(len(case["vector_sha256"]), 64)
            self.assertEqual(len(case["expected_sha256"]), 64)

    def test_near_tie_has_behavioral_gate(self):
        oracle = MODULE.build_oracle("0" * 40, "1" * 64)
        case = next(case for case in oracle["cases"] if case["name"] == "near_tie_rows")
        self.assertTrue(case["behavioral_selection"])
        self.assertIn(case["expected_argmax_lowest_index_tie_break"], (0, 1))


if __name__ == "__main__":
    unittest.main()

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_r11_oracle.py"
SPEC = importlib.util.spec_from_file_location("f017_r11_oracle", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class R11OracleTests(unittest.TestCase):
    def test_oracle_is_independent_deterministic_and_q4_k(self):
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        first = MODULE.build_oracle("0" * 40, generator_sha)
        second = MODULE.build_oracle("0" * 40, generator_sha)
        self.assertEqual(first, second)
        self.assertEqual(first["inputs"]["output_head"]["quantization"], "Q4_K")
        self.assertEqual(first["inputs"]["output_head"]["shape"], [16, 256])
        self.assertEqual(len(first["expected"]["top_k_ids"]), 8)
        self.assertEqual(first["numerical_contract"]["production"], "f017-production-r11-tier-b-v1")
        self.assertEqual(first["numerical_contract"]["greedy_applicability"], "applicable")
        self.assertEqual(len(first["top_k_stress_cases"]), 7)
        for case in first["top_k_stress_cases"]:
            self.assertEqual(case["expected_argmax"], case["expected_top_k_ids"][0])
        near_zero = next(case for case in first["top_k_stress_cases"] if case["name"] == "near_zero")
        self.assertEqual(near_zero["expected_top_k_ids"], [2, 1, 0, 3])
        self.assertFalse(first["independence"]["uses_rust_candidate"])
        self.assertFalse(first["independence"]["uses_mlx"])
        self.assertFalse(first["checkpoint_accessed"])

    def test_committed_oracle_regenerates_without_drift_when_present(self):
        artifact = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-r11-final-output-oracle-v1.json"
        if not artifact.exists():
            self.skipTest("fixture is frozen in the next commit")
        document = json.loads(artifact.read_text(encoding="utf-8"))
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        self.assertEqual(document, MODULE.build_oracle(document["source_commit"], generator_sha))


if __name__ == "__main__":
    unittest.main()

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_r8_oracle.py"
R7_FIXTURE = (
    ROOT
    / "specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json"
)
SPEC = importlib.util.spec_from_file_location("f017_r8_oracle", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class R8OracleTests(unittest.TestCase):
    def test_committed_oracle_is_generated_without_drift(self):
        artifact_path = (
            ROOT
            / "specs/017-rust-native-inference-runtime/fixtures/f017-r8-top8-shared-oracle-v2.json"
        )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        self.assertEqual(artifact["generator_sha256"], generator_sha)
        self.assertEqual(
            artifact,
            MODULE.build_oracle(artifact["source_commit"], generator_sha, R7_FIXTURE),
        )

    def test_oracle_is_independent_deterministic_and_complete(self):
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        first = MODULE.build_oracle("0" * 40, generator_sha, R7_FIXTURE)
        second = MODULE.build_oracle("0" * 40, generator_sha, R7_FIXTURE)
        self.assertEqual(first, second)
        self.assertEqual(first["selected_ids"], list(reversed(range(8))))
        self.assertEqual(len(first["expert_outputs"]), 8)
        self.assertEqual(len(first["shared_output"]), 32)
        self.assertEqual(len(first["aggregate_absolute_bounds"]), 32)
        self.assertEqual(bytes.fromhex(first["weights_f64_le_hex"]), MODULE._f64_bytes(first["weights"]))
        self.assertFalse(first["independence"]["uses_rust_candidate"])
        self.assertFalse(first["independence"]["uses_mlx"])
        self.assertFalse(first["independence"]["uses_checkpoint"])

    def test_router_weights_are_normalized_and_bounds_are_positive(self):
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        oracle = MODULE.build_oracle("0" * 40, generator_sha, R7_FIXTURE)
        self.assertAlmostEqual(sum(oracle["weights"]), 1.0, places=15)
        self.assertTrue(all(value > 0.0 for value in oracle["weights"]))
        self.assertTrue(all(value > 0.0 for value in oracle["aggregate_absolute_bounds"]))

    def test_v1_is_retained_as_rejected_decimal_only_transport(self):
        artifact_path = (
            ROOT
            / "specs/017-rust-native-inference-runtime/fixtures/f017-r8-top8-shared-oracle-v1.json"
        )
        self.assertEqual(
            hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "8a0ee21eb97f6b7967123bf05e908c1fca5292777db9feb02f28f9c15841a094",
        )


if __name__ == "__main__":
    unittest.main()

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_r10_oracle.py"
R9 = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-r9-mla-dsa-oracle-v1.json"
SPEC = importlib.util.spec_from_file_location("f017_r10_oracle", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class R10OracleTests(unittest.TestCase):
    def test_oracle_is_independent_deterministic_and_composed(self):
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        first = MODULE.build_oracle("0" * 40, generator_sha, R9)
        second = MODULE.build_oracle("0" * 40, generator_sha, R9)
        self.assertEqual(first, second)
        self.assertEqual(first["architecture"]["family"], "glm-dsa")
        self.assertEqual(first["architecture"]["selected_expert_count"], 8)
        self.assertEqual(len(first["expected"]["selected_ids"]), 8)
        self.assertEqual(len(first["inputs"]["routed_experts"]), 8)
        self.assertEqual(len(first["expected"]["routed_experts"]), 8)
        self.assertFalse(first["independence"]["uses_rust_candidate"])
        self.assertFalse(first["independence"]["uses_mlx"])
        self.assertFalse(first["checkpoint_accessed"])

    def test_committed_oracle_regenerates_without_drift_when_present(self):
        artifact = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-r10-complete-layer-oracle-v1.json"
        if not artifact.exists():
            self.skipTest("fixture is frozen in the next commit")
        document = json.loads(artifact.read_text(encoding="utf-8"))
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        self.assertEqual(document, MODULE.build_oracle(document["source_commit"], generator_sha, R9))


if __name__ == "__main__":
    unittest.main()

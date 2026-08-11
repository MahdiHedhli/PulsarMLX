import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_r9_oracle.py"
SPEC = importlib.util.spec_from_file_location("f017_r9_oracle", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class R9OracleTests(unittest.TestCase):
    def test_oracle_is_independent_deterministic_and_complete(self):
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        first = MODULE.build_oracle("0" * 40, generator_sha)
        second = MODULE.build_oracle("0" * 40, generator_sha)
        self.assertEqual(first, second)
        self.assertEqual(first["architecture"]["family"], "glm-dsa")
        self.assertEqual(first["architecture"]["dsa_mode"], "range_fill")
        self.assertFalse(first["architecture"]["full_indexer_active_for_p1"])
        self.assertFalse(first["independence"]["uses_rust_candidate"])
        self.assertFalse(first["independence"]["uses_mlx"])
        self.assertFalse(first["independence"]["uses_checkpoint"])
        self.assertFalse(first["checkpoint_accessed"])
        self.assertEqual(first["selection"]["selected_positions"], [0, 1, 2])
        self.assertEqual(first["dsa_indexer_fixture"]["selected_positions"], [7, 8, 11, 4])

    def test_every_float_boundary_has_canonical_f32_transport(self):
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        oracle = MODULE.build_oracle("0" * 40, generator_sha)
        records = list(oracle["inputs"].values()) + list(oracle["expected"].values())
        records.append(oracle["dsa_indexer_fixture"]["scores"])
        for record in records:
            if not isinstance(record, dict) or "f32_le_hex" not in record:
                continue
            payload = bytes.fromhex(record["f32_le_hex"])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), record["sha256"])
            self.assertEqual(len(payload), len(record["values"]) * 4)

    def test_committed_oracle_regenerates_without_drift_when_present(self):
        artifact = (
            ROOT
            / "specs/017-rust-native-inference-runtime/fixtures/f017-r9-mla-dsa-oracle-v1.json"
        )
        if not artifact.exists():
            self.skipTest("fixture is frozen in the next commit")
        document = json.loads(artifact.read_text(encoding="utf-8"))
        generator_sha = hashlib.sha256(GENERATOR.read_bytes()).hexdigest()
        self.assertEqual(document["generator_sha256"], generator_sha)
        self.assertEqual(document, MODULE.build_oracle(document["source_commit"], generator_sha))


if __name__ == "__main__":
    unittest.main()

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_r12_tiny_model.py"
FIXTURE = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model"
SPEC = importlib.util.spec_from_file_location("f017_r12_tiny_model", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class R12TinyModelTests(unittest.TestCase):
    def test_committed_multishard_fixture_regenerates_exactly(self):
        model = json.loads((FIXTURE / "model.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary)
            MODULE.generate(model["source_commit"], generated)
            for name in (*MODULE.SHARD_NAMES, "checkpoint.json", "model.json"):
                self.assertEqual((generated / name).read_bytes(), (FIXTURE / name).read_bytes(), name)

    def test_fixture_is_independent_public_safe_and_complete(self):
        model = json.loads((FIXTURE / "model.json").read_text())
        checkpoint = json.loads((FIXTURE / "checkpoint.json").read_text())
        self.assertEqual(model["generator_sha256"], hashlib.sha256(GENERATOR.read_bytes()).hexdigest())
        self.assertEqual(model["architecture"]["layer_count"], 2)
        self.assertEqual(model["architecture"]["top_k"], 8)
        self.assertEqual(model["architecture"]["shared_expert_count"], 1)
        self.assertEqual(checkpoint["tensor_count"], len(model["tensor_contracts"]))
        self.assertEqual(len(checkpoint["shards"]), 2)
        self.assertFalse(model["independence"]["uses_rust_candidate"])
        self.assertFalse(model["independence"]["uses_mlx"])
        self.assertFalse(model["checkpoint_accessed"])
        for shard in checkpoint["shards"]:
            payload = (FIXTURE / shard["filename"]).read_bytes()
            self.assertEqual(shard["size_bytes"], len(payload))
            self.assertEqual(shard["sha256"], hashlib.sha256(payload).hexdigest())


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "f017_m1d_generator", RESEARCH / "generate_f017_m1d_projection_oracle.py"
)
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
assert GENERATOR_SPEC.loader is not None
GENERATOR_SPEC.loader.exec_module(GENERATOR)

PREPARER_SPEC = importlib.util.spec_from_file_location(
    "f017_m1d_preparer", RESEARCH / "prepare_f017_m1d_real_reference.py"
)
PREPARER = importlib.util.module_from_spec(PREPARER_SPEC)
assert PREPARER_SPEC.loader is not None
PREPARER_SPEC.loader.exec_module(PREPARER)


class M1DOracleFinalizationTests(unittest.TestCase):
    def test_checkpoint_free_oracle_has_structural_finalization_not_boolean_claim(self):
        document, _ = GENERATOR.build()
        self.assertNotIn("generated_before_candidate", document["oracle"])
        finalization = document["finalization"]
        self.assertLess(
            int(finalization["preparation_started_at"]),
            int(finalization["oracle_completed_at"]),
        )
        self.assertEqual(
            finalization["completion_marker"], "oracle_finalized_sequence_0"
        )
        self.assertTrue(finalization["immutable_after_finalization"])

    def test_real_preparer_exclusive_write_is_fresh_read_only_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oracle.json"
            PREPARER.exclusive_write(path, b'{"finalized":true}\n')
            self.assertEqual(path.read_bytes(), b'{"finalized":true}\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), stat.S_IRUSR)
            with self.assertRaises(FileExistsError):
                PREPARER.exclusive_write(path, b'{"changed":true}\n')
            self.assertEqual(path.read_bytes(), b'{"finalized":true}\n')

    def test_committed_oracle_regenerates_with_same_finalization_envelope(self):
        committed = json.loads(
            (
                ROOT
                / "specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json"
            ).read_text()
        )
        generated, _ = GENERATOR.build()
        self.assertEqual(generated, committed)


if __name__ == "__main__":
    unittest.main()

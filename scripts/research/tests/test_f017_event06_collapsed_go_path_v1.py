"""Sequence 13 collapsed one-shot GO production composition tests."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

from f017_event06_collapsed_go_path_v1 import COLLAPSED_GO_FIELDS
from qualify_f017_event06_collapsed_go_path_v1 import qualify


class CollapsedGoPathV1Tests(unittest.TestCase):
    def test_real_public_composition_before_review(self) -> None:
        result = qualify()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["real_public_composition"], "PASS")
        self.assertEqual(result["fresh_process_repetitions"], 20)
        self.assertEqual(result["distinct_composition_sha_sets"], 1)
        self.assertGreaterEqual(result["mutation_campaign"]["total"], 200)
        self.assertEqual(result["mutation_campaign"]["unexpected_passes"], 0)
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["numerical_operations"], 0)

    def test_go_token_has_exactly_eight_fields(self) -> None:
        self.assertEqual(len(COLLAPSED_GO_FIELDS), 8)
        self.assertEqual(len(set(COLLAPSED_GO_FIELDS)), 8)

    def test_no_checkpoint_or_numerical_modules_in_qualifier(self) -> None:
        source = (RESEARCH / "qualify_f017_event06_collapsed_go_path_v1.py").read_text()
        self.assertNotIn("run_identity_stage(", source)
        self.assertNotIn("execute_bridge_and_bank(", source)
        self.assertNotIn("commit_production_installation(", source)

    def test_frozen_authority_bytes_unchanged(self) -> None:
        expected = {
            "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json": "a555abe0ff2aff03a693ac7313d4af17061d01766e90971d92a7ba528f4995f2",
            "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json": "4fd71e90f4184e5f2c7449eac6089f7392f1cc0d1961aecb0243f7ef723af101",
            "scripts/research/f017_corrected_oracle_primary_numerics_v3.py": "56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6",
            "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py": "c1b6b95cf2a597453aeecc43bf1d5c6df5b8488a6ac522bd01771af7b4d0e7d3",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()

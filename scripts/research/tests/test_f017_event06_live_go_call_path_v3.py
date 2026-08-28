"""Sequence 11 live-GO call-path regression tests."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

import f017_event06_production_installation_v3 as implementation
from validate_f017_event06_live_go_call_path_v3 import validate


class LiveGoCallPathV3Tests(unittest.TestCase):
    def test_generated_constants_are_current(self) -> None:
        subprocess.run(
            [
                sys.executable,
                str(RESEARCH / "generate_f017_event06_live_go_call_path_v3.py"),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_independent_qualification(self) -> None:
        result = validate()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["real_public_signatures"]["real_signatures_bound"], 12)
        self.assertEqual(result["real_public_signatures"]["real_signature_total"], 12)
        self.assertGreaterEqual(result["mutation_campaign"]["total"], 200)
        self.assertEqual(
            result["mutation_campaign"]["rejected"],
            result["mutation_campaign"]["total"],
        )
        self.assertEqual(result["unexpected_passes"], 0)
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["numerical_operations"], 0)

    def test_public_constructors_reject(self) -> None:
        for class_ in (
            implementation.LiveHumanGoV3,
            implementation.LiveOperatorApprovalV3,
            implementation.PromptBoundEventIdentityPlanV2,
            implementation.PreparedProductionInstallationV3,
            implementation.FutureGoCapabilityV3,
        ):
            with self.assertRaises(TypeError):
                class_()

    def test_historical_runtime_bytes_unchanged(self) -> None:
        expected = {
            "scripts/research/f017_event06_production_installation_v1.py": "13579b0d5b8d27e84b2eb8c5e91e85eac648798b24847169458370da670a6d6d",
            "scripts/research/f017_event06_production_installation_v2.py": "72fa96bd7bbc54baa257f18e928c179af8c1a8920e87aa132703581a0b1b7e05",
            "scripts/research/f017_corrected_oracle_primary_numerics_v2.py": "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767",
            "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py": "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791",
        }
        for relative, digest in expected.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest
            )


if __name__ == "__main__":
    unittest.main()

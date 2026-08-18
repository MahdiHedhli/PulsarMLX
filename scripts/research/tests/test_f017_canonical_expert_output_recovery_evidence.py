"""Public terminal-evidence tests for the canonical expert-output recovery."""

import unittest

from scripts.research.validate_f017_canonical_expert_output_recovery_evidence import validate


class CanonicalExpertOutputRecoveryEvidenceTests(unittest.TestCase):
    def test_public_recovery_evidence(self) -> None:
        self.assertRegex(validate(), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()

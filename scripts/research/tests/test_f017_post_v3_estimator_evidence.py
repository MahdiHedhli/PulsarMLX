from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PostV3EstimatorEvidenceTests(unittest.TestCase):
    def test_estimator_freeze_and_official_evidence_bind(self) -> None:
        contract_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-v3-membership-estimator-v1.json"
        contract = json.loads(contract_path.read_text())
        self.assertEqual(contract["status"], "FROZEN_BEFORE_OFFICIAL_SIMULATION")
        self.assertEqual(contract["post_observation_retuning"], "FORBIDDEN")
        self.assertEqual(
            sha(ROOT / contract["bindings"]["estimator_implementation_path"]),
            contract["bindings"]["estimator_implementation_sha256"],
        )
        result = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-m1f0-v3-frozen-ladder-estimate-v1.json").read_text()
        )
        self.assertEqual(result["sample_count"], 1_000_000)
        self.assertEqual(result["estimator_contract_sha256"], sha(contract_path))
        self.assertEqual(result["frozen_ladder_sha256"], contract["bindings"]["frozen_ladder_sha256"])
        self.assertEqual(result["checkpoint_access"], 0)

    def test_disposition_is_mechanically_derived_from_prefrozen_rule(self) -> None:
        result = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-m1f0-v3-frozen-ladder-estimate-v1.json").read_text()
        )
        threshold = float(result["planning_decision"]["threshold_p_any_8"])
        conservative_lower = result["scenarios"]["conservative_independent_envelope"]["engineering_H2"]["p_any_8_wilson_95"][0]
        optimistic_upper = result["scenarios"]["optimistic_strongest_observed_tightening"]["engineering_H2"]["p_any_8_wilson_95"][1]
        expected = (
            "EXISTING_FROZEN_LADDER_VIABLE"
            if conservative_lower >= threshold
            else "EXISTING_FROZEN_LADDER_NOT_VIABLE"
            if optimistic_upper < threshold
            else "ESTIMATOR_INCONCLUSIVE"
        )
        self.assertEqual(result["planning_decision"]["disposition"], expected)
        self.assertEqual(expected, "EXISTING_FROZEN_LADDER_NOT_VIABLE")

    def test_correlated_family_freeze_precedes_estimate(self) -> None:
        contract_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-v3-correlated-family-planning-v1.json"
        contract = json.loads(contract_path.read_text())
        result = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-m1f0-v3-correlated-family-estimate-v1.json").read_text()
        )
        self.assertEqual(contract["status"], "FROZEN_BEFORE_CORRELATED_FAMILY_SIMULATION")
        self.assertEqual(result["correlated_planning_contract_sha256"], sha(contract_path))
        self.assertEqual(result["correlated_family_sha256"], contract["bindings"]["family_artifact_sha256"])
        self.assertEqual(result["planning_decision"]["disposition"], "CORRELATED_FAMILY_NOT_VIABLE")
        self.assertFalse(result["actual_real_routes_predicted"])

    def test_track_summary_matches_evidence_and_keeps_ledger(self) -> None:
        summary = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-accelerated-post-v3-track1-v1.json").read_text()
        )
        self.assertEqual(summary["status"], "NEW_FAMILY_REQUIRED")
        self.assertEqual(summary["real_payload_ledger"], 57)
        self.assertEqual(summary["checkpoint_access"], 0)
        self.assertFalse(summary["frozen_random_normal"]["ladder_executed"])
        self.assertFalse(summary["future_real_access_handoff_prepared"])
        self.assertEqual(
            summary["frozen_random_normal"]["descriptor_evidence_sha256"],
            sha(
                ROOT
                / "docs/architecture/reviews/evidence/f017-m1f0-post-v3-frozen-fixture-descriptors-v1.json"
            ),
        )


if __name__ == "__main__":
    unittest.main()

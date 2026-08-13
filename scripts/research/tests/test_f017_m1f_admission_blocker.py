#!/usr/bin/env python3
"""Validate that the M1-F admission blocker stays fail-closed."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BLOCKER = ROOT / "docs/architecture/reviews/evidence/f017-m1-f-admission-blocker-v1.json"
M1E = ROOT / "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-3-v1.json"


class M1FAdmissionBlockerTests(unittest.TestCase):
    def test_blocker_preserves_scope_and_requires_operator_choice(self) -> None:
        value = json.loads(BLOCKER.read_text())
        self.assertEqual(value["status"], "BLOCKED_OPERATOR_DECISION_REQUIRED")
        self.assertEqual(value["selected_layer"], 3)
        self.assertFalse(value["real_m1f_execution_performed"])
        self.assertFalse(value["real_checkpoint_payload_accessed"])
        self.assertFalse(value["m1f_authorization_issued"])
        self.assertTrue(value["proof"]["real_attention_router_oracle_required_to_freeze_new_route"])
        self.assertFalse(value["proof"]["historical_route_transfer_to_new_input_valid"])
        self.assertEqual([choice["id"] for choice in value["operator_choices"]], ["A", "B", "C"])
        self.assertEqual(
            hashlib.sha256(M1E.read_bytes()).hexdigest(),
            value["accepted_m1e_evidence_sha256"],
        )

    def test_historical_top8_is_bound_to_its_historical_input(self) -> None:
        value = json.loads(BLOCKER.read_text())
        route = value["known_historical_route"]
        self.assertEqual(route["input_identity"], "token_embedding[9703]")
        self.assertEqual(
            route["selected_expert_ids"],
            [15, 177, 233, 41, 166, 26, 10, 152],
        )
        self.assertEqual(len(route["input_residual_sha256"]), 64)
        self.assertIn("not to the newly required independent input", route["independence_limitation"])


if __name__ == "__main__":
    unittest.main()

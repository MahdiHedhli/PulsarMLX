#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from f017_lifecycle_semantics_v5 import (
    MODEL_PATH,
    canonical_json_bytes,
    derive_outcome_obligations,
    load_json,
    simulate_trace,
    validate_model,
)


class LifecycleSemanticsV5Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = load_json(MODEL_PATH)

    def test_model_and_success_trace(self) -> None:
        result = validate_model(self.model)
        self.assertEqual(result["result"], "PASS")
        success = self.model["terminal_outcomes"]["COMPLETE_SUCCESS"]
        trace = simulate_trace(self.model, success["trace"])
        self.assertEqual(trace.state, "PACKAGE_TERMINAL_SUCCESS")
        self.assertEqual(trace.ledgers["CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER"], 1)
        self.assertEqual(trace.ledgers["CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER"], 1)
        self.assertEqual(trace.ledgers["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"], 1)

    def test_unstarted_secondary_has_no_evidence_or_delta(self) -> None:
        obligations = derive_outcome_obligations(self.model)["outcomes"]["SECONDARY_PRE_START_FAILURE"]
        self.assertEqual(obligations["package_consumer_disposition"]["secondary"], "NOT_STARTED")
        self.assertIn("secondary_receipt", obligations["forbidden_artifacts"])
        self.assertIn("secondary_terminal", obligations["forbidden_artifacts"])
        self.assertEqual(obligations["ledger_deltas"]["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"], 0)

    def test_started_primary_requires_receipt_and_terminal(self) -> None:
        obligations = derive_outcome_obligations(self.model)["outcomes"]["PRIMARY_POST_START_FAILURE"]
        self.assertIn("primary_receipt", obligations["required_artifacts"])
        self.assertIn("primary_terminal", obligations["required_artifacts"])

    def test_illegal_started_flag_fails(self) -> None:
        bad = copy.deepcopy(self.model)
        bad["terminal_outcomes"]["SECONDARY_PRE_START_FAILURE"]["secondary_started"] = True
        with self.assertRaises(ValueError):
            validate_model(bad)

    def test_path_matrix_omission_fails(self) -> None:
        bad = copy.deepcopy(self.model)
        bad["root_relation_matrix"]["pairs"].pop()
        with self.assertRaises(ValueError):
            validate_model(bad)

    def test_canonical_bytes_exact(self) -> None:
        self.assertEqual(canonical_json_bytes({"z": 1, "a": "é"}), b'{"a":"\\u00e9","z":1}\n')


if __name__ == "__main__":
    unittest.main()

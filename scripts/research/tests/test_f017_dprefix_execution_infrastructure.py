from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from scripts.research import validate_f017_dprefix_execution_infrastructure as M


class DensePrefixExecutionInfrastructureTests(unittest.TestCase):
    def test_committed_package_fails_closed_before_checkpoint_access(self) -> None:
        result = M.validate_checkpoint_free()
        self.assertEqual(result["result"], "NOT_EXECUTED_INFRASTRUCTURE")
        self.assertEqual(result["terminal_class"], "INFRASTRUCTURE")
        self.assertEqual(result["checkpoint_reads"], 0)
        self.assertFalse(result["attempt_consumed"])
        self.assertEqual(result["ledger"], 59)
        self.assertEqual(
            {item["code"] for item in result["blockers"]},
            {
                "CANDIDATE_EXECUTABLE_UNBOUND",
                "CANDIDATE_SOURCE_SURFACE_UNBOUND",
                "ORACLE_PACKAGE_NOT_INSTANTIATED",
                "ORACLE_PACKAGE_IDENTITY_ABSENT",
            },
        )

    def test_ready_requires_both_candidate_and_instantiated_oracle(self) -> None:
        config = json.loads(M.CONFIG.read_text())
        oracle = json.loads(M.ORACLE.read_text())
        config["candidate_executable_sha256"] = "a" * 64
        config["candidate_source_surface_sha256"] = "b" * 64
        oracle["status"] = "INSTANTIATED_FROZEN_BEFORE_CANDIDATE"
        oracle["instantiated_package_sha256"] = "c" * 64

        def fake_load(path):
            if path == M.CONFIG:
                return copy.deepcopy(config)
            if path == M.ORACLE:
                return copy.deepcopy(oracle)
            raise AssertionError(path)

        with patch.object(M, "load", side_effect=fake_load):
            result = M.validate_checkpoint_free()
        self.assertEqual(result, {"result": "EXECUTION_INFRASTRUCTURE_READY", "checkpoint_reads": 0, "blockers": []})

    def test_banked_nonexecution_reconciles_attempt_payload_and_evidence(self) -> None:
        self.assertEqual(
            M.validate_banked_nonexecution(),
            {
                "result": "BANKED_NONEXECUTION_RECONCILED",
                "terminal_class": "INFRASTRUCTURE",
                "payloads": 0,
                "ledger": 59,
                "checkpoint_reads": 0,
            },
        )

    def test_mutated_attempt_consumption_fails_closed(self) -> None:
        original = M.load

        def fake_load(path):
            value = copy.deepcopy(original(path))
            if path == M.ATTEMPT_LEDGER:
                value["events"][-1]["consumed"] = True
            return value

        with patch.object(M, "load", side_effect=fake_load):
            with self.assertRaisesRegex(ValueError, "attempt-ledger consumed mismatch"):
                M.validate_banked_nonexecution()

    def test_mutated_payload_count_fails_closed(self) -> None:
        original = M.load

        def fake_load(path):
            value = copy.deepcopy(original(path))
            if path == M.PAYLOAD_LEDGER:
                value["cumulative_tensor_payloads"] = 60
            return value

        with patch.object(M, "load", side_effect=fake_load):
            with self.assertRaisesRegex(ValueError, "payload-ledger cumulative total mismatch"):
                M.validate_banked_nonexecution()


if __name__ == "__main__":
    unittest.main()

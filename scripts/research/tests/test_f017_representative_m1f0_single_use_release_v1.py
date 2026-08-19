#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_m1f0_single_use_release_v1.py"
SPEC = importlib.util.spec_from_file_location("release_validator", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SingleUseReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release = MODULE.load(MODULE.RELEASE)
        cls.candidate = MODULE.load(MODULE.CANDIDATE)

    def errors(self, mutate) -> list[str]:
        document = copy.deepcopy(self.release)
        mutate(document)
        return MODULE.validate_document(document, self.candidate)

    def assert_rejected(self, mutate, code: str) -> None:
        self.assertIn(code, self.errors(mutate))

    def test_repository_artifact_passes(self) -> None:
        self.assertEqual([], MODULE.validate_paths())

    def test_mutation_matrix(self) -> None:
        cases = [
            (lambda d: d["authoritative_repository"].__setitem__("execution_code_head", "0" * 40), "AUTHORITATIVE_HEAD"),
            (lambda d: d["accepted_bindings"]["authorization_v3"].__setitem__("sha256", "0" * 64), "BINDING:authorization_v3"),
            (lambda d: d["accepted_bindings"]["independent_acceptance"].__setitem__("sha256", "0" * 64), "BINDING:independent_acceptance"),
            (lambda d: d["accepted_bindings"]["executor"].__setitem__("sha256", "0" * 64), "BINDING:executor"),
            (lambda d: d["accepted_bindings"]["release_wrapper"].__setitem__("sha256", "0" * 64), "BINDING:release_wrapper"),
            (lambda d: d["accepted_bindings"]["preopen_contract"].__setitem__("sha256", "0" * 64), "BINDING:preopen_contract"),
            (lambda d: d["accepted_bindings"]["crash_terminalizer"].__setitem__("sha256", "0" * 64), "BINDING:crash_terminalizer"),
            (lambda d: d["accepted_bindings"]["router_reuse_v2"].__setitem__("sha256", "0" * 64), "BINDING:router_reuse_v2"),
            (lambda d: d["accepted_bindings"]["reproduction_contract"].__setitem__("sha256", "0" * 64), "BINDING:reproduction_contract"),
            (lambda d: d["attention_payload_inventory"].reverse(), "INVENTORY"),
            (lambda d: d["attention_payload_inventory"][0].__setitem__("offset", 1), "INVENTORY"),
            (lambda d: d["read_contract"].__setitem__("total_packed_bytes", 1), "READ_CONTRACT"),
            (lambda d: d["checkpoint"].__setitem__("maximum_opens", 2), "SHARD_BINDING"),
            (lambda d: d["ledger"].__setitem__("start", 165), "LEDGER"),
            (lambda d: d["ledger"].__setitem__("success_after_read_phase", 174), "LEDGER"),
            (lambda d: d.__setitem__("stop_boundary", "AFTER_EXPERTS"), "STOP_BOUNDARY"),
            (lambda d: d["single_use"].__setitem__("consumed_release_can_be_reused", True), "IRREVOCABLE"),
            (lambda d: d["single_use"].pop("consumed_at"), "CONSUMPTION_BOUNDARY"),
            (lambda d: d["prohibitions"].__setitem__("retry", False), "PROHIBITIONS"),
            (lambda d: d["prohibitions"].__setitem__("resume", False), "PROHIBITIONS"),
            (lambda d: d["prohibitions"].__setitem__("second_attempt", False), "PROHIBITIONS"),
            (lambda d: d["prohibitions"].__setitem__("routed_expert_execution", False), "PROHIBITIONS"),
            (lambda d: d["checkpoint"].__setitem__("checkpoint_rereads_for_reproduction", 1), "SHARD_BINDING"),
            (lambda d: d["execution_environment"].__setitem__("numpy", "other"), "ENVIRONMENT"),
            (lambda d: d["storage_preflight"].__setitem__("required_free_bytes", 1), "STORAGE"),
            (lambda d: d["approval_boundary"].__setitem__("approval_asserted", True), "APPROVAL_BOUNDARY"),
            (lambda d: d["authorization"].__setitem__("real_event_authorized", True), "REAL_EVENT_AUTHORIZED"),
            (lambda d: d.__setitem__("release_id", "RELEASE-2"), "RELEASE_ID"),
        ]
        for mutate, code in cases:
            with self.subTest(code=code):
                self.assert_rejected(mutate, code)


if __name__ == "__main__":
    unittest.main()

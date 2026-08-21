#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import pathlib
import sys
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]
PATH = REPO / "scripts/research/validate_f017_real_payload_ledger_v2.py"
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("ledger_v2", PATH)
assert SPEC and SPEC.loader
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)


class LedgerV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = ledger.load(REPO / ledger.V2_PATH)

    def test_exact_receipt_derived_document(self):
        ledger.validate_document(REPO, self.document)

    def rejected(self, mutate):
        value = copy.deepcopy(self.document)
        mutate(value)
        with self.assertRaises(ledger.LedgerV2Error):
            ledger.validate_document(REPO, value)

    def test_terminal_count_mutation(self):
        self.rejected(lambda d: d.update(cumulative_tensor_payloads=174))

    def test_receipt_gap_mutation(self):
        self.rejected(lambda d: d["appended_events"][0]["receipt_chain"][4].update(ledger_after=172))

    def test_receipt_duplicate_mutation(self):
        self.rejected(lambda d: d["appended_events"][0]["receipt_chain"][1].update(receipt_sha256=d["appended_events"][0]["receipt_chain"][0]["receipt_sha256"]))

    def test_manual_count_invariant_mutation(self):
        self.rejected(lambda d: d["future_banking_invariant"].update(manual_independent_post_event_count=True))

    def test_payload_consumption_mutation(self):
        self.rejected(lambda d: d["reconciliation"].update(new_payload_consumption=1))

    def test_current_adapter_resolves_175(self):
        import f017_real_payload_ledger_adapter_v2 as adapter
        self.assertEqual(adapter.current_ledger(REPO), 175)


if __name__ == "__main__":
    unittest.main()

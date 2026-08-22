from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts/research/validate_f017_native_bounded_p1_d1_d2_v1.py"
SPEC = importlib.util.spec_from_file_location("d1d2", MODULE_PATH)
assert SPEC and SPEC.loader
d1d2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d1d2)


def load(relative: Path):
    return json.loads((ROOT / relative).read_text())


class D1D2Tests(unittest.TestCase):
    def setUp(self):
        self.d1 = load(d1d2.D1)
        self.d2 = load(d1d2.D2)

    def reject_d1(self, mutate):
        value = copy.deepcopy(self.d1)
        mutate(value)
        with self.assertRaises(d1d2.ValidationError):
            d1d2.validate_d1(ROOT, value)

    def reject_d2(self, mutate):
        value = copy.deepcopy(self.d2)
        mutate(value)
        with self.assertRaises(d1d2.ValidationError):
            d1d2.validate_d2(ROOT, value)

    def test_clean_contracts(self):
        d1d2.validate_d1(ROOT, self.d1)
        d1d2.validate_d2(ROOT, self.d2)

    def test_missing_counter_rejected(self):
        self.reject_d1(lambda x: x["counters"].pop())

    def test_duplicate_counter_rejected(self):
        self.reject_d1(lambda x: x["counters"].__setitem__(21, copy.deepcopy(x["counters"][0])))

    def test_counter_type_change_rejected(self):
        self.reject_d1(lambda x: x["counters"][0].__setitem__("type", "i64"))

    def test_invariant_removal_rejected(self):
        self.reject_d1(lambda x: x["counters"][0].__setitem__("post_invariant", ""))

    def test_all_zero_fixture_source_rejected(self):
        self.reject_d1(lambda x: x["implementation_rule"].__setitem__("hardcoded_zero_forbidden", False))

    def test_stale_snapshot_rejected(self):
        self.reject_d1(lambda x: x["snapshot_contract"].__setitem__("cached_snapshot_permitted", True))

    def test_historical_master_sha_change_rejected(self):
        self.reject_d2(lambda x: x["historical_master"].__setitem__("sha256", "0" * 64))

    def test_competing_master_rejected(self):
        self.reject_d2(lambda x: x["native_event_model"].__setitem__("does_not_create_competing_master", False))

    def test_page_fault_as_payload_rejected(self):
        self.reject_d2(lambda x: x["checkpoint_access_contract"].__setitem__("page_faults_as_historical_payload_units", True))

    def test_hand_entered_count_rejected(self):
        self.reject_d2(lambda x: x["native_event_model"].__setitem__("counts_derived_from_receipts_not_hand_entered", False))

    def test_alternate_checkpoint_rejected(self):
        self.reject_d2(lambda x: x["checkpoint_access_contract"].__setitem__("fallback", "ALLOWED"))

    def test_rn1_cross_process_terminalization_rejected(self):
        self.reject_d2(lambda x: x["rn1_attempt_lifecycle"].__setitem__("exception_may_terminalize_only_attempt_started_and_owned_by_this_process", False))

    def test_terminal_json_as_sole_authority_rejected(self):
        self.reject_d2(lambda x: x["rn1_attempt_lifecycle"].__setitem__("terminal_json_sole_accounting_authority", True))


if __name__ == "__main__":
    unittest.main()

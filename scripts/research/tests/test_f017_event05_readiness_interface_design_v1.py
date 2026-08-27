from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

import validate_f017_event05_readiness_interface_design_v1 as design


class Event05ReadinessInterfaceDesignTests(unittest.TestCase):
    def test_frozen_design_passes(self) -> None:
        report = design.validate_design()
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["field_count"], 56)
        self.assertEqual(report["uppercase_alias_fields"], 0)

    def test_uppercase_alias_is_rejected(self) -> None:
        contract = design.load_contract()
        mutated = copy.deepcopy(contract)
        mutated["required_fields"].append("ACTIVE_CORRECTED_ORACLE_GENERATION")
        mutated["field_count"] += 1
        with self.assertRaisesRegex(ValueError, "lower-case field vocabulary"):
            design.validate_contract(mutated)

    def test_field_count_drift_is_rejected(self) -> None:
        contract = design.load_contract()
        mutated = copy.deepcopy(contract)
        mutated["field_count"] = 55
        with self.assertRaisesRegex(ValueError, "field count"):
            design.validate_contract(mutated)

    def test_every_field_requires_one_exact_type(self) -> None:
        contract = design.load_contract()
        mutated = copy.deepcopy(contract)
        mutated["exact_types"]["exact_string_fields"].remove("exact_next_safe_action")
        with self.assertRaisesRegex(ValueError, "type exhaustiveness"):
            design.validate_contract(mutated)

    def test_mutation_floor_is_enforced(self) -> None:
        plan = json.loads(design.MUTATION_PLAN.read_text())
        plan["minimum_planned_cases"] = 199
        with self.assertRaisesRegex(ValueError, "mutation floor"):
            design.validate_mutation_plan(plan)


if __name__ == "__main__":
    unittest.main()

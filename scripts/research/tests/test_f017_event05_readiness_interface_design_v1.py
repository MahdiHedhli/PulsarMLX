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

    def test_schema_requires_exact_predicate(self) -> None:
        contract = design.load_contract()
        mutated = copy.deepcopy(contract)
        del mutated["exact_final_predicates"]["schema"]
        with self.assertRaisesRegex(ValueError, "predicate coverage"):
            design.validate_contract(mutated)

    def test_predicate_type_must_match_field_type(self) -> None:
        contract = design.load_contract()
        mutated = copy.deepcopy(contract)
        mutated["exact_final_predicates"]["event_05_executed"] = "false"
        with self.assertRaisesRegex(ValueError, "predicate type"):
            design.validate_contract(mutated)

    def test_ci_run_ids_are_strictly_positive(self) -> None:
        contract = design.load_contract()
        self.assertEqual(
            set(contract["exact_types"]["positive_integer_fields"]),
            {"full_native_run", "evidence_only_run"},
        )

    def test_mutation_floor_is_enforced(self) -> None:
        plan = json.loads(design.MUTATION_PLAN.read_text())
        plan["minimum_planned_cases"] = 199
        with self.assertRaisesRegex(ValueError, "mutation floor"):
            design.validate_mutation_plan(plan)

    def test_authority_manifest_rejects_artifact_sha_drift(self) -> None:
        manifest = json.loads(design.MANIFEST.read_text())
        mutated = copy.deepcopy(manifest)
        mutated["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "authority manifest sha"):
            design.validate_authority_manifest(mutated)

    def test_authority_manifest_binds_required_design_roles(self) -> None:
        manifest = json.loads(design.MANIFEST.read_text())
        report = design.validate_authority_manifest(manifest)
        self.assertGreaterEqual(report["binding_count"], 25)
        self.assertEqual(report["sha_mismatches"], 0)


if __name__ == "__main__":
    unittest.main()

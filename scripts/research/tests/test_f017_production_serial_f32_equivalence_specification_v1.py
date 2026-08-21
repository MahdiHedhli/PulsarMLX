#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest


REPO = pathlib.Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPO / "scripts/research/validate_f017_production_serial_f32_equivalence_specification_v1.py"
sys.path.insert(0, str(VALIDATOR_PATH.parent))
SPEC = importlib.util.spec_from_file_location("validator", VALIDATOR_PATH)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
CONTRACT = REPO / validator.CONTRACT


class MutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = validator.load_unique(CONTRACT)

    def rejected(self, mutate) -> None:
        data = copy.deepcopy(self.original)
        mutate(data)
        with self.assertRaises(validator.Invalid):
            validator.validate_contract(REPO, data)

    def stage(self, data, stage_id):
        return next(row for row in data["stage_contracts"] if row["id"] == stage_id)

    def test_unmodified_contract_accepts(self):
        validator.validate_contract(REPO, copy.deepcopy(self.original))

    def test_wrong_implementation_path(self):
        self.rejected(lambda d: d["implementation_inventory"][0].update(path="README.md"))

    def test_wrong_production_symbol(self):
        self.rejected(lambda d: d["implementation_inventory"][0].update(entry_point="helper"))

    def test_changed_accumulator_dtype(self):
        self.rejected(lambda d: self.stage(d, "routed_aggregate").update(accumulator="f64"))

    def test_changed_accumulation_order(self):
        self.rejected(lambda d: self.stage(d, "routed_aggregate").update(order="TREE"))

    def test_deleted_rounding_boundary(self):
        self.rejected(lambda d: self.stage(d, "s2_residual").update(rounding="NONE"))

    def test_weakened_byte_equivalence(self):
        self.rejected(lambda d: d["metrics"]["byte_equivalence"].update(canonical_bytes_exact=False))

    def test_enlarged_tolerance(self):
        self.rejected(lambda d: d["metrics"]["complete_layer_final"].update(max_abs_error=1.0))

    def test_removed_tolerance_justification(self):
        self.rejected(lambda d: d["metrics"]["expert_operand_bound"].update(per_coordinate=""))

    def test_route_membership_approximate(self):
        self.rejected(lambda d: d["routing_contract"].update(selected_membership="APPROXIMATE"))

    def test_route_order_removed(self):
        self.rejected(lambda d: d["routing_contract"].update(selected_order="IGNORED"))

    def test_altered_retained_sha(self):
        self.rejected(lambda d: next(r for r in d["retained_artifact_matrix"] if r["role"] == "S2").update(sha256="0" * 64))

    def test_checkpoint_decision_changed(self):
        self.rejected(lambda d: d["checkpoint_access"].update(decision="CHECKPOINT_ACCESS_REQUIRED: YES"))

    def test_ledger_changed(self):
        self.rejected(lambda d: d["accounting"].update(ledger_after=176))

    def test_nonzero_execution_counter(self):
        self.rejected(lambda d: d["accounting"].update(production_equivalence_executions=1))

    def test_unknown_classification(self):
        self.rejected(lambda d: self.stage(d, "softmax").update(relationship="CLOSE_ENOUGH"))

    def test_premature_numeric_result(self):
        self.rejected(lambda d: self.stage(d, "s2_residual").update(observed_result="NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE"))

    def test_premature_readiness(self):
        self.rejected(lambda d: d["phase_disposition"].update(readiness="READY_FOR_PRODUCTION_SERIAL_F32_EQUIVALENCE_EXECUTION_PREPARATION: YES"))

    def test_missing_stage(self):
        self.rejected(lambda d: d["stage_contracts"].pop())

    def test_bound_field_value_mismatch(self):
        self.rejected(lambda d: d["bound_field_bindings"][0].update(expected=174))

    def test_bound_field_hash_mismatch(self):
        self.rejected(lambda d: d["bound_field_bindings"][0].update(sha256="0" * 64))

    def test_executable_numeric_literal_mismatch(self):
        self.rejected(lambda d: d["executable_numeric_bindings"][0].update(expected=0.5))

    def test_executable_numeric_pattern_unresolved(self):
        self.rejected(lambda d: d["executable_numeric_bindings"][0].update(pattern="DOES_NOT_EXIST"))

    def test_master_ledger_reconciliation_removed(self):
        self.rejected(lambda d: d["master_ledger_reconciliation"].update(status="UNRESOLVED"))

    def test_rn1_weakened(self):
        self.rejected(lambda d: d["rn1_future_execution_gate"].update(next_execution_capable_generation_blocked_until_accepted=False))

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "dup.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaises(validator.Invalid):
                validator.load_unique(path)


class ReviewResultMutationTests(unittest.TestCase):
    def base(self, root: pathlib.Path):
        request = root / "request.json"
        response = root / "response.json"
        request.write_text("{}")
        response.write_text("{}")
        return {
            "schema": "pulsarmlx.f017.production-serial-f32-equivalence-independent-review-result",
            "reviewer_model": "claude-fable-5",
            "verdict": "ACCEPT",
            "blocking_findings": 0,
            "non_blocking_required_findings": 0,
            "reviewed_branch": "feat/017-real-checkpoint-runner",
            "reviewed_head": "a" * 40,
            "reviewer_track_or_invocation_identity": "test-track",
            "reviewed_artifact_hashes": {"contract": "a" * 64},
            "reviewer_tests": ["test"],
            "findings": [],
            "finding_to_fix_mapping": [],
            "exact_request": {"path": str(request.relative_to(REPO)) if request.is_relative_to(REPO) else str(request), "sha256": validator.sha256(request)},
            "exact_response": {"path": str(response.relative_to(REPO)) if response.is_relative_to(REPO) else str(response), "sha256": validator.sha256(response)},
            "defense_in_depth_dispositions": [],
        }

    def test_reviewer_substitution_rejected(self):
        with tempfile.TemporaryDirectory(dir=REPO) as td:
            data = self.base(pathlib.Path(td)); data["reviewer_model"] = "another-model"
            with self.assertRaises(validator.Invalid): validator.validate_review(REPO, write_result(pathlib.Path(td), data))

    def test_blocking_accept_rejected(self):
        with tempfile.TemporaryDirectory(dir=REPO) as td:
            data = self.base(pathlib.Path(td)); data["blocking_findings"] = 1
            with self.assertRaises(validator.Invalid): validator.validate_review(REPO, write_result(pathlib.Path(td), data))

    def test_required_accept_rejected(self):
        with tempfile.TemporaryDirectory(dir=REPO) as td:
            data = self.base(pathlib.Path(td)); data["non_blocking_required_findings"] = 1
            with self.assertRaises(validator.Invalid): validator.validate_review(REPO, write_result(pathlib.Path(td), data))

    def test_unbanked_or_changed_response_rejected(self):
        with tempfile.TemporaryDirectory(dir=REPO) as td:
            root = pathlib.Path(td); data = self.base(root)
            (root / "response.json").write_text('{"changed":true}')
            with self.assertRaises(validator.Invalid): validator.validate_review(REPO, write_result(root, data))


def write_result(root: pathlib.Path, data):
    path = root / "result.json"
    path.write_text(json.dumps(data))
    return path


if __name__ == "__main__":
    unittest.main()

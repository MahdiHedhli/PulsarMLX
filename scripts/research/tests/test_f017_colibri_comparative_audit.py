from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research import f017_colibri_comparative_audit as audit


ROOT = Path(__file__).resolve().parents[3]


class ColibriComparativeAuditTests(unittest.TestCase):
    def test_banked_machine_artifacts_regenerate_exactly(self) -> None:
        values = {
            "docs/architecture/reviews/evidence/f017-colibri-comparative-audit-v1.json": audit.audit_value(),
            "docs/architecture/reviews/evidence/f017-colibri-metal-risk-register-v1.json": audit.risk_register_value(),
            "docs/architecture/reviews/evidence/f017-colibri-adoption-candidates-v1.json": audit.adoption_candidates_value(),
            "specs/017-rust-native-inference-runtime/contracts/f017-decoded-tensor-reuse-v2-use-case-amendment-v1.json": audit.reuse_amendment_value(),
        }
        for relative, value in values.items():
            self.assertEqual((ROOT / relative).read_bytes(), audit.canonical_json_bytes(value), relative)

    def test_pin_license_and_no_copy_are_explicit(self) -> None:
        value = audit.audit_value()
        self.assertEqual(value["pinned_commit"], "6546cdde7296f28771e2ba1a1d7c1d4b0cb550aa")
        self.assertEqual(value["pinned_tree"], "bc52bec7cf224d641318c68e5ef7d6a5e3489ef0")
        self.assertEqual(value["license"]["spdx"], "Apache-2.0")
        self.assertFalse(value["no_copy_declaration"]["external_source_copied"])
        self.assertFalse(value["no_copy_declaration"]["external_runtime_dependency"])
        self.assertFalse(value["no_copy_declaration"]["external_submodule"])
        self.assertEqual(len(value["file_hashes"]), 12)

    def test_source_verifier_rejects_missing_or_mutated_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "git checkout"):
                audit.verify_colibri_source(root)
            (root / ".git").mkdir()
            for relative in audit.FILE_HASHES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "file mismatch"):
                audit.verify_colibri_source(root)

    def test_use_case_matrix_is_complete_and_requires_separation(self) -> None:
        matrix = audit.reuse_use_case_matrix()
        self.assertEqual(len(matrix), 7)
        self.assertEqual(len({item["use_case"] for item in matrix}), 7)
        by_case = {item["use_case"]: item["policy"] for item in matrix}
        self.assertEqual(by_case["multi-fixture oracle-only route analysis"], "REUSE_SAFE_FOR_ORACLE_ONLY")
        self.assertEqual(by_case["Q4_K/Q6_K decoder qualification"], "REUSE_PROHIBITED")
        self.assertEqual(by_case["dense-prefix production candidate"], "SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED")
        self.assertEqual(audit.reuse_amendment_value()["overall_disposition"], "SEPARATE_PACKAGES_REQUIRED")

    def test_f32_accumulation_order_is_numerically_observable(self) -> None:
        terms = [100_000_000.0, -100_000_000.0, 1.0]
        serial = audit.reduce_f32(terms, [0, 1, 2])
        reordered = audit.reduce_f32(terms, [0, 2, 1])
        self.assertEqual(serial, 1.0)
        self.assertEqual(reordered, 0.0)
        with self.assertRaisesRegex(ValueError, "permutation"):
            audit.reduce_f32(terms, [0, 0, 1])

    def test_top2_margin_retention_and_tie_policy(self) -> None:
        tied = audit.top2_margin([1.0, 3.0, 3.0, 2.0])
        self.assertEqual(tied["top1_id"], 1)
        self.assertEqual(tied["top2_id"], 2)
        self.assertEqual(tied["margin"], 0.0)
        with self.assertRaises(ValueError):
            audit.top2_margin([0.0, float("nan")])

    def test_dispatch_threshold_transition_and_near_tie_divergence(self) -> None:
        reference = [0.0, 1.000001, 1.0]
        candidate = [0.0, 1.0, 1.000001]
        below = audit.near_tie_transition_record(reference, reference, 15, 16)
        edge = audit.near_tie_transition_record(reference, candidate, 16, 16)
        above = audit.near_tie_transition_record(reference, candidate, 17, 16)
        for record in (below, edge, above):
            audit.validate_near_tie_record(record)
        self.assertEqual(below["path_class"], "BELOW_THRESHOLD")
        self.assertFalse(below["token_diverged"])
        self.assertEqual(edge["path_class"], "AT_OR_ABOVE_THRESHOLD")
        self.assertTrue(edge["token_diverged"])
        self.assertTrue(above["token_diverged"])

    def test_near_tie_summary_mutations_fail_closed(self) -> None:
        record = audit.near_tie_transition_record([0.0, 2.0, 1.999], [0.0, 1.999, 2.0], 16, 16)
        mutations = []
        missing = copy.deepcopy(record)
        del missing["reference"]["margin"]
        mutations.append(missing)
        wrong_path = copy.deepcopy(record)
        wrong_path["path_class"] = "BELOW_THRESHOLD"
        mutations.append(wrong_path)
        wrong_summary = copy.deepcopy(record)
        wrong_summary["token_diverged"] = False
        mutations.append(wrong_summary)
        nonfinite = copy.deepcopy(record)
        nonfinite["candidate"]["margin"] = float("inf")
        mutations.append(nonfinite)
        for mutation in mutations:
            with self.assertRaises(ValueError):
                audit.validate_near_tie_record(mutation)

    def test_dispatch_reconciliation_exposes_silent_no_work(self) -> None:
        no_work = {
            "backend_announced": True,
            "eligible_operations": 3,
            "native_dispatches": 0,
            "format_refusals": 3,
            "fallbacks": 0,
            "backend_errors": 0,
            "unclassified_no_dispatch": 0,
        }
        self.assertEqual(audit.reconcile_dispatch_evidence(no_work), "BACKEND_AVAILABLE_BUT_NO_NATIVE_WORK")
        active = dict(no_work, native_dispatches=3, format_refusals=0)
        self.assertEqual(audit.reconcile_dispatch_evidence(active), "RECONCILED")
        unaccounted = dict(no_work, format_refusals=2)
        with self.assertRaisesRegex(ValueError, "reconcile"):
            audit.reconcile_dispatch_evidence(unaccounted)
        hidden = dict(no_work, unclassified_no_dispatch=1)
        with self.assertRaisesRegex(ValueError, "unclassified"):
            audit.reconcile_dispatch_evidence(hidden)

    def test_quant_formats_are_not_used_as_gguf_oracles(self) -> None:
        compatibility = audit.audit_value()["format_compatibility"]
        self.assertFalse(compatibility["formal_equivalence"])
        self.assertEqual(compatibility["decoder_oracle_reuse"], "PROHIBITED")
        self.assertTrue(compatibility["algorithmic_lessons_only"])
        rejected = audit.adoption_candidates_value()["rejected"]
        self.assertIn("Colibrì output as Q4_K/Q6_K oracle", {item["candidate"] for item in rejected})

    def test_issue_622_and_silent_dispatch_issue_are_bound(self) -> None:
        issues = {item["number"]: item for item in audit.ISSUES}
        self.assertEqual(issues[622]["state"], "OPEN")
        self.assertEqual(issues[622]["body_sha256"], "34bfb247b7e997d5e5229737f1bb275e3614d4be37632a843d112f9b3583735e")
        self.assertEqual(issues[813]["state"], "OPEN")
        risk_ids = {item["id"] for item in audit.risk_register_value()["risks"]}
        self.assertIn("C-METAL-001", risk_ids)
        self.assertIn("C-METAL-002", risk_ids)

    def test_public_artifacts_are_path_safe_and_ledger_stable(self) -> None:
        for value in (audit.audit_value(), audit.risk_register_value(), audit.adoption_candidates_value(), audit.reuse_amendment_value()):
            encoded = audit.canonical_json_bytes(value).decode()
            self.assertNotIn("/Users/", encoded)
            self.assertNotIn("/tmp/", encoded)
            self.assertEqual(value["real_checkpoint_access"], 0)
            self.assertEqual(value["ledger"], 57)


if __name__ == "__main__":
    unittest.main()

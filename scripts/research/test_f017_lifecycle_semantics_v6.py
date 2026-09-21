#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import unittest

from f017_lifecycle_semantics_v6 import (
    MODEL_PATH,
    canonical_json_bytes,
    derive_outcome_obligations,
    load_json,
    simulate_trace,
    strict_json_bytes,
    validate_model,
)
from validate_f017_lifecycle_semantic_authority_v6 import (
    MANIFEST_PATH,
    PATHS,
    validate,
    validate_bundle,
    validate_semantics,
)


class LifecycleSemanticsV6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = load_json(MODEL_PATH)

    def test_model_and_success_trace(self) -> None:
        result = validate_model(self.model)
        self.assertEqual(result["result"], "PASS")
        success = self.model["terminal_branches"]["COMPLETE_SUCCESS"]
        trace = simulate_trace(self.model, success["trace"])
        self.assertEqual(trace.state, "PACKAGE_TERMINAL_SUCCESS")
        self.assertEqual(trace.ledgers["CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER"], 1)
        self.assertEqual(trace.ledgers["CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER"], 1)
        self.assertEqual(trace.ledgers["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"], 1)

    def test_unstarted_secondary_has_no_evidence_or_delta(self) -> None:
        obligations = derive_outcome_obligations(self.model)["variants"]["TERMINAL::SECONDARY_PRE_START_FAILURE"]
        self.assertEqual(obligations["package_consumer_disposition"]["secondary"], "NOT_STARTED")
        self.assertIn("secondary_receipt", obligations["forbidden_artifacts"])
        self.assertIn("secondary_terminal", obligations["forbidden_artifacts"])
        self.assertEqual(obligations["ledger_deltas"]["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"], 0)

    def test_started_primary_requires_receipt_and_terminal(self) -> None:
        obligations = derive_outcome_obligations(self.model)["variants"]["TERMINAL::PRIMARY_POST_START_FAILURE"]
        self.assertIn("primary_receipt", obligations["required_artifacts"])
        self.assertIn("primary_terminal", obligations["required_artifacts"])

    def test_illegal_started_flag_fails(self) -> None:
        bad = copy.deepcopy(self.model)
        bad["terminal_branches"]["SECONDARY_PRE_START_FAILURE"]["secondary_started"] = True
        with self.assertRaises(ValueError):
            validate_model(bad)

    def test_path_matrix_omission_fails(self) -> None:
        bad = copy.deepcopy(self.model)
        bad["root_relation_matrix"]["pairs"].pop()
        with self.assertRaises(ValueError):
            validate_model(bad)

    def test_canonical_bytes_exact(self) -> None:
        self.assertEqual(canonical_json_bytes({"z": 1, "a": "é"}), b'{"a":"\\u00e9","z":1}\n')
        for invalid in (b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'\xef\xbb\xbf{}\n', b'{}', b'{}\n\n'):
            with self.assertRaises(ValueError):
                strict_json_bytes(invalid, require_canonical=True)

    def test_failure_variants_follow_actual_branch_source(self) -> None:
        variants = {
            item["failed_transition"]: item
            for item in derive_outcome_obligations(self.model)["variants"].values()
            if item["failed_transition"] is not None
        }
        install = variants["F06_INSTALLATION_FAILURE"]
        self.assertEqual(install["state_reached"], "SECONDARY_CANDIDATE_VALIDATED")
        self.assertNotIn("installed_authorization", install["required_artifacts"])
        pre_primary = variants["T17_CLOSE_PRE_PRIMARY_FAILURE"]
        self.assertEqual(pre_primary["ledger_deltas"]["CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER"], 0)
        self.assertEqual(pre_primary["ledger_deltas"]["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"], 0)

    def test_terminal_artifact_paths_are_satisfiable(self) -> None:
        outcome = self.model["terminal_branches"]["COMPLETE_SUCCESS"]
        trace = simulate_trace(self.model, outcome["trace"])
        paths = dict(trace.path_states)
        for artifact in ("primary_terminal", "secondary_terminal", "comparison_terminal", "package_terminal"):
            self.assertEqual(paths[f"ARTIFACT::{artifact}"], "MUST_EXIST_REGULAR_FILE")
        self.assertEqual(paths["ARTIFACT::candidate_authorization"], "MUST_NOT_EXIST")

    def test_independent_anchor_rejects_coordinated_model_drift(self) -> None:
        bad = copy.deepcopy(self.model)
        bad["authorization_document"]["pinned_values"]["package_retries"] = 1
        with self.assertRaises(ValueError):
            validate_semantics(bad)

    def test_authorization_layout_is_exact_and_non_circular(self) -> None:
        documents = {name: load_json(path) for name, path in PATHS.items()}
        validate_bundle(self.model, documents)
        schemas = documents["schemas"]["artifacts"]
        candidate = schemas["candidate_authorization"]
        installed = schemas["installed_authorization"]
        self.assertEqual(candidate["identity_paths"], installed["identity_paths"])
        self.assertNotIn("candidate_sha256", candidate["identity_paths"])
        self.assertNotIn("primary_candidate_validation_report_sha256", candidate["identity_paths"])
        self.assertFalse(any(path.startswith("$.bindings") for path in candidate["identity_paths"].values()))

    def test_same_transition_sha_bindings_follow_declared_bank_order(self) -> None:
        matrix = load_json(PATHS["matrix"])
        rows = {row["identity"]: row["cells"] for row in matrix["rows"]}
        self.assertEqual(rows["package_ledger_entry_sha256"]["package_durable_start"]["required_outcomes"], [])
        self.assertTrue(rows["package_durable_start_sha256"]["package_ledger_entry"]["required_outcomes"])
        self.assertEqual(rows["primary_terminal_sha256"]["primary_receipt"]["required_outcomes"], [])
        self.assertTrue(rows["primary_receipt_sha256"]["primary_terminal"]["required_outcomes"])

    def test_every_transition_follows_declared_bank_order_for_every_trace(self) -> None:
        matrix = load_json(PATHS["matrix"])
        rows = {row["identity"]: row["cells"] for row in matrix["rows"]}
        outcomes = derive_outcome_obligations(self.model)["variants"]
        for transition in self.model["transitions"]:
            applicable = {
                name for name, obligation in outcomes.items()
                if transition["id"] in obligation["trace"]
            }
            ordered = transition["artifacts_created"]
            for index, earlier in enumerate(ordered):
                earlier_sha = self.model["artifact_self_sha_identities"][earlier]
                for later in ordered[index + 1:]:
                    later_sha = self.model["artifact_self_sha_identities"][later]
                    self.assertTrue(applicable.issubset(rows[earlier_sha][later]["required_outcomes"]))
                    self.assertTrue(applicable.isdisjoint(rows[later_sha][earlier]["required_outcomes"]))

    def test_generated_registry_and_matrix_schema_ids_are_exact(self) -> None:
        self.assertEqual(load_json(PATHS["registry"])["schema"], "pulsarmlx.f017.corrected-oracle-lifecycle-identity-registry/6.0.0")
        self.assertEqual(load_json(PATHS["matrix"])["schema"], "pulsarmlx.f017.corrected-oracle-lifecycle-binding-matrix/6.0.0")

    def test_failure_variant_preserves_exact_durable_prefix(self) -> None:
        variants = derive_outcome_obligations(self.model)["variants"]
        after_install = variants["FAILED::T07_BANK_INSTALL_RECEIPT"]
        before_install = variants["FAILED::T06_INSTALL_AUTHORIZATION"]
        self.assertIn("installed_authorization", after_install["required_artifacts"])
        self.assertNotIn("candidate_authorization", after_install["required_artifacts"])
        self.assertIn("candidate_authorization", before_install["required_artifacts"])
        self.assertNotIn("installed_authorization", before_install["required_artifacts"])

    def test_payload_binding_duplicates_have_exact_equality(self) -> None:
        schemas = load_json(PATHS["schemas"])["artifacts"]
        self.assertEqual(
            schemas["installation_receipt"]["payload_binding_equality"]["candidate_sha256"],
            "$.bindings.candidate_sha256",
        )
        self.assertEqual(
            schemas["primary_terminal"]["payload_binding_equality"]["primary_receipt_sha256"],
            "$.bindings.primary_receipt_sha256",
        )

    def test_validator_is_import_independent(self) -> None:
        validator = MODEL_PATH.parents[3] / "scripts/research/validate_f017_lifecycle_semantic_authority_v6.py"
        tree = ast.parse(validator.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertFalse(any("lifecycle_semantics" in name or "generate_f017" in name for name in imported))

    def test_full_byte_anchors_and_semantic_columns(self) -> None:
        self.assertTrue(MANIFEST_PATH.is_file())
        result = validate()
        self.assertEqual(result["whole_model_byte_anchor"], "PASS")
        self.assertEqual(result["registry_matrix_byte_anchors"], "PASS")
        self.assertEqual(result["semantic_columns_exact"], "PASS")


if __name__ == "__main__":
    unittest.main()

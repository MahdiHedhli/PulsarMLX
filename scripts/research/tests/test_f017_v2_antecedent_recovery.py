from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECOVERY = load("f017_v2_recovery", "scripts/research/f017_v2_antecedent_recovery.py")
PREPARE = load("f017_v2_recovery_prepare", "scripts/research/prepare_f017_v2_antecedent_recovery.py")
SUMMARY_VALIDATOR = load(
    "f017_v2_summary_integrity",
    "scripts/research/validate_f017_v2_summary_integrity.py",
)


class V2AntecedentRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        cls.config = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-execution-config-v1.json").read_text()
        )
        # The immutable reviewed config correctly binds the pre-event ledger at
        # 45. For semantic mutation tests after the accepted event, substitute
        # only the current append-only ledger hash so validation reaches the
        # field under test; the reviewed config artifact itself is unchanged.
        ledger = ROOT / cls.config["accepted_bindings"]["real_payload_ledger"]["symbolic_path"]
        cls.config["accepted_bindings"]["real_payload_ledger"]["sha256"] = hashlib.sha256(ledger.read_bytes()).hexdigest()
        validator = ROOT / cls.config["contracts"]["recovery_validator"]["symbolic_path"]
        cls.config["contracts"]["recovery_validator"]["sha256"] = hashlib.sha256(validator.read_bytes()).hexdigest()
        cls.raw_result_path = (
            ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json"
        )
        cls.raw_result = json.loads(cls.raw_result_path.read_text())
        cls.banked_surface = cls.raw_result["antecedent_retention"]["pairwise_surface"]

    def test_banked_surface_reproduces_first_failure_instead_of_global_minimum(self):
        raw_summary = self.raw_result["retrospective_v2"]
        self.assertEqual(
            self.banked_surface["adjacent_selected_pair_bounds"][0]["selected"], 166
        )
        self.assertEqual(
            self.banked_surface["adjacent_selected_pair_bounds"][0]["challenger"], 78
        )
        self.assertAlmostEqual(raw_summary["minimum_mathematical_safety_factor"], 0.6435667308079595)

        derived = RECOVERY.derive_pairwise_summary(self.banked_surface)
        self.assertEqual(derived["ordered"]["minimum_pair"]["selected"], 233)
        self.assertEqual(derived["ordered"]["minimum_pair"]["challenger"], 177)
        self.assertEqual(
            derived["ordered"]["minimum_mathematical_safety_factor"],
            0.22551544432236478,
        )

    def test_banked_surface_separates_route_set_from_ordered_route(self):
        self.assertFalse(self.raw_result["retrospective_v2"]["route_set_stable"])
        derived = RECOVERY.derive_pairwise_summary(self.banked_surface)
        self.assertTrue(derived["route_set_stable"])
        self.assertFalse(derived["route_order_stable"])
        self.assertEqual(derived["overall_mathematical_classification"], "NOT_MATHEMATICALLY_STABLE")

    def test_banked_recovery_detail_derives_authoritative_expected_summary(self):
        derived = RECOVERY.derive_pairwise_summary(self.banked_surface)
        membership = derived["membership"]
        ordered = derived["ordered"]
        self.assertEqual(
            (membership["minimum_pair"]["selected"], membership["minimum_pair"]["challenger"]),
            (177, 98),
        )
        self.assertEqual(membership["minimum_mathematical_safety_factor"], 1.2497550469932908)
        self.assertTrue(membership["mathematically_stable"])
        self.assertFalse(membership["engineering_headroom"])
        self.assertEqual(
            (ordered["minimum_pair"]["selected"], ordered["minimum_pair"]["challenger"]),
            (233, 177),
        )
        self.assertEqual(ordered["minimum_mathematical_safety_factor"], 0.22551544432236478)
        self.assertEqual(ordered["minimum_engineering_safety_factor"], 0.11275772216118239)
        self.assertFalse(ordered["mathematically_stable"])
        self.assertTrue(derived["route_set_stable"])
        self.assertFalse(derived["route_order_stable"])
        self.assertEqual(derived["overall_mathematical_classification"], "NOT_MATHEMATICALLY_STABLE")
        self.assertEqual(derived["overall_engineering_classification"], "NO_ENGINEERING_HEADROOM")

    def test_historical_raw_recovery_artifact_is_byte_immutable(self):
        self.assertEqual(
            hashlib.sha256(self.raw_result_path.read_bytes()).hexdigest(),
            "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a",
        )

    def test_checkpoint_free_validator_accepts_authoritative_banked_summary(self):
        result = SUMMARY_VALIDATOR.validate(ROOT)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["detail_records_validated"], 1991)
        self.assertTrue(result["route_set_stable"])
        self.assertFalse(result["route_order_stable"])
        self.assertEqual(result["checkpoint_access"], 0)

    def test_preparation_refuses_post_execution_ledger(self):
        with self.assertRaisesRegex(ValueError, "current ledger is not 45"):
            PREPARE.build_config(ROOT, self.head)

    def test_config_is_unexecuted_and_exactly_twelve_identity_bound_tensors(self):
        self.assertEqual(self.config["status"], "NOT_AUTHORIZED_NOT_EXECUTED")
        self.assertFalse(self.config["source_identities"]["authorization_issued"])
        self.assertEqual([item["name"] for item in self.config["tensor_allowlist"]], RECOVERY.EXPECTED_NAMES)
        self.assertEqual(sum(item["packed_length"] for item in self.config["tensor_allowlist"]), 139217920)
        self.assertEqual(sum(item["decoded_length"] for item in self.config["tensor_allowlist"]), 666430464)

    def test_no_new_route_and_no_attempt_consumption_are_fail_closed(self):
        for field in ("new_route_discovery", "route_attempt_consumed", "accepted_route_reclassification", "historical_v1_reclassification"):
            mutated = copy.deepcopy(self.config)
            mutated["semantics"][field] = True
            with self.assertRaisesRegex(ValueError, "no-new-route"):
                RECOVERY.validate_document(ROOT, mutated, verify_git=False)

    def test_access_and_identity_mutations_fail_closed(self):
        cases = []
        packed = copy.deepcopy(self.config)
        packed["tensor_allowlist"][0]["packed_sha256"] = "0" * 64
        cases.append(packed)
        decoded = copy.deepcopy(self.config)
        decoded["tensor_allowlist"][1]["decoded_sha256"] = "f" * 63
        cases.append(decoded)
        extra = copy.deepcopy(self.config)
        extra["tensor_allowlist"].append({"name": "blk.3.ffn_gate_exps.weight#166"})
        cases.append(extra)
        budget = copy.deepcopy(self.config)
        budget["access_budget"]["tensor_payloads"] = 13
        cases.append(budget)
        for item in cases:
            with self.assertRaises(ValueError):
                RECOVERY.validate_document(ROOT, item, verify_git=False)

    def test_every_accepted_output_gate_and_stale_contract_fail_closed(self):
        for field in (
            "attention_residual_sha256", "router_normalized_input_sha256",
            "router_scores_sha256", "ranking_sha256", "routing_weights_sha256",
        ):
            mutated = copy.deepcopy(self.config)
            mutated["expected_identities"][field] = "0" * 64
            with self.assertRaises(ValueError):
                RECOVERY.validate_document(ROOT, mutated, verify_git=False)
        mutated = copy.deepcopy(self.config)
        mutated["expected_identities"]["top8_ids"][1:3] = reversed(mutated["expected_identities"]["top8_ids"][1:3])
        with self.assertRaises(ValueError):
            RECOVERY.validate_document(ROOT, mutated, verify_git=False)
        mutated = copy.deepcopy(self.config)
        mutated["contracts"]["route_stability_v2"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "stale binding"):
            RECOVERY.validate_document(ROOT, mutated, verify_git=False)

    def test_future_execution_requires_exact_separate_authorization(self):
        config_sha = "d" * 64
        expected = {
            "schema": "pulsarmlx.f017.v2-antecedent-recovery-authorization",
            "schema_version": "1.0.0",
            "status": "AUTHORIZED_FOR_EXACTLY_ONE_V2_ANTECEDENT_RECOVERY_NOT_EXECUTED",
            "execution_config_sha256": config_sha,
            "tooling_commit_sha": self.config["source_identities"]["tooling_commit_sha"],
            "tooling_tree_oid": self.config["source_identities"]["tooling_tree_oid"],
            "accepted_route_sha256": self.config["accepted_bindings"]["route"]["sha256"],
            "retention_manifest_sha256": self.config["retention"]["manifest_sha256"],
            "payload_budget": self.config["access_budget"],
            "new_route_discovery": False,
            "route_attempt_consumed": False,
            "m1_f_authorized": False,
            "q6_k_qualification_authorized": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authorization.json"
            raw = RECOVERY.canonical_json(expected)
            path.write_bytes(raw)
            RECOVERY.validate_execution_authorization(self.config, config_sha, path, hashlib.sha256(raw).hexdigest())
            expected["route_attempt_consumed"] = True
            raw = RECOVERY.canonical_json(expected)
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "authorization binding"):
                RECOVERY.validate_execution_authorization(self.config, config_sha, path, hashlib.sha256(raw).hexdigest())

    def test_retention_surface_requires_1984_membership_and_7_order_bounds(self):
        result = RECOVERY.synthetic_recovery(ROOT)
        RECOVERY.validate_synthetic_result(result)
        surface = result["pairwise_surface"]
        self.assertEqual(surface["membership_pair_count"], 1984)
        self.assertEqual(surface["adjacent_selected_pair_count"], 7)
        self.assertEqual(len(surface["selected_unselected_pair_bounds"]), 1984)
        self.assertEqual(len(surface["adjacent_selected_pair_bounds"]), 7)
        self.assertEqual(result["payload_hashes_before"], result["payload_hashes_after"])
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertFalse(result["route_attempt_consumed"])
        self.assertFalse(result["new_route_discovery"])

    def test_private_antecedent_descriptors_are_immutable_and_path_safe(self):
        descriptors = RECOVERY.synthetic_recovery(ROOT)["private_antecedents"]
        expected = {
            "attention_residual", "router_normalized_input", "router_matrix", "ffn_norm_weight",
            "rmsnorm_decomposition_inputs", "non_radial_component_bounds",
            "router_reduction_bounds", "router_import_materialization_bounds",
        }
        self.assertEqual(set(descriptors), expected)
        for descriptor in descriptors.values():
            self.assertEqual(descriptor["path_kind"], "private_package_relative")
            self.assertFalse(Path(descriptor["symbolic_name"]).is_absolute())
            self.assertNotIn("..", Path(descriptor["symbolic_name"]).parts)
            self.assertTrue(descriptor["immutable"])
            self.assertTrue(descriptor["read_only"])
            self.assertEqual(len(descriptor["sha256"]), 64)

    def test_missing_retained_antecedents_and_bounds_fail(self):
        result = RECOVERY.synthetic_recovery(ROOT)
        for field in ("router_matrix", "non_radial_component_bounds", "rmsnorm_decomposition_inputs"):
            mutated = copy.deepcopy(result)
            del mutated["private_antecedents"][field]
            with self.assertRaisesRegex(ValueError, "missing private"):
                RECOVERY.validate_synthetic_result(mutated)
        mutated = copy.deepcopy(result)
        mutated["pairwise_surface"]["selected_unselected_pair_bounds"].pop()
        with self.assertRaisesRegex(ValueError, "missing pairwise"):
            RECOVERY.validate_synthetic_result(mutated)
        mutated = copy.deepcopy(result)
        mutated["pairwise_surface"]["adjacent_selected_pair_bounds"].pop()
        with self.assertRaisesRegex(ValueError, "missing ordered"):
            RECOVERY.validate_synthetic_result(mutated)
        mutated = copy.deepcopy(result)
        mutated["private_antecedents"]["router_matrix"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "corrupted private"):
            RECOVERY.validate_synthetic_result(mutated)

    def test_six_field_summary_mutation_matrix_fails_closed(self):
        mutations = (
            ("claimed minimum pair", lambda item: item["pairwise_surface"]["derived_detail_summary"].__setitem__("global_minimum_pair", item["pairwise_surface"]["adjacent_selected_pair_bounds"][0])),
            ("minimum mathematical factor", lambda item: item["retrospective_v2"].__setitem__("minimum_mathematical_safety_factor", -1.0)),
            ("minimum engineering factor", lambda item: item["retrospective_v2"].__setitem__("minimum_engineering_safety_factor", -1.0)),
            ("route-set stable", lambda item: item["retrospective_v2"].__setitem__("route_set_stable", not item["retrospective_v2"]["route_set_stable"])),
            ("route-order stable", lambda item: item["retrospective_v2"].__setitem__("route_order_stable", not item["retrospective_v2"]["route_order_stable"])),
            ("overall classification", lambda item: item["pairwise_surface"]["derived_detail_summary"].__setitem__("overall_mathematical_classification", "MUTATED")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                result = RECOVERY.synthetic_recovery(ROOT)
                mutate(result)
                with self.assertRaisesRegex(ValueError, "summary/detail mismatch"):
                    RECOVERY.validate_synthetic_result(result)

    def test_additional_summary_and_surface_mutations_fail_closed(self):
        def validate_mutation(mutate, pattern: str = "pair|summary|count"):
            result = RECOVERY.synthetic_recovery(ROOT)
            mutate(result)
            with self.assertRaisesRegex(ValueError, pattern):
                RECOVERY.validate_synthetic_result(result)

        validate_mutation(
            lambda item: item["pairwise_surface"]["derived_detail_summary"]["ordered"].__setitem__(
                "minimum_pair", item["pairwise_surface"]["adjacent_selected_pair_bounds"][0]
            ),
            "summary/detail mismatch",
        )
        validate_mutation(
            lambda item: item["retrospective_v2"].__setitem__("engineering_status", "MUTATED"),
            "summary/detail mismatch",
        )
        validate_mutation(
            lambda item: item["pairwise_surface"]["derived_detail_summary"]["membership"].__setitem__(
                "mathematical_classification", "MUTATED"
            ),
            "summary/detail mismatch",
        )
        validate_mutation(
            lambda item: item["pairwise_surface"].__setitem__("membership_pair_count", 1983),
            "missing pairwise|count",
        )
        validate_mutation(
            lambda item: item["pairwise_surface"]["selected_unselected_pair_bounds"].__setitem__(
                1, copy.deepcopy(item["pairwise_surface"]["selected_unselected_pair_bounds"][0])
            )
        )
        validate_mutation(
            lambda item: item["pairwise_surface"]["selected_unselected_pair_bounds"].pop(),
            "missing pairwise",
        )
        validate_mutation(
            lambda item: item["pairwise_surface"].update({
                "selected_unselected_pair_bounds": copy.deepcopy(item["pairwise_surface"]["adjacent_selected_pair_bounds"]),
                "adjacent_selected_pair_bounds": copy.deepcopy(item["pairwise_surface"]["selected_unselected_pair_bounds"]),
            }),
            "missing pairwise|ordered|cardinality",
        )
        validate_mutation(
            lambda item: item["pairwise_surface"]["derived_detail_summary"].__setitem__(
                "global_minimum_pair", item["pairwise_surface"]["adjacent_selected_pair_bounds"][0]
            ),
            "summary/detail mismatch",
        )

    def test_duplicate_key_and_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                RECOVERY.load_json(duplicate)
            outside = Path(directory) / "outside"
            outside.write_text("x")
            link = ROOT / "f017-v2-recovery-test-link"
            try:
                os.symlink(outside, link)
                with self.assertRaisesRegex(ValueError, "symlink escape"):
                    RECOVERY.safe_file(ROOT, link.name)
            finally:
                link.unlink(missing_ok=True)

    def test_result_schema_preserves_historical_v1_status(self):
        schema = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-v2-antecedent-recovery-result-v1.schema.json").read_text())
        historical = schema["properties"]["historical_status"]["properties"]
        self.assertTrue(historical["historical_v1_status_unchanged"]["const"])
        self.assertFalse(historical["accepted_route_reclassified"]["const"])

    def test_config_hash_mutation_is_detected_before_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            raw = RECOVERY.canonical_json(self.config)
            path.write_bytes(raw)
            expected = hashlib.sha256(raw).hexdigest()
            path.write_bytes(raw + b" ")
            with self.assertRaisesRegex(ValueError, "config mutation"):
                RECOVERY.preflight(ROOT, path, expected)


if __name__ == "__main__":
    unittest.main()

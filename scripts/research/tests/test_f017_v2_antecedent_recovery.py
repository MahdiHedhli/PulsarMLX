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


class V2AntecedentRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        cls.config = PREPARE.build_config(ROOT, cls.head)

    def test_config_is_unexecuted_and_exactly_twelve_identity_bound_tensors(self):
        RECOVERY.validate_document(ROOT, self.config, verify_git=False)
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

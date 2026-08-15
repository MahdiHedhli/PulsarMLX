from __future__ import annotations

import copy
import hashlib
import json
import unittest

from scripts.research import f017_dense_prefix_authorization_preparation as M


class DensePrefixAuthorizationPreparationTests(unittest.TestCase):
    def test_repository_audit_fails_closed_on_hash_only_reuse_descriptors(self):
        value = M.audit()
        M.validate(value)
        self.assertEqual(value["status"], "BLOCKED_QUALIFIED_REUSE")
        self.assertEqual(value["authorization"]["preflight_result"], "NOT_READY — QUALIFIED_PAYLOAD_REUSE_INVALID")
        self.assertFalse(value["authorization"]["execution_config_created"])
        self.assertEqual(value["ledger"]["after_preparation"], 59)

    def test_inventory_is_independently_regenerated_and_partitioned(self):
        value = M.audit()
        self.assertEqual(value["inventory"]["regenerated_tensor_count"], 40)
        self.assertEqual(value["inventory"]["packed_bytes"], 1_431_263_232)
        self.assertEqual(value["inventory"]["aggregate_decoded_f32_bytes"], 8_504_653_824)
        self.assertEqual(value["inventory"]["quantization_counts"], {"F32": 12, "Q4_K": 1, "Q5_K": 12, "Q6_K": 3, "Q8_0": 12})
        allowlist = value["proposed_new_read_allowlist"]
        self.assertEqual(allowlist["tensor_payloads"], 38)
        self.assertEqual(allowlist["packed_bytes"], 834_066_432)
        self.assertEqual(allowlist["shard_opens"], 1)
        names = [row["name"] for row in allowlist["ordered_entries"]]
        self.assertNotIn("token_embd.weight", names)
        self.assertNotIn("blk.0.ffn_down.weight", names)
        self.assertEqual(len(names), len(set(names)))

    def test_q4_q6_truth_is_accepted_but_not_a_resolvable_reuse_package(self):
        value = M.audit()
        for component in value["qualified_components"]:
            self.assertEqual(component["qualification_status"], "EXACT_REAL_BYTE_QUALIFIED")
            self.assertEqual(component["reusable_private_package_status"], "UNRESOLVABLE_HASH_ONLY_DESCRIPTOR")
            self.assertIn("private_artifacts.private_package_identity", component["descriptor_gaps"])
            self.assertIn("private_artifacts.packed.symbolic_name", component["descriptor_gaps"])
            self.assertIn("private_artifacts.decoded[accepted].symbolic_name", component["descriptor_gaps"])

    def test_complete_synthetic_descriptor_has_no_semantic_gaps(self):
        evidence = json.loads(M.Q6_PATH.read_text())
        private = evidence["identity"]["private_artifacts"]
        private["private_package_identity"] = "synthetic-private-package"
        private["private_package_manifest_sha256"] = "a" * 64
        private["packed"].update(path_kind="private_package_relative", symbolic_name="weights/q6.packed", creation_ordinal=1, immutable=True)
        for ordinal, decoded in enumerate(private["decoded"], 2):
            decoded.update(path_kind="private_package_relative", symbolic_name=f"weights/q6-{ordinal}.lef32", creation_ordinal=ordinal, immutable=True)
        self.assertEqual(M.reusable_binding_gaps(evidence), [])

    def test_mutations_cannot_turn_blocker_into_authorization(self):
        value = M.audit()
        for mutation in (
            lambda row: row["authorization"].update(execution_config_created=True),
            lambda row: row["authorization"].update(authorization_binding_created=True),
            lambda row: row["authorization"].update(attempt_ledger_entry_created=True),
            lambda row: row["ledger"].update(after_preparation=97),
            lambda row: row["isolation"].update(checkpoint_access=1),
            lambda row: row["proposed_new_read_allowlist"].update(tensor_payloads=40),
        ):
            candidate = copy.deepcopy(value)
            mutation(candidate)
            with self.assertRaises(ValueError):
                M.validate(candidate)

    def test_banked_audit_and_report_match_derived_blocker(self):
        derived = M.audit()
        path = M.EVIDENCE / "f017-dense-prefix-authorization-preparation-audit-v1.json"
        banked = json.loads(path.read_text())
        self.assertEqual(banked["status"], derived["status"])
        self.assertEqual(banked["inventory"], derived["inventory"])
        for key in ("ordered_entries_sha256", "shard_opens", "positional_reads", "tensor_payloads", "packed_bytes"):
            self.assertEqual(banked["proposed_new_read_allowlist"][key], derived["proposed_new_read_allowlist"][key])
        self.assertEqual(banked["authorization"], derived["authorization"])
        self.assertEqual(banked["ledger"], derived["ledger"])
        self.assertEqual(banked["isolation"], derived["isolation"])
        self.assertEqual(len(hashlib.sha256(path.read_bytes()).hexdigest()), 64)


if __name__ == "__main__":
    unittest.main()

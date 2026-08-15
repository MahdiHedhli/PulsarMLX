from __future__ import annotations

import copy
import json
import unittest

from scripts.research import f017_dense_prefix_40_read_authorization as M


class DensePrefix40ReadAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = M.build_package()

    def test_predecessor_blocker_is_preserved(self):
        self.assertEqual(M.file_sha256(M.BLOCKER_EVIDENCE), M.BLOCKER_EVIDENCE_SHA)
        blocker = M.load_json(M.BLOCKER_EVIDENCE)
        self.assertEqual(blocker["authorization"]["preflight_result"], "NOT_READY — QUALIFIED_PAYLOAD_REUSE_INVALID")

    def test_contract_v2_retires_reuse_only(self):
        contract = self.package["preparation_contract"]
        self.assertEqual(contract["predecessor_sha256"], M.PREPARATION_V1_SHA)
        self.assertEqual(contract["strategy"], "FORTY_FRESH_READS_WITH_Q4_Q6_IDENTITY_CONFIRMATION")
        self.assertEqual(contract["read_strategy"], {"fresh_payload_reads": 40, "cross_event_decoded_reuse": 0})
        self.assertEqual(contract["ledger"], {"before": 59, "after_all_40_reads": 99})
        self.assertEqual(contract["semantic_delta"], ["remove qualified-payload reuse", "promote Q4_K and Q6_K observations to hard identity-confirmation gates"])

    def test_inventory_and_allowlist_are_exact(self):
        allowlist = self.package["allowlist"]
        self.assertEqual(allowlist["tensor_count"], 40)
        self.assertEqual(allowlist["packed_bytes"], 1_431_263_232)
        self.assertEqual(allowlist["aggregate_decoded_f32_bytes"], 8_504_653_824)
        self.assertEqual(allowlist["quantization_counts"], {"F32": 12, "Q4_K": 1, "Q5_K": 12, "Q6_K": 3, "Q8_0": 12})
        names = [row["name"] for row in allowlist["entries"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(row["allowed_read_count"] == 1 for row in allowlist["entries"]))
        self.assertFalse(any(row["layer"] == 3 or "router" in row["role"] or "expert" in row["role"] for row in allowlist["entries"]))

    def test_q4_q6_are_hard_identity_confirmation_gates(self):
        gates = self.package["identity_confirmation"]["gates"]
        q4, q6 = gates
        self.assertEqual((q4["tensor_name"], q4["packed_sha256"], q4["decoded_sha256"]), ("token_embd.weight", M.Q4_PACKED_SHA, M.Q4_DECODED_SHA))
        self.assertEqual((q6["tensor_name"], q6["packed_sha256"], q6["decoded_sha256"]), ("blk.0.ffn_down.weight", M.Q6_PACKED_SHA, M.Q6_DECODED_SHA))
        self.assertEqual(q4["mismatch_terminal_class"], "Q4_IDENTITY_CONFIRMATION")
        self.assertEqual(q6["mismatch_terminal_class"], "Q6_IDENTITY_CONFIRMATION")
        self.assertFalse(q4["new_decoder_qualification"])
        self.assertFalse(q6["new_decoder_qualification"])

    def test_retention_at_creation_is_structural(self):
        contract = self.package["retention_contract"]
        required = set(contract["required_reusable_artifact_fields"])
        self.assertTrue({"private_package_identity", "manifest_sha256", "symbolic_package_relative_path", "creation_ordinal", "immutable", "read_only", "dtype", "shape", "count", "serialization", "content_sha256", "provenance", "source_event_evidence_sha256"} <= required)
        self.assertEqual(contract["missing_package_disposition"], "CROSS_EVENT_REUSE_INELIGIBLE")
        self.assertTrue(contract["layer3_entry_state"]["retention_at_creation_required"])

    def test_package_is_born_authorized_and_preflight_ready(self):
        M.validate_package(self.package)
        config = self.package["execution_config"]
        attempt = self.package["attempt_ledger"]["events"][0]
        self.assertTrue(config["execution_authorized"])
        self.assertEqual(config["status"], "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW")
        self.assertEqual(attempt["attempt_id"], "DPREFIX-REAL-1")
        self.assertTrue(attempt["authorized"])
        self.assertFalse(attempt["consumed"] or attempt["executed"] or attempt["checkpoint_accessed"])
        self.assertEqual(config["tokenizer_identity"], M.TOKENIZER_IDENTITY)
        self.assertEqual(config["environment_manifest_sha256"], M.ENVIRONMENT_MANIFEST_SHA)
        self.assertEqual(config["loaded_library_sha256"]["libmlx.dylib"], M.MLX_NATIVE_LIBRARY_SHA)
        self.assertEqual(config["loaded_library_sha256"]["libmlxc.dylib"], M.MLX_C_LIBRARY_SHA)
        self.assertEqual(M.canonical_preflight(check_git=False, check_host=False), "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE")

    def test_partial_read_ledger_is_honest(self):
        for reads in range(41):
            M.validate_partial_read_ledger(59, reads, 59 + reads)
        for reads, after in ((0, 99), (1, 59), (39, 99), (40, 98)):
            with self.assertRaises(M.ContractError):
                M.validate_partial_read_ledger(59, reads, after)

    def test_negative_mutation_matrix(self):
        mutations = [
            lambda p: p["identity_confirmation"]["gates"][0].update(packed_sha256="0" * 64),
            lambda p: p["identity_confirmation"]["gates"][0].update(decoded_sha256="0" * 64),
            lambda p: p["identity_confirmation"]["gates"][1].update(packed_sha256="0" * 64),
            lambda p: p["identity_confirmation"]["gates"][1].update(decoded_sha256="0" * 64),
            lambda p: p["allowlist"]["entries"].pop(),
            lambda p: p["allowlist"]["entries"].append(copy.deepcopy(p["allowlist"]["entries"][0])),
            lambda p: p["allowlist"]["entries"].append(copy.deepcopy(p["allowlist"]["entries"][1])),
            lambda p: p["allowlist"]["entries"][0].update(layer=3),
            lambda p: p["execution_config"].update(ledger_before=58),
            lambda p: p["execution_config"].update(expected_ledger_after=98),
            lambda p: p["retention_contract"]["layer3_entry_state"].update(retention_at_creation_required=False),
            lambda p: p["retention_contract"]["layer3_entry_state"].update(read_only=False),
            lambda p: p["retention_contract"]["layer3_entry_state"].update(public_path_policy="absolute_machine_path_allowed"),
            lambda p: p["execution_config"].update(automatic_m1f0_continuation=True),
            lambda p: p["attempt_ledger"]["events"][0].update(authorized=False),
            lambda p: p["attempt_ledger"]["events"][0].update(consumed=True),
            lambda p: p["host_admission"].update(required_available_memory_gib=26),
            lambda p: p["execution_config"].update(oracle_sha256="0" * 64),
            lambda p: p["identity_confirmation"]["gates"][0].update(mismatch_policy="WARNING"),
            lambda p: p["cross_artifact_contract"].update(partial_read_ledger_policy="ASSUME_FULL_40"),
        ]
        for mutate in mutations:
            candidate = copy.deepcopy(self.package)
            mutate(candidate)
            with self.assertRaises(M.ContractError):
                M.validate_package(candidate)

    def test_banked_artifacts_regenerate_exactly(self):
        M.validate_banked_artifacts(self.package)
        for path in M.GENERATED_PATHS:
            json.loads(path.read_text())


if __name__ == "__main__":
    unittest.main()

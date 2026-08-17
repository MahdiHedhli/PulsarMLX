import json
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.research import f017_dprefix_real2_orchestrator as R


class Real2PreparationTests(unittest.TestCase):
    def test_real1_is_terminal_and_retry_impossible(self):
        R.validate_predecessor_terminal()
        state = R.load(R.EVIDENCE / "f017-dense-prefix-attempt-ledger-v8.json")["current_state"]
        self.assertTrue(state["consumed"])
        self.assertFalse(state["automatic_retry"])
        self.assertEqual(state["attempt_id"], "DPREFIX-REAL-1")

    def test_real_shape_contract_identifies_key_head_orientation(self):
        contract = R.real_shape_contract()
        R.validate_static_shapes(contract)
        key = next(item for item in contract["tensors"] if item["tensor"] == "blk.0.attn_k_b.weight")
        self.assertEqual(key["gguf_dimensions"], [192, 512, 64])
        self.assertEqual(key["native_imported_dimensions"], [64, 192, 512])
        self.assertEqual(key["expected_input_width"], 512)
        self.assertEqual(key["expected_output_width"], 192)

    def test_all40_packed_gates_and_only_two_banked_decoded_gates(self):
        manifest = R.packed_identity_manifest()
        self.assertEqual(manifest["packed_hard_gate_count"], 40)
        self.assertEqual(manifest["decoded_hard_gate_count"], 2)
        self.assertEqual(manifest["packed_only_count"], 38)
        self.assertEqual(sum(item["decoded_sha256"] is not None for item in manifest["entries"]), 2)

    def test_every_packed_gate_mutation_fails(self):
        manifest = R.packed_identity_manifest()
        baseline = [
            {"ordinal": item["ordinal"], "tensor": item["tensor"], "packed_sha256": item["packed_sha256"], "decoded_sha256": item["decoded_sha256"]}
            for item in manifest["entries"]
        ]
        R.validate_all40_identity(manifest, baseline)
        for index in range(40):
            mutated = [dict(item) for item in baseline]
            mutated[index]["packed_sha256"] = "0" * 64
            with self.assertRaisesRegex(R.Real2Error, "REAL_PAYLOAD_IDENTITY_CONFIRMATION"):
                R.validate_all40_identity(manifest, mutated)

    def test_packed_package_rejects_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            builder = R.PackedPackageBuilder.create(Path(directory) / "packed", {"x": R.digest_bytes(b"good")})
            with self.assertRaisesRegex(R.Real2Error, "REAL_PAYLOAD_IDENTITY_CONFIRMATION"):
                builder.add(0, "x", b"bad", 3)

    def test_packed_package_binds_supplied_checkpoint_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = b"bound"
            builder = R.PackedPackageBuilder.create(
                Path(directory) / "packed",
                {"x": R.digest_bytes(payload)},
                checkpoint_identity=R.CHECKPOINT_SET_SHA,
            )
            builder.add(0, "x", payload, len(payload))
            self.assertEqual(builder.entries[0]["checkpoint_identity"], R.CHECKPOINT_SET_SHA)

    def test_oracle_is_durable_before_candidate_and_survives_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = R.run_candidate_failure_persistence_rehearsal(Path(directory) / "event")
            self.assertEqual(result["result"], "ORACLE RETENTION SURVIVES CANDIDATE FAILURE")
            self.assertEqual(result["packed_retention"], "PACKED PACKAGE SURVIVES CANDIDATE FAILURE")
            self.assertTrue(result["oracle_rehash_on_failure"])
            self.assertEqual(result["failure"]["lifecycle"]["result"], "NATIVE FAILURE LIFECYCLE RECONCILED")
            self.assertEqual(result["failure"]["candidate_exit_status"], 2)
            for name in ("layer_2_output", "layer_3_entry"):
                path = Path(directory) / "event/oracle-primary" / f"{name}.f32le"
                self.assertFalse(path.stat().st_mode & stat.S_IWUSR)

    def test_shape_mutation_campaign(self):
        campaign = R.mutation_campaign(R.real_shape_contract())
        self.assertEqual(campaign["result"], "PASS")
        self.assertTrue(all(case["pass"] for case in campaign["cases"]))

    def test_failure_path_matrix_has_no_retry(self):
        matrix = R.failure_path_matrix()
        self.assertEqual(len(matrix["cases"]), 10)
        self.assertTrue(all(not item["automatic_retry"] for item in matrix["cases"]))

    def test_successor_preflight_rejects_consumed_state(self):
        config = {"attempt_id": R.ATTEMPT, "access": {"ledger_before": 99, "expected_full_ledger_after": 139, "payloads": 40, "packed_bytes": R.PACKED_BYTES}}
        auth = {"attempt_id": R.ATTEMPT, "execution_authorized": True}
        attempt = {"current_state": {"attempt_id": R.ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "ledger": 99, "automatic_retry": False, "automatic_m1f0_continuation": False}}
        self.assertEqual(R.preflight(config, auth, attempt), "READY_TO_EXECUTE_DPREFIX_REAL_2_PENDING_INDEPENDENT_REVIEW")
        attempt["current_state"]["consumed"] = True
        with self.assertRaises(R.Real2Error):
            R.preflight(config, auth, attempt)

    def test_candidate_history_preserves_real2_and_current_source_is_append_only_real3(self):
        source = (R.ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs").read_text()
        historical = R.load(R.EVIDENCE / "f017-dprefix-candidate-build-manifest-v3.json")
        self.assertEqual(historical["attempt_id"], "DPREFIX-REAL-2")
        self.assertEqual(
            historical["binary"]["sha256"],
            "2f6a8885a17c10c7776a0d27ed6eb8e85024b03bc499885eddb905050cad17b1",
        )
        self.assertIn('const ATTEMPT: &str = "DPREFIX-REAL-3"', source)
        self.assertIn('name.ends_with("attn_k_b.weight")', source)
        self.assertIn("transpose_k_head", source)

    def test_banked_successor_controls_reconcile(self):
        config_path = R.EVIDENCE / "f017-dense-prefix-execution-config-v6.json"
        auth_path = R.EVIDENCE / "f017-dense-prefix-authorization-binding-v5.json"
        attempt_path = R.EVIDENCE / "f017-dense-prefix-attempt-ledger-v9.json"
        config, auth, attempt = map(R.load, (config_path, auth_path, attempt_path))
        self.assertEqual(R.digest_path(config_path), auth["execution_config_sha256"])
        self.assertEqual(R.preflight(config, auth, attempt), "READY_TO_EXECUTE_DPREFIX_REAL_2_PENDING_INDEPENDENT_REVIEW")
        self.assertEqual(config["tier_b_sha256"], R.TIER_B_SHA)
        self.assertEqual(config["access"]["ledger_before"], 99)
        self.assertEqual(config["access"]["expected_full_ledger_after"], 139)
        self.assertFalse(config["automatic_retry"])
        self.assertFalse(config["automatic_m1f0_continuation"])
        self.assertIn("ANALYTICAL_ROUTE_PLANNING_ONLY", config["downstream_oracle_state_policy"])
        self.assertEqual(attempt["prior_terminal_attempt"]["state"], "TERMINAL_REJECTED")
        self.assertEqual(attempt["prior_terminal_attempt"]["attempt_id"], "DPREFIX-REAL-1")

    def test_public_successor_artifacts_do_not_leak_private_absolute_paths(self):
        paths = list((R.EVIDENCE).glob("*real2*.json")) + list((R.CONTRACTS).glob("f017-dprefix-*.json"))
        for path in paths:
            text = path.read_text()
            self.assertNotIn("/Users/", text, path.name)
            self.assertNotIn(".pulsarmlx-local/dprefix-real-1/material/packed", text, path.name)


if __name__ == "__main__":
    unittest.main()

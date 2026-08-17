import copy
import json
import unittest
from pathlib import Path

from scripts.research import f017_dprefix_real3_replay as R


class Real3PreparationTests(unittest.TestCase):
    def test_real2_is_terminal_and_not_retryable(self):
        regression = R.load(R.EVIDENCE / "f017-dprefix-real3-real2-terminal-regression-v1.json")
        self.assertEqual(regression["result"], "DPREFIX-REAL-2 TERMINAL — NO RETRY")
        self.assertTrue(all(value == "REJECTED_TERMINAL_ATTEMPT" for value in regression["admission_attacks"].values()))

    def test_packed_package_is_complete_immutable_and_exact(self):
        result = R.validate_packed_package()
        self.assertEqual(result["result"], "PACKED PACKAGE READY FOR CHECKPOINT-FREE REPLAY")
        self.assertEqual(result["entries"], 40)
        self.assertEqual(result["packed_bytes"], 1_431_263_232)
        self.assertEqual(result["package_identity"], R.PACKED_PACKAGE_SHA)
        self.assertEqual((result["ledger_before"], result["ledger_after"]), (139, 139))

    def test_all_40_decoded_identities_are_hard_gates(self):
        manifest = R.load(R.DECODED_MANIFEST_PATH)
        observed = R.load(R.EVIDENCE / "f017-dprefix-real3-all40-independent-decode-v1.json")
        self.assertEqual(manifest["hard_gate_count"], 40)
        self.assertEqual(observed["hard_gate_count"], 40)
        self.assertTrue(all(item["exact"] for item in observed["observed"]))
        self.assertEqual(observed["candidate_import_independence"], "REPLAY CANDIDATE IMPORT INDEPENDENT")

    def test_replay_source_has_no_checkpoint_reader_or_ledger_writer(self):
        source = Path(R.__file__).read_text()
        for forbidden in ("os.pread", "mmap.mmap", "BoundedCheckpointReader", "DurableReadJournal"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("f017_dprefix_real2_orchestrator", source)
        attacks = R.zero_read_attack_campaign()
        self.assertEqual(attacks["result"], "REAL-3 ZERO-READ GUARANTEE STRUCTURAL")
        self.assertTrue(all(item["checkpoint_access"] == 0 and item["ledger"] == 139 for item in attacks["cases"]))

    def test_success_rehearsal_uses_actual_accounting(self):
        result = R.load(R.EVIDENCE / "f017-dprefix-real3-success-rehearsal-v1.json")
        self.assertEqual(result["result"], "SUCCESS-PATH TERMINAL EVIDENCE COMPLETE")
        self.assertEqual(result["instantiability"], "REAL-3 SUCCESS EVIDENCE FULLY INSTANTIABLE")
        self.assertEqual(result["actual_host_copy_count"], 4050)
        self.assertGreater(result["actual_host_copy_bytes"], 0)
        lifecycle = result["success_path_lifecycle_reconciliation"]
        self.assertEqual(lifecycle["result"], "PASS")
        self.assertEqual(lifecycle["arrays_created"], lifecycle["arrays_destroyed"])
        self.assertEqual(lifecycle["contexts_created"], lifecycle["contexts_destroyed"])
        self.assertEqual(result["repeats"], 10)
        self.assertTrue(result["deterministic"])
        self.assertEqual(len(result["tier_b_surfaces"]), 8)
        self.assertTrue(all(item["pass"] for item in result["tier_b_surfaces"]))

    def test_finalizer_rejects_missing_d4_fields(self):
        result = R.load(R.EVIDENCE / "f017-dprefix-real3-success-rehearsal-v1.json")
        candidate = result["terminal_evidence"]["candidate"]
        surfaces = result["tier_b_surfaces"]
        R.terminal_finalize(candidate, surfaces)
        missing_host = copy.deepcopy(candidate)
        missing_host["dispatch"].pop("actual_host_copy_count")
        with self.assertRaisesRegex(R.ReplayError, "D4_HOST_COPY_ACCOUNTING"):
            R.terminal_finalize(missing_host, surfaces)
        missing_lifecycle = copy.deepcopy(candidate)
        missing_lifecycle.pop("success_path_lifecycle_reconciliation")
        with self.assertRaisesRegex(R.ReplayError, "D4_LIFECYCLE_ACCOUNTING"):
            R.terminal_finalize(missing_lifecycle, surfaces)

    def test_controls_and_preflight_bind_zero_read_replay(self):
        config = R.load(R.CONFIG_PATH)
        auth = R.load(R.AUTH_PATH)
        attempt = R.load(R.EVIDENCE / "f017-dense-prefix-replay-attempt-ledger-v1.json")
        self.assertEqual(config["event_type"], "CHECKPOINT-FREE RETAINED-PACKAGE DPREFIX REPLAY")
        self.assertEqual(config["checkpoint_access_budget"], 0)
        self.assertEqual((config["ledger_before"], config["ledger_after"]), (139, 139))
        self.assertEqual(auth["execution_config_sha256"], R.digest_path(R.CONFIG_PATH))
        self.assertEqual(attempt["current_state"]["attempt_id"], "DPREFIX-REAL-3")
        self.assertFalse(attempt["current_state"]["consumed"])
        self.assertEqual(R.preflight(), "READY_TO_EXECUTE_DPREFIX_CHECKPOINT_FREE_REPLAY")

    def test_live_payload_ledger_remains_139_and_has_no_real3_event(self):
        ledger = R.load(R.PAYLOAD_LEDGER_PATH)
        self.assertEqual(ledger["cumulative_tensor_payloads"], 139)
        self.assertNotIn("DPREFIX-REAL-3", {item["attempt"] for item in ledger["events"]})

    def test_public_artifacts_contain_no_absolute_private_path(self):
        paths = list(R.EVIDENCE.glob("*real3*.json")) + list(R.EVIDENCE.glob("*replay*.json")) + list(R.CONTRACTS.glob("f017-dprefix-replay-*.json"))
        self.assertTrue(paths)
        for path in paths:
            self.assertNotIn("/Users/", path.read_text(), path.name)


if __name__ == "__main__":
    unittest.main()

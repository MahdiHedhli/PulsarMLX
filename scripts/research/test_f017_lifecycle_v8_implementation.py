#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from execute_f017_corrected_oracle_event_v8 import execute_synthetic
from f017_descriptor_runtime_mutations_v8 import qualify as qualify_runtime_mutations
from f017_synthetic_checkpoint_v8 import prepare


class LifecycleV8ImplementationTests(unittest.TestCase):
    def test_success_minimal_and_mixed(self):
        for mixed, seed in ((False, 18101), (True, 18102)):
            with self.subTest(mixed=mixed), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                installed, receipt, _ = prepare(root, seed, f"{'MIXED' if mixed else 'MIN'}-01", mixed)
                result = execute_synthetic(installed, receipt, root / "evidence")
                self.assertEqual(result["result"], "PASS")
                self.assertEqual(result["identity"]["retained_lease_count"], 5)
                self.assertEqual(result["release"]["live_leases_after_release"], 0)
                self.assertEqual(result["primary"]["path_reopen_count"], 0)
                self.assertEqual(result["secondary"]["path_reopen_count"], 0)
                for artifact in (
                    "package-claim.json", "package-durable-start.json", "package-ledger-entry.json",
                    "descriptor-lease-manifest.json", "checkpoint-identity-terminal.json",
                    "primary-durable-start.json", "primary-ledger-entry.json", "primary-receipt.json", "primary-terminal.json",
                    "secondary-durable-start.json", "secondary-ledger-entry.json", "secondary-receipt.json", "secondary-terminal.json",
                    "comparison-receipt.json", "comparison-terminal.json", "descriptor-release.json",
                    "package-receipt.json", "package-terminal.json",
                ):
                    self.assertTrue((root / "evidence" / artifact).is_file(), artifact)

    def test_malformed_runtime_artifacts_are_controlled(self):
        for mutation in ("MODE_65536", "NON_DICT", "UNHASHABLE_LEASE"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                installed, receipt, _ = prepare(root, 18103, f"FAIL-{mutation}")
                result = execute_synthetic(installed, receipt, root / "evidence", malformed=mutation)
                self.assertEqual(result["result"], "CONTROLLED_FAILURE")
                self.assertEqual(result["failure_class"], "ValueError")
                self.assertEqual(result["accounting"]["primary"], 0)
                self.assertEqual(result["accounting"]["secondary"], 0)

    def test_filesystem_error_is_normalized(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            installed, receipt, shards = prepare(root, 18105, "FAIL-SHARD-MISSING")
            (root / "checkpoint" / shards[2]["filename"]).unlink()
            result = execute_synthetic(installed, receipt, root / "evidence")
            self.assertEqual(result["result"], "CONTROLLED_FAILURE")
            self.assertEqual(result["failure_class"], "ValueError")
            self.assertEqual(result["source_exception_class"], "FileNotFoundError")

    def test_no_active_or_live_authority(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            installed, _, _ = prepare(root, 18104, "POSTURE-01")
            value = json.loads(installed.read_bytes())
            self.assertIs(value["live"], False)
            self.assertEqual(value["active_generation"], "NONE")

    def test_runtime_descriptor_mutation_campaign(self):
        result = qualify_runtime_mutations()
        self.assertGreaterEqual(result["mutation_count"], 40)
        self.assertEqual(result["unexpected_passes"], 0)
        self.assertEqual(result["uncontrolled_exception_classes"], 0)


if __name__ == "__main__":
    unittest.main()

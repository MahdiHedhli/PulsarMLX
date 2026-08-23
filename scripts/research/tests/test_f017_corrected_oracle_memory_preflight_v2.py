from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

import execute_f017_corrected_oracle_event_v2 as coordinator
from f017_macos_memory_observation_v1 import MemoryObservation, MemoryObservationError
import validate_f017_corrected_oracle_access_v2 as access_v2


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(path: Path) -> Path:
    value = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v1.json").read_text())
    value["schema"] = "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/2.0.0"
    value["bindings"]["event_coordinator"] = {
        "path": "scripts/research/execute_f017_corrected_oracle_event_v2.py",
        "sha256": digest(RESEARCH / "execute_f017_corrected_oracle_event_v2.py"),
    }
    value["bindings"]["memory_observer"] = {
        "path": "scripts/research/f017_macos_memory_observation_v1.py",
        "sha256": digest(RESEARCH / "f017_macos_memory_observation_v1.py"),
    }
    value["memory_preflight"] = {
        "minimum_free_bytes": 17179869184,
        "sample_freshness_seconds": 5,
    }
    path.write_text(json.dumps(value) + "\n")
    return path


def observation(available=20 * 1024**3):
    return MemoryObservation(
        parser_version="F017_MACOS_VM_STAT_V1",
        page_size_bytes=1,
        pages_free=available,
        pages_inactive=0,
        pages_speculative=0,
        pages_purgeable=0,
        available_bytes=available,
        canonical_observation="test",
        stdout_sha256="0" * 64,
        observed_at_unix_ns=1,
    )


class CoordinatorPreflightTests(unittest.TestCase):
    def patched_authority(self):
        return mock.patch.object(
            coordinator,
            "repository_authority",
            return_value={"git_head": "f" * 40, "local_remote_parity": True, "worktree_clean": True},
        )

    def test_committed_v2_authority_and_inert_fixture_validate(self):
        contract_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v2.json"
        inert_path = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v2.json"
        access_v2.validate(access_v2.strict(inert_path), access_v2.strict(contract_path), ROOT)

    def test_v1_coordinator_is_historical_only_and_cannot_satisfy_v1_binding(self):
        old = ROOT / "scripts/research/execute_f017_corrected_oracle_event.py"
        historical_sha = "e76a73150c415f73a6c8fc29429636084ab126c3302036bce39414dede40ce8a"
        self.assertNotEqual(digest(old), historical_sha)
        result = subprocess.run([sys.executable, str(old)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HISTORICAL_ONLY", result.stderr)

    def test_validation_cannot_mint_and_operator_command_requires_explicit_environment(self):
        contract_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v2.json"
        inert_path = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v2.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "authorization.json"
            result = subprocess.run(
                [sys.executable, str(RESEARCH / "validate_f017_corrected_oracle_access_v2.py"), "validate", str(inert_path), str(contract_path), str(ROOT)],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("PASS", result.stdout)
            self.assertFalse(output.exists())
            attempted = subprocess.run(
                [sys.executable, str(RESEARCH / "validate_f017_corrected_oracle_access_v2.py"), "authorize-live", str(inert_path), str(contract_path), str(ROOT), "missing-approval", "missing-preflight", "missing-checkpoint", str(Path(directory) / "state"), str(output)],
                text=True,
                capture_output=True,
                env={},
            )
            self.assertNotEqual(attempted.returncode, 0)
            self.assertIn("operator mint environment missing", attempted.stderr)
            self.assertFalse(output.exists())

    def test_stale_preflight_cannot_authorize(self):
        contract_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v2.json"
        value = access_v2.strict(contract_path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.CompletedProcess([], 0, stdout="Apple M1 Ultra\n", stderr="")
            with self.patched_authority(), mock.patch.object(coordinator, "observe_vm_stat", return_value=observation()), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"):
                report = coordinator.preflight(contract_path)
            report["observation"]["observed_at_unix_ns"] = 1
            with self.assertRaisesRegex(ValueError, "stale"):
                access_v2.validate_preflight(report, value, ROOT)

    def test_preflight_pass_banks_report_without_state_authorization_or_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            forbidden = (root / "state", root / "authorization.json", root / "claim.json", root / "checkpoint-open")
            completed = subprocess.CompletedProcess([], 0, stdout="Apple M1 Ultra\n", stderr="")
            with self.patched_authority(), mock.patch.object(coordinator, "observe_vm_stat", return_value=observation()), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"):
                value = coordinator.preflight(contract(root / "contract.json"), report)
            self.assertEqual(value["result"], "PASS")
            self.assertEqual(value["checkpoint_shard_opens"], 0)
            self.assertTrue(report.is_file())
            self.assertTrue(all(not path.exists() for path in forbidden))

    def test_memory_failure_precedes_all_side_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            completed = subprocess.CompletedProcess([], 0, stdout="Apple M1 Ultra\n", stderr="")
            with self.patched_authority(), mock.patch.object(coordinator, "observe_vm_stat", side_effect=MemoryObservationError("bad")), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"), self.assertRaises(MemoryObservationError):
                coordinator.preflight(contract(root / "contract.json"), report)
            self.assertFalse(report.exists())
            self.assertEqual(list(root.glob("state*")), [])
            self.assertEqual(list(root.glob("*authorization*")), [])

    def test_below_floor_fails_without_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.CompletedProcess([], 0, stdout="Apple M1 Ultra\n", stderr="")
            with self.patched_authority(), mock.patch.object(coordinator, "observe_vm_stat", return_value=observation(17179869183)), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"), self.assertRaises(ValueError):
                coordinator.preflight(contract(root / "contract.json"), root / "report.json")

    @unittest.skipUnless(platform.system() == "Darwin", "macOS-only host qualification")
    def test_current_host_preflight_is_observational_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            with self.patched_authority():
                value = coordinator.preflight(contract(root / "contract.json"), report)
            self.assertEqual(value["result"], "PASS")
            self.assertGreaterEqual(value["observation"]["available_bytes"], 17179869184)
            self.assertEqual(value["checkpoint_payload_reads"], 0)
            self.assertEqual(sorted(item.name for item in root.iterdir()), ["contract.json", "report.json"])


if __name__ == "__main__":
    unittest.main()

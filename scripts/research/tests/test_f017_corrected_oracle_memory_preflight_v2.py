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
        page_size_bytes=16384,
        pages_free=1,
        pages_inactive=1,
        pages_speculative=1,
        pages_purgeable=1,
        available_bytes=available,
        canonical_observation="test",
        stdout_sha256="0" * 64,
        observed_at_unix_ns=1,
    )


class CoordinatorPreflightTests(unittest.TestCase):
    def test_preflight_pass_banks_report_without_state_authorization_or_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            forbidden = (root / "state", root / "authorization.json", root / "claim.json", root / "checkpoint-open")
            completed = subprocess.CompletedProcess([], 0, stdout="Apple M1 Ultra\n", stderr="")
            with mock.patch.object(coordinator, "observe_vm_stat", return_value=observation()), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"):
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
            with mock.patch.object(coordinator, "observe_vm_stat", side_effect=MemoryObservationError("bad")), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"), self.assertRaises(MemoryObservationError):
                coordinator.preflight(contract(root / "contract.json"), report)
            self.assertFalse(report.exists())
            self.assertEqual(list(root.glob("state*")), [])
            self.assertEqual(list(root.glob("*authorization*")), [])

    def test_below_floor_fails_without_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            completed = subprocess.CompletedProcess([], 0, stdout="Apple M1 Ultra\n", stderr="")
            with mock.patch.object(coordinator, "observe_vm_stat", return_value=observation(17179869183)), mock.patch.object(coordinator.subprocess, "run", return_value=completed), mock.patch.object(coordinator.platform, "machine", return_value="arm64"), self.assertRaises(ValueError):
                coordinator.preflight(contract(root / "contract.json"), root / "report.json")

    @unittest.skipUnless(platform.system() == "Darwin", "macOS-only host qualification")
    def test_current_host_preflight_is_observational_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            value = coordinator.preflight(contract(root / "contract.json"), report)
            self.assertEqual(value["result"], "PASS")
            self.assertGreaterEqual(value["observation"]["available_bytes"], 17179869184)
            self.assertEqual(value["checkpoint_payload_reads"], 0)
            self.assertEqual(sorted(item.name for item in root.iterdir()), ["contract.json", "report.json"])


if __name__ == "__main__":
    unittest.main()

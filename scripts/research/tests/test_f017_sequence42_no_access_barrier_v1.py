from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RESEARCH_DIR = Path(__file__).resolve().parents[1]
RUNNER = RESEARCH_DIR / "run_f017_sequence42_no_access.py"
TARGET = RESEARCH_DIR / "f017_event06_minimum_gate_path_v1.py"
BARRIER_DIR = RESEARCH_DIR / "f017_sequence42_no_access_barrier"


class Sequence42NoAccessBarrierTests(unittest.TestCase):
    def _run(self, code: str) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
        with tempfile.TemporaryDirectory(prefix="f017-sequence42-barrier-") as root:
            log = Path(root) / "barrier.jsonl"
            environment = dict(os.environ)
            existing = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = os.pathsep.join(
                [
                    os.fspath(RESEARCH_DIR),
                    *[item for item in existing.split(os.pathsep) if item],
                ]
            )
            result = subprocess.run(
                [
                    sys.executable,
                    os.fspath(RUNNER),
                    "--source",
                    os.fspath(TARGET),
                    "--log",
                    os.fspath(log),
                    "--",
                    sys.executable,
                    "-c",
                    code,
                ],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )
            events = [json.loads(line) for line in log.read_text().splitlines()]
            return result, events

    def test_target_import_is_supervised(self) -> None:
        result, events = self._run("import f017_event06_minimum_gate_path_v1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[-1]["result"], "PASS")
        self.assertEqual(events[-1]["blocked_accesses"], 0)
        self.assertGreaterEqual(events[-1]["event06_target_imports"], 1)

    def test_python_child_inherits_barrier_and_is_accounted(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,subprocess,sys;"
            "subprocess.run([sys.executable,'-c',"
            "'import f017_checkpoint_identity_producer_v12'],check=True)"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = events[-1]
        self.assertEqual(summary["barrier_processes"], 2)
        self.assertEqual(summary["spawn_intents"], 1)
        self.assertEqual(summary["startup_coverage"], "PASS")

    def test_os_spawnve_inherits_one_supervised_token(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,os,sys;"
            "assert os.spawnve(os.P_WAIT,sys.executable,[sys.executable,'-c',"
            "'import f017_checkpoint_identity_producer_v12'],dict(os.environ))==0"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = events[-1]
        self.assertEqual(summary["barrier_processes"], 2)
        self.assertEqual(summary["spawn_intents"], 1)

    def test_caught_live_root_access_still_fails_supervision(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1 as target,os;"
            "\ntry: os.stat(target._LIVE_CHECKPOINT_ROOT)"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(item.get("event") == "BLOCKED_ACCESS" for item in events)
        )

    def test_caught_site_bypass_child_still_fails_supervision(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,subprocess,sys;"
            "\ntry: subprocess.run([sys.executable,'-S','-c','pass'])"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(
                item.get("event") == "BARRIER_POLICY_VIOLATION"
                and item.get("detail") == "site-startup-bypass-flag"
                for item in events
            )
        )

    def test_source_free_system_native_child_is_observed_without_python_token(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,subprocess;"
            "subprocess.run(['/usr/bin/true'],check=True)"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[-1]["result"], "PASS")
        self.assertEqual(events[-1]["barrier_processes"], 1)
        self.assertEqual(events[-1]["spawn_intents"], 0)
        self.assertEqual(events[-1]["native_subprocesses_observed"], 1)
        self.assertTrue(
            any(
                item.get("event") == "NATIVE_SUBPROCESS_OBSERVED"
                for item in events
            )
        )

    def test_native_child_live_root_argument_fails_even_when_caught(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1 as target,subprocess;"
            "\ntry: subprocess.run(['/usr/bin/true',str(target._LIVE_CHECKPOINT_ROOT)])"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(
                item.get("event") == "BLOCKED_ACCESS"
                and item.get("operation") == "subprocess.Popen"
                for item in events
            )
        )

    def test_native_child_environment_override_fails_supervision(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,subprocess;"
            "\ntry: subprocess.run(['/usr/bin/true'],env={})"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(
                item.get("event") == "BARRIER_POLICY_VIOLATION"
                and item.get("detail") == "native-environment-override-prohibited"
                for item in events
            )
        )

    def test_native_shell_child_fails_supervision(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,subprocess;"
            "\ntry: subprocess.run(['/usr/bin/true'],shell=True)"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(
                item.get("event") == "BARRIER_POLICY_VIOLATION"
                and item.get("detail") == "shell-child-prohibited"
                for item in events
            )
        )

    def test_native_preexec_callback_fails_supervision(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,subprocess;"
            "\ntry: subprocess.run(['/usr/bin/true'],preexec_fn=lambda:None)"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(
                item.get("event") == "BARRIER_POLICY_VIOLATION"
                and item.get("detail") == "preexec-callback-prohibited"
                for item in events
            )
        )

    def test_caught_barrier_environment_removal_fails_supervision(self) -> None:
        code = (
            "import f017_event06_minimum_gate_path_v1,os;"
            "\ntry: del os.environ['F017_SEQUENCE42_SOURCE_FILE']"
            "\nexcept RuntimeError: pass"
        )
        result, events = self._run(code)
        self.assertEqual(result.returncode, 97)
        self.assertTrue(
            any(
                item.get("event") == "BARRIER_POLICY_VIOLATION"
                and item.get("detail") == "barrier-environment-removal"
                for item in events
            )
        )

    def test_source_digest_mismatch_terminates_during_site_startup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-sequence42-binding-") as root:
            temporary = Path(root)
            source = temporary / "source.py"
            source.write_text(
                "from pathlib import Path\n"
                "_LIVE_PACKAGE_PARENT = Path('/private/tmp/f017-live-package')\n"
                "_LIVE_CHECKPOINT_ROOT = Path('/private/tmp/f017-live-checkpoint')\n"
            )
            log = temporary / "barrier.jsonl"
            descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            source_stat = source.stat()
            log_stat = log.stat()
            environment = dict(os.environ)
            environment.update(
                {
                    "PYTHONPATH": os.fspath(BARRIER_DIR),
                    "F017_SEQUENCE42_SOURCE_FILE": os.fspath(source),
                    "F017_SEQUENCE42_SOURCE_SHA256": "0" * 64,
                    "F017_SEQUENCE42_SOURCE_DEVICE": str(source_stat.st_dev),
                    "F017_SEQUENCE42_SOURCE_INODE": str(source_stat.st_ino),
                    "F017_SEQUENCE42_SOURCE_SIZE": str(source_stat.st_size),
                    "F017_SEQUENCE42_SOURCE_MTIME_NS": str(source_stat.st_mtime_ns),
                    "F017_SEQUENCE42_SOURCE_CTIME_NS": str(source_stat.st_ctime_ns),
                    "F017_SEQUENCE42_BARRIER_LOG": os.fspath(log),
                    "F017_SEQUENCE42_BARRIER_LOG_DEVICE": str(log_stat.st_dev),
                    "F017_SEQUENCE42_BARRIER_LOG_INODE": str(log_stat.st_ino),
                    "F017_SEQUENCE42_BARRIER_TOKEN": "binding-test",
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", "pass"],
                check=False,
                capture_output=True,
                env=environment,
                text=True,
            )
            self.assertEqual(result.returncode, 96)
            self.assertIn("SOURCE_DIGEST", result.stderr)
            self.assertEqual(log.read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import retain_f017_diagnostic_v1 as retention


class F017DiagnosticRetentionTests(unittest.TestCase):
    def paths(self, root: Path) -> tuple[Path, Path, Path, Path]:
        return tuple(root / name for name in ("report.json", "retained.json", "stdout", "stderr"))  # type: ignore[return-value]

    def write_json(self, path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_valid_report_is_projected_without_paths_or_stream_contents(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            stdout_raw = b"safe command output\n"
            stderr_raw = b"private raw stderr must never be retained\n"
            stdout.write_bytes(stdout_raw)
            stderr.write_bytes(stderr_raw)
            command = {
                "returncode": 0,
                "stdout_bytes": 4,
                "stdout_sha256": "a" * 64,
                "stderr_bytes": 0,
                "stderr_sha256": "b" * 64,
                "argv": ["python", "--secret-argument", "/private/runner/path"],
            }
            self.write_json(
                report,
                {
                    "schema": "producer-schema",
                    "historical_preflight": {
                        "root": "/private/runner/path",
                        "revision": "c" * 40,
                        "relative_path": "private/input.py",
                        "result": "PASS",
                        "model_environment_empty": True,
                        "required_checks_clean": True,
                        "historical_blob_is_blob": True,
                        "resolved": {
                            "git_dir": "/private/runner/.git",
                            "shallow_repository": "false",
                            "object_format": "sha1",
                            "cat_file_type": "blob",
                        },
                        "commands": {"show": command},
                    },
                },
            )

            envelope, status = retention.retain(
                report, output, stdout, stderr, 0, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
            )
            retained = output.read_text(encoding="utf-8")
            self.assertEqual(status, 0)
            self.assertEqual(envelope["status"], "PASS")
            self.assertTrue(envelope["report_available"])
            self.assertFalse(envelope["fallback_used"])
            self.assertEqual(envelope["stdout_bytes"], len(stdout_raw))
            self.assertEqual(envelope["stdout_sha256"], hashlib.sha256(stdout_raw).hexdigest())
            self.assertEqual(envelope["stderr_bytes"], len(stderr_raw))
            self.assertEqual(envelope["stderr_sha256"], hashlib.sha256(stderr_raw).hexdigest())
            self.assertNotIn("/private/runner/path", retained)
            self.assertNotIn("private/input.py", retained)
            self.assertNotIn("secret-argument", retained)
            self.assertNotIn("private raw stderr", retained)
            self.assertNotIn("argv", retained)
            self.assertEqual(envelope["diagnostic"]["revision"], "c" * 40)

    def test_missing_report_keeps_failed_status_with_safe_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            stdout.write_bytes(b"bounded stdout")
            stderr.write_bytes(b"bounded stderr")

            envelope, status = retention.retain(
                report, output, stdout, stderr, 23, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
            )

            self.assertEqual(status, 0)
            self.assertEqual(envelope["status"], "FAIL")
            self.assertEqual(envelope["command_exit_status"], 23)
            self.assertFalse(envelope["report_available"])
            self.assertTrue(envelope["fallback_used"])
            self.assertIsNone(envelope["diagnostic"])
            self.assertEqual(envelope["stdout_bytes"], len(b"bounded stdout"))
            self.assertEqual(envelope["stderr_bytes"], len(b"bounded stderr"))

    def test_missing_report_cannot_make_successful_command_green(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            stdout.touch()
            stderr.touch()

            envelope, status = retention.retain(
                report, output, stdout, stderr, 0, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
            )

            self.assertEqual(status, 1)
            self.assertEqual(envelope["status"], "FAIL")
            self.assertTrue(output.is_file())

    def test_malformed_report_is_replaced_by_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            report.write_bytes(b"not-json")
            stdout.touch()
            stderr.touch()

            envelope, status = retention.retain(
                report, output, stdout, stderr, 1, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
            )

            self.assertEqual(status, 0)
            self.assertFalse(envelope["report_available"])
            self.assertEqual(envelope["report_bytes"], len(b"not-json"))
            self.assertEqual(envelope["report_sha256"], hashlib.sha256(b"not-json").hexdigest())
            self.assertEqual(envelope["fallback_reason"], "REPORT_MISSING_OR_MALFORMED")

    def test_partial_or_duplicate_report_cannot_make_successful_command_green(self) -> None:
        for label, raw_report in (
            ("partial", b'{"result":"PASS","commands":{"show":{"returncode":0}}}'),
            ("duplicate", b'{"result":"PASS","result":"PASS","commands":{}}'),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                report, output, stdout, stderr = self.paths(root)
                report.write_bytes(raw_report)
                stdout.touch()
                stderr.touch()

                envelope, status = retention.retain(
                    report, output, stdout, stderr, 0, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
                )

                self.assertEqual(status, 1)
                self.assertFalse(envelope["report_available"])
                self.assertEqual(envelope["result"], "FAIL")


if __name__ == "__main__":
    unittest.main()

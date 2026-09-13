from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

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

    def test_malformed_result_shapes_use_sanitized_fail_fallback(self) -> None:
        for label, malformed_result in (
            ("array", ["raw-array-report-content"]),
            ("object", {"raw": "raw-object-report-content"}),
            ("list", ["raw-list-report-content", {"secret": "raw-list-secret"}]),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                report, output, stdout, stderr = self.paths(root)
                self.write_json(
                    report,
                    {
                        "historical_preflight": {
                            "result": malformed_result,
                            "commands": {
                                "show": {
                                    "returncode": 0,
                                    "stdout_bytes": 0,
                                    "stdout_sha256": "a" * 64,
                                    "stderr_bytes": 0,
                                    "stderr_sha256": "b" * 64,
                                }
                            },
                        }
                    },
                )
                stdout.touch()
                stderr.touch()

                envelope, status = retention.retain(
                    report, output, stdout, stderr, 23, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
                )

                retained = output.read_text(encoding="utf-8")
                self.assertEqual(status, 0)
                self.assertEqual(envelope["status"], "FAIL")
                self.assertEqual(envelope["result"], "FAIL")
                self.assertFalse(envelope["report_available"])
                self.assertIsNone(envelope["diagnostic"])
                self.assertNotIn("raw-", retained)
                self.assertNotIn("secret", retained)

    def test_growing_capture_is_not_read_or_marked_available_beyond_limit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            capture = root / "growing-capture"
            capture.write_bytes(b"base")
            limit = 8
            original_read = retention.os.read
            total_read = 0
            read_calls = 0

            def read_and_grow(fd: int, count: int) -> bytes:
                nonlocal read_calls, total_read
                chunk = original_read(fd, count)
                read_calls += 1
                total_read += len(chunk)
                if read_calls == 1:
                    with capture.open("ab") as handle:
                        handle.write(b"growth")
                return chunk

            with mock.patch.object(retention.os, "read", side_effect=read_and_grow):
                observation = retention._file_observation(capture, limit=limit)

            self.assertFalse(observation["available"])
            self.assertIsNone(observation["sha256"])
            self.assertLessEqual(total_read, limit)

    def test_retained_output_and_summary_are_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            summary = root / "summary.json"
            stdout.touch()
            stderr.touch()

            envelope, status = retention.retain(
                report,
                output,
                stdout,
                stderr,
                1,
                "EVENT06_PACKAGE_TERMINAL_UNIQUENESS",
                summary_path=summary,
            )

            self.assertEqual(status, 0)
            self.assertEqual(envelope["result"], "FAIL")
            for path in (output, summary):
                self.assertTrue(stat.S_ISREG(path.stat(follow_symlinks=False).st_mode))
            self.assertEqual(summary.read_bytes(), output.read_bytes())

    def test_retained_output_symlink_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            target = root / "output-target"
            target.write_bytes(b"do not overwrite")
            output.symlink_to(target)
            stdout.touch()
            stderr.touch()

            with self.assertRaises(OSError):
                retention.retain(
                    report, output, stdout, stderr, 1, "EVENT06_PACKAGE_TERMINAL_UNIQUENESS"
                )

            self.assertEqual(target.read_bytes(), b"do not overwrite")

    def test_summary_symlink_is_not_followed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report, output, stdout, stderr = self.paths(root)
            summary = root / "summary.json"
            target = root / "summary-target"
            target.write_bytes(b"do not overwrite")
            summary.symlink_to(target)
            stdout.touch()
            stderr.touch()

            with self.assertRaises(OSError):
                retention.retain(
                    report,
                    output,
                    stdout,
                    stderr,
                    1,
                    "EVENT06_PACKAGE_TERMINAL_UNIQUENESS",
                    summary_path=summary,
                )

            self.assertEqual(target.read_bytes(), b"do not overwrite")

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

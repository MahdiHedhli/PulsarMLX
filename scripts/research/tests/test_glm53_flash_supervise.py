"""Focused tests for bounded supervisor termination evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import signal
import subprocess
import unittest
from unittest import mock


SUPERVISOR_PATH = (
    Path(__file__).resolve().parents[1] / "glm53_flash" / "supervise.py"
)
SPEC = importlib.util.spec_from_file_location("glm53_flash_supervise_under_test", SUPERVISOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load supervisor source")
SUPERVISOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPERVISOR)


class NeverReapedProcess:
    pid = 12345

    def __init__(self):
        self.wait_timeouts = []

    def poll(self):
        return None

    def wait(self, timeout):
        self.wait_timeouts.append(timeout)
        raise subprocess.TimeoutExpired(cmd="fake-child", timeout=timeout)


class SupervisorTerminationEvidenceTests(unittest.TestCase):
    def test_post_sigkill_wait_timeout_is_stop_unknown(self):
        process = NeverReapedProcess()
        signals = []

        def record_signal(pid, sent_signal):
            signals.append((pid, sent_signal))

        with (
            mock.patch.object(SUPERVISOR.os, "killpg", side_effect=record_signal),
            mock.patch.object(SUPERVISOR.time, "monotonic", side_effect=[10.0, 10.1]),
        ):
            evidence = SUPERVISOR.terminate_group(process, child_start=9.0)

        self.assertEqual(
            signals,
            [
                (process.pid, signal.SIGTERM),
                (process.pid, signal.SIGKILL),
            ],
        )
        self.assertEqual(
            process.wait_timeouts,
            [SUPERVISOR.TERM_GRACE, SUPERVISOR.KILL_GRACE],
        )
        self.assertTrue(evidence["kill_escalated"])
        self.assertTrue(evidence["kill_wait_timeout"])
        self.assertFalse(evidence["stop_confirmed"])
        self.assertIsNone(evidence["stopped_seconds"])
        self.assertAlmostEqual(evidence["term_sent_seconds"], 1.0)
        self.assertAlmostEqual(evidence["kill_sent_seconds"], 1.1)


if __name__ == "__main__":
    unittest.main()

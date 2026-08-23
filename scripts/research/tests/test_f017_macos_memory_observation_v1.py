from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from scripts.research.f017_macos_memory_observation_v1 import (
    MAX_STDOUT_BYTES,
    MemoryObservationError,
    observe_vm_stat,
    parse_vm_stat,
)


def fixture(header="Mach Virtual Memory Statistics: (page size of 16384 bytes)", ending="."):
    return "\n".join(
        (
            header,
            f"Pages free: 1{ending}",
            f"Pages active: 99{ending}",
            f"Pages inactive: 2{ending}",
            f"Pages speculative: 3{ending}",
            f"Pages purgeable: 4{ending}",
        )
    ) + "\n"


class MemoryParserTests(unittest.TestCase):
    def test_current_header_and_formula(self):
        observed = parse_vm_stat(fixture(), observed_at_unix_ns=1)
        self.assertEqual(observed.page_size_bytes, 16384)
        self.assertEqual(observed.available_bytes, 16384 * (1 + 2 + 3 + 4))

    def test_4k_crlf_whitespace_period_zero_and_large(self):
        text = fixture("Mach Virtual Memory Statistics:\t(page size of 4096 bytes)   ", "")
        text = text.replace("Pages free: 1", "Pages free: 0").replace("Pages inactive: 2", "Pages inactive: 999999999999")
        observed = parse_vm_stat(text.replace("\n", "\r\n"))
        self.assertEqual(observed.page_size_bytes, 4096)
        self.assertEqual(observed.pages_free, 0)
        self.assertEqual(observed.pages_inactive, 999999999999)

    def test_old_parser_regression_vector(self):
        line = fixture().splitlines()[0]
        with self.assertRaises(ValueError):
            int(line.split()[-1].rstrip("."))
        self.assertEqual(parse_vm_stat(fixture()).page_size_bytes, 16384)

    def test_rejected_headers(self):
        bad = (
            "",
            "Pages free: 1.\n",
            "Mach Virtual Memory Statistics: page size of 16384 bytes)" ,
            "Mach Virtual Memory Statistics: (page size of 16384 bytes",
            "Mach Virtual Memory Statistics: (page size of bytes)",
            "Mach Virtual Memory Statistics: (page size of 0 bytes)",
            "Mach Virtual Memory Statistics: (page size of -1 bytes)",
            "Mach Virtual Memory Statistics: (page size of 1.5 bytes)",
            "Mach Virtual Memory Statistics: (page size of 1e4 bytes)",
            "Mach Virtual Memory Statistics: (page size of 0x4000 bytes)",
            "Mach Virtual Memory Statistics: (page size of １６３８４ bytes)",
            "Mach Virtual Memory Statistics: (page size of 16384 byte)",
            "Mach Virtual Memory Statistics: (page size of 16384 bytes) spoof",
            "Mach Virtual Memory Statistics: (page size of 16384 4096 bytes)",
        )
        for header in bad:
            with self.subTest(header=header), self.assertRaises(MemoryObservationError):
                parse_vm_stat(fixture(header))

    def test_header_must_be_first_nonempty_and_unique(self):
        with self.assertRaises(MemoryObservationError):
            parse_vm_stat("unexpected: 1.\n" + fixture())
        with self.assertRaises(MemoryObservationError):
            parse_vm_stat(fixture() + fixture().splitlines()[0] + "\n")

    def test_rejected_rows(self):
        base = fixture()
        cases = (
            base.replace("Pages purgeable: 4.\n", ""),
            base + "Pages free: 8.\n",
            base.replace("Pages free: 1.", "Pages free: -1."),
            base.replace("Pages free: 1.", "Pages free: 1.0."),
            base.replace("Pages free: 1.", "Pages free: 1e3."),
            base.replace("Pages free: 1.", "Pages free: 1. garbage"),
            base.replace("Pages free: 1.", "Pages free 1."),
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(MemoryObservationError):
                parse_vm_stat(value)

    def test_command_failures_timeout_stderr_and_bounds(self):
        completed = subprocess.CompletedProcess(["/usr/bin/vm_stat"], 1, b"", b"bad")
        with mock.patch("scripts.research.f017_macos_memory_observation_v1.subprocess.run", return_value=completed), self.assertRaises(MemoryObservationError):
            observe_vm_stat()
        with mock.patch("scripts.research.f017_macos_memory_observation_v1.subprocess.run", side_effect=subprocess.TimeoutExpired("vm_stat", 5)), self.assertRaises(MemoryObservationError):
            observe_vm_stat()
        completed = subprocess.CompletedProcess(["/usr/bin/vm_stat"], 0, fixture().encode(), b"warning")
        with mock.patch("scripts.research.f017_macos_memory_observation_v1.subprocess.run", return_value=completed), self.assertRaises(MemoryObservationError):
            observe_vm_stat()
        completed = subprocess.CompletedProcess(["/usr/bin/vm_stat"], 0, b"x" * (MAX_STDOUT_BYTES + 1), b"")
        with mock.patch("scripts.research.f017_macos_memory_observation_v1.subprocess.run", return_value=completed), self.assertRaises(MemoryObservationError):
            observe_vm_stat()

    @unittest.skipUnless(__import__("platform").system() == "Darwin", "macOS-only live observer")
    def test_live_vm_stat(self):
        observed = observe_vm_stat()
        self.assertIn(observed.page_size_bytes, (4096, 16384))
        self.assertGreaterEqual(observed.available_bytes, 0)


if __name__ == "__main__":
    unittest.main()

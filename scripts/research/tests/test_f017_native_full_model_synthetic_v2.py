#!/usr/bin/env python3
"""Receipt-v2 liveness mutations for the full-model synthetic qualifier."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.research.qualify_f017_native_full_model_synthetic_v2 import (
    COUNTERS,
    validate_run,
    validate_accounting_liveness,
)

ROOT = Path(__file__).resolve().parents[3]
V3 = ROOT / "docs/architecture/reviews/evidence/f017-native-full-model-synthetic-qualification-v3"
V3_AUTHORITY = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-native-tiny-full-model-inert-authority-v3.json"
V3_FIXTURE = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-native-tiny-full-model-v1.json"


class AccountingLiveness(unittest.TestCase):
    def test_all_zero_or_stale_pair_is_rejected(self) -> None:
        snapshot = {name: 0 for name in COUNTERS}
        with self.assertRaises(ValueError):
            validate_accounting_liveness(snapshot, snapshot)

    def test_required_live_lifecycle_is_accepted(self) -> None:
        before = {name: 0 for name in COUNTERS}
        after = dict(before)
        after.update(
            callback_count=2,
            managed_created=2,
            managed_destroyed=2,
            owned_stream_created=1,
            owned_stream_freed=1,
            native_owned_stream_freed=1,
            registrations=1,
            teardowns=1,
        )
        validate_accounting_liveness(before, after)

    def test_callback_or_native_free_spoof_is_rejected(self) -> None:
        before = {name: 0 for name in COUNTERS}
        after = dict(before)
        after.update(
            callback_count=1,
            managed_created=2,
            managed_destroyed=2,
            owned_stream_created=1,
            owned_stream_freed=1,
            native_owned_stream_freed=0,
            registrations=1,
            teardowns=1,
        )
        with self.assertRaises(ValueError):
            validate_accounting_liveness(before, after)

    def test_genuine_receipt_rewritten_to_all_zero_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            shutil.copytree(V3 / "run-01-state", state)
            summary = root / "summary.json"
            shutil.copy2(V3 / "run-01-summary.json", summary)
            authority = json.loads(V3_AUTHORITY.read_text())
            attempt = state / authority["attempt_id"]
            receipt_path = attempt / "execution-receipt.json"
            terminal_path = attempt / "terminal.json"
            os.chmod(receipt_path, 0o600)
            os.chmod(terminal_path, 0o600)
            receipt = json.loads(receipt_path.read_text())
            receipt["accounting_after"] = receipt["accounting_before"]
            receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
            terminal = json.loads(terminal_path.read_text())
            terminal["receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            terminal_path.write_text(json.dumps(terminal, sort_keys=True, separators=(",", ":")) + "\n")
            with self.assertRaises(ValueError):
                validate_run(
                    state,
                    summary,
                    hashlib.sha256(V3_FIXTURE.read_bytes()).hexdigest(),
                    authority,
                )


if __name__ == "__main__":
    unittest.main()

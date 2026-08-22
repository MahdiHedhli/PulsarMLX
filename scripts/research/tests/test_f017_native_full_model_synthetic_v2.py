#!/usr/bin/env python3
"""Receipt-v2 liveness mutations for the full-model synthetic qualifier."""

from __future__ import annotations

import unittest

from scripts.research.qualify_f017_native_full_model_synthetic_v2 import (
    COUNTERS,
    validate_accounting_liveness,
)


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


if __name__ == "__main__":
    unittest.main()

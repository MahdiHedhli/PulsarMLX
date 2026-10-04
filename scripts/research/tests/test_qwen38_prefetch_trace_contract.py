"""Synthetic-only contract cases; no model or third-party execution."""

import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_prefetch_trace_contract import ContractError, SCHEMA, compare_pair, validate  # noqa: E402


def trace(events):
    return {
        "schema": SCHEMA,
        "base_commit": "2d388856593b96a136fa5a6036c0e973919cedff",
        "model_revision": "synthetic-only",
        "tokenizer_revision": "synthetic-only",
        "runtime_revision": "synthetic-only",
        "prompt_digest": "prompt:synthetic",
        "decode_settings_digest": "decode:synthetic",
        "output_token_ids": [1, 2],
        "logits_digest": "logits:synthetic",
        "arm": "prefetch",
        "warmth": "logical-empty-os-warm",
        "max_prefetch_requests": 1,
        "max_prefetch_bytes": 64,
        "events": events,
        "metrics": {
            "physical_ssd_measurement": "unavailable",
            "physical_ssd_read_bytes": None,
            "logical_expert_read_bytes": 32,
            "prefetch_useful_bytes_before_demand": 32,
            "prefetch_late_bytes": 0,
            "prefetch_wasted_bytes": 0,
            "peak_footprint_bytes": 64,
            "swap_delta_bytes": 0,
            "ttft_ns": 20,
            "request_end_ns": 100,
            "decode_p50_ns": 1,
            "decode_p95_ns": 2,
            "decode_p99_ns": 3,
            "max_intertoken_stall_ns": 4,
        },
    }


def event(t, kind, key="L1:E2", **extra):
    return {"t_ns": t, "type": kind, "key": key, **extra}


class TraceContractTests(unittest.TestCase):
    def setUp(self):
        self.valid = [
            event(0, "route", selected=[2, 7], executed=[2, 7], weights_digest="weights:real"),
            event(1, "hint"),
            event(2, "prefetch_start", bytes=32),
            event(3, "prefetch_io_done"),
            event(4, "demand_queued"),
            event(5, "demand_start"),
            event(6, "prefetch_use"),
            event(7, "prefetch_gpu_done"),
            event(8, "buffer_release"),
        ]

    def test_complete_valid_trace(self):
        validate(trace(self.valid))

    def test_demand_has_priority(self):
        events = [self.valid[0], event(1, "hint"), event(2, "demand_queued", "L1:E7"), self.valid[2]]
        with self.assertRaisesRegex(ContractError, "overtook queued demand"):
            validate(trace(events))

    def test_promoted_inflight_hint_blocks_unrelated_prefetch(self):
        events = [self.valid[0], event(1, "hint"), event(2, "prefetch_start", bytes=32),
                  event(3, "demand_queued"), event(4, "demand_start"),
                  event(5, "hint", "L1:E3"), event(6, "prefetch_start", "L1:E3", bytes=16)]
        candidate = trace(events)
        candidate["max_prefetch_requests"] = 2
        with self.assertRaisesRegex(ContractError, "overtook waiting demand"):
            validate(candidate)

    def test_caps_include_inflight_buffer(self):
        events = self.valid[:3] + [event(3, "hint", "L1:E3"), event(4, "prefetch_start", "L1:E3", bytes=33)]
        candidate = trace(events)
        candidate["max_prefetch_requests"] = 2
        with self.assertRaisesRegex(ContractError, "cap exceeded"):
            validate(candidate)

    def test_request_cap_includes_completed_io_until_release(self):
        events = self.valid[:4] + [event(4, "hint", "L1:E3"), event(5, "prefetch_start", "L1:E3", bytes=1)]
        with self.assertRaisesRegex(ContractError, "cap exceeded"):
            validate(trace(events))

    def test_invalidated_hint_cannot_be_used(self):
        events = self.valid[:4] + [event(4, "hint_invalidate"), event(5, "prefetch_use")]
        with self.assertRaisesRegex(ContractError, "invalidated hint used"):
            validate(trace(events))

    def test_buffer_lifetime_includes_gpu_completion(self):
        events = self.valid[:7] + [event(7, "buffer_release")]
        with self.assertRaisesRegex(ContractError, "before completion"):
            validate(trace(events))

    def test_cancellation_invalidates_use_but_waits_for_io(self):
        events = self.valid[:3] + [event(3, "cancel", ""), event(4, "prefetch_use")]
        with self.assertRaisesRegex(ContractError, "before I/O completion"):
            validate(trace(events))
        events = self.valid[:3] + [event(3, "cancel", ""), event(4, "prefetch_io_done"), event(5, "prefetch_use")]
        with self.assertRaisesRegex(ContractError, "invalidated hint used"):
            validate(trace(events))
        candidate = trace(self.valid[:3] + [event(3, "cancel", ""), event(4, "prefetch_io_done"), event(5, "buffer_release")])
        candidate["metrics"]["prefetch_useful_bytes_before_demand"] = 0
        candidate["metrics"]["prefetch_wasted_bytes"] = 32
        validate(candidate)

    def test_route_remains_authoritative(self):
        events = [event(0, "route", selected=[2], executed=[3], weights_digest="weights:real")]
        with self.assertRaisesRegex(ContractError, "changed route"):
            validate(trace(events))

    def test_physical_io_cannot_be_inferred_from_logical_bytes(self):
        candidate = trace(self.valid)
        candidate["metrics"]["physical_ssd_measurement"] = "measured"
        with self.assertRaisesRegex(ContractError, "contradicts state"):
            validate(candidate)

    def test_useful_bytes_need_actual_demand_and_event_accounting(self):
        candidate = trace(self.valid)
        candidate["metrics"]["prefetch_useful_bytes_before_demand"] = 31
        with self.assertRaisesRegex(ContractError, "useful bytes disagree"):
            validate(candidate)
        events = self.valid[:4] + [event(4, "prefetch_use")]
        with self.assertRaisesRegex(ContractError, "without actual demand"):
            validate(trace(events))

    def test_late_prefetch_is_not_counted_useful(self):
        events = self.valid[:2] + [event(2, "prefetch_start", bytes=32), event(3, "demand_queued"),
                                   event(4, "demand_start"), event(5, "prefetch_io_done"),
                                   event(6, "prefetch_use"), event(7, "prefetch_gpu_done"),
                                   event(8, "buffer_release")]
        candidate = trace(events)
        candidate["metrics"]["prefetch_useful_bytes_before_demand"] = 0
        candidate["metrics"]["prefetch_late_bytes"] = 32
        validate(candidate)

    def test_pair_requires_same_route_outputs_and_identity(self):
        baseline = trace([deepcopy(self.valid[0])])
        baseline["arm"] = "baseline"
        baseline["metrics"]["prefetch_useful_bytes_before_demand"] = 0
        candidate = trace(self.valid)
        compare_pair(baseline, candidate)
        candidate["output_token_ids"] = [1, 3]
        with self.assertRaisesRegex(ContractError, "A/B mismatch: output_token_ids"):
            compare_pair(baseline, candidate)
        candidate["output_token_ids"] = [1, 2]
        candidate["events"][0]["weights_digest"] = "weights:different"
        with self.assertRaisesRegex(ContractError, "routing or weights differ"):
            compare_pair(baseline, candidate)


if __name__ == "__main__":
    unittest.main()

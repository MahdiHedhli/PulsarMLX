"""Bounded contention and lifetime acceptance; fake clocks/tiny files only."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_bounded_pager import BoundedPager, Limits, Observation, PagerProtocolError, PagerStop
from qwen38_adapter_memory import Budget, GIB
from qwen38_fixture_io import FixturePageStore
from qwen38_verified_files import VerifiedFiles
from test_qwen38_bounded_pager import E0, E1, E2, P0, synthetic_catalog
from test_qwen38_fixture_io import fixture, GOOD


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now


def setup_pager(*, fixed=0, inflight=2, staging=48):
    clock = Clock()
    p = BoundedPager(synthetic_catalog().page,
                     Limits(48 + fixed, staging, inflight, 3, 3, 480, 160,
                            fixed_model_bytes=fixed, demand_wait_ns=100), clock=clock)
    return p, clock


class BoundedWaitTests(unittest.TestCase):
    def test_inflight_actual_demand_defers_then_admits_after_finish(self):
        p, clock = setup_pager()
        p.demand(E0); first = p.next_io(); p.demand(E1)
        self.assertIsNone(p.next_io()); self.assertFalse(p.closed)
        self.assertEqual((p.staging_bytes, p.resident_bytes), (48, 0))
        p.complete_io(first)
        self.assertIsNone(p.next_io())  # Completed but still actual/unconsumed.
        lease = p.acquire(E0); p.mark_gpu_done(lease); p.release(lease); p.finish_demand(E0)
        second = p.next_io()
        self.assertEqual(second.spec.key, E1)
        self.assertNotIn(E0, p.resident)
        self.assertEqual(p.accounting()["reserved_weight_bytes"], 48)

    def test_gpu_lease_and_fixed_allowance_wait_for_release_and_finish(self):
        p, clock = setup_pager(fixed=48)
        p.demand(E0); p.complete_io(p.next_io()); lease = p.acquire(E0)
        p.demand(E1); self.assertIsNone(p.next_io())
        with self.assertRaises(PagerProtocolError): p.release(lease)
        p.mark_gpu_done(lease)
        self.assertIsNone(p.next_io())  # Acknowledgement alone cannot free it.
        p.release(lease)
        self.assertIsNone(p.next_io())  # Actual demand must also finish.
        p.finish_demand(E0)
        self.assertEqual(p.next_io().spec.key, E1)
        self.assertEqual(p.accounting()["reserved_weight_bytes"], 96)

    def test_wait_expiry_keeps_original_pending_io_until_completion(self):
        p, clock = setup_pager(); p.demand(E0); original = p.next_io(); p.demand(E1)
        clock.now = 99; self.assertIsNone(p.next_io())
        clock.now = 100
        with self.assertRaisesRegex(PagerStop, "wait expired"): p.check_waits()
        self.assertTrue(p.closed); self.assertEqual(p.staging_bytes, 48)
        self.assertEqual(p.accounting()["waiting_demands"], 0)
        before = p.accounting()
        with self.assertRaises(PagerProtocolError): p.complete_io(copy.copy(original))
        self.assertEqual(p.accounting(), before)
        p.complete_io(original)
        self.assertEqual((p.staging_bytes, p.resident_bytes), (0, 0))

    def test_wait_expiry_keeps_gpu_owner_until_original_completion(self):
        p, clock = setup_pager(); p.demand(E0); p.complete_io(p.next_io()); lease = p.acquire(E0)
        p.demand(E1); clock.now = 100
        with self.assertRaises(PagerStop): p.observe(Observation(100, 160, 0, False))
        self.assertEqual(p.resident_bytes, 48)
        with self.assertRaises(PagerProtocolError): p.release(lease)
        p.mark_gpu_done(lease); p.release(lease)
        self.assertEqual(p.resident_bytes, 0)

    def test_duplicate_and_unrelated_hint_activity_cannot_extend_deadline(self):
        p, clock = setup_pager(); p.demand(E0); first = p.next_io(); p.demand(E1)
        clock.now = 90; p.demand(E1); p.hint(E2); self.assertIsNone(p.next_io())
        p.complete_io(first)
        clock.now = 100
        with self.assertRaisesRegex(PagerStop, "wait expired"): p.next_io()

    def test_impossible_page_stops_even_when_io_slot_is_occupied(self):
        p, clock = setup_pager(inflight=1); p.demand(E0); ticket = p.next_io(); p.demand(P0)
        with self.assertRaisesRegex(PagerStop, "staging budget"): p.next_io()
        self.assertEqual(p.staging_bytes, 48)
        p.complete_io(ticket); self.assertEqual(p.staging_bytes, 0)

    def test_explicit_cancellation_drains_then_allows_new_request(self):
        p, clock = setup_pager(); p.demand(E0); old = p.next_io(); p.demand(E1)
        p.cancel_request()
        self.assertEqual(p.accounting()["waiting_demands"], 0)
        with self.assertRaises(PagerProtocolError): p.demand(E1)
        p.complete_io(old); clock.now = 1000
        p.demand(E1); new = p.next_io()
        self.assertEqual(new.spec.key, E1)
        with self.assertRaises(PagerProtocolError): p.complete_io(old)

    def test_demands_keep_priority_and_speculative_reservation_drains(self):
        p, clock = setup_pager()
        p.hint(E0); hint = p.next_io(); p.demand(E1); p.hint(E2)
        self.assertIsNone(p.next_io()); self.assertIn(E0, p.cancelled)
        p.complete_io(hint)
        self.assertEqual(p.next_io().spec.key, E1)
        self.assertEqual(p.hint_waste_bytes, 48)

    def test_promoted_hint_has_bounded_wait_until_io_completion(self):
        p, clock = setup_pager(); p.hint(E0); ticket = p.next_io(); p.demand(E0)
        clock.now = 99; self.assertIsNone(p.next_io())
        p.complete_io(ticket); clock.now = 100
        p.check_waits()
        self.assertFalse(p.closed); self.assertEqual(p.accounting()["waiting_demands"], 0)

    def test_original_ticket_and_lease_identity_are_scope_bound(self):
        p, clock = setup_pager(); p.demand(E0); ticket = p.next_io()
        before = p.accounting()
        for operation in (p.complete_io, p.fail_io):
            with self.assertRaises(PagerProtocolError): operation(copy.copy(ticket))
            self.assertEqual(p.accounting(), before)
        p.complete_io(ticket); lease = p.acquire(E0)
        q, _ = setup_pager(); q.demand(E0); q.complete_io(q.next_io()); foreign = q.acquire(E0)
        for copied in (int(lease), copy.copy(lease), foreign):
            with self.assertRaises(PagerProtocolError): p.mark_gpu_done(copied)
        p.mark_gpu_done(lease)
        with self.assertRaises(PagerProtocolError): p.release(int(lease))
        p.release(lease)

    def test_bad_clock_and_wait_configuration_fail_closed(self):
        for duration in (0, -1, True, 1.5):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                Limits(48, 48, 1, 1, 2, 480, 160, demand_wait_ns=duration)
        for value in (True, -1, 0.5):
            p, clock = setup_pager(); clock.now = value
            with self.subTest(value=value), self.assertRaises(PagerStop): p.demand(E0)
        p, clock = setup_pager(); clock.now = 5; p.demand(E0); clock.now = 4
        with self.assertRaises(PagerStop): p.check_waits()

    def test_resource_planning_gates_remain_unchanged(self):
        b = Budget()
        self.assertEqual((b.process_bytes, b.weight_bytes, b.headroom_bytes), (48*GIB, 40*GIB, 16*GIB))

    def test_generated_verified_fixture_competing_demand_preserves_exact_bytes(self):
        temp, root, catalog, blob = fixture()
        self.addCleanup(temp.cleanup)
        entries = [{"path": "synthetic.safetensors", "size_bytes": len(blob),
                    "sha256": hashlib.sha256(blob).hexdigest()}]
        clock = Clock()
        p = BoundedPager(catalog.page, Limits(48, 48, 2, 3, 3, 480, 160, demand_wait_ns=100), clock=clock)
        with VerifiedFiles(root, entries) as files:
            with FixturePageStore(root, files.file_sizes, p, lambda: GOOD, verified_files=files) as store:
                p.demand(E0); store.pump_one(); first = store.borrow(E0); p.demand(E1)
                self.assertIsNone(store.pump_one())
                self.assertEqual(store.accounting()["retained_host_buffer_bytes"], 48)
                store.gpu_done(first); store.release(first); p.finish_demand(E0)
                self.assertEqual(store.pump_one(), E1)
                second = store.borrow(E1)
                for span in catalog.page(E1).spans:
                    self.assertEqual(bytes(second.segments[span.tensor]), blob[span.offset:span.offset+span.length])
                store.gpu_done(second); store.release(second); p.finish_demand(E1)


if __name__ == "__main__": unittest.main()

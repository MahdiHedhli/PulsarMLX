"""Acceptance for the additive adapter contract; generated fixtures only."""
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_adapter_memory import GIB, Budget, MemoryLedger, MemoryStop, FreshObservation
from qwen38_adapter_session import SyntheticSession, SessionError
from qwen38_adapter_trace import SyntheticOperations, TraceError, validate
from qwen38_page_catalog import PageKey
from qwen38_adapter_fixture import Clock, Samples, make_bound

E0, E1, E2 = (PageKey("expert", 0, i) for i in range(3))


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.samples = Samples(self.clock)
        self.ledger = MemoryLedger(Budget(), self.samples, self.clock)

    def test_planning_limits_cannot_be_relaxed(self):
        self.assertEqual((Budget().process_bytes, Budget().weight_bytes, Budget().headroom_bytes),
                         (48 * GIB, 40 * GIB, 16 * GIB))
        for values in ({"process_bytes": 49 * GIB}, {"weight_bytes": 41 * GIB},
                       {"headroom_bytes": 15 * GIB}, {"other_bytes": 9 * GIB}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Budget(**values)

    def test_reservation_precedes_allocation_and_boundaries_stop_before_factory(self):
        self.samples.overrides["process_bytes"] = 48 * GIB - 24
        token = self.ledger.reserve("page", 24)
        self.ledger.allocate(token)
        with mock.patch("qwen38_adapter_memory.bytearray", create=True) as allocate:
            with self.assertRaises(MemoryStop): self.ledger.reserve("page", 25)
            allocate.assert_not_called()
        self.ledger.retire(token)

    def test_weight_other_headroom_and_runtime_gates(self):
        for kind, size, overrides in (("fixed", 40 * GIB + 1, {}),
                                      ("runtime", 8 * GIB + 1, {}),
                                      ("page", 1, {"headroom_bytes": 16 * GIB}),
                                      ("page", 1, {"runtime_bytes": 8 * GIB + 1}),
                                      ("page", 1, {"mlx_cache_bytes": 48 * GIB + 1})):
            with self.subTest(kind=kind, overrides=overrides):
                samples = Samples(self.clock); samples.overrides.update(overrides)
                ledger = MemoryLedger(Budget(), samples, self.clock)
                with self.assertRaises(MemoryStop):
                    ledger.reserve(kind, size)
                self.assertEqual(ledger.counts()["total_bytes"], 0)

    def test_bad_missing_stale_future_replayed_and_wrong_provenance_samples(self):
        overrides = [{"sampled_at_ns": 0}, {"sampled_at_ns": 10**12},
                     {"units": "KiB"}, {"process_source": "pager-counter"},
                     {"process_bytes": True}, {"mlx_live_bytes": -1}, {"pressure": 1}]
        for change in overrides:
            with self.subTest(change=change):
                samples = Samples(self.clock); samples.overrides.update(change)
                ledger = MemoryLedger(Budget(max_age_ns=100), samples, self.clock)
                with self.assertRaises(MemoryStop): ledger.check()
        self.ledger.check()
        self.samples.overrides["sequence"] = self.samples.sequence
        with self.assertRaises(MemoryStop): self.ledger.check()
        missing = MemoryLedger(Budget(), lambda: None, self.clock)
        with self.assertRaises(MemoryStop): missing.check()

    def test_pressure_swap_growth_and_provider_failure_stop(self):
        for change in ({"pressure": True}, {"swap_bytes": 1}):
            with self.subTest(change=change):
                samples = Samples(self.clock); ledger = MemoryLedger(Budget(), samples, self.clock)
                ledger.check(); samples.overrides.update(change)
                with self.assertRaises(MemoryStop): ledger.check()
        self.samples.failure = OSError("sample unavailable")
        with self.assertRaises(MemoryStop): self.ledger.check()

    def test_derived_views_keep_allocation_counted_after_parent_release(self):
        owner = self.ledger.reserve("page", 32); self.ledger.allocate(owner)
        parent = self.ledger.view(owner); child = parent[1:]; grandchild = child[1:]
        parent.release()
        self.assertFalse(self.ledger.retire(owner))
        self.assertEqual(self.ledger.counts()["weight_bytes"], 32)
        child.release(); self.ledger.collect()
        self.assertEqual(self.ledger.counts()["weight_bytes"], 32)
        grandchild.release(); self.ledger.collect()
        self.assertEqual(self.ledger.counts()["total_bytes"], 0)

    def test_retire_all_reports_exported_owner_and_retires_other_owners(self):
        retained = self.ledger.reserve("page", 32); self.ledger.allocate(retained)
        free = self.ledger.reserve("page", 16); self.ledger.allocate(free)
        child = self.ledger.view(retained)[1:]
        with self.assertRaisesRegex(BufferError, "retains exported views"):
            self.ledger.retire_all()
        self.assertEqual(self.ledger.counts()["total_bytes"], 32)
        self.assertEqual(self.ledger.counts()["retired_bytes"], 32)
        child.release(); self.ledger.collect()
        self.assertEqual(self.ledger.counts()["total_bytes"], 0)

    def test_identity_and_allocator_failure_cleanup(self):
        owner = self.ledger.reserve("fixed", 4)
        with self.assertRaises(ValueError): self.ledger.allocate(copy.copy(owner))
        with mock.patch("qwen38_adapter_memory.bytearray", side_effect=MemoryError("allocation"), create=True):
            with self.assertRaises(MemoryError): self.ledger.allocate(owner)
        self.assertEqual(self.ledger.counts()["total_bytes"], 0)

    def test_exact_weight_and_other_boundaries_with_counter_only_reservations(self):
        for kind, size in (("fixed", 40 * GIB), ("runtime", 8 * GIB)):
            with self.subTest(kind=kind):
                samples = Samples(self.clock); samples.overrides["headroom_bytes"] = 64 * GIB
                ledger = MemoryLedger(Budget(), samples, self.clock)
                token = ledger.reserve(kind, size)  # Never materializes a GiB allocation.
                with self.assertRaises(MemoryStop): ledger.reserve(kind, 1)
                ledger.retire(token)
                self.assertEqual(ledger.counts()["total_bytes"], 0)

    def test_future_owner_cannot_materialize_after_reservation_sample_expires(self):
        owner = self.ledger.reserve("page", 8)
        self.samples.overrides["sampled_at_ns"] = 0
        self.clock.value = 100_000_000
        with mock.patch("qwen38_adapter_memory.bytearray", create=True) as factory:
            with self.assertRaises(MemoryStop): self.ledger.allocate(owner)
            factory.assert_not_called()
        self.ledger.retire(owner)

    def test_sample_taken_during_provider_call_is_not_future_dated(self):
        def sample():
            observation = self.samples()
            values = dict(vars(observation), sampled_at_ns=self.clock())
            return FreshObservation(**values)
        ledger = MemoryLedger(Budget(), sample, self.clock)
        ledger.check()


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qwen-adapter-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bound, self.contents = make_bound(self.root)
        self.addCleanup(self.bound.close)
        self.clock = Clock(); self.samples = Samples(self.clock)
        self.ops = SyntheticOperations(routes={(0, 0): ((0,), (1.0,)), (1, 0): ((1,), (1.0,)),
                                                (2, 0): ((0,), (1.0,))}, ple_rows={(0, 0): 7})
        self.session = SyntheticSession(self.bound, self.ops, self.samples, self.clock)
        self.addCleanup(self.session.close)

    def use(self, demand):
        while not self.session.is_resident(demand): self.session.pump_one()
        borrow = self.session.borrow(demand)
        self.session.complete(borrow, borrow.completion)
        self.session.release(borrow)
        return borrow

    def finish(self):
        self.session.close()
        report = self.session.report()
        validate(report, self.session.catalog, self.ops)
        return report

    def test_exact_fixed_and_cross_file_expert_ple_operations(self):
        view = self.session.fixed_view("language_model.model.norm.weight")
        ref = self.bound.catalog.tensors["language_model.model.norm.weight"]
        self.assertEqual(bytes(view), self.contents[ref.filename][ref.data_start+ref.start:ref.data_start+ref.end])
        view.release()
        demand = self.session.route(0, 0)[0]
        self.session.pump_one(); borrow = self.session.borrow(demand)
        expected = b"".join(self.contents[s.filename][s.offset:s.offset+s.length] for s in self.session.catalog.page(E0).spans)
        self.assertEqual(b"".join(bytes(v) for v in borrow.segments.values()), expected)
        self.session.complete(borrow, borrow.completion); self.session.release(borrow)
        self.use(self.session.ple(0, 0))
        self.finish()

    def test_useful_late_and_wasted_hint_reconcile_eviction(self):
        self.session.hint(E0); self.session.pump_one(); self.use(self.session.route(0, 0)[0])
        self.session.hint(E1); ticket = self.session.begin_read()
        demand = self.session.route(1, 0)[0]; self.session.finish_read(ticket); self.use(demand)
        self.session.hint(E2); self.session.pump_one(); self.session.evict(E2)
        report = self.finish(); n = self.session.catalog.page(E0).size_bytes
        self.assertEqual(report["hint_bytes"], {"admitted": n*3, "useful": n, "late": n, "wasted": n})

    def test_repeat_demand_cache_hit_and_actual_ple_mapping(self):
        self.use(self.session.route(0, 0)[0]); self.use(self.session.route(2, 0)[0])
        ple = self.session.ple(0, 0)
        self.assertEqual(ple.key, self.session.catalog.ple_key_for_global_row(7))
        self.use(ple); self.finish()

    def test_waiting_promoted_demand_blocks_unrelated_hint(self):
        self.session.hint(E0); ticket = self.session.begin_read()
        demand = self.session.route(0, 0)[0]; self.session.hint(E2)
        self.assertIsNone(self.session.begin_read())
        self.session.finish_read(ticket); self.use(demand); self.finish()

    def test_forged_tickets_demands_borrows_completions_are_rejected(self):
        demand = self.session.route(0, 0)[0]; ticket = self.session.begin_read()
        with self.assertRaises(SessionError): self.session.finish_read(copy.copy(ticket))
        self.session.finish_read(ticket)
        with self.assertRaises(SessionError): self.session.borrow(copy.copy(demand))
        borrow = self.session.borrow(demand)
        for b, c in ((copy.copy(borrow), borrow.completion), (borrow, copy.copy(borrow.completion))):
            with self.assertRaises(SessionError): self.session.complete(b, c)
        with self.assertRaises(SessionError): self.session.release(borrow)
        self.session.complete(borrow, borrow.completion); self.session.release(borrow); self.finish()

    def test_device_duplicate_and_derived_owner_survive_cancel_until_drain(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one(); borrow = self.session.borrow(demand)
        child = next(iter(borrow.segments.values()))[1:]
        n = self.session.catalog.page(E0).size_bytes
        self.assertGreaterEqual(self.session.ledger.counts()["weight_bytes"], 2*n + 4)
        self.session.cancel()
        with self.assertRaises(SessionError): self.session.route(1, 0)
        self.session.complete(borrow, borrow.completion); self.session.release(borrow)
        self.session.close()
        self.assertEqual(self.session.ledger.counts()["weight_bytes"], n)
        child.release(); self.session.collect()
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        validate(self.session.report(), self.session.catalog, self.ops)

    def test_cancel_pending_hint_does_not_read_or_adopt_ticket(self):
        self.session.hint(E2); ticket = self.session.begin_read(); self.session.cancel()
        with mock.patch("qwen38_adapter_session.BoundCheckpoint.read_page_into", side_effect=AssertionError("must not read")):
            self.session.finish_read(ticket)
        with self.assertRaises(SessionError): self.session.finish_read(ticket)
        report = self.finish()
        self.assertEqual(report["hint_bytes"]["wasted"], ticket.size_bytes)

    def test_changed_files_catalog_and_partial_read_failure_stop_cleanup(self):
        self.session.hint(E0); ticket = self.session.begin_read()
        def partial(key, target):
            target[:1] = b"x"
            raise OSError("partial read")
        with mock.patch("qwen38_adapter_session.BoundCheckpoint.read_page_into", side_effect=partial):
            with self.assertRaisesRegex(OSError, "partial read"): self.session.finish_read(ticket)
        self.assertTrue(self.bound.files.closed)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        report = self.session.report(); validate(report, self.session.catalog, self.ops)
        self.assertEqual(report["hint_bytes"]["wasted"], ticket.size_bytes)

    def test_identity_replacement_and_catalog_mutation_fail_closed(self):
        self.session.hint(E0)
        self.bound.catalog.ple_rows_per_page = 3
        with self.assertRaises(SessionError): self.session.pump_one()
        self.assertTrue(self.bound.files.closed)

    def test_observation_failure_before_allocation_and_after_read(self):
        self.session.hint(E0)
        self.samples.failure = OSError("unavailable")
        with mock.patch("qwen38_adapter_session.BoundCheckpoint.read_page_into") as read:
            with self.assertRaises(MemoryStop): self.session.pump_one()
            read.assert_not_called()
        self.assertTrue(self.bound.files.closed)

    def test_failure_cleanup_keeps_original_and_attempts_all_descriptors(self):
        self.session.hint(E0); ticket = self.session.begin_read()
        real_close = os.close; closed = []
        def closing(fd):
            closed.append(fd); real_close(fd)
            if len(closed) == 1: raise OSError("close failure")
        with mock.patch("qwen38_adapter_session.BoundCheckpoint.read_page_into", side_effect=OSError("read failure")), \
             mock.patch("qwen38_verified_files.os.close", side_effect=closing):
            with self.assertRaisesRegex(OSError, "read failure") as caught: self.session.finish_read(ticket)
        self.assertEqual(len(closed), 4)
        self.assertTrue(any("close failure" in n for n in caught.exception.__notes__))
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)

    def test_trace_rejects_forged_route_ple_bytes_and_completions(self):
        self.session.hint(E0); self.session.pump_one(); self.use(self.session.route(0, 0)[0])
        self.use(self.session.ple(0, 0)); report = self.finish()
        for kind, field, value in (("route", "selected", [2]), ("ple", "global_row", 0),
                                   ("read_start", "bytes", 1), ("completion", "lease", 999),
                                   ("borrow", "payload_sha256", "0"*64)):
            changed = copy.deepcopy(report)
            event = next(e for e in changed["events"] if e["type"] == kind); event[field] = value
            with self.subTest(kind=kind), self.assertRaises(TraceError): validate(changed, self.session.catalog, self.ops)
        changed = copy.deepcopy(report); changed["file_signature"] = "0" * 64
        with self.assertRaises(TraceError): validate(changed, self.session.catalog, self.ops)

    def test_same_page_hint_can_be_readmitted_after_eviction(self):
        self.session.hint(E0); self.session.pump_one(); self.session.evict(E0)
        self.session.hint(E0); self.session.pump_one(); self.use(self.session.route(0, 0)[0])
        report = self.finish(); n = self.session.catalog.page(E0).size_bytes
        self.assertEqual(report["hint_bytes"], dict(admitted=2*n, useful=n, late=0, wasted=n))

    def test_changed_content_mode_replacement_symlink_and_closed_binding(self):
        cases = ("content", "mode", "replacement", "symlink", "closed")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="qwen-adapter-change-") as temp:
                bound, contents = make_bound(Path(temp)); session = SyntheticSession(bound, self.ops, self.samples, self.clock)
                path = Path(temp) / "a.safetensors"
                if case == "content": path.write_bytes(contents[path.name][:-1] + b"!")
                elif case == "mode": path.chmod(path.stat().st_mode ^ 0o100)
                elif case == "replacement":
                    replacement = Path(temp)/"replacement"; replacement.write_bytes(contents[path.name]); replacement.replace(path)
                elif case == "symlink": path.unlink(); path.symlink_to(Path(temp)/"b.safetensors")
                else: bound.close()
                with self.assertRaises(Exception): session.hint(E0)
                self.assertTrue(bound.files.closed)
                self.assertEqual(session.ledger.counts()["total_bytes"], 0)

    def test_mutated_derived_catalog_rows_rejected_before_exposure(self):
        self.bound.catalog.ple_rows[0] = 999
        with self.assertRaises(SessionError): self.session.fixed_view("language_model.model.norm.weight")
        self.assertTrue(self.bound.files.closed)

    def test_bound_rebinding_and_missing_marker_reject_and_close(self):
        for case in ("binding", "marker", "cap", "closed"):
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="qwen-adapter-rebind-") as temp:
                bound, _ = make_bound(Path(temp))
                if case == "binding": bound.catalog._verified_files = None
                elif case == "marker":
                    # Simulates a bound input without the authenticated fixture
                    # entry. No real or large file is opened or hashed.
                    bound.files.entries = {name: entry for name, entry in bound.files.entries.items() if name != ".qwen38-synthetic-fixture"}
                elif case == "closed": bound.close()
                if case == "cap":
                    with mock.patch("qwen38_adapter_session.MAX_FIXTURE_BYTES", 1):
                        with self.assertRaises(SessionError): SyntheticSession(bound, self.ops, self.samples, self.clock)
                else:
                    with self.assertRaises(SessionError): SyntheticSession(bound, self.ops, self.samples, self.clock)
                self.assertTrue(bound.files.closed)

    def test_post_read_observation_overage_discards_before_borrow(self):
        from qwen38_page_catalog import BoundCheckpoint
        original = BoundCheckpoint.read_page_into
        demand = self.session.route(0, 0)[0]; ticket = self.session.begin_read()
        def read(bound, key, target):
            original(bound, key, target)
            self.samples.overrides["process_bytes"] = 48 * GIB + 1
        with mock.patch("qwen38_adapter_session.BoundCheckpoint.read_page_into", new=read):
            with self.assertRaises(MemoryStop): self.session.finish_read(ticket)
        with self.assertRaises(SessionError): self.session.borrow(demand)
        self.assertTrue(self.bound.files.closed)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        validate(self.session.report(), self.session.catalog, self.ops)

    def test_duplicate_device_bytes_must_fit_before_factory(self):
        self.session.close()
        with tempfile.TemporaryDirectory(prefix="qwen-adapter-duplicate-") as temp:
            bound, _ = make_bound(Path(temp))
            session = SyntheticSession(bound, self.ops, self.samples, self.clock, budget=Budget(weight_bytes=48))
            demand = session.route(0, 0)[0]; session.pump_one()
            self.assertEqual(session.ledger.counts()["weight_bytes"], 28)
            with mock.patch("qwen38_adapter_memory.bytearray", create=True) as factory:
                with self.assertRaises(MemoryStop): session.borrow(demand)
                factory.assert_not_called()
            self.assertEqual(session.ledger.counts()["total_bytes"], 0)
            validate(session.report(), session.catalog, self.ops)

    def test_close_retains_active_completion_and_refuses_false_terminal_report(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one(); borrow = self.session.borrow(demand)
        self.session.close()
        self.assertTrue(self.bound.files.closed)
        self.assertEqual(self.session.ledger.counts()["weight_bytes"], 48)
        with self.assertRaises(TraceError): validate(self.session.report(), self.session.catalog, self.ops)
        self.session.complete(borrow, borrow.completion); self.session.release(borrow)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        validate(self.session.report(), self.session.catalog, self.ops)

    def test_unpublished_borrow_on_trace_failure_does_not_leak_owners(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one()
        original = self.session.tape.emit
        def emit(kind, **fields):
            if kind == "borrow": raise TraceError("injected trace cap")
            return original(kind, **fields)
        with mock.patch.object(self.session.tape, "emit", side_effect=emit):
            with self.assertRaises(TraceError): self.session.borrow(demand)
        self.assertFalse(self.session._borrows)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        validate(self.session.report(), self.session.catalog, self.ops)

    def test_numeric_type_forgery_duplicate_operation_and_missing_terminal_fail(self):
        self.session.hint(E0); self.session.pump_one(); self.use(self.session.route(0, 0)[0])
        report = self.finish()
        for kind, field, value in (("route", "layer", False), ("route", "weights", [1]),
                                   ("borrow", "device_bytes", 24.0), ("hint_terminal", "bytes", 24.0)):
            changed = copy.deepcopy(report); next(e for e in changed["events"] if e["type"] == kind)[field] = value
            with self.subTest(field=field), self.assertRaises(TraceError): validate(changed, self.session.catalog, self.ops)
        changed = copy.deepcopy(report); changed["events"] = [e for e in changed["events"] if e["type"] != "hint_terminal"]
        with self.assertRaises(TraceError): validate(changed, self.session.catalog, self.ops)
        with self.assertRaises(Exception): self.ops.routes = {}

    def test_view_creation_failure_releases_unpublished_exports(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one()
        original = __import__("qwen38_adapter_session")._segment
        calls = 0
        def segment(parent, start, end):
            nonlocal calls
            calls += 1
            if calls == 2: raise MemoryError("segment allocation")
            return original(parent, start, end)
        with mock.patch("qwen38_adapter_session._segment", side_effect=segment):
            with self.assertRaises(MemoryError): self.session.borrow(demand)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        validate(self.session.report(), self.session.catalog, self.ops)

    def test_device_export_failure_releases_original_view(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one()
        original = self.session.ledger.writable
        def writable(owner):
            if owner.kind == "device": raise MemoryError("device view")
            return original(owner)
        with mock.patch.object(self.session.ledger, "writable", side_effect=writable):
            with self.assertRaises(MemoryError): self.session.borrow(demand)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)

    def test_retirement_error_keeps_owner_counted_and_can_drain_without_duplicate_trace(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one(); borrow = self.session.borrow(demand)
        self.session.complete(borrow, borrow.completion)
        original = self.session.ledger.retire
        failed = False
        def retire(owner):
            nonlocal failed
            if owner.kind == "device" and not failed:
                failed = True
                raise MemoryError("device retire")
            return original(owner)
        with mock.patch.object(self.session.ledger, "retire", side_effect=retire):
            with self.assertRaises(MemoryError): self.session.release(borrow)
        self.assertTrue(self.bound.files.closed)
        self.assertEqual(self.session.ledger.counts()["weight_bytes"], 48)
        self.session.release(borrow)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)
        report = self.session.report()
        self.assertEqual(sum(e["type"] == "release" for e in report["events"]), 1)
        validate(report, self.session.catalog, self.ops)

    def test_fixed_payload_initialization_failure_closes_bound_handles(self):
        with tempfile.TemporaryDirectory(prefix="qwen-adapter-fixed-fail-") as temp:
            bound, _ = make_bound(Path(temp))
            with mock.patch.object(bound.files, "readinto", side_effect=OSError("fixed read")):
                with self.assertRaisesRegex(OSError, "fixed read"):
                    SyntheticSession(bound, self.ops, self.samples, self.clock)
            self.assertTrue(bound.files.closed)

    def test_multi_expert_operation_preserves_weights_and_demand_priority(self):
        self.session.close()
        ops = SyntheticOperations(routes={(0, 0): ((0, 2), (0.25, 0.75))}, ple_rows={})
        with tempfile.TemporaryDirectory(prefix="qwen-adapter-routes-") as temp:
            bound, _ = make_bound(Path(temp)); session = SyntheticSession(bound, ops, self.samples, self.clock)
            demands = session.route(0, 0); session.hint(E1)
            first, second = session.begin_read(), session.begin_read()
            self.assertEqual((first.key, second.key), (E0, E2))
            self.assertIsNone(session.begin_read())
            for ticket, demand in zip((first, second), demands):
                session.finish_read(ticket); borrow = session.borrow(demand)
                session.complete(borrow, borrow.completion); session.release(borrow)
            session.close(); report = session.report(); validate(report, session.catalog, ops)
            event = next(e for e in report["events"] if e["type"] == "route")
            self.assertEqual(event["weights"], [0.25, 0.75])
            self.assertEqual(report["hint_bytes"]["admitted"], 0)

    def test_readonly_view_object_mutation_cannot_silently_change_next_acquisition(self):
        demand = self.session.route(0, 0)[0]; self.session.pump_one(); borrow = self.session.borrow(demand)
        original_buffer = next(iter(borrow.segments.values())).obj
        self.session.complete(borrow, borrow.completion); self.session.release(borrow)
        original_buffer[0] ^= 1
        with self.assertRaisesRegex(SessionError, "cached payload changed"):
            self.session.borrow(self.session.route(2, 0)[0])
        self.assertTrue(self.bound.files.closed)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)

    def test_fixed_view_object_mutation_is_rejected(self):
        view = self.session.fixed_view("language_model.model.norm.weight")
        view.obj[0] ^= 1; view.release()
        with self.assertRaisesRegex(SessionError, "fixed payload changed"):
            self.session.fixed_view("language_model.model.norm.weight")
        self.assertTrue(self.bound.files.closed)
        self.assertEqual(self.session.ledger.counts()["total_bytes"], 0)


if __name__ == "__main__":
    unittest.main()

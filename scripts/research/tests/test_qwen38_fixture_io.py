"""Actual preadv on tiny synthetic files; never points at model weights."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_bounded_pager import (  # noqa: E402
    BoundedPager, Limits, Observation, PagerProtocolError, PagerStop,
)
from qwen38_fixture_io import FixturePageStore, MARKER, MARKER_CONTENT  # noqa: E402
from qwen38_page_catalog import ByteSpan, PageKey, PageSpec  # noqa: E402
from test_qwen38_bounded_pager import E0, E1, E2, P0, synthetic_catalog  # noqa: E402


GOOD = Observation(process_bytes=100, system_headroom_bytes=160,
                   swap_delta_bytes=0, memory_pressure=False)


def fixture():
    temp = tempfile.TemporaryDirectory(prefix="qwen38-synthetic-")
    root = Path(temp.name)
    (root / MARKER).write_text(MARKER_CONTENT)
    catalog = synthetic_catalog()
    end = max(ref.data_start + ref.end for ref in catalog.tensors.values())
    blob = bytearray(end)
    for name, ref in catalog.tensors.items():
        for row in range(ref.shape[0]):
            offset = ref.data_start + ref.start + row * ref.row_bytes
            blob[offset:offset + ref.row_bytes] = bytes([(sum(name.encode()) + row) % 256]) * ref.row_bytes
    (root / "synthetic.safetensors").write_bytes(blob)
    return temp, root, catalog, bytes(blob)


def pager(catalog, *, weight=192):
    return BoundedPager(catalog.page, Limits(weight, min(weight, 128), 2, 3, 3, 480, 160))


class FixtureIoTests(unittest.TestCase):
    def setUp(self):
        self.temp, self.root, self.catalog, self.blob = fixture()
        self.addCleanup(self.temp.cleanup)
        self.files = {"synthetic.safetensors": len(self.blob)}

    def test_exact_expert_segments_and_gpu_lifetime(self):
        p = pager(self.catalog)
        with FixturePageStore(self.root, self.files, p, lambda: GOOD) as store:
            p.demand(E1)
            self.assertEqual(store.pump_one(), E1)
            self.assertEqual(store.pump_one(), None)
            self.assertEqual(store.accounting()["retained_host_buffer_bytes"], 48)
            borrow = store.borrow(E1)
            for span in self.catalog.page(E1).spans:
                view = borrow.segments[span.tensor]
                self.assertTrue(view.readonly)
                self.assertEqual(bytes(view), self.blob[span.offset:span.offset + span.length])
            with self.assertRaisesRegex(PagerProtocolError, "before GPU"):
                store.release(borrow)
            with self.assertRaisesRegex(PagerProtocolError, "cannot close"):
                store.close()
            store.gpu_done(borrow)
            store.release(borrow)
            self.assertFalse(borrow.segments)
            p.finish_demand(E1)

    def test_hint_bytes_cannot_be_borrowed_without_actual_demand(self):
        p = pager(self.catalog)
        with FixturePageStore(self.root, self.files, p, lambda: GOOD) as store:
            p.hint(E0)
            store.pump_one()
            with self.assertRaisesRegex(PagerProtocolError, "not demanded"):
                store.borrow(E0)
            p.demand(E0)
            self.assertIsNone(store.pump_one())  # already resident; no second read.
            borrow = store.borrow(E0)
            store.gpu_done(borrow)
            store.release(borrow)

    def test_ple_row_block_reads_exact_affine_segments(self):
        p = pager(self.catalog)
        with FixturePageStore(self.root, self.files, p, lambda: GOOD) as store:
            key = self.catalog.ple_key_for_global_row(3)
            self.assertEqual(key, P0)
            p.demand(key)
            store.pump_one()
            borrow = store.borrow(key)
            spans = self.catalog.page(key).spans
            self.assertEqual(len(spans), 3)
            for span in spans:
                self.assertEqual(bytes(borrow.segments[span.tensor]),
                                 self.blob[span.offset:span.offset + span.length])
            store.gpu_done(borrow)
            store.release(borrow)

    def test_cross_file_segments_keep_tensor_order(self):
        other = bytes(range(32))
        (self.root / "second.bin").write_bytes(other)
        files = {**self.files, "second.bin": len(other)}
        spec = PageSpec(E0, (ByteSpan("synthetic.safetensors", 19, 5, "a.weight"),
                             ByteSpan("second.bin", 7, 9, "b.scales")))
        p = BoundedPager(lambda key: spec, Limits(96, 48, 1, 1, 1, 480, 160))
        with FixturePageStore(self.root, files, p, lambda: GOOD) as store:
            p.demand(E0)
            store.pump_one()
            borrow = store.borrow(E0)
            self.assertEqual(bytes(borrow.segments["a.weight"]), self.blob[19:24])
            self.assertEqual(bytes(borrow.segments["b.scales"]), other[7:16])
            store.gpu_done(borrow)
            store.release(borrow)

    def test_short_read_stops_and_releases_reservation(self):
        p = pager(self.catalog)
        with FixturePageStore(self.root, self.files, p, lambda: GOOD) as store:
            (self.root / "synthetic.safetensors").write_bytes(self.blob[:32])
            p.demand(E1)
            with self.assertRaisesRegex(PagerProtocolError, "short or invalid"):
                store.pump_one()
            self.assertTrue(p.closed)
            self.assertEqual(p.accounting()["staging_bytes"], 0)
            self.assertFalse(store.buffers)

    def test_out_of_range_span_is_rejected_before_read(self):
        bad = PageSpec(E0, (ByteSpan("synthetic.safetensors", len(self.blob), 4, "bad.weight"),))
        p = BoundedPager(lambda key: bad, Limits(96, 48, 1, 1, 1, 480, 160))
        with FixturePageStore(self.root, self.files, p, lambda: GOOD) as store:
            p.demand(E0)
            with self.assertRaisesRegex(PagerProtocolError, "outside admitted fixture"):
                store.pump_one()
            self.assertTrue(p.closed)

    def test_post_read_pressure_discards_buffer_and_ticket(self):
        p = pager(self.catalog)
        observations = iter([GOOD, Observation(481, 160, 0, False)])
        with FixturePageStore(self.root, self.files, p, lambda: next(observations)) as store:
            p.demand(E1)
            with self.assertRaisesRegex(PagerStop, "observed process"):
                store.pump_one()
            self.assertTrue(p.closed)
            self.assertFalse(store.buffers)
            self.assertEqual(p.accounting()["staging_bytes"], 0)

    def test_missing_memory_observation_fails_before_io(self):
        p = pager(self.catalog)

        def unavailable():
            raise RuntimeError("sampler unavailable")

        with FixturePageStore(self.root, self.files, p, unavailable) as store:
            p.demand(E0)
            with self.assertRaisesRegex(PagerStop, "observation failed"):
                store.pump_one()
            self.assertTrue(p.closed)
            self.assertEqual(p.accounting()["inflight_requests"], 0)

    def test_eviction_releases_store_owned_idle_buffer(self):
        p = pager(self.catalog, weight=96)
        with FixturePageStore(self.root, self.files, p, lambda: GOOD) as store:
            p.hint(E0)
            store.pump_one()
            p.demand(E1)
            store.pump_one()
            p.finish_demand(E1)
            p.demand(E2)
            store.pump_one()
            self.assertNotIn(E0, store.buffers)
            self.assertEqual(set(store.buffers), {E1, E2})
            self.assertEqual(store.accounting()["retained_host_buffer_bytes"], 96)

    def test_unmarked_directory_and_symlink_refused(self):
        p = pager(self.catalog)
        (self.root / MARKER).unlink()
        with self.assertRaisesRegex(PagerProtocolError, "marker"):
            FixturePageStore(self.root, self.files, p, lambda: GOOD)
        (self.root / MARKER).write_text(MARKER_CONTENT)
        (self.root / "synthetic.safetensors").unlink()
        (self.root / "synthetic.safetensors").symlink_to(self.root / MARKER)
        with self.assertRaisesRegex(PagerProtocolError, "identity"):
            FixturePageStore(self.root, self.files, p, lambda: GOOD)


if __name__ == "__main__":
    unittest.main()

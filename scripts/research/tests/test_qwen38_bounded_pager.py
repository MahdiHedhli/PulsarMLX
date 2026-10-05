"""Adversarial synthetic page tests; no model, MLX, or checkpoint payload."""

import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_bounded_pager import (  # noqa: E402
    BoundedPager, Limits, Observation, PagerProtocolError, PagerStop,
)
from qwen38_page_catalog import (  # noqa: E402
    ByteSpan, CatalogError, PageCatalog, PageKey, PageSpec, TensorRef, admit_checkpoint,
)


def synthetic_catalog(*, rows=9, ple_page_rows=4):
    tensors = {}
    offset = 0

    def triple(prefix, first_dim):
        nonlocal offset
        for suffix, dtype, row_bytes in (("weight", "U32", 8),
                                         ("scales", "BF16", 4),
                                         ("biases", "BF16", 4)):
            tensors[f"{prefix}.{suffix}"] = TensorRef(
                "synthetic.safetensors", 16, dtype, (first_dim, 2), offset,
                offset + first_dim * row_bytes)
            offset += first_dim * row_bytes

    for layer in range(2):
        for projection in ("gate_proj", "up_proj", "down_proj"):
            triple(f"language_model.model.layers.{layer}.mlp.switch_mlp.{projection}", 3)
    for shard in range(2):
        triple(f"language_model.model.layers.1.ple.ple_embedding.ngram_embedding.shard_{shard}", rows)
    return PageCatalog(tensors, layers=2, experts=3, ple_layer=1,
                       ple_shards=2, ple_rows_per_page=ple_page_rows)


def pager(*, weight=192, staging=128, inflight=2):
    catalog = synthetic_catalog()
    limits = Limits(weight, staging, inflight, 3, 3, 480, 160)
    return BoundedPager(catalog.page, limits)


E0 = PageKey("expert", 0, 0)
E1 = PageKey("expert", 0, 1)
E2 = PageKey("expert", 0, 2)
P0 = PageKey("ple", 1, 0, 0)
P1 = PageKey("ple", 1, 0, 1)


class CatalogTests(unittest.TestCase):
    def test_noninteger_page_coordinates_are_rejected(self):
        catalog = synthetic_catalog()
        for key in (PageKey("ple", 1, 0, 0.5), PageKey("expert", True, 0),
                    PageKey("expert", 0, 1.0), PageKey("ple", 1, 0, False)):
            with self.subTest(key=key), self.assertRaisesRegex(CatalogError, "invalid page key"):
                catalog.page(key)
        for row in (0.5, True):
            with self.subTest(row=row), self.assertRaisesRegex(CatalogError, "invalid PLE global row"):
                catalog.ple_key_for_global_row(row)
        with self.assertRaisesRegex(CatalogError, "invalid catalog geometry"):
            PageCatalog(catalog.tensors, layers=2, experts=3, ple_layer=1,
                        ple_shards=2, ple_rows_per_page=4.0)

    def test_receipt_and_index_shard_set_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="qwen38-admission-synthetic-") as temp:
            root = Path(temp)
            manifest_path = root / "manifest.json"
            manifest = {"repo": "pipenetwork/Qwen3.8-Flash-Next-MLX-mixed-4_8bit",
                        "revision": "synthetic", "files": [
                            {"path": "a.safetensors", "size_bytes": 1},
                            {"path": "b.safetensors", "size_bytes": 1},
                            {"path": "config.json", "size_bytes": 2},
                            {"path": "model.safetensors.index.json", "size_bytes": 44}]}
            config = "{}"
            index = json.dumps({"weight_map": {"x": "a.safetensors"}})
            manifest["files"][-1]["size_bytes"] = len(index)
            manifest_path.write_text(json.dumps(manifest))
            (root / "config.json").write_text(config)
            (root / "model.safetensors.index.json").write_text(index)
            (root / "a.safetensors").write_bytes(b"a")
            (root / "b.safetensors").write_bytes(b"b")
            receipt = {"complete": "true", "repo": manifest["repo"],
                       "revision": "synthetic", "verified_files": [
                           item["path"] for item in manifest["files"]]}
            (root / "acquisition-receipt.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(CatalogError, "unverified checkpoint"):
                admit_checkpoint(root, manifest_path=manifest_path)
            receipt["complete"] = True
            (root / "acquisition-receipt.json").write_text(json.dumps(receipt))
            with self.assertRaisesRegex(CatalogError, "index shard set"):
                admit_checkpoint(root, manifest_path=manifest_path)

    def test_expert_spans_are_exact_rows_of_all_nine_affine_tensors(self):
        catalog = synthetic_catalog()
        first = catalog.page(E0)
        second = catalog.page(E1)
        self.assertEqual(len(first.spans), 9)
        self.assertEqual(first.size_bytes, 48)
        self.assertEqual(second.size_bytes, 48)
        for a, b in zip(first.spans, second.spans):
            self.assertEqual(b.offset, a.offset + a.length)
            self.assertEqual(a.tensor, b.tensor)

    def test_ple_global_row_maps_to_shard_and_tail_block(self):
        catalog = synthetic_catalog()
        self.assertEqual(catalog.ple_key_for_global_row(8), PageKey("ple", 1, 0, 2))
        self.assertEqual(catalog.ple_key_for_global_row(9), PageKey("ple", 1, 1, 0))
        self.assertEqual(catalog.page(PageKey("ple", 1, 0, 2)).size_bytes, 16)
        self.assertEqual(catalog.page(P0).size_bytes, 64)
        with self.assertRaises(CatalogError):
            catalog.ple_key_for_global_row(18)
        with self.assertRaises(CatalogError):
            catalog.page(PageKey("ple", 1, 0, 3))

    def test_missing_triple_and_extra_pageable_tensor_fail_closed(self):
        catalog = synthetic_catalog()
        broken = dict(catalog.tensors)
        del broken["language_model.model.layers.0.mlp.switch_mlp.gate_proj.scales"]
        with self.assertRaisesRegex(CatalogError, "incomplete affine triple"):
            PageCatalog(broken, layers=2, experts=3, ple_layer=1, ple_shards=2)
        broken = dict(catalog.tensors)
        broken["language_model.model.layers.0.mlp.switch_mlp.unknown.weight"] = next(iter(broken.values()))
        with self.assertRaisesRegex(CatalogError, "unrecognized"):
            PageCatalog(broken, layers=2, experts=3, ple_layer=1, ple_shards=2)

    def test_scalar_or_empty_ple_tensor_fails_as_catalog_error(self):
        catalog = synthetic_catalog()
        name = "language_model.model.layers.1.ple.ple_embedding.ngram_embedding.shard_0.weight"
        original = catalog.tensors[name]
        for shape in ((), (original.shape[0], 0)):
            broken = dict(catalog.tensors)
            broken[name] = TensorRef(original.filename, original.data_start, original.dtype,
                                     shape, original.start, original.end)
            with self.subTest(shape=shape), self.assertRaises(CatalogError):
                PageCatalog(broken, layers=2, experts=3, ple_layer=1, ple_shards=2)


class SchedulerTests(unittest.TestCase):
    def test_catalog_span_offsets_and_lengths_are_integral(self):
        for span in (ByteSpan("synthetic", 0.5, 4, "x"),
                     ByteSpan("synthetic", 0, 4.0, "x")):
            p = BoundedPager(lambda key: PageSpec(key, (span,)),
                             Limits(96, 96, 1, 1, 1, 480, 160))
            with self.subTest(span=span), self.assertRaisesRegex(PagerProtocolError, "invalid page"):
                p.demand(E0)

    def test_demand_precedes_hint_and_only_real_demand_can_acquire(self):
        p = pager()
        self.assertTrue(p.hint(E0))
        p.demand(E1)
        ticket = p.next_io()
        self.assertEqual((ticket.spec.key, ticket.purpose), (E1, "demand"))
        p.complete_io(ticket)
        hint_ticket = p.next_io()
        self.assertEqual((hint_ticket.spec.key, hint_ticket.purpose), (E0, "hint"))
        p.complete_io(hint_ticket)
        with self.assertRaisesRegex(PagerProtocolError, "not demanded"):
            p.acquire(E0)
        lease = p.acquire(E1)
        with self.assertRaisesRegex(PagerProtocolError, "before GPU"):
            p.release(lease)
        p.mark_gpu_done(lease)
        p.release(lease)
        p.finish_demand(E1)

    def test_hint_promoted_to_demand_without_duplicate_io(self):
        p = pager()
        p.hint(E0)
        ticket = p.next_io()
        p.hint(E1)
        p.demand(E0)
        self.assertIsNone(p.next_io())
        p.complete_io(ticket)
        self.assertEqual(p.next_io().spec.key, E1)
        self.assertEqual(p.accounting()["resident_bytes"], 48)
        lease = p.acquire(E0)
        p.mark_gpu_done(lease)
        p.release(lease)

    def test_inflight_reservation_and_pinned_page_block_eviction(self):
        p = pager(weight=96, staging=96)
        p.demand(E0)
        first = p.next_io()
        p.complete_io(first)
        lease = p.acquire(E0)
        p.demand(E1)
        second = p.next_io()
        self.assertEqual(p.accounting()["reserved_weight_bytes"], 96)
        p.complete_io(second)
        second_lease = p.acquire(E1)
        p.demand(E2)
        with self.assertRaisesRegex(PagerStop, "available weight"):
            p.next_io()
        p.mark_gpu_done(lease)
        p.mark_gpu_done(second_lease)
        p.release(lease)
        p.release(second_lease)

    def test_idle_resident_page_is_evicted_for_demand(self):
        p = pager(weight=96, staging=96)
        p.hint(E0)
        first = p.next_io()
        p.complete_io(first)
        p.demand(E1)
        second = p.next_io()
        p.complete_io(second)
        p.finish_demand(E1)
        p.demand(E2)
        third = p.next_io()
        self.assertEqual(third.spec.key, E2)
        self.assertEqual(p.accounting()["reserved_weight_bytes"], 96)
        self.assertNotIn(E0, p.resident)

    def test_failed_hint_admission_does_not_evict_idle_page(self):
        p = pager(weight=96, staging=96)
        p.hint(E0)
        first = p.next_io()
        p.complete_io(first)
        p.demand(E1)
        second = p.next_io()
        p.complete_io(second)
        lease = p.acquire(E1)
        p.hint(P0)
        self.assertIsNone(p.next_io())
        self.assertIn(E0, p.resident)
        self.assertEqual(p.accounting()["resident_bytes"], 96)
        p.mark_gpu_done(lease)
        p.release(lease)

    def test_inflight_hint_waits_instead_of_stopping_demand(self):
        p = pager(weight=96, staging=96)
        p.demand(E0)
        p.complete_io(p.next_io())
        p.hint(E1)
        hint_ticket = p.next_io()
        p.demand(E2)
        self.assertIsNone(p.next_io())
        self.assertFalse(p.closed)
        p.complete_io(hint_ticket)
        demand_ticket = p.next_io()
        self.assertEqual(demand_ticket.spec.key, E2)

    def test_oversize_hint_is_rejected_before_queue_and_does_not_starve_demand(self):
        p = pager(weight=96, staging=48)
        self.assertFalse(p.hint(P0))  # 64 bytes cannot fit the 48-byte staging cap.
        self.assertEqual(p.accounting()["queued_hints"], 0)
        p.demand(E0)
        self.assertEqual(p.next_io().spec.key, E0)

    def test_invalidation_waits_for_io_and_releases_staging(self):
        p = pager()
        p.hint(P0)
        ticket = p.next_io()
        p.invalidate_hint(P0)
        self.assertEqual(p.accounting()["staging_bytes"], 64)
        p.complete_io(ticket)
        self.assertEqual(p.accounting()["staging_bytes"], 0)
        self.assertEqual(p.accounting()["resident_bytes"], 0)
        self.assertEqual(p.accounting()["invalidated_hint_bytes"], 64)
        with self.assertRaisesRegex(PagerProtocolError, "unmatched"):
            p.complete_io(ticket)

    def test_completed_unused_hint_is_released_on_invalidation(self):
        p = pager()
        p.hint(E0)
        p.complete_io(p.next_io())
        self.assertIn(E0, p.resident)
        p.invalidate_hint(E0)
        self.assertNotIn(E0, p.resident)
        self.assertEqual(p.accounting()["resident_bytes"], 0)
        self.assertEqual(p.accounting()["invalidated_hint_bytes"], 48)

    def test_observed_swap_or_headroom_stops_and_drains_inflight(self):
        p = pager()
        p.hint(P0)
        ticket = p.next_io()
        with self.assertRaisesRegex(PagerStop, "observed"):
            p.observe(Observation(300, 159, 0, False))
        with self.assertRaises(PagerStop):
            p.demand(E0)
        p.complete_io(ticket)
        self.assertEqual(p.accounting()["resident_bytes"], 0)
        q = pager()
        with self.assertRaises(PagerStop):
            q.observe(Observation(300, 160, 1, False))

    def test_pressure_stop_drains_idle_pages_but_waits_for_gpu_lease(self):
        p = pager()
        p.hint(E0)
        first = p.next_io()
        p.complete_io(first)
        p.demand(E1)
        second = p.next_io()
        p.complete_io(second)
        lease = p.acquire(E1)
        with self.assertRaises(PagerStop):
            p.observe(Observation(481, 160, 0, False))
        self.assertNotIn(E0, p.resident)
        self.assertIn(E1, p.resident)
        self.assertEqual(p.accounting()["resident_bytes"], 48)
        p.mark_gpu_done(lease)
        p.release(lease)
        self.assertEqual(p.accounting()["resident_bytes"], 0)

    def test_active_demand_count_is_bounded(self):
        p = pager()
        for key in (E0, E1, E2):
            p.demand(key)
        with self.assertRaisesRegex(PagerStop, "active demand"):
            p.demand(P0)
        self.assertEqual(p.accounting()["queued_demands"], 0)

    def test_fixed_text_weights_reduce_page_budget(self):
        limits = Limits(96, 48, 1, 1, 2, 480, 160, fixed_model_bytes=48)
        p = BoundedPager(synthetic_catalog().page, limits)
        p.demand(E0)
        first = p.next_io()
        p.complete_io(first)
        self.assertEqual(p.accounting()["reserved_weight_bytes"], 96)
        p.demand(E1)
        with self.assertRaises(PagerStop):
            p.next_io()  # E0 is a live demand; fixed tensors cannot be evicted.

    def test_cancel_keeps_gpu_lease_until_completion(self):
        p = pager()
        p.demand(E0)
        ticket = p.next_io()
        p.complete_io(ticket)
        lease = p.acquire(E0)
        p.cancel_request()
        with self.assertRaises(PagerProtocolError):
            p.release(lease)
        p.mark_gpu_done(lease)
        p.release(lease)

    def test_cancelled_read_cannot_be_promoted_by_next_request(self):
        p = pager()
        p.hint(E0)
        old_ticket = p.next_io()
        p.cancel_request()
        with self.assertRaisesRegex(PagerProtocolError, "cancellation still draining"):
            p.demand(E0)
        with self.assertRaisesRegex(PagerProtocolError, "cancellation still draining"):
            p.hint(E1)
        p.complete_io(old_ticket)
        self.assertNotIn(E0, p.resident)
        p.demand(E0)
        new_ticket = p.next_io()
        self.assertNotEqual(new_ticket.ticket, old_ticket.ticket)

    def test_cancelled_gpu_lease_blocks_next_request_until_release(self):
        p = pager()
        p.demand(E0)
        p.complete_io(p.next_io())
        lease = p.acquire(E0)
        p.cancel_request()
        with self.assertRaisesRegex(PagerProtocolError, "cancellation still draining"):
            p.demand(E1)
        p.mark_gpu_done(lease)
        p.release(lease)
        p.demand(E1)


if __name__ == "__main__":
    unittest.main()

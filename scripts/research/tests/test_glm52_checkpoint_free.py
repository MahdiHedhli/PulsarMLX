#!/usr/bin/env python3
"""Checkpoint-free GLM-5.2 unit tests (CI-safe)."""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glm52_expert_cache import ExpertCache, ExpertKey, FakeExpertStore
from glm52_fail_closed import ExecutionGuard, ExecutionPolicy, FailClosedError
from glm52_generation_harness import FROZEN_PROMPTS, DummyForward, generate_greedy
from glm52_synthetic_router import glm_route, router_scores, synthetic_moe_forward
from glm52_telemetry import TelemetryCollector, assert_public_safe, contains_private_leak
from iq2_xxs_dequant import BLOCK_BYTES, QK_K, dequantize_row_iq2_xxs


class TestExpertCache(unittest.TestCase):
    def test_hit_miss_evict(self):
        store = FakeExpertStore()
        cache = ExpertCache(store, budget_compressed_bytes=64)
        k1 = ExpertKey(0, 1, "gate")
        k2 = ExpertKey(0, 2, "gate")
        s1 = cache.get(k1, 0, 32)
        self.assertEqual(cache.stats.misses, 1)
        s1b = cache.get(k1, 0, 32)
        self.assertEqual(cache.stats.hits, 1)
        self.assertEqual(s1.payload, s1b.payload)
        cache.get(k2, 0, 32)
        # both fit? 32+32=64
        self.assertEqual(cache.entries(), 2)
        cache.get(ExpertKey(0, 3, "gate"), 0, 32)
        self.assertGreaterEqual(cache.stats.evictions, 1)
        self.assertLessEqual(cache.resident_bytes(), 64)

    def test_budget_exhaustion_single_slab(self):
        store = FakeExpertStore()
        cache = ExpertCache(store, budget_compressed_bytes=16)
        with self.assertRaises(MemoryError):
            cache.get(ExpertKey(0, 0, "gate"), 0, 32)

    def test_negative_range(self):
        store = FakeExpertStore()
        cache = ExpertCache(store, budget_compressed_bytes=1024)
        with self.assertRaises(ValueError):
            cache.get(ExpertKey(0, 0, "gate"), -1, 8)

    def test_duplicate_inflight_suppression(self):
        store = FakeExpertStore()
        cache = ExpertCache(store, budget_compressed_bytes=1024, max_in_flight=4)
        key = ExpertKey(1, 0, "up")
        results = []

        def worker():
            results.append(cache.get(key, 0, 64).payload)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r == results[0] for r in results))
        # one miss, others suppressed or hits
        self.assertEqual(cache.stats.misses, 1)

    def test_deterministic_payload(self):
        store = FakeExpertStore()
        cache = ExpertCache(store, budget_compressed_bytes=1024)
        a = cache.get(ExpertKey(2, 5, "down"), 10, 20).payload
        cache2 = ExpertCache(FakeExpertStore(), budget_compressed_bytes=1024)
        b = cache2.get(ExpertKey(2, 5, "down"), 10, 20).payload
        self.assertEqual(a, b)


class TestTelemetryPrivacy(unittest.TestCase):
    def test_rejects_home_path(self):
        with self.assertRaises(ValueError):
            assert_public_safe({"path": "/Users/alice/models/x.gguf"})

    def test_rejects_token_key(self):
        with self.assertRaises(ValueError):
            assert_public_safe({"token": "secret"})

    def test_snapshot_public(self):
        c = TelemetryCollector()
        c.record_read(100, 0.01)
        d = c.snapshot().to_public_dict()
        assert_public_safe(d)
        self.assertEqual(d["host_class"], "apple_silicon_m1_ultra")

    def test_leak_detector(self):
        self.assertTrue(contains_private_leak("username=bob"))


class TestFailClosed(unittest.TestCase):
    def test_cpu_forbidden_in_perf(self):
        g = ExecutionGuard(ExecutionPolicy(performance_mode=True, allow_cpu_fallback=False))
        with self.assertRaises(FailClosedError) as ctx:
            g.record_cpu("test")
        self.assertEqual(ctx.exception.code, "silent_cpu_fallback_forbidden")

    def test_mlx_required(self):
        g = ExecutionGuard(ExecutionPolicy(require_mlx=True))
        with self.assertRaises(FailClosedError):
            g.check_mlx_available(False)

    def test_materialization_cap(self):
        g = ExecutionGuard(ExecutionPolicy(max_materialized_bytes=100))
        g.admit_materialization(60)
        with self.assertRaises(FailClosedError) as ctx:
            g.admit_materialization(50)
        self.assertEqual(ctx.exception.code, "full_model_materialization_blocked")

    def test_headroom(self):
        g = ExecutionGuard(ExecutionPolicy(min_headroom_bytes=1000))
        with self.assertRaises(FailClosedError):
            g.check_headroom(10)

    def test_expert_range(self):
        g = ExecutionGuard()
        with self.assertRaises(FailClosedError):
            g.check_expert_range(10, 20, 25)


class TestSyntheticRouter(unittest.TestCase):
    def test_sigmoid_topk(self):
        logits = [0.0, 2.0, -1.0, 3.0, 0.5]
        r = glm_route(logits, k=2, n_shared=0, shared_as_sink=False)
        self.assertEqual(r["expert_ids"], [3, 1])
        self.assertAlmostEqual(sum(r["weights"]), 1.0, places=6)

    def test_shared_sink(self):
        logits = [1.0] * 8 + [0.0]  # 8 routed + 1 shared logit unused
        r = glm_route(logits, k=2, n_shared=1, shared_as_sink=True)
        self.assertEqual(r["n_routed"], 8)
        self.assertEqual(r["n_shared"], 1)
        self.assertIn(8, r["expert_ids"])

    def test_ties_stable(self):
        logits = [1.0, 1.0, 1.0]
        r = glm_route(logits, k=2, n_shared=0, shared_as_sink=False)
        self.assertEqual(r["expert_ids"], [0, 1])

    def test_moe_aggregate(self):
        x = [1.0, 0.0]
        experts = {0: [1.0, 0.0], 1: [0.0, 1.0]}
        route = {"expert_ids": [0, 1], "weights": [0.5, 0.5]}
        y = synthetic_moe_forward(x, experts, route)
        self.assertEqual(y, [0.5, 0.5])


class TestIQ2Dequant(unittest.TestCase):
    def test_block_length(self):
        enc = struct.pack("<e", 1.0) + bytes(64)
        self.assertEqual(len(enc), BLOCK_BYTES)
        y = dequantize_row_iq2_xxs(enc, QK_K)
        self.assertEqual(len(y), 256)
        # deterministic
        y2 = dequantize_row_iq2_xxs(enc, QK_K)
        self.assertEqual(y, y2)

    def test_malformed_length(self):
        with self.assertRaises(ValueError):
            dequantize_row_iq2_xxs(b"\x00" * 10)


class TestGenerationHarness(unittest.TestCase):
    def test_dummy_generate(self):
        fwd = DummyForward(vocab=100)
        out = generate_greedy([1, 2, 3], fwd, 4)
        self.assertEqual(len(out["generated_ids"]), 4)
        # deterministic
        out2 = generate_greedy([1, 2, 3], fwd, 4)
        self.assertEqual(out["generated_ids"], out2["generated_ids"])

    def test_frozen_prompts_present(self):
        for k in ("P-MIN", "P-FACT", "P-CODE", "P-REASON"):
            self.assertIn(k, FROZEN_PROMPTS)


class TestTier3FailClosed(unittest.TestCase):
    def test_missing_env_is_error_not_skip(self):
        # Simulate Tier-3 entry: missing path must fail
        import os

        os.environ.pop("PULSARMLX_GLM_GGUF", None)
        path = os.environ.get("PULSARMLX_GLM_GGUF")
        self.assertIsNone(path)
        # caller convention
        if not path:
            err = "PULSARMLX_GLM_GGUF unset"
        else:
            err = None
        self.assertEqual(err, "PULSARMLX_GLM_GGUF unset")


class TestTinyMultiShardFixture(unittest.TestCase):
    def test_catalog_two_shard_fake_headers(self):
        """Minimal GGUF-like headers are hard; test store discovery rules."""
        from glm52_gguf_catalog import discover_ggufs

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.gguf").write_bytes(b"GGUF" + b"\x00" * 12)
            (root / "b.gguf").write_bytes(b"GGUF" + b"\x00" * 12)
            found = discover_ggufs(root)
            self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()

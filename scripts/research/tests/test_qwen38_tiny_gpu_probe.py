"""Stdlib checks for the bounded host sampler and frozen literal oracle."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qwen38_tiny_gpu_probe import (GIB, MIB, MAX_MLX_BYTES, MAX_MLX_CACHE_BYTES,
                                   _QUARANTINED, check_observation, finish_stream,
                                   parse_host, _reference)


class TinyGpuProbeTests(unittest.TestCase):
    def test_literal_reference_shape_and_values(self):
        cases = _reference()
        self.assertEqual(cases["4:32"]["sparse_product"], [-20.0, 17.5])
        self.assertEqual(cases["8:64"]["sparse_product"], [-50.5, -54.75])
        self.assertEqual(cases["4:32"]["dense_product"], [90.75, 1.0])
        self.assertEqual(cases["8:64"]["dense_product"], [893.25, -78.5])
        self.assertEqual(cases["8:64"]["samples"][6], [1, 64, 64.5])

    def test_host_parser_and_gate(self):
        host = parse_host("The system has 68719476736 (4194304 pages)\nSystem-wide memory free percentage: 40%",
                          "total = 29696.00M  used = 27015.69M  free = 2680.31M",
                          "51200\n")
        self.assertEqual(host["rss_bytes"], 50 * MIB)
        check_observation(host, 27015.69)
        check_observation({**host, "free_percent": 25}, 27015.69)
        for change in ({"free_percent": 24}, {"rss_bytes": 513 * MIB},
                       {"swap_used_mib": 27015.70}, {"physical_bytes": 32 * GIB}):
            with self.assertRaises(RuntimeError):
                check_observation({**host, **change}, 27015.69)
        class MlxObservation:
            def __init__(self, active, peak, cache):
                self.active, self.peak, self.cache = active, peak, cache
            def get_active_memory(self):
                return self.active
            def get_peak_memory(self):
                return self.peak
            def get_cache_memory(self):
                return self.cache
        for active, peak, cache in ((MAX_MLX_BYTES + 1, 0, 0),
                                    (0, MAX_MLX_BYTES + 1, 0),
                                    (0, 0, MAX_MLX_CACHE_BYTES + 1)):
            with self.assertRaises(RuntimeError):
                check_observation(host, 27015.69, MlxObservation(active, peak, cache))

    def test_host_parser_fails_closed(self):
        with self.assertRaises(RuntimeError):
            parse_host("no pressure", "used = 1M", "42")
        with self.assertRaises(RuntimeError):
            parse_host("The system has 68719476736 (x)\nSystem-wide memory free percentage: 45%",
                       "used = ???", "42")

    def test_finish_stream_orders_fence_before_release(self):
        events = []
        class Mlx:
            def synchronize(self, stream):
                events.append(("sync", stream))
            def clear_cache(self):
                events.append(("clear_cache", None))
        owner = object()
        owners = [owner]
        finish_stream(Mlx(), "original", owners, lambda: events.append(("observe", None)))
        self.assertEqual(owners, [])
        self.assertEqual(events, [("sync", "original"), ("clear_cache", None),
                                  ("observe", None)])

    def test_fence_failure_quarantines_original_owners(self):
        class Mlx:
            def synchronize(self, stream):
                raise RuntimeError("fence failed")
        owner = object()
        owners = [owner]
        primary = ValueError("primary")
        start = len(_QUARANTINED)
        try:
            with self.assertRaises(ExceptionGroup) as raised:
                finish_stream(Mlx(), "original", owners, lambda: self.fail("observed"), primary)
            self.assertEqual([type(e) for e in raised.exception.exceptions], [ValueError, RuntimeError])
            self.assertEqual(owners, [owner])
            self.assertIs(_QUARANTINED[start], owner)
            self.assertEqual(_QUARANTINED[start + 1], "original")
        finally:
            del _QUARANTINED[start:]

    def test_cleanup_failure_preserves_primary(self):
        class Mlx:
            def synchronize(self, stream):
                pass
            def clear_cache(self):
                raise RuntimeError("cache cleanup failed")
        owners = [object()]
        with self.assertRaises(ExceptionGroup) as raised:
            finish_stream(Mlx(), "original", owners, lambda: self.fail("observed"), ValueError("primary"))
        self.assertEqual([type(e) for e in raised.exception.exceptions], [ValueError, RuntimeError])
        self.assertEqual(owners, [])


if __name__ == "__main__":
    unittest.main()

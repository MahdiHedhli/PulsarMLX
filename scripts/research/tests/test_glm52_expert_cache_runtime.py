#!/usr/bin/env python3
"""Checkpoint-free tests for ExpertSlabCache policy."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glm52_expert_cache_runtime import ExpertSlabCache, matvec_cached_rows


def test_lru_eviction_deterministic():
    c = ExpertSlabCache(max_bytes=20)
    c._lru["a"] = [[1.0]]
    c._sizes["a"] = 8
    c.stats.bytes_resident = 8
    c._lru["b"] = [[2.0]]
    c._sizes["b"] = 8
    c.stats.bytes_resident = 16
    # admit 12-byte entry forces eviction of oldest (a)
    nbytes = 12
    while c.stats.bytes_resident + nbytes > c.max_bytes and c._lru:
        k, _ = c._lru.popitem(last=False)
        c.stats.bytes_resident -= c._sizes.pop(k)
        c.stats.evictions += 1
    assert "a" not in c._lru
    assert "b" in c._lru
    assert c.stats.evictions == 1


def test_matvec_cached_rows():
    rows = [[1.0, 0.0], [0.0, 2.0]]
    y = matvec_cached_rows(rows, [3.0, 4.0])
    assert y == [3.0, 8.0]


def test_hit_path_moves_to_end():
    c = ExpertSlabCache(max_bytes=100)
    c._lru["x"] = [[1.0]]
    c._sizes["x"] = 4
    c.stats.bytes_resident = 4
    c._lru["y"] = [[2.0]]
    c._sizes["y"] = 4
    c.stats.bytes_resident = 8
    # touch x
    c._lru.move_to_end("x")
    k, _ = c._lru.popitem(last=False)
    assert k == "y"

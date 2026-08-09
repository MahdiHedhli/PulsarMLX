#!/usr/bin/env python3
"""Checkpoint-free tests for the GLM expert-cache simulator."""

from __future__ import annotations

import sys
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
ROOT = RESEARCH.parents[1]
sys.path.insert(0, str(RESEARCH))

from glm52_cache_simulator import (  # noqa: E402
    Access,
    build_accesses,
    load_catalog,
    load_route_trace,
    simulate,
    summarize_working_set,
)


def test_sequential_lru_thrashes_below_complete_working_set() -> None:
    accesses = [
        Access(f"k{i}", layer=i, expert=i, kind="gate", shared=False,
               compressed_bytes=1, decoded_bytes=4, quantization="TEST")
        for i in range(3)
    ]

    too_small = simulate(accesses, budget_bytes=8, policy="decoded_lru", repeats=2)
    assert too_small["per_token"][1]["decoded_hits"] == 0
    assert too_small["per_token"][1]["redequantizations"] == 3

    complete = simulate(accesses, budget_bytes=12, policy="decoded_lru", repeats=2)
    assert complete["per_token"][1]["decoded_hits"] == 3
    assert complete["per_token"][1]["redequantizations"] == 0


def test_compressed_hits_do_not_claim_decode_avoidance() -> None:
    accesses = [
        Access(f"k{i}", layer=i, expert=i, kind="gate", shared=False,
               compressed_bytes=2, decoded_bytes=16, quantization="TEST")
        for i in range(2)
    ]
    result = simulate(accesses, budget_bytes=4, policy="compressed_lru", repeats=2)
    warm = result["per_token"][1]
    assert warm["storage_hits"] == 2
    assert warm["decoded_hits"] == 0
    assert warm["bytes_avoided"] == 4
    assert warm["redequantizations"] == 2
    assert warm["decoded_bytes_materialized"] == 32


def test_shared_only_policy_protects_guaranteed_reuse() -> None:
    accesses = [
        Access("r0", layer=3, expert=7, kind="gate", shared=False,
               compressed_bytes=1, decoded_bytes=4, quantization="TEST"),
        Access("s0", layer=3, expert=0, kind="shared_gate", shared=True,
               compressed_bytes=1, decoded_bytes=4, quantization="TEST"),
        Access("r1", layer=4, expert=8, kind="gate", shared=False,
               compressed_bytes=1, decoded_bytes=4, quantization="TEST"),
        Access("s1", layer=4, expert=0, kind="shared_gate", shared=True,
               compressed_bytes=1, decoded_bytes=4, quantization="TEST"),
    ]
    result = simulate(
        accesses,
        budget_bytes=8,
        policy="decoded_shared_only",
        repeats=2,
    )
    warm = result["per_token"][1]
    assert warm["decoded_hits"] == 2
    assert warm["decoded_misses"] == 2
    assert warm["redequantizations"] == 2
    assert result["resident_entries"] == 2


def test_committed_catalog_produces_exact_glm_working_set() -> None:
    catalog_path = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
    trace_path = ROOT / "docs/research/glm52/raw/f016-c09-depth-0001.json"
    catalog = load_catalog(catalog_path)
    trace = load_route_trace(trace_path)
    accesses = build_accesses(catalog, trace)
    summary = summarize_working_set(accesses)

    assert len(trace) == 76
    assert len(accesses) == 2052
    assert summary == {
        "access_count": 2052,
        "unique_entry_count": 2052,
        "compressed_bytes": 9_070_411_776,
        "decoded_bytes": 103_280_541_696,
        "routed_compressed_bytes": 6_964_641_792,
        "routed_decoded_bytes": 91_804_925_952,
        "shared_compressed_bytes": 2_105_769_984,
        "shared_decoded_bytes": 11_475_615_744,
    }

    eight_gib = 8 * 1024**3
    sixteen_gib = 16 * 1024**3
    decoded = simulate(accesses, budget_bytes=eight_gib, policy="decoded_lru", repeats=2)
    assert decoded["resident_entries"] == 170
    assert decoded["per_token"][1]["decoded_hits"] == 0

    compressed_small = simulate(
        accesses, budget_bytes=eight_gib, policy="compressed_lru", repeats=2
    )
    assert compressed_small["per_token"][1]["storage_hits"] == 0

    compressed_fit = simulate(
        accesses, budget_bytes=sixteen_gib, policy="compressed_lru", repeats=2
    )
    assert compressed_fit["per_token"][1]["storage_hits"] == 2052
    assert compressed_fit["per_token"][1]["decoded_hits"] == 0

    shared = simulate(
        accesses,
        budget_bytes=sixteen_gib,
        policy="decoded_shared_only",
        repeats=2,
    )
    assert shared["resident_entries"] == 228
    assert shared["per_token"][1]["decoded_hits"] == 228
    assert shared["per_token"][1]["redequantizations"] == 1824

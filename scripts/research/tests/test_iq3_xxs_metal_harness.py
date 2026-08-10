#!/usr/bin/env python3
"""Checkpoint-free tests for the real IQ3_XXS Metal harness contract."""

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from benchmark_glm52_iq3_xxs_metal import _compare, _validate_runner  # noqa: E402


def valid_runner() -> dict:
    samples = [0.01] * 30
    summary = {"sample_count": 30, "measured_samples_seconds": samples}
    return {
        "schema": "pulsarmlx.internal.f018-iq3-metal-runner",
        "schema_version": "1.0.0",
        "source": {"commit": "a" * 40, "dirty": False},
        "binding": {
            "rows": 6144,
            "columns": 2048,
            "packed_sha256": "b" * 64,
            "activation_sha256": "c" * 64,
        },
        "setup": {
            "compiler": {
                "fast_math_enabled": False,
                "language_version": "3.2",
                "math_mode": "safe",
                "math_floating_point_functions": "precise",
                "pipeline_identity": "iq3_xxs_sequential_scaffold_v1",
            }
        },
        "protocol": {"warmups": 3, "measured": 30},
        "timing": {
            "total": summary,
            "dispatch": summary,
            "dispatch_preparation": summary,
            "synchronization": summary,
        },
        "cpu_fallback_count": 0,
        "complete_f32_weight_materialized_bytes": 0,
        "unique_output_hashes": 1,
    }


class Iq3MetalHarnessTests(unittest.TestCase):
    def test_frozen_runner_identity_passes(self) -> None:
        _validate_runner(
            valid_runner(),
            source_commit="a" * 40,
            rows=6144,
            columns=2048,
            packed_sha256="b" * 64,
            activation_sha256="c" * 64,
        )

    def test_runner_fails_closed_on_fallback_or_wrong_pipeline(self) -> None:
        fallback = valid_runner()
        fallback["cpu_fallback_count"] = 1
        with self.assertRaisesRegex(ValueError, "CPU fallback"):
            _validate_runner(
                fallback,
                source_commit="a" * 40,
                rows=6144,
                columns=2048,
                packed_sha256="b" * 64,
                activation_sha256="c" * 64,
            )
        wrong_pipeline = deepcopy(valid_runner())
        wrong_pipeline["setup"]["compiler"]["pipeline_identity"] = (
            "iq2_xxs_sequential_scaffold_v1"
        )
        with self.assertRaisesRegex(ValueError, "compiler contract"):
            _validate_runner(
                wrong_pipeline,
                source_commit="a" * 40,
                rows=6144,
                columns=2048,
                packed_sha256="b" * 64,
                activation_sha256="c" * 64,
            )

    def test_distinct_iq3_threshold_is_frozen(self) -> None:
        qualified = _compare([1.0, -2.0], [1.0001, -2.0002])
        self.assertEqual(qualified["contract_version"], "f018-iq3-down-v1")
        self.assertEqual(qualified["absolute_tolerance"], 0.00025)
        failed = _compare([1.0, 0.0], [1.001, 0.0])
        self.assertEqual(failed["classification"], "numerically_failed")


if __name__ == "__main__":
    unittest.main()

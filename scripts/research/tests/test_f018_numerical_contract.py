#!/usr/bin/env python3
"""Checkpoint-free tests for the frozen Feature 018 numerical contract."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_numerical_contract import (  # noqa: E402
    CLASS_GOLDEN_IDENTICAL,
    CLASS_NUMERICALLY_FAILED,
    CLASS_NUMERICALLY_QUALIFIED_GREEDY_DIVERGENT,
    CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL,
    CONTRACT_VERSION,
    classify_boundary,
    classify_teacher_forced_positions,
    contract_manifest,
)


class F018NumericalContractTests(unittest.TestCase):
    def test_committed_manifest_is_deterministic(self) -> None:
        path = ROOT / "fixtures/metal/iq2-xxs-numerical-v1.json"
        import json

        self.assertEqual(json.loads(path.read_text()), contract_manifest())

    def test_exact_bits_are_golden_identical(self) -> None:
        result = classify_boundary(
            reference=[1.0, -0.0, 3.5],
            candidate=[1.0, -0.0, 3.5],
            boundary="matrix",
            reference_argmax=2,
            candidate_argmax=2,
        )
        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["classification"], CLASS_GOLDEN_IDENTICAL)
        self.assertTrue(result["exact_f32_bits"])
        self.assertEqual(result["signed_zero_mismatch_count"], 0)

    def test_qualified_nonexact_same_greedy(self) -> None:
        result = classify_boundary(
            reference=[1.0, 2.0, 3.0],
            candidate=[1.0001, 1.9999, 3.0001],
            boundary="matrix",
            reference_argmax=2,
            candidate_argmax=2,
        )
        self.assertEqual(
            result["classification"],
            CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL,
        )
        self.assertFalse(result["exact_f32_bits"])
        self.assertEqual(result["elementwise_mismatch_count"], 0)

    def test_qualified_divergence_continues_teacher_forced(self) -> None:
        positions = [
            {
                "position": 0,
                "reference": [3.0, 2.0],
                "candidate": [3.0001, 2.0],
                "reference_argmax": 0,
                "candidate_argmax": 0,
                "teacher_forced_token": 11,
            },
            {
                "position": 1,
                "reference": [2.0, 2.0001],
                "candidate": [2.0001, 2.0],
                "reference_argmax": 1,
                "candidate_argmax": 0,
                "teacher_forced_token": 12,
            },
            {
                "position": 2,
                "reference": [4.0, 1.0],
                "candidate": [4.0001, 1.0],
                "reference_argmax": 0,
                "candidate_argmax": 0,
                "teacher_forced_token": 13,
            },
        ]
        result = classify_teacher_forced_positions(positions, boundary="matrix")
        self.assertEqual(
            result["classification"],
            CLASS_NUMERICALLY_QUALIFIED_GREEDY_DIVERGENT,
        )
        self.assertEqual(result["evaluated_position_count"], 3)
        self.assertEqual(result["first_greedy_divergence_position"], 1)
        self.assertEqual(
            [row["teacher_forced_token"] for row in result["positions"]],
            [11, 12, 13],
        )

    def test_nonfinite_or_wide_error_fails(self) -> None:
        for candidate in ([1.0, math.nan], [1.0, 2.0]):
            result = classify_boundary(
                reference=[1.0, 1.0],
                candidate=candidate,
                boundary="matrix",
                reference_argmax=0,
                candidate_argmax=0,
            )
            self.assertEqual(result["classification"], CLASS_NUMERICALLY_FAILED)

    def test_signed_zero_is_not_exact_but_can_qualify(self) -> None:
        result = classify_boundary(
            reference=[-0.0, 1.0],
            candidate=[0.0, 1.0],
            boundary="matrix",
            reference_argmax=1,
            candidate_argmax=1,
        )
        self.assertFalse(result["exact_f32_bits"])
        self.assertEqual(result["signed_zero_mismatch_count"], 1)
        self.assertEqual(
            result["classification"],
            CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL,
        )

    def test_fallback_materialization_identity_and_repeat_fail_closed(self) -> None:
        for overrides in (
            {"cpu_fallback_count": 1},
            {"complete_f32_weight_materialized_bytes": 4},
            {"identity_matches": False},
            {"deterministic": False},
            {"routes_match": False},
        ):
            result = classify_boundary(
                reference=[1.0],
                candidate=[1.0],
                boundary="matrix",
                reference_argmax=0,
                candidate_argmax=0,
                **overrides,
            )
            self.assertEqual(result["classification"], CLASS_NUMERICALLY_FAILED)


if __name__ == "__main__":
    unittest.main()

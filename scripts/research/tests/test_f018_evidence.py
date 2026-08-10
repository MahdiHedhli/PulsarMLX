#!/usr/bin/env python3
"""CI-safe Feature 018 evidence-contract tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402


def valid_record() -> dict:
    samples = [0.01, 0.02, 0.03]
    return {
        "schema": "pulsarmlx.research.f018-direct-iq2-xxs",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "classification": "golden_identical",
        "source": {"commit": "0" * 40, "dirty": False},
        "claim_boundary": "synthetic packed IQ2_XXS matrix only",
        "kernel": {
            "quantization": "IQ2_XXS",
            "complete_f32_weight_materialized_bytes": 0,
            "cpu_fallback_count": 0,
        },
        "timing": {
            "warmup_count": 1,
            "measured_samples_seconds": samples,
            "sample_count": len(samples),
            "minimum_seconds": min(samples),
            "maximum_seconds": max(samples),
            "mean_seconds": sum(samples) / len(samples),
        },
        "resource": {"level": "normal"},
        "unsupported_interpretations": ["full model inference"],
    }


class F018EvidenceTests(unittest.TestCase):
    def test_valid_record(self) -> None:
        result = validate_record(valid_record())
        self.assertEqual(result["actual_status"], "passed")

    def test_duplicate_json_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                load_unique_json(path)

    def test_private_path_rejected(self) -> None:
        record = valid_record()
        record["checkpoint"] = {
            "path": str(Path("/") / "Users" / "private" / "Models" / "model.gguf")
        }
        with self.assertRaisesRegex(ValueError, "public-safe"):
            validate_record(record)

    def test_hidden_fallback_or_f32_materialization_rejected(self) -> None:
        for field, value in (
            ("cpu_fallback_count", 1),
            ("complete_f32_weight_materialized_bytes", 4096),
        ):
            record = valid_record()
            record["kernel"][field] = value
            with self.assertRaisesRegex(ValueError, field):
                validate_record(record)

    def test_raw_sample_summary_mismatch_rejected(self) -> None:
        record = valid_record()
        record["timing"]["mean_seconds"] = 9.0
        with self.assertRaisesRegex(ValueError, "mean_seconds"):
            validate_record(record)

    def test_invalid_class_and_resource_rejected(self) -> None:
        record = valid_record()
        record["classification"] = "looks_fast"
        with self.assertRaisesRegex(ValueError, "classification"):
            validate_record(record)
        record = valid_record()
        record["resource"]["level"] = "critical"
        with self.assertRaisesRegex(ValueError, "resource"):
            validate_record(record)


if __name__ == "__main__":
    unittest.main()

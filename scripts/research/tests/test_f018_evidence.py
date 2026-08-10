#!/usr/bin/env python3
"""CI-safe Feature 018 evidence-contract tests."""

from __future__ import annotations

import json
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402
from benchmark_glm52_routed_expert_metal import _nonnegative_summary  # noqa: E402
from benchmark_glm52_complete_layer_metal import _historical_layer3  # noqa: E402


def valid_record() -> dict:
    samples = [0.01, 0.02, 0.03]
    component = {"measured_samples_seconds": samples}
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
            "dispatch": component,
            "synchronization": component,
            "kernel": component,
        },
        "correctness": {
            "contract_version": "f018-numerical-v1",
            "exact_f32_bits": True,
            "deterministic_repetitions": len(samples),
            "unique_output_hashes": 1,
            "candidate_output_sha256": "a" * 64,
            "f32_bit_mismatch_count": 0,
            "first_f32_bit_mismatch_index": None,
            "signed_zero_mismatch_count": 0,
            "elementwise_mismatch_count": 0,
            "maximum_absolute_error": 0.0,
            "mean_absolute_error": 0.0,
            "rmse": 0.0,
            "maximum_meaningful_relative_error": 0.0,
            "cosine_similarity": 1.0,
            "norm_ratio": 1.0,
            "absolute_tolerance": 0.0005,
            "relative_tolerance": 0.0005,
            "cosine_minimum": 0.999999,
            "norm_ratio_minimum": 0.9995,
            "norm_ratio_maximum": 1.0005,
        },
        "resource": {"level": "normal"},
        "unsupported_interpretations": ["full model inference"],
    }


class F018EvidenceTests(unittest.TestCase):
    def test_complete_layer_historical_reference_resolves_layer3(self) -> None:
        layer = _historical_layer3()
        self.assertEqual(layer["layer"], 3)
        self.assertRegex(layer["reference_output_f32_sha256"], r"^[0-9a-f]{64}$")

    def test_resident_worker_zero_storage_samples_are_valid(self) -> None:
        summary = _nonnegative_summary([0.0, 0.0, 0.0])
        self.assertEqual(summary["median_seconds"], 0.0)
        self.assertEqual(summary["coefficient_of_variation"], 0.0)

    def test_committed_synthetic_record_and_table(self) -> None:
        raw = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-synthetic-0002.json"
        if not raw.exists():
            self.skipTest("synthetic Feature 018 record not committed yet")
        record = validate_record(load_unique_json(raw))
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["correctness"]["deterministic_repetitions"], 100)
        self.assertEqual(record["kernel"]["cpu_fallback_count"], 0)
        self.assertEqual(record["kernel"]["complete_f32_weight_materialized_bytes"], 0)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research/analyze_glm52_iq2_xxs_metal.py"),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_committed_real_matrix_records(self) -> None:
        records = sorted(
            (ROOT / "docs/research/glm52/raw").glob(
                "f018-iq2-xxs-*-matrix-0001.json"
            )
        )
        for path in records:
            with self.subTest(path=path.name):
                record = validate_record(load_unique_json(path))
                self.assertEqual(record["actual_status"], "passed")
                self.assertEqual(record["correctness"]["deterministic_repetitions"], 30)
                self.assertEqual(record["kernel"]["cpu_fallback_count"], 0)
                self.assertEqual(
                    record["kernel"]["complete_f32_weight_materialized_bytes"], 0
                )
                table = (
                    ROOT
                    / "docs/research/glm52/tables"
                    / path.name.replace(".json", ".md")
                )
                if table.exists():
                    subprocess.run(
                        [
                            sys.executable,
                            str(
                                ROOT
                                / "scripts/research/analyze_glm52_iq2_xxs_metal.py"
                            ),
                            "--input",
                            str(path),
                            "--output",
                            str(table),
                            "--check",
                        ],
                        cwd=ROOT,
                        check=True,
                    )

    def test_committed_routed_expert_record(self) -> None:
        path = (
            ROOT
            / "docs/research/glm52/raw/f018-iq2-xxs-routed-expert-0001.json"
        )
        if not path.exists():
            self.skipTest("Feature 018 routed-expert record not committed yet")
        record = validate_record(load_unique_json(path))
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["numerical_qualification"]["elementwise_mismatch_count"], 0)
        self.assertEqual(len(record["direct_samples"]), 10)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research/analyze_glm52_iq2_xxs_metal.py"),
                "--input",
                str(path),
                "--output",
                str(
                    ROOT
                    / "docs/research/glm52/tables/f018-iq2-xxs-routed-expert-0001.md"
                ),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_committed_moe_record(self) -> None:
        path = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-moe-layer3-0001.json"
        if not path.exists():
            self.skipTest("Feature 018 MoE record not committed yet")
        record = validate_record(load_unique_json(path))
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["numerical_qualification"]["elementwise_mismatch_count"], 0)
        self.assertEqual(len(record["direct_samples"]), 10)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research/analyze_glm52_iq2_xxs_metal.py"),
                "--input",
                str(path),
                "--output",
                str(
                    ROOT
                    / "docs/research/glm52/tables/f018-iq2-xxs-moe-layer3-0001.md"
                ),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_committed_complete_layer_record(self) -> None:
        path = (
            ROOT
            / "docs/research/glm52/raw/f018-iq2-xxs-complete-layer3-0001.json"
        )
        if not path.exists():
            self.skipTest("Feature 018 complete-layer record not committed yet")
        record = validate_record(load_unique_json(path))
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(record["numerical_qualification"]["elementwise_mismatch_count"], 0)
        self.assertLess(
            record["direct_summaries"]["layer"]["total_seconds"]["median_seconds"],
            record["optimized_reference"]["summaries"]["total_seconds"]["median_seconds"],
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/research/analyze_glm52_iq2_xxs_metal.py"),
                "--input",
                str(path),
                "--output",
                str(
                    ROOT
                    / "docs/research/glm52/tables/f018-iq2-xxs-complete-layer3-0001.md"
                ),
                "--check",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_valid_record(self) -> None:
        result = validate_record(valid_record())
        self.assertEqual(result["actual_status"], "passed")

    def test_real_matrix_semantics(self) -> None:
        record = valid_record()
        samples = [0.01 + index * 0.0001 for index in range(30)]
        record["timing"].update(
            {
                "measured_samples_seconds": samples,
                "sample_count": len(samples),
                "minimum_seconds": min(samples),
                "maximum_seconds": max(samples),
                "mean_seconds": sum(samples) / len(samples),
                "dispatch": {"measured_samples_seconds": samples},
                "synchronization": {"measured_samples_seconds": samples},
                "kernel": {"measured_samples_seconds": samples},
            }
        )
        record["correctness"]["deterministic_repetitions"] = len(samples)
        record["binding"] = {
            "layer": 3,
            "expert_id": 15,
            "projection": "gate",
            "tensor_name": "blk.3.ffn_gate_exps.weight",
            "shard_filename": "model-00002-of-00006.gguf",
            "quantization": "IQ2_XXS",
            "shape": [2048, 6144],
            "packed_bytes": 3_244_032,
            "packed_sha256": "b" * 64,
            "activation_identity": "frozen fixture",
            "activation_token_id": 9703,
            "activation_length": 6144,
            "activation_sha256": "c" * 64,
            "reference_output_sha256": "d" * 64,
        }
        record["checkpoint"] = {
            "checkpoint_set_sha256": "e" * 64,
            "file_count": 6,
            "total_bytes": 238_458_632_928,
        }
        record["protocol"] = {
            "direct_metal_warmups": 3,
            "direct_metal_measured": 30,
        }
        record["optimized_reference"] = {
            "deterministic": True,
            "exact_f32_bits_vs_scalar": True,
            "samples": [{} for _ in range(30)],
        }
        record["setup"] = {
            "checkpoint_storage_read_count": 1,
            "checkpoint_storage_bytes": 3_244_032,
        }
        record["correctness"]["reference_output_sha256"] = "d" * 64
        record["correctness"]["optimized_reference_output_sha256"] = "d" * 64
        self.assertEqual(validate_record(record)["binding"]["expert_id"], 15)
        record["optimized_reference"]["exact_f32_bits_vs_scalar"] = False
        with self.assertRaisesRegex(ValueError, "match scalar"):
            validate_record(record)

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

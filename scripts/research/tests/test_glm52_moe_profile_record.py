#!/usr/bin/env python3
"""CI-safe semantic validation for the bounded real-checkpoint MoE profile."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_telemetry import assert_public_safe  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"


def _load() -> dict:
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(RECORD.read_text(), object_pairs_hook=reject_duplicate)


class Glm52MoeProfileRecordTests(unittest.TestCase):
    def test_identity_exactness_and_resource_contract(self) -> None:
        record = _load()
        self.assertEqual(record["schema"], "pulsarmlx.research.glm52-moe-stage-profile")
        self.assertEqual(record["schema_version"], "1.0.0")
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source_dirty"])
        self.assertFalse(record["model_inference_executed"])
        self.assertEqual(record["protocol"]["layers"], [3, 8, 40, 78])
        self.assertEqual(record["protocol"]["input_token_id"], 9703)
        self.assertEqual(record["protocol"]["warmups"], 3)
        self.assertEqual(record["protocol"]["measured_samples"], 10)
        self.assertFalse(record["protocol"]["os_page_cache_controlled"])

        checkpoint = record["checkpoint"]
        self.assertEqual(checkpoint["file_count"], 6)
        self.assertEqual(checkpoint["quant"], "UD-IQ2_XXS")
        self.assertEqual(checkpoint["total_bytes"], 238_458_632_928)
        self.assertEqual(
            checkpoint["checkpoint_set_sha256"],
            "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
        )

        self.assertEqual([layer["layer"] for layer in record["layers"]], [3, 8, 40, 78])
        for layer in record["layers"]:
            self.assertEqual(layer["actual_status"], "passed")
            self.assertEqual(len(layer["reference_route"]["expert_ids"]), 8)
            self.assertTrue(layer["process_first_comparison"]["exact_f32_bits"])
            self.assertEqual(layer["process_first_comparison"]["mismatch_count"], 0)
            self.assertEqual(len(layer["measured"]), 10)
            self.assertEqual(layer["cache_end"]["backend"], "mlx")
            self.assertIn("gpu", layer["cache_end"]["device"])
            self.assertEqual(layer["cache_end"]["cpu_fallbacks"], 0)
            self.assertEqual(layer["cache_end"]["evictions"], 0)
            self.assertEqual(layer["cache_end"]["admission_rejections"], 0)
            for sample in layer["measured"]:
                self.assertEqual(sample["route"]["expert_ids"], layer["reference_route"]["expert_ids"])
                self.assertEqual(sample["output_f32_sha256"], layer["reference_output_f32_sha256"])
                self.assertEqual(sample["stage_totals"]["routed_matrix_event_count"], 24)
                self.assertEqual(sample["stage_totals"]["shared_matrix_event_count"], 3)
                self.assertEqual(sample["stage_totals"]["shared_matrix_hit_count"], 3)
                self.assertEqual(sample["resource_before"]["level"], "normal")
                self.assertEqual(sample["resource_after"]["level"], "normal")

        self.assertEqual(record["resource_before"]["level"], "normal")
        self.assertEqual(record["resource_after"]["level"], "normal")
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        assert_public_safe(record)


if __name__ == "__main__":
    unittest.main()

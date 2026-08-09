#!/usr/bin/env python3
"""CI-safe semantic checks for the vectorized real-checkpoint P1 record."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_telemetry import assert_public_safe  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/f016-inference-p2-iq3-0001.json"


def _load() -> dict:
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(RECORD.read_text(), object_pairs_hook=reject_duplicate)


class Glm52P2Iq3RecordTests(unittest.TestCase):
    def test_golden_identity_backend_and_cache_contract(self) -> None:
        record = _load()
        self.assertEqual(record["schema"], "pulsarmlx.research.glm52-inference")
        self.assertEqual(record["schema_version"], "2.0.0")
        self.assertEqual(record["actual_status"], "passed")
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["generated_token_ids"], [9703, 21615, 220])
        self.assertTrue(record["matches_golden_prefix"])
        self.assertFalse(record["matches_golden_full"])
        self.assertEqual(record["decoder_mode"], "numpy_vectorized")
        self.assertEqual(record["cache_policy"], "decoded_shared_only")
        checkpoint = record["checkpoint"]
        self.assertEqual(checkpoint["file_count"], 6)
        self.assertEqual(checkpoint["quant"], "UD-IQ2_XXS")
        self.assertEqual(checkpoint["total_bytes"], 238_458_632_928)

        cache = record["expert_cache"]
        self.assertEqual(cache["backend"], "mlx")
        self.assertIn("gpu", cache["device"])
        self.assertEqual(cache["cpu_fallbacks"], 0)
        self.assertEqual(cache["decoded_cache_hits"], 456)
        self.assertEqual(cache["decoded_cache_misses"], 5700)
        self.assertEqual(cache["admissions"], 228)
        self.assertEqual(cache["evictions"], 0)
        self.assertEqual(cache["admission_rejections"], 0)
        self.assertEqual(cache["resident_entries"], 228)
        self.assertEqual(cache["storage_bytes_avoided"], 4_211_539_968)
        self.assertEqual(cache["decoded_bytes_avoided"], 22_951_231_488)
        self.assertEqual(
            set(cache["quantization_metrics"]),
            {"IQ2_S", "IQ2_XXS", "IQ3_XXS", "IQ4_XS", "Q2_K", "Q3_K", "Q5_K", "Q6_K", "Q8_0"},
        )

        timings = record["timings"]
        self.assertEqual(len(timings), 3)
        self.assertEqual(
            [item["phase"] for item in timings], ["prefill", "decode", "decode"]
        )
        self.assertEqual([item["token"] for item in timings], [9703, 21615, 220])
        self.assertTrue(all(len(item["layers"]) == 79 for item in timings))
        cold, warm, warm_second = (item["cache_delta"] for item in timings)
        self.assertEqual((cold["decoded_cache_hits"], cold["decoded_cache_misses"]), (0, 2052))
        self.assertEqual((warm["decoded_cache_hits"], warm["decoded_cache_misses"]), (228, 1824))
        self.assertEqual(
            (warm_second["decoded_cache_hits"], warm_second["decoded_cache_misses"]),
            (228, 1824),
        )
        self.assertLess(timings[1]["stack_seconds"], timings[0]["stack_seconds"])
        self.assertTrue(all(item["resource_after"]["level"] == "normal" for item in timings))

        routing = record["routing"]
        self.assertEqual(len(routing), 3)
        for stack in routing:
            self.assertEqual(len(stack["layers"]), 76)
            for layer in stack["layers"]:
                self.assertEqual(len(layer["expert_ids"]), 8)
                self.assertEqual(len(layer["weights"]), 8)
                self.assertEqual(layer["shared_expert"], 0)
        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )
        # The shared privacy helper intentionally rejects any field named
        # exactly `token`; this schema uses that name for public integer token
        # IDs. Validate the values above, then apply the recursive guard to a
        # copy with only those two semantic fields removed.
        guarded = json.loads(json.dumps(record))
        for stack in guarded["timings"]:
            stack.pop("token", None)
        for stack in guarded["routing"]:
            stack.pop("token", None)
        assert_public_safe(guarded)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""CI-safe semantic checks for the frozen vectorized golden-eight record."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_telemetry import assert_public_safe  # noqa: E402

RECORD = ROOT / "docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json"
RECORD_SHA256 = "be4232f2bb4df103756158bfd9d7f6a807c2b332ff651b1670a98a04be5c0018"
GOLDEN = [9703, 21615, 220, 16, 13, 16, 16, 15, 15]
QUANTIZATIONS = {
    "IQ2_S",
    "IQ2_XXS",
    "IQ3_XXS",
    "IQ4_XS",
    "Q2_K",
    "Q3_K",
    "Q5_K",
    "Q6_K",
    "Q8_0",
}


def _load() -> dict:
    def reject_duplicate(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(RECORD.read_text(), object_pairs_hook=reject_duplicate)


class Glm52Golden8Iq3RecordTests(unittest.TestCase):
    def test_frozen_golden_identity_backend_and_cache_contract(self) -> None:
        record = _load()
        self.assertEqual(hashlib.sha256(RECORD.read_bytes()).hexdigest(), RECORD_SHA256)
        self.assertEqual(record["schema"], "pulsarmlx.research.glm52-inference")
        self.assertEqual(record["schema_version"], "2.0.0")
        self.assertEqual(record["feature_id"], "016-glm52-full-execution")
        self.assertEqual(record["actual_status"], "passed")
        self.assertEqual(
            record["source_commit"], "1a2ca76ee2df0f518bfc9ddbaafd31500a5e6a26"
        )
        self.assertFalse(record["source_dirty"])
        self.assertEqual(record["prompt_text"], "Hello")
        self.assertEqual(record["prompt_token_ids"], [9703])
        self.assertEqual(record["requested_new_tokens"], 8)
        self.assertEqual(record["generated_token_ids"], GOLDEN)
        self.assertEqual(record["golden"], GOLDEN)
        self.assertTrue(record["matches_golden_prefix"])
        self.assertTrue(record["matches_golden_full"])
        self.assertEqual(record["mode"], "inference")
        self.assertEqual(record["decoder_mode"], "numpy_vectorized")
        self.assertEqual(record["cache_policy"], "decoded_shared_only")
        self.assertEqual(record["cache_budget_bytes"], 16 * 1024**3)

        checkpoint = record["checkpoint"]
        self.assertEqual(checkpoint["repo"], "unsloth/GLM-5.2-GGUF")
        self.assertEqual(
            checkpoint["revision"],
            "abc55e72527792c6e77069c99b4cb7de16fa9f23",
        )
        self.assertEqual(
            checkpoint["checkpoint_set_sha256"],
            "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
        )
        self.assertEqual(checkpoint["file_count"], 6)
        self.assertEqual(checkpoint["quant"], "UD-IQ2_XXS")
        self.assertEqual(checkpoint["total_bytes"], 238_458_632_928)

        cache = record["expert_cache"]
        self.assertEqual(cache["backend"], "mlx")
        self.assertIn("gpu", cache["device"])
        self.assertEqual(cache["mlx_version"], "0.32.0")
        self.assertEqual(cache["cpu_fallbacks"], 0)
        self.assertEqual(cache["decoded_cache_hits"], 1_824)
        self.assertEqual(cache["decoded_cache_misses"], 16_644)
        self.assertEqual(cache["admissions"], 228)
        self.assertEqual(cache["evictions"], 0)
        self.assertEqual(cache["admission_rejections"], 0)
        self.assertEqual(cache["resident_entries"], 228)
        self.assertEqual(cache["storage_bytes_avoided"], 16_846_159_872)
        self.assertEqual(cache["decoded_bytes_avoided"], 91_804_925_952)
        self.assertEqual(set(cache["quantization_metrics"]), QUANTIZATIONS)

        timings = record["timings"]
        self.assertEqual(len(timings), 9)
        self.assertEqual(
            [item["phase"] for item in timings], ["prefill"] + ["decode"] * 8
        )
        self.assertEqual([item["token"] for item in timings], GOLDEN)
        self.assertTrue(all(len(item["layers"]) == 79 for item in timings))
        self.assertTrue(all(item["resource_after"]["level"] == "normal" for item in timings))
        self.assertEqual(
            (timings[0]["cache_delta"]["decoded_cache_hits"],
             timings[0]["cache_delta"]["decoded_cache_misses"]),
            (0, 2_052),
        )
        for item in timings[1:]:
            delta = item["cache_delta"]
            self.assertEqual((delta["decoded_cache_hits"], delta["decoded_cache_misses"]), (228, 1_824))
            self.assertEqual(delta["bytes_resident_end"], 11_475_615_744)
            self.assertEqual(delta["resident_entries_end"], 228)
            self.assertEqual(delta["evictions"], 0)
            self.assertEqual(delta["admission_rejections"], 0)
            self.assertEqual(delta["cpu_fallbacks"], 0)

        routing = record["routing"]
        self.assertEqual(len(routing), 9)
        for stack in routing:
            self.assertEqual(len(stack["layers"]), 76)
            self.assertEqual([layer["layer"] for layer in stack["layers"]], list(range(3, 79)))
            for layer in stack["layers"]:
                self.assertEqual(len(layer["expert_ids"]), 8)
                self.assertEqual(len(set(layer["expert_ids"])), 8)
                self.assertEqual(len(layer["weights"]), 8)
                self.assertEqual(layer["shared_expert"], 0)

        subprocess.run(
            ["git", "cat-file", "-e", f"{record['source_commit']}^{{commit}}"],
            cwd=ROOT,
            check=True,
        )

        # Integer token IDs are public experiment semantics. Remove the two
        # schema fields named exactly `token`, then apply the shared recursive
        # guard to every other key and value.
        guarded = json.loads(json.dumps(record))
        for stack in guarded["timings"]:
            stack.pop("token", None)
        for stack in guarded["routing"]:
            stack.pop("token", None)
        assert_public_safe(guarded)


if __name__ == "__main__":
    unittest.main()

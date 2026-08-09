from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/rank_glm52_quant_hotspots.py"
SOURCE = ROOT / "docs/research/glm52/raw/f016-inference-p1-vectorized-0001.json"
COMMITTED_JSON = ROOT / "docs/research/glm52/raw/f016-p1-quant-hotspot-ranking-0001.json"
COMMITTED_TABLE = ROOT / "docs/research/glm52/tables/f016-p1-quant-hotspots.md"


class Glm52QuantHotspotRankingTests(unittest.TestCase):
    def test_generator_is_deterministic_and_committed_outputs_are_current(self) -> None:
        subprocess.run([sys.executable, str(SCRIPT), "--check"], cwd=ROOT, check=True)
        with tempfile.TemporaryDirectory() as temporary:
            first_json = Path(temporary) / "first.json"
            first_table = Path(temporary) / "first.md"
            second_json = Path(temporary) / "second.json"
            second_table = Path(temporary) / "second.md"
            for json_out, table_out in ((first_json, first_table), (second_json, second_table)):
                subprocess.run(
                    [
                        sys.executable, str(SCRIPT),
                        "--json-out", str(json_out), "--table-out", str(table_out),
                    ],
                    cwd=ROOT,
                    check=True,
                )
            self.assertEqual(first_json.read_bytes(), second_json.read_bytes())
            self.assertEqual(first_table.read_bytes(), second_table.read_bytes())
            self.assertEqual(first_json.read_bytes(), COMMITTED_JSON.read_bytes())
            self.assertEqual(first_table.read_bytes(), COMMITTED_TABLE.read_bytes())

    def test_ranking_recomputes_source_metrics_and_names_iq3_next(self) -> None:
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        record = json.loads(COMMITTED_JSON.read_text(encoding="utf-8"))
        rows = record["ranking"]
        self.assertEqual(rows[0]["quantization"], "IQ3_XXS")
        self.assertEqual(record["next_decoder_candidate"], "IQ3_XXS")
        self.assertFalse(record["scope"]["global_tensor_count_used_for_ranking"])
        self.assertEqual(set(record["formats_exercised"]), set(source["expert_cache"]["quantization_metrics"]))
        self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)))
        self.assertEqual(
            [row["measured_component_seconds"] for row in rows],
            sorted((row["measured_component_seconds"] for row in rows), reverse=True),
        )
        for row in rows:
            observed = source["expert_cache"]["quantization_metrics"][row["quantization"]]
            expected = sum(
                observed[field]
                for field in (
                    "storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds",
                    "mlx_matrix_build_seconds", "mlx_matvec_seconds",
                )
            )
            self.assertAlmostEqual(row["measured_component_seconds"], expected, places=12)
        self.assertAlmostEqual(
            sum(row["fraction_of_quantified_component_time"] for row in rows), 1.0, places=12
        )


if __name__ == "__main__":
    unittest.main()

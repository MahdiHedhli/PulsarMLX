"""The synthetic Safetensors fixtures match their generator and their manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures/safetensors"
MANIFEST = FIXTURES / "manifest.json"
GENERATOR = ROOT / "scripts/research/generate_safetensors_fixtures_v1.py"

POSITIVES = ("uniform-affine-v1", "mixed-4-8-v1", "mixed-4-8-index-total-size-v1")


class Determinism(unittest.TestCase):
    def test_the_generator_reproduces_every_committed_byte(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"], "PASS")


class Manifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def test_every_listed_file_exists_with_the_recorded_digest(self):
        for path, record in self.manifest["files"].items():
            target = FIXTURES / path
            self.assertTrue(target.is_file(), path)
            body = target.read_bytes()
            self.assertEqual(len(body), record["bytes"], path)
            self.assertEqual(hashlib.sha256(body).hexdigest(), record["sha256"], path)

    def test_the_generator_and_reference_digests_are_current(self):
        self.assertEqual(
            self.manifest["generator_sha256"],
            hashlib.sha256(GENERATOR.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.manifest["reference_sha256"],
            hashlib.sha256(
                (ROOT / "scripts/research/mlx_affine_reference_v1.py").read_bytes()
            ).hexdigest(),
        )

    def test_mlx_was_not_run_to_make_these(self):
        self.assertTrue(self.manifest["mlx_was_not_run"])

    def test_the_corpus_stays_small(self):
        total = sum(record["bytes"] for record in self.manifest["files"].values())
        self.assertLess(total, 1_000_000, "the fixtures must stay a few hundred KB")


class Shape(unittest.TestCase):
    def test_every_negative_case_declares_one_error_variant(self):
        cases = sorted(p for p in (FIXTURES / "negative").iterdir() if p.is_dir())
        self.assertGreaterEqual(len(cases), 20)
        seen = set()
        for case in cases:
            readme = (case / "README").read_text().splitlines()
            self.assertGreaterEqual(len(readme), 2, case.name)
            variant = readme[0].strip()
            self.assertTrue(
                variant.startswith("CatalogError::") or variant.startswith("AffineError::"),
                f"{case.name}: {variant}",
            )
            seen.add(variant)
        # The corpus must span both crates and a real spread of defects.
        self.assertGreaterEqual(
            len({v for v in seen if v.startswith("CatalogError::")}), 10
        )
        self.assertGreaterEqual(
            len({v for v in seen if v.startswith("AffineError::")}), 6
        )

    def test_every_positive_carries_a_config_and_reference_expectations(self):
        for name in POSITIVES:
            directory = FIXTURES / name
            config = json.loads((directory / "config.json").read_text())
            self.assertIn("quantization", config)
            expected = json.loads((directory / "expected.json").read_text())
            self.assertTrue(expected["modules"])
            for module, case in expected["modules"].items():
                self.assertEqual(
                    len(case["dequant"]), case["rows"] * case["columns"], module
                )

    def test_the_positives_carry_no_model_specific_names(self):
        forbidden = ("glm", "pipenetwork", "qwen", "switch_mlp", "self_attn", "lm_head")
        for name in POSITIVES:
            for leaf in (FIXTURES / name).iterdir():
                text = leaf.read_bytes().lower()
                for token in forbidden:
                    self.assertNotIn(token.encode(), text, f"{name}/{leaf.name}: {token}")

    def test_the_mixed_fixture_really_is_mixed(self):
        config = json.loads((FIXTURES / "mixed-4-8-v1/config.json").read_text())
        quantization = config["quantization"]
        self.assertEqual(quantization["bits"], 4)
        self.assertEqual(quantization["group_size"], 64)
        overrides = {k: v for k, v in quantization.items()
                     if k not in ("bits", "group_size")}
        self.assertGreaterEqual(len(overrides), 2)
        self.assertTrue(any(v["bits"] == 8 and v["group_size"] == 64 for v in overrides.values()))
        self.assertTrue(any(v["bits"] == 8 and v["group_size"] == 32 for v in overrides.values()))
        index = json.loads((FIXTURES / "mixed-4-8-v1/model.safetensors.index.json").read_text())
        self.assertEqual(len(set(index["weight_map"].values())), 3)
        self.assertNotIn("metadata", index)
        declared = json.loads(
            (FIXTURES / "mixed-4-8-index-total-size-v1/model.safetensors.index.json").read_text()
        )
        self.assertIn("total_size", declared["metadata"])

    def test_every_positive_shard_tiles_its_data_buffer(self):
        # Coverage is strict: upstream Safetensors requires the data buffer to
        # be fully covered, and all eighteen shards of the real checkpoint this
        # feature targets are gap-free. A positive fixture that left a gap
        # would be testing an extension nobody writes.
        for name in POSITIVES:
            for leaf in sorted((FIXTURES / name).glob("*.safetensors")):
                body = leaf.read_bytes()
                (length,) = struct.unpack("<Q", body[:8])
                self.assertEqual(body[8:9], b"{", f"{leaf.name} must begin with an object")
                header = json.loads(body[8:8 + length])
                data_length = len(body) - 8 - length
                spans = sorted(
                    entry["data_offsets"]
                    for key, entry in header.items() if key != "__metadata__"
                )
                cursor = 0
                for begin, end in spans:
                    self.assertEqual(begin, cursor, f"{leaf.name} leaves a gap at {cursor}")
                    cursor = end
                self.assertEqual(cursor, data_length, f"{leaf.name} has trailing bytes")

    def test_the_corpus_carries_gap_negative_cases(self):
        for case in ("header-uncovered-gap", "header-trailing-uncovered-bytes"):
            readme = (FIXTURES / "negative" / case / "README").read_text().splitlines()
            self.assertEqual(readme[0].strip(), "CatalogError::Gap")


if __name__ == "__main__":
    unittest.main()

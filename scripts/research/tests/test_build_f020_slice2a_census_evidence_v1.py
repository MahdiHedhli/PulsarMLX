"""The Slice 2A evidence builder keeps private material out and summarizes receipts faithfully."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "build_f020_slice2a_census_evidence_v1.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_f020_slice2a_census_evidence_v1", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("the builder could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load()
LOG = {"shards": [{"file": "model-00001.safetensors", "file_len": 100},
                  {"file": "model-00002.safetensors", "file_len": 200}]}


class BuilderTests(unittest.TestCase):
    def test_private_locations_users_and_hosts_are_refused(self):
        for text in ("/Users/someone/x", "/Volumes/Disk/models", "10.0.0.7",
                     "192.168.1.20", "/private/tmp/x", "/home/u", "/tmp/x"):
            self.assertIsNotNone(builder.FORBIDDEN.search(text), text)
        for text in ("pipenetwork/GLM-5.3-MLX-mixed-4_8bit", "huggingface_hub 1.32.0",
                     "model.layers.10.mlp.gate.weight", "2026-09-22T13:20:31Z"):
            self.assertIsNone(builder.FORBIDDEN.search(text), text)

    def test_a_record_without_files_is_reported_as_such_and_its_path_dropped(self):
        summary = builder._download_record(
            {"repo": "r", "revision": "v", "path": "/Volumes/x", "seconds": 3}, LOG)
        self.assertIsNone(summary["per_file_records"])
        self.assertEqual(summary["members_present"], ["path", "repo", "revision", "seconds"])
        self.assertNotIn("/Volumes/x", repr(summary))

    def test_per_shard_receipts_are_compared_with_the_stat_sizes(self):
        record = {
            "repo": "r", "revision": "v", "path": "/Volumes/x",
            "tool": {"huggingface_hub": "1.0", "interpreter": "/Users/u/bin/python"},
            "files": [
                {"name": "model-00001.safetensors", "bytes": 100, "sha256": "a" * 64, "verified": True},
                {"name": "model-00002.safetensors", "bytes": 201, "sha256": "b" * 64, "verified": True},
                {"name": "config.json", "bytes": 5, "sha256": None, "verified": True},
            ],
        }
        summary = builder._download_record(record, LOG)
        self.assertEqual(summary["tool"], {"huggingface_hub": "1.0"})
        self.assertFalse(summary["shard_sizes_all_equal_stat"])
        self.assertTrue(summary["shards_recorded_equal_shards_extracted"])
        self.assertEqual(summary["per_file_records"]["shards_with_sha256"], 2)
        self.assertNotIn("/Users/", repr(summary))
        self.assertIn("NOT re-verified", summary["label"])

    def test_layer_type_lists_are_summarized_with_positions(self):
        facts = builder._config_facts({"num_hidden_layers": 3,
                                       "mlp_layer_types": ["dense", "sparse", "sparse"],
                                       "private": "ignored"})
        self.assertEqual(facts["label"], "config-reported, not verified")
        self.assertEqual(facts["top_level"]["mlp_layer_types"]["positions"],
                         {"dense": [0], "sparse": [1, 2]})
        self.assertNotIn("private", facts["top_level"])


if __name__ == "__main__":
    unittest.main()

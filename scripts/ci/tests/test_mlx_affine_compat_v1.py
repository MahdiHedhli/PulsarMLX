"""The R2 compatibility script's report schema, and its fail-closed rule.

Stdlib only, and deliberately free of MLX: this module runs under the system
interpreter in the workspace job, where MLX is not installed. It therefore
tests the script's shape, its shard reader, its resolution rule and its refusal
behaviour -- the observation itself is made by the script in the native
small-fixture job.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.ci import mlx_affine_compat_v1 as compat

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/mlx_affine_compat_v1.py"
FIXTURES = ROOT / "fixtures/safetensors"

REQUIRED_ENVIRONMENT_KEYS = {
    "interpreter",
    "python_version",
    "platform",
    "machine",
    "mlx_version",
    "mlx_metal_version",
    "default_device",
    "metal_available",
}


class ShardReader(unittest.TestCase):
    def test_it_reads_a_committed_single_shard_checkpoint(self):
        tensors = compat.read_checkpoint(FIXTURES / "uniform-affine-v1")
        self.assertEqual(len(tensors), 9)
        weight = tensors["block.0.proj.weight"]
        self.assertEqual(weight["dtype"], "U32")
        self.assertEqual(len(weight["bytes"]), 4 * weight["shape"][0] * weight["shape"][1])

    def test_it_reads_a_committed_sharded_checkpoint(self):
        tensors = compat.read_checkpoint(FIXTURES / "mixed-4-8-v1")
        self.assertEqual(len(tensors), 17)
        self.assertIn("block.2.experts.weight", tensors)
        self.assertEqual(tensors["block.1.router.correction"]["dtype"], "F32")


class Resolution(unittest.TestCase):
    CONFIG = {"quantization": {"bits": 4, "group_size": 64,
                               "m.over": {"bits": 8, "group_size": 32}}}

    def test_an_explicit_override_wins(self):
        self.assertEqual(compat.resolve_spec(self.CONFIG, "m.over", True), (8, 32))

    def test_the_default_applies_only_when_scales_exist(self):
        self.assertEqual(compat.resolve_spec(self.CONFIG, "m.plain", True), (4, 64))
        self.assertIsNone(compat.resolve_spec(self.CONFIG, "m.plain", False))

    def test_a_silent_configuration_resolves_to_nothing(self):
        self.assertIsNone(compat.resolve_spec({}, "m.plain", True))


class FailClosed(unittest.TestCase):
    def run_script(self, require: bool):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            environment = {"PATH": "/usr/bin:/bin"}
            if require:
                environment["PULSAR_REQUIRE_NATIVE_MLX"] = "1"
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--output", str(output)],
                cwd=str(ROOT), capture_output=True, text=True, env=environment, timeout=300,
            )
            return result, json.loads(output.read_text())

    def test_an_unusable_mlx_is_a_failure_when_native_execution_is_required(self):
        result, report = self.run_script(require=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["result"], "UNAVAILABLE")
        self.assertTrue(report["require_native_mlx"])
        self.assertIn("not a skip", result.stderr)

    def test_an_unusable_mlx_is_still_reported_when_it_is_not_required(self):
        result, report = self.run_script(require=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["result"], "UNAVAILABLE")
        self.assertFalse(report["require_native_mlx"])
        self.assertIn("not required", result.stdout)
        # Not required is not the same as silent.
        self.assertIn("detail", report)


class Schema(unittest.TestCase):
    def test_an_unavailable_report_carries_the_fixed_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            report = {
                "schema": compat.SCHEMA,
                "arm": "R2",
                "is_correctness_oracle": False,
                "require_native_mlx": False,
                "fixture_manifest_sha256": None,
            }
            compat.unavailable(output, report, "synthetic")
            written = json.loads(output.read_text())
        self.assertEqual(written["schema"], "pulsarmlx.f020.mlx-affine-compatibility/1.0.0")
        self.assertEqual(written["arm"], "R2")
        self.assertFalse(written["is_correctness_oracle"])
        self.assertEqual(written["result"], "UNAVAILABLE")
        self.assertEqual(written["detail"], "synthetic")

    def test_the_script_declares_it_is_not_the_correctness_oracle(self):
        text = SCRIPT.read_text()
        self.assertIn("not** the numerical correctness oracle", text)
        self.assertIn('"is_correctness_oracle": False', text)

    def validate_full_report(self, report):
        """The shape a PASS report must have; used on a real run's output."""
        self.assertEqual(report["schema"], compat.SCHEMA)
        self.assertEqual(report["arm"], "R2")
        self.assertFalse(report["is_correctness_oracle"])
        self.assertIn(report["result"], {"PASS", "FAIL"})
        self.assertEqual(REQUIRED_ENVIRONMENT_KEYS, set(report["environment"]))
        self.assertGreater(report["quantized_modules_observed"], 0)
        self.assertEqual(set(report["cases"]), set(compat.POSITIVES))
        for entries in report["cases"].values():
            for entry in entries:
                self.assertIn("module", entry)
                self.assertIn(entry["result"],
                              {"PASS", "FAIL", "SKIPPED_UNQUANTIZED"})
                if entry["kind"] == "quantized":
                    self.assertIn(entry["bits"], (4, 8))
                    self.assertIn(entry["group_size"], (32, 64, 128))
                    self.assertIsInstance(entry["codes_exactly_equal"], bool)
                    self.assertIsInstance(entry["values_within_one_ulp"], bool)
                    self.assertGreaterEqual(entry["max_abs_difference"], 0.0)

    def test_a_recorded_report_validates_when_one_is_supplied(self):
        # The native job cats its report; when a copy is present in the
        # evidence directory, its shape is checked here too.
        evidence = ROOT / "docs/architecture/reviews/evidence/f020-slice1-numerics-results-v1.json"
        if not evidence.is_file():
            self.skipTest("no recorded numerics evidence in this tree")
        recorded = json.loads(evidence.read_text())
        observation = recorded.get("r2_compatibility_observation")
        if not observation or observation.get("result") == "UNAVAILABLE":
            self.skipTest("the recorded observation is not a completed run")
        self.validate_full_report(observation)

    def test_the_recorded_ci_report_validates_when_one_is_supplied(self):
        # Evidence here is append-only, so the CI run's own report is a
        # separate file rather than an edit to the one above.
        evidence = ROOT / "docs/architecture/reviews/evidence/f020-slice1-ci-numerics-results-v1.json"
        if not evidence.is_file():
            self.skipTest("no recorded CI numerics evidence in this tree")
        recorded = json.loads(evidence.read_text())
        self.assertFalse(recorded["r2_is_correctness_oracle"])
        self.assertTrue(recorded["r2_ci_summary"]["fixture_manifest_matches"])
        self.validate_full_report(recorded["r2_compatibility_observation_on_ci"])


if __name__ == "__main__":
    unittest.main()

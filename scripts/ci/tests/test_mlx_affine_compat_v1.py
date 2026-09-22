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


class StubbedRuntime(unittest.TestCase):
    """Both refusal branches, driven by an injected stub.

    Round 1 tested these by relying on the test interpreter not having MLX
    installed. That is an accident of the environment, not a test: it passes
    for the wrong reason wherever MLX happens to be absent and stops testing
    anything wherever it is present. Injecting a loader makes both branches
    deterministic on any machine.
    """

    class Device:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, type(self)) and other.name == self.name

        def __repr__(self):
            return f"Device({self.name})"

    def stub_mlx(self, metal_available=True, selection_sticks=True):
        test = self

        class Metal:
            @staticmethod
            def is_available():
                return metal_available

        class Mx:
            metal = Metal
            gpu = test.Device("gpu")
            cpu = test.Device("cpu")

            def __init__(self):
                self.selected = test.Device("cpu")

            def set_default_device(self, device):
                self.selected = device if selection_sticks else test.Device("cpu")

            def default_device(self):
                return self.selected

        return Mx()

    def test_an_absent_mlx_raises_rather_than_returning_a_runtime(self):
        def loader():
            raise ImportError("No module named 'mlx'")

        with self.assertRaises(ImportError):
            compat.acquire_runtime(loader)

    def test_unavailable_metal_is_refused(self):
        mx = self.stub_mlx(metal_available=False)
        with self.assertRaises(compat.Refusal) as caught:
            compat.acquire_runtime(lambda: (mx, None, "0.32.0", "0.32.0"))
        self.assertIn("Metal is not available", str(caught.exception))

    def test_the_gpu_is_selected_explicitly_and_the_selection_is_asserted(self):
        mx = self.stub_mlx()
        self.assertEqual(mx.default_device(), mx.cpu, "the stub starts on the CPU")
        _, _, version, _ = compat.acquire_runtime(lambda: (mx, None, "0.32.0", "0.32.0"))
        self.assertEqual(version, "0.32.0")
        self.assertEqual(mx.default_device(), mx.gpu, "the GPU must be selected")

    def test_a_selection_that_does_not_take_is_refused(self):
        # Metal available and set_default_device silently ignored: the run
        # would otherwise proceed on the CPU while reporting a GPU claim.
        mx = self.stub_mlx(selection_sticks=False)
        with self.assertRaises(compat.Refusal) as caught:
            compat.acquire_runtime(lambda: (mx, None, "0.32.0", "0.32.0"))
        self.assertIn("after selecting the GPU", str(caught.exception))


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
        self.assertEqual(written["schema"], "pulsarmlx.f020.mlx-affine-compatibility/2.0.0")
        self.assertEqual(written["arm"], "R2")
        self.assertFalse(written["is_correctness_oracle"])
        self.assertEqual(written["result"], "UNAVAILABLE")
        self.assertEqual(written["detail"], "synthetic")

    def test_the_script_declares_it_is_not_the_correctness_oracle(self):
        text = SCRIPT.read_text()
        self.assertIn("not** the numerical correctness oracle", text)
        self.assertIn('"is_correctness_oracle": False', text)

    def validate_full_report(self, report):
        """The shape a PASS report must have; used on a real run's output.

        A Round 1 report is a valid 1.0.0 document and is not edited, so the
        fields 2.0.0 added are required only of 2.0.0 reports.
        """
        current = report["schema"] == compat.SCHEMA
        self.assertIn(
            report["schema"],
            {compat.SCHEMA, "pulsarmlx.f020.mlx-affine-compatibility/1.0.0"},
        )
        self.assertEqual(report["arm"], "R2")
        self.assertFalse(report["is_correctness_oracle"])
        self.assertIn(report["result"], {"PASS", "FAIL"})
        self.assertTrue(
            REQUIRED_ENVIRONMENT_KEYS.issubset(set(report["environment"])),
            set(report["environment"]),
        )
        if current:
            self.assertTrue(report["environment"]["gpu_explicitly_selected"])
        self.assertGreater(report["quantized_modules_observed"], 0)
        if not current:
            # A 1.0.0 report describes the corpus of its own round.
            self.assertTrue(set(report["cases"]))
            return
        self.assertEqual(set(report["cases"]), set(compat.POSITIVES))
        # The observation must cover every metadata width and group size the
        # representation admits, not only the ones the first fixtures used.
        combinations = {
            (entry["bits"], entry["group_size"], entry["metadata_dtype"])
            for entries in report["cases"].values()
            for entry in entries
            if entry["kind"] == "quantized"
        }
        self.assertEqual(
            {dtype for _b, _g, dtype in combinations}, {"BF16", "F16", "F32"}
        )
        self.assertEqual({group for _b, group, _d in combinations}, {32, 64, 128})
        self.assertEqual({bits for bits, _g, _d in combinations}, {4, 8})
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

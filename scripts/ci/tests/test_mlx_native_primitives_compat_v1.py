"""The Slice 2B R2 script: labelling predicate, fail-closed rule, no gating.

Stdlib only and free of MLX, so it runs under the system interpreter; the
observation itself is made by the script in the native small-fixture job.
Every refusal branch is driven by an injected loader, not by whatever
happens to be installed (acceptance B11).
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.ci import mlx_native_primitives_compat_v1 as r2


class Labelling(unittest.TestCase):
    def test_the_quad_branch_is_tested_first(self):
        for k in (64, 128):
            self.assertFalse(r2.different_kernel_family(2, k, 32, 17))

    def test_the_predicate_needs_every_clause(self):
        self.assertTrue(r2.different_kernel_family(2, 256, 14, 15))
        self.assertFalse(r2.different_kernel_family(1, 256, 14, 15), "M_eff >= 2")
        self.assertFalse(r2.different_kernel_family(14, 256, 14, 15), "M_eff < L")
        self.assertFalse(r2.different_kernel_family(2, 256, 14, 14), "generation >= 15")
        self.assertFalse(r2.different_kernel_family(2, 256, 14, 15, transpose=False), "transpose")

    def test_generation_and_batch_limit_transcription(self):
        self.assertEqual(r2.architecture_generation("applegpu_g14s"), 14)
        self.assertEqual(r2.architecture_generation("applegpu_g15d"), 15)
        self.assertEqual(r2.architecture_generation("x"), 0)
        self.assertEqual(r2.qmv_batch_limit(256, 64, "applegpu_g14s"), 14)
        self.assertEqual(r2.qmv_batch_limit(256, 64, "applegpu_g15s"), 18)
        self.assertEqual(r2.qmv_batch_limit(4096, 64, "applegpu_g16d"), 18)
        self.assertEqual(r2.qmv_batch_limit(8192, 8192, "applegpu_g14s"), 6)

    def test_the_label_is_the_contract_label(self):
        self.assertEqual(r2.LABEL, "CROSS_VERSION_0.32.0_vs_0.31.2")


class StubMx:
    class Device:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, StubMx.Device) and other.name == self.name

    def __init__(self, metal=True, sticks=True):
        self.gpu, self.cpu = StubMx.Device("gpu"), StubMx.Device("cpu")
        self.selected = self.cpu
        self.sticks = sticks
        available = metal

        class Metal:
            @staticmethod
            def is_available():
                return available
        self.metal = Metal

    def set_default_device(self, d):
        self.selected = d if self.sticks else self.cpu

    def default_device(self):
        return self.selected


class FailClosed(unittest.TestCase):
    def run_main(self, require, loader):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r2.json"
            with mock.patch.object(r2, "REQUIRE", require), contextlib.redirect_stderr(io.StringIO()):
                code = r2.main(["--output", str(out)], loader=loader)
            return code, json.loads(out.read_text())

    def absent(self):
        raise ImportError("No module named 'mlx'")

    def test_an_absent_mlx_fails_closed_when_required(self):
        code, report = self.run_main(True, self.absent)
        self.assertEqual(code, 1)
        self.assertEqual(report["result"], "FAILED_CLOSED")
        self.assertFalse(report["gates_anything"])

    def test_an_absent_mlx_is_reported_not_run_when_not_required(self):
        code, report = self.run_main(False, self.absent)
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "NOT_RUN")

    def test_unavailable_metal_fails_closed(self):
        code, report = self.run_main(True, lambda: (StubMx(metal=False), None, "0.32.0", "0.32.0"))
        self.assertEqual(code, 1)
        self.assertIn("Metal is not available", report["detail"])

    def test_a_gpu_selection_that_does_not_take_fails_closed(self):
        code, report = self.run_main(True, lambda: (StubMx(sticks=False), None, "0.32.0", "0.32.0"))
        self.assertEqual(code, 1)
        self.assertIn("after selecting the GPU", report["detail"])


class NoGating(unittest.TestCase):
    def test_a_completed_observation_exits_zero_whatever_it_observed(self):
        # observe() is replaced: a record far outside the yardstick and not
        # bit-identical to R3 is recorded, and the exit status is still 0.
        record = {"label": r2.LABEL, "op": "quantized_matmul", "different_kernel_family": True,
                  "compatibility_observation": True, "gates": False,
                  "margin_vs_exact_r1": {"worst_ratio": 7.0, "elements_over_yardstick": 3},
                  "bit_identical_to_r3": {"elements": 4, "identical": 0, "all": False, "claimed": False}}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "r2.json"
            with mock.patch.object(r2, "observe", lambda *a: {"case": record}), \
                    mock.patch.object(r2, "device_architecture", lambda mx: "applegpu_g15s"), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = r2.main(["--output", str(out)], loader=lambda: (StubMx(), None, "0.32.0", "0.32.0"))
            report = json.loads(out.read_text())
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "OBSERVED")
        self.assertEqual(report["summary"]["records_over_yardstick"], ["case"])
        self.assertTrue(report["summary"]["every_record_labelled"])


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, RESEARCH / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATOR = load("f017_m1e_activation", "generate_f017_m1e_activation.py")
PREPARER = load("f017_m1e_preparer", "prepare_f017_m1e_real_reference.py")


class M1EPackageTests(unittest.TestCase):
    def test_activation_is_deterministic_real_width_and_committed(self):
        generated = GENERATOR.document()
        committed = json.loads((ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json").read_text())
        self.assertEqual(generated, committed)
        self.assertEqual(generated["activation"]["element_count"], 6144)
        self.assertEqual(generated["generator"], {"algorithm":"normal_f32_with_frozen_stress_prefix_v1","numpy":"2.4.5","prng":"PCG64","python":"3.13.13","seed":17017005})

    def test_oracle_finalization_is_exclusive_and_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oracle.json"
            digest = PREPARER.exclusive_finalize(path, {"finalized": True})
            self.assertEqual(len(digest), 64)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), stat.S_IRUSR)
            with self.assertRaises(FileExistsError):
                PREPARER.exclusive_finalize(path, {"changed": True})

    def test_stress_shapes_and_composed_bounds_are_candidate_independent(self):
        subnormal = np.nextafter(np.float32(0.0), np.float32(1.0))
        fixtures = {
            "gate_up_cancellation": np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32),
            "high_dynamic_range": np.array([127.0, -127.0, 1e-10, -1e-10], dtype=np.float32),
            "near_zero_activation": np.array([1e-30, -1e-30, 0.0, -0.0], dtype=np.float32),
            "subnormal_and_signed_zero": np.array([subnormal, -subnormal, 0.0, -0.0], dtype=np.float32),
            "simultaneous_upstream_error_directions": np.array([4.0, -4.0, 0.25, -0.25], dtype=np.float32),
        }
        matrices = [
            np.array([[1.0, 1.0, -1.0, -1.0], [1e10, -1e10, 1e-10, -1e-10]], dtype=np.float32),
            np.array([[-1.0, 1.0, 1.0, -1.0], [0.25, -0.25, 8.0, -8.0]], dtype=np.float32),
        ]
        down = np.array([[1.0, -1.0], [-1e-5, 1e-5], [64.0, -64.0], [1e-20, 1e-20]], dtype=np.float32)
        for label, activation in fixtures.items():
            gate = PREPARER.strict_matvec(matrices[0], activation)
            up = PREPARER.strict_matvec(matrices[1], activation)
            hidden = PREPARER.strict_swiglu(gate, up)
            output = PREPARER.strict_matvec(down, hidden)
            bounds = PREPARER.composed_bounds(matrices[0], matrices[1], down, activation, gate, up, hidden)
            self.assertTrue(all(np.isfinite(value).all() and (value >= 0).all() for value in bounds), label)
            self.assertTrue(np.isfinite(output).all(), label)

        edge_gate = np.array([-80.0, -0.0, 0.0, 80.0], dtype=np.float32)
        edge_up = np.array([1.0, -1.0, 1.0, 1.0], dtype=np.float32)
        edge_hidden = PREPARER.strict_swiglu(edge_gate, edge_up)
        self.assertTrue(np.isfinite(edge_hidden).all(), "silu_edge_behavior")

        # Exercise a final result close to the useful f32 exponent limit while
        # staying finite. This is an admission stress case, not a threshold-
        # fitting observation.
        near_overflow_input = np.array([1.0], dtype=np.float32)
        near_overflow_gate_matrix = np.array([[1e17]], dtype=np.float32)
        near_overflow_up_matrix = np.array([[1.0]], dtype=np.float32)
        near_overflow_down_matrix = np.array([[1e20]], dtype=np.float32)
        near_overflow_gate = PREPARER.strict_matvec(near_overflow_gate_matrix, near_overflow_input)
        near_overflow_up = PREPARER.strict_matvec(near_overflow_up_matrix, near_overflow_input)
        near_overflow_hidden = PREPARER.strict_swiglu(near_overflow_gate, near_overflow_up)
        near_overflow_output = PREPARER.strict_matvec(near_overflow_down_matrix, near_overflow_hidden)
        near_overflow_bounds = PREPARER.composed_bounds(
            near_overflow_gate_matrix,
            near_overflow_up_matrix,
            near_overflow_down_matrix,
            near_overflow_input,
            near_overflow_gate,
            near_overflow_up,
            near_overflow_hidden,
        )
        self.assertTrue(np.isfinite(near_overflow_output).all(), "near_overflow_finite")
        self.assertTrue(all(np.isfinite(value).all() for value in near_overflow_bounds), "near_overflow_bounds")

    def test_zero_up_lane_retains_silu_bound_contribution(self):
        gate_matrix = np.array([[2.0]], dtype=np.float32)
        up_matrix = np.array([[0.0]], dtype=np.float32)
        down_matrix = np.array([[1.0]], dtype=np.float32)
        activation = np.array([1.0], dtype=np.float32)
        gate = PREPARER.strict_matvec(gate_matrix, activation)
        up = PREPARER.strict_matvec(up_matrix, activation)
        hidden = PREPARER.strict_swiglu(gate, up)
        bounds = PREPARER.composed_bounds(
            gate_matrix, up_matrix, down_matrix, activation, gate, up, hidden
        )
        self.assertGreater(bounds[2][0], 0.0)

    def test_preparer_has_no_candidate_or_ffi_dependency(self):
        source = (RESEARCH / "prepare_f017_m1e_real_reference.py").read_text()
        for forbidden in ("import ctypes", "import cffi", "import mlx", "from mlx"):
            self.assertNotIn(forbidden, source.lower())

    def test_execution_config_preparer_is_exclusive_and_binds_one_expert(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            package = temporary / "private"
            package.mkdir()
            environment = temporary / "environment.json"
            environment.write_text("{}")
            shard = temporary / "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
            shard.write_bytes(b"metadata-only")
            checkpoint = temporary / "checkpoint.json"
            checkpoint.write_text(json.dumps({"shards":[{"filename":shard.name,"size_bytes":shard.stat().st_size,"sha256":"d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"}]}))
            output = temporary / "config.json"
            command = [sys.executable, str(RESEARCH / "prepare_f017_m1e_execution.py"), "--repository-root", str(ROOT), "--package-root", str(package), "--environment-manifest", str(environment), "--checkpoint-manifest", str(checkpoint), "--target-shard", str(shard), "--runner-binary", sys.executable, "--oracle-launcher", sys.executable, "--runtime-sha", "1" * 40, "--tooling-sha", "2" * 40, "--output", str(output), "--mode", "fixture_expert"]
            first = subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual(len(first.stdout.strip()), 64)
            document = json.loads(output.read_text())
            self.assertEqual(document["schema_version"], "2.0.0")
            self.assertEqual(document["attempt"], 2)
            self.assertEqual(document["expert"], {"layer":3,"expert":15,"symbolic_id":"blk.3.expert.15"})
            self.assertEqual([tensor["role"] for tensor in document["tensors"]], ["gate", "up", "down"])
            self.assertEqual(document["execution"]["native_dispatch_count"], 30)
            self.assertEqual(document["activation_fixture"]["symbolic_path"], "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json")
            self.assertEqual(
                document["repository_artifacts"]["decoder_contract"]["symbolic_path"],
                "specs/017-rust-native-inference-runtime/contracts/m1e-decoder-contract-v2.json",
            )
            self.assertEqual(
                document["prior_evidence"]["m1_e_attempt_1"],
                "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119",
            )
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)


if __name__ == "__main__":
    unittest.main()

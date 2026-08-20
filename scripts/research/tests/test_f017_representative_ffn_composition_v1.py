#!/usr/bin/env python3
"""Checkpoint-free tests for shared-output reuse and FFN composition v1."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


def load_module(name: str, relative: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


validator = load_module(
    "f017_ffn_validator",
    "scripts/research/validate_f017_representative_ffn_composition_v1.py",
)
executor = load_module(
    "f017_ffn_executor",
    "scripts/research/f017_representative_ffn_composition_executor_v1.py",
)


class FFNCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shared = validator.load(validator.SHARED_REUSE)
        cls.authorization = validator.load(validator.FFN_AUTHORIZATION)

    def test_committed_package_validates_against_producer_bytes(self) -> None:
        validator.validate_shared_reuse(copy.deepcopy(self.shared), repo=True)
        validator.validate_ffn(copy.deepcopy(self.authorization), repo=True)

    def test_shared_reuse_mutations_fail_closed(self) -> None:
        mutations = (
            lambda value: value.__setitem__("preparation_base_head", "0" * 40),
            lambda value: value["source_authority"]["execution_evidence"].__setitem__("sha256", "0" * 64),
            lambda value: value["retained_shared_output"].__setitem__("sha256", validator.HISTORICAL_SHARED_SHA),
            lambda value: value["retained_shared_output"].__setitem__("byte_length", 8),
            lambda value: value["retained_shared_output"].__setitem__("dtype", "little-endian-f64"),
            lambda value: value["retained_shared_output"].__setitem__("expected_equals_before_equals_consumed_equals_after", False),
            lambda value: value["retained_shared_output"].__setitem__("read_only", False),
            lambda value: value["retained_shared_output"].__setitem__("hard_link_count", 2),
            lambda value: value["surface_isolation"].__setitem__("checkpoint_fallback", True),
            lambda value: value["consumer_scope"].__setitem__("ffn_completion", True),
            lambda value: value["accounting"].__setitem__("real_payload_ledger_after", 176),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(self.shared)
                mutation(candidate)
                with self.assertRaises(validator.ValidationError):
                    validator.validate_shared_reuse(candidate, repo=False)

    def test_ffn_authorization_mutations_fail_closed(self) -> None:
        mutations = (
            lambda value: value.__setitem__("preparation_head", "0" * 40),
            lambda value: value["bindings"]["routed_reuse_authorization"].__setitem__("sha256", "0" * 64),
            lambda value: value["bindings"]["shared_reuse_authorization"].__setitem__("sha256", "0" * 64),
            lambda value: value["inputs"]["routed"]["artifact"].__setitem__("sha256", "0" * 64),
            lambda value: value["inputs"]["shared"]["artifact"].__setitem__("sha256", validator.HISTORICAL_SHARED_SHA),
            lambda value: value.__setitem__("semantic_classification", "PRODUCTION_SERIAL_F32"),
            lambda value: value["arithmetic"].__setitem__("shared_promotion", "f32"),
            lambda value: value["arithmetic"].__setitem__("addition_order", "Shared then Routed"),
            lambda value: value["arithmetic"].__setitem__("addition_dtype", "IEEE-754 binary32"),
            lambda value: value["arithmetic"].__setitem__("blas", True),
            lambda value: value["future_output"].__setitem__("dtype", "little-endian-f32"),
            lambda value: value["future_single_use"].__setitem__("retry", True),
            lambda value: value["future_single_use"].__setitem__("second_attempt", True),
            lambda value: value["s1_and_s2_boundary"].__setitem__("s1_sha256", "0" * 64),
            lambda value: value["s1_and_s2_boundary"].__setitem__("s1_materialization_authorized", True),
            lambda value: value["s1_and_s2_boundary"].__setitem__("s2_authorized", True),
            lambda value: value["accounting"].__setitem__("starting_ledger", 174),
            lambda value: value["accounting"].__setitem__("future_checkpoint_read_budget", 1),
            lambda value: value["accounting"].__setitem__("future_shard_open_budget", 1),
            lambda value: value["accounting"].__setitem__("future_expert_execution_budget", 1),
            lambda value: value["accounting"].__setitem__("future_shared_expert_execution_budget", 1),
            lambda value: value["accounting"].__setitem__("future_ffn_composition_count", 2),
            lambda value: value["accounting"].__setitem__("future_s2_construction_budget", 1),
            lambda value: value["prohibitions"].__setitem__("production_serial_f32_substitution", False),
            lambda value: value.__setitem__("stop_boundary", "AFTER_S2"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(self.authorization)
                mutation(candidate)
                with self.assertRaises(validator.ValidationError):
                    validator.validate_ffn(candidate, repo=False)

    def test_composition_matches_exact_binary64_coordinate_addition(self) -> None:
        routed_values = [float(index) / 8.0 for index in range(6144)]
        shared_values = [(-1.0 if index % 2 else 1.0) * float(index % 17) / 16.0 for index in range(6144)]
        routed = struct.pack("<6144d", *routed_values)
        shared = struct.pack("<6144f", *shared_values)
        result = struct.unpack("<6144d", executor.compose_bytes(routed, shared))
        expected = tuple(routed_value + float(shared_value) for routed_value, shared_value in zip(routed_values, struct.unpack("<6144f", shared), strict=True))
        self.assertEqual(result, expected)

    def test_nonfinite_and_wrong_geometry_reject(self) -> None:
        routed = bytearray(struct.pack("<6144d", *([0.0] * 6144)))
        shared = bytearray(struct.pack("<6144f", *([0.0] * 6144)))
        struct.pack_into("<d", routed, 0, math.nan)
        with self.assertRaises(executor.CompositionError):
            executor.compose_bytes(bytes(routed), bytes(shared))
        struct.pack_into("<d", routed, 0, 0.0)
        struct.pack_into("<f", shared, 0, math.inf)
        with self.assertRaises(executor.CompositionError):
            executor.compose_bytes(bytes(routed), bytes(shared))
        with self.assertRaises(executor.CompositionError):
            executor.compose_bytes(bytes(routed[:-1]), bytes(shared))

    def test_real_execution_cli_is_absent(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(validator.EXECUTOR),
                "--execute",
                "--routed-root", ".",
                "--shared-root", ".",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertTrue(
            "unrecognized arguments: --execute" in completed.stderr
            or "one of the arguments --preflight-only --synthetic-rehearsal is required" in completed.stderr
        )

    def test_synthetic_mode_rejects_protected_real_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {
                "schema": "pulsarmlx.f017.representative-ffn-composition-synthetic-input",
                "inputs": {
                    "routed": {"artifact": {"sha256": executor.REAL_ROUTED_SHA256}},
                    "shared": {"artifact": {"sha256": "0" * 64}},
                },
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            environment = dict(os.environ)
            environment.update({
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            })
            completed = subprocess.run(
                [
                    sys.executable,
                    str(validator.EXECUTOR),
                    "--synthetic-rehearsal",
                    "--synthetic-config", str(config_path),
                    "--routed-root", str(root),
                    "--shared-root", str(root),
                    "--output", str(root / "output.f64le"),
                ],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("REAL_INPUT_IN_SYNTHETIC_MODE", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()

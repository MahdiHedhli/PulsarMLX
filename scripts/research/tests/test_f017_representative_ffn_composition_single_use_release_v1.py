#!/usr/bin/env python3
"""Checkpoint-free mutation and durability tests for FFN release v1."""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))


def module(name: str, relative: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert specification and specification.loader
    value = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(value)
    return value


validator = module("f017_ffn_release_validator", "scripts/research/validate_f017_representative_ffn_composition_single_use_release_v1.py")
wrapper = module("f017_ffn_release_wrapper", "scripts/research/f017_representative_ffn_composition_release_wrapper_v1.py")
terminalizer = module("f017_ffn_release_terminalizer", "scripts/research/f017_representative_ffn_composition_release_terminalizer_v1.py")


class FFNReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.release = validator.load(validator.RELEASE_PATH)

    def reject(self, mutation) -> None:
        candidate = copy.deepcopy(self.release)
        mutation(candidate)
        with self.assertRaises((validator.ValidationError, KeyError, TypeError)):
            validator.validate(candidate, repo=False)

    def test_repository_release_passes(self) -> None:
        validator.validate(copy.deepcopy(self.release), repo=True)

    def test_load_bearing_mutations_reject(self) -> None:
        mutations = [
            lambda d: d.__setitem__("authoritative_execution_code_head", "0" * 40),
            lambda d: d["bindings"]["ffn_authorization"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["arithmetic_contract"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["routed_reuse_authorization"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["shared_reuse_authorization"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["executor"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["synthetic_rehearsal"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["ffn_authorization_review"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["release_wrapper"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["terminalizer"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["release_rehearsal"].__setitem__("sha256", "0" * 64),
            lambda d: d["retained_inputs"]["routed"].__setitem__("sha256", "0" * 64),
            lambda d: d["retained_inputs"]["routed"].__setitem__("private_manifest_sha256", "0" * 64),
            lambda d: d["retained_inputs"]["shared"].__setitem__("sha256", "0" * 64),
            lambda d: d["retained_inputs"]["shared"].__setitem__("private_manifest_sha256", "0" * 64),
            lambda d: d["numerical_surface"].__setitem__("classification", "PRODUCTION_SERIAL_F32"),
            lambda d: d["numerical_surface"].__setitem__("shared_promotion", "f32"),
            lambda d: d["numerical_surface"].__setitem__("addition", "f32 accumulation"),
            lambda d: d["numerical_surface"].__setitem__("blas", True),
            lambda d: d["numerical_surface"].__setitem__("gpu", True),
            lambda d: d["preexecution_gates"].__setitem__("all_locally_checkable_before_ffn", False),
            lambda d: d["single_use"].__setitem__("exclusive_attempt_creation", False),
            lambda d: d["single_use"].__setitem__("retry", True),
            lambda d: d["single_use"].__setitem__("resume", True),
            lambda d: d["single_use"].__setitem__("second_attempt", True),
            lambda d: d["single_use"].__setitem__("ffn_execution_counted_at", "OUTPUT_PUBLICATION"),
            lambda d: d["output_banking"].__setitem__("dtype", "little-endian-f32"),
            lambda d: d["output_banking"].__setitem__("byte_length", 24576),
            lambda d: d["output_banking"].__setitem__("private_manifest", False),
            lambda d: d["output_banking"].__setitem__("execution_receipt", False),
            lambda d: d["output_banking"].__setitem__("matching_complete_terminal_required", False),
            lambda d: d["output_banking"].__setitem__("overwrite", True),
            lambda d: d["machine_local_paths"].__setitem__("output", "/tmp/output"),
            lambda d: d["runtime"].__setitem__("cpython", "3.13"),
            lambda d: d["accounting"].__setitem__("starting_ledger", 174),
            lambda d: d["accounting"].__setitem__("checkpoint_reads", 1),
            lambda d: d["accounting"].__setitem__("shard_opens", 1),
            lambda d: d["accounting"].__setitem__("expert_executions", 1),
            lambda d: d["accounting"].__setitem__("shared_expert_executions", 1),
            lambda d: d["accounting"].__setitem__("future_ffn_compositions", 2),
            lambda d: d["accounting"].__setitem__("s1_materializations", 1),
            lambda d: d["accounting"].__setitem__("s2_constructions", 1),
            lambda d: d["prohibitions"].__setitem__("s1_input_interface", False),
            lambda d: d["prohibitions"].__setitem__("s2_construction", False),
            lambda d: d.__setitem__("stop_boundary", "AFTER_S2"),
            lambda d: d.__setitem__("approval_asserted", True),
            lambda d: d.__setitem__("real_event_authorized", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.reject(mutation)

    def test_output_validation_rejects_wrong_geometry_and_nonfinite(self) -> None:
        with self.assertRaises(wrapper.ReleaseError):
            wrapper.validate_output(bytes(wrapper.OUTPUT_BYTES - 1))
        raw = bytearray(wrapper.OUTPUT_BYTES)
        struct.pack_into("<d", raw, 0, math.nan)
        with self.assertRaises(wrapper.ReleaseError):
            wrapper.validate_output(bytes(raw))

    def test_publication_is_no_replace_read_only_and_finite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            os.chmod(root, 0o700)
            raw = bytes(wrapper.OUTPUT_BYTES)
            output_sha, manifest_sha = wrapper.publish_output_and_manifest(raw, root)
            self.assertEqual(output_sha, wrapper.sha256_bytes(raw))
            self.assertEqual(len(manifest_sha), 64)
            for name in (wrapper.OUTPUT_BASENAME, wrapper.MANIFEST_BASENAME):
                metadata = (root / name).lstat()
                self.assertEqual(metadata.st_nlink, 1)
                self.assertEqual(metadata.st_mode & 0o777, 0o400)
            with self.assertRaises(wrapper.ReleaseError):
                wrapper.publish_output_and_manifest(raw, root)

    def test_terminalizer_rejects_complete_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = wrapper.fixed_paths(Path(temporary))
            paths["release_root"].mkdir(parents=True, mode=0o700)
            paths["output_root"].mkdir(mode=0o700)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            for path in (release, approval, token):
                path.write_text("{}\n", encoding="utf-8")
                os.chmod(path, 0o400)
            wrapper.begin_attempt(paths, release, approval, token)
            wrapper.begin_ffn(paths, release)
            output_sha, manifest_sha = wrapper.publish_output_and_manifest(bytes(wrapper.OUTPUT_BYTES), paths["output_root"])
            wrapper.write_terminal(paths, "TERMINAL_FAILURE", output_sha, manifest_sha, None, "test")
            result = terminalizer.reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
            self.assertEqual(result["disposition"], "TERMINAL_FAILURE_RECONSTRUCTED")
            self.assertFalse(result["output_authority"])


if __name__ == "__main__":
    unittest.main()

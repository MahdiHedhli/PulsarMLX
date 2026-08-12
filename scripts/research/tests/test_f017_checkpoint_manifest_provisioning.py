import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

import provision_f017_checkpoint_manifest as subject  # noqa: E402


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fake_manifest() -> dict:
    shards = []
    for index, name in enumerate(subject.EXPECTED_BASENAMES, start=1):
        shards.append(
            {"filename": name, "size_bytes": index, "sha256": digest(bytes([index]))}
        )
    return {
        "schema": subject.MANIFEST_SCHEMA,
        "schema_version": subject.MANIFEST_VERSION,
        "kind": "production",
        "immutable_revision": subject.CHECKPOINT_REVISION,
        "architecture": subject.ARCHITECTURE,
        "tokenizer_identity": "glm52-gguf-tokenizer-v1:" + "a" * 64,
        "checkpoint_set_sha256": subject.checkpoint_set_sha256(shards),
        "catalog_sha256": "b" * 64,
        "tensor_count": subject.EXPECTED_TENSOR_COUNT,
        "shards": shards,
    }


def fake_review() -> dict:
    return {
        "schema": subject.REVIEW_SCHEMA,
        "schema_version": subject.REVIEW_VERSION,
        "manifest_kind": subject.MANIFEST_KIND,
        "runtime_source_sha": subject.RUNTIME_SOURCE_SHA,
        "privacy": "public_safe_hashes_and_basenames_only",
        "checkpoint": {
            "architecture": subject.ARCHITECTURE,
            "layer_count": subject.EXPECTED_LAYER_COUNT,
            "tensor_count": subject.EXPECTED_TENSOR_COUNT,
            "shard_count": 6,
        },
        "execution_policy": {
            "identity_only": True,
            "tensor_execution_authorized": False,
            "quant_decode_authorized": False,
            "model_compute_authorized": False,
        },
        "validation": {
            "six_shards": True,
            "sizes_and_hashes": True,
            "architecture": True,
            "tokenizer_identity": True,
            "catalog_matches_committed_identity": True,
            "tensor_map_contract_compatible": True,
            "zero_tensor_execution": True,
            "zero_quant_decode": True,
            "zero_model_compute": True,
        },
    }


class ManifestValidatorTests(unittest.TestCase):
    def test_six_valid_fake_shards_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in subject.EXPECTED_BASENAMES:
                (root / name).write_bytes(b"fixture")
            self.assertEqual(
                [path.name for path in subject.discover_canonical_shards(root)],
                subject.EXPECTED_BASENAMES,
            )

    def test_valid_six_shard_manifest(self):
        subject.validate_runner_manifest(fake_manifest())

    def test_wrong_shard_count_and_duplicate_are_rejected(self):
        manifest = fake_manifest()
        manifest["shards"].pop()
        with self.assertRaises(subject.ProvisioningError):
            subject.validate_runner_manifest(manifest)
        manifest = fake_manifest()
        manifest["shards"][1]["filename"] = manifest["shards"][0]["filename"]
        with self.assertRaises(subject.ProvisioningError):
            subject.validate_runner_manifest(manifest)

    def test_wrong_size_hash_and_basename_are_rejected(self):
        for mutate in (
            lambda manifest: manifest["shards"][0].update(size_bytes=0),
            lambda manifest: manifest["shards"][0].update(sha256="bad"),
            lambda manifest: manifest["shards"][0].update(filename="other.gguf"),
        ):
            manifest = fake_manifest()
            mutate(manifest)
            with self.assertRaises(subject.ProvisioningError):
                subject.validate_runner_manifest(manifest)

    def test_wrong_architecture_tokenizer_tensor_expectation_and_schema_are_rejected(self):
        cases = (
            ("architecture", "other"),
            ("tokenizer_identity", "unbound"),
            ("tensor_count", 1),
            ("schema_version", "2.0.0"),
        )
        for key, value in cases:
            manifest = fake_manifest()
            manifest[key] = value
            with self.assertRaises(subject.ProvisioningError):
                subject.validate_runner_manifest(manifest)

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links unavailable")
    def test_symlink_checkpoint_shard_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, name in enumerate(subject.EXPECTED_BASENAMES):
                path = root / name
                if index == 0:
                    target = root / "target"
                    target.write_bytes(b"x")
                    path.symlink_to(target)
                else:
                    path.write_bytes(b"x")
            with self.assertRaises(subject.ProvisioningError):
                subject.discover_canonical_shards(root)

    def test_public_projection_rejects_path_leak_and_execution_authority(self):
        review = fake_review()
        review["local_path"] = "/" + "Users/private/checkpoint"
        with self.assertRaises(subject.ProvisioningError):
            subject.validate_public_review(review)
        review = fake_review()
        review["execution_policy"]["tensor_execution_authorized"] = True
        with self.assertRaises(subject.ProvisioningError):
            subject.validate_public_review(review)


class SourceBindingTests(unittest.TestCase):
    def test_committed_admission_binding_is_self_consistent(self):
        binding = subject.load_json(
            ROOT / "docs/architecture/reviews/evidence/f017-m1-b-admission-binding-v1.json"
        )
        subject.validate_admission_binding(ROOT, binding)

    def test_admission_binding_rejects_stale_runtime(self):
        binding = subject.load_json(
            ROOT / "docs/architecture/reviews/evidence/f017-m1-b-admission-binding-v1.json"
        )
        binding["required_runtime_source_sha"] = (
            "91359dd59265de71fd25848142af23823e41e160"
        )
        with self.assertRaises(subject.ProvisioningError):
            subject.validate_admission_binding(ROOT, binding)

    def test_exact_runtime_sha_passes(self):
        self.assertEqual(
            subject.validate_runtime_source_binding(
                ROOT, subject.RUNTIME_SOURCE_SHA, subject.RUNTIME_SOURCE_SHA
            ),
            [],
        )

    def test_old_handoff_pin_fails_after_compiled_runner_change(self):
        with self.assertRaises(subject.ProvisioningError):
            subject.validate_runtime_source_binding(
                ROOT,
                "91359dd59265de71fd25848142af23823e41e160",
                subject.RUNTIME_SOURCE_SHA,
            )

    def test_docs_and_provisioning_tool_descendant_is_non_runtime(self):
        self.assertTrue(
            subject.runtime_delta_is_non_runtime(
                [
                    "docs/architecture/reviews/handoff.md",
                    "scripts/research/provision_f017_checkpoint_manifest.py",
                    "scripts/research/tests/test_f017_checkpoint_manifest_provisioning.py",
                    "specs/017-rust-native-inference-runtime/tasks.md",
                ]
            )
        )
        self.assertFalse(subject.runtime_delta_is_non_runtime(["crates/f017-runner/src/lib.rs"]))


class ExclusiveWriteTests(unittest.TestCase):
    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                subject.write_exclusive(path, b"replacement")
            self.assertEqual(path.read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()

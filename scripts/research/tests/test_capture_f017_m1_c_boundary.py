import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

import capture_f017_m1_c_boundary as subject  # noqa: E402


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class CaptureTests(unittest.TestCase):
    def test_f32_diagnostics_preserve_exact_bits(self):
        payload = b"\x00\x00\x80?\x00\x00\x00\x80"
        diagnostics, decoded = subject.f32_diagnostics(payload, [2])
        self.assertEqual(decoded, payload)
        self.assertEqual(diagnostics["element_count"], 2)
        self.assertEqual(diagnostics["finite_count"], 2)
        self.assertEqual(diagnostics["signed_zero_count"], 1)

    def test_f32_diagnostics_reject_shape_and_nonfinite(self):
        with self.assertRaises(subject.CaptureError):
            subject.f32_diagnostics(b"\x00" * 4, [2])
        with self.assertRaises(subject.CaptureError):
            subject.f32_diagnostics(b"\x00\x00\x80\x7f", [1])

    def test_exclusive_outputs_reject_stale_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing"
            existing.write_bytes(b"do not overwrite")
            with self.assertRaises(FileExistsError):
                subject.reserve_outputs([root / "new", existing])
            self.assertFalse((root / "new").exists())
            self.assertEqual(existing.read_bytes(), b"do not overwrite")

    def test_checkpoint_validation_rejects_symlink_and_manifest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shard = root / "fake.gguf"
            shard.write_bytes(b"fixture")
            manifest = {
                "kind": "production",
                "immutable_revision": subject.CHECKPOINT_REVISION,
                "architecture": "glm-dsa",
                "checkpoint_set_sha256": subject.CHECKPOINT_SET_SHA256,
                "catalog_sha256": subject.CATALOG_SHA256,
                "tensor_count": 1809,
                "shards": [
                    {"filename": "fake.gguf", "size_bytes": 7, "sha256": digest(b"fixture")}
                    for _ in range(6)
                ],
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            manifest_hash = digest(manifest_path.read_bytes())
            subject.validate_checkpoint_manifest(
                manifest_path,
                shard,
                expected_manifest_sha256=manifest_hash,
                expected_shard_basename="fake.gguf",
                expected_shard_sha256=digest(b"fixture"),
                expected_shard_size=7,
            )
            link = root / "link.gguf"
            link.symlink_to(shard)
            with self.assertRaises(subject.CaptureError):
                subject.validate_checkpoint_manifest(
                    manifest_path,
                    link,
                    expected_manifest_sha256=manifest_hash,
                    expected_shard_basename="link.gguf",
                    expected_shard_sha256=digest(b"fixture"),
                    expected_shard_size=7,
                )
            with self.assertRaises(subject.CaptureError):
                subject.validate_checkpoint_manifest(
                    manifest_path,
                    shard,
                    expected_manifest_sha256="0" * 64,
                    expected_shard_basename="fake.gguf",
                    expected_shard_sha256=digest(b"fixture"),
                    expected_shard_size=7,
                )

    def test_admission_rejects_fixture_or_unsafe_state(self):
        admission = {
            "environment_kind": "production_reviewed",
            "telemetry_source": "measured_host",
            "architecture": "arm64",
            "physical_memory_bytes": 128,
            "memory_floor_bytes": 16,
            "available_memory_bytes": 32,
            "memory_pressure": "normal",
            "swap_used_bytes": 0,
            "swap_safe": True,
            "checkpoint_volume_free_bytes": 1,
            "evidence_volume_free_bytes": 1,
            "load_averages": [0.1, 0.2, 0.3],
            "competing_inference_clear": True,
            "port_1234_listener": False,
            "thermal_state": "normal",
            "performance_warning": False,
            "mlx_native": {
                "version": "0.31.2",
                "sha256": "6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed",
                "architecture": "arm64",
                "matched": True,
            },
            "mlx_c": {
                "version": "0.6.0",
                "sha256": "a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62",
                "architecture": "arm64",
                "matched": True,
            },
        }
        subject.validate_admission(admission)
        admission["environment_kind"] = "checkpoint_free_fixture"
        with self.assertRaises(subject.CaptureError):
            subject.validate_admission(admission)


if __name__ == "__main__":
    unittest.main()

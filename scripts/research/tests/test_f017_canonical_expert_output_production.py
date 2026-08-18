"""Synthetic-only tests for the F017 canonical expert recovery production surface."""

from __future__ import annotations

import json
import os
import random
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.research import f017_canonical_expert_output_production as production
from scripts.research import validate_f017_canonical_expert_output_authorization as auth
from scripts.research.f017_canonical_expert_output_recovery_executor import (
    RecoveryExecutionError,
)


ROOT = Path(__file__).resolve().parents[3]


class ProductionSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            ["cargo", "build", "-p", "quant", "--bin", "f017-canonical-decode"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode(errors="replace"))

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_provider_has_one_capability_and_exact_pread(self) -> None:
        shard = self.root / production.SHARD_BASENAME
        shard.write_bytes(b"0123456789")
        provider = production.ProductionShardProvider(shard)
        handle = provider.open_shard(production.SHARD_SHA256)
        self.assertEqual(handle.read_at(2, 4, 0), b"2345")
        with self.assertRaisesRegex(RecoveryExecutionError, "SHARD_OPEN_BUDGET"):
            provider.open_shard(production.SHARD_SHA256)
        handle.close()
        self.assertEqual((provider.open_count, provider.read_count), (1, 1))

    def test_provider_rejects_wrong_basename_before_open(self) -> None:
        provider = production.ProductionShardProvider(self.root / "other.gguf")
        with self.assertRaisesRegex(RecoveryExecutionError, "SHARD_PATH_BINDING"):
            provider.open_shard(production.SHARD_SHA256)
        self.assertEqual(provider.open_count, 0)

    def test_decoder_pairs_are_independent_and_byte_only(self) -> None:
        pairs = production.production_decoder_pair(ROOT, fixture_mode=True)
        self.assertNotEqual(pairs.decoder_a_identity, pairs.decoder_b_identity)
        iq2 = bytes(66)
        iq3 = bytes(98)
        iq2_entry = {"quant_type": "IQ2_XXS", "logical_decoded_shape": [1, 256]}
        iq3_entry = {"quant_type": "IQ3_XXS", "logical_decoded_shape": [1, 256]}
        self.assertEqual(pairs.decoder_a(iq2, iq2_entry), pairs.decoder_b(iq2, iq2_entry))
        self.assertEqual(pairs.decoder_a(iq3, iq3_entry), pairs.decoder_b(iq3, iq3_entry))

    def test_decoder_pairs_exactly_agree_on_nonzero_adversarial_blocks(self) -> None:
        pairs = production.production_decoder_pair(ROOT, fixture_mode=True)
        for quantization, byte_count in (("IQ2_XXS", 66), ("IQ3_XXS", 98)):
            entry = {"quant_type": quantization, "logical_decoded_shape": [1, 256]}
            for seed in range(10):
                packed = bytearray(random.Random(seed).randbytes(byte_count))
                packed[0:2] = (0x3C00).to_bytes(2, "little")  # finite f16 scale 1.0
                self.assertEqual(
                    pairs.decoder_a(bytes(packed), entry),
                    pairs.decoder_b(bytes(packed), entry),
                    (quantization, seed),
                )

    def test_canonical_resolver_verifies_private_inputs(self) -> None:
        exact = self.root / "layer_3_entry.f32le"
        gamma = self.root / "ffn_norm_weight.bin"
        exact.write_bytes(b"\0" * 24_576)
        gamma.write_bytes(b"\0" * 24_576)
        exact.chmod(0o400)
        gamma.chmod(0o400)
        resolver = production.CanonicalInputResolver(
            exact, gamma,
            exact_sha256=production.sha256_path(exact),
            gamma_sha256=production.sha256_path(gamma),
        )
        value = resolver.resolve()
        self.assertEqual(value.exact_state.shape, (6144,))
        self.assertEqual(value.gamma.shape, (6144,))
        exact.chmod(0o600)
        with self.assertRaisesRegex(RecoveryExecutionError, "PRIVATE_INPUT_NOT_READ_ONLY"):
            resolver.resolve()

    def test_strict_f32_primitives_and_tiny_output(self) -> None:
        np = production.np
        x = np.asarray([1.0, -2.0, 3.0, -4.0], dtype="<f4")
        gamma = np.ones(4, dtype="<f4")
        normalized = production.strict_f32_rmsnorm(x, gamma, np.float32(1e-5))
        self.assertEqual(normalized.dtype, np.dtype("float32"))
        matrix = np.eye(4, dtype="<f4")
        self.assertEqual(
            production.strict_f32_matvec(matrix, normalized).tobytes(),
            normalized.tobytes(),
        )
        self.assertTrue(np.isfinite(production.strict_f32_silu(x)).all())

    def test_private_writer_is_atomic_read_only_and_alias_free(self) -> None:
        writer = production.PrivatePackageWriter(self.root / "package")
        artifact = writer.write("expert_outputs/expert_250_down_output.bin", b"abcd")
        mode = artifact.path.lstat().st_mode
        self.assertTrue(stat.S_ISREG(mode))
        self.assertFalse(mode & 0o222)
        self.assertEqual(artifact.path.stat().st_nlink, 1)
        self.assertEqual(artifact.sha256, production.sha256_path(artifact.path))

    def test_public_writer_strips_private_paths_and_payloads(self) -> None:
        writer = production.PublicEvidenceWriter(self.root / "public.json")
        result = writer.write({
            "classification": "COMPLETE",
            "output_sha256_by_expert": {"250": "a" * 64},
            "private_path": "/Users/example/private.bin",
            "payload": b"secret",
        })
        raw = result.read_text()
        self.assertNotIn("/Users/", raw)
        self.assertNotIn("secret", raw)
        self.assertNotIn("private_path", raw)

    def test_preflight_resolves_all_fourteen_without_side_effects(self) -> None:
        descriptor = production.build_preflight_descriptor(ROOT, fixture_mode=True)
        self.assertEqual(descriptor["status"], "PRODUCTION_BINDINGS_RESOLVED")
        self.assertEqual(len(descriptor["production_surfaces"]), 14)
        self.assertRegex(descriptor["reproduction_runner_identity"], r"^[0-9a-f]{64}$")
        self.assertRegex(descriptor["rust_decoder_binary_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(descriptor["checkpoint_reads"], 0)
        self.assertEqual(descriptor["shard_opens"], 0)
        self.assertFalse((self.root / "attempt.json").exists())

    def test_real_path_audit_allows_only_provider_boundary(self) -> None:
        audit = production.audit_checkpoint_capabilities(ROOT)
        self.assertEqual(audit["result"], "PASS")
        self.assertEqual(audit["capability_boundaries"], [
            "ProductionShardProvider.open_shard",
            "ProductionShardHandle.read_at",
        ])

    def test_synthetic_integration_matrix(self) -> None:
        result = production.run_synthetic_integration_rehearsal(ROOT)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["successful_entries"], 24)
        self.assertEqual(result["cases_passed"], result["cases_total"])
        self.assertEqual(result["real_ledger_after"], 139)

    def test_entrypoint_has_no_arbitrary_path_or_inventory_flags(self) -> None:
        parser = production.build_parser()
        actions = {flag for action in parser._actions for flag in action.option_strings}
        self.assertNotIn("--shard", actions)
        self.assertNotIn("--inventory", actions)
        self.assertNotIn("--experts", actions)
        self.assertIn("--preflight-only", actions)
        self.assertIn("--execute-reviewed-event", actions)

    def test_dry_run_never_calls_checkpoint_open(self) -> None:
        with mock.patch.object(production.ProductionShardProvider, "open_shard") as opened:
            descriptor = production.run_preflight(ROOT, fixture_mode=True)
        opened.assert_not_called()
        self.assertEqual(descriptor["checkpoint_reads"], 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.research.f017_representative_routed_aggregate_reuse_v1 import ReuseError, preflight_and_consume
from scripts.research.validate_f017_representative_routed_aggregate_reuse_v1 import AUTH, ValidationError, load, validate


class AuthorizationMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = load(AUTH)

    def rejects(self, mutation) -> None:
        value = copy.deepcopy(self.base)
        mutation(value)
        with self.assertRaises(ValidationError):
            validate(value, repo=False)

    def test_committed_authorization(self) -> None:
        validate(self.base, repo=True)

    def test_required_mutations(self) -> None:
        mutations = [
            lambda x: x.__setitem__("preparation_base_head", "0" * 40),
            lambda x: x["source_authority"]["execution_evidence"].__setitem__("sha256", "0" * 64),
            lambda x: x["source_authority"]["execution_evidence"].__setitem__("terminal", "TERMINAL_FAILURE"),
            lambda x: x["private_manifest"].__setitem__("sha256", "0" * 64),
            lambda x: x["retained_aggregate"].__setitem__("sha256", "0" * 64),
            lambda x: x["retained_aggregate"].__setitem__("dtype", "little-endian-f32"),
            lambda x: x["retained_aggregate"].__setitem__("shape", [1, 6144]),
            lambda x: x["retained_aggregate"].__setitem__("byte_length", 24576),
            lambda x: x["retained_aggregate"].__setitem__("semantic_surface", "PRODUCTION_SERIAL_F32"),
            lambda x: x["retained_aggregate"].__setitem__("open_once_consume_same_descriptor", False),
            lambda x: x["retained_aggregate"].__setitem__("no_writable_alias", False),
            lambda x: x["surface_isolation"].__setitem__("production_serial_f32_authority", True),
            lambda x: x["surface_isolation"].__setitem__("historical_direct_dprefix_aggregate", True),
            lambda x: x["surface_isolation"].__setitem__("aggregate_recomputation_fallback", True),
            lambda x: x["accounting"].__setitem__("checkpoint_reads", 1),
            lambda x: x["accounting"].__setitem__("shard_opens", 1),
            lambda x: x["accounting"].__setitem__("aggregate_recomputations", 1),
            lambda x: x["accounting"].__setitem__("real_payload_ledger_after", 176),
            lambda x: x["consumer_scope"].__setitem__("shared_expert_execution", True),
            lambda x: x["consumer_scope"].__setitem__("ffn_completion", True),
            lambda x: x["consumer_scope"].__setitem__("s2_construction", True),
            lambda x: x["downstream_semantics"].__setitem__("sha256", "0" * 64),
            lambda x: x["downstream_semantics"].__setitem__("next_phase_checkpoint_free", False),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.rejects(mutation)


class ResolverTests(unittest.TestCase):
    def fixture(self, root: Path) -> dict:
        doc = load(AUTH)
        raw = struct.pack("<6144d", *(float(i) / 8192.0 for i in range(6144)))
        output = root / "routed-aggregate.f64le"
        output.write_bytes(raw)
        os.chmod(output, 0o400)
        output_sha = hashlib.sha256(raw).hexdigest()
        doc["retained_aggregate"]["sha256"] = output_sha
        manifest_doc = {
            "schema": "pulsarmlx.f017.representative-routed-aggregate-private-manifest",
            "artifacts": [{
                "symbolic_path": "routed-aggregate.f64le",
                "sha256": output_sha,
                "semantic_role": "REPRESENTATIVE_M1F0_ROUTED_AGGREGATE_PROOF_REFERENCE",
            }],
        }
        manifest_raw = json.dumps(manifest_doc, sort_keys=True, separators=(",", ":")).encode()
        manifest = root / "routed-aggregate-private-manifest-v1.json"
        manifest.write_bytes(manifest_raw)
        os.chmod(manifest, 0o400)
        doc["private_manifest"]["sha256"] = hashlib.sha256(manifest_raw).hexdigest()
        doc["private_manifest"]["byte_length"] = len(manifest_raw)
        return doc

    def test_exact_open_once_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = preflight_and_consume(self.fixture(root), root)
            self.assertEqual(result["disposition"], "REPRESENTATIVE_ROUTED_AGGREGATE_REUSE_PREFLIGHT_PASS")
            self.assertEqual(result["finite_count"], 6144)
            self.assertEqual(result["expected_sha256"], result["before_sha256"])
            self.assertEqual(result["before_sha256"], result["consumed_sha256"])
            self.assertEqual(result["consumed_sha256"], result["after_sha256"])

    def test_wrong_hash_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.fixture(root)
            doc["retained_aggregate"]["sha256"] = "0" * 64
            with self.assertRaises(ReuseError):
                preflight_and_consume(doc, root)

    def test_writable_output_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.fixture(root)
            os.chmod(root / "routed-aggregate.f64le", 0o600)
            with self.assertRaises(ReuseError):
                preflight_and_consume(doc, root)

    def test_symlink_output_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.fixture(root)
            output = root / "routed-aggregate.f64le"
            real = root / "real.f64le"
            output.rename(real)
            output.symlink_to(real.name)
            with self.assertRaises((ReuseError, OSError)):
                preflight_and_consume(doc, root)

    def test_historical_or_alternate_output_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.fixture(root)
            output = root / "routed-aggregate.f64le"
            os.chmod(output, 0o600)
            output.write_bytes(b"\0" * 49152)
            os.chmod(output, 0o400)
            with self.assertRaises(ReuseError):
                preflight_and_consume(doc, root)


if __name__ == "__main__":
    unittest.main()

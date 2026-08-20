from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts/research"
sys.path.insert(0, str(SCRIPTS))

import f017_representative_s2_executor_v1 as executor_v1
import f017_representative_s2_executor_v2 as executor
import f017_representative_s2_release_wrapper_v2 as wrapper
import f017_representative_s2_terminalizer_v2 as terminalizer
import validate_f017_representative_s2_release_v2 as validator


RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v2.json"
V1_APPROVAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-s2-single-use-release-v1-independent-approval-v1.json"


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class OperandFixture:
    def __init__(self, root: Path, kind: str) -> None:
        self.root = root
        self.kind = kind
        if kind == "s1":
            self.name = "representative-s1.f32le"
            self.manifest_name = "representative-s1-private-manifest-v1.json"
            self.raw = b"\0" * 24576
            self.artifact = {
                "relative_path": self.name,
                "sha256": hashlib.sha256(self.raw).hexdigest(),
                "semantic_role": "REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL",
                "producer_semantic_role": "LAYER3_POST_ATTENTION_RESIDUAL",
                "dtype": "little-endian-f32",
                "shape": [6144],
                "byte_length": 24576,
            }
            self.doc = {
                "schema": "pulsarmlx.f017.representative-s1-private-manifest",
                "schema_version": "1.0.0",
                "artifact": {
                    "byte_length": 24576,
                    "dtype": "little-endian-f32",
                    "finite": True,
                    "path": self.name,
                    "semantic_role": "LAYER3_POST_ATTENTION_RESIDUAL",
                    "sha256": self.artifact["sha256"],
                    "shape": [6144],
                },
                "expected_equals_produced_equals_readback": True,
                "matching_complete_terminal_required": True,
            }
            manifest_kind = "S1_SINGULAR_PRODUCER_V1"
        else:
            self.name = "representative-ffn-output.f64le"
            self.manifest_name = "representative-ffn-output-private-manifest-v1.json"
            self.raw = b"\0" * 49152
            self.artifact = {
                "relative_path": self.name,
                "sha256": hashlib.sha256(self.raw).hexdigest(),
                "semantic_role": "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT",
                "semantic_surface": "CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32",
                "dtype": "little-endian-f64",
                "shape": [6144],
                "byte_length": 49152,
            }
            self.doc = {
                "schema": "pulsarmlx.f017.representative-ffn-output-private-manifest",
                "schema_version": "1.0.0",
                "semantic_surface": self.artifact["semantic_surface"],
                "artifacts": [{
                    "byte_length": 49152,
                    "dtype": "little-endian-f64",
                    "finite": True,
                    "semantic_role": self.artifact["semantic_role"],
                    "sha256": self.artifact["sha256"],
                    "shape": [6144],
                    "symbolic_path": self.name,
                }],
                "authority_requires_matching_complete_terminal": True,
                "execution_receipt_relative_path": "../attempt-state/ffn-execution-receipt.json",
            }
            manifest_kind = "FFN_PLURAL_PRODUCER_V1"
        self.spec = {
            "manifest_kind": manifest_kind,
            "manifest": {"relative_path": self.manifest_name, "sha256": "", "byte_length": 0},
            "artifact": self.artifact,
        }
        (root / self.name).write_bytes(self.raw)
        os.chmod(root / self.name, 0o400)
        self.write_manifest(self.doc)

    def write_manifest(self, doc: dict) -> None:
        raw = canonical(doc)
        path = self.root / self.manifest_name
        if path.exists():
            os.chmod(path, 0o600)
        path.write_bytes(raw)
        os.chmod(path, 0o400)
        self.spec["manifest"].update(sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))

    def write_manifest_raw(self, raw: bytes) -> None:
        path = self.root / self.manifest_name
        if path.exists():
            os.chmod(path, 0o600)
        path.write_bytes(raw)
        os.chmod(path, 0o400)
        self.spec["manifest"].update(sha256=hashlib.sha256(raw).hexdigest(), byte_length=len(raw))


class ManifestCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def assert_manifest_rejected(self, mutate, error: str = "S1_MANIFEST_BINDING") -> None:
        fixture = OperandFixture(self.root, "s1")
        doc = copy.deepcopy(fixture.doc)
        mutate(doc)
        fixture.write_manifest(doc)
        with self.assertRaisesRegex(executor.S2Error, error):
            executor.OpenOperand(self.root, fixture.spec)

    def test_exact_singular_s1_and_plural_ffn_pass(self) -> None:
        s1_root = self.root / "s1"; ffn_root = self.root / "ffn"
        s1_root.mkdir(); ffn_root.mkdir(); os.chmod(s1_root, 0o700); os.chmod(ffn_root, 0o700)
        s1 = OperandFixture(s1_root, "s1"); ffn = OperandFixture(ffn_root, "ffn")
        opened_s1 = executor.OpenOperand(s1_root, s1.spec)
        opened_ffn = executor.OpenOperand(ffn_root, ffn.spec)
        try:
            self.assertEqual(opened_s1.consumer_semantic_role, "REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL")
            self.assertEqual(len(set(opened_s1.verify_after().values())), 1)
            self.assertEqual(len(set(opened_ffn.verify_after().values())), 1)
        finally:
            opened_ffn.close(); opened_s1.close()

    def test_pluralized_missing_and_ambiguous_s1_rejected(self) -> None:
        self.assert_manifest_rejected(lambda d: d.update(artifacts=[d.pop("artifact")]))
        self.root.joinpath("representative-s1-private-manifest-v1.json").unlink(missing_ok=True)
        self.root.joinpath("representative-s1.f32le").unlink(missing_ok=True)
        self.assert_manifest_rejected(lambda d: d.pop("artifact"))
        self.root.joinpath("representative-s1-private-manifest-v1.json").unlink(missing_ok=True)
        self.root.joinpath("representative-s1.f32le").unlink(missing_ok=True)
        self.assert_manifest_rejected(lambda d: d.update(artifacts=[copy.deepcopy(d["artifact"])]))

    def test_wrong_producer_role_and_consumer_alias_rejected(self) -> None:
        self.assert_manifest_rejected(lambda d: d["artifact"].update(semantic_role="WRONG"))
        self.root.joinpath("representative-s1-private-manifest-v1.json").unlink(missing_ok=True)
        self.root.joinpath("representative-s1.f32le").unlink(missing_ok=True)
        self.assert_manifest_rejected(lambda d: d["artifact"].update(semantic_role="REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL"))

    def test_s1_path_dtype_shape_length_and_sha_mutations_rejected(self) -> None:
        mutations = [
            lambda d: d["artifact"].update(path="alias.f32le"),
            lambda d: d["artifact"].update(dtype="little-endian-f64"),
            lambda d: d["artifact"].update(shape=[1]),
            lambda d: d["artifact"].update(byte_length=1),
            lambda d: d["artifact"].update(sha256="0" * 64),
        ]
        for index, mutation in enumerate(mutations):
            if index:
                self.root.joinpath("representative-s1-private-manifest-v1.json").unlink(missing_ok=True)
                self.root.joinpath("representative-s1.f32le").unlink(missing_ok=True)
            self.assert_manifest_rejected(mutation)

    def test_wrong_manifest_sha_malformed_and_duplicate_keys_rejected(self) -> None:
        fixture = OperandFixture(self.root, "s1")
        fixture.spec["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(executor.S2Error, "MANIFEST_SHA"):
            executor.OpenOperand(self.root, fixture.spec)
        fixture.write_manifest_raw(b"{")
        with self.assertRaisesRegex(executor.S2Error, "MANIFEST_JSON"):
            executor.OpenOperand(self.root, fixture.spec)
        fixture.write_manifest_raw(b'{"schema":"a","schema":"b"}\n')
        with self.assertRaisesRegex(executor.S2Error, "DUPLICATE_KEY:schema"):
            executor.OpenOperand(self.root, fixture.spec)

    def test_s1_and_ffn_schemas_cannot_swap(self) -> None:
        fixture = OperandFixture(self.root, "s1")
        fixture.spec["manifest_kind"] = "FFN_PLURAL_PRODUCER_V1"
        with self.assertRaisesRegex(executor.S2Error, "FFN_SPEC_CENSUS"):
            executor.OpenOperand(self.root, fixture.spec)

    def test_writable_symlink_multilink_and_descriptor_change_rejected(self) -> None:
        fixture = OperandFixture(self.root, "s1"); artifact = self.root / fixture.name
        os.chmod(artifact, 0o600)
        with self.assertRaisesRegex(executor.S2Error, "READ_ONLY_REQUIRED"):
            executor.OpenOperand(self.root, fixture.spec)
        os.chmod(artifact, 0o400); alias = self.root / "alias"; os.link(artifact, alias)
        with self.assertRaisesRegex(executor.S2Error, "SINGLE_LINK_REQUIRED"):
            executor.OpenOperand(self.root, fixture.spec)
        alias.unlink(); opened = executor.OpenOperand(self.root, fixture.spec)
        try:
            os.chmod(artifact, 0o600); artifact.write_bytes(b"\1" * 24576); os.chmod(artifact, 0o400)
            with self.assertRaisesRegex(executor.S2Error, "EXPECTED_BEFORE_CONSUMED_AFTER"):
                opened.verify_after()
        finally:
            opened.close()
        artifact.unlink(); os.symlink("missing", artifact)
        with self.assertRaises(OSError):
            executor.OpenOperand(self.root, fixture.spec)


class PreservedMechanicsTests(unittest.TestCase):
    def test_arithmetic_is_exact_accepted_v1_implementation(self) -> None:
        s1 = bytearray(24576); ffn = bytearray(49152)
        struct.pack_into("<f", s1, 0, 1.0); struct.pack_into("<d", ffn, 0, 2.0 ** -24)
        self.assertEqual(executor.compose_bytes(bytes(s1), bytes(ffn)), executor_v1.compose_bytes(bytes(s1), bytes(ffn)))
        self.assertIs(executor.compose_bytes, executor_v1.compose_bytes)

    def test_v1_approval_and_release_rejected_as_v2(self) -> None:
        with self.assertRaisesRegex(wrapper.ReleaseError, "RELEASE_PATH"):
            wrapper.validate_release(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v1.json")
        self.assertEqual(json.loads(V1_APPROVAL.read_text())["release_id"], "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-RELEASE-1")
        self.assertEqual(wrapper.RELEASE_ID, "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-RELEASE-2")

    def test_no_fallback_or_s2_arithmetic_in_preflight_source(self) -> None:
        source = Path(wrapper.__file__).read_text()
        self.assertNotIn("checkpoint", Path(executor.__file__).read_text().lower())
        self.assertNotIn("s1-materialization", source)
        self.assertNotIn("ffn-composition-release-2/go-token", source)

    def test_concurrent_attempt_race_still_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "attempt-state"; outcomes = []; barrier = threading.Barrier(2)
            def contender() -> None:
                barrier.wait()
                try: os.mkdir(target, 0o700); outcomes.append("WIN")
                except FileExistsError: outcomes.append("LOSE")
            threads = [threading.Thread(target=contender) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertCountEqual(outcomes, ["WIN", "LOSE"])

    def test_terminalizer_uses_release_v2_identity(self) -> None:
        self.assertEqual(terminalizer.RELEASE_ID, "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-RELEASE-2")

    def test_release_mutations_rejected(self) -> None:
        base = json.loads(RELEASE.read_text())
        for path, value in [
            (("operand_manifest_contracts", "s1", "collection"), "ONE_ELEMENT_ARTIFACTS_ARRAY_ONLY"),
            (("operand_manifest_contracts", "s1", "producer_semantic_role"), "REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL"),
            (("operand_manifest_contracts", "ffn", "collection"), "SINGULAR_ARTIFACT_OBJECT_ONLY"),
            (("v1_disposition", "v1_go_token_prohibited"), False),
            (("numerical_surface", "addition"), "f32"),
            (("single_use", "retry"), True),
            (("accounting", "future_s2_constructions"), 2),
            (("prohibitions", "checkpoint_access"), False),
        ]:
            doc = copy.deepcopy(base); cursor = doc
            for key in path[:-1]: cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(validator.ValidationError):
                validator.validate_release(doc, repo=False)


if __name__ == "__main__":
    unittest.main()

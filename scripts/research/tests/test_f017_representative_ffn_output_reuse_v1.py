from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from f017_representative_ffn_output_reuse_v1 import (  # noqa: E402
    AUTH,
    ROLE,
    SURFACE,
    ReuseError,
    load,
    open_leaf,
    validate_authorization,
    validate_manifest,
    validate_output_bytes,
)
from validate_f017_representative_ffn_output_reuse_v1 import (  # noqa: E402
    EVIDENCE,
    ValidationError,
    validate,
    validate_execution_evidence,
)


class AuthorizationMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = load(AUTH)
        self.evidence = load(EVIDENCE)

    def rejects_authorization(self, mutation) -> None:
        document = copy.deepcopy(self.authorization)
        mutation(document)
        with self.assertRaises(ReuseError):
            validate_authorization(document)

    def rejects_evidence(self, mutation) -> None:
        document = copy.deepcopy(self.evidence)
        mutation(document)
        with self.assertRaises(ValidationError):
            validate_execution_evidence(document)

    def test_committed_package(self) -> None:
        validate(self.authorization, repo=True)

    def test_authorization_mutations_rejected(self) -> None:
        mutations = [
            lambda x: x["source_authority"]["execution_evidence"].__setitem__("sha256", "0" * 64),
            lambda x: x["source_authority"]["single_use_release_v2"].__setitem__("sha256", "37752ccedadf5db5eb655d4ba4383a37a431197ec41e07d15f6aa7905dfc6b8a"),
            lambda x: x["source_authority"]["independent_release_approval"].__setitem__("sha256", "0" * 64),
            lambda x: x["source_authority"]["arithmetic_contract"].__setitem__("sha256", "0" * 64),
            lambda x: x["source_authority"].__setitem__("execution_code_head", "0" * 40),
            lambda x: x["completed_attempt"].__setitem__("attempt_id", "WRONG"),
            lambda x: x["completed_attempt"]["receipt"].__setitem__("sha256", "0" * 64),
            lambda x: x["completed_attempt"]["terminal"].__setitem__("disposition", "TERMINAL_FAILURE"),
            lambda x: x["completed_attempt"]["terminal"].__setitem__("output_authority", False),
            lambda x: x["completed_attempt"].__setitem__("token_consumed", False),
            lambda x: x["private_manifest"].__setitem__("sha256", "0" * 64),
            lambda x: x["retained_ffn_output"].__setitem__("sha256", "0" * 64),
            lambda x: x["retained_ffn_output"].__setitem__("dtype", "little-endian-f32"),
            lambda x: x["retained_ffn_output"].__setitem__("shape", [1, 6144]),
            lambda x: x["retained_ffn_output"].__setitem__("byte_length", 24576),
            lambda x: x["retained_ffn_output"].__setitem__("semantic_surface", "PRODUCTION_SERIAL_F32"),
            lambda x: x["retained_ffn_output"].__setitem__("open_once_consume_same_descriptor", False),
            lambda x: x["retained_ffn_output"].__setitem__("no_writable_alias", False),
            lambda x: x["reproduction_adjudication"].__setitem__("post_event_reproduction_performed", True),
            lambda x: x["reproduction_adjudication"].__setitem__("required_for_reuse_acceptance", True),
            lambda x: x["surface_isolation"].__setitem__("production_serial_f32_authority", True),
            lambda x: x["surface_isolation"].__setitem__("ffn_recomputation_fallback", True),
            lambda x: x["accounting"].__setitem__("checkpoint_reads", 1),
            lambda x: x["accounting"].__setitem__("shard_opens", 1),
            lambda x: x["accounting"].__setitem__("release_v2_reruns", 1),
            lambda x: x["accounting"].__setitem__("new_ffn_compositions", 1),
            lambda x: x["accounting"].__setitem__("s1_materializations", 1),
            lambda x: x["accounting"].__setitem__("s2_constructions", 1),
            lambda x: x["consumer_scope"].__setitem__("s1_materialization", True),
            lambda x: x["consumer_scope"].__setitem__("s2_construction", True),
            lambda x: x["resolver"].__setitem__("ffn_compute_capability", True),
            lambda x: x.__setitem__("unexpected", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.rejects_authorization(mutation)

    def test_execution_evidence_mutations_rejected(self) -> None:
        mutations = [
            lambda x: x.__setitem__("result", "FAILURE"),
            lambda x: x["authority"].__setitem__("release_sha256", "0" * 64),
            lambda x: x["authority"].__setitem__("independent_approval_sha256", "0" * 64),
            lambda x: x["authority"].__setitem__("arithmetic_contract_sha256", "0" * 64),
            lambda x: x["authority"].__setitem__("execution_code_head", "0" * 40),
            lambda x: x["attempt"].__setitem__("attempt_id", "WRONG"),
            lambda x: x["attempt"].__setitem__("token_consumed", False),
            lambda x: x["accounting"].__setitem__("ffn_compositions", 2),
            lambda x: x["retained_inputs"]["routed"].__setitem__("consumed_sha256", "0" * 64),
            lambda x: x["retained_inputs"]["shared"].__setitem__("after_sha256", "0" * 64),
            lambda x: x["output"].__setitem__("sha256", "0" * 64),
            lambda x: x["output"].__setitem__("finite", False),
            lambda x: x["private_manifest"].__setitem__("sha256", "0" * 64),
            lambda x: x["receipt"].__setitem__("sha256", "0" * 64),
            lambda x: x["terminal"].__setitem__("disposition", "TERMINAL_FAILURE"),
            lambda x: x["terminal"].__setitem__("output_authority", False),
            lambda x: x["reproduction"].__setitem__("post_event_reproduction_performed", True),
            lambda x: x["downstream_prohibitions"].__setitem__("s1_materialized", True),
            lambda x: x["downstream_prohibitions"].__setitem__("s2_constructed", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.rejects_evidence(mutation)


class RetainedFileMechanicsTests(unittest.TestCase):
    def artifact(self, raw: bytes) -> dict:
        return {
            "relative_path": "representative-ffn-output.f64le",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "semantic_role": ROLE,
            "semantic_surface": SURFACE,
            "dtype": "little-endian-f64",
            "shape": [6144],
            "byte_length": 49152,
        }

    def fixture(self, root: Path, values: tuple[float, ...] | None = None) -> tuple[dict, bytes]:
        actual = values if values is not None else tuple(float(index) / 8192.0 for index in range(6144))
        raw = struct.pack("<6144d", *actual)
        artifact = self.artifact(raw)
        output = root / artifact["relative_path"]
        output.write_bytes(raw)
        os.chmod(output, 0o400)
        return artifact, raw

    def test_exact_read_only_single_link_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact, raw = self.fixture(root)
            root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            descriptor = -1
            try:
                descriptor, _, observed = open_leaf(root_fd, artifact["relative_path"], 49152)
                self.assertEqual(observed, raw)
                self.assertEqual(len(validate_output_bytes(observed, artifact)), 6144)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                os.close(root_fd)

    def test_nonfinite_rejected(self) -> None:
        raw = struct.pack("<6144d", math.nan, *(0.0 for _ in range(6143)))
        with self.assertRaises(ReuseError):
            validate_output_bytes(raw, self.artifact(raw))

    def test_writable_symlink_hardlink_and_wrong_size_rejected(self) -> None:
        for case in ("writable", "symlink", "hardlink", "size"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                artifact, raw = self.fixture(root)
                output = root / artifact["relative_path"]
                if case == "writable":
                    os.chmod(output, 0o600)
                elif case == "symlink":
                    real = root / "real.f64le"
                    output.rename(real)
                    output.symlink_to(real.name)
                elif case == "hardlink":
                    os.link(output, root / "alias.f64le")
                else:
                    os.chmod(output, 0o600)
                    output.write_bytes(raw[:-8])
                    os.chmod(output, 0o400)
                root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    with self.assertRaises((ReuseError, OSError)):
                        descriptor, _, _ = open_leaf(root_fd, artifact["relative_path"], 49152)
                        os.close(descriptor)
                finally:
                    os.close(root_fd)

    def test_manifest_mismatch_rejected(self) -> None:
        raw = struct.pack("<6144d", *(0.0 for _ in range(6144)))
        artifact = self.artifact(raw)
        manifest = {
            "schema": "pulsarmlx.f017.representative-ffn-output-private-manifest",
            "schema_version": "1.0.0",
            "semantic_surface": SURFACE,
            "authority_requires_matching_complete_terminal": True,
            "execution_receipt_relative_path": "../attempt-state/ffn-execution-receipt.json",
            "artifacts": [{
                "byte_length": 49152,
                "dtype": "little-endian-f64",
                "finite": True,
                "semantic_role": ROLE,
                "sha256": "0" * 64,
                "shape": [6144],
                "symbolic_path": artifact["relative_path"],
            }],
        }
        with self.assertRaises(ReuseError):
            validate_manifest(json.dumps(manifest).encode(), artifact)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Focused tests for the bounded public CPU-oracle publication adapter."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_DIR = REPOSITORY_ROOT / "scripts" / "research"
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))

import oracle_publication  # noqa: E402
import verify_package  # noqa: E402
from scripts.research.tests import test_verify_package as oracle_fixture  # noqa: E402


SOURCE_COMMIT = "d" * 40
VERIFICATION = {
    "candidate_sha256": "a" * 64,
    "manifest_sha256": "b" * 64,
    "oracle_document_sha256": "c" * 64,
}
TEST_ORACLE = oracle_fixture._router_oracle_document()
TEST_INPUT_SHA256 = TEST_ORACLE["input"]["canonical_f32le_sha256"]
TEST_OUTPUT_SHA256 = TEST_ORACLE["result"]["hashes"]["output_bundle_sha256"]
TEST_NUMPY = TEST_ORACLE["result"]["numpy_cross_check"]
TEST_CAPTURE_PROVENANCE_SHA256 = hashlib.sha256(
    oracle_publication._canonical_bytes(
        oracle_publication._public_capture_provenance(
            TEST_ORACLE["capture_provenance"]
        )
    )
).hexdigest()


def _model_manifest() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / oracle_publication.MODEL_MANIFEST_RELATIVE).read_text(
            encoding="utf-8"
        )
    )


def _public_record() -> dict:
    return oracle_publication.project_public_record(
        deepcopy(TEST_ORACLE),
        deepcopy(VERIFICATION),
        _model_manifest(),
        repository_root=REPOSITORY_ROOT,
        source_commit=SOURCE_COMMIT,
    )


def _prepare_repository_root(root: Path) -> None:
    """Install only the three source files bound by public-record hashes."""

    for relative in (
        oracle_publication.VERIFIER_RELATIVE,
        oracle_publication.PUBLISHER_RELATIVE,
        Path("scripts/research/router_oracle.py"),
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPOSITORY_ROOT / relative).read_bytes())


def _nested_keys(value: object) -> set[str]:
    keys: set[str] = set()
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            keys.update(current)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return keys


class PinnedTestOracleCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.multiple(
            oracle_publication,
            PINNED_ORACLE_CANDIDATE_SHA256=VERIFICATION["candidate_sha256"],
            PINNED_ORACLE_MANIFEST_SHA256=VERIFICATION["manifest_sha256"],
            PINNED_ORACLE_DOCUMENT_SHA256=VERIFICATION["oracle_document_sha256"],
            PINNED_INPUT_SHA256=TEST_INPUT_SHA256,
            PINNED_OUTPUT_SHA256=TEST_OUTPUT_SHA256,
            PINNED_NUMPY_LOGITS_SHA256=TEST_NUMPY["numpy_logits_f32le_sha256"],
            PINNED_NUMPY_MAXIMUM_ABSOLUTE_ERROR=TEST_NUMPY[
                "maximum_absolute_error"
            ],
            PINNED_NUMPY_MAXIMUM_RELATIVE_ERROR=TEST_NUMPY[
                "maximum_relative_error"
            ],
            PINNED_CAPTURE_PROVENANCE_SHA256=TEST_CAPTURE_PROVENANCE_SHA256,
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class PublicRecordTests(PinnedTestOracleCase):
    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_bounded_reader_rejects_fifo_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fifo = Path(temporary) / "candidate.json"
            os.mkfifo(fifo)
            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication._read_regular(
                    fifo,
                    maximum=1024,
                    subject="test candidate",
                )

    def test_bounded_reader_rejects_short_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary) / "candidate.json"
            candidate.write_bytes(b"{}\n")
            with (
                mock.patch.object(oracle_publication.os, "read", return_value=b""),
                self.assertRaises(oracle_publication.OraclePublicationError),
            ):
                oracle_publication._read_regular(
                    candidate,
                    maximum=1024,
                    subject="test candidate",
                )

    def test_projection_is_closed_reconstructable_and_public_safe(self) -> None:
        record = _public_record()

        summary = oracle_publication.validate_public_record(
            record,
            repository_root=REPOSITORY_ROOT,
        )

        self.assertTrue(oracle_publication.is_public_oracle_record(record))
        self.assertEqual(summary["publication_id"], oracle_publication.PUBLICATION_ID)
        self.assertEqual(len(record["input"]["values"]), 2)
        self.assertTrue(all(len(row) == 2048 for row in record["input"]["values"]))
        self.assertEqual(len(record["result"]["logits"]), 2)
        self.assertTrue(all(len(row) == 128 for row in record["result"]["logits"]))
        self.assertEqual(len(record["result"]["full_softmax_probabilities"]), 2)
        self.assertEqual(len(record["result"]["selected_expert_ids"]), 2)
        self.assertEqual(record["result"]["cutoff_ties"], [False, False])
        self.assertEqual(summary["numpy_mismatch_count"], 0)

        keys = _nested_keys(record)
        self.assertTrue(keys.isdisjoint(oracle_publication.FORBIDDEN_FIELDS))
        serialized = oracle_publication._canonical_bytes(record).decode("utf-8")
        for forbidden in (
            "/Users/",
            "/private/",
            '"device"',
            '"inode"',
            '"runtime_identity"',
            '"consumer_proofs"',
            '"model_bytes"',
            '"tensor_bytes"',
            '"router_weight_bytes"',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertFalse(record["redistribution"]["model_weights_included"])
        self.assertFalse(record["redistribution"]["router_tensor_bytes_included"])
        self.assertFalse(record["redistribution"]["capture_binaries_included"])

    def test_projection_is_deterministic(self) -> None:
        first = _public_record()
        second = _public_record()

        self.assertEqual(
            oracle_publication._canonical_bytes(first),
            oracle_publication._canonical_bytes(second),
        )

    def test_validator_rejects_mutation_privacy_and_unknown_fields(self) -> None:
        mutations: list[tuple[str, dict]] = []

        unknown = _public_record()
        unknown["unexpected"] = True
        mutations.append(("unknown", unknown))

        changed_input = _public_record()
        changed_input["input"]["values"][0][0] = 1.0
        mutations.append(("input_hash", changed_input))

        changed_output = _public_record()
        changed_output["result"]["logits"][0][0] = 1.0
        mutations.append(("output_hash", changed_output))

        private_path = _public_record()
        private_path["generator"]["generation_command"] = str(
            Path("/", "Users", "private", "model.gguf")
        )
        mutations.append(("private_path", private_path))

        runtime_identity = _public_record()
        runtime_identity["model"]["runtime_identity"] = {"device": 1, "inode": 2}
        mutations.append(("runtime_identity", runtime_identity))

        tensor_payload = _public_record()
        tensor_payload["tensor"]["tensor_values"] = [0.0]
        mutations.append(("tensor_values", tensor_payload))

        changed_provenance = _public_record()
        changed_provenance["capture_provenance"]["build"][
            "capture_source_overlay_sha256"
        ] = "0" * 64
        mutations.append(("capture_provenance_hash", changed_provenance))

        changed_build_command = _public_record()
        changed_build_command["capture_provenance"]["build"][
            "configure_command"
        ] += " -DUNREVIEWED=ON"
        mutations.append(("capture_provenance_command", changed_build_command))

        non_finite = _public_record()
        non_finite["input"]["values"][0][0] = float("nan")
        mutations.append(("non_finite", non_finite))

        for name, mutation in mutations:
            with self.subTest(mutation=name), self.assertRaises(
                oracle_publication.OraclePublicationError
            ):
                oracle_publication.validate_public_record(
                    mutation,
                    repository_root=REPOSITORY_ROOT,
                )

    def test_validator_rejects_a_coherently_rehashed_alternate_output(self) -> None:
        forged = _public_record()
        logits = forged["result"]["logits"]
        logits[0][0] = 1.0
        probabilities = [
            oracle_publication.router_oracle.full_softmax_f32(row) for row in logits
        ]
        routes = [
            oracle_publication.router_oracle.select_top_k_f32(row)
            for row in probabilities
        ]
        selected_ids = [route[0] for route in routes]
        selected_probabilities = [route[1] for route in routes]
        normalized_weights = [route[2] for route in routes]
        cutoff_ties = []
        for row in probabilities:
            ranked = sorted(range(128), key=lambda expert: (-row[expert], expert))
            cutoff_ties.append(row[ranked[7]] == row[ranked[8]])

        logits_bytes = oracle_publication._f32_bytes(logits)
        probability_bytes = oracle_publication._f32_bytes(probabilities)
        ids_bytes = oracle_publication._u32_bytes(selected_ids)
        selected_bytes = oracle_publication._f32_bytes(selected_probabilities)
        normalized_bytes = oracle_publication._f32_bytes(normalized_weights)
        forged["result"].update(
            {
                "full_softmax_probabilities": probabilities,
                "selected_expert_ids": selected_ids,
                "selected_probabilities": selected_probabilities,
                "normalized_weights": normalized_weights,
                "cutoff_ties": cutoff_ties,
                "hashes": {
                    "logits_f32le_sha256": hashlib.sha256(logits_bytes).hexdigest(),
                    "full_softmax_probabilities_f32le_sha256": hashlib.sha256(
                        probability_bytes
                    ).hexdigest(),
                    "selected_expert_ids_u32le_sha256": hashlib.sha256(
                        ids_bytes
                    ).hexdigest(),
                    "selected_probabilities_f32le_sha256": hashlib.sha256(
                        selected_bytes
                    ).hexdigest(),
                    "normalized_weights_f32le_sha256": hashlib.sha256(
                        normalized_bytes
                    ).hexdigest(),
                    "output_bundle_sha256": hashlib.sha256(
                        logits_bytes
                        + probability_bytes
                        + ids_bytes
                        + selected_bytes
                        + normalized_bytes
                    ).hexdigest(),
                },
            }
        )

        with self.assertRaises(oracle_publication.OraclePublicationError):
            oracle_publication.validate_public_record(
                forged,
                repository_root=REPOSITORY_ROOT,
            )

    def test_schema_discriminator_does_not_accept_other_records(self) -> None:
        self.assertFalse(oracle_publication.is_public_oracle_record({}))
        self.assertFalse(
            oracle_publication.is_public_oracle_record(
                {"schema": "pulsarmlx.research.experiment"}
            )
        )


class PublicationTransactionTests(PinnedTestOracleCase):
    def _root(self, temporary: str) -> Path:
        root = Path(temporary).resolve() / "repository"
        root.mkdir()
        _prepare_repository_root(root)
        return root

    def test_publication_is_deterministic_idempotent_and_committed_verifiable(
        self,
    ) -> None:
        record = _public_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)

            first = oracle_publication.publish_public_record(record, repository_root=root)
            fixture = root / oracle_publication.FIXTURE_RECORD_RELATIVE
            raw = root / oracle_publication.RAW_RECORD_RELATIVE
            manifest = root / oracle_publication.MANIFEST_RELATIVE
            snapshot = {
                "fixture": fixture.read_bytes(),
                "raw": raw.read_bytes(),
                "manifest": manifest.read_bytes(),
            }
            second = oracle_publication.publish_public_record(record, repository_root=root)
            committed = oracle_publication.verify_committed_publication(root)

            self.assertEqual(snapshot["fixture"], snapshot["raw"])
            self.assertEqual(fixture.read_bytes(), snapshot["fixture"])
            self.assertEqual(raw.read_bytes(), snapshot["raw"])
            self.assertEqual(manifest.read_bytes(), snapshot["manifest"])
            self.assertEqual(first, second)
            self.assertEqual(second, committed)
            self.assertTrue(committed["passed"])
            self.assertEqual(committed["copy_count"], 2)
            self.assertEqual(
                set(path.name for path in fixture.parent.iterdir()),
                {fixture.name, manifest.name},
            )
            self.assertEqual(
                set(path.name for path in raw.parent.iterdir()),
                {raw.name},
            )

    def test_partial_matching_publication_rolls_forward(self) -> None:
        record = _public_record()
        record_bytes = oracle_publication._canonical_bytes(record)
        for first_copy in ("fixture", "raw"):
            with self.subTest(first_copy=first_copy), tempfile.TemporaryDirectory() as temporary:
                root = self._root(temporary)
                fixture = root / oracle_publication.FIXTURE_RECORD_RELATIVE
                raw = root / oracle_publication.RAW_RECORD_RELATIVE
                existing = fixture if first_copy == "fixture" else raw
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_bytes(record_bytes)

                summary = oracle_publication.publish_public_record(
                    record,
                    repository_root=root,
                )

                self.assertTrue(summary["passed"])
                self.assertEqual(fixture.read_bytes(), record_bytes)
                self.assertEqual(raw.read_bytes(), record_bytes)
                self.assertTrue((root / oracle_publication.MANIFEST_RELATIVE).is_file())

    def test_conflicting_destination_is_refused_without_completing_transaction(self) -> None:
        record = _public_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            fixture = root / oracle_publication.FIXTURE_RECORD_RELATIVE
            raw = root / oracle_publication.RAW_RECORD_RELATIVE
            manifest = root / oracle_publication.MANIFEST_RELATIVE
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text("{}\n", encoding="utf-8")

            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication.publish_public_record(record, repository_root=root)

            self.assertEqual(fixture.read_text(encoding="utf-8"), "{}\n")
            self.assertFalse(raw.exists())
            self.assertFalse(manifest.exists())

    def test_post_link_failure_rolls_back_every_new_destination(self) -> None:
        record = _public_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            raw_parent = (root / oracle_publication.RAW_RECORD_RELATIVE).parent
            real_sync = oracle_publication._sync_directory

            def fail_raw_sync(path: Path) -> None:
                if path == raw_parent:
                    raise OSError("injected bounded sync failure")
                real_sync(path)

            with (
                mock.patch.object(
                    oracle_publication,
                    "_sync_directory",
                    side_effect=fail_raw_sync,
                ),
                self.assertRaises(oracle_publication.OraclePublicationError),
            ):
                oracle_publication.publish_public_record(record, repository_root=root)

            self.assertFalse(
                (root / oracle_publication.FIXTURE_RECORD_RELATIVE).exists()
            )
            self.assertFalse((root / oracle_publication.RAW_RECORD_RELATIVE).exists())
            self.assertFalse((root / oracle_publication.MANIFEST_RELATIVE).exists())

    def test_temporary_cleanup_failure_rolls_back_and_retries_cleanup(self) -> None:
        record = _public_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            real_unlink = Path.unlink
            injected = False

            def fail_first_temporary_unlink(
                path: Path,
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal injected
                if not injected and path.name.startswith(".f002-router-oracle-freeze"):
                    injected = True
                    raise OSError("injected bounded unlink failure")
                real_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(Path, "unlink", new=fail_first_temporary_unlink),
                self.assertRaises(oracle_publication.OraclePublicationError),
            ):
                oracle_publication.publish_public_record(record, repository_root=root)

            self.assertTrue(injected)
            self.assertFalse(
                (root / oracle_publication.FIXTURE_RECORD_RELATIVE).exists()
            )
            self.assertFalse((root / oracle_publication.RAW_RECORD_RELATIVE).exists())
            self.assertFalse((root / oracle_publication.MANIFEST_RELATIVE).exists())
            self.assertEqual(list(root.rglob(".*.json.*")), [])

    def test_symlink_destination_is_refused(self) -> None:
        record = _public_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            fixture = root / oracle_publication.FIXTURE_RECORD_RELATIVE
            raw = root / oracle_publication.RAW_RECORD_RELATIVE
            manifest = root / oracle_publication.MANIFEST_RELATIVE
            fixture.parent.mkdir(parents=True, exist_ok=True)
            target = root / "outside.json"
            target.write_text("{}\n", encoding="utf-8")
            fixture.symlink_to(target)

            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication.publish_public_record(record, repository_root=root)

            self.assertEqual(target.read_text(encoding="utf-8"), "{}\n")
            self.assertFalse(raw.exists())
            self.assertFalse(manifest.exists())

    def test_package_inventory_admits_only_the_exact_oracle_support_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _prepare_repository_root(root)
            oracle_publication.publish_public_record(
                _public_record(),
                repository_root=root,
            )
            raw_root = root / "docs/research/raw/002-router-parity"
            with mock.patch.object(verify_package, "REPOSITORY_ROOT", root):
                experiments, support = verify_package._publication_raw_inventory(
                    raw_root
                )
                self.assertEqual(experiments, [])
                self.assertEqual(
                    support,
                    [
                        root / oracle_publication.FIXTURE_RECORD_RELATIVE,
                        root / oracle_publication.RAW_RECORD_RELATIVE,
                        root / oracle_publication.MANIFEST_RELATIVE,
                    ],
                )

                unsupported = raw_root / "unreviewed-support"
                unsupported.mkdir()
                with self.assertRaises(verify_package.VerificationError):
                    verify_package._publication_raw_inventory(raw_root)

    def test_committed_verifier_rejects_manifest_or_inventory_mutation(self) -> None:
        record = _public_record()
        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            oracle_publication.publish_public_record(record, repository_root=root)
            manifest = root / oracle_publication.MANIFEST_RELATIVE
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["byte_identical_copies"] = False
            manifest.write_text(
                json.dumps(document, allow_nan=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication.verify_committed_publication(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            oracle_publication.publish_public_record(record, repository_root=root)
            manifest = root / oracle_publication.MANIFEST_RELATIVE
            document = json.loads(manifest.read_text(encoding="utf-8"))
            manifest.write_text(
                json.dumps(document, allow_nan=False, sort_keys=True),
                encoding="utf-8",
            )

            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication.verify_committed_publication(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            oracle_publication.publish_public_record(record, repository_root=root)
            fixture = root / oracle_publication.FIXTURE_RECORD_RELATIVE
            raw = root / oracle_publication.RAW_RECORD_RELATIVE
            manifest = root / oracle_publication.MANIFEST_RELATIVE
            compact_record = json.dumps(
                record,
                allow_nan=False,
                sort_keys=True,
            ).encode("utf-8")
            fixture.write_bytes(compact_record)
            raw.write_bytes(compact_record)
            manifest.write_bytes(
                oracle_publication._canonical_bytes(
                    oracle_publication._manifest(compact_record)
                )
            )

            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication.verify_committed_publication(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self._root(temporary)
            oracle_publication.publish_public_record(record, repository_root=root)
            raw = root / oracle_publication.RAW_RECORD_RELATIVE
            (raw.parent / "unexpected.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(oracle_publication.OraclePublicationError):
                oracle_publication.verify_committed_publication(root)


class CliTests(PinnedTestOracleCase):
    def test_cli_requires_exactly_one_mode(self) -> None:
        for arguments in (
            [],
            ["--check", "--oracle-candidate", "/private/tmp/private-candidate"],
        ):
            with self.subTest(arguments=arguments):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = oracle_publication.main(arguments)
                self.assertEqual(result, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn("/private/tmp/private-candidate", stderr.getvalue())

    def test_check_cli_returns_only_bounded_summary(self) -> None:
        summary = {
            "passed": True,
            "publication_id": oracle_publication.PUBLICATION_ID,
            "record_sha256": "a" * 64,
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            oracle_publication,
            "verify_committed_publication",
            return_value=summary,
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            result = oracle_publication.main(["--check"])

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue()), summary)
        self.assertEqual(stderr.getvalue(), "")

    def test_publish_cli_does_not_disclose_external_candidate_path(self) -> None:
        private_candidate = "/private/tmp/operator-secret/oracle"
        oracle_bytes = b"{}\n"
        verification = {
            **VERIFICATION,
            "oracle_document_sha256": hashlib.sha256(oracle_bytes).hexdigest(),
        }
        bounded_summary = {
            "passed": True,
            "publication_id": oracle_publication.PUBLICATION_ID,
            "record_sha256": "e" * 64,
        }
        fake_verifier = SimpleNamespace(
            verify_oracle_candidate_bundle=mock.Mock(return_value=verification)
        )
        read_results = [
            (oracle_fixture._router_oracle_document(), oracle_bytes),
            (_model_manifest(), b"{}\n"),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            oracle_publication, "_clean_commit", return_value=SOURCE_COMMIT
        ), mock.patch.object(
            oracle_publication, "_read_json", side_effect=read_results
        ), mock.patch.object(
            oracle_publication, "project_public_record", return_value=_public_record()
        ), mock.patch.object(
            oracle_publication, "publish_public_record", return_value=bounded_summary
        ), mock.patch.dict(
            sys.modules, {"verify_package": fake_verifier}
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            result = oracle_publication.main(
                ["--oracle-candidate", private_candidate]
            )

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue()), bounded_summary)
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(private_candidate, stdout.getvalue())
        self.assertNotIn(private_candidate, stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

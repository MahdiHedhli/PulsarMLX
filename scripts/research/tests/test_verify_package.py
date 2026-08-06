from __future__ import annotations

from copy import deepcopy
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


RESEARCH_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FULL_FIXTURE = (
    REPOSITORY_ROOT
    / "fixtures"
    / "research"
    / "router-v1"
    / "evidence"
    / "f002-router-fixture-0001.json"
)
VERIFY_COMMAND = RESEARCH_DIR / "verify_package.py"
if str(RESEARCH_DIR) not in sys.path:
    # Preserve standard-library import precedence during full test discovery.
    sys.path.append(str(RESEARCH_DIR))


def _candidate(experiment_id: str = "fixture-publish-v1") -> dict:
    return {
        "schema_id": "pulsarmlx.research.experiment",
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "feature_id": "002-qwen-router-parity",
        "status": "passed",
        "scope": "synthetic_fixture_only",
        "source": {
            "commit": "a" * 40,
            "clean": True,
        },
        "command": {
            "display": "validate-router-fixtures --manifest fixtures/research/router-v1/manifest.json",
            "exit_code": 0,
        },
        "raw_observations": [
            {
                "observation_id": "fixture-publish-v1-warm-000",
                "case_id": "generated-router-single-row-v1",
                "batch_id": "fixture-batch-v1",
                "observation_kind": "measurement",
                "condition": "warm",
                "instrumentation_mode": "minimally_instrumented",
                "duration_ns": 123_457,
                "status": "passed",
            }
        ],
        "unsupported_interpretations": [
            "real_checkpoint_routing",
            "expert_execution",
            "model_inference",
        ],
        "_local": {
            "candidate_directory": "/private/tmp/router-candidate",
            "model_path": "/private/models/checkpoint.gguf",
        },
    }


def _claim_scope(record: dict) -> str:
    return ";".join(
        (
            f"checkpoint={record['model']['repository']}@{record['model']['revision']}",
            f"tensor={record['tensor']['name']}",
            f"case={record['summaries'][0]['group']['case_id']}",
            f"depth={record['claim_boundary']['operation']}",
        )
    )


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.publisher = importlib.import_module("publish_evidence")
            self.verifier = importlib.import_module("verify_package")
        except ModuleNotFoundError as error:
            self.fail(f"planned publication module is not implemented: {error}")

    def _write_candidate(self, directory: Path, record: dict) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "candidate.json"
        path.write_text(
            json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _materialize_publication_package(self, root: Path) -> dict[str, Path]:
        research_root = root / "docs" / "research"
        raw_dir = research_root / "raw" / "002-router-parity"
        table_dir = research_root / "tables"
        figure_dir = research_root / "figures"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / FULL_FIXTURE.name
        raw_path.write_bytes(FULL_FIXTURE.read_bytes())
        evidence = json.loads(raw_path.read_text(encoding="utf-8"))

        previous_directory = Path.cwd()
        try:
            os.chdir(root)
            self.verifier.generate_tables.generate_tables(
                Path("docs/research/raw/002-router-parity"),
                Path("docs/research/tables"),
            )
            self.verifier.generate_figures.generate_figures(
                Path("docs/research/raw/002-router-parity"),
                Path("docs/research/figures"),
            )
        finally:
            os.chdir(previous_directory)
        table_paths = sorted(path for path in table_dir.iterdir() if path.is_file())
        figure_paths = sorted(path for path in figure_dir.iterdir() if path.is_file())
        generated_paths = table_paths + figure_paths

        claims_path = research_root / "CLAIMS_LEDGER.md"
        claims_path.write_text(
            "\n".join(
                (
                    "# Feature 002 Claims Ledger",
                    "",
                    "| Claim | Evidence files | Commit | Scope | Status | Caveat |",
                    "| --- | --- | --- | --- | --- | --- |",
                    (
                        "| F002-C01 Synthetic router methodology is reproducible | "
                        f"[raw evidence](raw/002-router-parity/{raw_path.name}) | "
                        f"{evidence['source_commit']} | {_claim_scope(evidence)} | "
                        "provisional | Does not establish real-checkpoint routing. |"
                    ),
                    "",
                )
            ),
            encoding="utf-8",
        )

        reproduction_path = research_root / "REPRODUCIBILITY.md"
        reproduction_path.write_text(
            "# Reproduction\n\nRun the checked-in fixture-only package verifier.\n",
            encoding="utf-8",
        )
        reviewer_path = research_root / "REVIEWER_INDEX.md"
        table_links = "\n".join(
            f"- [{path.name}]({path.relative_to(research_root).as_posix()})"
            for path in table_paths
        )
        figure_links = "\n".join(
            f"- [{path.name}]({path.relative_to(research_root).as_posix()})"
            for path in figure_paths
        )
        reviewer_path.write_text(
            "\n".join(
                (
                    "# Feature 002 Reviewer Index",
                    "",
                    "## Raw evidence",
                    f"- [{raw_path.name}](raw/002-router-parity/{raw_path.name})",
                    "",
                    "## Generated tables",
                    table_links,
                    "",
                    "## Generated figures",
                    figure_links,
                    "",
                    "## Claims and reproduction links",
                    "- [claims](CLAIMS_LEDGER.md)",
                    "- [reproduction](REPRODUCIBILITY.md)",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return {
            "research_root": research_root,
            "raw": raw_path,
            "claims": claims_path,
            "reviewer": reviewer_path,
            "reproduction": reproduction_path,
            "generated": generated_paths[0],
            "sidecar": next(
                path for path in generated_paths if path.name.endswith(".sources.json")
            ),
        }

    def _verify_publication_index(
        self,
        root: Path,
        paths: dict[str, Path],
    ) -> dict[str, int]:
        with mock.patch.multiple(
            self.verifier,
            REPOSITORY_ROOT=root,
            CLAIMS_LEDGER=paths["claims"],
            REVIEWER_INDEX=paths["reviewer"],
        ):
            return self.verifier.verify_publication_index()

    def test_candidate_sanitization_drops_only_declared_local_metadata(self) -> None:
        record = _candidate()
        sanitized = self.publisher.sanitize_candidate(record)

        self.assertNotIn("_local", sanitized)
        self.assertEqual(sanitized["experiment_id"], record["experiment_id"])
        self.assertEqual(sanitized["raw_observations"], record["raw_observations"])
        serialized = json.dumps(sanitized, allow_nan=False, sort_keys=True)
        self.assertNotIn("/private/", serialized)
        self.assertNotIn("checkpoint.gguf", serialized)

        leaked = _candidate("fixture-private-leak-v1")
        leaked["command"]["display"] = "/private/tmp/run --token secret-value"
        with self.assertRaises(self.publisher.PublicationError):
            self.publisher.sanitize_candidate(leaked)

        benign = _candidate("fixture-benign-token-prose-v1")
        benign["warnings"] = ["Direct token IDs are fixed by protocol."]
        self.assertEqual(
            self.publisher.sanitize_candidate(benign)["warnings"],
            benign["warnings"],
        )
        benign["command"]["display"] = "tool --token-ids 0,1"
        self.assertEqual(
            self.publisher.sanitize_candidate(benign)["command"]["display"],
            benign["command"]["display"],
        )

        credential_name = "pass" + "word"
        command_fragments = (
            f"tool --{credential_name} abc",
            f"tool --{credential_name}=abc",
            f"tool --{credential_name} 'abc'",
            f'tool --{credential_name} "abc"',
            f"tool {credential_name}='abc'",
            'tool ' + "token" + '="abc"',
        )
        for index, display in enumerate(command_fragments):
            with self.subTest(index=index):
                leaked = _candidate(f"fixture-explicit-credential-{index}")
                leaked["command"]["display"] = display
                with self.assertRaises(self.publisher.PublicationError):
                    self.publisher.sanitize_candidate(leaked)

        full_record = json.loads(FULL_FIXTURE.read_text(encoding="utf-8"))
        compound_commands = (
            "HF_" + "TOKEN=abc python3 tool.py",
            "python3 tool.py --auth abc",
            "python3 tool.py --access_" + "token abc",
            "python3 tool.py --client" + "Secret='abc'",
        )
        for index, display in enumerate(compound_commands):
            with self.subTest(compound_index=index):
                leaked = deepcopy(full_record)
                leaked["execution"]["command"] = display
                leaked["execution"]["argv"] = ["zsh", "-lc", display]
                with self.assertRaises(self.publisher.PublicationError):
                    self.publisher.sanitize_candidate(leaked)

        split_options = (
            "--" + credential_name,
            "--auth",
            "--access_" + "token",
        )
        for index, option in enumerate(split_options):
            with self.subTest(split_argv_index=index):
                leaked = deepcopy(full_record)
                leaked["execution"]["argv"] = ["python3", "tool.py", option, "abc"]
                with self.assertRaises(self.publisher.PublicationError):
                    self.publisher.sanitize_candidate(leaked)

    def test_publish_is_append_only_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root / "candidate", _candidate())
            raw_dir = root / "raw"

            installed = self.publisher.publish_candidate(candidate_path, raw_dir)
            original = installed.read_bytes()
            self.assertEqual(installed.name, "fixture-publish-v1.json")
            self.assertNotIn("_local", json.loads(original))

            changed = _candidate()
            changed["status"] = "failed"
            changed_path = self._write_candidate(root / "changed", changed)
            with self.assertRaises(FileExistsError):
                self.publisher.publish_candidate(changed_path, raw_dir)
            self.assertEqual(installed.read_bytes(), original)

    def test_publish_rejects_duplicate_identity_under_an_existing_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw_dir = root / "raw"
            raw_dir.mkdir()
            existing = raw_dir / "historical-attempt.json"
            existing.write_text(
                json.dumps(
                    self.publisher.sanitize_candidate(_candidate()),
                    allow_nan=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
            candidate_path = self._write_candidate(root / "candidate", _candidate())

            with self.assertRaises((self.publisher.PublicationError, FileExistsError)):
                self.publisher.publish_candidate(candidate_path, raw_dir)

            self.assertEqual(
                {path.name: path.read_bytes() for path in raw_dir.iterdir()},
                before,
                msg="duplicate identity admission changed append-only history",
            )

    def test_publish_rejects_invalid_existing_history_without_changes(self) -> None:
        private_key = "hardware." + "serial"
        private_history = _candidate("private-history-v1")
        private_history.pop("_local")
        private_history["environment"] = {
            private_key: "fixture-private-marker"
        }
        cases = (
            {"experiment_id": "malformed-history-v1"},
            private_history,
        )
        for existing_record in cases:
            with self.subTest(experiment_id=existing_record["experiment_id"]):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    raw_dir = root / "raw"
                    raw_dir.mkdir()
                    existing = raw_dir / f"{existing_record['experiment_id']}.json"
                    existing.write_text(
                        json.dumps(existing_record, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
                    candidate_path = self._write_candidate(
                        root / "candidate",
                        _candidate("new-candidate-v1"),
                    )

                    with self.assertRaises(self.publisher.PublicationError):
                        self.publisher.publish_candidate(candidate_path, raw_dir)

                    self.assertEqual(
                        {path.name: path.read_bytes() for path in raw_dir.iterdir()},
                        before,
                    )

    def test_private_identifier_and_secret_shaped_keys_are_rejected(self) -> None:
        mutations = (
            ("metadata", "host", "fixture-machine-marker"),
            ("metadata", "host" + "name", "fixture-machine.local"),
            ("metadata", "hardware." + "serial", "fixture-hardware-marker"),
            ("metadata", "access_" + "token", "fixture-sensitive-marker"),
            ("metadata", "access" + "Token", "fixture-sensitive-marker"),
            ("metadata", "ntfy_" + "token", "fixture-sensitive-marker"),
            ("metadata", "client_" + "secret", "fixture-sensitive-marker"),
            ("metadata", "client" + "Secret", "fixture-sensitive-marker"),
            (
                "environment",
                "RUNNER_" + "TOKEN" + "_ALIAS",
                "fixture-sensitive-marker",
            ),
        )
        for container, key, value in mutations:
            with self.subTest(key=key):
                leaked = _candidate(f"fixture-private-{len(key)}")
                leaked[container] = {key: value}
                with self.assertRaises(self.publisher.PublicationError) as raised:
                    self.publisher.sanitize_candidate(leaked)
                self.assertRegex(str(raised.exception).lower(), r"private|secret")
                self.assertNotIn(value, str(raised.exception))

    def test_failed_validation_leaves_no_partial_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            malformed = _candidate("")
            malformed_path = self._write_candidate(root / "candidate", malformed)
            raw_dir = root / "raw"

            with self.assertRaises(self.publisher.PublicationError):
                self.publisher.publish_candidate(malformed_path, raw_dir)

            self.assertFalse(raw_dir.exists() and any(raw_dir.iterdir()))
            self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_malformed_numeric_and_depth_errors_are_bounded(self) -> None:
        for status in ([], {}):
            with self.subTest(status_type=type(status).__name__):
                malformed = _candidate(f"fixture-invalid-status-{type(status).__name__}")
                malformed["status"] = status
                with self.assertRaises(self.publisher.PublicationError):
                    self.publisher.sanitize_candidate(malformed)

        malformed_payloads = (
            '{"experiment_id":1' + "0" * 5000 + "}\n",
            "[" * 1200 + "0" + "]" * 1200 + "\n",
        )
        for index, payload in enumerate(malformed_payloads):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                candidate_path = root / "candidate.json"
                candidate_path.write_text(payload, encoding="utf-8")
                raw_dir = root / "raw"

                with self.assertRaises(self.publisher.PublicationError):
                    self.publisher.publish_candidate(candidate_path, raw_dir)

                self.assertFalse(raw_dir.exists() and any(raw_dir.iterdir()))
                self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_post_link_failure_never_reports_failure_with_an_installed_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root / "candidate", _candidate())
            raw_dir = root / "raw"
            original_unlink = Path.unlink

            def refuse_destination_unlink(path: Path, *args: object, **kwargs: object) -> None:
                if path.name == "fixture-publish-v1.json":
                    raise OSError("bounded rollback failure")
                original_unlink(path, *args, **kwargs)

            with (
                mock.patch.object(
                    self.publisher,
                    "_sync_directory",
                    side_effect=OSError("bounded sync failure"),
                ),
                mock.patch.object(Path, "unlink", new=refuse_destination_unlink),
            ):
                installed = self.publisher.publish_candidate(candidate_path, raw_dir)

            self.assertEqual(installed.name, "fixture-publish-v1.json")
            self.assertTrue(installed.is_file())
            self.assertNotIn("_local", json.loads(installed.read_bytes()))

    def test_symlink_destination_is_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root / "candidate", _candidate())
            private_dir = root / "private"
            private_dir.mkdir()
            marker = private_dir / "marker.txt"
            marker.write_text("unchanged", encoding="utf-8")
            alias = root / "raw-alias"
            alias.symlink_to(private_dir, target_is_directory=True)

            with self.assertRaises(self.publisher.PublicationError):
                self.publisher.publish_candidate(candidate_path, alias)
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            self.assertEqual(sorted(path.name for path in private_dir.iterdir()), ["marker.txt"])

    def test_candidate_verification_is_read_only_and_reports_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root, _candidate())
            before = candidate_path.read_bytes()

            result = self.verifier.verify_candidate(
                candidate_path,
                expected_feature="002-qwen-router-parity",
            )

            self.assertTrue(result["passed"])
            self.assertEqual(result["experiment_id"], "fixture-publish-v1")
            self.assertRegex(result["candidate_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(candidate_path.read_bytes(), before)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["candidate.json"])

    def test_full_schema_fixture_uses_the_semantic_validator(self) -> None:
        before = FULL_FIXTURE.read_bytes()
        result = self.verifier.verify_candidate(
            FULL_FIXTURE,
            expected_feature="002-qwen-router-parity",
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["experiment_id"], "f002-router-fixture-0001")
        self.assertEqual(FULL_FIXTURE.read_bytes(), before)

    def test_fixture_only_package_cli_is_model_independent_and_read_only(self) -> None:
        before = {
            path.relative_to(REPOSITORY_ROOT): path.read_bytes()
            for path in FULL_FIXTURE.parent.glob("*.json")
        }
        environment = os.environ.copy()
        environment["PULSARMLX_MODEL_GGUF"] = ""
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFY_COMMAND),
                "--feature",
                "002-qwen-router-parity",
                "--fixture-only",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])
        self.assertTrue(result["fixture_only"])
        self.assertEqual(result["record_count"], 3)
        after = {
            path.relative_to(REPOSITORY_ROOT): path.read_bytes()
            for path in FULL_FIXTURE.parent.glob("*.json")
        }
        self.assertEqual(after, before)

    def test_complete_publication_index_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)

            result = self._verify_publication_index(root, paths)

            self.assertEqual(result, {"claim_count": 1})

    def test_fresh_regeneration_must_equal_committed_publication_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)
            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.multiple(
                    self.verifier,
                    REPOSITORY_ROOT=root,
                    CLAIMS_LEDGER=paths["claims"],
                    REVIEWER_INDEX=paths["reviewer"],
                ):
                    result = self.verifier.verify_committed_regeneration(
                        paths["raw"].parent
                    )
                    self.assertEqual(result["artifact_count"], 6)

                    paths["generated"].write_bytes(
                        paths["generated"].read_bytes() + b"bounded mutation\n"
                    )
                    with self.assertRaises(self.verifier.VerificationError):
                        self.verifier.verify_committed_regeneration(
                            paths["raw"].parent
                        )
            finally:
                os.chdir(previous_directory)

    def test_publication_documents_reject_private_values(self) -> None:
        private_path = str(
            Path("/", "Users", "fixture-private", "publication-note.log")
        )
        for document_key in ("claims", "reviewer"):
            with (
                self.subTest(document=document_key),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                paths = self._materialize_publication_package(root)
                with paths[document_key].open("a", encoding="utf-8") as handle:
                    handle.write(f"\nPrivate diagnostic: {private_path}\n")

                with self.assertRaises(self.verifier.VerificationError) as raised:
                    self._verify_publication_index(root, paths)
                self.assertNotIn(private_path, str(raised.exception))

    def test_claim_evidence_links_must_be_existing_package_relative_paths(self) -> None:
        link_mutations = {
            "missing": "raw/002-router-parity/missing-evidence.json",
            "absolute_escape": Path("/", "outside", FULL_FIXTURE.name).as_posix(),
            "parent_escape": f"../../outside/{FULL_FIXTURE.name}",
        }
        for name, replacement in link_mutations.items():
            with (
                self.subTest(mutation=name),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                paths = self._materialize_publication_package(root)
                claims = paths["claims"].read_text(encoding="utf-8")
                claims = claims.replace(
                    f"raw/002-router-parity/{paths['raw'].name}",
                    replacement,
                )
                paths["claims"].write_text(claims, encoding="utf-8")

                with self.assertRaises(self.verifier.VerificationError):
                    self._verify_publication_index(root, paths)

    def test_reviewer_index_must_name_every_raw_and_generated_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)
            omitted = paths["generated"].relative_to(paths["research_root"]).as_posix()
            reviewer = paths["reviewer"].read_text(encoding="utf-8")
            paths["reviewer"].write_text(
                "\n".join(
                    line for line in reviewer.splitlines() if omitted not in line
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(self.verifier.VerificationError):
                self._verify_publication_index(root, paths)

    def test_generated_sidecar_provenance_mutations_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)
            original = json.loads(paths["sidecar"].read_text(encoding="utf-8"))
            source_path, source_sha256 = next(iter(original["sources"].items()))
            mutations = {
                "source_hash": lambda sidecar: sidecar["sources"].__setitem__(
                    source_path,
                    "0" * 64,
                ),
                "source_parent_escape": lambda sidecar: sidecar.__setitem__(
                    "sources",
                    {f"../{Path(source_path).name}": source_sha256},
                ),
                "source_absolute_escape": lambda sidecar: sidecar.__setitem__(
                    "sources",
                    {
                        Path("/", "outside", Path(source_path).name).as_posix(): (
                            source_sha256
                        )
                    },
                ),
                "generator_identity": lambda sidecar: sidecar.__setitem__(
                    "generator",
                    "scripts/research/unreviewed_generator.py",
                ),
                "generator_hash": lambda sidecar: sidecar.__setitem__(
                    "generator_sha256",
                    "0" * 64,
                ),
                "generation_command": lambda sidecar: sidecar.__setitem__(
                    "generation_command",
                    "python3 scripts/research/unreviewed_generator.py",
                ),
                "source_commit": lambda sidecar: sidecar.__setitem__(
                    "source_commits",
                    ["0" * 40],
                ),
                "output_hash": lambda sidecar: sidecar.__setitem__(
                    "output_sha256",
                    "0" * 64,
                ),
            }
            for name, mutate in mutations.items():
                with self.subTest(mutation=name):
                    sidecar = deepcopy(original)
                    mutate(sidecar)
                    paths["sidecar"].write_text(
                        json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )

                    with self.assertRaises(self.verifier.VerificationError):
                        self._verify_publication_index(root, paths)

    def test_duplicate_claim_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)
            evidence = json.loads(paths["raw"].read_text(encoding="utf-8"))
            duplicate = (
                "| F002-C01 Duplicate public statement | "
                f"[raw evidence](raw/002-router-parity/{paths['raw'].name}) | "
                f"{evidence['source_commit']} | {_claim_scope(evidence)} | "
                "provisional | Duplicate identities are ambiguous. |\n"
            )
            with paths["claims"].open("a", encoding="utf-8") as handle:
                handle.write(duplicate)

            with self.assertRaises(self.verifier.VerificationError):
                self._verify_publication_index(root, paths)

    def test_provisional_claim_scope_cannot_exceed_linked_evidence_depth(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)
            evidence = json.loads(paths["raw"].read_text(encoding="utf-8"))
            claims = paths["claims"].read_text(encoding="utf-8")
            self.assertIn("| provisional |", claims)
            claims = claims.replace(
                _claim_scope(evidence),
                _claim_scope(evidence).replace(
                    "depth=layer_0_router_only",
                    "depth=full_model_generation",
                ),
            )
            paths["claims"].write_text(claims, encoding="utf-8")

            with self.assertRaises(self.verifier.VerificationError):
                self._verify_publication_index(root, paths)

    def test_verified_claim_cannot_promote_provisional_linked_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = self._materialize_publication_package(root)
            evidence = json.loads(paths["raw"].read_text(encoding="utf-8"))
            self.assertEqual(evidence["claim_boundary"]["status"], "provisional")
            claims = paths["claims"].read_text(encoding="utf-8")
            claims = claims.replace("| provisional |", "| verified |")
            paths["claims"].write_text(claims, encoding="utf-8")

            with self.assertRaises(self.verifier.VerificationError):
                self._verify_publication_index(root, paths)


if __name__ == "__main__":
    unittest.main()

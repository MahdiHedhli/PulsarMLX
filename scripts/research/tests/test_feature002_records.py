"""Red-contract tests for complete Feature 002 research records.

These tests cover the evidence semantics added in the User Story 3 publication
slice.  They use only the committed fixture record and model manifest; no model
path is resolved and no MLX process is started.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "research" / "validate_evidence.py"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "research" / "v1"
BASE_FIXTURE = (
    REPOSITORY_ROOT
    / "fixtures"
    / "research"
    / "router-v1"
    / "evidence"
    / "f002-router-fixture-0001.json"
)
MODEL_MANIFEST = REPOSITORY_ROOT / "docs" / "research" / "MODEL_MANIFEST.json"
PROTOCOL = REPOSITORY_ROOT / "docs" / "research" / "EXPERIMENT_PROTOCOL.md"
ROUTER_MANIFEST = REPOSITORY_ROOT / "fixtures" / "research" / "router-v1" / "manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record() -> dict[str, object]:
    """Return a fixture record bound to the frozen Feature 001 model identity."""

    record = json.loads(BASE_FIXTURE.read_text(encoding="utf-8"))
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    model_identity = manifest["model_identity"]
    model = record["model"]
    for field in ("repository", "revision", "filename", "size_bytes", "sha256"):
        model[field] = model_identity[field]
    record["protocol"]["sha256"] = _sha256(PROTOCOL)
    record["artifacts"] = [
        {
            "kind": "frozen_protocol",
            "path": "docs/research/EXPERIMENT_PROTOCOL.md",
            "sha256": _sha256(PROTOCOL),
        },
        {
            "kind": "router_fixture_manifest",
            "path": "fixtures/research/router-v1/manifest.json",
            "sha256": _sha256(ROUTER_MANIFEST),
        },
    ]
    return record


def _unsuccessful_attempt(
    template: dict[str, object],
    *,
    observation_id: str,
    run_index: int,
    status: str,
) -> dict[str, object]:
    attempt = deepcopy(template)
    attempt.update(
        {
            "observation_id": observation_id,
            "run_index": run_index,
            "status": status,
            "selected_device": "not_available",
            "evaluated": False,
            "synchronized": False,
            "output_sha256": None,
            "correctness_passed": None,
            "failure": {
                "code": f"fixture_{status}",
                "message": f"bounded fixture {status} attempt",
                "stage": "fixture_contract_validation",
            },
        }
    )
    return attempt


class Feature002RecordContractTests(unittest.TestCase):
    """Specify semantics that the foundational v1 validator does not yet enforce."""

    maxDiff = None

    def _run_validator(self, record: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-f002-record-test-") as temporary:
            input_path = Path(temporary) / f"{record['experiment_id']}.json"
            input_path.write_text(
                json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PULSARMLX_MODEL_GGUF"] = ""
            return subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--schema-dir",
                    str(SCHEMA_DIR),
                    "--input",
                    str(input_path),
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

    def _assert_rejected(self, record: dict[str, object], expected_code: str) -> None:
        completed = self._run_validator(record)
        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0, "validator accepted invalid Feature 002 evidence")
        self.assertIn(expected_code, output)

    def _assert_accepted(self, record: dict[str, object]) -> None:
        completed = self._run_validator(record)
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )

    def test_rejects_mutated_immutable_identity_and_artifact_links(self) -> None:
        def model_field(field: str, value: object) -> Callable[[dict[str, object]], None]:
            def mutate(record: dict[str, object]) -> None:
                record["model"][field] = value  # type: ignore[index]

            return mutate

        def nested_field(
            group: str,
            field: str,
            value: object,
        ) -> Callable[[dict[str, object]], None]:
            def mutate(record: dict[str, object]) -> None:
                record[group][field] = value  # type: ignore[index]

            return mutate

        def artifact_field(field: str, value: object) -> Callable[[dict[str, object]], None]:
            def mutate(record: dict[str, object]) -> None:
                record["artifacts"][0][field] = value  # type: ignore[index]

            return mutate

        mutations: tuple[tuple[str, Callable[[dict[str, object]], None]], ...] = (
            ("model_repository", model_field("repository", "Qwen/another-repository")),
            ("model_revision", model_field("revision", "0" * 40)),
            ("model_filename", model_field("filename", "another-model.gguf")),
            ("model_size", model_field("size_bytes", 32_483_931_649)),
            ("model_sha256", model_field("sha256", "0" * 64)),
            (
                "tensor_to_oracle_hash",
                nested_field("tensor", "encoded_sha256", "1" * 64),
            ),
            (
                "input_to_oracle_hash",
                nested_field("input", "canonical_sha256", "2" * 64),
            ),
            (
                "oracle_to_tensor_hash",
                nested_field("oracle", "tensor_sha256", "3" * 64),
            ),
            (
                "oracle_to_input_hash",
                nested_field("oracle", "input_fixture_sha256", "4" * 64),
            ),
            (
                "protocol_path",
                nested_field("protocol", "path", "docs/research/MODEL_MANIFEST.json"),
            ),
            ("protocol_sha256", nested_field("protocol", "sha256", "5" * 64)),
            (
                "artifact_path_hash_pair",
                artifact_field("path", "docs/research/MODEL_MANIFEST.json"),
            ),
            ("artifact_sha256", artifact_field("sha256", "6" * 64)),
        )
        for identity, mutate in mutations:
            with self.subTest(identity=identity):
                record = _record()
                mutate(record)
                self._assert_rejected(record, "semantic_relationship")

    def test_rejects_non_contiguous_raw_attempt_indices(self) -> None:
        record = _record()
        measurements = [
            observation
            for observation in record["raw_observations"]  # type: ignore[union-attr]
            if observation["observation_kind"] == "measurement"
        ]
        measurements[-1]["run_index"] = 99

        self._assert_rejected(record, "semantic_relationship")

    def test_accepts_retained_failed_and_aborted_attempts(self) -> None:
        cases = (
            ("failed", "failed", 1),
            ("aborted", "blocked", 130),
        )
        for actual_status, claim_status, exit_code in cases:
            with self.subTest(actual_status=actual_status):
                record = _record()
                template = record["raw_observations"][0]  # type: ignore[index]
                record["actual_status"] = actual_status
                record["claim_boundary"]["status"] = claim_status  # type: ignore[index]
                record["execution"]["exit_code"] = exit_code  # type: ignore[index]
                record["failures"] = [
                    {
                        "code": f"fixture_{actual_status}",
                        "message": f"bounded fixture {actual_status} experiment",
                        "stage": "fixture_contract_validation",
                    }
                ]
                record["raw_observations"].append(  # type: ignore[union-attr]
                    _unsuccessful_attempt(
                        template,
                        observation_id=f"warmup-{actual_status}-05",
                        run_index=5,
                        status=actual_status,
                    )
                )

                # The earlier correctness evidence remains internally passing;
                # the terminal failure/abort is a separate retained outcome.
                self.assertIs(record["correctness"]["passed"], True)  # type: ignore[index]
                self._assert_accepted(record)

    def test_rejects_impossible_correctness_metric_relationships(self) -> None:
        record = _record()
        correctness = record["correctness"]  # type: ignore[assignment]
        correctness["maximum_absolute_error"] = 0.25
        correctness["mean_absolute_error"] = 0.50
        correctness["rmse"] = 0.75

        self._assert_rejected(record, "semantic_relationship")

    def test_rejects_supported_capability_as_an_unsupported_interpretation(self) -> None:
        record = _record()
        record["claim_boundary"]["unsupported_interpretations"].append(  # type: ignore[index,union-attr]
            "router_logits"
        )

        self._assert_rejected(record, "capability_overclaim")

    def test_rejects_verified_promotion_from_a_dirty_post_run_tree(self) -> None:
        record = _record()
        record["claim_boundary"]["status"] = "verified"  # type: ignore[index]
        record["source_worktree_after"] = {"state": "dirty", "paths": []}

        self._assert_rejected(record, "capability_overclaim")


if __name__ == "__main__":
    unittest.main()

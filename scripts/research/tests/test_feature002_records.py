"""Contract tests for complete Feature 002 research records.

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

from scripts.research.validate_evidence import summarize_nanoseconds


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
    """Exercise Feature 002 identity, retention, and promotion semantics."""

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

    def test_rejects_widened_frozen_tolerances(self) -> None:
        record = _record()
        record["correctness"]["absolute_tolerance"] = 1.0  # type: ignore[index]
        record["correctness"]["relative_tolerance"] = 1.0  # type: ignore[index]

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

    def test_rejects_verified_promotion_of_fixture_scoped_evidence(self) -> None:
        record = _record()
        record["warnings"] = []
        record["claim_boundary"]["unsupported_interpretations"].remove(  # type: ignore[index]
            "real_checkpoint_routing"
        )
        record["claim_boundary"]["status"] = "verified"  # type: ignore[index]

        self._assert_rejected(record, "capability_overclaim")

    def test_accepts_a_retained_evaluated_failed_observation(self) -> None:
        record = _record()
        template = deepcopy(record["raw_observations"][0])  # type: ignore[index]
        failure = {
            "code": "fixture_evaluated_failure",
            "message": "bounded evaluated fixture failure",
            "stage": "fixture_contract_validation",
        }
        template.update(
            {
                "observation_id": "warmup-evaluated-failed-05",
                "run_index": 5,
                "status": "failed",
                "selected_device": "gpu",
                "evaluated": True,
                "synchronized": True,
                "output_sha256": record["correctness"]["repeat_output_hashes"][0],  # type: ignore[index]
                "correctness_passed": False,
                "failure": failure,
            }
        )
        record["raw_observations"].append(template)  # type: ignore[union-attr]
        record["actual_status"] = "failed"
        record["claim_boundary"]["status"] = "failed"  # type: ignore[index]
        record["execution"]["exit_code"] = 1  # type: ignore[index]
        record["failures"] = [failure]

        self._assert_accepted(record)

    def test_rejects_malformed_scalars_without_traceback_or_private_output(self) -> None:
        deeply_nested: object = "bounded"
        for _ in range(70):
            deeply_nested = [deeply_nested]
        private_path = str(Path("/", "Users", "fixture-private", "checkpoint.gguf"))
        mutations: tuple[tuple[str, Callable[[dict[str, object]], None]], ...] = (
            (
                "huge_numeric",
                lambda record: record["correctness"].__setitem__(  # type: ignore[union-attr]
                    "maximum_absolute_error", 10**400
                ),
            ),
            ("excessive_depth", lambda record: record.__setitem__("warnings", deeply_nested)),
            (
                "invalid_unicode",
                lambda record: record.__setitem__("warnings", ["\ud800"]),
            ),
            (
                "private_path",
                lambda record: record["model"].__setitem__(  # type: ignore[union-attr]
                    "external_locator", private_path
                ),
            ),
            ("wrong_scalar_type", lambda record: record.__setitem__("record_kind", [])),
        )
        for name, mutate in mutations:
            with self.subTest(mutation=name):
                record = _record()
                mutate(record)
                completed = self._run_validator(record)
                output = completed.stdout + completed.stderr
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn("Traceback", output)
                self.assertNotIn(private_path, output)

    def test_rejects_noncanonical_and_incomplete_fixture_artifact_links(self) -> None:
        for name, mutate in (
            (
                "noncanonical_path",
                lambda record: record["artifacts"][0].__setitem__(  # type: ignore[index,union-attr]
                    "path", "docs/research//EXPERIMENT_PROTOCOL.md"
                ),
            ),
            (
                "missing_fixture_kind",
                lambda record: record["artifacts"][1].__setitem__(  # type: ignore[index,union-attr]
                    "kind", "unregistered_fixture_manifest"
                ),
            ),
        ):
            with self.subTest(mutation=name):
                record = _record()
                mutate(record)
                self._assert_rejected(record, "semantic_relationship")

        record = _record()
        record["artifacts"].append(  # type: ignore[union-attr]
            {
                "kind": "frozen_model_manifest",
                "path": "docs/research/MODEL_MANIFEST.json",
                "sha256": _sha256(MODEL_MANIFEST),
            }
        )
        self._assert_accepted(record)

    def test_repetition_counts_do_not_pool_incompatible_conditions(self) -> None:
        record = _record()
        measurements = [
            observation
            for observation in record["raw_observations"]  # type: ignore[union-attr]
            if observation["observation_kind"] == "measurement"
        ]
        for new_index, observation in enumerate(measurements[5:]):
            observation["condition"] = "controlled_cold"
            observation["run_index"] = new_index
        record["summaries"][0]["included_observation_ids"] = [  # type: ignore[index]
            observation["observation_id"] for observation in measurements[:5]
        ]

        self._assert_rejected(record, "insufficient_repetitions")

    def test_stage_diagnostics_do_not_require_a_clean_process_replication(self) -> None:
        record = _record()
        stage_ids: list[str] = []
        for observation in list(record["raw_observations"]):  # type: ignore[arg-type]
            if observation["observation_kind"] not in {"warmup", "measurement"}:
                continue
            duplicate = deepcopy(observation)
            duplicate["observation_id"] = f"stage-{observation['observation_id']}"
            duplicate["instrumentation_mode"] = "stage_instrumented"
            record["raw_observations"].append(duplicate)  # type: ignore[union-attr]
            if duplicate["observation_kind"] == "measurement":
                stage_ids.append(duplicate["observation_id"])

        stage_summary = deepcopy(record["summaries"][0])  # type: ignore[index]
        stage_summary["summary_id"] = "warm-stage-measurement-total"
        stage_summary["group"]["instrumentation_mode"] = "stage_instrumented"
        stage_summary["included_observation_ids"] = stage_ids
        durations = [
            observation["durations_ns"]["total_evaluated_router"]
            for observation in record["raw_observations"]  # type: ignore[union-attr]
            if observation["observation_id"] in stage_ids
        ]
        stage_summary["unfiltered_summary"] = summarize_nanoseconds(durations)
        record["summaries"].append(stage_summary)  # type: ignore[union-attr]

        self._assert_accepted(record)

    def test_auxiliary_series_does_not_infer_a_major_clean_replication_rule(self) -> None:
        record = _record()
        record["raw_observations"] = [
            observation
            for observation in record["raw_observations"]  # type: ignore[union-attr]
            if observation["observation_kind"] != "clean_process_replication"
        ]
        for observation in record["raw_observations"]:  # type: ignore[union-attr]
            observation["case_id"] = "costly-router-read-v1"
        record["summaries"] = [record["summaries"][0]]  # type: ignore[index]
        record["summaries"][0]["group"]["case_id"] = "costly-router-read-v1"  # type: ignore[index]

        self._assert_accepted(record)

    def test_summaries_do_not_pool_process_states(self) -> None:
        record = _record()
        fresh_measurement_ids: list[str] = []
        for observation in list(record["raw_observations"]):  # type: ignore[arg-type]
            if observation["observation_kind"] not in {"warmup", "measurement"}:
                continue
            duplicate = deepcopy(observation)
            duplicate["observation_id"] = f"fresh-{observation['observation_id']}"
            duplicate["process_state"] = "fresh_process"
            record["raw_observations"].append(duplicate)  # type: ignore[union-attr]
            if duplicate["observation_kind"] == "measurement":
                fresh_measurement_ids.append(duplicate["observation_id"])
        record["summaries"][0]["included_observation_ids"].extend(  # type: ignore[index,union-attr]
            fresh_measurement_ids
        )

        self._assert_rejected(record, "incompatible_summary_group")

    def test_top_level_failure_codes_equal_retained_attempt_codes(self) -> None:
        record = _record()
        template = record["raw_observations"][0]  # type: ignore[index]
        record["actual_status"] = "failed"
        record["claim_boundary"]["status"] = "failed"  # type: ignore[index]
        record["execution"]["exit_code"] = 1  # type: ignore[index]
        record["failures"] = [
            {
                "code": "fixture_failed",
                "message": "bounded fixture failed experiment",
                "stage": "fixture_contract_validation",
            },
            {
                "code": "unretained_failure",
                "message": "bounded missing attempt",
                "stage": "fixture_contract_validation",
            },
        ]
        record["raw_observations"].append(  # type: ignore[union-attr]
            _unsuccessful_attempt(
                template,
                observation_id="warmup-failed-05",
                run_index=5,
                status="failed",
            )
        )

        self._assert_rejected(record, "semantic_relationship")


if __name__ == "__main__":
    unittest.main()

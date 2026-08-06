"""Fail-closed contracts for linked Feature 002 second-batch evidence."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_DIR = REPOSITORY_ROOT / "scripts" / "research"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "research" / "v1"
VALIDATOR = RESEARCH_DIR / "validate_evidence.py"
SINGLE_CASE = "qwen3moe-layer0-router-token0-row0-v1"
TWO_CASE = "qwen3moe-layer0-router-token0-token1-batch-v1"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = _load_module(
    "pulsarmlx_second_batch_fixtures",
    Path(__file__).with_name("test_validate_evidence.py"),
)
environment_contracts = _load_module(
    "pulsarmlx_second_batch_environment_fixtures",
    Path(__file__).with_name("test_environment.py"),
)
validator = _load_module(
    "pulsarmlx_second_batch_validator",
    VALIDATOR,
)


def _prepare_batch(
    record: dict[str, object],
    *,
    batch_id: str,
    process_suffix: str,
    reverse_cases: bool,
) -> None:
    """Add the bounded two-row case and give the batch disjoint processes."""

    record["batch_id"] = batch_id
    record["process_replication_id"] = f"process-single-warm-{process_suffix}"

    single_observations = deepcopy(record["raw_observations"])
    observation_id_map: dict[str, str] = {}
    for observation in single_observations:
        original_id = str(observation["observation_id"])
        observation_id_map[original_id] = f"single-{original_id}"
        observation["observation_id"] = observation_id_map[original_id]
        observation["batch_id"] = batch_id
        observation["case_id"] = SINGLE_CASE
        kind = observation["observation_kind"]
        observation["process_replication_id"] = (
            f"process-single-clean-{process_suffix}"
            if kind == "clean_process_replication"
            else f"process-single-warm-{process_suffix}"
        )

    single_summaries = deepcopy(record["summaries"])
    for summary in single_summaries:
        summary["summary_id"] = f"single-{summary['summary_id']}"
        summary["group"]["batch_id"] = batch_id
        summary["group"]["case_id"] = SINGLE_CASE
        summary["included_observation_ids"] = [
            observation_id_map[str(observation_id)]
            for observation_id in summary["included_observation_ids"]
        ]

    two_observations = deepcopy(single_observations)
    for observation in two_observations:
        observation["observation_id"] = str(observation["observation_id"]).replace(
            "single-", "two-", 1
        )
        observation["case_id"] = TWO_CASE
        observation["process_replication_id"] = str(
            observation["process_replication_id"]
        ).replace("process-single-", "process-two-", 1)

    two_summaries = deepcopy(single_summaries)
    for summary in two_summaries:
        summary["summary_id"] = str(summary["summary_id"]).replace(
            "single-", "two-", 1
        )
        summary["group"]["case_id"] = TWO_CASE
        summary["included_observation_ids"] = [
            str(observation_id).replace("single-", "two-", 1)
            for observation_id in summary["included_observation_ids"]
        ]

    record["raw_observations"] = (
        two_observations + single_observations
        if reverse_cases
        else single_observations + two_observations
    )
    record["summaries"] = single_summaries + two_summaries


def _valid_pair() -> tuple[dict[str, object], dict[str, object]]:
    source = fixtures.valid_evidence("f002-second-batch-source")
    target = fixtures.valid_evidence("f002-second-batch-target")
    _prepare_batch(source, batch_id="batch-a", process_suffix="a", reverse_cases=False)
    _prepare_batch(target, batch_id="batch-b", process_suffix="b", reverse_cases=True)
    target["second_batch"] = {
        "status": "unavailable",
        "reason": "no third independent collection window is part of this bounded pair",
        "between_batch_variation_measured": False,
    }
    source["second_batch"] = {
        "status": "observed",
        "between_batch_variation_measured": True,
        "linked_experiment_id": target["experiment_id"],
        "linked_batch_id": target["batch_id"],
        "linked_record_sha256": validator._canonical_record_sha256(target),
    }
    return source, target


class SecondBatchContractTests(unittest.TestCase):
    maxDiff = None

    def _run_validator(
        self, records: list[dict[str, object]]
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-second-batch-") as temp:
            input_directory = Path(temp) / "evidence"
            input_directory.mkdir()
            for record in records:
                experiment_id = str(record["experiment_id"])
                (input_directory / f"{experiment_id}.json").write_text(
                    json.dumps(record, sort_keys=True, indent=2) + "\n",
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
                    str(input_directory),
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

    def _run_raw_validator(self, raw: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-duplicate-json-") as temp:
            input_path = Path(temp) / "duplicate-json.json"
            input_path.write_text(raw, encoding="utf-8")
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
                check=False,
                capture_output=True,
                text=True,
            )

    def _assert_cross_rejected(self, records: list[dict[str, object]]) -> None:
        with self.assertRaises(validator.EvidenceValidationError) as captured:
            validator._validate_second_batch_cross_records(records)
        self.assertEqual(captured.exception.code, "semantic_relationship")

    def test_accepts_a_valid_resolved_counterbalanced_pair(self) -> None:
        source, target = _valid_pair()

        completed = self._run_validator([source, target])

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_observed_and_unavailable_shapes_are_exact(self) -> None:
        old_boolean_only = fixtures.valid_evidence("f002-second-batch-old-shape")
        old_boolean_only["second_batch"] = {
            "status": "observed",
            "between_batch_variation_measured": True,
        }
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_structure(old_boolean_only)

        source, _ = _valid_pair()
        source["second_batch"]["reason"] = "observed links cannot carry an unavailable reason"
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_structure(source)

        unavailable = fixtures.valid_evidence("f002-second-batch-unavailable-shape")
        unavailable["second_batch"] = {
            "status": "unavailable",
            "reason": "the second collection window was unavailable",
            "between_batch_variation_measured": False,
            "linked_experiment_id": "unexpected-link",
        }
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_structure(unavailable)

    def test_unavailable_requires_false_measurement_and_a_bounded_reason(self) -> None:
        for reason, measured in (("", False), ("x" * 513, False), ("unavailable", True)):
            with self.subTest(reason_length=len(reason), measured=measured):
                record = fixtures.valid_evidence("f002-second-batch-invalid-unavailable")
                record["second_batch"] = {
                    "status": "unavailable",
                    "reason": reason,
                    "between_batch_variation_measured": measured,
                }
                with self.assertRaises(validator.EvidenceValidationError):
                    validator.validate_record(record)

    def test_external_timing_cannot_omit_a_second_batch_disposition(self) -> None:
        record = fixtures.valid_evidence("f002-second-batch-external-missing")
        record["evidence_scope"] = "external_checkpoint"

        with self.assertRaises(validator.EvidenceValidationError) as captured:
            validator._validate_semantics(record, REPOSITORY_ROOT)

        self.assertEqual(captured.exception.code, "semantic_relationship")

    def test_rejects_self_missing_same_batch_and_wrong_hash_links(self) -> None:
        source, target = _valid_pair()
        source["second_batch"]["linked_experiment_id"] = source["experiment_id"]
        self._assert_cross_rejected([source, target])

        source, _ = _valid_pair()
        self._assert_cross_rejected([source])

        source, target = _valid_pair()
        source["second_batch"]["linked_batch_id"] = source["batch_id"]
        self._assert_cross_rejected([source, target])

        source, target = _valid_pair()
        source["second_batch"]["linked_record_sha256"] = "0" * 64
        self._assert_cross_rejected([source, target])

    def test_rejects_reused_processes_chains_and_cycles(self) -> None:
        source, target = _valid_pair()
        target["process_replication_id"] = source["process_replication_id"]
        self._assert_cross_rejected([source, target])

        source, target = _valid_pair()
        third = deepcopy(target)
        third["experiment_id"] = "f002-second-batch-third"
        third["batch_id"] = "batch-c"
        target["second_batch"] = {
            "status": "observed",
            "between_batch_variation_measured": True,
            "linked_experiment_id": third["experiment_id"],
            "linked_batch_id": third["batch_id"],
            "linked_record_sha256": validator._canonical_record_sha256(third),
        }
        self._assert_cross_rejected([source, target, third])

        source, target = _valid_pair()
        target["second_batch"] = {
            "status": "observed",
            "between_batch_variation_measured": True,
            "linked_experiment_id": source["experiment_id"],
            "linked_batch_id": source["batch_id"],
            "linked_record_sha256": validator._canonical_record_sha256(source),
        }
        self._assert_cross_rejected([source, target])

    def test_rejects_incompatible_frozen_and_runtime_facts(self) -> None:
        mutations = {
            "source": lambda target: target.__setitem__("source_commit", "e" * 40),
            "protocol": lambda target: target["protocol"].__setitem__("order_seed", 22003),
            "model": lambda target: target["model"].__setitem__("sha256", "e" * 64),
            "tensor": lambda target: target["tensor"].__setitem__("encoded_sha256", "e" * 64),
            "input": lambda target: target["input"].__setitem__("canonical_sha256", "e" * 64),
            "oracle": lambda target: target["oracle"].__setitem__("output_sha256", "e" * 64),
            "device": lambda target: target["raw_observations"][0].__setitem__(
                "selected_device", "cpu"
            ),
            "environment": lambda target: target["environment"].__setitem__(
                "interference_admission", "postponed"
            ),
        }
        for fact, mutate in mutations.items():
            with self.subTest(fact=fact):
                source, target = _valid_pair()
                mutate(target)
                self._assert_cross_rejected([source, target])

    def test_rejects_every_execution_identity_mutation(self) -> None:
        mutations = {
            "shell": lambda execution: execution.__setitem__("shell", "bash"),
            "command": lambda execution: execution.__setitem__(
                "command", "python3 scripts/research/run_router_experiment.py --changed"
            ),
            "argv": lambda execution: execution["argv"].append("--changed"),
            "working_directory_policy": lambda execution: execution.__setitem__(
                "working_directory_policy", "different_root"
            ),
            "exit_code": lambda execution: execution.__setitem__("exit_code", 1),
            "build_profile": lambda execution: execution.__setitem__(
                "build_profile", "debug"
            ),
            "features": lambda execution: execution["features"].append("changed"),
            "benchmark_order_policy": lambda execution: execution.__setitem__(
                "benchmark_order_policy", "changed_order"
            ),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                source, target = _valid_pair()
                mutate(target["execution"])
                self._assert_cross_rejected([source, target])

    def test_rejects_individually_admitted_load_average_drift(self) -> None:
        source_snapshot = environment_contracts._collect(
            load_average=lambda: (1.0, 0.5, 0.25)
        )
        target_snapshot = environment_contracts._collect(
            load_average=lambda: (14.0, 14.0, 0.25)
        )
        self.assertEqual(source_snapshot["interference_admission"], "admitted")
        self.assertEqual(target_snapshot["interference_admission"], "admitted")
        self.assertEqual(
            source_snapshot["observations"]["physical_cpu_count"]["value"], 20
        )

        source, target = _valid_pair()
        source["environment"]["before_snapshot"] = source_snapshot
        target["environment"]["before_snapshot"] = target_snapshot

        self._assert_cross_rejected([source, target])

    def test_rejects_each_load_average_observation_mutation(self) -> None:
        snapshot = environment_contracts._collect(
            load_average=lambda: (1.0, 0.5, 0.25)
        )
        changed_values = {
            "load_average_1m": 2.0,
            "load_average_5m": 1.5,
            "load_average_15m": 1.25,
        }
        for field, changed_value in changed_values.items():
            with self.subTest(field=field):
                source, target = _valid_pair()
                source["environment"]["before_snapshot"] = deepcopy(snapshot)
                target["environment"]["before_snapshot"] = deepcopy(snapshot)
                target["environment"]["before_snapshot"]["observations"][field][
                    "value"
                ] = changed_value
                self._assert_cross_rejected([source, target])

    def test_duplicate_json_keys_fail_before_privacy_validation(self) -> None:
        private_marker = "/" + "Users/private-operator/model.gguf"
        records = (
            (
                '{"experiment_id":"first","experiment_id":"'
                + private_marker
                + '"}'
            ),
            (
                '{"experiment_id":"duplicate-json","nested":'
                + '{"value":1,"value":"'
                + private_marker
                + '"}}'
            ),
        )
        for raw in records:
            with self.subTest(nested='"nested"' in raw):
                completed = self._run_raw_validator(raw)
                output = completed.stdout + completed.stderr
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("schema_violation", output)
                self.assertNotIn("private_value", output)
                self.assertNotIn(private_marker, output)
                self.assertNotIn("Traceback", output)
                self.assertLess(len(output.encode("utf-8")), 512)

    def test_rejects_repeated_case_block_interleaving(self) -> None:
        source, target = _valid_pair()
        single = next(
            observation
            for observation in source["raw_observations"]
            if observation["observation_kind"] == "warmup"
            and observation["case_id"] == SINGLE_CASE
        )
        two = next(
            observation
            for observation in source["raw_observations"]
            if observation["observation_kind"] == "warmup"
            and observation["case_id"] == TWO_CASE
        )
        source["raw_observations"].extend((deepcopy(single), deepcopy(two)))

        # The warm-up step now reads single,two,single,two. Only one frozen
        # contiguous block per case is admissible.
        self._assert_cross_rejected([source, target])

    def test_rejects_a_second_batch_without_reversed_case_order(self) -> None:
        source, target = _valid_pair()
        observations = target["raw_observations"]
        non_measurements = [
            observation
            for observation in observations
            if observation["observation_kind"] != "measurement"
        ]
        single_measurements = [
            observation
            for observation in observations
            if observation["observation_kind"] == "measurement"
            and observation["case_id"] == SINGLE_CASE
        ]
        two_measurements = [
            observation
            for observation in observations
            if observation["observation_kind"] == "measurement"
            and observation["case_id"] == TWO_CASE
        ]
        # The record still encounters the two-row case first overall, but the
        # measurement pair itself is not reversed. A first-occurrence-only
        # validator would incorrectly accept this schedule.
        target["raw_observations"] = (
            non_measurements + single_measurements + two_measurements
        )

        self._assert_cross_rejected([source, target])


if __name__ == "__main__":
    unittest.main()

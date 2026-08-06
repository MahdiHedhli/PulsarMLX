"""Red contract tests for the Feature 002 timing evidence policy.

These tests stay model-free.  They exercise the checked-in statistics helper
and evidence-validator command boundary so timing evidence cannot silently
weaken the frozen experiment protocol.
"""

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


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


statistics = _load_module("pulsarmlx_timing_statistics", RESEARCH_DIR / "statistics.py")
fixtures = _load_module(
    "pulsarmlx_timing_validator_fixtures",
    Path(__file__).with_name("test_validate_evidence.py"),
)
environment_contracts = _load_module(
    "pulsarmlx_timing_environment_fixtures",
    Path(__file__).with_name("test_environment.py"),
)
validator = _load_module(
    "pulsarmlx_timing_validator",
    RESEARCH_DIR / "validate_evidence.py",
)

SINGLE_CASE, TWO_CASE = validator.SECOND_BATCH_CASE_ORDER
SINGLE_OUTPUT_SHA256 = "b" * 64
TWO_OUTPUT_SHA256 = "c" * 64


def _external_evidence(experiment_id: str) -> dict[str, object]:
    """Return model-free evidence shaped like an admitted external run."""

    record = fixtures.valid_evidence(experiment_id)
    before = environment_contracts._collect()
    after = environment_contracts._collect(capture_phase="after")
    for snapshot in (before, after):
        snapshot["observations"]["repository_commit"]["value"] = fixtures.SOURCE_COMMIT
        snapshot["observations"]["pulsarmlx_version"]["value"] = fixtures.SOURCE_COMMIT
    resources = {
        "process_footprint_bytes": environment_contracts.environment.observed(2048, "worker"),
        "mlx_active_memory_bytes": environment_contracts.environment.observed(256, "worker"),
        "mlx_cache_memory_bytes": environment_contracts.environment.observed(128, "worker"),
        "mlx_peak_memory_bytes": environment_contracts.environment.observed(512, "worker"),
        "process_cpu_time_seconds": environment_contracts.environment.unavailable(
            "not exposed by the bounded worker protocol", "worker_process_cpu_time"
        ),
        "process_bytes_read": environment_contracts.environment.unavailable(
            "not exposed reliably by the bounded worker protocol", "worker_process_bytes_read"
        ),
        "worker_backend": environment_contracts.environment.observed("apple-mlx", "worker"),
        "worker_requested_device": environment_contracts.environment.observed("gpu", "worker"),
        "worker_selected_device": environment_contracts.environment.observed("gpu", "worker"),
        "worker_fallback_used": environment_contracts.environment.observed(False, "worker"),
        "worker_evaluated": environment_contracts.environment.observed(True, "worker"),
        "worker_synchronized": environment_contracts.environment.observed(True, "worker"),
    }
    record["environment"] = environment_contracts.environment.combine_environment_evidence(
        before_snapshot=before,
        after_snapshot=after,
        after_unavailable_reason=None,
        benchmark_resources=resources,
    )
    record["evidence_scope"] = "external_checkpoint"
    for observation in record["raw_observations"]:
        duration = observation["durations_ns"]["total_evaluated_router"]
        observation["durations_ns"] = {
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization",
            },
            "total_evaluated_router": {
                "status": "observed",
                "duration_ns": duration,
            },
        }
    return record


def _first_process_repetition_record(
    *,
    single_count: int = 10,
    two_count: int = 10,
    condition: str = "first_read_new_process_os_cache_uncontrolled",
) -> dict[str, object]:
    """Return a two-case record with flat 0+1 fresh-process cohorts."""

    record = fixtures.valid_evidence("timing-first-process-cohorts")
    record["evidence_scope"] = "external_checkpoint"
    single_case_observations = deepcopy(record["raw_observations"])
    two_case_observations = deepcopy(single_case_observations)
    for observation in two_case_observations:
        observation["observation_id"] = f"two-{observation['observation_id']}"
        observation["case_id"] = TWO_CASE
        observation["process_replication_id"] = (
            f"two-{observation['process_replication_id']}"
        )
        observation["output_sha256"] = TWO_OUTPUT_SHA256
    record["raw_observations"] = single_case_observations + two_case_observations
    record["correctness"]["deterministic_repeat_count"] = 20
    record["correctness"]["repeat_output_hashes"] = (
        [SINGLE_OUTPUT_SHA256] * 10 + [TWO_OUTPUT_SHA256] * 10
    )

    template = next(
        observation
        for observation in single_case_observations
        if observation["observation_kind"] == "measurement"
    )
    for case_id, output_sha256, prefix, count in (
        (SINGLE_CASE, SINGLE_OUTPUT_SHA256, "single", single_count),
        (TWO_CASE, TWO_OUTPUT_SHA256, "two", two_count),
    ):
        for index in range(count):
            observation = deepcopy(template)
            observation.update(
                {
                    "observation_id": f"{prefix}-first-read-{index:02d}",
                    "case_id": case_id,
                    "process_replication_id": (
                        f"{prefix}-first-read-process-{index:02d}"
                    ),
                    "observation_kind": "measurement",
                    "process_state": "fresh_process",
                    "condition": condition,
                    "instrumentation_mode": "minimally_instrumented",
                    "run_index": 0,
                    "output_sha256": output_sha256,
                }
            )
            record["raw_observations"].append(observation)
    return record


def _observation_index(record: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(observation["observation_id"]): observation
        for observation in record["raw_observations"]
    }


class TimingPolicyContractTests(unittest.TestCase):
    maxDiff = None

    def _run_validator(self, record: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-timing-policy-") as temp:
            input_directory = Path(temp) / "evidence"
            input_directory.mkdir()
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

    def _assert_accepted(self, record: dict[str, object]) -> None:
        completed = self._run_validator(record)
        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stdout + completed.stderr,
        )

    def _assert_rejected(self, record: dict[str, object], code: str) -> None:
        completed = self._run_validator(record)
        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0, msg="validator accepted invalid timing evidence")
        self.assertIn(code, output, msg=output)

    def _assert_observation_contract_rejected(
        self, record: dict[str, object], code: str = "semantic_relationship"
    ) -> None:
        with self.assertRaises(validator.EvidenceValidationError) as captured:
            validator._validate_observations(record)
        self.assertEqual(captured.exception.code, code)

    def test_groups_every_incompatible_timing_dimension_separately(self) -> None:
        base = {
            "observation_id": "obs-00",
            "experiment_id": "experiment-a",
            "case_id": "single-row",
            "batch_id": "batch-a",
            "process_replication_id": "process-a",
            "observation_kind": "measurement",
            "observation_status": "passed",
            "process_state": "reused_process",
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "stage": "total_evaluated_router",
            "requested_device": "gpu",
            "selected_device": "gpu",
            "source_commit": "a" * 40,
            "memory_pressure": "normal",
            "power_mode": "automatic",
            "thermal_state": "nominal",
            "interference_admission": "admitted",
        }
        incompatible = (
            ("experiment_id", "experiment-b"),
            ("process_replication_id", "process-b"),
            ("observation_kind", "warmup"),
            ("observation_status", "failed"),
            ("process_state", "fresh_process"),
            ("stage", "router_projection"),
            ("requested_device", "not_applicable"),
            ("selected_device", "not_available"),
            ("memory_pressure", "warning"),
            ("power_mode", "low_power"),
            ("thermal_state", "serious"),
            ("interference_admission", "observed_interference"),
        )
        observations = [base, {**base, "observation_id": "obs-01"}]
        observations.extend(
            {**base, "observation_id": f"obs-{index:02d}", field: value}
            for index, (field, value) in enumerate(incompatible, start=2)
        )

        groups = statistics.group_raw_observations(observations)

        self.assertEqual(len(groups), len(incompatible) + 1)
        self.assertEqual(sorted(map(len, groups.values())), [1] * len(incompatible) + [2])

    def test_postponed_or_interfered_batches_cannot_claim_clean_results(self) -> None:
        for admission in ("postponed", "observed_interference"):
            with self.subTest(admission=admission):
                record = fixtures.valid_evidence(f"timing-{admission}")
                record["environment"]["interference_admission"] = admission
                self._assert_rejected(record, "semantic_relationship")

    def test_unfiltered_summary_is_mandatory_and_filtered_requires_a_rule(self) -> None:
        missing_unfiltered = fixtures.valid_evidence("timing-missing-unfiltered")
        del missing_unfiltered["summaries"][0]["unfiltered_summary"]
        self._assert_rejected(missing_unfiltered, "schema_violation")

        undeclared_filter = fixtures.valid_evidence("timing-undeclared-filter")
        summary = undeclared_filter["summaries"][0]
        summary["filtered_summary"] = deepcopy(summary["unfiltered_summary"])
        self._assert_rejected(undeclared_filter, "semantic_relationship")

    def test_inexpensive_synthetic_series_requires_thirty_measurements(self) -> None:
        record = fixtures.valid_evidence("timing-synthetic-29")
        observations = record["raw_observations"]
        template = next(
            item for item in observations if item["observation_kind"] == "measurement"
        )
        observations[:] = [
            item for item in observations if item["observation_kind"] != "measurement"
        ]
        measurements = []
        for index in range(29):
            item = deepcopy(template)
            item["observation_id"] = f"measurement-{index:02d}"
            item["run_index"] = index
            item["case_id"] = "generated-qwen3moe-router-single-row-v1"
            item["durations_ns"]["total_evaluated_router"] = 1_000 + index
            measurements.append(item)
        for item in observations:
            item["case_id"] = "generated-qwen3moe-router-single-row-v1"
        observations.extend(measurements)
        measured_summary = record["summaries"][0]
        measured_summary["group"]["case_id"] = "generated-qwen3moe-router-single-row-v1"
        measured_summary["included_observation_ids"] = [
            item["observation_id"] for item in measurements
        ]
        measured_summary["unfiltered_summary"] = fixtures._summary_values(
            [1_000 + index for index in range(29)]
        )
        record["summaries"][1]["group"]["case_id"] = (
            "generated-qwen3moe-router-single-row-v1"
        )

        self._assert_rejected(record, "insufficient_repetitions")

    def test_first_process_cohorts_use_distinct_fresh_process_zero_plus_one_series(
        self,
    ) -> None:
        # The flat raw ledger can contain two predeclared ten-series cohorts for
        # one case (primary plus clean-process) and one cohort for the other.
        record = _first_process_repetition_record(single_count=20, two_count=10)
        validator._validate_repetitions(record, _observation_index(record))

        for invalid in (
            _first_process_repetition_record(two_count=9),
            _first_process_repetition_record(two_count=11),
        ):
            with self.assertRaises(validator.EvidenceValidationError) as captured:
                validator._validate_repetitions(invalid, _observation_index(invalid))
            self.assertEqual(captured.exception.code, "insufficient_repetitions")

    def test_first_process_series_reject_reuse_warmups_and_multiple_measurements(
        self,
    ) -> None:
        reused_state = _first_process_repetition_record()
        reused_state["raw_observations"][-1]["process_state"] = "reused_process"

        warmup = _first_process_repetition_record()
        warmup["raw_observations"][-1]["observation_kind"] = "warmup"

        multiple = _first_process_repetition_record()
        extra = deepcopy(multiple["raw_observations"][-1])
        extra["observation_id"] = "two-first-read-extra-measurement"
        extra["run_index"] = 1
        multiple["raw_observations"].append(extra)

        duplicate_process = _first_process_repetition_record()
        duplicate_process["raw_observations"][-1]["process_replication_id"] = (
            duplicate_process["raw_observations"][-2]["process_replication_id"]
        )

        for invalid in (reused_state, warmup, multiple, duplicate_process):
            with self.assertRaises(validator.EvidenceValidationError) as captured:
                validator._validate_repetitions(invalid, _observation_index(invalid))
            self.assertEqual(captured.exception.code, "insufficient_repetitions")

    def test_controlled_cold_uses_the_same_fresh_process_zero_plus_one_contract(
        self,
    ) -> None:
        record = _first_process_repetition_record(condition="controlled_cold")
        validator._validate_repetitions(record, _observation_index(record))

    def test_unavailable_phases_use_status_and_reason_while_total_remains_observed(self) -> None:
        record = fixtures.valid_evidence("timing-explicit-phases")
        for observation in record["raw_observations"]:
            total = observation["durations_ns"]["total_evaluated_router"]
            observation["durations_ns"] = {
                "total_evaluated_router": {
                    "status": "observed",
                    "duration_ns": total,
                },
                "dequantization": {
                    "status": "not_applicable",
                    "reason": "the admitted router tensor is F32",
                },
                "host_to_device_transfer": {
                    "status": "unavailable",
                    "reason": "MLX did not expose a separable transfer boundary",
                },
            }

        self._assert_accepted(record)

    def test_second_batch_unavailable_requires_a_bounded_reason(self) -> None:
        available_reason = fixtures.valid_evidence("timing-second-batch-unavailable")
        available_reason["second_batch"] = {
            "status": "unavailable",
            "reason": "the later independent collection window was unavailable",
            "between_batch_variation_measured": False,
        }
        self._assert_accepted(available_reason)

        missing_reason = fixtures.valid_evidence("timing-second-batch-missing-reason")
        missing_reason["second_batch"] = {
            "status": "unavailable",
            "between_batch_variation_measured": False,
        }
        self._assert_rejected(missing_reason, "semantic_relationship")

    def test_external_timing_requires_the_frozen_structured_stage_contract(self) -> None:
        valid = _external_evidence("timing-external-structured")
        validator._validate_observations(valid)

        arbitrary = _external_evidence("timing-external-arbitrary")
        arbitrary["raw_observations"][0]["durations_ns"]["arbitrary_stage"] = {
            "status": "observed",
            "duration_ns": 7,
        }
        self._assert_observation_contract_rejected(arbitrary)

        legacy_integer = _external_evidence("timing-external-legacy-integer")
        legacy_integer["raw_observations"][0]["durations_ns"][
            "total_evaluated_router"
        ] = 7
        self._assert_observation_contract_rejected(legacy_integer)

        missing_total = _external_evidence("timing-external-missing-total")
        missing_total["raw_observations"][0]["durations_ns"][
            "total_evaluated_router"
        ] = {"status": "unavailable", "reason": "evaluation did not complete"}
        self._assert_observation_contract_rejected(missing_total)

        wrong_f32_reason = _external_evidence("timing-external-wrong-f32-reason")
        wrong_f32_reason["raw_observations"][0]["durations_ns"]["dequantization"][
            "reason"
        ] = "the tensor happened to be skipped"
        self._assert_observation_contract_rejected(wrong_f32_reason)

        wrong_not_applicable = _external_evidence("timing-external-wrong-na-stage")
        wrong_not_applicable["raw_observations"][0]["durations_ns"]["file_io"] = {
            "status": "not_applicable",
            "reason": "not measured",
        }
        self._assert_observation_contract_rejected(wrong_not_applicable)

        # A fixture cannot become real evidence by changing only its scope and
        # attaching otherwise valid host/timing metadata.
        self._assert_rejected(valid, "semantic_relationship")

    def test_external_stage_mode_requires_every_frozen_boundary(self) -> None:
        record = _external_evidence("timing-external-stage-incomplete")
        observation = record["raw_observations"][0]
        observation["instrumentation_mode"] = "stage_instrumented"
        self._assert_observation_contract_rejected(record)


if __name__ == "__main__":
    unittest.main()

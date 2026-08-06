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

    def test_groups_every_incompatible_timing_dimension_separately(self) -> None:
        base = {
            "observation_id": "obs-00",
            "experiment_id": "experiment-a",
            "case_id": "single-row",
            "batch_id": "batch-a",
            "process_replication_id": "process-a",
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


if __name__ == "__main__":
    unittest.main()

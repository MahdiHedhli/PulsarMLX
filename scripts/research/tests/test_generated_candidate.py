"""Model-free validation tests for the generated-router timing candidate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "validate_generated_candidate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "pulsarmlx_test_generated_candidate", MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("generated candidate validator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_module()
environment = validator._ENVIRONMENT
SOURCE_COMMIT = "a" * 40


def _load(relative: str):
    return json.loads((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))


def _memory():
    return {
        "mlx_active_bytes": 1024,
        "mlx_cache_bytes": 128,
        "mlx_peak_bytes": 2048,
        "process_footprint_bytes": 4096,
        "process_footprint_source": "fixture-rss",
        "system_pressure": "normal",
        "reported_summed_total_bytes": None,
    }


def _candidate_output(case):
    hashes = validator.recompute_golden_hashes(case)
    return {
        "case_id": case["case_id"],
        "case_scope": "synthetic_fixture",
        "row_count": case["hidden_shape"][0],
        "logits_shape": case["logits_shape"],
        "logits": [value for row in case["logits"] for value in row],
        "logits_f32le_sha256": hashes["logits_f32le_sha256"],
        "full_probabilities_shape": case["logits_shape"],
        "full_probabilities": [
            value for row in case["full_softmax_probabilities"] for value in row
        ],
        "full_probabilities_f32le_sha256": hashes[
            "full_softmax_probabilities_f32le_sha256"
        ],
        "selected_expert_ids": case["selected_expert_ids"],
        "selected_expert_ids_u32le_sha256": hashes[
            "selected_expert_ids_u32le_sha256"
        ],
        "selected_probabilities": case["selected_probabilities"],
        "selected_probabilities_f32le_sha256": hashes[
            "selected_probabilities_f32le_sha256"
        ],
        "normalized_weights": case["normalized_weights"],
        "normalized_weights_f32le_sha256": hashes[
            "normalized_weights_f32le_sha256"
        ],
        "complete_output_sha256": hashes["complete_output_sha256"],
    }


def _positive_case(case):
    output = _candidate_output(case)
    rows = case["hidden_shape"][0]
    comparison_output = {
        **output,
        "logits": [
            output["logits"][index * 128 : (index + 1) * 128]
            for index in range(rows)
        ],
        "full_probabilities": [
            output["full_probabilities"][index * 128 : (index + 1) * 128]
            for index in range(rows)
        ],
    }
    return {
        "backend": "apple-mlx",
        "case_id": case["case_id"],
        "fixture_kind": "synthetic",
        "case_scope": "synthetic_fixture",
        "validation_mode": "mlx_gpu_execution_and_host_golden_comparison",
        "real_checkpoint_evidence": False,
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
        "operation": "complete_router_projection_topk",
        "batch_size": case["hidden_shape"][0],
        "hidden_width": 2048,
        "expert_count": 128,
        "top_k": 8,
        "output_dtype": "float32",
        "selected_expert_ids": case["selected_expert_ids"],
        "hashes": {
            "logits_f32le_sha256": output["logits_f32le_sha256"],
            "full_probabilities_f32le_sha256": output[
                "full_probabilities_f32le_sha256"
            ],
            "selected_probabilities_f32le_sha256": output[
                "selected_probabilities_f32le_sha256"
            ],
            "normalized_weights_f32le_sha256": output[
                "normalized_weights_f32le_sha256"
            ],
        },
        "comparison": validator._independent_output_comparison(case, comparison_output),
        "memory_gauges": _memory(),
        "status": "passed",
    }


def valid_candidate():
    manifest_path = REPOSITORY_ROOT / validator.MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    golden = _load("fixtures/research/router-v1/golden/expected_results.json")
    ties = _load("fixtures/research/router-v1/synthetic-tie.json")
    single = golden["cases"][validator.GOLDEN_CASE_ID]
    canonical = _candidate_output(single)
    output_hash = canonical["complete_output_sha256"]

    positive_cases = [
        _positive_case(golden["cases"][validator.GOLDEN_CASE_ID]),
        _positive_case(golden["cases"][validator.TWO_ROW_CASE_ID]),
    ]
    tie_cases = []
    for source in ties["cases"]:
        source_hashes = source["hashes"]
        tie_cases.append(
            {
                "case_id": source["case_id"],
                "kind": source["kind"],
                "fixture_kind": "synthetic",
                "case_scope": "synthetic_fixture",
                "validation_mode": "host_contract_validation",
                "mlx_executed": False,
                "real_checkpoint_evidence": False,
                "cutoff": {
                    "rank_8_expert_id": source["cutoff"]["rank_8_expert_id"],
                    "rank_9_expert_id": source["cutoff"]["rank_9_expert_id"],
                    "relation": source["cutoff"]["relation"],
                },
                "selected_expert_ids": source["selected_expert_ids"],
                "hashes": {
                    "logits_f32le_sha256": source_hashes["logits_f32le_sha256"],
                    "full_probabilities_f32le_sha256": source_hashes[
                        "full_softmax_probabilities_f32le_sha256"
                    ],
                    "selected_probabilities_f32le_sha256": source_hashes[
                        "selected_probabilities_f32le_sha256"
                    ],
                    "normalized_weights_f32le_sha256": source_hashes[
                        "normalized_weights_f32le_sha256"
                    ],
                },
                "status": "passed",
            }
        )
    negative_cases = []
    for relative in validator.EXPECTED_MANIFEST_FILES[3:10]:
        document = _load(f"fixtures/research/router-v1/{relative}")
        case = document["case"]
        failure = case["expected_failure"]
        negative_cases.append(
            {
                "fixture": relative,
                "fixture_id": document["fixture_id"],
                "category": case["category"],
                "validation_surface": case["validation_surface"],
                "expected_code": failure["code"],
                "must_precede": failure["must_precede"],
                "accepted_result": False,
                "router_runner_called": False,
                "validation_mode": "fixture_contract_validation",
                "mlx_executed": False,
                "mutation": case["mutation"],
                "status": "covered",
            }
        )

    observations = []
    results = []
    for attempt_index in range(validator.ATTEMPT_COUNT):
        if attempt_index < validator.WARMUP_COUNT:
            kind = "warmup"
            run_index = attempt_index
        else:
            kind = "measurement"
            run_index = attempt_index - validator.WARMUP_COUNT
        observation_id = f"generated-router-{kind}-{run_index:02}"
        observations.append(
            {
                "observation_id": observation_id,
                "run_index": run_index,
                "observation_kind": kind,
                "process_replication_id": validator.PROCESS_REPLICATION_ID,
                "process_state": "reused_process",
                "condition": "warm",
                "instrumentation_mode": "minimally_instrumented",
                "monotonic_clock": "perf_counter_ns",
                "stages": {
                    "dequantization": {
                        "status": "not_applicable",
                        "reason": "f32_router_requires_no_dequantization",
                    },
                    "total_evaluated_router": {
                        "status": "observed",
                        "duration_ns": 1000 + attempt_index,
                    },
                },
                "status": "passed",
                "requested_device": "gpu",
                "selected_device": "gpu",
                "fallback_used": False,
                "evaluated": True,
                "synchronized": True,
                "output_sha256": output_hash,
                "correctness_passed": True,
            }
        )
        results.append(
            {
                "observation_id": observation_id,
                "backend": "apple-mlx",
                "requested_device": "gpu",
                "selected_device": "gpu",
                "fallback_used": False,
                "evaluated": True,
                "synchronized": True,
                "golden_comparison_passed": True,
                "output_sha256": output_hash,
                "memory_gauges": _memory(),
                "status": "passed",
            }
        )

    return {
        "schema_version": 1,
        "validation": "qwen3moe-router-fixtures",
        "status": "passed",
        "passed": True,
        "fixture_kind": "synthetic",
        "evidence_level": "synthetic_fixture_only",
        "model_free": True,
        "real_checkpoint_evidence": False,
        "external_checkpoint_accessed": False,
        "manifest": validator.MANIFEST_PATH,
        "manifest_sha256": validator.MANIFEST_SHA256,
        "manifest_files": manifest["files"],
        "runtime": {
            "protocol": 1,
            "worker_version": "0.1.0",
            "python_version": "3.12.0",
            "python_arch": "arm64",
            "mlx_version": "0.32.0",
            "macos_version": "26.0",
            "metal_available": True,
            "gpu_count": 1,
            "operations": [
                "health",
                "tensor_probe",
                "run_fixture",
                "run_router",
                "run_synthetic_moe",
                "shutdown",
            ],
            "model_operation_advertised": False,
        },
        "positive_cases": positive_cases,
        "synthetic_tie_cases": tie_cases,
        "negative_cases": negative_cases,
        "generated_router_microbenchmark": {
            "benchmark_id": validator.BENCHMARK_ID,
            "case_id": validator.GOLDEN_CASE_ID,
            "fixture_kind": "synthetic",
            "evidence_level": "synthetic_fixture_only",
            "model_free": True,
            "real_checkpoint_evidence": False,
            "manifest_sha256": validator.MANIFEST_SHA256,
            "status": "passed",
            "passed": True,
            "warmup_count": validator.WARMUP_COUNT,
            "measurement_count": validator.MEASUREMENT_COUNT,
            "retained_observation_count": validator.ATTEMPT_COUNT,
            "complete_output_sha256": output_hash,
            "canonical_output": canonical,
            "stage_sum_claimed": False,
            "timing_series": {
                "benchmark_id": validator.BENCHMARK_ID,
                "case_id": validator.GOLDEN_CASE_ID,
                "row_count": 1,
                "series_kind": "inexpensive_synthetic",
                "replication_role": "primary",
                "process_replication_id": validator.PROCESS_REPLICATION_ID,
                "process_state": "reused_process",
                "condition": "warm",
                "instrumentation_mode": "minimally_instrumented",
                "warmup_count": validator.WARMUP_COUNT,
                "measurement_count": validator.MEASUREMENT_COUNT,
                "raw_timing_observations": observations,
            },
            "result_records": results,
            "failure": None,
            "exclusions": validator.BENCHMARK_EXCLUSIONS,
        },
        "cleanup": {
            "attempted": True,
            "outcome": "graceful",
            "exit_code": 0,
            "message": None,
        },
        "failure": None,
        "warnings": validator.ROOT_WARNINGS,
        "exclusions": validator.ROOT_EXCLUSIONS,
    }


def _snapshot(*, phase: str):
    observed = environment.observed
    gib = environment.GIB
    values = {
        "repository_commit": SOURCE_COMMIT,
        "worktree_dirty": False,
        "captured_at_utc": "2026-08-06T06:00:00Z" if phase == "before" else "2026-08-06T06:01:00Z",
        "python_version": "3.12.0",
        "mlx_version": "0.32.0",
        "rust_version": "rustc 1.97.1 (fixture)",
        "cargo_version": "cargo 1.97.1 (fixture)",
        "worker_protocol_version": "1",
        "pulsarmlx_version": SOURCE_COMMIT,
        "macos_product_version": "26.0",
        "macos_build": "25A123",
        "shell_architecture": "arm64",
        "chip_model": "Apple M1 Ultra",
        "unified_memory_bytes": 128 * gib,
        "physical_cpu_count": 20,
        "logical_cpu_count": 20,
        "filesystem_type": "apfs",
        "available_storage_bytes": 200 * gib,
        "storage_rounding_bytes": gib,
        "memory_pressure": "normal",
        "power_mode": "automatic",
        "thermal_state": "nominal",
        "collector_process_resident_bytes": 1024,
        "collector_peak_resident_bytes": 2048,
        "collector_process_cpu_time_seconds": 0.1,
        "collector_process_bytes_read": 0,
        "load_average_1m": 1.0,
        "load_average_5m": 0.5,
        "load_average_15m": 0.25,
        "workload_category": "none",
        "material_concurrent_workload": False,
        "benchmark_concurrency": 1,
        "capture_wall_time_ns": 1000,
    }
    observations = {name: observed(value, "fixture") for name, value in values.items()}
    return {
        "snapshot_schema": "pulsarmlx.research.environment",
        "snapshot_schema_version": "1.0.0",
        "capture_phase": phase,
        "platform": "macos-arm64",
        "requested_backend": "apple-mlx",
        "requested_device": "gpu",
        "storage_role": "candidate_evidence_storage",
        "storage_locator": "$PULSARMLX_ROUTER_EVIDENCE",
        "safe_environment": {
            "PULSARMLX_MODEL_GGUF": "$PULSARMLX_MODEL_GGUF",
            "PULSARMLX_ROUTER_EVIDENCE": "$PULSARMLX_ROUTER_EVIDENCE",
        },
        "interference_admission": "admitted",
        "admission_reasons": [],
        "observations": observations,
    }


def valid_environment(candidate):
    resources = environment.extract_benchmark_resources(candidate)
    return environment.combine_environment_evidence(
        before_snapshot=_snapshot(phase="before"),
        after_snapshot=_snapshot(phase="after"),
        after_unavailable_reason=None,
        benchmark_resources=resources,
    )


class GeneratedCandidateValidationTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.candidate = valid_candidate()
        self.environment = valid_environment(self.candidate)

    def validate(self, candidate=None, environment_value=None):
        return validator.validate_generated_candidate(
            self.candidate if candidate is None else candidate,
            self.environment if environment_value is None else environment_value,
        )

    def test_valid_candidate_reproduces_closed_groups_and_type7_statistics(self):
        report = self.validate()
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["stage_sum_claimed"])
        self.assertTrue(report["independent_golden_comparison"]["passed"])
        self.assertEqual(
            [group["summary"]["sample_count"] for group in report["timing_groups"]],
            [5, 30],
        )
        measured = report["timing_groups"][1]
        self.assertEqual(
            measured["summary"],
            validator.summarize_nanoseconds(range(1005, 1035)),
        )
        self.assertEqual(
            measured["group"]["observation_kind"], "measurement"
        )

    def test_validation_is_deterministic(self):
        self.assertEqual(self.validate(), self.validate())

    def test_unavailable_power_mode_is_retained_in_canonical_grouping(self):
        unavailable = environment.unavailable(
            "the active power mode was not exposed by pmset",
            "pmset_live_lowpowermode",
        )
        before = _snapshot(phase="before")
        after = _snapshot(phase="after")
        before["observations"]["power_mode"] = unavailable
        after["observations"]["power_mode"] = deepcopy(unavailable)
        resources = environment.extract_benchmark_resources(self.candidate)
        combined = environment.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after,
            after_unavailable_reason=None,
            benchmark_resources=resources,
        )
        report = self.validate(environment_value=combined)
        for group in report["timing_groups"]:
            self.assertEqual(
                group["group"]["power_mode"],
                [
                    "unavailable",
                    "the active power mode was not exposed by pmset",
                    "pmset_live_lowpowermode",
                ],
            )

    def test_closed_objects_reject_unknown_fields(self):
        mutations = []
        root = deepcopy(self.candidate)
        root["unexpected"] = True
        mutations.append(root)
        benchmark = deepcopy(self.candidate)
        benchmark["generated_router_microbenchmark"]["unexpected"] = True
        mutations.append(benchmark)
        output = deepcopy(self.candidate)
        output["generated_router_microbenchmark"]["canonical_output"]["unexpected"] = True
        mutations.append(output)
        observation = deepcopy(self.candidate)
        observation["generated_router_microbenchmark"]["timing_series"][
            "raw_timing_observations"
        ][0]["unexpected"] = True
        mutations.append(observation)
        for candidate in mutations:
            with self.subTest(index=mutations.index(candidate)):
                with self.assertRaises(validator.CandidateValidationError) as captured:
                    self.validate(candidate)
                self.assertEqual(captured.exception.code, "schema_violation")

    def test_manifest_and_inventory_mutations_are_rejected(self):
        mutations = []
        changed_hash = deepcopy(self.candidate)
        changed_hash["manifest_sha256"] = "0" * 64
        mutations.append(changed_hash)
        reordered = deepcopy(self.candidate)
        reordered["manifest_files"][0], reordered["manifest_files"][1] = (
            reordered["manifest_files"][1],
            reordered["manifest_files"][0],
        )
        mutations.append(reordered)
        changed_file_hash = deepcopy(self.candidate)
        changed_file_hash["manifest_files"][0]["sha256"] = "0" * 64
        mutations.append(changed_file_hash)
        for candidate in mutations:
            with self.assertRaises(validator.CandidateValidationError) as captured:
                self.validate(candidate)
            self.assertEqual(captured.exception.code, "manifest_mismatch")

    def test_actual_output_values_and_hashes_are_independently_bound(self):
        output = deepcopy(self.candidate)
        output["generated_router_microbenchmark"]["canonical_output"]["logits"][0] += 1.0
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(output)
        self.assertEqual(captured.exception.code, "golden_mismatch")

        forged_metric = deepcopy(self.candidate)
        forged_metric["positive_cases"][0]["comparison"]["logits"][
            "maximum_absolute_error"
        ] = 1.0e-12
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(forged_metric)
        self.assertEqual(captured.exception.code, "golden_mismatch")

    def test_golden_declared_hash_mutation_is_detected_by_recomputation(self):
        golden = _load("fixtures/research/router-v1/golden/expected_results.json")
        golden["cases"][validator.GOLDEN_CASE_ID]["hashes"][
            "logits_f32le_sha256"
        ] = "0" * 64
        with self.assertRaises(validator.CandidateValidationError) as captured:
            validator._validate_golden_document(golden)
        self.assertEqual(captured.exception.code, "golden_mismatch")

    def test_fixed_5_plus_30_order_and_stage_contract_are_enforced(self):
        missing = deepcopy(self.candidate)
        missing["generated_router_microbenchmark"]["timing_series"][
            "raw_timing_observations"
        ].pop()
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(missing)
        self.assertEqual(captured.exception.code, "timing_contract")

        reordered = deepcopy(self.candidate)
        observations = reordered["generated_router_microbenchmark"]["timing_series"][
            "raw_timing_observations"
        ]
        observations[0], observations[1] = observations[1], observations[0]
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(reordered)
        self.assertEqual(captured.exception.code, "timing_contract")

        extra_stage = deepcopy(self.candidate)
        extra_stage["generated_router_microbenchmark"]["timing_series"][
            "raw_timing_observations"
        ][0]["stages"]["router_projection"] = {
            "status": "observed",
            "duration_ns": 1,
        }
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(extra_stage)
        self.assertEqual(captured.exception.code, "schema_violation")

    def test_no_stage_sum_claim_is_structural(self):
        candidate = deepcopy(self.candidate)
        candidate["generated_router_microbenchmark"]["stage_sum_claimed"] = True
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(candidate)
        self.assertEqual(captured.exception.code, "candidate_not_passed")

    def test_result_records_are_a_bijection_with_timing_observations(self):
        missing = deepcopy(self.candidate)
        missing["generated_router_microbenchmark"]["result_records"].pop()
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(missing)
        self.assertEqual(captured.exception.code, "timing_contract")

        duplicate = deepcopy(self.candidate)
        records = duplicate["generated_router_microbenchmark"]["result_records"]
        records[1]["observation_id"] = records[0]["observation_id"]
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(duplicate)
        self.assertEqual(captured.exception.code, "result_bijection")

        wrong_hash = deepcopy(self.candidate)
        wrong_hash["generated_router_microbenchmark"]["result_records"][0][
            "output_sha256"
        ] = "0" * 64
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(wrong_hash)
        self.assertEqual(captured.exception.code, "result_bijection")

    def test_failure_state_and_resource_provenance_are_consistent(self):
        failed = deepcopy(self.candidate)
        failed["passed"] = False
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(failed)
        self.assertEqual(captured.exception.code, "candidate_not_passed")

        fallback = deepcopy(self.candidate)
        fallback["generated_router_microbenchmark"]["result_records"][0][
            "fallback_used"
        ] = True
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(fallback)
        self.assertEqual(captured.exception.code, "result_bijection")

        stale_environment = deepcopy(self.environment)
        stale_environment["benchmark_resources"]["mlx_peak_memory_bytes"]["value"] += 1
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(environment_value=stale_environment)
        self.assertEqual(captured.exception.code, "resource_mismatch")

    def test_private_values_and_duplicate_json_fail_closed(self):
        private = deepcopy(self.candidate)
        private["warnings"][0] = "/" + "Users/private-user/candidate.json"
        with self.assertRaises(validator.CandidateValidationError) as captured:
            self.validate(private)
        self.assertEqual(captured.exception.code, "private_value")

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidate.json"
            path.write_text('{"status":"passed","status":"failed"}', encoding="utf-8")
            with self.assertRaises(validator.CandidateValidationError) as captured:
                validator._load_external_json(
                    path,
                    maximum_bytes=validator.MAX_CANDIDATE_BYTES,
                    label="generated router candidate",
                )
            self.assertEqual(captured.exception.code, "invalid_json")

    def test_committed_candidate_schema_is_closed_and_synchronized(self):
        validator._validate_contract_schema(REPOSITORY_ROOT)
        schema = _load("schemas/research/v1/router-fixture-candidate.schema.json")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), validator.ROOT_FIELDS)
        self.assertEqual(set(schema["properties"]), validator.ROOT_FIELDS)
        self.assertFalse(schema["$defs"]["benchmark"]["additionalProperties"])
        self.assertFalse(schema["$defs"]["canonicalOutput"]["additionalProperties"])


if __name__ == "__main__":
    unittest.main()

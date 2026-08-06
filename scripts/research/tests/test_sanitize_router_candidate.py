"""Model-free contracts for the real-router candidate sanitizer."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from scripts.research.tests import test_environment as environment_fixtures


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "sanitize_router_candidate.py"
_SPEC = importlib.util.spec_from_file_location("pulsarmlx_router_sanitizer_tested", MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("router candidate sanitizer could not be loaded")
sanitizer = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sanitizer
_SPEC.loader.exec_module(sanitizer)
validator = sanitizer.validator
environment = sanitizer.environment_tools


SOURCE_COMMIT = "a" * 40
FAILURE = {
    "code": "internal_worker_error",
    "message": "the worker did not start",
    "stage": "worker_startup",
}


def _model_and_tensor() -> tuple[dict[str, object], dict[str, object]]:
    model = validator._load_model_identity(REPOSITORY_ROOT)
    manifest = validator._load_model_manifest(REPOSITORY_ROOT)
    tensor = manifest["router_tensor_admission"]["observed"]
    return model, tensor


def _abort_candidate() -> dict[str, object]:
    model, tensor = _model_and_tensor()
    publication = validator._load_real_oracle_publication(REPOSITORY_ROOT)
    observation_id = "batch-a-qwen3moe-abort-correctness-warmup-00"
    case_id = sanitizer.SINGLE_CASE
    process_id = "batch-a-correctness-worker"
    started = "2026-08-06T04:05:04Z"
    completed = "2026-08-06T04:05:07Z"
    ledger = {
        "global_order_index": 0,
        "observation_id": observation_id,
        "case_id": case_id,
        "batch_id": "batch-a",
        "process_replication_id": process_id,
        "process_state": "reused_process",
        "condition": "warm",
        "schedule_step": "single_row_correctness",
        "source_kind": "correctness_attempt",
        "observation_kind": "warmup",
        "run_index": 0,
        "status": "aborted",
        "orchestration_status": "rejected",
        "timing_profile": "minimal",
        "started_at_utc": started,
        "completed_at_utc": completed,
        "host_wall_duration_ns": 1_000,
        "host_monotonic_clock": "rust_std_instant",
        "process_request_index": None,
        "router_tensor_bytes_read": None,
        "router_tensor_cache_status": None,
        "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
    }
    attempt = {
        "attempt_id": observation_id,
        "attempt_index": 0,
        "observation_kind": "warmup",
        "run_index": 0,
        "batch_id": "batch-a",
        "case_id": case_id,
        "process_replication_id": process_id,
        "process_state": "reused_process",
        "condition": "warm",
        "schedule_step": "single_row_correctness",
        "requested_device": "gpu",
        "selected_device": "not_available",
        "fallback_used": False,
        "evaluated": False,
        "synchronized": False,
        "memory_gauges": None,
        "complete_output_sha256": None,
        "canonical_output": None,
        "comparison": None,
        "status": "aborted",
        "passed": False,
        "failure": FAILURE,
    }
    lifecycle = [
        {
            "event_order": 0,
            "recorded_at_utc": "2026-08-06T04:05:05Z",
            "process_replication_id": process_id,
            "timing_profile": "minimal",
            "event": "spawn",
            "outcome": "started",
            "details": {"model_transport": "inherited_read_only_fd_198"},
        },
        {
            "event_order": 1,
            "recorded_at_utc": "2026-08-06T04:05:06Z",
            "process_replication_id": process_id,
            "timing_profile": "minimal",
            "event": "spawn",
            "outcome": "failed",
            "details": {"failure": FAILURE},
        },
    ]
    window = {
        "observation_id": observation_id,
        "batch_id": "batch-a",
        "case_id": case_id,
        "schedule_step": "single_row_correctness",
        "source_kind": "correctness_attempt",
        "process_replication_id": process_id,
        "process_state": "reused_process",
        "condition": "warm",
        "timing_profile": "minimal",
        "started_at_utc": started,
        "completed_at_utc": completed,
        "host_wall_duration_ns": 1_000,
        "host_monotonic_clock": "rust_std_instant",
        "request_sent": False,
        "process_request_index": None,
        "router_tensor_bytes_read": None,
        "router_tensor_cache_status": None,
        "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
        "status": "aborted",
        "failure": FAILURE,
        "timestamp_observation": "failed_after_spawn_before_request",
    }
    resource = {
        "observation_id": observation_id,
        "source_kind": "correctness_attempt",
        "process_state": "reused_process",
        "condition": "warm",
        "backend": "apple-mlx",
        "requested_device": "gpu",
        "selected_device": "not_available",
        "fallback_used": False,
        "evaluated": False,
        "synchronized": False,
        "output_sha256": None,
        "correctness_passed": None,
        "canonical_output": None,
        "canonical_output_retention": "unavailable_aborted_request",
        "router_tensor_bytes_read": None,
        "router_tensor_cache_status": None,
        "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
        "memory_gauges": None,
        "monotonic_clock": None,
        "instrumentation_mode": "minimally_instrumented",
        "timing_stages": None,
        "timing_stage_retention": "unavailable_aborted_request",
        "status": "aborted",
        "failure": FAILURE,
    }
    return {
        "schema_version": 1,
        "candidate_kind": "qwen3moe-router-internal-orchestration",
        "candidate_status": "failed",
        "publication_status": "external_unvalidated_candidate",
        "started_at_utc": started,
        "completed_at_utc": completed,
        "experiment_wall_duration_ns": 3_000,
        "source_commit": SOURCE_COMMIT,
        "source_worktree_before": "clean",
        "source_worktree_after": "clean",
        "parent_invocation": {
            "operation": "validate-router",
            "argv": list(sanitizer.EXPECTED_PARENT_ARGV),
        },
        "backend": "apple-mlx",
        "requested_device": "gpu",
        "artifact": {
            "repository_id": model["repository"],
            "revision": model["revision"],
            "filename": model["filename"],
            "size_bytes": model["size_bytes"],
            "sha256": model["sha256"],
            "location_symbolic": f"<external-model>/{model['filename']}",
            "read_only": True,
            "automatic_download": False,
        },
        "router_tensor": {
            "name": tensor["name"],
            "absolute_data_offset": tensor["absolute_offset"],
            "encoded_length_bytes": tensor["encoded_length_bytes"],
            "exclusive_end_offset": tensor["exclusive_end_offset"],
            "encoded_sha256": tensor["encoded_sha256"],
            "reader_shape": tensor["reader_shape"],
            "execution_shape": tensor["execution_shape"],
            "gguf_type": tensor["gguf_type"],
            "quantization": tensor["quantization"],
            "expert_count": tensor["expert_count"],
            "top_k": tensor["selected_expert_count"],
            "weight_scale": tensor["weight_scale"],
            "bias_present": tensor["bias_present"],
            "correction_bias_present": tensor["correction_bias_present"],
            "selected_probability_renormalization": tensor[
                "selected_probability_renormalization"
            ],
        },
        "oracle": {
            "oracle_id": validator.REAL_ORACLE_ID,
            "external_document_sha256": sanitizer.EXTERNAL_ORACLE_SHA256,
            "public_projection_sha256": validator.REAL_ORACLE_PUBLICATION_SHA256,
            "input_f32le_sha256": publication["input"]["canonical_f32le_sha256"],
            "output_bundle_sha256": publication["result"]["hashes"][
                "output_bundle_sha256"
            ],
            "worker_control_request_included_hidden_values": False,
            "worker_loaded_committed_hidden_input": True,
            "worker_received_oracle_outputs": False,
        },
        "immutable_rechecks": {
            "full_model_sha256": True,
            "exact_router_range_sha256": True,
            "oracle_whole_file_sha256": True,
            "path_identity": True,
            "source_commit_and_cleanliness": True,
        },
        "host_resource_observations": {
            "collector_wall_duration_ns": {"status": "observed", "value": 3_000},
            "collector_process_cpu_time_seconds": {
                "status": "unavailable",
                "reason": "the bounded Rust command does not expose reliable combined parent-and-live-child CPU time",
                "source": "rust_std_process_boundary",
            },
        },
        "worker": {
            "runtime": None,
            "worker_lifecycle": lifecycle,
            "request_utc_windows": [window],
            "timestamp_join_contract": {
                "join_key": "observation_id",
                "relationship": "exactly_one_request_window_and_one_resource_record_per_ordered_observation",
                "validated": True,
            },
            "result_resource_records": [resource],
            "attempted_timing_observation_count": 0,
            "active_process_count_at_serialization": 0,
            "completed_process_count": 1,
            "max_active_process_count_observed": 0,
            "benchmark_concurrency": 1,
        },
        "orchestration": {
            "schema_version": 1,
            "orchestration": "qwen3moe-router-frozen-schedule",
            "status": "failed",
            "batch_id": "batch-a",
            "order": "single_row_first",
            "stage": "worker_startup",
            "failure": FAILURE,
            "order_seed": 22_002,
            "raw_observations": [ledger],
            "completed_correctness_gates": [],
            "retained_current_case_attempts": [attempt],
            "retained_timing": {
                "first_process_series": [],
                "costly_series": [],
                "major_series": [],
                "stage_diagnostic_series": [],
                "rejected_series": [],
            },
            "second_batch": None,
            "first_process_observation_started": False,
            "timing_started": False,
            "passed": False,
        },
        "unsupported_interpretations": list(
            sanitizer.INTERNAL_UNSUPPORTED_INTERPRETATIONS
        ),
    }


def _sent_request_abort_candidate() -> dict[str, object]:
    """Build a worker-owned request that aborts before MLX evaluation."""

    candidate = _abort_candidate()
    failure = {
        "code": "internal_worker_error",
        "message": "the worker closed after receiving the request",
        "stage": "live_adapter",
    }
    worker = candidate["worker"]
    orchestration = candidate["orchestration"]
    ledger = orchestration["raw_observations"][0]
    attempt = orchestration["retained_current_case_attempts"][0]
    window = worker["request_utc_windows"][0]
    resource = worker["result_resource_records"][0]

    for failed_record in (attempt, window, resource):
        failed_record["failure"] = deepcopy(failure)
    ledger["process_request_index"] = 0
    window.update({
        "request_sent": True,
        "process_request_index": 0,
        "timestamp_observation": "observed",
    })
    worker.update({
        "runtime": _runtime_identity(),
        "max_active_process_count_observed": 1,
        "worker_lifecycle": [
            {
                "event_order": 0,
                "recorded_at_utc": "2026-08-06T04:05:03Z",
                "process_replication_id": attempt["process_replication_id"],
                "timing_profile": "minimal",
                "event": "spawn",
                "outcome": "started",
                "details": {"model_transport": "inherited_read_only_fd_198"},
            },
            {
                "event_order": 1,
                "recorded_at_utc": "2026-08-06T04:05:04Z",
                "process_replication_id": attempt["process_replication_id"],
                "timing_profile": "minimal",
                "event": "spawn",
                "outcome": "passed",
                "details": _runtime_identity(),
            },
            {
                "event_order": 2,
                "recorded_at_utc": "2026-08-06T04:05:08Z",
                "process_replication_id": attempt["process_replication_id"],
                "timing_profile": "minimal",
                "event": "shutdown",
                "outcome": "graceful",
                "details": {
                    "outcome": "graceful",
                    "exit_code": 0,
                    "error_code": None,
                },
            },
        ],
    })
    orchestration.update({"stage": "live_adapter", "failure": failure})
    return candidate


def _combined_environment(candidate: dict[str, object]) -> dict[str, object]:
    before = environment_fixtures._collect()
    after = environment_fixtures._collect(capture_phase="after")
    resources = environment.extract_benchmark_resources(candidate)
    return environment.combine_environment_evidence(
        before_snapshot=before,
        after_snapshot=after,
        after_unavailable_reason=None,
        benchmark_resources=resources,
    )


GAUGES = {
    "mlx_active_bytes": 10_000,
    "mlx_cache_bytes": 2_000,
    "mlx_peak_bytes": 12_000,
    "process_footprint_bytes": 20_000,
    "process_footprint_source": "task_vm_info",
    "system_pressure": "normal",
    "reported_summed_total_bytes": None,
}


def _runtime_identity() -> dict[str, object]:
    return {
        "protocol": 1,
        "worker_version": "0.1.0",
        "python_version": platform.python_version(),
        "python_architecture": "arm64",
        "mlx_version": "0.32.0",
        "macos_version": "26.0",
        "metal_available": True,
        "gpu_count": 1,
    }


def _timing_stages(mode: str, duration: int) -> dict[str, object]:
    stages: dict[str, object] = {
        "dequantization": {
            "status": "not_applicable",
            "reason": sanitizer.F32_DEQUANTIZATION_REASON,
        },
        "total_evaluated_router": {"status": "observed", "duration_ns": duration},
    }
    if mode == "stage_instrumented":
        for stage in validator.ROUTER_TIMING_STAGES:
            if stage not in stages:
                stages[stage] = {"status": "observed", "duration_ns": duration + 1}
    return stages


def _passing_attempt(
    *, batch_id: str, case_id: str, index: int, output: dict[str, object]
) -> dict[str, object]:
    observation_kind = "warmup" if index < 5 else "measurement"
    run_index = index if index < 5 else index - 5
    return {
        "backend": "apple-mlx",
        "attempt_id": (
            f"{batch_id}-{case_id}-correctness-{observation_kind}-{run_index:02}"
        ),
        "attempt_index": index,
        "observation_kind": observation_kind,
        "run_index": run_index,
        "case_id": case_id,
        "process_replication_id": f"{batch_id}-correctness-worker",
        "process_state": "reused_process",
        "condition": "warm",
        "logits_f32le_sha256": output["logits_f32le_sha256"],
        "full_probabilities_f32le_sha256": output[
            "full_probabilities_f32le_sha256"
        ],
        "selected_expert_ids": output["selected_expert_ids"],
        "selected_expert_ids_u32le_sha256": output[
            "selected_expert_ids_u32le_sha256"
        ],
        "selected_probabilities_f32le_sha256": output[
            "selected_probabilities_f32le_sha256"
        ],
        "normalized_weights_f32le_sha256": output[
            "normalized_weights_f32le_sha256"
        ],
        "complete_output_sha256": output["complete_output_sha256"],
        "canonical_output": deepcopy(output),
        "comparison": sanitizer._recompute_output_comparison(output, output),
        "memory_gauges": deepcopy(GAUGES),
        "result_passed": True,
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
        "status": "passed",
        "failure": None,
        "passed": True,
    }


def _passing_candidate() -> dict[str, object]:
    candidate = _abort_candidate()
    oracle_outputs = validator._load_real_oracle_outputs(REPOSITORY_ROOT)
    all_windows: list[dict[str, object]] = []
    all_resources: list[dict[str, object]] = []
    all_lifecycles: list[dict[str, object]] = []
    all_batches: list[dict[str, object]] = []

    def cache_pair(
        process_counts: dict[str, int], process_id: str, *, force_read: bool
    ) -> tuple[int, str, int]:
        request_index = process_counts.get(process_id, 0)
        process_counts[process_id] = request_index + 1
        if force_read or request_index == 0:
            return 1_048_576, "read_and_cached", request_index
        return 0, "cache_hit", request_index

    for batch_id, batch_order in (
        ("batch-a", "single_row_first"),
        ("batch-b", "two_row_first"),
    ):
        ledger: list[dict[str, object]] = []
        gates: list[dict[str, object]] = []
        first_process_series: list[dict[str, object]] = []
        costly_series: list[dict[str, object]] = []
        major_series: list[dict[str, object]] = []
        stage_series: list[dict[str, object]] = []
        process_counts: dict[str, int] = {}
        process_profiles: dict[str, str] = {}

        def append_live(
            *,
            observation_id: str,
            case_id: str,
            process_id: str,
            process_state: str,
            condition: str,
            schedule_step: str,
            source_kind: str,
            observation_kind: str,
            run_index: int,
            timing_profile: str,
            instrumentation_mode: str,
            output: dict[str, object],
            stages: dict[str, object],
            force_read: bool,
        ) -> None:
            bytes_read, cache_status, process_request_index = cache_pair(
                process_counts, process_id, force_read=force_read
            )
            process_profiles.setdefault(process_id, timing_profile)
            common = {
                "observation_id": observation_id,
                "batch_id": batch_id,
                "case_id": case_id,
                "schedule_step": schedule_step,
                "source_kind": source_kind,
                "process_replication_id": process_id,
                "timing_profile": timing_profile,
                "started_at_utc": "2026-08-06T04:05:06Z",
                "completed_at_utc": "2026-08-06T04:05:06Z",
                "host_wall_duration_ns": 2_000 + len(ledger),
                "host_monotonic_clock": "rust_std_instant",
                "process_request_index": process_request_index,
                "router_tensor_bytes_read": bytes_read,
                "router_tensor_cache_status": cache_status,
                "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
                "status": "passed",
            }
            all_windows.append({
                **common,
                "process_state": process_state,
                "condition": condition,
                "request_sent": True,
                "failure": None,
                "timestamp_observation": "observed",
            })
            all_resources.append({
                "observation_id": observation_id,
                "source_kind": source_kind,
                "process_state": process_state,
                "condition": condition,
                "backend": "apple-mlx",
                "requested_device": "gpu",
                "selected_device": "gpu",
                "fallback_used": False,
                "evaluated": True,
                "synchronized": True,
                "output_sha256": output["complete_output_sha256"],
                "correctness_passed": True,
                "canonical_output": None,
                "canonical_output_retention": (
                    "hash_only_joined_correctness_attempt"
                    if source_kind == "correctness_attempt"
                    else "hash_only_passing_timing"
                ),
                "router_tensor_bytes_read": bytes_read,
                "router_tensor_cache_status": cache_status,
                "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
                "memory_gauges": deepcopy(GAUGES),
                "monotonic_clock": "perf_counter_ns",
                "instrumentation_mode": instrumentation_mode,
                "timing_stages": stages if source_kind == "correctness_attempt" else None,
                "timing_stage_retention": (
                    "complete_in_resource_record"
                    if source_kind == "correctness_attempt"
                    else "complete_in_joined_raw_timing_observation"
                ),
                "status": "passed",
                "failure": None,
            })
            ledger.append({
                "global_order_index": len(ledger),
                **common,
                "process_state": process_state,
                "condition": condition,
                "observation_kind": observation_kind,
                "run_index": run_index,
                "orchestration_status": "accepted",
            })

        case_order = (
            [sanitizer.SINGLE_CASE, sanitizer.TWO_ROW_CASE]
            if batch_order == "single_row_first"
            else [sanitizer.TWO_ROW_CASE, sanitizer.SINGLE_CASE]
        )
        for case_id in case_order:
            attempts: list[dict[str, object]] = []
            output = oracle_outputs[case_id]
            for index in range(15):
                attempt = _passing_attempt(
                    batch_id=batch_id, case_id=case_id, index=index, output=output
                )
                attempts.append(attempt)
                append_live(
                    observation_id=attempt["attempt_id"],
                    case_id=case_id,
                    process_id=attempt["process_replication_id"],
                    process_state="reused_process",
                    condition="warm",
                    schedule_step=(
                        "single_row_correctness"
                        if case_id == sanitizer.SINGLE_CASE
                        else "two_row_correctness"
                    ),
                    source_kind="correctness_attempt",
                    observation_kind=attempt["observation_kind"],
                    run_index=attempt["run_index"],
                    timing_profile="minimal",
                    instrumentation_mode="minimally_instrumented",
                    output=output,
                    stages=_timing_stages("minimally_instrumented", 1_000 + index),
                    force_read=False,
                )
            gates.append({
                "batch_id": batch_id,
                "case_id": case_id,
                "attempt_count": 15,
                "warmup_count": 5,
                "measurement_count": 10,
                "complete_output_sha256": output["complete_output_sha256"],
                "canonical_output": deepcopy(output),
                "requested_device": "gpu",
                "selected_device": "gpu",
                "fallback_used": False,
                "evaluated": True,
                "synchronized": True,
                "comparison_passed": True,
                "passed": True,
                "attempts": attempts,
            })

        plan = validator._expected_passing_timing_plan(batch_id, batch_order)
        for series_index, planned in enumerate(plan):
            output = oracle_outputs[planned["case_id"]]
            raw_observations: list[dict[str, object]] = []
            count = planned["warmup_count"] + planned["measurement_count"]
            force_read = planned["series_kind"] in {
                "costly_real", "first_process_costly"
            }
            for position in range(count):
                kind = "warmup" if position < planned["warmup_count"] else "measurement"
                run_index = (
                    position if kind == "warmup" else position - planned["warmup_count"]
                )
                observation_id = (
                    f"{batch_id}-timing-{series_index:02}-{kind}-{run_index:02}"
                )
                stages = _timing_stages(
                    planned["instrumentation_mode"],
                    10_000 + series_index * 100 + position,
                )
                timing_profile = (
                    "costly" if planned["series_kind"] in {
                        "costly_real", "first_process_costly"
                    } else "stage" if planned["series_kind"] == "stage_diagnostic"
                    else "minimal"
                )
                append_live(
                    observation_id=observation_id,
                    case_id=planned["case_id"],
                    process_id=planned["process_replication_id"],
                    process_state=planned["process_state"],
                    condition=planned["condition"],
                    schedule_step=planned["schedule_step"],
                    source_kind="timing_series",
                    observation_kind=kind,
                    run_index=run_index,
                    timing_profile=timing_profile,
                    instrumentation_mode=planned["instrumentation_mode"],
                    output=output,
                    stages=stages,
                    force_read=force_read,
                )
                raw_observations.append({
                    "observation_id": observation_id,
                    "run_index": run_index,
                    "observation_kind": kind,
                    "process_replication_id": planned["process_replication_id"],
                    "process_state": planned["process_state"],
                    "condition": planned["condition"],
                    "instrumentation_mode": planned["instrumentation_mode"],
                    "monotonic_clock": "perf_counter_ns",
                    "stages": stages,
                    "status": "passed",
                    "requested_device": "gpu",
                    "selected_device": "gpu",
                    "fallback_used": False,
                    "evaluated": True,
                    "synchronized": True,
                    "output_sha256": output["complete_output_sha256"],
                    "correctness_passed": True,
                    "timing_profile": timing_profile,
                    "started_at_utc": "2026-08-06T04:05:06Z",
                    "completed_at_utc": "2026-08-06T04:05:06Z",
                    "host_wall_duration_ns": all_windows[-1][
                        "host_wall_duration_ns"
                    ],
                    "router_tensor_bytes_read": all_resources[-1][
                        "router_tensor_bytes_read"
                    ],
                    "router_tensor_cache_status": all_resources[-1][
                        "router_tensor_cache_status"
                    ],
                })
            series = {
                "benchmark_id": planned["benchmark_id"],
                "case_id": planned["case_id"],
                "row_count": 1 if planned["case_id"] == sanitizer.SINGLE_CASE else 2,
                "series_kind": planned["series_kind"],
                "replication_role": planned["replication_role"],
                "process_replication_id": planned["process_replication_id"],
                "process_state": planned["process_state"],
                "condition": planned["condition"],
                "instrumentation_mode": planned["instrumentation_mode"],
                "warmup_count": planned["warmup_count"],
                "measurement_count": planned["measurement_count"],
                "raw_timing_observations": raw_observations,
            }
            if planned["series_kind"] == "first_process_costly":
                first_process_series.append(series)
            elif planned["series_kind"] == "costly_real":
                costly_series.append(series)
            elif planned["series_kind"] == "stage_diagnostic":
                stage_series.append(series)
            else:
                major_series.append(series)

        for process_id, profile in process_profiles.items():
            for event, outcome in (
                ("spawn", "started"), ("spawn", "passed"), ("shutdown", "graceful")
            ):
                details = (
                    {"model_transport": "inherited_read_only_fd_198"}
                    if (event, outcome) == ("spawn", "started") else
                    _runtime_identity()
                    if (event, outcome) == ("spawn", "passed") else
                    {"outcome": "graceful", "exit_code": 0, "error_code": None}
                )
                all_lifecycles.append({
                    "event_order": len(all_lifecycles),
                    "recorded_at_utc": "2026-08-06T04:05:06Z",
                    "process_replication_id": process_id,
                    "timing_profile": profile,
                    "event": event,
                    "outcome": outcome,
                    "details": details,
                })
        self_batch = {
            "batch_id": batch_id,
            "raw_observations": ledger,
            "correctness_gates": gates,
            "first_process_series": first_process_series,
            "costly_series": costly_series,
            "major_series": major_series,
            "stage_diagnostic_series": stage_series,
        }
        all_batches.append(self_batch)

    candidate.update({
        "candidate_status": "passed",
        "started_at_utc": "2026-08-06T04:05:06Z",
        "completed_at_utc": "2026-08-06T04:05:06Z",
        "worker": {
            "runtime": _runtime_identity(),
            "worker_lifecycle": all_lifecycles,
            "request_utc_windows": all_windows,
            "timestamp_join_contract": {
                "join_key": "observation_id",
                "relationship": "exactly_one_request_window_and_one_resource_record_per_ordered_observation",
                "validated": True,
            },
            "result_resource_records": all_resources,
            "attempted_timing_observation_count": 460,
            "active_process_count_at_serialization": 0,
            "completed_process_count": len({
                item["process_replication_id"] for item in all_lifecycles
            }),
            "max_active_process_count_observed": 1,
            "benchmark_concurrency": 1,
        },
        "orchestration": {
            "schema_version": 1,
            "orchestration": "qwen3moe-router-frozen-schedule",
            "status": "passed",
            "order_seed": 22_002,
            "correctness_gates": all_batches[0]["correctness_gates"],
            "primary_batch": {
                "order": "single_row_before_two_row_within_each_major_pair",
                **{
                key: value for key, value in all_batches[0].items()
                if key != "correctness_gates"
                },
            },
            "second_batch": {
                "status": "recorded",
                "batch_id": "batch-b",
                "order": "two_row_before_single_row_within_each_major_pair",
                "raw_observations": all_batches[1]["raw_observations"],
                "between_batch_variation_measured": True,
                "first_process_series": all_batches[1]["first_process_series"],
                "correctness_gates": all_batches[1]["correctness_gates"],
                "costly_series": all_batches[1]["costly_series"],
                "major_series": all_batches[1]["major_series"],
                "stage_diagnostic_series": all_batches[1]["stage_diagnostic_series"],
            },
        },
    })
    return candidate


def _evaluated_failure_candidate(*, retain_output: bool) -> dict[str, object]:
    candidate = _abort_candidate()
    output = validator._load_real_oracle_outputs(REPOSITORY_ROOT)[sanitizer.SINGLE_CASE]
    attempt = _passing_attempt(
        batch_id="batch-a",
        case_id=sanitizer.SINGLE_CASE,
        index=0,
        output=output,
    )
    failure = {
        "code": "comparison_failed",
        "message": "the evaluated correctness attempt did not complete its gate",
        "stage": "correctness_gate",
    }
    attempt.update({"status": "failed", "passed": False, "failure": failure})
    if retain_output:
        attempt["result_passed"] = False
    else:
        for field in (
            "backend", "logits_f32le_sha256", "full_probabilities_f32le_sha256",
            "selected_expert_ids", "selected_expert_ids_u32le_sha256",
            "selected_probabilities_f32le_sha256", "normalized_weights_f32le_sha256",
            "result_passed",
        ):
            attempt.pop(field, None)
        attempt.update({
            "batch_id": "batch-a",
            "schedule_step": "single_row_correctness",
            "complete_output_sha256": None,
            "canonical_output": None,
            "comparison": None,
        })

    observation_id = attempt["attempt_id"]
    process_id = attempt["process_replication_id"]
    started = "2026-08-06T04:05:04Z"
    completed = "2026-08-06T04:05:07Z"
    output_sha256 = output["complete_output_sha256"]
    ledger = {
        "global_order_index": 0,
        "observation_id": observation_id,
        "case_id": sanitizer.SINGLE_CASE,
        "batch_id": "batch-a",
        "process_replication_id": process_id,
        "process_state": "reused_process",
        "condition": "warm",
        "schedule_step": "single_row_correctness",
        "source_kind": "correctness_attempt",
        "observation_kind": "warmup",
        "run_index": 0,
        "status": "failed",
        "orchestration_status": "rejected",
        "timing_profile": "minimal",
        "started_at_utc": started,
        "completed_at_utc": completed,
        "host_wall_duration_ns": 1_000,
        "host_monotonic_clock": "rust_std_instant",
        "process_request_index": 0,
        "router_tensor_bytes_read": 1_048_576,
        "router_tensor_cache_status": "read_and_cached",
        "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
    }
    window = {
        "observation_id": observation_id,
        "batch_id": "batch-a",
        "case_id": sanitizer.SINGLE_CASE,
        "schedule_step": "single_row_correctness",
        "source_kind": "correctness_attempt",
        "process_replication_id": process_id,
        "process_state": "reused_process",
        "condition": "warm",
        "timing_profile": "minimal",
        "started_at_utc": started,
        "completed_at_utc": completed,
        "host_wall_duration_ns": 1_000,
        "host_monotonic_clock": "rust_std_instant",
        "request_sent": True,
        "process_request_index": 0,
        "router_tensor_bytes_read": 1_048_576,
        "router_tensor_cache_status": "read_and_cached",
        "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
        "status": "failed",
        "failure": failure,
        "timestamp_observation": "observed",
    }
    resource = {
        "observation_id": observation_id,
        "source_kind": "correctness_attempt",
        "process_state": "reused_process",
        "condition": "warm",
        "backend": "apple-mlx",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
        "output_sha256": output_sha256,
        "correctness_passed": False,
        "canonical_output": deepcopy(output) if retain_output else None,
        "canonical_output_retention": (
            "complete" if retain_output else "unavailable_invalid_output"
        ),
        "router_tensor_bytes_read": 1_048_576,
        "router_tensor_cache_status": "read_and_cached",
        "router_tensor_bytes_semantics": sanitizer.APPLICATION_READ_SEMANTICS,
        "memory_gauges": deepcopy(GAUGES),
        "monotonic_clock": "perf_counter_ns",
        "instrumentation_mode": "minimally_instrumented",
        "timing_stages": _timing_stages("minimally_instrumented", 900),
        "timing_stage_retention": "complete_in_resource_record",
        "status": "failed",
        "failure": failure,
    }
    lifecycle_times = (
        "2026-08-06T04:05:03Z",
        "2026-08-06T04:05:04Z",
        "2026-08-06T04:05:08Z",
    )
    lifecycle_plan = (
        (
            "spawn", "started",
            {"model_transport": "inherited_read_only_fd_198"},
        ),
        ("spawn", "passed", _runtime_identity()),
        (
            "shutdown", "graceful",
            {"outcome": "graceful", "exit_code": 0, "error_code": None},
        ),
    )
    lifecycle = [
        {
            "event_order": index,
            "recorded_at_utc": lifecycle_times[index],
            "process_replication_id": process_id,
            "timing_profile": "minimal",
            "event": event,
            "outcome": outcome,
            "details": details,
        }
        for index, (event, outcome, details) in enumerate(lifecycle_plan)
    ]
    candidate.update({
        "candidate_status": "failed",
        "started_at_utc": started,
        "completed_at_utc": completed,
        "worker": {
            "runtime": _runtime_identity(),
            "worker_lifecycle": lifecycle,
            "request_utc_windows": [window],
            "timestamp_join_contract": {
                "join_key": "observation_id",
                "relationship": "exactly_one_request_window_and_one_resource_record_per_ordered_observation",
                "validated": True,
            },
            "result_resource_records": [resource],
            "attempted_timing_observation_count": 0,
            "active_process_count_at_serialization": 0,
            "completed_process_count": 1,
            "max_active_process_count_observed": 1,
            "benchmark_concurrency": 1,
        },
        "orchestration": {
            "schema_version": 1,
            "orchestration": "qwen3moe-router-frozen-schedule",
            "status": "failed",
            "batch_id": "batch-a",
            "order": "single_row_first",
            "stage": "correctness_gate",
            "failure": failure,
            "order_seed": 22_002,
            "raw_observations": [ledger],
            "completed_correctness_gates": [],
            "retained_current_case_attempts": [attempt],
            "retained_timing": {
                "first_process_series": [],
                "costly_series": [],
                "major_series": [],
                "stage_diagnostic_series": [],
                "rejected_series": [],
            },
            "second_batch": None,
            "first_process_observation_started": False,
            "timing_started": False,
            "passed": False,
        },
    })
    return candidate


def _failed_later_batch_candidate() -> dict[str, object]:
    candidate = _passing_candidate()
    passed = candidate["orchestration"]
    primary = passed["primary_batch"]
    later = passed["second_batch"]
    failure = {
        "code": "model_checksum_mismatch",
        "message": "the later batch failed its post-request identity recheck",
        "stage": "immutable_recheck",
    }
    later_major = later["major_series"]
    candidate["candidate_status"] = "failed"
    candidate["orchestration"] = {
        "schema_version": 1,
        "orchestration": "qwen3moe-router-frozen-schedule",
        "status": "failed",
        "batch_id": primary["batch_id"],
        "order": "single_row_first",
        "stage": failure["stage"],
        "failure": failure,
        "order_seed": 22_002,
        "raw_observations": primary["raw_observations"],
        "completed_correctness_gates": passed["correctness_gates"],
        "retained_current_case_attempts": [],
        "retained_timing": {
            "first_process_series": primary["first_process_series"],
            "costly_series": primary["costly_series"],
            "major_series": primary["major_series"],
            "stage_diagnostic_series": primary["stage_diagnostic_series"],
            "rejected_series": [],
        },
        "second_batch": {
            "status": "failed",
            "batch_id": later["batch_id"],
            "retained_evidence": {
                "status": "complete_candidate",
                "batch_id": later["batch_id"],
                "order": "two_row_first",
                "next_step": "complete",
                "raw_observations": later["raw_observations"],
                "failure": None,
                "correctness_gates": later["correctness_gates"],
                "pending_correctness_attempts": [],
                "first_process_series": later["first_process_series"],
                "costly_series": later["costly_series"],
                "primary_major_series": [
                    item for item in later_major
                    if item["replication_role"] == "primary"
                ],
                "stage_diagnostic_series": later["stage_diagnostic_series"],
                "clean_major_series": [
                    item for item in later_major
                    if item["replication_role"] == "clean_process_replication"
                ],
                "rejected_timing_series": [],
            },
        },
        "first_process_observation_started": True,
        "timing_started": True,
        "passed": False,
    }
    return candidate


class SecureIntakeTests(unittest.TestCase):
    def test_exact_candidate_digest_includes_whitespace_and_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            compact = Path(temp).resolve() / "compact.json"
            pretty = Path(temp).resolve() / "pretty.json"
            compact_bytes = b'{"value":1}\n'
            pretty_bytes = b'{ "value": 1 }\n\n'
            compact.write_bytes(compact_bytes)
            pretty.write_bytes(pretty_bytes)
            compact_document = sanitizer._read_secure_json(compact, subject="candidate")
            pretty_document = sanitizer._read_secure_json(pretty, subject="candidate")
            self.assertEqual(
                compact_document.sha256, hashlib.sha256(compact_bytes).hexdigest()
            )
            self.assertEqual(
                pretty_document.sha256, hashlib.sha256(pretty_bytes).hexdigest()
            )
            self.assertNotEqual(compact_document.sha256, pretty_document.sha256)

    def test_duplicate_nonfinite_private_and_symlink_inputs_fail_closed(self) -> None:
        payloads = (
            b'{"value":1,"value":2}',
            b'{"value":NaN}',
            ('{"value":"/' + 'Users/private/model.gguf"}').encode(),
        )
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            for index, payload in enumerate(payloads):
                path = root / f"bad-{index}.json"
                path.write_bytes(payload)
                with self.subTest(index=index), self.assertRaises(
                    sanitizer.SanitizationError
                ):
                    sanitizer._read_secure_json(path, subject="candidate")
            target = root / "target.json"
            target.write_text('{"value":1}', encoding="utf-8")
            link = root / "link.json"
            os.symlink(target, link)
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer._read_secure_json(link, subject="candidate")

            hard_link = root / "hard-link.json"
            os.link(target, hard_link)
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer._read_secure_json(hard_link, subject="candidate")

            physical_parent = root / "physical-parent"
            physical_parent.mkdir()
            nested = physical_parent / "nested.json"
            nested.write_text('{"value":1}', encoding="utf-8")
            parent_link = root / "parent-link"
            os.symlink(physical_parent, parent_link)
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer._read_secure_json(
                    parent_link / "nested.json", subject="candidate"
                )

    def test_credential_shaped_free_text_and_fields_fail_closed(self) -> None:
        payloads = (
            {"message": "password=hunter2"},
            {"message": "Authorization: Bearer abcdefghijklmnop"},
            {"message": "Cookie=session-value"},
            {"message": "url?access_token=operatorprivate"},
            {"message": "github_token=operatorprivate"},
            {"message": "x|password=operatorprivate"},
            {"token": "secret-value"},
            {"github_token": "secret-value"},
            {"clientSecret": "secret-value"},
        )
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            for index, payload in enumerate(payloads):
                path = root / f"credential-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(
                    sanitizer.SanitizationError
                ):
                    sanitizer._read_secure_json(path, subject="candidate")

            benign = root / "benign-token-identity.json"
            benign.write_text(json.dumps({"token_ids": [0, 1]}), encoding="utf-8")
            self.assertEqual(
                sanitizer._read_secure_json(benign, subject="candidate").value,
                {"token_ids": [0, 1]},
            )

    def test_environment_digest_is_canonical_but_candidate_digest_is_not(self) -> None:
        left = {"b": 2, "a": {"d": 4, "c": 3}}
        right = {"a": {"c": 3, "d": 4}, "b": 2}
        self.assertEqual(
            sanitizer.canonical_json_sha256(left),
            sanitizer.canonical_json_sha256(right),
        )

    def test_candidate_intake_remains_capped_at_four_mibibytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            path = Path(temp).resolve() / "oversized.json"
            path.write_bytes(b'{"padding":"' + b"x" * sanitizer.MAX_CANDIDATE_INPUT_BYTES + b'"}')
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer._read_secure_json(
                    path,
                    subject="candidate",
                    maximum_bytes=sanitizer.MAX_CANDIDATE_INPUT_BYTES,
                )


class AbortSanitizationTests(unittest.TestCase):
    maxDiff = None

    def test_evaluated_early_failure_retains_comparison_prefix(self) -> None:
        candidate = _evaluated_failure_candidate(retain_output=True)
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")
            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            record = json.loads(installed[0].read_text(encoding="utf-8"))
            self.assertEqual(record["actual_status"], "failed")
            self.assertTrue(record["correctness"]["passed"])
            self.assertEqual(record["correctness"]["deterministic_repeat_count"], 0)
            self.assertEqual(record["correctness"]["repeat_output_hashes"], [])
            self.assertIsInstance(
                record["router_detail"]["correctness_cases"][0]["comparison"], dict
            )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_evaluated_invalid_output_uses_distinct_unavailability(self) -> None:
        candidate = _evaluated_failure_candidate(retain_output=False)
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")
            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            record = json.loads(installed[0].read_text(encoding="utf-8"))
            self.assertEqual(record["actual_status"], "failed")
            self.assertEqual(
                record["correctness"]["source"], "evaluated_output_invalid"
            )
            self.assertIsNone(
                record["router_detail"]["correctness_cases"][0]["mlx_output"]
            )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_first_request_abort_sanitizes_and_validates_without_fabrication(self) -> None:
        candidate = _abort_candidate()
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            raw_candidate = (
                json.dumps(candidate, sort_keys=False, separators=(",", ":")) + "\n"
            ).encode()
            candidate_path.write_bytes(raw_candidate)
            environment_path.write_text(
                json.dumps(combined, sort_keys=True) + "\n", encoding="utf-8"
            )

            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            self.assertEqual(len(installed), 1)
            self.assertEqual(candidate_path.read_bytes(), raw_candidate)
            digest = hashlib.sha256(raw_candidate).hexdigest()
            self.assertEqual(
                installed[0].stem, f"f002-router-real-{digest}-batch-a"
            )
            record = json.loads(installed[0].read_text(encoding="utf-8"))
            self.assertEqual(record["actual_status"], "aborted")
            self.assertEqual(record["correctness"]["status"], "unavailable")
            self.assertEqual(record["summaries"], [])
            self.assertEqual(record["router_detail"]["source_candidate_sha256"], digest)
            raw = record["raw_observations"][0]
            self.assertFalse(raw["evaluated"])
            self.assertIsNone(raw["output_sha256"])
            self.assertEqual(
                raw["durations_ns"]["end_to_end_router_command"],
                {"status": "observed", "duration_ns": 1_000},
            )
            self.assertIsNone(
                record["router_detail"]["resource_records"][0]["memory_gauges"]
            )
            self.assertEqual(
                record["failures"][0]["message"],
                sanitizer.KNOWN_FAILURE_MESSAGES["internal_worker_error"],
            )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_sent_request_abort_before_evaluation_retains_owned_lifecycle(self) -> None:
        candidate = _sent_request_abort_candidate()
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")

            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            record = json.loads(installed[0].read_text(encoding="utf-8"))
            raw = record["raw_observations"][0]
            self.assertFalse(raw["evaluated"])
            self.assertEqual(raw["status"], "aborted")
            self.assertEqual(
                raw["durations_ns"]["total_evaluated_router"]["status"],
                "unavailable",
            )
            self.assertTrue(record["router_detail"]["request_windows"][0]["request_sent"])
            self.assertEqual(
                [
                    (item["event"], item["outcome"])
                    for item in record["router_detail"]["process_lifecycles"]
                ],
                [("spawn", "started"), ("spawn", "passed"), ("shutdown", "graceful")],
            )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_same_candidate_is_deterministic_and_output_is_append_only(self) -> None:
        candidate = _abort_candidate()
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")
            first = root / "first"
            second = root / "second"
            first_paths = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=first,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            second_paths = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=second,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            self.assertEqual(first_paths[0].read_bytes(), second_paths[0].read_bytes())
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer.sanitize_candidate_files(
                    candidate_path=candidate_path,
                    environment_path=environment_path,
                    output_dir=first,
                    repository_root=REPOSITORY_ROOT,
                    enforce_repository_state=False,
                )

    def test_privacy_leak_in_dropped_candidate_field_is_rejected(self) -> None:
        candidate = _abort_candidate()
        candidate["unsupported_interpretations"] = [
            "/" + "Users/private/model.gguf"
        ]
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            path = Path(temp).resolve() / "candidate.json"
            path.write_text(json.dumps(candidate), encoding="utf-8")
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer._read_secure_json(path, subject="candidate")


class SanitizerAuditRegressionTests(unittest.TestCase):
    def test_fixed_rust_metadata_and_worker_count_mutations_are_rejected(self) -> None:
        base = _abort_candidate()
        mutations: dict[str, object] = {}

        unsupported = deepcopy(base)
        unsupported["unsupported_interpretations"] = ["safe but forged"]
        mutations["unsupported_interpretations"] = unsupported

        host_resource = deepcopy(base)
        host_resource["host_resource_observations"][
            "collector_process_cpu_time_seconds"
        ]["reason"] = "safe but forged"
        mutations["host_resource_observations"] = host_resource

        timing_count = deepcopy(base)
        timing_count["worker"]["attempted_timing_observation_count"] = 1
        mutations["attempted_timing_observation_count"] = timing_count

        completed_count = deepcopy(base)
        completed_count["worker"]["completed_process_count"] = 2
        mutations["completed_process_count"] = completed_count

        lifecycle = deepcopy(base)
        lifecycle["worker"]["worker_lifecycle"][0]["details"] = {
            "model_transport": "forged_transport"
        }
        mutations["lifecycle_details"] = lifecycle

        failure = deepcopy(base)
        failure["orchestration"]["failure"]["code"] = "invented_failure"
        failure["orchestration"]["retained_current_case_attempts"][0][
            "failure"
        ]["code"] = "invented_failure"
        failure["worker"]["worker_lifecycle"][1]["details"]["failure"][
            "code"
        ] = "invented_failure"
        failure["worker"]["request_utc_windows"][0]["failure"][
            "code"
        ] = "invented_failure"
        failure["worker"]["result_resource_records"][0]["failure"][
            "code"
        ] = "invented_failure"
        mutations["failure_code"] = failure

        for name, candidate in mutations.items():
            with self.subTest(name=name), self.assertRaises(
                sanitizer.SanitizationError
            ):
                sanitizer.build_public_records(
                    candidate,
                    _combined_environment(candidate),
                    source_candidate_sha256="c" * 64,
                    repository_root=REPOSITORY_ROOT,
                )

    def test_every_redundant_timing_join_rejects_a_mutation(self) -> None:
        base = _passing_candidate()
        combined = _combined_environment(base)

        def mutate(field: str, value: object) -> dict[str, object]:
            candidate = deepcopy(base)
            observation = candidate["orchestration"]["second_batch"][
                "first_process_series"
            ][0]["raw_timing_observations"][0]
            observation[field] = value
            return candidate

        mutations = {
            "selected_device": mutate("selected_device", "cpu"),
            "output_sha256": mutate("output_sha256", "d" * 64),
            "router_tensor_bytes_read": mutate(
                "router_tensor_bytes_read", 1_048_575
            ),
            "router_tensor_cache_status": mutate(
                "router_tensor_cache_status", "cache_hit"
            ),
            "started_at_utc": mutate("started_at_utc", "2026-08-06T04:05:05Z"),
            "host_wall_duration_ns": mutate("host_wall_duration_ns", 99),
            "monotonic_clock": mutate("monotonic_clock", "forged_clock"),
            "status": mutate("status", "failed"),
        }
        series_role = deepcopy(base)
        series_role["orchestration"]["second_batch"]["first_process_series"][0][
            "condition"
        ] = "controlled_cold"
        mutations["series_condition"] = series_role

        for name, candidate in mutations.items():
            with self.subTest(name=name), self.assertRaises(
                sanitizer.SanitizationError
            ):
                sanitizer.build_public_records(
                    candidate,
                    combined,
                    source_candidate_sha256="d" * 64,
                    repository_root=REPOSITORY_ROOT,
                )

    def test_private_reason_matrix_is_rejected_in_candidate_and_environment(self) -> None:
        fragments = (
            "url?access_token=operatorprivate",
            "github_token=operatorprivate",
            "x|password=operatorprivate",
        )
        passing = _passing_candidate()
        passing_environment = _combined_environment(passing)
        aborted = _abort_candidate()
        before = environment_fixtures._collect()
        unavailable_environment = environment.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=None,
            after_unavailable_reason="the bounded after snapshot was unavailable",
            benchmark_resources=environment.extract_benchmark_resources(aborted),
        )
        for fragment in fragments:
            candidate = deepcopy(passing)
            candidate["orchestration"]["second_batch"] = {
                "status": "unavailable",
                "reason": fragment,
                "between_batch_variation_measured": False,
            }
            with self.subTest(location="candidate", fragment=fragment), self.assertRaises(
                sanitizer.SanitizationError
            ):
                sanitizer.build_public_records(
                    candidate,
                    passing_environment,
                    source_candidate_sha256="e" * 64,
                    repository_root=REPOSITORY_ROOT,
                )

            handoff = deepcopy(unavailable_environment)
            handoff["after_snapshot"]["reason"] = fragment
            with self.subTest(location="environment", fragment=fragment), self.assertRaises(
                sanitizer.SanitizationError
            ):
                sanitizer.build_public_records(
                    aborted,
                    handoff,
                    source_candidate_sha256="e" * 64,
                    repository_root=REPOSITORY_ROOT,
                )

        noncanonical = deepcopy(passing)
        noncanonical["orchestration"]["second_batch"] = {
            "status": "unavailable",
            "reason": "a safe but noncanonical producer reason",
            "between_batch_variation_measured": False,
        }
        with self.assertRaises(sanitizer.SanitizationError):
            sanitizer.build_public_records(
                noncanonical,
                passing_environment,
                source_candidate_sha256="e" * 64,
                repository_root=REPOSITORY_ROOT,
            )

    def test_orphan_lifecycle_and_forged_matching_worker_version_are_rejected(self) -> None:
        orphan = _abort_candidate()
        orphan_entry = deepcopy(orphan["worker"]["worker_lifecycle"][0])
        orphan_entry.update({
            "event_order": len(orphan["worker"]["worker_lifecycle"]),
            "process_replication_id": "batch-a-orphan-worker",
        })
        orphan["worker"]["worker_lifecycle"].append(orphan_entry)
        orphan["worker"]["completed_process_count"] = 2
        with self.assertRaises(sanitizer.SanitizationError):
            sanitizer.build_public_records(
                orphan,
                _combined_environment(orphan),
                source_candidate_sha256="f" * 64,
                repository_root=REPOSITORY_ROOT,
            )

        forged_version = _sent_request_abort_candidate()
        forged_version["worker"]["runtime"]["worker_version"] = "9.9.9"
        forged_version["worker"]["worker_lifecycle"][1]["details"][
            "worker_version"
        ] = "9.9.9"
        with self.assertRaises(sanitizer.SanitizationError):
            sanitizer.build_public_records(
                forged_version,
                _combined_environment(forged_version),
                source_candidate_sha256="f" * 64,
                repository_root=REPOSITORY_ROOT,
            )

    def test_unknown_fields_are_rejected_at_all_rust_producer_boundaries(self) -> None:
        base = _passing_candidate()
        combined = _combined_environment(base)
        locations = (
            lambda candidate: candidate["orchestration"],
            lambda candidate: candidate["orchestration"]["primary_batch"],
            lambda candidate: candidate["orchestration"]["second_batch"],
            lambda candidate: candidate["orchestration"]["primary_batch"][
                "raw_observations"
            ][0],
            lambda candidate: candidate["orchestration"]["correctness_gates"][0],
        )
        for index, locate in enumerate(locations):
            candidate = deepcopy(base)
            locate(candidate)["unexpected_producer_field"] = "forged"
            with self.subTest(index=index), self.assertRaises(
                sanitizer.SanitizationError
            ):
                sanitizer.build_public_records(
                    candidate,
                    combined,
                    source_candidate_sha256="1" * 64,
                    repository_root=REPOSITORY_ROOT,
                )

    def test_correctness_gate_aggregate_contradictions_are_rejected(self) -> None:
        candidate = _passing_candidate()
        gate = candidate["orchestration"]["correctness_gates"][0]
        gate.update({
            "batch_id": "batch-forged",
            "attempt_count": 14,
            "warmup_count": 4,
            "measurement_count": 9,
            "complete_output_sha256": "2" * 64,
            "requested_device": "cpu",
            "fallback_used": True,
            "evaluated": False,
            "synchronized": False,
            "comparison_passed": False,
            "passed": False,
        })
        with self.assertRaises(sanitizer.SanitizationError):
            sanitizer.build_public_records(
                candidate,
                _combined_environment(candidate),
                source_candidate_sha256="2" * 64,
                repository_root=REPOSITORY_ROOT,
            )

    def test_passing_attempt_redundant_contradictions_are_rejected(self) -> None:
        candidate = _passing_candidate()
        attempt = candidate["orchestration"]["correctness_gates"][0]["attempts"][0]
        attempt.update({
            "backend": "forged-backend",
            "logits_f32le_sha256": "3" * 64,
            "selected_expert_ids": [[127] * 8],
            "selected_expert_ids_u32le_sha256": "4" * 64,
            "comparison": {"passed": False},
            "requested_device": "cpu",
            "selected_device": "cpu",
            "fallback_used": True,
            "evaluated": False,
            "synchronized": False,
            "result_passed": False,
            "failure": deepcopy(FAILURE),
        })
        with self.assertRaises(sanitizer.SanitizationError):
            sanitizer.build_public_records(
                candidate,
                _combined_environment(candidate),
                source_candidate_sha256="3" * 64,
                repository_root=REPOSITORY_ROOT,
            )

    def test_staged_and_installed_content_mutation_rolls_back(self) -> None:
        candidate = _abort_candidate()
        records = sanitizer.build_public_records(
            candidate,
            _combined_environment(candidate),
            source_candidate_sha256="4" * 64,
            repository_root=REPOSITORY_ROOT,
        )
        for mutation_recheck in (1, 2):
            with self.subTest(mutation_recheck=mutation_recheck), tempfile.TemporaryDirectory(
                prefix="pulsarmlx-sanitize-test-"
            ) as temp:
                root = Path(temp).resolve()
                output = root / "public"
                recheck_count = 0

                def mutate_published_bytes() -> None:
                    nonlocal recheck_count
                    recheck_count += 1
                    if recheck_count != mutation_recheck:
                        return
                    directory = output if output.is_dir() else next(
                        root.glob(".router-sanitize-*")
                    )
                    next(directory.glob("*.json")).write_bytes(b"{}\n")

                with self.assertRaises(sanitizer.SanitizationError):
                    sanitizer._install_records_exclusively(
                        records,
                        output,
                        repository_root=REPOSITORY_ROOT,
                        source_recheck=mutate_published_bytes,
                    )
                self.assertFalse(output.exists())
                self.assertFalse(any(root.glob(".router-sanitize-*")))

    def test_symlinked_output_and_repository_parents_are_rejected(self) -> None:
        candidate = _abort_candidate()
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")

            physical_output_parent = root / "physical-output-parent"
            physical_output_parent.mkdir()
            output_parent_link = root / "output-parent-link"
            os.symlink(physical_output_parent, output_parent_link)
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer.sanitize_candidate_files(
                    candidate_path=candidate_path,
                    environment_path=environment_path,
                    output_dir=output_parent_link / "public",
                    repository_root=REPOSITORY_ROOT,
                    enforce_repository_state=False,
                )

            repository_link = root / "repository-link"
            os.symlink(REPOSITORY_ROOT, repository_link)
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer.sanitize_candidate_files(
                    candidate_path=candidate_path,
                    environment_path=environment_path,
                    output_dir=root / "public",
                    repository_root=repository_link,
                    enforce_repository_state=False,
                )


class PassingTwoBatchSanitizationTests(unittest.TestCase):
    maxDiff = None

    def test_complete_counterbalanced_candidate_produces_target_then_source(self) -> None:
        candidate = _passing_candidate()
        combined = _combined_environment(candidate)
        raw_candidate = (
            json.dumps(candidate, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode()
        digest = hashlib.sha256(raw_candidate).hexdigest()
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            candidate_path.write_bytes(raw_candidate)
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")
            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            self.assertEqual([path.stem.rsplit("-", 1)[-1] for path in installed], ["b", "a"])
            target = json.loads(installed[0].read_text(encoding="utf-8"))
            source = json.loads(installed[1].read_text(encoding="utf-8"))
            self.assertEqual(target["batch_id"], "batch-b")
            self.assertEqual(source["batch_id"], "batch-a")
            self.assertEqual(len(target["raw_observations"]), 260)
            self.assertEqual(len(source["raw_observations"]), 260)
            self.assertEqual(target["actual_status"], "passed")
            self.assertEqual(source["actual_status"], "passed")
            self.assertEqual(
                source["second_batch"]["linked_record_sha256"],
                sanitizer.canonical_json_sha256(target),
            )
            self.assertEqual(
                source["router_detail"]["source_candidate_sha256"], digest
            )
            self.assertEqual(
                target["router_detail"]["source_candidate_sha256"], digest
            )
            self.assertFalse(
                set(item["process_replication_id"] for item in source["raw_observations"])
                & set(item["process_replication_id"] for item in target["raw_observations"])
            )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_failed_later_batch_is_linked_without_coercing_primary_status(self) -> None:
        candidate = _failed_later_batch_candidate()
        combined = _combined_environment(candidate)
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")
            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            target = json.loads(installed[0].read_text(encoding="utf-8"))
            source = json.loads(installed[1].read_text(encoding="utf-8"))
            self.assertEqual((target["batch_id"], target["actual_status"]), ("batch-b", "failed"))
            self.assertEqual((source["batch_id"], source["actual_status"]), ("batch-a", "passed"))
            self.assertEqual(target["execution"]["exit_code"], 1)
            self.assertEqual(source["execution"]["exit_code"], 0)
            self.assertEqual(
                source["second_batch"]["linked_record_sha256"],
                sanitizer.canonical_json_sha256(target),
            )
            self.assertEqual(
                source["protocol"]["sha256"], validator.FROZEN_PROTOCOL_SHA256
            )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_unavailable_after_snapshot_blocks_without_summaries_or_capabilities(self) -> None:
        candidate = _passing_candidate()
        before = environment_fixtures._collect()
        combined = environment.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=None,
            after_unavailable_reason="the bounded after snapshot was unavailable",
            benchmark_resources=environment.extract_benchmark_resources(candidate),
        )
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            candidate_path = root / "candidate.json"
            environment_path = root / "environment.json"
            output = root / "public"
            candidate_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")
            environment_path.write_text(json.dumps(combined) + "\n", encoding="utf-8")
            installed = sanitizer.sanitize_candidate_files(
                candidate_path=candidate_path,
                environment_path=environment_path,
                output_dir=output,
                repository_root=REPOSITORY_ROOT,
                enforce_repository_state=False,
            )
            for path in installed:
                record = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(record["actual_status"], "blocked")
                self.assertNotEqual(record["execution"]["exit_code"], 0)
                self.assertEqual(record["summaries"], [])
                self.assertEqual(record["claim_boundary"]["capabilities"], [])
                self.assertEqual(
                    record["router_detail"]["terminal_failure"]["phase"],
                    "environment_admission_unavailable",
                )
                self.assertEqual(
                    record["environment"]["after_snapshot"],
                    {
                        "status": "unavailable",
                        "reason": sanitizer.PUBLIC_AFTER_UNAVAILABLE_REASON,
                        "attempted_method": sanitizer.PUBLIC_AFTER_UNAVAILABLE_METHOD,
                    },
                )
                self.assertEqual(
                    record["protocol"]["sha256"], validator.FROZEN_PROTOCOL_SHA256
                )
            validator.validate_input(REPOSITORY_ROOT / "schemas/research/v1", output)

    def test_multi_record_installation_rolls_back_post_install_source_change(self) -> None:
        candidate = _passing_candidate()
        combined = _combined_environment(candidate)
        records = sanitizer.build_public_records(
            candidate,
            combined,
            source_candidate_sha256="b" * 64,
            repository_root=REPOSITORY_ROOT,
        )
        recheck_count = 0

        def changed_after_install() -> None:
            nonlocal recheck_count
            recheck_count += 1
            if recheck_count == 2:
                raise sanitizer.SanitizationError("synthetic source change")

        with tempfile.TemporaryDirectory(prefix="pulsarmlx-sanitize-test-") as temp:
            root = Path(temp).resolve()
            output = root / "public"
            with self.assertRaises(sanitizer.SanitizationError):
                sanitizer._install_records_exclusively(
                    records,
                    output,
                    repository_root=REPOSITORY_ROOT,
                    source_recheck=changed_after_install,
                )
            self.assertFalse(output.exists())
            self.assertFalse(any(root.glob(".router-sanitize-*")))


if __name__ == "__main__":
    unittest.main()

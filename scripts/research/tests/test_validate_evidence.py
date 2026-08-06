"""Contract tests for the fail-closed Feature 002 evidence validator.

These tests intentionally exercise the public command-line boundary rather than
importing implementation details.  T006 lands them red; T009 and T011 provide
the closed schemas and validator that make them green.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile
from typing import Any
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "research" / "validate_evidence.py"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "research" / "v1"
MODEL_MANIFEST = REPOSITORY_ROOT / "docs" / "research" / "MODEL_MANIFEST.json"
PROTOCOL = REPOSITORY_ROOT / "docs" / "research" / "EXPERIMENT_PROTOCOL.md"
ROUTER_MANIFEST = REPOSITORY_ROOT / "fixtures" / "research" / "router-v1" / "manifest.json"
REAL_ORACLE_PUBLICATION = (
    REPOSITORY_ROOT
    / "fixtures"
    / "research"
    / "router-v1"
    / "real"
    / "f002-router-oracle-freeze-0001.json"
)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SOURCE_COMMIT = "d" * 40
LEGACY_PROTOCOL_COMMIT = "246e3da87d56d2f346f7b5c3547694005e5c89fe"
LEGACY_PROTOCOL_SHA256 = "c4bc12eb294a5849cc1a88ec7e9820af5cd4387722536565697a30fdf8fe3863"


_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "pulsarmlx_evidence_validator_contract", VALIDATOR
)
if _VALIDATOR_SPEC is None or _VALIDATOR_SPEC.loader is None:
    raise RuntimeError("cannot load the research evidence validator")
validator = importlib.util.module_from_spec(_VALIDATOR_SPEC)
_VALIDATOR_SPEC.loader.exec_module(validator)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _type7(values: list[int], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    fraction = position - lower
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _summary_values(values: list[int]) -> dict[str, object]:
    mean = statistics.fmean(values)
    sample_standard_deviation = statistics.stdev(values) if len(values) > 1 else None
    return {
        "sample_count": len(values),
        "minimum_ns": min(values),
        "maximum_ns": max(values),
        "mean_ns": mean,
        "sample_standard_deviation_ns": sample_standard_deviation,
        "sample_standard_deviation_reason": (
            None
            if sample_standard_deviation is not None
            else "requires_at_least_two_samples"
        ),
        "p5_ns": _type7(values, 0.05),
        "p25_ns": _type7(values, 0.25),
        "median_ns": _type7(values, 0.50),
        "p75_ns": _type7(values, 0.75),
        "p95_ns": _type7(values, 0.95),
        "coefficient_of_variation": (
            sample_standard_deviation / mean
            if sample_standard_deviation is not None and mean != 0
            else None
        ),
        "coefficient_of_variation_reason": (
            None
            if sample_standard_deviation is not None and mean != 0
            else "sample_standard_deviation_unavailable"
        ),
    }


def _observation(
    observation_id: str,
    run_index: int,
    kind: str,
    duration_ns: int,
    *,
    process_state: str = "reused_process",
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "run_index": run_index,
        "batch_id": "batch-a",
        "case_id": "qwen3moe-layer0-router-token0-row0-v1",
        "process_replication_id": (
            "process-clean-a" if kind == "clean_process_replication" else "process-warm-a"
        ),
        "observation_kind": kind,
        "process_state": process_state,
        "condition": "warm",
        "instrumentation_mode": "minimally_instrumented",
        "started_at_utc": "2026-08-05T18:00:00Z",
        "completed_at_utc": "2026-08-05T18:00:01Z",
        "monotonic_clock": "perf_counter_ns",
        "durations_ns": {"total_evaluated_router": duration_ns},
        "status": "passed",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
        "output_sha256": SHA_B,
        "correctness_passed": True,
    }


def _summary(
    summary_id: str,
    observations: list[dict[str, object]],
    kind: str,
) -> dict[str, object]:
    included = [item for item in observations if item["observation_kind"] == kind]
    values = [
        int(item["durations_ns"]["total_evaluated_router"])  # type: ignore[index]
        for item in included
    ]
    return {
        "summary_id": summary_id,
        "statistics_algorithm": "pulsarmlx-type7-v1",
        "group": {
            "case_id": "qwen3moe-layer0-router-token0-row0-v1",
            "batch_id": "batch-a",
            "observation_kind": kind,
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "stage": "total_evaluated_router",
        },
        "included_observation_ids": [item["observation_id"] for item in included],
        "excluded_observation_ids": [],
        "unfiltered_summary": _summary_values(values),
    }


def valid_evidence(experiment_id: str = "f002-router-fixture-0001") -> dict[str, object]:
    model_identity = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))["model_identity"]
    protocol_sha256 = _sha256(PROTOCOL)
    observations = [
        _observation(f"warmup-{index:02d}", index, "warmup", 900 + index)
        for index in range(5)
    ]
    observations.extend(
        _observation(f"measurement-{index:02d}", index, "measurement", 1_000 + index)
        for index in range(10)
    )
    observations.append(
        _observation(
            "clean-process-00",
            0,
            "clean_process_replication",
            1_025,
            process_state="fresh_process",
        )
    )

    return {
        "evidence_schema": "pulsarmlx.research.experiment",
        "evidence_schema_version": "1.2.0",
        "payload_schema": "pulsarmlx.research.router-parity",
        "payload_schema_version": "1.1.0",
        "experiment_id": experiment_id,
        "feature_id": "002-qwen-router-parity",
        "evidence_scope": "synthetic_fixture",
        "record_kind": "combined",
        "actual_status": "passed",
        "started_at_utc": "2026-08-05T17:59:00Z",
        "completed_at_utc": "2026-08-05T18:10:00Z",
        "source_commit": SOURCE_COMMIT,
        "source_worktree_before": "clean",
        "source_worktree_after": {
            "state": "declared_evidence_outputs_only",
            "paths": [f"docs/research/raw/002-router-parity/{experiment_id}.json"],
        },
        "protocol": {
            "protocol_id": "f002-router-protocol-amendment-002",
            "protocol_version": "1.2.0",
            "path": "docs/research/EXPERIMENT_PROTOCOL.md",
            "sha256": protocol_sha256,
            "order_seed": 22002,
        },
        "execution": {
            "shell": "zsh",
            "command": "python3 scripts/research/run_router_experiment.py --model $PULSARMLX_MODEL_GGUF",
            "argv": [
                "python3",
                "scripts/research/run_router_experiment.py",
                "--model",
                "$PULSARMLX_MODEL_GGUF",
            ],
            "working_directory_policy": "repository_root",
            "exit_code": 0,
            "build_profile": "release",
            "features": ["mlx-backend"],
            "benchmark_order_policy": "deterministic_seeded",
        },
        "batch_id": "batch-a",
        "process_replication_id": "process-warm-a",
        "model": {
            field: model_identity[field]
            for field in (
                "repository",
                "revision",
                "filename",
                "size_bytes",
                "sha256",
                "architecture",
                "external_locator",
            )
        },
        "tensor": {
            "name": "blk.0.ffn_gate_inp.weight",
            "semantic_role": "layer_0_router_projection",
            "occurrence_count": 1,
            "gguf_dimensions": [2048, 128],
            "reader_shape": [128, 2048],
            "execution_shape": [128, 2048],
            "dtype": "F32",
            "quantization": "none_f32",
            "absolute_offset": 0,
            "encoded_length": 1_048_576,
            "end_offset": 1_048_576,
            "encoded_sha256": SHA_B,
        },
        "input": {
            "fixture_id": "qwen3moe-layer0-router-direct-tokens-v1",
            "graph_node": "ffn_norm-0",
            "input_adapter": "direct_token_ids_v1",
            "tokenizer_identity": "not_used_direct_token_ids",
            "token_ids": [0, 1],
            "positions": [0, 1],
            "shape": [2, 2048],
            "dtype": "float32",
            "byte_order": "little",
            "byte_length": 16_384,
            "canonical_sha256": SHA_C,
            "selected_rows": [0],
        },
        "oracle": {
            "oracle_id": "f002-scalar-f32-v1",
            "project": "llama.cpp-plus-standalone-scalar-oracle",
            "revision": "b06aa774c03dbbb624e726664b714a57d1f49815",
            "generation_command": "python3 scripts/research/router_oracle.py --fixture $PULSARMLX_ROUTER_FIXTURE",
            "input_fixture_sha256": SHA_C,
            "tensor_sha256": SHA_B,
            "output_sha256": SHA_A,
            "independence_statement": "Does not import or invoke MLX or the PulsarMLX worker.",
        },
        "environment": {
            "platform": "macos-arm64",
            "selected_backend": "apple-mlx",
            "selected_device": "gpu",
            "safe_environment": {"PULSARMLX_MODEL_GGUF": "$PULSARMLX_MODEL_GGUF"},
            "interference_admission": "admitted",
        },
        "correctness": {
            "passed": True,
            "compared_count": 128,
            "id_mismatch_count": 0,
            "order_mismatch_count": 0,
            "numeric_mismatch_count": 0,
            "first_mismatch": None,
            "maximum_absolute_error": 0.0,
            "mean_absolute_error": 0.0,
            "rmse": 0.0,
            "maximum_relative_error": 0.0,
            "absolute_tolerance": 0.0005,
            "relative_tolerance": 0.0005,
            "non_finite_policy": "reject",
            "non_finite_count": 0,
            "deterministic_repeat_count": 10,
            "repeat_output_hashes": [SHA_B] * 10,
        },
        "raw_observations": observations,
        "summaries": [
            _summary("warm-measurement-total", observations, "measurement"),
            _summary(
                "clean-process-total",
                observations,
                "clean_process_replication",
            ),
        ],
        "claim_boundary": {
            "status": "provisional",
            "operation": "layer_0_router_only",
            "capabilities": [
                "router_logits",
                "router_full_softmax",
                "router_top8_selection",
                "router_selected_weight_normalization",
            ],
            "unsupported_interpretations": [
                "expert_execution",
                "routed_moe_aggregation",
                "complete_transformer_layer",
                "language_model_head_or_model_output_logits",
                "generation",
                "full_model_generation",
                "serving",
                "custom_metal",
                "complete_model_inference",
                "full_or_giant_model_inference",
                "projected_tokens_per_second",
                "token_throughput",
                "linux_cuda_runtime_parity",
                "real_checkpoint_routing",
            ],
        },
        "warnings": ["Fixture-only evidence; no real checkpoint measurement."],
        "failures": [],
        "artifacts": [
            {
                "kind": "frozen_protocol",
                "path": "docs/research/EXPERIMENT_PROTOCOL.md",
                "sha256": protocol_sha256,
            },
            {
                "kind": "router_fixture_manifest",
                "path": "fixtures/research/router-v1/manifest.json",
                "sha256": _sha256(ROUTER_MANIFEST),
            },
        ],
    }


def external_oracle_identity() -> tuple[dict[str, object], dict[str, object]]:
    """Return the experiment projection of the committed real-oracle publication."""

    publication = json.loads(REAL_ORACLE_PUBLICATION.read_text(encoding="utf-8"))
    identity = {
        "oracle_id": "qwen3moe-layer0-router-cpu-oracle-v1",
        "project": "llama.cpp-plus-standalone-scalar-oracle",
        "revision": publication["source"]["revision"],
        "generation_command": publication["generator"]["generation_command"],
        "input_fixture_sha256": publication["input"]["canonical_f32le_sha256"],
        "tensor_sha256": publication["tensor"]["encoded_sha256"],
        "output_sha256": publication["result"]["hashes"]["output_bundle_sha256"],
        "independence_statement": publication["generator"]["independence"],
    }
    return publication, identity


def _public_single_row_output() -> dict[str, object]:
    publication = json.loads(REAL_ORACLE_PUBLICATION.read_text(encoding="utf-8"))
    result = publication["result"]
    case_id = "qwen3moe-layer0-router-token0-row0-v1"
    logits = list(result["logits"][0])
    probabilities = list(result["full_softmax_probabilities"][0])
    selected_ids = [list(result["selected_expert_ids"][0])]
    selected_probabilities = [list(result["selected_probabilities"][0])]
    normalized_weights = [list(result["normalized_weights"][0])]

    def f32le(values):
        flat = values[0] if values and isinstance(values[0], list) else values
        return b"".join(struct.pack("<f", value) for value in flat)

    def u32le(values):
        return b"".join(struct.pack("<I", value) for value in values[0])

    components = [
        f32le(logits),
        f32le(probabilities),
        u32le(selected_ids),
        f32le(selected_probabilities),
        f32le(normalized_weights),
    ]
    return {
        "case_id": case_id,
        "case_scope": "real_checkpoint",
        "row_count": 1,
        "logits_shape": [1, 128],
        "logits": logits,
        "logits_f32le_sha256": hashlib.sha256(components[0]).hexdigest(),
        "full_probabilities_shape": [1, 128],
        "full_probabilities": probabilities,
        "full_probabilities_f32le_sha256": hashlib.sha256(components[1]).hexdigest(),
        "selected_expert_ids": selected_ids,
        "selected_expert_ids_u32le_sha256": hashlib.sha256(components[2]).hexdigest(),
        "selected_probabilities": selected_probabilities,
        "selected_probabilities_f32le_sha256": hashlib.sha256(components[3]).hexdigest(),
        "normalized_weights": normalized_weights,
        "normalized_weights_f32le_sha256": hashlib.sha256(components[4]).hexdigest(),
        "complete_output_sha256": hashlib.sha256(b"".join(components)).hexdigest(),
    }


def _first_request_abort_detail() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    observation_id = "batch-a-single-correctness-warmup-00"
    case_id = "qwen3moe-layer0-router-token0-row0-v1"
    process_id = "batch-a-correctness-worker"
    failure = {
        "code": "worker_startup_failed",
        "message": "the worker did not start",
        "stage": "worker_startup",
    }
    observation = {
        "observation_id": observation_id,
        "run_index": 0,
        "batch_id": "batch-a",
        "case_id": case_id,
        "process_replication_id": process_id,
        "observation_kind": "warmup",
        "process_state": "reused_process",
        "condition": "warm",
        "instrumentation_mode": "minimally_instrumented",
        "started_at_utc": "2026-08-06T11:59:59Z",
        "completed_at_utc": "2026-08-06T12:00:02Z",
        "monotonic_clock": "rust_std_instant",
        "durations_ns": {
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization",
            },
            "total_evaluated_router": {
                "status": "unavailable",
                "reason": "worker_startup_failed_before_evaluation",
            },
            "end_to_end_router_command": {"status": "observed", "duration_ns": 1_000},
        },
        "status": "aborted",
        "requested_device": "gpu",
        "selected_device": "not_available",
        "fallback_used": False,
        "evaluated": False,
        "synchronized": False,
        "output_sha256": None,
        "correctness_passed": None,
        "failure": failure,
    }
    environment = {"sentinel": "public-safe"}
    detail = {
        "detail_schema": "pulsarmlx.research.router-detail",
        "detail_schema_version": "1.0.0",
        "source_candidate_sha256": SHA_A,
        "source_environment_sha256": validator._canonical_json_sha256(environment),
        "application_read_semantics": "application_positional_read_not_physical_disk_io",
        "batch_order": "single_row_first",
        "ordered_observations": [{
            "global_order_index": 0,
            "observation_id": observation_id,
            "schedule_step": "single_row_correctness",
            "source_kind": "correctness_attempt",
            "batch_id": "batch-a",
            "case_id": case_id,
            "process_replication_id": process_id,
            "observation_kind": "warmup",
            "run_index": 0,
            "orchestration_status": "rejected",
            "identity_disposition": "unique",
        }],
        "correctness_cases": [{
            "case_id": case_id,
            "row_count": 1,
            "oracle_output": validator._load_real_oracle_outputs(REPOSITORY_ROOT)[case_id],
            "mlx_output": None,
            "comparison": None,
            "attempts": [{
                "attempt_id": observation_id,
                "attempt_index": 0,
                "observation_kind": "warmup",
                "run_index": 0,
                "process_replication_id": process_id,
                "canonical_output": None,
                "comparison": None,
                "memory_gauges": None,
                "requested_device": "gpu",
                "selected_device": "not_available",
                "fallback_used": False,
                "evaluated": False,
                "synchronized": False,
                "status": "aborted",
                "passed": False,
                "failure": failure,
            }],
        }],
        "timing_series": [],
        "process_lifecycles": [
            {
                "event_order": 0,
                "recorded_at_utc": "2026-08-06T12:00:00Z",
                "process_replication_id": process_id,
                "timing_profile": "minimal",
                "event": "spawn",
                "outcome": "started",
                "details": {},
            },
            {
                "event_order": 1,
                "recorded_at_utc": "2026-08-06T12:00:01Z",
                "process_replication_id": process_id,
                "timing_profile": "minimal",
                "event": "spawn",
                "outcome": "failed",
                "details": {"failure": failure},
            },
        ],
        "request_windows": [{
            "observation_id": observation_id,
            "batch_id": "batch-a",
            "case_id": case_id,
            "schedule_step": "single_row_correctness",
            "source_kind": "correctness_attempt",
            "process_replication_id": process_id,
            "timing_profile": "minimal",
            "started_at_utc": "2026-08-06T11:59:59Z",
            "completed_at_utc": "2026-08-06T12:00:02Z",
            "host_wall_duration_ns": 1_000,
            "host_monotonic_clock": "rust_std_instant",
            "request_sent": False,
            "status": "aborted",
            "failure": failure,
        }],
        "resource_records": [{
            "observation_id": observation_id,
            "source_kind": "correctness_attempt",
            "backend": "apple-mlx",
            "requested_device": "gpu",
            "selected_device": "not_available",
            "fallback_used": False,
            "evaluated": False,
            "synchronized": False,
            "output_sha256": None,
            "correctness_passed": None,
            "canonical_output": None,
            "memory_gauges": None,
            "monotonic_clock": None,
            "instrumentation_mode": "minimally_instrumented",
            "timing_stages": None,
            "application_tensor_bytes_read": None,
            "tensor_cache_outcome": "unavailable",
            "canonical_output_retention": "unavailable_aborted_request",
            "status": "aborted",
            "failure": failure,
        }],
        "terminal_failure": None,
    }
    record = {
        "evidence_scope": "external_checkpoint",
        "actual_status": "aborted",
        "environment": environment,
        "input": {"selected_rows": [0, 1]},
        "correctness": {
            "status": "unavailable",
            "reason": "worker startup failed before evaluation",
            "source": "pre_execution_abort",
        },
        "router_detail": detail,
    }
    return record, {observation_id: observation}


def _owned_pre_evaluation_abort_detail(
    *,
    request_sent: bool,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Construct an owned-worker abort before an evaluated result exists."""

    record, by_id = _first_request_abort_detail()
    observation_id = next(iter(by_id))
    if request_sent:
        failure = {
            "code": "protocol_mismatch",
            "message": "the live worker rejected the request protocol",
            "stage": "router_execution",
        }
        started_at = "2026-08-06T12:00:01Z"
        completed_at = "2026-08-06T12:00:01Z"
        unavailable_reason = "worker_request_aborted_before_evaluation"
    else:
        failure = {
            "code": "internal_worker_error",
            "message": "a public-safe admitted-request timestamp could not be observed",
            "stage": "request_observation",
        }
        # This is Rust's explicit UTC fallback. It is request evidence, not a
        # bound around the already-owned worker lifecycle.
        started_at = "2026-08-06T11:59:59Z"
        completed_at = "2026-08-06T11:59:59Z"
        unavailable_reason = "admitted_request_timestamp_failed_before_evaluation"

    observation = by_id[observation_id]
    observation.update({
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "failure": deepcopy(failure),
    })
    observation["durations_ns"]["total_evaluated_router"]["reason"] = (
        unavailable_reason
    )

    detail = record["router_detail"]
    attempt = detail["correctness_cases"][0]["attempts"][0]
    attempt["failure"] = deepcopy(failure)
    detail["process_lifecycles"] = [
        {
            "event_order": 0,
            "recorded_at_utc": "2026-08-06T12:00:00Z",
            "process_replication_id": observation["process_replication_id"],
            "timing_profile": "minimal",
            "event": "spawn",
            "outcome": "started",
            "details": {},
        },
        {
            "event_order": 1,
            "recorded_at_utc": "2026-08-06T12:00:01Z",
            "process_replication_id": observation["process_replication_id"],
            "timing_profile": "minimal",
            "event": "spawn",
            "outcome": "passed",
            "details": {},
        },
        {
            "event_order": 2,
            "recorded_at_utc": "2026-08-06T12:00:02Z",
            "process_replication_id": observation["process_replication_id"],
            "timing_profile": "minimal",
            "event": "shutdown",
            "outcome": "graceful",
            "details": {},
        },
    ]
    window = detail["request_windows"][0]
    window.update({
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "request_sent": request_sent,
        "failure": deepcopy(failure),
    })
    detail["resource_records"][0]["failure"] = deepcopy(failure)
    record["correctness"]["reason"] = unavailable_reason.replace("_", " ")
    return record, by_id


def _identical_output_comparison(output: dict[str, object]) -> dict[str, object]:
    logits = list(output["logits"])
    probabilities = list(output["full_probabilities"])
    row_count = int(output["row_count"])
    selected = [value for row in output["selected_probabilities"] for value in row]
    normalized = [value for row in output["normalized_weights"] for value in row]
    whole = {
        "logits": validator._expected_numeric_comparison(
            logits, logits, row_count=row_count, columns=128,
            absolute_tolerance=5.0e-4, relative_tolerance=5.0e-4,
        ),
        "full_probabilities": validator._expected_numeric_comparison(
            probabilities, probabilities, row_count=row_count, columns=128,
            absolute_tolerance=1.0e-6, relative_tolerance=1.0e-6,
        ),
        "selected_probabilities": validator._expected_numeric_comparison(
            selected, selected, row_count=row_count, columns=8,
            absolute_tolerance=1.0e-6, relative_tolerance=1.0e-6,
        ),
        "normalized_weights": validator._expected_numeric_comparison(
            normalized, normalized, row_count=row_count, columns=8,
            absolute_tolerance=1.0e-6, relative_tolerance=1.0e-6,
        ),
    }
    ranges = {}
    for label, columns in (("0..16", range(0, 16)), ("64..80", range(64, 80))):
        ranges[label] = {
            "logits": validator._expected_numeric_comparison(
                logits, logits, row_count=row_count, columns=128,
                absolute_tolerance=5.0e-4, relative_tolerance=5.0e-4,
                column_range=columns,
            ),
            "full_probabilities": validator._expected_numeric_comparison(
                probabilities, probabilities, row_count=row_count, columns=128,
                absolute_tolerance=1.0e-6, relative_tolerance=1.0e-6,
                column_range=columns,
            ),
            "passed": True,
        }
    return {
        **whole,
        "id_mismatch_count": 0,
        "order_mismatch_count": 0,
        "expert_range_comparisons": ranges,
        "passed": True,
    }


def _passing_external_record(
    experiment_id: str,
    batch_id: str,
    batch_order: str,
) -> dict[str, Any]:
    """Build one complete 260-observation external record without model access."""

    from scripts.research.tests import test_environment as environment_fixtures

    single_case = "qwen3moe-layer0-router-token0-row0-v1"
    two_row_case = "qwen3moe-layer0-router-token0-token1-batch-v1"
    case_order = (
        [single_case, two_row_case]
        if batch_order == "single_row_first"
        else [two_row_case, single_case]
    )
    outputs = validator._load_real_oracle_outputs(REPOSITORY_ROOT)
    comparisons = {
        case_id: _identical_output_comparison(output)
        for case_id, output in outputs.items()
    }
    gauges = {
        "mlx_active_bytes": 1_024,
        "mlx_cache_bytes": 2_048,
        "mlx_peak_bytes": 4_096,
        "process_footprint_bytes": 8_192,
        "process_footprint_source": "task_vm_info",
        "system_pressure": "normal",
        "reported_summed_total_bytes": None,
    }
    timestamp = "2026-08-06T12:00:01Z"
    raw_observations: list[dict[str, Any]] = []
    ordered_observations: list[dict[str, Any]] = []
    request_windows: list[dict[str, Any]] = []
    resource_records: list[dict[str, Any]] = []
    process_profiles: dict[str, str] = {}
    successful_process_accesses: dict[str, int] = {}

    def durations(mode: str, ordinal: int) -> dict[str, Any]:
        total = 10_000 + ordinal
        if mode == "stage_instrumented":
            stages = {
                stage: {"status": "observed", "duration_ns": total + index}
                for index, stage in enumerate(sorted(validator.ROUTER_TIMING_STAGES))
            }
            stages["dequantization"] = {
                "status": "not_applicable",
                "reason": validator.ROUTER_F32_DEQUANTIZATION_REASON,
            }
            return stages
        return {
            "dequantization": {
                "status": "not_applicable",
                "reason": validator.ROUTER_F32_DEQUANTIZATION_REASON,
            },
            "total_evaluated_router": {
                "status": "observed",
                "duration_ns": total,
            },
            "end_to_end_router_command": {
                "status": "observed",
                "duration_ns": total + 1_000,
            },
        }

    def append_observation(
        *,
        observation_id: str,
        case_id: str,
        process_id: str,
        observation_kind: str,
        run_index: int,
        process_state: str,
        condition: str,
        instrumentation_mode: str,
        schedule_step: str,
        source_kind: str,
        timing_profile: str,
        canonical_output: dict[str, Any] | None,
        series_kind: str | None = None,
        replication_role: str | None = None,
        benchmark_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ordinal = len(raw_observations)
        stage_durations = durations(instrumentation_mode, ordinal)
        output_sha256 = outputs[case_id]["complete_output_sha256"]
        observation = {
            "observation_id": observation_id,
            "run_index": run_index,
            "batch_id": batch_id,
            "case_id": case_id,
            "process_replication_id": process_id,
            "observation_kind": observation_kind,
            "process_state": process_state,
            "condition": condition,
            "instrumentation_mode": instrumentation_mode,
            "started_at_utc": timestamp,
            "completed_at_utc": timestamp,
            "monotonic_clock": "perf_counter_ns",
            "durations_ns": stage_durations,
            "status": "passed",
            "requested_device": "gpu",
            "selected_device": "gpu",
            "fallback_used": False,
            "evaluated": True,
            "synchronized": True,
            "output_sha256": output_sha256,
            "correctness_passed": True,
        }
        raw_observations.append(observation)
        ledger = {
            "global_order_index": ordinal,
            "observation_id": observation_id,
            "schedule_step": schedule_step,
            "source_kind": source_kind,
            "batch_id": batch_id,
            "case_id": case_id,
            "process_replication_id": process_id,
            "observation_kind": observation_kind,
            "run_index": run_index,
            "orchestration_status": "accepted",
            "identity_disposition": "unique",
        }
        if benchmark_id is not None:
            ledger.update({
                "benchmark_id": benchmark_id,
                "series_kind": series_kind,
                "replication_role": replication_role,
            })
        ordered_observations.append(ledger)
        request_windows.append({
            "observation_id": observation_id,
            "batch_id": batch_id,
            "case_id": case_id,
            "schedule_step": schedule_step,
            "source_kind": source_kind,
            "process_replication_id": process_id,
            "timing_profile": timing_profile,
            "started_at_utc": timestamp,
            "completed_at_utc": timestamp,
            "host_wall_duration_ns": 1_000 + ordinal,
            "host_monotonic_clock": "rust_std_instant",
            "request_sent": True,
            "status": "passed",
        })
        process_profiles.setdefault(process_id, timing_profile)
        if process_profiles[process_id] != timing_profile:
            raise AssertionError("fixture process changed timing profile")
        force_read = series_kind in {"costly_real", "first_process_costly"}
        access_count = successful_process_accesses.get(process_id, 0)
        read_and_cached = force_read or access_count == 0
        successful_process_accesses[process_id] = access_count + 1
        resource = {
            "observation_id": observation_id,
            "source_kind": source_kind,
            "backend": "apple-mlx",
            "requested_device": "gpu",
            "selected_device": "gpu",
            "fallback_used": False,
            "evaluated": True,
            "synchronized": True,
            "output_sha256": output_sha256,
            "correctness_passed": True,
            "canonical_output": deepcopy(canonical_output),
            "memory_gauges": deepcopy(gauges),
            "monotonic_clock": "perf_counter_ns",
            "instrumentation_mode": instrumentation_mode,
            "timing_stages": deepcopy(stage_durations),
            "application_tensor_bytes_read": 1_048_576 if read_and_cached else 0,
            "tensor_cache_outcome": "read_and_cached" if read_and_cached else "cache_hit",
            "canonical_output_retention": (
                "complete" if canonical_output is not None else "hash_only_passing_timing"
            ),
            "status": "passed",
            "failure": None,
        }
        resource_records.append(resource)
        return observation, resource

    correctness_cases: list[dict[str, Any]] = []
    correctness_process = f"{batch_id}-correctness-worker"
    for case_id in case_order:
        attempts: list[dict[str, Any]] = []
        step = "single_row_correctness" if case_id == single_case else "two_row_correctness"
        label = "single" if case_id == single_case else "two-row"
        for attempt_index in range(15):
            kind = "warmup" if attempt_index < 5 else "measurement"
            run_index = attempt_index if kind == "warmup" else attempt_index - 5
            observation_id = (
                f"{batch_id}-{label}-correctness-{kind}-{run_index:02d}"
            )
            _observation, resource = append_observation(
                observation_id=observation_id,
                case_id=case_id,
                process_id=correctness_process,
                observation_kind=kind,
                run_index=run_index,
                process_state="reused_process",
                condition="warm",
                instrumentation_mode="minimally_instrumented",
                schedule_step=step,
                source_kind="correctness_attempt",
                timing_profile="minimal",
                canonical_output=outputs[case_id],
            )
            attempts.append({
                "attempt_id": observation_id,
                "attempt_index": attempt_index,
                "observation_kind": kind,
                "run_index": run_index,
                "process_replication_id": correctness_process,
                "canonical_output": deepcopy(outputs[case_id]),
                "comparison": deepcopy(comparisons[case_id]),
                "memory_gauges": deepcopy(resource["memory_gauges"]),
                "requested_device": "gpu",
                "selected_device": "gpu",
                "fallback_used": False,
                "evaluated": True,
                "synchronized": True,
                "status": "passed",
                "passed": True,
            })
        correctness_cases.append({
            "case_id": case_id,
            "row_count": outputs[case_id]["row_count"],
            "oracle_output": deepcopy(outputs[case_id]),
            "mlx_output": deepcopy(outputs[case_id]),
            "comparison": deepcopy(comparisons[case_id]),
            "attempts": attempts,
        })

    timing_series: list[dict[str, Any]] = []
    timing_plan = validator._expected_passing_timing_plan(batch_id, batch_order)
    for series_index, plan in enumerate(timing_plan):
        observation_ids: list[str] = []
        count = plan["warmup_count"] + plan["measurement_count"]
        profile = (
            "costly"
            if plan["series_kind"] in {"costly_real", "first_process_costly"}
            else "stage"
            if plan["series_kind"] == "stage_diagnostic"
            else "minimal"
        )
        for position in range(count):
            kind = "warmup" if position < plan["warmup_count"] else "measurement"
            run_index = position if kind == "warmup" else position - plan["warmup_count"]
            observation_id = f"{batch_id}-timing-{series_index:02d}-{kind}-{run_index:02d}"
            append_observation(
                observation_id=observation_id,
                case_id=plan["case_id"],
                process_id=plan["process_replication_id"],
                observation_kind=kind,
                run_index=run_index,
                process_state=plan["process_state"],
                condition=plan["condition"],
                instrumentation_mode=plan["instrumentation_mode"],
                schedule_step=plan["schedule_step"],
                source_kind="timing_series",
                timing_profile=profile,
                canonical_output=None,
                series_kind=plan["series_kind"],
                replication_role=plan["replication_role"],
                benchmark_id=plan["benchmark_id"],
            )
            observation_ids.append(observation_id)
        timing_series.append({
            **{
                field: plan[field]
                for field in (
                    "benchmark_id", "case_id", "series_kind", "replication_role",
                    "process_replication_id", "process_state", "condition",
                    "instrumentation_mode", "warmup_count", "measurement_count",
                )
            },
            "attempted_warmup_count": plan["warmup_count"],
            "attempted_measurement_count": plan["measurement_count"],
            "retained_observation_count": count,
            "observation_ids": observation_ids,
        })

    process_lifecycles: list[dict[str, Any]] = []
    for process_id, profile in process_profiles.items():
        for event, outcome in (
            ("spawn", "started"),
            ("spawn", "passed"),
            ("shutdown", "graceful"),
        ):
            process_lifecycles.append({
                "event_order": len(process_lifecycles),
                "recorded_at_utc": timestamp,
                "process_replication_id": process_id,
                "timing_profile": profile,
                "event": event,
                "outcome": outcome,
                "details": {},
            })

    before = environment_fixtures._collect()
    after = environment_fixtures._collect(capture_phase="after")
    for snapshot in (before, after):
        for name in ("repository_commit", "pulsarmlx_version"):
            snapshot["observations"][name]["value"] = SOURCE_COMMIT
    benchmark_resources = environment_fixtures.environment.extract_benchmark_resources({
        "backend": "apple-mlx",
        "worker": {"result_resource_records": resource_records},
    })
    environment = environment_fixtures.environment.combine_environment_evidence(
        before_snapshot=before,
        after_snapshot=after,
        after_unavailable_reason=None,
        benchmark_resources=benchmark_resources,
    )

    record = valid_evidence(experiment_id)
    publication, oracle_identity = external_oracle_identity()
    record.update({
        "evidence_scope": "external_checkpoint",
        "actual_status": "passed",
        "started_at_utc": "2026-08-06T12:00:00Z",
        "completed_at_utc": "2026-08-06T12:10:00Z",
        "batch_id": batch_id,
        "process_replication_id": correctness_process,
        "second_batch": {
            "status": "unavailable",
            "reason": "no linked counterbalanced batch was supplied in this record",
            "between_batch_variation_measured": False,
        },
        "oracle": oracle_identity,
        "environment": environment,
        "correctness": {
            "passed": True,
            "compared_count": 384,
            "id_mismatch_count": 0,
            "order_mismatch_count": 0,
            "numeric_mismatch_count": 0,
            "first_mismatch": None,
            "maximum_absolute_error": 0.0,
            "mean_absolute_error": 0.0,
            "rmse": 0.0,
            "maximum_relative_error": 0.0,
            "absolute_tolerance": 0.0005,
            "relative_tolerance": 0.0005,
            "non_finite_policy": "reject",
            "non_finite_count": 0,
            "deterministic_repeat_count": 20,
            "repeat_output_hashes": sorted(
                [outputs[single_case]["complete_output_sha256"]] * 10
                + [outputs[two_row_case]["complete_output_sha256"]] * 10
            ),
        },
        "raw_observations": raw_observations,
        "summaries": [],
        "warnings": ["Bounded external layer-0 router validation only."],
        "failures": [],
    })
    record["execution"]["exit_code"] = 0
    record["source_worktree_after"] = {
        "state": "declared_evidence_outputs_only",
        "paths": [f"docs/research/raw/002-router-parity/{experiment_id}.json"],
    }
    record["tensor"].update({
        "absolute_offset": publication["tensor"]["absolute_offset"],
        "encoded_length": publication["tensor"]["encoded_length_bytes"],
        "end_offset": publication["tensor"]["exclusive_end_offset"],
        "encoded_sha256": publication["tensor"]["encoded_sha256"],
    })
    record["input"].update({
        "canonical_sha256": publication["input"]["canonical_f32le_sha256"],
        "selected_rows": [0, 1],
    })
    record["claim_boundary"]["unsupported_interpretations"].remove(
        "real_checkpoint_routing"
    )
    record["artifacts"] = [
        {
            "kind": "frozen_protocol",
            "path": "docs/research/EXPERIMENT_PROTOCOL.md",
            "sha256": _sha256(PROTOCOL),
        },
        {
            "kind": "model_manifest",
            "path": "docs/research/MODEL_MANIFEST.json",
            "sha256": _sha256(MODEL_MANIFEST),
        },
        {
            "kind": "real_router_input_and_independent_cpu_oracle",
            "path": "fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json",
            "sha256": _sha256(REAL_ORACLE_PUBLICATION),
        },
    ]
    record["router_detail"] = {
        "detail_schema": "pulsarmlx.research.router-detail",
        "detail_schema_version": "1.0.0",
        "source_candidate_sha256": SHA_A,
        "source_environment_sha256": validator._canonical_json_sha256(environment),
        "application_read_semantics": "application_positional_read_not_physical_disk_io",
        "batch_order": batch_order,
        "ordered_observations": ordered_observations,
        "correctness_cases": correctness_cases,
        "timing_series": timing_series,
        "process_lifecycles": process_lifecycles,
        "request_windows": request_windows,
        "resource_records": resource_records,
        "terminal_failure": None,
    }

    summary_series = next(
        series
        for series in timing_series
        if series["series_kind"] == "costly_real"
        and series["case_id"] == case_order[0]
    )
    summary_ids = summary_series["observation_ids"][5:]
    raw_by_id = {item["observation_id"]: item for item in raw_observations}
    samples = [
        raw_by_id[observation_id]["durations_ns"]["total_evaluated_router"][
            "duration_ns"
        ]
        for observation_id in summary_ids
    ]
    record["summaries"] = [{
        "summary_id": f"{batch_id}-costly-first-case-total",
        "statistics_algorithm": "pulsarmlx-type7-v1",
        "group": {
            "case_id": case_order[0],
            "batch_id": batch_id,
            "observation_kind": "measurement",
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "stage": "total_evaluated_router",
        },
        "included_observation_ids": summary_ids,
        "excluded_observation_ids": [],
        "unfiltered_summary": validator.summarize_nanoseconds(samples),
    }]
    return record


def _failed_external_correctness_prefix(*, invalid_output: bool) -> dict[str, Any]:
    """Reduce a complete model-free record to one truthful evaluated failure."""

    from scripts.research.tests import test_environment as environment_fixtures

    record = _passing_external_record(
        "f002-evaluated-correctness-failure",
        "batch-evaluated-correctness-failure",
        "single_row_first",
    )
    detail = record["router_detail"]
    failure = {
        "code": "evaluated_correctness_attempt_failed",
        "message": "the evaluated correctness attempt did not complete its gate",
        "stage": "correctness_gate",
    }
    observation = deepcopy(record["raw_observations"][0])
    observation.update({
        "status": "failed",
        "correctness_passed": False,
        "failure": failure,
    })
    case = deepcopy(detail["correctness_cases"][0])
    attempt = case["attempts"][0]
    attempt.update({"status": "failed", "passed": False, "failure": failure})
    case["attempts"] = [attempt]
    window = deepcopy(detail["request_windows"][0])
    window.update({"status": "failed", "failure": failure})
    resource = deepcopy(detail["resource_records"][0])
    resource.update({
        "status": "failed",
        "correctness_passed": False,
        "failure": failure,
    })
    if invalid_output:
        attempt["canonical_output"] = None
        attempt["comparison"] = None
        case["mlx_output"] = None
        case["comparison"] = None
        resource["canonical_output"] = None
        resource["canonical_output_retention"] = "unavailable_invalid_output"
        correctness: dict[str, Any] = {
            "status": "unavailable",
            "reason": "the evaluated worker output was invalid before comparison",
            "source": "evaluated_output_invalid",
        }
    else:
        correctness = {
            "passed": True,
            "compared_count": 128,
            "id_mismatch_count": 0,
            "order_mismatch_count": 0,
            "numeric_mismatch_count": 0,
            "first_mismatch": None,
            "maximum_absolute_error": 0.0,
            "mean_absolute_error": 0.0,
            "rmse": 0.0,
            "maximum_relative_error": 0.0,
            "absolute_tolerance": 0.0005,
            "relative_tolerance": 0.0005,
            "non_finite_policy": "reject",
            "non_finite_count": 0,
            "deterministic_repeat_count": 0,
            "repeat_output_hashes": [],
        }

    detail.update({
        "ordered_observations": [deepcopy(detail["ordered_observations"][0])],
        "correctness_cases": [case],
        "timing_series": [],
        "process_lifecycles": deepcopy(detail["process_lifecycles"][:3]),
        "request_windows": [window],
        "resource_records": [resource],
    })
    detail["process_lifecycles"][2]["outcome"] = "failed"
    benchmark_resources = environment_fixtures.environment.extract_benchmark_resources({
        "backend": "apple-mlx",
        "worker": {"result_resource_records": [resource]},
    })
    environment = environment_fixtures.environment.combine_environment_evidence(
        before_snapshot=record["environment"]["before_snapshot"],
        after_snapshot=record["environment"]["after_snapshot"],
        after_unavailable_reason=None,
        benchmark_resources=benchmark_resources,
    )
    record.update({
        "actual_status": "failed",
        "environment": environment,
        "correctness": correctness,
        "raw_observations": [observation],
        "summaries": [],
        "failures": [failure],
    })
    record["execution"]["exit_code"] = 1
    record["claim_boundary"].update({"status": "failed", "capabilities": []})
    detail["source_environment_sha256"] = validator._canonical_json_sha256(environment)
    return record


class EvidenceValidatorContractTests(unittest.TestCase):
    maxDiff = None

    def _run_validator(self, records: dict[str, dict[str, object]]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-validator-test-") as temp:
            input_directory = Path(temp) / "evidence"
            input_directory.mkdir()
            for filename, record in records.items():
                (input_directory / filename).write_text(
                    json.dumps(record, sort_keys=True, indent=2, allow_nan=True) + "\n",
                    encoding="utf-8",
                )
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
                check=False,
                capture_output=True,
                text=True,
            )

    def _assert_accepted(self, record: dict[str, object]) -> None:
        experiment_id = str(record["experiment_id"])
        completed = self._run_validator({f"{experiment_id}.json": record})
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"validator rejected valid fixture (exit {completed.returncode})",
        )

    def _assert_rejected(
        self,
        records: dict[str, dict[str, object]],
        expected_code: str,
        *,
        forbidden_output: str | None = None,
    ) -> None:
        completed = self._run_validator(records)
        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0, msg="validator accepted invalid evidence")
        self.assertIn(
            expected_code,
            output,
            msg=f"validator did not report stable code {expected_code!r}",
        )
        if forbidden_output is not None:
            self.assertNotIn(forbidden_output, output, msg="validator disclosed a private value")

    def test_accepts_a_structurally_and_semantically_valid_fixture(self) -> None:
        self._assert_accepted(valid_evidence())

    def test_external_oracle_identity_is_bound_to_the_frozen_publication(self) -> None:
        publication, identity = external_oracle_identity()
        record = valid_evidence("f002-router-real-oracle-identity")
        record["evidence_scope"] = "external_checkpoint"
        record["input"]["canonical_sha256"] = publication["input"][  # type: ignore[index]
            "canonical_f32le_sha256"
        ]
        record["tensor"]["encoded_sha256"] = publication["tensor"][  # type: ignore[index]
            "encoded_sha256"
        ]
        record["oracle"] = identity

        validator._validate_oracle_identity(record, REPOSITORY_ROOT)

        mutations = {
            "oracle_id": "f002-scalar-f32-v1",
            "revision": "0" * 40,
            "generation_command": "python3 scripts/research/router_oracle.py --changed",
            "input_fixture_sha256": "0" * 64,
            "tensor_sha256": "1" * 64,
            "output_sha256": "2" * 64,
            "independence_statement": "unverified implementation",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                mutated = deepcopy(record)
                mutated["oracle"][field] = value  # type: ignore[index]
                with self.assertRaises(validator.EvidenceValidationError):
                    validator._validate_oracle_identity(mutated, REPOSITORY_ROOT)

        with tempfile.TemporaryDirectory(prefix="pulsarmlx-mutated-oracle-") as temp:
            repository_root = Path(temp)
            publication_path = repository_root / REAL_ORACLE_PUBLICATION.relative_to(
                REPOSITORY_ROOT
            )
            publication_path.parent.mkdir(parents=True)
            mutated_publication = deepcopy(publication)
            mutated_publication["status"] = "failed"
            publication_path.write_text(
                json.dumps(mutated_publication, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(validator.EvidenceValidationError):
                validator._load_real_oracle_identity(repository_root)

    def test_execution_shape_names_the_weight_before_matmul_transpose(self) -> None:
        record = valid_evidence()
        tensor = record["tensor"]
        self.assertEqual(tensor["reader_shape"], [128, 2048])
        self.assertEqual(tensor["execution_shape"], [128, 2048])

        transposed_rhs_shape = valid_evidence("f002-router-transposed-rhs-shape")
        transposed_rhs_shape["tensor"]["execution_shape"] = [2048, 128]
        self._assert_rejected(
            {
                f"{transposed_rhs_shape['experiment_id']}.json": transposed_rhs_shape
            },
            "semantic_relationship",
        )

    def test_rejects_schema_identity_and_version_mutations(self) -> None:
        mutations = (
            ("evidence_schema", "another.research.envelope"),
            ("evidence_schema_version", "2.0.0"),
            ("payload_schema", "another.router.payload"),
            ("payload_schema_version", "2.0.0"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                record = valid_evidence()
                record[field] = value
                self._assert_rejected(
                    {f"{record['experiment_id']}.json": record},
                    "unsupported_schema_identity",
                )

    def test_legacy_envelope_resolves_immutable_protocol_bytes_from_git(self) -> None:
        record = valid_evidence("f002-router-legacy-history")
        record["evidence_schema_version"] = "1.1.0"
        record["payload_schema_version"] = "1.0.0"
        record["source_commit"] = LEGACY_PROTOCOL_COMMIT
        record["protocol"] = {
            "protocol_id": "f002-router-protocol-amendment-001",
            "protocol_version": "1.1.0",
            "path": "docs/research/EXPERIMENT_PROTOCOL.md",
            "sha256": LEGACY_PROTOCOL_SHA256,
            "order_seed": 22002,
        }
        record["artifacts"][0]["sha256"] = LEGACY_PROTOCOL_SHA256
        self._assert_accepted(record)

        tampered = deepcopy(record)
        tampered["protocol"]["sha256"] = "0" * 64
        tampered["artifacts"][0]["sha256"] = "0" * 64
        self._assert_rejected(
            {f"{tampered['experiment_id']}.json": tampered},
            "semantic_relationship",
        )

    def test_legacy_envelope_rejects_unavailable_protocol_history(self) -> None:
        record = valid_evidence("f002-router-legacy-missing-history")
        record["evidence_schema_version"] = "1.1.0"
        record["payload_schema_version"] = "1.0.0"
        record["source_commit"] = "f" * 40
        record["protocol"] = {
            "protocol_id": "f002-router-protocol-amendment-001",
            "protocol_version": "1.1.0",
            "path": "docs/research/EXPERIMENT_PROTOCOL.md",
            "sha256": LEGACY_PROTOCOL_SHA256,
            "order_seed": 22002,
        }
        record["artifacts"][0]["sha256"] = LEGACY_PROTOCOL_SHA256
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "semantic_relationship",
        )

    def test_first_request_abort_retains_truthful_timing_and_unavailable_correctness(self) -> None:
        record, by_id = _first_request_abort_detail()
        parsed, _ = validator._validate_observations(
            {
                "evidence_scope": "external_checkpoint",
                "batch_id": "batch-a",
                "raw_observations": list(by_id.values()),
            }
        )
        validator._validate_router_detail(record, parsed)
        validator._validate_correctness(
            {
                "actual_status": "aborted",
                "correctness": {
                    "status": "unavailable",
                    "reason": "worker startup failed before evaluation",
                    "source": "pre_execution_abort",
                },
            }
        )

        transient = deepcopy(record)
        transient["router_detail"]["request_windows"][0]["status"] = "result_received"
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_router_detail(transient, parsed)

        non_boolean_request = deepcopy(record)
        non_boolean_request["router_detail"]["request_windows"][0][
            "request_sent"
        ] = 0
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_router_detail(non_boolean_request, parsed)

        fabricated = deepcopy(record)
        fabricated["router_detail"]["resource_records"][0][
            "application_tensor_bytes_read"
        ] = 0
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_router_detail(fabricated, parsed)

        for mutation in ("ledger", "window", "resource", "lifecycle"):
            tampered = deepcopy(record)
            if mutation == "ledger":
                tampered["router_detail"]["ordered_observations"][0]["run_index"] = 1
            elif mutation == "window":
                tampered["router_detail"]["request_windows"][0]["schedule_step"] = "wrong_step"
            elif mutation == "resource":
                tampered["router_detail"]["resource_records"][0]["selected_device"] = "gpu"
            else:
                tampered["router_detail"]["process_lifecycles"][1]["event_order"] = 9
            with self.assertRaises(validator.EvidenceValidationError):
                validator._validate_router_detail(tampered, parsed)

    def test_owned_worker_pre_evaluation_abort_lifecycles_are_distinct(self) -> None:
        for request_sent in (False, True):
            with self.subTest(request_sent=request_sent):
                record, by_id = _owned_pre_evaluation_abort_detail(
                    request_sent=request_sent
                )
                parsed, _ = validator._validate_observations({
                    "evidence_scope": "external_checkpoint",
                    "batch_id": "batch-a",
                    "raw_observations": list(by_id.values()),
                })
                validator._validate_router_detail(record, parsed)

                wrong_disposition = deepcopy(record)
                wrong_disposition["router_detail"]["request_windows"][0][
                    "request_sent"
                ] = not request_sent
                with self.assertRaises(validator.EvidenceValidationError):
                    validator._validate_router_detail(wrong_disposition, parsed)

                missing_shutdown = deepcopy(record)
                missing_shutdown["router_detail"]["process_lifecycles"].pop()
                with self.assertRaises(validator.EvidenceValidationError):
                    validator._validate_router_detail(missing_shutdown, parsed)

        timestamp_record, timestamp_by_id = _owned_pre_evaluation_abort_detail(
            request_sent=False
        )
        parsed, _ = validator._validate_observations({
            "evidence_scope": "external_checkpoint",
            "batch_id": "batch-a",
            "raw_observations": list(timestamp_by_id.values()),
        })
        wrong_stage = deepcopy(timestamp_record)
        for failure in (
            wrong_stage["router_detail"]["request_windows"][0]["failure"],
            wrong_stage["router_detail"]["resource_records"][0]["failure"],
            wrong_stage["router_detail"]["correctness_cases"][0]["attempts"][0]["failure"],
        ):
            failure["stage"] = "router_execution"
        timestamp_observation = next(iter(timestamp_by_id))
        timestamp_by_id[timestamp_observation]["failure"]["stage"] = "router_execution"
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_router_detail(wrong_stage, parsed)

    def test_full_first_request_abort_record_validates_without_fabricated_correctness(self) -> None:
        from scripts.research.tests import test_environment as environment_fixtures

        record = valid_evidence("f002-router-first-request-abort")
        detail_record, by_id = _first_request_abort_detail()
        publication, oracle_identity = external_oracle_identity()
        before = environment_fixtures._collect()
        after = environment_fixtures._collect(capture_phase="after")
        for snapshot in (before, after):
            for name in ("repository_commit", "pulsarmlx_version"):
                snapshot["observations"][name]["value"] = SOURCE_COMMIT
        resources = environment_fixtures.environment.extract_benchmark_resources(
            {
                "backend": "apple-mlx",
                "worker": {
                    "result_resource_records": [{
                        "observation_id": next(iter(by_id)),
                        "status": "aborted",
                        "backend": "apple-mlx",
                        "requested_device": "gpu",
                        "selected_device": "not_available",
                        "fallback_used": False,
                        "evaluated": False,
                        "synchronized": False,
                        "memory_gauges": None,
                    }]
                },
            }
        )
        environment = environment_fixtures.environment.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after,
            after_unavailable_reason=None,
            benchmark_resources=resources,
        )
        record.update({
            "evidence_scope": "external_checkpoint",
            "actual_status": "aborted",
            "batch_id": "batch-a",
            "process_replication_id": "batch-a-correctness-worker",
            "second_batch": {
                "status": "unavailable",
                "reason": "the first request aborted before a later batch could begin",
                "between_batch_variation_measured": False,
            },
            "oracle": oracle_identity,
            "environment": environment,
            "correctness": {
                "status": "unavailable",
                "reason": "worker startup failed before evaluation",
                "source": "pre_execution_abort",
            },
            "raw_observations": list(by_id.values()),
            "summaries": [],
            "warnings": ["The first Apple request aborted before evaluation."],
            "failures": [{
                "code": "worker_startup_failed",
                "message": "the worker did not start",
                "stage": "worker_startup",
            }],
            "router_detail": detail_record["router_detail"],
        })
        record["execution"]["exit_code"] = 1
        record["claim_boundary"]["status"] = "blocked"
        record["claim_boundary"]["capabilities"] = []
        record["claim_boundary"]["unsupported_interpretations"].remove(
            "real_checkpoint_routing"
        )
        record["tensor"].update({
            "absolute_offset": publication["tensor"]["absolute_offset"],
            "encoded_length": publication["tensor"]["encoded_length_bytes"],
            "end_offset": publication["tensor"]["exclusive_end_offset"],
            "encoded_sha256": publication["tensor"]["encoded_sha256"],
        })
        record["input"].update({
            "canonical_sha256": publication["input"]["canonical_f32le_sha256"],
            "selected_rows": [0, 1],
        })
        record["router_detail"]["source_environment_sha256"] = (
            validator._canonical_json_sha256(environment)
        )
        record["artifacts"] = [
            {
                "kind": "frozen_protocol",
                "path": "docs/research/EXPERIMENT_PROTOCOL.md",
                "sha256": _sha256(PROTOCOL),
            },
            {
                "kind": "model_manifest",
                "path": "docs/research/MODEL_MANIFEST.json",
                "sha256": _sha256(MODEL_MANIFEST),
            },
            {
                "kind": "real_router_input_and_independent_cpu_oracle",
                "path": "fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json",
                "sha256": _sha256(REAL_ORACLE_PUBLICATION),
            },
        ]

        validator.validate_record(record)

        valid_gauges = {
            "mlx_active_bytes": 1,
            "mlx_cache_bytes": 2,
            "mlx_peak_bytes": 3,
            "process_footprint_bytes": 4,
            "process_footprint_source": "task_vm_info",
            "system_pressure": "normal",
            "reported_summed_total_bytes": 7,
        }
        mutations: dict[str, dict[str, object]] = {}

        altered_oracle = deepcopy(record)
        altered_output = altered_oracle["router_detail"]["correctness_cases"][0][
            "oracle_output"
        ]
        altered_output["logits"][0] = struct.unpack(
            "<f", struct.pack("<f", altered_output["logits"][0] + 1.0)
        )[0]
        altered_components = [
            validator._f32le(altered_output["logits"]),
            validator._f32le(altered_output["full_probabilities"]),
            validator._u32le(altered_output["selected_expert_ids"][0]),
            validator._f32le(altered_output["selected_probabilities"][0]),
            validator._f32le(altered_output["normalized_weights"][0]),
        ]
        altered_output["logits_f32le_sha256"] = hashlib.sha256(
            altered_components[0]
        ).hexdigest()
        altered_output["complete_output_sha256"] = hashlib.sha256(
            b"".join(altered_components)
        ).hexdigest()
        mutations["self_consistent_altered_oracle"] = altered_oracle

        attempt_process = deepcopy(record)
        attempt_process["router_detail"]["correctness_cases"][0]["attempts"][0][
            "process_replication_id"
        ] = "different-process"
        mutations["attempt_process_join"] = attempt_process

        attempt_status = deepcopy(record)
        attempt_status["router_detail"]["correctness_cases"][0]["attempts"][0][
            "status"
        ] = "failed"
        mutations["attempt_status_join"] = attempt_status

        fabricated_evaluation = deepcopy(record)
        fabricated_attempt = fabricated_evaluation["router_detail"]["correctness_cases"][0][
            "attempts"
        ][0]
        fabricated_attempt.update({
            "selected_device": "gpu",
            "evaluated": True,
            "synchronized": True,
            "memory_gauges": valid_gauges,
        })
        mutations["aborted_attempt_fabricates_evaluation"] = fabricated_evaluation

        sent_startup_abort = deepcopy(record)
        sent_startup_abort["router_detail"]["request_windows"][0]["request_sent"] = True
        mutations["startup_abort_request_sent"] = sent_startup_abort

        resource_failure = deepcopy(record)
        resource_failure["router_detail"]["resource_records"][0]["failure"][
            "message"
        ] = "different failure"
        mutations["resource_failure_join"] = resource_failure

        top_failure = deepcopy(record)
        top_failure["failures"][0]["message"] = "different failure"
        mutations["top_failure_join"] = top_failure

        empty_memory = deepcopy(record)
        empty_memory["router_detail"]["resource_records"][0]["memory_gauges"] = {}
        mutations["empty_resource_memory"] = empty_memory

        malformed_case_output = deepcopy(record)
        malformed_case_output["router_detail"]["correctness_cases"][0][
            "mlx_output"
        ] = "not-an-output"
        mutations["malformed_partial_case_output"] = malformed_case_output

        malformed_window_failure = deepcopy(record)
        malformed_window_failure["router_detail"]["request_windows"][0][
            "failure"
        ] = "not-a-failure"
        mutations["malformed_window_failure"] = malformed_window_failure

        invalid_lifecycle = deepcopy(record)
        failed_event = invalid_lifecycle["router_detail"]["process_lifecycles"][1]
        failed_event["event_order"] = 2
        invalid_lifecycle["router_detail"]["process_lifecycles"].insert(1, {
            "event_order": 1,
            "recorded_at_utc": "2026-08-06T12:00:00Z",
            "process_replication_id": "batch-a-correctness-worker",
            "timing_profile": "minimal",
            "event": "spawn",
            "outcome": "passed",
            "details": {},
        })
        mutations["spawn_passed_then_failed"] = invalid_lifecycle

        flat_selected = deepcopy(record)
        flat_selected["router_detail"]["correctness_cases"][0]["oracle_output"][
            "selected_expert_ids"
        ] = flat_selected["router_detail"]["correctness_cases"][0]["oracle_output"][
            "selected_expert_ids"
        ][0]
        mutations["flat_selected_rows"] = flat_selected

        for name, mutated in mutations.items():
            with self.subTest(name=name), self.assertRaises(
                validator.EvidenceValidationError
            ):
                validator.validate_record(mutated)

    def test_complete_external_schedule_validates_all_260_joined_observations(self) -> None:
        record = _passing_external_record(
            "f002-complete-router-schedule",
            "batch-complete-router-schedule",
            "single_row_first",
        )

        validator.validate_record(record)
        self.assertEqual(len(record["raw_observations"]), 260)
        self.assertEqual(len(record["router_detail"]["timing_series"]), 38)

        mutations: dict[str, dict[str, Any]] = {}
        reordered_plan = deepcopy(record)
        reordered_plan["router_detail"]["timing_series"][0:2] = reversed(
            reordered_plan["router_detail"]["timing_series"][0:2]
        )
        mutations["reordered_exact_timing_plan"] = reordered_plan

        changed_schedule_step = deepcopy(record)
        changed_schedule_step["router_detail"]["ordered_observations"][30][
            "schedule_step"
        ] = "wrong_step"
        mutations["changed_schedule_step"] = changed_schedule_step

        changed_cache_sequence = deepcopy(record)
        changed_cache_sequence["router_detail"]["resource_records"][0].update({
            "tensor_cache_outcome": "cache_hit",
            "application_tensor_bytes_read": 0,
        })
        mutations["changed_process_cache_sequence"] = changed_cache_sequence

        changed_top_projection = deepcopy(record)
        changed_top_projection["correctness"]["compared_count"] = 383
        mutations["changed_top_correctness_projection"] = changed_top_projection

        partial_attempt_counts = deepcopy(record)
        partial_attempt_counts["router_detail"]["timing_series"][10][
            "attempted_measurement_count"
        ] = 9
        mutations["passing_series_partial_attempt_count"] = partial_attempt_counts

        for name, mutated in mutations.items():
            with self.subTest(name=name), self.assertRaises(
                validator.EvidenceValidationError
            ):
                validator.validate_record(mutated)

    def test_evaluated_correctness_failure_retains_zero_measurement_prefix(self) -> None:
        record = _failed_external_correctness_prefix(invalid_output=False)

        validator.validate_record(record)
        self.assertEqual(record["correctness"]["deterministic_repeat_count"], 0)
        self.assertEqual(record["correctness"]["repeat_output_hashes"], [])
        self.assertEqual(len(record["raw_observations"]), 1)

        fabricated_hash = deepcopy(record)
        fabricated_hash["correctness"]["deterministic_repeat_count"] = 1
        fabricated_hash["correctness"]["repeat_output_hashes"] = [SHA_A]
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(fabricated_hash)

    def test_evaluated_invalid_output_uses_distinct_correctness_unavailability(self) -> None:
        record = _failed_external_correctness_prefix(invalid_output=True)

        validator.validate_record(record)
        self.assertEqual(
            record["correctness"]["source"],
            "evaluated_output_invalid",
        )

        relabeled = deepcopy(record)
        relabeled["correctness"]["source"] = "pre_execution_abort"
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(relabeled)

    def test_complete_linked_batches_require_reversed_roles_and_exact_target_hash(self) -> None:
        source = _passing_external_record(
            "f002-linked-router-source",
            "batch-linked-router-source",
            "single_row_first",
        )
        target = _passing_external_record(
            "f002-linked-router-target",
            "batch-linked-router-target",
            "two_row_first",
        )
        source["second_batch"] = {
            "status": "observed",
            "between_batch_variation_measured": True,
            "linked_experiment_id": target["experiment_id"],
            "linked_batch_id": target["batch_id"],
            "linked_record_sha256": validator._canonical_record_sha256(target),
        }

        validator.validate_record(source)
        validator.validate_record(target)
        validator._validate_second_batch_cross_records([source, target])

        failed_target = deepcopy(target)
        terminal_failure = {
            "code": "later_batch_identity_recheck_failed",
            "message": "the later batch failed its post-request identity recheck",
            "stage": "post_request_identity",
        }
        failed_target.update({
            "actual_status": "failed",
            "failures": [terminal_failure],
        })
        failed_target["execution"]["exit_code"] = 1
        failed_target["claim_boundary"].update({"status": "failed", "capabilities": []})
        failed_target["router_detail"]["terminal_failure"] = {
            "phase": "post_request_identity",
            "process_replication_id": None,
            "failure": terminal_failure,
        }
        source_for_failed_target = deepcopy(source)
        source_for_failed_target["second_batch"]["linked_record_sha256"] = (
            validator._canonical_record_sha256(failed_target)
        )
        validator.validate_record(failed_target)
        validator._validate_second_batch_cross_records(
            [source_for_failed_target, failed_target]
        )

        changed_command_target = deepcopy(failed_target)
        changed_command_target["execution"]["command"] = "different command"
        source_for_changed_command = deepcopy(source)
        source_for_changed_command["second_batch"]["linked_record_sha256"] = (
            validator._canonical_record_sha256(changed_command_target)
        )
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_second_batch_cross_records(
                [source_for_changed_command, changed_command_target]
            )

        bad_role = deepcopy(target)
        bad_role["router_detail"]["batch_order"] = "single_row_first"
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_second_batch_cross_records([source, bad_role])

        bad_hash_source = deepcopy(source)
        bad_hash_source["second_batch"]["linked_record_sha256"] = "0" * 64
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_second_batch_cross_records([bad_hash_source, target])

        reused_process_target = deepcopy(target)
        reused_process_target["raw_observations"][0]["process_replication_id"] = (
            source["raw_observations"][0]["process_replication_id"]
        )
        source_for_reused_process = deepcopy(source)
        source_for_reused_process["second_batch"]["linked_record_sha256"] = (
            validator._canonical_record_sha256(reused_process_target)
        )
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_second_batch_cross_records(
                [source_for_reused_process, reused_process_target]
            )

    def test_post_run_interference_blocks_complete_requests_without_summaries_or_claims(self) -> None:
        from scripts.research.tests import test_environment as environment_fixtures

        record = _passing_external_record(
            "f002-complete-router-interference",
            "batch-complete-router-interference",
            "single_row_first",
        )
        after = environment_fixtures._collect(
            capture_phase="after",
            workload_category="large_build",
        )
        for name in ("repository_commit", "pulsarmlx_version"):
            after["observations"][name]["value"] = SOURCE_COMMIT
        environment = environment_fixtures.environment.combine_environment_evidence(
            before_snapshot=record["environment"]["before_snapshot"],
            after_snapshot=after,
            after_unavailable_reason=None,
            benchmark_resources=record["environment"]["benchmark_resources"],
        )
        failure = {
            "code": "post_run_interference_observed",
            "message": "material workload interference was observed after the run",
            "stage": "after_environment_capture",
        }
        record.update({
            "actual_status": "blocked",
            "environment": environment,
            "summaries": [],
            "failures": [failure],
        })
        record["execution"]["exit_code"] = 1
        record["claim_boundary"].update({"status": "blocked", "capabilities": []})
        record["router_detail"]["source_environment_sha256"] = (
            validator._canonical_json_sha256(environment)
        )
        record["router_detail"]["terminal_failure"] = {
            "phase": "environment_interference",
            "process_replication_id": None,
            "failure": failure,
        }

        validator.validate_record(record)

        with_summary = deepcopy(record)
        with_summary["summaries"] = _passing_external_record(
            "f002-summary-source",
            "batch-summary-source",
            "single_row_first",
        )["summaries"]
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(with_summary)

        with_capability = deepcopy(record)
        with_capability["claim_boundary"]["capabilities"] = ["router_logits"]
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(with_capability)

    def test_unavailable_after_snapshot_blocks_complete_requests_without_claims(self) -> None:
        from scripts.research.tests import test_environment as environment_fixtures

        record = _passing_external_record(
            "f002-complete-router-after-unavailable",
            "batch-complete-router-after-unavailable",
            "single_row_first",
        )
        admitted_environment = deepcopy(record["environment"])
        environment = environment_fixtures.environment.combine_environment_evidence(
            before_snapshot=record["environment"]["before_snapshot"],
            after_snapshot=None,
            after_unavailable_reason="post-run environment capture was unavailable",
            benchmark_resources=record["environment"]["benchmark_resources"],
        )
        failure = {
            "code": "after_snapshot_unavailable",
            "message": "the post-run environment snapshot was unavailable",
            "stage": "after_environment_capture",
        }
        record.update({
            "actual_status": "blocked",
            "environment": environment,
            "summaries": [],
            "failures": [failure],
        })
        record["execution"]["exit_code"] = 1
        record["claim_boundary"].update({"status": "blocked", "capabilities": []})
        record["router_detail"]["source_environment_sha256"] = (
            validator._canonical_json_sha256(environment)
        )
        record["router_detail"]["terminal_failure"] = {
            "phase": "environment_admission_unavailable",
            "process_replication_id": None,
            "failure": failure,
        }

        validator.validate_record(record)
        self.assertEqual(environment["interference_admission"], "postponed")
        self.assertEqual(environment["after_snapshot"]["status"], "unavailable")

        observed_interference_label = deepcopy(record)
        observed_interference_label["router_detail"]["terminal_failure"]["phase"] = (
            "environment_interference"
        )
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(observed_interference_label)

        available_after_snapshot = deepcopy(record)
        available_after_snapshot["environment"] = admitted_environment
        available_after_snapshot["router_detail"]["source_environment_sha256"] = (
            validator._canonical_json_sha256(admitted_environment)
        )
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(available_after_snapshot)

        with_summary = deepcopy(record)
        with_summary["summaries"] = _passing_external_record(
            "f002-after-unavailable-summary-source",
            "batch-after-unavailable-summary-source",
            "single_row_first",
        )["summaries"]
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(with_summary)

        with_capability = deepcopy(record)
        with_capability["claim_boundary"]["capabilities"] = ["router_logits"]
        with self.assertRaises(validator.EvidenceValidationError):
            validator.validate_record(with_capability)

    def test_correctness_unavailability_cannot_replace_a_passing_result(self) -> None:
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_correctness(
                {
                    "actual_status": "passed",
                    "correctness": {
                        "status": "unavailable",
                        "reason": "not measured",
                        "source": "pre_execution_abort",
                    },
                }
            )

    def test_public_capacity_model_covers_a_260_observation_envelope(self) -> None:
        representative = valid_evidence("f002-router-capacity-model")
        output = validator._load_real_oracle_outputs(REPOSITORY_ROOT)[
            "qwen3moe-layer0-router-token0-token1-batch-v1"
        ]
        comparison = _identical_output_comparison(_public_single_row_output())
        observation_ids = [f"capacity-observation-{index:03}" for index in range(260)]
        representative["raw_observations"] = [
            {
                **deepcopy(representative["raw_observations"][0]),
                "observation_id": observation_id,
                "run_index": index,
            }
            for index, observation_id in enumerate(observation_ids)
        ]
        representative["router_detail"] = {
            "detail_schema": "pulsarmlx.research.router-detail",
            "detail_schema_version": "1.0.0",
            "source_candidate_sha256": SHA_A,
            "source_environment_sha256": SHA_B,
            "application_read_semantics": "application_positional_read_not_physical_disk_io",
            "batch_order": "single_row_first",
            "ordered_observations": [
                {"global_order_index": index, "observation_id": observation_id}
                for index, observation_id in enumerate(observation_ids)
            ],
            "correctness_cases": [
                {
                    "case_id": f"capacity-case-{case_index}",
                    "oracle_output": deepcopy(output),
                    "mlx_output": deepcopy(output),
                    "comparison": deepcopy(comparison),
                    "attempts": [
                        {
                            "attempt_id": observation_ids[case_index * 15 + attempt],
                            "canonical_output": deepcopy(output),
                            "comparison": deepcopy(comparison),
                        }
                        for attempt in range(15)
                    ],
                }
                for case_index in range(2)
            ],
            "timing_series": [
                {
                    "series_id": f"capacity-series-{index:02}",
                    "observation_ids": observation_ids[30 + index * 6 : 30 + (index + 1) * 6],
                }
                for index in range(38)
            ],
            "process_lifecycles": [
                {"event_order": index, "details": {"status": "bounded"}}
                for index in range(120)
            ],
            "request_windows": [
                {"observation_id": observation_id, "host_wall_duration_ns": 1_000}
                for observation_id in observation_ids
            ],
            "resource_records": [
                {
                    "observation_id": observation_id,
                    "canonical_output": deepcopy(output) if index < 30 else None,
                    "output_sha256": output["complete_output_sha256"],
                }
                for index, observation_id in enumerate(observation_ids)
            ],
            "terminal_failure": None,
        }

        encoded = (
            json.dumps(representative, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        pending = [representative]
        node_count = 0
        while pending:
            value = pending.pop()
            node_count += 1
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        self.assertLess(len(encoded), validator.MAX_PUBLIC_RECORD_BYTES)
        self.assertLess(node_count, validator.MAX_JSON_NODES)

        oversized = valid_evidence("f002-router-oversized-public-record")
        oversized["warnings"] = ["x" * 512 for _ in range(9_000)]
        with self.assertRaises(validator.EvidenceValidationError) as raised:
            validator.validate_record(oversized)
        self.assertEqual(raised.exception.code, "schema_violation")

    def test_memory_gauges_match_the_worker_contract(self) -> None:
        gauges = {
            "mlx_active_bytes": 10,
            "mlx_cache_bytes": 2,
            "mlx_peak_bytes": 12,
            "process_footprint_bytes": 20,
            "process_footprint_source": "task_vm_info",
            "system_pressure": "normal",
            "reported_summed_total_bytes": None,
        }
        validator._validate_memory_gauges(gauges)
        mutations = []
        summed = deepcopy(gauges)
        summed["reported_summed_total_bytes"] = 32
        mutations.append(summed)
        low_peak = deepcopy(gauges)
        low_peak["mlx_peak_bytes"] = 9
        mutations.append(low_peak)
        unpaired = deepcopy(gauges)
        unpaired["process_footprint_source"] = None
        mutations.append(unpaired)
        unstable = deepcopy(gauges)
        unstable["system_pressure"] = "not stable"
        mutations.append(unstable)
        for mutated in mutations:
            with self.assertRaises(validator.EvidenceValidationError):
                validator._validate_memory_gauges(mutated)

    def test_complete_output_comparison_recomputes_metrics_ranges_and_tolerances(self) -> None:
        output = _public_single_row_output()
        comparison = _identical_output_comparison(output)
        validator._validate_output_comparison(
            comparison, output, output, 1, require_pass=True
        )

        mutations = []
        metric = deepcopy(comparison)
        metric["logits"]["maximum_absolute_error"] = 0.25
        mutations.append(metric)
        tolerance = deepcopy(comparison)
        tolerance["normalized_weights"]["absolute_tolerance"] = 0.001
        mutations.append(tolerance)
        range_metric = deepcopy(comparison)
        range_metric["expert_range_comparisons"]["64..80"]["logits"][
            "mismatch_count"
        ] = 1
        mutations.append(range_metric)
        for mutated in mutations:
            with self.assertRaises(validator.EvidenceValidationError):
                validator._validate_output_comparison(
                    mutated, output, output, 1, require_pass=True
                )

        tampered_output = deepcopy(output)
        tampered_output["logits"][0] = float(tampered_output["logits"][0]) + 1.0
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_canonical_output(
                tampered_output,
                "qwen3moe-layer0-router-token0-row0-v1",
                1,
            )

    def test_passing_timing_matrix_is_exact_not_a_partial_prefix(self) -> None:
        matrix = []
        for kind, role, warmups, measurements, count in (
            ("first_process_costly", "primary", 0, 1, 10),
            ("costly_real", "primary", 5, 10, 2),
            ("major_minimally_instrumented", "primary", 5, 30, 2),
            ("stage_diagnostic", "primary", 5, 10, 2),
        ):
            matrix.extend(
                {
                    "series_kind": kind,
                    "replication_role": role,
                    "warmup_count": warmups,
                    "measurement_count": measurements,
                }
                for _ in range(count)
            )
        for _ in range(2):
            matrix.extend(
                {
                    "series_kind": "first_process_costly",
                    "replication_role": "clean_process_replication",
                    "warmup_count": 0,
                    "measurement_count": 1,
                }
                for _ in range(10)
            )
            matrix.append({
                "series_kind": "major_minimally_instrumented",
                "replication_role": "clean_process_replication",
                "warmup_count": 5,
                "measurement_count": 30,
            })
        validator._validate_passing_timing_matrix(
            matrix, raw_count=260, correctness_count=30, timing_count=230
        )
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_passing_timing_matrix(
                matrix[:-1], raw_count=225, correctness_count=30, timing_count=195
            )
        reordered = deepcopy(matrix)
        reordered[0], reordered[10] = reordered[10], reordered[0]
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_passing_timing_matrix(
                reordered, raw_count=260, correctness_count=30, timing_count=230
            )

    def test_public_oracle_artifact_satisfies_input_and_oracle_roles_once(self) -> None:
        record = {
            "evidence_scope": "external_checkpoint",
            "evidence_schema_version": "1.2.0",
            "source_commit": SOURCE_COMMIT,
            "protocol": {"sha256": _sha256(PROTOCOL)},
            "artifacts": [
                {
                    "kind": "frozen_protocol",
                    "path": "docs/research/EXPERIMENT_PROTOCOL.md",
                    "sha256": _sha256(PROTOCOL),
                },
                {
                    "kind": "model_manifest",
                    "path": "docs/research/MODEL_MANIFEST.json",
                    "sha256": _sha256(MODEL_MANIFEST),
                },
                {
                    "kind": "real_router_input_and_independent_cpu_oracle",
                    "path": "fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json",
                    "sha256": _sha256(REAL_ORACLE_PUBLICATION),
                },
            ],
        }
        validator._validate_artifacts(record, REPOSITORY_ROOT)
        tampered = deepcopy(record)
        tampered["artifacts"][2]["sha256"] = "0" * 64
        with self.assertRaises(validator.EvidenceValidationError):
            validator._validate_artifacts(tampered, REPOSITORY_ROOT)

    def test_rejects_missing_required_and_unknown_closed_schema_fields(self) -> None:
        missing = valid_evidence()
        del missing["feature_id"]
        self._assert_rejected(
            {f"{missing['experiment_id']}.json": missing},
            "schema_violation",
        )

        unknown = valid_evidence()
        unknown["unreviewed_extension"] = True
        self._assert_rejected(
            {f"{unknown['experiment_id']}.json": unknown},
            "schema_violation",
        )

    def test_rejects_semantically_inconsistent_identity_and_time_fields(self) -> None:
        abbreviated_commit = valid_evidence()
        abbreviated_commit["source_commit"] = "deadbeef"
        self._assert_rejected(
            {f"{abbreviated_commit['experiment_id']}.json": abbreviated_commit},
            "semantic_relationship",
        )

        reversed_time = valid_evidence()
        reversed_time["completed_at_utc"] = "2026-08-05T17:00:00Z"
        self._assert_rejected(
            {f"{reversed_time['experiment_id']}.json": reversed_time},
            "semantic_relationship",
        )

    def test_rejects_private_paths_without_echoing_the_private_value(self) -> None:
        record = valid_evidence()
        private_path = str(Path("/", "Users", "fixture-user", "private", "checkpoint.gguf"))
        record["model"]["external_locator"] = private_path  # type: ignore[index]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "private_value",
            forbidden_output=private_path,
        )

        private_email = "private.user@example.com"
        email_record = valid_evidence("f002-router-fixture-private-email")
        email_record["warnings"].append(private_email)
        self._assert_rejected(
            {f"{email_record['experiment_id']}.json": email_record},
            "private_value",
            forbidden_output=private_email,
        )

        account_record = valid_evidence("f002-router-fixture-private-account")
        account_record["account" + "_id"] = "private-account"
        self._assert_rejected(
            {f"{account_record['experiment_id']}.json": account_record},
            "private_value",
            forbidden_output="private-account",
        )

    def test_rejects_nested_non_finite_values(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                record = valid_evidence()
                record["correctness"]["maximum_absolute_error"] = value  # type: ignore[index]
                self._assert_rejected(
                    {f"{record['experiment_id']}.json": record},
                    "non_finite_value",
                )

    def test_rejects_insufficient_determinism_and_measurement_repetitions(self) -> None:
        too_few_hashes = valid_evidence()
        too_few_hashes["correctness"]["deterministic_repeat_count"] = 9  # type: ignore[index]
        too_few_hashes["correctness"]["repeat_output_hashes"] = [SHA_B] * 9  # type: ignore[index]
        self._assert_rejected(
            {f"{too_few_hashes['experiment_id']}.json": too_few_hashes},
            "insufficient_repetitions",
        )

        too_few_measurements = valid_evidence()
        too_few_measurements["raw_observations"] = [
            observation
            for observation in too_few_measurements["raw_observations"]  # type: ignore[union-attr]
            if observation["observation_id"] != "measurement-09"
        ]
        self._assert_rejected(
            {f"{too_few_measurements['experiment_id']}.json": too_few_measurements},
            "insufficient_repetitions",
        )

    def test_rejects_duplicate_observation_identities(self) -> None:
        record = valid_evidence()
        observations = record["raw_observations"]  # type: ignore[assignment]
        duplicate = deepcopy(observations[-1])  # type: ignore[index]
        duplicate["run_index"] = 1
        observations.append(duplicate)  # type: ignore[union-attr]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "duplicate_observation_id",
        )

    def test_rejects_duplicate_experiment_ids_in_append_only_input(self) -> None:
        first = valid_evidence()
        duplicate = valid_evidence()
        self._assert_rejected(
            {"first.json": first, "attempted-replacement.json": duplicate},
            "duplicate_experiment_id",
        )

    def test_rejects_filename_identity_mismatch_as_append_only_violation(self) -> None:
        record = valid_evidence()
        self._assert_rejected(
            {"different-identity.json": record},
            "append_only_identity_mismatch",
        )

    def test_rejects_raw_summary_mismatch(self) -> None:
        record = valid_evidence()
        record["summaries"][0]["unfiltered_summary"]["mean_ns"] += 1  # type: ignore[index,operator]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "raw_summary_mismatch",
        )

    def test_rejects_incompatible_condition_pooling(self) -> None:
        record = valid_evidence()
        for observation in record["raw_observations"]:  # type: ignore[union-attr]
            if observation["observation_id"] == "measurement-09":
                observation["condition"] = "first_read_new_process_os_cache_uncontrolled"
                break
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "incompatible_summary_group",
        )

    def test_rejects_verified_claims_beyond_the_router_boundary(self) -> None:
        record = valid_evidence()
        record["claim_boundary"]["status"] = "verified"  # type: ignore[index]
        record["claim_boundary"]["operation"] = "full_model_generation"  # type: ignore[index]
        record["claim_boundary"]["capabilities"] = [  # type: ignore[index]
            "generation",
            "token_throughput",
        ]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "capability_overclaim",
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Fail-closed validator for PulsarMLX research evidence version 1."""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable


_STATISTICS_PATH = Path(__file__).with_name("statistics.py")
_STATISTICS_SPEC = importlib.util.spec_from_file_location(
    "pulsarmlx_research_statistics", _STATISTICS_PATH
)
if _STATISTICS_SPEC is None or _STATISTICS_SPEC.loader is None:
    raise RuntimeError("research statistics module is unavailable")
_STATISTICS_MODULE = importlib.util.module_from_spec(_STATISTICS_SPEC)
_STATISTICS_SPEC.loader.exec_module(_STATISTICS_MODULE)
summarize_nanoseconds = _STATISTICS_MODULE.summarize_nanoseconds


EXPERIMENT_SCHEMA = "pulsarmlx.research.experiment"
ROUTER_SCHEMA = "pulsarmlx.research.router-parity"
SCHEMA_VERSION = "1.0.0"
FEATURE_ID = "002-qwen-router-parity"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PRIVATE_PATH_RE = re.compile(r"(?:^|[\s='\"])(?:/Users/|/home/|/private/var/|[A-Za-z]:\\Users\\)")
SECRET_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,})"
)


class EvidenceValidationError(ValueError):
    """A bounded public validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def _fail(code: str, message: str) -> None:
    raise EvidenceValidationError(code, message)


def _plain_int(value: Any, *, positive: bool = False, nonnegative: bool = False) -> int:
    if type(value) is not int:
        _fail("schema_violation", "an integer field has the wrong type")
    if positive and value <= 0:
        _fail("semantic_relationship", "a positive integer field is out of range")
    if nonnegative and value < 0:
        _fail("semantic_relationship", "a nonnegative integer field is out of range")
    return value


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("schema_violation", "a numeric field has the wrong type")
    result = float(value)
    if not math.isfinite(result):
        _fail("non_finite_value", "evidence contains a non-finite number")
    return result


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _reject_non_finite_and_private_values(record: dict[str, Any]) -> None:
    for value in _walk(record):
        if isinstance(value, float) and not math.isfinite(value):
            _fail("non_finite_value", "evidence contains a non-finite number")
        if isinstance(value, str):
            if PRIVATE_PATH_RE.search(value) or SECRET_RE.search(value):
                _fail("private_value", "evidence contains a forbidden private value")
            if "\x00" in value:
                _fail("schema_violation", "evidence contains an invalid string")


def _closed_object(
    value: Any,
    *,
    allowed: set[str],
    required: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("schema_violation", "an object field has the wrong type")
    required_fields = allowed if required is None else required
    if required_fields - value.keys() or value.keys() - allowed:
        _fail("schema_violation", "a closed object has missing or unknown fields")
    return value


TOP_LEVEL_FIELDS = {
    "evidence_schema",
    "evidence_schema_version",
    "payload_schema",
    "payload_schema_version",
    "experiment_id",
    "feature_id",
    "record_kind",
    "actual_status",
    "started_at_utc",
    "completed_at_utc",
    "source_commit",
    "source_worktree_before",
    "source_worktree_after",
    "protocol",
    "execution",
    "batch_id",
    "process_replication_id",
    "model",
    "tensor",
    "input",
    "oracle",
    "environment",
    "correctness",
    "raw_observations",
    "summaries",
    "claim_boundary",
    "warnings",
    "failures",
    "artifacts",
}


def _validate_schema_files(schema_dir: Path) -> None:
    if not schema_dir.is_dir() or schema_dir.is_symlink():
        _fail("schema_violation", "schema directory is unavailable")
    for name in ("experiment.schema.json", "router-parity.schema.json"):
        path = schema_dir / name
        if not path.is_file() or path.is_symlink():
            _fail("schema_violation", "a required schema is unavailable")
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            _fail("schema_violation", "a required schema is invalid")
        if (
            not isinstance(schema, dict)
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
        ):
            _fail("schema_violation", "a required schema is not closed")


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("semantic_relationship", "a timestamp is not canonical UTC")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("semantic_relationship", "a timestamp is invalid")


def _validate_identity(record: dict[str, Any]) -> None:
    identities = (
        record.get("evidence_schema"),
        record.get("evidence_schema_version"),
        record.get("payload_schema"),
        record.get("payload_schema_version"),
    )
    if identities != (
        EXPERIMENT_SCHEMA,
        SCHEMA_VERSION,
        ROUTER_SCHEMA,
        SCHEMA_VERSION,
    ):
        _fail("unsupported_schema_identity", "evidence schema identity is unsupported")


def _validate_structure(record: dict[str, Any]) -> None:
    _closed_object(record, allowed=TOP_LEVEL_FIELDS)
    if record["feature_id"] != FEATURE_ID:
        _fail("semantic_relationship", "feature identity does not match")
    for name in ("experiment_id", "batch_id", "process_replication_id"):
        if not isinstance(record[name], str) or not ID_RE.fullmatch(record[name]):
            _fail("schema_violation", "an evidence identity is invalid")
    if record["record_kind"] not in {"correctness", "timing", "resource", "combined"}:
        _fail("schema_violation", "record kind is unsupported")
    if record["actual_status"] not in {"passed", "failed", "aborted", "excluded"}:
        _fail("schema_violation", "actual status is unsupported")
    if not isinstance(record["warnings"], list) or not isinstance(record["failures"], list):
        _fail("schema_violation", "warning or failure collection is invalid")
    if not isinstance(record["artifacts"], list):
        _fail("schema_violation", "artifact collection is invalid")

    _closed_object(
        record["source_worktree_after"],
        allowed={"state", "paths"},
    )
    _closed_object(
        record["protocol"],
        allowed={"protocol_id", "protocol_version", "path", "sha256", "order_seed"},
    )
    _closed_object(
        record["execution"],
        allowed={
            "shell",
            "command",
            "argv",
            "working_directory_policy",
            "exit_code",
            "build_profile",
            "features",
            "benchmark_order_policy",
        },
    )
    _closed_object(
        record["model"],
        allowed={
            "repository",
            "revision",
            "filename",
            "size_bytes",
            "sha256",
            "architecture",
            "external_locator",
        },
    )
    _closed_object(
        record["tensor"],
        allowed={
            "name",
            "semantic_role",
            "occurrence_count",
            "gguf_dimensions",
            "reader_shape",
            "execution_shape",
            "dtype",
            "quantization",
            "absolute_offset",
            "encoded_length",
            "end_offset",
            "encoded_sha256",
        },
    )
    _closed_object(
        record["input"],
        allowed={
            "fixture_id",
            "graph_node",
            "input_adapter",
            "tokenizer_identity",
            "token_ids",
            "positions",
            "shape",
            "dtype",
            "byte_order",
            "byte_length",
            "canonical_sha256",
            "selected_rows",
        },
    )
    _closed_object(
        record["oracle"],
        allowed={
            "oracle_id",
            "project",
            "revision",
            "generation_command",
            "input_fixture_sha256",
            "tensor_sha256",
            "output_sha256",
            "independence_statement",
        },
    )
    _closed_object(
        record["environment"],
        allowed={
            "platform",
            "selected_backend",
            "selected_device",
            "safe_environment",
            "interference_admission",
        },
    )
    _closed_object(
        record["correctness"],
        allowed={
            "passed",
            "compared_count",
            "id_mismatch_count",
            "order_mismatch_count",
            "numeric_mismatch_count",
            "first_mismatch",
            "maximum_absolute_error",
            "mean_absolute_error",
            "rmse",
            "maximum_relative_error",
            "absolute_tolerance",
            "relative_tolerance",
            "non_finite_policy",
            "non_finite_count",
            "deterministic_repeat_count",
            "repeat_output_hashes",
        },
    )
    _closed_object(
        record["claim_boundary"],
        allowed={"status", "operation", "capabilities", "unsupported_interpretations"},
    )


def _validate_semantics(record: dict[str, Any]) -> None:
    if not COMMIT_RE.fullmatch(record["source_commit"]):
        _fail("semantic_relationship", "source commit is not immutable")
    if _parse_utc(record["started_at_utc"]) > _parse_utc(record["completed_at_utc"]):
        _fail("semantic_relationship", "experiment timestamps are reversed")

    protocol = record["protocol"]
    if protocol["protocol_version"] != SCHEMA_VERSION or not SHA256_RE.fullmatch(protocol["sha256"]):
        _fail("semantic_relationship", "protocol identity is invalid")
    _plain_int(protocol["order_seed"], nonnegative=True)

    execution = record["execution"]
    _plain_int(execution["exit_code"], nonnegative=True)
    if execution["working_directory_policy"] != "repository_root":
        _fail("semantic_relationship", "working-directory policy is invalid")

    model = record["model"]
    _plain_int(model["size_bytes"], positive=True)
    if not SHA256_RE.fullmatch(model["sha256"]):
        _fail("semantic_relationship", "model identity is invalid")

    tensor = record["tensor"]
    if (
        tensor["name"] != "blk.0.ffn_gate_inp.weight"
        or tensor["semantic_role"] != "layer_0_router_projection"
        or tensor["occurrence_count"] != 1
        or tensor["gguf_dimensions"] != [2048, 128]
        or tensor["reader_shape"] != [128, 2048]
        or tensor["execution_shape"] != [2048, 128]
        or tensor["dtype"] != "F32"
        or tensor["quantization"] != "none_f32"
    ):
        _fail("semantic_relationship", "router tensor contract does not match")
    offset = _plain_int(tensor["absolute_offset"], nonnegative=True)
    length = _plain_int(tensor["encoded_length"], positive=True)
    end = _plain_int(tensor["end_offset"], positive=True)
    if end != offset + length or not SHA256_RE.fullmatch(tensor["encoded_sha256"]):
        _fail("semantic_relationship", "router tensor range is invalid")

    fixture = record["input"]
    if (
        fixture["graph_node"] != "ffn_norm-0"
        or fixture["input_adapter"] != "direct_token_ids_v1"
        or fixture["tokenizer_identity"] != "not_used_direct_token_ids"
        or fixture["token_ids"] != [0, 1]
        or fixture["positions"] != [0, 1]
        or fixture["shape"] != [2, 2048]
        or fixture["dtype"] != "float32"
        or fixture["byte_order"] != "little"
        or fixture["byte_length"] != 16_384
        or fixture["selected_rows"] not in ([0], [0, 1])
        or not SHA256_RE.fullmatch(fixture["canonical_sha256"])
    ):
        _fail("semantic_relationship", "router input fixture is invalid")

    oracle = record["oracle"]
    for name in ("input_fixture_sha256", "tensor_sha256", "output_sha256"):
        if not SHA256_RE.fullmatch(oracle[name]):
            _fail("semantic_relationship", "oracle identity is invalid")
    if oracle["input_fixture_sha256"] != fixture["canonical_sha256"]:
        _fail("semantic_relationship", "oracle input identity does not match")
    if oracle["tensor_sha256"] != tensor["encoded_sha256"]:
        _fail("semantic_relationship", "oracle tensor identity does not match")


OBSERVATION_FIELDS = {
    "observation_id",
    "run_index",
    "batch_id",
    "case_id",
    "process_replication_id",
    "observation_kind",
    "process_state",
    "condition",
    "instrumentation_mode",
    "started_at_utc",
    "completed_at_utc",
    "monotonic_clock",
    "durations_ns",
    "status",
    "requested_device",
    "selected_device",
    "fallback_used",
    "evaluated",
    "synchronized",
    "output_sha256",
    "correctness_passed",
    "failure",
    "exclusion_rule_id",
}


def _validate_observations(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observations = record["raw_observations"]
    if not isinstance(observations, list) or not observations:
        _fail("schema_violation", "raw observations are missing")
    by_id: dict[str, dict[str, Any]] = {}
    for observation in observations:
        item = _closed_object(
            observation,
            allowed=OBSERVATION_FIELDS,
            required=OBSERVATION_FIELDS - {"failure", "exclusion_rule_id"},
        )
        observation_id = item["observation_id"]
        if not isinstance(observation_id, str) or not ID_RE.fullmatch(observation_id):
            _fail("schema_violation", "observation identity is invalid")
        if observation_id in by_id:
            _fail("duplicate_observation_id", "observation identity is duplicated")
        by_id[observation_id] = item
        _plain_int(item["run_index"], nonnegative=True)
        if item["observation_kind"] not in {
            "warmup",
            "measurement",
            "clean_process_replication",
        }:
            _fail("schema_violation", "observation kind is invalid")
        if item["condition"] not in {
            "warm",
            "first_read_new_process_os_cache_uncontrolled",
            "controlled_cold",
        }:
            _fail("schema_violation", "observation condition is invalid")
        if item["instrumentation_mode"] not in {
            "minimally_instrumented",
            "stage_instrumented",
        }:
            _fail("schema_violation", "instrumentation mode is invalid")
        if item["status"] not in {"passed", "failed", "aborted", "excluded"}:
            _fail("schema_violation", "observation status is invalid")
        if not isinstance(item["durations_ns"], dict) or not item["durations_ns"]:
            _fail("schema_violation", "duration map is invalid")
        for duration in item["durations_ns"].values():
            _plain_int(duration, positive=True)
        if item["status"] == "passed":
            if (
                item["requested_device"] != "gpu"
                or item["selected_device"] != "gpu"
                or item["fallback_used"] is not False
                or item["evaluated"] is not True
                or item["synchronized"] is not True
                or item["correctness_passed"] is not True
                or not SHA256_RE.fullmatch(item["output_sha256"])
            ):
                _fail("semantic_relationship", "successful observation metadata is inconsistent")
    return by_id


def _validate_repetitions(record: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    correctness = record["correctness"]
    repeat_count = _plain_int(correctness["deterministic_repeat_count"], positive=True)
    hashes = correctness["repeat_output_hashes"]
    if (
        repeat_count < 10
        or not isinstance(hashes, list)
        or len(hashes) != repeat_count
        or any(not isinstance(value, str) or not SHA256_RE.fullmatch(value) for value in hashes)
    ):
        _fail("insufficient_repetitions", "deterministic repetition policy is not met")
    if len(set(hashes)) != 1:
        _fail("semantic_relationship", "deterministic output hashes differ")
    measurements = [item for item in by_id.values() if item["observation_kind"] == "measurement"]
    warmups = [item for item in by_id.values() if item["observation_kind"] == "warmup"]
    replications = [
        item for item in by_id.values() if item["observation_kind"] == "clean_process_replication"
    ]
    if len(measurements) < 10 or len(warmups) < 5 or not replications:
        _fail("insufficient_repetitions", "timing repetition policy is not met")


SUMMARY_FIELDS = {
    "summary_id",
    "statistics_algorithm",
    "group",
    "included_observation_ids",
    "excluded_observation_ids",
    "unfiltered_summary",
}
GROUP_FIELDS = {
    "case_id",
    "batch_id",
    "observation_kind",
    "condition",
    "instrumentation_mode",
    "stage",
}


def _equal_number(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    if (
        isinstance(right, (int, float))
        and not isinstance(right, bool)
        and isinstance(left, (int, float))
        and not isinstance(left, bool)
    ):
        return math.isclose(
            _finite_number(left),
            _finite_number(right),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    return left == right


def _validate_summaries(record: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    summaries = record["summaries"]
    if not isinstance(summaries, list) or not summaries:
        _fail("schema_violation", "statistical summaries are missing")
    for raw_summary in summaries:
        summary = _closed_object(raw_summary, allowed=SUMMARY_FIELDS)
        group = _closed_object(summary["group"], allowed=GROUP_FIELDS)
        if summary["statistics_algorithm"] != "pulsarmlx-type7-v1":
            _fail("semantic_relationship", "statistics algorithm is invalid")
        included_ids = summary["included_observation_ids"]
        if not isinstance(included_ids, list) or len(set(included_ids)) != len(included_ids):
            _fail("schema_violation", "included observation identities are invalid")
        included: list[dict[str, Any]] = []
        for observation_id in included_ids:
            observation = by_id.get(observation_id)
            if observation is None:
                _fail("raw_summary_mismatch", "summary references a missing observation")
            for field in (
                "case_id",
                "batch_id",
                "observation_kind",
                "condition",
                "instrumentation_mode",
            ):
                if observation[field] != group[field]:
                    _fail("incompatible_summary_group", "summary pools incompatible observations")
            included.append(observation)
        stage = group["stage"]
        if not isinstance(stage, str) or any(stage not in item["durations_ns"] for item in included):
            _fail("raw_summary_mismatch", "summary timing stage is unavailable")
        recomputed = summarize_nanoseconds([item["durations_ns"][stage] for item in included])
        reported = summary["unfiltered_summary"]
        if not isinstance(reported, dict) or reported.keys() != recomputed.keys():
            _fail("raw_summary_mismatch", "summary fields do not match the frozen method")
        for field, expected in recomputed.items():
            if not _equal_number(reported[field], expected):
                _fail("raw_summary_mismatch", "summary does not match raw observations")


def _validate_correctness(record: dict[str, Any]) -> None:
    correctness = record["correctness"]
    for field in (
        "compared_count",
        "id_mismatch_count",
        "order_mismatch_count",
        "numeric_mismatch_count",
        "non_finite_count",
    ):
        _plain_int(correctness[field], nonnegative=True)
    for field in (
        "maximum_absolute_error",
        "mean_absolute_error",
        "rmse",
        "maximum_relative_error",
        "absolute_tolerance",
        "relative_tolerance",
    ):
        if _finite_number(correctness[field]) < 0:
            _fail("semantic_relationship", "a correctness metric is negative")
    if correctness["non_finite_policy"] != "reject":
        _fail("semantic_relationship", "non-finite policy is invalid")
    if correctness["passed"] is True:
        if (
            correctness["compared_count"] <= 0
            or correctness["id_mismatch_count"] != 0
            or correctness["order_mismatch_count"] != 0
            or correctness["numeric_mismatch_count"] != 0
            or correctness["non_finite_count"] != 0
            or correctness["first_mismatch"] is not None
        ):
            _fail("semantic_relationship", "passing correctness fields contradict each other")


def _validate_claim_boundary(record: dict[str, Any]) -> None:
    boundary = record["claim_boundary"]
    allowed_capabilities = {
        "router_logits",
        "router_full_softmax",
        "router_top8_selection",
        "router_selected_weight_normalization",
    }
    required_unsupported = {
        "expert_execution",
        "routed_moe_aggregation",
        "complete_transformer_layer",
        "full_model_generation",
        "serving",
        "token_throughput",
        "linux_cuda_runtime_parity",
    }
    capabilities = boundary["capabilities"]
    unsupported = boundary["unsupported_interpretations"]
    if (
        boundary["operation"] != "layer_0_router_only"
        or not isinstance(capabilities, list)
        or not set(capabilities) <= allowed_capabilities
        or not isinstance(unsupported, list)
        or not required_unsupported <= set(unsupported)
        or boundary["status"] not in {"provisional", "verified", "failed", "blocked"}
    ):
        _fail("capability_overclaim", "claim exceeds the bounded router evidence")
    if boundary["status"] == "verified" and record["source_worktree_before"] != "clean":
        _fail("capability_overclaim", "verified evidence requires a clean source")


def validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        _fail("schema_violation", "evidence root is not an object")
    _reject_non_finite_and_private_values(record)
    _validate_identity(record)
    _validate_structure(record)
    _validate_semantics(record)
    by_id = _validate_observations(record)
    _validate_repetitions(record, by_id)
    _validate_summaries(record, by_id)
    _validate_correctness(record)
    _validate_claim_boundary(record)
    if record["actual_status"] == "passed" and (
        record["execution"]["exit_code"] != 0
        or record["correctness"]["passed"] is not True
        or record["failures"]
    ):
        _fail("semantic_relationship", "passing experiment fields contradict each other")
    return record


def _load_records(input_path: Path) -> list[tuple[Path, dict[str, Any]]]:
    if input_path.is_symlink():
        _fail("schema_violation", "evidence input cannot be a symlink")
    if input_path.is_file():
        paths = [input_path]
    elif input_path.is_dir():
        paths = sorted(input_path.glob("*.json"))
    else:
        _fail("schema_violation", "evidence input is unavailable")
    if not paths:
        _fail("schema_violation", "evidence input contains no JSON records")
    records: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            _fail("schema_violation", "an evidence file is unsafe or oversized")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            _fail("schema_violation", "an evidence file is invalid JSON")
        if not isinstance(record, dict):
            _fail("schema_violation", "an evidence root is not an object")
        records.append((path, record))
    return records


def validate_input(schema_dir: Path, input_path: Path) -> list[dict[str, Any]]:
    _validate_schema_files(schema_dir)
    loaded = _load_records(input_path)
    experiment_ids = [record.get("experiment_id") for _, record in loaded]
    if len(set(map(str, experiment_ids))) != len(experiment_ids):
        _fail("duplicate_experiment_id", "experiment identity is duplicated")
    validated: list[dict[str, Any]] = []
    for path, record in loaded:
        experiment_id = record.get("experiment_id")
        if not isinstance(experiment_id, str) or path.stem != experiment_id:
            _fail("append_only_identity_mismatch", "filename and experiment identity differ")
        validated.append(validate_record(record))
    return validated


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-dir", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        records = validate_input(args.schema_dir, args.input)
    except EvidenceValidationError as error:
        print(f"validation failed: {error.code}: {error.public_message}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"status": "passed", "record_count": len(records)},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate the external, model-free generated-router timing candidate.

This validator is deliberately separate from the external-checkpoint research
envelope.  It admits exactly the fixed generated fixture run produced by
``validate-router-fixtures``: five retained warm-ups followed by thirty
retained measurements in one persistent MLX worker.  The input remains outside
Git; the deterministic validation report contains no local path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import sys
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = "schemas/research/v1/router-fixture-candidate.schema.json"
MANIFEST_PATH = "fixtures/research/router-v1/manifest.json"
MANIFEST_SHA256 = "b953d9c1c86357612b757b41e22a33b80cdb5da412522ae4ca93508945ebc9ba"
FIXTURE_ID = "generated-qwen3moe-router-v1"
GOLDEN_CASE_ID = "generated-qwen3moe-router-single-row-v1"
TWO_ROW_CASE_ID = "generated-qwen3moe-router-two-row-v1"
BENCHMARK_ID = "f002-generated-router-single-row-minimal-v1"
PROCESS_REPLICATION_ID = "generated-router-persistent-worker-v1"
SYNTHETIC_BATCH_ID = "f002-generated-router-fixture-batch-v1"
VALIDATION_SCHEMA = "pulsarmlx.research.generated-router-candidate-validation"
VALIDATION_SCHEMA_VERSION = "1.0.0"
WARMUP_COUNT = 5
MEASUREMENT_COUNT = 30
ATTEMPT_COUNT = WARMUP_COUNT + MEASUREMENT_COUNT
MAX_CANDIDATE_BYTES = 256 * 1024
MAX_REPOSITORY_JSON_BYTES = 128 * 1024
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64

EXPECTED_MANIFEST_FILES = (
    "golden/expected_results.json",
    "golden/hidden_states.json",
    "golden/weight_recipe.json",
    "malformed/invalid-control-type.json",
    "malformed/invalid-hidden-shape.json",
    "malformed/invalid-orientation.json",
    "malformed/invalid-top-k.json",
    "malformed/non-finite-hidden-state.json",
    "malformed/overlong-router-range.json",
    "malformed/truncated-router-range.json",
    "synthetic-tie.json",
)

ROOT_FIELDS = {
    "schema_version",
    "validation",
    "status",
    "passed",
    "fixture_kind",
    "evidence_level",
    "model_free",
    "real_checkpoint_evidence",
    "external_checkpoint_accessed",
    "manifest",
    "manifest_sha256",
    "manifest_files",
    "runtime",
    "positive_cases",
    "synthetic_tie_cases",
    "negative_cases",
    "generated_router_microbenchmark",
    "cleanup",
    "failure",
    "warnings",
    "exclusions",
}

ROOT_WARNINGS = [
    "Tie cases use host contract validation and are not represented as MLX execution.",
    "Negative fixture records verify the frozen failure contract; focused tests prove rejection ordering and runner-not-called behavior.",
]
ROOT_EXCLUSIONS = [
    "No external checkpoint, model descriptor, model weight, or real hidden state was accessed.",
    "Synthetic results are not real-checkpoint router evidence.",
    "No expert, complete layer, generation, serving, or non-Apple backend execution was established.",
]
BENCHMARK_EXCLUSIONS = [
    "This generated fixture timing is not real-checkpoint latency.",
    "No external checkpoint, expert, layer, generation, or serving operation was accessed.",
]


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{name} module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_STATISTICS = _load_module(
    "pulsarmlx_generated_candidate_statistics",
    Path(__file__).with_name("statistics.py"),
)
_ENVIRONMENT = _load_module(
    "pulsarmlx_generated_candidate_environment",
    Path(__file__).with_name("environment.py"),
)

COMPATIBILITY_FIELDS = _STATISTICS.COMPATIBILITY_FIELDS
group_raw_observations = _STATISTICS.group_raw_observations
project_timing_rows = _STATISTICS.project_timing_rows
summarize_nanoseconds = _STATISTICS.summarize_nanoseconds
assert_public_safe = _ENVIRONMENT.assert_public_safe
combine_environment_evidence = _ENVIRONMENT.combine_environment_evidence
extract_benchmark_resources = _ENVIRONMENT.extract_benchmark_resources


class CandidateValidationError(ValueError):
    """A stable, public-safe generated-candidate validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def _fail(code: str, message: str) -> None:
    raise CandidateValidationError(code, message)


def _duplicate_free_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("invalid_json", "candidate JSON contains a duplicate object key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    _fail("non_finite_value", "candidate JSON contains a non-finite value")


def _parse_json_bytes(raw: bytes, *, label: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_free_object,
            parse_constant=_reject_constant,
        )
    except CandidateValidationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail("invalid_json", f"{label} is not bounded duplicate-free JSON")


def _bounded_walk(value: Any) -> Iterable[Any]:
    pending: list[tuple[Any, int]] = [(value, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail("schema_violation", "candidate JSON exceeds its structural bound")
        yield current
        if isinstance(current, dict):
            for key, child in reversed(tuple(current.items())):
                pending.append((child, depth + 1))
                pending.append((key, depth + 1))
        elif isinstance(current, list):
            for child in reversed(current):
                pending.append((child, depth + 1))


def _load_external_json(path: Path, *, maximum_bytes: int, label: str) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            _fail("unsafe_input", f"{label} must be a regular non-link file")
        if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
            _fail("unsafe_input", f"{label} violates its byte bound")
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size != metadata.st_size:
                _fail("unsafe_input", f"{label} changed during validation")
            raw = handle.read(maximum_bytes + 1)
    except CandidateValidationError:
        raise
    except OSError:
        _fail("unsafe_input", f"{label} is unavailable")
    if len(raw) > maximum_bytes:
        _fail("unsafe_input", f"{label} violates its byte bound")
    value = _parse_json_bytes(raw, label=label)
    if not isinstance(value, dict):
        _fail("schema_violation", f"{label} root must be an object")
    for _ in _bounded_walk(value):
        pass
    try:
        assert_public_safe(value)
    except Exception:
        _fail("private_value", f"{label} contains a forbidden private value")
    return value


def _closed(
    value: Any,
    fields: set[str],
    *,
    label: str,
    required: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("schema_violation", f"{label} must be an object")
    required_fields = fields if required is None else required
    if set(value) - fields or required_fields - set(value):
        _fail("schema_violation", f"{label} has missing or unknown fields")
    return value


def _plain_int(
    value: Any,
    *,
    label: str,
    minimum: int | None = None,
) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        _fail("schema_violation", f"{label} must be a bounded integer")
    return value


def _finite(value: Any, *, label: str, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("schema_violation", f"{label} must be numeric")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        _fail("non_finite_value", f"{label} must be finite")
    if not math.isfinite(result) or (nonnegative and result < 0):
        _fail("non_finite_value", f"{label} must be finite and nonnegative")
    return result


def _bounded_string(value: Any, *, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        _fail("schema_violation", f"{label} must be a nonempty string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        _fail("schema_violation", f"{label} must be valid UTF-8")
    if size > maximum:
        _fail("schema_violation", f"{label} exceeds its byte bound")
    return value


def _sha256(value: Any, *, label: str) -> str:
    text = _bounded_string(value, label=label, maximum=64)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        _fail("schema_violation", f"{label} must be a canonical SHA-256")
    return text


def _commit(value: Any, *, label: str) -> str:
    text = _bounded_string(value, label=label, maximum=40)
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        _fail("schema_violation", f"{label} must be a canonical Git commit")
    return text


def _repository_file(
    repository_root: Path,
    relative_path: str,
    *,
    maximum_bytes: int = MAX_REPOSITORY_JSON_BYTES,
) -> tuple[bytes, str]:
    pure = PurePosixPath(relative_path)
    if (
        pure.is_absolute()
        or not pure.parts
        or pure.as_posix() != relative_path
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        _fail("manifest_mismatch", "a committed fixture path is not canonical")
    try:
        root = repository_root.resolve(strict=True)
        candidate = root
        for part in pure.parts:
            candidate = candidate / part
            if candidate.is_symlink():
                _fail("manifest_mismatch", "a committed fixture path is a symbolic link")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        with resolved.open("rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size <= 0
                or metadata.st_size > maximum_bytes
            ):
                _fail("manifest_mismatch", "a committed fixture file violates its bound")
            raw = handle.read(maximum_bytes + 1)
    except CandidateValidationError:
        raise
    except (OSError, RuntimeError, ValueError):
        _fail("manifest_mismatch", "a committed fixture file is unavailable")
    if len(raw) > maximum_bytes:
        _fail("manifest_mismatch", "a committed fixture file violates its bound")
    return raw, hashlib.sha256(raw).hexdigest()


def _validate_contract_schema(repository_root: Path) -> None:
    raw, _ = _repository_file(repository_root, SCHEMA_PATH)
    schema = _parse_json_bytes(raw, label="generated candidate schema")
    if not isinstance(schema, dict):
        _fail("schema_violation", "generated candidate schema root is invalid")
    if (
        schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or set(schema.get("required", [])) != ROOT_FIELDS
        or set(schema.get("properties", {})) != ROOT_FIELDS
    ):
        _fail("schema_violation", "generated candidate schema is not closed or synchronized")


def _validate_manifest(
    candidate: Mapping[str, Any], repository_root: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    raw, digest = _repository_file(repository_root, MANIFEST_PATH)
    if digest != MANIFEST_SHA256:
        _fail("manifest_mismatch", "the committed router manifest hash is not frozen")
    manifest = _parse_json_bytes(raw, label="router fixture manifest")
    if not isinstance(manifest, dict):
        _fail("manifest_mismatch", "the router fixture manifest root is invalid")
    _closed(
        manifest,
        {
            "cases",
            "contract",
            "expected_results",
            "files",
            "fixture_id",
            "hidden_state_fixture",
            "provenance",
            "schema",
            "schema_version",
            "scope",
            "weight_fixture",
        },
        label="router fixture manifest",
    )
    if (
        manifest["schema"] != "pulsarmlx.fixture.router-manifest"
        or manifest["schema_version"] != "1.0.0"
        or manifest["fixture_id"] != FIXTURE_ID
        or candidate["manifest"] != MANIFEST_PATH
        or candidate["manifest_sha256"] != digest
    ):
        _fail("manifest_mismatch", "candidate manifest identity is inconsistent")

    contract = _closed(
        manifest["contract"],
        {
            "contract_id",
            "expert_count",
            "hidden_width",
            "normalization",
            "tie_rule",
            "top_k",
            "weight_byte_order",
            "weight_dtype",
            "weight_layout",
        },
        label="router manifest contract",
    )
    if (
        contract["contract_id"] != "qwen3moe-layer0-router-parity-v1"
        or contract["expert_count"] != 128
        or contract["hidden_width"] != 2048
        or contract["top_k"] != 8
        or contract["weight_dtype"] != "float32"
        or contract["weight_byte_order"] != "little"
        or contract["weight_layout"] != "expert_major_rows_input_columns"
        or contract["normalization"]
        != "full_128_way_softmax_then_selected_probability_renormalization"
        or contract["tie_rule"]
        != "probability_descending_then_expert_id_ascending"
    ):
        _fail("manifest_mismatch", "router manifest contract is inconsistent")

    provenance = _closed(
        manifest["provenance"],
        {
            "external_checkpoint_access_required",
            "generation_command",
            "generator",
            "generator_sha256",
            "independence",
            "kind",
            "license",
            "model_free",
            "redistributable",
        },
        label="router manifest provenance",
    )
    if (
        provenance["kind"] != "synthetic_generated"
        or provenance["model_free"] is not True
        or provenance["external_checkpoint_access_required"] is not False
        or provenance["redistributable"] is not True
        or provenance["generator"] != "golden/generate.py"
    ):
        _fail("manifest_mismatch", "router manifest provenance is inconsistent")
    generator_path = f"fixtures/research/router-v1/{provenance['generator']}"
    _, generator_digest = _repository_file(repository_root, generator_path)
    if generator_digest != provenance["generator_sha256"]:
        _fail("manifest_mismatch", "router fixture generator hash is inconsistent")

    entries = manifest["files"]
    if not isinstance(entries, list) or len(entries) != len(EXPECTED_MANIFEST_FILES):
        _fail("manifest_mismatch", "router manifest inventory size is inconsistent")
    observed_entries: list[dict[str, Any]] = []
    for entry, expected_path in zip(entries, EXPECTED_MANIFEST_FILES, strict=True):
        item = _closed(
            entry,
            {"path", "byte_length", "sha256"},
            label="router manifest file entry",
        )
        if item["path"] != expected_path:
            _fail("manifest_mismatch", "router manifest inventory order is inconsistent")
        length = _plain_int(item["byte_length"], label="fixture byte length", minimum=1)
        expected_digest = _sha256(item["sha256"], label="fixture file SHA-256")
        fixture_path = f"fixtures/research/router-v1/{expected_path}"
        fixture_raw, fixture_digest = _repository_file(repository_root, fixture_path)
        if len(fixture_raw) != length or fixture_digest != expected_digest:
            _fail("manifest_mismatch", "a committed fixture differs from its inventory")
        observed_entries.append(dict(item))
    if candidate["manifest_files"] != observed_entries:
        _fail("manifest_mismatch", "candidate manifest inventory is not exact")

    expected_results = _closed(
        manifest["expected_results"],
        {"path", "arithmetic", "independently_computed", "complete_values"},
        label="router expected-results index",
    )
    if expected_results != {
        "path": "golden/expected_results.json",
        "arithmetic": "scalar_float32",
        "independently_computed": True,
        "complete_values": True,
    }:
        _fail("manifest_mismatch", "router expected-results index is inconsistent")

    case_indexes = manifest["cases"]
    if not isinstance(case_indexes, list) or [
        case.get("case_id") if isinstance(case, dict) else None for case in case_indexes
    ] != [GOLDEN_CASE_ID, TWO_ROW_CASE_ID]:
        _fail("manifest_mismatch", "router case inventory is inconsistent")

    golden_raw, _ = _repository_file(
        repository_root,
        "fixtures/research/router-v1/golden/expected_results.json",
    )
    golden = _parse_json_bytes(golden_raw, label="router golden results")
    tie_raw, _ = _repository_file(
        repository_root,
        "fixtures/research/router-v1/synthetic-tie.json",
    )
    ties = _parse_json_bytes(tie_raw, label="router tie results")
    if not isinstance(golden, dict) or not isinstance(ties, dict):
        _fail("golden_mismatch", "router golden documents are invalid")

    negatives: list[dict[str, Any]] = []
    for relative in EXPECTED_MANIFEST_FILES[3:10]:
        payload, _ = _repository_file(
            repository_root,
            f"fixtures/research/router-v1/{relative}",
        )
        document = _parse_json_bytes(payload, label="negative router fixture")
        if not isinstance(document, dict):
            _fail("manifest_mismatch", "a negative router fixture is invalid")
        negatives.append(document)
    return manifest, golden, ties, negatives


def _matrix(
    value: Any,
    *,
    rows: int,
    columns: int,
    label: str,
    integers: bool = False,
) -> list[list[int | float]]:
    if not isinstance(value, list) or len(value) != rows:
        _fail("golden_mismatch", f"{label} row count is invalid")
    result: list[list[int | float]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != columns:
            _fail("golden_mismatch", f"{label} column count is invalid")
        validated: list[int | float] = []
        for item in row:
            if integers:
                number = _plain_int(item, label=label, minimum=0)
                if number >= 128:
                    _fail("golden_mismatch", f"{label} contains an invalid expert ID")
                validated.append(number)
            else:
                validated.append(_finite(item, label=label))
        result.append(validated)
    return result


def _vector(
    value: Any,
    *,
    length: int,
    label: str,
) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        _fail("golden_mismatch", f"{label} length is invalid")
    return [_finite(item, label=label) for item in value]


def _f32le(rows: Sequence[Sequence[int | float]]) -> bytes:
    return b"".join(struct.pack("<f", float(value)) for row in rows for value in row)


def _u32le(rows: Sequence[Sequence[int | float]]) -> bytes:
    return b"".join(struct.pack("<I", int(value)) for row in rows for value in row)


def recompute_golden_hashes(case: Mapping[str, Any]) -> dict[str, str]:
    """Independently recompute every declared golden output hash."""

    hidden_shape = case.get("hidden_shape")
    logits_shape = case.get("logits_shape")
    if (
        not isinstance(hidden_shape, list)
        or len(hidden_shape) != 2
        or hidden_shape[1] != 2048
        or logits_shape != [hidden_shape[0], 128]
    ):
        _fail("golden_mismatch", "golden router shapes are inconsistent")
    rows = _plain_int(hidden_shape[0], label="golden row count", minimum=1)
    logits = _matrix(case.get("logits"), rows=rows, columns=128, label="golden logits")
    probabilities = _matrix(
        case.get("full_softmax_probabilities"),
        rows=rows,
        columns=128,
        label="golden probabilities",
    )
    selected_ids = _matrix(
        case.get("selected_expert_ids"),
        rows=rows,
        columns=8,
        label="golden selected expert IDs",
        integers=True,
    )
    selected = _matrix(
        case.get("selected_probabilities"),
        rows=rows,
        columns=8,
        label="golden selected probabilities",
    )
    normalized = _matrix(
        case.get("normalized_weights"),
        rows=rows,
        columns=8,
        label="golden normalized weights",
    )
    encoded_logits = _f32le(logits)
    encoded_probabilities = _f32le(probabilities)
    encoded_ids = _u32le(selected_ids)
    encoded_selected = _f32le(selected)
    encoded_normalized = _f32le(normalized)
    return {
        "logits_f32le_sha256": hashlib.sha256(encoded_logits).hexdigest(),
        "full_softmax_probabilities_f32le_sha256": hashlib.sha256(
            encoded_probabilities
        ).hexdigest(),
        "selected_expert_ids_u32le_sha256": hashlib.sha256(encoded_ids).hexdigest(),
        "selected_probabilities_f32le_sha256": hashlib.sha256(
            encoded_selected
        ).hexdigest(),
        "normalized_weights_f32le_sha256": hashlib.sha256(
            encoded_normalized
        ).hexdigest(),
        "float_output_bundle_f32le_sha256": hashlib.sha256(
            encoded_logits + encoded_probabilities + encoded_selected + encoded_normalized
        ).hexdigest(),
        "complete_output_sha256": hashlib.sha256(
            encoded_logits
            + encoded_probabilities
            + encoded_ids
            + encoded_selected
            + encoded_normalized
        ).hexdigest(),
    }


def _validate_golden_document(golden: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    document = _closed(
        golden,
        {"schema", "schema_version", "fixture_id", "contract", "cases", "provenance"},
        label="router golden document",
    )
    if (
        document["schema"] != "pulsarmlx.fixture.router-expected-results"
        or document["schema_version"] != "1.0.0"
        or document["fixture_id"] != "generated-qwen3moe-router-expected-results-v1"
    ):
        _fail("golden_mismatch", "router golden identity is inconsistent")
    cases = document["cases"]
    if not isinstance(cases, dict) or list(cases) != [GOLDEN_CASE_ID, TWO_ROW_CASE_ID]:
        _fail("golden_mismatch", "router golden case inventory is inconsistent")
    recomputed: dict[str, dict[str, str]] = {}
    expected_rows = {GOLDEN_CASE_ID: 1, TWO_ROW_CASE_ID: 2}
    case_fields = {
        "case_id",
        "hidden_row_ids",
        "hidden_shape",
        "logits_shape",
        "logits",
        "full_softmax_probabilities",
        "selected_expert_ids",
        "selected_probabilities",
        "normalized_weights",
        "hashes",
        "provenance",
    }
    declared_hash_fields = {
        "logits_f32le_sha256",
        "full_softmax_probabilities_f32le_sha256",
        "selected_expert_ids_u32le_sha256",
        "selected_probabilities_f32le_sha256",
        "normalized_weights_f32le_sha256",
        "float_output_bundle_f32le_sha256",
    }
    for case_id, rows in expected_rows.items():
        case = _closed(cases[case_id], case_fields, label="router golden case")
        if (
            case["case_id"] != case_id
            or case["hidden_shape"] != [rows, 2048]
            or case["logits_shape"] != [rows, 128]
            or case["provenance"] != "synthetic_generated_model_free"
        ):
            _fail("golden_mismatch", "router golden case identity is inconsistent")
        hashes = _closed(case["hashes"], declared_hash_fields, label="golden hashes")
        for name, value in hashes.items():
            _sha256(value, label=f"golden {name}")
        computed = recompute_golden_hashes(case)
        if hashes != {name: computed[name] for name in declared_hash_fields}:
            _fail("golden_mismatch", "declared golden hashes do not match complete values")
        recomputed[case_id] = computed
    return recomputed


def _validate_memory_gauges(value: Any) -> dict[str, Any]:
    gauges = _closed(
        value,
        {
            "mlx_active_bytes",
            "mlx_cache_bytes",
            "mlx_peak_bytes",
            "process_footprint_bytes",
            "process_footprint_source",
            "system_pressure",
            "reported_summed_total_bytes",
        },
        label="worker memory gauges",
    )
    for field in (
        "mlx_active_bytes",
        "mlx_cache_bytes",
        "mlx_peak_bytes",
        "process_footprint_bytes",
        "reported_summed_total_bytes",
    ):
        if gauges[field] is not None:
            _plain_int(gauges[field], label=f"memory gauge {field}", minimum=0)
    if gauges["process_footprint_bytes"] is not None and gauges["process_footprint_bytes"] <= 0:
        _fail("resource_mismatch", "worker process footprint must be positive when observed")
    if gauges["process_footprint_source"] is not None:
        _bounded_string(gauges["process_footprint_source"], label="memory gauge source", maximum=64)
    if gauges["system_pressure"] not in {None, "normal", "warning", "critical"}:
        _fail("resource_mismatch", "worker memory pressure is invalid")
    active = gauges["mlx_active_bytes"]
    peak = gauges["mlx_peak_bytes"]
    if type(active) is int and type(peak) is int and peak < active:
        _fail("resource_mismatch", "worker peak MLX memory is below active memory")
    return gauges


def _validate_numeric_comparison(
    value: Any,
    *,
    label: str,
    compared_count: int,
    tolerance: float,
) -> None:
    comparison = _closed(
        value,
        {
            "compared_count",
            "mismatch_count",
            "first_mismatch",
            "maximum_absolute_error",
            "mean_absolute_error",
            "rmse",
            "maximum_relative_error",
            "absolute_tolerance",
            "relative_tolerance",
        },
        label=label,
    )
    if (
        comparison["compared_count"] != compared_count
        or comparison["mismatch_count"] != 0
        or comparison["first_mismatch"] is not None
        or comparison["absolute_tolerance"] != tolerance
        or comparison["relative_tolerance"] != tolerance
    ):
        _fail("golden_mismatch", f"{label} does not describe a passing comparison")
    for field in (
        "maximum_absolute_error",
        "mean_absolute_error",
        "rmse",
        "maximum_relative_error",
    ):
        if comparison[field] is not None:
            _finite(comparison[field], label=f"{label} {field}", nonnegative=True)


def _numeric_comparison(
    reference: Sequence[Sequence[int | float]],
    candidate: Sequence[Sequence[int | float]],
    *,
    row_width: int,
    tolerance: float,
) -> dict[str, Any]:
    reference_values = [float(value) for row in reference for value in row]
    candidate_values = [float(value) for row in candidate for value in row]
    if not reference_values or len(reference_values) != len(candidate_values):
        _fail("golden_mismatch", "canonical output has an incompatible numeric shape")
    mismatch_count = 0
    first_mismatch: dict[str, Any] | None = None
    maximum_absolute_error = 0.0
    absolute_error_sum = 0.0
    squared_error_sum = 0.0
    maximum_relative_error: float | None = None
    for index, (reference_value, candidate_value) in enumerate(
        zip(reference_values, candidate_values, strict=True)
    ):
        absolute_error = abs(candidate_value - reference_value)
        admitted = tolerance + tolerance * abs(reference_value)
        if absolute_error > admitted:
            mismatch_count += 1
            if first_mismatch is None:
                first_mismatch = {
                    "row_index": index // row_width,
                    "column_index": index % row_width,
                    "reference": reference_value,
                    "candidate": candidate_value,
                }
        maximum_absolute_error = max(maximum_absolute_error, absolute_error)
        absolute_error_sum += absolute_error
        squared_error_sum += absolute_error * absolute_error
        if reference_value != 0.0:
            relative_error = absolute_error / abs(reference_value)
            maximum_relative_error = max(maximum_relative_error or 0.0, relative_error)
    compared_count = len(reference_values)
    return {
        "compared_count": compared_count,
        "mismatch_count": mismatch_count,
        "first_mismatch": first_mismatch,
        "maximum_absolute_error": maximum_absolute_error,
        "mean_absolute_error": absolute_error_sum / compared_count,
        "rmse": math.sqrt(squared_error_sum / compared_count),
        "maximum_relative_error": maximum_relative_error,
        "absolute_tolerance": tolerance,
        "relative_tolerance": tolerance,
    }


def _independent_output_comparison(
    golden_case: Mapping[str, Any], canonical_output: Mapping[str, Any]
) -> dict[str, Any]:
    numeric = {
        "logits": _numeric_comparison(
            golden_case["logits"],
            canonical_output["logits"],
            row_width=128,
            tolerance=5.0e-4,
        ),
        "full_probabilities": _numeric_comparison(
            golden_case["full_softmax_probabilities"],
            canonical_output["full_probabilities"],
            row_width=128,
            tolerance=1.0e-6,
        ),
        "selected_probabilities": _numeric_comparison(
            golden_case["selected_probabilities"],
            canonical_output["selected_probabilities"],
            row_width=8,
            tolerance=1.0e-6,
        ),
        "normalized_weights": _numeric_comparison(
            golden_case["normalized_weights"],
            canonical_output["normalized_weights"],
            row_width=8,
            tolerance=1.0e-6,
        ),
    }
    id_mismatch_count = 0
    order_mismatch_count = 0
    for reference_ids, candidate_ids in zip(
        golden_case["selected_expert_ids"],
        canonical_output["selected_expert_ids"],
        strict=True,
    ):
        id_mismatch_count += len(set(reference_ids).difference(candidate_ids))
        order_mismatch_count += sum(
            left != right
            for left, right in zip(reference_ids, candidate_ids, strict=True)
        )
    passed = (
        id_mismatch_count == 0
        and order_mismatch_count == 0
        and all(item["mismatch_count"] == 0 for item in numeric.values())
    )
    return {
        **numeric,
        "id_mismatch_count": id_mismatch_count,
        "order_mismatch_count": order_mismatch_count,
        "passed": passed,
    }


def _validate_canonical_output(
    value: Any,
    *,
    golden_case: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    fields = {
        "case_id",
        "case_scope",
        "row_count",
        "logits_shape",
        "logits",
        "logits_f32le_sha256",
        "full_probabilities_shape",
        "full_probabilities",
        "full_probabilities_f32le_sha256",
        "selected_expert_ids",
        "selected_expert_ids_u32le_sha256",
        "selected_probabilities",
        "selected_probabilities_f32le_sha256",
        "normalized_weights",
        "normalized_weights_f32le_sha256",
        "complete_output_sha256",
    }
    output = _closed(value, fields, label="generated canonical output")
    if (
        output["case_id"] != GOLDEN_CASE_ID
        or output["case_scope"] != "synthetic_fixture"
        or output["row_count"] != 1
        or output["logits_shape"] != [1, 128]
        or output["full_probabilities_shape"] != [1, 128]
    ):
        _fail("golden_mismatch", "generated canonical output identity is inconsistent")
    logits = [_vector(output["logits"], length=128, label="canonical logits")]
    probabilities = [
        _vector(
            output["full_probabilities"],
            length=128,
            label="canonical full probabilities",
        )
    ]
    selected_ids = _matrix(
        output["selected_expert_ids"],
        rows=1,
        columns=8,
        label="canonical selected expert IDs",
        integers=True,
    )
    selected = _matrix(
        output["selected_probabilities"],
        rows=1,
        columns=8,
        label="canonical selected probabilities",
    )
    normalized = _matrix(
        output["normalized_weights"],
        rows=1,
        columns=8,
        label="canonical normalized weights",
    )
    if len(set(selected_ids[0])) != 8:
        _fail("golden_mismatch", "canonical selected expert IDs are not unique")
    if any(value < 0.0 for row in probabilities for value in row):
        _fail("golden_mismatch", "canonical full probabilities contain a negative value")
    if any(value < 0.0 for row in selected for value in row):
        _fail("golden_mismatch", "canonical selected probabilities contain a negative value")
    if any(value < 0.0 for row in normalized for value in row):
        _fail("golden_mismatch", "canonical normalized weights contain a negative value")

    encoded_logits = _f32le(logits)
    encoded_probabilities = _f32le(probabilities)
    encoded_ids = _u32le(selected_ids)
    encoded_selected = _f32le(selected)
    encoded_normalized = _f32le(normalized)
    recomputed = {
        "logits_f32le_sha256": hashlib.sha256(encoded_logits).hexdigest(),
        "full_probabilities_f32le_sha256": hashlib.sha256(
            encoded_probabilities
        ).hexdigest(),
        "selected_expert_ids_u32le_sha256": hashlib.sha256(encoded_ids).hexdigest(),
        "selected_probabilities_f32le_sha256": hashlib.sha256(
            encoded_selected
        ).hexdigest(),
        "normalized_weights_f32le_sha256": hashlib.sha256(
            encoded_normalized
        ).hexdigest(),
        "complete_output_sha256": hashlib.sha256(
            encoded_logits
            + encoded_probabilities
            + encoded_ids
            + encoded_selected
            + encoded_normalized
        ).hexdigest(),
    }
    if any(output[name] != digest for name, digest in recomputed.items()):
        _fail("golden_mismatch", "canonical actual-output hashes do not match its values")
    canonical = dict(output)
    canonical_for_comparison = {
        **canonical,
        "logits": logits,
        "full_probabilities": probabilities,
    }
    independent = _independent_output_comparison(golden_case, canonical_for_comparison)
    if independent["passed"] is not True:
        _fail("golden_mismatch", "canonical actual output differs from golden tolerance or order")
    return canonical, recomputed, independent


def _validate_positive_cases(
    candidate_cases: Any,
    golden: Mapping[str, Any],
    golden_hashes: Mapping[str, Mapping[str, str]],
    canonical_output: Mapping[str, Any],
    canonical_hashes: Mapping[str, str],
    independent_comparison: Mapping[str, Any],
) -> None:
    if not isinstance(candidate_cases, list) or len(candidate_cases) != 2:
        _fail("golden_mismatch", "candidate must retain exactly two positive cases")
    fields = {
        "backend",
        "case_id",
        "fixture_kind",
        "case_scope",
        "validation_mode",
        "real_checkpoint_evidence",
        "requested_device",
        "selected_device",
        "fallback_used",
        "evaluated",
        "synchronized",
        "operation",
        "batch_size",
        "hidden_width",
        "expert_count",
        "top_k",
        "output_dtype",
        "selected_expert_ids",
        "hashes",
        "comparison",
        "memory_gauges",
        "status",
    }
    hash_fields = {
        "logits_f32le_sha256",
        "full_probabilities_f32le_sha256",
        "selected_probabilities_f32le_sha256",
        "normalized_weights_f32le_sha256",
    }
    for index, case_id in enumerate((GOLDEN_CASE_ID, TWO_ROW_CASE_ID)):
        rows = index + 1
        item = _closed(candidate_cases[index], fields, label="candidate positive case")
        fixed = {
            "backend": "apple-mlx",
            "case_id": case_id,
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
            "batch_size": rows,
            "hidden_width": 2048,
            "expert_count": 128,
            "top_k": 8,
            "output_dtype": "float32",
            "status": "passed",
        }
        if any(item[name] != expected for name, expected in fixed.items()):
            _fail("golden_mismatch", "candidate positive execution identity is inconsistent")
        expected_case = golden["cases"][case_id]
        if item["selected_expert_ids"] != expected_case["selected_expert_ids"]:
            _fail("golden_mismatch", "candidate selected expert IDs differ from golden")
        hashes = _closed(item["hashes"], hash_fields, label="candidate output hashes")
        for name, digest in hashes.items():
            _sha256(digest, label=f"candidate {name}")
        if hashes["logits_f32le_sha256"] != golden_hashes[case_id]["logits_f32le_sha256"]:
            _fail("golden_mismatch", "candidate generated logits hash differs from golden")
        comparison = _closed(
            item["comparison"],
            {
                "logits",
                "full_probabilities",
                "selected_probabilities",
                "normalized_weights",
                "id_mismatch_count",
                "order_mismatch_count",
                "passed",
            },
            label="candidate router comparison",
        )
        if (
            comparison["id_mismatch_count"] != 0
            or comparison["order_mismatch_count"] != 0
            or comparison["passed"] is not True
        ):
            _fail("golden_mismatch", "candidate router comparison did not pass")
        _validate_numeric_comparison(
            comparison["logits"],
            label="candidate logits comparison",
            compared_count=rows * 128,
            tolerance=5.0e-4,
        )
        for name, count in (
            ("full_probabilities", rows * 128),
            ("selected_probabilities", rows * 8),
            ("normalized_weights", rows * 8),
        ):
            _validate_numeric_comparison(
                comparison[name],
                label=f"candidate {name} comparison",
                compared_count=count,
                tolerance=1.0e-6,
            )
        _validate_memory_gauges(item["memory_gauges"])
        if index == 0:
            expected_hashes = {
                "logits_f32le_sha256": canonical_hashes["logits_f32le_sha256"],
                "full_probabilities_f32le_sha256": canonical_hashes[
                    "full_probabilities_f32le_sha256"
                ],
                "selected_probabilities_f32le_sha256": canonical_hashes[
                    "selected_probabilities_f32le_sha256"
                ],
                "normalized_weights_f32le_sha256": canonical_hashes[
                    "normalized_weights_f32le_sha256"
                ],
            }
            if (
                hashes != expected_hashes
                or item["selected_expert_ids"]
                != canonical_output["selected_expert_ids"]
                or comparison != independent_comparison
            ):
                _fail(
                    "golden_mismatch",
                    "producer comparison or component hashes differ from independent recomputation",
                )


def _validate_tie_cases(candidate_cases: Any, ties: Mapping[str, Any]) -> None:
    if not isinstance(candidate_cases, list) or len(candidate_cases) != 2:
        _fail("golden_mismatch", "candidate tie inventory is incomplete")
    source_cases = ties.get("cases")
    if not isinstance(source_cases, list) or len(source_cases) != 2:
        _fail("golden_mismatch", "committed tie inventory is invalid")
    fields = {
        "case_id",
        "kind",
        "fixture_kind",
        "case_scope",
        "validation_mode",
        "mlx_executed",
        "real_checkpoint_evidence",
        "cutoff",
        "selected_expert_ids",
        "hashes",
        "status",
    }
    hash_names = {
        "logits_f32le_sha256",
        "full_probabilities_f32le_sha256",
        "selected_probabilities_f32le_sha256",
        "normalized_weights_f32le_sha256",
    }
    for item_value, source in zip(candidate_cases, source_cases, strict=True):
        item = _closed(item_value, fields, label="candidate tie case")
        source_hashes = source.get("hashes")
        if not isinstance(source_hashes, dict):
            _fail("golden_mismatch", "committed tie hashes are invalid")
        expected_hashes = {
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
        }
        hashes = _closed(item["hashes"], hash_names, label="candidate tie hashes")
        expected = {
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
            "hashes": expected_hashes,
            "status": "passed",
        }
        if item != expected or hashes != expected_hashes:
            _fail("golden_mismatch", "candidate tie case differs from committed golden")


def _validate_negative_cases(candidate_cases: Any, negatives: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(candidate_cases, list) or len(candidate_cases) != 7:
        _fail("manifest_mismatch", "candidate negative inventory is incomplete")
    fields = {
        "fixture",
        "fixture_id",
        "category",
        "validation_surface",
        "expected_code",
        "must_precede",
        "accepted_result",
        "router_runner_called",
        "validation_mode",
        "mlx_executed",
        "mutation",
        "status",
    }
    for relative, item_value, document in zip(
        EXPECTED_MANIFEST_FILES[3:10], candidate_cases, negatives, strict=True
    ):
        item = _closed(item_value, fields, label="candidate negative case")
        case = document.get("case")
        if not isinstance(case, dict) or not isinstance(case.get("expected_failure"), dict):
            _fail("manifest_mismatch", "a committed negative fixture is invalid")
        failure = case["expected_failure"]
        expected = {
            "fixture": relative,
            "fixture_id": document.get("fixture_id"),
            "category": case.get("category"),
            "validation_surface": case.get("validation_surface"),
            "expected_code": failure.get("code"),
            "must_precede": failure.get("must_precede"),
            "accepted_result": False,
            "router_runner_called": False,
            "validation_mode": "fixture_contract_validation",
            "mlx_executed": False,
            "mutation": case.get("mutation"),
            "status": "covered",
        }
        if item != expected:
            _fail("manifest_mismatch", "candidate negative case differs from its fixture")


def _validate_runtime(value: Any) -> None:
    runtime = _closed(
        value,
        {
            "protocol",
            "worker_version",
            "python_version",
            "python_arch",
            "mlx_version",
            "macos_version",
            "metal_available",
            "gpu_count",
            "operations",
            "model_operation_advertised",
        },
        label="candidate runtime",
    )
    if (
        runtime["protocol"] != 1
        or runtime["worker_version"] != "0.1.0"
        or runtime["python_arch"] != "arm64"
        or runtime["mlx_version"] != "0.32.0"
        or runtime["metal_available"] is not True
        or runtime["gpu_count"] != 1
        or runtime["operations"]
        != [
            "health",
            "tensor_probe",
            "run_fixture",
            "run_router",
            "run_synthetic_moe",
            "shutdown",
        ]
        or runtime["model_operation_advertised"] is not False
    ):
        _fail("execution_mismatch", "candidate runtime identity is inconsistent")
    _bounded_string(runtime["python_version"], label="runtime Python version", maximum=64)
    _bounded_string(runtime["macos_version"], label="runtime macOS version", maximum=64)


def _validate_benchmark(
    value: Any,
    manifest_sha256: str,
    *,
    golden_case: Mapping[str, Any],
) -> tuple[
    list[dict[str, Any]],
    str,
    dict[str, Any],
    dict[str, str],
    dict[str, Any],
]:
    benchmark = _closed(
        value,
        {
            "benchmark_id",
            "case_id",
            "fixture_kind",
            "evidence_level",
            "model_free",
            "real_checkpoint_evidence",
            "manifest_sha256",
            "status",
            "passed",
            "warmup_count",
            "measurement_count",
            "retained_observation_count",
            "complete_output_sha256",
            "canonical_output",
            "stage_sum_claimed",
            "timing_series",
            "result_records",
            "failure",
            "exclusions",
        },
        label="generated router benchmark",
    )
    fixed = {
        "benchmark_id": BENCHMARK_ID,
        "case_id": GOLDEN_CASE_ID,
        "fixture_kind": "synthetic",
        "evidence_level": "synthetic_fixture_only",
        "model_free": True,
        "real_checkpoint_evidence": False,
        "manifest_sha256": manifest_sha256,
        "status": "passed",
        "passed": True,
        "warmup_count": WARMUP_COUNT,
        "measurement_count": MEASUREMENT_COUNT,
        "retained_observation_count": ATTEMPT_COUNT,
        "stage_sum_claimed": False,
        "failure": None,
        "exclusions": BENCHMARK_EXCLUSIONS,
    }
    if any(benchmark[name] != expected for name, expected in fixed.items()):
        _fail("candidate_not_passed", "generated router benchmark is incomplete or failed")
    output_sha256 = _sha256(
        benchmark["complete_output_sha256"],
        label="generated benchmark complete output SHA-256",
    )
    canonical_output, canonical_hashes, independent_comparison = (
        _validate_canonical_output(
            benchmark["canonical_output"],
            golden_case=golden_case,
        )
    )
    if canonical_hashes["complete_output_sha256"] != output_sha256:
        _fail(
            "result_bijection",
            "generated complete output hash is not bound to the canonical actual output",
        )

    series = _closed(
        benchmark["timing_series"],
        {
            "benchmark_id",
            "case_id",
            "row_count",
            "series_kind",
            "replication_role",
            "process_replication_id",
            "process_state",
            "condition",
            "instrumentation_mode",
            "warmup_count",
            "measurement_count",
            "raw_timing_observations",
        },
        label="generated timing series",
    )
    series_fixed = {
        "benchmark_id": BENCHMARK_ID,
        "case_id": GOLDEN_CASE_ID,
        "row_count": 1,
        "series_kind": "inexpensive_synthetic",
        "replication_role": "primary",
        "process_replication_id": PROCESS_REPLICATION_ID,
        "process_state": "reused_process",
        "condition": "warm",
        "instrumentation_mode": "minimally_instrumented",
        "warmup_count": WARMUP_COUNT,
        "measurement_count": MEASUREMENT_COUNT,
    }
    if any(series[name] != expected for name, expected in series_fixed.items()):
        _fail("timing_contract", "generated timing series identity is inconsistent")

    observations = series["raw_timing_observations"]
    result_records = benchmark["result_records"]
    if (
        not isinstance(observations, list)
        or len(observations) != ATTEMPT_COUNT
        or not isinstance(result_records, list)
        or len(result_records) != ATTEMPT_COUNT
    ):
        _fail("timing_contract", "generated benchmark does not retain exactly 5+30 attempts")

    observation_fields = {
        "observation_id",
        "run_index",
        "observation_kind",
        "process_replication_id",
        "process_state",
        "condition",
        "instrumentation_mode",
        "monotonic_clock",
        "stages",
        "status",
        "requested_device",
        "selected_device",
        "fallback_used",
        "evaluated",
        "synchronized",
        "output_sha256",
        "correctness_passed",
    }
    result_fields = {
        "observation_id",
        "backend",
        "requested_device",
        "selected_device",
        "fallback_used",
        "evaluated",
        "synchronized",
        "golden_comparison_passed",
        "output_sha256",
        "memory_gauges",
        "status",
    }
    canonical: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    result_by_id: dict[str, dict[str, Any]] = {}
    for raw_result in result_records:
        result = _closed(raw_result, result_fields, label="generated benchmark result record")
        observation_id = _bounded_string(
            result["observation_id"], label="result observation identity", maximum=128
        )
        if observation_id in result_by_id:
            _fail("result_bijection", "generated result records reuse an observation identity")
        if (
            result["backend"] != "apple-mlx"
            or result["requested_device"] != "gpu"
            or result["selected_device"] != "gpu"
            or result["fallback_used"] is not False
            or result["evaluated"] is not True
            or result["synchronized"] is not True
            or result["golden_comparison_passed"] is not True
            or result["output_sha256"] != output_sha256
            or result["status"] != "passed"
        ):
            _fail("result_bijection", "generated result record is not an evaluated MLX GPU pass")
        _validate_memory_gauges(result["memory_gauges"])
        result_by_id[observation_id] = result

    for attempt_index, raw_observation in enumerate(observations):
        observation = _closed(
            raw_observation,
            observation_fields,
            label="generated timing observation",
        )
        if attempt_index < WARMUP_COUNT:
            kind = "warmup"
            run_index = attempt_index
        else:
            kind = "measurement"
            run_index = attempt_index - WARMUP_COUNT
        expected_id = f"generated-router-{kind}-{run_index:02}"
        if (
            observation["observation_id"] != expected_id
            or observation["run_index"] != run_index
            or observation["observation_kind"] != kind
            or observation["process_replication_id"] != PROCESS_REPLICATION_ID
            or observation["process_state"] != "reused_process"
            or observation["condition"] != "warm"
            or observation["instrumentation_mode"] != "minimally_instrumented"
            or observation["monotonic_clock"] != "perf_counter_ns"
            or observation["status"] != "passed"
            or observation["requested_device"] != "gpu"
            or observation["selected_device"] != "gpu"
            or observation["fallback_used"] is not False
            or observation["evaluated"] is not True
            or observation["synchronized"] is not True
            or observation["output_sha256"] != output_sha256
            or observation["correctness_passed"] is not True
        ):
            _fail("timing_contract", "generated timing observation order or state is inconsistent")
        if expected_id in seen_ids:
            _fail("timing_contract", "generated timing observation identity is duplicated")
        seen_ids.add(expected_id)
        if expected_id not in result_by_id:
            _fail("result_bijection", "generated timing observation lacks its result record")
        stages = _closed(
            observation["stages"],
            {"dequantization", "total_evaluated_router"},
            label="generated timing stages",
        )
        dequantization = _closed(
            stages["dequantization"],
            {"status", "reason"},
            label="generated dequantization timing stage",
        )
        total = _closed(
            stages["total_evaluated_router"],
            {"status", "duration_ns"},
            label="generated total timing stage",
        )
        if dequantization != {
            "status": "not_applicable",
            "reason": "f32_router_requires_no_dequantization",
        }:
            _fail("timing_contract", "F32 generated router dequantization is not explicit")
        duration_ns = _plain_int(
            total["duration_ns"], label="generated total duration", minimum=1
        )
        if total["status"] != "observed":
            _fail("timing_contract", "generated total duration is not observed")
        canonical.append(
            {
                "observation_id": expected_id,
                "observation_kind": kind,
                "process_replication_id": PROCESS_REPLICATION_ID,
                "process_state": "reused_process",
                "condition": "warm",
                "instrumentation_mode": "minimally_instrumented",
                "stage": "total_evaluated_router",
                "requested_device": "gpu",
                "selected_device": "gpu",
                "duration_ns": duration_ns,
            }
        )
    if seen_ids != set(result_by_id):
        _fail("result_bijection", "generated timing/result identities are not bijective")
    return (
        canonical,
        output_sha256,
        canonical_output,
        canonical_hashes,
        independent_comparison,
    )


def _validate_environment(
    value: Mapping[str, Any], candidate: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment_fields = {
        "platform",
        "selected_backend",
        "selected_device",
        "safe_environment",
        "interference_admission",
        "interference_reasons",
        "before_snapshot",
        "after_snapshot",
        "benchmark_resources",
    }
    environment = _closed(value, environment_fields, label="generated benchmark environment")
    try:
        assert_public_safe(environment)
        resources = extract_benchmark_resources(candidate)
    except Exception:
        _fail("resource_mismatch", "generated benchmark resources are invalid or private")
    if environment["benchmark_resources"] != resources:
        _fail("resource_mismatch", "environment resources do not match the validated candidate")
    before = environment["before_snapshot"]
    after = environment["after_snapshot"]
    if not isinstance(before, dict) or not isinstance(after, dict):
        _fail("environment_mismatch", "generated benchmark requires paired environment snapshots")
    try:
        recombined = combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after,
            after_unavailable_reason=None,
            benchmark_resources=resources,
        )
    except Exception:
        _fail("environment_mismatch", "generated benchmark environment pair is invalid")
    if environment != recombined:
        _fail("environment_mismatch", "generated benchmark environment is not canonical")
    if (
        environment["platform"] != "macos-arm64"
        or environment["selected_backend"] != "apple-mlx"
        or environment["selected_device"] != "gpu"
        or environment["interference_admission"] != "admitted"
        or environment["interference_reasons"] != []
    ):
        _fail("environment_mismatch", "generated benchmark environment was not admitted")
    observations = before.get("observations")
    if not isinstance(observations, dict):
        _fail("environment_mismatch", "generated benchmark before-snapshot is incomplete")
    repository_commit = observations.get("repository_commit")
    memory_pressure = observations.get("memory_pressure")
    power_mode = observations.get("power_mode")
    thermal_state = observations.get("thermal_state")
    if (
        not isinstance(repository_commit, dict)
        or repository_commit.get("status") != "observed"
        or not isinstance(memory_pressure, dict)
        or memory_pressure.get("status") != "observed"
        or not isinstance(power_mode, dict)
        or power_mode.get("status") not in {"observed", "unavailable"}
        or not isinstance(thermal_state, dict)
        or thermal_state.get("status") != "observed"
    ):
        _fail("environment_mismatch", "generated benchmark compatibility facts are incomplete")
    source_commit = repository_commit.get("value")
    _commit(source_commit, label="generated benchmark source commit")
    if memory_pressure.get("value") != "normal":
        _fail("environment_mismatch", "generated benchmark memory pressure was not normal")
    if power_mode.get("status") == "observed" and power_mode.get("value") not in {
        "automatic",
        "normal",
    }:
        _fail("environment_mismatch", "generated benchmark power mode was not admitted")
    if thermal_state.get("value") != "nominal":
        _fail("environment_mismatch", "generated benchmark thermal state was not nominal")
    return {"repository_commit": source_commit}, resources


def _project_and_summarize(
    observations: Sequence[Mapping[str, Any]],
    environment: Mapping[str, Any],
    *,
    source_commit: str,
) -> list[dict[str, Any]]:
    projection_record = {
        "experiment_id": BENCHMARK_ID,
        "source_commit": source_commit,
        "environment": environment,
        "raw_observations": [
            {
                "observation_id": observation["observation_id"],
                "case_id": GOLDEN_CASE_ID,
                "batch_id": SYNTHETIC_BATCH_ID,
                "process_replication_id": observation["process_replication_id"],
                "observation_kind": observation["observation_kind"],
                "status": "passed",
                "process_state": observation["process_state"],
                "condition": observation["condition"],
                "instrumentation_mode": observation["instrumentation_mode"],
                "requested_device": observation["requested_device"],
                "selected_device": observation["selected_device"],
                "durations_ns": {
                    "total_evaluated_router": {
                        "status": "observed",
                        "duration_ns": observation["duration_ns"],
                    }
                },
            }
            for observation in observations
        ],
    }
    try:
        rows = project_timing_rows(projection_record)
        grouped = group_raw_observations(rows)
    except (KeyError, TypeError, ValueError) as error:
        _fail("statistics_mismatch", f"canonical timing grouping failed: {error}")
    if (
        len(rows) != ATTEMPT_COUNT
        or any(row.get("stage") != "total_evaluated_router" for row in rows)
    ):
        _fail("statistics_mismatch", "canonical timing projection is incomplete")
    if len(grouped) != 2:
        _fail("statistics_mismatch", "generated warm-up and measurement groups are not distinct")

    projected: list[dict[str, Any]] = []
    order = {"warmup": 0, "measurement": 1}
    for key, group in sorted(
        grouped.items(),
        key=lambda item: order.get(str(item[0][4]), 99),
    ):
        compatibility = {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in zip(COMPATIBILITY_FIELDS, key, strict=True)
        }
        kind = compatibility["observation_kind"]
        expected_count = WARMUP_COUNT if kind == "warmup" else MEASUREMENT_COUNT
        if kind not in {"warmup", "measurement"} or len(group) != expected_count:
            _fail("statistics_mismatch", "generated timing group sample count is inconsistent")
        durations = [row["duration_ns"] for row in group]
        try:
            summary = summarize_nanoseconds(durations)
        except (TypeError, ValueError) as error:
            _fail("statistics_mismatch", f"generated timing summary failed: {error}")
        projected.append(
            {
                "group": compatibility,
                "included_observation_ids": [row["observation_id"] for row in group],
                "summary": summary,
            }
        )
    return projected


def validate_generated_candidate(
    candidate: Mapping[str, Any],
    environment: Mapping[str, Any],
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate and deterministically summarize one external generated run."""

    for _ in _bounded_walk(candidate):
        pass
    try:
        assert_public_safe(candidate)
    except Exception:
        _fail("private_value", "generated candidate contains a forbidden private value")
    _validate_contract_schema(repository_root)
    root = _closed(candidate, ROOT_FIELDS, label="generated router candidate")
    fixed = {
        "schema_version": 1,
        "validation": "qwen3moe-router-fixtures",
        "status": "passed",
        "passed": True,
        "fixture_kind": "synthetic",
        "evidence_level": "synthetic_fixture_only",
        "model_free": True,
        "real_checkpoint_evidence": False,
        "external_checkpoint_accessed": False,
        "failure": None,
        "warnings": ROOT_WARNINGS,
        "exclusions": ROOT_EXCLUSIONS,
    }
    if any(root[name] != expected for name, expected in fixed.items()):
        _fail("candidate_not_passed", "generated candidate failure state is inconsistent")
    _validate_runtime(root["runtime"])
    cleanup = _closed(
        root["cleanup"],
        {"attempted", "outcome", "exit_code", "message"},
        label="generated candidate cleanup",
    )
    if cleanup != {
        "attempted": True,
        "outcome": "graceful",
        "exit_code": 0,
        "message": None,
    }:
        _fail("candidate_not_passed", "generated candidate worker cleanup was not graceful")

    _, golden, ties, negatives = _validate_manifest(root, repository_root)
    golden_hashes = _validate_golden_document(golden)
    _validate_tie_cases(root["synthetic_tie_cases"], ties)
    _validate_negative_cases(root["negative_cases"], negatives)
    (
        projected_observations,
        candidate_output_sha256,
        canonical_output,
        canonical_hashes,
        independent_comparison,
    ) = _validate_benchmark(
        root["generated_router_microbenchmark"],
        root["manifest_sha256"],
        golden_case=golden["cases"][GOLDEN_CASE_ID],
    )
    _validate_positive_cases(
        root["positive_cases"],
        golden,
        golden_hashes,
        canonical_output,
        canonical_hashes,
        independent_comparison,
    )
    environment_facts, resources = _validate_environment(environment, root)
    timing_groups = _project_and_summarize(
        projected_observations,
        environment,
        source_commit=environment_facts["repository_commit"],
    )

    report = {
        "validation_schema": VALIDATION_SCHEMA,
        "validation_schema_version": VALIDATION_SCHEMA_VERSION,
        "status": "passed",
        "fixture_id": FIXTURE_ID,
        "manifest_sha256": root["manifest_sha256"],
        "benchmark_id": BENCHMARK_ID,
        "case_id": GOLDEN_CASE_ID,
        "source_commit": environment_facts["repository_commit"],
        "candidate_complete_output_sha256": candidate_output_sha256,
        "golden_complete_output_sha256": golden_hashes[GOLDEN_CASE_ID][
            "complete_output_sha256"
        ],
        "warmup_count": WARMUP_COUNT,
        "measurement_count": MEASUREMENT_COUNT,
        "retained_observation_count": ATTEMPT_COUNT,
        "stage_sum_claimed": False,
        "independent_golden_comparison": independent_comparison,
        "timing_groups": timing_groups,
        "benchmark_resources": resources,
    }
    try:
        assert_public_safe(report)
    except Exception:
        _fail("private_value", "generated validation report is not public-safe")
    return report


def _write_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail("unsafe_output", "generated validation output already exists")
    payload = (
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        _fail("unsafe_output", "generated validation output already exists")
    except OSError:
        _fail("unsafe_output", "generated validation output could not be written")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        candidate = _load_external_json(
            args.candidate,
            maximum_bytes=MAX_CANDIDATE_BYTES,
            label="generated router candidate",
        )
        environment = _load_external_json(
            args.environment,
            maximum_bytes=MAX_CANDIDATE_BYTES,
            label="generated benchmark environment",
        )
        report = validate_generated_candidate(candidate, environment)
        if args.output is None:
            json.dump(report, sys.stdout, indent=2, sort_keys=True, allow_nan=False)
            sys.stdout.write("\n")
        else:
            _write_exclusive(args.output, report)
    except CandidateValidationError as error:
        print(f"validate-generated-candidate: {error.code}: {error.public_message}", file=sys.stderr)
        return 2
    print("validate-generated-candidate: passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

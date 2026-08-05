#!/usr/bin/env python3
"""Independent, CPU-only oracle for the bounded Feature 002 router.

The canonical calculation in this module is deliberately scalar.  Every
multiply and every addition is rounded to IEEE-754 binary32 before the next
operation.  NumPy is loaded lazily and is used only as an independently
implemented cross-check; it is never the source of canonical router values.

The command-line entry point is local-only.  It requires an already existing,
pinned llama.cpp checkout, two externally produced capture attempts, and the
operator-supplied checkpoint.  It has no acquisition or fallback path.
"""

from __future__ import annotations

import argparse
import ast
import ctypes
import errno
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, Protocol, Sequence


PINNED_LLAMA_CPP_REVISION = "b06aa774c03dbbb624e726664b714a57d1f49815"
PINNED_LLAMA_CPP_REPOSITORY = "https://github.com/ggml-org/llama.cpp.git"
PINNED_LLAMA_CPP_LICENSE = "MIT"

EXPECTED_MODEL_FILENAME = "Qwen3-30B-A3B-Q8_0.gguf"
EXPECTED_MODEL_SIZE_BYTES = 32_483_931_648
EXPECTED_MODEL_SHA256 = (
    "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
)
ROUTER_TENSOR_NAME = "blk.0.ffn_gate_inp.weight"

HIDDEN_WIDTH = 2_048
EXPERT_COUNT = 128
TOP_K = 8
CAPTURE_ROWS = 2
CAPTURE_FLOAT_COUNT = CAPTURE_ROWS * HIDDEN_WIDTH
CAPTURE_BYTE_LENGTH = CAPTURE_FLOAT_COUNT * 4

LOGIT_ATOL = 5.0e-4
LOGIT_RTOL = 5.0e-4
PROBABILITY_ATOL = 1.0e-6
PROBABILITY_RTOL = 1.0e-6

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ERROR_MESSAGE = 512
_MAX_SOURCE_BYTES = 1_048_576
_MAX_JSON_BYTES = 262_144
_MAX_SCHEDULER_TRACE_BYTES = 8_388_608
_MAX_CANONICAL_FLOATS = EXPERT_COUNT * HIDDEN_WIDTH
_FORBIDDEN_IMPORT_ROOTS = frozenset(("mlx", "pulsar_mlx_worker"))
_SCHEDULER_TRACE_BEGIN = "PULSARMLX_SCHED_TRACE_BEGIN_V1"
_SCHEDULER_TRACE_END = "PULSARMLX_SCHED_TRACE_END_V1"
_SCHEDULER_SPLIT_RE = re.compile(
    r"## SPLIT #([0-9]{1,6}):[ \t]*([^#\r\n]+?)[ \t]+#[ \t]+"
    r"([0-9]{1,7})[ \t]+inputs(?:[ \t][^\r\n]*)?"
)
_MAX_SCHEDULER_INPUT_COUNT = 1_000_000
_CANDIDATE_ARTIFACTS = (
    "oracle.json",
    "capture-a.f32le",
    "capture-a.json",
    "capture-a.scheduler-trace.txt",
    "capture-b.f32le",
    "capture-b.json",
    "capture-b.scheduler-trace.txt",
    "capture-provenance.json",
    "execution-provenance.json",
)
_COMPLETE_CANDIDATE_FILES = frozenset((*_CANDIDATE_ARTIFACTS, "bundle-manifest.json"))


class RouterOracleError(ValueError):
    """A stable, bounded failure safe to surface without private values."""

    def __init__(self, code: str, message: str) -> None:
        safe_code = code if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) else "oracle_error"
        safe_message = " ".join(str(message).split())[:_MAX_ERROR_MESSAGE]
        if not safe_message:
            safe_message = "router oracle validation failed"
        super().__init__(safe_message)
        self.code = safe_code
        self.message = safe_message


def _fail(code: str, message: str) -> None:
    raise RouterOracleError(code, message)


def _is_plain_number(value: object) -> bool:
    return type(value) in (int, float)


def _f32(value: object, *, code: str = "non_finite_value") -> float:
    if not _is_plain_number(value):
        _fail("invalid_dtype", "a router numeric value is not a plain number")
    try:
        rounded = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    except (OverflowError, struct.error, ValueError):
        _fail(code, "a router numeric value cannot be represented as float32")
    if not math.isfinite(rounded):
        _fail(code, "a router numeric value is not finite")
    return rounded


def _f32_multiply(left: object, right: object) -> float:
    return _f32(_f32(left) * _f32(right))


def _f32_add(left: object, right: object) -> float:
    return _f32(_f32(left) + _f32(right))


def _validated_matrix(
    value: object,
    *,
    label: str,
    maximum_rows: int,
    maximum_columns: int,
    expected_columns: int | None = None,
) -> list[list[float]]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail("invalid_shape", f"{label} must be a bounded matrix")
    if not 1 <= len(value) <= maximum_rows:
        _fail("invalid_shape", f"{label} has an invalid row count")

    result: list[list[float]] = []
    width: int | None = None
    for row in value:
        if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
            _fail("invalid_shape", f"{label} contains a non-row value")
        if not 1 <= len(row) <= maximum_columns:
            _fail("invalid_shape", f"{label} has an invalid column count")
        if width is None:
            width = len(row)
        elif len(row) != width:
            _fail("invalid_shape", f"{label} is not rectangular")
        if expected_columns is not None and len(row) != expected_columns:
            _fail("invalid_shape", f"{label} has the wrong inner dimension")
        result.append([_f32(item) for item in row])
    return result


def _iter_numeric_values(values: object) -> Iterable[object]:
    if _is_plain_number(values):
        yield values
        return
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        _fail("invalid_dtype", "canonical float32 input is not numeric")
    for item in values:
        yield from _iter_numeric_values(item)


def canonical_f32_bytes(values: object) -> bytes:
    """Encode a bounded scalar or nested sequence as canonical f32le bytes."""

    encoded = bytearray()
    count = 0
    for value in _iter_numeric_values(values):
        count += 1
        if count > _MAX_CANONICAL_FLOATS:
            _fail("resource_limit", "canonical float32 input exceeds the oracle bound")
        encoded.extend(struct.pack("<f", _f32(value)))
    if count == 0:
        _fail("invalid_shape", "canonical float32 input is empty")
    return bytes(encoded)


def canonical_f32_sha256(values: object) -> str:
    return hashlib.sha256(canonical_f32_bytes(values)).hexdigest()


def canonical_u32_bytes(values: Iterable[int]) -> bytes:
    encoded = bytearray()
    count = 0
    for value in values:
        if type(value) is not int or not 0 <= value < EXPERT_COUNT:
            _fail("invalid_dtype", "an expert ID is outside the canonical range")
        count += 1
        if count > CAPTURE_ROWS * TOP_K:
            _fail("resource_limit", "expert ID output exceeds the oracle bound")
        encoded.extend(struct.pack("<I", value))
    if count == 0:
        _fail("invalid_shape", "expert ID output is empty")
    return bytes(encoded)


def scalar_f32_projection(
    hidden_rows: Sequence[Sequence[float]],
    weight_rows: Sequence[Sequence[float]],
) -> list[list[float]]:
    """Return ``hidden @ weight.T`` with step-rounded scalar F32 arithmetic."""

    hidden = _validated_matrix(
        hidden_rows,
        label="hidden rows",
        maximum_rows=CAPTURE_ROWS,
        maximum_columns=HIDDEN_WIDTH,
    )
    width = len(hidden[0])
    weights = _validated_matrix(
        weight_rows,
        label="weight rows",
        maximum_rows=EXPERT_COUNT,
        maximum_columns=HIDDEN_WIDTH,
        expected_columns=width,
    )

    projected: list[list[float]] = []
    for hidden_row in hidden:
        output_row: list[float] = []
        for weight_row in weights:
            accumulator = _f32(0.0)
            for hidden_value, weight_value in zip(hidden_row, weight_row):
                accumulator = _f32_add(
                    accumulator,
                    _f32_multiply(hidden_value, weight_value),
                )
            output_row.append(accumulator)
        projected.append(output_row)
    return projected


def full_softmax_f32(logits: Sequence[float]) -> list[float]:
    """Compute a complete, step-rounded F32 softmax for one bounded row."""

    if isinstance(logits, (str, bytes, bytearray)) or not isinstance(logits, Sequence):
        _fail("invalid_shape", "softmax input must be a bounded row")
    if not 1 <= len(logits) <= EXPERT_COUNT:
        _fail("invalid_shape", "softmax input has an invalid expert count")
    values = [_f32(value) for value in logits]
    maximum = max(values)
    exponentials: list[float] = []
    for value in values:
        shifted = _f32(_f32(value) - maximum)
        exponential = _f32(math.exp(shifted))
        exponentials.append(exponential)

    denominator = _f32(0.0)
    for value in exponentials:
        denominator = _f32_add(denominator, value)
    if not math.isfinite(denominator) or denominator <= 0.0:
        _fail("normalization_failed", "full-softmax denominator is not positive")
    return [_f32(value / denominator) for value in exponentials]


def select_top_k_f32(
    probabilities: Sequence[float],
    *,
    top_k: int = TOP_K,
) -> tuple[list[int], list[float], list[float]]:
    """Select descending probabilities, lower expert ID first on exact ties."""

    if isinstance(probabilities, (str, bytes, bytearray)) or not isinstance(
        probabilities, Sequence
    ):
        _fail("invalid_shape", "selection input must be a bounded row")
    values = [_f32(value) for value in probabilities]
    if not values or len(values) > EXPERT_COUNT:
        _fail("invalid_shape", "selection input has an invalid expert count")
    if type(top_k) is not int or not 1 <= top_k <= len(values):
        _fail("invalid_top_k", "top-k must fit inside the expert count")

    selected_ids = sorted(
        range(len(values)),
        key=lambda expert_id: (-values[expert_id], expert_id),
    )[:top_k]
    selected_probabilities = [values[expert_id] for expert_id in selected_ids]
    selected_sum = _f32(0.0)
    for value in selected_probabilities:
        selected_sum = _f32_add(selected_sum, value)
    if not math.isfinite(selected_sum) or selected_sum <= 0.0:
        _fail("normalization_failed", "selected-probability denominator is not positive")
    normalized_weights = [_f32(value / selected_sum) for value in selected_probabilities]
    return selected_ids, selected_probabilities, normalized_weights


class NumpyProjection(Protocol):
    def project_f32(
        self,
        hidden_rows: Sequence[Sequence[float]],
        weight_rows: Sequence[Sequence[float]],
        *,
        dtype: str,
    ) -> object: ...


class NumpyProjectionAdapter:
    """Lazy real-NumPy adapter kept separate from the canonical calculation."""

    def __init__(self) -> None:
        try:
            self._numpy = importlib.import_module("numpy")
        except (ImportError, OSError) as error:
            raise RouterOracleError(
                "numpy_unavailable",
                "the independent NumPy float32 cross-check is unavailable",
            ) from error

    @property
    def version(self) -> str:
        return str(getattr(self._numpy, "__version__", "unknown"))[:64]

    def project_f32(
        self,
        hidden_rows: Sequence[Sequence[float]],
        weight_rows: Sequence[Sequence[float]],
        *,
        dtype: str,
    ) -> object:
        if dtype != "float32":
            _fail("invalid_dtype", "NumPy cross-check must use float32")
        np = self._numpy
        hidden = np.asarray(hidden_rows, dtype=np.float32, order="C")
        weights = np.asarray(weight_rows, dtype=np.float32, order="C")
        result = np.asarray(hidden @ weights.T, dtype=np.float32, order="C")
        return result.tolist()


def cross_check_numpy_f32(
    hidden_rows: Sequence[Sequence[float]],
    weight_rows: Sequence[Sequence[float]],
    scalar_result: Sequence[Sequence[float]],
    *,
    numpy_adapter: NumpyProjection | None = None,
    absolute_tolerance: float = LOGIT_ATOL,
    relative_tolerance: float = LOGIT_RTOL,
) -> dict[str, object]:
    """Compare canonical scalar logits with an injected or real NumPy result."""

    hidden = _validated_matrix(
        hidden_rows,
        label="hidden rows",
        maximum_rows=CAPTURE_ROWS,
        maximum_columns=HIDDEN_WIDTH,
    )
    width = len(hidden[0])
    weights = _validated_matrix(
        weight_rows,
        label="weight rows",
        maximum_rows=EXPERT_COUNT,
        maximum_columns=HIDDEN_WIDTH,
        expected_columns=width,
    )
    scalar = _validated_matrix(
        scalar_result,
        label="scalar result",
        maximum_rows=CAPTURE_ROWS,
        maximum_columns=EXPERT_COUNT,
        expected_columns=len(weights),
    )
    if len(scalar) != len(hidden):
        _fail("invalid_shape", "scalar result has the wrong row count")

    atol = _f32(absolute_tolerance)
    rtol = _f32(relative_tolerance)
    if atol < 0.0 or rtol < 0.0:
        _fail("invalid_tolerance", "cross-check tolerances must be nonnegative")

    adapter = numpy_adapter if numpy_adapter is not None else NumpyProjectionAdapter()
    try:
        candidate_value = adapter.project_f32(hidden, weights, dtype="float32")
    except RouterOracleError:
        raise
    except Exception as error:
        raise RouterOracleError(
            "numpy_cross_check_failed",
            "the independent NumPy projection failed",
        ) from error
    candidate = _validated_matrix(
        candidate_value,
        label="NumPy result",
        maximum_rows=CAPTURE_ROWS,
        maximum_columns=EXPERT_COUNT,
        expected_columns=len(weights),
    )
    if len(candidate) != len(scalar):
        _fail("numpy_cross_check_failed", "NumPy result has the wrong row count")

    mismatch_count = 0
    first_mismatch: list[int] | None = None
    maximum_absolute_error = 0.0
    maximum_relative_error = 0.0
    for row_index, (reference_row, candidate_row) in enumerate(zip(scalar, candidate)):
        for column_index, (reference, observed) in enumerate(
            zip(reference_row, candidate_row)
        ):
            absolute_error = abs(float(observed) - float(reference))
            maximum_absolute_error = max(maximum_absolute_error, absolute_error)
            if reference != 0.0:
                maximum_relative_error = max(
                    maximum_relative_error,
                    absolute_error / abs(float(reference)),
                )
            threshold = float(atol) + float(rtol) * abs(float(reference))
            if absolute_error > threshold:
                mismatch_count += 1
                if first_mismatch is None:
                    first_mismatch = [row_index, column_index]

    if mismatch_count:
        _fail(
            "numpy_cross_check_failed",
            "the scalar and NumPy float32 projections differ outside the frozen tolerance",
        )
    return {
        "passed": True,
        "compared_count": len(scalar) * len(weights),
        "mismatch_count": 0,
        "first_mismatch": first_mismatch,
        "maximum_absolute_error": maximum_absolute_error,
        "maximum_relative_error": maximum_relative_error,
        "absolute_tolerance": float(atol),
        "relative_tolerance": float(rtol),
        "numpy_logits_f32le_sha256": canonical_f32_sha256(candidate),
    }


def validate_pinned_source(record: Mapping[str, object]) -> dict[str, object]:
    """Require the exact clean MIT llama.cpp CPU-only source identity."""

    if not isinstance(record, Mapping):
        _fail("source_identity_mismatch", "source identity must be an object")
    required = {
        "repository": PINNED_LLAMA_CPP_REPOSITORY,
        "revision": PINNED_LLAMA_CPP_REVISION,
        "clean": True,
        "license": PINNED_LLAMA_CPP_LICENSE,
        "metal": False,
        "gpu_offload": False,
    }
    for field, expected in required.items():
        if field not in record or type(record[field]) is not type(expected) or record[field] != expected:
            _fail(
                "source_identity_mismatch",
                "llama.cpp source identity or CPU-only configuration differs from the pin",
            )
    return {field: record[field] for field in required}


def _require_sha256(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(code, "a required SHA-256 identity is invalid")
    return value


def _validated_posix_identity(
    value: object,
    *,
    code: str,
    require_model_digest: bool,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _fail(code, "a runtime file identity must be an object")
    device = value.get("device")
    inode = value.get("inode")
    size_bytes = value.get("size_bytes")
    digest = _require_sha256(value.get("sha256"), code=code)
    if (
        type(device) is not int
        or device < 0
        or type(inode) is not int
        or inode <= 0
        or type(size_bytes) is not int
        or size_bytes <= 0
    ):
        _fail(code, "a runtime file identity has invalid metadata")
    identity = {
        "device": device,
        "inode": inode,
        "size_bytes": size_bytes,
        "sha256": digest,
    }
    if require_model_digest:
        if size_bytes != EXPECTED_MODEL_SIZE_BYTES or digest != EXPECTED_MODEL_SHA256:
            _fail(code, "runtime model identity differs from the admission")
    return identity


def validate_capture_provenance(record: Mapping[str, object]) -> dict[str, object]:
    """Bind both path-based capture consumers to one admitted model and helper."""

    if not isinstance(record, Mapping):
        _fail("capture_provenance_invalid", "capture provenance must be an object")
    if (
        record.get("schema") != "pulsarmlx.research.router-capture-provenance"
        or record.get("schema_version") != "1.0.0"
        or record.get("binding_strategy")
        != "pre_post_full_sha256_plus_device_inode_size"
    ):
        _fail("capture_provenance_invalid", "capture provenance contract differs")
    admitted = _validated_posix_identity(
        record.get("admitted_model"),
        code="capture_provenance_invalid",
        require_model_digest=True,
    )

    build = record.get("build")
    if not isinstance(build, Mapping) or build.get("attempt_scoped_fresh") is not True:
        _fail("capture_provenance_invalid", "capture build was not attempt-scoped")
    if (
        build.get("source_revision") != PINNED_LLAMA_CPP_REVISION
        or build.get("source_clean_before") is not True
        or build.get("source_clean_after") is not True
    ):
        _fail("capture_provenance_invalid", "capture source identity differs")
    source_tree = build.get("source_tree")
    if not isinstance(source_tree, str) or re.fullmatch(r"[0-9a-f]{40,64}", source_tree) is None:
        _fail("capture_provenance_invalid", "capture source tree identity is invalid")
    repository_source_hash = _require_sha256(
        build.get("capture_source_repository_sha256"),
        code="capture_provenance_invalid",
    )
    overlay_source_hash = _require_sha256(
        build.get("capture_source_overlay_sha256"),
        code="capture_provenance_invalid",
    )
    if repository_source_hash != overlay_source_hash:
        _fail("capture_provenance_invalid", "capture helper source copy differs")
    for field in (
        "cmake_lists_sha256",
        "cmake_cache_sha256",
        "configure_log_sha256",
        "build_log_sha256",
    ):
        _require_sha256(build.get(field), code="capture_provenance_invalid")
    for field in ("configure_command", "build_command"):
        value = build.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= 2048:
            _fail("capture_provenance_invalid", "capture build command is invalid")
    tools = build.get("tools")
    tool_names = [
        tool.get("name") if isinstance(tool, Mapping) else None for tool in tools
    ] if isinstance(tools, list) else []
    if tool_names != ["cmake", "cxx", "cmake-build-tool"]:
        _fail("capture_provenance_invalid", "capture build tool provenance is incomplete")
    validated_tools: list[dict[str, object]] = []
    for tool in tools:
        assert isinstance(tool, Mapping)
        version = tool.get("version")
        if not isinstance(version, str) or not 1 <= len(version) <= 256:
            _fail("capture_provenance_invalid", "capture build tool version is invalid")
        validated_tools.append(
            {
                "name": tool["name"],
                "version": version,
                "executable_sha256": _require_sha256(
                    tool.get("executable_sha256"),
                    code="capture_provenance_invalid",
                ),
            }
        )
    helper = _validated_posix_identity(
        build.get("helper"),
        code="capture_provenance_invalid",
        require_model_digest=False,
    )

    consumers = record.get("consumers")
    if not isinstance(consumers, list) or len(consumers) != 2:
        _fail("capture_provenance_invalid", "capture consumer proof count differs")
    validated_consumers: list[dict[str, object]] = []
    for index, expected_id in enumerate(("capture-a", "capture-b")):
        consumer = consumers[index]
        if not isinstance(consumer, Mapping) or consumer.get("consumer_id") != expected_id:
            _fail("capture_provenance_invalid", "capture consumer ordering differs")
        model_before = _validated_posix_identity(
            consumer.get("model_before"),
            code="capture_provenance_invalid",
            require_model_digest=True,
        )
        model_after = _validated_posix_identity(
            consumer.get("model_after"),
            code="capture_provenance_invalid",
            require_model_digest=True,
        )
        helper_before = _validated_posix_identity(
            consumer.get("helper_before"),
            code="capture_provenance_invalid",
            require_model_digest=False,
        )
        helper_after = _validated_posix_identity(
            consumer.get("helper_after"),
            code="capture_provenance_invalid",
            require_model_digest=False,
        )
        if model_before != admitted or model_after != admitted:
            _fail("capture_provenance_invalid", "capture model identity changed")
        if helper_before != helper or helper_after != helper:
            _fail("capture_provenance_invalid", "capture helper identity changed")
        validated_consumers.append(
            {
                "consumer_id": expected_id,
                "model_before": admitted,
                "model_after": admitted,
                "helper_before": helper,
                "helper_after": helper,
            }
        )
    return {
        "schema": record["schema"],
        "schema_version": record["schema_version"],
        "binding_strategy": record["binding_strategy"],
        "admitted_model": admitted,
        "build": {
            "attempt_scoped_fresh": True,
            "source_revision": PINNED_LLAMA_CPP_REVISION,
            "source_tree": source_tree,
            "source_clean_before": True,
            "source_clean_after": True,
            "capture_source_repository_sha256": repository_source_hash,
            "capture_source_overlay_sha256": overlay_source_hash,
            "cmake_lists_sha256": build["cmake_lists_sha256"],
            "cmake_cache_sha256": build["cmake_cache_sha256"],
            "configure_log_sha256": build["configure_log_sha256"],
            "build_log_sha256": build["build_log_sha256"],
            "configure_command": build["configure_command"],
            "build_command": build["build_command"],
            "tools": validated_tools,
            "helper": helper,
        },
        "consumers": validated_consumers,
    }


_CAPTURE_CONSTANTS: dict[str, object] = {
    "source_revision": PINNED_LLAMA_CPP_REVISION,
    "capture_node": "ffn_norm-0",
    "shape": [CAPTURE_ROWS, HIDDEN_WIDTH],
    "dtype": "float32_little_endian",
    "direct_token_ids": [0, 1],
    "positions": [0, 1],
    "context": 2,
    "batch": 2,
    "ubatch": 2,
    "threads": 1,
    "input_adapter": "direct_token_ids_v1",
    "tokenizer": "not_used_direct_token_ids",
}


def _validated_capture_record(record: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(record, Mapping):
        _fail("capture_mismatch", "capture identity must be an object")
    for field, expected in _CAPTURE_CONSTANTS.items():
        if field not in record or type(record[field]) is not type(expected) or record[field] != expected:
            _fail("capture_mismatch", "capture parameters differ from the frozen contract")
    capture_hash = _require_sha256(record.get("capture_sha256"), code="capture_mismatch")
    row_hashes = record.get("row_sha256")
    if (
        not isinstance(row_hashes, list)
        or len(row_hashes) != CAPTURE_ROWS
        or any(not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None for value in row_hashes)
        or row_hashes[0] == row_hashes[1]
    ):
        _fail("capture_mismatch", "capture rows are incomplete, invalid, or identical")
    byte_length = record.get("canonical_byte_length", CAPTURE_BYTE_LENGTH)
    if type(byte_length) is not int or byte_length != CAPTURE_BYTE_LENGTH:
        _fail("capture_mismatch", "capture byte length differs from the frozen contract")
    cancellation = validate_cancellation_trace(record.get("cancellation"))
    raw_model_identity = record.get("model_identity")
    if (
        not isinstance(raw_model_identity, Mapping)
        or raw_model_identity.get("pre_post_match") is not True
    ):
        _fail("capture_mismatch", "capture model stability proof is incomplete")
    model_identity = _validated_posix_identity(
        raw_model_identity,
        code="capture_mismatch",
        require_model_digest=True,
    )
    return {
        **_CAPTURE_CONSTANTS,
        "capture_sha256": capture_hash,
        "row_sha256": list(row_hashes),
        "canonical_byte_length": CAPTURE_BYTE_LENGTH,
        "model_identity": model_identity,
        "cancellation": cancellation,
    }


def validate_capture_pair(
    first: Mapping[str, object],
    second: Mapping[str, object],
) -> dict[str, object]:
    """Prove two independently started complete captures are byte-identical."""

    first_validated = _validated_capture_record(first)
    second_validated = _validated_capture_record(second)
    if (
        first_validated["capture_sha256"] != second_validated["capture_sha256"]
        or first_validated["row_sha256"] != second_validated["row_sha256"]
        or first_validated["model_identity"] != second_validated["model_identity"]
    ):
        _fail("capture_mismatch", "independent capture identities do not match")
    return {
        **{
            field: value
            for field, value in first_validated.items()
            if field != "cancellation"
        },
        "independent_capture_count": 2,
        "rows_distinct": True,
        "cancellation_proofs": [
            first_validated["cancellation"],
            second_validated["cancellation"],
        ],
    }


def validate_scheduler_debug_trace(trace_text: str) -> dict[str, object]:
    """Validate one bounded, marker-delimited CPU scheduler assignment."""

    if not isinstance(trace_text, str):
        _fail("scheduler_trace_invalid", "scheduler trace must be text")
    try:
        encoded = trace_text.encode("utf-8")
    except UnicodeError as error:
        raise RouterOracleError(
            "scheduler_trace_invalid",
            "scheduler trace is not valid UTF-8",
        ) from error
    if not encoded or len(encoded) > _MAX_SCHEDULER_TRACE_BYTES:
        _fail("scheduler_trace_invalid", "scheduler trace exceeds its byte bound")

    lines = trace_text.splitlines()
    begin_indexes = [
        index for index, line in enumerate(lines) if line == _SCHEDULER_TRACE_BEGIN
    ]
    end_indexes = [
        index for index, line in enumerate(lines) if line == _SCHEDULER_TRACE_END
    ]
    if (
        len(begin_indexes) != 1
        or len(end_indexes) != 1
        or begin_indexes[0] >= end_indexes[0]
    ):
        _fail(
            "scheduler_trace_invalid",
            "scheduler trace does not contain one ordered marker pair",
        )

    delimited_lines = lines[begin_indexes[0] + 1 : end_indexes[0]]
    delimited_text = "\n".join(delimited_lines)
    matches = list(_SCHEDULER_SPLIT_RE.finditer(delimited_text))
    if delimited_text.count("## SPLIT #") != len(matches) or len(matches) != 1:
        _fail(
            "scheduler_trace_invalid",
            "the marked decode does not contain exactly one scheduler split",
        )
    split_id = int(matches[0].group(1))
    backend = matches[0].group(2).strip().lower()
    input_count = int(matches[0].group(3))
    if split_id != 0 or backend != "cpu":
        _fail(
            "scheduler_trace_invalid",
            "the marked decode is not exactly scheduler split zero on CPU",
        )
    if not 0 <= input_count <= _MAX_SCHEDULER_INPUT_COUNT:
        _fail("scheduler_trace_invalid", "scheduler input count exceeds its bound")
    canonical_line = f"## SPLIT #0: CPU # {input_count} inputs"
    canonical_block = (canonical_line + "\n").encode("utf-8")
    retained_block = (
        f"{_SCHEDULER_TRACE_BEGIN}\n"
        f"{canonical_line}\n"
        f"{_SCHEDULER_TRACE_END}\n"
    ).encode("utf-8")
    return {
        "scheduler_trace_format": "ggml_sched_debug_marker_v1",
        "scheduler_split_count": 1,
        "scheduler_split_ids": [0],
        "scheduler_backends": ["cpu"],
        "scheduler_input_count": input_count,
        "scheduler_trace_sha256": hashlib.sha256(canonical_block).hexdigest(),
        "retained_scheduler_trace_byte_length": len(retained_block),
        "retained_scheduler_trace_sha256": hashlib.sha256(retained_block).hexdigest(),
    }


def canonical_scheduler_trace_bytes(trace_text: str) -> bytes:
    """Return the complete, bounded marker block after validating its proof."""

    validation = validate_scheduler_debug_trace(trace_text)
    retained = (
        f"{_SCHEDULER_TRACE_BEGIN}\n"
        f"## SPLIT #0: CPU # {validation['scheduler_input_count']} inputs\n"
        f"{_SCHEDULER_TRACE_END}\n"
    ).encode("utf-8")
    if (
        len(retained) != validation["retained_scheduler_trace_byte_length"]
        or hashlib.sha256(retained).hexdigest()
        != validation["retained_scheduler_trace_sha256"]
    ):
        _fail("scheduler_trace_invalid", "retained scheduler trace identity differs")
    return retained


def validate_cancellation_trace(trace: Mapping[str, object]) -> dict[str, object]:
    """Require one CPU split and a complete, untriggered cancellation boundary."""

    if not isinstance(trace, Mapping):
        _fail("cancellation_unproved", "cancellation trace must be an object")
    if "split_count" in trace or "abort_guard_triggered" in trace:
        _fail(
            "cancellation_unproved",
            "the capture trace contains a deprecated self-reported proof field",
        )
    required = {
        "backend": "cpu",
        "scheduler_trace_format": "ggml_sched_debug_marker_v1",
        "scheduler_split_count": 1,
        "scheduler_split_ids": [0],
        "scheduler_backends": ["cpu"],
        "target": "ffn_norm-0",
        "target_ask_count": 1,
        "target_observation_count": 1,
        "target_complete": True,
        "callback_returned_false": True,
        "abort_guard_armed": True,
        "abort_callback_calls_after_target": 0,
        "abort_callback_true_count": 0,
        "decode_status": 0,
    }
    for field, expected in required.items():
        if (
            field not in trace
            or type(trace[field]) is not type(expected)
            or trace[field] != expected
        ):
            _fail(
                "cancellation_unproved",
                "the capture trace does not prove the frozen CPU cancellation boundary",
            )
    callback_calls = trace.get("abort_callback_call_count")
    if type(callback_calls) is not int or not 1 <= callback_calls <= 1_000_000:
        _fail(
            "cancellation_unproved",
            "the CPU abort callback was not exercised within its bound",
        )
    trace_hash = _require_sha256(
        trace.get("scheduler_trace_sha256"),
        code="cancellation_unproved",
    )
    retained_trace_hash = _require_sha256(
        trace.get("retained_scheduler_trace_sha256"),
        code="cancellation_unproved",
    )
    retained_trace_length = trace.get("retained_scheduler_trace_byte_length")
    if (
        type(retained_trace_length) is not int
        or not 1 <= retained_trace_length <= 65_536
    ):
        _fail("cancellation_unproved", "retained scheduler trace length is invalid")
    scheduler_input_count = trace.get("scheduler_input_count")
    if (
        type(scheduler_input_count) is not int
        or not 0 <= scheduler_input_count <= _MAX_SCHEDULER_INPUT_COUNT
    ):
        _fail("cancellation_unproved", "scheduler input count is invalid")
    nodes_after = trace.get("nodes_after_target")
    if not isinstance(nodes_after, list) or nodes_after:
        _fail(
            "cancellation_unproved",
            "the capture trace contains a node after the target",
        )
    return {
        **required,
        "abort_callback_call_count": callback_calls,
        "scheduler_trace_sha256": trace_hash,
        "scheduler_input_count": scheduler_input_count,
        "retained_scheduler_trace_byte_length": retained_trace_length,
        "retained_scheduler_trace_sha256": retained_trace_hash,
        "nodes_after_target": [],
        "cancelled_before_router_or_expert": True,
    }


def _import_root(module_name: str | None) -> str:
    return "" if not module_name else module_name.split(".", 1)[0]


def assert_independent_source(source: str) -> None:
    """Reject static or simple dynamic imports of MLX and worker modules."""

    if not isinstance(source, str) or len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        _fail("oracle_not_independent", "oracle source is unavailable or too large")
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, TypeError) as error:
        raise RouterOracleError(
            "oracle_not_independent",
            "oracle source cannot be parsed for independence",
        ) from error

    def reject_module(module_name: str | None) -> None:
        if _import_root(module_name).lower() in _FORBIDDEN_IMPORT_ROOTS:
            _fail(
                "oracle_not_independent",
                "oracle source imports the implementation under test",
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                reject_module(alias.name)
        elif isinstance(node, ast.ImportFrom):
            reject_module(node.module)
        elif isinstance(node, ast.Call) and node.args:
            dynamic_import = False
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                dynamic_import = True
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                dynamic_import = True
            if dynamic_import and isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str
            ):
                reject_module(node.args[0].value)
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in ("exec", "eval")
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                assert_independent_source(node.args[0].value)


def assert_no_model_download(source: str) -> None:
    """Reject source text containing a known automatic acquisition mechanism."""

    if not isinstance(source, str) or len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        _fail("model_download_forbidden", "capture source is unavailable or too large")
    lowered = source.lower()
    patterns = (
        r"\bhf_hub_download\b",
        r"\bsnapshot_download\b",
        r"\bhuggingface-cli\s+download\b",
        r"(?:^|[;&|()\n])\s*(?:command\s+)?curl\s+",
        r"(?:^|[;&|()\n])\s*(?:command\s+)?wget\s+",
        r"(?:^|[;&|()\n])\s*(?:command\s+)?aria2c\s+",
        r"\bgit\s+(?:-[^\s]+\s+)*clone\b",
        r"\brequests\s*\.\s*get\s*\(",
        r"\burllib\s*\.\s*request\s*\.\s*urlopen\s*\(",
    )
    if any(re.search(pattern, lowered, flags=re.MULTILINE) for pattern in patterns):
        _fail(
            "model_download_forbidden",
            "capture orchestration contains an automatic acquisition mechanism",
        )


def compute_router_oracle(
    hidden_rows: Sequence[Sequence[float]],
    weight_rows: Sequence[Sequence[float]],
    *,
    numpy_adapter: NumpyProjection | None = None,
    top_k: int = TOP_K,
) -> dict[str, object]:
    """Compute complete canonical router outputs and an independent cross-check."""

    scalar_logits = scalar_f32_projection(hidden_rows, weight_rows)
    if len(weight_rows) != EXPERT_COUNT:
        _fail("invalid_shape", "the real router oracle requires all 128 experts")
    if top_k != TOP_K:
        _fail("invalid_top_k", "the real router oracle requires top-8")
    numpy_cross_check = cross_check_numpy_f32(
        hidden_rows,
        weight_rows,
        scalar_logits,
        numpy_adapter=numpy_adapter,
    )

    probabilities: list[list[float]] = []
    selected_ids: list[list[int]] = []
    selected_probabilities: list[list[float]] = []
    normalized_weights: list[list[float]] = []
    cutoff_ties: list[bool] = []
    for logits_row in scalar_logits:
        probability_row = full_softmax_f32(logits_row)
        ranked_ids = sorted(
            range(EXPERT_COUNT),
            key=lambda expert_id: (-probability_row[expert_id], expert_id),
        )
        cutoff_tie = probability_row[ranked_ids[TOP_K - 1]] == probability_row[
            ranked_ids[TOP_K]
        ]
        ids, selected, normalized = select_top_k_f32(
            probability_row,
            top_k=top_k,
        )
        probabilities.append(probability_row)
        selected_ids.append(ids)
        selected_probabilities.append(selected)
        normalized_weights.append(normalized)
        cutoff_ties.append(cutoff_tie)
    if any(cutoff_ties):
        _fail(
            "real_cutoff_tie",
            "an exact float32 probability tie crosses real ranks eight and nine",
        )

    logits_bytes = canonical_f32_bytes(scalar_logits)
    probabilities_bytes = canonical_f32_bytes(probabilities)
    selected_bytes = canonical_f32_bytes(selected_probabilities)
    normalized_bytes = canonical_f32_bytes(normalized_weights)
    ids_bytes = canonical_u32_bytes(
        expert_id for row in selected_ids for expert_id in row
    )
    output_bundle = (
        logits_bytes
        + probabilities_bytes
        + ids_bytes
        + selected_bytes
        + normalized_bytes
    )
    return {
        "arithmetic": "scalar_float32_multiply_then_add_left_to_right",
        "logits": scalar_logits,
        "full_softmax_probabilities": probabilities,
        "selected_expert_ids": selected_ids,
        "selected_probabilities": selected_probabilities,
        "normalized_weights": normalized_weights,
        "cutoff_ties": cutoff_ties,
        "hashes": {
            "logits_f32le_sha256": hashlib.sha256(logits_bytes).hexdigest(),
            "full_softmax_probabilities_f32le_sha256": hashlib.sha256(
                probabilities_bytes
            ).hexdigest(),
            "selected_expert_ids_u32le_sha256": hashlib.sha256(ids_bytes).hexdigest(),
            "selected_probabilities_f32le_sha256": hashlib.sha256(
                selected_bytes
            ).hexdigest(),
            "normalized_weights_f32le_sha256": hashlib.sha256(
                normalized_bytes
            ).hexdigest(),
            "output_bundle_sha256": hashlib.sha256(output_bundle).hexdigest(),
        },
        "numpy_cross_check": numpy_cross_check,
    }


def _read_bounded_json(path: Path) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                _fail("duplicate_json_key", "an oracle input record repeats a JSON key")
            result[key] = value
        return result

    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("unsafe_path", "an oracle input record is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > _MAX_JSON_BYTES:
            _fail("resource_limit", "an oracle input record exceeds the size bound")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except RouterOracleError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RouterOracleError(
            "invalid_capture_record",
            "an oracle input record cannot be read",
        ) from error
    if not isinstance(value, dict):
        _fail("invalid_capture_record", "an oracle input record is not an object")
    return value


def _read_scheduler_trace(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("unsafe_path", "scheduler trace is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > _MAX_SCHEDULER_TRACE_BYTES:
            _fail("scheduler_trace_invalid", "scheduler trace exceeds its byte bound")
        trace_text = path.read_text(encoding="utf-8")
    except RouterOracleError:
        raise
    except (OSError, UnicodeError) as error:
        raise RouterOracleError(
            "scheduler_trace_invalid",
            "scheduler trace cannot be read",
        ) from error
    return validate_scheduler_debug_trace(trace_text)


def _read_capture(
    path: Path,
    record_path: Path,
    scheduler_trace_path: Path,
) -> tuple[list[list[float]], dict[str, object]]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("unsafe_path", "capture bytes are not a regular file")
        if metadata.st_size != CAPTURE_BYTE_LENGTH:
            _fail("capture_mismatch", "capture bytes have the wrong length")
        raw = path.read_bytes()
    except RouterOracleError:
        raise
    except OSError as error:
        raise RouterOracleError("capture_mismatch", "capture bytes cannot be read") from error
    values = list(struct.unpack(f"<{CAPTURE_FLOAT_COUNT}f", raw))
    if any(not math.isfinite(value) for value in values):
        _fail("non_finite_value", "capture bytes contain a non-finite value")
    rows = [
        values[index * HIDDEN_WIDTH : (index + 1) * HIDDEN_WIDTH]
        for index in range(CAPTURE_ROWS)
    ]
    row_hashes = [canonical_f32_sha256(row) for row in rows]
    if row_hashes[0] == row_hashes[1]:
        _fail("capture_mismatch", "captured rows are not distinct")

    record = _read_bounded_json(record_path)
    for field, expected in _CAPTURE_CONSTANTS.items():
        if record.get(field) != expected:
            _fail("capture_mismatch", "capture record differs from the frozen contract")
    supplied_capture_hash = record.get("capture_sha256")
    observed_capture_hash = hashlib.sha256(raw).hexdigest()
    if supplied_capture_hash is not None and supplied_capture_hash != observed_capture_hash:
        _fail("capture_mismatch", "capture record hash differs from its bytes")
    supplied_row_hashes = record.get("row_sha256")
    if supplied_row_hashes is not None and supplied_row_hashes != row_hashes:
        _fail("capture_mismatch", "capture row hashes differ from their bytes")
    raw_model_identity = record.get("model_identity")
    if (
        not isinstance(raw_model_identity, Mapping)
        or raw_model_identity.get("pre_post_match") is not True
    ):
        _fail("capture_mismatch", "capture model stability proof is incomplete")
    complete_record = {
        **_CAPTURE_CONSTANTS,
        "capture_sha256": observed_capture_hash,
        "row_sha256": row_hashes,
        "canonical_byte_length": CAPTURE_BYTE_LENGTH,
        "model_identity": {
            **_validated_posix_identity(
                raw_model_identity,
                code="capture_mismatch",
                require_model_digest=True,
            ),
            "pre_post_match": True,
        },
    }
    cancellation = record.get("cancellation")
    if not isinstance(cancellation, Mapping):
        _fail("cancellation_unproved", "capture record lacks cancellation proof")
    scheduler_evidence = _read_scheduler_trace(scheduler_trace_path)
    complete_record["cancellation"] = validate_cancellation_trace(
        {
            **cancellation,
            **scheduler_evidence,
            "decode_status": record.get("decode_status"),
        }
    )
    return rows, complete_record


def _run_git(source_dir: Path, arguments: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_dir), *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RouterOracleError(
            "source_identity_mismatch",
            "the external source identity cannot be verified",
        ) from error
    if result.returncode != 0 or len(result.stdout) > 65_536:
        _fail("source_identity_mismatch", "the external source identity cannot be verified")
    return result.stdout.strip()


def _inspect_source_checkout(source_dir: Path) -> dict[str, object]:
    try:
        metadata = source_dir.lstat()
    except OSError as error:
        raise RouterOracleError(
            "source_identity_mismatch",
            "the external source checkout is unavailable",
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("source_identity_mismatch", "the external source checkout is unsafe")
    revision = _run_git(source_dir, ("rev-parse", "HEAD"))
    clean = _run_git(source_dir, ("status", "--porcelain", "--untracked-files=normal")) == ""
    origin = _run_git(source_dir, ("config", "--get", "remote.origin.url"))
    if origin not in {
        "https://github.com/ggml-org/llama.cpp",
        PINNED_LLAMA_CPP_REPOSITORY,
        "git@github.com:ggml-org/llama.cpp.git",
        "ssh://git@github.com/ggml-org/llama.cpp.git",
    }:
        _fail("source_identity_mismatch", "the external source origin differs from the pin")
    try:
        license_path = source_dir / "LICENSE"
        license_metadata = license_path.lstat()
        license_text = license_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise RouterOracleError(
            "source_identity_mismatch",
            "the pinned source license cannot be verified",
        ) from error
    if (
        stat.S_ISLNK(license_metadata.st_mode)
        or not stat.S_ISREG(license_metadata.st_mode)
        or len(license_text.encode("utf-8")) > 65_536
        or "MIT License" not in license_text
    ):
        _fail("source_identity_mismatch", "the pinned source license cannot be verified")
    return validate_pinned_source(
        {
            "repository": PINNED_LLAMA_CPP_REPOSITORY,
            "revision": revision,
            "clean": clean,
            "license": PINNED_LLAMA_CPP_LICENSE,
            "metal": False,
            "gpu_offload": False,
        }
    )


def _runtime_file_identity(metadata: os.stat_result, digest: str) -> dict[str, object]:
    return {
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
        "size_bytes": int(metadata.st_size),
        "sha256": digest,
    }


def _validate_model_identity(identity: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(identity, Mapping):
        _fail("model_identity_mismatch", "model identity proof is not an object")
    device = identity.get("device")
    inode = identity.get("inode")
    size_bytes = identity.get("size_bytes")
    digest = identity.get("sha256")
    if (
        type(device) is not int
        or device < 0
        or type(inode) is not int
        or inode <= 0
        or type(size_bytes) is not int
        or size_bytes != EXPECTED_MODEL_SIZE_BYTES
        or digest != EXPECTED_MODEL_SHA256
    ):
        _fail("model_identity_mismatch", "model identity differs from the admission")
    return {
        "device": device,
        "inode": inode,
        "size_bytes": size_bytes,
        "sha256": digest,
    }


def _admit_model(
    path: Path,
    *,
    consumer_id: str,
    expected_identity: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Hash one descriptor and prove its path identity stayed unchanged."""

    if not path.is_absolute() or path.name != EXPECTED_MODEL_FILENAME:
        _fail("model_identity_mismatch", "model path does not name the admitted artifact")
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if no_follow == 0:
        _fail("model_identity_mismatch", "read-only no-follow admission is unavailable")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", buffering=0) as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                _fail("model_identity_mismatch", "model descriptor is not a regular file")
            digest_builder = hashlib.sha256()
            while True:
                chunk = source.read(16 * 1024 * 1024)
                if not chunk:
                    break
                digest_builder.update(chunk)
            after = os.fstat(source.fileno())
        path_after = path.lstat()
    except OSError as error:
        raise RouterOracleError(
            "model_identity_mismatch",
            "model identity cannot be read",
        ) from error
    digest = digest_builder.hexdigest()
    before_identity = _runtime_file_identity(before, digest)
    after_identity = _runtime_file_identity(after, digest)
    path_identity = _runtime_file_identity(path_after, digest)
    if stat.S_ISLNK(path_after.st_mode) or not stat.S_ISREG(path_after.st_mode):
        _fail("model_identity_mismatch", "model is not a regular non-symlink file")
    admitted = _validate_model_identity(before_identity)
    if after_identity != admitted or path_identity != admitted:
        _fail("model_identity_mismatch", "model identity changed while it was hashed")
    if expected_identity is not None and admitted != _validate_model_identity(expected_identity):
        _fail("model_identity_mismatch", "model consumer identities do not match")
    return {
        "consumer_id": consumer_id,
        "descriptor_opened_read_only": True,
        "no_follow": True,
        "before": admitted,
        "after": admitted,
    }


def _load_f32_router(path: Path) -> tuple[list[list[float]], dict[str, object]]:
    try:
        gguf = importlib.import_module("gguf")
    except (ImportError, OSError) as error:
        raise RouterOracleError(
            "gguf_reader_unavailable",
            "pinned llama.cpp gguf-py is unavailable",
        ) from error
    try:
        reader = gguf.GGUFReader(path, mode="r")
        if reader.endianess != gguf.GGUFEndian.LITTLE:
            _fail("model_tensor_mismatch", "the admitted GGUF is not little-endian")
        matches = [tensor for tensor in reader.tensors if tensor.name == ROUTER_TENSOR_NAME]
        if len(matches) != 1:
            _fail("model_tensor_mismatch", "the router tensor is missing or duplicated")
        tensor = matches[0]
        tensor_type = getattr(tensor.tensor_type, "name", str(tensor.tensor_type))
        dimensions = [int(value) for value in tensor.shape.tolist()]
        data_shape = tuple(int(value) for value in tensor.data.shape)
        if tensor_type != "F32" or dimensions != [HIDDEN_WIDTH, EXPERT_COUNT]:
            _fail("model_tensor_mismatch", "the router tensor type or dimensions differ")
        if data_shape != (EXPERT_COUNT, HIDDEN_WIDTH):
            _fail("model_tensor_mismatch", "the router tensor reader orientation differs")
        if int(tensor.n_elements) != EXPERT_COUNT * HIDDEN_WIDTH:
            _fail("model_tensor_mismatch", "the router tensor element count differs")
        if int(tensor.n_bytes) != EXPERT_COUNT * HIDDEN_WIDTH * 4:
            _fail("model_tensor_mismatch", "the router tensor byte count differs")
        encoded = tensor.data.tobytes(order="C")
        if len(encoded) != EXPERT_COUNT * HIDDEN_WIDTH * 4:
            _fail("model_tensor_mismatch", "the router tensor byte materialization differs")
        weights = [[float(value) for value in row] for row in tensor.data.tolist()]
    except RouterOracleError:
        raise
    except Exception as error:
        raise RouterOracleError(
            "model_tensor_mismatch",
            "the pinned GGUF reader could not admit the router tensor",
        ) from error
    _validated_matrix(
        weights,
        label="router weights",
        maximum_rows=EXPERT_COUNT,
        maximum_columns=HIDDEN_WIDTH,
        expected_columns=HIDDEN_WIDTH,
    )
    return weights, {
        "name": ROUTER_TENSOR_NAME,
        "gguf_type": "F32",
        "gguf_dimensions_fastest_axis_first": [HIDDEN_WIDTH, EXPERT_COUNT],
        "reader_shape": [EXPERT_COUNT, HIDDEN_WIDTH],
        "logical_element_count": EXPERT_COUNT * HIDDEN_WIDTH,
        "encoded_byte_length": EXPERT_COUNT * HIDDEN_WIDTH * 4,
        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
        "orientation": "expert_major_rows_input_columns",
    }


def _json_bytes(value: object) -> bytes:
    try:
        encoded = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RouterOracleError("output_invalid", "oracle output is not canonical JSON") from error
    if len(encoded) > _MAX_JSON_BYTES:
        _fail("resource_limit", "oracle JSON output exceeds the bounded record limit")
    return encoded


def _write_json_exclusive(destination: Path, value: object) -> None:
    if not destination.is_absolute():
        _fail("unsafe_path", "oracle output path must be absolute")
    parent = destination.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as error:
        raise RouterOracleError("unsafe_path", "oracle output directory is unavailable") from error
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        _fail("unsafe_path", "oracle output directory is unsafe")
    if destination.exists() or destination.is_symlink():
        _fail("overwrite_refused", "oracle output already exists")
    content = _json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".router-oracle-", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError as error:
        raise RouterOracleError("overwrite_refused", "oracle output already exists") from error
    except OSError as error:
        raise RouterOracleError("output_invalid", "oracle output cannot be installed") from error
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _candidate_directory(path: Path) -> None:
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        _fail("unsafe_path", "oracle candidate directory must be normalized and absolute")
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RouterOracleError(
            "unsafe_path",
            "oracle candidate directory is unavailable",
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("unsafe_path", "oracle candidate directory is unsafe")


def _candidate_file_record(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("unsafe_path", "oracle candidate contains a non-regular artifact")
        if metadata.st_size <= 0 or metadata.st_size > _MAX_SCHEDULER_TRACE_BYTES:
            _fail("resource_limit", "oracle candidate artifact exceeds its bound")
        content = path.read_bytes()
    except RouterOracleError:
        raise
    except OSError as error:
        raise RouterOracleError(
            "output_invalid",
            "oracle candidate artifact cannot be read",
        ) from error
    if len(content) != metadata.st_size:
        _fail("output_invalid", "oracle candidate artifact changed while read")
    return {
        "path": path.name,
        "byte_length": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def retain_scheduler_trace(source: Path, destination: Path) -> dict[str, object]:
    """Install only the validated marker-delimited scheduler proof."""

    try:
        metadata = source.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("unsafe_path", "scheduler trace source is not a regular file")
        if metadata.st_size <= 0 or metadata.st_size > _MAX_SCHEDULER_TRACE_BYTES:
            _fail("scheduler_trace_invalid", "scheduler trace exceeds its byte bound")
        trace_text = source.read_text(encoding="utf-8")
    except RouterOracleError:
        raise
    except (OSError, UnicodeError) as error:
        raise RouterOracleError(
            "scheduler_trace_invalid",
            "scheduler trace cannot be retained",
        ) from error
    retained = canonical_scheduler_trace_bytes(trace_text)
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        _fail("overwrite_refused", "retained scheduler trace destination exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(retained)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        raise RouterOracleError(
            "output_invalid",
            "retained scheduler trace cannot be installed",
        ) from error
    return _candidate_file_record(destination)


def write_oracle_candidate_manifest(candidate: Path) -> dict[str, object]:
    """Hash every retained raw attempt artifact into one exclusive manifest."""

    _candidate_directory(candidate)
    observed = frozenset(path.name for path in candidate.iterdir())
    if observed != frozenset(_CANDIDATE_ARTIFACTS):
        _fail("output_invalid", "oracle candidate artifact set is incomplete")
    files = [_candidate_file_record(candidate / name) for name in _CANDIDATE_ARTIFACTS]
    document = {
        "schema": "pulsarmlx.research.router-oracle-candidate",
        "schema_version": "1.0.0",
        "complete": True,
        "publication": "same_parent_atomic_no_replace_directory_rename",
        "attempts": [
            {
                "attempt_id": attempt_id,
                "capture": f"capture-{attempt_id}.f32le",
                "record": f"capture-{attempt_id}.json",
                "scheduler_trace": f"capture-{attempt_id}.scheduler-trace.txt",
            }
            for attempt_id in ("a", "b")
        ],
        "files": files,
    }
    _write_json_exclusive(candidate / "bundle-manifest.json", document)
    return document


def validate_oracle_candidate_bundle(candidate: Path) -> dict[str, object]:
    """Revalidate the complete staged bundle before it can become visible."""

    _candidate_directory(candidate)
    observed = frozenset(path.name for path in candidate.iterdir())
    if observed != _COMPLETE_CANDIDATE_FILES:
        _fail("output_invalid", "oracle candidate artifact set differs")
    manifest = _read_bounded_json(candidate / "bundle-manifest.json")
    if (
        manifest.get("schema") != "pulsarmlx.research.router-oracle-candidate"
        or manifest.get("schema_version") != "1.0.0"
        or manifest.get("complete") is not True
        or manifest.get("publication")
        != "same_parent_atomic_no_replace_directory_rename"
    ):
        _fail("output_invalid", "oracle candidate manifest contract differs")
    attempts = manifest.get("attempts")
    expected_attempts = [
        {
            "attempt_id": attempt_id,
            "capture": f"capture-{attempt_id}.f32le",
            "record": f"capture-{attempt_id}.json",
            "scheduler_trace": f"capture-{attempt_id}.scheduler-trace.txt",
        }
        for attempt_id in ("a", "b")
    ]
    if attempts != expected_attempts:
        _fail("output_invalid", "oracle candidate attempt inventory differs")
    expected_files = [
        _candidate_file_record(candidate / name) for name in _CANDIDATE_ARTIFACTS
    ]
    if manifest.get("files") != expected_files:
        _fail("output_invalid", "oracle candidate artifact identity differs")

    first_rows, first_record = _read_capture(
        candidate / "capture-a.f32le",
        candidate / "capture-a.json",
        candidate / "capture-a.scheduler-trace.txt",
    )
    second_rows, second_record = _read_capture(
        candidate / "capture-b.f32le",
        candidate / "capture-b.json",
        candidate / "capture-b.scheduler-trace.txt",
    )
    capture = validate_capture_pair(first_record, second_record)
    if canonical_f32_bytes(first_rows) != canonical_f32_bytes(second_rows):
        _fail("capture_mismatch", "retained independent capture bytes differ")
    oracle_document = _read_bounded_json(candidate / "oracle.json")
    if (
        oracle_document.get("schema") != "pulsarmlx.research.router-oracle"
        or oracle_document.get("status") != "passed"
        or oracle_document.get("capture") != capture
    ):
        _fail("output_invalid", "retained oracle and raw capture proofs differ")
    capture_provenance = validate_capture_provenance(
        _read_bounded_json(candidate / "capture-provenance.json")
    )
    if oracle_document.get("capture_provenance") != capture_provenance:
        _fail("output_invalid", "retained capture provenance differs from oracle")
    generator = oracle_document.get("generator")
    if not isinstance(generator, Mapping):
        _fail("output_invalid", "retained oracle generator identity is incomplete")
    execution = _read_bounded_json(candidate / "execution-provenance.json")
    if (
        execution.get("schema")
        != "pulsarmlx.research.router-oracle-execution-provenance"
        or execution.get("schema_version") != "1.0.0"
        or execution.get("binding_strategy")
        != "pre_post_full_sha256_plus_device_inode_size"
        or execution.get("oracle_source_sha256")
        != generator.get("sha256")
        or execution.get("capture_provenance_sha256")
        != _candidate_file_record(candidate / "capture-provenance.json")["sha256"]
        or execution.get("oracle_document_sha256")
        != _candidate_file_record(candidate / "oracle.json")["sha256"]
    ):
        _fail("output_invalid", "oracle execution provenance differs")
    consumer = execution.get("oracle_process_consumer")
    if not isinstance(consumer, Mapping) or consumer.get("consumer_id") != "oracle-process":
        _fail("output_invalid", "oracle process consumer proof is incomplete")
    before = _validated_posix_identity(
        consumer.get("model_before"),
        code="output_invalid",
        require_model_digest=True,
    )
    after = _validated_posix_identity(
        consumer.get("model_after"),
        code="output_invalid",
        require_model_digest=True,
    )
    if before != capture_provenance["admitted_model"] or after != before:
        _fail("output_invalid", "oracle process model identity changed")
    return manifest


def publish_oracle_candidate(candidate: Path, destination: Path) -> None:
    """Fsync then atomically publish one complete sibling directory, no replace."""

    validate_oracle_candidate_bundle(candidate)
    if (
        not destination.is_absolute()
        or Path(os.path.normpath(destination)) != destination
        or candidate.parent != destination.parent
        or not candidate.name.startswith(".pulsarmlx-router-oracle.")
    ):
        _fail("unsafe_path", "oracle publication paths are not safe siblings")
    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise RouterOracleError("unsafe_path", "oracle destination cannot be checked") from error
    else:
        _fail("overwrite_refused", "oracle destination already exists")

    for name in sorted(_COMPLETE_CANDIDATE_FILES):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate / name, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                _fail("unsafe_path", "oracle candidate artifact changed before publish")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    candidate_descriptor = os.open(candidate, directory_flags)
    try:
        os.fsync(candidate_descriptor)
    finally:
        os.close(candidate_descriptor)

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(candidate)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        result = rename(source_bytes, destination_bytes, 0x00000004)
    elif hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        result = rename(-100, source_bytes, -100, destination_bytes, 0x00000001)
    else:
        _fail("output_invalid", "atomic no-replace directory rename is unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in (errno.EEXIST, errno.ENOTEMPTY):
            _fail("overwrite_refused", "oracle destination already exists")
        raise RouterOracleError(
            "output_invalid",
            f"atomic oracle publication failed with errno {error_number}",
        )
    parent_descriptor = os.open(destination.parent, directory_flags)
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)
    if candidate.exists() or candidate.is_symlink() or not destination.is_dir():
        _fail("output_invalid", "atomic oracle publication did not complete")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded independent CPU router oracle from two captures.",
    )
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--capture-a", required=True, type=Path)
    parser.add_argument("--capture-a-record", required=True, type=Path)
    parser.add_argument("--capture-a-scheduler-trace", required=True, type=Path)
    parser.add_argument("--capture-b", required=True, type=Path)
    parser.add_argument("--capture-b-record", required=True, type=Path)
    parser.add_argument("--capture-b-scheduler-trace", required=True, type=Path)
    parser.add_argument("--capture-provenance", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _build_oracle_document(arguments: argparse.Namespace) -> dict[str, object]:
    source = _inspect_source_checkout(arguments.source_dir)
    capture_provenance = validate_capture_provenance(
        _read_bounded_json(arguments.capture_provenance)
    )
    first_rows, first_record = _read_capture(
        arguments.capture_a,
        arguments.capture_a_record,
        arguments.capture_a_scheduler_trace,
    )
    second_rows, second_record = _read_capture(
        arguments.capture_b,
        arguments.capture_b_record,
        arguments.capture_b_scheduler_trace,
    )
    capture = validate_capture_pair(first_record, second_record)
    if canonical_f32_bytes(first_rows) != canonical_f32_bytes(second_rows):
        _fail("capture_mismatch", "independent capture bytes do not match")
    admitted_identity = capture_provenance["admitted_model"]
    if capture["model_identity"] != admitted_identity:
        _fail("capture_provenance_invalid", "capture record model identity differs")
    before_reader = _admit_model(
        arguments.model,
        consumer_id="oracle-before-gguf-reader",
        expected_identity=admitted_identity,
    )
    weights, tensor = _load_f32_router(arguments.model)
    after_reader = _admit_model(
        arguments.model,
        consumer_id="oracle-after-gguf-reader",
        expected_identity=admitted_identity,
    )
    if before_reader["before"] != after_reader["before"]:
        _fail("model_identity_mismatch", "model identity changed across the GGUF reader")
    model = {
        "filename": EXPECTED_MODEL_FILENAME,
        "size_bytes": EXPECTED_MODEL_SIZE_BYTES,
        "sha256": EXPECTED_MODEL_SHA256,
        "runtime_identity": admitted_identity,
        "consumer_proofs": [before_reader, after_reader],
    }
    adapter = NumpyProjectionAdapter()
    result = compute_router_oracle(first_rows, weights, numpy_adapter=adapter)
    source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {
        "schema": "pulsarmlx.research.router-oracle",
        "schema_version": "1.0.0",
        "oracle_id": "qwen3moe-layer0-router-cpu-oracle-v1",
        "status": "passed",
        "source": source,
        "generator": {
            "path": "scripts/research/router_oracle.py",
            "sha256": source_sha256,
            "generation_command": (
                "python3 scripts/research/router_oracle.py --model "
                "$PULSARMLX_MODEL_GGUF --source-dir $PULSARMLX_LLAMA_CPP "
                "--capture-a $PULSARMLX_CAPTURE_A --capture-a-record "
                "$PULSARMLX_CAPTURE_A_RECORD --capture-a-scheduler-trace "
                "$PULSARMLX_CAPTURE_A_SCHEDULER_TRACE --capture-b "
                "$PULSARMLX_CAPTURE_B --capture-b-record "
                "$PULSARMLX_CAPTURE_B_RECORD --capture-b-scheduler-trace "
                "$PULSARMLX_CAPTURE_B_SCHEDULER_TRACE --capture-provenance "
                "$PULSARMLX_CAPTURE_PROVENANCE --output "
                "$PULSARMLX_ROUTER_ORACLE"
            ),
            "independence": (
                "scalar CPU implementation; no MLX or PulsarMLX worker import or call"
            ),
            "numpy_version": adapter.version,
        },
        "model": model,
        "tensor": tensor,
        "capture": capture,
        "capture_provenance": capture_provenance,
        "input": {
            "case_ids": [
                "qwen3moe-layer0-router-token0-row0-v1",
                "qwen3moe-layer0-router-token0-token1-batch-v1",
            ],
            "shape": [CAPTURE_ROWS, HIDDEN_WIDTH],
            "dtype": "float32",
            "byte_order": "little",
            "values": first_rows,
            "canonical_f32le_sha256": capture["capture_sha256"],
            "row_sha256": capture["row_sha256"],
        },
        "result": result,
        "comparison_policy": {
            "logits": {"absolute_tolerance": LOGIT_ATOL, "relative_tolerance": LOGIT_RTOL},
            "probabilities_and_weights": {
                "absolute_tolerance": PROBABILITY_ATOL,
                "relative_tolerance": PROBABILITY_RTOL,
            },
            "non_finite_policy": "reject",
            "tie_rule": "probability_descending_then_expert_id_ascending",
            "real_rank_8_rank_9_tie": "stop",
        },
        "unsupported_interpretations": [
            "expert execution",
            "routed MoE aggregation",
            "complete layer or model inference",
            "generation or serving",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        assert_independent_source(Path(__file__).read_text(encoding="utf-8"))
        arguments = _parser().parse_args(argv)
        document = _build_oracle_document(arguments)
        _write_json_exclusive(arguments.output, document)
    except RouterOracleError as error:
        print(f"router oracle: {error.code}: {error.message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("router oracle: interrupted: oracle generation was interrupted", file=sys.stderr)
        return 130
    print("router oracle: wrote one bounded independent CPU oracle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

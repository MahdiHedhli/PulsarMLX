"""Strict deterministic tensor fixtures for the Apple MLX worker.

All descriptor, shape, dtype, layout, byte-count, and fixture-specific checks
finish before this module imports or accesses MLX.  Successful results are
observable only after explicit evaluation and synchronization on ``mx.gpu``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import struct
from typing import Any

from .runtime import (
    BACKEND_ID,
    GPU_DEVICE_ID,
    MemoryGauges,
    RuntimeContractError,
    collect_memory_gauges,
)


_SCHEMA_VERSION = 1
_MAX_MANIFEST_BYTES = 256 * 1024
_MAX_MANIFEST_OPERATIONS = 64
_HARD_MAX_FIXTURE_ELEMENTS = 4_096
_MAX_RANK = 16
_MAX_ID_CHARS = 128
_MAX_DIAGNOSTIC_CHARS = 512
_U64_MAX = (1 << 64) - 1
_SYNC_RULE = "explicit_eval_then_gpu_synchronize"

_FLOAT_OPERATION_IDS = frozenset(
    {
        "elementwise_fma",
        "matmul",
        "embedding_gather",
        "rms_norm",
        "residual_add",
        "router_topk_softmax",
    }
)
_OPERATION_IDS = _FLOAT_OPERATION_IDS | {"q8_0_decode_dot"}

_BASE_CASE_KEYS = frozenset(
    {
        "case_id",
        "operation",
        "logical_shape",
        "storage_shape",
        "layout",
        "input_dtype",
        "accumulation_dtype",
        "output_dtype",
        "inputs",
        "expected",
        "comparison",
    }
)
_ROUTER_CASE_KEYS = _BASE_CASE_KEYS | {"expected_expert_ids"}
_Q8_CASE_KEYS = _BASE_CASE_KEYS | {
    "encoded_byte_count",
    "quantization",
    "expected_decoded",
}


class TensorOperationError(RuntimeContractError):
    """Stable bounded failure at the public tensor-fixture boundary."""


@dataclass(frozen=True, slots=True)
class FixtureDescriptor:
    case_id: str
    operation: str
    logical_shape: tuple[int, ...]
    storage_shape: tuple[int, ...]
    layout: str
    input_dtype: str
    accumulation_dtype: str
    output_dtype: str
    element_count: int
    encoded_byte_count: int | None


@dataclass(frozen=True, slots=True)
class FixtureManifest:
    schema_version: int
    fixture_set_id: str
    oracle_id: str
    backend_id: str
    requested_device: str
    allow_fallback: bool
    synchronization_rule: str
    maximum_fixture_elements: int
    operations: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class FixtureComparisonResult:
    oracle_id: str
    mode: str
    absolute_tolerance: float
    relative_tolerance: float
    non_finite_policy: str
    compared_count: int
    max_absolute_error: float
    max_relative_error: float
    first_mismatch_index: int | None
    passed: bool

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "oracle_id": self.oracle_id,
            "mode": self.mode,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "non_finite_policy": self.non_finite_policy,
            "compared_count": self.compared_count,
            "max_absolute_error": self.max_absolute_error,
            "max_relative_error": self.max_relative_error,
            "first_mismatch_index": self.first_mismatch_index,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class FixtureOperationResult:
    fixture_set_id: str
    case_id: str
    operation: str
    backend_id: str
    requested_device: str
    selected_device: str
    fallback_used: bool
    output_shape: tuple[int, ...]
    input_dtype: str
    accumulation_dtype: str
    output_dtype: str
    evaluated: bool
    synchronized: bool
    actual: tuple[float, ...]
    comparison: FixtureComparisonResult
    selected_expert_ids: tuple[int, ...]
    selected_expert_ids_match: bool | None
    decoded: tuple[float, ...]
    decoded_comparison: FixtureComparisonResult | None
    memory_gauges: MemoryGauges

    @property
    def passed(self) -> bool:
        return (
            self.evaluated
            and self.synchronized
            and not self.fallback_used
            and self.selected_device == GPU_DEVICE_ID
            and self.comparison.passed
            and self.selected_expert_ids_match is not False
            and (
                self.decoded_comparison is None
                or self.decoded_comparison.passed
            )
        )

    def to_protocol_result(self) -> dict[str, object]:
        result: dict[str, object] = {
            "fixture_set_id": self.fixture_set_id,
            "case_id": self.case_id,
            "operation": self.operation,
            "backend_id": self.backend_id,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "output_shape": list(self.output_shape),
            "input_dtype": self.input_dtype,
            "accumulation_dtype": self.accumulation_dtype,
            "output_dtype": self.output_dtype,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "actual": list(self.actual),
            "comparison": self.comparison.to_protocol_result(),
            "memory_gauges": self.memory_gauges.to_protocol_result(),
            "passed": self.passed,
        }
        if self.selected_expert_ids:
            result["selected_expert_ids"] = list(self.selected_expert_ids)
        if self.decoded:
            result["decoded"] = list(self.decoded)
        return result


def load_fixture_manifest(
    path: str | Path,
    *,
    expected_fixture_set_id: str,
) -> FixtureManifest:
    """Load one bounded explicit fixture manifest and validate every case."""

    expected_identity = _stable_id(
        expected_fixture_set_id,
        "expected fixture-set identity",
    )
    manifest_path = Path(path)
    try:
        with manifest_path.open("rb") as manifest_file:
            raw = manifest_file.read(_MAX_MANIFEST_BYTES + 1)
    except (OSError, TypeError, ValueError) as error:
        raise TensorOperationError(
            "malformed_request",
            "the explicit fixture manifest could not be read",
        ) from error
    if not raw or len(raw) > _MAX_MANIFEST_BYTES:
        raise TensorOperationError(
            "resource_limit",
            "the fixture manifest is empty or exceeds its byte limit",
        )

    try:
        document = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite_json,
        )
    except TensorOperationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as error:
        raise TensorOperationError(
            "malformed_request",
            "the fixture manifest is not strict bounded JSON",
        ) from error
    if not isinstance(document, dict):
        raise TensorOperationError(
            "malformed_request",
            "the fixture manifest root must be an object",
        )

    required_keys = {
        "schema_version",
        "fixture_set_id",
        "oracle_id",
        "backend_id",
        "requested_device",
        "allow_fallback",
        "synchronization_rule",
        "maximum_fixture_elements",
        "operations",
    }
    _require_exact_keys(document, required_keys, "fixture manifest")
    if _strict_integer(document["schema_version"], "schema version") != _SCHEMA_VERSION:
        raise TensorOperationError(
            "malformed_request",
            "the fixture manifest schema version is unsupported",
        )

    fixture_set_id = _stable_id(document["fixture_set_id"], "fixture-set identity")
    if fixture_set_id != expected_identity:
        raise TensorOperationError(
            "malformed_request",
            "the fixture manifest identity does not match the requested fixture set",
        )
    oracle_id = _stable_id(document["oracle_id"], "oracle identity")
    backend_id = _stable_id(document["backend_id"], "backend identity")
    requested_device = _stable_id(document["requested_device"], "requested device")
    if backend_id != BACKEND_ID or requested_device != GPU_DEVICE_ID:
        raise TensorOperationError(
            "device_unavailable",
            "the fixture manifest does not select the explicit Apple MLX GPU",
        )
    if document["allow_fallback"] is not False:
        raise TensorOperationError(
            "device_unavailable",
            "the fixture manifest must prohibit backend fallback",
        )
    synchronization_rule = _stable_id(
        document["synchronization_rule"],
        "synchronization rule",
    )
    if synchronization_rule != _SYNC_RULE:
        raise TensorOperationError(
            "malformed_request",
            "the fixture manifest does not require evaluation and GPU synchronization",
        )
    maximum_fixture_elements = _strict_integer(
        document["maximum_fixture_elements"],
        "maximum fixture elements",
    )
    if not 1 <= maximum_fixture_elements <= _HARD_MAX_FIXTURE_ELEMENTS:
        raise TensorOperationError(
            "resource_limit",
            "the fixture element limit is outside the worker bound",
        )

    raw_operations = document["operations"]
    if (
        not isinstance(raw_operations, list)
        or not raw_operations
        or len(raw_operations) > _MAX_MANIFEST_OPERATIONS
    ):
        raise TensorOperationError(
            "resource_limit",
            "the fixture operation list is empty or exceeds its bound",
        )

    operations: list[dict[str, object]] = []
    seen_case_ids: set[str] = set()
    for raw_case in raw_operations:
        if not isinstance(raw_case, dict):
            raise TensorOperationError(
                "malformed_request",
                "every fixture operation must be an object",
            )
        descriptor = validate_fixture_descriptor(
            raw_case,
            maximum_fixture_elements=maximum_fixture_elements,
        )
        _validate_operation_contents(
            raw_case,
            descriptor,
            maximum_fixture_elements=maximum_fixture_elements,
        )
        if descriptor.case_id in seen_case_ids:
            raise TensorOperationError(
                "malformed_request",
                "fixture case identities must be unique",
            )
        seen_case_ids.add(descriptor.case_id)
        operations.append(raw_case)

    return FixtureManifest(
        schema_version=_SCHEMA_VERSION,
        fixture_set_id=fixture_set_id,
        oracle_id=oracle_id,
        backend_id=backend_id,
        requested_device=requested_device,
        allow_fallback=False,
        synchronization_rule=synchronization_rule,
        maximum_fixture_elements=maximum_fixture_elements,
        operations=tuple(operations),
    )


def validate_fixture_descriptor(
    case: Mapping[str, object],
    *,
    maximum_fixture_elements: int,
) -> FixtureDescriptor:
    """Resolve a strict immutable descriptor without importing MLX."""

    if not isinstance(case, Mapping):
        raise TensorOperationError(
            "malformed_request",
            "a fixture operation must be an object",
        )
    limit = _strict_integer(maximum_fixture_elements, "maximum fixture elements")
    if not 1 <= limit <= _HARD_MAX_FIXTURE_ELEMENTS:
        raise TensorOperationError(
            "resource_limit",
            "the fixture element limit is outside the worker bound",
        )

    operation = _stable_id(case.get("operation"), "operation identity")
    if operation not in _OPERATION_IDS:
        raise TensorOperationError(
            "unsupported_operation",
            "the requested tensor fixture operation is unsupported",
        )
    expected_keys = (
        _ROUTER_CASE_KEYS
        if operation == "router_topk_softmax"
        else _Q8_CASE_KEYS
        if operation == "q8_0_decode_dot"
        else _BASE_CASE_KEYS
    )
    _require_exact_keys(case, expected_keys, "fixture operation")

    case_id = _stable_id(case["case_id"], "case identity")
    logical_shape, element_count = _checked_shape(
        case["logical_shape"],
        "logical shape",
        maximum_elements=limit,
    )
    storage_shape, _ = _checked_shape(
        case["storage_shape"],
        "storage shape",
        maximum_elements=limit,
    )
    layout = _stable_id(case["layout"], "tensor layout")
    admitted_layout = (
        "gguf_fastest_dimension_first"
        if operation == "q8_0_decode_dot"
        else "row_major"
    )
    if layout != admitted_layout:
        raise TensorOperationError(
            "invalid_layout",
            "the fixture tensor layout is not admitted for this operation",
        )

    input_dtype = _stable_id(case["input_dtype"], "input dtype")
    accumulation_dtype = _stable_id(
        case["accumulation_dtype"],
        "accumulation dtype",
    )
    output_dtype = _stable_id(case["output_dtype"], "output dtype")
    expected_input_dtype = "q8_0" if operation == "q8_0_decode_dot" else "float32"
    if input_dtype != expected_input_dtype:
        raise TensorOperationError(
            "invalid_dtype",
            "the fixture input dtype is unsupported for this operation",
        )
    if accumulation_dtype != "float32" or output_dtype != "float32":
        raise TensorOperationError(
            "invalid_dtype",
            "the initial fixture suite requires float32 accumulation and output",
        )

    encoded_byte_count: int | None = None
    if operation == "q8_0_decode_dot":
        encoded_byte_count = _strict_integer(
            case["encoded_byte_count"],
            "encoded byte count",
        )
        if encoded_byte_count <= 0:
            raise TensorOperationError(
                "invalid_byte_count",
                "the encoded Q8_0 byte count must be positive",
            )

    descriptor = FixtureDescriptor(
        case_id=case_id,
        operation=operation,
        logical_shape=logical_shape,
        storage_shape=storage_shape,
        layout=layout,
        input_dtype=input_dtype,
        accumulation_dtype=accumulation_dtype,
        output_dtype=output_dtype,
        element_count=element_count,
        encoded_byte_count=encoded_byte_count,
    )
    _validate_storage_orientation(descriptor)
    return descriptor


def run_fixture_operation(
    case: Mapping[str, object],
    *,
    fixture_set_id: str,
    synchronization_rule: str,
    maximum_fixture_elements: int,
    requested_device: str,
    allow_fallback: bool,
    mx_module: Any | None = None,
) -> FixtureOperationResult:
    """Validate, execute, evaluate, synchronize, and compare one fixture."""

    set_id = _stable_id(fixture_set_id, "fixture-set identity")
    sync_rule = _stable_id(synchronization_rule, "synchronization rule")
    if sync_rule != _SYNC_RULE:
        raise TensorOperationError(
            "malformed_request",
            "fixture execution requires explicit evaluation and GPU synchronization",
        )
    if requested_device != GPU_DEVICE_ID or allow_fallback is not False:
        raise TensorOperationError(
            "device_unavailable",
            "fixture execution accepts only an explicit GPU with fallback disabled",
        )

    # No MLX object may be imported or accessed above or during these checks.
    descriptor = validate_fixture_descriptor(
        case,
        maximum_fixture_elements=maximum_fixture_elements,
    )
    validated = _validate_operation_contents(
        case,
        descriptor,
        maximum_fixture_elements=maximum_fixture_elements,
    )

    mx = mx_module if mx_module is not None else _import_mlx()
    try:
        result_array, selected_ids_array, decoded_array, output_shape = (
            _schedule_operation(mx, descriptor, validated)
        )
        evaluated_arrays = [result_array]
        if selected_ids_array is not None:
            evaluated_arrays.append(selected_ids_array)
        if decoded_array is not None:
            evaluated_arrays.append(decoded_array)
        mx.eval(*evaluated_arrays)
        evaluated = True
        mx.synchronize(mx.gpu)
        synchronized = True

        _validate_result_metadata(mx, result_array, output_shape)
        actual = _bounded_float_readback(
            result_array.tolist(),
            expected_count=_shape_product(output_shape),
            maximum_count=maximum_fixture_elements,
        )
        selected_expert_ids = (
            _bounded_integer_readback(
                selected_ids_array.tolist(),
                expected_count=len(validated["expected_expert_ids"]),
                maximum_count=maximum_fixture_elements,
            )
            if selected_ids_array is not None
            else ()
        )
        decoded = (
            _bounded_float_readback(
                decoded_array.tolist(),
                expected_count=len(validated["expected_decoded"]),
                maximum_count=maximum_fixture_elements,
            )
            if decoded_array is not None
            else ()
        )
    except TensorOperationError:
        raise
    except Exception as error:
        raise TensorOperationError(
            "evaluation_failed",
            "the explicit MLX GPU fixture operation did not complete",
        ) from error

    comparison = _compare_fixture_values(
        validated["expected"],
        actual,
        validated["comparison"],
        oracle_id="committed-independent-scalar-v1",
    )
    expected_ids = validated["expected_expert_ids"]
    selected_expert_ids_match = (
        selected_expert_ids == expected_ids if expected_ids else None
    )
    expected_decoded = validated["expected_decoded"]
    decoded_comparison = (
        _compare_fixture_values(
            expected_decoded,
            decoded,
            validated["comparison"],
            oracle_id=f"committed-independent-q8-decode-v1:{descriptor.case_id}",
        )
        if expected_decoded
        else None
    )
    if selected_expert_ids_match is False or (
        decoded_comparison is not None and not decoded_comparison.passed
    ):
        comparison = replace(
            comparison,
            first_mismatch_index=(
                comparison.first_mismatch_index
                if comparison.first_mismatch_index is not None
                else 0
            ),
            passed=False,
        )

    try:
        memory_gauges = collect_memory_gauges(mx)
    except RuntimeContractError as error:
        raise TensorOperationError(error.code, error.message) from error

    return FixtureOperationResult(
        fixture_set_id=set_id,
        case_id=descriptor.case_id,
        operation=descriptor.operation,
        backend_id=BACKEND_ID,
        requested_device=GPU_DEVICE_ID,
        selected_device=GPU_DEVICE_ID,
        fallback_used=False,
        output_shape=output_shape,
        input_dtype=descriptor.input_dtype,
        accumulation_dtype=descriptor.accumulation_dtype,
        output_dtype=descriptor.output_dtype,
        evaluated=evaluated,
        synchronized=synchronized,
        actual=actual,
        comparison=comparison,
        selected_expert_ids=selected_expert_ids,
        selected_expert_ids_match=selected_expert_ids_match,
        decoded=decoded,
        decoded_comparison=decoded_comparison,
        memory_gauges=memory_gauges,
    )


def _validate_operation_contents(
    case: Mapping[str, object],
    descriptor: FixtureDescriptor,
    *,
    maximum_fixture_elements: int,
) -> dict[str, Any]:
    inputs = case["inputs"]
    if not isinstance(inputs, Mapping):
        raise TensorOperationError(
            "malformed_request",
            "fixture inputs must be an object",
        )
    comparison = _validate_comparison_policy(case["comparison"])

    expected_output_shape: tuple[int, ...]
    if descriptor.operation == "elementwise_fma":
        _require_exact_keys(inputs, {"left", "right", "bias"}, "elementwise inputs")
        left = _finite_float_list(
            inputs["left"],
            "elementwise left input",
            exact_count=descriptor.element_count,
        )
        right = _finite_float_list(
            inputs["right"],
            "elementwise right input",
            exact_count=descriptor.element_count,
        )
        bias = _finite_float(inputs["bias"], "elementwise bias")
        expected_output_shape = descriptor.logical_shape
        normalized_inputs: dict[str, Any] = {
            "left": left,
            "right": right,
            "bias": bias,
        }

    elif descriptor.operation == "matmul":
        _require_exact_keys(
            inputs,
            {"left_shape", "left", "right_shape", "right"},
            "matmul inputs",
        )
        left_shape, left_count = _checked_shape(
            inputs["left_shape"],
            "matmul left shape",
            maximum_elements=maximum_fixture_elements,
            exact_rank=2,
        )
        right_shape, right_count = _checked_shape(
            inputs["right_shape"],
            "matmul right shape",
            maximum_elements=maximum_fixture_elements,
            exact_rank=2,
        )
        if left_shape[1] != right_shape[0]:
            raise TensorOperationError(
                "invalid_shape",
                "matmul inner dimensions do not match",
            )
        expected_output_shape = (left_shape[0], right_shape[1])
        if descriptor.logical_shape != expected_output_shape:
            raise TensorOperationError(
                "invalid_shape",
                "matmul logical output shape does not match its inputs",
            )
        normalized_inputs = {
            "left_shape": left_shape,
            "left": _finite_float_list(
                inputs["left"],
                "matmul left input",
                exact_count=left_count,
            ),
            "right_shape": right_shape,
            "right": _finite_float_list(
                inputs["right"],
                "matmul right input",
                exact_count=right_count,
            ),
        }

    elif descriptor.operation == "embedding_gather":
        _require_exact_keys(
            inputs,
            {"table_shape", "table", "token_ids", "invalid_token_ids"},
            "embedding inputs",
        )
        table_shape, table_count = _checked_shape(
            inputs["table_shape"],
            "embedding table shape",
            maximum_elements=maximum_fixture_elements,
            exact_rank=2,
        )
        token_ids = _integer_list(
            inputs["token_ids"],
            "embedding token IDs",
            maximum_count=maximum_fixture_elements,
            allow_negative=True,
        )
        if not token_ids or any(token < 0 or token >= table_shape[0] for token in token_ids):
            raise TensorOperationError(
                "malformed_request",
                "embedding token IDs are outside the admitted table range",
            )
        invalid_token_ids = _integer_list(
            inputs["invalid_token_ids"],
            "declared invalid embedding token IDs",
            maximum_count=maximum_fixture_elements,
            allow_negative=True,
        )
        if not invalid_token_ids or any(
            0 <= token < table_shape[0] for token in invalid_token_ids
        ):
            raise TensorOperationError(
                "malformed_request",
                "the invalid-token fixture must contain only rejected IDs",
            )
        expected_output_shape = (len(token_ids), table_shape[1])
        if descriptor.logical_shape != expected_output_shape:
            raise TensorOperationError(
                "invalid_shape",
                "embedding logical output shape does not match token and table shapes",
            )
        if descriptor.storage_shape != table_shape:
            raise TensorOperationError(
                "invalid_shape",
                "embedding storage orientation does not match the table",
            )
        normalized_inputs = {
            "table_shape": table_shape,
            "table": _finite_float_list(
                inputs["table"],
                "embedding table",
                exact_count=table_count,
            ),
            "token_ids": token_ids,
        }

    elif descriptor.operation == "rms_norm":
        _require_exact_keys(
            inputs,
            {"values", "weight", "epsilon"},
            "RMS norm inputs",
        )
        width = descriptor.logical_shape[-1]
        epsilon = _finite_float(inputs["epsilon"], "RMS norm epsilon")
        if epsilon <= 0.0:
            raise TensorOperationError(
                "malformed_request",
                "RMS norm epsilon must be finite and positive",
            )
        expected_output_shape = descriptor.logical_shape
        normalized_inputs = {
            "values": _finite_float_list(
                inputs["values"],
                "RMS norm values",
                exact_count=descriptor.element_count,
            ),
            "weight": _finite_float_list(
                inputs["weight"],
                "RMS norm weight",
                exact_count=width,
            ),
            "epsilon": epsilon,
        }

    elif descriptor.operation == "residual_add":
        _require_exact_keys(
            inputs,
            {"residual", "update"},
            "residual inputs",
        )
        expected_output_shape = descriptor.logical_shape
        normalized_inputs = {
            "residual": _finite_float_list(
                inputs["residual"],
                "residual input",
                exact_count=descriptor.element_count,
            ),
            "update": _finite_float_list(
                inputs["update"],
                "residual update",
                exact_count=descriptor.element_count,
            ),
        }

    elif descriptor.operation == "router_topk_softmax":
        _require_exact_keys(
            inputs,
            {
                "scores",
                "token_count",
                "expert_count",
                "top_k",
                "tie_rule",
            },
            "router inputs",
        )
        token_count = _strict_integer(inputs["token_count"], "router token count")
        expert_count = _strict_integer(inputs["expert_count"], "router expert count")
        top_k = _strict_integer(inputs["top_k"], "router top-k")
        if token_count <= 0 or expert_count <= 0 or top_k <= 0 or top_k > expert_count:
            raise TensorOperationError(
                "invalid_shape",
                "router counts and top-k are outside their admitted bounds",
            )
        if token_count > maximum_fixture_elements // expert_count:
            raise TensorOperationError(
                "resource_limit",
                "router score cardinality exceeds the fixture bound",
            )
        if descriptor.logical_shape != (token_count, expert_count):
            raise TensorOperationError(
                "invalid_shape",
                "router logical shape does not match token and expert counts",
            )
        tie_rule = _stable_id(inputs["tie_rule"], "router tie rule")
        if tie_rule != "score_descending_then_expert_id_ascending":
            raise TensorOperationError(
                "malformed_request",
                "the router tie rule is unsupported",
            )
        expected_expert_ids = _integer_list(
            case["expected_expert_ids"],
            "expected router expert IDs",
            exact_count=token_count * top_k,
        )
        if any(expert < 0 or expert >= expert_count for expert in expected_expert_ids):
            raise TensorOperationError(
                "malformed_request",
                "an expected router expert ID is outside its range",
            )
        expected_output_shape = (token_count, top_k)
        normalized_inputs = {
            "scores": _finite_float_list(
                inputs["scores"],
                "router scores",
                exact_count=token_count * expert_count,
            ),
            "token_count": token_count,
            "expert_count": expert_count,
            "top_k": top_k,
        }

    else:
        _require_exact_keys(
            inputs,
            {"encoded_hex", "activation"},
            "Q8_0 inputs",
        )
        quantization = case["quantization"]
        if not isinstance(quantization, Mapping):
            raise TensorOperationError(
                "malformed_request",
                "the Q8_0 descriptor must contain a quantization object",
            )
        _require_exact_keys(
            quantization,
            {"id", "block_elements", "block_bytes", "scale_dtype"},
            "Q8_0 quantization",
        )
        if _stable_id(quantization["id"], "quantization identity") != "Q8_0":
            raise TensorOperationError(
                "invalid_dtype",
                "the quantization identity is not Q8_0",
            )
        block_elements = _strict_integer(
            quantization["block_elements"],
            "Q8_0 block elements",
        )
        block_bytes = _strict_integer(
            quantization["block_bytes"],
            "Q8_0 block bytes",
        )
        if block_elements != 32 or block_bytes != 34:
            raise TensorOperationError(
                "invalid_byte_count",
                "the Q8_0 block layout must be exactly 32 elements in 34 bytes",
            )
        if (
            _stable_id(quantization["scale_dtype"], "Q8_0 scale dtype")
            != "float16_little_endian"
        ):
            raise TensorOperationError(
                "invalid_dtype",
                "the Q8_0 scale must be little-endian IEEE binary16",
            )
        if len(descriptor.logical_shape) != 2 or descriptor.logical_shape[0] != 1:
            raise TensorOperationError(
                "invalid_shape",
                "the initial Q8_0 fixture admits one complete row",
            )
        row_width = descriptor.logical_shape[1]
        if row_width <= 0 or row_width % block_elements != 0:
            raise TensorOperationError(
                "invalid_shape",
                "the Q8_0 row width must be positive and divisible by 32",
            )
        block_count = row_width // block_elements
        expected_encoded_bytes = block_count * block_bytes
        if descriptor.encoded_byte_count != expected_encoded_bytes:
            raise TensorOperationError(
                "invalid_byte_count",
                "the declared Q8_0 encoded byte count is not exact",
            )
        encoded = _strict_hex_bytes(
            inputs["encoded_hex"],
            exact_count=expected_encoded_bytes,
        )
        scales, quants = _decode_q8_blocks_for_validation(encoded, block_count)
        expected_decoded = _finite_float_list(
            case["expected_decoded"],
            "expected Q8_0 decoded values",
            exact_count=row_width,
        )
        expected_output_shape = (1,)
        normalized_inputs = {
            "row_width": row_width,
            "block_count": block_count,
            "scales": scales,
            "quants": quants,
            "activation": _finite_float_list(
                inputs["activation"],
                "Q8_0 activation",
                exact_count=row_width,
            ),
        }

    expected_count = _shape_product(expected_output_shape)
    expected = _finite_float_list(
        case["expected"],
        "expected fixture output",
        exact_count=expected_count,
    )
    return {
        "inputs": normalized_inputs,
        "expected": expected,
        "comparison": comparison,
        "output_shape": expected_output_shape,
        "expected_expert_ids": (
            expected_expert_ids
            if descriptor.operation == "router_topk_softmax"
            else ()
        ),
        "expected_decoded": (
            expected_decoded if descriptor.operation == "q8_0_decode_dot" else ()
        ),
    }


def _schedule_operation(
    mx: Any,
    descriptor: FixtureDescriptor,
    validated: Mapping[str, Any],
) -> tuple[Any, Any | None, Any | None, tuple[int, ...]]:
    values = validated["inputs"]
    output_shape = validated["output_shape"]
    selected_ids = None
    decoded = None

    with mx.stream(mx.gpu):
        if descriptor.operation == "elementwise_fma":
            left = _mlx_float_array(mx, values["left"], descriptor.logical_shape)
            right = _mlx_float_array(mx, values["right"], descriptor.logical_shape)
            result = left * right + values["bias"]

        elif descriptor.operation == "matmul":
            left = _mlx_float_array(mx, values["left"], values["left_shape"])
            right = _mlx_float_array(mx, values["right"], values["right_shape"])
            result = mx.matmul(left, right, stream=mx.gpu)

        elif descriptor.operation == "embedding_gather":
            table = _mlx_float_array(mx, values["table"], values["table_shape"])
            token_ids = mx.array(values["token_ids"], dtype=mx.int32)
            result = mx.take(table, token_ids, axis=0, stream=mx.gpu)

        elif descriptor.operation == "rms_norm":
            tensor = _mlx_float_array(mx, values["values"], descriptor.logical_shape)
            weight = mx.array(values["weight"], dtype=mx.float32)
            mean_square = mx.mean(
                tensor * tensor,
                axis=-1,
                keepdims=True,
                stream=mx.gpu,
            )
            result = tensor * mx.rsqrt(mean_square + values["epsilon"], stream=mx.gpu)
            result = result * weight

        elif descriptor.operation == "residual_add":
            residual = _mlx_float_array(
                mx,
                values["residual"],
                descriptor.logical_shape,
            )
            update = _mlx_float_array(mx, values["update"], descriptor.logical_shape)
            result = residual + update

        elif descriptor.operation == "router_topk_softmax":
            scores = _mlx_float_array(
                mx,
                values["scores"],
                (values["token_count"], values["expert_count"]),
            )
            # MLX argsort is stable. Sorting negated scores therefore orders
            # descending scores while retaining ascending expert IDs on ties.
            order = mx.argsort(-scores, axis=-1, stream=mx.gpu)
            selected_ids = order[:, : values["top_k"]]
            selected_scores = mx.take_along_axis(
                scores,
                selected_ids,
                axis=1,
                stream=mx.gpu,
            )
            result = mx.softmax(selected_scores, axis=1, stream=mx.gpu)

        else:
            quant_values = _mlx_float_array(
                mx,
                values["quants"],
                (values["block_count"], 32),
            )
            scales = _mlx_float_array(
                mx,
                values["scales"],
                (values["block_count"], 1),
            )
            decoded = mx.reshape(
                quant_values * scales,
                (values["row_width"],),
                stream=mx.gpu,
            )
            activation = mx.array(values["activation"], dtype=mx.float32)
            dot = mx.sum(decoded * activation, stream=mx.gpu)
            result = mx.reshape(dot, (1,), stream=mx.gpu)

    return result, selected_ids, decoded, output_shape


def _validate_storage_orientation(descriptor: FixtureDescriptor) -> None:
    if descriptor.operation == "embedding_gather":
        return
    if descriptor.operation == "q8_0_decode_dot":
        if (
            len(descriptor.logical_shape) != 2
            or descriptor.storage_shape
            != (descriptor.logical_shape[1], descriptor.logical_shape[0])
        ):
            raise TensorOperationError(
                "invalid_shape",
                "Q8_0 storage must state the GGUF fastest-dimension-first orientation",
            )
        return
    if descriptor.storage_shape != descriptor.logical_shape:
        raise TensorOperationError(
            "invalid_shape",
            "row-major storage orientation must match the logical fixture shape",
        )


def _validate_comparison_policy(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TensorOperationError(
            "malformed_request",
            "the fixture comparison policy must be an object",
        )
    _require_exact_keys(
        value,
        {
            "mode",
            "absolute_tolerance",
            "relative_tolerance",
            "non_finite_policy",
        },
        "comparison policy",
    )
    mode = _stable_id(value["mode"], "comparison mode")
    if mode not in {"exact", "abs_rel"}:
        raise TensorOperationError(
            "malformed_request",
            "the fixture comparison mode is unsupported",
        )
    absolute_tolerance = _finite_float(
        value["absolute_tolerance"],
        "absolute tolerance",
    )
    relative_tolerance = _finite_float(
        value["relative_tolerance"],
        "relative tolerance",
    )
    if absolute_tolerance < 0.0 or relative_tolerance < 0.0:
        raise TensorOperationError(
            "malformed_request",
            "comparison tolerances must be nonnegative",
        )
    if mode == "exact" and (absolute_tolerance != 0.0 or relative_tolerance != 0.0):
        raise TensorOperationError(
            "malformed_request",
            "exact comparison cannot declare nonzero tolerances",
        )
    non_finite_policy = _stable_id(
        value["non_finite_policy"],
        "non-finite policy",
    )
    if non_finite_policy != "reject":
        raise TensorOperationError(
            "malformed_request",
            "the initial fixture suite rejects all non-finite values",
        )
    return {
        "mode": mode,
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "non_finite_policy": non_finite_policy,
    }


def _mlx_float_array(mx: Any, values: Sequence[float], shape: Sequence[int]) -> Any:
    array = mx.array(values, dtype=mx.float32)
    return mx.reshape(array, tuple(shape), stream=mx.gpu)


def _validate_result_metadata(
    mx: Any,
    result: Any,
    expected_shape: tuple[int, ...],
) -> None:
    try:
        actual_shape = tuple(result.shape)
        actual_dtype = result.dtype
    except Exception as error:
        raise TensorOperationError(
            "evaluation_failed",
            "the MLX result did not expose bounded shape and dtype metadata",
        ) from error
    if actual_shape != expected_shape:
        raise TensorOperationError(
            "invalid_shape",
            "the evaluated MLX output shape does not match its fixture contract",
        )
    if actual_dtype != mx.float32:
        raise TensorOperationError(
            "invalid_dtype",
            "the evaluated MLX output dtype does not match float32",
        )


def _bounded_float_readback(
    value: object,
    *,
    expected_count: int,
    maximum_count: int,
) -> tuple[float, ...]:
    flattened = _flatten_bounded(value, maximum_count=maximum_count)
    if len(flattened) != expected_count:
        raise TensorOperationError(
            "invalid_shape",
            "the MLX float readback cardinality does not match its contract",
        )
    output: list[float] = []
    for element in flattened:
        if isinstance(element, bool) or not isinstance(element, (int, float)):
            raise TensorOperationError(
                "evaluation_failed",
                "the MLX float readback contains a nonnumeric value",
            )
        number = float(element)
        if not math.isfinite(number):
            raise TensorOperationError(
                "evaluation_failed",
                "the MLX float readback contains a non-finite value",
            )
        output.append(number)
    return tuple(output)


def _bounded_integer_readback(
    value: object,
    *,
    expected_count: int,
    maximum_count: int,
) -> tuple[int, ...]:
    flattened = _flatten_bounded(value, maximum_count=maximum_count)
    if len(flattened) != expected_count:
        raise TensorOperationError(
            "invalid_shape",
            "the MLX integer readback cardinality does not match its contract",
        )
    output: list[int] = []
    for element in flattened:
        if isinstance(element, bool) or not isinstance(element, int):
            raise TensorOperationError(
                "evaluation_failed",
                "the MLX integer readback contains a non-integer value",
            )
        output.append(element)
    return tuple(output)


def _flatten_bounded(value: object, *, maximum_count: int) -> list[object]:
    flattened: list[object] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, (list, tuple)):
            if len(current) > maximum_count:
                raise TensorOperationError(
                    "resource_limit",
                    "an MLX readback dimension exceeds the fixture bound",
                )
            stack.extend(reversed(current))
            continue
        flattened.append(current)
        if len(flattened) > maximum_count:
            raise TensorOperationError(
                "resource_limit",
                "the MLX readback exceeds the fixture element bound",
            )
    return flattened


def _compare_fixture_values(
    expected: Sequence[float],
    actual: Sequence[float],
    policy: Mapping[str, object],
    *,
    oracle_id: str,
) -> FixtureComparisonResult:
    if not expected or len(expected) != len(actual):
        raise TensorOperationError(
            "comparison_failed",
            "fixture comparison operands have different cardinality",
        )
    mode = str(policy["mode"])
    absolute_tolerance = float(policy["absolute_tolerance"])
    relative_tolerance = float(policy["relative_tolerance"])
    max_absolute_error = 0.0
    max_relative_error = 0.0
    first_mismatch_index: int | None = None

    for index, (expected_value, actual_value) in enumerate(zip(expected, actual)):
        if not math.isfinite(expected_value) or not math.isfinite(actual_value):
            raise TensorOperationError(
                "comparison_failed",
                "fixture comparison rejects non-finite values",
            )
        absolute_error = abs(actual_value - expected_value)
        relative_error = (
            absolute_error / abs(expected_value)
            if expected_value != 0.0
            else absolute_error
        )
        max_absolute_error = max(max_absolute_error, absolute_error)
        max_relative_error = max(max_relative_error, relative_error)
        admitted = (
            0.0
            if mode == "exact"
            else absolute_tolerance + relative_tolerance * abs(expected_value)
        )
        if absolute_error > admitted and first_mismatch_index is None:
            first_mismatch_index = index

    return FixtureComparisonResult(
        oracle_id=oracle_id,
        mode=mode,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        non_finite_policy="reject",
        compared_count=len(expected),
        max_absolute_error=max_absolute_error,
        max_relative_error=max_relative_error,
        first_mismatch_index=first_mismatch_index,
        passed=first_mismatch_index is None,
    )


def _checked_shape(
    value: object,
    label: str,
    *,
    maximum_elements: int,
    exact_rank: int | None = None,
) -> tuple[tuple[int, ...], int]:
    if not isinstance(value, list):
        raise TensorOperationError(
            "invalid_shape",
            f"{label} must be a list of positive dimensions",
        )
    if not value or len(value) > _MAX_RANK or (
        exact_rank is not None and len(value) != exact_rank
    ):
        raise TensorOperationError(
            "invalid_shape",
            f"{label} rank is outside its admitted bound",
        )
    dimensions: list[int] = []
    product = 1
    for dimension in value:
        if (
            isinstance(dimension, bool)
            or not isinstance(dimension, int)
            or dimension <= 0
            or dimension > _U64_MAX
        ):
            raise TensorOperationError(
                "invalid_shape",
                f"{label} contains an invalid dimension",
            )
        if product > maximum_elements // dimension:
            raise TensorOperationError(
                "resource_limit",
                f"{label} exceeds the fixture element bound",
            )
        product *= dimension
        dimensions.append(dimension)
    return tuple(dimensions), product


def _shape_product(shape: Sequence[int]) -> int:
    product = 1
    for dimension in shape:
        product *= dimension
    return product


def _finite_float_list(
    value: object,
    label: str,
    *,
    exact_count: int,
) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != exact_count:
        raise TensorOperationError(
            "invalid_shape",
            f"{label} cardinality does not match its declared shape",
        )
    return tuple(_finite_float(element, label) for element in value)


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TensorOperationError(
            "malformed_request",
            f"{label} must contain only numeric values",
        )
    number = float(value)
    if not math.isfinite(number):
        raise TensorOperationError(
            "malformed_request",
            f"{label} must contain only finite values",
        )
    return number


def _integer_list(
    value: object,
    label: str,
    *,
    exact_count: int | None = None,
    maximum_count: int | None = None,
    allow_negative: bool = False,
) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise TensorOperationError(
            "malformed_request",
            f"{label} must be an integer list",
        )
    if exact_count is not None and len(value) != exact_count:
        raise TensorOperationError(
            "invalid_shape",
            f"{label} cardinality does not match its contract",
        )
    if maximum_count is not None and len(value) > maximum_count:
        raise TensorOperationError(
            "resource_limit",
            f"{label} exceeds its item bound",
        )
    output: list[int] = []
    for item in value:
        if allow_negative:
            if (
                isinstance(item, bool)
                or not isinstance(item, int)
                or item < -(1 << 63)
                or item > (1 << 63) - 1
            ):
                raise TensorOperationError(
                    "malformed_request",
                    f"{label} must contain bounded integers",
                )
            output.append(item)
        else:
            output.append(_strict_integer(item, label))
    return tuple(output)


def _strict_hex_bytes(value: object, *, exact_count: int) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) != exact_count * 2
        or any(character not in "0123456789abcdefABCDEF" for character in value)
    ):
        raise TensorOperationError(
            "invalid_byte_count",
            "the Q8_0 encoded hex payload is not an exact byte representation",
        )
    try:
        decoded = bytes.fromhex(value)
    except ValueError as error:
        raise TensorOperationError(
            "invalid_byte_count",
            "the Q8_0 encoded hex payload is malformed",
        ) from error
    if len(decoded) != exact_count:
        raise TensorOperationError(
            "invalid_byte_count",
            "the Q8_0 encoded payload byte count is not exact",
        )
    return decoded


def _decode_q8_blocks_for_validation(
    encoded: bytes,
    block_count: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    scales: list[float] = []
    quants: list[float] = []
    for block_index in range(block_count):
        start = block_index * 34
        scale = float(struct.unpack_from("<e", encoded, start)[0])
        if not math.isfinite(scale):
            raise TensorOperationError(
                "invalid_dtype",
                "the Q8_0 block scale must be finite",
            )
        scales.append(scale)
        for byte in encoded[start + 2 : start + 34]:
            quants.append(float(byte - 256 if byte >= 128 else byte))
    return tuple(scales), tuple(quants)


def _strict_integer(value: object, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > _U64_MAX
    ):
        raise TensorOperationError(
            "malformed_request",
            f"{label} must be an unsigned integer",
        )
    return value


def _stable_id(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TensorOperationError(
            "malformed_request",
            f"{label} must be a stable string",
        )
    if (
        not value
        or len(value) > _MAX_ID_CHARS
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:"
            for character in value
        )
    ):
        raise TensorOperationError(
            "malformed_request",
            f"{label} is empty, unbounded, or contains unsupported characters",
        )
    return value


def _require_exact_keys(
    value: Mapping[object, object],
    expected: set[str] | frozenset[str],
    label: str,
) -> None:
    if set(value) != set(expected):
        raise TensorOperationError(
            "malformed_request",
            f"{label} fields do not match the required schema",
        )


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise TensorOperationError(
                "malformed_request",
                "the fixture manifest contains a duplicate object key",
            )
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> object:
    raise TensorOperationError(
        "malformed_request",
        "the fixture manifest contains a non-finite JSON number",
    )


def _import_mlx() -> Any:
    try:
        import mlx.core as mx
    except Exception as error:
        raise TensorOperationError(
            "device_unavailable",
            "the pinned MLX runtime could not be imported",
        ) from error
    return mx

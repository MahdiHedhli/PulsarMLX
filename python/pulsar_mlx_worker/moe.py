"""Bounded synthetic routed-MoE validation for the Apple MLX worker.

The committed fixture is fully admitted before MLX is imported or accessed.
Successful evidence comes only from an explicitly evaluated and synchronized
GPU graph; fixture metadata and scheduled work are never treated as proof.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import math
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
_FIXTURE_KIND = "synthetic"
_MAX_FIXTURE_ELEMENTS = 4_096
_MAX_LOGICAL_BYTES = 256 * 1_024
_MAX_SHARDS = 64
_MAX_ID_CHARS = 128
_MAX_TEXT_CHARS = 512
_U64_MAX = (1 << 64) - 1
_SYNC_RULE = "explicit_eval_then_gpu_synchronize"
_TIE_RULE = "score_descending_then_expert_id_ascending"
_NORMALIZATION = "softmax_over_selected_scores"


class RoutedMoeError(RuntimeContractError):
    """Stable bounded failure at the synthetic routed-MoE boundary."""


@dataclass(frozen=True, slots=True)
class RoutedMoeComparison:
    """Bounded comparison summary against a committed scalar oracle."""

    oracle_id: str
    absolute_tolerance: float
    relative_tolerance: float
    compared_count: int
    max_absolute_error: float
    max_relative_error: float
    first_mismatch_index: int | None
    passed: bool

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "oracle_id": self.oracle_id,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "compared_count": self.compared_count,
            "max_absolute_error": self.max_absolute_error,
            "max_relative_error": self.max_relative_error,
            "first_mismatch_index": self.first_mismatch_index,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class FetchedExpertEvidence:
    """Sanitized identity for one admitted synthetic expert payload."""

    expert_id: int
    offset: int
    length: int
    shard_id: str
    payload_sha256: str

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "expert_id": self.expert_id,
            "offset": self.offset,
            "length": self.length,
            "shard_id": self.shard_id,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True, slots=True)
class RoutedMoeDescriptor:
    """Immutable fixture state admitted without consulting MLX."""

    fixture_id: str
    fixture_kind: str
    oracle_id: str
    token_count: int
    hidden_size: int
    expert_count: int
    top_k: int
    selected_expert_ids: tuple[int, ...]
    normalized_weights: tuple[float, ...]
    unique_expert_ids: tuple[int, ...]
    fetched_experts: tuple[FetchedExpertEvidence, ...]
    tokens: tuple[float, ...]
    router_scores: tuple[float, ...]
    expert_matrices: tuple[tuple[float, ...], ...]
    selected_outputs: tuple[float, ...]
    weighted_output: tuple[float, ...]
    route_absolute_tolerance: float
    route_relative_tolerance: float
    output_absolute_tolerance: float
    output_relative_tolerance: float


@dataclass(frozen=True, slots=True)
class RoutedMoeResult:
    """Evaluated synthetic routed-MoE result and independent evidence."""

    fixture_id: str
    fixture_kind: str
    backend_id: str
    requested_device: str
    selected_device: str
    fallback_used: bool
    evaluated: bool
    synchronized: bool
    token_count: int
    hidden_size: int
    expert_count: int
    top_k: int
    selected_expert_ids: tuple[int, ...]
    normalized_weights: tuple[float, ...]
    fetched_experts: tuple[FetchedExpertEvidence, ...]
    output_shape: tuple[int, int]
    selected_outputs: tuple[float, ...]
    actual: tuple[float, ...]
    route_weight_comparison: RoutedMoeComparison
    output_comparison: RoutedMoeComparison
    memory_gauges: MemoryGauges

    @property
    def passed(self) -> bool:
        return (
            self.evaluated
            and self.synchronized
            and not self.fallback_used
            and self.selected_device == GPU_DEVICE_ID
            and self.route_weight_comparison.passed
            and self.output_comparison.passed
        )

    def to_protocol_result(self) -> dict[str, object]:
        """Return only fields admitted by the strict Rust protocol schema."""

        return {
            "fixture_id": self.fixture_id,
            "fixture_kind": self.fixture_kind,
            "backend_id": self.backend_id,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "token_count": self.token_count,
            "hidden_size": self.hidden_size,
            "expert_count": self.expert_count,
            "top_k": self.top_k,
            "selected_expert_ids": _reshape_rows(
                self.selected_expert_ids,
                self.token_count,
                self.top_k,
            ),
            "normalized_weights": _reshape_rows(
                self.normalized_weights,
                self.token_count,
                self.top_k,
            ),
            "fetched_experts": [
                expert.to_protocol_result() for expert in self.fetched_experts
            ],
            "actual": list(self.actual),
            "comparison": self.output_comparison.to_protocol_result(),
            "memory_gauges": self.memory_gauges.to_protocol_result(),
            "passed": self.passed,
        }


def validate_routed_moe_fixture(
    fixture: Mapping[str, object],
    *,
    expected_fixture_id: str,
) -> RoutedMoeDescriptor:
    """Validate the complete committed fixture without importing or using MLX."""

    expected_identity = _stable_id(expected_fixture_id, "expected fixture identity")
    document = _mapping(fixture, "routed-MoE fixture")
    _require_exact_keys(
        document,
        {
            "schema_version",
            "fixture_id",
            "fixture_kind",
            "oracle_id",
            "provenance",
            "generation",
            "tensor_contract",
            "shards",
            "experts",
            "inputs",
            "routing_oracle",
            "expert_output_oracle",
            "expected_fetch_plan",
        },
        "routed-MoE fixture",
    )
    if _strict_integer(document["schema_version"], "schema version") != _SCHEMA_VERSION:
        raise RoutedMoeError(
            "malformed_request",
            "the routed-MoE fixture schema version is unsupported",
        )
    fixture_id = _stable_id(document["fixture_id"], "fixture identity")
    if fixture_id != expected_identity:
        raise RoutedMoeError(
            "malformed_request",
            "the routed-MoE fixture identity does not match the request",
        )
    fixture_kind = _stable_id(document["fixture_kind"], "fixture kind")
    if fixture_kind != _FIXTURE_KIND:
        raise RoutedMoeError(
            "malformed_request",
            "the routed-MoE fixture must be labeled synthetic",
        )
    oracle_id = _stable_id(document["oracle_id"], "oracle identity")

    _validate_provenance(document["provenance"])
    contract = _validate_tensor_contract(document["tensor_contract"])
    token_count = contract["token_count"]
    hidden_size = contract["hidden_size"]
    expert_count = contract["expert_count"]
    top_k = contract["top_k"]

    logical_blob, shard_ranges = _validate_shards(
        document["shards"],
        document["generation"],
    )
    expert_matrices, experts = _validate_experts(
        document["experts"],
        expert_count=expert_count,
        hidden_size=hidden_size,
        logical_blob=logical_blob,
        shard_ranges=shard_ranges,
    )
    tokens, router_scores = _validate_inputs(
        document["inputs"],
        token_count=token_count,
        hidden_size=hidden_size,
        expert_count=expert_count,
    )
    (
        selected_expert_ids,
        normalized_weights,
        unique_expert_ids,
        route_absolute_tolerance,
        route_relative_tolerance,
    ) = _validate_routing_oracle(
        document["routing_oracle"],
        router_scores=router_scores,
        token_count=token_count,
        expert_count=expert_count,
        top_k=top_k,
    )
    (
        selected_outputs,
        weighted_output,
        output_absolute_tolerance,
        output_relative_tolerance,
    ) = _validate_output_oracle(
        document["expert_output_oracle"],
        tokens=tokens,
        expert_matrices=expert_matrices,
        selected_expert_ids=selected_expert_ids,
        normalized_weights=normalized_weights,
        token_count=token_count,
        hidden_size=hidden_size,
        top_k=top_k,
    )
    fetched_experts = _validate_fetch_plan(
        document["expected_fetch_plan"],
        unique_expert_ids=unique_expert_ids,
        experts=experts,
    )

    return RoutedMoeDescriptor(
        fixture_id=fixture_id,
        fixture_kind=fixture_kind,
        oracle_id=oracle_id,
        token_count=token_count,
        hidden_size=hidden_size,
        expert_count=expert_count,
        top_k=top_k,
        selected_expert_ids=selected_expert_ids,
        normalized_weights=normalized_weights,
        unique_expert_ids=unique_expert_ids,
        fetched_experts=fetched_experts,
        tokens=tokens,
        router_scores=router_scores,
        expert_matrices=expert_matrices,
        selected_outputs=selected_outputs,
        weighted_output=weighted_output,
        route_absolute_tolerance=route_absolute_tolerance,
        route_relative_tolerance=route_relative_tolerance,
        output_absolute_tolerance=output_absolute_tolerance,
        output_relative_tolerance=output_relative_tolerance,
    )


def run_routed_moe_fixture(
    fixture: Mapping[str, object],
    *,
    expected_fixture_id: str,
    requested_device: str,
    allow_fallback: bool,
    mx_module: Any | None = None,
) -> RoutedMoeResult:
    """Admit, schedule, evaluate, synchronize, and compare one MoE fixture."""

    _stable_id(expected_fixture_id, "expected fixture identity")
    if requested_device != GPU_DEVICE_ID or allow_fallback is not False:
        raise RoutedMoeError(
            "device_unavailable",
            "routed-MoE validation requires an explicit GPU with fallback disabled",
        )

    # This complete admission pass must stay above all MLX import/access sites.
    descriptor = validate_routed_moe_fixture(
        fixture,
        expected_fixture_id=expected_fixture_id,
    )

    mx = mx_module if mx_module is not None else _import_mlx()
    try:
        with mx.stream(mx.gpu):
            tokens = _mlx_float_array(
                mx,
                descriptor.tokens,
                (descriptor.token_count, descriptor.hidden_size),
            )
            scores = _mlx_float_array(
                mx,
                descriptor.router_scores,
                (descriptor.token_count, descriptor.expert_count),
            )
            matrices = _mlx_float_array(
                mx,
                tuple(
                    value
                    for matrix in descriptor.expert_matrices
                    for value in matrix
                ),
                (
                    descriptor.expert_count,
                    descriptor.hidden_size,
                    descriptor.hidden_size,
                ),
            )

            # Stable argsort on negated scores implements descending scores and
            # preserves ascending expert IDs for equal values.
            order = mx.argsort(-scores, axis=-1, stream=mx.gpu)
            selected_ids = order[:, : descriptor.top_k]
            selected_scores = mx.take_along_axis(
                scores,
                selected_ids,
                axis=1,
                stream=mx.gpu,
            )
            normalized_weights = mx.softmax(
                selected_scores,
                axis=1,
                stream=mx.gpu,
            )
            selected_matrices = mx.take(
                matrices,
                selected_ids,
                axis=0,
                stream=mx.gpu,
            )
            token_rows = mx.reshape(
                tokens,
                (descriptor.token_count, 1, 1, descriptor.hidden_size),
                stream=mx.gpu,
            )
            selected_outputs = mx.matmul(
                token_rows,
                selected_matrices,
                stream=mx.gpu,
            )
            selected_outputs = mx.reshape(
                selected_outputs,
                (
                    descriptor.token_count,
                    descriptor.top_k,
                    descriptor.hidden_size,
                ),
                stream=mx.gpu,
            )
            weighted = selected_outputs * mx.reshape(
                normalized_weights,
                (descriptor.token_count, descriptor.top_k, 1),
                stream=mx.gpu,
            )
            output = mx.sum(weighted, axis=1, stream=mx.gpu)

        mx.eval(selected_ids, normalized_weights, selected_outputs, output)
        evaluated = True
        mx.synchronize(mx.gpu)
        synchronized = True

        _require_array_metadata(
            mx,
            selected_ids,
            (descriptor.token_count, descriptor.top_k),
            require_float32=False,
        )
        _require_array_metadata(
            mx,
            normalized_weights,
            (descriptor.token_count, descriptor.top_k),
            require_float32=True,
        )
        _require_array_metadata(
            mx,
            selected_outputs,
            (
                descriptor.token_count,
                descriptor.top_k,
                descriptor.hidden_size,
            ),
            require_float32=True,
        )
        _require_array_metadata(
            mx,
            output,
            (descriptor.token_count, descriptor.hidden_size),
            require_float32=True,
        )
        actual_ids = _bounded_integer_readback(
            selected_ids.tolist(),
            expected_count=descriptor.token_count * descriptor.top_k,
        )
        actual_weights = _bounded_float_readback(
            normalized_weights.tolist(),
            expected_count=descriptor.token_count * descriptor.top_k,
        )
        actual_selected_outputs = _bounded_float_readback(
            selected_outputs.tolist(),
            expected_count=(
                descriptor.token_count
                * descriptor.top_k
                * descriptor.hidden_size
            ),
        )
        actual = _bounded_float_readback(
            output.tolist(),
            expected_count=descriptor.token_count * descriptor.hidden_size,
        )
    except RoutedMoeError:
        raise
    except Exception as error:
        raise RoutedMoeError(
            "evaluation_failed",
            "the explicit MLX GPU routed-MoE graph did not complete",
        ) from error

    route_comparison = _compare_values(
        descriptor.normalized_weights,
        actual_weights,
        oracle_id=f"{descriptor.oracle_id}:routes",
        absolute_tolerance=descriptor.route_absolute_tolerance,
        relative_tolerance=descriptor.route_relative_tolerance,
    )
    if actual_ids != descriptor.selected_expert_ids:
        route_comparison = replace(
            route_comparison,
            first_mismatch_index=_first_difference(
                descriptor.selected_expert_ids,
                actual_ids,
            ),
            passed=False,
        )
    selected_output_comparison = _compare_values(
        descriptor.selected_outputs,
        actual_selected_outputs,
        oracle_id=f"{descriptor.oracle_id}:selected-outputs",
        absolute_tolerance=descriptor.output_absolute_tolerance,
        relative_tolerance=descriptor.output_relative_tolerance,
    )
    output_comparison = _compare_values(
        descriptor.weighted_output,
        actual,
        oracle_id=descriptor.oracle_id,
        absolute_tolerance=descriptor.output_absolute_tolerance,
        relative_tolerance=descriptor.output_relative_tolerance,
    )
    if not route_comparison.passed or not selected_output_comparison.passed:
        output_comparison = replace(
            output_comparison,
            max_absolute_error=max(
                output_comparison.max_absolute_error,
                selected_output_comparison.max_absolute_error,
            ),
            max_relative_error=max(
                output_comparison.max_relative_error,
                selected_output_comparison.max_relative_error,
            ),
            first_mismatch_index=(
                output_comparison.first_mismatch_index
                if output_comparison.first_mismatch_index is not None
                else 0
            ),
            passed=False,
        )

    try:
        memory_gauges = collect_memory_gauges(mx)
    except RuntimeContractError as error:
        raise RoutedMoeError(error.code, error.message) from error

    return RoutedMoeResult(
        fixture_id=descriptor.fixture_id,
        fixture_kind=descriptor.fixture_kind,
        backend_id=BACKEND_ID,
        requested_device=GPU_DEVICE_ID,
        selected_device=GPU_DEVICE_ID,
        fallback_used=False,
        evaluated=evaluated,
        synchronized=synchronized,
        token_count=descriptor.token_count,
        hidden_size=descriptor.hidden_size,
        expert_count=descriptor.expert_count,
        top_k=descriptor.top_k,
        selected_expert_ids=actual_ids,
        normalized_weights=actual_weights,
        fetched_experts=descriptor.fetched_experts,
        output_shape=(descriptor.token_count, descriptor.hidden_size),
        selected_outputs=actual_selected_outputs,
        actual=actual,
        route_weight_comparison=route_comparison,
        output_comparison=output_comparison,
        memory_gauges=memory_gauges,
    )


def _validate_provenance(value: object) -> None:
    provenance = _mapping(value, "fixture provenance")
    _require_exact_keys(
        provenance,
        {"origin", "authors", "license", "license_file"},
        "fixture provenance",
    )
    for field in ("origin", "authors", "license", "license_file"):
        _bounded_text(provenance[field], f"provenance {field}")
    if provenance["license"] != "MIT" or provenance["license_file"] != "LICENSE":
        raise RoutedMoeError(
            "malformed_request",
            "the synthetic fixture provenance must retain its MIT license identity",
        )


def _validate_tensor_contract(value: object) -> dict[str, int]:
    contract = _mapping(value, "tensor contract")
    _require_exact_keys(
        contract,
        {
            "token_count",
            "hidden_size",
            "expert_count",
            "top_k",
            "input_dtype",
            "weight_dtype",
            "accumulation_dtype",
            "output_dtype",
            "weight_layout",
            "synchronization_rule",
            "requested_device",
            "allow_fallback",
        },
        "tensor contract",
    )
    token_count = _strict_integer(contract["token_count"], "token count")
    hidden_size = _strict_integer(contract["hidden_size"], "hidden size")
    expert_count = _strict_integer(contract["expert_count"], "expert count")
    top_k = _strict_integer(contract["top_k"], "top-k")
    if (
        token_count <= 0
        or hidden_size <= 0
        or expert_count <= 0
        or top_k <= 0
        or top_k > expert_count
    ):
        raise RoutedMoeError(
            "invalid_shape",
            "routed-MoE dimensions and top-k must be positive and bounded",
        )
    for dimensions in (
        (token_count, hidden_size),
        (token_count, expert_count),
        (token_count, top_k, hidden_size),
        (expert_count, hidden_size, hidden_size),
    ):
        _checked_cardinality(dimensions)
    if any(
        contract[field] != "float32"
        for field in (
            "input_dtype",
            "weight_dtype",
            "accumulation_dtype",
            "output_dtype",
        )
    ):
        raise RoutedMoeError(
            "invalid_dtype",
            "the synthetic routed-MoE contract requires float32 tensors",
        )
    if contract["weight_layout"] != "row_major_input_by_output":
        raise RoutedMoeError(
            "invalid_layout",
            "the synthetic expert matrix orientation is unsupported",
        )
    if (
        contract["synchronization_rule"] != _SYNC_RULE
        or contract["requested_device"] != GPU_DEVICE_ID
        or contract["allow_fallback"] is not False
    ):
        raise RoutedMoeError(
            "malformed_request",
            "the fixture must require evaluated GPU execution without fallback",
        )
    return {
        "token_count": token_count,
        "hidden_size": hidden_size,
        "expert_count": expert_count,
        "top_k": top_k,
    }


def _validate_shards(
    value: object,
    generation_value: object,
) -> tuple[bytes, dict[str, tuple[int, int]]]:
    generation = _mapping(generation_value, "fixture generation")
    _require_exact_keys(
        generation,
        {"format", "recipe", "logical_blob_sha256", "logical_blob_bytes"},
        "fixture generation",
    )
    if generation["format"] != "IEEE-754 float32 little-endian":
        raise RoutedMoeError(
            "invalid_dtype",
            "the synthetic blob encoding is unsupported",
        )
    _bounded_text(generation["recipe"], "fixture generation recipe")
    expected_blob_hash = _sha256_text(
        generation["logical_blob_sha256"],
        "logical blob digest",
    )
    expected_blob_bytes = _strict_integer(
        generation["logical_blob_bytes"],
        "logical blob byte count",
    )
    if not 0 < expected_blob_bytes <= _MAX_LOGICAL_BYTES:
        raise RoutedMoeError(
            "resource_limit",
            "the synthetic logical blob exceeds its byte bound",
        )

    shards = _bounded_list(value, "fixture shards", maximum_count=_MAX_SHARDS)
    if not shards:
        raise RoutedMoeError("invalid_shape", "the fixture has no expert shards")
    chunks: list[bytes] = []
    shard_ranges: dict[str, tuple[int, int]] = {}
    next_base = 0
    for index, raw_shard in enumerate(shards):
        shard = _mapping(raw_shard, "fixture shard")
        _require_exact_keys(
            shard,
            {"shard_id", "base", "length", "data_hex", "sha256"},
            "fixture shard",
        )
        shard_id = _stable_id(shard["shard_id"], "shard identity")
        if shard_id in shard_ranges:
            raise RoutedMoeError(
                "malformed_request",
                "the fixture repeats a shard identity",
            )
        base = _strict_integer(shard["base"], "shard base")
        length = _strict_integer(shard["length"], "shard length")
        if base != next_base or length <= 0:
            raise RoutedMoeError(
                "invalid_shape",
                "fixture shards must form one positive contiguous logical space",
            )
        end = _checked_add(base, length, "shard logical range")
        if end > _MAX_LOGICAL_BYTES:
            raise RoutedMoeError(
                "resource_limit",
                "the synthetic shard space exceeds its byte bound",
            )
        payload = _hex_bytes(shard["data_hex"], exact_count=length)
        digest = _sha256_text(shard["sha256"], "shard digest")
        if hashlib.sha256(payload).hexdigest() != digest:
            raise RoutedMoeError(
                "malformed_request",
                "a synthetic shard payload does not match its digest",
            )
        chunks.append(payload)
        shard_ranges[shard_id] = (base, end)
        next_base = end
        if index + 1 > _MAX_SHARDS:
            raise RoutedMoeError("resource_limit", "too many synthetic shards")

    logical_blob = b"".join(chunks)
    if (
        len(logical_blob) != expected_blob_bytes
        or hashlib.sha256(logical_blob).hexdigest() != expected_blob_hash
    ):
        raise RoutedMoeError(
            "malformed_request",
            "the synthetic logical blob does not match its declared identity",
        )
    return logical_blob, shard_ranges


def _validate_experts(
    value: object,
    *,
    expert_count: int,
    hidden_size: int,
    logical_blob: bytes,
    shard_ranges: Mapping[str, tuple[int, int]],
) -> tuple[
    tuple[tuple[float, ...], ...],
    dict[int, FetchedExpertEvidence],
]:
    entries = _bounded_list(value, "fixture experts", maximum_count=_MAX_FIXTURE_ELEMENTS)
    if len(entries) != expert_count:
        raise RoutedMoeError(
            "invalid_shape",
            "the fixture expert count does not match its tensor contract",
        )
    matrix_count = _checked_cardinality((hidden_size, hidden_size))
    matrices: list[tuple[float, ...] | None] = [None] * expert_count
    experts: dict[int, FetchedExpertEvidence] = {}
    for raw_expert in entries:
        expert = _mapping(raw_expert, "fixture expert")
        _require_exact_keys(
            expert,
            {"expert_id", "matrix", "logical_range", "payload_sha256"},
            "fixture expert",
        )
        expert_id = _strict_integer(expert["expert_id"], "expert identity")
        if not 0 <= expert_id < expert_count or expert_id in experts:
            raise RoutedMoeError(
                "malformed_request",
                "an expert identity is out of range or duplicated",
            )
        matrix = _finite_float_list(
            expert["matrix"],
            "expert matrix",
            exact_count=matrix_count,
            shape_error=True,
        )
        logical_range = _mapping(expert["logical_range"], "expert logical range")
        _require_exact_keys(
            logical_range,
            {"offset", "length", "shard_id"},
            "expert logical range",
        )
        offset = _strict_integer(logical_range["offset"], "expert offset")
        length = _strict_integer(logical_range["length"], "expert byte length")
        shard_id = _stable_id(logical_range["shard_id"], "expert shard identity")
        expected_length = matrix_count * struct.calcsize("<f")
        if length != expected_length:
            raise RoutedMoeError(
                "invalid_shape",
                "an expert payload length does not match its matrix shape",
            )
        end = _checked_add(offset, length, "expert logical range")
        shard_range = shard_ranges.get(shard_id)
        if (
            shard_range is None
            or offset < shard_range[0]
            or end > shard_range[1]
            or end > len(logical_blob)
        ):
            raise RoutedMoeError(
                "malformed_request",
                "an expert range is not contained in its declared shard",
            )
        payload_hash = _sha256_text(expert["payload_sha256"], "expert digest")
        payload = logical_blob[offset:end]
        encoded_matrix = b"".join(struct.pack("<f", item) for item in matrix)
        if payload != encoded_matrix or hashlib.sha256(payload).hexdigest() != payload_hash:
            raise RoutedMoeError(
                "malformed_request",
                "an expert matrix does not match its exact stored payload",
            )
        evidence = FetchedExpertEvidence(
            expert_id=expert_id,
            offset=offset,
            length=length,
            shard_id=shard_id,
            payload_sha256=payload_hash,
        )
        matrices[expert_id] = matrix
        experts[expert_id] = evidence

    if any(matrix is None for matrix in matrices):
        raise RoutedMoeError(
            "malformed_request",
            "the fixture expert identities are not contiguous",
        )
    return tuple(matrix for matrix in matrices if matrix is not None), experts


def _validate_inputs(
    value: object,
    *,
    token_count: int,
    hidden_size: int,
    expert_count: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    inputs = _mapping(value, "routed-MoE inputs")
    _require_exact_keys(inputs, {"tokens", "router_scores"}, "routed-MoE inputs")
    tokens = _finite_float_matrix(
        inputs["tokens"],
        "token input",
        rows=token_count,
        columns=hidden_size,
    )
    router_scores = _finite_float_matrix(
        inputs["router_scores"],
        "router scores",
        rows=token_count,
        columns=expert_count,
    )
    return tokens, router_scores


def _validate_routing_oracle(
    value: object,
    *,
    router_scores: Sequence[float],
    token_count: int,
    expert_count: int,
    top_k: int,
) -> tuple[tuple[int, ...], tuple[float, ...], tuple[int, ...], float, float]:
    oracle = _mapping(value, "routing oracle")
    _require_exact_keys(
        oracle,
        {
            "tie_rule",
            "normalization",
            "selected_expert_ids",
            "normalized_weights",
            "repeated_expert_ids_are_valid",
            "repeated_expert_ids",
            "absolute_tolerance",
            "relative_tolerance",
        },
        "routing oracle",
    )
    if oracle["tie_rule"] != _TIE_RULE or oracle["normalization"] != _NORMALIZATION:
        raise RoutedMoeError(
            "malformed_request",
            "the routing oracle uses an unsupported tie or normalization rule",
        )
    if oracle["repeated_expert_ids_are_valid"] is not True:
        raise RoutedMoeError(
            "malformed_request",
            "the synthetic route must explicitly admit repeated experts across tokens",
        )
    selected_ids = _integer_matrix(
        oracle["selected_expert_ids"],
        "selected expert IDs",
        rows=token_count,
        columns=top_k,
    )
    if any(expert_id < 0 or expert_id >= expert_count for expert_id in selected_ids):
        raise RoutedMoeError(
            "malformed_request",
            "the routing oracle contains an out-of-range expert",
        )
    for row_start in range(0, len(selected_ids), top_k):
        if len(set(selected_ids[row_start : row_start + top_k])) != top_k:
            raise RoutedMoeError(
                "malformed_request",
                "a route selects the same expert more than once for one token",
            )
    weights = _finite_float_matrix(
        oracle["normalized_weights"],
        "normalized routing weights",
        rows=token_count,
        columns=top_k,
    )
    for row_start in range(0, len(weights), top_k):
        row = weights[row_start : row_start + top_k]
        if any(weight < 0.0 for weight in row) or abs(sum(row) - 1.0) > 1.0e-6:
            raise RoutedMoeError(
                "malformed_request",
                "routing weights must be finite, nonnegative, and normalized",
            )
    absolute_tolerance = _nonnegative_finite(
        oracle["absolute_tolerance"],
        "routing absolute tolerance",
    )
    relative_tolerance = _nonnegative_finite(
        oracle["relative_tolerance"],
        "routing relative tolerance",
    )

    scalar_ids: list[int] = []
    scalar_weights: list[float] = []
    for token_index in range(token_count):
        row_start = token_index * expert_count
        scores = router_scores[row_start : row_start + expert_count]
        ordered = sorted(range(expert_count), key=lambda expert_id: (-scores[expert_id], expert_id))
        chosen = ordered[:top_k]
        maximum = max(scores[expert_id] for expert_id in chosen)
        exponentials = [math.exp(scores[expert_id] - maximum) for expert_id in chosen]
        denominator = sum(exponentials)
        scalar_ids.extend(chosen)
        scalar_weights.extend(value / denominator for value in exponentials)
    if tuple(scalar_ids) != selected_ids:
        raise RoutedMoeError(
            "malformed_request",
            "the selected-expert oracle contradicts deterministic scalar routing",
        )
    _require_values_close(
        scalar_weights,
        weights,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        label="normalized routing oracle",
    )

    counts = Counter(selected_ids)
    repeated = tuple(sorted(expert_id for expert_id, count in counts.items() if count > 1))
    declared_repeated = _integer_list(
        oracle["repeated_expert_ids"],
        "repeated expert IDs",
        maximum_count=expert_count,
    )
    if declared_repeated != repeated:
        raise RoutedMoeError(
            "malformed_request",
            "the repeated-expert declaration contradicts the routing oracle",
        )
    unique_expert_ids = tuple(dict.fromkeys(selected_ids))
    return (
        selected_ids,
        weights,
        unique_expert_ids,
        absolute_tolerance,
        relative_tolerance,
    )


def _validate_output_oracle(
    value: object,
    *,
    tokens: Sequence[float],
    expert_matrices: Sequence[Sequence[float]],
    selected_expert_ids: Sequence[int],
    normalized_weights: Sequence[float],
    token_count: int,
    hidden_size: int,
    top_k: int,
) -> tuple[tuple[float, ...], tuple[float, ...], float, float]:
    oracle = _mapping(value, "expert output oracle")
    _require_exact_keys(
        oracle,
        {
            "selected_outputs",
            "weighted_output",
            "absolute_tolerance",
            "relative_tolerance",
            "non_finite_policy",
        },
        "expert output oracle",
    )
    if oracle["non_finite_policy"] != "reject":
        raise RoutedMoeError(
            "malformed_request",
            "the synthetic output oracle must reject non-finite values",
        )
    selected_outputs = _finite_float_tensor3(
        oracle["selected_outputs"],
        "selected expert outputs",
        depth0=token_count,
        depth1=top_k,
        depth2=hidden_size,
    )
    weighted_output = _finite_float_matrix(
        oracle["weighted_output"],
        "weighted expert output",
        rows=token_count,
        columns=hidden_size,
    )
    absolute_tolerance = _nonnegative_finite(
        oracle["absolute_tolerance"],
        "output absolute tolerance",
    )
    relative_tolerance = _nonnegative_finite(
        oracle["relative_tolerance"],
        "output relative tolerance",
    )

    scalar_selected: list[float] = []
    scalar_weighted: list[float] = []
    for token_index in range(token_count):
        token = tokens[
            token_index * hidden_size : (token_index + 1) * hidden_size
        ]
        token_outputs: list[tuple[float, ...]] = []
        for route_index in range(top_k):
            route_offset = token_index * top_k + route_index
            matrix = expert_matrices[selected_expert_ids[route_offset]]
            expert_output = tuple(
                sum(
                    token[input_index]
                    * matrix[input_index * hidden_size + output_index]
                    for input_index in range(hidden_size)
                )
                for output_index in range(hidden_size)
            )
            token_outputs.append(expert_output)
            scalar_selected.extend(expert_output)
        for output_index in range(hidden_size):
            scalar_weighted.append(
                sum(
                    normalized_weights[token_index * top_k + route_index]
                    * token_outputs[route_index][output_index]
                    for route_index in range(top_k)
                )
            )
    _require_values_close(
        scalar_selected,
        selected_outputs,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        label="selected expert output oracle",
    )
    _require_values_close(
        scalar_weighted,
        weighted_output,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        label="weighted expert output oracle",
    )
    return (
        selected_outputs,
        weighted_output,
        absolute_tolerance,
        relative_tolerance,
    )


def _validate_fetch_plan(
    value: object,
    *,
    unique_expert_ids: Sequence[int],
    experts: Mapping[int, FetchedExpertEvidence],
) -> tuple[FetchedExpertEvidence, ...]:
    plan = _bounded_list(value, "expected fetch plan", maximum_count=len(experts))
    if len(plan) != len(unique_expert_ids):
        raise RoutedMoeError(
            "invalid_shape",
            "the fetch plan does not cover exactly the unique routed experts",
        )
    result: list[FetchedExpertEvidence] = []
    for raw_entry, expected_expert_id in zip(plan, unique_expert_ids):
        entry = _mapping(raw_entry, "fetch-plan entry")
        _require_exact_keys(
            entry,
            {"expert_id", "offset", "length", "shard_id"},
            "fetch-plan entry",
        )
        expert_id = _strict_integer(entry["expert_id"], "fetch-plan expert identity")
        expected = experts.get(expected_expert_id)
        if expected is None or expert_id != expected_expert_id:
            raise RoutedMoeError(
                "malformed_request",
                "the fetch plan order does not match first routed expert use",
            )
        if (
            _strict_integer(entry["offset"], "fetch-plan offset") != expected.offset
            or _strict_integer(entry["length"], "fetch-plan length") != expected.length
            or _stable_id(entry["shard_id"], "fetch-plan shard identity")
            != expected.shard_id
        ):
            raise RoutedMoeError(
                "malformed_request",
                "a fetch-plan range contradicts its admitted expert payload",
            )
        result.append(expected)
    return tuple(result)


def _compare_values(
    expected: Sequence[float],
    actual: Sequence[float],
    *,
    oracle_id: str,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> RoutedMoeComparison:
    if not expected or len(expected) != len(actual):
        raise RoutedMoeError(
            "comparison_failed",
            "routed-MoE comparison operands have different cardinality",
        )
    maximum_absolute = 0.0
    maximum_relative = 0.0
    first_mismatch: int | None = None
    for index, (expected_value, actual_value) in enumerate(zip(expected, actual)):
        if not math.isfinite(expected_value) or not math.isfinite(actual_value):
            raise RoutedMoeError(
                "comparison_failed",
                "routed-MoE comparison rejects non-finite values",
            )
        absolute_error = abs(actual_value - expected_value)
        relative_error = (
            absolute_error / abs(expected_value)
            if expected_value != 0.0
            else absolute_error
        )
        maximum_absolute = max(maximum_absolute, absolute_error)
        maximum_relative = max(maximum_relative, relative_error)
        admitted = absolute_tolerance + relative_tolerance * abs(expected_value)
        if absolute_error > admitted and first_mismatch is None:
            first_mismatch = index
    return RoutedMoeComparison(
        oracle_id=oracle_id,
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        compared_count=len(expected),
        max_absolute_error=maximum_absolute,
        max_relative_error=maximum_relative,
        first_mismatch_index=first_mismatch,
        passed=first_mismatch is None,
    )


def _require_values_close(
    expected: Sequence[float],
    actual: Sequence[float],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
    label: str,
) -> None:
    if len(expected) != len(actual):
        raise RoutedMoeError("invalid_shape", f"{label} cardinality is incorrect")
    for expected_value, actual_value in zip(expected, actual):
        admitted = absolute_tolerance + relative_tolerance * abs(expected_value)
        if abs(actual_value - expected_value) > admitted:
            raise RoutedMoeError(
                "malformed_request",
                f"{label} contradicts its independent scalar computation",
            )


def _mlx_float_array(mx: Any, values: Sequence[float], shape: Sequence[int]) -> Any:
    array = mx.array(values, dtype=mx.float32)
    return mx.reshape(array, tuple(shape), stream=mx.gpu)


def _require_array_metadata(
    mx: Any,
    array: Any,
    expected_shape: tuple[int, ...],
    *,
    require_float32: bool,
) -> None:
    try:
        shape = tuple(array.shape)
        dtype = array.dtype
    except Exception as error:
        raise RoutedMoeError(
            "evaluation_failed",
            "an evaluated routed-MoE array lacks bounded metadata",
        ) from error
    if shape != expected_shape:
        raise RoutedMoeError(
            "invalid_shape",
            "an evaluated routed-MoE array shape contradicts the fixture",
        )
    if require_float32 and dtype != mx.float32:
        raise RoutedMoeError(
            "invalid_dtype",
            "an evaluated routed-MoE array is not float32",
        )


def _bounded_float_readback(value: object, *, expected_count: int) -> tuple[float, ...]:
    flattened = _flatten_bounded(value)
    if len(flattened) != expected_count:
        raise RoutedMoeError(
            "invalid_shape",
            "the routed-MoE float readback cardinality is incorrect",
        )
    result: list[float] = []
    for element in flattened:
        if isinstance(element, bool) or not isinstance(element, (int, float)):
            raise RoutedMoeError(
                "evaluation_failed",
                "the routed-MoE float readback contains a nonnumeric value",
            )
        number = float(element)
        if not math.isfinite(number):
            raise RoutedMoeError(
                "evaluation_failed",
                "the routed-MoE float readback contains a non-finite value",
            )
        result.append(number)
    return tuple(result)


def _bounded_integer_readback(value: object, *, expected_count: int) -> tuple[int, ...]:
    flattened = _flatten_bounded(value)
    if len(flattened) != expected_count:
        raise RoutedMoeError(
            "invalid_shape",
            "the routed-MoE integer readback cardinality is incorrect",
        )
    result: list[int] = []
    for element in flattened:
        if isinstance(element, bool) or not isinstance(element, int):
            raise RoutedMoeError(
                "evaluation_failed",
                "the routed-MoE integer readback contains a non-integer value",
            )
        result.append(element)
    return tuple(result)


def _flatten_bounded(value: object) -> list[object]:
    flattened: list[object] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, (list, tuple)):
            if len(current) > _MAX_FIXTURE_ELEMENTS:
                raise RoutedMoeError(
                    "resource_limit",
                    "a routed-MoE readback dimension exceeds its bound",
                )
            stack.extend(reversed(current))
            continue
        flattened.append(current)
        if len(flattened) > _MAX_FIXTURE_ELEMENTS:
            raise RoutedMoeError(
                "resource_limit",
                "the routed-MoE readback exceeds its element bound",
            )
    return flattened


def _finite_float_matrix(
    value: object,
    label: str,
    *,
    rows: int,
    columns: int,
) -> tuple[float, ...]:
    outer = _bounded_list(value, label, maximum_count=_MAX_FIXTURE_ELEMENTS)
    if len(outer) != rows:
        raise RoutedMoeError("invalid_shape", f"{label} row count is incorrect")
    flattened: list[float] = []
    for row in outer:
        flattened.extend(
            _finite_float_list(
                row,
                label,
                exact_count=columns,
                shape_error=True,
            )
        )
    return tuple(flattened)


def _integer_matrix(
    value: object,
    label: str,
    *,
    rows: int,
    columns: int,
) -> tuple[int, ...]:
    outer = _bounded_list(value, label, maximum_count=_MAX_FIXTURE_ELEMENTS)
    if len(outer) != rows:
        raise RoutedMoeError("invalid_shape", f"{label} row count is incorrect")
    flattened: list[int] = []
    for row in outer:
        values = _bounded_list(row, label, maximum_count=columns)
        if len(values) != columns:
            raise RoutedMoeError("invalid_shape", f"{label} row width is incorrect")
        flattened.extend(_strict_integer(element, label) for element in values)
    return tuple(flattened)


def _finite_float_tensor3(
    value: object,
    label: str,
    *,
    depth0: int,
    depth1: int,
    depth2: int,
) -> tuple[float, ...]:
    outer = _bounded_list(value, label, maximum_count=_MAX_FIXTURE_ELEMENTS)
    if len(outer) != depth0:
        raise RoutedMoeError("invalid_shape", f"{label} outer dimension is incorrect")
    flattened: list[float] = []
    for plane in outer:
        rows = _bounded_list(plane, label, maximum_count=depth1)
        if len(rows) != depth1:
            raise RoutedMoeError("invalid_shape", f"{label} middle dimension is incorrect")
        for row in rows:
            flattened.extend(
                _finite_float_list(
                    row,
                    label,
                    exact_count=depth2,
                    shape_error=True,
                )
            )
    return tuple(flattened)


def _finite_float_list(
    value: object,
    label: str,
    *,
    exact_count: int,
    shape_error: bool,
) -> tuple[float, ...]:
    values = _bounded_list(value, label, maximum_count=_MAX_FIXTURE_ELEMENTS)
    if len(values) != exact_count:
        raise RoutedMoeError(
            "invalid_shape" if shape_error else "malformed_request",
            f"{label} cardinality is incorrect",
        )
    return tuple(_finite_float(element, label) for element in values)


def _integer_list(
    value: object,
    label: str,
    *,
    maximum_count: int,
) -> tuple[int, ...]:
    values = _bounded_list(value, label, maximum_count=maximum_count)
    return tuple(_strict_integer(element, label) for element in values)


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RoutedMoeError("malformed_request", f"{label} must contain numbers")
    number = float(value)
    if not math.isfinite(number):
        raise RoutedMoeError(
            "malformed_request",
            f"{label} contains a non-finite value",
        )
    return number


def _nonnegative_finite(value: object, label: str) -> float:
    number = _finite_float(value, label)
    if number < 0.0:
        raise RoutedMoeError(
            "malformed_request",
            f"{label} must be nonnegative",
        )
    return number


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RoutedMoeError("malformed_request", f"{label} must be an object")
    return value


def _bounded_list(value: object, label: str, *, maximum_count: int) -> list[object]:
    if not isinstance(value, list):
        raise RoutedMoeError("invalid_shape", f"{label} must be a list")
    if len(value) > maximum_count:
        raise RoutedMoeError("resource_limit", f"{label} exceeds its item bound")
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise RoutedMoeError(
            "malformed_request",
            f"{label} fields do not match the committed schema",
        )


def _stable_id(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_ID_CHARS
        or any(
            not (
                character.isascii()
                and (character.isalnum() or character in "-_.:/")
            )
            for character in value
        )
    ):
        raise RoutedMoeError(
            "malformed_request",
            f"{label} is not a stable bounded identifier",
        )
    return value


def _bounded_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT_CHARS:
        raise RoutedMoeError(
            "malformed_request",
            f"{label} is not bounded text",
        )
    return value


def _strict_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _U64_MAX:
        raise RoutedMoeError(
            "malformed_request",
            f"{label} must be an unsigned integer",
        )
    return value


def _checked_add(left: int, right: int, label: str) -> int:
    result = left + right
    if result > _U64_MAX:
        raise RoutedMoeError("resource_limit", f"{label} overflows")
    return result


def _checked_cardinality(dimensions: Sequence[int]) -> int:
    result = 1
    for dimension in dimensions:
        if dimension <= 0 or result > _MAX_FIXTURE_ELEMENTS // dimension:
            raise RoutedMoeError(
                "resource_limit",
                "a routed-MoE tensor exceeds its element bound",
            )
        result *= dimension
    return result


def _hex_bytes(value: object, *, exact_count: int) -> bytes:
    if (
        not isinstance(value, str)
        or len(value) != exact_count * 2
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RoutedMoeError(
            "malformed_request",
            "a synthetic shard is not exact lowercase hexadecimal bytes",
        )
    try:
        return bytes.fromhex(value)
    except ValueError as error:
        raise RoutedMoeError(
            "malformed_request",
            "a synthetic shard contains invalid hexadecimal bytes",
        ) from error


def _sha256_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RoutedMoeError(
            "malformed_request",
            f"{label} is not a lowercase SHA-256 digest",
        )
    return value


def _first_difference(expected: Sequence[int], actual: Sequence[int]) -> int:
    for index, (expected_value, actual_value) in enumerate(zip(expected, actual)):
        if expected_value != actual_value:
            return index
    return min(len(expected), len(actual))


def _reshape_rows(
    values: Sequence[int] | Sequence[float],
    rows: int,
    columns: int,
) -> list[list[int]] | list[list[float]]:
    return [
        list(values[row * columns : (row + 1) * columns])
        for row in range(rows)
    ]


def _import_mlx() -> Any:
    try:
        import mlx.core as mx
    except Exception as error:
        raise RoutedMoeError(
            "device_unavailable",
            "the pinned MLX runtime could not be imported",
        ) from error
    return mx

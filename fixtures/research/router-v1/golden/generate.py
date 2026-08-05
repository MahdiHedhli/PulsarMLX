#!/usr/bin/env python3
"""Generate and byte-check the model-free Feature 002 router fixture.

This module deliberately imports only the Python standard library.  It does
not import MLX, the PulsarMLX worker, NumPy, or any checkpoint reader.  The
committed fixture is derived from an exact, reviewable weight recipe and two
one-hot hidden rows.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
from typing import Iterable, Iterator, Sequence


HIDDEN_WIDTH = 2_048
EXPERT_COUNT = 128
TOP_K = 8
SINGLE_ROW_CASE_ID = "generated-qwen3moe-router-single-row-v1"
BOUNDED_BATCH_CASE_ID = "generated-qwen3moe-router-two-row-v1"
ROW_IDS = (
    "generated-qwen3moe-router-one-hot-column-0-v1",
    "generated-qwen3moe-router-one-hot-column-1-v1",
)
EXPECTED_TOP8_IDS = (
    (83, 38, 121, 76, 31, 114, 69, 24),
    (24, 123, 94, 65, 36, 7, 106, 77),
)

FIXTURE_ROOT = Path(__file__).parent.parent
GENERATED_PATHS = (
    Path("golden/hidden_states.json"),
    Path("golden/weight_recipe.json"),
    Path("golden/expected_results.json"),
    Path("malformed/invalid-control-type.json"),
    Path("malformed/invalid-hidden-shape.json"),
    Path("malformed/truncated-router-range.json"),
    Path("malformed/overlong-router-range.json"),
    Path("malformed/invalid-orientation.json"),
    Path("malformed/invalid-top-k.json"),
    Path("malformed/non-finite-hidden-state.json"),
    Path("synthetic-tie.json"),
    Path("manifest.json"),
)

NEGATIVE_FIXTURE_MAXIMUM_BYTES = 65_536
NEGATIVE_FAILURE_STAGE = "before_router_mlx_array_construction"


def f32(value: float | Decimal) -> float:
    """Round one finite numeric value to IEEE-754 binary32."""

    rounded = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    if not math.isfinite(rounded):
        raise ValueError("fixture generation produced a non-finite float32")
    return rounded


def f32_add(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def f32_multiply(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def iter_floats(rows: Sequence[Sequence[float]]) -> Iterator[float]:
    for row in rows:
        yield from row


def canonical_f32le(values: Iterable[float]) -> bytes:
    output = bytearray()
    for value in values:
        finite = f32(value)
        output.extend(struct.pack("<f", finite))
    return bytes(output)


def canonical_f32le_sha256(values: Iterable[float]) -> str:
    return hashlib.sha256(canonical_f32le(values)).hexdigest()


def canonical_u32le_sha256(values: Iterable[int]) -> str:
    output = bytearray()
    for value in values:
        if not 0 <= value < EXPERT_COUNT:
            raise ValueError("selected expert ID is outside the fixture range")
        output.extend(struct.pack("<I", value))
    return hashlib.sha256(output).hexdigest()


def f32_bits_hex(value: float) -> str:
    """Return the conventional eight-digit binary32 bit pattern."""

    finite = f32(value)
    bits = struct.unpack("<I", struct.pack("<f", finite))[0]
    return f"{bits:08x}"


def next_positive_f32(value: float) -> float:
    """Return the next representable positive finite binary32 value."""

    finite = f32(value)
    if finite <= 0.0:
        raise ValueError("next_positive_f32 requires a positive input")
    bits = struct.unpack("<I", struct.pack("<f", finite))[0]
    return f32(struct.unpack("<f", struct.pack("<I", bits + 1))[0])


def weight_value(expert_id: int, input_column: int) -> float:
    if not 0 <= expert_id < EXPERT_COUNT:
        raise ValueError("expert_id is outside the fixture range")
    if not 0 <= input_column < HIDDEN_WIDTH:
        raise ValueError("input_column is outside the fixture range")
    if input_column == 0:
        return f32((((expert_id * 37) % EXPERT_COUNT) - 64) / 16.0)
    if input_column == 1:
        return f32((((expert_id * 53 + 7) % EXPERT_COUNT) - 64) / 16.0)
    return f32(0.0)


def weight_sha256() -> str:
    digest = hashlib.sha256()
    for expert_id in range(EXPERT_COUNT):
        for input_column in range(HIDDEN_WIDTH):
            digest.update(struct.pack("<f", weight_value(expert_id, input_column)))
    return digest.hexdigest()


def one_hot_hidden(input_column: int) -> list[float]:
    if not 0 <= input_column < HIDDEN_WIDTH:
        raise ValueError("one-hot column is outside the hidden width")
    row = [f32(0.0)] * HIDDEN_WIDTH
    row[input_column] = f32(1.0)
    return row


def scalar_f32_projection(hidden_rows: Sequence[Sequence[float]]) -> list[list[float]]:
    """Project rows with multiply/add rounding after every scalar operation."""

    result: list[list[float]] = []
    for hidden_row in hidden_rows:
        if len(hidden_row) != HIDDEN_WIDTH:
            raise ValueError("hidden row has the wrong width")
        projected_row: list[float] = []
        for expert_id in range(EXPERT_COUNT):
            accumulator = f32(0.0)
            for input_column, hidden_value in enumerate(hidden_row):
                product = f32_multiply(
                    hidden_value,
                    weight_value(expert_id, input_column),
                )
                accumulator = f32_add(accumulator, product)
            projected_row.append(accumulator)
        result.append(projected_row)
    return result


def deterministic_exp_f32(value: float) -> float:
    """Compute exp independently at high precision, then round once to F32."""

    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        exact_input = Decimal.from_float(f32(value))
        return f32(exact_input.exp())


def full_softmax_f32(logits: Sequence[float]) -> list[float]:
    if len(logits) != EXPERT_COUNT:
        raise ValueError("softmax requires all 128 fixture logits")
    maximum = max(f32(value) for value in logits)
    exponentials = [
        deterministic_exp_f32(f32(f32(value) - maximum)) for value in logits
    ]
    denominator = f32(0.0)
    for value in exponentials:
        denominator = f32_add(denominator, value)
    if denominator <= 0.0:
        raise ValueError("softmax denominator is not positive")
    return [f32(value / denominator) for value in exponentials]


def select_and_normalize(
    probabilities: Sequence[float],
) -> tuple[list[int], list[float], list[float]]:
    if len(probabilities) != EXPERT_COUNT:
        raise ValueError("selection requires all 128 probabilities")
    selected_ids = sorted(
        range(EXPERT_COUNT),
        key=lambda expert_id: (-probabilities[expert_id], expert_id),
    )[:TOP_K]
    selected_probabilities = [probabilities[expert_id] for expert_id in selected_ids]
    selected_sum = f32(0.0)
    for value in selected_probabilities:
        selected_sum = f32_add(selected_sum, value)
    if selected_sum <= 0.0:
        raise ValueError("selected-probability denominator is not positive")
    normalized_weights = [f32(value / selected_sum) for value in selected_probabilities]
    return selected_ids, selected_probabilities, normalized_weights


def hash_output_groups(
    logits: Sequence[Sequence[float]],
    probabilities: Sequence[Sequence[float]],
    selected_ids: Sequence[Sequence[int]],
    selected_probabilities: Sequence[Sequence[float]],
    normalized_weights: Sequence[Sequence[float]],
) -> dict[str, str]:
    flat_logits = list(iter_floats(logits))
    flat_probabilities = list(iter_floats(probabilities))
    flat_selected = list(iter_floats(selected_probabilities))
    flat_normalized = list(iter_floats(normalized_weights))
    float_bundle = (
        canonical_f32le(flat_logits)
        + canonical_f32le(flat_probabilities)
        + canonical_f32le(flat_selected)
        + canonical_f32le(flat_normalized)
    )
    return {
        "logits_f32le_sha256": canonical_f32le_sha256(flat_logits),
        "full_softmax_probabilities_f32le_sha256": canonical_f32le_sha256(
            flat_probabilities
        ),
        "selected_expert_ids_u32le_sha256": canonical_u32le_sha256(
            expert_id for row in selected_ids for expert_id in row
        ),
        "selected_probabilities_f32le_sha256": canonical_f32le_sha256(flat_selected),
        "normalized_weights_f32le_sha256": canonical_f32le_sha256(flat_normalized),
        "float_output_bundle_f32le_sha256": hashlib.sha256(float_bundle).hexdigest(),
    }


def build_case(
    case_id: str,
    hidden_rows: Sequence[Sequence[float]],
    hidden_row_ids: Sequence[str],
) -> dict[str, object]:
    logits = scalar_f32_projection(hidden_rows)
    probabilities = [full_softmax_f32(row) for row in logits]
    selected_ids: list[list[int]] = []
    selected_probabilities: list[list[float]] = []
    normalized_weights: list[list[float]] = []
    for row in probabilities:
        ids, selected, normalized = select_and_normalize(row)
        selected_ids.append(ids)
        selected_probabilities.append(selected)
        normalized_weights.append(normalized)

    expected_ids = [list(row) for row in EXPECTED_TOP8_IDS[: len(hidden_rows)]]
    if selected_ids != expected_ids:
        raise ValueError(
            f"generated selected IDs drifted for {case_id}: {selected_ids!r}"
        )
    for row in probabilities:
        if abs(sum(row) - 1.0) > 1.0e-6:
            raise ValueError("full-softmax row does not sum to one within policy")
    for row in normalized_weights:
        if abs(sum(row) - 1.0) > 1.0e-6:
            raise ValueError("normalized-weight row does not sum to one within policy")

    return {
        "case_id": case_id,
        "provenance": "synthetic_generated_model_free",
        "hidden_row_ids": list(hidden_row_ids),
        "hidden_shape": [len(hidden_rows), HIDDEN_WIDTH],
        "logits_shape": [len(hidden_rows), EXPERT_COUNT],
        "logits": logits,
        "full_softmax_probabilities": probabilities,
        "selected_expert_ids": selected_ids,
        "selected_probabilities": selected_probabilities,
        "normalized_weights": normalized_weights,
        "hashes": hash_output_groups(
            logits,
            probabilities,
            selected_ids,
            selected_probabilities,
            normalized_weights,
        ),
    }


def negative_fixture_bounds() -> dict[str, object]:
    """Return the common hard bounds carried by every negative fixture."""

    return {
        "expert_count": EXPERT_COUNT,
        "hidden_width": HIDDEN_WIDTH,
        "maximum_fixture_bytes": NEGATIVE_FIXTURE_MAXIMUM_BYTES,
        "maximum_hidden_rows": 2,
        "router_tensor_byte_length": EXPERT_COUNT * HIDDEN_WIDTH * 4,
        "top_k": TOP_K,
    }


def build_negative_case(
    *,
    fixture_id: str,
    category: str,
    validation_surface: str,
    expected_code: str,
    mutation: dict[str, object],
) -> dict[str, object]:
    """Describe one bounded mutation without embedding model or tensor bytes."""

    if not fixture_id or not category or not validation_surface or not expected_code:
        raise ValueError("negative fixture identity fields must be nonempty")
    if set(mutation) != {"field", "operation", "original", "replacement"}:
        raise ValueError("negative fixture mutations use one exact bounded schema")
    return {
        "bounds": negative_fixture_bounds(),
        "case": {
            "category": category,
            "expected_failure": {
                "accepted_result": False,
                "code": expected_code,
                "must_precede": NEGATIVE_FAILURE_STAGE,
                "router_runner_called": False,
            },
            "mutation": mutation,
            "validation_surface": validation_surface,
        },
        "contract_id": "qwen3moe-layer0-router-parity-v1",
        "fixture_id": fixture_id,
        "provenance": {
            "evidence_level": "synthetic_negative_fixture_only",
            "external_checkpoint_access_required": False,
            "kind": "synthetic_generated_malformed",
            "model_free": True,
            "raw_model_or_tensor_bytes_committed": False,
        },
        "schema": "pulsarmlx.fixture.router-negative-case",
        "schema_version": "1.0.0",
    }


def build_negative_documents() -> dict[Path, bytes]:
    """Build the complete bounded malformed-input inventory."""

    expected_tensor_bytes = EXPERT_COUNT * HIDDEN_WIDTH * 4
    documents = {
        Path("malformed/invalid-control-type.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-invalid-control-type-v1",
            category="malformed_scalar_type",
            validation_surface="worker_control_admission",
            expected_code="malformed_request",
            mutation={
                "field": "router_case_id",
                "operation": "replace_scalar",
                "original": SINGLE_ROW_CASE_ID,
                "replacement": 7,
            },
        ),
        Path("malformed/invalid-hidden-shape.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-invalid-hidden-shape-v1",
            category="malformed_hidden_shape",
            validation_surface="worker_hidden_state_admission",
            expected_code="invalid_shape",
            mutation={
                "field": "hidden_states.shape",
                "operation": "replace_shape",
                "original": [1, HIDDEN_WIDTH],
                "replacement": [1, HIDDEN_WIDTH - 1],
            },
        ),
        Path("malformed/truncated-router-range.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-truncated-range-v1",
            category="truncated_router_range",
            validation_surface="host_positional_range_read",
            expected_code="invalid_byte_count",
            mutation={
                "field": "router_tensor.observed_byte_count",
                "operation": "replace_observed_byte_count",
                "original": expected_tensor_bytes,
                "replacement": expected_tensor_bytes - 4,
            },
        ),
        Path("malformed/overlong-router-range.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-overlong-range-v1",
            category="overlong_router_range",
            validation_surface="host_positional_range_read",
            expected_code="invalid_byte_count",
            mutation={
                "field": "router_tensor.observed_byte_count",
                "operation": "replace_observed_byte_count",
                "original": expected_tensor_bytes,
                "replacement": expected_tensor_bytes + 4,
            },
        ),
        Path("malformed/invalid-orientation.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-invalid-orientation-v1",
            category="transposed_router_orientation",
            validation_surface="host_tensor_descriptor_admission",
            expected_code="invalid_layout",
            mutation={
                "field": "router_tensor.orientation",
                "operation": "replace_scalar",
                "original": "expert_major_rows_input_columns",
                "replacement": "input_major_rows_expert_columns",
            },
        ),
        Path("malformed/invalid-top-k.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-invalid-top-k-v1",
            category="invalid_top_k",
            validation_surface="host_tensor_descriptor_admission",
            expected_code="model_tensor_mismatch",
            mutation={
                "field": "router_tensor.top_k",
                "operation": "replace_scalar",
                "original": TOP_K,
                "replacement": TOP_K - 1,
            },
        ),
        Path("malformed/non-finite-hidden-state.json"): build_negative_case(
            fixture_id="generated-qwen3moe-router-non-finite-hidden-state-v1",
            category="non_finite_hidden_state",
            validation_surface="worker_hidden_state_admission",
            expected_code="invalid_dtype",
            mutation={
                "field": "hidden_states[0][1]",
                "operation": "replace_f32_bits_before_decode",
                "original": {
                    "f32_bits_hex": "00000000",
                    "semantic": "positive_zero",
                },
                "replacement": {
                    "f32_bits_hex": "7fc00000",
                    "semantic": "quiet_nan",
                },
            },
        ),
    }
    encoded: dict[Path, bytes] = {}
    for path, document in documents.items():
        payload = json_bytes(document)
        if len(payload) > NEGATIVE_FIXTURE_MAXIMUM_BYTES:
            raise ValueError(f"negative fixture exceeds its bound: {path.as_posix()}")
        encoded[path] = payload
    return encoded


def synthetic_tie_logits(*, near_tie: bool) -> list[float]:
    """Build complete logits with the only cutoff ambiguity at experts 7/8."""

    logits: list[float] = []
    for expert_id in range(EXPERT_COUNT):
        if expert_id < 7:
            value = 16.0 - expert_id
        elif expert_id in (7, 8):
            value = 9.0
        else:
            value = 8.0 - (expert_id / EXPERT_COUNT)
        logits.append(f32(value))
    if near_tie:
        logits[8] = next_positive_f32(logits[8])
    return logits


def build_synthetic_tie_case(*, near_tie: bool) -> dict[str, object]:
    logits = synthetic_tie_logits(near_tie=near_tie)
    probabilities = full_softmax_f32(logits)
    selected_ids, selected_probabilities, normalized_weights = select_and_normalize(
        probabilities
    )
    if near_tie:
        expected_ids = [0, 1, 2, 3, 4, 5, 6, 8]
        rank_8_expert_id = 8
        rank_9_expert_id = 7
        relation = "one_f32_ulp_logit_above"
        if not probabilities[8] > probabilities[7]:
            raise ValueError("near-tie probabilities must remain representably ordered")
    else:
        expected_ids = [0, 1, 2, 3, 4, 5, 6, 7]
        rank_8_expert_id = 7
        rank_9_expert_id = 8
        relation = "exact_f32_equal"
        if f32_bits_hex(probabilities[7]) != f32_bits_hex(probabilities[8]):
            raise ValueError("exact-tie probabilities must have identical F32 bits")
    if selected_ids != expected_ids:
        raise ValueError("synthetic cutoff fixture selected unexpected experts")
    if abs(sum(normalized_weights) - 1.0) > 1.0e-6:
        raise ValueError("synthetic cutoff weights do not sum to one")

    case_id = (
        "generated-qwen3moe-router-near-tie-v1"
        if near_tie
        else "generated-qwen3moe-router-exact-tie-v1"
    )
    return {
        "case_id": case_id,
        "cutoff": {
            "rank_8_expert_id": rank_8_expert_id,
            "rank_8_logit_f32_bits": f32_bits_hex(logits[rank_8_expert_id]),
            "rank_8_probability_f32_bits": f32_bits_hex(
                probabilities[rank_8_expert_id]
            ),
            "rank_9_expert_id": rank_9_expert_id,
            "rank_9_logit_f32_bits": f32_bits_hex(logits[rank_9_expert_id]),
            "rank_9_probability_f32_bits": f32_bits_hex(
                probabilities[rank_9_expert_id]
            ),
            "relation": relation,
        },
        "full_softmax_probabilities": [probabilities],
        "hashes": hash_output_groups(
            [logits],
            [probabilities],
            [selected_ids],
            [selected_probabilities],
            [normalized_weights],
        ),
        "kind": "near_tie" if near_tie else "exact_tie",
        "logits": [logits],
        "logits_shape": [1, EXPERT_COUNT],
        "normalized_weights": [normalized_weights],
        "provenance": "synthetic_generated_model_free",
        "selected_expert_ids": [selected_ids],
        "selected_probabilities": [selected_probabilities],
    }


def build_synthetic_tie_document() -> bytes:
    document = {
        "bounds": {
            "case_count": 2,
            "expert_count": EXPERT_COUNT,
            "maximum_fixture_bytes": NEGATIVE_FIXTURE_MAXIMUM_BYTES,
            "maximum_rows_per_case": 1,
            "top_k": TOP_K,
        },
        "cases": [
            build_synthetic_tie_case(near_tie=False),
            build_synthetic_tie_case(near_tie=True),
        ],
        "contract": {
            "contract_id": "qwen3moe-layer0-router-parity-v1",
            "non_finite_policy": "reject",
            "normalization": (
                "full_128_way_softmax_then_selected_probability_renormalization"
            ),
            "tie_rule": "probability_descending_then_expert_id_ascending",
        },
        "fixture_id": "generated-qwen3moe-router-synthetic-cutoff-v1",
        "provenance": {
            "evidence_level": "synthetic_tie_fixture_only",
            "external_checkpoint_access_required": False,
            "kind": "synthetic_generated",
            "model_free": True,
            "proves_real_checkpoint_routing": False,
        },
        "schema": "pulsarmlx.fixture.router-synthetic-tie",
        "schema_version": "1.0.0",
    }
    payload = json_bytes(document)
    if len(payload) > NEGATIVE_FIXTURE_MAXIMUM_BYTES:
        raise ValueError("synthetic tie fixture exceeds its bound")
    return payload


def json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def build_generated_documents() -> dict[Path, bytes]:
    hidden_rows = [one_hot_hidden(0), one_hot_hidden(1)]
    if canonical_f32le(hidden_rows[0]) == canonical_f32le(hidden_rows[1]):
        raise ValueError("the two generated hidden rows must differ")

    hidden_document = {
        "schema": "pulsarmlx.fixture.router-hidden-states",
        "schema_version": "1.0.0",
        "fixture_id": "generated-qwen3moe-router-hidden-states-v1",
        "provenance": "synthetic_generated_model_free",
        "dtype": "float32",
        "byte_order": "little",
        "shape": [2, HIDDEN_WIDTH],
        "canonical_byte_length": 2 * HIDDEN_WIDTH * 4,
        "canonical_f32le_sha256": canonical_f32le_sha256(iter_floats(hidden_rows)),
        "rows": [
            {
                "row_id": row_id,
                "one_hot_column": row_index,
                "canonical_f32le_sha256": canonical_f32le_sha256(row),
                "values": row,
            }
            for row_index, (row_id, row) in enumerate(zip(ROW_IDS, hidden_rows))
        ],
    }

    weight_document = {
        "schema": "pulsarmlx.fixture.router-weight-recipe",
        "schema_version": "1.0.0",
        "fixture_id": "generated-qwen3moe-router-weights-v1",
        "provenance": "synthetic_generated_model_free",
        "dtype": "float32",
        "byte_order": "little",
        "shape": [EXPERT_COUNT, HIDDEN_WIDTH],
        "layout": "expert_major_rows_input_columns",
        "logical_element_count": EXPERT_COUNT * HIDDEN_WIDTH,
        "canonical_byte_length": EXPERT_COUNT * HIDDEN_WIDTH * 4,
        "raw_weight_bytes_committed": False,
        "canonical_encoding": (
            "concatenate IEEE-754 binary32 little-endian values in expert-major "
            "row order, then input-column order"
        ),
        "columns": [
            {
                "input_column": 0,
                "formula": "f32((((expert_id * 37) % 128) - 64) / 16.0)",
                "multiplier": 37,
                "offset": 0,
                "modulus": EXPERT_COUNT,
                "center": 64,
                "divisor": 16,
            },
            {
                "input_column": 1,
                "formula": "f32((((expert_id * 53 + 7) % 128) - 64) / 16.0)",
                "multiplier": 53,
                "offset": 7,
                "modulus": EXPERT_COUNT,
                "center": 64,
                "divisor": 16,
            },
        ],
        "remaining_columns": {
            "start_inclusive": 2,
            "end_exclusive": HIDDEN_WIDTH,
            "value": 0.0,
        },
        "canonical_f32le_sha256": weight_sha256(),
    }

    cases = {
        SINGLE_ROW_CASE_ID: build_case(
            SINGLE_ROW_CASE_ID,
            hidden_rows[:1],
            ROW_IDS[:1],
        ),
        BOUNDED_BATCH_CASE_ID: build_case(
            BOUNDED_BATCH_CASE_ID,
            hidden_rows,
            ROW_IDS,
        ),
    }
    expected_document = {
        "schema": "pulsarmlx.fixture.router-expected-results",
        "schema_version": "1.0.0",
        "fixture_id": "generated-qwen3moe-router-expected-results-v1",
        "provenance": "synthetic_generated_model_free_independent_scalar",
        "contract": {
            "hidden_width": HIDDEN_WIDTH,
            "expert_count": EXPERT_COUNT,
            "top_k": TOP_K,
            "projection": (
                "expert-major scalar multiply and accumulate in ascending input "
                "column order, rounding every multiply and add to float32"
            ),
            "softmax": (
                "subtract row maximum in float32; compute each exponential at "
                "Decimal precision 80 and round it to float32; accumulate the "
                "denominator in ascending expert-ID order with float32 rounding; "
                "divide and round each probability to float32"
            ),
            "selection": (
                "full-softmax probability descending, then expert ID ascending"
            ),
            "normalization": (
                "accumulate selected probabilities in rank order with float32 "
                "rounding; divide each selected probability and round to float32"
            ),
            "non_finite_policy": "reject",
            "hash_encoding": {
                "floating_point_groups": (
                    "flatten rows in row-major order and encode each value as "
                    "IEEE-754 binary32 little-endian"
                ),
                "selected_expert_ids": (
                    "flatten rows in row-major order and encode each ID as "
                    "unsigned 32-bit little-endian"
                ),
                "float_output_bundle": (
                    "concatenate canonical logits, full-softmax probabilities, "
                    "selected probabilities, and normalized weights in that order"
                ),
            },
        },
        "cases": cases,
    }

    documents = {
        Path("golden/hidden_states.json"): json_bytes(hidden_document),
        Path("golden/weight_recipe.json"): json_bytes(weight_document),
        Path("golden/expected_results.json"): json_bytes(expected_document),
    }
    documents.update(build_negative_documents())
    documents[Path("synthetic-tie.json")] = build_synthetic_tie_document()
    generator_bytes = Path(__file__).read_bytes()
    file_records = [
        {
            "path": path.as_posix(),
            "byte_length": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(documents.items(), key=lambda item: item[0].as_posix())
    ]
    manifest_document = {
        "schema": "pulsarmlx.fixture.router-manifest",
        "schema_version": "1.0.0",
        "fixture_id": "generated-qwen3moe-router-v1",
        "provenance": {
            "kind": "synthetic_generated",
            "redistributable": True,
            "license": "MIT",
            "model_free": True,
            "external_checkpoint_access_required": False,
            "generator": "golden/generate.py",
            "generation_command": (
                "python3 fixtures/research/router-v1/golden/generate.py --write"
            ),
            "generator_sha256": hashlib.sha256(generator_bytes).hexdigest(),
            "independence": (
                "standard-library scalar generator; imports no MLX, worker, "
                "NumPy, model parser, or checkpoint reader"
            ),
        },
        "contract": {
            "contract_id": "qwen3moe-layer0-router-parity-v1",
            "hidden_width": HIDDEN_WIDTH,
            "expert_count": EXPERT_COUNT,
            "top_k": TOP_K,
            "weight_layout": "expert_major_rows_input_columns",
            "weight_dtype": "float32",
            "weight_byte_order": "little",
            "normalization": (
                "full_128_way_softmax_then_selected_probability_renormalization"
            ),
            "tie_rule": "probability_descending_then_expert_id_ascending",
        },
        "weight_fixture": {
            "recipe_path": "golden/weight_recipe.json",
            "shape": [EXPERT_COUNT, HIDDEN_WIDTH],
            "canonical_byte_length": EXPERT_COUNT * HIDDEN_WIDTH * 4,
            "canonical_f32le_sha256": weight_document[
                "canonical_f32le_sha256"
            ],
            "raw_weight_bytes_committed": False,
        },
        "hidden_state_fixture": {
            "path": "golden/hidden_states.json",
            "complete_shape": [2, HIDDEN_WIDTH],
            "canonical_byte_length": 2 * HIDDEN_WIDTH * 4,
            "canonical_f32le_sha256": hidden_document[
                "canonical_f32le_sha256"
            ],
            "finite": True,
            "rows_distinct": True,
        },
        "expected_results": {
            "path": "golden/expected_results.json",
            "complete_values": True,
            "independently_computed": True,
            "arithmetic": "scalar_float32",
        },
        "cases": [
            {
                "case_id": SINGLE_ROW_CASE_ID,
                "hidden_row_ids": [ROW_IDS[0]],
                "hidden_shape": [1, HIDDEN_WIDTH],
                "expected_result_key": SINGLE_ROW_CASE_ID,
                "hidden_f32le_sha256": canonical_f32le_sha256(hidden_rows[0]),
            },
            {
                "case_id": BOUNDED_BATCH_CASE_ID,
                "hidden_row_ids": list(ROW_IDS),
                "hidden_shape": [2, HIDDEN_WIDTH],
                "expected_result_key": BOUNDED_BATCH_CASE_ID,
                "hidden_f32le_sha256": hidden_document[
                    "canonical_f32le_sha256"
                ],
            },
        ],
        "files": file_records,
        "scope": {
            "evidence_level": "synthetic_fixture_only",
            "proves": [
                "generated complete-router fixture construction",
                "independent scalar expected-output construction",
                "deterministic byte-for-byte regeneration",
                "bounded negative-fixture inventory",
                "synthetic exact-tie and near-tie cutoff expectations",
            ],
            "does_not_prove": [
                "external checkpoint access or identity",
                "real Qwen hidden-state provenance",
                "MLX execution or Apple GPU behavior",
                "expert execution, a complete layer, model inference, or generation",
                "Linux or CUDA runtime parity",
            ],
        },
    }
    documents[Path("manifest.json")] = json_bytes(manifest_document)
    return documents


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o644)
    temporary_path.replace(path)


def write_documents(root: Path, documents: dict[Path, bytes]) -> None:
    for relative_path in GENERATED_PATHS:
        atomic_write(root / relative_path, documents[relative_path])


def check_documents(root: Path, documents: dict[Path, bytes]) -> list[str]:
    failures: list[str] = []
    for relative_path in GENERATED_PATHS:
        path = root / relative_path
        if not path.is_file():
            failures.append(f"missing generated file: {relative_path.as_posix()}")
            continue
        actual = path.read_bytes()
        expected = documents[relative_path]
        if actual != expected:
            failures.append(f"byte mismatch: {relative_path.as_posix()}")
    return failures


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate or byte-check the model-free router-v1 golden fixture."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="write generated files")
    action.add_argument("--check", action="store_true", help="compare generated bytes")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=FIXTURE_ROOT,
        help="fixture root to write/check (default: repository router-v1 fixture)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    documents = build_generated_documents()
    if arguments.write:
        write_documents(arguments.output_root, documents)
        print(
            json.dumps(
                {
                    "generated_file_count": len(GENERATED_PATHS),
                    "status": "written",
                },
                sort_keys=True,
            )
        )
        return 0

    failures = check_documents(arguments.output_root, documents)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generated_file_count": len(GENERATED_PATHS),
                "status": "byte_identical",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

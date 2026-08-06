#!/usr/bin/env python3
"""Read-only verification boundary for Feature 002 evidence candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import struct
import tempfile
from typing import Any

import generate_figures
import generate_tables
import oracle_publication
import router_oracle
from publish_evidence import (
    PublicationError,
    _read_candidate,
    _reject_non_public_values,
    sanitize_candidate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_RAW_DIRECTORY = (
    REPOSITORY_ROOT / "fixtures" / "research" / "router-v1" / "evidence"
)
CLAIMS_LEDGER = REPOSITORY_ROOT / "docs" / "research" / "CLAIMS_LEDGER.md"
REVIEWER_INDEX = REPOSITORY_ROOT / "docs" / "research" / "REVIEWER_INDEX.md"

MAX_DOCUMENT_BYTES = 512 * 1024
MAX_SIDECAR_BYTES = 128 * 1024
MAX_GENERATED_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 16 * 1024 * 1024
MAX_PUBLICATION_RAW_FILES = 512
MAX_PACKAGE_BYTES = 96 * 1024 * 1024
MAX_PACKAGE_FILES = 4_096
MAX_MARKDOWN_LINKS = 8_192
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CLAIM_ID_RE = re.compile(r"^(F002-C[0-9]{2})\s+\S.*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\n]+)\)")
URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

SIDECAR_FIELDS = {
    "schema_id",
    "schema_version",
    "generator",
    "generator_sha256",
    "generation_command",
    "output",
    "output_sha256",
    "source_commits",
    "sources",
}
REVIEWER_SECTIONS = (
    "## Raw evidence",
    "## Generated tables",
    "## Generated figures",
    "## Claims and reproduction links",
)

PINNED_ORACLE_REVISION = "b06aa774c03dbbb624e726664b714a57d1f49815"
PINNED_MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
PINNED_ROUTER_SHA256 = "98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c"
ORACLE_GENERATION_COMMAND = (
    "python3 scripts/research/router_oracle.py --model "
    "$PULSARMLX_MODEL_GGUF --source-dir $PULSARMLX_LLAMA_CPP "
    "--capture-a $PULSARMLX_CAPTURE_A --capture-a-record "
    "$PULSARMLX_CAPTURE_A_RECORD --capture-a-scheduler-trace "
    "$PULSARMLX_CAPTURE_A_SCHEDULER_TRACE --capture-b "
    "$PULSARMLX_CAPTURE_B --capture-b-record "
    "$PULSARMLX_CAPTURE_B_RECORD --capture-b-scheduler-trace "
    "$PULSARMLX_CAPTURE_B_SCHEDULER_TRACE --capture-provenance "
    "$PULSARMLX_CAPTURE_PROVENANCE --output $PULSARMLX_ROUTER_ORACLE"
)
REAL_CASE_IDS = [
    "qwen3moe-layer0-router-token0-row0-v1",
    "qwen3moe-layer0-router-token0-token1-batch-v1",
]
REAL_ORACLE_UNSUPPORTED = [
    "expert execution",
    "routed MoE aggregation",
    "complete layer or model inference",
    "generation or serving",
]
ORACLE_BUNDLE_FILES = frozenset(
    {
        "bundle-manifest.json",
        "capture-a.f32le",
        "capture-a.json",
        "capture-a.scheduler-trace.txt",
        "capture-b.f32le",
        "capture-b.json",
        "capture-b.scheduler-trace.txt",
        "capture-provenance.json",
        "execution-provenance.json",
        "oracle.json",
    }
)


class VerificationError(ValueError):
    """A bounded package-verification failure."""


def _exact_mapping(value: Any, fields: set[str], *, subject: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise VerificationError(f"{subject} contract differs")
    return value


def _round_f32(value: Any, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VerificationError(f"{subject} is not numeric")
    try:
        result = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    except (OverflowError, struct.error, ValueError) as error:
        raise VerificationError(f"{subject} is outside F32") from error
    if not math.isfinite(result):
        raise VerificationError(f"{subject} is not finite F32")
    return result


def _f32(value: Any, *, subject: str) -> float:
    result = _round_f32(value, subject=subject)
    if float(value) != result:
        raise VerificationError(f"{subject} is not canonical F32")
    return result


def _f32_add(left: float, right: float) -> float:
    return _round_f32(left + right, subject="oracle F32 accumulation")


def _f32_matrix(
    value: Any,
    *,
    rows: int,
    columns: int,
    subject: str,
) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != rows:
        raise VerificationError(f"{subject} row count differs")
    result: list[list[float]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != columns:
            raise VerificationError(f"{subject} column count differs")
        result.append([_f32(item, subject=subject) for item in row])
    return result


def _canonical_f32(values: list[list[float]]) -> bytes:
    return b"".join(struct.pack("<f", item) for row in values for item in row)


def _canonical_u32(values: list[list[int]]) -> bytes:
    if not isinstance(values, list) or len(values) != 2 or any(
        not isinstance(row, list) or len(row) != 8 for row in values
    ):
        raise VerificationError("oracle selected expert ID shape differs")
    encoded = bytearray()
    for row in values:
        for item in row:
            if type(item) is not int or not 0 <= item < 128:
                raise VerificationError("oracle selected expert ID is invalid")
            encoded.extend(struct.pack("<I", item))
    return bytes(encoded)


def _softmax_f32(logits: list[float]) -> list[float]:
    maximum = max(logits)
    exponentials = [
        _round_f32(
            math.exp(_round_f32(value - maximum, subject="oracle shifted logit")),
            subject="oracle exponential",
        )
        for value in logits
    ]
    denominator = 0.0
    for value in exponentials:
        denominator = _f32_add(denominator, value)
    if not denominator > 0.0:
        raise VerificationError("oracle softmax denominator is invalid")
    return [
        _round_f32(value / denominator, subject="oracle probability")
        for value in exponentials
    ]


def _route_f32(probabilities: list[float]) -> tuple[list[int], list[float], list[float], bool]:
    ranked = sorted(range(128), key=lambda expert_id: (-probabilities[expert_id], expert_id))
    cutoff_tie = probabilities[ranked[7]] == probabilities[ranked[8]]
    selected_ids = ranked[:8]
    selected = [probabilities[expert_id] for expert_id in selected_ids]
    selected_sum = 0.0
    for value in selected:
        selected_sum = _f32_add(selected_sum, value)
    if not selected_sum > 0.0:
        raise VerificationError("oracle selected-probability sum is invalid")
    normalized = [
        _round_f32(value / selected_sum, subject="oracle normalized weight")
        for value in selected
    ]
    return selected_ids, selected, normalized, cutoff_tie


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_router_oracle_document(document: dict[str, Any]) -> dict[str, Any]:
    """Independently revalidate bounded oracle values without model access."""

    try:
        _reject_non_public_values(document)
    except PublicationError as error:
        raise VerificationError("router oracle contains non-public data") from error
    root = _exact_mapping(
        document,
        {
            "schema", "schema_version", "oracle_id", "status", "source",
            "generator", "model", "tensor", "capture", "capture_provenance",
            "input", "result", "comparison_policy", "unsupported_interpretations",
        },
        subject="router oracle",
    )
    if (
        root["schema"] != "pulsarmlx.research.router-oracle"
        or root["schema_version"] != "1.0.0"
        or root["oracle_id"] != "qwen3moe-layer0-router-cpu-oracle-v1"
        or root["status"] != "passed"
    ):
        raise VerificationError("router oracle identity differs")

    source = _exact_mapping(
        root["source"],
        {"repository", "revision", "clean", "license", "metal", "gpu_offload"},
        subject="router oracle source",
    )
    if (
        source["repository"] not in {
            "https://github.com/ggml-org/llama.cpp",
            "https://github.com/ggml-org/llama.cpp.git",
        }
        or source["revision"] != PINNED_ORACLE_REVISION
        or source["clean"] is not True
        or source["license"] != "MIT"
        or source["metal"] is not False
        or source["gpu_offload"] is not False
    ):
        raise VerificationError("router oracle source identity differs")

    generator = _exact_mapping(
        root["generator"],
        {"path", "sha256", "generation_command", "independence", "numpy_version"},
        subject="router oracle generator",
    )
    expected_generator = REPOSITORY_ROOT / "scripts" / "research" / "router_oracle.py"
    if (
        not all(
            isinstance(generator[name], str)
            for name in ("path", "sha256", "generation_command", "independence", "numpy_version")
        )
        or generator["generation_command"] != ORACLE_GENERATION_COMMAND
        or generator["path"] != "scripts/research/router_oracle.py"
        or generator["sha256"] != _sha256(expected_generator.read_bytes())
        or "no MLX or PulsarMLX worker import or call" not in generator["independence"]
        or generator["numpy_version"] != "2.4.5"
    ):
        raise VerificationError("router oracle generator identity differs")

    model = _exact_mapping(
        root["model"],
        {"filename", "size_bytes", "sha256", "runtime_identity", "consumer_proofs"},
        subject="router oracle model",
    )
    if (
        model["filename"] != "Qwen3-30B-A3B-Q8_0.gguf"
        or model["size_bytes"] != 32_483_931_648
        or model["sha256"] != PINNED_MODEL_SHA256
    ):
        raise VerificationError("router oracle model identity differs")

    def validate_posix_identity(value: Any) -> dict[str, Any]:
        identity = _exact_mapping(
            value,
            {"device", "inode", "size_bytes", "sha256"},
            subject="router oracle runtime identity",
        )
        if (
            type(identity["device"]) is not int
            or identity["device"] < 0
            or type(identity["inode"]) is not int
            or identity["inode"] <= 0
            or identity["size_bytes"] != 32_483_931_648
            or identity["sha256"] != PINNED_MODEL_SHA256
        ):
            raise VerificationError("router oracle runtime identity differs")
        return identity

    admitted_identity = validate_posix_identity(model["runtime_identity"])
    consumers = model["consumer_proofs"]
    if not isinstance(consumers, list) or len(consumers) != 2:
        raise VerificationError("router oracle model consumers differ")
    expected_consumer_ids = ["oracle-before-gguf-reader", "oracle-after-gguf-reader"]
    for consumer, consumer_id in zip(consumers, expected_consumer_ids, strict=True):
        proof = _exact_mapping(
            consumer,
            {"consumer_id", "before", "after", "descriptor_opened_read_only", "no_follow"},
            subject="router oracle model consumer",
        )
        if (
            proof["consumer_id"] != consumer_id
            or proof["descriptor_opened_read_only"] is not True
            or proof["no_follow"] is not True
            or validate_posix_identity(proof["before"]) != admitted_identity
            or validate_posix_identity(proof["after"]) != admitted_identity
        ):
            raise VerificationError("router oracle model consumer differs")

    tensor = _exact_mapping(
        root["tensor"],
        {
            "name", "gguf_type", "gguf_dimensions_fastest_axis_first",
            "reader_shape", "orientation", "logical_element_count",
            "encoded_byte_length", "encoded_sha256",
        },
        subject="router oracle tensor",
    )
    if (
        tensor["name"] != "blk.0.ffn_gate_inp.weight"
        or tensor["gguf_type"] != "F32"
        or tensor["gguf_dimensions_fastest_axis_first"] != [2048, 128]
        or tensor["reader_shape"] != [128, 2048]
        or tensor["orientation"] != "expert_major_rows_input_columns"
        or tensor["logical_element_count"] != 262_144
        or tensor["encoded_byte_length"] != 1_048_576
        or tensor["encoded_sha256"] != PINNED_ROUTER_SHA256
    ):
        raise VerificationError("router oracle tensor identity differs")

    capture = _exact_mapping(
        root["capture"],
        {
            "source_revision", "capture_node", "capture_sha256", "row_sha256",
            "shape", "dtype", "canonical_byte_length", "direct_token_ids",
            "positions", "context", "batch", "ubatch", "threads",
            "input_adapter", "tokenizer", "model_identity",
            "independent_capture_count", "rows_distinct", "cancellation_proofs",
        },
        subject="router oracle capture",
    )
    if (
        capture.get("source_revision") != PINNED_ORACLE_REVISION
        or capture.get("capture_node") != "ffn_norm-0"
        or capture.get("shape") != [2, 2048]
        or capture.get("dtype") != "float32_little_endian"
        or capture.get("canonical_byte_length") != 16_384
        or capture.get("direct_token_ids") != [0, 1]
        or capture.get("positions") != [0, 1]
        or capture.get("context") != 2
        or capture.get("batch") != 2
        or capture.get("ubatch") != 2
        or capture.get("threads") != 1
        or capture.get("input_adapter") != "direct_token_ids_v1"
        or capture.get("tokenizer") != "not_used_direct_token_ids"
        or capture.get("independent_capture_count") != 2
        or capture.get("rows_distinct") is not True
    ):
        raise VerificationError("router oracle capture contract differs")
    if validate_posix_identity(capture["model_identity"]) != admitted_identity:
        raise VerificationError("router oracle capture model identity differs")
    proofs = capture.get("cancellation_proofs")
    if not isinstance(proofs, list) or len(proofs) != 2:
        raise VerificationError("router oracle cancellation proofs differ")
    for proof in proofs:
        checked_proof = _exact_mapping(
            proof,
            {
                "backend", "scheduler_trace_format", "scheduler_split_count",
                "scheduler_split_ids", "scheduler_backends", "scheduler_input_count",
                "scheduler_trace_sha256", "retained_scheduler_trace_byte_length",
                "retained_scheduler_trace_sha256", "target", "target_ask_count",
                "target_observation_count", "target_complete", "callback_returned_false",
                "abort_guard_armed", "abort_callback_call_count",
                "abort_callback_calls_after_target", "abort_callback_true_count",
                "decode_status", "nodes_after_target", "cancelled_before_router_or_expert",
            },
            subject="router oracle cancellation proof",
        )
        if (
            checked_proof["scheduler_trace_format"] != "ggml_sched_debug_marker_v1"
            or type(checked_proof["scheduler_input_count"]) is not int
            or not 0 <= checked_proof["scheduler_input_count"] <= 1_000_000
            or not isinstance(checked_proof["scheduler_trace_sha256"], str)
            or SHA256_RE.fullmatch(checked_proof["scheduler_trace_sha256"]) is None
            or type(checked_proof["retained_scheduler_trace_byte_length"]) is not int
            or not 1 <= checked_proof["retained_scheduler_trace_byte_length"] <= 4096
            or not isinstance(checked_proof["retained_scheduler_trace_sha256"], str)
            or SHA256_RE.fullmatch(checked_proof["retained_scheduler_trace_sha256"]) is None
            or checked_proof["target_ask_count"] != 1
            or checked_proof["target_observation_count"] != 1
            or type(checked_proof["abort_callback_call_count"]) is not int
            or checked_proof["abort_callback_call_count"] < 1
            or checked_proof["abort_callback_true_count"] != 0
            or checked_proof["decode_status"] != 0
            or proof.get("backend") != "cpu"
            or proof.get("scheduler_split_count") != 1
            or proof.get("scheduler_split_ids") != [0]
            or proof.get("scheduler_backends") != ["cpu"]
            or proof.get("target") != "ffn_norm-0"
            or proof.get("target_complete") is not True
            or proof.get("callback_returned_false") is not True
            or proof.get("abort_guard_armed") is not True
            or proof.get("abort_callback_calls_after_target") != 0
            or proof.get("nodes_after_target") != []
            or proof.get("cancelled_before_router_or_expert") is not True
        ):
            raise VerificationError("router oracle cancellation proof differs")

    validated_capture_provenance = _closed_capture_provenance(
        root["capture_provenance"]
    )
    if validated_capture_provenance["admitted_model"] != admitted_identity:
        raise VerificationError("router oracle capture provenance model differs")

    oracle_input = _exact_mapping(
        root["input"],
        {"case_ids", "shape", "dtype", "byte_order", "values", "canonical_f32le_sha256", "row_sha256"},
        subject="router oracle input",
    )
    if (
        oracle_input["case_ids"] != REAL_CASE_IDS
        or oracle_input["shape"] != [2, 2048]
        or oracle_input["dtype"] != "float32"
        or oracle_input["byte_order"] != "little"
    ):
        raise VerificationError("router oracle input contract differs")
    hidden = _f32_matrix(oracle_input["values"], rows=2, columns=2048, subject="router oracle input")
    hidden_bytes = _canonical_f32(hidden)
    row_hashes = [_sha256(_canonical_f32([row])) for row in hidden]
    if (
        hidden[0] == hidden[1]
        or oracle_input["canonical_f32le_sha256"] != _sha256(hidden_bytes)
        or oracle_input["row_sha256"] != row_hashes
        or capture.get("capture_sha256") != _sha256(hidden_bytes)
        or capture.get("row_sha256") != row_hashes
    ):
        raise VerificationError("router oracle input hashes differ")

    result = _exact_mapping(
        root["result"],
        {
            "arithmetic", "logits", "full_softmax_probabilities",
            "selected_expert_ids", "selected_probabilities", "normalized_weights",
            "cutoff_ties", "hashes", "numpy_cross_check",
        },
        subject="router oracle result",
    )
    if result["arithmetic"] != "scalar_float32_multiply_then_add_left_to_right":
        raise VerificationError("router oracle arithmetic differs")
    logits = _f32_matrix(result["logits"], rows=2, columns=128, subject="router oracle logits")
    probabilities = _f32_matrix(
        result["full_softmax_probabilities"], rows=2, columns=128,
        subject="router oracle probabilities",
    )
    selected_probabilities = _f32_matrix(
        result["selected_probabilities"], rows=2, columns=8,
        subject="router oracle selected probabilities",
    )
    normalized_weights = _f32_matrix(
        result["normalized_weights"], rows=2, columns=8,
        subject="router oracle normalized weights",
    )
    selected_ids = result["selected_expert_ids"]
    ids_bytes = _canonical_u32(selected_ids) if isinstance(selected_ids, list) else b""
    recomputed_probabilities = [_softmax_f32(row) for row in logits]
    routes = [_route_f32(row) for row in recomputed_probabilities]
    expected_ids = [route[0] for route in routes]
    expected_selected = [route[1] for route in routes]
    expected_normalized = [route[2] for route in routes]
    cutoff_ties = [route[3] for route in routes]
    if (
        _canonical_f32(probabilities) != _canonical_f32(recomputed_probabilities)
        or selected_ids != expected_ids
        or _canonical_f32(selected_probabilities) != _canonical_f32(expected_selected)
        or _canonical_f32(normalized_weights) != _canonical_f32(expected_normalized)
        or result["cutoff_ties"] != cutoff_ties
        or any(cutoff_ties)
    ):
        raise VerificationError("router oracle routing result differs")

    logits_bytes = _canonical_f32(logits)
    probabilities_bytes = _canonical_f32(probabilities)
    selected_bytes = _canonical_f32(selected_probabilities)
    normalized_bytes = _canonical_f32(normalized_weights)
    output_bundle = logits_bytes + probabilities_bytes + ids_bytes + selected_bytes + normalized_bytes
    expected_hashes = {
        "logits_f32le_sha256": _sha256(logits_bytes),
        "full_softmax_probabilities_f32le_sha256": _sha256(probabilities_bytes),
        "selected_expert_ids_u32le_sha256": _sha256(ids_bytes),
        "selected_probabilities_f32le_sha256": _sha256(selected_bytes),
        "normalized_weights_f32le_sha256": _sha256(normalized_bytes),
        "output_bundle_sha256": _sha256(output_bundle),
    }
    hashes = _exact_mapping(
        result["hashes"],
        {
            "logits_f32le_sha256", "full_softmax_probabilities_f32le_sha256",
            "selected_expert_ids_u32le_sha256", "selected_probabilities_f32le_sha256",
            "normalized_weights_f32le_sha256", "output_bundle_sha256",
        },
        subject="router oracle output hashes",
    )
    if hashes != expected_hashes:
        raise VerificationError("router oracle output hashes differ")

    policy = root["comparison_policy"]
    expected_policy = {
        "logits": {"absolute_tolerance": 5e-4, "relative_tolerance": 5e-4},
        "probabilities_and_weights": {"absolute_tolerance": 1e-6, "relative_tolerance": 1e-6},
        "non_finite_policy": "reject",
        "tie_rule": "probability_descending_then_expert_id_ascending",
        "real_rank_8_rank_9_tie": "stop",
    }
    if policy != expected_policy:
        raise VerificationError("router oracle comparison policy differs")
    numpy = _exact_mapping(
        result["numpy_cross_check"],
        {
            "passed", "compared_count", "mismatch_count", "first_mismatch",
            "absolute_tolerance", "relative_tolerance", "maximum_absolute_error",
            "maximum_relative_error", "numpy_logits_f32le_sha256",
        },
        subject="router oracle NumPy cross-check",
    )
    if (
        numpy.get("passed") is not True
        or numpy.get("compared_count") != 256
        or numpy.get("mismatch_count") != 0
        or numpy.get("first_mismatch") is not None
        or numpy.get("absolute_tolerance") != _round_f32(5e-4, subject="NumPy tolerance")
        or numpy.get("relative_tolerance") != _round_f32(5e-4, subject="NumPy tolerance")
        or not isinstance(numpy.get("numpy_logits_f32le_sha256"), str)
        or SHA256_RE.fullmatch(numpy["numpy_logits_f32le_sha256"]) is None
    ):
        raise VerificationError("router oracle NumPy cross-check differs")
    for name in ("maximum_absolute_error", "maximum_relative_error"):
        value = numpy.get(name)
        try:
            finite = math.isfinite(value)
        except (OverflowError, TypeError, ValueError):
            finite = False
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not finite
            or value < 0
        ):
            raise VerificationError("router oracle NumPy error metric differs")
    if root["unsupported_interpretations"] != REAL_ORACLE_UNSUPPORTED:
        raise VerificationError("router oracle redistribution scope differs")

    return {
        "passed": True,
        "row_count": 2,
        "expert_count": 128,
        "top_k": 8,
        "selected_expert_ids": selected_ids,
        "cutoff_ties": cutoff_ties,
        "scheduler_input_counts": [
            proof["scheduler_input_count"] for proof in proofs
        ],
        "input_sha256": _sha256(hidden_bytes),
        "tensor_sha256": tensor["encoded_sha256"],
        "output_sha256": expected_hashes["output_bundle_sha256"],
        "numpy_mismatch_count": numpy["mismatch_count"],
        "redistribution": "bounded_derived_values_only_no_model_weights",
    }


def _json_bytes(raw: bytes, *, subject: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise VerificationError(f"{subject} repeats a JSON field")
            value[key] = item
        return value

    def reject_constant(_: str) -> None:
        raise VerificationError(f"{subject} contains a non-finite number")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except VerificationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise VerificationError(f"{subject} is not bounded JSON") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{subject} root is not an object")
    return value


_POSIX_IDENTITY_FIELDS = {"device", "inode", "size_bytes", "sha256"}
_RAW_CAPTURE_FIELDS = {
    "source_revision",
    "capture_node",
    "shape",
    "dtype",
    "canonical_byte_length",
    "direct_token_ids",
    "positions",
    "context",
    "batch",
    "ubatch",
    "threads",
    "input_adapter",
    "tokenizer",
    "decode_status",
    "model_identity",
    "cancellation",
}
_RAW_CANCELLATION_FIELDS = {
    "backend",
    "scheduler_trace_format",
    "target",
    "target_ask_count",
    "target_observation_count",
    "target_complete",
    "callback_returned_false",
    "abort_guard_armed",
    "abort_callback_call_count",
    "abort_callback_calls_after_target",
    "abort_callback_true_count",
    "nodes_after_target",
}
_CAPTURE_PROVENANCE_FIELDS = {
    "schema",
    "schema_version",
    "binding_strategy",
    "admitted_model",
    "build",
    "consumers",
}
_CAPTURE_BUILD_FIELDS = {
    "attempt_scoped_fresh",
    "source_revision",
    "source_tree",
    "source_clean_before",
    "source_clean_after",
    "capture_source_repository_sha256",
    "capture_source_overlay_sha256",
    "cmake_lists_sha256",
    "cmake_cache_sha256",
    "configure_log_sha256",
    "build_log_sha256",
    "configure_command",
    "build_command",
    "tools",
    "helper",
}
_CAPTURE_CONSUMER_FIELDS = {
    "consumer_id",
    "model_before",
    "model_after",
    "helper_before",
    "helper_after",
}


def _closed_posix_identity(value: Any, *, subject: str) -> dict[str, Any]:
    return _exact_mapping(value, _POSIX_IDENTITY_FIELDS, subject=subject)


def _closed_capture_provenance(value: Any) -> dict[str, Any]:
    provenance = _exact_mapping(
        value,
        _CAPTURE_PROVENANCE_FIELDS,
        subject="oracle capture provenance",
    )
    _closed_posix_identity(
        provenance["admitted_model"],
        subject="oracle admitted model identity",
    )
    build = _exact_mapping(
        provenance["build"],
        _CAPTURE_BUILD_FIELDS,
        subject="oracle capture build provenance",
    )
    _closed_posix_identity(build["helper"], subject="oracle capture helper identity")
    tools = build["tools"]
    if not isinstance(tools, list) or len(tools) != 3:
        raise VerificationError("oracle capture build tools differ")
    for tool in tools:
        _exact_mapping(
            tool,
            {"name", "version", "executable_sha256"},
            subject="oracle capture build tool",
        )
    consumers = provenance["consumers"]
    if not isinstance(consumers, list) or len(consumers) != 2:
        raise VerificationError("oracle capture consumers differ")
    for consumer in consumers:
        proof = _exact_mapping(
            consumer,
            _CAPTURE_CONSUMER_FIELDS,
            subject="oracle capture consumer",
        )
        for name in ("model_before", "model_after", "helper_before", "helper_after"):
            _closed_posix_identity(
                proof[name],
                subject="oracle capture consumer file identity",
            )
    try:
        canonical = router_oracle.validate_capture_provenance(provenance)
    except router_oracle.RouterOracleError as error:
        raise VerificationError(
            f"router oracle capture provenance failed: {error.code}"
        ) from error
    if provenance != canonical:
        raise VerificationError("oracle capture provenance is not canonical")
    return canonical


def _verify_closed_oracle_bundle_json(documents: dict[str, dict[str, Any]]) -> None:
    manifest = _exact_mapping(
        documents["bundle-manifest.json"],
        {"schema", "schema_version", "complete", "publication", "attempts", "files"},
        subject="oracle candidate manifest",
    )
    attempts = manifest["attempts"]
    if not isinstance(attempts, list) or len(attempts) != 2:
        raise VerificationError("oracle candidate attempt inventory differs")
    for attempt in attempts:
        _exact_mapping(
            attempt,
            {"attempt_id", "capture", "record", "scheduler_trace"},
            subject="oracle candidate attempt",
        )
    files = manifest["files"]
    if not isinstance(files, list) or len(files) != 9:
        raise VerificationError("oracle candidate manifest inventory differs")
    for record in files:
        _exact_mapping(
            record,
            {"path", "byte_length", "sha256"},
            subject="oracle candidate file identity",
        )

    for name in ("capture-a.json", "capture-b.json"):
        capture = _exact_mapping(
            documents[name],
            _RAW_CAPTURE_FIELDS,
            subject="oracle raw capture record",
        )
        _exact_mapping(
            capture["model_identity"],
            {*_POSIX_IDENTITY_FIELDS, "pre_post_match"},
            subject="oracle raw capture model identity",
        )
        _exact_mapping(
            capture["cancellation"],
            _RAW_CANCELLATION_FIELDS,
            subject="oracle raw cancellation proof",
        )

    _closed_capture_provenance(documents["capture-provenance.json"])
    execution = _exact_mapping(
        documents["execution-provenance.json"],
        {
            "schema",
            "schema_version",
            "binding_strategy",
            "oracle_process_consumer",
            "oracle_source_sha256",
            "capture_provenance_sha256",
            "oracle_document_sha256",
        },
        subject="oracle execution provenance",
    )
    consumer = _exact_mapping(
        execution["oracle_process_consumer"],
        {"consumer_id", "model_before", "model_after"},
        subject="oracle process consumer",
    )
    _closed_posix_identity(
        consumer["model_before"],
        subject="oracle process model identity",
    )
    _closed_posix_identity(
        consumer["model_after"],
        subject="oracle process model identity",
    )


def verify_oracle_candidate_bundle(
    candidate_path: Path | str,
    *,
    expected_feature: str,
) -> dict[str, Any]:
    """Read-only cross-file and numerical verification for the CPU oracle bundle."""

    if expected_feature != "002-qwen-router-parity":
        raise VerificationError("oracle candidate feature identity differs")
    candidate = Path(candidate_path)
    if not candidate.is_absolute() or Path(os.path.normpath(str(candidate))) != candidate:
        raise VerificationError("oracle candidate path must be normalized and absolute")
    _reject_symlink_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        resolved.relative_to(repository)
    except ValueError:
        pass
    except OSError as error:
        raise VerificationError("oracle candidate is unavailable") from error
    else:
        raise VerificationError("oracle candidate must remain outside the repository")
    try:
        directory_before = resolved.lstat()
        if stat.S_ISLNK(directory_before.st_mode) or not stat.S_ISDIR(directory_before.st_mode):
            raise VerificationError("oracle candidate must be a real directory")
        entries = sorted(resolved.iterdir(), key=lambda item: item.name)
    except VerificationError:
        raise
    except OSError as error:
        raise VerificationError("oracle candidate cannot be inventoried") from error
    if frozenset(item.name for item in entries) != ORACLE_BUNDLE_FILES:
        raise VerificationError("oracle candidate artifact inventory differs")

    snapshot: dict[str, bytes] = {}
    metadata: dict[str, tuple[int, int, int, int]] = {}
    aggregate_bytes = 0
    for item in entries:
        try:
            before = item.lstat()
        except OSError as error:
            raise VerificationError("oracle candidate artifact is unavailable") from error
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise VerificationError("oracle candidate contains an unsafe artifact")
        maximum = 512 * 1024
        raw = _read_regular_bytes(
            item,
            maximum_bytes=maximum,
            subject="oracle candidate artifact",
        )
        if item.name in {"capture-a.f32le", "capture-b.f32le"} and len(raw) != 16_384:
            raise VerificationError("oracle capture byte length differs")
        aggregate_bytes += len(raw)
        if aggregate_bytes > 2 * 1024 * 1024:
            raise VerificationError("oracle candidate aggregate size exceeds its bound")
        snapshot[item.name] = raw
        metadata[item.name] = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )

    documents = {
        name: _json_bytes(raw, subject="oracle JSON artifact")
        for name, raw in snapshot.items()
        if name.endswith(".json")
    }
    _verify_closed_oracle_bundle_json(documents)
    manifest = documents["bundle-manifest.json"]
    expected_manifest_files = [
        {
            "path": name,
            "byte_length": len(snapshot[name]),
            "sha256": _sha256(snapshot[name]),
        }
        for name in (
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
    ]
    if manifest.get("files") != expected_manifest_files:
        raise VerificationError("oracle candidate manifest hashes differ")
    for name, raw in snapshot.items():
        if name.endswith(".json"):
            try:
                _reject_non_public_values(documents[name])
            except PublicationError as error:
                raise VerificationError("oracle candidate contains non-public data") from error
        elif name.endswith(".txt"):
            try:
                trace_text = raw.decode("utf-8")
                _reject_non_public_values({"scheduler_trace": trace_text})
                if router_oracle.canonical_scheduler_trace_bytes(trace_text) != raw:
                    raise VerificationError("oracle scheduler trace is not canonical")
            except router_oracle.RouterOracleError as error:
                raise VerificationError(
                    f"oracle scheduler trace failed: {error.code}"
                ) from error
            except (PublicationError, UnicodeError) as error:
                raise VerificationError("oracle candidate trace is not public-safe") from error

    try:
        router_oracle.validate_oracle_candidate_bundle(resolved)
    except router_oracle.RouterOracleError as error:
        raise VerificationError(f"oracle candidate producer proof failed: {error.code}") from error

    try:
        directory_after = resolved.lstat()
        if (
            directory_before.st_dev,
            directory_before.st_ino,
            directory_before.st_mtime_ns,
        ) != (
            directory_after.st_dev,
            directory_after.st_ino,
            directory_after.st_mtime_ns,
        ):
            raise VerificationError("oracle candidate directory changed during verification")
        for item in entries:
            after = item.lstat()
            if metadata[item.name] != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise VerificationError("oracle candidate artifact changed during verification")
    except VerificationError:
        raise
    except OSError as error:
        raise VerificationError("oracle candidate changed during verification") from error

    oracle_document = documents["oracle.json"]
    summary = verify_router_oracle_document(oracle_document)
    cancellation_proofs = oracle_document["capture"]["cancellation_proofs"]
    for index, attempt in enumerate(("a", "b")):
        trace_text = snapshot[f"capture-{attempt}.scheduler-trace.txt"].decode("utf-8")
        try:
            trace = router_oracle.validate_scheduler_debug_trace(trace_text)
        except router_oracle.RouterOracleError as error:
            raise VerificationError(
                f"oracle scheduler trace failed: {error.code}"
            ) from error
        for field, value in trace.items():
            if cancellation_proofs[index].get(field) != value:
                raise VerificationError("oracle scheduler trace binding differs")
    model_manifest, _ = _read_json_object(
        REPOSITORY_ROOT / "docs" / "research" / "MODEL_MANIFEST.json",
        maximum_bytes=MAX_DOCUMENT_BYTES,
        subject="model manifest",
    )
    try:
        model_identity = model_manifest["model_identity"]
        admission = model_manifest["router_tensor_admission"]
        observed = admission["observed"]
        model_license = model_identity["license"]
    except (KeyError, TypeError) as error:
        raise VerificationError("model redistribution identity is unavailable") from error
    if (
        model_manifest.get("feature_id") != expected_feature
        or model_manifest.get("status") != "sealed_read_only_inspection"
        or model_manifest.get("observed_feature_002_model_access") is not True
        or not isinstance(model_identity, dict)
        or model_identity.get("repository") != "Qwen/Qwen3-30B-A3B-GGUF"
        or model_identity.get("revision") != "e4d4bafdfb96a411a163846265362aceb0b9c63a"
        or model_identity.get("filename") != "Qwen3-30B-A3B-Q8_0.gguf"
        or model_identity.get("size_bytes") != 32_483_931_648
        or model_identity.get("sha256") != PINNED_MODEL_SHA256
        or model_license != "Apache-2.0"
        or model_identity.get("access_policy")
        != "caller_supplied_external_read_only_no_automatic_download"
        or model_identity.get("license_reference")
        != "docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json"
        or not isinstance(admission, dict)
        or admission.get("status") != "admitted_observed"
        or not isinstance(observed, dict)
        or observed.get("name") != "blk.0.ffn_gate_inp.weight"
        or observed.get("gguf_type") != "F32"
        or observed.get("gguf_dimensions") != [2048, 128]
        or observed.get("reader_shape") != [128, 2048]
        or observed.get("execution_shape") != [128, 2048]
        or observed.get("logical_element_count") != 262_144
        or observed.get("encoded_length_bytes") != 1_048_576
        or observed.get("orientation") != "expert_major_rows_input_columns"
        or observed.get("encoded_sha256") != PINNED_ROUTER_SHA256
        or observed.get("validation_status") != "passed"
    ):
        raise VerificationError("sealed model/tensor admission differs")

    candidate_material = b"".join(
        name.encode("utf-8") + b"\0" + snapshot[name]
        for name in sorted(snapshot)
    )
    return {
        **summary,
        "feature_id": expected_feature,
        "candidate_sha256": _sha256(candidate_material),
        "manifest_sha256": _sha256(snapshot["bundle-manifest.json"]),
        "oracle_document_sha256": _sha256(snapshot["oracle.json"]),
        "artifact_count": len(snapshot),
        "source_license": "MIT",
        "model_license": model_license,
        "publication_status": "eligible_for_sanitization_not_published",
    }


def _reject_symlink_components(path: Path) -> None:
    """Reject caller-controlled symlinks without rejecting macOS root aliases."""

    current = path.absolute()
    while True:
        is_macos_root_alias = (
            current.parent == Path("/") and current.name in {"var", "tmp", "etc"}
        )
        if current.is_symlink() and not is_macos_root_alias:
            raise VerificationError("publication package contains a symbolic link")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _read_regular_bytes(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> bytes:
    """Read one bounded regular file through a no-follow descriptor."""

    _reject_symlink_components(path)
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise VerificationError(f"{subject} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum_bytes:
            raise VerificationError(f"{subject} exceeds its size bound")

        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, min(64 * 1024, maximum_bytes + 1)):
            size += len(chunk)
            if size > maximum_bytes:
                raise VerificationError(f"{subject} exceeds its size bound")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or size != before.st_size:
            raise VerificationError(f"{subject} changed while it was read")
        return b"".join(chunks)
    except VerificationError:
        raise
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_bounded_text(path: Path, *, subject: str) -> str:
    raw = _read_regular_bytes(
        path,
        maximum_bytes=MAX_DOCUMENT_BYTES,
        subject=subject,
    )
    try:
        return raw.decode("utf-8")
    except UnicodeError as error:
        raise VerificationError(f"{subject} is not valid UTF-8") from error


def _verify_public_document(text: str, *, subject: str) -> None:
    try:
        _reject_non_public_values({"public_document": text})
    except PublicationError as error:
        raise VerificationError(
            f"{subject} contains forbidden private or secret content"
        ) from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("publication JSON contains a duplicate field")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise VerificationError("publication JSON contains a non-finite number")


def _read_json_object(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_bytes(path, maximum_bytes=maximum_bytes, subject=subject)
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except VerificationError:
        raise
    except (RecursionError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise VerificationError(f"{subject} contains invalid JSON") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{subject} root must be an object")
    return value, raw


def _resolved_repository_root() -> Path:
    try:
        root = REPOSITORY_ROOT.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("repository root is unavailable") from error
    if not root.is_dir():
        raise VerificationError("repository root is unavailable")
    return root


def _relative_to_root(path: Path, root: Path, *, subject: str) -> str:
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        raise VerificationError(f"{subject} escapes the repository") from error


def _resolve_repository_relative_file(value: str, *, subject: str) -> Path:
    """Resolve a strict repository-relative POSIX file path."""

    if (
        not value
        or "\x00" in value
        or "\\" in value
        or "?" in value
        or "#" in value
        or "%" in value
        or URI_SCHEME_RE.match(value)
    ):
        raise VerificationError(f"{subject} is not a package-relative path")
    lexical_parts = value.split("/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(
        part in {"", ".", ".."} for part in lexical_parts
    ):
        raise VerificationError(f"{subject} is not a package-relative path")

    root = _resolved_repository_root()
    candidate = REPOSITORY_ROOT.joinpath(*pure.parts)
    _reject_symlink_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise VerificationError(f"{subject} is unavailable or escapes the repository") from error
    try:
        mode = resolved.stat().st_mode
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    if not stat.S_ISREG(mode):
        raise VerificationError(f"{subject} must identify a regular file")
    return resolved


def _markdown_target(target: str) -> str:
    """Return an unambiguous Markdown link target without an optional title."""

    value = target.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if not value or any(character.isspace() for character in value):
        raise VerificationError("publication documentation has an ambiguous link")
    return value


def _resolve_markdown_file(
    target: str,
    *,
    document: Path,
    package_only: bool,
    subject: str,
) -> Path | None:
    """Resolve a local Markdown link with lexical and resolved containment."""

    value = _markdown_target(target)
    if URI_SCHEME_RE.match(value):
        if value.startswith(("https:", "http:")):
            return None
        raise VerificationError(f"{subject} uses an unsupported link scheme")
    if value.startswith("#"):
        return None
    if (
        "\x00" in value
        or "\\" in value
        or "?" in value
        or "#" in value
        or "%" in value
    ):
        raise VerificationError(f"{subject} is not a safe local link")
    lexical_parts = value.split("/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts:
        raise VerificationError(f"{subject} is not a safe local link")
    if any(part in {"", "."} for part in lexical_parts):
        raise VerificationError(f"{subject} is not a safe local link")
    if package_only and ".." in lexical_parts:
        raise VerificationError(f"{subject} is not package-relative")

    root = _resolved_repository_root()
    try:
        package_root = CLAIMS_LEDGER.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("publication package root is unavailable") from error
    candidate = document.parent.joinpath(*pure.parts)
    _reject_symlink_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(package_root if package_only else root)
    except (OSError, RuntimeError, ValueError) as error:
        raise VerificationError(f"{subject} is unavailable or escapes its package") from error
    try:
        mode = resolved.stat().st_mode
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    if not stat.S_ISREG(mode):
        raise VerificationError(f"{subject} must identify a regular file")
    return resolved


def _markdown_links(text: str) -> list[str]:
    links = MARKDOWN_LINK_RE.findall(text)
    if len(links) > MAX_MARKDOWN_LINKS:
        raise VerificationError("publication documentation contains too many links")
    return links


def _flat_files(directory: Path, *, subject: str) -> list[Path]:
    """Inventory a bounded flat publication directory without following links."""

    if directory.is_symlink():
        raise VerificationError(f"{subject} cannot be a symbolic link")
    if not directory.exists():
        return []
    _reject_symlink_components(directory)
    try:
        if not directory.is_dir():
            raise VerificationError(f"{subject} must be a directory")
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    if len(entries) > MAX_PACKAGE_FILES:
        raise VerificationError(f"{subject} contains too many entries")
    files: list[Path] = []
    for entry in entries:
        _reject_symlink_components(entry)
        try:
            mode = entry.stat().st_mode
        except OSError as error:
            raise VerificationError(f"{subject} contains an unavailable entry") from error
        if not stat.S_ISREG(mode):
            raise VerificationError(f"{subject} must contain only regular files")
        files.append(entry)
    return files


def _publication_raw_inventory(
    directory: Path,
) -> tuple[list[Path], list[Path]]:
    """Inventory flat experiments plus the one bounded oracle-support package."""

    if directory.is_symlink():
        raise VerificationError("raw evidence directory cannot be a symbolic link")
    support_paths = [
        REPOSITORY_ROOT / oracle_publication.FIXTURE_RECORD_RELATIVE,
        REPOSITORY_ROOT / oracle_publication.RAW_RECORD_RELATIVE,
        REPOSITORY_ROOT / oracle_publication.MANIFEST_RELATIVE,
    ]
    support_present = any(path.exists() or path.is_symlink() for path in support_paths)
    if not directory.exists():
        if support_present:
            raise VerificationError("oracle support package is incomplete")
        return [], []
    _reject_symlink_components(directory)
    try:
        if not directory.is_dir():
            raise VerificationError("raw evidence directory must be a directory")
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise VerificationError("raw evidence directory is unavailable") from error
    if len(entries) > MAX_PACKAGE_FILES:
        raise VerificationError("raw evidence directory contains too many entries")

    experiments: list[Path] = []
    oracle_directory: Path | None = None
    for entry in entries:
        _reject_symlink_components(entry)
        try:
            mode = entry.stat().st_mode
        except OSError as error:
            raise VerificationError(
                "raw evidence directory contains an unavailable entry"
            ) from error
        if stat.S_ISREG(mode):
            experiments.append(entry)
        elif stat.S_ISDIR(mode) and entry.name == "oracle":
            oracle_directory = entry
        else:
            raise VerificationError(
                "raw evidence directory contains an unsupported entry"
            )

    if support_present or oracle_directory is not None:
        try:
            oracle_publication.verify_committed_publication(REPOSITORY_ROOT)
        except oracle_publication.OraclePublicationError as error:
            raise VerificationError("oracle support package is invalid") from error
        return experiments, support_paths
    return experiments, []


def verify_candidate(
    candidate_path: Path | str,
    *,
    expected_feature: str,
) -> dict[str, Any]:
    """Verify one candidate without modifying it or creating sidecar state."""

    path = Path(candidate_path)
    try:
        record, raw = _read_candidate(path)
        sanitized = sanitize_candidate(record)
    except PublicationError as error:
        raise VerificationError(str(error)) from error
    if sanitized["feature_id"] != expected_feature:
        raise VerificationError("candidate feature identity does not match")

    sanitized_bytes = (
        json.dumps(sanitized, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return {
        "passed": True,
        "experiment_id": sanitized["experiment_id"],
        "feature_id": sanitized["feature_id"],
        "candidate_sha256": hashlib.sha256(raw).hexdigest(),
        "sanitized_sha256": hashlib.sha256(sanitized_bytes).hexdigest(),
        "full_schema": "evidence_schema" in sanitized,
    }


def verify_candidate_collection(
    candidate: Path | str,
    *,
    expected_feature: str,
) -> list[dict[str, Any]]:
    """Verify a candidate file or a flat append-only candidate directory."""

    path = Path(candidate)
    if path.is_symlink():
        raise VerificationError("candidate collection cannot be a symbolic link")
    if path.is_file():
        return [verify_candidate(path, expected_feature=expected_feature)]
    if not path.is_dir():
        raise VerificationError("candidate collection is unavailable")
    files = sorted(path.glob("*.json"))
    if not files:
        raise VerificationError("candidate collection contains no JSON records")

    results = [
        verify_candidate(item, expected_feature=expected_feature)
        for item in files
    ]
    identities = [result["experiment_id"] for result in results]
    if len(identities) != len(set(identities)):
        raise VerificationError("candidate collection repeats an experiment identity")
    for item, identity in zip(files, identities, strict=True):
        if item.stem != identity:
            raise VerificationError("candidate filename and experiment identity differ")
    return results


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify_deterministic_regeneration(raw_directory: Path | str) -> dict[str, Any]:
    """Regenerate tables and figures twice and compare every output byte."""

    raw_path = Path(raw_directory)
    with tempfile.TemporaryDirectory(prefix="pulsarmlx-verify-a-") as first_temp:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-verify-b-") as second_temp:
            first = Path(first_temp)
            second = Path(second_temp)
            try:
                generate_tables.generate_tables(raw_path, first / "tables")
                generate_figures.generate_figures(raw_path, first / "figures")
                generate_tables.generate_tables(raw_path, second / "tables")
                generate_figures.generate_figures(raw_path, second / "figures")
            except (generate_tables.GenerationError, generate_figures.GenerationError) as error:
                raise VerificationError("deterministic regeneration failed") from error
            first_files = _tree_bytes(first)
            second_files = _tree_bytes(second)
            if not first_files or first_files != second_files:
                raise VerificationError("generated package is not byte-for-byte deterministic")
            return {
                "artifact_count": len(first_files),
                "artifact_sha256": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in sorted(first_files.items())
                },
            }


def _load_publication_raw_records(
    raw_files: list[Path],
) -> tuple[dict[Path, dict[str, Any]], dict[str, str], list[str]]:
    """Validate committed raw records and derive their exact provenance sets."""

    root = _resolved_repository_root()
    records: dict[Path, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    commits: set[str] = set()
    experiment_ids: set[str] = set()
    for path in raw_files:
        if path.suffix != ".json":
            raise VerificationError("raw evidence directory contains a non-JSON file")
        record, raw = _read_json_object(
            path,
            maximum_bytes=MAX_RAW_BYTES,
            subject="raw evidence",
        )
        try:
            sanitized = sanitize_candidate(record)
        except PublicationError as error:
            raise VerificationError("published raw evidence is invalid") from error
        if sanitized.get("feature_id") != "002-qwen-router-parity":
            raise VerificationError("published raw evidence has the wrong feature identity")
        if "evidence_schema" not in sanitized:
            raise VerificationError("published raw evidence must use the full schema")
        experiment_id = record.get("experiment_id")
        if not isinstance(experiment_id, str) or path.name != f"{experiment_id}.json":
            raise VerificationError("raw filename and experiment identity differ")
        if experiment_id in experiment_ids:
            raise VerificationError("raw package repeats an experiment identity")
        experiment_ids.add(experiment_id)
        commit = record.get("source_commit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise VerificationError("raw evidence has an invalid source commit")
        resolved = path.resolve(strict=True)
        relative = _relative_to_root(resolved, root, subject="raw evidence")
        records[resolved] = sanitized
        sources[relative] = _sha256(raw)
        commits.add(commit)
    return records, dict(sorted(sources.items())), sorted(commits)


def _generator_contract(directory_name: str) -> tuple[Any, str, str]:
    if directory_name == "tables":
        module = generate_tables
    elif directory_name == "figures":
        module = generate_figures
    else:  # Defensive: callers pass only the two fixed publication directories.
        raise VerificationError("generated artifact directory is unsupported")
    generator = getattr(module, "GENERATOR_ID", None)
    command = getattr(module, "GENERATION_COMMAND", None)
    if not isinstance(generator, str) or not generator:
        raise VerificationError("generator identity is unavailable")
    if not isinstance(command, str) or not command:
        raise VerificationError("generator command identity is unavailable")
    return module, generator, command


def _verify_generated_directory(
    directory: Path,
    files: list[Path],
    *,
    expected_sources: dict[str, str],
    expected_commits: list[str],
) -> list[Path]:
    """Verify every output/sidecar pair against current source and generator bytes."""

    if directory.name == "tables":
        allowed_outputs = {".csv", ".md"}
        basename = getattr(generate_tables, "OUTPUT_BASENAME", None)
        expected_output_names = (
            {f"{basename}.csv", f"{basename}.md"}
            if isinstance(basename, str) and basename
            else set()
        )
    elif directory.name == "figures":
        allowed_outputs = {".svg"}
        output_name = getattr(generate_figures, "OUTPUT_NAME", None)
        expected_output_names = (
            {output_name} if isinstance(output_name, str) and output_name else set()
        )
    else:
        raise VerificationError("generated artifact directory is unsupported")

    outputs = [path for path in files if not path.name.endswith(".sources.json")]
    sidecars = [path for path in files if path.name.endswith(".sources.json")]
    if any(path.suffix not in allowed_outputs for path in outputs):
        raise VerificationError("generated artifact has an unsupported file type")
    if outputs and {path.name for path in outputs} != expected_output_names:
        raise VerificationError("generated artifact set does not match the current generator")
    expected_sidecars = {directory / f"{path.name}.sources.json" for path in outputs}
    if set(sidecars) != expected_sidecars:
        raise VerificationError("generated outputs and provenance sidecars are incomplete")

    module, generator_id, generation_command = _generator_contract(directory.name)
    generator_file_value = getattr(module, "__file__", None)
    if not isinstance(generator_file_value, str) or not generator_file_value:
        raise VerificationError("generator source file is unavailable")
    generator_bytes = _read_regular_bytes(
        Path(generator_file_value),
        maximum_bytes=MAX_GENERATED_BYTES,
        subject="generator source",
    )
    generator_sha256 = _sha256(generator_bytes)

    for output in outputs:
        output_bytes = _read_regular_bytes(
            output,
            maximum_bytes=MAX_GENERATED_BYTES,
            subject="generated output",
        )
        if directory.name == "figures":
            svg_bound = getattr(generate_figures, "MAX_SVG_BYTES", None)
            if not isinstance(svg_bound, int) or len(output_bytes) >= svg_bound:
                raise VerificationError("generated SVG exceeds the frozen size bound")
        sidecar_path = directory / f"{output.name}.sources.json"
        sidecar, sidecar_bytes = _read_json_object(
            sidecar_path,
            maximum_bytes=MAX_SIDECAR_BYTES,
            subject="generated provenance sidecar",
        )
        canonical = (
            json.dumps(sidecar, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if sidecar_bytes != canonical:
            raise VerificationError("generated provenance sidecar is not canonical JSON")
        if set(sidecar) != SIDECAR_FIELDS:
            raise VerificationError("generated provenance sidecar has an invalid shape")
        if (
            sidecar.get("schema_id") != "pulsarmlx.research.generated-sources"
            or sidecar.get("schema_version") != "1.0.0"
            or sidecar.get("generator") != generator_id
            or sidecar.get("generator_sha256") != generator_sha256
            or sidecar.get("generation_command") != generation_command
            or sidecar.get("output") != output.name
            or sidecar.get("output_sha256") != _sha256(output_bytes)
        ):
            raise VerificationError("generated provenance identity or hash is invalid")

        source_values = sidecar.get("sources")
        if not isinstance(source_values, dict) or any(
            not isinstance(path_value, str)
            or not isinstance(hash_value, str)
            or not SHA256_RE.fullmatch(hash_value)
            for path_value, hash_value in source_values.items()
        ):
            raise VerificationError("generated provenance sources are invalid")
        for source_path, source_hash in source_values.items():
            resolved = _resolve_repository_relative_file(
                source_path,
                subject="generated provenance source",
            )
            raw = _read_regular_bytes(
                resolved,
                maximum_bytes=MAX_RAW_BYTES,
                subject="generated provenance source",
            )
            if _sha256(raw) != source_hash:
                raise VerificationError("generated provenance source hash is stale")
        if source_values != expected_sources:
            raise VerificationError("generated provenance source set is incomplete")

        source_commits = sidecar.get("source_commits")
        if (
            not isinstance(source_commits, list)
            or any(
                not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit)
                for commit in source_commits
            )
            or source_commits != sorted(set(source_commits))
            or source_commits != expected_commits
        ):
            raise VerificationError("generated provenance commit set is invalid")
    return outputs


def _reviewer_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    positions: list[int] = []
    for heading in REVIEWER_SECTIONS:
        matches = [index for index, line in enumerate(lines) if line == heading]
        if len(matches) != 1:
            raise VerificationError("reviewer index is missing or repeats a required section")
        positions.append(matches[0])
    if positions != sorted(positions):
        raise VerificationError("reviewer index sections are out of order")
    sections: dict[str, str] = {}
    for index, heading in enumerate(REVIEWER_SECTIONS):
        end = positions[index + 1] if index + 1 < len(positions) else len(lines)
        sections[heading] = "\n".join(lines[positions[index] + 1 : end])
    return sections


def _resolved_section_links(section: str) -> list[Path]:
    links: list[Path] = []
    for target in _markdown_links(section):
        resolved = _resolve_markdown_file(
            target,
            document=REVIEWER_INDEX,
            package_only=False,
            subject="reviewer-index link",
        )
        if resolved is not None:
            links.append(resolved)
    return links


def _require_exact_reviewer_coverage(
    links: list[Path],
    expected: list[Path],
    *,
    subject: str,
) -> None:
    normalized = [path.resolve(strict=True) for path in links]
    for path in expected:
        count = normalized.count(path.resolve(strict=True))
        if count != 1:
            raise VerificationError(f"reviewer index does not uniquely name every {subject}")


def _split_markdown_row(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise VerificationError("claims ledger row is malformed")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    return cells


def _record_scopes(record: dict[str, Any]) -> set[str]:
    try:
        repository = record["model"]["repository"]
        revision = record["model"]["revision"]
        tensor = record["tensor"]["name"]
        depth = record["claim_boundary"]["operation"]
        summaries = record["summaries"]
    except (KeyError, TypeError) as error:
        raise VerificationError("linked evidence cannot establish exact claim scope") from error
    if any(not isinstance(value, str) or not value for value in (repository, revision, tensor, depth)):
        raise VerificationError("linked evidence has an invalid claim scope")
    case_ids: set[str] = set()
    if isinstance(summaries, list):
        for summary in summaries:
            if isinstance(summary, dict) and isinstance(summary.get("group"), dict):
                case_id = summary["group"].get("case_id")
                if isinstance(case_id, str) and case_id:
                    case_ids.add(case_id)
    if not case_ids:
        raise VerificationError("linked evidence has no exact case scope")
    return {
        ";".join(
            (
                f"checkpoint={repository}@{revision}",
                f"tensor={tensor}",
                f"case={case_id}",
                f"depth={depth}",
            )
        )
        for case_id in case_ids
    }


def _promotion_identity(record: dict[str, Any]) -> str:
    """Return the immutable identity that an independent reproduction must match."""

    try:
        identity = {
            "model": {
                key: record["model"][key]
                for key in ("repository", "revision", "filename", "sha256")
            },
            "tensor": {
                key: record["tensor"][key]
                for key in ("name", "encoded_sha256")
            },
            "input": {
                key: record["input"][key]
                for key in ("fixture_id", "canonical_sha256")
            },
            "oracle": {
                key: record["oracle"][key]
                for key in ("oracle_id", "input_fixture_sha256", "tensor_sha256", "output_sha256")
            },
            "output_sha256": record["correctness"]["repeat_output_hashes"][0],
        }
    except (IndexError, KeyError, TypeError) as error:
        raise VerificationError("linked evidence lacks promotion identity") from error
    return json.dumps(identity, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _verify_claim_promotion(records: list[dict[str, Any]]) -> None:
    """Require two clean, matching raw attempts before package-level promotion."""

    if len(records) < 2:
        raise VerificationError("verified claim lacks clean-checkout reproduction evidence")
    identities = {_promotion_identity(record) for record in records}
    experiment_ids = {record.get("experiment_id") for record in records}
    process_ids = {record.get("process_replication_id") for record in records}
    if len(identities) != 1 or len(experiment_ids) != len(records) or len(process_ids) < 2:
        raise VerificationError("verified claim reproduction identity is incomplete")
    for record in records:
        boundary = record.get("claim_boundary")
        correctness = record.get("correctness")
        unsupported = boundary.get("unsupported_interpretations") if isinstance(boundary, dict) else None
        if (
            record.get("actual_status") != "passed"
            or record.get("source_worktree_before") != "clean"
            or not isinstance(correctness, dict)
            or correctness.get("passed") is not True
            or not isinstance(boundary, dict)
            or boundary.get("status") != "provisional"
            or not isinstance(unsupported, list)
            or "real_checkpoint_routing" in unsupported
        ):
            raise VerificationError("verified claim is not supported by promotable evidence")


def _validate_claim_rows(
    claims_text: str,
    raw_records: dict[Path, dict[str, Any]],
) -> int:
    header = "| Claim | Evidence files | Commit | Scope | Status | Caveat |"
    lines = claims_text.splitlines()
    header_positions = [index for index, line in enumerate(lines) if line == header]
    if len(header_positions) != 1:
        raise VerificationError("claims ledger has an invalid table header")
    header_index = header_positions[0]
    if header_index + 1 >= len(lines):
        raise VerificationError("claims ledger has no table separator")
    separator = _split_markdown_row(lines[header_index + 1])
    if len(separator) != 6 or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        raise VerificationError("claims ledger has an invalid table separator")

    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if len(cells) != 6:
            raise VerificationError("claims ledger row has the wrong field count")
        rows.append(cells)
    if len(rows) > MAX_PACKAGE_FILES:
        raise VerificationError("claims ledger contains too many rows")

    claim_ids: set[str] = set()
    raw_root = (CLAIMS_LEDGER.parent / "raw" / "002-router-parity").resolve()
    for claim, evidence, commit, scope, status, caveat in rows:
        match = CLAIM_ID_RE.fullmatch(claim)
        if (
            match is None
            or not evidence
            or not COMMIT_RE.fullmatch(commit)
            or not scope
            or status not in {"verified", "provisional", "rejected", "unsupported"}
            or not caveat
        ):
            raise VerificationError("claims ledger row is incomplete or invalid")
        claim_id = match.group(1)
        if claim_id in claim_ids:
            raise VerificationError("claims ledger repeats a claim identity")
        claim_ids.add(claim_id)

        evidence_paths: list[Path] = []
        for target in _markdown_links(evidence):
            resolved = _resolve_markdown_file(
                target,
                document=CLAIMS_LEDGER,
                package_only=True,
                subject="claim evidence link",
            )
            if resolved is None:  # External links are not package evidence.
                raise VerificationError("claim evidence must be package-relative")
            evidence_paths.append(resolved)
        if not evidence_paths or len(evidence_paths) != len(set(evidence_paths)):
            raise VerificationError("claim evidence links are missing or duplicated")

        linked_records: list[dict[str, Any]] = []
        for path in evidence_paths:
            try:
                path.relative_to(raw_root)
            except ValueError:
                continue
            record = raw_records.get(path)
            if record is None:
                raise VerificationError("claim links unindexed raw evidence")
            linked_records.append(record)
        if not linked_records:
            raise VerificationError("claim has no linked machine-readable raw evidence")
        if any(record.get("source_commit") != commit for record in linked_records):
            raise VerificationError("claim commit does not match linked evidence")
        if any(scope not in _record_scopes(record) for record in linked_records):
            raise VerificationError("claim scope does not exactly match linked evidence")

        if status == "verified":
            _verify_claim_promotion(linked_records)
        elif status == "provisional":
            if any(
                record.get("actual_status") != "passed"
                or not isinstance(record.get("claim_boundary"), dict)
                or record["claim_boundary"].get("status") != "provisional"
                for record in linked_records
            ):
                raise VerificationError("provisional claim is not supported by passing evidence")
        elif status == "rejected" and all(
            record.get("actual_status") == "passed" for record in linked_records
        ):
            raise VerificationError("rejected claim does not link a failed outcome")
    return len(rows)


def verify_publication_index() -> dict[str, int]:
    """Verify bounded provenance, claim promotion, and reviewer completeness."""

    claims_text = _read_bounded_text(CLAIMS_LEDGER, subject="claims ledger")
    reviewer_text = _read_bounded_text(REVIEWER_INDEX, subject="reviewer index")
    _verify_public_document(claims_text, subject="claims ledger")
    _verify_public_document(reviewer_text, subject="reviewer index")
    research_root = CLAIMS_LEDGER.parent
    if REVIEWER_INDEX.parent.resolve(strict=True) != research_root.resolve(strict=True):
        raise VerificationError("publication index documents do not share a package root")

    raw_files, oracle_support_files = _publication_raw_inventory(
        research_root / "raw" / "002-router-parity"
    )
    table_files = _flat_files(research_root / "tables", subject="generated tables")
    figure_files = _flat_files(research_root / "figures", subject="generated figures")
    if (
        len(raw_files)
        + len(oracle_support_files)
        + len(table_files)
        + len(figure_files)
        > MAX_PACKAGE_FILES
    ):
        raise VerificationError("publication package contains too many files")
    if len(raw_files) > MAX_PUBLICATION_RAW_FILES:
        raise VerificationError("publication package contains too many raw records")
    try:
        package_bytes = sum(
            path.stat().st_size
            for path in (
                *raw_files,
                *oracle_support_files,
                *table_files,
                *figure_files,
            )
        )
    except OSError as error:
        raise VerificationError("publication package size cannot be inspected") from error
    if package_bytes > MAX_PACKAGE_BYTES:
        raise VerificationError("publication package exceeds the aggregate size bound")

    raw_records, expected_sources, expected_commits = _load_publication_raw_records(
        raw_files
    )
    table_outputs = _verify_generated_directory(
        research_root / "tables",
        table_files,
        expected_sources=expected_sources,
        expected_commits=expected_commits,
    )
    figure_outputs = _verify_generated_directory(
        research_root / "figures",
        figure_files,
        expected_sources=expected_sources,
        expected_commits=expected_commits,
    )
    if raw_files and (not table_outputs or not figure_outputs):
        raise VerificationError("published raw evidence lacks generated tables or figures")
    if (table_outputs or figure_outputs) and not raw_files:
        raise VerificationError("generated package has no raw evidence")

    sections = _reviewer_sections(reviewer_text)
    raw_links = _resolved_section_links(sections["## Raw evidence"])
    table_links = _resolved_section_links(sections["## Generated tables"])
    figure_links = _resolved_section_links(sections["## Generated figures"])
    claim_links = _resolved_section_links(sections["## Claims and reproduction links"])
    _require_exact_reviewer_coverage(
        raw_links,
        [*raw_files, *oracle_support_files],
        subject="raw/support artifact",
    )
    _require_exact_reviewer_coverage(table_links, table_files, subject="table artifact")
    _require_exact_reviewer_coverage(figure_links, figure_files, subject="figure artifact")
    _require_exact_reviewer_coverage(
        claim_links,
        [CLAIMS_LEDGER, research_root / "REPRODUCIBILITY.md"],
        subject="claim/reproduction document",
    )

    claim_count = _validate_claim_rows(claims_text, raw_records)
    return {"claim_count": claim_count}


def verify_committed_regeneration(raw_directory: Path | str) -> dict[str, Any]:
    """Require fresh deterministic outputs to equal every committed package byte."""

    regeneration = verify_deterministic_regeneration(raw_directory)
    research_root = CLAIMS_LEDGER.parent
    files = _flat_files(research_root / "tables", subject="generated tables")
    files.extend(
        _flat_files(research_root / "figures", subject="generated figures")
    )
    committed_hashes: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(research_root).as_posix()
        content = _read_regular_bytes(
            path,
            maximum_bytes=MAX_GENERATED_BYTES,
            subject="committed generated artifact",
        )
        committed_hashes[relative] = _sha256(content)
    if regeneration["artifact_sha256"] != dict(sorted(committed_hashes.items())):
        raise VerificationError(
            "committed generated artifacts differ from fresh regeneration"
        )
    return regeneration


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only verification of a bounded Feature 002 evidence package."
    )
    parser.add_argument("--feature", required=True)
    parser.add_argument(
        "--candidate",
        type=Path,
        help=(
            "Candidate JSON file or directory. If omitted, verify the committed "
            "raw directory for the requested feature."
        ),
    )
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help=(
            "Verify the committed model-free evidence fixture, regenerate its "
            "artifacts twice, and check publication index scaffolding."
        ),
    )
    parser.add_argument(
        "--oracle-candidate",
        type=Path,
        help=(
            "External complete CPU-oracle bundle to verify read-only. This mode "
            "does not publish or modify the candidate."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    selected_modes = sum(
        (
            arguments.fixture_only,
            arguments.candidate is not None,
            arguments.oracle_candidate is not None,
        )
    )
    if selected_modes > 1:
        print(
            "verification_error: explicit verification modes are mutually exclusive",
            file=os.sys.stderr,
        )
        return 2
    if arguments.oracle_candidate is not None:
        try:
            result = verify_oracle_candidate_bundle(
                arguments.oracle_candidate,
                expected_feature=arguments.feature,
            )
        except VerificationError as error:
            print(f"verification_error: {error}", file=os.sys.stderr)
            return 1
        except (
            OSError,
            OverflowError,
            RecursionError,
            TypeError,
            UnicodeError,
            ValueError,
            struct.error,
        ):
            print("verification_error: oracle candidate is malformed", file=os.sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "fixture_only": False,
                    "oracle_candidate": True,
                    "passed": True,
                    "record_count": 0,
                    "oracle": result,
                },
                sort_keys=True,
            )
        )
        return 0
    candidate = arguments.candidate
    complete_package = not arguments.fixture_only and candidate is None
    if arguments.fixture_only:
        candidate = FIXTURE_RAW_DIRECTORY
    elif candidate is None:
        candidate = Path("docs/research/raw") / arguments.feature.removeprefix("002-")
        if arguments.feature == "002-qwen-router-parity":
            candidate = Path("docs/research/raw/002-router-parity")
    try:
        results = verify_candidate_collection(
            candidate,
            expected_feature=arguments.feature,
        )
        regeneration: dict[str, Any] | None = None
        publication_index: dict[str, int] | None = None
        if arguments.fixture_only:
            if not results or any(not result["full_schema"] for result in results):
                raise VerificationError("fixture-only input is not full-schema evidence")
            regeneration = verify_deterministic_regeneration(candidate)
            publication_index = verify_publication_index()
        elif complete_package:
            publication_index = verify_publication_index()
            regeneration = verify_committed_regeneration(candidate)
    except VerificationError as error:
        print(f"verification_error: {error}", file=os.sys.stderr)
        return 1
    output: dict[str, Any] = {
        "fixture_only": arguments.fixture_only,
        "passed": True,
        "record_count": len(results),
        "records": results,
    }
    if regeneration is not None:
        output["regeneration"] = regeneration
    if publication_index is not None:
        output["publication_index"] = publication_index
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

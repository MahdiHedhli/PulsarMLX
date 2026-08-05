#!/usr/bin/env python3
"""Fail-closed validator for PulsarMLX research evidence version 1."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
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
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODEL_MANIFEST_PATH = "docs/research/MODEL_MANIFEST.json"
FROZEN_PROTOCOL_PATH = "docs/research/EXPERIMENT_PROTOCOL.md"
FROZEN_PROTOCOL_ID = "f002-router-protocol"
FROZEN_PROTOCOL_ORDER_SEED = 22_002
FROZEN_PROTOCOL_SHA256 = "6452f920102a87502143effa33b7a85911c931af93bc3a63b8a3007514ac1f0f"
FROZEN_MODEL_REVISION = "e4d4bafdfb96a411a163846265362aceb0b9c63a"
FROZEN_MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
FROZEN_LOGIT_ABSOLUTE_TOLERANCE = 5e-4
FROZEN_LOGIT_RELATIVE_TOLERANCE = 5e-4
PINNED_ORACLE_REVISION = "b06aa774c03dbbb624e726664b714a57d1f49815"
ROUTER_FIXTURE_MANIFEST_PATH = "fixtures/research/router-v1/manifest.json"
ROUTER_FIXTURE_MANIFEST_SHA256 = (
    "b953d9c1c86357612b757b41e22a33b80cdb5da412522ae4ca93508945ebc9ba"
)
MAX_MANIFEST_BYTES = 128 * 1024
MAX_LINKED_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_COUNT = 32
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PRIVATE_PATH_RE = re.compile(r"(?:^|[\s='\"])(?:/Users/|/home/|/private/var/|[A-Za-z]:\\Users\\)")
SECRET_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,})"
)

ROUTER_CAPABILITIES = {
    "router_logits",
    "router_full_softmax",
    "router_top8_selection",
    "router_selected_weight_normalization",
}
REQUIRED_UNSUPPORTED_INTERPRETATIONS = {
    "expert_execution",
    "routed_moe_aggregation",
    "complete_transformer_layer",
    "language_model_head_or_model_output_logits",
    "generation",
    "serving",
    "custom_metal",
    "complete_model_inference",
    "full_or_giant_model_inference",
    "projected_tokens_per_second",
    "linux_cuda_runtime_parity",
    # Stable v1 spellings retained for existing reviewers and artifacts.
    "full_model_generation",
    "token_throughput",
}


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
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        _fail("non_finite_value", "evidence contains a non-finite number")
    if not math.isfinite(result):
        _fail("non_finite_value", "evidence contains a non-finite number")
    return result


def _walk(value: Any) -> Iterable[Any]:
    """Iterate bounded JSON-like values without recursive Python calls."""

    pending: list[tuple[Any, int]] = [(value, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail("schema_violation", "evidence exceeds the structural bound")
        yield current
        if isinstance(current, dict):
            for key, child in reversed(tuple(current.items())):
                pending.append((child, depth + 1))
                pending.append((key, depth + 1))
        elif isinstance(current, list):
            for child in reversed(current):
                pending.append((child, depth + 1))


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


def _stable_id(value: Any) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        _fail("schema_violation", "a stable identity is invalid")
    return value


def _bounded_text(value: Any, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value:
        _fail("schema_violation", "a bounded text field is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        _fail("schema_violation", "a bounded text field is invalid")
    if len(encoded) > maximum:
        _fail("schema_violation", "a bounded text field is invalid")
    return value


def _repository_relative_parts(
    value: Any,
    *,
    allowed_prefixes: tuple[tuple[str, ...], ...],
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        _fail("semantic_relationship", "a repository artifact path is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        _fail("semantic_relationship", "a repository artifact path is invalid")
    if len(encoded) > 512:
        _fail("semantic_relationship", "a repository artifact path is invalid")
    if "\\" in value:
        _fail("semantic_relationship", "a repository artifact path is invalid")
    path = PurePosixPath(value)
    parts = path.parts
    canonical = PurePosixPath(*parts).as_posix() if parts else ""
    if (
        path.is_absolute()
        or not parts
        or canonical != value
        or any(part in {"", ".", ".."} for part in parts)
        or not any(parts[: len(prefix)] == prefix for prefix in allowed_prefixes)
    ):
        _fail("semantic_relationship", "a repository artifact path is invalid")
    return parts


def _read_repository_file(
    repository_root: Path,
    relative_path: Any,
    *,
    allowed_prefixes: tuple[tuple[str, ...], ...],
    maximum_bytes: int,
) -> tuple[bytes, str]:
    """Read and hash one bounded regular repository file without following links."""

    parts = _repository_relative_parts(
        relative_path,
        allowed_prefixes=allowed_prefixes,
    )
    try:
        root = repository_root.resolve(strict=True)
    except OSError:
        _fail("semantic_relationship", "the repository root is unavailable")

    candidate = root
    try:
        for part in parts:
            candidate = candidate / part
            if candidate.is_symlink():
                _fail("semantic_relationship", "a repository artifact link is unsafe")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        with resolved.open("rb") as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes:
                _fail("semantic_relationship", "a repository artifact is unsafe or oversized")
            digest = hashlib.sha256()
            chunks: list[bytes] = []
            total = 0
            while chunk := handle.read(64 * 1024):
                total += len(chunk)
                if total > maximum_bytes:
                    _fail(
                        "semantic_relationship",
                        "a repository artifact is unsafe or oversized",
                    )
                chunks.append(chunk)
                digest.update(chunk)
    except EvidenceValidationError:
        raise
    except (OSError, RuntimeError, ValueError):
        _fail("semantic_relationship", "a repository artifact is unavailable")
    return b"".join(chunks), digest.hexdigest()


def _hash_repository_file(
    repository_root: Path,
    relative_path: Any,
    *,
    allowed_prefixes: tuple[tuple[str, ...], ...],
    maximum_bytes: int,
) -> str:
    return _read_repository_file(
        repository_root,
        relative_path,
        allowed_prefixes=allowed_prefixes,
        maximum_bytes=maximum_bytes,
    )[1]


def _load_model_identity(repository_root: Path) -> dict[str, Any]:
    manifest_bytes, _ = _read_repository_file(
        repository_root,
        MODEL_MANIFEST_PATH,
        allowed_prefixes=(("docs", "research"),),
        maximum_bytes=MAX_MANIFEST_BYTES,
    )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail("semantic_relationship", "the frozen model manifest is invalid")
    if not isinstance(manifest, dict):
        _fail("semantic_relationship", "the frozen model manifest is invalid")
    if (
        manifest.get("manifest_schema") != "pulsarmlx.research.model-manifest"
        or manifest.get("manifest_schema_version") != SCHEMA_VERSION
        or manifest.get("feature_id") != FEATURE_ID
    ):
        _fail("semantic_relationship", "the frozen model manifest identity is invalid")
    identity = manifest.get("model_identity")
    if not isinstance(identity, dict):
        _fail("semantic_relationship", "the frozen model identity is unavailable")
    required = {
        "repository",
        "revision",
        "filename",
        "size_bytes",
        "sha256",
        "architecture",
        "external_locator",
    }
    if not required <= identity.keys():
        _fail("semantic_relationship", "the frozen model identity is incomplete")
    if (
        identity["repository"] != "Qwen/Qwen3-30B-A3B-GGUF"
        or identity["revision"] != FROZEN_MODEL_REVISION
        or identity["filename"] != "Qwen3-30B-A3B-Q8_0.gguf"
        or _plain_int(identity["size_bytes"], positive=True) != 32_483_931_648
        or identity["sha256"] != FROZEN_MODEL_SHA256
        or identity["architecture"] != "qwen3moe"
        or identity["external_locator"] != "$PULSARMLX_MODEL_GGUF"
    ):
        _fail("semantic_relationship", "the frozen model identity is invalid")
    return {field: identity[field] for field in required}


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
FAILURE_FIELDS = {"code", "message", "stage"}
ARTIFACT_FIELDS = {"kind", "path", "sha256"}


def _validate_schema_files(schema_dir: Path) -> None:
    if not schema_dir.is_dir() or schema_dir.is_symlink():
        _fail("schema_violation", "schema directory is unavailable")
    for name in ("experiment.schema.json", "router-parity.schema.json"):
        path = schema_dir / name
        if not path.is_file() or path.is_symlink():
            _fail("schema_violation", "a required schema is unavailable")
        try:
            with path.open("rb") as handle:
                metadata = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_size <= 0
                    or metadata.st_size > MAX_MANIFEST_BYTES
                ):
                    _fail("schema_violation", "a required schema is unsafe or oversized")
                raw = handle.read(MAX_MANIFEST_BYTES + 1)
            if len(raw) > MAX_MANIFEST_BYTES:
                _fail("schema_violation", "a required schema is unsafe or oversized")
            schema = json.loads(raw.decode("utf-8"))
        except EvidenceValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
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
    except (OverflowError, ValueError):
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
    if not isinstance(record["record_kind"], str) or record["record_kind"] not in {
        "correctness",
        "timing",
        "resource",
        "combined",
    }:
        _fail("schema_violation", "record kind is unsupported")
    if not isinstance(record["actual_status"], str) or record["actual_status"] not in {
        "passed",
        "failed",
        "aborted",
        "excluded",
    }:
        _fail("schema_violation", "actual status is unsupported")
    if not isinstance(record["warnings"], list) or not isinstance(record["failures"], list):
        _fail("schema_violation", "warning or failure collection is invalid")
    if not isinstance(record["artifacts"], list):
        _fail("schema_violation", "artifact collection is invalid")
    if not isinstance(record["source_worktree_before"], str):
        _fail("schema_violation", "source worktree state is invalid")

    for warning in record["warnings"]:
        _bounded_text(warning)
    for raw_failure in record["failures"]:
        failure = _closed_object(
            raw_failure,
            allowed=FAILURE_FIELDS,
            required={"code", "message"},
        )
        _stable_id(failure["code"])
        _bounded_text(failure["message"])
        if "stage" in failure:
            _bounded_text(failure["stage"], maximum=128)
    for raw_artifact in record["artifacts"]:
        artifact = _closed_object(raw_artifact, allowed=ARTIFACT_FIELDS)
        _bounded_text(artifact["kind"], maximum=128)
        if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(
            artifact["sha256"]
        ):
            _fail("schema_violation", "an artifact hash is invalid")

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


def _validate_semantics(record: dict[str, Any], repository_root: Path) -> None:
    source_commit = record["source_commit"]
    if not isinstance(source_commit, str) or not COMMIT_RE.fullmatch(source_commit):
        _fail("semantic_relationship", "source commit is not immutable")
    if _parse_utc(record["started_at_utc"]) > _parse_utc(record["completed_at_utc"]):
        _fail("semantic_relationship", "experiment timestamps are reversed")

    if not isinstance(record["source_worktree_before"], str) or record[
        "source_worktree_before"
    ] not in {"clean", "dirty", "unknown"}:
        _fail("semantic_relationship", "source worktree state is invalid")
    worktree_after = record["source_worktree_after"]
    if not isinstance(worktree_after["state"], str) or worktree_after["state"] not in {
        "clean",
        "declared_evidence_outputs_only",
        "dirty",
        "unknown",
    }:
        _fail("semantic_relationship", "post-run worktree state is invalid")
    paths = worktree_after["paths"]
    if not isinstance(paths, list) or len(paths) != len(set(map(str, paths))):
        _fail("schema_violation", "post-run worktree paths are invalid")
    for path in paths:
        _repository_relative_parts(
            path,
            allowed_prefixes=(("docs", "research"), ("fixtures", "research")),
        )
    if worktree_after["state"] == "clean" and paths:
        _fail("semantic_relationship", "post-run worktree paths contradict its state")
    if worktree_after["state"] == "declared_evidence_outputs_only" and not paths:
        _fail("semantic_relationship", "post-run worktree paths contradict its state")
    if worktree_after["state"] in {"dirty", "unknown"} and paths:
        _fail("semantic_relationship", "unreviewed worktree paths cannot be declared outputs")

    protocol = record["protocol"]
    if (
        protocol["protocol_id"] != FROZEN_PROTOCOL_ID
        or protocol["protocol_version"] != SCHEMA_VERSION
        or protocol["path"] != FROZEN_PROTOCOL_PATH
        or not isinstance(protocol["sha256"], str)
        or protocol["sha256"] != FROZEN_PROTOCOL_SHA256
        or _plain_int(protocol["order_seed"], nonnegative=True)
        != FROZEN_PROTOCOL_ORDER_SEED
    ):
        _fail("semantic_relationship", "protocol identity is invalid")
    actual_protocol_sha256 = _hash_repository_file(
        repository_root,
        protocol["path"],
        allowed_prefixes=(("docs", "research"),),
        maximum_bytes=MAX_LINKED_ARTIFACT_BYTES,
    )
    if actual_protocol_sha256 != FROZEN_PROTOCOL_SHA256:
        _fail("semantic_relationship", "protocol content identity does not match")

    execution = record["execution"]
    _plain_int(execution["exit_code"], nonnegative=True)
    if execution["working_directory_policy"] != "repository_root":
        _fail("semantic_relationship", "working-directory policy is invalid")

    model = record["model"]
    _plain_int(model["size_bytes"], positive=True)
    if not isinstance(model["sha256"], str) or not SHA256_RE.fullmatch(model["sha256"]):
        _fail("semantic_relationship", "model identity is invalid")
    frozen_model = _load_model_identity(repository_root)
    if any(model[field] != frozen_model[field] for field in frozen_model):
        _fail("semantic_relationship", "model identity does not match the frozen manifest")

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
    if (
        length != 1_048_576
        or end != offset + length
        or end > model["size_bytes"]
        or not isinstance(tensor["encoded_sha256"], str)
        or not SHA256_RE.fullmatch(tensor["encoded_sha256"])
    ):
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
        if not isinstance(oracle[name], str) or not SHA256_RE.fullmatch(oracle[name]):
            _fail("semantic_relationship", "oracle identity is invalid")
    if (
        oracle["oracle_id"] != "f002-scalar-f32-v1"
        or oracle["project"] != "llama.cpp-plus-standalone-scalar-oracle"
        or oracle["revision"] != PINNED_ORACLE_REVISION
        or "$PULSARMLX_ROUTER_FIXTURE" not in oracle["generation_command"]
        or not isinstance(oracle["independence_statement"], str)
        or "does not import or invoke mlx" not in oracle["independence_statement"].lower()
    ):
        _fail("semantic_relationship", "oracle identity is invalid")
    if oracle["input_fixture_sha256"] != fixture["canonical_sha256"]:
        _fail("semantic_relationship", "oracle input identity does not match")
    if oracle["tensor_sha256"] != tensor["encoded_sha256"]:
        _fail("semantic_relationship", "oracle tensor identity does not match")


def _is_fixture_scoped(record: dict[str, Any]) -> bool:
    experiment_id = record.get("experiment_id")
    tensor = record.get("tensor")
    artifacts = record.get("artifacts")
    return (
        isinstance(experiment_id, str)
        and experiment_id.startswith("f002-router-fixture-")
    ) or (
        isinstance(tensor, dict) and tensor.get("absolute_offset") == 0
    ) or (
        isinstance(artifacts, list)
        and any(
            isinstance(artifact, dict)
            and artifact.get("kind") == "router_fixture_manifest"
            and artifact.get("path") == ROUTER_FIXTURE_MANIFEST_PATH
            for artifact in artifacts
        )
    ) or any(
        "fixture-only" in warning.lower() or "synthetic fixture" in warning.lower()
        for warning in record["warnings"]
    )


def _validate_artifacts(record: dict[str, Any], repository_root: Path) -> None:
    artifacts = record["artifacts"]
    if not artifacts or len(artifacts) > MAX_ARTIFACT_COUNT:
        _fail("semantic_relationship", "evidence has no linked repository artifacts")
    paths: set[str] = set()
    protocol_links = 0
    router_fixture_links = 0
    for artifact in artifacts:
        path = artifact["path"]
        _repository_relative_parts(
            path,
            allowed_prefixes=(("docs", "research"), ("fixtures", "research")),
        )
        if path in paths:
            _fail("semantic_relationship", "an artifact path is linked more than once")
        paths.add(path)
        actual_sha256 = _hash_repository_file(
            repository_root,
            path,
            allowed_prefixes=(("docs", "research"), ("fixtures", "research")),
            maximum_bytes=MAX_LINKED_ARTIFACT_BYTES,
        )
        if artifact["sha256"] != actual_sha256:
            _fail("semantic_relationship", "an artifact content identity does not match")
        if artifact["kind"] == "frozen_protocol":
            if (
                path != FROZEN_PROTOCOL_PATH
                or artifact["sha256"] != FROZEN_PROTOCOL_SHA256
                or artifact["sha256"] != record["protocol"]["sha256"]
            ):
                _fail("semantic_relationship", "the protocol artifact identity does not match")
            protocol_links += 1
        if artifact["kind"] == "router_fixture_manifest":
            if (
                path != ROUTER_FIXTURE_MANIFEST_PATH
                or artifact["sha256"] != ROUTER_FIXTURE_MANIFEST_SHA256
            ):
                _fail("semantic_relationship", "the router fixture artifact identity does not match")
            router_fixture_links += 1
    if protocol_links != 1:
        _fail("semantic_relationship", "the frozen protocol artifact is not linked")
    if _is_fixture_scoped(record):
        if router_fixture_links != 1:
            _fail("semantic_relationship", "fixture evidence artifacts are incomplete")


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


def _validate_observations(
    record: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[tuple[Any, ...], list[int]]]:
    observations = record["raw_observations"]
    if not isinstance(observations, list) or not observations:
        _fail("schema_violation", "raw observations are missing")
    by_id: dict[str, dict[str, Any]] = {}
    compatible_series: dict[tuple[Any, ...], list[int]] = {}
    for observation in observations:
        item = _closed_object(
            observation,
            allowed=OBSERVATION_FIELDS,
            required=OBSERVATION_FIELDS - {"failure", "exclusion_rule_id"},
        )
        observation_id = _stable_id(item["observation_id"])
        if observation_id in by_id:
            _fail("duplicate_observation_id", "observation identity is duplicated")
        by_id[observation_id] = item
        run_index = _plain_int(item["run_index"], nonnegative=True)
        if item["batch_id"] != record["batch_id"]:
            _fail("semantic_relationship", "an observation batch identity does not match")
        for identity_field in ("batch_id", "case_id", "process_replication_id"):
            _stable_id(item[identity_field])
        if not isinstance(item["observation_kind"], str) or item["observation_kind"] not in {
            "warmup",
            "measurement",
            "clean_process_replication",
        }:
            _fail("schema_violation", "observation kind is invalid")
        if not isinstance(item["condition"], str) or item["condition"] not in {
            "warm",
            "first_read_new_process_os_cache_uncontrolled",
            "controlled_cold",
        }:
            _fail("schema_violation", "observation condition is invalid")
        if not isinstance(item["instrumentation_mode"], str) or item[
            "instrumentation_mode"
        ] not in {
            "minimally_instrumented",
            "stage_instrumented",
        }:
            _fail("schema_violation", "instrumentation mode is invalid")
        if not isinstance(item["process_state"], str) or item["process_state"] not in {
            "fresh_process",
            "reused_process",
        }:
            _fail("schema_violation", "process state is invalid")
        if not isinstance(item["requested_device"], str) or item[
            "requested_device"
        ] not in {"gpu", "not_applicable"}:
            _fail("schema_violation", "requested device is invalid")
        if not isinstance(item["selected_device"], str) or item[
            "selected_device"
        ] not in {"gpu", "not_available", "not_applicable"}:
            _fail("schema_violation", "selected device is invalid")
        if type(item["fallback_used"]) is not bool:
            _fail("schema_violation", "fallback state is invalid")
        if type(item["evaluated"]) is not bool or type(item["synchronized"]) is not bool:
            _fail("schema_violation", "evaluation state is invalid")
        if not isinstance(item["status"], str) or item["status"] not in {
            "passed",
            "failed",
            "aborted",
            "excluded",
        }:
            _fail("schema_violation", "observation status is invalid")
        if _parse_utc(item["started_at_utc"]) > _parse_utc(item["completed_at_utc"]):
            _fail("semantic_relationship", "observation timestamps are reversed")
        if item["monotonic_clock"] != "perf_counter_ns":
            _fail("semantic_relationship", "observation clock identity is invalid")
        if not isinstance(item["durations_ns"], dict) or not item["durations_ns"]:
            _fail("schema_violation", "duration map is invalid")
        if len(item["durations_ns"]) > 16:
            _fail("schema_violation", "duration map is invalid")
        for stage, duration in item["durations_ns"].items():
            _bounded_text(stage, maximum=128)
            _plain_int(duration, positive=True)
        if item["status"] == "passed":
            if (
                item["requested_device"] != "gpu"
                or item["selected_device"] != "gpu"
                or item["fallback_used"] is not False
                or item["evaluated"] is not True
                or item["synchronized"] is not True
                or item["correctness_passed"] is not True
                or not isinstance(item["output_sha256"], str)
                or not SHA256_RE.fullmatch(item["output_sha256"])
                or "failure" in item
                or "exclusion_rule_id" in item
            ):
                _fail("semantic_relationship", "successful observation metadata is inconsistent")
        elif item["status"] in {"failed", "aborted"}:
            if "failure" not in item or "exclusion_rule_id" in item:
                _fail("semantic_relationship", "unsuccessful observation metadata is incomplete")
            failure = _closed_object(
                item["failure"],
                allowed=FAILURE_FIELDS,
                required={"code", "message"},
            )
            _stable_id(failure["code"])
            _bounded_text(failure["message"])
            if "stage" in failure:
                _bounded_text(failure["stage"], maximum=128)
            pre_execution_failure = (
                item["selected_device"] in {"not_available", "not_applicable"}
                and item["fallback_used"] is False
                and item["evaluated"] is False
                and item["synchronized"] is False
                and item["output_sha256"] is None
                and item["correctness_passed"] is None
            )
            evaluated_failure = (
                item["status"] == "failed"
                and item["requested_device"] == "gpu"
                and item["selected_device"] == "gpu"
                and item["fallback_used"] is False
                and item["evaluated"] is True
                and item["synchronized"] is True
                and isinstance(item["output_sha256"], str)
                and SHA256_RE.fullmatch(item["output_sha256"]) is not None
                and item["correctness_passed"] is False
            )
            if not (pre_execution_failure or evaluated_failure):
                _fail("semantic_relationship", "unsuccessful observation metadata is inconsistent")
        else:
            # The frozen v1 protocol has retain-all semantics and declares no
            # exclusion rule. A later amendment needs a new protocol identity.
            _fail("semantic_relationship", "frozen protocol v1 declares no exclusion rule")

        series_key = (
            item["case_id"],
            item["batch_id"],
            item["process_replication_id"],
            item["observation_kind"],
            item["process_state"],
            item["condition"],
            item["instrumentation_mode"],
        )
        compatible_series.setdefault(series_key, []).append(run_index)

    return by_id, compatible_series


def _validate_contiguous_series(
    compatible_series: dict[tuple[Any, ...], list[int]],
) -> None:
    for indices in compatible_series.values():
        if sorted(indices) != list(range(len(indices))):
            _fail("semantic_relationship", "raw attempt indices are not contiguous")


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
    passed = [item for item in by_id.values() if item["status"] == "passed"]
    timing_series: dict[tuple[Any, ...], dict[str, list[dict[str, Any]]]] = {}
    for item in passed:
        base = (
            item["case_id"],
            item["batch_id"],
            item["process_replication_id"],
            item["process_state"],
            item["condition"],
            item["instrumentation_mode"],
        )
        timing_series.setdefault(base, {}).setdefault(item["observation_kind"], []).append(
            item
        )
    measurement_series = [
        (base, kinds)
        for base, kinds in timing_series.items()
        if kinds.get("measurement")
    ]
    if not measurement_series:
        _fail("insufficient_repetitions", "timing repetition policy is not met")
    for base, kinds in measurement_series:
        measurements = kinds["measurement"]
        warmups = kinds.get("warmup", [])
        condition = base[4]
        if len(measurements) < 10 or (condition == "warm" and len(warmups) < 5):
            _fail("insufficient_repetitions", "timing repetition policy is not met")
    if any(item["output_sha256"] != hashes[0] for item in passed):
        _fail("semantic_relationship", "raw and repeated output identities differ")


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


def _validate_summary_compatibility(
    record: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> None:
    """Reject known cross-group pooling before repetition-count diagnostics."""

    summaries = record["summaries"]
    if not isinstance(summaries, list):
        _fail("schema_violation", "statistical summaries are missing")
    for raw_summary in summaries:
        if not isinstance(raw_summary, dict) or not isinstance(raw_summary.get("group"), dict):
            continue
        group = raw_summary["group"]
        included_ids = raw_summary.get("included_observation_ids")
        if not isinstance(included_ids, list):
            continue
        for observation_id in included_ids:
            observation = by_id.get(observation_id) if isinstance(observation_id, str) else None
            if observation is None:
                continue
            for field in (
                "case_id",
                "batch_id",
                "observation_kind",
                "condition",
                "instrumentation_mode",
            ):
                if field in group and observation[field] != group[field]:
                    _fail(
                        "incompatible_summary_group",
                        "summary pools incompatible observations",
                    )


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
    summary_ids: set[str] = set()
    for raw_summary in summaries:
        summary = _closed_object(raw_summary, allowed=SUMMARY_FIELDS)
        group = _closed_object(summary["group"], allowed=GROUP_FIELDS)
        summary_id = _stable_id(summary["summary_id"])
        if summary_id in summary_ids:
            _fail("semantic_relationship", "summary identity is duplicated")
        summary_ids.add(summary_id)
        if summary["statistics_algorithm"] != "pulsarmlx-type7-v1":
            _fail("semantic_relationship", "statistics algorithm is invalid")
        included_ids = summary["included_observation_ids"]
        excluded_ids = summary["excluded_observation_ids"]
        if (
            not isinstance(included_ids, list)
            or not included_ids
            or any(not isinstance(value, str) for value in included_ids)
            or len(set(included_ids)) != len(included_ids)
        ):
            _fail("schema_violation", "included observation identities are invalid")
        if excluded_ids != []:
            _fail("semantic_relationship", "frozen protocol v1 declares no exclusion rule")
        if (
            group["batch_id"] != record["batch_id"]
            or group["observation_kind"]
            not in {"measurement", "clean_process_replication"}
            or group["condition"]
            not in {"warm", "first_read_new_process_os_cache_uncontrolled", "controlled_cold"}
            or group["instrumentation_mode"]
            not in {"minimally_instrumented", "stage_instrumented"}
        ):
            _fail("incompatible_summary_group", "summary group is invalid")
        _stable_id(group["case_id"])
        _stable_id(group["batch_id"])
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
            if observation["status"] != "passed":
                _fail("raw_summary_mismatch", "summary includes an unsuccessful observation")
            included.append(observation)
        replication_id = included[0]["process_replication_id"]
        if any(item["process_replication_id"] != replication_id for item in included):
            _fail("incompatible_summary_group", "summary pools process replications")
        process_state = included[0]["process_state"]
        if any(item["process_state"] != process_state for item in included):
            _fail("incompatible_summary_group", "summary pools process states")
        stage = group["stage"]
        if not isinstance(stage, str) or any(stage not in item["durations_ns"] for item in included):
            _fail("raw_summary_mismatch", "summary timing stage is unavailable")
        expected_ids = {
            item["observation_id"]
            for item in by_id.values()
            if item["status"] == "passed"
            and item["process_replication_id"] == replication_id
            and item["process_state"] == process_state
            and stage in item["durations_ns"]
            and all(
                item[field] == group[field]
                for field in (
                    "case_id",
                    "batch_id",
                    "observation_kind",
                    "condition",
                    "instrumentation_mode",
                )
            )
        }
        if set(included_ids) != expected_ids:
            _fail("raw_summary_mismatch", "summary omits compatible raw observations")
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
    if correctness["compared_count"] <= 0:
        _fail("semantic_relationship", "correctness compared count is invalid")
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
    maximum_absolute_error = _finite_number(correctness["maximum_absolute_error"])
    mean_absolute_error = _finite_number(correctness["mean_absolute_error"])
    rmse = _finite_number(correctness["rmse"])
    if (
        _finite_number(correctness["absolute_tolerance"])
        != FROZEN_LOGIT_ABSOLUTE_TOLERANCE
        or _finite_number(correctness["relative_tolerance"])
        != FROZEN_LOGIT_RELATIVE_TOLERANCE
    ):
        _fail("semantic_relationship", "correctness tolerances do not match protocol v1")
    if not (
        mean_absolute_error <= rmse + 1e-15
        and rmse <= maximum_absolute_error + 1e-15
    ):
        _fail("semantic_relationship", "correctness error metrics contradict each other")
    for field in (
        "id_mismatch_count",
        "order_mismatch_count",
        "numeric_mismatch_count",
        "non_finite_count",
    ):
        if correctness[field] > correctness["compared_count"]:
            _fail("semantic_relationship", "correctness mismatch count exceeds comparison count")
    if correctness["non_finite_policy"] != "reject":
        _fail("semantic_relationship", "non-finite policy is invalid")
    mismatch_count = sum(
        correctness[field]
        for field in (
            "id_mismatch_count",
            "order_mismatch_count",
            "numeric_mismatch_count",
            "non_finite_count",
        )
    )
    derived_passed = mismatch_count == 0
    if type(correctness["passed"]) is not bool or correctness["passed"] != derived_passed:
        _fail("semantic_relationship", "correctness pass state is not derived from mismatches")
    if derived_passed != (correctness["first_mismatch"] is None):
        _fail("semantic_relationship", "correctness mismatch detail is inconsistent")
    if correctness["first_mismatch"] is not None:
        if not isinstance(correctness["first_mismatch"], dict) or not correctness[
            "first_mismatch"
        ]:
            _fail("schema_violation", "correctness mismatch detail is invalid")


def _validate_claim_boundary(record: dict[str, Any]) -> None:
    boundary = record["claim_boundary"]
    capabilities = boundary["capabilities"]
    unsupported = boundary["unsupported_interpretations"]
    if (
        boundary["operation"] != "layer_0_router_only"
        or not isinstance(capabilities, list)
        or any(not isinstance(value, str) for value in capabilities)
        or len(set(capabilities)) != len(capabilities)
        or not set(capabilities) <= ROUTER_CAPABILITIES
        or not isinstance(unsupported, list)
        or any(not isinstance(value, str) for value in unsupported)
        or len(set(unsupported)) != len(unsupported)
        or not REQUIRED_UNSUPPORTED_INTERPRETATIONS <= set(unsupported)
        or not isinstance(boundary["status"], str)
        or boundary["status"] not in {"provisional", "verified", "failed", "blocked"}
    ):
        _fail("capability_overclaim", "claim exceeds the bounded router evidence")
    if set(capabilities) & set(unsupported):
        _fail("capability_overclaim", "supported and unsupported scopes overlap")
    fixture_scoped = _is_fixture_scoped(record)
    if fixture_scoped and "real_checkpoint_routing" not in unsupported:
        _fail("capability_overclaim", "fixture evidence does not exclude real checkpoint scope")
    if boundary["status"] == "verified":
        # The raw v1 schema has no closed field that can prove committed/indexed
        # evidence plus a clean-checkout reproduction. Package-level promotion
        # remains responsible for that proof; raw records stay provisional.
        _fail("capability_overclaim", "raw v1 evidence cannot prove verified promotion")


def _validate_outcome_state(
    record: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> None:
    actual_status = record["actual_status"]
    claim_status = record["claim_boundary"]["status"]
    exit_code = record["execution"]["exit_code"]
    observation_statuses = [item["status"] for item in by_id.values()]
    failure_codes = {failure["code"] for failure in record["failures"]}
    observation_failure_codes = {
        item["failure"]["code"]
        for item in by_id.values()
        if item["status"] in {"failed", "aborted"}
    }

    if actual_status == "excluded":
        _fail("semantic_relationship", "frozen protocol v1 declares no exclusion rule")
    if actual_status == "passed":
        if (
            exit_code != 0
            or record["correctness"]["passed"] is not True
            or record["failures"]
            or any(status != "passed" for status in observation_statuses)
            or claim_status not in {"provisional", "verified"}
        ):
            _fail("semantic_relationship", "passing experiment fields contradict each other")
        return

    expected_claim_status = "failed" if actual_status == "failed" else "blocked"
    if (
        actual_status not in {"failed", "aborted"}
        or exit_code == 0
        or not record["failures"]
        or actual_status not in observation_statuses
        or claim_status != expected_claim_status
        or failure_codes != observation_failure_codes
    ):
        _fail("semantic_relationship", "unsuccessful experiment fields contradict each other")


def validate_record(
    record: Any,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    try:
        if not isinstance(record, dict):
            _fail("schema_violation", "evidence root is not an object")
        _reject_non_finite_and_private_values(record)
        _validate_identity(record)
        _validate_structure(record)
        _validate_semantics(record, repository_root)
        _validate_artifacts(record, repository_root)
        by_id, compatible_series = _validate_observations(record)
        _validate_summary_compatibility(record, by_id)
        _validate_contiguous_series(compatible_series)
        _validate_repetitions(record, by_id)
        _validate_summaries(record, by_id)
        _validate_correctness(record)
        _validate_claim_boundary(record)
        _validate_outcome_state(record, by_id)
        return record
    except EvidenceValidationError:
        raise
    except (OSError, OverflowError, RecursionError, TypeError, UnicodeError, ValueError):
        _fail("schema_violation", "evidence contains an invalid scalar value")


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
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
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
    except RecursionError:
        print(
            "validation failed: schema_violation: evidence exceeds the structural bound",
            file=sys.stderr,
        )
        return 1
    except (OSError, OverflowError, TypeError, UnicodeError, ValueError):
        # The CLI is a publication boundary: malformed scalar values and file
        # races fail closed without a traceback or echoing the input path.
        print(
            "validation failed: schema_violation: evidence could not be validated",
            file=sys.stderr,
        )
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

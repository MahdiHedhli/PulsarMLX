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
from typing import Any, Iterable, Mapping


_STATISTICS_PATH = Path(__file__).with_name("statistics.py")
_STATISTICS_SPEC = importlib.util.spec_from_file_location(
    "pulsarmlx_research_statistics", _STATISTICS_PATH
)
if _STATISTICS_SPEC is None or _STATISTICS_SPEC.loader is None:
    raise RuntimeError("research statistics module is unavailable")
_STATISTICS_MODULE = importlib.util.module_from_spec(_STATISTICS_SPEC)
_STATISTICS_SPEC.loader.exec_module(_STATISTICS_MODULE)
summarize_nanoseconds = _STATISTICS_MODULE.summarize_nanoseconds
project_timing_rows = _STATISTICS_MODULE.project_timing_rows
group_raw_observations = _STATISTICS_MODULE.group_raw_observations

_ENVIRONMENT_PATH = Path(__file__).with_name("environment.py")
_ENVIRONMENT_SPEC = importlib.util.spec_from_file_location(
    "pulsarmlx_research_environment", _ENVIRONMENT_PATH
)
if _ENVIRONMENT_SPEC is None or _ENVIRONMENT_SPEC.loader is None:
    raise RuntimeError("research environment module is unavailable")
_ENVIRONMENT_MODULE = importlib.util.module_from_spec(_ENVIRONMENT_SPEC)
_ENVIRONMENT_SPEC.loader.exec_module(_ENVIRONMENT_MODULE)
snapshot_admission = _ENVIRONMENT_MODULE.snapshot_admission
combine_environment_evidence = _ENVIRONMENT_MODULE.combine_environment_evidence


EXPERIMENT_SCHEMA = "pulsarmlx.research.experiment"
ROUTER_SCHEMA = "pulsarmlx.research.router-parity"
EVIDENCE_SCHEMA_VERSION = "1.1.0"
PAYLOAD_SCHEMA_VERSION = "1.0.0"
MODEL_MANIFEST_SCHEMA_VERSION = "1.0.0"
ENVIRONMENT_SNAPSHOT_SCHEMA_VERSION = "1.0.0"
FEATURE_ID = "002-qwen-router-parity"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODEL_MANIFEST_PATH = "docs/research/MODEL_MANIFEST.json"
FROZEN_PROTOCOL_PATH = "docs/research/EXPERIMENT_PROTOCOL.md"
FROZEN_PROTOCOL_ID = "f002-router-protocol-amendment-001"
FROZEN_PROTOCOL_VERSION = "1.1.0"
FROZEN_PROTOCOL_ORDER_SEED = 22_002
FROZEN_PROTOCOL_SHA256 = "c4bc12eb294a5849cc1a88ec7e9820af5cd4387722536565697a30fdf8fe3863"
FROZEN_MODEL_REVISION = "e4d4bafdfb96a411a163846265362aceb0b9c63a"
FROZEN_MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
FROZEN_LOGIT_ABSOLUTE_TOLERANCE = 5e-4
FROZEN_LOGIT_RELATIVE_TOLERANCE = 5e-4
PINNED_ORACLE_REVISION = "b06aa774c03dbbb624e726664b714a57d1f49815"
REAL_ORACLE_ID = "qwen3moe-layer0-router-cpu-oracle-v1"
REAL_ORACLE_PROJECT = "llama.cpp-plus-standalone-scalar-oracle"
REAL_ORACLE_PUBLICATION_PATH = (
    "fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json"
)
REAL_ORACLE_PUBLICATION_SHA256 = (
    "3f570ce97f45902a1717d3770c6665d1023d8ccfc18266e25229bc1e86725133"
)
ROUTER_FIXTURE_MANIFEST_PATH = "fixtures/research/router-v1/manifest.json"
ROUTER_FIXTURE_MANIFEST_SHA256 = (
    "b953d9c1c86357612b757b41e22a33b80cdb5da412522ae4ca93508945ebc9ba"
)
MAX_MANIFEST_BYTES = 128 * 1024
MAX_LINKED_ARTIFACT_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_COUNT = 32
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64
MINIMUM_TOTAL_MEMORY_BYTES = 42_949_672_960
MINIMUM_AVAILABLE_STORAGE_BYTES = 134_761_081_856
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PRIVATE_PATH_RE = re.compile(
    r"(?:/"
    r"Users/|/"
    r"home/|/"
    r"Volumes/|/private/var/|/var/folders/|"
    r"[A-Za-z]:\\Users\\)"
)
SECRET_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,})"
)
UUID_RE = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])"
)
MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
IPV4_RE = re.compile(
    r"(?<![0-9])(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})"
    r"(?:\.(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}(?![0-9])"
)
HOSTNAME_RE = re.compile(r"(?i)\b[a-z0-9][a-z0-9-]{0,62}(?:\.[a-z0-9-]{1,63})*\.local\b")
EMAIL_RE = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@"
    r"[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![a-z0-9.-])"
)
FORBIDDEN_PUBLIC_FIELD_NAMES = {
    "account", "account_id", "account_identifier", "email", "email_address",
    "username", "user_name", "hostname", "host_name", "serial",
    "serial_number", "hardware_uuid", "volume_uuid", "mac_address",
    "ip_address", "home", "home_directory", "command_line",
    "process_command_line",
}

SAFE_ENVIRONMENT_SYMBOLS = {
    "PULSARMLX_MODEL_GGUF": "$PULSARMLX_MODEL_GGUF",
    "PULSARMLX_MODEL_STORAGE_ROOT": "$PULSARMLX_MODEL_STORAGE_ROOT",
    "PULSARMLX_ENVIRONMENT_EVIDENCE": "$PULSARMLX_ENVIRONMENT_EVIDENCE",
    "PULSARMLX_ROUTER_INSPECTION": "$PULSARMLX_ROUTER_INSPECTION",
    "PULSARMLX_ORACLE_WORK": "$PULSARMLX_ORACLE_WORK",
    "PULSARMLX_ORACLE_OUTPUT": "$PULSARMLX_ORACLE_OUTPUT",
    "PULSARMLX_ROUTER_ORACLE": "$PULSARMLX_ROUTER_ORACLE",
    "PULSARMLX_ROUTER_EVIDENCE": "$PULSARMLX_ROUTER_EVIDENCE",
    "PULSARMLX_ROUTER_FIXTURE_EVIDENCE": "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE",
}
SECRET_ENVIRONMENT_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "AUTH", "COOKIE", "KEY")
ENVIRONMENT_OBSERVATION_FIELDS = {
    "repository_commit",
    "worktree_dirty",
    "captured_at_utc",
    "python_version",
    "mlx_version",
    "rust_version",
    "cargo_version",
    "worker_protocol_version",
    "pulsarmlx_version",
    "macos_product_version",
    "macos_build",
    "shell_architecture",
    "chip_model",
    "unified_memory_bytes",
    "physical_cpu_count",
    "logical_cpu_count",
    "filesystem_type",
    "available_storage_bytes",
    "storage_rounding_bytes",
    "memory_pressure",
    "power_mode",
    "thermal_state",
    "collector_process_resident_bytes",
    "collector_peak_resident_bytes",
    "collector_process_cpu_time_seconds",
    "collector_process_bytes_read",
    "load_average_1m",
    "load_average_5m",
    "load_average_15m",
    "workload_category",
    "material_concurrent_workload",
    "benchmark_concurrency",
    "capture_wall_time_ns",
}
ENVIRONMENT_SNAPSHOT_FIELDS = {
    "snapshot_schema", "snapshot_schema_version", "capture_phase", "platform",
    "requested_backend", "requested_device", "storage_role", "storage_locator",
    "safe_environment", "interference_admission", "admission_reasons", "observations",
}
BENCHMARK_RESOURCE_FIELDS = {
    "process_footprint_bytes", "mlx_active_memory_bytes",
    "mlx_cache_memory_bytes", "mlx_peak_memory_bytes",
    "process_cpu_time_seconds", "process_bytes_read",
    "worker_backend", "worker_requested_device", "worker_selected_device",
    "worker_fallback_used", "worker_evaluated", "worker_synchronized",
}
SECOND_BATCH_CASE_ORDER = (
    "qwen3moe-layer0-router-token0-row0-v1",
    "qwen3moe-layer0-router-token0-token1-batch-v1",
)
FIRST_PROCESS_CONDITIONS = frozenset(
    {
        "first_read_new_process_os_cache_uncontrolled",
        "controlled_cold",
    }
)
FIRST_PROCESS_COHORT_SIZE = 10
SECOND_BATCH_ENVIRONMENT_OBSERVATIONS = (
    "repository_commit",
    "worktree_dirty",
    "python_version",
    "mlx_version",
    "rust_version",
    "cargo_version",
    "worker_protocol_version",
    "pulsarmlx_version",
    "macos_product_version",
    "macos_build",
    "shell_architecture",
    "chip_model",
    "unified_memory_bytes",
    "physical_cpu_count",
    "logical_cpu_count",
    "filesystem_type",
    "memory_pressure",
    "power_mode",
    "thermal_state",
    "load_average_1m",
    "load_average_5m",
    "load_average_15m",
    "workload_category",
    "material_concurrent_workload",
    "benchmark_concurrency",
)
SECOND_BATCH_WORKER_FACTS = (
    "worker_backend",
    "worker_requested_device",
    "worker_selected_device",
    "worker_fallback_used",
    "worker_evaluated",
    "worker_synchronized",
)

# These names are shared by the Python worker and Rust orchestration boundary.
# External-checkpoint evidence is fail-closed to this vocabulary; synthetic
# fixture records retain their legacy integer-stage compatibility so older
# redistributable contract fixtures remain replayable.
ROUTER_TIMING_STAGES = {
    "setup_admission",
    "file_io",
    "storage_validation_f32_decode",
    "dequantization",
    "host_to_device",
    "graph_construction",
    "compilation",
    "router_projection",
    "top_k",
    "normalization",
    "total_evaluated_router",
    "synchronized_readback",
    "end_to_end_router_command",
}
ROUTER_F32_DEQUANTIZATION_REASON = "f32_router_requires_no_dequantization"

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
            if (
                value.lower() in FORBIDDEN_PUBLIC_FIELD_NAMES
                or PRIVATE_PATH_RE.search(value)
                or SECRET_RE.search(value)
                or UUID_RE.search(value)
                or MAC_RE.search(value)
                or IPV4_RE.search(value)
                or HOSTNAME_RE.search(value)
                or EMAIL_RE.search(value)
                or value.startswith("~/")
            ):
                _fail("private_value", "evidence contains a forbidden private value")
            if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
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


def _validate_public_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("schema_violation", "a public environment observation is invalid")
    status = value.get("status")
    if status == "observed":
        item = _closed_object(value, allowed={"status", "value", "source"})
        observation_value = item["value"]
        if isinstance(observation_value, bool):
            pass
        elif type(observation_value) is int:
            pass
        elif isinstance(observation_value, float):
            _finite_number(observation_value)
        elif isinstance(observation_value, str):
            _bounded_text(observation_value, maximum=256)
        else:
            _fail("schema_violation", "an observed environment value has the wrong type")
        _bounded_text(item["source"], maximum=128)
        return item
    if status == "unavailable":
        item = _closed_object(
            value,
            allowed={"status", "reason", "attempted_method"},
        )
        _bounded_text(item["reason"], maximum=256)
        _bounded_text(item["attempted_method"], maximum=256)
        return item
    _fail("schema_violation", "a public environment observation status is invalid")


def _validate_safe_environment(value: Any) -> dict[str, Any]:
    safe_environment = _closed_object(
        value,
        allowed=set(SAFE_ENVIRONMENT_SYMBOLS),
        required={"PULSARMLX_MODEL_GGUF"},
    )
    for key, symbolic_value in safe_environment.items():
        if any(marker in key.upper() for marker in SECRET_ENVIRONMENT_MARKERS):
            _fail("private_value", "a secret-shaped environment key is forbidden")
        if symbolic_value != SAFE_ENVIRONMENT_SYMBOLS[key]:
            _fail("private_value", "an environment value is not symbolic")
    return safe_environment


def _validate_environment_snapshot_structure(value: Any) -> dict[str, Any]:
    snapshot = _closed_object(value, allowed=ENVIRONMENT_SNAPSHOT_FIELDS)
    _validate_safe_environment(snapshot["safe_environment"])
    reasons = snapshot["admission_reasons"]
    if (
        not isinstance(reasons, list)
        or len(reasons) > 16
        or len(set(map(str, reasons))) != len(reasons)
    ):
        _fail("schema_violation", "environment admission reasons are invalid")
    for reason in reasons:
        _stable_id(reason)
    observations = _closed_object(
        snapshot["observations"],
        allowed=ENVIRONMENT_OBSERVATION_FIELDS,
    )
    for observation in observations.values():
        _validate_public_observation(observation)
    return snapshot


def _validate_benchmark_resources_structure(value: Any) -> dict[str, Any]:
    resources = _closed_object(value, allowed=BENCHMARK_RESOURCE_FIELDS)
    for observation in resources.values():
        _validate_public_observation(observation)
    return resources


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


def _load_model_manifest(repository_root: Path) -> dict[str, Any]:
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
        or manifest.get("manifest_schema_version") != MODEL_MANIFEST_SCHEMA_VERSION
        or manifest.get("feature_id") != FEATURE_ID
    ):
        _fail("semantic_relationship", "the frozen model manifest identity is invalid")
    return manifest


def _load_model_identity(repository_root: Path) -> dict[str, Any]:
    manifest = _load_model_manifest(repository_root)
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


def _load_real_oracle_identity(repository_root: Path) -> dict[str, Any]:
    """Project the immutable public oracle into the experiment identity shape."""

    publication_bytes, publication_sha256 = _read_repository_file(
        repository_root,
        REAL_ORACLE_PUBLICATION_PATH,
        allowed_prefixes=(("fixtures", "research"),),
        maximum_bytes=MAX_LINKED_ARTIFACT_BYTES,
    )
    if publication_sha256 != REAL_ORACLE_PUBLICATION_SHA256:
        _fail("semantic_relationship", "the frozen real oracle publication changed")
    try:
        publication = json.loads(publication_bytes.decode("utf-8"))
        source = publication["source"]
        generator = publication["generator"]
        fixture = publication["input"]
        tensor = publication["tensor"]
        result_hashes = publication["result"]["hashes"]
        identity = {
            "oracle_id": REAL_ORACLE_ID,
            "project": REAL_ORACLE_PROJECT,
            "revision": source["revision"],
            "generation_command": generator["generation_command"],
            "input_fixture_sha256": fixture["canonical_f32le_sha256"],
            "tensor_sha256": tensor["encoded_sha256"],
            "output_sha256": result_hashes["output_bundle_sha256"],
            "independence_statement": generator["independence"],
        }
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail("semantic_relationship", "the frozen real oracle publication is invalid")
    if (
        not isinstance(publication, dict)
        or publication.get("schema") != "pulsarmlx.research.router-oracle-publication"
        or publication.get("schema_version") != "1.0.0"
        or publication.get("publication_id") != "f002-router-oracle-freeze-0001"
        or publication.get("feature_id") != FEATURE_ID
        or publication.get("status") != "passed"
        or identity["revision"] != PINNED_ORACLE_REVISION
        or any(
            not isinstance(identity[name], str) or not SHA256_RE.fullmatch(identity[name])
            for name in ("input_fixture_sha256", "tensor_sha256", "output_sha256")
        )
        or any(
            not isinstance(identity[name], str) or not identity[name]
            for name in ("generation_command", "independence_statement")
        )
    ):
        _fail("semantic_relationship", "the frozen real oracle publication is invalid")
    return identity


TOP_LEVEL_FIELDS = {
    "evidence_schema",
    "evidence_schema_version",
    "payload_schema",
    "payload_schema_version",
    "experiment_id",
    "feature_id",
    "evidence_scope",
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
    "second_batch",
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
        EVIDENCE_SCHEMA_VERSION,
        ROUTER_SCHEMA,
        PAYLOAD_SCHEMA_VERSION,
    ):
        _fail("unsupported_schema_identity", "evidence schema identity is unsupported")


def _validate_structure(record: dict[str, Any]) -> None:
    _closed_object(
        record,
        allowed=TOP_LEVEL_FIELDS,
        required=TOP_LEVEL_FIELDS - {"second_batch", "evidence_scope"},
    )
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
        "blocked",
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
    if "second_batch" in record:
        second_batch = record["second_batch"]
        if not isinstance(second_batch, dict):
            _fail("schema_violation", "second-batch evidence has the wrong type")
        if second_batch.get("status") == "observed":
            observed = _closed_object(
                second_batch,
                allowed={
                    "status",
                    "between_batch_variation_measured",
                    "linked_experiment_id",
                    "linked_batch_id",
                    "linked_record_sha256",
                },
            )
            _stable_id(observed["linked_experiment_id"])
            _stable_id(observed["linked_batch_id"])
            linked_hash = observed["linked_record_sha256"]
            if not isinstance(linked_hash, str) or not SHA256_RE.fullmatch(linked_hash):
                _fail("schema_violation", "a linked second-batch hash is invalid")
        elif second_batch.get("status") == "unavailable":
            unavailable = _closed_object(
                second_batch,
                allowed={"status", "reason", "between_batch_variation_measured"},
                required={"status", "between_batch_variation_measured"},
            )
            if "reason" in unavailable:
                _bounded_text(unavailable["reason"])
        else:
            _fail("schema_violation", "second-batch status is invalid")
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
    environment = _closed_object(
        record["environment"],
        allowed={
            "platform",
            "selected_backend",
            "selected_device",
            "safe_environment",
            "interference_admission",
            "interference_reasons",
            "before_snapshot",
            "after_snapshot",
            "benchmark_resources",
        },
        required={
            "platform",
            "selected_backend",
            "selected_device",
            "safe_environment",
            "interference_admission",
        },
    )
    _validate_safe_environment(environment["safe_environment"])
    paired_fields = {
        "interference_reasons",
        "before_snapshot",
        "after_snapshot",
        "benchmark_resources",
    }
    paired_fields_present = paired_fields & environment.keys()
    if paired_fields_present and paired_fields_present != paired_fields:
        _fail("schema_violation", "paired environment evidence is incomplete")
    if paired_fields_present:
        reasons = environment["interference_reasons"]
        if (
            not isinstance(reasons, list)
            or len(reasons) > 32
            or len(set(map(str, reasons))) != len(reasons)
        ):
            _fail("schema_violation", "environment interference reasons are invalid")
        for reason in reasons:
            _stable_id(reason)
        _validate_environment_snapshot_structure(environment["before_snapshot"])
        after_snapshot = environment["after_snapshot"]
        if isinstance(after_snapshot, dict) and after_snapshot.get("status") == "unavailable":
            unavailable_after = _closed_object(
                after_snapshot,
                allowed={"status", "reason", "attempted_method"},
            )
            _bounded_text(unavailable_after["reason"], maximum=256)
            _bounded_text(unavailable_after["attempted_method"], maximum=256)
        else:
            _validate_environment_snapshot_structure(after_snapshot)
        _validate_benchmark_resources_structure(environment["benchmark_resources"])
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


def _environment_observed_value(
    observations: Mapping[str, Any],
    name: str,
) -> Any | None:
    observation = observations[name]
    return observation.get("value") if observation.get("status") == "observed" else None


def _validate_environment_snapshot_semantics(
    record: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    phase: str,
) -> None:
    if (
        snapshot["snapshot_schema"] != "pulsarmlx.research.environment"
        or snapshot["snapshot_schema_version"] != ENVIRONMENT_SNAPSHOT_SCHEMA_VERSION
        or snapshot["capture_phase"] != phase
        or snapshot["platform"] != "macos-arm64"
        or snapshot["requested_backend"] != "apple-mlx"
        or snapshot["requested_device"] != "gpu"
    ):
        _fail("semantic_relationship", "environment snapshot identity is invalid")
    role_to_locator = {
        "repository_storage": "$PULSARMLX_REPOSITORY_ROOT",
        "model_storage": "$PULSARMLX_MODEL_STORAGE_ROOT",
        "oracle_work_storage": "$PULSARMLX_ORACLE_WORK",
        "candidate_evidence_storage": "$PULSARMLX_ROUTER_EVIDENCE",
    }
    if role_to_locator.get(snapshot["storage_role"]) != snapshot["storage_locator"]:
        _fail("semantic_relationship", "environment storage role is invalid")

    observations = snapshot["observations"]
    commit = _environment_observed_value(observations, "repository_commit")
    pulsarmlx_version = _environment_observed_value(observations, "pulsarmlx_version")
    dirty = _environment_observed_value(observations, "worktree_dirty")
    captured_at = _environment_observed_value(observations, "captured_at_utc")
    architecture = _environment_observed_value(observations, "shell_architecture")
    if commit != record["source_commit"] or pulsarmlx_version != commit:
        _fail("semantic_relationship", "environment source identity does not match")
    if type(dirty) is not bool:
        _fail("schema_violation", "environment worktree state is invalid")
    _parse_utc(captured_at)
    if architecture != "arm64":
        _fail("semantic_relationship", "environment architecture is not arm64")

    for name in (
        "python_version", "mlx_version", "rust_version", "cargo_version",
        "worker_protocol_version", "macos_product_version", "macos_build",
        "chip_model", "filesystem_type",
    ):
        value = _environment_observed_value(observations, name)
        if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
            _fail("schema_violation", "environment string observation is invalid")
    if _environment_observed_value(observations, "worker_protocol_version") != "1":
        _fail("semantic_relationship", "worker protocol version is invalid")

    positive_integer_fields = (
        "unified_memory_bytes", "physical_cpu_count", "logical_cpu_count",
        "available_storage_bytes", "storage_rounding_bytes",
        "collector_process_resident_bytes", "collector_peak_resident_bytes",
        "benchmark_concurrency", "capture_wall_time_ns",
    )
    for name in positive_integer_fields:
        value = _environment_observed_value(observations, name)
        if value is not None:
            _plain_int(value, positive=True)
    physical = _environment_observed_value(observations, "physical_cpu_count")
    logical = _environment_observed_value(observations, "logical_cpu_count")
    if isinstance(physical, int) and isinstance(logical, int) and logical < physical:
        _fail("semantic_relationship", "environment CPU counts are inconsistent")
    resident = _environment_observed_value(observations, "collector_process_resident_bytes")
    peak = _environment_observed_value(observations, "collector_peak_resident_bytes")
    if isinstance(resident, int) and isinstance(peak, int) and peak < resident:
        _fail("semantic_relationship", "collector memory gauges are inconsistent")

    for name in (
        "collector_process_cpu_time_seconds", "load_average_1m",
        "load_average_5m", "load_average_15m",
    ):
        value = _environment_observed_value(observations, name)
        if value is not None and _finite_number(value) < 0:
            _fail("semantic_relationship", "environment numeric observation is negative")
    bytes_read = _environment_observed_value(observations, "collector_process_bytes_read")
    if bytes_read is not None:
        _plain_int(bytes_read, nonnegative=True)

    storage_rounding = _environment_observed_value(observations, "storage_rounding_bytes")
    if storage_rounding is not None and storage_rounding != 1_073_741_824:
        _fail("semantic_relationship", "environment storage rounding is invalid")
    pressure = _environment_observed_value(observations, "memory_pressure")
    power = _environment_observed_value(observations, "power_mode")
    thermal = _environment_observed_value(observations, "thermal_state")
    workload = _environment_observed_value(observations, "workload_category")
    material_workload = _environment_observed_value(
        observations, "material_concurrent_workload"
    )
    if pressure is not None and pressure not in {"normal", "warning", "critical"}:
        _fail("semantic_relationship", "environment memory pressure is invalid")
    if power is not None and power not in {"automatic", "low_power"}:
        _fail("semantic_relationship", "environment power mode is invalid")
    if thermal is not None and thermal not in {"nominal", "warning", "serious", "critical"}:
        _fail("semantic_relationship", "environment thermal state is invalid")
    if workload not in {
        "none", "local_inference", "accelerator_benchmark", "large_build",
        "memory_pressure", "compute_storage_workload", "other_material",
    } or type(material_workload) is not bool:
        _fail("semantic_relationship", "environment workload observation is invalid")
    if material_workload != (workload != "none"):
        _fail("semantic_relationship", "environment workload facts contradict")

    try:
        expected_status, expected_reasons = snapshot_admission(
            observations,
            workload_category=workload,
            capture_phase=phase,
        )
    except (KeyError, TypeError, ValueError):
        _fail("semantic_relationship", "environment admission could not be recomputed")
    if (
        snapshot["interference_admission"] != expected_status
        or snapshot["admission_reasons"] != expected_reasons
    ):
        _fail("semantic_relationship", "environment admission facts contradict")


def _validate_benchmark_resource_semantics(
    resources: Mapping[str, Any],
    *,
    require_observed: bool,
) -> None:
    values: dict[str, Any | None] = {
        name: _environment_observed_value(resources, name)
        for name in BENCHMARK_RESOURCE_FIELDS
    }
    for name in (
        "process_footprint_bytes", "mlx_active_memory_bytes",
        "mlx_cache_memory_bytes", "mlx_peak_memory_bytes", "process_bytes_read",
    ):
        value = values[name]
        if value is not None:
            _plain_int(value, positive=name == "process_footprint_bytes", nonnegative=True)
    cpu_time = values["process_cpu_time_seconds"]
    if cpu_time is not None and _finite_number(cpu_time) < 0:
        _fail("semantic_relationship", "benchmark CPU time is negative")
    active = values["mlx_active_memory_bytes"]
    peak = values["mlx_peak_memory_bytes"]
    if isinstance(active, int) and isinstance(peak, int) and peak < active:
        _fail("semantic_relationship", "benchmark MLX memory gauges are inconsistent")
    if require_observed and any(
        values[name] is None
        for name in (
            "process_footprint_bytes", "mlx_active_memory_bytes",
            "mlx_cache_memory_bytes", "mlx_peak_memory_bytes",
        )
    ):
        _fail("semantic_relationship", "executed evidence lacks benchmark memory gauges")
    worker_facts = {
        name: values[name]
        for name in (
            "worker_backend", "worker_requested_device", "worker_selected_device",
            "worker_fallback_used", "worker_evaluated", "worker_synchronized",
        )
    }
    if worker_facts != {
        "worker_backend": "apple-mlx",
        "worker_requested_device": "gpu",
        "worker_selected_device": "gpu",
        "worker_fallback_used": False,
        "worker_evaluated": True,
        "worker_synchronized": True,
    }:
        _fail("semantic_relationship", "benchmark resources lack evaluated MLX GPU provenance")


def _evidence_scope(record: Mapping[str, Any]) -> str:
    """Return the additive v1.1 scope; omitted v1 records are fixture-only."""

    scope = record.get("evidence_scope", "synthetic_fixture")
    if scope not in {"synthetic_fixture", "external_checkpoint"}:
        _fail("semantic_relationship", "evidence scope is invalid")
    return scope


def _validate_environment_semantics(record: dict[str, Any]) -> None:
    environment = record["environment"]
    if (
        environment["platform"] != "macos-arm64"
        or environment["selected_backend"] != "apple-mlx"
        or environment["selected_device"] != "gpu"
        or environment["interference_admission"]
        not in {"admitted", "postponed", "observed_interference"}
    ):
        _fail("semantic_relationship", "environment identity is invalid")

    has_pair = {
        "interference_reasons", "before_snapshot", "after_snapshot",
        "benchmark_resources",
    } <= environment.keys()
    if not has_pair:
        if _evidence_scope(record) != "synthetic_fixture":
            _fail("semantic_relationship", "real evidence lacks paired environment snapshots")
        return

    before = environment["before_snapshot"]
    after = environment["after_snapshot"]
    _validate_environment_snapshot_semantics(record, before, phase="before")
    after_snapshot: dict[str, Any] | None
    after_reason: str | None
    if after.get("status") == "unavailable":
        if record["actual_status"] != "blocked":
            _fail("semantic_relationship", "executed evidence lacks an after snapshot")
        after_snapshot = None
        after_reason = after["reason"]
    else:
        after_snapshot = after
        after_reason = None
        _validate_environment_snapshot_semantics(record, after, phase="after")
    resources = environment["benchmark_resources"]
    _validate_benchmark_resource_semantics(
        resources,
        require_observed=_evidence_scope(record) == "external_checkpoint"
        and after_snapshot is not None,
    )
    try:
        recomputed = combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after_snapshot,
            after_unavailable_reason=after_reason,
            benchmark_resources=resources,
        )
    except (KeyError, TypeError, ValueError):
        _fail("semantic_relationship", "paired environment evidence is inconsistent")
    if (
        environment["interference_admission"] != recomputed["interference_admission"]
        or environment["interference_reasons"] != recomputed["interference_reasons"]
        or environment["safe_environment"] != recomputed["safe_environment"]
    ):
        _fail("semantic_relationship", "paired environment admission facts contradict")


def _validate_oracle_identity(record: dict[str, Any], repository_root: Path) -> None:
    """Validate fixture or real-checkpoint oracle identity without conflating them."""

    oracle = record["oracle"]
    fixture = record["input"]
    tensor = record["tensor"]
    for name in ("input_fixture_sha256", "tensor_sha256", "output_sha256"):
        if not isinstance(oracle[name], str) or not SHA256_RE.fullmatch(oracle[name]):
            _fail("semantic_relationship", "oracle identity is invalid")

    if _evidence_scope(record) == "synthetic_fixture":
        if (
            oracle["oracle_id"] != "f002-scalar-f32-v1"
            or oracle["project"] != REAL_ORACLE_PROJECT
            or oracle["revision"] != PINNED_ORACLE_REVISION
            or "$PULSARMLX_ROUTER_FIXTURE" not in oracle["generation_command"]
            or not isinstance(oracle["independence_statement"], str)
            or "does not import or invoke mlx"
            not in oracle["independence_statement"].lower()
        ):
            _fail("semantic_relationship", "oracle identity is invalid")
    elif oracle != _load_real_oracle_identity(repository_root):
        _fail("semantic_relationship", "oracle identity is invalid")

    if oracle["input_fixture_sha256"] != fixture["canonical_sha256"]:
        _fail("semantic_relationship", "oracle input identity does not match")
    if oracle["tensor_sha256"] != tensor["encoded_sha256"]:
        _fail("semantic_relationship", "oracle tensor identity does not match")


def _validate_semantics(record: dict[str, Any], repository_root: Path) -> None:
    evidence_scope = _evidence_scope(record)
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
        or protocol["protocol_version"] != FROZEN_PROTOCOL_VERSION
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

    if (
        evidence_scope == "external_checkpoint"
        and record["record_kind"] in {"timing", "combined"}
        and "second_batch" not in record
    ):
        _fail(
            "semantic_relationship",
            "external timing evidence lacks a second-batch disposition",
        )

    _validate_environment_semantics(record)

    if (
        record["actual_status"] == "passed"
        and record["environment"]["interference_admission"] != "admitted"
    ):
        _fail(
            "semantic_relationship",
            "a passing experiment requires admitted interference conditions",
        )

    if "second_batch" in record:
        second_batch = record["second_batch"]
        status = second_batch["status"]
        measured = second_batch["between_batch_variation_measured"]
        if type(measured) is not bool or status not in {"observed", "unavailable"}:
            _fail("semantic_relationship", "second-batch observation is invalid")
        if status == "observed":
            if measured is not True:
                _fail("semantic_relationship", "second-batch observation is inconsistent")
        else:
            if measured is not False or "reason" not in second_batch:
                _fail("semantic_relationship", "second-batch unavailable reason is missing")
            _bounded_text(second_batch["reason"])

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
        or tensor["execution_shape"] != [128, 2048]
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

    _validate_oracle_identity(record, repository_root)


def _is_fixture_scoped(record: dict[str, Any]) -> bool:
    return _evidence_scope(record) == "synthetic_fixture"


def _validate_scope_provenance(
    record: dict[str, Any], repository_root: Path
) -> None:
    """Prevent a constructed fixture from being relabeled as checkpoint evidence."""

    if _is_fixture_scoped(record):
        if (
            record["tensor"]["absolute_offset"] != 0
            or "real_checkpoint_routing"
            not in record["claim_boundary"]["unsupported_interpretations"]
            or not any("fixture" in warning.lower() for warning in record["warnings"])
        ):
            _fail("semantic_relationship", "synthetic fixture provenance is inconsistent")
        return

    manifest = _load_model_manifest(repository_root)
    admission = manifest.get("router_tensor_admission")
    observed = admission.get("observed") if isinstance(admission, dict) else None
    tensor = record["tensor"]
    if (
        manifest.get("observed_feature_002_model_access") is not True
        or manifest.get("status") != "sealed_read_only_inspection"
        or not isinstance(admission, dict)
        or admission.get("status") != "admitted_observed"
        or not isinstance(observed, dict)
        or observed.get("name") != tensor["name"]
        or observed.get("absolute_offset") != tensor["absolute_offset"]
        or observed.get("encoded_length_bytes") != tensor["encoded_length"]
        or observed.get("encoded_sha256") != tensor["encoded_sha256"]
        or tensor["absolute_offset"] <= 0
        or "real_checkpoint_routing"
        in record["claim_boundary"]["unsupported_interpretations"]
        or any(
            "fixture-only" in warning.lower()
            or "no real checkpoint" in warning.lower()
            for warning in record["warnings"]
        )
    ):
        _fail("semantic_relationship", "external checkpoint provenance is not sealed")


def _validate_artifacts(record: dict[str, Any], repository_root: Path) -> None:
    artifacts = record["artifacts"]
    if not artifacts or len(artifacts) > MAX_ARTIFACT_COUNT:
        _fail("semantic_relationship", "evidence has no linked repository artifacts")
    paths: set[str] = set()
    protocol_links = 0
    router_fixture_links = 0
    model_manifest_links = 0
    real_input_links = 0
    independent_oracle_links = 0
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
        if artifact["kind"] == "model_manifest":
            if path != MODEL_MANIFEST_PATH:
                _fail("semantic_relationship", "the model manifest artifact path is invalid")
            model_manifest_links += 1
        if artifact["kind"] == "real_router_input":
            if not path.startswith("fixtures/research/router-v1/real/"):
                _fail("semantic_relationship", "the real router input artifact path is invalid")
            real_input_links += 1
        if artifact["kind"] == "independent_cpu_oracle":
            if not (
                path.startswith("fixtures/research/router-v1/real/")
                or path.startswith("docs/research/raw/002-router-parity/")
            ):
                _fail("semantic_relationship", "the independent oracle artifact path is invalid")
            independent_oracle_links += 1
    if protocol_links != 1:
        _fail("semantic_relationship", "the frozen protocol artifact is not linked")
    if _is_fixture_scoped(record):
        if router_fixture_links != 1:
            _fail("semantic_relationship", "fixture evidence artifacts are incomplete")
    elif (model_manifest_links, real_input_links, independent_oracle_links) != (1, 1, 1):
        _fail("semantic_relationship", "external evidence provenance artifacts are incomplete")


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


def _observed_duration_ns(value: Any) -> int | None:
    """Validate one stage observation and return its measured duration."""

    if type(value) is int:
        return _plain_int(value, positive=True)
    if not isinstance(value, dict):
        _fail("schema_violation", "a timing stage observation is invalid")
    status = value.get("status")
    if status == "observed":
        stage = _closed_object(value, allowed={"status", "duration_ns"})
        return _plain_int(stage["duration_ns"], positive=True)
    if status in {"unavailable", "not_applicable"}:
        stage = _closed_object(value, allowed={"status", "reason"})
        _bounded_text(stage["reason"])
        return None
    _fail("schema_violation", "a timing stage observation status is invalid")


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
        external_checkpoint = _evidence_scope(record) == "external_checkpoint"
        if external_checkpoint and any(
            stage not in ROUTER_TIMING_STAGES for stage in item["durations_ns"]
        ):
            _fail("semantic_relationship", "external timing stage name is invalid")
        if external_checkpoint and any(
            type(duration) is int for duration in item["durations_ns"].values()
        ):
            _fail(
                "semantic_relationship",
                "external timing stages require structured status evidence",
            )

        observed_stage_count = 0
        for stage, duration in item["durations_ns"].items():
            _bounded_text(stage, maximum=128)
            if _observed_duration_ns(duration) is not None:
                observed_stage_count += 1
        if observed_stage_count == 0:
            _fail("semantic_relationship", "timing observation has no observed stage")
        if external_checkpoint:
            dequantization = item["durations_ns"].get("dequantization")
            if dequantization != {
                "status": "not_applicable",
                "reason": ROUTER_F32_DEQUANTIZATION_REASON,
            }:
                _fail(
                    "semantic_relationship",
                    "external F32 timing lacks canonical dequantization evidence",
                )
            if any(
                stage != "dequantization"
                and isinstance(duration, dict)
                and duration.get("status") == "not_applicable"
                for stage, duration in item["durations_ns"].items()
            ):
                _fail(
                    "semantic_relationship",
                    "only F32 dequantization can be not applicable",
                )
            if item["instrumentation_mode"] == "minimally_instrumented":
                total = item["durations_ns"].get("total_evaluated_router")
                if not (
                    isinstance(total, dict)
                    and total.get("status") == "observed"
                    and type(total.get("duration_ns")) is int
                    and total["duration_ns"] > 0
                ):
                    _fail(
                        "semantic_relationship",
                        "external minimal timing lacks its evaluated router total",
                    )
            elif set(item["durations_ns"]) != ROUTER_TIMING_STAGES:
                _fail(
                    "semantic_relationship",
                    "external stage timing omits a frozen boundary",
                )
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
    passed = [item for item in by_id.values() if item["status"] == "passed"]
    passed_by_case: dict[str, list[dict[str, Any]]] = {}
    for item in passed:
        passed_by_case.setdefault(item["case_id"], []).append(item)
    case_output_hashes: dict[str, str] = {}
    for case_id, observations in passed_by_case.items():
        observed_hashes = {str(item["output_sha256"]) for item in observations}
        if len(observed_hashes) != 1:
            _fail(
                "semantic_relationship",
                "deterministic output hashes differ within one case",
            )
        case_output_hashes[case_id] = observed_hashes.pop()
    if not case_output_hashes:
        _fail("insufficient_repetitions", "deterministic repetition policy is not met")
    if _evidence_scope(record) == "external_checkpoint":
        required_real_cases = set(SECOND_BATCH_CASE_ORDER)
        if set(case_output_hashes) != required_real_cases or len(
            {case_output_hashes[case_id] for case_id in required_real_cases}
        ) != len(required_real_cases):
            _fail(
                "semantic_relationship",
                "external evidence does not retain two distinct real-case outputs",
            )
    expected_repeat_hashes = sorted(
        output_sha256
        for output_sha256 in case_output_hashes.values()
        for _ in range(10)
    )
    if sorted(hashes) != expected_repeat_hashes:
        _fail(
            "semantic_relationship",
            "raw and repeated output identities differ by case",
        )
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
    has_measurement_series = False
    first_process_cohorts: dict[tuple[Any, ...], list[str]] = {}
    first_process_ids: set[str] = set()
    for base, kinds in timing_series.items():
        case_id, batch_id, process_id, process_state, condition, mode = base
        measurements = kinds.get("measurement", [])
        warmups = kinds.get("warmup", [])
        if condition in FIRST_PROCESS_CONDITIONS:
            # A first-process series is 0+1 by construction. The flat raw
            # ledger can collapse multiple separately named schedule cohorts
            # for the same case, so cohort multiplicity is checked below.
            if (
                process_state != "fresh_process"
                or len(measurements) != 1
                or warmups
                or kinds.get("clean_process_replication")
                or process_id in first_process_ids
            ):
                _fail(
                    "insufficient_repetitions",
                    "first-process timing policy is not met",
                )
            first_process_ids.add(process_id)
            first_process_cohorts.setdefault(
                (case_id, batch_id, condition, mode), []
            ).append(process_id)
            has_measurement_series = True
            continue
        if not measurements:
            continue
        has_measurement_series = True
        required_measurements = 30 if case_id.startswith("generated-") else 10
        if len(measurements) < required_measurements or (
            condition == "warm" and len(warmups) < 5
        ):
            _fail("insufficient_repetitions", "timing repetition policy is not met")
    if not has_measurement_series:
        _fail("insufficient_repetitions", "timing repetition policy is not met")
    for process_ids in first_process_cohorts.values():
        # Exactly ten series form one frozen cohort. A count of 20 is valid in
        # the flat ledger when primary and clean-process cohorts share the same
        # case/condition dimensions; the detailed candidate proves their
        # individual schedule identities before publication.
        if (
            len(process_ids) < FIRST_PROCESS_COHORT_SIZE
            or len(process_ids) % FIRST_PROCESS_COHORT_SIZE != 0
            or len(set(process_ids)) != len(process_ids)
        ):
            _fail(
                "insufficient_repetitions",
                "first-process timing cohort policy is not met",
            )


SUMMARY_FIELDS = {
    "summary_id",
    "statistics_algorithm",
    "group",
    "included_observation_ids",
    "excluded_observation_ids",
    "unfiltered_summary",
    "filtered_summary",
    "exclusion_rule_id",
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


def _validate_summaries(
    record: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    timing_groups: Mapping[tuple[Any, ...], list[Mapping[str, Any]]],
) -> None:
    summaries = record["summaries"]
    if not isinstance(summaries, list) or not summaries:
        _fail("schema_violation", "statistical summaries are missing")
    summary_ids: set[str] = set()
    projected_rows: dict[tuple[str, str], tuple[Any, ...]] = {}
    for compatibility_key, rows in timing_groups.items():
        for row in rows:
            observation_id = row.get("observation_id")
            stage = row.get("stage")
            if isinstance(observation_id, str) and isinstance(stage, str):
                identity = (observation_id, stage)
                if identity in projected_rows:
                    _fail(
                        "incompatible_summary_group",
                        "canonical timing projection contains duplicate rows",
                    )
                projected_rows[identity] = compatibility_key
    for raw_summary in summaries:
        summary = _closed_object(
            raw_summary,
            allowed=SUMMARY_FIELDS,
            required=SUMMARY_FIELDS - {"filtered_summary", "exclusion_rule_id"},
        )
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
        if "filtered_summary" in summary or "exclusion_rule_id" in summary:
            if "filtered_summary" not in summary or "exclusion_rule_id" not in summary:
                _fail("semantic_relationship", "filtered summary has no declared rule")
            _stable_id(summary["exclusion_rule_id"])
            # Protocol v1 retains every observation and declares no filter.
            _fail("semantic_relationship", "frozen protocol v1 declares no exclusion rule")
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
        included_compatibility_keys: list[tuple[Any, ...]] = []
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
            projected_key = projected_rows.get((observation_id, group["stage"]))
            if projected_key is None:
                _fail(
                    "raw_summary_mismatch",
                    "summary stage is absent from the canonical timing projection",
                )
            included_compatibility_keys.append(projected_key)
            included.append(observation)
        if len(set(included_compatibility_keys)) != 1:
            _fail(
                "incompatible_summary_group",
                "summary pools incompatible canonical timing rows",
            )
        replication_id = included[0]["process_replication_id"]
        if any(item["process_replication_id"] != replication_id for item in included):
            _fail("incompatible_summary_group", "summary pools process replications")
        process_state = included[0]["process_state"]
        if any(item["process_state"] != process_state for item in included):
            _fail("incompatible_summary_group", "summary pools process states")
        stage = group["stage"]
        if not isinstance(stage, str) or any(
            stage not in item["durations_ns"]
            or _observed_duration_ns(item["durations_ns"][stage]) is None
            for item in included
        ):
            _fail("raw_summary_mismatch", "summary timing stage is unavailable")
        expected_ids = {
            item["observation_id"]
            for item in by_id.values()
            if item["status"] == "passed"
            and item["process_replication_id"] == replication_id
            and item["process_state"] == process_state
            and stage in item["durations_ns"]
            and _observed_duration_ns(item["durations_ns"][stage]) is not None
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
        observed_durations = [
            _observed_duration_ns(item["durations_ns"][stage]) for item in included
        ]
        if any(value is None for value in observed_durations):
            _fail("raw_summary_mismatch", "summary timing stage is unavailable")
        recomputed = summarize_nanoseconds(
            [value for value in observed_durations if value is not None]
        )
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
    expected_observation_status = "aborted" if actual_status == "blocked" else actual_status
    if (
        actual_status not in {"failed", "blocked", "aborted"}
        or exit_code == 0
        or not record["failures"]
        or expected_observation_status not in observation_statuses
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
        timing_rows = project_timing_rows(record)
        timing_groups = group_raw_observations(timing_rows)
        if not timing_rows or not timing_groups:
            _fail("incompatible_summary_group", "timing compatibility projection is empty")
        _validate_summary_compatibility(record, by_id)
        _validate_contiguous_series(compatible_series)
        _validate_repetitions(record, by_id)
        _validate_summaries(record, by_id, timing_groups)
        _validate_correctness(record)
        _validate_claim_boundary(record)
        _validate_scope_provenance(record, repository_root)
        _validate_outcome_state(record, by_id)
        return record
    except EvidenceValidationError:
        raise
    except (OSError, OverflowError, RecursionError, TypeError, UnicodeError, ValueError):
        _fail("schema_violation", "evidence contains an invalid scalar value")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("schema_violation", "an evidence object contains a duplicate key")
        result[key] = value
    return result


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
            record = json.loads(
                path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except EvidenceValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
            _fail("schema_violation", "an evidence file is invalid JSON")
        if not isinstance(record, dict):
            _fail("schema_violation", "an evidence root is not an object")
        records.append((path, record))
    return records


def _canonical_record_sha256(record: Mapping[str, Any]) -> str:
    """Hash the complete record using the publication JSON canonicalization."""

    try:
        encoded = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeError, ValueError):
        _fail("schema_violation", "a linked record cannot be canonicalized")
    return hashlib.sha256(encoded).hexdigest()


def _second_batch_case_orders(
    record: Mapping[str, Any],
) -> dict[tuple[Any, ...], tuple[str, ...]]:
    orders: dict[tuple[Any, ...], list[str]] = {}
    for observation in record.get("raw_observations", []):
        if not isinstance(observation, Mapping):
            continue
        case_id = observation.get("case_id")
        if case_id not in SECOND_BATCH_CASE_ORDER:
            continue
        paired_step = (
            observation.get("observation_kind"),
            observation.get("process_state"),
            observation.get("condition"),
            observation.get("instrumentation_mode"),
        )
        order = orders.setdefault(paired_step, [])
        if not order or order[-1] != case_id:
            order.append(str(case_id))
    return {key: tuple(order) for key, order in orders.items()}


def _is_frozen_case_block(
    order: tuple[str, ...],
    expected_pair: tuple[str, str],
) -> bool:
    return order == expected_pair


def _second_batch_process_ids(record: Mapping[str, Any]) -> set[str]:
    process_ids = {str(record.get("process_replication_id"))}
    for observation in record.get("raw_observations", []):
        if isinstance(observation, Mapping):
            process_ids.add(str(observation.get("process_replication_id")))
    return process_ids


def _second_batch_device_facts(record: Mapping[str, Any]) -> tuple[tuple[Any, ...], ...]:
    facts = {
        (
            observation.get("requested_device"),
            observation.get("selected_device"),
            observation.get("fallback_used"),
            observation.get("evaluated"),
            observation.get("synchronized"),
        )
        for observation in record.get("raw_observations", [])
        if isinstance(observation, Mapping)
    }
    return tuple(sorted(facts, key=repr))


def _second_batch_environment_facts(record: Mapping[str, Any]) -> dict[str, Any]:
    environment = record.get("environment")
    if not isinstance(environment, Mapping):
        _fail("semantic_relationship", "linked second-batch environment is invalid")

    facts: dict[str, Any] = {
        "platform": environment.get("platform"),
        "selected_backend": environment.get("selected_backend"),
        "selected_device": environment.get("selected_device"),
        "safe_environment": environment.get("safe_environment"),
        "interference_admission": environment.get("interference_admission"),
        "interference_reasons": environment.get("interference_reasons"),
    }
    for phase in ("before_snapshot", "after_snapshot"):
        snapshot = environment.get(phase)
        if not isinstance(snapshot, Mapping):
            facts[phase] = None
            continue
        if snapshot.get("status") == "unavailable":
            facts[phase] = {"status": "unavailable"}
            continue
        observations = snapshot.get("observations")
        selected_observations = (
            {
                name: observations.get(name)
                for name in SECOND_BATCH_ENVIRONMENT_OBSERVATIONS
            }
            if isinstance(observations, Mapping)
            else None
        )
        facts[phase] = {
            "snapshot_schema": snapshot.get("snapshot_schema"),
            "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
            "platform": snapshot.get("platform"),
            "requested_backend": snapshot.get("requested_backend"),
            "requested_device": snapshot.get("requested_device"),
            "storage_role": snapshot.get("storage_role"),
            "storage_locator": snapshot.get("storage_locator"),
            "safe_environment": snapshot.get("safe_environment"),
            "interference_admission": snapshot.get("interference_admission"),
            "admission_reasons": snapshot.get("admission_reasons"),
            "observations": selected_observations,
        }

    resources = environment.get("benchmark_resources")
    facts["worker_device_facts"] = (
        {name: resources.get(name) for name in SECOND_BATCH_WORKER_FACTS}
        if isinstance(resources, Mapping)
        else None
    )
    return facts


def _validate_second_batch_cross_records(records: Iterable[Mapping[str, Any]]) -> None:
    """Resolve and validate every observed second-batch relationship in one input."""

    records_by_id = {
        str(record.get("experiment_id")): record
        for record in records
    }
    linked_targets: set[str] = set()
    observed_links: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []

    for source in records_by_id.values():
        second_batch = source.get("second_batch")
        if not isinstance(second_batch, Mapping) or second_batch.get("status") != "observed":
            continue
        source_id = str(source.get("experiment_id"))
        target_id = str(second_batch.get("linked_experiment_id"))
        if source_id == target_id:
            _fail("semantic_relationship", "a second-batch link cannot reference itself")
        target = records_by_id.get(target_id)
        if target is None:
            _fail("semantic_relationship", "a second-batch link is missing from this input")
        if target_id in linked_targets:
            _fail("semantic_relationship", "a second-batch record is linked more than once")
        linked_targets.add(target_id)

        source_batch_id = source.get("batch_id")
        linked_batch_id = second_batch.get("linked_batch_id")
        if source_batch_id == linked_batch_id or target.get("batch_id") == source_batch_id:
            _fail("semantic_relationship", "a second-batch link reuses the source batch")
        if target.get("batch_id") != linked_batch_id:
            _fail("semantic_relationship", "a linked second-batch identity does not resolve")

        target_disposition = target.get("second_batch")
        if (
            not isinstance(target_disposition, Mapping)
            or target_disposition.get("status") != "unavailable"
        ):
            _fail("semantic_relationship", "second-batch links cannot form chains or cycles")
        observed_links.append((source, target))

    for source, target in observed_links:
        immutable_fields = (
            "evidence_scope",
            "record_kind",
            "source_commit",
            "source_worktree_before",
            "protocol",
            "execution",
            "model",
            "tensor",
            "input",
            "oracle",
        )
        if any(source.get(field) != target.get(field) for field in immutable_fields):
            _fail("semantic_relationship", "linked second batches have incompatible identities")
        if _second_batch_environment_facts(source) != _second_batch_environment_facts(target):
            _fail("semantic_relationship", "linked second batches have incompatible environments")
        if _second_batch_device_facts(source) != _second_batch_device_facts(target):
            _fail("semantic_relationship", "linked second batches have incompatible device facts")
        if _second_batch_process_ids(source) & _second_batch_process_ids(target):
            _fail("semantic_relationship", "linked second batches reuse a process identity")

        source_orders = _second_batch_case_orders(source)
        target_orders = _second_batch_case_orders(target)
        reverse_order = tuple(reversed(SECOND_BATCH_CASE_ORDER))
        if (
            not source_orders
            or source_orders.keys() != target_orders.keys()
            or any(
                not _is_frozen_case_block(order, SECOND_BATCH_CASE_ORDER)
                for order in source_orders.values()
            )
            or any(
                not _is_frozen_case_block(order, reverse_order)
                for order in target_orders.values()
            )
        ):
            _fail("semantic_relationship", "linked second batches are not counterbalanced")

        second_batch = source["second_batch"]
        expected_hash = _canonical_record_sha256(target)
        if second_batch.get("linked_record_sha256") != expected_hash:
            _fail("semantic_relationship", "a linked second-batch hash does not match")
        if second_batch.get("linked_record_sha256") == _canonical_record_sha256(source):
            _fail("semantic_relationship", "a second-batch link is not a distinct record")


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
    _validate_second_batch_cross_records(validated)
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

#!/usr/bin/env python3
"""Fail-closed transformation of a private real-router candidate into public evidence.

This command is intentionally model-free.  It reads the bounded candidate and
the already-combined public environment handoff, recomputes every public
projection, validates the resulting records, and installs them exclusively.
It never imports MLX and never opens the checkpoint or private oracle paths.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
from datetime import datetime
import errno
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tomllib
from typing import Any, Callable, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_VALIDATOR_PATH = Path(__file__).with_name("validate_evidence.py")
_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "pulsarmlx_router_evidence_validator_for_sanitizer", _VALIDATOR_PATH
)
if _VALIDATOR_SPEC is None or _VALIDATOR_SPEC.loader is None:
    raise RuntimeError("research evidence validator is unavailable")
validator = importlib.util.module_from_spec(_VALIDATOR_SPEC)
_VALIDATOR_SPEC.loader.exec_module(validator)
environment_tools = validator._ENVIRONMENT_MODULE


MAX_PUBLIC_INPUT_BYTES = 4 * 1024 * 1024
MAX_CANDIDATE_INPUT_BYTES = 4 * 1024 * 1024
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64
READ_CHUNK_BYTES = 64 * 1024
APPLICATION_READ_SEMANTICS = (
    "application_positional_read_not_physical_disk_io"
)
F32_DEQUANTIZATION_REASON = "f32_router_requires_no_dequantization"
EXTERNAL_ORACLE_SHA256 = (
    "e31e4337ddf2c7cf1bb6cfe721428e6baaeffec7e29aee0f77727969e756e645"
)
PUBLIC_ORACLE_PATH = (
    "fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json"
)
MODEL_MANIFEST_PATH = "docs/research/MODEL_MANIFEST.json"
PROTOCOL_PATH = "docs/research/EXPERIMENT_PROTOCOL.md"
PRIMARY_BATCH = "batch-a"
SECOND_BATCH = "batch-b"
SINGLE_CASE = "qwen3moe-layer0-router-token0-row0-v1"
TWO_ROW_CASE = "qwen3moe-layer0-router-token0-token1-batch-v1"
EXPECTED_PARENT_ARGV = [
    "cargo", "run", "--release", "-p", "mlx-backend", "--bin",
    "pulsar-mlx", "--", "validate-router", "--model",
    "$PULSARMLX_MODEL_GGUF", "--oracle", "$PULSARMLX_ROUTER_ORACLE",
    "--evidence-dir", "$PULSARMLX_ROUTER_EVIDENCE",
]
PUBLIC_COMMAND = (
    "cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-router "
    "--model $PULSARMLX_MODEL_GGUF --oracle $PULSARMLX_ROUTER_ORACLE "
    "--evidence-dir $PULSARMLX_ROUTER_EVIDENCE"
)
UNSUPPORTED_INTERPRETATIONS = [
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
]
CAPABILITIES = [
    "router_logits",
    "router_full_softmax",
    "router_top8_selection",
    "router_selected_weight_normalization",
]
WARNINGS = [
    "This record covers only the bounded layer-0 router operation.",
    "First-read observations do not prove filesystem-cold access.",
    "Application bytes read are not physical-device I/O measurements.",
    "Stage-instrumented durations overlap or perturb lazy evaluation and are not additive.",
]
INTERNAL_UNSUPPORTED_INTERPRETATIONS = [
    "This candidate covers only the complete layer-0 router projection, full softmax, deterministic top-8, and selected-weight normalization boundary.",
    "It does not execute experts, a complete MoE block or layer, generation, serving, or full-model inference.",
    "Stage-instrumented durations overlap or perturb lazy evaluation and must not be summed into the minimally instrumented total.",
    "This external internal candidate is not public verified evidence until T086 validation and sanitization.",
]
KNOWN_FAILURE_MESSAGES = {
    "model_identity_mismatch": "the retained router operation reported a model identity mismatch",
    "model_size_mismatch": "the retained router operation reported a model size mismatch",
    "model_checksum_mismatch": "the retained router operation reported a model checksum mismatch",
    "missing_tensor_role": "the retained router operation reported a missing tensor role",
    "duplicate_tensor_role": "the retained router operation reported a duplicate tensor role",
    "model_tensor_mismatch": "the retained router operation reported a model tensor mismatch",
    "unsupported_tensor_quantization": "the retained router operation reported unsupported tensor quantization",
    "invalid_tensor_range": "the retained router operation reported an invalid tensor range",
    "model_budget_exceeded": "the retained router operation exceeded its model budget",
    "protocol_mismatch": "the retained router operation reported a protocol mismatch",
    "message_too_large": "the retained router operation reported an oversized message",
    "malformed_request": "the retained router operation reported a malformed request",
    "unsupported_operation": "the retained router operation reported an unsupported operation",
    "invalid_shape": "the retained router operation reported an invalid shape",
    "invalid_dtype": "the retained router operation reported an invalid data type",
    "invalid_layout": "the retained router operation reported an invalid layout",
    "invalid_byte_count": "the retained router operation reported an invalid byte count",
    "runtime_version_mismatch": "the retained router operation reported a runtime version mismatch",
    "unsupported_host": "the retained router operation reported an unsupported host",
    "metal_unavailable": "the retained router operation reported unavailable Metal support",
    "device_unavailable": "the retained router operation reported an unavailable device",
    "evaluation_failed": "the retained router operation reported an evaluation failure",
    "comparison_failed": "the retained router operation reported a correctness comparison failure",
    "resource_limit": "the retained router operation reported a resource limit",
    "internal_worker_error": "the retained router operation reported an internal worker error",
}
KNOWN_FAILURE_STAGES = {
    "correctness_gate", "immutable_recheck", "lifecycle_observation",
    "live_adapter", "orchestration", "protocol", "request_observation",
    "router_execution", "worker_shutdown", "worker_startup",
}
SECOND_BATCH_UNAVAILABLE_REASONS = frozenset({
    "the later independent collection window was unavailable",
    "the later batch did not pass the frozen resource-admission gate",
    "the later batch did not match the admitted thermal or power state",
    "the later batch was unavailable because external interference was observed",
})
PUBLIC_AFTER_UNAVAILABLE_REASON = (
    "the post-run public environment observation was unavailable"
)
PUBLIC_AFTER_UNAVAILABLE_METHOD = "post_run_environment_capture"
PASSING_ORCHESTRATION_FIELDS = frozenset({
    "schema_version", "orchestration", "status", "order_seed",
    "correctness_gates", "primary_batch", "second_batch",
})
FAILED_ORCHESTRATION_FIELDS = frozenset({
    "schema_version", "orchestration", "status", "batch_id", "order", "stage",
    "failure", "order_seed", "raw_observations", "completed_correctness_gates",
    "retained_current_case_attempts", "retained_timing", "second_batch",
    "first_process_observation_started", "timing_started", "passed",
})
PRIMARY_BATCH_FIELDS = frozenset({
    "batch_id", "order", "raw_observations", "first_process_series",
    "costly_series", "major_series", "stage_diagnostic_series",
})
RECORDED_SECOND_BATCH_FIELDS = frozenset({
    "status", "batch_id", "order", "raw_observations",
    "between_batch_variation_measured", "first_process_series",
    "correctness_gates", "costly_series", "major_series",
    "stage_diagnostic_series",
})
UNAVAILABLE_SECOND_BATCH_FIELDS = frozenset({
    "status", "reason", "between_batch_variation_measured",
})
CORRECTNESS_GATE_FIELDS = frozenset({
    "batch_id", "case_id", "attempt_count", "warmup_count",
    "measurement_count", "complete_output_sha256", "canonical_output",
    "requested_device", "selected_device", "fallback_used", "evaluated",
    "synchronized", "comparison_passed", "passed", "attempts",
})
LEDGER_FIELDS = frozenset({
    "global_order_index", "observation_id", "case_id", "batch_id",
    "process_replication_id", "process_state", "condition", "schedule_step",
    "source_kind", "observation_kind", "run_index", "status",
    "orchestration_status", "identity_duplicate", "timing_profile",
    "started_at_utc", "completed_at_utc", "host_wall_duration_ns",
    "host_monotonic_clock", "process_request_index", "router_tensor_bytes_read",
    "router_tensor_cache_status", "router_tensor_bytes_semantics",
})
LIFECYCLE_FIELDS = frozenset({
    "event_order", "recorded_at_utc", "process_replication_id", "timing_profile",
    "event", "outcome", "details",
})
BENIGN_TOKEN_FIELD_NAMES = frozenset({
    "token_count", "token_counts", "token_id", "token_ids", "token_index",
    "token_indices", "token_type", "token_types",
})
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9_.-])"
    r"(?P<name>[A-Za-z][A-Za-z0-9_.-]{0,63})\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;}&|]+"
)
BEARER_CREDENTIAL_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")


def _credential_name(value: str) -> bool:
    """Recognize credential-bearing field names without flagging token IDs."""

    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    normalized = re.sub(r"[^a-z0-9]+", "_", separated.lower()).strip("_")
    if not normalized or normalized in BENIGN_TOKEN_FIELD_NAMES:
        return False
    parts = tuple(part for part in normalized.split("_") if part)
    if any(
        part in {
            "authorization", "cookie", "credential", "credentials", "password",
            "passwd", "pwd", "secret",
        }
        for part in parts
    ):
        return True
    if "token" in parts:
        return True
    pairs = set(zip(parts, parts[1:]))
    return bool(
        pairs.intersection({
            ("api", "key"), ("private", "key"), ("access", "key"),
            ("signing", "key"),
        })
        or "apikey" in parts
    )


def _contains_credential_assignment(value: str) -> bool:
    return any(
        _credential_name(match.group("name"))
        for match in CREDENTIAL_ASSIGNMENT_RE.finditer(value)
    )


class SanitizationError(ValueError):
    """A bounded failure that is safe to report without local path disclosure."""


@dataclass(frozen=True)
class SecureDocument:
    path: Path
    raw: bytes
    value: dict[str, Any]
    sha256: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    maximum_bytes: int


@dataclass(frozen=True)
class CanonicalPublicArtifact:
    payload: bytes
    sha256: str
    size: int


def _fail(message: str) -> None:
    raise SanitizationError(message)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("input JSON contains a duplicate object field")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    _fail("input JSON contains a non-finite number")


def _scan_structure_and_privacy(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail("input JSON exceeds the structural bound")
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    _fail("input JSON contains a non-string object field")
                if _credential_name(key) and not (
                    child is None or child == ""
                ):
                    _fail("input JSON contains credential-shaped data")
                # Keys are privacy-scanned below by the shared validator but,
                # like the producer/validator contract, are not JSON value nodes.
                pending.append((child, depth + 1))
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)
        elif isinstance(current, float) and not math.isfinite(current):
            _fail("input JSON contains a non-finite number")
        elif isinstance(current, str) and any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in current
        ):
            _fail("input JSON contains an invalid control character")
        elif isinstance(current, str) and (
            _contains_credential_assignment(current)
            or BEARER_CREDENTIAL_RE.search(current) is not None
        ):
            _fail("input JSON contains credential-shaped data")
    try:
        validator._reject_non_finite_and_private_values(value)
    except validator.EvidenceValidationError as error:
        _fail(f"input JSON is not public-safe ({error.code})")


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _path_parts(path: Path, *, subject: str) -> tuple[int, list[str]]:
    raw = os.fspath(path)
    if not raw or "\x00" in raw:
        _fail(f"{subject} path is invalid")
    absolute = os.path.isabs(raw)
    parts = list(Path(raw).parts)
    if absolute:
        parts = parts[1:]
    normalized: list[str] = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == ".." or "/" in part:
            _fail(f"{subject} path traversal is not allowed")
        normalized.append(part)
    try:
        anchor = os.open("/" if absolute else ".", _directory_open_flags())
    except OSError:
        _fail(f"{subject} path anchor could not be opened")
    return anchor, normalized


def _open_parent_directory_no_symlinks(
    path: Path, *, subject: str
) -> tuple[int, str]:
    descriptor, parts = _path_parts(path, subject=subject)
    if not parts:
        os.close(descriptor)
        _fail(f"{subject} path lacks a final component")
    try:
        for component in parts[:-1]:
            next_descriptor = os.open(
                component, _directory_open_flags(), dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except OSError:
        os.close(descriptor)
        _fail(f"{subject} path has an unavailable or symlinked parent")


def _open_directory_no_symlinks(path: Path, *, subject: str) -> int:
    descriptor, parts = _path_parts(path, subject=subject)
    try:
        for component in parts:
            next_descriptor = os.open(
                component, _directory_open_flags(), dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError:
        os.close(descriptor)
        _fail(f"{subject} has an unavailable or symlinked component")


def _same_directory_binding(path: Path, expected: os.stat_result, *, subject: str) -> None:
    descriptor = _open_directory_no_symlinks(path, subject=subject)
    try:
        observed = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if observed.st_dev != expected.st_dev or observed.st_ino != expected.st_ino:
        _fail(f"{subject} changed during sanitization")


def _read_secure_json(
    path: Path, *, subject: str, maximum_bytes: int = MAX_PUBLIC_INPUT_BYTES
) -> SecureDocument:
    descriptor: int | None = None
    parent_descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        parent_descriptor, name = _open_parent_directory_no_symlinks(
            path, subject=subject
        )
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            _fail(f"{subject} must be a regular file")
        if metadata.st_nlink != 1:
            _fail(f"{subject} must have exactly one filesystem link")
        if metadata.st_size <= 0 or metadata.st_size > maximum_bytes:
            _fail(f"{subject} size is outside the bounded intake")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, READ_CHUNK_BYTES):
            total += len(chunk)
            if total > maximum_bytes:
                _fail(f"{subject} size is outside the bounded intake")
            chunks.append(chunk)
        raw = b"".join(chunks)
        if len(raw) != metadata.st_size:
            _fail(f"{subject} changed while it was read")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except SanitizationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail(f"{subject} is unreadable or invalid JSON")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    if not isinstance(value, dict):
        _fail(f"{subject} root must be an object")
    _scan_structure_and_privacy(value)
    return SecureDocument(
        path=path,
        raw=raw,
        value=value,
        sha256=hashlib.sha256(raw).hexdigest(),
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
        maximum_bytes=maximum_bytes,
    )


def _recheck_secure_document(document: SecureDocument, *, subject: str) -> None:
    current = _read_secure_json(
        document.path, subject=subject, maximum_bytes=document.maximum_bytes
    )
    if (
        current.device != document.device
        or current.inode != document.inode
        or current.size != document.size
        or current.mtime_ns != document.mtime_ns
        or current.sha256 != document.sha256
        or current.raw != document.raw
    ):
        _fail(f"{subject} changed during sanitization")


def _closed(
    value: Any,
    *,
    allowed: Iterable[str],
    required: Iterable[str] | None = None,
    subject: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{subject} must be an object")
    allowed_set = set(allowed)
    required_set = allowed_set if required is None else set(required)
    if set(value) - allowed_set or required_set - set(value):
        _fail(f"{subject} does not match its closed field contract")
    return value


def _list(value: Any, *, subject: str, maximum: int = 1_024) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(f"{subject} must be a bounded array")
    return value


def _plain_int(
    value: Any, *, subject: str, minimum: int = 0, maximum: int | None = None
) -> int:
    if type(value) is not int or value < minimum or (
        maximum is not None and value > maximum
    ):
        _fail(f"{subject} is outside its integer bound")
    return value


def _stable_id(value: Any, *, subject: str) -> str:
    if not isinstance(value, str) or validator.ID_RE.fullmatch(value) is None:
        _fail(f"{subject} is not a stable identity")
    return value


def _sha(value: Any, *, subject: str) -> str:
    if not isinstance(value, str) or validator.SHA256_RE.fullmatch(value) is None:
        _fail(f"{subject} is not a canonical SHA-256")
    return value


def _utc(value: Any, *, subject: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(f"{subject} is not canonical UTC")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except (OverflowError, ValueError):
        _fail(f"{subject} is not canonical UTC")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeError, ValueError):
        _fail("a public projection cannot be canonically encoded")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _public_record_bytes(record: Mapping[str, Any]) -> bytes:
    try:
        encoded = (
            json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
            + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeError, ValueError):
        _fail("a public record cannot be encoded")
    if len(encoded) > validator.MAX_PUBLIC_RECORD_BYTES:
        _fail("a public record exceeds the publication bound")
    return encoded


def _hash_repository_artifact(root: Path, relative: str) -> str:
    return validator._hash_repository_file(
        root,
        relative,
        allowed_prefixes=(("docs", "research"), ("fixtures", "research")),
        maximum_bytes=validator.MAX_LINKED_ARTIFACT_BYTES,
    )


def _repository_state(root: Path) -> tuple[str, bool]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root, check=True, capture_output=True, text=True, timeout=10,
        ).stdout)
    except (OSError, subprocess.SubprocessError):
        _fail("repository identity could not be verified")
    if validator.COMMIT_RE.fullmatch(head) is None:
        _fail("repository HEAD is not an immutable commit")
    return head, dirty


def _worker_package_version(root: Path) -> str:
    """Read the exact mlx-backend package version from the repository manifest."""

    try:
        raw, _ = validator._read_repository_file(
            root,
            "crates/mlx-backend/Cargo.toml",
            allowed_prefixes=(("crates", "mlx-backend"),),
            maximum_bytes=64 * 1024,
        )
        document = tomllib.loads(raw.decode("utf-8"))
        version = document.get("package", {}).get("version")
    except (
        AttributeError, KeyError, TypeError, UnicodeError, ValueError,
        validator.EvidenceValidationError,
    ):
        _fail("mlx-backend package version could not be verified")
    if not isinstance(version, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", version
    ):
        _fail("mlx-backend package version is invalid")
    return version


def _validate_candidate_root(candidate: dict[str, Any], root: Path) -> None:
    _closed(
        candidate,
        allowed={
            "schema_version", "candidate_kind", "candidate_status",
            "publication_status", "started_at_utc", "completed_at_utc",
            "experiment_wall_duration_ns", "source_commit",
            "source_worktree_before", "source_worktree_after", "parent_invocation",
            "backend", "requested_device", "artifact", "router_tensor", "oracle",
            "immutable_rechecks", "host_resource_observations", "worker",
            "orchestration", "unsupported_interpretations",
        },
        subject="candidate root",
    )
    if (
        candidate["schema_version"] != 1
        or candidate["candidate_kind"] != "qwen3moe-router-internal-orchestration"
        or candidate["candidate_status"] not in {"passed", "failed"}
        or candidate["publication_status"] != "external_unvalidated_candidate"
        or candidate["source_worktree_before"] != "clean"
        or candidate["source_worktree_after"] not in {"clean", "identity_recheck_failed"}
        or candidate["backend"] != "apple-mlx"
        or candidate["requested_device"] != "gpu"
    ):
        _fail("candidate identity is invalid")
    started = _utc(candidate["started_at_utc"], subject="candidate start")
    completed = _utc(candidate["completed_at_utc"], subject="candidate completion")
    if started > completed:
        _fail("candidate timestamps are reversed")
    _plain_int(
        candidate["experiment_wall_duration_ns"],
        subject="candidate wall duration", minimum=1,
    )
    if not isinstance(candidate["source_commit"], str) or validator.COMMIT_RE.fullmatch(
        candidate["source_commit"]
    ) is None:
        _fail("candidate source commit is invalid")

    invocation = _closed(
        candidate["parent_invocation"],
        allowed={"operation", "argv"},
        subject="candidate parent invocation",
    )
    if invocation != {"operation": "validate-router", "argv": EXPECTED_PARENT_ARGV}:
        _fail("candidate parent invocation is not the frozen symbolic command")

    model = _closed(
        candidate["artifact"],
        allowed={
            "repository_id", "revision", "filename", "size_bytes", "sha256",
            "location_symbolic", "read_only", "automatic_download",
        },
        subject="candidate model identity",
    )
    frozen_model = validator._load_model_identity(root)
    expected_model = {
        "repository_id": frozen_model["repository"],
        "revision": frozen_model["revision"],
        "filename": frozen_model["filename"],
        "size_bytes": frozen_model["size_bytes"],
        "sha256": frozen_model["sha256"],
        "location_symbolic": f"<external-model>/{frozen_model['filename']}",
        "read_only": True,
        "automatic_download": False,
    }
    if model != expected_model:
        _fail("candidate model identity differs from the frozen manifest")

    tensor = _closed(
        candidate["router_tensor"],
        allowed={
            "name", "absolute_data_offset", "encoded_length_bytes",
            "exclusive_end_offset", "encoded_sha256", "reader_shape",
            "execution_shape", "gguf_type", "quantization", "expert_count",
            "top_k", "weight_scale", "bias_present", "correction_bias_present",
            "selected_probability_renormalization",
        },
        subject="candidate router tensor",
    )
    manifest = validator._load_model_manifest(root)
    observed = manifest["router_tensor_admission"]["observed"]
    expected_tensor = {
        "name": observed["name"],
        "absolute_data_offset": observed["absolute_offset"],
        "encoded_length_bytes": observed["encoded_length_bytes"],
        "exclusive_end_offset": observed["exclusive_end_offset"],
        "encoded_sha256": observed["encoded_sha256"],
        "reader_shape": observed["reader_shape"],
        "execution_shape": observed["execution_shape"],
        "gguf_type": observed["gguf_type"],
        "quantization": observed["quantization"],
        "expert_count": observed["expert_count"],
        "top_k": observed["selected_expert_count"],
        "weight_scale": observed["weight_scale"],
        "bias_present": observed["bias_present"],
        "correction_bias_present": observed["correction_bias_present"],
        "selected_probability_renormalization": observed[
            "selected_probability_renormalization"
        ],
    }
    if tensor != expected_tensor:
        _fail("candidate router tensor differs from the frozen admission")

    oracle = _closed(
        candidate["oracle"],
        allowed={
            "oracle_id", "external_document_sha256", "public_projection_sha256",
            "input_f32le_sha256", "output_bundle_sha256",
            "worker_control_request_included_hidden_values",
            "worker_loaded_committed_hidden_input", "worker_received_oracle_outputs",
        },
        subject="candidate oracle identity",
    )
    public_oracle = validator._load_real_oracle_publication(root)
    if oracle != {
        "oracle_id": validator.REAL_ORACLE_ID,
        "external_document_sha256": EXTERNAL_ORACLE_SHA256,
        "public_projection_sha256": validator.REAL_ORACLE_PUBLICATION_SHA256,
        "input_f32le_sha256": public_oracle["input"]["canonical_f32le_sha256"],
        "output_bundle_sha256": public_oracle["result"]["hashes"][
            "output_bundle_sha256"
        ],
        "worker_control_request_included_hidden_values": False,
        "worker_loaded_committed_hidden_input": True,
        "worker_received_oracle_outputs": False,
    }:
        _fail("candidate oracle binding is invalid")

    rechecks = _closed(
        candidate["immutable_rechecks"],
        allowed={
            "full_model_sha256", "exact_router_range_sha256",
            "oracle_whole_file_sha256", "path_identity",
            "source_commit_and_cleanliness",
        },
        subject="candidate immutable rechecks",
    )
    if any(type(value) is not bool for value in rechecks.values()):
        _fail("candidate immutable rechecks are invalid")
    if (candidate["source_worktree_after"] == "clean") != all(rechecks.values()):
        _fail("candidate post-run identity contradicts immutable rechecks")

    resources = _closed(
        candidate["host_resource_observations"],
        allowed={"collector_wall_duration_ns", "collector_process_cpu_time_seconds"},
        subject="candidate host resource observations",
    )
    wall = _closed(
        resources["collector_wall_duration_ns"],
        allowed={"status", "value"},
        subject="candidate collector wall observation",
    )
    cpu = _closed(
        resources["collector_process_cpu_time_seconds"],
        allowed={"status", "reason", "source"},
        subject="candidate collector CPU observation",
    )
    if (
        wall.get("status") != "observed"
        or wall.get("value") != candidate["experiment_wall_duration_ns"]
        or cpu != {
            "status": "unavailable",
            "reason": "the bounded Rust command does not expose reliable combined parent-and-live-child CPU time",
            "source": "rust_std_process_boundary",
        }
        or candidate["unsupported_interpretations"]
        != INTERNAL_UNSUPPORTED_INTERPRETATIONS
    ):
        _fail("candidate fixed producer metadata differs from the Rust contract")


def _validate_environment_handoff(
    candidate: dict[str, Any], handoff: dict[str, Any], root: Path
) -> dict[str, Any]:
    _closed(
        handoff,
        allowed={
            "platform", "selected_backend", "selected_device", "safe_environment",
            "interference_admission", "interference_reasons", "before_snapshot",
            "after_snapshot", "benchmark_resources",
        },
        subject="combined environment",
    )
    try:
        environment_tools.assert_public_safe(handoff)
        before = handoff["before_snapshot"]
        after_value = handoff["after_snapshot"]
        environment_tools.validate_environment_snapshot(before, capture_phase="before")
        if after_value.get("status") == "unavailable":
            unavailable_after = _closed(
                after_value,
                allowed={"status", "reason", "attempted_method"},
                subject="post-run unavailable environment observation",
            )
            if unavailable_after["attempted_method"] != PUBLIC_AFTER_UNAVAILABLE_METHOD:
                _fail("post-run environment observation method differs")
            after = None
            after_reason = unavailable_after["reason"]
        else:
            environment_tools.validate_environment_snapshot(after_value, capture_phase="after")
            after = after_value
            after_reason = None
        expected_resources = environment_tools.extract_benchmark_resources(candidate)
        if handoff["benchmark_resources"] != expected_resources:
            _fail("combined environment resources differ from the candidate")
        recomputed = environment_tools.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after,
            after_unavailable_reason=after_reason,
            benchmark_resources=expected_resources,
        )
    except SanitizationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        _fail("combined environment handoff is invalid")
    if handoff != recomputed:
        _fail("combined environment handoff is not its canonical recomputation")

    for snapshot in (before, after):
        if snapshot is None:
            continue
        observations = snapshot["observations"]
        if (
            observations["repository_commit"].get("value")
            != candidate["source_commit"]
            or observations["pulsarmlx_version"].get("value")
            != candidate["source_commit"]
            or observations["worktree_dirty"].get("value") is not False
        ):
            _fail("environment source identity differs from the candidate")

    runtime = candidate["worker"].get("runtime")
    if runtime is not None:
        runtime = _closed(
            runtime,
            allowed={
                "protocol", "worker_version", "python_version", "python_architecture",
                "mlx_version", "macos_version", "metal_available", "gpu_count",
            },
            subject="worker runtime identity",
        )
        observations = before["observations"]
        if (
            runtime["protocol"] != 1
            or runtime["worker_version"] != _worker_package_version(root)
            or runtime["python_architecture"] != "arm64"
            or runtime["metal_available"] is not True
            or runtime["gpu_count"] != 1
            or runtime["python_version"] != observations["python_version"].get("value")
            or runtime["mlx_version"] != observations["mlx_version"].get("value")
            or runtime["macos_version"]
            != observations["macos_product_version"].get("value")
        ):
            _fail("worker runtime identity differs from the environment")
    projected = dict(handoff)
    if after is None:
        projected["after_snapshot"] = {
            "status": "unavailable",
            "reason": PUBLIC_AFTER_UNAVAILABLE_REASON,
            "attempted_method": PUBLIC_AFTER_UNAVAILABLE_METHOD,
        }
    return projected


def _project_model(candidate: Mapping[str, Any], root: Path) -> dict[str, Any]:
    return validator._load_model_identity(root)


def _project_tensor(candidate: Mapping[str, Any]) -> dict[str, Any]:
    source = candidate["router_tensor"]
    return {
        "name": source["name"],
        "semantic_role": "layer_0_router_projection",
        "occurrence_count": 1,
        "gguf_dimensions": [2048, 128],
        "reader_shape": source["reader_shape"],
        "execution_shape": source["execution_shape"],
        "dtype": source["gguf_type"],
        "quantization": source["quantization"],
        "absolute_offset": source["absolute_data_offset"],
        "encoded_length": source["encoded_length_bytes"],
        "end_offset": source["exclusive_end_offset"],
        "encoded_sha256": source["encoded_sha256"],
    }


def _project_input(root: Path) -> dict[str, Any]:
    publication = validator._load_real_oracle_publication(root)
    return {
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
        "canonical_sha256": publication["input"]["canonical_f32le_sha256"],
        "selected_rows": [0, 1],
    }


def _project_oracle(root: Path) -> dict[str, Any]:
    return validator._load_real_oracle_identity(root)


def _flatten(values: Any) -> list[Any]:
    result: list[Any] = []
    pending = [values]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(reversed(value))
        else:
            result.append(value)
    return result


def _recompute_output_comparison(
    oracle_output: dict[str, Any], candidate_output: dict[str, Any]
) -> dict[str, Any]:
    row_count = candidate_output["row_count"]
    numeric_specs = {
        "logits": (128, 5.0e-4, 5.0e-4),
        "full_probabilities": (128, 1.0e-6, 1.0e-6),
        "selected_probabilities": (8, 1.0e-6, 1.0e-6),
        "normalized_weights": (8, 1.0e-6, 1.0e-6),
    }
    comparison: dict[str, Any] = {}
    for field, (columns, absolute, relative) in numeric_specs.items():
        comparison[field] = validator._expected_numeric_comparison(
            _flatten(oracle_output[field]),
            _flatten(candidate_output[field]),
            row_count=row_count,
            columns=columns,
            absolute_tolerance=absolute,
            relative_tolerance=relative,
        )
    oracle_ids = oracle_output["selected_expert_ids"]
    candidate_ids = candidate_output["selected_expert_ids"]
    comparison["id_mismatch_count"] = sum(
        len(set(reference) - set(actual))
        for reference, actual in zip(oracle_ids, candidate_ids, strict=True)
    )
    comparison["order_mismatch_count"] = sum(
        left != right
        for reference, actual in zip(oracle_ids, candidate_ids, strict=True)
        for left, right in zip(reference, actual, strict=True)
    )
    ranges: dict[str, Any] = {}
    for label, columns_range in (("0..16", range(16)), ("64..80", range(64, 80))):
        logits = validator._expected_numeric_comparison(
            _flatten(oracle_output["logits"]),
            _flatten(candidate_output["logits"]),
            row_count=row_count,
            columns=128,
            absolute_tolerance=5.0e-4,
            relative_tolerance=5.0e-4,
            column_range=columns_range,
        )
        probabilities = validator._expected_numeric_comparison(
            _flatten(oracle_output["full_probabilities"]),
            _flatten(candidate_output["full_probabilities"]),
            row_count=row_count,
            columns=128,
            absolute_tolerance=1.0e-6,
            relative_tolerance=1.0e-6,
            column_range=columns_range,
        )
        ranges[label] = {
            "logits": logits,
            "full_probabilities": probabilities,
            "passed": logits["mismatch_count"] == 0
            and probabilities["mismatch_count"] == 0,
        }
    comparison["expert_range_comparisons"] = ranges
    comparison["passed"] = (
        comparison["id_mismatch_count"] == 0
        and comparison["order_mismatch_count"] == 0
        and all(comparison[field]["mismatch_count"] == 0 for field in numeric_specs)
    )
    return comparison


def _validate_and_copy_output(
    value: Any, *, case_id: str, row_count: int
) -> dict[str, Any]:
    try:
        output = json.loads(json.dumps(value, allow_nan=False))
        validator._validate_canonical_output(output, case_id, row_count)
    except validator.EvidenceValidationError as error:
        _fail(f"candidate canonical output is invalid ({error.code})")
    except (RecursionError, TypeError, ValueError):
        _fail("candidate canonical output is invalid")
    return output


def _failure(value: Any, *, subject: str) -> dict[str, Any]:
    item = _closed(
        value,
        allowed={"code", "message", "stage"},
        subject=subject,
    )
    code = _stable_id(item["code"], subject=f"{subject} code")
    stage = _stable_id(item["stage"], subject=f"{subject} stage")
    if code not in KNOWN_FAILURE_MESSAGES or stage not in KNOWN_FAILURE_STAGES:
        _fail(f"{subject} is not a closed producer failure")
    if not isinstance(item["message"], str) or not item["message"] or len(
        item["message"].encode("utf-8")
    ) > 512:
        _fail(f"{subject} message is invalid")
    return {
        "code": code,
        "message": KNOWN_FAILURE_MESSAGES[code],
        "stage": stage,
    }


def _passing_attempt_projection(
    attempt: dict[str, Any], oracle_output: dict[str, Any], row_count: int
) -> dict[str, Any]:
    candidate_output = _validate_and_copy_output(
        attempt["canonical_output"], case_id=attempt["case_id"], row_count=row_count
    )
    comparison = _recompute_output_comparison(oracle_output, candidate_output)
    expected_output_fields = {
        "logits_f32le_sha256": candidate_output["logits_f32le_sha256"],
        "full_probabilities_f32le_sha256": candidate_output[
            "full_probabilities_f32le_sha256"
        ],
        "selected_expert_ids": candidate_output["selected_expert_ids"],
        "selected_expert_ids_u32le_sha256": candidate_output[
            "selected_expert_ids_u32le_sha256"
        ],
        "selected_probabilities_f32le_sha256": candidate_output[
            "selected_probabilities_f32le_sha256"
        ],
        "normalized_weights_f32le_sha256": candidate_output[
            "normalized_weights_f32le_sha256"
        ],
        "complete_output_sha256": candidate_output["complete_output_sha256"],
    }
    if (
        attempt["backend"] != "apple-mlx"
        or any(attempt[field] != value for field, value in expected_output_fields.items())
        or attempt["comparison"] != comparison
        or attempt["requested_device"] != "gpu"
        or attempt["selected_device"] != "gpu"
        or attempt["fallback_used"] is not False
        or attempt["evaluated"] is not True
        or attempt["synchronized"] is not True
        or attempt["status"] != "passed"
        or attempt["passed"] is not True
        or attempt["result_passed"] is not True
        or attempt["failure"] is not None
        or comparison["passed"] is not True
    ):
        _fail("candidate marks a non-passing correctness output as passing")
    return {
        "attempt_id": attempt["attempt_id"],
        "attempt_index": attempt["attempt_index"],
        "observation_kind": attempt["observation_kind"],
        "run_index": attempt["run_index"],
        "process_replication_id": attempt["process_replication_id"],
        "canonical_output": candidate_output,
        "comparison": comparison,
        "memory_gauges": attempt["memory_gauges"],
        "requested_device": attempt["requested_device"],
        "selected_device": attempt["selected_device"],
        "fallback_used": attempt["fallback_used"],
        "evaluated": attempt["evaluated"],
        "synchronized": attempt["synchronized"],
        "status": "passed",
        "passed": True,
    }


def _attempt_projection(
    attempt: dict[str, Any], oracle_output: dict[str, Any], row_count: int
) -> dict[str, Any]:
    required_common = {
        "attempt_id", "attempt_index", "observation_kind", "run_index", "case_id",
        "process_replication_id", "process_state", "condition", "requested_device",
        "selected_device", "fallback_used", "evaluated", "synchronized",
        "memory_gauges", "canonical_output", "comparison", "status", "passed",
    }
    passing_only = {
        "backend", "logits_f32le_sha256", "full_probabilities_f32le_sha256",
        "selected_expert_ids", "selected_expert_ids_u32le_sha256",
        "selected_probabilities_f32le_sha256", "normalized_weights_f32le_sha256",
        "complete_output_sha256", "result_passed", "failure",
    }
    failed_only = {"batch_id", "schedule_step", "complete_output_sha256", "failure"}
    if attempt.get("status") == "passed" or "backend" in attempt:
        _closed(
            attempt,
            allowed=required_common | passing_only,
            required=required_common | passing_only,
            subject="candidate live correctness attempt",
        )
    else:
        _closed(
            attempt,
            allowed=required_common | failed_only,
            required=required_common | failed_only,
            subject="candidate aborted correctness attempt",
        )
    if (
        attempt["case_id"] not in {SINGLE_CASE, TWO_ROW_CASE}
        or attempt["process_state"] != "reused_process"
        or attempt["condition"] != "warm"
    ):
        _fail("candidate correctness attempt role is invalid")
    if attempt["status"] == "passed":
        return _passing_attempt_projection(attempt, oracle_output, row_count)
    if attempt["status"] not in {"failed", "aborted"} or attempt["passed"] is not False:
        _fail("candidate failed correctness attempt status is invalid")
    failure = _failure(attempt.get("failure"), subject="correctness failure")
    canonical_output = attempt.get("canonical_output")
    if canonical_output is None:
        comparison = None
    else:
        canonical_output = _validate_and_copy_output(
            canonical_output, case_id=attempt["case_id"], row_count=row_count
        )
        comparison = _recompute_output_comparison(oracle_output, canonical_output)
    return {
        "attempt_id": attempt["attempt_id"],
        "attempt_index": attempt["attempt_index"],
        "observation_kind": attempt["observation_kind"],
        "run_index": attempt["run_index"],
        "process_replication_id": attempt["process_replication_id"],
        "canonical_output": canonical_output,
        "comparison": comparison,
        "memory_gauges": attempt["memory_gauges"],
        "requested_device": attempt["requested_device"],
        "selected_device": attempt["selected_device"],
        "fallback_used": attempt["fallback_used"],
        "evaluated": attempt["evaluated"],
        "synchronized": attempt["synchronized"],
        "status": attempt["status"],
        "passed": False,
        "failure": failure,
    }


def _series_arrays(batch_source: Mapping[str, Any]) -> list[dict[str, Any]]:
    arrays: list[Any] = []
    if "retained_timing" in batch_source:
        retained = batch_source["retained_timing"]
        arrays.extend(
            retained.get(name, [])
            for name in (
                "first_process_series", "costly_series", "major_series",
                "stage_diagnostic_series",
            )
        )
        for rejected in retained.get("rejected_series", []):
            if not isinstance(rejected, dict) or set(rejected) != {"status", "failure", "series"}:
                _fail("rejected timing series is malformed")
            arrays.append([rejected["series"]])
    else:
        arrays.extend(
            batch_source.get(name, [])
            for name in (
                "first_process_series", "costly_series", "major_series",
                "stage_diagnostic_series",
            )
        )
    result: list[dict[str, Any]] = []
    for array in arrays:
        for series in _list(array, subject="candidate timing series array", maximum=128):
            if not isinstance(series, dict):
                _fail("candidate timing series entry is invalid")
            result.append(series)
    return result


def _extract_batch_sources(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    orchestration = candidate["orchestration"]
    if not isinstance(orchestration, dict) or orchestration.get("orchestration") != (
        "qwen3moe-router-frozen-schedule"
    ) or orchestration.get("schema_version") != 1 or orchestration.get("order_seed") != 22_002:
        _fail("candidate orchestration identity is invalid")
    if orchestration.get("status") == "passed":
        orchestration = _closed(
            orchestration,
            allowed=PASSING_ORCHESTRATION_FIELDS,
            subject="candidate passing orchestration",
        )
        if candidate["candidate_status"] != "passed":
            _fail("candidate status contradicts orchestration")
        primary_source = _closed(
            orchestration["primary_batch"],
            allowed=PRIMARY_BATCH_FIELDS,
            subject="candidate primary batch",
        )
        if primary_source["order"] != "single_row_before_two_row_within_each_major_pair":
            _fail("candidate primary batch order differs")
        primary = dict(primary_source)
        primary["batch_order"] = "single_row_first"
        primary["correctness_gates"] = orchestration["correctness_gates"]
        primary["terminal_failure_source"] = None
        later = orchestration["second_batch"]
        if not isinstance(later, dict):
            _fail("candidate later-batch disposition is invalid")
        if later.get("status") == "recorded":
            later = _closed(
                later,
                allowed=RECORDED_SECOND_BATCH_FIELDS,
                subject="candidate recorded second batch",
            )
            if (
                later["order"] != "two_row_before_single_row_within_each_major_pair"
                or later["between_batch_variation_measured"] is not True
            ):
                _fail("candidate recorded second-batch disposition differs")
            second = dict(later)
            second["batch_order"] = "two_row_first"
            second["terminal_failure_source"] = None
            return [primary, second]
        if later.get("status") != "unavailable":
            _fail("candidate later-batch disposition is invalid")
        later = _closed(
            later,
            allowed=UNAVAILABLE_SECOND_BATCH_FIELDS,
            subject="candidate unavailable second batch",
        )
        if (
            later["between_batch_variation_measured"] is not False
            or later["reason"] not in SECOND_BATCH_UNAVAILABLE_REASONS
        ):
            _fail("candidate unavailable second-batch reason differs")
        primary["second_batch_unavailable"] = later["reason"]
        return [primary]
    if orchestration.get("status") != "failed" or candidate["candidate_status"] != "failed":
        _fail("candidate orchestration status is invalid")
    orchestration = _closed(
        orchestration,
        allowed=FAILED_ORCHESTRATION_FIELDS,
        subject="candidate failed orchestration",
    )
    later = orchestration.get("second_batch")
    if isinstance(later, dict) and later.get("status") == "failed":
        later = _closed(
            later,
            allowed={"status", "batch_id", "retained_evidence"},
            subject="candidate failed later-batch disposition",
        )
        retained = _closed(
            later["retained_evidence"],
            allowed={
                "status", "batch_id", "order", "next_step", "raw_observations",
                "failure", "correctness_gates", "pending_correctness_attempts",
                "first_process_series", "costly_series", "primary_major_series",
                "stage_diagnostic_series", "clean_major_series",
                "rejected_timing_series",
            },
            subject="candidate failed later-batch evidence",
        )
        later_batch_id = _stable_id(
            later.get("batch_id"), subject="candidate failed later-batch identity"
        )
        if (
            retained.get("batch_id") != later_batch_id
            or retained.get("order") != "two_row_first"
            or retained.get("status") not in {"failed", "complete_candidate", "incomplete"}
        ):
            _fail("candidate failed later-batch identity is inconsistent")

        primary = dict(orchestration)
        primary["batch_order"] = "single_row_first"
        primary["correctness_gates"] = orchestration.get(
            "completed_correctness_gates", []
        )
        primary["pending_correctness_attempts"] = orchestration.get(
            "retained_current_case_attempts", []
        )
        primary["terminal_failure_source"] = None

        second = dict(retained)
        second["batch_order"] = "two_row_first"
        second["retained_timing"] = {
            "first_process_series": retained["first_process_series"],
            "costly_series": retained["costly_series"],
            "major_series": [
                *_list(
                    retained["primary_major_series"],
                    subject="candidate failed later primary-major series",
                    maximum=128,
                ),
                *_list(
                    retained["clean_major_series"],
                    subject="candidate failed later clean-major series",
                    maximum=128,
                ),
            ],
            "stage_diagnostic_series": retained["stage_diagnostic_series"],
            "rejected_series": retained["rejected_timing_series"],
        }
        second["terminal_failure_source"] = (
            retained.get("failure") or orchestration.get("failure")
        )
        if second["terminal_failure_source"] is None:
            _fail("candidate failed later batch lacks a terminal failure")
        return [primary, second]
    if later is not None:
        _fail("candidate failed second-batch disposition is invalid")
    primary = dict(orchestration)
    primary["batch_order"] = (
        "two_row_first" if orchestration.get("order") == "two_row_first" else "single_row_first"
    )
    primary["correctness_gates"] = orchestration.get("completed_correctness_gates", [])
    primary["pending_correctness_attempts"] = orchestration.get(
        "retained_current_case_attempts", []
    )
    primary["terminal_failure_source"] = orchestration.get("failure")
    return [primary]


def _prepare_batch(
    candidate: dict[str, Any], batch_source: dict[str, Any]
) -> dict[str, Any]:
    batch_id = _stable_id(batch_source.get("batch_id"), subject="batch identity")
    batch_order = batch_source.get("batch_order")
    if batch_order not in {"single_row_first", "two_row_first"}:
        _fail("candidate batch order is invalid")
    ledger = _list(
        batch_source.get("raw_observations"), subject="candidate ordered ledger", maximum=512
    )
    if not ledger:
        _fail("candidate batch has no ordered observations")

    gates = _list(
        batch_source.get("correctness_gates", []),
        subject="candidate correctness gates", maximum=2,
    )
    attempts: list[dict[str, Any]] = []
    for gate in gates:
        gate = _closed(
            gate,
            allowed=CORRECTNESS_GATE_FIELDS,
            subject="candidate correctness gate",
        )
        gate_attempts = _list(
            gate.get("attempts"), subject="candidate gate attempts", maximum=15
        )
        attempts.extend(gate_attempts)
    attempts.extend(
        _list(
            batch_source.get("pending_correctness_attempts", []),
            subject="candidate pending correctness attempts", maximum=15,
        )
    )

    series = _series_arrays(batch_source)
    timing_observations: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for item in series:
        raw = _list(
            item.get("raw_timing_observations"),
            subject="candidate raw timing observations", maximum=35,
        )
        for observation in raw:
            if not isinstance(observation, dict):
                _fail("candidate raw timing observation is invalid")
            identity = _stable_id(
                observation.get("observation_id"), subject="timing observation identity"
            )
            if identity in timing_observations:
                _fail("candidate timing observation identity is duplicated")
            timing_observations[identity] = (item, observation)

    attempt_map: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            _fail("candidate correctness attempt is invalid")
        identity = _stable_id(
            attempt.get("attempt_id"), subject="correctness attempt identity"
        )
        if identity in attempt_map:
            _fail("candidate correctness attempt identity is duplicated")
        attempt_map[identity] = attempt

    ordered_ids: list[str] = []
    for index, row in enumerate(ledger):
        row = _closed(
            row,
            allowed=LEDGER_FIELDS,
            required=LEDGER_FIELDS - {"identity_duplicate"},
            subject="candidate ordered ledger entry",
        )
        identity = _stable_id(row.get("observation_id"), subject="ledger identity")
        if row.get("global_order_index") != index or identity in ordered_ids:
            _fail("candidate ordered ledger is non-contiguous or duplicated")
        if row.get("batch_id") != batch_id:
            _fail("candidate ordered ledger batch differs")
        ordered_ids.append(identity)
    if set(ordered_ids) != set(attempt_map) | set(timing_observations):
        _fail("candidate correctness/timing sources are not bijective with the ledger")
    return {
        "batch_id": batch_id,
        "batch_order": batch_order,
        "source": batch_source,
        "gates": gates,
        "ledger": ledger,
        "ordered_ids": ordered_ids,
        "attempts": attempt_map,
        "timing": timing_observations,
        "series": series,
    }


def _worker_maps(candidate: dict[str, Any]) -> dict[str, Any]:
    worker = _closed(
        candidate["worker"],
        allowed={
            "runtime", "worker_lifecycle", "request_utc_windows",
            "timestamp_join_contract", "result_resource_records",
            "attempted_timing_observation_count", "active_process_count_at_serialization",
            "completed_process_count", "max_active_process_count_observed",
            "benchmark_concurrency",
        },
        subject="candidate worker evidence",
    )
    contract = _closed(
        worker["timestamp_join_contract"],
        allowed={"join_key", "relationship", "validated"},
        subject="candidate timestamp join contract",
    )
    attempted_count = _plain_int(
        worker["attempted_timing_observation_count"],
        subject="candidate attempted timing count",
        maximum=1_024,
    )
    active_count = _plain_int(
        worker["active_process_count_at_serialization"],
        subject="candidate active process count",
        maximum=1,
    )
    completed_count = _plain_int(
        worker["completed_process_count"],
        subject="candidate completed process count",
        maximum=256,
    )
    maximum_active = _plain_int(
        worker["max_active_process_count_observed"],
        subject="candidate maximum active process count",
        maximum=1,
    )
    if contract != {
        "join_key": "observation_id",
        "relationship": "exactly_one_request_window_and_one_resource_record_per_ordered_observation",
        "validated": True,
    } or active_count != 0 or worker["benchmark_concurrency"] != 1:
        _fail("candidate worker ownership contract is invalid")
    del attempted_count, completed_count, maximum_active

    def index(records: Any, subject: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for record in _list(records, subject=subject, maximum=1_024):
            if not isinstance(record, dict):
                _fail(f"{subject} entry is invalid")
            identity = _stable_id(record.get("observation_id"), subject=f"{subject} identity")
            if identity in result:
                _fail(f"{subject} identity is duplicated")
            result[identity] = record
        return result

    return {
        "worker": worker,
        "windows": index(worker["request_utc_windows"], "candidate request windows"),
        "resources": index(worker["result_resource_records"], "candidate resource records"),
        "lifecycles": _list(
            worker["worker_lifecycle"], subject="candidate worker lifecycle", maximum=256
        ),
    }


def _validate_global_bijection(
    batches: list[dict[str, Any]], worker_maps: dict[str, Any]
) -> None:
    ids = [identity for batch in batches for identity in batch["ordered_ids"]]
    if len(ids) != len(set(ids)):
        _fail("candidate observation identities are reused across batches")
    if set(ids) != set(worker_maps["windows"]) or set(ids) != set(worker_maps["resources"]):
        _fail("candidate ledger, request, and resource identities are not bijective")
    worker = worker_maps["worker"]
    timing_count = sum(len(batch["timing"]) for batch in batches)
    ledger_processes = {
        _stable_id(
            row.get("process_replication_id"), subject="ledger process identity"
        )
        for batch in batches for row in batch["ledger"]
    }
    lifecycle_processes: set[str] = set()
    for index, item in enumerate(worker_maps["lifecycles"]):
        item = _closed(
            item,
            allowed=LIFECYCLE_FIELDS,
            subject="candidate lifecycle entry",
        )
        if item["event_order"] != index:
            _fail("candidate lifecycle event order is non-contiguous")
        _utc(item["recorded_at_utc"], subject="candidate lifecycle timestamp")
        process_id = _stable_id(
            item["process_replication_id"], subject="candidate lifecycle process identity"
        )
        lifecycle_processes.add(process_id)
        _project_lifecycle_details(item, worker["runtime"])
    saw_admitted_process = any(
        item.get("event") == "spawn"
        and item.get("outcome") == "passed"
        for item in worker_maps["lifecycles"]
    )
    if (
        lifecycle_processes != ledger_processes
        or
        worker["attempted_timing_observation_count"] != timing_count
        or worker["completed_process_count"] != len(lifecycle_processes)
        or worker["max_active_process_count_observed"]
        != (1 if saw_admitted_process else 0)
    ):
        _fail("candidate worker counts differ from retained evidence")


def _project_timing_series(batch: dict[str, Any]) -> list[dict[str, Any]]:
    position = {identity: index for index, identity in enumerate(batch["ordered_ids"])}
    projected: list[dict[str, Any]] = []
    for raw_source in batch["series"]:
        source = _closed(
            raw_source,
            allowed={
                "benchmark_id", "case_id", "row_count", "series_kind",
                "replication_role", "process_replication_id", "process_state",
                "condition", "instrumentation_mode", "warmup_count",
                "measurement_count", "raw_timing_observations",
            },
            subject="candidate timing series",
        )
        observations = _list(
            source["raw_timing_observations"],
            subject="candidate timing series observations",
            maximum=35,
        )
        row_count = 1 if source["case_id"] == SINGLE_CASE else (
            2 if source["case_id"] == TWO_ROW_CASE else 0
        )
        warmup_plan = _plain_int(
            source["warmup_count"], subject="candidate timing warmup count", maximum=5
        )
        measurement_plan = _plain_int(
            source["measurement_count"],
            subject="candidate timing measurement count",
            maximum=30,
        )
        if (
            row_count == 0
            or source["row_count"] != row_count
            or not observations
            or len(observations) > warmup_plan + measurement_plan
        ):
            _fail("candidate timing series shape/count differs")
        ids = [item["observation_id"] for item in observations]
        warmups = sum(item["observation_kind"] == "warmup" for item in observations)
        measurements = sum(item["observation_kind"] == "measurement" for item in observations)
        projected.append({
            "benchmark_id": source["benchmark_id"],
            "case_id": source["case_id"],
            "series_kind": source["series_kind"],
            "replication_role": source["replication_role"],
            "process_replication_id": source["process_replication_id"],
            "process_state": source["process_state"],
            "condition": source["condition"],
            "instrumentation_mode": source["instrumentation_mode"],
            "warmup_count": source["warmup_count"],
            "measurement_count": source["measurement_count"],
            "attempted_warmup_count": warmups,
            "attempted_measurement_count": measurements,
            "retained_observation_count": len(ids),
            "observation_ids": ids,
        })
    projected.sort(key=lambda item: position[item["observation_ids"][0]])
    return projected


def _validate_correctness_gate(
    gate: dict[str, Any],
    *,
    batch_id: str,
    projected_by_id: Mapping[str, dict[str, Any]],
) -> None:
    case_id = gate["case_id"]
    row_count = 1 if case_id == SINGLE_CASE else 2 if case_id == TWO_ROW_CASE else 0
    source_attempts = _list(
        gate["attempts"], subject="candidate gate attempts", maximum=15
    )
    try:
        attempts = [projected_by_id[item["attempt_id"]] for item in source_attempts]
    except (KeyError, TypeError):
        _fail("candidate correctness gate attempts are not retained")
    expected_roles = [
        ("warmup", index) for index in range(5)
    ] + [
        ("measurement", index) for index in range(10)
    ]
    gate_output = _validate_and_copy_output(
        gate["canonical_output"], case_id=case_id, row_count=row_count
    ) if row_count else None
    first_measurement = attempts[5] if len(attempts) > 5 else None
    if (
        row_count == 0
        or gate["batch_id"] != batch_id
        or gate["attempt_count"] != 15
        or gate["warmup_count"] != 5
        or gate["measurement_count"] != 10
        or len(source_attempts) != 15
        or len(attempts) != 15
        or [
            (attempt["observation_kind"], attempt["run_index"])
            for attempt in attempts
        ] != expected_roles
        or [attempt["attempt_index"] for attempt in attempts] != list(range(15))
        or any(source["case_id"] != case_id for source in source_attempts)
        or any(
            source["process_replication_id"] != f"{batch_id}-correctness-worker"
            for source in source_attempts
        )
        or any(attempt["status"] != "passed" or attempt["passed"] is not True for attempt in attempts)
        or first_measurement is None
        or gate_output != first_measurement["canonical_output"]
        or gate["complete_output_sha256"] != gate_output["complete_output_sha256"]
        or any(
            attempt["canonical_output"] != first_measurement["canonical_output"]
            for attempt in attempts[5:]
        )
        or gate["requested_device"] != "gpu"
        or gate["selected_device"] != "gpu"
        or gate["fallback_used"] is not False
        or gate["evaluated"] is not True
        or gate["synchronized"] is not True
        or gate["comparison_passed"] is not True
        or gate["passed"] is not True
    ):
        _fail("candidate correctness gate aggregate differs from retained attempts")


def _project_correctness_cases(
    batch: dict[str, Any], root: Path
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    oracle_outputs = validator._load_real_oracle_outputs(root)
    attempts_by_case: dict[str, list[dict[str, Any]]] = {}
    positions = {identity: index for index, identity in enumerate(batch["ordered_ids"])}
    projected_by_id: dict[str, dict[str, Any]] = {}
    for attempt in batch["attempts"].values():
        case_id = attempt["case_id"]
        row_count = 1 if case_id == SINGLE_CASE else 2 if case_id == TWO_ROW_CASE else 0
        if row_count == 0:
            _fail("candidate correctness case is unsupported")
        projected = _attempt_projection(attempt, oracle_outputs[case_id], row_count)
        projected_by_id[attempt["attempt_id"]] = projected
        attempts_by_case.setdefault(case_id, []).append(projected)
    gate_cases: set[str] = set()
    for gate in batch["gates"]:
        _validate_correctness_gate(
            gate,
            batch_id=batch["batch_id"],
            projected_by_id=projected_by_id,
        )
        if gate["case_id"] in gate_cases:
            _fail("candidate correctness gate case is duplicated")
        gate_cases.add(gate["case_id"])
    cases: list[dict[str, Any]] = []
    for case_id, attempts in attempts_by_case.items():
        attempts.sort(key=lambda item: positions[item["attempt_id"]])
        for expected_index, attempt in enumerate(attempts):
            if attempt["attempt_index"] != expected_index:
                _fail("candidate correctness attempt order is not contiguous")
        last_output = next(
            (item["canonical_output"] for item in reversed(attempts) if item["canonical_output"] is not None),
            None,
        )
        comparison = (
            _recompute_output_comparison(oracle_outputs[case_id], last_output)
            if last_output is not None
            else None
        )
        cases.append({
            "case_id": case_id,
            "row_count": 1 if case_id == SINGLE_CASE else 2,
            "oracle_output": oracle_outputs[case_id],
            "mlx_output": last_output,
            "comparison": comparison,
            "attempts": attempts,
        })
    cases.sort(key=lambda item: min(
        positions[attempt["attempt_id"]] for attempt in item["attempts"]
    ))
    return cases, projected_by_id


def _project_lifecycle_details(
    source: dict[str, Any], runtime: dict[str, Any] | None
) -> dict[str, Any]:
    event = source["event"]
    outcome = source["outcome"]
    details = source["details"]
    if not isinstance(event, str) or not isinstance(outcome, str):
        _fail("candidate lifecycle event/outcome is invalid")
    if event == "spawn" and outcome == "started":
        expected = {"model_transport": "inherited_read_only_fd_198"}
        if details != expected:
            _fail("candidate lifecycle transport details differ")
        return expected
    if event == "spawn" and outcome == "passed":
        if runtime is None or details != runtime:
            _fail("candidate lifecycle runtime details differ")
        return dict(runtime)
    if event == "spawn" and outcome == "failed":
        item = _closed(
            details,
            allowed={"failure"},
            subject="candidate failed-spawn lifecycle details",
        )
        return {"failure": _failure(item["failure"], subject="lifecycle failure")}
    if event == "shutdown" and outcome in {
        "graceful", "forced_termination", "failed"
    }:
        item = _closed(
            details,
            allowed={"outcome", "exit_code", "error_code"},
            subject="candidate shutdown lifecycle details",
        )
        exit_code = item["exit_code"]
        error_code = item["error_code"]
        if (
            item["outcome"] != outcome
            or (exit_code is not None and type(exit_code) is not int)
            or (error_code is not None and error_code not in KNOWN_FAILURE_MESSAGES)
            or (outcome == "graceful" and (exit_code != 0 or error_code is not None))
        ):
            _fail("candidate shutdown lifecycle details differ")
        return {
            "outcome": outcome,
            "exit_code": exit_code,
            "error_code": error_code,
        }
    _fail("candidate lifecycle event/outcome is unsupported")


def _project_lifecycle(
    batch: dict[str, Any], worker_maps: dict[str, Any]
) -> list[dict[str, Any]]:
    process_ids = {
        row["process_replication_id"] for row in batch["ledger"]
    }
    result: list[dict[str, Any]] = []
    for source in worker_maps["lifecycles"]:
        if not isinstance(source, dict):
            _fail("candidate lifecycle entry is invalid")
        if source.get("process_replication_id") not in process_ids:
            continue
        item = _closed(
            source,
            allowed={
                "event_order", "recorded_at_utc", "process_replication_id",
                "timing_profile", "event", "outcome", "details",
            },
            subject="candidate lifecycle entry",
        )
        projected = dict(item)
        projected["details"] = _project_lifecycle_details(
            item, worker_maps["worker"]["runtime"]
        )
        projected["event_order"] = len(result)
        result.append(projected)
    if {item["process_replication_id"] for item in result} != process_ids:
        _fail("candidate lifecycle does not cover every batch process")
    return result


def _project_window(source: dict[str, Any]) -> dict[str, Any]:
    required = {
        "observation_id", "batch_id", "case_id", "schedule_step", "source_kind",
        "process_replication_id", "process_state", "condition", "timing_profile", "started_at_utc",
        "completed_at_utc", "host_wall_duration_ns", "host_monotonic_clock",
        "request_sent", "process_request_index", "router_tensor_bytes_read",
        "router_tensor_cache_status", "router_tensor_bytes_semantics", "status",
        "failure", "timestamp_observation",
    }
    _closed(source, allowed=required, subject="candidate request window")
    timestamp_state = source["timestamp_observation"]
    if timestamp_state not in {
        "observed", "completion_fallback_to_request_start",
        "failed_after_spawn_before_request",
    } or (
        source["request_sent"] is False
        and timestamp_state != "failed_after_spawn_before_request"
    ):
        _fail("candidate request timestamp disposition differs")
    projected = {
        field: source[field]
        for field in (
            "observation_id", "batch_id", "case_id", "schedule_step", "source_kind",
            "process_replication_id", "timing_profile", "started_at_utc",
            "completed_at_utc", "host_wall_duration_ns", "host_monotonic_clock",
            "request_sent", "status", "failure",
        )
    }
    projected["failure"] = (
        None if source["failure"] is None else
        _failure(source["failure"], subject="request-window failure")
    )
    return projected


def _abort_durations(window: dict[str, Any], failure: dict[str, Any]) -> dict[str, Any]:
    reason = f"{failure['code']}_before_evaluation"
    if len(reason) > 512:
        reason = "request_failed_before_evaluation"
    projected = {
        "dequantization": {
            "status": "not_applicable",
            "reason": F32_DEQUANTIZATION_REASON,
        },
        "total_evaluated_router": {"status": "unavailable", "reason": reason},
        "end_to_end_router_command": {
            "status": "observed",
            "duration_ns": window["host_wall_duration_ns"],
        },
    }
    return projected


def _project_resource(
    source: dict[str, Any],
    *,
    attempt: dict[str, Any] | None,
    timing_source: dict[str, Any] | None,
) -> dict[str, Any]:
    allowed = {
        "observation_id", "source_kind", "process_state", "condition", "backend",
        "requested_device", "selected_device", "fallback_used", "evaluated",
        "synchronized", "output_sha256", "correctness_passed", "canonical_output",
        "canonical_output_retention", "router_tensor_bytes_read",
        "router_tensor_cache_status", "router_tensor_bytes_semantics", "memory_gauges",
        "monotonic_clock", "instrumentation_mode", "timing_stages",
        "timing_stage_retention", "status", "failure",
    }
    _closed(source, allowed=allowed, subject="candidate resource record")
    canonical_output = source["canonical_output"]
    retention = source["canonical_output_retention"]
    timing_stages = source["timing_stages"]
    if attempt is not None:
        canonical_output = attempt["canonical_output"]
        retention = (
            "complete" if canonical_output is not None else
            "unavailable_aborted_request" if not source["evaluated"] else
            "unavailable_invalid_output"
        )
    elif timing_source is not None:
        timing_stages = timing_source["stages"] if source["evaluated"] else None
    cache = source["router_tensor_cache_status"]
    projected = {
        "observation_id": source["observation_id"],
        "source_kind": source["source_kind"],
        "backend": source["backend"],
        "requested_device": source["requested_device"],
        "selected_device": source["selected_device"],
        "fallback_used": source["fallback_used"],
        "evaluated": source["evaluated"],
        "synchronized": source["synchronized"],
        "output_sha256": source["output_sha256"],
        "correctness_passed": source["correctness_passed"],
        "canonical_output": canonical_output,
        "memory_gauges": source["memory_gauges"],
        "monotonic_clock": source["monotonic_clock"],
        "instrumentation_mode": source["instrumentation_mode"],
        "timing_stages": timing_stages,
        "application_tensor_bytes_read": source["router_tensor_bytes_read"],
        "tensor_cache_outcome": cache if cache is not None else "unavailable",
        "canonical_output_retention": retention,
        "status": source["status"],
        "failure": (
            None if source["failure"] is None else
            _failure(source["failure"], subject="resource failure")
        ),
    }
    return projected


def _project_batch_detail(
    batch: dict[str, Any],
    candidate: dict[str, Any],
    worker_maps: dict[str, Any],
    environment: dict[str, Any],
    source_candidate_sha256: str,
    root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    cases, attempts = _project_correctness_cases(batch, root)
    timing_series = _project_timing_series(batch)
    timing_series_by_observation = {
        observation_id: series
        for series in timing_series
        for observation_id in series["observation_ids"]
    }
    windows: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    ordered: list[dict[str, Any]] = []
    for index, ledger in enumerate(batch["ledger"]):
        observation_id = ledger["observation_id"]
        source_window = worker_maps["windows"][observation_id]
        source_resource = worker_maps["resources"][observation_id]
        window = _project_window(source_window)
        attempt = attempts.get(observation_id)
        timing_pair = batch["timing"].get(observation_id)
        timing_source = timing_pair[1] if timing_pair is not None else None
        resource = _project_resource(
            source_resource, attempt=attempt, timing_source=timing_source
        )
        if source_window["router_tensor_bytes_read"] != source_resource[
            "router_tensor_bytes_read"
        ] or source_window["router_tensor_cache_status"] != source_resource[
            "router_tensor_cache_status"
        ] or source_window["router_tensor_bytes_semantics"] != APPLICATION_READ_SEMANTICS or (
            source_resource["router_tensor_bytes_semantics"] != APPLICATION_READ_SEMANTICS
        ):
            _fail("candidate request/resource application-read join differs")
        if any(
            ledger.get(field) != source_window.get(field)
            for field in (
                "observation_id", "batch_id", "case_id", "schedule_step", "source_kind",
                "process_replication_id", "process_state", "condition", "status",
                "timing_profile", "started_at_utc",
                "completed_at_utc", "host_wall_duration_ns", "host_monotonic_clock",
                "process_request_index", "router_tensor_bytes_read",
                "router_tensor_cache_status", "router_tensor_bytes_semantics",
            )
        ):
            _fail("candidate ledger/request join differs")
        if ledger.get("process_state") != source_resource.get("process_state") or ledger.get(
            "condition"
        ) != source_resource.get("condition"):
            _fail("candidate process-state/condition join differs")

        if attempt is not None:
            process_state = "reused_process"
            condition = "warm"
            instrumentation = resource["instrumentation_mode"]
            durations = (
                resource["timing_stages"]
                if resource["evaluated"]
                else _abort_durations(window, resource["failure"])
            )
            if attempt["process_replication_id"] != ledger["process_replication_id"]:
                _fail("candidate correctness process join differs")
        elif timing_source is not None:
            timing_source = _closed(
                timing_source,
                allowed={
                    "observation_id", "run_index", "observation_kind",
                    "process_replication_id", "process_state", "condition",
                    "instrumentation_mode", "monotonic_clock", "stages", "status",
                    "requested_device", "selected_device", "fallback_used",
                    "evaluated", "synchronized", "output_sha256",
                    "correctness_passed", "timing_profile", "started_at_utc",
                    "completed_at_utc", "host_wall_duration_ns",
                    "router_tensor_bytes_read", "router_tensor_cache_status",
                    "failure",
                },
                required={
                    "observation_id", "run_index", "observation_kind",
                    "process_replication_id", "process_state", "condition",
                    "instrumentation_mode", "monotonic_clock", "stages", "status",
                    "requested_device", "selected_device", "fallback_used",
                    "evaluated", "synchronized", "output_sha256",
                    "correctness_passed", "timing_profile", "started_at_utc",
                    "completed_at_utc", "host_wall_duration_ns",
                    "router_tensor_bytes_read", "router_tensor_cache_status",
                },
                subject="candidate raw timing observation",
            )
            series_source = timing_pair[0]
            series = timing_series_by_observation[observation_id]
            process_state = series["process_state"]
            condition = series["condition"]
            instrumentation = series["instrumentation_mode"]
            durations = timing_source["stages"]
            timing_to_ledger = {
                "observation_id": "observation_id",
                "process_replication_id": "process_replication_id",
                "process_state": "process_state",
                "condition": "condition",
                "observation_kind": "observation_kind",
                "run_index": "run_index",
                "status": "status",
            }
            timing_to_window = {
                "timing_profile": "timing_profile",
                "started_at_utc": "started_at_utc",
                "completed_at_utc": "completed_at_utc",
                "host_wall_duration_ns": "host_wall_duration_ns",
                "router_tensor_bytes_read": "router_tensor_bytes_read",
                "router_tensor_cache_status": "router_tensor_cache_status",
                "status": "status",
            }
            timing_to_resource = {
                "requested_device": "requested_device",
                "selected_device": "selected_device",
                "fallback_used": "fallback_used",
                "evaluated": "evaluated",
                "synchronized": "synchronized",
                "output_sha256": "output_sha256",
                "correctness_passed": "correctness_passed",
                "instrumentation_mode": "instrumentation_mode",
                "monotonic_clock": "monotonic_clock",
                "router_tensor_bytes_read": "router_tensor_bytes_read",
                "router_tensor_cache_status": "router_tensor_cache_status",
                "status": "status",
            }
            if (
                any(
                    timing_source[left] != ledger[right]
                    for left, right in timing_to_ledger.items()
                )
                or any(
                    timing_source[left] != source_window[right]
                    for left, right in timing_to_window.items()
                )
                or any(
                    timing_source[left] != source_resource[right]
                    for left, right in timing_to_resource.items()
                )
                or timing_source["process_replication_id"]
                != series_source["process_replication_id"]
                or timing_source["process_state"] != series_source["process_state"]
                or timing_source["condition"] != series_source["condition"]
                or timing_source["instrumentation_mode"]
                != series_source["instrumentation_mode"]
                or ledger["case_id"] != series_source["case_id"]
                or source_resource["timing_stages"] is not None
                or source_resource["timing_stage_retention"]
                != "complete_in_joined_raw_timing_observation"
                or timing_source.get("failure") != source_window.get("failure")
                or timing_source.get("failure") != source_resource.get("failure")
            ):
                _fail("candidate timing joins differ")
        else:
            _fail("candidate ledger lacks correctness or timing source")

        observation = {
            "observation_id": observation_id,
            "run_index": ledger["run_index"],
            "batch_id": batch["batch_id"],
            "case_id": ledger["case_id"],
            "process_replication_id": ledger["process_replication_id"],
            "observation_kind": ledger["observation_kind"],
            "process_state": process_state,
            "condition": condition,
            "instrumentation_mode": instrumentation,
            "started_at_utc": window["started_at_utc"],
            "completed_at_utc": window["completed_at_utc"],
            "monotonic_clock": (
                resource["monotonic_clock"] if resource["evaluated"]
                else "rust_std_instant"
            ),
            "durations_ns": durations,
            "status": resource["status"],
            "requested_device": resource["requested_device"],
            "selected_device": resource["selected_device"],
            "fallback_used": resource["fallback_used"],
            "evaluated": resource["evaluated"],
            "synchronized": resource["synchronized"],
            "output_sha256": resource["output_sha256"],
            "correctness_passed": resource["correctness_passed"],
        }
        if resource["failure"] is not None:
            observation["failure"] = _failure(
                resource["failure"], subject="resource failure"
            )
        public_ledger = {
            "global_order_index": index,
            "observation_id": observation_id,
            "schedule_step": ledger["schedule_step"],
            "source_kind": ledger["source_kind"],
            "batch_id": batch["batch_id"],
            "case_id": ledger["case_id"],
            "process_replication_id": ledger["process_replication_id"],
            "observation_kind": ledger["observation_kind"],
            "run_index": ledger["run_index"],
            "orchestration_status": ledger["orchestration_status"],
            "identity_disposition": (
                "rejected_duplicate" if ledger.get("identity_duplicate") is True else "unique"
            ),
        }
        if timing_pair is not None:
            series = timing_series_by_observation[observation_id]
            for field in ("benchmark_id", "series_kind", "replication_role"):
                public_ledger[field] = series[field]
        ordered.append(public_ledger)
        windows.append(window)
        resources.append(resource)
        raw.append(observation)

    terminal_source = batch["source"].get("terminal_failure_source")
    raw_failures = [item["failure"] for item in raw if "failure" in item]
    terminal: dict[str, Any] | None = None
    if terminal_source is not None:
        retained = _failure(terminal_source, subject="orchestration terminal failure")
        if retained not in raw_failures:
            stage = retained.get("stage", "orchestration")
            phase = (
                "post_request_identity" if stage in {"immutable_recheck", "path_identity"}
                else "worker_shutdown" if "shutdown" in stage
                else "orchestration"
            )
            terminal = {
                "phase": phase,
                "process_replication_id": None,
                "failure": retained,
            }
    if candidate["source_worktree_after"] != "clean" and terminal is None:
        terminal = {
            "phase": "post_request_identity",
            "process_replication_id": None,
            "failure": {
                "code": "model_checksum_mismatch",
                "message": "post-run source, model, oracle, or path identity recheck failed",
                "stage": "immutable_recheck",
            },
        }
    if (
        environment["interference_admission"] in {"observed_interference", "postponed"}
        and not raw_failures
        and terminal is None
    ):
        observed = environment["interference_admission"] == "observed_interference"
        terminal = {
            "phase": (
                "environment_interference"
                if observed else "environment_admission_unavailable"
            ),
            "process_replication_id": None,
            "failure": {
                "code": (
                    "environment_interference"
                    if observed else "environment_admission_unavailable"
                ),
                "message": (
                    "post-run public environment evidence observed material interference"
                    if observed else
                    "the post-run public environment observation was unavailable"
                ),
                "stage": "environment",
            },
        }
    detail = {
        "detail_schema": "pulsarmlx.research.router-detail",
        "detail_schema_version": "1.0.0",
        "source_candidate_sha256": source_candidate_sha256,
        "source_environment_sha256": canonical_json_sha256(environment),
        "application_read_semantics": APPLICATION_READ_SEMANTICS,
        "batch_order": batch["batch_order"],
        "ordered_observations": ordered,
        "correctness_cases": cases,
        "timing_series": timing_series,
        "process_lifecycles": _project_lifecycle(batch, worker_maps),
        "request_windows": windows,
        "resource_records": resources,
        "terminal_failure": terminal,
    }
    return detail, raw, terminal


def _top_correctness(
    detail: dict[str, Any], raw: list[dict[str, Any]]
) -> dict[str, Any]:
    cases = detail["correctness_cases"]
    retained = [
        (case["case_id"], case["comparison"])
        for case in cases
        if isinstance(case["comparison"], dict)
    ]
    if not retained:
        evaluated_invalid_output = any(
            attempt["evaluated"] is True and attempt["canonical_output"] is None
            for case in cases for attempt in case["attempts"]
        )
        return {
            "status": "unavailable",
            "reason": (
                "the evaluated worker output was invalid before comparison"
                if evaluated_invalid_output else
                "a correctness request aborted before a retained comparison"
            ),
            "source": (
                "evaluated_output_invalid"
                if evaluated_invalid_output else "pre_execution_abort"
            ),
        }
    comparisons = [comparison for _, comparison in retained]
    logits = [comparison["logits"] for comparison in comparisons]
    compared_count = sum(item["compared_count"] for item in logits)
    relative = [
        item["maximum_relative_error"]
        for item in logits if item["maximum_relative_error"] is not None
    ]
    repeat_hashes = [
        attempt["canonical_output"]["complete_output_sha256"]
        for case in cases
        for attempt in case["attempts"]
        if attempt["observation_kind"] == "measurement"
        and isinstance(attempt["canonical_output"], dict)
    ]
    first_mismatch = None
    for case_id, comparison in retained:
        if comparison["id_mismatch_count"]:
            first_mismatch = {
                "case_id": case_id,
                "component": "selected_expert_ids",
                "mismatch_kind": "id_membership",
            }
            break
        if comparison["order_mismatch_count"]:
            first_mismatch = {
                "case_id": case_id,
                "component": "selected_expert_ids",
                "mismatch_kind": "order",
            }
            break
        if comparison["logits"]["first_mismatch"] is not None:
            first_mismatch = {
                "case_id": case_id,
                "component": "logits",
                **comparison["logits"]["first_mismatch"],
            }
            break
    id_mismatch_count = sum(item["id_mismatch_count"] for item in comparisons)
    order_mismatch_count = sum(
        item["order_mismatch_count"] for item in comparisons
    )
    numeric_mismatch_count = sum(item["mismatch_count"] for item in logits)
    return {
        "passed": (
            id_mismatch_count + order_mismatch_count + numeric_mismatch_count == 0
        ),
        "compared_count": compared_count,
        "id_mismatch_count": id_mismatch_count,
        "order_mismatch_count": order_mismatch_count,
        "numeric_mismatch_count": numeric_mismatch_count,
        "first_mismatch": first_mismatch,
        "maximum_absolute_error": max(item["maximum_absolute_error"] for item in logits),
        "mean_absolute_error": sum(
            item["mean_absolute_error"] * item["compared_count"] for item in logits
        ) / compared_count,
        "rmse": math.sqrt(sum(
            item["rmse"] ** 2 * item["compared_count"] for item in logits
        ) / compared_count),
        "maximum_relative_error": max(relative, default=0.0),
        "absolute_tolerance": 5.0e-4,
        "relative_tolerance": 5.0e-4,
        "non_finite_policy": "reject",
        "non_finite_count": 0,
        "deterministic_repeat_count": len(repeat_hashes),
        "repeat_output_hashes": repeat_hashes,
    }


def _summaries(record: dict[str, Any]) -> list[dict[str, Any]]:
    if record["environment"]["interference_admission"] != "admitted":
        return []
    rows = validator.project_timing_rows(record)
    groups = validator.group_raw_observations(rows)
    summaries: list[dict[str, Any]] = []
    for rows_in_group in groups.values():
        first = rows_in_group[0]
        if (
            first["observation_status"] != "passed"
            or first["observation_kind"] not in {"measurement", "clean_process_replication"}
        ):
            continue
        ids = [str(item["observation_id"]) for item in rows_in_group]
        durations = [item["duration_ns"] for item in rows_in_group]
        summaries.append({
            "summary_id": f"f002-{record['batch_id']}-summary-{len(summaries):03}",
            "statistics_algorithm": "pulsarmlx-type7-v1",
            "group": {
                "case_id": first["case_id"],
                "batch_id": first["batch_id"],
                "observation_kind": first["observation_kind"],
                "condition": first["condition"],
                "instrumentation_mode": first["instrumentation_mode"],
                "stage": first["stage"],
            },
            "included_observation_ids": ids,
            "excluded_observation_ids": [],
            "unfiltered_summary": validator.summarize_nanoseconds(durations),
        })
    return summaries


def _ordered_failures(
    raw: Sequence[Mapping[str, Any]], terminal: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for observation in raw:
        if observation.get("status") in {"failed", "aborted"}:
            failure = observation.get("failure")
            if isinstance(failure, dict) and failure not in failures:
                failures.append(dict(failure))
    if terminal is not None and terminal["failure"] not in failures:
        failures.append(dict(terminal["failure"]))
    return failures


def _outcome(
    raw: Sequence[Mapping[str, Any]], terminal: Mapping[str, Any] | None,
    environment: Mapping[str, Any], correctness: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    statuses = [item["status"] for item in raw]
    if "failed" in statuses:
        return "failed", "failed", []
    if "aborted" in statuses:
        return "aborted", "blocked", []
    if terminal is not None:
        if terminal["phase"] in {
            "environment_interference", "environment_admission_unavailable"
        }:
            return "blocked", "blocked", []
        return "failed", "failed", []
    if environment["interference_admission"] != "admitted":
        return "blocked", "blocked", []
    if correctness.get("passed") is not True:
        return "failed", "failed", []
    return "passed", "provisional", CAPABILITIES


def _artifacts(root: Path) -> list[dict[str, str]]:
    return [
        {
            "kind": "frozen_protocol",
            "path": PROTOCOL_PATH,
            "sha256": _hash_repository_artifact(root, PROTOCOL_PATH),
        },
        {
            "kind": "model_manifest",
            "path": MODEL_MANIFEST_PATH,
            "sha256": _hash_repository_artifact(root, MODEL_MANIFEST_PATH),
        },
        {
            "kind": "real_router_input_and_independent_cpu_oracle",
            "path": PUBLIC_ORACLE_PATH,
            "sha256": _hash_repository_artifact(root, PUBLIC_ORACLE_PATH),
        },
    ]


def _build_record(
    *,
    candidate: dict[str, Any],
    batch: dict[str, Any],
    worker_maps: dict[str, Any],
    environment: dict[str, Any],
    source_candidate_sha256: str,
    root: Path,
    second_batch: dict[str, Any],
) -> dict[str, Any]:
    detail, raw, terminal = _project_batch_detail(
        batch, candidate, worker_maps, environment, source_candidate_sha256, root
    )
    correctness = _top_correctness(detail, raw)
    actual_status, claim_status, capabilities = _outcome(
        raw, terminal, environment, correctness
    )
    experiment_id = f"f002-router-real-{source_candidate_sha256}-{batch['batch_id']}"
    record: dict[str, Any] = {
        "evidence_schema": "pulsarmlx.research.experiment",
        "evidence_schema_version": "1.2.0",
        "payload_schema": "pulsarmlx.research.router-parity",
        "payload_schema_version": "1.1.0",
        "experiment_id": experiment_id,
        "feature_id": "002-qwen-router-parity",
        "evidence_scope": "external_checkpoint",
        "record_kind": "combined",
        "actual_status": actual_status,
        "started_at_utc": min(item["started_at_utc"] for item in raw),
        "completed_at_utc": max(item["completed_at_utc"] for item in raw),
        "source_commit": candidate["source_commit"],
        "source_worktree_before": "clean",
        "source_worktree_after": {
            "state": "clean" if candidate["source_worktree_after"] == "clean" else "unknown",
            "paths": [],
        },
        "protocol": {
            "protocol_id": validator.FROZEN_PROTOCOL_ID,
            "protocol_version": validator.FROZEN_PROTOCOL_VERSION,
            "path": PROTOCOL_PATH,
            "sha256": _hash_repository_artifact(root, PROTOCOL_PATH),
            "order_seed": 22_002,
        },
        "execution": {
            "shell": "zsh",
            "command": PUBLIC_COMMAND,
            "argv": EXPECTED_PARENT_ARGV,
            "working_directory_policy": "repository_root",
            "exit_code": 0 if actual_status == "passed" else 1,
            "build_profile": "release",
            "features": ["mlx-backend"],
            "benchmark_order_policy": "deterministic_seeded",
        },
        "batch_id": batch["batch_id"],
        "process_replication_id": raw[0]["process_replication_id"],
        "second_batch": second_batch,
        "model": _project_model(candidate, root),
        "tensor": _project_tensor(candidate),
        "input": _project_input(root),
        "oracle": _project_oracle(root),
        "environment": environment,
        "correctness": correctness,
        "raw_observations": raw,
        "summaries": [],
        "claim_boundary": {
            "status": claim_status,
            "operation": "layer_0_router_only",
            "capabilities": capabilities,
            "unsupported_interpretations": UNSUPPORTED_INTERPRETATIONS,
        },
        "warnings": list(WARNINGS),
        "failures": _ordered_failures(raw, terminal),
        "artifacts": _artifacts(root),
        "router_detail": detail,
    }
    record["summaries"] = _summaries(record)
    return record


def build_public_records(
    candidate: dict[str, Any],
    environment: dict[str, Any],
    *,
    source_candidate_sha256: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[dict[str, Any]]:
    """Build target-first records in memory and validate every public projection."""

    _scan_structure_and_privacy(candidate)
    _scan_structure_and_privacy(environment)
    _validate_candidate_root(candidate, repository_root)
    handoff = _validate_environment_handoff(candidate, environment, repository_root)
    batch_sources = _extract_batch_sources(candidate)
    batches = [_prepare_batch(candidate, source) for source in batch_sources]
    workers = _worker_maps(candidate)
    _validate_global_bijection(batches, workers)

    if len(batches) == 2:
        target = _build_record(
            candidate=candidate,
            batch=batches[1],
            worker_maps=workers,
            environment=handoff,
            source_candidate_sha256=source_candidate_sha256,
            root=repository_root,
            second_batch={
                "status": "unavailable",
                "reason": "no third batch is admitted by the frozen protocol",
                "between_batch_variation_measured": False,
            },
        )
        target_hash = canonical_json_sha256(target)
        source = _build_record(
            candidate=candidate,
            batch=batches[0],
            worker_maps=workers,
            environment=handoff,
            source_candidate_sha256=source_candidate_sha256,
            root=repository_root,
            second_batch={
                "status": "observed",
                "between_batch_variation_measured": True,
                "linked_experiment_id": target["experiment_id"],
                "linked_batch_id": target["batch_id"],
                "linked_record_sha256": target_hash,
            },
        )
        records = [target, source]
    else:
        reason = batches[0]["source"].get(
            "second_batch_unavailable",
            "the primary run stopped before a later batch could begin",
        )
        records = [_build_record(
            candidate=candidate,
            batch=batches[0],
            worker_maps=workers,
            environment=handoff,
            source_candidate_sha256=source_candidate_sha256,
            root=repository_root,
            second_batch={
                "status": "unavailable",
                "reason": reason,
                "between_batch_variation_measured": False,
            },
        )]

    try:
        for record in records:
            validator.validate_record(record, repository_root=repository_root)
            _scan_structure_and_privacy(record)
            _public_record_bytes(record)
        validator._validate_second_batch_cross_records(records)
    except validator.EvidenceValidationError as error:
        _fail(f"sanitized public record failed validation ({error.code})")
    return records


def _atomic_rename_exclusive(
    parent_descriptor: int, source_name: str, destination_name: str
) -> None:
    if any(
        not name or "/" in name or name in {".", ".."}
        for name in (source_name, destination_name)
    ):
        _fail("atomic evidence rename has an invalid component")
    library = ctypes.CDLL(None, use_errno=True)
    encoded_source = os.fsencode(source_name)
    encoded_destination = os.fsencode(destination_name)
    if sys.platform == "darwin" and hasattr(library, "renameatx_np"):
        function = library.renameatx_np
        function.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor, encoded_source,
            parent_descriptor, encoded_destination,
            0x00000004,  # RENAME_EXCL
        )
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(
            parent_descriptor, encoded_source,
            parent_descriptor, encoded_destination,
            0x00000001,  # RENAME_NOREPLACE
        )
    else:
        _fail("exclusive atomic directory rename is unavailable on this host")
    if result != 0:
        observed_errno = ctypes.get_errno()
        if observed_errno in {errno.EEXIST, errno.ENOTEMPTY}:
            _fail("append-only public evidence destination already exists")
        _fail("exclusive atomic directory rename failed")


def _new_sibling_name(parent_descriptor: int, prefix: str) -> str:
    for _ in range(32):
        name = f"{prefix}{secrets.token_hex(12)}"
        try:
            os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return name
        except OSError:
            _fail("evidence staging identity could not be checked")
    _fail("a unique evidence staging identity could not be allocated")


def _remove_owned_directory(
    parent_descriptor: int,
    name: str,
    expected_files: set[str],
    *,
    require_complete: bool,
) -> bool:
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_descriptor)
        observed_files = set(os.listdir(descriptor))
        if (
            (require_complete and observed_files != expected_files)
            or not observed_files <= expected_files
        ):
            return False
        for filename in observed_files:
            metadata = os.stat(filename, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                return False
            os.unlink(filename, dir_fd=descriptor)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.rmdir(name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        return True
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _verify_canonical_artifacts(
    directory_descriptor: int,
    expected: Mapping[str, CanonicalPublicArtifact],
    *,
    subject: str,
) -> None:
    """Verify an exact artifact set through one already-anchored directory fd."""

    try:
        if set(os.listdir(directory_descriptor)) != set(expected):
            _fail(f"{subject} file inventory differs")
        for filename, artifact in expected.items():
            if not filename or "/" in filename or filename in {".", ".."}:
                _fail(f"{subject} filename is invalid")
            flags = os.O_RDONLY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_NONBLOCK"):
                flags |= os.O_NONBLOCK
            descriptor = os.open(filename, flags, dir_fd=directory_descriptor)
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                    or before.st_size != artifact.size
                ):
                    _fail(f"{subject} file metadata differs")
                chunks: list[bytes] = []
                total = 0
                while chunk := os.read(descriptor, READ_CHUNK_BYTES):
                    total += len(chunk)
                    if total > artifact.size:
                        _fail(f"{subject} file size differs")
                    chunks.append(chunk)
                after = os.fstat(descriptor)
                observed = b"".join(chunks)
                if (
                    after.st_dev != before.st_dev
                    or after.st_ino != before.st_ino
                    or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or after.st_ctime_ns != before.st_ctime_ns
                    or total != artifact.size
                    or observed != artifact.payload
                    or hashlib.sha256(observed).hexdigest() != artifact.sha256
                ):
                    _fail(f"{subject} canonical content differs")
            finally:
                os.close(descriptor)
    except SanitizationError:
        raise
    except OSError:
        _fail(f"{subject} could not be verified")


def _install_records_exclusively(
    records: Sequence[dict[str, Any]], output_dir: Path,
    *,
    repository_root: Path,
    source_recheck: Callable[[], None],
) -> list[Path]:
    expected_artifacts: dict[str, CanonicalPublicArtifact] = {}
    for record in records:
        filename = f"{record['experiment_id']}.json"
        payload = _public_record_bytes(record)
        if filename in expected_artifacts:
            _fail("public evidence artifact identity is duplicated")
        expected_artifacts[filename] = CanonicalPublicArtifact(
            payload=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
            size=len(payload),
        )
    expected_files = set(expected_artifacts)
    parent_descriptor, output_name = _open_parent_directory_no_symlinks(
        output_dir, subject="public evidence output"
    )
    parent_metadata = os.fstat(parent_descriptor)
    staging_name = _new_sibling_name(parent_descriptor, ".router-sanitize-")
    staging_descriptor: int | None = None
    installed_descriptor: int | None = None
    staging_metadata: os.stat_result | None = None
    installed = False
    try:
        try:
            os.stat(output_name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _fail("append-only public evidence destination already exists")
        os.mkdir(staging_name, mode=0o700, dir_fd=parent_descriptor)
        staging_descriptor = os.open(
            staging_name, _directory_open_flags(), dir_fd=parent_descriptor
        )
        staging_metadata = os.fstat(staging_descriptor)
        for filename, artifact in expected_artifacts.items():
            descriptor = os.open(
                filename,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | (os.O_CLOEXEC if hasattr(os, "O_CLOEXEC") else 0),
                0o600,
                dir_fd=staging_descriptor,
            )
            try:
                payload = artifact.payload
                written = 0
                while written < len(payload):
                    written += os.write(descriptor, payload[written:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        os.fsync(staging_descriptor)
        _same_directory_binding(
            output_dir.parent, parent_metadata, subject="public evidence parent"
        )
        validator.validate_input(
            repository_root / "schemas/research/v1",
            output_dir.parent / staging_name,
        )
        source_recheck()
        _same_directory_binding(
            output_dir.parent, parent_metadata, subject="public evidence parent"
        )
        _verify_canonical_artifacts(
            staging_descriptor,
            expected_artifacts,
            subject="staged public evidence",
        )
        _atomic_rename_exclusive(parent_descriptor, staging_name, output_name)
        installed = True
        os.close(staging_descriptor)
        staging_descriptor = None
        os.fsync(parent_descriptor)
        installed_descriptor = os.open(
            output_name, _directory_open_flags(), dir_fd=parent_descriptor
        )
        installed_metadata = os.fstat(installed_descriptor)
        if (
            staging_metadata is None
            or installed_metadata.st_dev != staging_metadata.st_dev
            or installed_metadata.st_ino != staging_metadata.st_ino
            or not stat.S_ISDIR(installed_metadata.st_mode)
        ):
            _fail("installed evidence directory identity differs from staging")
        source_recheck()
        _same_directory_binding(
            output_dir.parent, parent_metadata, subject="public evidence parent"
        )
        _verify_canonical_artifacts(
            installed_descriptor,
            expected_artifacts,
            subject="installed public evidence",
        )
        os.close(installed_descriptor)
        installed_descriptor = None
    except (OSError, SanitizationError, validator.EvidenceValidationError) as error:
        if staging_descriptor is not None:
            os.close(staging_descriptor)
            staging_descriptor = None
        if installed_descriptor is not None:
            os.close(installed_descriptor)
            installed_descriptor = None
        if installed:
            try:
                installed_metadata = os.stat(
                    output_name, dir_fd=parent_descriptor, follow_symlinks=False
                )
            except OSError:
                _fail("post-install evidence rollback target is unavailable")
            if (
                staging_metadata is None
                or installed_metadata.st_dev != staging_metadata.st_dev
                or installed_metadata.st_ino != staging_metadata.st_ino
                or not stat.S_ISDIR(installed_metadata.st_mode)
            ):
                _fail("post-install evidence rollback target changed identity")
            quarantine_name = _new_sibling_name(
                parent_descriptor, ".router-sanitize-rollback-"
            )
            _atomic_rename_exclusive(
                parent_descriptor, output_name, quarantine_name
            )
            installed = False
            os.fsync(parent_descriptor)
            if not _remove_owned_directory(
                parent_descriptor,
                quarantine_name,
                expected_files,
                require_complete=True,
            ):
                _fail("post-install source change rollback was not verifiable")
        else:
            try:
                staging_exists = stat.S_ISDIR(
                    os.stat(
                        staging_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    ).st_mode
                )
            except FileNotFoundError:
                staging_exists = False
            except OSError:
                staging_exists = True
            if staging_exists and not _remove_owned_directory(
                parent_descriptor,
                staging_name,
                expected_files,
                require_complete=False,
            ):
                _fail("evidence staging cleanup was not verifiable")
        if isinstance(error, SanitizationError):
            raise error
        _fail("public evidence installation failed validation or atomic installation")
    finally:
        if staging_descriptor is not None:
            os.close(staging_descriptor)
        if installed_descriptor is not None:
            os.close(installed_descriptor)
        os.close(parent_descriptor)
    return [
        output_dir / f"{record['experiment_id']}.json" for record in records
    ]


def sanitize_candidate_files(
    *,
    candidate_path: Path,
    environment_path: Path,
    output_dir: Path,
    repository_root: Path = REPOSITORY_ROOT,
    enforce_repository_state: bool = True,
) -> list[Path]:
    repository_descriptor = _open_directory_no_symlinks(
        repository_root, subject="repository root"
    )
    os.close(repository_descriptor)
    candidate_document = _read_secure_json(
        candidate_path,
        subject="router candidate",
        maximum_bytes=MAX_CANDIDATE_INPUT_BYTES,
    )
    environment_document = _read_secure_json(environment_path, subject="environment handoff")

    def source_recheck() -> None:
        _recheck_secure_document(candidate_document, subject="router candidate")
        _recheck_secure_document(environment_document, subject="environment handoff")
        if enforce_repository_state:
            head, dirty = _repository_state(repository_root)
            if dirty or head != candidate_document.value.get("source_commit"):
                _fail("repository is not the clean source commit recorded by the candidate")

    source_recheck()
    records = build_public_records(
        candidate_document.value,
        environment_document.value,
        source_candidate_sha256=candidate_document.sha256,
        repository_root=repository_root,
    )
    source_recheck()
    return _install_records_exclusively(
        records,
        output_dir,
        repository_root=repository_root,
        source_recheck=source_recheck,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        installed = sanitize_candidate_files(
            candidate_path=arguments.candidate,
            environment_path=arguments.environment,
            output_dir=arguments.output_dir,
        )
    except SanitizationError as error:
        print(f"sanitize-router-candidate: {error}", file=sys.stderr)
        return 1
    print(f"sanitize-router-candidate: wrote {len(installed)} validated public record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

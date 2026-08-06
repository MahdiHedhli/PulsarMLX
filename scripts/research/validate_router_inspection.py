#!/usr/bin/env python3
"""Fail-closed validation for one external read-only router inspection."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from dataclasses import dataclass
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
from typing import Any, Callable, Iterable, Mapping
import unicodedata


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = REPOSITORY_ROOT / "schemas/research/v1/router-inspection.schema.json"
MAX_CANDIDATE_BYTES = 512 * 1024
MAX_ENVIRONMENT_BYTES = 512 * 1024
MAX_SCHEMA_BYTES = 256 * 1024
MAX_JSON_NODES = 20_000
MAX_JSON_DEPTH = 48
MAX_ENVIRONMENT_AGE_SECONDS = 15 * 60
MAX_LOAD_PER_LOGICAL_CPU = 0.75
MODEL_REPOSITORY = "Qwen/Qwen3-30B-A3B-GGUF"
MODEL_REVISION = "e4d4bafdfb96a411a163846265362aceb0b9c63a"
MODEL_FILENAME = "Qwen3-30B-A3B-Q8_0.gguf"
MODEL_SIZE_BYTES = 32_483_931_648
MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
MODEL_LOCATION = f"<external-model>/{MODEL_FILENAME}"
MODEL_LICENSE = "Apache-2.0"
GGUF_DATA_OFFSET = 5_969_408
GGUF_TENSOR_COUNT = 579
GGUF_F32_COUNT = 241
GGUF_Q8_0_COUNT = 338
ROUTER_NAME = "blk.0.ffn_gate_inp.weight"
ROUTER_ELEMENTS = 262_144
ROUTER_BYTES = 1_048_576
MINIMUM_AVAILABLE_STORAGE_BYTES = 134_761_081_856
MINIMUM_UNIFIED_MEMORY_BYTES = 42_949_672_960
PRESENT_NORMALIZATION_SOURCE = "gguf:qwen3moe.expert_weights_norm"
ABSENT_NORMALIZATION_SOURCE = (
    "frozen-architecture-contract:"
    "qwen3moe.expert_weights_norm-default-true-key-absent"
)
EXPECTED_WARNINGS = [
    "The inherited Rust GGUF map does not independently retain duplicate metadata keys; "
    "the exact full-file SHA-256 and pinned artifact identity close this artifact-specific "
    "boundary.",
    "This read-only admission record is a candidate for T075 validation and is not "
    "execution evidence or a capability promotion.",
]
EXPECTED_EXCLUSIONS = [
    "No MLX runtime or worker process was initialized.",
    "No router projection, softmax, top-k selection, expert execution, model output, "
    "generation, serving, or benchmark was performed.",
    "No model or tensor bytes, decoded values, private paths, or machine identifiers are "
    "included in this record.",
]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
PRIVATE_PATH_RE = re.compile(
    r"(?:/Users/|/home/|/Volumes/|/private/|/tmp/|/var/folders/|"
    r"[A-Za-z]:\\Users\\)"
)
SECRET_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|"
    r"Bearer\s+[^\s'\"]+)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(
    r"(?i)(?<![a-z0-9._%+-])[a-z0-9._%+-]+@"
    r"[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![a-z0-9.-])"
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
FORBIDDEN_FIELDS = {
    "account",
    "account_id",
    "authorization",
    "command",
    "command_line",
    "cookie",
    "email",
    "email_address",
    "hardware_uuid",
    "home",
    "home_directory",
    "host",
    "host_name",
    "hostname",
    "ip_address",
    "mac_address",
    "machine_id",
    "machine_identifier",
    "password",
    "private_key",
    "process_command_line",
    "serial",
    "serial_number",
    "shell_history",
    "token",
    "user",
    "user_name",
    "username",
    "uuid",
    "volume_uuid",
}
SECRET_KEY_PARTS = {
    "auth",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "key",
    "password",
    "secret",
    "token",
}
ROOT_FIELDS = {
    "schema_version",
    "validation",
    "status",
    "passed",
    "recorded_at_utc",
    "source_commit",
    "source_worktree_clean_before_inspection",
    "source_worktree_clean_after_inspection",
    "artifact",
    "gguf",
    "router_tensor",
    "routing_semantics",
    "resource_admission",
    "execution",
    "warnings",
    "exclusions",
}

_ENVIRONMENT_PATH = Path(__file__).with_name("environment.py")
_ENVIRONMENT_SPEC = importlib.util.spec_from_file_location(
    "pulsarmlx_router_inspection_environment", _ENVIRONMENT_PATH
)
if _ENVIRONMENT_SPEC is None or _ENVIRONMENT_SPEC.loader is None:
    raise RuntimeError("research environment module is unavailable")
_ENVIRONMENT_MODULE = importlib.util.module_from_spec(_ENVIRONMENT_SPEC)
_ENVIRONMENT_SPEC.loader.exec_module(_ENVIRONMENT_MODULE)


@dataclass(frozen=True)
class SourceState:
    """Bounded source facts used by production validation and injected tests."""

    current_head: str
    worktree_clean: bool
    candidate_exists: bool


class InspectionValidationError(ValueError):
    """A bounded failure whose message never includes candidate values."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise InspectionValidationError(code, message)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_field", "validation input contains a duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    _fail("invalid_json_number", "validation input contains a non-finite JSON number")


def _reject_final_symlink(path: Path, *, subject: str) -> None:
    """Reject a link supplied as the object, while allowing canonical system aliases.

    macOS exposes standard temporary locations such as ``/tmp`` through a symbolic
    link.  Rejecting every link in the ancestry would therefore reject an otherwise
    regular candidate.  The caller resolves the parent chain before opening the
    file and uses ``O_NOFOLLOW`` plus descriptor identity checks for the final
    object.
    """

    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError:
        _fail("unsafe_path", f"{subject} path could not be inspected safely")
    if stat.S_ISLNK(metadata.st_mode):
        _fail("unsafe_path", f"{subject} must not be a symbolic link")


def _require_external_path(path: Path, *, subject: str, must_exist: bool) -> Path:
    if not path.is_absolute():
        _fail("unsafe_path", f"{subject} path must be absolute")
    _reject_final_symlink(path, subject=subject)
    try:
        resolved = path.resolve(strict=must_exist)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        resolved.relative_to(repository)
    except ValueError:
        return resolved
    except OSError:
        _fail("unsafe_path", f"{subject} path could not be resolved safely")
    _fail("unsafe_path", f"{subject} path must remain outside the repository")


def _read_regular_file(path: Path, *, maximum_bytes: int, subject: str) -> bytes:
    resolved = _require_external_path(path, subject=subject, must_exist=True)
    descriptor: int | None = None
    try:
        path_before = os.stat(resolved, follow_symlinks=False)
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        descriptor = os.open(resolved, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
            _fail("unsafe_input", f"{subject} must be a nonempty regular file")
        if (path_before.st_dev, path_before.st_ino) != (before.st_dev, before.st_ino):
            _fail("changed_input", f"{subject} changed before it was opened")
        if before.st_size > maximum_bytes:
            _fail("bounded_input", f"{subject} exceeds its byte bound")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                _fail("bounded_input", f"{subject} exceeds its byte bound")
        after = os.fstat(descriptor)
        path_after = os.stat(resolved, follow_symlinks=False)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ) or total != before.st_size:
            _fail("changed_input", f"{subject} changed while being read")
        if (after.st_dev, after.st_ino, after.st_size) != (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
        ):
            _fail("changed_input", f"{subject} changed while being read")
        return b"".join(chunks)
    except InspectionValidationError:
        raise
    except OSError:
        _fail("unsafe_input", f"{subject} could not be read safely")
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _read_schema(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            _fail("schema_violation", "router inspection schema is unavailable")
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_SCHEMA_BYTES:
            _fail("schema_violation", "router inspection schema is invalid or oversized")
        schema = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except InspectionValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail("schema_violation", "router inspection schema is invalid")
    if not isinstance(schema, dict):
        _fail("schema_violation", "router inspection schema root is invalid")
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or set(schema.get("required", [])) != ROOT_FIELDS
        or set(schema.get("properties", {})) != ROOT_FIELDS
    ):
        _fail("schema_violation", "router inspection schema is not closed or synchronized")
    return schema


def _bounded_structure(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail("bounded_input", "inspection candidate exceeds its structural bound")
        if isinstance(current, dict):
            pending.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def _load_json_object(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_file(
        path,
        maximum_bytes=maximum_bytes,
        subject=subject,
    )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except InspectionValidationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        _fail("invalid_json", f"{subject} is invalid JSON")
    if not isinstance(value, dict):
        _fail("schema_violation", f"{subject} root must be an object")
    _bounded_structure(value)
    return value, raw


def _load_candidate(path: Path) -> tuple[dict[str, Any], bytes]:
    return _load_json_object(
        path,
        maximum_bytes=MAX_CANDIDATE_BYTES,
        subject="router inspection candidate",
    )


def _load_environment(path: Path) -> tuple[dict[str, Any], bytes]:
    return _load_json_object(
        path,
        maximum_bytes=MAX_ENVIRONMENT_BYTES,
        subject="Feature 002 environment snapshot",
    )


def _normalized_key(key: str) -> str:
    words = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", words)
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_")


def _walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                yield key, child
                pending.append(child)
        elif isinstance(current, list):
            for child in current:
                yield None, child
                pending.append(child)


def _validate_public_safety(candidate: dict[str, Any]) -> None:
    for key, value in _walk(candidate):
        if key is not None:
            normalized = _normalized_key(key)
            parts = set(normalized.split("_"))
            if normalized in FORBIDDEN_FIELDS:
                _fail("public_safety", "inspection candidate contains a private identifier field")
            if parts & SECRET_KEY_PARTS:
                _fail("public_safety", "inspection candidate contains a secret-shaped field")
        if isinstance(value, float) and not math.isfinite(value):
            _fail("public_safety", "inspection candidate contains a non-finite value")
        if isinstance(value, str):
            if (
                "\x00" in value
                or value.startswith("/")
                or value.startswith("~/")
                or PRIVATE_PATH_RE.search(value)
                or SECRET_RE.search(value)
                or EMAIL_RE.search(value)
                or UUID_RE.search(value)
                or MAC_RE.search(value)
                or IPV4_RE.search(value)
            ):
                _fail("public_safety", "inspection candidate contains a non-public value")


def _closed_object(value: Any, fields: set[str], *, subject: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail("schema_violation", f"{subject} object is not closed and complete")
    return value


def _exact(value: Any, expected: Any, *, subject: str) -> None:
    if type(value) is not type(expected) or value != expected:
        _fail("semantic_mismatch", f"{subject} does not match the frozen contract")


def _plain_int(value: Any, *, subject: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail("schema_violation", f"{subject} is not a bounded integer")
    return value


def _finite_number(value: Any, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("schema_violation", f"{subject} is not a number")
    result = float(value)
    if not math.isfinite(result):
        _fail("schema_violation", f"{subject} is not finite")
    return result


def _bounded_text_list(value: Any, *, subject: str, minimum: int) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= 16:
        _fail("schema_violation", f"{subject} list is invalid")
    seen: set[str] = set()
    for item in value:
        if (
            not isinstance(item, str)
            or not item
            or item.strip() != item
            or len(item) > 512
            or any(
                unicodedata.category(character) in {"Cc", "Cf", "Cs"}
                for character in item
            )
            or item in seen
        ):
            _fail("schema_violation", f"{subject} list is invalid")
        seen.add(item)
    return value


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _fail("schema_violation", "inspection timestamp is not canonical UTC")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("schema_violation", "inspection timestamp is invalid")
    if parsed.year < 2020:
        _fail("semantic_mismatch", "inspection timestamp predates the admitted workflow")


def _validate_typed_metadata(
    value: Any,
    *,
    expected_type: str,
    expected_value: Any,
    subject: str,
) -> None:
    item = _closed_object(value, {"type", "value"}, subject=subject)
    _exact(item["type"], expected_type, subject=f"{subject} type")
    _exact(item["value"], expected_value, subject=f"{subject} value")


def _validate_optional_scale(value: Any) -> None:
    item = _closed_object(
        value,
        {"present", "type", "value", "effective_value"},
        subject="router scale metadata",
    )
    if type(item["present"]) is not bool:
        _fail("schema_violation", "router scale presence is invalid")
    if _finite_number(item["effective_value"], subject="effective router scale") != 1.0:
        _fail("semantic_mismatch", "effective router scale differs from 1.0")
    if item["present"]:
        _exact(item["type"], "FLOAT32", subject="router scale metadata type")
        if _finite_number(item["value"], subject="router scale metadata value") != 1.0:
            _fail("semantic_mismatch", "router scale metadata differs from 1.0")
    elif item["type"] is not None or item["value"] is not None:
        _fail("semantic_mismatch", "absent router scale metadata carries a value")


def _validate_optional_normalization(value: Any) -> bool:
    item = _closed_object(
        value,
        {"present", "type", "value", "effective_value"},
        subject="router normalization metadata",
    )
    if type(item["present"]) is not bool or item["effective_value"] is not True:
        _fail("semantic_mismatch", "effective router normalization is not true")
    if item["present"]:
        _exact(item["type"], "BOOL", subject="router normalization metadata type")
        if item["value"] is not True:
            _fail("semantic_mismatch", "router normalization metadata is not true")
    elif item["type"] is not None or item["value"] is not None:
        _fail("semantic_mismatch", "absent router normalization metadata carries a value")
    return item["present"]


def _validate_artifact(value: Any) -> dict[str, Any]:
    fields = {
        "repository_id",
        "revision",
        "filename",
        "license_spdx",
        "size_bytes",
        "sha256",
        "location_symbolic",
        "stored_outside_repository",
        "read_only",
        "automatic_download",
        "identity_rechecked_after_inspection",
    }
    artifact = _closed_object(value, fields, subject="artifact")
    expected = {
        "repository_id": MODEL_REPOSITORY,
        "revision": MODEL_REVISION,
        "filename": MODEL_FILENAME,
        "license_spdx": MODEL_LICENSE,
        "size_bytes": MODEL_SIZE_BYTES,
        "sha256": MODEL_SHA256,
        "location_symbolic": MODEL_LOCATION,
        "stored_outside_repository": True,
        "read_only": True,
        "automatic_download": False,
        "identity_rechecked_after_inspection": True,
    }
    for field, expected_value in expected.items():
        _exact(artifact[field], expected_value, subject=f"artifact {field}")
    return artifact


def _validate_gguf(value: Any) -> tuple[dict[str, Any], bool]:
    gguf = _closed_object(
        value,
        {"version", "endianness", "data_offset", "tensor_count", "tensor_type_counts", "metadata"},
        subject="GGUF",
    )
    for field, expected in {
        "version": 3,
        "endianness": "little",
        "data_offset": GGUF_DATA_OFFSET,
        "tensor_count": GGUF_TENSOR_COUNT,
    }.items():
        _exact(gguf[field], expected, subject=f"GGUF {field}")
    counts = _closed_object(
        gguf["tensor_type_counts"], {"F32", "Q8_0"}, subject="GGUF tensor counts"
    )
    _exact(counts["F32"], GGUF_F32_COUNT, subject="GGUF F32 tensor count")
    _exact(counts["Q8_0"], GGUF_Q8_0_COUNT, subject="GGUF Q8_0 tensor count")
    metadata_fields = {
        "general.architecture",
        "qwen3moe.embedding_length",
        "qwen3moe.expert_feed_forward_length",
        "qwen3moe.expert_count",
        "qwen3moe.expert_used_count",
        "qwen3moe.expert_weights_scale",
        "qwen3moe.expert_weights_norm",
    }
    metadata = _closed_object(gguf["metadata"], metadata_fields, subject="GGUF metadata")
    _validate_typed_metadata(
        metadata["general.architecture"],
        expected_type="STRING",
        expected_value="qwen3moe",
        subject="GGUF architecture metadata",
    )
    _validate_typed_metadata(
        metadata["qwen3moe.embedding_length"],
        expected_type="UINT32",
        expected_value=2048,
        subject="GGUF embedding metadata",
    )
    _validate_typed_metadata(
        metadata["qwen3moe.expert_feed_forward_length"],
        expected_type="UINT32",
        expected_value=768,
        subject="GGUF expert feed-forward metadata",
    )
    _validate_typed_metadata(
        metadata["qwen3moe.expert_count"],
        expected_type="UINT32",
        expected_value=128,
        subject="GGUF expert-count metadata",
    )
    _validate_typed_metadata(
        metadata["qwen3moe.expert_used_count"],
        expected_type="UINT32",
        expected_value=8,
        subject="GGUF top-k metadata",
    )
    _validate_optional_scale(metadata["qwen3moe.expert_weights_scale"])
    normalization_present = _validate_optional_normalization(
        metadata["qwen3moe.expert_weights_norm"]
    )
    return gguf, normalization_present


def _validate_router_tensor(value: Any, *, gguf: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "name",
        "semantic_role",
        "occurrence_count",
        "gguf_dimensions_fastest_axis_first",
        "reader_shape",
        "execution_shape",
        "gguf_type",
        "quantization",
        "logical_elements",
        "relative_data_offset",
        "absolute_data_offset",
        "encoded_length_bytes",
        "exclusive_end_offset",
        "encoded_range_sha256",
        "byte_order",
        "orientation",
        "finite_f32_values_verified",
        "finite_element_count",
    }
    tensor = _closed_object(value, fields, subject="router tensor")
    expected = {
        "name": ROUTER_NAME,
        "semantic_role": "layer_0_router_projection",
        "occurrence_count": 1,
        "gguf_dimensions_fastest_axis_first": [2048, 128],
        "reader_shape": [128, 2048],
        "execution_shape": [128, 2048],
        "gguf_type": "F32",
        "quantization": "none_f32",
        "logical_elements": ROUTER_ELEMENTS,
        "encoded_length_bytes": ROUTER_BYTES,
        "byte_order": "little",
        "orientation": "expert_major_rows_input_columns",
        "finite_f32_values_verified": True,
        "finite_element_count": ROUTER_ELEMENTS,
    }
    for field, expected_value in expected.items():
        _exact(tensor[field], expected_value, subject=f"router tensor {field}")
    relative = _plain_int(
        tensor["relative_data_offset"], subject="router relative offset", minimum=0
    )
    absolute = _plain_int(
        tensor["absolute_data_offset"], subject="router absolute offset", minimum=1
    )
    end = _plain_int(tensor["exclusive_end_offset"], subject="router range end", minimum=1)
    if absolute != gguf["data_offset"] + relative:
        _fail("invalid_tensor_range", "router absolute and relative offsets disagree")
    if end != absolute + ROUTER_BYTES or end > MODEL_SIZE_BYTES:
        _fail("invalid_tensor_range", "router tensor range is outside the immutable artifact")
    tensor_hash = tensor["encoded_range_sha256"]
    if not isinstance(tensor_hash, str) or not SHA256_RE.fullmatch(tensor_hash):
        _fail("schema_violation", "router tensor range hash is invalid")
    return tensor


def _validate_routing_semantics(value: Any, *, normalization_present: bool) -> None:
    fields = {
        "expert_count",
        "selected_expert_count",
        "weight_scale",
        "bias_present",
        "bias_occurrence_count",
        "correction_bias_present",
        "correction_bias_occurrence_count",
        "unexpected_router_alias_occurrence_count",
        "full_softmax",
        "selected_probability_renormalization",
        "normalization_source",
    }
    routing = _closed_object(value, fields, subject="routing semantics")
    expected = {
        "expert_count": 128,
        "selected_expert_count": 8,
        "weight_scale": 1.0,
        "bias_present": False,
        "bias_occurrence_count": 0,
        "correction_bias_present": False,
        "correction_bias_occurrence_count": 0,
        "unexpected_router_alias_occurrence_count": 0,
        "full_softmax": True,
        "selected_probability_renormalization": True,
        "normalization_source": (
            PRESENT_NORMALIZATION_SOURCE if normalization_present else ABSENT_NORMALIZATION_SOURCE
        ),
    }
    for field, expected_value in expected.items():
        _exact(routing[field], expected_value, subject=f"routing {field}")


def _validate_resources(value: Any) -> dict[str, Any]:
    fields = {
        "available_disk_bytes",
        "required_disk_bytes",
        "disk_headroom_satisfied",
        "host_unified_memory_bytes",
        "required_host_bytes",
        "unified_memory_headroom_satisfied",
        "system_pressure",
        "memory_pressure_normal",
    }
    resources = _closed_object(value, fields, subject="resource admission")
    available = _plain_int(
        resources["available_disk_bytes"], subject="available disk", minimum=1
    )
    required_disk = _plain_int(
        resources["required_disk_bytes"], subject="required disk", minimum=1
    )
    memory = _plain_int(
        resources["host_unified_memory_bytes"], subject="unified memory", minimum=1
    )
    required_memory = _plain_int(
        resources["required_host_bytes"], subject="required unified memory", minimum=1
    )
    if (
        required_disk != MINIMUM_AVAILABLE_STORAGE_BYTES
        or available < required_disk
        or resources["disk_headroom_satisfied"] is not True
        or required_memory != MINIMUM_UNIFIED_MEMORY_BYTES
        or memory < required_memory
        or resources["unified_memory_headroom_satisfied"] is not True
        or resources["system_pressure"] != "normal"
        or resources["memory_pressure_normal"] is not True
    ):
        _fail("resource_admission", "router inspection resource admission did not pass")
    return resources


def _validate_execution(value: Any) -> None:
    fields = {
        "performed",
        "worker_spawned",
        "mlx_initialized",
        "router_projection_performed",
        "router_output_produced",
        "expert_execution_performed",
        "network_access_performed",
        "automatic_download_performed",
    }
    execution = _closed_object(value, fields, subject="execution")
    if any(type(execution[field]) is not bool or execution[field] for field in fields):
        _fail("execution_boundary", "router inspection record claims forbidden execution")


def _validate_exclusions(warnings: Any, exclusions: Any) -> None:
    warning_values = _bounded_text_list(warnings, subject="warning", minimum=1)
    exclusion_values = _bounded_text_list(exclusions, subject="exclusion", minimum=3)
    if warning_values != EXPECTED_WARNINGS or exclusion_values != EXPECTED_EXCLUSIONS:
        _fail("claim_boundary", "inspection claim-boundary text differs from the contract")


def validate_candidate(candidate: dict[str, Any], *, candidate_sha256: str) -> dict[str, Any]:
    """Validate one decoded candidate and return a bounded public report."""

    _validate_public_safety(candidate)
    _closed_object(candidate, ROOT_FIELDS, subject="inspection candidate")
    _exact(candidate["schema_version"], 1, subject="inspection schema version")
    _exact(
        candidate["validation"],
        "qwen3moe-layer0-router-read-only-inspection",
        subject="inspection validation identity",
    )
    _exact(candidate["status"], "admitted_observed", subject="inspection status")
    _exact(candidate["passed"], True, subject="inspection pass state")
    _validate_timestamp(candidate["recorded_at_utc"])
    source_commit = candidate["source_commit"]
    if not isinstance(source_commit, str) or not COMMIT_RE.fullmatch(source_commit):
        _fail("source_identity", "inspection source commit is not a full immutable commit")
    _exact(
        candidate["source_worktree_clean_before_inspection"],
        True,
        subject="inspection source worktree state",
    )
    _exact(
        candidate["source_worktree_clean_after_inspection"],
        True,
        subject="post-inspection source worktree state",
    )
    artifact = _validate_artifact(candidate["artifact"])
    gguf, normalization_present = _validate_gguf(candidate["gguf"])
    tensor = _validate_router_tensor(candidate["router_tensor"], gguf=gguf)
    _validate_routing_semantics(
        candidate["routing_semantics"], normalization_present=normalization_present
    )
    resources = _validate_resources(candidate["resource_admission"])
    _validate_execution(candidate["execution"])
    _validate_exclusions(candidate["warnings"], candidate["exclusions"])
    if not SHA256_RE.fullmatch(candidate_sha256):
        _fail("candidate_identity", "inspection candidate hash is invalid")
    return {
        "schema_version": 1,
        "validation": "qwen3moe-layer0-router-inspection-candidate-validation",
        "status": "passed",
        "passed": True,
        "candidate_sha256": candidate_sha256,
        "source_commit": source_commit,
        "artifact": {
            "repository_id": artifact["repository_id"],
            "revision": artifact["revision"],
            "filename": artifact["filename"],
            "size_bytes": artifact["size_bytes"],
            "sha256": artifact["sha256"],
            "license_spdx": artifact["license_spdx"],
        },
        "router_tensor": {
            "name": tensor["name"],
            "absolute_data_offset": tensor["absolute_data_offset"],
            "encoded_length_bytes": tensor["encoded_length_bytes"],
            "exclusive_end_offset": tensor["exclusive_end_offset"],
            "encoded_range_sha256": tensor["encoded_range_sha256"],
        },
        "resource_admission": {
            "disk_headroom_satisfied": resources["disk_headroom_satisfied"],
            "unified_memory_headroom_satisfied": resources[
                "unified_memory_headroom_satisfied"
            ],
            "memory_pressure_normal": resources["memory_pressure_normal"],
        },
        "execution_boundary": {
            "mlx_initialized": False,
            "router_projection_performed": False,
            "router_output_produced": False,
        },
        "public_safe": True,
    }


SourceStateProvider = Callable[[str], SourceState]
NowProvider = Callable[[], datetime]


def _observe_source_state(
    candidate_commit: str,
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> SourceState:
    """Observe a clean current HEAD and candidate existence without a shell."""

    if not COMMIT_RE.fullmatch(candidate_commit):
        _fail("source_identity", "inspection source commit is not canonical")
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        candidate = subprocess.run(
            ["git", "cat-file", "-e", f"{candidate_commit}^{{commit}}"],
            cwd=repository_root,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        _fail("source_identity", "source repository state could not be observed safely")
    try:
        current_head = head.stdout.decode("ascii").strip()
    except UnicodeError:
        _fail("source_identity", "current source commit is malformed")
    if head.returncode != 0 or not COMMIT_RE.fullmatch(current_head):
        _fail("source_identity", "current source commit is unavailable")
    if status.returncode != 0:
        _fail("source_identity", "source worktree state is unavailable")
    return SourceState(
        current_head=current_head,
        worktree_clean=not status.stdout,
        candidate_exists=candidate.returncode == 0,
    )


def _validate_source_state(candidate_commit: str, state: SourceState) -> None:
    if (
        not isinstance(state, SourceState)
        or not COMMIT_RE.fullmatch(state.current_head)
        or type(state.worktree_clean) is not bool
        or type(state.candidate_exists) is not bool
    ):
        _fail("source_identity", "source-state observation is invalid")
    if not state.candidate_exists:
        _fail("source_identity", "inspection source commit does not exist locally")
    if not state.worktree_clean:
        _fail("source_identity", "inspection validation requires a clean source worktree")
    if state.current_head != candidate_commit:
        _fail("source_identity", "inspection source commit is not the current HEAD")


def _observed_environment_value(snapshot: Mapping[str, Any], name: str) -> Any:
    observations = snapshot.get("observations")
    if not isinstance(observations, Mapping):
        _fail("environment_snapshot", "environment observations are unavailable")
    observation = observations.get(name)
    if not isinstance(observation, Mapping) or observation.get("status") != "observed":
        _fail("environment_snapshot", "a required environment observation is unavailable")
    return observation.get("value")


def _parse_environment_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("environment_snapshot", "environment timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except (OverflowError, ValueError):
        _fail("environment_snapshot", "environment timestamp is invalid")
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("environment_snapshot", "environment timestamp is not UTC")
    return parsed.astimezone(timezone.utc)


def _validate_environment_snapshot(
    snapshot: dict[str, Any],
    *,
    raw_sha256: str,
    candidate_commit: str,
    candidate_recorded_at: str,
    validation_time: datetime,
) -> dict[str, Any]:
    try:
        _ENVIRONMENT_MODULE.validate_environment_snapshot(snapshot, capture_phase="before")
    except (
        _ENVIRONMENT_MODULE.EnvironmentCollectionError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ):
        _fail("environment_snapshot", "Feature 002 environment snapshot is invalid")
    if (
        snapshot.get("interference_admission") != "admitted"
        or snapshot.get("admission_reasons") != []
        or snapshot.get("storage_role") != "model_storage"
        or snapshot.get("storage_locator") != "$PULSARMLX_MODEL_STORAGE_ROOT"
    ):
        _fail("environment_snapshot", "Feature 002 environment admission did not pass")

    environment_commit = _observed_environment_value(snapshot, "repository_commit")
    pulsarmlx_version = _observed_environment_value(snapshot, "pulsarmlx_version")
    worktree_dirty = _observed_environment_value(snapshot, "worktree_dirty")
    workload = _observed_environment_value(snapshot, "workload_category")
    material_workload = _observed_environment_value(
        snapshot, "material_concurrent_workload"
    )
    thermal = _observed_environment_value(snapshot, "thermal_state")
    observations = snapshot.get("observations")
    if not isinstance(observations, Mapping):
        _fail("environment_snapshot", "environment observations are unavailable")
    power_observation = observations.get("power_mode")
    if not isinstance(power_observation, Mapping):
        _fail("environment_snapshot", "environment power-mode observation is invalid")
    if power_observation.get("status") == "observed":
        if power_observation.get("value") != "automatic":
            _fail("environment_snapshot", "environment power admission did not pass")
        power_summary: dict[str, Any] = {
            "status": "observed",
            "value": "automatic",
        }
    elif power_observation.get("status") == "unavailable":
        power_summary = {
            "status": "unavailable",
            "reason": power_observation.get("reason"),
            "attempted_method": power_observation.get("attempted_method"),
        }
    else:
        _fail("environment_snapshot", "environment power-mode observation is invalid")
    logical_cpus = _observed_environment_value(snapshot, "logical_cpu_count")
    captured_at = _observed_environment_value(snapshot, "captured_at_utc")
    loads = {
        name: _observed_environment_value(snapshot, name)
        for name in ("load_average_1m", "load_average_5m", "load_average_15m")
    }
    if (
        environment_commit != candidate_commit
        or pulsarmlx_version != candidate_commit
        or worktree_dirty is not False
    ):
        _fail("environment_snapshot", "environment source identity differs from the candidate")
    if workload != "none" or material_workload is not False:
        _fail("environment_snapshot", "environment reports a concurrent material workload")
    if thermal != "nominal":
        _fail("environment_snapshot", "environment thermal admission did not pass")
    if type(logical_cpus) is not int or logical_cpus <= 0:
        _fail("environment_snapshot", "environment logical CPU count is invalid")
    maximum_load = logical_cpus * MAX_LOAD_PER_LOGICAL_CPU
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
        or value > maximum_load
        for value in loads.values()
    ):
        _fail("environment_snapshot", "environment load admission did not pass")

    candidate_time = datetime.strptime(
        candidate_recorded_at, "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=timezone.utc)
    environment_time = _parse_environment_timestamp(captured_at)
    if not isinstance(validation_time, datetime) or validation_time.tzinfo is None:
        _fail("environment_snapshot", "validation clock is not timezone-aware")
    validation_time = validation_time.astimezone(timezone.utc)
    environment_to_candidate = (candidate_time - environment_time).total_seconds()
    candidate_to_validation = (validation_time - candidate_time).total_seconds()
    if not 0 <= environment_to_candidate <= MAX_ENVIRONMENT_AGE_SECONDS:
        _fail("environment_snapshot", "environment snapshot does not freshly precede candidate")
    if not 0 <= candidate_to_validation <= MAX_ENVIRONMENT_AGE_SECONDS:
        _fail("environment_snapshot", "inspection candidate is stale or future-dated")
    if not SHA256_RE.fullmatch(raw_sha256):
        _fail("environment_snapshot", "environment snapshot hash is invalid")

    summary = {
        "sha256": raw_sha256,
        "snapshot_schema": snapshot["snapshot_schema"],
        "snapshot_schema_version": snapshot["snapshot_schema_version"],
        "capture_phase": snapshot["capture_phase"],
        "captured_at_utc": captured_at,
        "storage_role": snapshot["storage_role"],
        "storage_locator": snapshot["storage_locator"],
        "source_commit": environment_commit,
        "interference_admission": snapshot["interference_admission"],
        "workload_category": workload,
        "material_concurrent_workload": material_workload,
        "thermal_state": thermal,
        "power_mode": power_summary,
        "logical_cpu_count": logical_cpus,
        **loads,
    }
    try:
        _ENVIRONMENT_MODULE.assert_public_safe(summary)
    except _ENVIRONMENT_MODULE.EnvironmentCollectionError:
        _fail("environment_snapshot", "environment validation summary is not public-safe")
    return summary


def validate_file(
    candidate_path: Path,
    *,
    environment_path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
    source_state_provider: SourceStateProvider | None = None,
    now_provider: NowProvider | None = None,
) -> dict[str, Any]:
    """Read and validate one external candidate without accessing a model."""

    _read_schema(schema_path)
    candidate, raw = _load_candidate(candidate_path)
    report = validate_candidate(candidate, candidate_sha256=hashlib.sha256(raw).hexdigest())
    provider = source_state_provider or _observe_source_state
    _validate_source_state(report["source_commit"], provider(report["source_commit"]))
    candidate_resolved = _require_external_path(
        candidate_path, subject="router inspection candidate", must_exist=True
    )
    environment_resolved = _require_external_path(
        environment_path, subject="Feature 002 environment snapshot", must_exist=True
    )
    if candidate_resolved == environment_resolved:
        _fail("unsafe_path", "candidate and environment snapshot must be distinct")
    environment, environment_raw = _load_environment(environment_path)
    environment_summary = _validate_environment_snapshot(
        environment,
        raw_sha256=hashlib.sha256(environment_raw).hexdigest(),
        candidate_commit=report["source_commit"],
        candidate_recorded_at=candidate["recorded_at_utc"],
        validation_time=(now_provider or (lambda: datetime.now(timezone.utc)))(),
    )
    report["environment_snapshot"] = environment_summary
    return report


def _write_exclusive(
    path: Path,
    report: dict[str, Any],
    *,
    input_paths: tuple[Path, ...],
) -> None:
    resolved = _require_external_path(path, subject="validation report", must_exist=False)
    if path.suffix != ".json":
        _fail("unsafe_output", "validation report must name a JSON file")
    for input_path in input_paths:
        input_resolved = _require_external_path(
            input_path, subject="validation input", must_exist=True
        )
        if resolved == input_resolved:
            _fail("unsafe_output", "validation report must be distinct from its inputs")
    parent = resolved.parent
    try:
        metadata = os.lstat(parent)
    except OSError:
        _fail("unsafe_output", "validation report parent is unavailable")
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        _fail("unsafe_output", "validation report parent is unsafe")
    content = (json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()
    temporary_name = (
        f".router-inspection-validation.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    output_name = resolved.name
    directory_descriptor: int | None = None
    file_descriptor: int | None = None
    temporary_created = False
    installed = False
    completed = False
    try:
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory_descriptor = os.open(parent, directory_flags)
        opened_parent = os.fstat(directory_descriptor)
        path_parent = os.stat(parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened_parent.st_mode)
            or (opened_parent.st_dev, opened_parent.st_ino)
            != (metadata.st_dev, metadata.st_ino)
            or (opened_parent.st_dev, opened_parent.st_ino)
            != (path_parent.st_dev, path_parent.st_ino)
        ):
            _fail("unsafe_output", "validation report parent identity changed")
        try:
            os.stat(output_name, dir_fd=directory_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _fail("unsafe_output", "validation report already exists")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        file_descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        temporary_created = True
        view = memoryview(content)
        while view:
            written = os.write(file_descriptor, view)
            if written <= 0:
                _fail("unsafe_output", "validation report write made no progress")
            view = view[written:]
        os.fsync(file_descriptor)
        os.close(file_descriptor)
        file_descriptor = None
        os.link(
            temporary_name,
            output_name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        installed = True
        os.unlink(temporary_name, dir_fd=directory_descriptor)
        temporary_created = False
        os.fsync(directory_descriptor)
        final_parent = os.stat(parent, follow_symlinks=False)
        if (opened_parent.st_dev, opened_parent.st_ino) != (
            final_parent.st_dev,
            final_parent.st_ino,
        ):
            _fail("unsafe_output", "validation report parent identity changed")
        completed = True
    except FileExistsError:
        _fail("unsafe_output", "validation report already exists")
    except InspectionValidationError:
        raise
    except OSError:
        _fail("unsafe_output", "validation report could not be written safely")
    finally:
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        if temporary_created and directory_descriptor is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except OSError:
                pass
        if installed and not completed and directory_descriptor is not None:
            try:
                os.unlink(output_name, dir_fd=directory_descriptor)
                os.fsync(directory_descriptor)
            except OSError:
                pass
        if directory_descriptor is not None:
            try:
                os.close(directory_descriptor)
            except OSError:
                pass
    if not completed:
        _fail("unsafe_output", "validation report was not installed atomically")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a bounded external read-only router inspection candidate."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output", type=Path)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    source_state_provider: SourceStateProvider | None = None,
    now_provider: NowProvider | None = None,
) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate_file(
            arguments.input,
            environment_path=arguments.environment,
            schema_path=arguments.schema,
            source_state_provider=source_state_provider,
            now_provider=now_provider,
        )
        if arguments.output is None:
            print(json.dumps(report, allow_nan=False, sort_keys=True))
        else:
            _write_exclusive(
                arguments.output,
                report,
                input_paths=(arguments.input, arguments.environment),
            )
            print(
                json.dumps(
                    {
                        "passed": True,
                        "status": "validation_report_written",
                        "candidate_sha256": report["candidate_sha256"],
                    },
                    sort_keys=True,
                )
            )
        return 0
    except InspectionValidationError as error:
        print(
            json.dumps(
                {"passed": False, "code": error.code, "message": error.message},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

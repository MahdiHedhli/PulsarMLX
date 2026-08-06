#!/usr/bin/env python3
"""Publish the bounded public projection of a verified Feature 002 CPU oracle."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
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
from typing import Any

import router_oracle
from publish_evidence import PublicationError, _reject_non_public_values


PUBLICATION_ID = "f002-router-oracle-freeze-0001"
PUBLICATION_SCHEMA = "pulsarmlx.research.router-oracle-publication"
PUBLICATION_SCHEMA_VERSION = "1.0.0"
MANIFEST_SCHEMA = "pulsarmlx.research.router-oracle-publication-manifest"
MANIFEST_SCHEMA_VERSION = "1.0.0"
FEATURE_ID = "002-qwen-router-parity"
FIXTURE_RECORD_RELATIVE = Path(
    "fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json"
)
RAW_RECORD_RELATIVE = Path(
    "docs/research/raw/002-router-parity/oracle/f002-router-oracle-freeze-0001.json"
)
MANIFEST_RELATIVE = Path("fixtures/research/router-v1/real/manifest.json")
MODEL_MANIFEST_RELATIVE = Path("docs/research/MODEL_MANIFEST.json")
VERIFIER_RELATIVE = Path("scripts/research/verify_package.py")
PUBLISHER_RELATIVE = Path("scripts/research/oracle_publication.py")
PROJECTION_COMMAND = (
    "python3 scripts/research/oracle_publication.py "
    "--oracle-candidate $PULSARMLX_ORACLE_OUTPUT"
)

PINNED_MODEL_REPOSITORY = "Qwen/Qwen3-30B-A3B-GGUF"
PINNED_MODEL_REVISION = "e4d4bafdfb96a411a163846265362aceb0b9c63a"
PINNED_MODEL_FILENAME = "Qwen3-30B-A3B-Q8_0.gguf"
PINNED_MODEL_SIZE = 32_483_931_648
PINNED_MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
PINNED_TENSOR_SHA256 = "98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c"
PINNED_ORACLE_REVISION = "b06aa774c03dbbb624e726664b714a57d1f49815"
PINNED_ORACLE_CANDIDATE_SHA256 = (
    "b27ab74a539b06bfdd48f9be5c4353d7987a972448cac74fb959c48f783d8b6a"
)
PINNED_ORACLE_MANIFEST_SHA256 = (
    "14cfa011aa621ab64d016469521d4e2bad8c18fd88708728ad2728de54bdd7f6"
)
PINNED_ORACLE_DOCUMENT_SHA256 = (
    "e31e4337ddf2c7cf1bb6cfe721428e6baaeffec7e29aee0f77727969e756e645"
)
PINNED_INPUT_SHA256 = "978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7"
PINNED_OUTPUT_SHA256 = "eba36f9149b61f0d408de3ec5ad6ba73d1ff45b98867a4da56cfc586109ee93f"
PINNED_NUMPY_LOGITS_SHA256 = (
    "2bc2f956689239c1d375b0cbea50b432f1b48df95f35478cf04151f138e2c3f4"
)
PINNED_NUMPY_MAXIMUM_ABSOLUTE_ERROR = 1.430511474609375e-06
PINNED_NUMPY_MAXIMUM_RELATIVE_ERROR = 2.903159876627318e-07
PINNED_CAPTURE_PROVENANCE_SHA256 = (
    "8f5756dae12521afa6651251c25046b3db7cc77de47d27790eb3e17384afbba6"
)
ORACLE_GENERATION_COMMAND = (
    "python3 scripts/research/router_oracle.py --model $PULSARMLX_MODEL_GGUF "
    "--source-dir $PULSARMLX_LLAMA_CPP --capture-a $PULSARMLX_CAPTURE_A "
    "--capture-a-record $PULSARMLX_CAPTURE_A_RECORD --capture-a-scheduler-trace "
    "$PULSARMLX_CAPTURE_A_SCHEDULER_TRACE --capture-b $PULSARMLX_CAPTURE_B "
    "--capture-b-record $PULSARMLX_CAPTURE_B_RECORD --capture-b-scheduler-trace "
    "$PULSARMLX_CAPTURE_B_SCHEDULER_TRACE --capture-provenance "
    "$PULSARMLX_CAPTURE_PROVENANCE --output $PULSARMLX_ROUTER_ORACLE"
)
ORACLE_INDEPENDENCE = (
    "scalar CPU implementation; no MLX or PulsarMLX worker import or call"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_RECORD_BYTES = 1024 * 1024
MAX_JSON_NODES = 20_000
MAX_JSON_DEPTH = 32

UNSUPPORTED = [
    "expert execution",
    "routed MoE aggregation",
    "complete layer or model inference",
    "generation or serving",
]
FORBIDDEN_FIELDS = {
    "device",
    "inode",
    "runtime_identity",
    "consumer_proofs",
    "admitted_model",
    "model_before",
    "model_after",
    "helper_before",
    "helper_after",
    "router_weight_bytes",
    "tensor_bytes",
    "model_bytes",
    "process_command_line",
}


class OraclePublicationError(ValueError):
    """A bounded publication failure safe to expose to the operator."""


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _closed(value: Any, fields: set[str], *, subject: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise OraclePublicationError(f"{subject} contract differs")
    return value


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        result = (json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise OraclePublicationError("public oracle is not bounded JSON") from error
    if not result or len(result) > MAX_RECORD_BYTES:
        raise OraclePublicationError("public oracle exceeds its byte bound")
    return result


def _read_regular(path: Path, *, maximum: int, subject: str) -> bytes:
    _reject_symlink_components(path)
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise OraclePublicationError(f"{subject} is unsafe or oversized")
        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, 64 * 1024):
            size += len(chunk)
            if size > maximum:
                raise OraclePublicationError(f"{subject} is unsafe or oversized")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        raw = b"".join(chunks)
        if (
            size != before.st_size
            or len(raw) != before.st_size
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
        ):
            raise OraclePublicationError(f"{subject} changed while read")
        return raw
    except OraclePublicationError:
        raise
    except OSError as error:
        raise OraclePublicationError(f"{subject} is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _json_bytes(raw: bytes, *, subject: str) -> dict[str, Any]:
    def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise OraclePublicationError(f"{subject} repeats a JSON field")
            result[key] = value
        return result

    def reject_constant(_: str) -> None:
        raise OraclePublicationError(f"{subject} contains a non-finite number")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=duplicate_guard,
            parse_constant=reject_constant,
        )
    except OraclePublicationError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise OraclePublicationError(f"{subject} is not bounded JSON") from error
    if not isinstance(value, dict):
        raise OraclePublicationError(f"{subject} root is not an object")
    return value


def _read_json(path: Path, *, maximum: int, subject: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular(path, maximum=maximum, subject=subject)
    return _json_bytes(raw, subject=subject), raw


def _source_sha_matches(
    repository_root: Path,
    relative: Path,
    expected_sha256: str,
    *,
    source_commit: str,
) -> bool:
    """Bind source to the publication commit even after later tool evolution."""

    try:
        current = _read_regular(
            repository_root / relative,
            maximum=MAX_RECORD_BYTES,
            subject="oracle publication source",
        )
    except OraclePublicationError:
        current = b""
    if current and _sha256(current) == expected_sha256:
        return True
    if COMMIT_RE.fullmatch(source_commit) is None:
        return False
    try:
        historical = subprocess.run(
            ["git", "show", f"{source_commit}:{relative.as_posix()}"],
            cwd=repository_root,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return (
        historical.returncode == 0
        and 0 < len(historical.stdout) <= MAX_RECORD_BYTES
        and _sha256(historical.stdout) == expected_sha256
    )


def _walk_public(value: Any) -> None:
    pending = [(value, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise OraclePublicationError("public oracle exceeds its structural bound")
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str) or key in FORBIDDEN_FIELDS:
                    raise OraclePublicationError("public oracle contains a forbidden field")
                normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
                if "weight_bytes" in normalized or "tensor_values" in normalized:
                    raise OraclePublicationError("public oracle contains model or tensor bytes")
                pending.append((child, depth + 1))
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def _f32(value: Any, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OraclePublicationError(f"{subject} is not numeric")
    try:
        result = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    except (OverflowError, struct.error, ValueError) as error:
        raise OraclePublicationError(f"{subject} is outside F32") from error
    if not math.isfinite(result) or float(value) != result:
        raise OraclePublicationError(f"{subject} is not canonical finite F32")
    return result


def _matrix(value: Any, rows: int, columns: int, *, subject: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != rows:
        raise OraclePublicationError(f"{subject} row count differs")
    result: list[list[float]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != columns:
            raise OraclePublicationError(f"{subject} column count differs")
        result.append([_f32(item, subject=subject) for item in row])
    return result


def _f32_bytes(value: list[list[float]]) -> bytes:
    return b"".join(struct.pack("<f", item) for row in value for item in row)


def _u32_bytes(value: Any) -> bytes:
    if not isinstance(value, list) or len(value) != 2:
        raise OraclePublicationError("public oracle selected IDs differ")
    encoded = bytearray()
    for row in value:
        if not isinstance(row, list) or len(row) != 8:
            raise OraclePublicationError("public oracle selected IDs differ")
        for expert_id in row:
            if type(expert_id) is not int or not 0 <= expert_id < 128:
                raise OraclePublicationError("public oracle selected IDs differ")
            encoded.extend(struct.pack("<I", expert_id))
    return bytes(encoded)


def _public_capture_provenance(value: dict[str, Any]) -> dict[str, Any]:
    build = value["build"]
    helper = build["helper"]
    admitted = value["admitted_model"]
    consumers = value["consumers"]
    return {
        "binding_strategy": value["binding_strategy"],
        "build": {
            key: deepcopy(build[key])
            for key in (
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
            )
        }
        | {
            "helper_identity": {
                "size_bytes": helper["size_bytes"],
                "sha256": helper["sha256"],
            }
        },
        "capture_consumer_ids": [item["consumer_id"] for item in consumers],
        "identity_checks": {
            "model": {
                "size_bytes": admitted["size_bytes"],
                "sha256": admitted["sha256"],
                "all_before_after_match": all(
                    item["model_before"] == admitted and item["model_after"] == admitted
                    for item in consumers
                ),
            },
            "helper": {
                "size_bytes": helper["size_bytes"],
                "sha256": helper["sha256"],
                "all_before_after_match": all(
                    item["helper_before"] == helper and item["helper_after"] == helper
                    for item in consumers
                ),
            },
        },
    }


def project_public_record(
    oracle: dict[str, Any],
    verification: dict[str, Any],
    model_manifest: dict[str, Any],
    *,
    repository_root: Path,
    source_commit: str,
) -> dict[str, Any]:
    """Project only bounded derived input/oracle data from a verified bundle."""

    try:
        model = model_manifest["model_identity"]
        observed = model_manifest["router_tensor_admission"]["observed"]
        capture = oracle["capture"]
        provenance = oracle["capture_provenance"]
    except (KeyError, TypeError) as error:
        raise OraclePublicationError("oracle projection inputs are incomplete") from error
    verifier_raw = _read_regular(
        repository_root / VERIFIER_RELATIVE,
        maximum=MAX_RECORD_BYTES,
        subject="oracle verifier source",
    )
    publisher_raw = _read_regular(
        repository_root / PUBLISHER_RELATIVE,
        maximum=MAX_RECORD_BYTES,
        subject="oracle publisher source",
    )
    public_capture = {
        key: deepcopy(capture[key])
        for key in (
            "source_revision",
            "capture_node",
            "capture_sha256",
            "row_sha256",
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
            "independent_capture_count",
            "rows_distinct",
            "cancellation_proofs",
        )
    }
    record = {
        "schema": PUBLICATION_SCHEMA,
        "schema_version": PUBLICATION_SCHEMA_VERSION,
        "publication_id": PUBLICATION_ID,
        "feature_id": FEATURE_ID,
        "status": "passed",
        "verification": {
            "pulsarmlx_source_commit": source_commit,
            "candidate_sha256": verification["candidate_sha256"],
            "bundle_manifest_sha256": verification["manifest_sha256"],
            "oracle_document_sha256": verification["oracle_document_sha256"],
            "verifier": VERIFIER_RELATIVE.as_posix(),
            "verifier_sha256": _sha256(verifier_raw),
            "publisher": PUBLISHER_RELATIVE.as_posix(),
            "publisher_sha256": _sha256(publisher_raw),
            "projection_command": PROJECTION_COMMAND,
        },
        "source": deepcopy(oracle["source"]),
        "generator": deepcopy(oracle["generator"]),
        "model": {
            key: deepcopy(model[key])
            for key in (
                "repository",
                "revision",
                "filename",
                "size_bytes",
                "sha256",
                "architecture",
                "license",
                "license_reference",
            )
        },
        "tensor": {
            "name": observed["name"],
            "semantic_role": observed["semantic_role"],
            "gguf_type": observed["gguf_type"],
            "quantization": observed["quantization"],
            "gguf_dimensions": observed["gguf_dimensions"],
            "reader_shape": observed["reader_shape"],
            "execution_shape": observed["execution_shape"],
            "orientation": observed["orientation"],
            "logical_element_count": observed["logical_element_count"],
            "absolute_offset": observed["absolute_offset"],
            "encoded_length_bytes": observed["encoded_length_bytes"],
            "exclusive_end_offset": observed["exclusive_end_offset"],
            "encoded_sha256": observed["encoded_sha256"],
            "expert_count": observed["expert_count"],
            "selected_expert_count": observed["selected_expert_count"],
            "weight_scale": observed["weight_scale"],
            "router_bias_present": observed["bias_present"],
            "correction_bias_present": observed["correction_bias_present"],
            "selected_probability_renormalization": observed[
                "selected_probability_renormalization"
            ],
        },
        "capture": public_capture,
        "capture_provenance": _public_capture_provenance(provenance),
        "input": deepcopy(oracle["input"]),
        "result": deepcopy(oracle["result"]),
        "comparison_policy": deepcopy(oracle["comparison_policy"]),
        "redistribution": {
            "checkpoint_license": model["license"],
            "checkpoint_license_reference": model["license_reference"],
            "oracle_source_license": oracle["source"]["license"],
            "artifact_kind": "bounded_derived_hidden_states_and_oracle_outputs",
            "model_weights_included": False,
            "router_tensor_bytes_included": False,
            "capture_binaries_included": False,
            "private_runtime_identity_included": False,
            "upstream_endorsement_implied": False,
        },
        "unsupported_interpretations": deepcopy(oracle["unsupported_interpretations"]),
    }
    validate_public_record(record, repository_root=repository_root)
    return record


def is_public_oracle_record(record: Any) -> bool:
    return isinstance(record, dict) and record.get("schema") == PUBLICATION_SCHEMA


def validate_public_record(
    record: dict[str, Any],
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate one complete closed public projection without checkpoint access."""

    try:
        _reject_non_public_values(record)
    except PublicationError as error:
        raise OraclePublicationError("public oracle contains non-public data") from error
    _walk_public(record)
    root = _closed(
        record,
        {
            "schema",
            "schema_version",
            "publication_id",
            "feature_id",
            "status",
            "verification",
            "source",
            "generator",
            "model",
            "tensor",
            "capture",
            "capture_provenance",
            "input",
            "result",
            "comparison_policy",
            "redistribution",
            "unsupported_interpretations",
        },
        subject="public oracle",
    )
    if (
        root["schema"] != PUBLICATION_SCHEMA
        or root["schema_version"] != PUBLICATION_SCHEMA_VERSION
        or root["publication_id"] != PUBLICATION_ID
        or root["feature_id"] != FEATURE_ID
        or root["status"] != "passed"
    ):
        raise OraclePublicationError("public oracle identity differs")

    verification = _closed(
        root["verification"],
        {
            "pulsarmlx_source_commit",
            "candidate_sha256",
            "bundle_manifest_sha256",
            "oracle_document_sha256",
            "verifier",
            "verifier_sha256",
            "publisher",
            "publisher_sha256",
            "projection_command",
        },
        subject="public oracle verification",
    )
    if (
        not isinstance(verification["pulsarmlx_source_commit"], str)
        or COMMIT_RE.fullmatch(verification["pulsarmlx_source_commit"]) is None
        or any(
            not isinstance(verification[name], str)
            or SHA256_RE.fullmatch(verification[name]) is None
            for name in (
                "candidate_sha256",
                "bundle_manifest_sha256",
                "oracle_document_sha256",
                "verifier_sha256",
                "publisher_sha256",
            )
        )
        or verification["verifier"] != VERIFIER_RELATIVE.as_posix()
        or verification["publisher"] != PUBLISHER_RELATIVE.as_posix()
        or verification["projection_command"] != PROJECTION_COMMAND
        or verification["candidate_sha256"] != PINNED_ORACLE_CANDIDATE_SHA256
        or verification["bundle_manifest_sha256"]
        != PINNED_ORACLE_MANIFEST_SHA256
        or verification["oracle_document_sha256"]
        != PINNED_ORACLE_DOCUMENT_SHA256
        or not _source_sha_matches(
            repository_root,
            VERIFIER_RELATIVE,
            verification["verifier_sha256"],
            source_commit=verification["pulsarmlx_source_commit"],
        )
        or not _source_sha_matches(
            repository_root,
            PUBLISHER_RELATIVE,
            verification["publisher_sha256"],
            source_commit=verification["pulsarmlx_source_commit"],
        )
    ):
        raise OraclePublicationError("public oracle verification identity differs")

    source = _closed(
        root["source"],
        {"repository", "revision", "clean", "license", "metal", "gpu_offload"},
        subject="public oracle source",
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
        raise OraclePublicationError("public oracle source differs")
    generator = _closed(
        root["generator"],
        {"path", "sha256", "generation_command", "independence", "numpy_version"},
        subject="public oracle generator",
    )
    if (
        generator["path"] != "scripts/research/router_oracle.py"
        or not _source_sha_matches(
            repository_root,
            Path(generator["path"]),
            generator["sha256"],
            source_commit=verification["pulsarmlx_source_commit"],
        )
        or generator["numpy_version"] != "2.4.5"
        or generator["independence"] != ORACLE_INDEPENDENCE
        or generator["generation_command"] != ORACLE_GENERATION_COMMAND
    ):
        raise OraclePublicationError("public oracle generator differs")

    model = _closed(
        root["model"],
        {
            "repository",
            "revision",
            "filename",
            "size_bytes",
            "sha256",
            "architecture",
            "license",
            "license_reference",
        },
        subject="public oracle model",
    )
    if (
        model["repository"] != PINNED_MODEL_REPOSITORY
        or model["revision"] != PINNED_MODEL_REVISION
        or model["filename"] != PINNED_MODEL_FILENAME
        or model["size_bytes"] != PINNED_MODEL_SIZE
        or model["sha256"] != PINNED_MODEL_SHA256
        or model["architecture"] != "qwen3moe"
        or model["license"] != "Apache-2.0"
        or model["license_reference"]
        != "docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json"
    ):
        raise OraclePublicationError("public oracle model differs")
    tensor = _closed(
        root["tensor"],
        {
            "name",
            "semantic_role",
            "gguf_type",
            "quantization",
            "gguf_dimensions",
            "reader_shape",
            "execution_shape",
            "orientation",
            "logical_element_count",
            "absolute_offset",
            "encoded_length_bytes",
            "exclusive_end_offset",
            "encoded_sha256",
            "expert_count",
            "selected_expert_count",
            "weight_scale",
            "router_bias_present",
            "correction_bias_present",
            "selected_probability_renormalization",
        },
        subject="public oracle tensor",
    )
    if (
        tensor["name"] != "blk.0.ffn_gate_inp.weight"
        or tensor["semantic_role"] != "layer_0_router_projection"
        or tensor["gguf_type"] != "F32"
        or tensor["quantization"] != "none_f32"
        or tensor["gguf_dimensions"] != [2048, 128]
        or tensor["reader_shape"] != [128, 2048]
        or tensor["execution_shape"] != [128, 2048]
        or tensor["orientation"] != "expert_major_rows_input_columns"
        or tensor["logical_element_count"] != 262_144
        or tensor["absolute_offset"] != 1_115_085_312
        or tensor["encoded_length_bytes"] != 1_048_576
        or tensor["exclusive_end_offset"] != 1_116_133_888
        or tensor["encoded_sha256"] != PINNED_TENSOR_SHA256
        or tensor["expert_count"] != 128
        or tensor["selected_expert_count"] != 8
        or tensor["weight_scale"] != 1.0
        or tensor["router_bias_present"] is not False
        or tensor["correction_bias_present"] is not False
        or tensor["selected_probability_renormalization"] is not True
    ):
        raise OraclePublicationError("public oracle tensor differs")

    capture = _closed(
        root["capture"],
        {
            "source_revision",
            "capture_node",
            "capture_sha256",
            "row_sha256",
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
            "independent_capture_count",
            "rows_distinct",
            "cancellation_proofs",
        },
        subject="public oracle capture",
    )
    if (
        capture["source_revision"] != PINNED_ORACLE_REVISION
        or capture["capture_node"] != "ffn_norm-0"
        or capture["shape"] != [2, 2048]
        or capture["dtype"] != "float32_little_endian"
        or capture["canonical_byte_length"] != 16_384
        or capture["direct_token_ids"] != [0, 1]
        or capture["positions"] != [0, 1]
        or capture["context"] != 2
        or capture["batch"] != 2
        or capture["ubatch"] != 2
        or capture["threads"] != 1
        or capture["input_adapter"] != "direct_token_ids_v1"
        or capture["tokenizer"] != "not_used_direct_token_ids"
        or capture["independent_capture_count"] != 2
        or capture["rows_distinct"] is not True
        or not isinstance(capture["cancellation_proofs"], list)
        or len(capture["cancellation_proofs"]) != 2
    ):
        raise OraclePublicationError("public oracle capture differs")
    for proof in capture["cancellation_proofs"]:
        proof = _closed(
            proof,
            {
                "abort_callback_call_count",
                "abort_callback_calls_after_target",
                "abort_callback_true_count",
                "abort_guard_armed",
                "backend",
                "callback_returned_false",
                "cancelled_before_router_or_expert",
                "decode_status",
                "nodes_after_target",
                "retained_scheduler_trace_byte_length",
                "retained_scheduler_trace_sha256",
                "scheduler_backends",
                "scheduler_input_count",
                "scheduler_split_count",
                "scheduler_split_ids",
                "scheduler_trace_format",
                "scheduler_trace_sha256",
                "target",
                "target_ask_count",
                "target_complete",
                "target_observation_count",
            },
            subject="public oracle cancellation proof",
        )
        if (
            proof["backend"] != "cpu"
            or proof["scheduler_split_count"] != 1
            or proof["scheduler_split_ids"] != [0]
            or proof["scheduler_backends"] != ["cpu"]
            or type(proof["scheduler_input_count"]) is not int
            or not 0 <= proof["scheduler_input_count"] <= 1_000_000
            or proof["target"] != "ffn_norm-0"
            or proof["target_complete"] is not True
            or proof["callback_returned_false"] is not True
            or proof["abort_guard_armed"] is not True
            or proof["abort_callback_calls_after_target"] != 0
            or proof["abort_callback_true_count"] != 0
            or proof["decode_status"] != 0
            or proof["nodes_after_target"] != []
            or proof["cancelled_before_router_or_expert"] is not True
            or type(proof["abort_callback_call_count"]) is not int
            or proof["abort_callback_call_count"] < 1
            or type(proof["target_ask_count"]) is not int
            or proof["target_ask_count"] != 1
            or type(proof["target_observation_count"]) is not int
            or proof["target_observation_count"] != 1
            or type(proof["retained_scheduler_trace_byte_length"]) is not int
            or proof["retained_scheduler_trace_byte_length"] < 1
            or proof["scheduler_trace_format"] != "ggml_sched_debug_marker_v1"
            or not isinstance(proof["retained_scheduler_trace_sha256"], str)
            or SHA256_RE.fullmatch(proof["retained_scheduler_trace_sha256"]) is None
            or not isinstance(proof["scheduler_trace_sha256"], str)
            or SHA256_RE.fullmatch(proof["scheduler_trace_sha256"]) is None
        ):
            raise OraclePublicationError("public oracle cancellation proof differs")

    provenance = _closed(
        root["capture_provenance"],
        {"binding_strategy", "build", "capture_consumer_ids", "identity_checks"},
        subject="public oracle capture provenance",
    )
    build = _closed(
        provenance["build"],
        {
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
            "helper_identity",
        },
        subject="public oracle capture build",
    )
    helper_identity = _closed(
        build["helper_identity"],
        {"size_bytes", "sha256"},
        subject="public oracle capture helper identity",
    )
    identity_checks = _closed(
        provenance["identity_checks"],
        {"model", "helper"},
        subject="public oracle identity checks",
    )
    model_check = _closed(
        identity_checks["model"],
        {"size_bytes", "sha256", "all_before_after_match"},
        subject="public oracle model identity check",
    )
    helper_check = _closed(
        identity_checks["helper"],
        {"size_bytes", "sha256", "all_before_after_match"},
        subject="public oracle helper identity check",
    )
    tools = build["tools"]
    if not isinstance(tools, list) or len(tools) != 3:
        raise OraclePublicationError("public oracle capture tools differ")
    tool_names: list[str] = []
    for tool in tools:
        tool = _closed(
            tool,
            {"name", "version", "executable_sha256"},
            subject="public oracle capture tool",
        )
        if (
            not isinstance(tool["name"], str)
            or not tool["name"]
            or not isinstance(tool["version"], str)
            or not tool["version"]
            or not isinstance(tool["executable_sha256"], str)
            or SHA256_RE.fullmatch(tool["executable_sha256"]) is None
        ):
            raise OraclePublicationError("public oracle capture tool differs")
        tool_names.append(tool["name"])
    provenance_hash_fields = (
        "capture_source_repository_sha256",
        "capture_source_overlay_sha256",
        "cmake_lists_sha256",
        "cmake_cache_sha256",
        "configure_log_sha256",
        "build_log_sha256",
    )
    if (
        provenance["binding_strategy"] != "pre_post_full_sha256_plus_device_inode_size"
        or provenance["capture_consumer_ids"] != ["capture-a", "capture-b"]
        or build["attempt_scoped_fresh"] is not True
        or build["source_revision"] != PINNED_ORACLE_REVISION
        or not isinstance(build["source_tree"], str)
        or COMMIT_RE.fullmatch(build["source_tree"]) is None
        or build["source_clean_before"] is not True
        or build["source_clean_after"] is not True
        or any(
            not isinstance(build[name], str)
            or SHA256_RE.fullmatch(build[name]) is None
            for name in provenance_hash_fields
        )
        or build["capture_source_repository_sha256"]
        != build["capture_source_overlay_sha256"]
        or not isinstance(build["configure_command"], str)
        or not build["configure_command"].startswith("cmake -S $ATTEMPT_SOURCE ")
        or not isinstance(build["build_command"], str)
        or not build["build_command"].startswith("cmake --build $ATTEMPT_BUILD")
        or tool_names != ["cmake", "cxx", "cmake-build-tool"]
        or type(helper_identity["size_bytes"]) is not int
        or helper_identity["size_bytes"] < 1
        or not isinstance(helper_identity["sha256"], str)
        or SHA256_RE.fullmatch(helper_identity["sha256"]) is None
        or model_check
        != {
            "size_bytes": PINNED_MODEL_SIZE,
            "sha256": PINNED_MODEL_SHA256,
            "all_before_after_match": True,
        }
        or helper_check
        != {
            "size_bytes": helper_identity["size_bytes"],
            "sha256": helper_identity["sha256"],
            "all_before_after_match": True,
        }
        or _sha256(_canonical_bytes(provenance))
        != PINNED_CAPTURE_PROVENANCE_SHA256
    ):
        raise OraclePublicationError("public oracle capture provenance differs")

    oracle_input = _closed(
        root["input"],
        {
            "case_ids",
            "shape",
            "dtype",
            "byte_order",
            "values",
            "canonical_f32le_sha256",
            "row_sha256",
        },
        subject="public oracle input",
    )
    if (
        oracle_input["case_ids"]
        != [
            "qwen3moe-layer0-router-token0-row0-v1",
            "qwen3moe-layer0-router-token0-token1-batch-v1",
        ]
        or oracle_input["shape"] != [2, 2048]
        or oracle_input["dtype"] != "float32"
        or oracle_input["byte_order"] != "little"
    ):
        raise OraclePublicationError("public oracle input differs")
    hidden = _matrix(oracle_input["values"], 2, 2048, subject="public oracle input")
    hidden_bytes = _f32_bytes(hidden)
    row_hashes = [_sha256(_f32_bytes([row])) for row in hidden]
    if (
        hidden[0] == hidden[1]
        or oracle_input["canonical_f32le_sha256"] != _sha256(hidden_bytes)
        or oracle_input["canonical_f32le_sha256"] != PINNED_INPUT_SHA256
        or oracle_input["row_sha256"] != row_hashes
        or capture["capture_sha256"] != _sha256(hidden_bytes)
        or capture["row_sha256"] != row_hashes
    ):
        raise OraclePublicationError("public oracle input hashes differ")

    result = _closed(
        root["result"],
        {
            "arithmetic",
            "logits",
            "full_softmax_probabilities",
            "selected_expert_ids",
            "selected_probabilities",
            "normalized_weights",
            "cutoff_ties",
            "hashes",
            "numpy_cross_check",
        },
        subject="public oracle result",
    )
    logits = _matrix(result["logits"], 2, 128, subject="public oracle logits")
    probabilities = _matrix(
        result["full_softmax_probabilities"], 2, 128, subject="public oracle probabilities"
    )
    selected = _matrix(
        result["selected_probabilities"], 2, 8, subject="public oracle selected probabilities"
    )
    normalized = _matrix(
        result["normalized_weights"], 2, 8, subject="public oracle normalized weights"
    )
    expected_probabilities = [router_oracle.full_softmax_f32(row) for row in logits]
    routes = [router_oracle.select_top_k_f32(row) for row in expected_probabilities]
    expected_ids = [route[0] for route in routes]
    expected_selected = [route[1] for route in routes]
    expected_normalized = [route[2] for route in routes]
    ids_bytes = _u32_bytes(result["selected_expert_ids"])
    logits_bytes = _f32_bytes(logits)
    probabilities_bytes = _f32_bytes(probabilities)
    selected_bytes = _f32_bytes(selected)
    normalized_bytes = _f32_bytes(normalized)
    expected_hashes = {
        "logits_f32le_sha256": _sha256(logits_bytes),
        "full_softmax_probabilities_f32le_sha256": _sha256(probabilities_bytes),
        "selected_expert_ids_u32le_sha256": _sha256(ids_bytes),
        "selected_probabilities_f32le_sha256": _sha256(selected_bytes),
        "normalized_weights_f32le_sha256": _sha256(normalized_bytes),
        "output_bundle_sha256": _sha256(
            logits_bytes
            + probabilities_bytes
            + ids_bytes
            + selected_bytes
            + normalized_bytes
        ),
    }
    if (
        result["arithmetic"] != "scalar_float32_multiply_then_add_left_to_right"
        or _f32_bytes(probabilities) != _f32_bytes(expected_probabilities)
        or result["selected_expert_ids"] != expected_ids
        or _f32_bytes(selected) != _f32_bytes(expected_selected)
        or _f32_bytes(normalized) != _f32_bytes(expected_normalized)
        or result["cutoff_ties"] != [False, False]
        or result["hashes"] != expected_hashes
        or expected_hashes["output_bundle_sha256"] != PINNED_OUTPUT_SHA256
    ):
        raise OraclePublicationError("public oracle numerical result differs")
    if root["comparison_policy"] != {
        "logits": {"absolute_tolerance": 5e-4, "relative_tolerance": 5e-4},
        "probabilities_and_weights": {
            "absolute_tolerance": 1e-6,
            "relative_tolerance": 1e-6,
        },
        "non_finite_policy": "reject",
        "tie_rule": "probability_descending_then_expert_id_ascending",
        "real_rank_8_rank_9_tie": "stop",
    }:
        raise OraclePublicationError("public oracle comparison policy differs")
    numpy = _closed(
        result["numpy_cross_check"],
        {
            "passed",
            "compared_count",
            "mismatch_count",
            "first_mismatch",
            "maximum_absolute_error",
            "maximum_relative_error",
            "absolute_tolerance",
            "relative_tolerance",
            "numpy_logits_f32le_sha256",
        },
        subject="public oracle NumPy cross-check",
    )
    numpy_metrics = (
        numpy["maximum_absolute_error"],
        numpy["maximum_relative_error"],
        numpy["absolute_tolerance"],
        numpy["relative_tolerance"],
    )
    if (
        numpy["passed"] is not True
        or numpy["compared_count"] != 256
        or numpy["mismatch_count"] != 0
        or numpy["first_mismatch"] is not None
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in numpy_metrics
        )
        or numpy["absolute_tolerance"] != 0.0005000000237487257
        or numpy["relative_tolerance"] != 0.0005000000237487257
        or numpy["maximum_absolute_error"] > numpy["absolute_tolerance"]
        or numpy["maximum_relative_error"] > numpy["relative_tolerance"]
        or numpy["maximum_absolute_error"]
        != PINNED_NUMPY_MAXIMUM_ABSOLUTE_ERROR
        or numpy["maximum_relative_error"]
        != PINNED_NUMPY_MAXIMUM_RELATIVE_ERROR
        or numpy["numpy_logits_f32le_sha256"] != PINNED_NUMPY_LOGITS_SHA256
    ):
        raise OraclePublicationError("public oracle NumPy cross-check differs")
    redistribution = _closed(
        root["redistribution"],
        {
            "checkpoint_license",
            "checkpoint_license_reference",
            "oracle_source_license",
            "artifact_kind",
            "model_weights_included",
            "router_tensor_bytes_included",
            "capture_binaries_included",
            "private_runtime_identity_included",
            "upstream_endorsement_implied",
        },
        subject="public oracle redistribution",
    )
    if (
        redistribution["checkpoint_license"] != "Apache-2.0"
        or redistribution["checkpoint_license_reference"] != model["license_reference"]
        or redistribution["oracle_source_license"] != "MIT"
        or redistribution["artifact_kind"]
        != "bounded_derived_hidden_states_and_oracle_outputs"
        or any(
            redistribution[name] is not False
            for name in (
                "model_weights_included",
                "router_tensor_bytes_included",
                "capture_binaries_included",
                "private_runtime_identity_included",
                "upstream_endorsement_implied",
            )
        )
        or root["unsupported_interpretations"] != UNSUPPORTED
    ):
        raise OraclePublicationError("public oracle redistribution scope differs")
    _canonical_bytes(record)
    return {
        "publication_id": PUBLICATION_ID,
        "record_sha256": _sha256(_canonical_bytes(record)),
        "input_sha256": _sha256(hidden_bytes),
        "output_sha256": expected_hashes["output_bundle_sha256"],
        "selected_expert_ids": result["selected_expert_ids"],
        "cutoff_ties": result["cutoff_ties"],
        "numpy_mismatch_count": numpy["mismatch_count"],
    }


def _manifest(record_bytes: bytes) -> dict[str, Any]:
    digest = _sha256(record_bytes)
    return {
        "schema": MANIFEST_SCHEMA,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "publication_id": PUBLICATION_ID,
        "complete": True,
        "commit_marker_installed_last": True,
        "byte_identical_copies": True,
        "records": [
            {
                "path": FIXTURE_RECORD_RELATIVE.as_posix(),
                "byte_length": len(record_bytes),
                "sha256": digest,
            },
            {
                "path": RAW_RECORD_RELATIVE.as_posix(),
                "byte_length": len(record_bytes),
                "sha256": digest,
            },
        ],
    }


def _validate_manifest(value: dict[str, Any], record_bytes: bytes) -> None:
    expected = _manifest(record_bytes)
    if value != expected:
        raise OraclePublicationError("public oracle manifest differs")


def _reject_symlink_components(path: Path) -> None:
    current = path.absolute()
    while True:
        root_alias = current.parent == Path("/") and current.name in {"var", "tmp", "etc"}
        if current.is_symlink() and not root_alias:
            raise OraclePublicationError("oracle publication path contains a symbolic link")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _sync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("not a directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepare_parent(path: Path) -> None:
    _reject_symlink_components(path.parent)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise OraclePublicationError("oracle publication directory cannot be created") from error
    _reject_symlink_components(path.parent)
    if not path.parent.is_dir():
        raise OraclePublicationError("oracle publication parent is not a directory")


def _existing_state(path: Path, expected: bytes) -> str:
    _reject_symlink_components(path)
    if not path.exists():
        return "absent"
    observed = _read_regular(path, maximum=MAX_RECORD_BYTES, subject="oracle publication file")
    if observed != expected:
        raise OraclePublicationError("existing oracle publication bytes differ")
    return "exact"


def _remove_installed(path: Path) -> None:
    try:
        path.unlink()
        _sync_directory(path.parent)
    except FileNotFoundError:
        return
    except OSError as error:
        raise OraclePublicationError("oracle publication rollback failed") from error


def _remove_temporary(path: Path) -> None:
    try:
        path.unlink()
        _sync_directory(path.parent)
    except FileNotFoundError:
        return
    except OSError as error:
        raise OraclePublicationError(
            "oracle publication temporary cleanup failed"
        ) from error


def _install_exact(path: Path, payload: bytes) -> bool:
    if _existing_state(path, payload) == "exact":
        return False
    _prepare_parent(path)
    descriptor: int | None = None
    temporary_path: Path | None = None
    destination_linked = False
    failure: OraclePublicationError | OSError | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(name)
        os.fchmod(descriptor, 0o644)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("zero-progress write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(temporary_path, path, follow_symlinks=False)
            destination_linked = True
        except FileExistsError:
            if _existing_state(path, payload) != "exact":
                raise
        _sync_directory(path.parent)
    except (OraclePublicationError, OSError) as error:
        failure = error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                if failure is None:
                    failure = error

    cleanup_failure: OraclePublicationError | None = None
    if temporary_path is not None:
        try:
            _remove_temporary(temporary_path)
        except OraclePublicationError as error:
            cleanup_failure = error
    if failure is not None or cleanup_failure is not None:
        rollback_failure: OraclePublicationError | None = None
        if destination_linked:
            try:
                _remove_installed(path)
            except OraclePublicationError as error:
                rollback_failure = error
        if cleanup_failure is not None and temporary_path is not None:
            try:
                _remove_temporary(temporary_path)
            except OraclePublicationError as error:
                cleanup_failure = error
        if rollback_failure is not None:
            raise rollback_failure
        if cleanup_failure is not None:
            raise cleanup_failure
        if isinstance(failure, OraclePublicationError):
            raise failure
        raise OraclePublicationError("oracle publication install failed") from failure
    return destination_linked


def publish_public_record(
    record: dict[str, Any],
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Install exact copies and a manifest-last logical transaction marker."""

    summary = validate_public_record(record, repository_root=repository_root)
    record_bytes = _canonical_bytes(record)
    manifest_bytes = _canonical_bytes(_manifest(record_bytes))
    fixture_path = repository_root / FIXTURE_RECORD_RELATIVE
    raw_path = repository_root / RAW_RECORD_RELATIVE
    manifest_path = repository_root / MANIFEST_RELATIVE
    for path in (fixture_path, raw_path, manifest_path):
        _prepare_parent(path)
    manifest_state = _existing_state(manifest_path, manifest_bytes)
    fixture_state = _existing_state(fixture_path, record_bytes)
    raw_state = _existing_state(raw_path, record_bytes)
    if manifest_state == "exact" and (fixture_state, raw_state) != ("exact", "exact"):
        raise OraclePublicationError("complete oracle publication is missing a record")
    installed: list[Path] = []
    try:
        for path, payload in (
            (fixture_path, record_bytes),
            (raw_path, record_bytes),
            (manifest_path, manifest_bytes),
        ):
            if _install_exact(path, payload):
                installed.append(path)
        verified = verify_committed_publication(repository_root)
    except (OraclePublicationError, OSError):
        rollback_failed = False
        for path in reversed(installed):
            try:
                _remove_installed(path)
            except OraclePublicationError:
                rollback_failed = True
        if rollback_failed:
            raise OraclePublicationError("oracle publication rollback failed")
        raise
    return {**summary, **verified}


def verify_committed_publication(repository_root: Path) -> dict[str, Any]:
    fixture_path = repository_root / FIXTURE_RECORD_RELATIVE
    raw_path = repository_root / RAW_RECORD_RELATIVE
    manifest_path = repository_root / MANIFEST_RELATIVE
    fixture, fixture_bytes = _read_json(
        fixture_path, maximum=MAX_RECORD_BYTES, subject="public fixture oracle"
    )
    raw, raw_bytes = _read_json(raw_path, maximum=MAX_RECORD_BYTES, subject="public raw oracle")
    manifest, manifest_bytes = _read_json(
        manifest_path, maximum=MAX_RECORD_BYTES, subject="public oracle manifest"
    )
    if fixture_bytes != raw_bytes or fixture != raw:
        raise OraclePublicationError("public oracle copies differ")
    if (
        fixture_bytes != _canonical_bytes(fixture)
        or raw_bytes != _canonical_bytes(raw)
        or manifest_bytes != _canonical_bytes(manifest)
    ):
        raise OraclePublicationError("public oracle bytes are not canonical")
    summary = validate_public_record(fixture, repository_root=repository_root)
    _validate_manifest(manifest, fixture_bytes)
    expected_fixture = {MANIFEST_RELATIVE.name, FIXTURE_RECORD_RELATIVE.name}
    expected_raw = {RAW_RECORD_RELATIVE.name}
    try:
        fixture_names = {path.name for path in fixture_path.parent.iterdir()}
        raw_names = {path.name for path in raw_path.parent.iterdir()}
    except OSError as error:
        raise OraclePublicationError("public oracle inventory is unavailable") from error
    if fixture_names != expected_fixture or raw_names != expected_raw:
        raise OraclePublicationError("public oracle inventory differs")
    return {
        "passed": True,
        "publication_id": PUBLICATION_ID,
        "record_sha256": _sha256(fixture_bytes),
        "record_byte_length": len(fixture_bytes),
        "copy_count": 2,
        "manifest_sha256": _sha256(manifest_bytes),
        "input_sha256": summary["input_sha256"],
        "output_sha256": summary["output_sha256"],
        "selected_expert_ids": summary["selected_expert_ids"],
        "cutoff_ties": summary["cutoff_ties"],
        "numpy_mismatch_count": summary["numpy_mismatch_count"],
    }


def _clean_commit(repository_root: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository_root,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0 or status.stdout:
        raise OraclePublicationError("oracle publication requires a clean worktree")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    commit = head.stdout.strip()
    if head.returncode != 0 or COMMIT_RE.fullmatch(commit) is None:
        raise OraclePublicationError("oracle publication source commit is unavailable")
    return commit


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-candidate", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.check == (arguments.oracle_candidate is not None):
        print("oracle_publication_error: select exactly one mode", file=sys.stderr)
        return 2
    repository_root = _repository_root()
    try:
        if arguments.check:
            summary = verify_committed_publication(repository_root)
        else:
            source_commit = _clean_commit(repository_root)
            import verify_package

            verification = verify_package.verify_oracle_candidate_bundle(
                arguments.oracle_candidate,
                expected_feature=FEATURE_ID,
            )
            oracle, oracle_bytes = _read_json(
                arguments.oracle_candidate / "oracle.json",
                maximum=MAX_RECORD_BYTES,
                subject="external oracle document",
            )
            if _sha256(oracle_bytes) != verification["oracle_document_sha256"]:
                raise OraclePublicationError("verified oracle identity changed")
            model_manifest, _ = _read_json(
                repository_root / MODEL_MANIFEST_RELATIVE,
                maximum=MAX_RECORD_BYTES,
                subject="model manifest",
            )
            record = project_public_record(
                oracle,
                verification,
                model_manifest,
                repository_root=repository_root,
                source_commit=source_commit,
            )
            summary = publish_public_record(record, repository_root=repository_root)
    except (OraclePublicationError, OSError, OverflowError, TypeError, ValueError):
        print("oracle_publication_error: bounded oracle publication failed", file=sys.stderr)
        return 1
    print(json.dumps(summary, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

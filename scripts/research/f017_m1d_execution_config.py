#!/usr/bin/env python3
"""Typed M1-D attempt-3 execution configuration and non-consuming preflight."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "pulsarmlx.f017.m1d-execution-config"
SCHEMA_VERSION = "1.0.0"
READY = "READY_TO_EXECUTE_ATTEMPT_3"
ATTEMPT = 3
ACTIVATION_PATH = "specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json"
WRONG_HISTORICAL_ACTIVATION_PATH = "specs/017-real-checkpoint-runner/fixtures/f017-m1d-projection-oracle-v1.json"
ACTIVATION_ARTIFACT_SHA256 = "1727e63a5daee0ffbb0bf6dea11ea5ecf1b559850632785d5c8864c2bbaf503a"
ACTIVATION_PAYLOAD_SHA256 = "dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2"
PRIOR = {
    "attempt_1": "a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62",
    "attempt_2": "6a87c36c380fb43393bc79cdc4e22e59bb81c0425ad0285017d6a1bc00dd79f6",
    "m1_a": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
}
CHECKPOINT = {
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
}
EXPECTED_REPOSITORY_ARTIFACTS = {
    "fixture_finalization_source": (
        "scripts/research/generate_f017_m1d_projection_oracle.py",
        "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92",
    ),
    "real_reference_preparer": ("scripts/research/prepare_f017_m1d_real_reference.py", None),
    "boundary_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json",
        "d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613",
    ),
    "decoder_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json",
        "aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd",
    ),
    "scaffold_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-exact-scaffold-v1.json",
        "3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5",
    ),
    "tier_b_contract": (
        "specs/017-rust-native-inference-runtime/contracts/production-m1d-projection-tier-b-v1.json",
        "f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b",
    ),
    "repeat_integrity_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-repeat-integrity-v1.json",
        "1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f",
    ),
    "oracle_ordering_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-oracle-ordering-v1.json",
        "f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528",
    ),
    "path_resolution_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
        "40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d",
    ),
    "package_schema": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-projection-package-v2.schema.json",
        "eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a",
    ),
    "command_assembly_contract": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-command-assembly-v1.json",
        None,
    ),
    "execution_config_schema": (
        "specs/017-rust-native-inference-runtime/contracts/m1d-execution-config-v1.schema.json",
        None,
    ),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json_no_duplicates(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError("execution document must be an object")
    return value


def canonical_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def validate_sha(value: Any, role: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{role} must be a lowercase SHA-256")
    return value


def validate_symbolic_path(value: Any, role: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{role} symbolic path is missing")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"{role} symbolic path is not a normal repository-relative path")
    return value


def repository_identity(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def resolve_repository_artifact(root: Path, reference: dict[str, Any], role: str) -> Path:
    if set(reference) != {"path_kind", "symbolic_path", "content_sha256", "logical_role"}:
        raise ValueError(f"{role} artifact reference has ambiguous fields")
    if reference["path_kind"] != "repository_relative" or reference["logical_role"] != role:
        raise ValueError(f"{role} path namespace or logical role mismatch")
    symbolic = validate_symbolic_path(reference["symbolic_path"], role)
    expected = validate_sha(reference["content_sha256"], role)
    candidate = root.joinpath(*PurePosixPath(symbolic).parts)
    current = root
    for part in PurePosixPath(symbolic).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{role} contains a symlink component")
    resolved = candidate.resolve(strict=True)
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"{role} escapes the trusted repository root")
    if sha256(resolved.read_bytes()) != expected:
        raise ValueError(f"{role} content hash mismatch")
    return resolved


def validate_execution_config(document: dict[str, Any], *, check_outputs_absent: bool = False) -> None:
    required = {
        "schema", "schema_version", "status", "attempt", "attempt_consumed",
        "runtime_sha", "tooling_sha", "repository_root", "package_root",
        "activation_fixture", "activation_payload_sha256", "provenance", "repository_artifacts",
        "local_artifacts", "prior_evidence", "checkpoint_bindings", "runner", "execution",
    }
    if set(document) != required:
        raise ValueError("execution config has missing, extra, or unbound fields")
    if (document["schema"], document["schema_version"], document["status"]) != (SCHEMA, SCHEMA_VERSION, READY):
        raise ValueError("execution config schema/status mismatch")
    if document["attempt"] != ATTEMPT or document["attempt_consumed"] is not False:
        raise ValueError("attempt-3 config must be unconsumed")
    runtime = document["runtime_sha"]
    tooling = document["tooling_sha"]
    if not isinstance(runtime, str) or len(runtime) != 40 or not isinstance(tooling, str) or len(tooling) != 40:
        raise ValueError("runtime/tooling identity must be full Git SHAs")
    root_binding = document["repository_root"]
    if root_binding.get("path_kind") != "absolute_private_local" or root_binding.get("identity") != runtime:
        raise ValueError("repository root binding is not explicit or does not match runtime")
    root = Path(root_binding["path"])
    if root.is_symlink():
        raise ValueError("repository root symlink is forbidden")
    root = root.resolve(strict=True)
    if repository_identity(root) != runtime:
        raise ValueError("repository root Git identity mismatch")
    package_binding = document["package_root"]
    if package_binding.get("path_kind") != "absolute_private_local" or package_binding.get("identity") != "m1d_attempt_3_private_package_root":
        raise ValueError("private package root binding mismatch")
    package_root = Path(package_binding["path"])
    if package_root.is_symlink():
        raise ValueError("private package root symlink is forbidden")
    package_root = package_root.resolve(strict=True)

    activation = document["activation_fixture"]
    if activation.get("symbolic_path") != ACTIVATION_PATH:
        raise ValueError("activation symbolic path differs from authorization")
    if activation.get("symbolic_path") == WRONG_HISTORICAL_ACTIVATION_PATH:
        raise ValueError("historical attempt-2 activation path is forbidden")
    if activation.get("content_sha256") != ACTIVATION_ARTIFACT_SHA256:
        raise ValueError("activation fixture artifact hash mismatch")
    resolve_repository_artifact(root, activation, "activation_fixture")
    if document["activation_payload_sha256"] != ACTIVATION_PAYLOAD_SHA256:
        raise ValueError("activation payload hash mismatch")
    provenance = document["provenance"]
    if provenance.get("activation_generation_source_sha256") != "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984":
        raise ValueError("activation generation provenance mismatch")
    if provenance.get("fixture_finalization_source_sha256") != "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92":
        raise ValueError("fixture finalization provenance mismatch")
    validate_sha(provenance.get("real_reference_preparer_sha256"), "real-reference preparer")
    if set(provenance) != {"activation_generation_source_sha256", "fixture_finalization_source_sha256", "real_reference_preparer_sha256"}:
        raise ValueError("provenance roles are collapsed, missing, or ambiguous")

    artifacts = document["repository_artifacts"]
    if set(artifacts) != set(EXPECTED_REPOSITORY_ARTIFACTS):
        raise ValueError("repository artifact set is incomplete or contains an unbound input")
    for role, (path, digest) in EXPECTED_REPOSITORY_ARTIFACTS.items():
        reference = artifacts[role]
        if reference.get("symbolic_path") != path or (digest is not None and reference.get("content_sha256") != digest):
            raise ValueError(f"{role} path/hash differs from frozen binding")
        resolve_repository_artifact(root, reference, role)
    if artifacts["real_reference_preparer"]["content_sha256"] != provenance["real_reference_preparer_sha256"]:
        raise ValueError("real-reference preparer artifact/provenance binding mismatch")
    if document["prior_evidence"] != PRIOR or document["checkpoint_bindings"] != CHECKPOINT:
        raise ValueError("prior evidence or checkpoint binding mismatch")
    runner = document["runner"]
    if runner != {
        "mode": "real_projection",
        "validation_mode": "golden_strict",
        "stream_mode": "owned_device",
        "numerical_mode": "production_mlx_tier_b",
        "memory_floor_bytes": 17179869184,
    } and runner != {
        "mode": "fixture_projection",
        "validation_mode": "golden_strict",
        "stream_mode": "owned_device",
        "numerical_mode": "production_mlx_tier_b",
        "memory_floor_bytes": 1,
    }:
        raise ValueError("runner mode contains a manual or unsupported override")
    execution = document["execution"]
    if execution != {
        "conceptual_projection_count": 1,
        "repeat_count": 10,
        "native_dispatch_count": 10,
        "auto_retry": False,
        "stop_before_m1_e": True,
    }:
        raise ValueError("execution bounds differ from authorization")

    local = document["local_artifacts"]
    if set(local) != {"environment_manifest", "checkpoint_manifest", "target_shard", "oracle_output", "package_output", "evidence_output"}:
        raise ValueError("local artifact set mismatch")
    for role in ("environment_manifest", "checkpoint_manifest"):
        item = local[role]
        if item.get("path_kind") != "absolute_private_local":
            raise ValueError(f"{role} is not a typed private path")
        path = Path(item["path"])
        if path.is_symlink() or sha256(path.read_bytes()) != item.get("content_sha256"):
            raise ValueError(f"{role} path/hash mismatch")
    shard = local["target_shard"]
    if shard.get("path_kind") != "absolute_private_local" or shard.get("ordinal") != 2:
        raise ValueError("target shard binding mismatch")
    shard_path = Path(shard["path"])
    if shard_path.is_symlink() or not shard_path.is_file():
        raise ValueError("target shard must be a non-symlink regular file")
    if shard_path.name != shard.get("basename") or shard_path.stat().st_size != shard.get("byte_size"):
        raise ValueError("target shard basename/size mismatch")
    validate_sha(shard.get("sha256"), "target shard")
    for role in ("oracle_output", "package_output", "evidence_output"):
        path = Path(local[role])
        parent = path.parent.resolve(strict=True)
        if role != "evidence_output" and parent != package_root:
            raise ValueError(f"{role} is outside private package root")
        if check_outputs_absent and path.exists():
            raise ValueError(f"{role} must be fresh")


def exclusive_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(stat.S_IRUSR)


def validate_config_file(path: Path, expected_sha256: str, *, check_outputs_absent: bool = False) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha256(raw) != validate_sha(expected_sha256, "execution config"):
        raise ValueError("execution config SHA-256 mismatch")
    document = load_json_no_duplicates(path)
    validate_execution_config(document, check_outputs_absent=check_outputs_absent)
    return document

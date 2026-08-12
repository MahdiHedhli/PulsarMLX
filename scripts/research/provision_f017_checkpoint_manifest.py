#!/usr/bin/env python3
"""Provision and validate the local-only F017 production checkpoint manifest.

This tool is deliberately not the canonical F017 runner. It performs streaming
shard hashing plus GGUF header/catalog parsing only. It never reads tensor
payload ranges for numerical execution, decodes quantized values, constructs an
MLX context, or dispatches model compute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from glm52_gguf_catalog import parse_header


RUNTIME_SOURCE_SHA = "b29202171a279cd3bb2ac2cf4dc6b3be7486019e"
MANIFEST_SCHEMA = "pulsarmlx.f017.checkpoint-manifest"
MANIFEST_VERSION = "1.0.0"
REVIEW_SCHEMA = "pulsarmlx.f017.production-checkpoint-manifest-review"
REVIEW_VERSION = 1
MANIFEST_KIND = "production_f017_checkpoint"
CHECKPOINT_REVISION = "abc55e72527792c6e77069c99b4cb7de16fa9f23"
ARCHITECTURE = "glm-dsa"
EXPECTED_LAYER_COUNT = 79
EXPECTED_TENSOR_COUNT = 1_809
TENSOR_MAP_VERSION = "f017-glm52-tensor-map-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

EXPECTED_BASENAMES = [
    f"GLM-5.2-UD-IQ2_XXS-{ordinal:05d}-of-00006.gguf"
    for ordinal in range(1, 7)
]

BLOCK_LAYOUTS = {
    0: (1, 4),       # F32
    1: (1, 2),       # F16
    2: (32, 18),     # Q4_0
    6: (32, 22),     # Q5_0
    7: (32, 24),     # Q5_1
    8: (32, 34),     # Q8_0
    10: (256, 84),   # Q2_K
    11: (256, 110),  # Q3_K
    12: (256, 144),  # Q4_K
    13: (256, 176),  # Q5_K
    14: (256, 210),  # Q6_K
    15: (256, 292),  # Q8_K
    16: (256, 66),   # IQ2_XXS
    17: (256, 74),   # IQ2_XS
    18: (256, 98),   # IQ3_XXS
    19: (256, 50),   # IQ1_S
    20: (32, 18),    # IQ4_NL
    21: (256, 110),  # IQ3_S
    22: (256, 82),   # IQ2_S
    23: (256, 136),  # IQ4_XS
    26: (1, 4),      # I32
    30: (1, 2),      # BF16
    39: (32, 17),    # MXFP4
}


class ProvisioningError(ValueError):
    """Fail-closed manifest provisioning error."""


def _reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvisioningError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)
    except (OSError, json.JSONDecodeError) as error:
        raise ProvisioningError(f"cannot load {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise ProvisioningError(f"{path.name}: top-level JSON must be an object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while block := handle.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_exclusive(path: Path, payload: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def discover_canonical_shards(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise ProvisioningError("checkpoint root must be a real directory, not a symlink")
    candidates = sorted(root.glob("*.gguf"), key=lambda path: path.name)
    names = [path.name for path in candidates]
    if names != EXPECTED_BASENAMES:
        raise ProvisioningError(
            f"checkpoint directory must contain exactly the six canonical shards; found {names}"
        )
    seen: set[str] = set()
    for path in candidates:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ProvisioningError(f"shard {path.name} must be a non-symlink regular file")
        if path.name in seen:
            raise ProvisioningError(f"duplicate shard basename {path.name}")
        seen.add(path.name)
        if not os.access(path, os.R_OK):
            raise ProvisioningError(f"shard {path.name} is not readable")
    return candidates


def checkpoint_set_sha256(shards: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for shard in shards:
        digest.update(shard["sha256"].encode())
        digest.update(str(shard["size_bytes"]).encode())
    return digest.hexdigest()


def tensor_byte_size(tensor: dict[str, Any]) -> int:
    try:
        block_size, block_bytes = BLOCK_LAYOUTS[int(tensor["type_id"])]
    except KeyError as error:
        raise ProvisioningError(
            f"unsupported GGUF tensor type {tensor.get('type_id')} for {tensor.get('name')}"
        ) from error
    dimensions = [int(value) for value in tensor["dims"]]
    if not dimensions or any(value <= 0 for value in dimensions):
        raise ProvisioningError(f"invalid dimensions for {tensor.get('name')}")
    row_bytes = ((dimensions[0] + block_size - 1) // block_size) * block_bytes
    rows = 1
    for value in dimensions[1:]:
        rows *= value
    return row_bytes * max(rows, 1)


def catalog_sha256(tensors: list[dict[str, Any]]) -> str:
    """Match f017_runner::checkpoint::catalog_sha256 exactly."""
    digest = hashlib.sha256()
    for tensor in tensors:
        digest.update(tensor["name"].encode())
        digest.update(b"\0")
        dimensions = [int(value) for value in tensor["dims"]]
        digest.update(struct.pack("<Q", len(dimensions)))
        for dimension in dimensions:
            digest.update(struct.pack("<Q", dimension))
        digest.update(struct.pack("<I", int(tensor["type_id"])))
        digest.update(struct.pack("<Q", int(tensor["merged_offset"])))
        digest.update(struct.pack("<Q", tensor_byte_size(tensor)))
    return digest.hexdigest()


def tensor_map_contract_sha256(tensors: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    digest.update(TENSOR_MAP_VERSION.encode())
    for tensor in sorted(tensors, key=lambda item: item["name"]):
        digest.update(tensor["name"].encode())
        digest.update(b"\0")
        for dimension in tensor["dims"]:
            digest.update(struct.pack("<Q", int(dimension)))
        digest.update(struct.pack("<I", int(tensor["type_id"])))
    return digest.hexdigest()


def inspect_catalog(paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tensors: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    logical_base = 0
    shard_summaries: list[dict[str, Any]] = []
    for path in paths:
        header = parse_header(path)
        for key, value in header["kv"].items():
            metadata.setdefault(key, value)
        for original in header["tensors"]:
            tensor = dict(original)
            tensor["file"] = path.name
            tensor["merged_offset"] = (
                logical_base + int(header["data_section_start"]) + int(tensor["data_offset_rel"])
            )
            tensors.append(tensor)
        shard_summaries.append(
            {
                "basename": path.name,
                "gguf_version": int(header["gguf_version"]),
                "tensor_count": int(header["n_tensors"]),
                "metadata_count": int(header["n_kv"]),
                "data_section_start": int(header["data_section_start"]),
            }
        )
        logical_base += path.stat().st_size
    return tensors, {"metadata": metadata, "shards": shard_summaries}


def validate_catalog_against_public(
    tensors: list[dict[str, Any]], catalog_state: dict[str, Any], public_catalog: dict[str, Any]
) -> None:
    metadata = catalog_state["metadata"]
    if metadata.get("general.architecture") != ARCHITECTURE:
        raise ProvisioningError("GGUF architecture is not glm-dsa")
    expected_metadata = {
        "glm-dsa.block_count": EXPECTED_LAYER_COUNT,
        "glm-dsa.leading_dense_block_count": 3,
        "glm-dsa.expert_count": 256,
        "glm-dsa.expert_used_count": 8,
        "glm-dsa.expert_shared_count": 1,
        "glm-dsa.embedding_length": 6144,
        "glm-dsa.vocab_size": 154880,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise ProvisioningError(f"GGUF metadata {key} differs from {expected}")
    if len(tensors) != EXPECTED_TENSOR_COUNT:
        raise ProvisioningError(
            f"catalog has {len(tensors)} tensors; expected {EXPECTED_TENSOR_COUNT}"
        )
    if public_catalog.get("tensor_count") != EXPECTED_TENSOR_COUNT:
        raise ProvisioningError("committed public catalog tensor count differs")
    public_tensors = public_catalog.get("tensors")
    if not isinstance(public_tensors, list) or len(public_tensors) != len(tensors):
        raise ProvisioningError("committed public catalog tensor list differs")
    fields = ("name", "dims", "type_id", "data_offset_rel", "file")
    for index, (actual, expected) in enumerate(zip(tensors, public_tensors, strict=True)):
        for field in fields:
            if actual.get(field) != expected.get(field):
                raise ProvisioningError(
                    f"catalog tensor {index} field {field} differs from committed identity"
                )


def tokenizer_identity(metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    def array_length(key: str) -> int:
        value = metadata.get(key)
        if not isinstance(value, dict) or value.get("truncated") is not True:
            raise ProvisioningError(f"tokenizer array identity unavailable for {key}")
        return int(value["len"])

    chat_template = metadata.get("tokenizer.chat_template")
    if not isinstance(chat_template, str) or not chat_template:
        raise ProvisioningError("tokenizer chat template is missing")
    identity = {
        "ggml_model": metadata.get("tokenizer.ggml.model"),
        "pre": metadata.get("tokenizer.ggml.pre"),
        "bos_token_id": metadata.get("tokenizer.ggml.bos_token_id"),
        "eos_token_id": metadata.get("tokenizer.ggml.eos_token_id"),
        "unknown_token_id": metadata.get("tokenizer.ggml.unknown_token_id"),
        "pad_token_id": metadata.get("tokenizer.ggml.padding_token_id"),
        "eom_token_id": metadata.get("tokenizer.ggml.eom_token_id"),
        "eot_token_id": metadata.get("tokenizer.ggml.eot_token_id"),
        "vocab_size": array_length("tokenizer.ggml.tokens"),
        "token_type_count": array_length("tokenizer.ggml.token_type"),
        "merge_count": array_length("tokenizer.ggml.merges"),
        "chat_template_sha256": sha256_bytes(chat_template.encode()),
    }
    expected = {
        "ggml_model": "gpt2",
        "pre": "glm4",
        "bos_token_id": 154822,
        "eos_token_id": 154820,
        "unknown_token_id": 154820,
        "pad_token_id": 154821,
        "eom_token_id": 154829,
        "eot_token_id": 154827,
        "vocab_size": 154880,
        "token_type_count": 154880,
        "merge_count": 321649,
    }
    for key, value in expected.items():
        if identity.get(key) != value:
            raise ProvisioningError(f"tokenizer identity field {key} differs")
    digest = sha256_bytes(canonical_json_bytes(identity))
    return f"glm52-gguf-tokenizer-v1:{digest}", identity


def validate_runner_manifest(manifest: dict[str, Any]) -> None:
    expected_keys = {
        "schema", "schema_version", "kind", "immutable_revision", "architecture",
        "tokenizer_identity", "checkpoint_set_sha256", "catalog_sha256",
        "tensor_count", "shards",
    }
    if set(manifest) != expected_keys:
        raise ProvisioningError("checkpoint manifest fields differ from runner schema")
    if manifest["schema"] != MANIFEST_SCHEMA or manifest["schema_version"] != MANIFEST_VERSION:
        raise ProvisioningError("unsupported checkpoint manifest schema")
    if manifest["kind"] != "production":
        raise ProvisioningError("checkpoint manifest kind must be production")
    if manifest["immutable_revision"] != CHECKPOINT_REVISION:
        raise ProvisioningError("checkpoint revision differs")
    if manifest["architecture"] != ARCHITECTURE:
        raise ProvisioningError("checkpoint architecture differs")
    if manifest["tensor_count"] != EXPECTED_TENSOR_COUNT:
        raise ProvisioningError("checkpoint tensor expectation differs")
    if not isinstance(manifest["tokenizer_identity"], str) or not manifest["tokenizer_identity"].startswith("glm52-gguf-tokenizer-v1:"):
        raise ProvisioningError("tokenizer identity differs")
    for key in ("checkpoint_set_sha256", "catalog_sha256"):
        if not isinstance(manifest[key], str) or not SHA256_RE.fullmatch(manifest[key]):
            raise ProvisioningError(f"invalid {key}")
    shards = manifest["shards"]
    if not isinstance(shards, list) or len(shards) != 6:
        raise ProvisioningError("production manifest requires exactly six shards")
    names = [item.get("filename") for item in shards]
    if names != EXPECTED_BASENAMES or len(set(names)) != 6:
        raise ProvisioningError("production shard names/order differ")
    for shard in shards:
        if set(shard) != {"filename", "size_bytes", "sha256"}:
            raise ProvisioningError("checkpoint shard fields differ")
        if not isinstance(shard["size_bytes"], int) or shard["size_bytes"] <= 0:
            raise ProvisioningError("checkpoint shard size is invalid")
        if not isinstance(shard["sha256"], str) or not SHA256_RE.fullmatch(shard["sha256"]):
            raise ProvisioningError("checkpoint shard hash is invalid")


def contains_absolute_path(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("/") or ("/" + "Users/") in value
    if isinstance(value, dict):
        return any(contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_absolute_path(item) for item in value)
    return False


def validate_public_review(review: dict[str, Any]) -> None:
    if review.get("schema") != REVIEW_SCHEMA or review.get("schema_version") != REVIEW_VERSION:
        raise ProvisioningError("unsupported public review schema")
    if review.get("manifest_kind") != MANIFEST_KIND:
        raise ProvisioningError("public manifest kind differs")
    if review.get("privacy") != "public_safe_hashes_and_basenames_only":
        raise ProvisioningError("public review privacy classification differs")
    if contains_absolute_path(review):
        raise ProvisioningError("public manifest review leaks an absolute path")
    if review.get("runtime_source_sha") != RUNTIME_SOURCE_SHA:
        raise ProvisioningError("public review runtime source differs")
    if review.get("checkpoint", {}).get("architecture") != ARCHITECTURE:
        raise ProvisioningError("public review architecture differs")
    if review.get("checkpoint", {}).get("layer_count") != EXPECTED_LAYER_COUNT:
        raise ProvisioningError("public review layer expectation differs")
    if review.get("checkpoint", {}).get("tensor_count") != EXPECTED_TENSOR_COUNT:
        raise ProvisioningError("public review tensor expectation differs")
    if review.get("checkpoint", {}).get("shard_count") != 6:
        raise ProvisioningError("public review shard expectation differs")
    policy = review.get("execution_policy", {})
    required_policy = {
        "identity_only": True,
        "tensor_execution_authorized": False,
        "quant_decode_authorized": False,
        "model_compute_authorized": False,
    }
    if policy != required_policy:
        raise ProvisioningError("public review execution policy is not identity-only")
    validation = review.get("validation", {})
    required_true = (
        "six_shards", "sizes_and_hashes", "architecture", "tokenizer_identity",
        "catalog_matches_committed_identity", "tensor_map_contract_compatible",
        "zero_tensor_execution", "zero_quant_decode", "zero_model_compute",
    )
    if any(validation.get(key) is not True for key in required_true):
        raise ProvisioningError("public review validation is incomplete")


def runtime_delta_is_non_runtime(paths: Iterable[str]) -> bool:
    runtime_prefixes = ("crates/", "python/", "app/", "Cargo.toml", "Cargo.lock", "build.rs")
    return all(not path.startswith(runtime_prefixes) for path in paths)


def changed_paths(repo: Path, old: str, new: str) -> list[str]:
    if not GIT_SHA_RE.fullmatch(old) or not GIT_SHA_RE.fullmatch(new):
        raise ProvisioningError("source binding requires full Git SHAs")
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{old}..{new}"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def validate_runtime_source_binding(repo: Path, runtime_sha: str, handoff_sha: str) -> list[str]:
    paths = changed_paths(repo, runtime_sha, handoff_sha)
    if runtime_sha != handoff_sha and not runtime_delta_is_non_runtime(paths):
        raise ProvisioningError(
            "handoff descendant changes runtime source; execution must use the exact runtime SHA"
        )
    return paths


def validate_admission_binding(repo: Path, binding: dict[str, Any]) -> None:
    if binding.get("schema") != "pulsarmlx.f017.m1-b-admission-binding":
        raise ProvisioningError("unsupported M1-B admission binding schema")
    if binding.get("schema_version") != 1:
        raise ProvisioningError("unsupported M1-B admission binding version")
    if binding.get("required_runtime_source_sha") != RUNTIME_SOURCE_SHA:
        raise ProvisioningError("M1-B binding does not require the reviewed runtime source")
    if binding.get("runtime_delta_from_stale_pin_contains_compiled_code") is not True:
        raise ProvisioningError("M1-B binding does not preserve the stale-pin finding")
    if binding.get("m1_b_attempts") != 0:
        raise ProvisioningError("M1-B binding must remain unexecuted during provisioning")
    access = binding.get("checkpoint_access", {})
    if access != {
        "provisioning_hash_and_header_catalog": True,
        "canonical_identity_mode_executed": False,
        "tensor_execution_count": 0,
        "quant_decode_count": 0,
        "model_compute_dispatch_count": 0,
    }:
        raise ProvisioningError("M1-B binding execution boundary differs")
    for path_key, hash_key in (
        ("handoff_document", "handoff_document_sha256"),
        ("fresh_authorization_document", "fresh_authorization_document_sha256"),
    ):
        relative = binding.get(path_key)
        expected_hash = binding.get(hash_key)
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise ProvisioningError(f"{path_key} must be repository-relative")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise ProvisioningError(f"{hash_key} is invalid")
        actual_hash = sha256_file(repo / relative)
        if actual_hash != expected_hash:
            raise ProvisioningError(f"{path_key} hash differs")


def provision(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = args.repo.resolve()
    root = args.checkpoint_root
    paths = discover_canonical_shards(root)
    checkpoint_binding = load_json(repo / "docs/validation/glm52-checkpoint.json")
    revision_binding = load_json(repo / "docs/validation/glm52-revision-binding.json")
    public_catalog = load_json(repo / "docs/research/glm52/raw/f016-c01-catalog-0001.json")

    expected_by_name = {item["filename"]: item for item in checkpoint_binding["files"]}
    shards: list[dict[str, Any]] = []
    for ordinal, path in enumerate(paths, start=1):
        size = path.stat().st_size
        expected = expected_by_name.get(path.name)
        if expected is None or size != expected["size_bytes"]:
            raise ProvisioningError(f"shard {path.name} size differs from frozen binding")
        print(f"hashing {path.name} ({size} bytes) ...", flush=True)
        digest = sha256_file(path)
        if digest != expected["sha256"]:
            raise ProvisioningError(f"shard {path.name} hash differs from frozen binding")
        shards.append(
            {"filename": path.name, "size_bytes": size, "sha256": digest, "ordinal": ordinal}
        )

    set_hash = checkpoint_set_sha256(shards)
    if set_hash != checkpoint_binding["checkpoint_set_sha256"]:
        raise ProvisioningError("checkpoint-set hash differs from frozen binding")
    if revision_binding["checkpoint_set_sha256"] != set_hash:
        raise ProvisioningError("revision binding checkpoint-set hash differs")
    if revision_binding.get("revision") != CHECKPOINT_REVISION:
        raise ProvisioningError("immutable revision differs")

    print("parsing GGUF headers/catalog only ...", flush=True)
    tensors, catalog_state = inspect_catalog(paths)
    validate_catalog_against_public(tensors, catalog_state, public_catalog)
    tokenizer_id, tokenizer_details = tokenizer_identity(catalog_state["metadata"])
    catalog_hash = catalog_sha256(tensors)
    map_hash = tensor_map_contract_sha256(tensors)

    runner_manifest = {
        "schema": MANIFEST_SCHEMA,
        "schema_version": MANIFEST_VERSION,
        "kind": "production",
        "immutable_revision": CHECKPOINT_REVISION,
        "architecture": ARCHITECTURE,
        "tokenizer_identity": tokenizer_id,
        "checkpoint_set_sha256": set_hash,
        "catalog_sha256": catalog_hash,
        "tensor_count": EXPECTED_TENSOR_COUNT,
        "shards": [
            {"filename": item["filename"], "size_bytes": item["size_bytes"], "sha256": item["sha256"]}
            for item in shards
        ],
    }
    validate_runner_manifest(runner_manifest)
    manifest_bytes = canonical_json_bytes(runner_manifest)

    timestamp = args.created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    review = {
        "schema": REVIEW_SCHEMA,
        "schema_version": REVIEW_VERSION,
        "manifest_kind": MANIFEST_KIND,
        "created_at": timestamp,
        "runtime_source_sha": args.runtime_source_sha,
        "privacy": "public_safe_hashes_and_basenames_only",
        "checkpoint": {
            "immutable_revision": CHECKPOINT_REVISION,
            "architecture": ARCHITECTURE,
            "shard_count": 6,
            "tensor_count": EXPECTED_TENSOR_COUNT,
            "layer_count": EXPECTED_LAYER_COUNT,
            "tokenizer_identity": tokenizer_id,
            "tokenizer_details": tokenizer_details,
        },
        "shards": shards,
        "aggregate": {
            "total_bytes": sum(item["size_bytes"] for item in shards),
            "checkpoint_set_sha256": set_hash,
            "catalog_sha256": catalog_hash,
            "tensor_map_version": TENSOR_MAP_VERSION,
            "tensor_map_contract_sha256": map_hash,
            "private_manifest_sha256": sha256_bytes(manifest_bytes),
        },
        "catalog_shards": catalog_state["shards"],
        "execution_policy": {
            "identity_only": True,
            "tensor_execution_authorized": False,
            "quant_decode_authorized": False,
            "model_compute_authorized": False,
        },
        "validation": {
            "six_shards": True,
            "sizes_and_hashes": True,
            "architecture": True,
            "tokenizer_identity": True,
            "catalog_matches_committed_identity": True,
            "tensor_map_contract_compatible": True,
            "zero_tensor_execution": True,
            "zero_quant_decode": True,
            "zero_model_compute": True,
        },
        "checkpoint_access": {
            "shards_opened_for_streaming_hash": 6,
            "headers_and_catalog_parsed": True,
            "tensor_payload_ranges_read": 0,
        },
    }
    validate_public_review(review)
    write_exclusive(args.out, manifest_bytes)
    if args.public_review_out:
        write_exclusive(args.public_review_out, canonical_json_bytes(review), mode=0o644)
    return runner_manifest, review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--public-review-out", type=Path)
    parser.add_argument("--runtime-source-sha", default=RUNTIME_SOURCE_SHA)
    parser.add_argument("--created-at")
    args = parser.parse_args(argv)
    if args.runtime_source_sha != RUNTIME_SOURCE_SHA:
        parser.error(f"runtime source must be {RUNTIME_SOURCE_SHA}")
    try:
        manifest, review = provision(args)
    except (ProvisioningError, OSError, subprocess.CalledProcessError) as error:
        print(f"provision_f017_checkpoint_manifest: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "passed",
                "manifest_sha256": review["aggregate"]["private_manifest_sha256"],
                "checkpoint_set_sha256": manifest["checkpoint_set_sha256"],
                "catalog_sha256": manifest["catalog_sha256"],
                "tensor_execution_count": 0,
                "quant_decode_count": 0,
                "model_compute_dispatch_count": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

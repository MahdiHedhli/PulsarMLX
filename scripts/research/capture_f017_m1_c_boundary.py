#!/usr/bin/env python3
"""Capture the single reviewed F017 M1-C F32 tensor boundary.

The production CLI is intentionally frozen to ``output_norm.weight``.  It
performs one exact ``os.pread`` against one reviewed shard range, writes the
checkpoint-derived payload to an exclusive local-only fixture, reparses only
that fixture as little-endian IEEE-754 f32, and writes a public-safe evidence
projection plus the private local-boundary manifest.  It never imports MLX,
decodes a quantized format, or executes model math.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import struct
import sys
from pathlib import Path
from typing import Any, Iterable


RUNTIME_SOURCE_SHA = "b29202171a279cd3bb2ac2cf4dc6b3be7486019e"
M1_A_EVIDENCE_SHA256 = "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805"
M1_B_EVIDENCE_SHA256 = "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770"
CHECKPOINT_MANIFEST_SHA256 = "208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4"
CHECKPOINT_SET_SHA256 = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
CATALOG_SHA256 = "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0"
CATALOG_ARTIFACT_SHA256 = "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19"
MAP_SHA256 = "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
CHECKPOINT_REVISION = "abc55e72527792c6e77069c99b4cb7de16fa9f23"
TENSOR_NAME = "output_norm.weight"
SHARD_BASENAME = "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
SHARD_SHA256 = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
SHARD_SIZE = 49_105_028_960
TENSOR_OFFSET = 535_291_744
TENSOR_LENGTH = 24_576
TENSOR_DIMENSIONS = [6_144]
TENSOR_TYPE = "F32"
DECODER_CONTRACT_ID = "quant::row_to_f32:f32-little-endian-v1"
DECODER_CONTRACT_SHA256 = "b9d0c302ec9761432f55433d8b2b8208d4a366adc875370b7d7493d6cfc3b402"
GENERATOR_PATH = "scripts/research/capture_f017_m1_c_boundary.py"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class CaptureError(ValueError):
    """Fail-closed M1-C capture error."""


def _reject_duplicates(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureError(f"cannot load {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise CaptureError(f"{path.name}: top-level JSON must be an object")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_admission(admission: dict[str, Any]) -> None:
    required = {
        "environment_kind",
        "telemetry_source",
        "architecture",
        "physical_memory_bytes",
        "memory_floor_bytes",
        "available_memory_bytes",
        "memory_pressure",
        "swap_used_bytes",
        "swap_safe",
        "checkpoint_volume_free_bytes",
        "evidence_volume_free_bytes",
        "load_averages",
        "competing_inference_clear",
        "port_1234_listener",
        "thermal_state",
        "performance_warning",
        "mlx_native",
        "mlx_c",
    }
    if set(admission) != required:
        raise CaptureError("admission snapshot fields differ")
    if admission["environment_kind"] != "production_reviewed":
        raise CaptureError("production-reviewed environment is required")
    if admission["telemetry_source"] != "measured_host":
        raise CaptureError("measured host telemetry is required")
    if admission["architecture"] != "arm64":
        raise CaptureError("arm64 is required")
    if admission["memory_floor_bytes"] <= 0 or admission["available_memory_bytes"] < admission["memory_floor_bytes"]:
        raise CaptureError("memory floor failed")
    if admission["memory_pressure"] != "normal" or admission["swap_safe"] is not True:
        raise CaptureError("memory pressure or swap gate failed")
    if admission["checkpoint_volume_free_bytes"] <= 0 or admission["evidence_volume_free_bytes"] <= 0:
        raise CaptureError("disk admission failed")
    if admission["competing_inference_clear"] is not True or admission["port_1234_listener"] is not False:
        raise CaptureError("competing inference gate failed")
    if admission["thermal_state"] != "normal" or admission["performance_warning"] is not False:
        raise CaptureError("thermal/performance gate failed")
    if not isinstance(admission["load_averages"], list) or len(admission["load_averages"]) != 3:
        raise CaptureError("load averages are unavailable")
    expected_libraries = {
        "mlx_native": ("0.31.2", "6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed"),
        "mlx_c": ("0.6.0", "a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62"),
    }
    for key, (version, digest) in expected_libraries.items():
        observed = admission[key]
        if observed != {"version": version, "sha256": digest, "architecture": "arm64", "matched": True}:
            raise CaptureError(f"{key} identity differs")


def validate_checkpoint_manifest(
    manifest_path: Path,
    shard_path: Path,
    *,
    expected_manifest_sha256: str = CHECKPOINT_MANIFEST_SHA256,
    expected_shard_basename: str = SHARD_BASENAME,
    expected_shard_sha256: str = SHARD_SHA256,
    expected_shard_size: int = SHARD_SIZE,
) -> dict[str, Any]:
    if sha256_file(manifest_path) != expected_manifest_sha256:
        raise CaptureError("private checkpoint manifest hash differs")
    manifest = load_json(manifest_path)
    if manifest.get("kind") != "production":
        raise CaptureError("checkpoint manifest is not production")
    if manifest.get("immutable_revision") != CHECKPOINT_REVISION:
        raise CaptureError("checkpoint revision differs")
    if manifest.get("architecture") != "glm-dsa":
        raise CaptureError("checkpoint architecture differs")
    if manifest.get("checkpoint_set_sha256") != CHECKPOINT_SET_SHA256:
        raise CaptureError("checkpoint-set binding differs")
    if manifest.get("catalog_sha256") != CATALOG_SHA256 or manifest.get("tensor_count") != 1_809:
        raise CaptureError("catalog binding differs")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or len(shards) != 6:
        raise CaptureError("checkpoint manifest does not contain six shards")
    target = next((item for item in shards if item.get("filename") == expected_shard_basename), None)
    if target != {
        "filename": expected_shard_basename,
        "size_bytes": expected_shard_size,
        "sha256": expected_shard_sha256,
    }:
        raise CaptureError("target shard identity differs")
    metadata = shard_path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CaptureError("target shard must be a non-symlink regular file")
    if shard_path.name != expected_shard_basename or metadata.st_size != expected_shard_size:
        raise CaptureError("target shard basename or size differs")
    if not os.access(shard_path, os.R_OK):
        raise CaptureError("target shard is unreadable")
    return manifest


def validate_catalog(repo: Path) -> None:
    catalog_path = repo / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
    if sha256_file(catalog_path) != CATALOG_ARTIFACT_SHA256:
        raise CaptureError("catalog artifact hash differs")
    catalog = load_json(catalog_path)
    tensors = catalog.get("tensors")
    if not isinstance(tensors, list):
        raise CaptureError("catalog tensor list is unavailable")
    matches = [tensor for tensor in tensors if tensor.get("name") == TENSOR_NAME]
    expected = {
        "data_offset_abs": TENSOR_OFFSET,
        "data_offset_rel": 535_265_280,
        "dims": TENSOR_DIMENSIONS,
        "file": SHARD_BASENAME,
        "name": TENSOR_NAME,
        "offset_in_range": True,
        "type": TENSOR_TYPE,
        "type_id": 0,
    }
    if matches != [expected]:
        raise CaptureError("target catalog entry differs")


def reserve_outputs(paths: list[Path]) -> list[tuple[Path, int]]:
    reserved: list[tuple[Path, int]] = []
    try:
        for path in paths:
            if path.is_symlink():
                raise CaptureError(f"output target is a symlink: {path.name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            reserved.append((path, descriptor))
    except BaseException:
        for path, descriptor in reserved:
            os.close(descriptor)
            path.unlink(missing_ok=True)
        raise
    return reserved


def write_reserved(descriptor: int, payload: bytes) -> None:
    with os.fdopen(descriptor, "wb", closefd=True) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def f32_diagnostics(payload: bytes, dimensions: list[int]) -> tuple[dict[str, Any], bytes]:
    if len(payload) % 4 != 0:
        raise CaptureError("F32 payload byte length is not divisible by four")
    count = len(payload) // 4
    expected_count = math.prod(dimensions)
    if count != expected_count:
        raise CaptureError("F32 element count differs from shape")
    values = [item[0] for item in struct.iter_unpack("<f", payload)]
    finite_count = sum(math.isfinite(value) for value in values)
    if finite_count != count:
        raise CaptureError("F32 payload contains NaN or infinity")
    signed_zero_count = sum(value == 0.0 and (struct.unpack("<I", struct.pack("<f", value))[0] >> 31) for value in values)
    reparsed = b"".join(struct.pack("<f", value) for value in values)
    if reparsed != payload:
        raise CaptureError("F32 reparse did not reproduce exact IEEE-754 bits")
    diagnostics = {
        "element_count": count,
        "finite_count": finite_count,
        "non_finite_count": count - finite_count,
        "minimum": min(values),
        "maximum": max(values),
        "mean": math.fsum(values) / count,
        "signed_zero_count": signed_zero_count,
        "ieee754_reparse_identical": True,
    }
    return diagnostics, reparsed


def capture_boundary(args: argparse.Namespace) -> dict[str, Any]:
    if not GIT_SHA_RE.fullmatch(args.tooling_source_sha):
        raise CaptureError("tooling source SHA is invalid")
    admission = load_json(args.admission_snapshot)
    validate_admission(admission)
    validate_checkpoint_manifest(args.checkpoint_manifest, args.shard)
    validate_catalog(args.repo)
    if sha256_file(args.repo / "crates/quant/src/lib.rs") != DECODER_CONTRACT_SHA256:
        raise CaptureError("frozen F32 decoder contract hash differs")

    reserved = reserve_outputs([args.fixture_out, args.local_manifest_out, args.evidence_out])
    descriptors = {path: descriptor for path, descriptor in reserved}
    try:
        shard_descriptor = os.open(args.shard, os.O_RDONLY)
        try:
            payload = os.pread(shard_descriptor, TENSOR_LENGTH, TENSOR_OFFSET)
        finally:
            os.close(shard_descriptor)
        if len(payload) != TENSOR_LENGTH:
            raise CaptureError(f"short read: expected {TENSOR_LENGTH}, got {len(payload)}")
        payload_sha256 = sha256_bytes(payload)
        diagnostics, decoded_bytes = f32_diagnostics(payload, TENSOR_DIMENSIONS)
        decoded_sha256 = sha256_bytes(decoded_bytes)

        write_reserved(descriptors.pop(args.fixture_out), payload)
        replay = args.fixture_out.read_bytes()
        if replay != payload or sha256_bytes(replay) != payload_sha256:
            raise CaptureError("local fixture replay differs from captured payload")

        local_manifest = {
            "schema": "pulsarmlx.f017.local-real-boundary-fixture",
            "schema_version": 1,
            "source_sha": RUNTIME_SOURCE_SHA,
            "checkpoint_set_sha256": CHECKPOINT_SET_SHA256,
            "checkpoint_revision": CHECKPOINT_REVISION,
            "tensor": {
                "name": TENSOR_NAME,
                "shard_id": SHARD_BASENAME,
                "shard_sha256": SHARD_SHA256,
                "offset": TENSOR_OFFSET,
                "length": TENSOR_LENGTH,
                "quantization": TENSOR_TYPE,
                "dimensions": TENSOR_DIMENSIONS,
            },
            "decoder_contract": {"id": DECODER_CONTRACT_ID, "sha256": DECODER_CONTRACT_SHA256},
            "fixture": {
                "path": str(args.fixture_out.resolve()),
                "byte_length": TENSOR_LENGTH,
                "sha256": payload_sha256,
            },
            "reference": {
                "generator": GENERATOR_PATH,
                "generator_source_sha": args.tooling_source_sha,
                "independent": True,
                "input_sha256": payload_sha256,
                "expected_output_sha256": decoded_sha256,
            },
            "privacy_classification": "local_only_private_checkpoint_derived",
            "redistributable": False,
        }
        write_reserved(descriptors.pop(args.local_manifest_out), canonical_json_bytes(local_manifest))

        evidence = {
            "schema": "pulsarmlx.f017.m1-c-real-tensor-evidence",
            "schema_version": 1,
            "result": "M1-C ACCEPTED",
            "runtime_source_sha": RUNTIME_SOURCE_SHA,
            "tooling_source_sha": args.tooling_source_sha,
            "bindings": {
                "m1_a_evidence_sha256": M1_A_EVIDENCE_SHA256,
                "m1_b_evidence_sha256": M1_B_EVIDENCE_SHA256,
                "checkpoint_manifest_sha256": CHECKPOINT_MANIFEST_SHA256,
                "checkpoint_set_sha256": CHECKPOINT_SET_SHA256,
                "catalog_sha256": CATALOG_SHA256,
                "tensor_map_contract_sha256": MAP_SHA256,
            },
            "admission": admission,
            "tensor": {
                "name": TENSOR_NAME,
                "shard_basename": SHARD_BASENAME,
                "shard_sha256": SHARD_SHA256,
                "offset": TENSOR_OFFSET,
                "length": TENSOR_LENGTH,
                "dimensions": TENSOR_DIMENSIONS,
                "gguf_type": TENSOR_TYPE,
                "payload_sha256": payload_sha256,
            },
            "f32_validation": {**diagnostics, "decoded_output_sha256": decoded_sha256},
            "isolation": {
                "checkpoint_accessed": True,
                "real_tensor_payload_accessed": True,
                "tensor_payload_count": 1,
                "shard_open_count": 1,
                "positional_read_count": 1,
                "bytes_read": TENSOR_LENGTH,
                "quant_decode_count": 0,
                "tensor_execution_count": 0,
                "model_compute_dispatch_count": 0,
                "projection_count": 0,
                "expert_execution_count": 0,
                "layer_execution_count": 0,
                "logits_execution_count": 0,
                "mlx_compute_count": 0,
            },
            "privacy": {
                "classification": "local_only_private_checkpoint_derived",
                "payload_committed": False,
                "absolute_paths_in_public_evidence": False,
            },
            "validation": {
                "exclusive_targets_acquired_before_payload_read": True,
                "short_read_rejected": True,
                "fixture_replay_exact": True,
                "independent_f32_reader": True,
                "local_manifest_pending_rust_validation": True,
            },
        }
        write_reserved(descriptors.pop(args.evidence_out), canonical_json_bytes(evidence))
        return evidence
    except BaseException:
        for path, descriptor in list(descriptors.items()):
            os.close(descriptor)
            path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--admission-snapshot", type=Path, required=True)
    parser.add_argument("--fixture-out", type=Path, required=True)
    parser.add_argument("--local-manifest-out", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path, required=True)
    parser.add_argument("--tooling-source-sha", required=True)
    args = parser.parse_args(argv)
    try:
        evidence = capture_boundary(args)
    except (CaptureError, OSError) as error:
        print(f"capture_f017_m1_c_boundary: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "result": evidence["result"],
        "tensor": evidence["tensor"]["name"],
        "payload_sha256": evidence["tensor"]["payload_sha256"],
        "tensor_payload_count": evidence["isolation"]["tensor_payload_count"],
        "quant_decode_count": evidence["isolation"]["quant_decode_count"],
        "model_compute_dispatch_count": evidence["isolation"]["model_compute_dispatch_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

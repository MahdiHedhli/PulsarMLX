#!/usr/bin/env python3
"""Open-once, non-computational resolver for the banked representative FFN output."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-output-reuse-authorization-v1.json"
OUTPUT_ROOT = Path.home() / ".local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs"
EXECUTION_EVIDENCE_SHA = "946d41a37cb4ae97938eae195c6b665441088c197312474613f8ca4cb282b2df"
RELEASE_SHA = "f6aa2133e91c9fc1639f3424e656f6db94677c71e7e1e03c64c5212bbed8f5b6"
APPROVAL_SHA = "03ce0086ef955f3edfd7a9b218a72d6c8a2caa55bf40ec188a155c8924ab636b"
ARITHMETIC_SHA = "1054d014c23628fa56771518f066d14cfd445b0d7b4ba7da98b638c37981cdbb"
FFN_AUTHORIZATION_SHA = "69e6e49b0e2967b9b7cde7ee00154b7abdaa08609904eca75e54c29b8e4ca1a5"
APPROVAL_REVIEW_SHA = "23468de7972c6dfd08dd87b43571233850e81a9fb8249c04d0f33ab463b4dae9"
OUTPUT_SHA = "4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a"
MANIFEST_SHA = "0f6a887fed8e0e4a96494f50bf94879ffec74ef6bc1d0fa64f9b0a3771efc04c"
SURFACE = "CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32"
ROLE = "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT"


class ReuseError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReuseError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256(path.read_bytes())


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"DUPLICATE_KEY:{key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def read_exact(descriptor: int, size: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        require(bool(chunk), "SHORT_READ")
        chunks.append(chunk)
        remaining -= len(chunk)
    require(os.read(descriptor, 1) == b"", "LONG_READ")
    return b"".join(chunks)


def open_directory(path: Path) -> int:
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode), "DIRECTORY_IDENTITY")
    require(before.st_uid == os.getuid(), "DIRECTORY_OWNER")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    observed = os.fstat(descriptor)
    require((before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino), "DIRECTORY_SUBSTITUTION")
    return descriptor


def open_leaf(root_fd: int, name: str, size: int) -> tuple[int, os.stat_result, bytes]:
    require(isinstance(name, str) and Path(name).name == name, "PURE_BASENAME_REQUIRED")
    descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
    metadata = os.fstat(descriptor)
    require(stat.S_ISREG(metadata.st_mode), "REGULAR_FILE_REQUIRED")
    require(metadata.st_uid == os.getuid(), "OWNER_REQUIRED")
    require(metadata.st_nlink == 1, "SINGLE_HARD_LINK_REQUIRED")
    require(metadata.st_mode & 0o222 == 0, "READ_ONLY_REQUIRED")
    require(metadata.st_size == size, "BYTE_LENGTH")
    return descriptor, metadata, read_exact(descriptor, size)


def validate_authorization(document: dict[str, Any]) -> None:
    expected_keys = {
        "schema", "schema_version", "authorization_id", "consumer_id", "preparation_base_head",
        "status", "real_event_authorized", "source_authority", "completed_attempt", "private_manifest",
        "retained_ffn_output", "reproduction_adjudication", "surface_isolation", "resolver",
        "consumer_scope", "accounting", "prohibitions", "stop_boundary", "next_authority",
    }
    require(set(document) == expected_keys, "AUTHORIZATION_KEYS")
    require(document.get("schema") == "pulsarmlx.f017.representative-ffn-output-reuse-authorization", "AUTHORIZATION_SCHEMA")
    require(document.get("schema_version") == "1.0.0", "AUTHORIZATION_VERSION")
    require(document.get("authorization_id") == "F017-REPRESENTATIVE-FFN-OUTPUT-REUSE-1", "AUTHORIZATION_ID")
    require(document.get("consumer_id") == "F017-REPRESENTATIVE-S2-PREPARATION-1", "CONSUMER_ID")
    require(document.get("preparation_base_head") == "52a68bcd1d7dce66668a5c062065961133799c28", "PREPARATION_HEAD")
    require(document.get("status") == "PREPARED_REVIEW_REQUIRED" and document.get("real_event_authorized") is False, "AUTHORIZATION_STATE")

    sources = document.get("source_authority", {})
    expected_sources = {
        "execution_evidence": ("docs/architecture/reviews/evidence/f017-representative-ffn-composition-real-execution-result-v1.json", EXECUTION_EVIDENCE_SHA),
        "single_use_release_v2": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-single-use-release-v2.json", RELEASE_SHA),
        "independent_release_approval": ("docs/architecture/reviews/evidence/f017-representative-ffn-composition-single-use-release-v2-independent-approval-v1.json", APPROVAL_SHA),
        "approval_review": ("docs/architecture/reviews/evidence/f017-representative-ffn-composition-release-v2-approval-cycle-01-independent-review.json", APPROVAL_REVIEW_SHA),
        "ffn_authorization": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-authorization-v1.json", FFN_AUTHORIZATION_SHA),
        "arithmetic_contract": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-arithmetic-v1.json", ARITHMETIC_SHA),
    }
    require(set(sources) == set(expected_sources) | {"execution_code_head"}, "SOURCE_CENSUS")
    for key, (relative_path, expected_sha) in expected_sources.items():
        require(sources[key] == {"path": relative_path, "sha256": expected_sha}, f"SOURCE_BINDING:{key}")
        require(sha256_path(ROOT / relative_path) == expected_sha, f"SOURCE_BYTES:{key}")
    require(sources.get("execution_code_head") == "0c5ac29777e78aa8a2755feb378ab47dbcfaae0b", "EXECUTION_CODE_HEAD")

    attempt = document.get("completed_attempt", {})
    require(attempt == {
        "event_id": "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1",
        "release_id": "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1-RELEASE-2",
        "attempt_id": "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1-ATTEMPT-1",
        "attempt_start": {"relative_path": "attempt-start.json", "sha256": "cc76bf06bd4fff4a616d2a16407bfe1639134ed0c6f3290865dc424e6501634c", "byte_length": 1157},
        "ffn_start": {"relative_path": "ffn-start.json", "sha256": "0f97e1958d3e5e133b8725fc84693bb01001d06514f4d89f87c41390e179c853", "byte_length": 654},
        "receipt": {"relative_path": "ffn-execution-receipt.json", "sha256": "8c55a32198070e3f9ef087242cebc0474151259ed0564d7963044ec5ad24b84e", "byte_length": 1540},
        "terminal": {"relative_path": "terminal.json", "sha256": "22cd0d23a72470acf8ce706140578602831b047e8562e577a7e1297d444ed1d9", "byte_length": 923, "disposition": "COMPLETE", "output_authority": True},
        "token_consumed": True,
        "retry": False,
        "resume": False,
        "second_attempt": False,
    }, "COMPLETED_ATTEMPT")

    require(document.get("private_manifest") == {
        "relative_path": "representative-ffn-output-private-manifest-v1.json",
        "sha256": MANIFEST_SHA,
        "byte_length": 627,
        "machine_local_root_not_committed": True,
        "machine_local_absolute_path_not_committed": True,
        "regular_file": True,
        "non_symlink": True,
        "hard_link_count": 1,
        "read_only": True,
    }, "PRIVATE_MANIFEST")

    artifact = document.get("retained_ffn_output", {})
    require(artifact == {
        "relative_path": "representative-ffn-output.f64le",
        "sha256": OUTPUT_SHA,
        "semantic_role": ROLE,
        "semantic_surface": SURFACE,
        "dtype": "little-endian-f64",
        "shape": [6144],
        "byte_length": 49152,
        "finite": True,
        "expected_equals_before_equals_consumed_equals_after": True,
        "open_once_consume_same_descriptor": True,
        "fstat_before_and_after": True,
        "regular_file": True,
        "non_symlink": True,
        "hard_link_count": 1,
        "read_only": True,
        "no_writable_alias": True,
    }, "RETAINED_FFN_OUTPUT")

    require(document.get("reproduction_adjudication") == {
        "post_event_reproduction_authorized_by_release": False,
        "post_event_reproduction_performed": False,
        "required_for_reuse_acceptance": False,
        "basis": "EXACT_BYTE_RETENTION_PLUS_COMPLETE_TERMINAL_MANIFEST_RECEIPT_INPUT_IDENTITIES_AND_ACCEPTED_ARITHMETIC",
        "precedent": "REPRESENTATIVE_ROUTED_AGGREGATE_CROSS_EVENT_REUSE_ACCEPTED_WITHOUT_POST_EVENT_RECOMPUTATION",
        "retroactive_execution_authority_expansion": False,
        "future_deterministic_reproduction_requires_separate_authority": True,
    }, "REPRODUCTION_ADJUDICATION")
    require(document.get("surface_isolation") == {
        "proof_reference_surface_required": True,
        "production_serial_f32_authority": False,
        "surface_conversion_authorized": False,
        "serial_f32_substitution_authorized": False,
        "ffn_recomputation_fallback": False,
        "routed_aggregate_recomputation_fallback": False,
        "shared_expert_recomputation_fallback": False,
        "alternate_ffn_output": False,
        "historical_ffn_surface_substitution": False,
    }, "SURFACE_ISOLATION")

    resolver = document.get("resolver", {})
    require(resolver.get("path") == "scripts/research/f017_representative_ffn_output_reuse_v1.py", "RESOLVER_PATH")
    require(resolver.get("sha256") == sha256_path(Path(__file__).resolve()), "RESOLVER_SHA")
    for capability in ("checkpoint_capability", "shard_capability", "expert_compute_capability",
                       "shared_expert_compute_capability", "routed_aggregate_compute_capability",
                       "ffn_compute_capability", "s1_materialization_capability", "s2_compute_capability"):
        require(resolver.get(capability) is False, f"RESOLVER_CAPABILITY:{capability}")

    require(document.get("consumer_scope") == {
        "allowed": "CHECKPOINT_FREE_REPRESENTATIVE_S2_PREPARATION_AND_INPUT_AUTHORITY_ONLY",
        "ffn_release_v2_rerun": False,
        "ffn_recomputation": False,
        "s1_materialization": False,
        "s2_construction": False,
    }, "CONSUMER_SCOPE")
    require(document.get("accounting") == {
        "real_payload_ledger_before": 175,
        "real_payload_ledger_after": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "release_v2_reruns": 0,
        "new_ffn_compositions": 0,
        "s1_materializations": 0,
        "s2_constructions": 0,
    }, "ACCOUNTING")
    require(all(value is True for value in document.get("prohibitions", {}).values()), "PROHIBITIONS")
    require(set(document.get("prohibitions", {})) == {
        "checkpoint_access", "shard_open", "expert_execution", "shared_expert_execution",
        "release_v2_rerun", "ffn_recomputation", "production_serial_f32_relabeling",
        "alternate_or_historical_ffn_output", "s1_materialization", "s2_construction",
    }, "PROHIBITION_CENSUS")
    require(document.get("stop_boundary") == "AFTER_FFN_OUTPUT_REUSE_PREFLIGHT_BEFORE_S1_MATERIALIZATION_OR_S2_CONSTRUCTION", "STOP_BOUNDARY")
    require(document.get("next_authority") == "SEPARATE_CHECKPOINT_FREE_S1_OR_S2_PREPARATION_AUTHORITY_AS_APPLICABLE", "NEXT_AUTHORITY")


def validate_manifest(raw: bytes, artifact: dict[str, Any]) -> None:
    manifest = json.loads(raw, object_pairs_hook=unique)
    require(manifest.get("schema") == "pulsarmlx.f017.representative-ffn-output-private-manifest", "MANIFEST_SCHEMA")
    require(manifest.get("schema_version") == "1.0.0", "MANIFEST_VERSION")
    require(manifest.get("semantic_surface") == SURFACE, "MANIFEST_SURFACE")
    require(manifest.get("authority_requires_matching_complete_terminal") is True, "MANIFEST_TERMINAL_REQUIREMENT")
    require(manifest.get("execution_receipt_relative_path") == "../attempt-state/ffn-execution-receipt.json", "MANIFEST_RECEIPT_PATH")
    entries = manifest.get("artifacts")
    require(isinstance(entries, list) and len(entries) == 1, "MANIFEST_CENSUS")
    require(entries[0] == {
        "byte_length": 49152,
        "dtype": "little-endian-f64",
        "finite": True,
        "semantic_role": ROLE,
        "sha256": artifact["sha256"],
        "shape": [6144],
        "symbolic_path": artifact["relative_path"],
    }, "MANIFEST_ARTIFACT")


def validate_output_bytes(raw: bytes, artifact: dict[str, Any]) -> tuple[float, ...]:
    require(artifact.get("dtype") == "little-endian-f64", "FFN_OUTPUT_DTYPE")
    require(artifact.get("shape") == [6144] and artifact.get("byte_length") == 49152, "FFN_OUTPUT_GEOMETRY")
    require(len(raw) == 49152, "FFN_OUTPUT_BYTE_LENGTH")
    values = struct.unpack("<6144d", raw)
    require(all(math.isfinite(value) for value in values), "FFN_OUTPUT_NONFINITE")
    return values


def validate_attempt_state(document: dict[str, Any], release_root: Path) -> None:
    state_fd = open_directory(release_root / "attempt-state")
    observed: dict[str, dict[str, Any]] = {}
    try:
        for key in ("attempt_start", "ffn_start", "receipt", "terminal"):
            identity = document["completed_attempt"][key]
            descriptor, _, raw = open_leaf(state_fd, identity["relative_path"], identity["byte_length"])
            try:
                require(sha256(raw) == identity["sha256"], f"ATTEMPT_STATE_SHA:{key}")
                observed[key] = json.loads(raw, object_pairs_hook=unique)
            finally:
                os.close(descriptor)
    finally:
        os.close(state_fd)
    terminal = observed["terminal"]
    receipt = observed["receipt"]
    require(terminal.get("disposition") == "COMPLETE" and terminal.get("output_authority") is True, "TERMINAL_AUTHORITY")
    require(terminal.get("output_sha256") == receipt.get("output_sha256") == OUTPUT_SHA, "TERMINAL_RECEIPT_OUTPUT")
    require(terminal.get("output_manifest_sha256") == receipt.get("output_manifest_sha256") == MANIFEST_SHA, "TERMINAL_RECEIPT_MANIFEST")
    require(terminal.get("execution_receipt_sha256") == document["completed_attempt"]["receipt"]["sha256"], "TERMINAL_RECEIPT_SHA")
    require(observed["ffn_start"].get("ffn_compositions") == receipt.get("ffn_compositions") == terminal.get("ffn_compositions") == 1, "FFN_ACCOUNTING")


class ValidatedFfnOutput:
    def __init__(self, descriptor: int, metadata: os.stat_result, raw: bytes, expected_sha: str):
        self.descriptor = descriptor
        self.metadata = metadata
        self.raw = raw
        self.expected_sha = expected_sha
        self.before_sha256 = sha256(raw)

    def consumed_sha256(self) -> str:
        return sha256(self.raw)

    def verify_after(self) -> str:
        after = read_exact(self.descriptor, len(self.raw))
        metadata = os.fstat(self.descriptor)
        require((self.metadata.st_dev, self.metadata.st_ino) == (metadata.st_dev, metadata.st_ino), "OUTPUT_OBJECT_CHANGED")
        after_sha = sha256(after)
        require(self.before_sha256 == self.consumed_sha256() == after_sha == self.expected_sha, "EXPECTED_BEFORE_CONSUMED_AFTER")
        return after_sha

    def close(self) -> None:
        os.close(self.descriptor)


def open_validated(document: dict[str, Any], output_root: Path) -> ValidatedFfnOutput:
    validate_authorization(document)
    require(output_root.resolve() == OUTPUT_ROOT.resolve(), "FIXED_OUTPUT_ROOT")
    validate_attempt_state(document, output_root.parent)
    artifact = document["retained_ffn_output"]
    manifest_identity = document["private_manifest"]
    root_fd = open_directory(output_root)
    try:
        manifest_fd, _, manifest_raw = open_leaf(root_fd, manifest_identity["relative_path"], manifest_identity["byte_length"])
        try:
            require(sha256(manifest_raw) == manifest_identity["sha256"], "MANIFEST_SHA")
            validate_manifest(manifest_raw, artifact)
        finally:
            os.close(manifest_fd)
        descriptor, metadata, raw = open_leaf(root_fd, artifact["relative_path"], artifact["byte_length"])
    finally:
        os.close(root_fd)
    before_sha = sha256(raw)
    require(before_sha == artifact["sha256"], "FFN_OUTPUT_BEFORE_IDENTITY")
    validate_output_bytes(raw, artifact)
    return ValidatedFfnOutput(descriptor, metadata, raw, artifact["sha256"])


def preflight_and_consume(document: dict[str, Any], output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    retained = open_validated(document, output_root)
    try:
        consumed_sha = retained.consumed_sha256()
        finite_count = sum(math.isfinite(value[0]) for value in struct.iter_unpack("<d", retained.raw))
        after_sha = retained.verify_after()
        return {
            "disposition": "REPRESENTATIVE_FFN_OUTPUT_REUSE_PREFLIGHT_PASS",
            "expected_sha256": retained.expected_sha,
            "before_sha256": retained.before_sha256,
            "consumed_sha256": consumed_sha,
            "after_sha256": after_sha,
            "finite_count": finite_count,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "shared_expert_executions": 0,
            "release_v2_reruns": 0,
            "new_ffn_compositions": 0,
            "s1_materializations": 0,
            "s2_constructions": 0,
        }
    finally:
        retained.close()


def main() -> int:
    document = load(AUTH)
    print(json.dumps(preflight_and_consume(document), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

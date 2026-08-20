#!/usr/bin/env python3
"""Open-once, non-computational resolver for the banked representative S1."""

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
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-output-reuse-authorization-v1.json"
RELEASE_ROOT = Path.home() / ".local/share/pulsarmlx/f017/representative-s1-materialization-release-2"
OUTPUT_ROOT = RELEASE_ROOT / "outputs"
STATE_ROOT = RELEASE_ROOT / "attempt-state"
EVIDENCE_SHA = "ea924afbc8972c194adc9d8a9759e1fca35ae8c2ab362225477cb4c54229fb55"
AUTHORIZATION_SHA = "f2efce04a1047d0e31b16f44e976a8b2b3102b340a6e3adfac32dfdf73f3ce0f"
RELEASE_SHA = "c441f956122cba6866a6729248d092584c4b1ee7e9d574bd98cffe9d74247424"
APPROVAL_SHA = "e2729bb1c8aee5ef8cc1b9920bfa832c4eb2ffcb72b782e8df20af1698f36108"
APPROVAL_REVIEW_SHA = "f3104e4a0ffdfb4399f56fa4cef57a53e70ce37f9e2274983a986c64550794b1"
RELEASE_REVIEW_SHA = "bd56546e21f8291864afbc0775681d63113f1629178c53ca49e7c8e79ae541d7"
OUTPUT_SHA = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
MANIFEST_SHA = "9ddf842ceec92eee3ae51e9386e4774315965654d711b5751d98ad96868d876e"
RECEIPT_SHA = "fca40fd446d7b4098e60d0f9fdcc55c3181bdfb757d8e6065e671b9c9ab6a0dc"
TERMINAL_SHA = "72a8131e2b7c8de8bd3cf57aa12aaab4989606354cdd93a4f04781dbc52026c9"
ROLE = "REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL"
STAGE_ROLE = "LAYER3_POST_ATTENTION_RESIDUAL"


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


def validate_output_bytes(raw: bytes, artifact: dict[str, Any]) -> None:
    require(set(artifact) == {
        "relative_path", "sha256", "semantic_role", "stage_role", "formula", "dtype", "shape",
        "byte_length", "finite", "expected_equals_before_equals_consumed_equals_after",
        "open_once_consume_same_descriptor", "fstat_before_and_after", "regular_file",
        "non_symlink", "hard_link_count", "read_only", "no_writable_alias",
    }, "ARTIFACT_KEYS")
    require(artifact["relative_path"] == "representative-s1.f32le", "OUTPUT_PATH")
    require(artifact["sha256"] == OUTPUT_SHA and sha256(raw) == OUTPUT_SHA, "OUTPUT_SHA")
    require(artifact["semantic_role"] == ROLE and artifact["stage_role"] == STAGE_ROLE, "OUTPUT_ROLE")
    require(artifact["formula"] == "S1 = f32(S0 + layer3_attention_output)", "OUTPUT_FORMULA")
    require(artifact["dtype"] == "little-endian-f32" and artifact["shape"] == [6144], "OUTPUT_GEOMETRY")
    require(artifact["byte_length"] == 24576 and len(raw) == 24576, "OUTPUT_LENGTH")
    require(artifact["finite"] is True, "OUTPUT_FINITE_DECLARATION")
    values = struct.unpack("<6144f", raw)
    require(all(math.isfinite(value) for value in values), "OUTPUT_NONFINITE")
    require(artifact["expected_equals_before_equals_consumed_equals_after"] is True, "IDENTITY_POLICY")
    require(artifact["open_once_consume_same_descriptor"] is True and artifact["fstat_before_and_after"] is True, "DESCRIPTOR_POLICY")
    require(artifact["regular_file"] is True and artifact["non_symlink"] is True, "FILE_POLICY")
    require(artifact["hard_link_count"] == 1 and artifact["read_only"] is True and artifact["no_writable_alias"] is True, "ALIAS_POLICY")


def validate_manifest(raw: bytes, artifact: dict[str, Any]) -> None:
    require(sha256(raw) == MANIFEST_SHA, "MANIFEST_SHA")
    manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    require(manifest.get("schema") == "pulsarmlx.f017.representative-s1-private-manifest", "MANIFEST_SCHEMA")
    require(manifest.get("schema_version") == "1.0.0", "MANIFEST_VERSION")
    require(manifest.get("expected_equals_produced_equals_readback") is True, "MANIFEST_IDENTITY")
    require(manifest.get("matching_complete_terminal_required") is True, "MANIFEST_TERMINAL")
    expected = {
        "path": artifact["relative_path"], "semantic_role": STAGE_ROLE,
        "sha256": OUTPUT_SHA, "dtype": "little-endian-f32", "shape": [6144],
        "byte_length": 24576, "finite": True,
    }
    require(manifest.get("artifact") == expected, "MANIFEST_ARTIFACT")


def validate_authorization(document: dict[str, Any]) -> None:
    expected_keys = {
        "schema", "schema_version", "authorization_id", "consumer_id", "preparation_base_head",
        "status", "real_event_authorized", "source_authority", "completed_attempt", "source_lineage",
        "private_manifest", "retained_s1", "reproduction_adjudication", "resolver", "consumer_scope",
        "accounting", "prohibitions", "stop_boundary", "next_authority",
    }
    require(set(document) == expected_keys, "AUTHORIZATION_KEYS")
    require(document["schema"] == "pulsarmlx.f017.representative-s1-output-reuse-authorization", "AUTHORIZATION_SCHEMA")
    require(document["schema_version"] == "1.0.0", "AUTHORIZATION_VERSION")
    require(document["authorization_id"] == "F017-REPRESENTATIVE-S1-OUTPUT-REUSE-1", "AUTHORIZATION_ID")
    require(document["consumer_id"] == "F017-REPRESENTATIVE-S2-PREPARATION-1", "CONSUMER_ID")
    require(document["preparation_base_head"] == "dbcf1dc5cafde118e7904b3e6174389215758182", "PREPARATION_HEAD")
    require(document["status"] == "PREPARED_REVIEW_REQUIRED" and document["real_event_authorized"] is False, "AUTHORIZATION_STATE")

    sources = document["source_authority"]
    expected_sources = {
        "execution_evidence": ("docs/architecture/reviews/evidence/f017-representative-s1-materialization-real-execution-result-v1.json", EVIDENCE_SHA),
        "materialization_authorization": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-materialization-authorization-v1.json", AUTHORIZATION_SHA),
        "single_use_release_v2": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-materialization-single-use-release-v2.json", RELEASE_SHA),
        "independent_release_approval": ("docs/architecture/reviews/evidence/f017-representative-s1-materialization-single-use-release-v2-independent-approval-v1.json", APPROVAL_SHA),
        "approval_review": ("docs/architecture/reviews/evidence/f017-representative-s1-materialization-release-v2-approval-cycle-01-independent-review.json", APPROVAL_REVIEW_SHA),
        "release_review": ("docs/architecture/reviews/evidence/f017-representative-s1-materialization-cycle-02-independent-review.json", RELEASE_REVIEW_SHA),
    }
    require(set(sources) == set(expected_sources) | {"execution_code_head"}, "SOURCE_CENSUS")
    for key, (relative_path, expected_sha) in expected_sources.items():
        require(sources[key] == {"path": relative_path, "sha256": expected_sha}, f"SOURCE_BINDING:{key}")
        require(sha256_path(ROOT / relative_path) == expected_sha, f"SOURCE_BYTES:{key}")
    require(sources["execution_code_head"] == "6272f3b846b62d11ba27a6ce5a5bfbdb6fae3fac", "EXECUTION_CODE_HEAD")

    attempt = document["completed_attempt"]
    require(attempt["event_id"] == "F017-REPRESENTATIVE-S1-MATERIALIZATION-1", "EVENT_ID")
    require(attempt["release_id"] == "F017-REPRESENTATIVE-S1-MATERIALIZATION-1-RELEASE-2", "RELEASE_ID")
    require(attempt["attempt_id"] == "F017-REPRESENTATIVE-S1-MATERIALIZATION-1-ATTEMPT-1", "ATTEMPT_ID")
    require(attempt["attempt_start"] == {"relative_path":"attempt-start.json","sha256":"bf883109e3ffae39e60ccfd689e6fd3ae9703fa3399d3bfb5ec5ab0ad25ff41c","byte_length":363}, "ATTEMPT_START")
    require(attempt["materialization_start"] == {"relative_path":"materialization-start.json","sha256":"d1ff891432e86fda733a870545b8ecdb6601493ce8f3781e266ef765474ac5fe","byte_length":213}, "MATERIALIZATION_START")
    require(attempt["receipt"] == {"relative_path":"s1-execution-receipt.json","sha256":RECEIPT_SHA,"byte_length":1383}, "RECEIPT")
    require(attempt["terminal"] == {"relative_path":"terminal.json","sha256":TERMINAL_SHA,"byte_length":364,"status":"COMPLETE","output_authority":True}, "TERMINAL")
    require(attempt["token_consumed"] is True and attempt["retry"] is False and attempt["resume"] is False and attempt["second_attempt"] is False, "ATTEMPT_FINALITY")

    lineage = document["source_lineage"]
    expected_attention = {
        "blk.3.attn_norm.weight":"8f642efd9c89ec5cb59fea36262ad370985428a8f0f028b78d524e581f584b85",
        "blk.3.attn_q_a.weight":"30eac1dc6c0538ebff3ceb56216423002ec798fd896785186e0653af3758d579",
        "blk.3.attn_q_a_norm.weight":"faf7fc183f8539ac4c7be45d97353ca0068212d435c46c96daa1f6b8bb809f0f",
        "blk.3.attn_q_b.weight":"c54a2250b8da6f4bb4a3f7676a83dec862ccfd0d145634250dea7167496f1b47",
        "blk.3.attn_kv_a_mqa.weight":"8f45a6d6e69a204c714acf4a09f7c29a1c5b34e4f581fb2fcc5771f0290d9053",
        "blk.3.attn_kv_a_norm.weight":"ab7ae58c665fd82c5731ebea86b818d7d9652f870e503019068e154524801ce4",
        "blk.3.attn_k_b.weight":"9903c9eea679d86016d28d61f8cf30f831ddf0d1458f9a8f43e062f2aa1f420f",
        "blk.3.attn_v_b.weight":"86dbc54eae38b1d0dc8f9f7a3dfdbcca00e0eb87ac6dee2d244054a496a35367",
        "blk.3.attn_output.weight":"30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084",
    }
    require(set(lineage) == {"canonical_s0_sha256","attention_payload_count","attention_payload_sha256","all_expected_equals_before_equals_consumed_equals_after","accepted_attention_reproduction","new_attention_execution","checkpoint_reconstruction"}, "LINEAGE_KEYS")
    require(lineage["canonical_s0_sha256"] == "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11", "S0_LINEAGE")
    require(lineage["attention_payload_count"] == 9 and lineage["attention_payload_sha256"] == expected_attention and lineage["all_expected_equals_before_equals_consumed_equals_after"] is True, "ATTENTION_LINEAGE")
    require(lineage["accepted_attention_reproduction"] == "10_OF_10_RETAINED_ONLY_EXACT_STAGE_IDENTITY", "ATTENTION_REPRODUCTION")
    require(lineage["new_attention_execution"] is False and lineage["checkpoint_reconstruction"] is False, "LINEAGE_BOUNDARY")

    manifest = document["private_manifest"]
    require(manifest == {"relative_path":"representative-s1-private-manifest-v1.json","sha256":MANIFEST_SHA,"byte_length":427,"machine_local_root_not_committed":True,"machine_local_absolute_path_not_committed":True,"regular_file":True,"non_symlink":True,"hard_link_count":1,"read_only":True}, "PRIVATE_MANIFEST")
    artifact = document["retained_s1"]
    require(set(artifact) == {"relative_path","sha256","semantic_role","stage_role","formula","dtype","shape","byte_length","finite","expected_equals_before_equals_consumed_equals_after","open_once_consume_same_descriptor","fstat_before_and_after","regular_file","non_symlink","hard_link_count","read_only","no_writable_alias"}, "RETAINED_S1_KEYS")
    require(artifact["relative_path"] == "representative-s1.f32le" and artifact["sha256"] == OUTPUT_SHA, "RETAINED_S1_IDENTITY")
    require(artifact["semantic_role"] == ROLE and artifact["stage_role"] == STAGE_ROLE and artifact["formula"] == "S1 = f32(S0 + layer3_attention_output)", "RETAINED_S1_ROLE")
    require(artifact["dtype"] == "little-endian-f32" and artifact["shape"] == [6144] and artifact["byte_length"] == 24576 and artifact["finite"] is True, "RETAINED_S1_GEOMETRY")
    require(artifact["expected_equals_before_equals_consumed_equals_after"] is True and artifact["open_once_consume_same_descriptor"] is True and artifact["fstat_before_and_after"] is True, "RETAINED_S1_CONSUMPTION")
    require(artifact["regular_file"] is True and artifact["non_symlink"] is True and artifact["hard_link_count"] == 1 and artifact["read_only"] is True and artifact["no_writable_alias"] is True, "RETAINED_S1_FILE_POLICY")
    require(document["reproduction_adjudication"] == {
        "additional_post_event_materialization_authorized":False,
        "additional_post_event_materialization_performed":False,
        "required_for_reuse_acceptance":False,
        "adjudication":"SOUND_WITHOUT_ADDITIONAL_POST_EVENT_REPRODUCTION",
        "basis":"PRECOMMITTED_EXPECTED_SHA_PLUS_EXACT_RETAINED_BYTES_COMPLETE_TERMINAL_MANIFEST_RECEIPT_SOURCE_IDENTITIES_AND_ACCEPTED_10_OF_10_ATTENTION_REPRODUCTION",
        "retroactive_execution_authority_expansion":False,
        "future_reproduction_requires_separate_authority":True,
    }, "REPRODUCTION_ADJUDICATION")
    require(document["resolver"]["path"] == "scripts/research/f017_representative_s1_output_reuse_v1.py", "RESOLVER_PATH")
    require(document["resolver"]["sha256"] == sha256_path(Path(__file__)), "RESOLVER_SHA")
    require(all(value is False for value in document["resolver"].values() if isinstance(value, bool)), "RESOLVER_CAPABILITIES")
    require(document["consumer_scope"] == {"allowed":"CHECKPOINT_FREE_REPRESENTATIVE_S2_PREPARATION_AND_INPUT_AUTHORITY_ONLY","s1_release_v2_rerun":False,"attention_reconstruction":False,"ffn_artifact_consumption":False,"s2_construction":False}, "CONSUMER_SCOPE")
    require(document["accounting"] == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"s1_release_v2_reruns":0,"new_s1_materializations":0,"ffn_compositions":0,"s2_constructions":0}, "ACCOUNTING")
    require(all(document["prohibitions"].values()), "PROHIBITIONS")
    require(document["stop_boundary"] == "AFTER_S1_OUTPUT_REUSE_PREFLIGHT_BEFORE_FFN_CONSUMPTION_OR_S2_CONSTRUCTION", "STOP_BOUNDARY")
    require(document["next_authority"] == "SEPARATE_CHECKPOINT_FREE_S2_PREPARATION_AUTHORITY", "NEXT_AUTHORITY")


def validate_evidence(evidence: dict[str, Any]) -> None:
    require(evidence["schema"] == "pulsarmlx.f017.representative-s1-materialization-real-execution-result", "EVIDENCE_SCHEMA")
    require(evidence["result"] == "SUCCESS" and evidence["process_exit"] == 0, "EVIDENCE_RESULT")
    require(evidence["execution_head"] == "dbcf1dc5cafde118e7904b3e6174389215758182", "EVIDENCE_HEAD")
    require(evidence["attempt"]["attempt_id"] == "F017-REPRESENTATIVE-S1-MATERIALIZATION-1-ATTEMPT-1", "EVIDENCE_ATTEMPT")
    require(evidence["attempt"]["go_token_consumed"] is True and not evidence["attempt"]["retry"] and not evidence["attempt"]["resume"] and not evidence["attempt"]["second_attempt"], "EVIDENCE_FINALITY")
    require(evidence["terminal"]["status"] == "COMPLETE" and evidence["terminal"]["output_authority"] is True, "EVIDENCE_TERMINAL")
    require(evidence["retained_output"]["sha256"] == OUTPUT_SHA and evidence["retained_output"]["authority"] is True, "EVIDENCE_OUTPUT")
    require(evidence["private_manifest"]["sha256"] == MANIFEST_SHA and evidence["receipt"]["sha256"] == RECEIPT_SHA, "EVIDENCE_RECORDS")
    require(evidence["source_lineage"]["all_expected_equals_before_equals_consumed_equals_after"] is True, "EVIDENCE_SOURCES")
    require(evidence["accounting"] == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"durable_attempt_starts":1,"materialization_starts":1,"s1_materializations":1,"ffn_compositions":0,"s2_constructions":0}, "EVIDENCE_ACCOUNTING")


def resolve(authorization_path: Path = AUTH) -> dict[str, Any]:
    authorization = load(authorization_path)
    validate_authorization(authorization)
    evidence = load(ROOT / authorization["source_authority"]["execution_evidence"]["path"])
    validate_evidence(evidence)

    output_fd = open_directory(OUTPUT_ROOT)
    state_fd = open_directory(STATE_ROOT)
    descriptors: list[int] = []
    try:
        artifact = authorization["retained_s1"]
        output_descriptor, output_before, output_raw = open_leaf(output_fd, artifact["relative_path"], 24576)
        descriptors.append(output_descriptor)
        manifest_descriptor, manifest_before, manifest_raw = open_leaf(output_fd, authorization["private_manifest"]["relative_path"], 427)
        descriptors.append(manifest_descriptor)
        receipt_descriptor, _, receipt_raw = open_leaf(state_fd, authorization["completed_attempt"]["receipt"]["relative_path"], 1383)
        descriptors.append(receipt_descriptor)
        terminal_descriptor, _, terminal_raw = open_leaf(state_fd, authorization["completed_attempt"]["terminal"]["relative_path"], 364)
        descriptors.append(terminal_descriptor)

        validate_output_bytes(output_raw, artifact)
        validate_manifest(manifest_raw, artifact)
        require(sha256(receipt_raw) == RECEIPT_SHA and sha256(terminal_raw) == TERMINAL_SHA, "DURABLE_RECORD_SHA")
        receipt = json.loads(receipt_raw.decode("utf-8"), object_pairs_hook=unique)
        terminal = json.loads(terminal_raw.decode("utf-8"), object_pairs_hook=unique)
        require(receipt["output_sha256"] == OUTPUT_SHA and receipt["manifest_sha256"] == MANIFEST_SHA, "RECEIPT_BINDING")
        require(terminal == {"schema":"pulsarmlx.f017.representative-s1-terminal","status":"COMPLETE","output_authority":True,"output_sha256":OUTPUT_SHA,"manifest_sha256":MANIFEST_SHA,"receipt_sha256":RECEIPT_SHA,"ledger":175}, "TERMINAL_BINDING")
        require(receipt["checkpoint_reads"] == receipt["shard_opens"] == receipt["new_attention_executions"] == receipt["ffn_compositions"] == receipt["s2_constructions"] == 0, "RECEIPT_ACCOUNTING")

        consumed_sha = sha256(output_raw)
        output_after = os.fstat(output_descriptor)
        manifest_after = os.fstat(manifest_descriptor)
        require((output_before.st_dev, output_before.st_ino, output_before.st_size) == (output_after.st_dev, output_after.st_ino, output_after.st_size), "OUTPUT_SUBSTITUTION")
        require((manifest_before.st_dev, manifest_before.st_ino, manifest_before.st_size) == (manifest_after.st_dev, manifest_after.st_ino, manifest_after.st_size), "MANIFEST_SUBSTITUTION")
        after_raw = read_exact(output_descriptor, 24576)
        require(after_raw == output_raw, "OUTPUT_CHANGED")
        return {
            "result": "REPRESENTATIVE_S1_OUTPUT_REUSE_PREFLIGHT_PASS",
            "semantic_role": ROLE,
            "expected_sha256": OUTPUT_SHA,
            "before_sha256": sha256(output_raw),
            "consumed_sha256": consumed_sha,
            "after_sha256": sha256(after_raw),
            "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576,
            "finite_elements": 6144, "ledger": 175, "checkpoint_reads": 0,
            "shard_opens": 0, "new_attention_executions": 0,
            "s1_release_v2_reruns": 0, "new_s1_materializations": 0,
            "ffn_compositions": 0, "s2_constructions": 0,
        }
    finally:
        for descriptor in descriptors:
            os.close(descriptor)
        os.close(output_fd)
        os.close(state_fd)


def main() -> int:
    print(json.dumps(resolve(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

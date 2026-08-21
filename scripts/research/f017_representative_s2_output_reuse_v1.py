#!/usr/bin/env python3
"""Open-once, non-computational resolver for the banked representative S2."""

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
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-output-reuse-authorization-v1.json"
RELEASE_ROOT = Path.home() / ".local/share/pulsarmlx/f017/representative-s2-release-2"
OUTPUT_ROOT = RELEASE_ROOT / "outputs"
STATE_ROOT = RELEASE_ROOT / "attempt-state"
EVIDENCE_PATH = "docs/architecture/reviews/evidence/f017-representative-s2-real-execution-result-v1.json"
EVIDENCE_SHA = "f64d0ff797a9bd1ae9a0f7c2b99cfb9ed5894b1110cc433de152b1c2526fdd75"
OUTPUT_SHA = "0341314230654d21fa56506dfe601f90bdb603fc38fd1203b6dd62b1e54c98c1"
MANIFEST_SHA = "fa0f8d9aeb19a6358611ef063cd120878eeb7ebdad6fce9e245f8625f019cabc"
RECEIPT_SHA = "2321205359ffb5b28518ab8488632f165a33b9d641ba86913dcb7128559763b9"
TERMINAL_SHA = "b5448de77aba28e1892291efec780bd5a7c4b2a07440fa119416215c11ca216b"
S1_SHA = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
FFN_SHA = "4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a"
ROLE = "REPRESENTATIVE_M1F0_S2_PROOF_REFERENCE_DERIVED"
SURFACE = "CANONICAL_F017_PROOF_REFERENCE_DERIVED_S2_SURFACE_INTENTIONALLY_NOT_CLAIMED_EQUIVALENT_TO_PRODUCTION_SERIAL_F32"


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
    require(Path(name).name == name, "PURE_BASENAME_REQUIRED")
    descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
    metadata = os.fstat(descriptor)
    require(stat.S_ISREG(metadata.st_mode), "REGULAR_FILE_REQUIRED")
    require(metadata.st_uid == os.getuid(), "OWNER_REQUIRED")
    require(metadata.st_nlink == 1, "SINGLE_HARD_LINK_REQUIRED")
    require(metadata.st_mode & 0o222 == 0, "READ_ONLY_REQUIRED")
    require(metadata.st_size == size, "BYTE_LENGTH")
    return descriptor, metadata, read_exact(descriptor, size)


def validate_output(raw: bytes, artifact: dict[str, Any]) -> None:
    require(artifact == {
        "relative_path": "representative-s2.f32le", "sha256": OUTPUT_SHA,
        "semantic_role": ROLE, "semantic_surface": SURFACE,
        "formula": "S2_f32[k] = binary32(binary64(S1_f32[k]) + FFN_f64[k])",
        "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576,
        "finite": True, "expected_equals_before_equals_consumed_equals_after": True,
        "open_once_consume_same_descriptor": True, "fstat_before_and_after": True,
        "regular_file": True, "non_symlink": True, "hard_link_count": 1,
        "read_only": True, "no_writable_alias": True,
    }, "ARTIFACT_BINDING")
    require(len(raw) == 24576 and sha256(raw) == OUTPUT_SHA, "OUTPUT_IDENTITY")
    require(all(math.isfinite(value) for value in struct.unpack("<6144f", raw)), "OUTPUT_NONFINITE")


def validate_manifest(raw: bytes) -> None:
    require(sha256(raw) == MANIFEST_SHA, "MANIFEST_SHA")
    manifest = json.loads(raw.decode(), object_pairs_hook=unique)
    require(manifest == {
        "artifacts": [{"byte_length":24576,"dtype":"little-endian-f32","finite":True,
            "semantic_role":ROLE,"sha256":OUTPUT_SHA,"shape":[6144],"symbolic_path":"representative-s2.f32le"}],
        "authority_requires_matching_complete_terminal": True,
        "execution_receipt_relative_path": "../attempt-state/s2-execution-receipt.json",
        "schema": "pulsarmlx.f017.representative-s2-private-manifest",
        "schema_version": "1.0.0", "semantic_surface": SURFACE,
    }, "MANIFEST_BINDING")


def validate_evidence(evidence: dict[str, Any]) -> None:
    require(evidence["schema"] == "pulsarmlx.f017.representative-s2-real-execution-result", "EVIDENCE_SCHEMA")
    require(evidence["result"] == "SUCCESS" and evidence["process_exit"] == 0, "EVIDENCE_RESULT")
    require(evidence["attempt"]["attempt_id"] == "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-ATTEMPT-1", "ATTEMPT")
    require(evidence["attempt"]["go_token_consumed"] is True and not evidence["attempt"]["retry"] and not evidence["attempt"]["resume"] and not evidence["attempt"]["second_attempt"], "ATTEMPT_FINALITY")
    require(evidence["terminal"]["disposition"] == "COMPLETE" and evidence["terminal"]["output_authority"] is True, "TERMINAL_AUTHORITY")
    require(evidence["output"]["sha256"] == OUTPUT_SHA and evidence["output"]["authority"] is True, "OUTPUT_AUTHORITY")
    require(evidence["private_manifest"]["sha256"] == MANIFEST_SHA and evidence["receipt"]["sha256"] == RECEIPT_SHA, "BANKING_RECORDS")
    for key, expected in (("s1", S1_SHA), ("ffn", FFN_SHA)):
        source = evidence["retained_inputs"][key]
        require(source["expected_sha256"] == source["before_sha256"] == source["consumed_sha256"] == source["after_sha256"] == expected, f"{key.upper()}_IDENTITY")
    require(evidence["accounting"] == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"expert_executions":0,"shared_expert_executions":0,"new_s1_materializations":0,"new_ffn_compositions":0,"durable_attempt_starts":1,"s2_starts":1,"s1_execution_consumptions":1,"ffn_execution_consumptions":1,"s2_constructions":1}, "EVIDENCE_ACCOUNTING")


def validate_authorization(document: dict[str, Any]) -> None:
    require(set(document) == {"schema","schema_version","authorization_id","consumer_id","preparation_base_head","status","real_event_authorized","source_authority","completed_attempt","consumed_lineage","private_manifest","retained_s2","reproduction_adjudication","resolver","consumer_scope","accounting","prohibitions","stop_boundary","next_authority"}, "AUTHORIZATION_KEYS")
    require(document["schema"] == "pulsarmlx.f017.representative-s2-output-reuse-authorization" and document["schema_version"] == "1.0.0", "AUTHORIZATION_SCHEMA")
    require(document["authorization_id"] == "F017-REPRESENTATIVE-S2-OUTPUT-REUSE-1" and document["consumer_id"] == "F017-REPRESENTATIVE-M1F0-FINAL-CLOSURE-PREPARATION-1", "AUTHORIZATION_ID")
    require(document["preparation_base_head"] == "502ba05cf61861710c6aee0de473469f4bb87c20", "PREPARATION_HEAD")
    require(document["status"] == "PREPARED_REVIEW_REQUIRED" and document["real_event_authorized"] is False, "STATE")
    sources = document["source_authority"]
    expected = {
        "execution_evidence": (EVIDENCE_PATH, EVIDENCE_SHA),
        "construction_authorization": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-construction-authorization-v1.json", "b85b255f8aa47968ec7a83cbe332d0ee8928874959685495d0c6e808e204185a"),
        "arithmetic_contract": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-arithmetic-v1.json", "abbf158320d1fdfade5b8553e9ea1871c34830f541e4186074262fc702776e86"),
        "single_use_release_v2": ("specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v2.json", "1182257c5c5f14525a2942b4802bde7ed59e7253ffafefbeceef5f05a5a994a2"),
        "independent_release_approval": ("docs/architecture/reviews/evidence/f017-representative-s2-single-use-release-v2-independent-approval-v1.json", "c6ccffc3b1917f958bff14e9c693d9ec78dd49f452bb51ae7ef8eb85e45d86dc"),
        "approval_review": ("docs/architecture/reviews/evidence/f017-representative-s2-release-v2-approval-cycle-01-independent-review.json", "d70571cb1fa21e3de0fd4bb1208ffacf8f1b7e859230d258883a723f1c7c87a6"),
        "release_review": ("docs/architecture/reviews/evidence/f017-representative-s2-release-v2-cycle-01-independent-review.json", "79016f237d850d03d89da10014795cd2113625532db34794ef99c04ba253b8b6"),
    }
    require(set(sources) == set(expected) | {"execution_code_head"}, "SOURCE_CENSUS")
    for key, (path, digest) in expected.items():
        require(sources[key] == {"path":path,"sha256":digest}, f"SOURCE_BINDING:{key}")
        require(sha256_path(ROOT / path) == digest, f"SOURCE_BYTES:{key}")
    require(sources["execution_code_head"] == "33d0355c94d0eb34147aadfa233c3e01322aa1ba", "CODE_HEAD")
    require(document["completed_attempt"] == {"event_id":"F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1","release_id":"F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-RELEASE-2","attempt_id":"F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-ATTEMPT-1","attempt_start":{"relative_path":"attempt-start.json","sha256":"abc478f56c19629043da7bbc46fb25e4f4cd4d73ae71f6ab6fe5dc4d273e0fbc","byte_length":875},"s2_start":{"relative_path":"s2-start.json","sha256":"a274d5be1396bf8900820447152b4ab03ab4bb129ca58a44b0dfa64ee151dcf6","byte_length":665},"receipt":{"relative_path":"s2-execution-receipt.json","sha256":RECEIPT_SHA,"byte_length":1624},"terminal":{"relative_path":"terminal.json","sha256":TERMINAL_SHA,"byte_length":843,"disposition":"COMPLETE","output_authority":True},"token_consumed":True,"retry":False,"resume":False,"second_attempt":False}, "COMPLETED_ATTEMPT")
    require(document["consumed_lineage"] == {"s1_reuse_authorization_sha256":"5c6437f2ab6ae2d01acc765430880195211e892dfb612fbb3b4125d9038ffe13","s1_expected_equals_before_equals_consumed_equals_after_sha256":S1_SHA,"ffn_reuse_authorization_sha256":"983b119970f8d60bddb887d4478455b4d9eb638c3dc90853319cc302f290cd06","ffn_expected_equals_before_equals_consumed_equals_after_sha256":FFN_SHA}, "CONSUMED_LINEAGE")
    require(document["private_manifest"] == {"relative_path":"representative-s2-private-manifest-v1.json","sha256":MANIFEST_SHA,"byte_length":629,"regular_file":True,"non_symlink":True,"hard_link_count":1,"read_only":True}, "PRIVATE_MANIFEST")
    artifact = document["retained_s2"]
    require(artifact["sha256"] == OUTPUT_SHA and artifact["semantic_role"] == ROLE and artifact["semantic_surface"] == SURFACE and artifact["dtype"] == "little-endian-f32" and artifact["shape"] == [6144] and artifact["byte_length"] == 24576 and artifact["finite"] is True, "RETAINED_S2")
    require(document["reproduction_adjudication"] == {"post_event_reproduction_authorized":False,"post_event_reproduction_performed":False,"required_for_reuse_acceptance":False,"adjudication":"SOUND_WITHOUT_ADDITIONAL_POST_EVENT_REPRODUCTION","basis":"EXACT_RETAINED_BYTES_COMPLETE_TERMINAL_OUTPUT_AUTHORITY_MANIFEST_RECEIPT_EXACT_OPERAND_IDENTITIES_FROZEN_ARITHMETIC_AND_ACCEPTED_SYNTHETIC_2_OF_2_REHEARSAL","retroactive_execution_authority_expansion":False,"future_reproduction_requires_separate_authority":True}, "REPRODUCTION")
    require(document["resolver"]["path"] == "scripts/research/f017_representative_s2_output_reuse_v1.py" and document["resolver"]["sha256"] == sha256_path(Path(__file__)), "RESOLVER")
    require(all(value is False for value in document["resolver"].values() if isinstance(value, bool)), "RESOLVER_CAPABILITIES")
    require(document["consumer_scope"] == {"allowed":"CHECKPOINT_FREE_REPRESENTATIVE_M1F0_FINAL_CLOSURE_PREPARATION_ONLY","s2_release_v2_rerun":False,"s2_reconstruction":False,"numerical_stage_execution":False,"project_level_closure_declaration":False}, "CONSUMER_SCOPE")
    require(document["accounting"] == {"ledger_before":175,"ledger_after":175,"checkpoint_reads":0,"shard_opens":0,"new_attention_executions":0,"expert_executions":0,"shared_expert_executions":0,"aggregate_executions":0,"ffn_compositions":0,"s1_materializations":0,"s2_release_v2_reruns":0,"new_s2_constructions":0}, "ACCOUNTING")
    require(all(document["prohibitions"].values()), "PROHIBITIONS")
    require(document["stop_boundary"] == "AFTER_S2_OUTPUT_REUSE_PREFLIGHT_BEFORE_FINAL_PROJECT_LEVEL_M1F0_CLOSURE_DECLARATION", "STOP_BOUNDARY")


def resolve(authorization_path: Path = AUTH) -> dict[str, Any]:
    authorization = load(authorization_path); validate_authorization(authorization)
    evidence = load(ROOT / EVIDENCE_PATH); validate_evidence(evidence)
    out_fd = open_directory(OUTPUT_ROOT); state_fd = open_directory(STATE_ROOT); descriptors: list[int] = []
    try:
        output_fd, before, raw = open_leaf(out_fd, "representative-s2.f32le", 24576); descriptors.append(output_fd)
        manifest_fd, manifest_before, manifest_raw = open_leaf(out_fd, "representative-s2-private-manifest-v1.json", 629); descriptors.append(manifest_fd)
        receipt_fd, _, receipt_raw = open_leaf(state_fd, "s2-execution-receipt.json", 1624); descriptors.append(receipt_fd)
        terminal_fd, _, terminal_raw = open_leaf(state_fd, "terminal.json", 843); descriptors.append(terminal_fd)
        validate_output(raw, authorization["retained_s2"]); validate_manifest(manifest_raw)
        require(sha256(receipt_raw) == RECEIPT_SHA and sha256(terminal_raw) == TERMINAL_SHA, "DURABLE_RECORD_SHA")
        receipt = json.loads(receipt_raw, object_pairs_hook=unique); terminal = json.loads(terminal_raw, object_pairs_hook=unique)
        require(receipt["output_sha256"] == OUTPUT_SHA and receipt["output_manifest_sha256"] == MANIFEST_SHA, "RECEIPT_BINDING")
        require(terminal["disposition"] == "COMPLETE" and terminal["output_authority"] is True and terminal["output_sha256"] == OUTPUT_SHA and terminal["execution_receipt_sha256"] == RECEIPT_SHA, "TERMINAL_BINDING")
        after = os.fstat(output_fd); manifest_after = os.fstat(manifest_fd)
        require((before.st_dev,before.st_ino,before.st_size) == (after.st_dev,after.st_ino,after.st_size), "OUTPUT_SUBSTITUTION")
        require((manifest_before.st_dev,manifest_before.st_ino,manifest_before.st_size) == (manifest_after.st_dev,manifest_after.st_ino,manifest_after.st_size), "MANIFEST_SUBSTITUTION")
        after_raw = read_exact(output_fd, 24576); require(after_raw == raw, "OUTPUT_CHANGED")
        return {"result":"REPRESENTATIVE_S2_OUTPUT_REUSE_PREFLIGHT_PASS","semantic_role":ROLE,"semantic_surface":SURFACE,"expected_sha256":OUTPUT_SHA,"before_sha256":sha256(raw),"consumed_sha256":sha256(raw),"after_sha256":sha256(after_raw),"dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"finite_elements":6144,"ledger":175,"checkpoint_reads":0,"shard_opens":0,"new_s2_constructions":0}
    finally:
        for descriptor in descriptors: os.close(descriptor)
        os.close(out_fd); os.close(state_fd)


if __name__ == "__main__":
    print(json.dumps(resolve(), sort_keys=True))

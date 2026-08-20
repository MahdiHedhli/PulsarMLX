#!/usr/bin/env python3
"""Fail-closed single-use wrapper for one future representative S2 event."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import stat
import struct
import subprocess
import sys
from types import ModuleType
from typing import Any

from f017_representative_expert_ledger_adapter_v1 import current_ledger


ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-construction-authorization-v1.json"
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-arithmetic-v1.json"
S1_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-output-reuse-authorization-v1.json"
FFN_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-output-reuse-authorization-v1.json"
APPROVAL_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-release-approval-contract-v1.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_s2_executor_v1.py"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v1.json"
APPROVAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-s2-single-use-release-v1-independent-approval-v1.json"

AUTHORIZATION_SHA = "b85b255f8aa47968ec7a83cbe332d0ee8928874959685495d0c6e808e204185a"
ARITHMETIC_SHA = "abbf158320d1fdfade5b8553e9ea1871c34830f541e4186074262fc702776e86"
S1_REUSE_SHA = "5c6437f2ab6ae2d01acc765430880195211e892dfb612fbb3b4125d9038ffe13"
FFN_REUSE_SHA = "983b119970f8d60bddb887d4478455b4d9eb638c3dc90853319cc302f290cd06"
APPROVAL_CONTRACT_SHA = "c391d84b4573f49d0be40a75665e3c7b18db6b73f37b6cdad342255c34f7800b"
EXECUTOR_SHA = "c0268b47249539b682e3f667b9de0ba2afae8efae648bb18d435c7d61e0bd285"
EVENT_ID = "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
OUTPUT_NAME = "representative-s2.f32le"
MANIFEST_NAME = "representative-s2-private-manifest-v1.json"
OUTPUT_BYTES = 24576
REVIEWER_IDENTITY = "CLAUDE_FABLE_5_INDEPENDENT_ADVERSARIAL_REVIEWER"
REVIEWER_MODEL = "claude-fable-5"
APPROVER_IDENTITY = "CLAUDE_FABLE_5_INDEPENDENT_APPROVER"
APPROVER_MODEL = "claude-fable-5"
REVIEW_RE = re.compile(r"f017-representative-s2-release-cycle-[0-9]{2}-independent-review\.json")


class ReleaseError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


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


def canonical(packet: dict[str, Any]) -> bytes:
    return (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256(path.read_bytes())


def fixed_paths(home: Path | None = None) -> dict[str, Path]:
    anchor = home if home is not None else Path.home()
    release_root = anchor / ".local/share/pulsarmlx/f017/representative-s2-release-1"
    return {
        "s1_root": anchor / ".local/share/pulsarmlx/f017/representative-s1-materialization-release-2/outputs",
        "ffn_root": anchor / ".local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs",
        "release_root": release_root,
        "state_root": release_root / "attempt-state",
        "output_root": release_root / "outputs",
        "output": release_root / "outputs" / OUTPUT_NAME,
        "manifest": release_root / "outputs" / MANIFEST_NAME,
        "receipt": release_root / "attempt-state" / "s2-execution-receipt.json",
        "terminal": release_root / "attempt-state" / "terminal.json",
        "token": release_root / "go-token.json",
        "approval": APPROVAL,
    }


def open_directory(path: Path, exact_mode: int | None = None) -> int:
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode), "DIRECTORY_IDENTITY")
    require(before.st_uid == os.getuid() and before.st_mode & 0o022 == 0, "DIRECTORY_POLICY")
    if exact_mode is not None:
        require(stat.S_IMODE(before.st_mode) == exact_mode, "DIRECTORY_MODE")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    observed = os.fstat(descriptor)
    require((before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino), "DIRECTORY_SUBSTITUTION")
    return descriptor


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


def require_absent(directory_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ReleaseError(f"PREEXISTING_DESTINATION:{name}")


def publish(directory_fd: int, name: str, raw: bytes, mode: int = 0o400) -> str:
    require(Path(name).name == name, "PURE_BASENAME_REQUIRED")
    require_absent(directory_fd, name)
    temporary = f".{name}.{secrets.token_hex(16)}"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                offset += os.write(descriptor, view[offset:])
            os.fsync(descriptor)
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
        os.unlink(temporary, dir_fd=directory_fd)
        temporary = ""
        os.fsync(directory_fd)
        published = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            metadata = os.fstat(published)
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and stat.S_IMODE(metadata.st_mode) == mode, "PUBLISHED_POLICY")
            require(read_exact(published, len(raw)) == raw, "PUBLISHED_READBACK")
        finally:
            os.close(published)
        return sha256(raw)
    finally:
        if temporary:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass


def write_state(root: Path, name: str, packet: dict[str, Any]) -> str:
    fd = open_directory(root, exact_mode=0o700)
    try:
        return publish(fd, name, canonical(packet))
    finally:
        os.close(fd)


def require_environment() -> None:
    require(sys.version_info[:3] == (3, 14, 6), "CPYTHON_3_14_6_REQUIRED")
    require(platform.system() == "Darwin" and platform.machine() == "arm64", "DARWIN_ARM64_REQUIRED")
    require(sys.byteorder == "little", "LITTLE_ENDIAN_REQUIRED")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        require(os.environ.get(name) == "1", f"THREAD_PIN:{name}")


def validate_bindings(release: dict[str, Any]) -> None:
    fixed = {
        "authorization": (AUTHORIZATION, AUTHORIZATION_SHA),
        "arithmetic_contract": (ARITHMETIC, ARITHMETIC_SHA),
        "s1_reuse_authorization": (S1_REUSE, S1_REUSE_SHA),
        "ffn_reuse_authorization": (FFN_REUSE, FFN_REUSE_SHA),
        "approval_contract": (APPROVAL_CONTRACT, APPROVAL_CONTRACT_SHA),
        "executor": (EXECUTOR, EXECUTOR_SHA),
    }
    for name, (path, identity) in fixed.items():
        require(sha256_path(path) == identity, f"{name.upper()}_IDENTITY")
        require(release["bindings"][name] == {"path": path.relative_to(ROOT).as_posix(), "sha256": identity}, f"RELEASE_BINDING:{name}")
    for name in ("release_wrapper", "terminalizer", "validator", "tests", "synthetic_rehearsal"):
        binding = release["bindings"][name]
        require(sha256_path(ROOT / binding["path"]) == binding["sha256"], f"RELEASE_BINDING:{name}")


def validate_release(release_path: Path) -> dict[str, Any]:
    require(release_path.resolve() == RELEASE.resolve(), "RELEASE_PATH")
    release = load(release_path)
    require(release.get("schema") == "pulsarmlx.f017.representative-s2-single-use-release" and release.get("schema_version") == "1.0.0", "RELEASE_SCHEMA")
    require((release.get("event_id"), release.get("release_id"), release.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "RELEASE_IDENTITY")
    require(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL" and release.get("real_event_authorized") is False, "RELEASE_STATE")
    require(release.get("stop_boundary") == "AFTER_REPRESENTATIVE_S2_OUTPUT_ONLY", "STOP_BOUNDARY")
    validate_bindings(release)
    return release


def git_bytes(head: str, relative_path: str) -> bytes:
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "REVIEWED_HEAD_FORMAT")
    result = subprocess.run(["git", "-C", str(ROOT), "show", f"{head}:{relative_path}"], capture_output=True, check=False)
    require(result.returncode == 0, "REVIEWED_HEAD_OBJECT")
    return result.stdout


def validate_approval(release: dict[str, Any], approval_path: Path) -> dict[str, Any]:
    contract = load(APPROVAL_CONTRACT)
    approval = load(approval_path)
    require(list(approval.keys()) == contract["approval_exact_fields"], "APPROVAL_EXACT_FIELDS_AND_ORDER")
    constants = contract["required_constants"]
    require(all(approval.get(key) == value for key, value in constants.items()), "APPROVAL_CONSTANTS")
    require((approval["event_id"], approval["release_id"], approval["attempt_id"]) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "APPROVAL_IDENTITY")
    require(approval["release_sha256"] == sha256_path(RELEASE), "APPROVAL_RELEASE")
    require(approval["authorization_sha256"] == AUTHORIZATION_SHA and approval["arithmetic_contract_sha256"] == ARITHMETIC_SHA, "APPROVAL_CONTRACT_BINDING")
    require(approval["execution_code_head"] == release["authoritative_execution_code_head"], "APPROVAL_CODE_HEAD")
    review_rel = Path(approval["release_review_path"])
    require(not review_rel.is_absolute() and review_rel.parent.as_posix() == "docs/architecture/reviews/evidence" and REVIEW_RE.fullmatch(review_rel.name) is not None, "REVIEW_PATH")
    review_path = ROOT / review_rel
    require(sha256_path(review_path) == approval["release_review_sha256"], "REVIEW_SHA")
    review = load(review_path)
    require(review.get("reviewer_identity") == approval["release_reviewer_identity"] == REVIEWER_IDENTITY, "REVIEWER_IDENTITY")
    require(review.get("reviewer_model") == approval["release_reviewer_model"] == REVIEWER_MODEL, "REVIEWER_MODEL")
    require(review.get("reviewed_head") == approval["reviewed_head"], "REVIEWED_HEAD")
    require(review.get("verdict") == "ACCEPT" and review.get("blocking_findings") == [] and review.get("non_blocking_required_findings") == [], "REVIEW_VERDICT")
    release_rel = RELEASE.relative_to(ROOT).as_posix()
    require(sha256(git_bytes(approval["reviewed_head"], release_rel)) == approval["release_sha256"], "REVIEWED_RELEASE_BYTES")
    require(approval["approver_identity"] == APPROVER_IDENTITY and approval["approver_model"] == APPROVER_MODEL, "APPROVER")
    return approval


def validate_token(token_path: Path, release: dict[str, Any], approval_path: Path) -> dict[str, Any]:
    before = token_path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode), "TOKEN_IDENTITY")
    require(before.st_uid == os.getuid() and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o400, "TOKEN_POLICY")
    token = load(token_path)
    contract = load(APPROVAL_CONTRACT)
    require(list(token.keys()) == contract["go_token_exact_fields"], "TOKEN_EXACT_FIELDS_AND_ORDER")
    expected = {
        "approval_sha256": sha256_path(approval_path), "attempt_id": ATTEMPT_ID,
        "authorization_sha256": AUTHORIZATION_SHA, "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
        "event_id": EVENT_ID, "real_event_authorized": True, "release_id": RELEASE_ID,
        "release_sha256": sha256_path(RELEASE),
    }
    require(token == expected, "TOKEN_BINDING")
    return token


def static_preflight(release_path: Path, home: Path | None = None) -> tuple[dict[str, Any], dict[str, Path]]:
    release = validate_release(release_path)
    require_environment()
    require(current_ledger() == 175, "LEDGER")
    paths = fixed_paths(home)
    require(paths["release_root"].exists() and paths["release_root"].is_dir(), "RELEASE_ROOT")
    root_fd = open_directory(paths["release_root"], exact_mode=0o700)
    try:
        require_absent(root_fd, "attempt-state")
        require_absent(root_fd, "outputs")
    finally:
        os.close(root_fd)
    require(not paths["state_root"].exists() and not paths["output_root"].exists(), "PRIOR_STATE")
    require(shutil.disk_usage(paths["release_root"]).free >= release["storage_required_bytes"], "STORAGE")
    return release, paths


def operand_specs(authorization: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    def spec(name: str, manifest_bytes: int) -> dict[str, Any]:
        item = authorization["inputs"][name]
        return {
            "manifest": {"relative_path": item["private_manifest_relative_path"], "sha256": item["private_manifest_sha256"], "byte_length": manifest_bytes},
            "artifact": {key: item[key] for key in ("relative_path", "sha256", "semantic_role", "dtype", "shape", "byte_length")},
        }
    return spec("s1", 427), spec("ffn", 627)


def load_executor() -> ModuleType:
    require(sha256_path(EXECUTOR) == EXECUTOR_SHA, "EXECUTOR_IDENTITY")
    spec = importlib.util.spec_from_file_location("f017_bound_s2_executor", EXECUTOR)
    require(spec is not None and spec.loader is not None, "EXECUTOR_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def begin_attempt(paths: dict[str, Path], release_path: Path, approval_path: Path, token_path: Path) -> str:
    require(not paths["state_root"].exists(), "PRIOR_ATTEMPT")
    os.mkdir(paths["state_root"], 0o700)
    parent_fd = open_directory(paths["release_root"], exact_mode=0o700)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return write_state(paths["state_root"], "attempt-start.json", {
        "schema": "pulsarmlx.f017.representative-s2-attempt-start", "schema_version": "1.0.0",
        "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID,
        "release_sha256": sha256_path(release_path), "authorization_sha256": AUTHORIZATION_SHA,
        "approval_sha256": sha256_path(approval_path), "go_token_sha256": sha256_path(token_path),
        "consumption_boundary": "DURABLE_ATTEMPT_START_BEFORE_S2_ARITHMETIC",
        "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "s1_materializations": 0, "ffn_compositions": 0, "s2_constructions": 0,
        "retry": False, "resume": False, "second_attempt": False,
    })


def begin_s2(paths: dict[str, Path], attempt_sha: str, release_path: Path) -> str:
    return write_state(paths["state_root"], "s2-start.json", {
        "schema": "pulsarmlx.f017.representative-s2-start", "schema_version": "1.0.0",
        "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID,
        "attempt_start_sha256": attempt_sha, "release_sha256": sha256_path(release_path),
        "accounting_semantics": "DURABLE_START_COUNTS_ONE_S2_CONSTRUCTION_REGARDLESS_OF_OUTCOME",
        "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "s1_materializations": 0, "ffn_compositions": 0, "s2_constructions": 1,
    })


def output_manifest(output_sha: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.representative-s2-private-manifest", "schema_version": "1.0.0",
        "semantic_surface": "CANONICAL_F017_PROOF_REFERENCE_DERIVED_S2_SURFACE_INTENTIONALLY_NOT_CLAIMED_EQUIVALENT_TO_PRODUCTION_SERIAL_F32",
        "artifacts": [{"symbolic_path": OUTPUT_NAME, "sha256": output_sha,
            "semantic_role": "REPRESENTATIVE_M1F0_S2_PROOF_REFERENCE_DERIVED", "dtype": "little-endian-f32",
            "shape": [6144], "byte_length": OUTPUT_BYTES, "finite": True}],
        "execution_receipt_relative_path": "../attempt-state/s2-execution-receipt.json",
        "authority_requires_matching_complete_terminal": True,
    }


def publish_output(raw: bytes, paths: dict[str, Path]) -> tuple[str, str]:
    require(len(raw) == OUTPUT_BYTES and all(math.isfinite(value) for value in struct.unpack("<6144f", raw)), "OUTPUT_INVALID")
    os.mkdir(paths["output_root"], 0o700)
    parent_fd = open_directory(paths["release_root"], exact_mode=0o700)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    fd = open_directory(paths["output_root"], exact_mode=0o700)
    try:
        output_sha = publish(fd, OUTPUT_NAME, raw)
        manifest_sha = publish(fd, MANIFEST_NAME, canonical(output_manifest(output_sha)))
        return output_sha, manifest_sha
    finally:
        os.close(fd)


def terminal(paths: dict[str, Path], disposition: str, output_sha: str | None, manifest_sha: str | None, receipt_sha: str | None, error: str | None) -> str:
    count = int((paths["state_root"] / "s2-start.json").is_file())
    require(disposition != "COMPLETE" or (count == 1 and output_sha and manifest_sha and receipt_sha), "COMPLETE_WITHOUT_AUTHORITY")
    return write_state(paths["state_root"], "terminal.json", {
        "schema": "pulsarmlx.f017.representative-s2-terminal", "schema_version": "1.0.0",
        "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID,
        "disposition": disposition, "output_authority": disposition == "COMPLETE",
        "output_sha256": output_sha, "output_manifest_sha256": manifest_sha,
        "execution_receipt_sha256": receipt_sha, "error": error,
        "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "s1_materializations": 0, "ffn_compositions": 0, "s2_constructions": count,
        "retry": False, "resume": False, "second_attempt": False,
        "stop_boundary": "AFTER_REPRESENTATIVE_S2_OUTPUT_ONLY",
    })


def execute(release_path: Path, token_path: Path, home: Path | None = None) -> dict[str, Any]:
    owned = False
    paths = fixed_paths(home)
    output_sha = manifest_sha = receipt_sha = None
    s1 = ffn = None
    try:
        release, paths = static_preflight(release_path, home)
        approval = validate_approval(release, paths["approval"])
        validate_token(token_path, release, paths["approval"])
        authorization = load(AUTHORIZATION)
        executor = load_executor()
        executor.validate_arithmetic()
        s1_spec, ffn_spec = operand_specs(authorization)
        s1 = executor.OpenOperand(paths["s1_root"], s1_spec)
        ffn = executor.OpenOperand(paths["ffn_root"], ffn_spec)
        attempt_sha = begin_attempt(paths, release_path, paths["approval"], token_path)
        owned = True
        start_sha = begin_s2(paths, attempt_sha, release_path)
        raw, after = executor.compose_from_open_operands(s1, ffn)
        output_sha, manifest_sha = publish_output(raw, paths)
        receipt_sha = write_state(paths["state_root"], "s2-execution-receipt.json", {
            "schema": "pulsarmlx.f017.representative-s2-execution-receipt", "schema_version": "1.0.0",
            "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID,
            "release_sha256": sha256_path(release_path), "approval_sha256": sha256_path(paths["approval"]),
            "s2_start_sha256": start_sha, "output_sha256": output_sha,
            "output_manifest_sha256": manifest_sha, "inputs_after": after,
            "output_dtype": "little-endian-f32", "output_shape": [6144], "output_bytes": OUTPUT_BYTES,
            "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
            "s1_materializations": 0, "ffn_compositions": 0, "s2_constructions": 1,
        })
        terminal_sha = terminal(paths, "COMPLETE", output_sha, manifest_sha, receipt_sha, None)
        return {"result": "COMPLETE", "output_sha256": output_sha, "manifest_sha256": manifest_sha,
            "receipt_sha256": receipt_sha, "terminal_sha256": terminal_sha, "ledger": 175,
            "checkpoint_reads": 0, "shard_opens": 0, "s2_constructions": 1}
    except Exception as error:
        if owned and not paths["terminal"].exists():
            terminal(paths, "TERMINAL_FAILURE", output_sha, manifest_sha, receipt_sha, f"{type(error).__name__}:{error}")
        raise
    finally:
        if ffn is not None:
            ffn.close()
        if s1 is not None:
            s1.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--go-token", type=Path)
    args = parser.parse_args()
    if args.preflight_only:
        require(args.go_token is None, "PREFLIGHT_TOKEN_FORBIDDEN")
        release, paths = static_preflight(args.release)
        executor = load_executor()
        s1_spec, ffn_spec = operand_specs(load(AUTHORIZATION))
        s1 = executor.OpenOperand(paths["s1_root"], s1_spec)
        try:
            ffn = executor.OpenOperand(paths["ffn_root"], ffn_spec)
            try:
                after = {"s1": s1.verify_after(), "ffn": ffn.verify_after()}
            finally:
                ffn.close()
        finally:
            s1.close()
        print(json.dumps({"result": "PRODUCTION_BINDINGS_RESOLVED", "inputs_after": after,
            "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
            "s1_materializations": 0, "ffn_compositions": 0, "s2_constructions": 0,
            "stop_boundary": release["stop_boundary"]}, sort_keys=True))
        return 0
    require(args.go_token is not None, "GO_TOKEN_REQUIRED")
    print(json.dumps(execute(args.release, args.go_token), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseError, FileNotFoundError, PermissionError, OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"result": "FAIL_CLOSED", "error": f"{type(error).__name__}:{error}",
            "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)

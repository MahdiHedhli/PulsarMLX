#!/usr/bin/env python3
"""Single-use release wrapper for future representative FFN composition."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
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
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-authorization-v1.json"
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-arithmetic-v1.json"
ROUTED_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-reuse-authorization-v1.json"
SHARED_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-output-reuse-authorization-v1.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_ffn_composition_executor_v1.py"
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_ffn_composition_single_use_release_v1.py"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-single-use-release-v1.json"
APPROVAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-ffn-composition-single-use-release-v1-independent-approval-v1.json"

AUTHORIZATION_SHA = "69e6e49b0e2967b9b7cde7ee00154b7abdaa08609904eca75e54c29b8e4ca1a5"
ARITHMETIC_SHA = "1054d014c23628fa56771518f066d14cfd445b0d7b4ba7da98b638c37981cdbb"
ROUTED_REUSE_SHA = "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb"
SHARED_REUSE_SHA = "3642200f50f2ed7140243cd885dfe8c3d8628f5605ab37467cc342ea6376019a"
EXECUTOR_SHA = "7632b19af4a0b3bb16ec7032cec049bcab45dabd246cac5d77f0daaec24d256c"
EVENT_ID = "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
OUTPUT_BASENAME = "representative-ffn-output.f64le"
MANIFEST_BASENAME = "representative-ffn-output-private-manifest-v1.json"
OUTPUT_BYTES = 49152
STORAGE_REQUIRED = 67108864


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


def canonical_json(packet: dict[str, Any]) -> bytes:
    return (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fixed_paths(home: Path | None = None) -> dict[str, Path]:
    anchor = home if home is not None else Path.home()
    release_root = anchor / ".local/share/pulsarmlx/f017/representative-ffn-composition-release-1"
    return {
        "routed_root": anchor / ".local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/outputs",
        "shared_root": anchor / ".local/share/pulsarmlx/f017/representative-shared-expert-release-1/outputs",
        "release_root": release_root,
        "state_root": release_root / "attempt-state",
        "output_root": release_root / "outputs",
        "output": release_root / "outputs" / OUTPUT_BASENAME,
        "output_manifest": release_root / "outputs" / MANIFEST_BASENAME,
        "receipt": release_root / "attempt-state" / "ffn-execution-receipt.json",
        "go_token": release_root / "go-token.json",
        "approval": APPROVAL,
    }


def open_directory(path: Path, *, exact_mode: int | None = None) -> tuple[int, os.stat_result]:
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode), f"DIRECTORY_IDENTITY:{path.name}")
    require(before.st_uid == os.getuid(), f"DIRECTORY_OWNER:{path.name}")
    require(before.st_mode & 0o022 == 0, f"DIRECTORY_WRITABLE_ALIAS:{path.name}")
    if exact_mode is not None:
        require(stat.S_IMODE(before.st_mode) == exact_mode, f"DIRECTORY_MODE:{path.name}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    observed = os.fstat(descriptor)
    require((before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino), f"DIRECTORY_SUBSTITUTION:{path.name}")
    return descriptor, observed


def require_absent_at(directory_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ReleaseError(f"PREEXISTING_DESTINATION:{name}")


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


def publish_bytes(directory_fd: int, basename: str, raw: bytes, *, mode: int = 0o400) -> str:
    require(Path(basename).name == basename, "PURE_BASENAME_REQUIRED")
    require_absent_at(directory_fd, basename)
    temporary = f".{basename}.{secrets.token_hex(16)}"
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
        os.link(temporary, basename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
        os.unlink(temporary, dir_fd=directory_fd)
        temporary = ""
        os.fsync(directory_fd)
        published = os.open(basename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            metadata = os.fstat(published)
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid(), "PUBLISHED_IDENTITY")
            require(metadata.st_nlink == 1 and stat.S_IMODE(metadata.st_mode) == mode, "PUBLISHED_MODE_LINKS")
            observed = read_exact(published, len(raw))
            require(observed == raw, "PUBLISHED_READBACK")
        finally:
            os.close(published)
        return sha256_bytes(raw)
    finally:
        if temporary:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass


def validate_output(raw: bytes) -> str:
    require(len(raw) == OUTPUT_BYTES, "OUTPUT_BYTES")
    require(all(math.isfinite(value) for value in struct.unpack("<6144d", raw)), "OUTPUT_NONFINITE")
    return sha256_bytes(raw)


def output_manifest(output_sha256: str, receipt_relative_path: str = "../attempt-state/ffn-execution-receipt.json") -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.representative-ffn-output-private-manifest",
        "schema_version": "1.0.0",
        "semantic_surface": "CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32",
        "artifacts": [{
            "symbolic_path": OUTPUT_BASENAME,
            "sha256": output_sha256,
            "semantic_role": "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT",
            "dtype": "little-endian-f64",
            "shape": [6144],
            "byte_length": OUTPUT_BYTES,
            "finite": True,
        }],
        "execution_receipt_relative_path": receipt_relative_path,
        "authority_requires_matching_complete_terminal": True,
    }


def publish_output_and_manifest(raw: bytes, output_root: Path) -> tuple[str, str]:
    output_sha = validate_output(raw)
    directory_fd, _ = open_directory(output_root, exact_mode=0o700)
    try:
        require_absent_at(directory_fd, OUTPUT_BASENAME)
        require_absent_at(directory_fd, MANIFEST_BASENAME)
        published_output_sha = publish_bytes(directory_fd, OUTPUT_BASENAME, raw)
        require(published_output_sha == output_sha, "OUTPUT_PUBLICATION_SHA")
        manifest_raw = canonical_json(output_manifest(output_sha))
        manifest_sha = publish_bytes(directory_fd, MANIFEST_BASENAME, manifest_raw)
        return output_sha, manifest_sha
    finally:
        os.close(directory_fd)


def write_state(state_root: Path, name: str, packet: dict[str, Any]) -> str:
    raw = canonical_json(packet)
    directory_fd, _ = open_directory(state_root, exact_mode=0o700)
    try:
        return publish_bytes(directory_fd, name, raw)
    finally:
        os.close(directory_fd)


def begin_attempt(paths: dict[str, Path], release_path: Path, approval_path: Path, token_path: Path) -> str:
    require(not paths["state_root"].exists(), "PRIOR_ATTEMPT")
    os.mkdir(paths["state_root"], 0o700)
    parent_fd, _ = open_directory(paths["state_root"].parent, exact_mode=0o700)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return write_state(paths["state_root"], "attempt-start.json", {
        "schema": "pulsarmlx.f017.representative-ffn-composition-attempt-start",
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "release_id": RELEASE_ID,
        "attempt_id": ATTEMPT_ID,
        "authorization_sha256": AUTHORIZATION_SHA,
        "release_sha256": sha256_path(release_path),
        "approval_sha256": sha256_path(approval_path),
        "go_token_sha256": sha256_path(token_path),
        "executor_sha256": EXECUTOR_SHA,
        "wrapper_sha256": sha256_path(Path(__file__)),
        "consumption_boundary": "DURABLE_ATTEMPT_START_BEFORE_FFN_COMPUTATION",
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
    })


def begin_ffn(paths: dict[str, Path], release_path: Path) -> str:
    return write_state(paths["state_root"], "ffn-start.json", {
        "schema": "pulsarmlx.f017.representative-ffn-composition-start",
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "release_id": RELEASE_ID,
        "attempt_id": ATTEMPT_ID,
        "release_sha256": sha256_path(release_path),
        "accounting_semantics": "DURABLE_START_COUNTS_ONE_FFN_COMPOSITION_REGARDLESS_OF_OUTCOME",
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "ffn_compositions": 1,
        "s1_materializations": 0,
        "s2_constructions": 0,
    })


def write_receipt(paths: dict[str, Path], release_path: Path, output_sha: str, manifest_sha: str,
                  input_after: dict[str, dict[str, str]]) -> str:
    return write_state(paths["state_root"], "ffn-execution-receipt.json", {
        "schema": "pulsarmlx.f017.representative-ffn-composition-execution-receipt",
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "release_id": RELEASE_ID,
        "attempt_id": ATTEMPT_ID,
        "release_sha256": sha256_path(release_path),
        "output_sha256": output_sha,
        "output_manifest_sha256": manifest_sha,
        "output_bytes": OUTPUT_BYTES,
        "output_dtype": "little-endian-f64",
        "output_shape": [6144],
        "inputs_after": input_after,
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "ffn_compositions": 1,
        "s1_materializations": 0,
        "s2_constructions": 0,
    })


def write_terminal(paths: dict[str, Path], disposition: str, output_sha: str | None,
                   manifest_sha: str | None, receipt_sha: str | None, error: str | None) -> str:
    ffn_count = int((paths["state_root"] / "ffn-start.json").is_file())
    require(disposition != "COMPLETE" or (ffn_count == 1 and output_sha and manifest_sha and receipt_sha), "COMPLETE_WITHOUT_AUTHORITY")
    return write_state(paths["state_root"], "terminal.json", {
        "schema": "pulsarmlx.f017.representative-ffn-composition-terminal",
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "release_id": RELEASE_ID,
        "attempt_id": ATTEMPT_ID,
        "disposition": disposition,
        "output_sha256": output_sha,
        "output_manifest_sha256": manifest_sha,
        "execution_receipt_sha256": receipt_sha,
        "output_authority": disposition == "COMPLETE",
        "error": error,
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "ffn_compositions": ffn_count,
        "s1_materializations": 0,
        "s2_constructions": 0,
        "retry": False,
        "resume": False,
        "second_attempt": False,
        "stop_boundary": "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY",
    })


def load_executor() -> ModuleType:
    require(sha256_path(EXECUTOR) == EXECUTOR_SHA, "EXECUTOR_IDENTITY")
    spec = importlib.util.spec_from_file_location("f017_bound_ffn_executor", EXECUTOR)
    require(spec is not None and spec.loader is not None, "EXECUTOR_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_fixed_bindings() -> None:
    for path, identity, label in (
        (AUTHORIZATION, AUTHORIZATION_SHA, "AUTHORIZATION"),
        (ARITHMETIC, ARITHMETIC_SHA, "ARITHMETIC"),
        (ROUTED_REUSE, ROUTED_REUSE_SHA, "ROUTED_REUSE"),
        (SHARED_REUSE, SHARED_REUSE_SHA, "SHARED_REUSE"),
        (EXECUTOR, EXECUTOR_SHA, "EXECUTOR"),
    ):
        require(sha256_path(path) == identity, f"{label}_IDENTITY")


def validate_release_path(release_path: Path) -> dict[str, Any]:
    require(release_path.resolve() == RELEASE.resolve(), "RELEASE_PATH")
    release = load(release_path)
    require(release.get("schema") == "pulsarmlx.f017.representative-ffn-composition-single-use-release", "RELEASE_SCHEMA")
    require(release.get("schema_version") == "1.0.0", "RELEASE_VERSION")
    require(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "RELEASE_STATUS")
    require(release.get("real_event_authorized") is False and release.get("approval_asserted") is False, "RELEASE_AUTHORIZATION")
    require((release.get("event_id"), release.get("release_id"), release.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "RELEASE_IDENTITY")
    return release


def authorize(release_path: Path, approval_path: Path, token_path: Path) -> None:
    release = load(release_path)
    approval = load(approval_path)
    expected_approval_keys = {
        "schema", "schema_version", "reviewed_head", "execution_code_head", "release_sha256", "release_id",
        "authorization_sha256", "verdict", "statement", "approval_does_not_execute", "approval_is_not_token",
        "real_event_authorized", "ledger", "stop_boundary",
    }
    require(set(approval) == expected_approval_keys, "APPROVAL_KEYS")
    require(approval.get("schema") == "pulsarmlx.f017.representative-ffn-composition-single-use-release-independent-approval", "APPROVAL_SCHEMA")
    require(approval.get("schema_version") == "1.0.0" and approval.get("verdict") == "ACCEPT", "APPROVAL_VERDICT")
    require(approval.get("release_sha256") == sha256_path(release_path) and approval.get("release_id") == RELEASE_ID, "APPROVAL_RELEASE")
    require(approval.get("authorization_sha256") == AUTHORIZATION_SHA, "APPROVAL_AUTHORIZATION")
    require(approval.get("execution_code_head") == release.get("authoritative_execution_code_head"), "APPROVAL_CODE_HEAD")
    require(approval.get("statement") == "REPRESENTATIVE FFN COMPOSITION SINGLE-USE RELEASE V1 APPROVED", "APPROVAL_STATEMENT")
    require(approval.get("approval_does_not_execute") is True and approval.get("approval_is_not_token") is True, "APPROVAL_SEPARATION")
    require(approval.get("real_event_authorized") is False and approval.get("ledger") == 175, "APPROVAL_ACCOUNTING")
    require(approval.get("stop_boundary") == "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY", "APPROVAL_BOUNDARY")
    expected_token = {
        "approval_sha256": sha256_path(approval_path),
        "attempt_id": ATTEMPT_ID,
        "authorization_sha256": AUTHORIZATION_SHA,
        "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
        "event_id": EVENT_ID,
        "real_event_authorized": True,
        "release_id": RELEASE_ID,
        "release_sha256": sha256_path(release_path),
    }
    require(load(token_path) == expected_token, "GO_TOKEN")


def preflight(release_path: Path, *, home: Path | None = None) -> tuple[dict[str, Path], ModuleType, dict[str, Any]]:
    require(current_ledger() == 175, "LEDGER")
    validate_fixed_bindings()
    release = validate_release_path(release_path)
    subprocess.run([sys.executable, str(VALIDATOR), "--release", str(release_path)], check=True, capture_output=True, text=True)
    module = load_executor()
    module.require_environment()
    module.validate_arithmetic()
    module.validate_authorization(load(AUTHORIZATION))
    paths = fixed_paths(home)
    routed_fd, routed_stat = open_directory(paths["routed_root"])
    shared_fd, shared_stat = open_directory(paths["shared_root"])
    release_fd, release_stat = open_directory(paths["release_root"], exact_mode=0o700)
    output_fd, output_stat = open_directory(paths["output_root"], exact_mode=0o700)
    try:
        require_absent_at(output_fd, OUTPUT_BASENAME)
        require_absent_at(output_fd, MANIFEST_BASENAME)
    finally:
        os.close(output_fd); os.close(release_fd); os.close(shared_fd); os.close(routed_fd)
    require(not paths["state_root"].exists(), "PRIOR_ATTEMPT_STATE")
    require(release_stat.st_dev == output_stat.st_dev, "STATE_OUTPUT_FILESYSTEM")
    require(routed_stat.st_dev != 0 and shared_stat.st_dev != 0, "INPUT_FILESYSTEM_IDENTITY")
    require(shutil.disk_usage(paths["output_root"]).free >= STORAGE_REQUIRED, "STORAGE")
    routed, shared = module.open_pair(load(AUTHORIZATION), paths["routed_root"], paths["shared_root"])
    try:
        after = {"routed": routed.verify_after(), "shared": shared.verify_after()}
    finally:
        shared.close(); routed.close()
    return paths, module, after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--go-token", type=Path)
    args = parser.parse_args()
    paths, module, preflight_after = preflight(args.release.resolve())
    if args.preflight_only:
        require(args.go_token is None, "PREFLIGHT_TOKEN_FORBIDDEN")
        print(json.dumps({
            "disposition": "PRODUCTION_BINDINGS_RESOLVED",
            "ledger": 175,
            "inputs_after": preflight_after,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "shared_expert_executions": 0,
            "ffn_compositions": 0,
            "s1_materializations": 0,
            "s2_constructions": 0,
            "attempt_start": False,
            "output_published": False,
        }, sort_keys=True))
        return 0
    require(args.go_token is not None and args.go_token.resolve() == paths["go_token"].resolve(), "FIXED_GO_TOKEN_PATH")
    authorize(args.release.resolve(), paths["approval"].resolve(), args.go_token.resolve())
    attempt_started = False
    output_sha: str | None = None
    manifest_sha: str | None = None
    receipt_sha: str | None = None
    try:
        document = load(AUTHORIZATION)
        routed, shared = module.open_pair(document, paths["routed_root"], paths["shared_root"])
        try:
            begin_attempt(paths, args.release.resolve(), paths["approval"].resolve(), args.go_token.resolve())
            attempt_started = True
            begin_ffn(paths, args.release.resolve())
            raw, input_after = module.compose_from_open_inputs(routed, shared)
            output_sha, manifest_sha = publish_output_and_manifest(raw, paths["output_root"])
            receipt_sha = write_receipt(paths, args.release.resolve(), output_sha, manifest_sha, input_after)
        finally:
            shared.close(); routed.close()
        terminal_sha = write_terminal(paths, "COMPLETE", output_sha, manifest_sha, receipt_sha, None)
    except Exception as error:
        if attempt_started and not (paths["state_root"] / "terminal.json").exists():
            try:
                write_terminal(paths, "TERMINAL_FAILURE", output_sha, manifest_sha, receipt_sha, type(error).__name__)
            except Exception:
                pass
        raise
    print(json.dumps({
        "disposition": "COMPLETE",
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "ffn_compositions": 1,
        "s1_materializations": 0,
        "s2_constructions": 0,
        "output_sha256": output_sha,
        "output_manifest_sha256": manifest_sha,
        "execution_receipt_sha256": receipt_sha,
        "terminal_sha256": terminal_sha,
        "stop_boundary": "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseError, FileNotFoundError, PermissionError, subprocess.CalledProcessError) as error:
        ffn_count = 0
        try:
            ffn_count = int((fixed_paths()["state_root"] / "ffn-start.json").is_file())
        except Exception:
            pass
        print(json.dumps({
            "disposition": "FAIL_CLOSED",
            "error": type(error).__name__,
            "ledger": 175,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "shared_expert_executions": 0,
            "ffn_compositions": ffn_count,
            "s1_materializations": 0,
            "s2_constructions": 0,
        }, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)

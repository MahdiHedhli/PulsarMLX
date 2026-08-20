#!/usr/bin/env python3
"""Single-use release wrapper for the representative routed aggregate."""

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
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-authorization-v1.json"
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-arithmetic-v1.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_routed_aggregate_executor_v1.py"
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_routed_aggregate_single_use_release_v1.py"
PATHS_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-release-paths-v1.json"
PUBLICATION_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-output-publication-v1.json"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-single-use-release-v1.json"
APPROVAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-routed-aggregate-single-use-release-v1-independent-approval-v1.json"

AUTHORIZATION_SHA = "d103ab6abc81cbeffea1c95553ba70b41cd7c430b403b39bcf2542d6cc4d3590"
ARITHMETIC_SHA = "ef4b6f5c4e66efd031d6fba1fafee087e5496dd16b5b6f658204359f89762da2"
EXECUTOR_SHA = "fa85558686caa3a57ca356d7e49e5d73ca1f7cb512c1148b670ce0f504e921d5"
EVENT_ID = "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
OUTPUT_BASENAME = "routed-aggregate.f64le"
OUTPUT_BYTES = 49152
STORAGE_REQUIRED = 67108864


class ReleaseError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_unique)
    require(isinstance(value, dict), "JSON object required")
    return value


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fixed_paths(home: Path | None = None) -> dict[str, Path]:
    anchor = home if home is not None else Path.home()
    input_root = anchor / ".local/share/pulsarmlx/f017/representative-expert-recovery-release-1/outputs"
    release_root = anchor / ".local/share/pulsarmlx/f017/representative-routed-aggregate-release-1"
    return {
        "input_root": input_root,
        "manifest": input_root / "manifest.json",
        "release_root": release_root,
        "state_root": release_root / "attempt-state",
        "output_root": release_root / "outputs",
        "output": release_root / "outputs" / OUTPUT_BASENAME,
        "go_token": release_root / "go-token.json",
        "approval": APPROVAL,
    }


def open_validated_directory(path: Path, *, exact_mode: int | None = None) -> tuple[int, os.stat_result]:
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode), f"directory identity: {path.name}")
    require(before.st_uid == os.getuid(), f"directory owner: {path.name}")
    require(before.st_mode & 0o022 == 0, f"directory writable alias: {path.name}")
    if exact_mode is not None:
        require(stat.S_IMODE(before.st_mode) == exact_mode, f"directory mode: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    after = os.fstat(descriptor)
    require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), f"directory substitution: {path.name}")
    return descriptor, after


def require_absent_at(directory_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ReleaseError(f"pre-existing destination: {name}")


def load_executor() -> ModuleType:
    require(sha256_path(EXECUTOR) == EXECUTOR_SHA, "executor identity")
    spec = importlib.util.spec_from_file_location("f017_bound_routed_aggregate_executor", EXECUTOR)
    require(spec is not None and spec.loader is not None, "executor import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_fixed_bindings() -> None:
    require(sha256_path(AUTHORIZATION) == AUTHORIZATION_SHA, "authorization identity")
    require(sha256_path(ARITHMETIC) == ARITHMETIC_SHA, "arithmetic identity")
    require(sha256_path(EXECUTOR) == EXECUTOR_SHA, "executor identity")


def validate_release_path(release_path: Path) -> dict[str, Any]:
    require(release_path.resolve() == RELEASE.resolve(), "release path")
    release = load(release_path)
    require(release.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-single-use-release", "release schema")
    require(release.get("schema_version") == "1.0.0", "release schema version")
    require(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "release state")
    require(release.get("real_event_authorized") is False and release.get("approval_asserted") is False, "release authorization state")
    require(release.get("event_id") == EVENT_ID and release.get("release_id") == RELEASE_ID and release.get("attempt_id") == ATTEMPT_ID, "release identity")
    return release


def validate_output_descriptor(descriptor: int) -> tuple[str, bytes]:
    metadata = os.fstat(descriptor)
    require(stat.S_ISREG(metadata.st_mode), "output regular file")
    require(metadata.st_uid == os.getuid(), "output owner")
    require(stat.S_IMODE(metadata.st_mode) == 0o400, "output mode")
    require(metadata.st_nlink == 1 and metadata.st_size == OUTPUT_BYTES, "output geometry")
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = b""
    while len(raw) < OUTPUT_BYTES:
        chunk = os.read(descriptor, OUTPUT_BYTES - len(raw))
        require(bool(chunk), "short output")
        raw += chunk
    require(os.read(descriptor, 1) == b"", "long output")
    values = struct.unpack("<6144d", raw)
    require(all(math.isfinite(value) for value in values), "non-finite output")
    return sha256_bytes(raw), raw


def publish_no_replace(raw: bytes, output_root: Path, output_basename: str = OUTPUT_BASENAME) -> str:
    require(len(raw) == OUTPUT_BYTES, "output byte count")
    directory_fd, _ = open_validated_directory(output_root, exact_mode=0o700)
    temporary_name: str | None = None
    try:
        require_absent_at(directory_fd, output_basename)
        temporary_name = f".{output_basename}.{secrets.token_hex(16)}"
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        try:
            view = memoryview(raw)
            written = 0
            while written < len(view):
                written += os.write(descriptor, view[written:])
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary_name, output_basename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_name = None
        os.fsync(directory_fd)
        output_fd = os.open(output_basename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            identity, observed = validate_output_descriptor(output_fd)
            require(observed == raw, "published output mismatch")
        finally:
            os.close(output_fd)
        return identity
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def write_state_artifact(state_root: Path, name: str, packet: dict[str, Any]) -> str:
    raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
    directory_fd, _ = open_validated_directory(state_root, exact_mode=0o700)
    try:
        require_absent_at(directory_fd, name)
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o400, dir_fd=directory_fd)
        try:
            view = memoryview(raw)
            written = 0
            while written < len(view):
                written += os.write(descriptor, view[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return sha256_bytes(raw)


def begin_attempt(paths: dict[str, Path], release_path: Path, approval_path: Path, token_path: Path) -> str:
    state_root = paths["state_root"]
    require(not state_root.exists(), "prior attempt")
    os.mkdir(state_root, 0o700)
    parent_fd, _ = open_validated_directory(state_root.parent, exact_mode=0o700)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    packet = {
        "schema": "pulsarmlx.f017.representative-routed-aggregate-release-attempt-start",
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
        "consumption_boundary": "DURABLE_ATTEMPT_START_BEFORE_AGGREGATE_COMPUTATION",
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
    }
    return write_state_artifact(state_root, "attempt-start.json", packet)


def write_terminal(paths: dict[str, Path], disposition: str, output_sha256: str | None, error: str | None) -> str:
    packet = {
        "schema": "pulsarmlx.f017.representative-routed-aggregate-release-terminal",
        "schema_version": "1.0.0",
        "event_id": EVENT_ID,
        "release_id": RELEASE_ID,
        "attempt_id": ATTEMPT_ID,
        "disposition": disposition,
        "output_sha256": output_sha256,
        "output_bytes": OUTPUT_BYTES if output_sha256 else 0,
        "error": error,
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "aggregate_executions": 1 if output_sha256 else 0,
        "retry": False,
        "resume": False,
        "second_attempt": False,
        "stop_boundary": "AFTER_ROUTED_AGGREGATE_ONLY",
    }
    return write_state_artifact(paths["state_root"], "terminal.json", packet)


def authorize(release_path: Path, token_path: Path, approval_path: Path) -> None:
    release = load(release_path)
    approval = load(approval_path)
    expected_approval_keys = {
        "schema", "schema_version", "reviewed_head", "execution_code_head", "release_sha256", "release_id",
        "authorization_sha256", "verdict", "statement", "approval_does_not_execute", "approval_is_not_token",
        "real_event_authorized", "ledger", "stop_boundary"
    }
    require(set(approval) == expected_approval_keys, "approval schema keys")
    require(approval.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-single-use-release-independent-approval", "approval schema")
    require(approval.get("schema_version") == "1.0.0" and approval.get("verdict") == "ACCEPT", "approval verdict")
    require(approval.get("release_sha256") == sha256_path(release_path) and approval.get("release_id") == RELEASE_ID, "approval release binding")
    require(approval.get("authorization_sha256") == AUTHORIZATION_SHA, "approval authorization binding")
    require(approval.get("execution_code_head") == release.get("authoritative_execution_code_head"), "approval code head")
    require(approval.get("statement") == "REPRESENTATIVE ROUTED-AGGREGATE SINGLE-USE RELEASE V1 APPROVED", "approval statement")
    require(approval.get("approval_does_not_execute") is True and approval.get("approval_is_not_token") is True, "approval separation")
    require(approval.get("real_event_authorized") is False and approval.get("ledger") == 175, "approval accounting")
    require(approval.get("stop_boundary") == "AFTER_ROUTED_AGGREGATE_ONLY", "approval stop boundary")
    token = load(token_path)
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
    require(token == expected_token, "GO token")


def preflight(release_path: Path) -> tuple[dict[str, Path], ModuleType, list[dict[str, Any]]]:
    require(current_ledger() == 175, "ledger")
    validate_fixed_bindings()
    validate_release_path(release_path)
    subprocess.run([sys.executable, str(VALIDATOR), "--release", str(release_path)], check=True, capture_output=True, text=True)
    module = load_executor()
    module.require_environment()
    _, records = module.validate_authorization(AUTHORIZATION)
    paths = fixed_paths()
    input_fd, input_stat = open_validated_directory(paths["input_root"])
    os.close(input_fd)
    release_fd, release_stat = open_validated_directory(paths["release_root"], exact_mode=0o700)
    os.close(release_fd)
    output_fd, output_stat = open_validated_directory(paths["output_root"], exact_mode=0o700)
    try:
        require_absent_at(output_fd, OUTPUT_BASENAME)
    finally:
        os.close(output_fd)
    require(not paths["state_root"].exists(), "prior attempt state")
    require(release_stat.st_dev == output_stat.st_dev, "state/output filesystem")
    require(shutil.disk_usage(paths["output_root"]).free >= STORAGE_REQUIRED, "storage")
    require(input_stat.st_dev != 0, "input filesystem identity")
    with module.OpenOnceInputs(paths["input_root"], records, manifest_sha=module.MANIFEST_SHA, forbidden_shas=frozenset()) as inputs:
        after = inputs.verify_after()
    require(len(after) == 8, "input count")
    return paths, module, records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--go-token", type=Path)
    args = parser.parse_args()
    paths, module, records = preflight(args.release.resolve())
    if args.preflight_only:
        require(args.go_token is None, "preflight token forbidden")
        print(json.dumps({
            "disposition": "PRODUCTION_BINDINGS_RESOLVED",
            "ledger": 175,
            "inputs": 8,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "aggregate_executions": 0,
            "attempt_start": False,
            "output_published": False,
        }, sort_keys=True))
        return 0
    require(args.go_token is not None and args.go_token.resolve() == paths["go_token"].resolve(), "fixed GO token path")
    authorize(args.release.resolve(), args.go_token.resolve(), paths["approval"].resolve())
    attempt_started = False
    output_identity: str | None = None
    try:
        with module.OpenOnceInputs(paths["input_root"], records, manifest_sha=module.MANIFEST_SHA, forbidden_shas=frozenset()) as inputs:
            begin_attempt(paths, args.release.resolve(), paths["approval"].resolve(), args.go_token.resolve())
            attempt_started = True
            raw = module.aggregate_bytes(inputs.raw_inputs)
            inputs.verify_after()
            output_identity = publish_no_replace(raw, paths["output_root"])
        terminal_sha = write_terminal(paths, "COMPLETE", output_identity, None)
    except Exception as error:
        if attempt_started and not (paths["state_root"] / "terminal.json").exists():
            try:
                write_terminal(paths, "TERMINAL_FAILURE", output_identity, type(error).__name__)
            except Exception:
                pass
        raise
    print(json.dumps({
        "disposition": "COMPLETE",
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "aggregate_executions": 1,
        "output_sha256": output_identity,
        "output_bytes": OUTPUT_BYTES,
        "terminal_sha256": terminal_sha,
        "stop_boundary": "AFTER_ROUTED_AGGREGATE_ONLY",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseError, FileNotFoundError, PermissionError, subprocess.CalledProcessError) as error:
        print(json.dumps({
            "disposition": "FAIL_CLOSED",
            "error": type(error).__name__,
            "ledger": 175,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "aggregate_executions": 0,
        }, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)

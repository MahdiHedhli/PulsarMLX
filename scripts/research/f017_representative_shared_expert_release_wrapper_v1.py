#!/usr/bin/env python3
"""Single-use retained-only representative shared-expert release wrapper."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import platform
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
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-single-use-release-v1.json"
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-authorization-v1.json"
COMPUTATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-computation-v1.json"
PATH_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-release-paths-v1.json"
PUBLICATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-output-publication-v1.json"
REPRODUCTION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-reproduction-v1.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_shared_expert_recovery_executor_v1.py"
REPRODUCER = ROOT / "scripts/research/f017_representative_shared_expert_reproduction_v1.py"
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_shared_expert_single_use_release_v1.py"

EVENT_ID = "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-1"
RELEASE_ID = EVENT_ID + "-RELEASE-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
AUTHORIZATION_SHA = "45b25de7978e01898eb5ea948202d70d5b43f33c2cbc84ec7b11a9955c5d9596"
OUTPUT_NAME = "representative-shared-expert-output.f32le"
OUTPUT_BYTES = 24576
STORAGE_REQUIRED = 3221225472

FIXED_PATHS = {
    "representative_input": Path("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-expert-input-v1/router_normalized.f32le"),
    "parameter_root": Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-runner/.pulsarmlx-local/canonical-shared-expert-output-recovery-1/package"),
    "state_root": Path("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/attempt-state"),
    "output_root": Path("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/outputs"),
    "approval": ROOT / "docs/architecture/reviews/evidence/f017-representative-shared-expert-recovery-single-use-release-v1-independent-approval-v1.json",
    "go_token": Path("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/go-token.json"),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"DUPLICATE_JSON_KEY:{key}")
        result[key] = value
    return result


def parse_json_bytes(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def load(path: Path) -> dict[str, Any]:
    return parse_json_bytes(path.read_bytes())


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def open_validated_directory(path: Path, *, exact_mode: int | None = None) -> tuple[int, os.stat_result]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    metadata = os.fstat(descriptor)
    require(stat.S_ISDIR(metadata.st_mode), "DIRECTORY_REQUIRED")
    require(metadata.st_uid == os.getuid(), "DIRECTORY_OWNER")
    if exact_mode is not None:
        require(stat.S_IMODE(metadata.st_mode) == exact_mode, "DIRECTORY_MODE")
    return descriptor, metadata


def write_state_artifact(state_root: Path, name: str, packet: dict[str, Any]) -> str:
    raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
    directory_fd, _ = open_validated_directory(state_root, exact_mode=0o700)
    try:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o400, dir_fd=directory_fd)
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                offset += os.write(descriptor, view[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return sha256_bytes(raw)


def validate_output_descriptor(descriptor: int) -> tuple[str, bytes]:
    metadata = os.fstat(descriptor)
    require(stat.S_ISREG(metadata.st_mode), "OUTPUT_REGULAR")
    require(metadata.st_uid == os.getuid(), "OUTPUT_OWNER")
    require(stat.S_IMODE(metadata.st_mode) == 0o400, "OUTPUT_MODE")
    require(metadata.st_nlink == 1 and metadata.st_size == OUTPUT_BYTES, "OUTPUT_GEOMETRY")
    raw = b""
    while len(raw) < OUTPUT_BYTES:
        chunk = os.pread(descriptor, OUTPUT_BYTES - len(raw), len(raw))
        require(bool(chunk), "OUTPUT_SHORT_READ")
        raw += chunk
    require(os.pread(descriptor, 1, OUTPUT_BYTES) == b"", "OUTPUT_LONG_READ")
    values = struct.unpack("<6144f", raw)
    require(all(math.isfinite(value) for value in values), "OUTPUT_NONFINITE")
    return sha256_bytes(raw), raw


def publish_no_replace(raw: bytes, output_root: Path) -> str:
    require(len(raw) == OUTPUT_BYTES, "OUTPUT_BYTE_COUNT")
    directory_fd, _ = open_validated_directory(output_root, exact_mode=0o700)
    temporary_name: str | None = None
    try:
        try:
            os.stat(OUTPUT_NAME, dir_fd=directory_fd, follow_symlinks=False)
            raise RuntimeError("OUTPUT_PREEXISTS")
        except FileNotFoundError:
            pass
        temporary_name = f".{OUTPUT_NAME}.{secrets.token_hex(16)}"
        descriptor = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
        try:
            view = memoryview(raw)
            offset = 0
            while offset < len(view):
                offset += os.write(descriptor, view[offset:])
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.link(temporary_name, OUTPUT_NAME, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
        os.unlink(temporary_name, dir_fd=directory_fd)
        temporary_name = None
        os.fsync(directory_fd)
        published_fd = os.open(OUTPUT_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            identity, observed = validate_output_descriptor(published_fd)
            require(observed == raw, "OUTPUT_DESCRIPTOR_READBACK_MISMATCH")
        finally:
            os.close(published_fd)
        return identity
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def load_executor() -> ModuleType:
    spec = importlib.util.spec_from_file_location("f017_shared_release_executor", EXECUTOR)
    require(spec is not None and spec.loader is not None, "EXECUTOR_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_environment() -> None:
    require(sys.version_info[:3] == (3, 14, 6), "ENVIRONMENT_CPYTHON")
    import numpy as np
    require(np.__version__ == "2.4.5", "ENVIRONMENT_NUMPY")
    require(sys.byteorder == "little", "ENVIRONMENT_ENDIANNESS")
    require(platform.system() == "Darwin" and platform.machine() == "arm64", "ENVIRONMENT_PLATFORM")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        require(os.environ.get(name) == "1", f"ENVIRONMENT_THREADS:{name}")


def validate_kernel_identities(module: ModuleType) -> None:
    contract = load(COMPUTATION)
    expected_sources = {
        ROOT / contract["decoders"]["q5_k"]["decoder_a"]["path"]: contract["decoders"]["q5_k"]["decoder_a"]["source_sha256"],
        ROOT / contract["decoders"]["q5_k"]["decoder_b"]["path"]: contract["decoders"]["q5_k"]["decoder_b"]["source_sha256"],
        ROOT / contract["decoders"]["q6_k"]["decoder_a"]["path"]: contract["decoders"]["q6_k"]["decoder_a"]["source_sha256"],
    }
    for path, expected in expected_sources.items():
        require(sha256_path(path) == expected, "DECODER_SOURCE_IDENTITY")
    symbols = {
        module.decode_q5_k_spec: contract["decoders"]["q5_k"]["decoder_a"]["implementation_sha256"],
        module.decode_q5_k_upstream_spec: contract["decoders"]["q5_k"]["decoder_b"]["implementation_sha256"],
        module.decode_q6_k_spec: contract["decoders"]["q6_k"]["decoder_a"]["implementation_sha256"],
        module.decode_q6_k_independent: contract["decoders"]["q6_k"]["decoder_b"]["implementation_sha256"],
        module.strict_f32_matvec: contract["runtime_kernel_identities"]["strict_f32_matvec"],
        module.strict_f32_silu: contract["runtime_kernel_identities"]["strict_f32_silu"],
        module.compute: contract["runtime_kernel_identities"]["compute"],
    }
    for symbol, expected in symbols.items():
        require(sha256_bytes(inspect.getsource(symbol).encode()) == expected, "KERNEL_IMPLEMENTATION_IDENTITY")


def validate_fixed_bindings(release: dict[str, Any]) -> None:
    require(Path.home() == Path("/Users/mhedhli"), "HOST_HOME")
    require(ROOT == Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-live-one-shot"), "REPOSITORY_ROOT")
    for binding in release["bindings"].values():
        path = ROOT / binding["path"]
        require(path.is_file() and sha256_path(path) == binding["sha256"], f"BINDING:{binding['path']}")
    code_head = release["authoritative_execution_code_head"]
    subprocess.run(["git", "merge-base", "--is-ancestor", code_head, "HEAD"], cwd=ROOT, check=True, capture_output=True)
    require(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True, capture_output=True, text=True).stdout == "", "WORKTREE_NOT_CLEAN")


def validate_release(release_path: Path, release: dict[str, Any]) -> None:
    require(release_path.resolve() == RELEASE.resolve(), "RELEASE_PATH")
    require(release.get("schema") == "pulsarmlx.f017.representative-shared-expert-recovery-single-use-release", "RELEASE_SCHEMA")
    require(release.get("schema_version") == "1.0.0", "RELEASE_SCHEMA_VERSION")
    require(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "RELEASE_STATUS")
    require(release.get("real_event_authorized") is False and release.get("approval_asserted") is False, "RELEASE_AUTHORIZATION_STATE")
    require(release.get("event_id") == EVENT_ID and release.get("release_id") == RELEASE_ID and release.get("attempt_id") == ATTEMPT_ID, "RELEASE_IDENTITY")


def prepare_retained(module: ModuleType, authorization: dict[str, Any]):
    return module.open_retained(authorization, FIXED_PATHS["representative_input"], FIXED_PATHS["parameter_root"])


def destination_preflight() -> None:
    base = FIXED_PATHS["state_root"].parent
    require(base.is_dir() and not base.is_symlink(), "RELEASE_ROOT")
    base_fd, _ = open_validated_directory(base, exact_mode=0o700)
    os.close(base_fd)
    require(not FIXED_PATHS["state_root"].exists(), "PRIOR_ATTEMPT")
    require(not FIXED_PATHS["output_root"].exists(), "PRIOR_OUTPUT_ROOT")
    require(shutil.disk_usage(base).free >= STORAGE_REQUIRED, "STORAGE")


def preflight(release_path: Path):
    require(current_ledger() == 175, "LEDGER")
    release_raw = release_path.read_bytes()
    release = parse_json_bytes(release_raw)
    validate_release(release_path, release)
    validate_fixed_bindings(release)
    require_environment()
    subprocess.run([sys.executable, str(VALIDATOR), "--release", str(release_path)], check=True, capture_output=True, text=True)
    module = load_executor()
    validate_kernel_identities(module)
    authorization_raw = AUTHORIZATION.read_bytes()
    require(sha256_bytes(authorization_raw) == AUTHORIZATION_SHA, "AUTHORIZATION_IDENTITY")
    authorization = parse_json_bytes(authorization_raw)
    module.validate_authorization(authorization)
    destination_preflight()
    normalized, manifest, parameters = prepare_retained(module, authorization)
    return release_raw, release, authorization_raw, authorization, module, normalized, manifest, parameters


def authorize(release_raw: bytes, release: dict[str, Any], token_path: Path) -> None:
    approval_path = FIXED_PATHS["approval"]
    require(approval_path.is_file(), "INDEPENDENT_APPROVAL_REQUIRED")
    approval = load(approval_path)
    expected_approval_keys = {"schema", "schema_version", "reviewed_head", "execution_code_head", "release_sha256", "release_id", "authorization_sha256", "verdict", "statement", "approval_does_not_execute", "approval_is_not_token", "real_event_authorized", "ledger", "stop_boundary"}
    require(set(approval) == expected_approval_keys, "APPROVAL_SCHEMA_KEYS")
    require(approval.get("schema") == "pulsarmlx.f017.representative-shared-expert-recovery-single-use-release-independent-approval", "APPROVAL_SCHEMA")
    require(approval.get("schema_version") == "1.0.0" and approval.get("verdict") == "ACCEPT", "APPROVAL_VERDICT")
    require(approval.get("release_sha256") == sha256_bytes(release_raw) and approval.get("release_id") == RELEASE_ID, "APPROVAL_RELEASE_BINDING")
    require(approval.get("authorization_sha256") == AUTHORIZATION_SHA, "APPROVAL_AUTHORIZATION_BINDING")
    require(approval.get("execution_code_head") == release.get("authoritative_execution_code_head"), "APPROVAL_CODE_HEAD")
    require(approval.get("statement") == "REPRESENTATIVE SHARED-EXPERT RECOVERY SINGLE-USE RELEASE V1 APPROVED", "APPROVAL_STATEMENT")
    require(approval.get("approval_does_not_execute") is True and approval.get("approval_is_not_token") is True, "APPROVAL_SEPARATION")
    require(approval.get("real_event_authorized") is False and approval.get("ledger") == 175, "APPROVAL_ACCOUNTING")
    require(approval.get("stop_boundary") == "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY", "APPROVAL_STOP_BOUNDARY")
    token = load(token_path)
    expected_token = {"approval_sha256": sha256_path(approval_path), "attempt_id": ATTEMPT_ID, "authorization_sha256": AUTHORIZATION_SHA, "disposition": "GO_EXECUTE_ONCE_NO_RETRY", "event_id": EVENT_ID, "real_event_authorized": True, "release_id": RELEASE_ID, "release_sha256": sha256_bytes(release_raw)}
    require(token == expected_token, "GO_TOKEN")


def begin_attempt(release_raw: bytes, authorization_raw: bytes, token_path: Path) -> None:
    state_root = FIXED_PATHS["state_root"]
    os.mkdir(state_root, 0o700)
    fsync_directory(state_root.parent)
    packet = {"schema": "pulsarmlx.f017.representative-shared-expert-release-attempt-start", "schema_version": "1.0.0", "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID, "release_sha256": sha256_bytes(release_raw), "authorization_sha256": sha256_bytes(authorization_raw), "approval_sha256": sha256_path(FIXED_PATHS["approval"]), "go_token_sha256": sha256_path(token_path), "consumption_boundary": "DURABLE_ATTEMPT_START_BEFORE_SHARED_EXPERT_COMPUTATION", "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0}
    write_state_artifact(state_root, "attempt-start.json", packet)


def begin_computation(release_raw: bytes) -> None:
    packet = {"schema": "pulsarmlx.f017.representative-shared-expert-release-computation-start", "schema_version": "1.0.0", "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID, "release_sha256": sha256_bytes(release_raw), "accounting_semantics": "DURABLE_START_COUNTS_ONE_REAL_SHARED_EXPERT_EXECUTION_REGARDLESS_OF_OUTCOME", "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "shared_expert_executions": 1, "routed_aggregate_executions": 0, "ffn_completions": 0, "s2_constructions": 0}
    write_state_artifact(FIXED_PATHS["state_root"], "shared-computation-start.json", packet)


def reproduce(output_sha256: str) -> list[dict[str, Any]]:
    results = []
    command = [sys.executable, str(REPRODUCER), "--representative-input", str(FIXED_PATHS["representative_input"]), "--parameter-root", str(FIXED_PATHS["parameter_root"]), "--expected-output-sha256", output_sha256]
    for _ in range(2):
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        packet = parse_json_bytes(completed.stdout.encode())
        require(packet.get("result") == "EXACT_IDENTITY" and packet.get("output_sha256") == output_sha256, "REPRODUCTION_IDENTITY")
        require(packet.get("checkpoint_reads") == 0 and packet.get("shard_opens") == 0, "REPRODUCTION_ACCESS")
        results.append(packet)
    return results


def write_terminal(disposition: str, output_sha256: str | None, reproduction_results: list[dict[str, Any]], error: str | None) -> dict[str, Any]:
    computation_started = (FIXED_PATHS["state_root"] / "shared-computation-start.json").is_file()
    complete = disposition == "COMPLETE"
    require(not complete or (computation_started and output_sha256 is not None and len(reproduction_results) == 2), "COMPLETE_REQUIREMENTS")
    packet = {"schema": "pulsarmlx.f017.representative-shared-expert-release-terminal", "schema_version": "1.0.0", "event_id": EVENT_ID, "release_id": RELEASE_ID, "attempt_id": ATTEMPT_ID, "disposition": disposition, "error": error, "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "shared_expert_executions": 1 if computation_started else 0, "verification_reproduction_computations": len(reproduction_results), "reproduction_exact_identity": complete, "output_sha256": output_sha256, "output_bytes": OUTPUT_BYTES if output_sha256 else 0, "output_authority": complete, "routed_aggregate_executions": 0, "ffn_completions": 0, "s2_constructions": 0, "retry": False, "resume": False, "second_attempt": False, "stop_boundary": "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY"}
    write_state_artifact(FIXED_PATHS["state_root"], "terminal.json", packet)
    return packet


def execute(release_path: Path, token_path: Path) -> dict[str, Any]:
    release_raw, release, authorization_raw, authorization, module, normalized, manifest, parameters = preflight(release_path)
    authorize(release_raw, release, token_path)
    begin_attempt(release_raw, authorization_raw, token_path)
    begin_computation(release_raw)
    output_sha256: str | None = None
    reproduction_results: list[dict[str, Any]] = []
    try:
        raw = module.compute(authorization, normalized, parameters)
        module.verify_after(normalized, manifest, parameters)
        FIXED_PATHS["output_root"].mkdir(mode=0o700, parents=False, exist_ok=False)
        fsync_directory(FIXED_PATHS["output_root"].parent)
        output_sha256 = publish_no_replace(raw, FIXED_PATHS["output_root"])
        module.close_all(normalized, manifest, parameters)
        normalized = manifest = None
        parameters = []
        reproduction_results = reproduce(output_sha256)
        return write_terminal("COMPLETE", output_sha256, reproduction_results, None)
    except Exception as error:
        if not (FIXED_PATHS["state_root"] / "terminal.json").exists():
            write_terminal("TERMINAL_FAILURE", output_sha256, reproduction_results, type(error).__name__)
        raise
    finally:
        if normalized is not None:
            module.close_all(normalized, manifest, parameters)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--go-token", type=Path)
    args = parser.parse_args()
    if args.preflight_only:
        release_raw, _, _, _, module, normalized, manifest, parameters = preflight(args.release.resolve())
        try:
            after = module.verify_after(normalized, manifest, parameters)
        finally:
            module.close_all(normalized, manifest, parameters)
        print(json.dumps({"result": "PRODUCTION_BINDINGS_RESOLVED", "release_sha256": sha256_bytes(release_raw), "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "shared_expert_executions": 0, "retained_parameters": 3, "retained_packed_bytes": 27623424, "after_sha256": after}, sort_keys=True))
        return 0
    require(args.go_token is not None and args.go_token.resolve() == FIXED_PATHS["go_token"], "FIXED_GO_TOKEN_PATH")
    print(json.dumps(execute(args.release.resolve(), args.go_token.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

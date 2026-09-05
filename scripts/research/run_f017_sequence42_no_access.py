#!/usr/bin/env python3
"""Start a Sequence 42 qualification under the inherited live-root barrier.

This launcher deliberately imports no F017 target module.  It verifies that the
target source contains the two literal live-root constants, then starts a fresh
Python process whose ``sitecustomize`` installs the barrier before target-code
imports can occur.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import sys


_LIVE_NAMES = ("_LIVE_PACKAGE_PARENT", "_LIVE_CHECKPOINT_ROOT")


def _literal_path(node: ast.AST | None) -> str | None:
    if (
        not isinstance(node, ast.Call)
        or not isinstance(node.func, ast.Name)
        or node.func.id != "Path"
        or len(node.args) != 1
        or node.keywords
        or not isinstance(node.args[0], ast.Constant)
        or not isinstance(node.args[0].value, str)
    ):
        return None
    return node.args[0].value


_MAXIMUM_SOURCE_BYTES = 2_000_000
_MAXIMUM_LOG_BYTES = 16_777_216
_BYPASS_FLAGS = frozenset({"S", "I", "E"})


def _validated_python_command(command: list[str]) -> list[str]:
    if not command:
        raise ValueError("Sequence 42 barrier child command required")
    executable = command[0]
    if (
        not os.path.isabs(executable)
        or os.path.normpath(executable) != os.path.normpath(sys.executable)
    ):
        raise ValueError("exact current Python executable required")
    for value in command[1:]:
        if value in {"-c", "-m", "--"} or not value.startswith("-"):
            break
        if value.startswith("--"):
            continue
        if any(flag in _BYPASS_FLAGS for flag in value[1:]):
            raise ValueError("Python site-startup bypass flag prohibited")
    return command


def _source_roots(source: Path) -> tuple[tuple[str, str], dict[str, int | str]]:
    if (
        not source.is_absolute()
        or Path(os.path.normpath(os.fspath(source))) != source
        or os.fspath(source).startswith("//")
    ):
        raise ValueError("canonical absolute Sequence 42 target source required")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(source, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAXIMUM_SOURCE_BYTES
        ):
            raise ValueError("Sequence 42 target source identity")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("short Sequence 42 target source read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("Sequence 42 target source excess bytes")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise RuntimeError("Sequence 42 target source changed")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    tree = ast.parse(raw, filename=os.fspath(source))
    found: dict[str, str] = {}
    for item in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(item, ast.AnnAssign):
            target, value = item.target, item.value
        elif isinstance(item, ast.Assign) and len(item.targets) == 1:
            target, value = item.targets[0], item.value
        if isinstance(target, ast.Name) and target.id in _LIVE_NAMES:
            if target.id in found:
                raise ValueError(f"duplicate live root: {target.id}")
            literal = _literal_path(value)
            if literal is None:
                raise ValueError(f"nonliteral live root: {target.id}")
            found[target.id] = literal
    if set(found) != set(_LIVE_NAMES):
        raise ValueError("Sequence 42 live-root constant census")
    roots = tuple(found[name] for name in _LIVE_NAMES)
    if len(set(roots)) != 2 or any(not os.path.isabs(root) for root in roots):
        raise ValueError("Sequence 42 live-root geometry")
    identity: dict[str, int | str] = {
        "device": before.st_dev,
        "inode": before.st_ino,
        "size": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "ctime_ns": before.st_ctime_ns,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return roots, identity  # type: ignore[return-value]


def _read_log(log: Path, identity: tuple[int, int]) -> tuple[list[dict[str, object]], bytes]:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(log, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or (before.st_dev, before.st_ino) != identity
            or before.st_size > _MAXIMUM_LOG_BYTES
        ):
            raise ValueError("Sequence 42 barrier log identity")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("short Sequence 42 barrier log read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("Sequence 42 barrier log excess bytes")
        after = os.fstat(descriptor)
        canonical = os.stat(log, follow_symlinks=False)
        stable = ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size")
        if any(getattr(before, name) != getattr(after, name) for name in stable) or (
            canonical.st_dev,
            canonical.st_ino,
        ) != identity:
            raise RuntimeError("Sequence 42 barrier log changed")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    events: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line:
            raise ValueError("empty Sequence 42 barrier event")
        value = json.loads(line)
        if type(value) is not dict:
            raise ValueError("Sequence 42 barrier event object")
        events.append(value)
    return events, raw


def _validate_log(
    events: list[dict[str, object]],
    *,
    root_token: str,
    source_sha256: str,
    child_returncode: int,
) -> dict[str, object]:
    active_events = [item for item in events if item.get("event") == "BARRIER_ACTIVE"]
    spawn_events = [item for item in events if item.get("event") == "SPAWN_INTENT"]
    native_events = [
        item for item in events if item.get("event") == "NATIVE_SUBPROCESS_OBSERVED"
    ]
    active_tokens = [item.get("token") for item in active_events]
    spawn_tokens = [item.get("token") for item in spawn_events]
    violations = [
        item
        for item in events
        if item.get("event") in {"BLOCKED_ACCESS", "BARRIER_POLICY_VIOLATION"}
    ]
    if any(type(item) is not str or not item for item in active_tokens + spawn_tokens):
        raise ValueError("Sequence 42 barrier token type")
    if any(
        item.get("root_count") != 2
        or item.get("scope")
        != "LIVE_EVENT06_ROOTS_DESCENDANTS_RESOLVERS_AND_SUBPROCESSES"
        or item.get("source_sha256") != source_sha256
        or type(item.get("pid")) is not int
        or item["pid"] <= 0
        for item in active_events
    ):
        raise RuntimeError("Sequence 42 startup barrier authority")
    if active_tokens.count(root_token) != 1:
        raise RuntimeError("Sequence 42 root startup barrier coverage")
    if len(spawn_tokens) != len(set(spawn_tokens)):
        raise RuntimeError("Sequence 42 duplicate spawn token")
    expected_active = {root_token, *spawn_tokens}
    if set(active_tokens) != expected_active or len(active_tokens) != len(expected_active):
        raise RuntimeError("Sequence 42 child startup barrier coverage")
    if violations:
        raise RuntimeError("Sequence 42 prohibited access or process launch")
    if any(
        item.get("operation") != "subprocess.Popen"
        or type(item.get("executable")) is not str
        or not item["executable"].startswith(
            ("/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/")
        )
        or type(item.get("argument_count")) is not int
        or item["argument_count"] <= 0
        or type(item.get("child_pid")) is not int
        or item["child_pid"] <= 0
        or type(item.get("pid")) is not int
        or item["pid"] <= 0
        or item.get("source_free_from_live_roots") is not True
        or item.get("token") not in expected_active
        for item in native_events
    ):
        raise RuntimeError("Sequence 42 native subprocess observation authority")
    target_imports = [
        item for item in events if item.get("event") == "EVENT06_TARGET_IMPORT"
    ]
    if not target_imports:
        raise RuntimeError("Sequence 42 target import coverage")
    if any(
        item.get("token") not in expected_active
        or type(item.get("module")) is not str
        or not item["module"]
        for item in target_imports
    ):
        raise RuntimeError("Sequence 42 target import authority")
    observed_processes = {
        *[int(item["pid"]) for item in active_events],
        *[int(item["child_pid"]) for item in native_events],
    }
    for pid in observed_processes:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise RuntimeError("Sequence 42 barrier process census") from exc
        raise RuntimeError("Sequence 42 barrier descendant still running")
    return {
        "schema": "pulsarmlx.f017.sequence42-no-access-supervisor/1.0.0",
        "barrier_processes": len(active_tokens),
        "spawn_intents": len(spawn_tokens),
        "native_subprocesses_observed": len(native_events),
        "event06_target_imports": len(target_imports),
        "source_sha256": source_sha256,
        "blocked_accesses": 0,
        "barrier_policy_violations": 0,
        "child_returncode": child_returncode,
        "startup_coverage": "PASS",
        "result": "PASS" if child_returncode == 0 else "CHILD_FAILURE",
    }


def _append_summary(log: Path, identity: tuple[int, int], value: dict[str, object]) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(log, flags)
    try:
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or observed.st_nlink != 1
            or stat.S_IMODE(observed.st_mode) != 0o600
            or (observed.st_dev, observed.st_ino) != identity
        ):
            raise ValueError("Sequence 42 barrier summary log identity")
        if os.write(descriptor, raw) != len(raw):
            raise OSError("short Sequence 42 barrier summary write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = list(arguments.command)
    if command and command[0] == "--":
        command.pop(0)
    command = _validated_python_command(command)

    source = arguments.source
    _roots, source_identity = _source_roots(source)
    log = arguments.log
    if not log.is_absolute() or log.exists() or not log.parent.is_dir():
        raise ValueError("fresh absolute Sequence 42 barrier log required")
    descriptor = os.open(
        log,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    os.fsync(descriptor)
    log_observed = os.fstat(descriptor)
    log_identity = (log_observed.st_dev, log_observed.st_ino)
    os.close(descriptor)

    barrier = Path(__file__).with_name("f017_sequence42_no_access_barrier")
    if not (barrier / "sitecustomize.py").is_file():
        raise RuntimeError("Sequence 42 sitecustomize barrier unavailable")
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        [os.fspath(barrier), *[item for item in existing.split(os.pathsep) if item]]
    )
    environment["F017_SEQUENCE42_SOURCE_FILE"] = os.fspath(source)
    environment["F017_SEQUENCE42_SOURCE_SHA256"] = str(source_identity["sha256"])
    environment["F017_SEQUENCE42_SOURCE_DEVICE"] = str(source_identity["device"])
    environment["F017_SEQUENCE42_SOURCE_INODE"] = str(source_identity["inode"])
    environment["F017_SEQUENCE42_SOURCE_SIZE"] = str(source_identity["size"])
    environment["F017_SEQUENCE42_SOURCE_MTIME_NS"] = str(source_identity["mtime_ns"])
    environment["F017_SEQUENCE42_SOURCE_CTIME_NS"] = str(source_identity["ctime_ns"])
    environment["F017_SEQUENCE42_BARRIER_LOG"] = os.fspath(log)
    environment["F017_SEQUENCE42_BARRIER_LOG_DEVICE"] = str(log_identity[0])
    environment["F017_SEQUENCE42_BARRIER_LOG_INODE"] = str(log_identity[1])
    root_token = f"launcher-{os.getpid()}-{secrets.token_hex(16)}"
    environment["F017_SEQUENCE42_BARRIER_TOKEN"] = root_token
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        child = subprocess.run(command, env=environment, check=False)
        _final_roots, final_source_identity = _source_roots(source)
        if final_source_identity != source_identity:
            raise RuntimeError("Sequence 42 target source changed during run")
        events, _raw = _read_log(log, log_identity)
        summary = _validate_log(
            events,
            root_token=root_token,
            source_sha256=str(source_identity["sha256"]),
            child_returncode=child.returncode,
        )
        _append_summary(log, log_identity, summary)
    except BaseException as exc:
        print(f"Sequence 42 no-access supervision failed: {exc}", file=sys.stderr)
        return 97
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())

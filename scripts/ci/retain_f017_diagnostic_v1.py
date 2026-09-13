#!/usr/bin/env python3
"""Retain bounded, sanitized evidence for the Event 06 CI terminal step.

The qualification command owns the report format, but its report may contain
runner paths or command arguments.  This module keeps only typed diagnostic
fields and byte/hash metadata.  Raw command streams are never printed or
copied to the retained artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


REPORT_LIMIT = 64 * 1024
CAPTURE_LIMIT = 1024 * 1024
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,96}\Z")
_COMMAND_FIELDS = ("returncode", "stdout_bytes", "stdout_sha256", "stderr_bytes", "stderr_sha256")
_RESOLVED_VALUES = {
    "shallow_repository": {"true", "false"},
    "object_format": {"sha1", "sha256"},
    "cat_file_type": {"blob", "tree", "commit", "None"},
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _empty_observation() -> dict[str, Any]:
    return {"available": False, "bytes": None, "sha256": None}


def _file_observation(path: Path, *, limit: int) -> dict[str, Any]:
    """Return only size/hash metadata for a trusted temporary capture."""
    observation = _empty_observation()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode):
                return observation
            size = details.st_size
            observation["bytes"] = size
            if size > limit:
                return observation
            digest = hashlib.sha256()
            total_read = 0
            while total_read < limit:
                current = os.fstat(fd)
                if current.st_size > limit:
                    observation["bytes"] = current.st_size
                    return observation
                chunk = os.read(fd, min(8192, limit - total_read))
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > limit:
                    return observation
                digest.update(chunk)
            current = os.fstat(fd)
            if current.st_size > limit:
                observation["bytes"] = current.st_size
                return observation
            observation["available"] = True
            observation["sha256"] = digest.hexdigest()
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return observation
    return observation


def _report_bytes(path: Path) -> tuple[bytes | None, int | None, str | None]:
    """Read a report only when it is a bounded regular file."""
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode) or details.st_size > REPORT_LIMIT:
                return None, details.st_size, None
            raw = bytearray()
            while True:
                chunk = os.read(fd, 8192)
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > REPORT_LIMIT:
                    return None, len(raw), None
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None, None, None
    value = bytes(raw)
    return value, len(value), _sha256(value)


def _safe_command_observation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for field in _COMMAND_FIELDS:
        item = value.get(field)
        if field.endswith("_sha256"):
            if type(item) is str and _SHA256.fullmatch(item):
                result[field] = item
            else:
                return None
        elif type(item) is int and not isinstance(item, bool) and 0 <= item <= CAPTURE_LIMIT:
            result[field] = item
        else:
            return None
    return result


def _safe_report(value: Any) -> dict[str, Any] | None:
    """Project the producer envelope without paths, argv, or raw streams."""
    if not isinstance(value, dict):
        return None
    source = value.get("historical_preflight")
    if not isinstance(source, dict):
        source = value
    commands = source.get("commands")
    result = source.get("result")
    if not isinstance(commands, dict) or type(result) is not str or result not in {"PASS", "FAIL"}:
        return None

    safe: dict[str, Any] = {"result": result}
    revision = source.get("revision")
    if type(revision) is str and _SHA1.fullmatch(revision):
        safe["revision"] = revision
    for field in ("model_environment_empty", "required_checks_clean", "historical_blob_is_blob"):
        item = source.get(field)
        if type(item) is bool:
            safe[field] = item
    resolved = source.get("resolved")
    if isinstance(resolved, dict):
        safe_resolved: dict[str, str] = {}
        for field, allowed in _RESOLVED_VALUES.items():
            item = resolved.get(field)
            if type(item) is str and item in allowed:
                safe_resolved[field] = item
        if safe_resolved:
            safe["resolved"] = safe_resolved

    safe_commands: dict[str, dict[str, Any]] = {}
    for name, observation in commands.items():
        if type(name) is not str or _TOKEN.fullmatch(name) is None:
            continue
        sanitized = _safe_command_observation(observation)
        if sanitized is not None:
            safe_commands[name] = sanitized
    if not safe_commands:
        return None
    safe["commands"] = safe_commands
    return safe


def _safe_stage(stage: str) -> str:
    return stage if _TOKEN.fullmatch(stage) else "UNSAFE_STAGE"


def _write_exclusive_regular_file(path: Path, raw: bytes) -> None:
    """Create a private regular file without following a pre-existing name."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode):
            raise OSError("retention output is not a regular file")
        view = memoryview(raw)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("retention output short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def retain(
    report_path: Path,
    output_path: Path,
    stdout_capture: Path,
    stderr_capture: Path,
    command_exit_status: int,
    stage: str,
    summary_path: Path | None = None,
) -> tuple[dict[str, Any], int]:
    raw, report_bytes, report_sha256 = _report_bytes(report_path)
    parsed: Any = None
    if raw is not None:
        try:
            parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            parsed = None
    diagnostic = _safe_report(parsed)
    stdout = _file_observation(stdout_capture, limit=CAPTURE_LIMIT)
    stderr = _file_observation(stderr_capture, limit=CAPTURE_LIMIT)
    report_available = diagnostic is not None
    original_passed = command_exit_status == 0
    retained_passed = original_passed and report_available and diagnostic["result"] == "PASS"
    envelope: dict[str, Any] = {
        "schema": "pulsarmlx.f017.ci-diagnostic-retention/1.0.0",
        "stage": _safe_stage(stage),
        "status": "PASS" if retained_passed else "FAIL",
        "result": "PASS" if retained_passed else "FAIL",
        "command_exit_status": command_exit_status,
        "report_available": report_available,
        "fallback_used": not report_available,
        "fallback_reason": None if report_available else "REPORT_MISSING_OR_MALFORMED",
        "report_bytes": report_bytes,
        "report_sha256": report_sha256,
        "stdout_bytes": stdout["bytes"],
        "stdout_sha256": stdout["sha256"],
        "stderr_bytes": stderr["bytes"],
        "stderr_sha256": stderr["sha256"],
        "diagnostic": diagnostic,
    }
    serialized = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_exclusive_regular_file(output_path, serialized)
    if summary_path is not None:
        _write_exclusive_regular_file(summary_path, serialized)
    # A missing/malformed report must not convert a successful command into a
    # green step.  A prior nonzero command remains the original failure.
    return envelope, 0 if retained_passed or not original_passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stdout-capture", type=Path, required=True)
    parser.add_argument("--stderr-capture", type=Path, required=True)
    parser.add_argument("--command-exit-status", type=int, required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    try:
        envelope, status = retain(
            args.report,
            args.output,
            args.stdout_capture,
            args.stderr_capture,
            args.command_exit_status,
            args.stage,
            args.summary,
        )
    except (OSError, ValueError, TypeError):
        # Keep the log bounded and free of paths. The upload step will fail if
        # the caller-owned retained file could not be written.
        print(json.dumps({"schema": "pulsarmlx.f017.ci-diagnostic-retention/1.0.0", "status": "FAIL", "result": "FAIL", "retention_error": "OUTPUT_OR_INPUT_FAILURE"}, sort_keys=True))
        return 2
    print(json.dumps(envelope, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())

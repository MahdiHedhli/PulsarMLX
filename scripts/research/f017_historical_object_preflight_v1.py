#!/usr/bin/env python3
"""Fail-closed diagnostics for one exact historical repository blob.

This module is deliberately read-only.  It never resolves ``HEAD`` or reads the
working tree: every Git object query is bound to the caller-supplied full
revision and relative path.  The envelope records command metadata and safe
byte hashes, while raw stdout/stderr remain in the caller's normal evidence
capture.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Mapping


_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_DIAGNOSTIC_ENV = "PULSARMLX_F017_HISTORY_DIAGNOSTIC"
_HISTORICAL_GIT_DIR_ENV = "PULSARMLX_F017_HISTORY_GIT_DIR"
_HISTORICAL_GIT_COMMON_DIR_ENV = "PULSARMLX_F017_HISTORY_GIT_COMMON_DIR"
_HISTORICAL_GIT_WORK_TREE_ENV = "PULSARMLX_F017_HISTORY_GIT_WORK_TREE"
_HISTORICAL_GIT_CONTEXT_VARIABLES = frozenset({
    _HISTORICAL_GIT_DIR_ENV,
    _HISTORICAL_GIT_COMMON_DIR_ENV,
    _HISTORICAL_GIT_WORK_TREE_ENV,
})
_NATIVE_GIT_LOCATOR_VARIABLES = frozenset({
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
})


class HistoricalObjectLookupError(ValueError):
    """The exact historical blob could not be read without relaxing the guard."""


def _checkout_common_git_dir(root: Path) -> Path:
    """Resolve the checkout common directory without consulting Git config."""
    git_entry = root / ".git"
    try:
        if git_entry.is_dir():
            git_dir = git_entry.resolve(strict=True)
        else:
            line = git_entry.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir:"):
                raise ValueError("invalid checkout gitdir metadata")
            git_dir = (git_entry.parent / line.split(":", 1)[1].strip()).resolve(strict=True)
        commondir = git_dir / "commondir"
        if commondir.is_file():
            return (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve(strict=True)
        return git_dir
    except (OSError, UnicodeError, ValueError) as exc:
        raise HistoricalObjectLookupError("historical Git checkout context") from exc


def _context_path(environment: Mapping[str, str], name: str) -> Path:
    value = environment.get(name)
    if type(value) is not str or not value or not Path(value).is_absolute():
        raise HistoricalObjectLookupError("historical Git checkout context")
    try:
        return Path(value).resolve(strict=True)
    except OSError as exc:
        raise HistoricalObjectLookupError("historical Git checkout context") from exc


def _historical_git_context(
    root: Path, environment: Mapping[str, str]
) -> tuple[Path, Path, Path] | None:
    """Validate the complete private context, rejecting partial fallbacks."""
    present = _HISTORICAL_GIT_CONTEXT_VARIABLES.intersection(environment)
    if not present:
        return None
    if present != _HISTORICAL_GIT_CONTEXT_VARIABLES:
        raise HistoricalObjectLookupError("historical Git checkout context")

    try:
        resolved_root = root.resolve(strict=True)
        isolated_git = _context_path(environment, _HISTORICAL_GIT_DIR_ENV)
        common_git = _context_path(environment, _HISTORICAL_GIT_COMMON_DIR_ENV)
        work_tree = _context_path(environment, _HISTORICAL_GIT_WORK_TREE_ENV)
        tmpdir = _context_path(environment, "TMPDIR")
    except (OSError, RuntimeError) as exc:
        raise HistoricalObjectLookupError("historical Git checkout context") from exc

    if work_tree != resolved_root or isolated_git.parent != tmpdir:
        raise HistoricalObjectLookupError("historical Git checkout context")
    if not isolated_git.is_dir() or not (isolated_git / "config").is_file():
        raise HistoricalObjectLookupError("historical Git checkout context")
    if common_git != _checkout_common_git_dir(resolved_root):
        raise HistoricalObjectLookupError("historical Git checkout context")
    return isolated_git, common_git, work_tree


def _git_subprocess_environment(
    root: Path, environment: Mapping[str, str]
) -> dict[str, str]:
    """Apply historical locators only to this one Git subprocess."""
    child = dict(environment)
    for name in _NATIVE_GIT_LOCATOR_VARIABLES | _HISTORICAL_GIT_CONTEXT_VARIABLES:
        child.pop(name, None)
    context = _historical_git_context(root, environment)
    if context is not None:
        isolated_git, common_git, work_tree = context
        child.update({
            "GIT_DIR": str(isolated_git),
            "GIT_COMMON_DIR": str(common_git),
            "GIT_WORK_TREE": str(work_tree),
        })
    return child


def _validate_revision(revision: str) -> None:
    if type(revision) is not str or _SHA1.fullmatch(revision) is None:
        raise ValueError("historical repository revision")


def _validate_path(relative_path: str) -> None:
    if (
        type(relative_path) is not str
        or relative_path.startswith("/")
        or "\\" in relative_path
        or any(part in {"", ".", ".."} for part in Path(relative_path).parts)
    ):
        raise ValueError("historical repository path")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _observation(argv: list[str], completed: subprocess.CompletedProcess[bytes]) -> dict[str, object]:
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout_bytes": len(completed.stdout),
        "stdout_sha256": _hash(completed.stdout),
        "stderr_bytes": len(completed.stderr),
        "stderr_sha256": _hash(completed.stderr),
    }


def _run(
    argv: list[str], *, root: Path, environment: Mapping[str, str]
) -> tuple[dict[str, object], bytes, bytes]:
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            env=dict(environment),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        # Keep the envelope useful when the selected executable/helper cannot
        # be launched.  Do not copy the exception text into retained reports.
        stderr = str(type(exc).__name__).encode("ascii", "replace")
        completed = subprocess.CompletedProcess(argv, 127, b"", stderr)
    return _observation(argv, completed), completed.stdout, completed.stderr


def _git_command(
    arguments: list[str], *, root: Path, environment: Mapping[str, str]
) -> tuple[dict[str, object], bytes, bytes]:
    return _run(
        ["git", *arguments],
        root=root,
        environment=_git_subprocess_environment(root, environment),
    )


def _visibility(path: str | None) -> dict[str, object]:
    if not path:
        return {"path": None, "exists": False, "directory": False, "readable": False}
    candidate = Path(path)
    return {
        "path": path,
        "exists": candidate.exists(),
        "directory": candidate.is_dir(),
        "readable": os.access(candidate, os.R_OK),
    }


def _selected_git(environment: Mapping[str, str]) -> dict[str, object]:
    # subprocess uses os.defpath when PATH is absent.  shutil.which defaults
    # to the parent process environment instead, so pass the same fallback.
    search_path = environment.get("PATH", os.defpath)
    selected = shutil.which("git", path=search_path)
    return {
        "which": selected,
        "exec_path": os.get_exec_path(dict(environment)),
        "selected_visibility": _visibility(selected),
    }


def _decode_line(stdout: bytes, completed: dict[str, object]) -> str | None:
    if completed["returncode"] != 0 or completed["stderr_bytes"] != 0:
        return None
    return stdout.decode("utf-8", "replace").strip() or None


def _successful_exact_object_checks(
    root: Path,
    revision: str,
    object_name: str,
    *,
    environment: Mapping[str, str],
) -> bool:
    revision_check, revision_out, _ = _git_command(
        ["rev-parse", "--verify", f"{revision}^{{commit}}"],
        root=root,
        environment=environment,
    )
    path_type, path_type_out, _ = _git_command(
        ["cat-file", "-t", object_name],
        root=root,
        environment=environment,
    )
    return (
        _decode_line(revision_out, revision_check) == revision
        and _decode_line(path_type_out, path_type) == "blob"
    )


def preflight_historical_object(
    root: Path,
    revision: str,
    relative_path: str,
    *,
    environment: Mapping[str, str] | None = None,
    initial_show: tuple[dict[str, object], bytes, bytes] | None = None,
) -> dict[str, object]:
    """Collect a bounded, same-environment read-only historical-object probe."""
    _validate_revision(revision)
    _validate_path(relative_path)
    root = root.resolve(strict=True)
    env = dict(os.environ if environment is None else environment)
    object_name = f"{revision}:{relative_path}"
    commands: dict[str, dict[str, object]] = {}
    outputs: dict[str, bytes] = {}

    version, version_out, _ = _git_command(["--version"], root=root, environment=env)
    commands["git_version"] = version
    outputs["git_version"] = version_out

    for name, arguments in (
        ("git_dir", ["rev-parse", "--path-format=absolute", "--git-dir"]),
        ("git_common_dir", ["rev-parse", "--path-format=absolute", "--git-common-dir"]),
        ("git_object_path", ["rev-parse", "--path-format=absolute", "--git-path", "objects"]),
        ("shallow_repository", ["rev-parse", "--is-shallow-repository"]),
        ("object_format", ["rev-parse", "--show-object-format"]),
        ("promisor_remote", ["config", "--get", "remote.origin.promisor"]),
        ("partial_clone_filter", ["config", "--get", "remote.origin.partialclonefilter"]),
    ):
        observation, stdout, _ = _git_command(arguments, root=root, environment=env)
        commands[name] = observation
        outputs[name] = stdout

    revision_check, revision_out, _ = _git_command(
        ["rev-parse", "--verify", f"{revision}^{{commit}}"],
        root=root,
        environment=env,
    )
    commands["revision_check"] = revision_check
    outputs["revision_check"] = revision_out

    path_check, path_out, _ = _git_command(
        ["rev-parse", "--verify", object_name], root=root, environment=env
    )
    commands["path_check"] = path_check
    outputs["path_check"] = path_out

    cat_type, cat_type_out, _ = _git_command(
        ["cat-file", "-t", object_name], root=root, environment=env
    )
    commands["cat_file_type"] = cat_type
    outputs["cat_file_type"] = cat_type_out

    cat_exists, cat_exists_out, _ = _git_command(
        ["cat-file", "-e", object_name], root=root, environment=env
    )
    commands["cat_file_exists"] = cat_exists
    outputs["cat_file_exists"] = cat_exists_out

    if initial_show is None:
        show, show_out, show_err = _git_command(
            ["show", object_name], root=root, environment=env
        )
    else:
        show, show_out, show_err = initial_show
    commands["show"] = show
    outputs["show"] = show_out

    # xcode-select and git --exec-path are intentionally best-effort metadata;
    # Git's strict object checks below determine the preflight result.
    xcode_select, xcode_out, _ = _run(
        ["/usr/bin/xcode-select", "-p"], root=root, environment=env
    )
    commands["xcode_select"] = xcode_select
    outputs["xcode_select"] = xcode_out
    developer_dir = _decode_line(xcode_out, xcode_select)

    git_exec, git_exec_out, _ = _git_command(["--exec-path"], root=root, environment=env)
    commands["git_exec_path"] = git_exec
    outputs["git_exec_path"] = git_exec_out
    git_exec_path = _decode_line(git_exec_out, git_exec)

    required = (
        "git_version",
        "git_dir",
        "git_common_dir",
        "git_object_path",
        "shallow_repository",
        "object_format",
        "revision_check",
        "path_check",
        "cat_file_type",
        "cat_file_exists",
        "show",
    )
    required_clean = all(
        commands[name]["returncode"] == 0 and commands[name]["stderr_bytes"] == 0
        for name in required
    )
    type_is_blob = _decode_line(outputs["cat_file_type"], commands["cat_file_type"]) == "blob"
    model_environment_empty = env.get("PULSARMLX_MODEL_GGUF") == ""
    result = "PASS" if required_clean and type_is_blob and model_environment_empty else "FAIL"
    return {
        "schema": "pulsarmlx.f017.historical-object-preflight/1.0.0",
        "root": str(root),
        "revision": revision,
        "relative_path": relative_path,
        "object_name": object_name,
        "model_environment_empty": model_environment_empty,
        "git_selection": _selected_git(env),
        "developer_tool_selection": {
            "developer_dir": _visibility(developer_dir),
            "git_exec_path": _visibility(git_exec_path),
        },
        "resolved": {
            "git_dir": _decode_line(outputs["git_dir"], commands["git_dir"]),
            "git_common_dir": _decode_line(
                outputs["git_common_dir"], commands["git_common_dir"]
            ),
            "git_object_path": _decode_line(
                outputs["git_object_path"], commands["git_object_path"]
            ),
            "shallow_repository": _decode_line(
                outputs["shallow_repository"], commands["shallow_repository"]
            ),
            "object_format": _decode_line(outputs["object_format"], commands["object_format"]),
            "cat_file_type": _decode_line(outputs["cat_file_type"], commands["cat_file_type"]),
        },
        "commands": commands,
        "required_checks_clean": required_clean,
        "historical_blob_is_blob": type_is_blob,
        "result": result,
    }


def write_diagnostic(path: Path | str | None, envelope: dict[str, object]) -> None:
    """Write only the structured safe envelope when the caller requested it."""
    if path is None:
        return
    destination = Path(path)
    if not destination.is_absolute() or not destination.parent.is_dir():
        return
    destination.write_text(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def read_historical_blob(
    root: Path,
    revision: str,
    relative_path: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> bytes:
    """Read exactly ``revision:path`` and fail closed on any Git stderr."""
    _validate_revision(revision)
    _validate_path(relative_path)
    env = dict(os.environ if environment is None else environment)
    object_name = f"{revision}:{relative_path}"
    root = root.resolve(strict=True)
    observation, stdout, stderr = _git_command(
        ["show", object_name], root=root, environment=env
    )
    if (
        observation["returncode"] != 0
        or stderr
        or not _successful_exact_object_checks(
            root,
            revision,
            object_name,
            environment=env,
        )
    ):
        envelope = preflight_historical_object(
            root,
            revision,
            relative_path,
            environment=env,
            initial_show=(observation, stdout, stderr),
        )
        write_diagnostic(env.get(_DIAGNOSTIC_ENV), envelope)
        raise HistoricalObjectLookupError(f"historical repository blob: {relative_path}")
    return stdout


__all__ = [
    "HistoricalObjectLookupError",
    "preflight_historical_object",
    "read_historical_blob",
    "write_diagnostic",
]

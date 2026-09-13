#!/usr/bin/env python3
"""Independent macOS sandbox and out-of-process monitor for Sequence 18."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from f017_event06_storage_authority_v1 import (
    FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256,
    fixed_live_registry_root,
)


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_DAG_COMMIT = "9bfe3c0af88d774df15d595389f7f2778cea7806"
HISTORICAL_BLOB_PATH = "scripts/research/f017_event06_readiness_authority_v3.py"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_FAILURE_ENVELOPE_BYTES = 16 * 1024
MAX_PREFLIGHT_DIAGNOSTIC_BYTES = 64 * 1024
_PREFLIGHT_SCHEMA = "pulsarmlx.f017.historical-object-preflight/1.0.0"
_PREFLIGHT_COMMANDS = (
    "git_version",
    "git_dir",
    "git_common_dir",
    "git_object_path",
    "shallow_repository",
    "object_format",
    "promisor_remote",
    "partial_clone_filter",
    "revision_check",
    "path_check",
    "cat_file_type",
    "cat_file_exists",
    "show",
    "xcode_select",
    "git_exec_path",
)
_HISTORICAL_GIT_LOCATOR_VARIABLES = frozenset({
    "GIT_DIR",
    "GIT_COMMON_DIR",
    "GIT_WORK_TREE",
})
_HISTORICAL_GIT_CONTEXT_VARIABLES = frozenset({
    "PULSARMLX_F017_HISTORY_GIT_DIR",
    "PULSARMLX_F017_HISTORY_GIT_COMMON_DIR",
    "PULSARMLX_F017_HISTORY_GIT_WORK_TREE",
})
_HISTORICAL_GIT_VARIABLES = _HISTORICAL_GIT_LOCATOR_VARIABLES | frozenset({
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
}) | _HISTORICAL_GIT_CONTEXT_VARIABLES

HISTORICAL_PREFLIGHT = r'''
import json
import os
from pathlib import Path

from f017_historical_object_preflight_v1 import (
    preflight_historical_object,
    write_diagnostic,
)

root = Path(os.environ["PULSARMLX_F017_HISTORY_ROOT"])
destination = Path(os.environ["PULSARMLX_F017_HISTORY_DIAGNOSTIC"])
result = preflight_historical_object(
    root,
    os.environ["PULSARMLX_F017_HISTORY_COMMIT"],
    os.environ["PULSARMLX_F017_HISTORY_PATH"],
    environment=os.environ,
)
write_diagnostic(destination, result)
print(json.dumps({"result": result["result"]}, sort_keys=True))
raise SystemExit(0 if result["result"] == "PASS" else 1)
'''


def _allow(operation: str, kind: str, path: Path | str) -> str:
    escaped = str(path).replace('"', '\\"')
    return f'(allow {operation} ({kind} "{escaped}"))'


def _git_common_dir(repository: Path) -> Path:
    """Resolve Git's common directory from checkout metadata, not config."""
    git_entry = repository / ".git"
    if git_entry.is_dir():
        git_dir = git_entry.resolve(strict=True)
    else:
        line = git_entry.read_text(encoding="utf-8").strip()
        if not line.startswith("gitdir:"):
            raise RuntimeError("invalid checkout gitdir metadata")
        git_dir = (git_entry.parent / line.split(":", 1)[1].strip()).resolve(strict=True)
    commondir = git_dir / "commondir"
    if commondir.is_file():
        return (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve(strict=True)
    return git_dir


def _prepare_historical_git_context(repository: Path, graph_root: Path) -> tuple[Path, Path]:
    """Create a config-free Git dir that shares the checkout's object store."""
    common_git = _git_common_dir(repository)
    isolated_git = graph_root / "historical-gitdir"
    setup_environment = {
        name: value
        for name, value in os.environ.items()
        if name not in _HISTORICAL_GIT_VARIABLES
    }
    setup_environment.update({"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"})
    subprocess.run(
        ["git", "init", "--quiet", "--bare", str(isolated_git)],
        check=True,
        cwd=graph_root,
        env=setup_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        ["git", "config", "--file", str(isolated_git / "config"), "core.bare", "false"],
        check=True,
        env=setup_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return isolated_git, common_git


def _historical_git_context_environment(
    base_environment: dict[str, str],
    *,
    isolated_git: Path,
    common_git: Path,
    work_tree: Path,
) -> dict[str, str]:
    """Transport historical Git context without native child locators."""
    environment = {
        name: value
        for name, value in base_environment.items()
        if name not in _HISTORICAL_GIT_VARIABLES
    }
    environment.update({
        "PULSARMLX_F017_HISTORY_GIT_DIR": str(isolated_git),
        "PULSARMLX_F017_HISTORY_GIT_COMMON_DIR": str(common_git),
        "PULSARMLX_F017_HISTORY_GIT_WORK_TREE": str(work_tree),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return environment


def _profile(graph_root: Path) -> tuple[str, list[str]]:
    common_git = _git_common_dir(ROOT)
    python_runtime = Path(sys.base_prefix)
    rules = [
        "(version 1)", "(deny default)", "(allow process*)", "(allow sysctl-read)",
        "(allow mach-lookup)", "(allow network*)", "(allow ipc-posix-shm)",
        "(allow ipc-posix-sem)", _allow("file-read*", "literal", "/"),
        _allow("file-read*", "literal", "/var"),
        _allow("file-read*", "subpath", "/var/select"),
        _allow("file-read*", "subpath", "/var/folders"),
        _allow("file-read*", "literal", "/private"),
        _allow("file-read*", "literal", "/private/tmp"),
        _allow("file-read*", "subpath", ROOT),
        _allow("file-read*", "subpath", graph_root),
        _allow("file-read*", "subpath", "/private/var/db"),
        _allow("file-read*", "subpath", "/private/var/select"),
        _allow("file-read*", "subpath", "/private/var/folders"),
        _allow("file-read*", "subpath", "/private/etc"),
        _allow("file-read*", "subpath", "/etc"),
        _allow("file-read*", "subpath", "/System"),
        _allow("file-read*", "subpath", "/usr"),
        _allow("file-read*", "subpath", "/bin"),
        _allow("file-read*", "subpath", "/sbin"),
        _allow("file-read*", "subpath", "/Library"),
        _allow("file-read*", "subpath", "/Applications/Xcode.app"),
        _allow("file-read*", "subpath", "/opt/homebrew"),
        _allow("file-read*", "subpath", python_runtime),
        _allow("file-read*", "subpath", common_git),
        _allow("file-read*", "literal", Path.home() / ".gitconfig"),
        _allow("file-read*", "subpath", "/dev"),
        _allow("file-write*", "literal", "/dev/null"),
        _allow("file-write*", "subpath", graph_root),
        _allow("file-write*", "subpath", "/var/folders"),
        _allow("file-write*", "subpath", "/private/var/folders"),
        f'(deny file* (subpath "{fixed_live_registry_root()}"))',
    ]
    # Permit traversal metadata for the exact common-git ancestry without
    # widening file contents beneath the user's home directory.
    ancestors = set()
    for leaf in (Path(common_git), python_runtime, ROOT, graph_root):
        cursor = leaf
        while cursor != Path("/"):
            ancestors.add(cursor)
            cursor = cursor.parent
    for ancestor in sorted(ancestors, key=lambda item: (len(item.parts), item.as_posix())):
        if ancestor not in {Path(common_git), Path.home() / ".gitconfig"}:
            rules.insert(-1, _allow("file-read*", "literal", ancestor))
    return "".join(rules), [f"SBPL-{index:03d}" for index in range(len(rules))]


def _stream_bytes(value: object) -> bytes:
    return value if isinstance(value, bytes) else b""


def _stream_metadata(value: object) -> tuple[int, str]:
    raw = _stream_bytes(value)
    return len(raw), hashlib.sha256(raw).hexdigest()


def _safe_int(value: object, *, lower: int = 0) -> int | None:
    if type(value) is not int or value < lower or value > (2**63 - 1):
        return None
    return value


def _safe_hash(value: object, pattern: re.Pattern[str]) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _project_command_observation(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    returncode = value.get("returncode")
    if type(returncode) is not int or returncode < -255 or returncode > 255:
        return None
    stdout_bytes = _safe_int(value.get("stdout_bytes"))
    stderr_bytes = _safe_int(value.get("stderr_bytes"))
    stdout_sha256 = _safe_hash(value.get("stdout_sha256"), _SHA256)
    stderr_sha256 = _safe_hash(value.get("stderr_sha256"), _SHA256)
    if None in (stdout_bytes, stderr_bytes, stdout_sha256, stderr_sha256):
        return None
    return {
        "returncode": returncode,
        "stdout_bytes": stdout_bytes,
        "stdout_sha256": stdout_sha256,
        "stderr_bytes": stderr_bytes,
        "stderr_sha256": stderr_sha256,
    }


def _project_preflight_diagnostic(candidate: object) -> dict[str, object] | None:
    """Project only typed, path-free fields from the child diagnostic."""
    if not isinstance(candidate, dict) or candidate.get("schema") != _PREFLIGHT_SCHEMA:
        return None
    result = candidate.get("result")
    revision = _safe_hash(candidate.get("revision"), _SHA1)
    target = candidate.get("relative_path")
    commands = candidate.get("commands")
    if (
        result not in {"PASS", "FAIL"}
        or revision is None
        or not isinstance(target, str)
        or not target
        or target.startswith("/")
        or "\\" in target
        or any(part in {"", ".", ".."} for part in target.split("/"))
        or not isinstance(commands, dict)
    ):
        return None
    if not all(type(candidate.get(name)) is bool for name in (
        "model_environment_empty", "required_checks_clean", "historical_blob_is_blob"
    )):
        return None
    projected_commands: dict[str, dict[str, object]] = {}
    for name in _PREFLIGHT_COMMANDS:
        if name in commands:
            observation = _project_command_observation(commands[name])
            if observation is None:
                return None
            projected_commands[name] = observation
    if "show" not in projected_commands:
        return None
    try:
        target_sha256 = hashlib.sha256(target.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:
        return None
    return {
        "schema": _PREFLIGHT_SCHEMA,
        "result": result,
        "revision": revision,
        "target_sha256": target_sha256,
        "model_environment_empty": candidate["model_environment_empty"],
        "required_checks_clean": candidate["required_checks_clean"],
        "historical_blob_is_blob": candidate["historical_blob_is_blob"],
        "commands": projected_commands,
        "failed_command_names": [
            name for name, observation in projected_commands.items()
            if observation["returncode"] != 0 or observation["stderr_bytes"] != 0
        ],
    }


def _load_preflight_diagnostic(
    diagnostic_path: Path,
) -> tuple[str, dict[str, object] | None]:
    """Read a bounded diagnostic and never retain its raw or path-bearing fields."""
    try:
        if diagnostic_path.is_symlink() or not diagnostic_path.is_file():
            return "MISSING", None
        with diagnostic_path.open("rb") as handle:
            raw = handle.read(MAX_PREFLIGHT_DIAGNOSTIC_BYTES + 1)
    except OSError:
        return "MISSING", None
    if len(raw) > MAX_PREFLIGHT_DIAGNOSTIC_BYTES:
        return "OVERSIZE", None
    try:
        candidate = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return "MALFORMED", None
    projected = _project_preflight_diagnostic(candidate)
    return ("VALID", projected) if projected is not None else ("MALFORMED", None)


def _write_preflight_failure(
    output: Path | str | None,
    preflight: subprocess.CompletedProcess[bytes],
    diagnostic_path: Path,
) -> None:
    """Emit one bounded safe log line before the temporary root is removed."""
    stdout_bytes, stdout_sha256 = _stream_metadata(preflight.stdout)
    stderr_bytes, stderr_sha256 = _stream_metadata(preflight.stderr)
    diagnostic_status, diagnostic = _load_preflight_diagnostic(diagnostic_path)
    if diagnostic is not None and diagnostic["result"] != "FAIL":
        diagnostic_status, diagnostic = "MALFORMED", None
    envelope = {
        "schema": "pulsarmlx.f017.event06-v12-sequence18-independent-sandbox-failure/1.0.0",
        "mechanism": "MACOS_SANDBOX_EXEC_DEFAULT_DENY_PLUS_OUT_OF_PROCESS_MONITOR",
        "status": "FAIL",
        "result": "FAIL",
        "failure_stage": "HISTORICAL_PREFLIGHT",
        "historical_preflight_exit_status": preflight.returncode,
        "historical_preflight_stdout_bytes": stdout_bytes,
        "historical_preflight_stdout_sha256": stdout_sha256,
        "historical_preflight_stderr_bytes": stderr_bytes,
        "historical_preflight_stderr_sha256": stderr_sha256,
        "historical_preflight_diagnostic_status": diagnostic_status,
        "historical_preflight_diagnostic_available": diagnostic is not None,
        "historical_preflight": diagnostic,
    }
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_FAILURE_ENVELOPE_BYTES:
        envelope["historical_preflight_diagnostic_status"] = "OVERSIZE"
        envelope["historical_preflight_diagnostic_available"] = False
        envelope["historical_preflight"] = None
        serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    try:
        sys.stderr.write(serialized + "\n")
        sys.stderr.flush()
    except OSError:
        pass
    if output is not None:
        Path(output).write_text(serialized + "\n", encoding="utf-8")


def run(output: Path | str | None = None) -> dict[str, object]:
    if not Path("/usr/bin/sandbox-exec").is_file():
        raise RuntimeError("NO_ACCESS_ASSURANCE_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="f017-seq18-sandbox-", dir="/private/tmp") as raw:
        graph_root = Path(raw)
        profile, rule_ids = _profile(graph_root)
        isolated_git, common_git = _prepare_historical_git_context(ROOT, graph_root)
        diagnostic_path = graph_root / "historical-object-diagnostic.json"
        fixed = fixed_live_registry_root()
        pre_exists = os.path.lexists(fixed)
        probe = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", profile, "/bin/mkdir", str(fixed)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        post_probe_exists = os.path.lexists(fixed)
        if probe.returncode == 0 or post_probe_exists:
            raise RuntimeError("independent fixed-root denial probe failed")
        environment = {
            "TMPDIR": str(graph_root),
            "PYTHONPATH": os.pathsep.join((
                str(ROOT / "scripts/research"),
                str(ROOT / ".venv/lib/python3.13/site-packages"),
            )),
            "PULSARMLX_MODEL_GGUF": "",
            "PULSARMLX_F017_HISTORY_ROOT": str(ROOT),
            "PULSARMLX_F017_HISTORY_COMMIT": HISTORICAL_DAG_COMMIT,
            "PULSARMLX_F017_HISTORY_PATH": HISTORICAL_BLOB_PATH,
            "PULSARMLX_F017_HISTORY_DIAGNOSTIC": str(diagnostic_path),
            # Keep Git config isolation for every sandboxed command.  Private
            # context values are translated to native locators per Git read.
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        environment = _historical_git_context_environment(
            environment,
            isolated_git=isolated_git,
            common_git=common_git,
            work_tree=ROOT,
        )
        preflight = subprocess.run(
            [
                "/usr/bin/sandbox-exec", "-p", profile, str(Path(sys.executable).resolve()),
                "-c", HISTORICAL_PREFLIGHT,
            ],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if preflight.returncode != 0:
            _write_preflight_failure(output, preflight, diagnostic_path)
            raise RuntimeError(
                "historical object preflight failed "
                f"exit {preflight.returncode}, "
                f"stdout_bytes={len(preflight.stdout)}, "
                f"stdout_sha256={hashlib.sha256(preflight.stdout).hexdigest()}, "
                f"stderr_bytes={len(preflight.stderr)}, "
                f"stderr_sha256={hashlib.sha256(preflight.stderr).hexdigest()}"
            )
        output = graph_root / "qualification.json"
        stderr_path = graph_root / "child.stderr"
        with stderr_path.open("wb") as stderr:
            child = subprocess.Popen(
                [
                    "/usr/bin/sandbox-exec", "-p", profile, str(Path(sys.executable).resolve()),
                    str(ROOT / "scripts/research/qualify_f017_event06_sequence18_amendment_v1.py"),
                    "--output", str(output),
                ],
                cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=stderr,
            )
            observed_pids: set[int] = set()
            maximum_fd_count = 0
            fixed_root_fd_mentions = 0
            checkpoint_filename_mentions = 0
            while child.poll() is None:
                processes = subprocess.run(
                    ["ps", "-axo", "pid=,ppid=,comm="], text=True,
                    stdout=subprocess.PIPE, check=True,
                ).stdout.splitlines()
                frontier = {child.pid}
                changed = True
                while changed:
                    changed = False
                    for row in processes:
                        parts = row.strip().split(None, 2)
                        if len(parts) >= 2 and int(parts[1]) in frontier and int(parts[0]) not in frontier:
                            frontier.add(int(parts[0])); changed = True
                observed_pids.update(frontier)
                for pid in frontier:
                    listing = subprocess.run(
                        ["/usr/sbin/lsof", "-n", "-P", "-p", str(pid)],
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    ).stdout
                    lines = listing.splitlines()[1:]
                    maximum_fd_count = max(maximum_fd_count, len(lines))
                    fixed_root_fd_mentions += str(fixed) in listing
                    checkpoint_filename_mentions += ".gguf" in listing.lower()
                time.sleep(0.02)
            exit_status = child.wait()
        diagnostic_raw = diagnostic_path.read_bytes() if diagnostic_path.is_file() else b""
        if exit_status != 0:
            diagnostic = stderr_path.read_text(encoding="utf-8", errors="replace")[-1000:]
            raise RuntimeError(
                f"sandboxed qualification child exit {exit_status}: {diagnostic}"
                f" historical_preflight_bytes={len(diagnostic_raw)}"
                f" historical_preflight_sha256={hashlib.sha256(diagnostic_raw).hexdigest()}"
            )
        qualification = json.loads(output.read_text(encoding="utf-8"))
        post_exists = os.path.lexists(fixed)
        stderr_raw = stderr_path.read_bytes()
        return {
            "schema": "pulsarmlx.f017.event06-v12-sequence18-independent-sandbox/1.0.0",
            "mechanism": "MACOS_SANDBOX_EXEC_DEFAULT_DENY_PLUS_OUT_OF_PROCESS_MONITOR",
            "profile_sha256": hashlib.sha256(profile.encode()).hexdigest(),
            "profile_rule_ids": rule_ids,
            "profile_rule_count": len(rule_ids),
            "denial_probe_exit_status": probe.returncode,
            "denial_probe_stderr_sha256": hashlib.sha256(probe.stderr).hexdigest(),
            "denial_probe_fixed_root_created": post_probe_exists,
            "historical_preflight_exit_status": preflight.returncode,
            "historical_preflight_stdout_bytes": len(preflight.stdout),
            "historical_preflight_stdout_sha256": hashlib.sha256(preflight.stdout).hexdigest(),
            "historical_preflight_stderr_bytes": len(preflight.stderr),
            "historical_preflight_stderr_sha256": hashlib.sha256(preflight.stderr).hexdigest(),
            "historical_preflight_bytes": len(diagnostic_raw),
            "historical_preflight_sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
            "historical_preflight": json.loads(diagnostic_raw.decode("utf-8")),
            "child_exit_status": exit_status,
            "child_identity": "GRAPH_OWNED_SANDBOXED_QUALIFICATION",
            "observed_process_count": len(observed_pids),
            "maximum_observed_fd_count": maximum_fd_count,
            "fixed_root_fd_mentions": fixed_root_fd_mentions,
            "checkpoint_filename_fd_mentions": checkpoint_filename_mentions,
            "child_stderr_sha256": hashlib.sha256(stderr_raw).hexdigest(),
            "child_stderr_bytes": len(stderr_raw),
            "fixed_root_pre_exists": pre_exists,
            "fixed_root_post_exists": post_exists,
            "fixed_live_registry_root_canonical_utf8_sha256": FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256,
            "qualification_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "qualification_result": qualification["result"],
            "production_live_registry_creates_or_writes": 0,
            "original_checkpoint_access": "NONE",
            "event06_executed": False,
            "result": "PASS" if (
                not pre_exists and not post_probe_exists and not post_exists
                and probe.returncode != 0 and exit_status == 0
                and fixed_root_fd_mentions == 0 and checkpoint_filename_mentions == 0
                and qualification["result"] == "PASS"
            ) else "FAIL",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(run(output=args.output), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

#!/usr/bin/env python3
"""Independent macOS sandbox and out-of-process monitor for Sequence 18."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def _allow(operation: str, kind: str, path: Path | str) -> str:
    escaped = str(path).replace('"', '\\"')
    return f'(allow {operation} ({kind} "{escaped}"))'


def _profile(graph_root: Path) -> tuple[str, list[str]]:
    common_git = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
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
    for leaf in (Path(common_git), python_runtime, ROOT):
        cursor = leaf
        while cursor != Path("/"):
            ancestors.add(cursor)
            cursor = cursor.parent
    for ancestor in sorted(ancestors, key=lambda item: (len(item.parts), item.as_posix())):
        if ancestor not in {Path(common_git), Path.home() / ".gitconfig"}:
            rules.insert(-1, _allow("file-read*", "literal", ancestor))
    return "".join(rules), [f"SBPL-{index:03d}" for index in range(len(rules))]


def run() -> dict[str, object]:
    if not Path("/usr/bin/sandbox-exec").is_file():
        raise RuntimeError("NO_ACCESS_ASSURANCE_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="f017-seq18-sandbox-", dir="/private/tmp") as raw:
        graph_root = Path(raw)
        profile, rule_ids = _profile(graph_root)
        fixed = fixed_live_registry_root()
        pre_exists = os.path.lexists(fixed)
        probe = subprocess.run(
            ["/usr/bin/sandbox-exec", "-p", profile, "/bin/mkdir", str(fixed)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        post_probe_exists = os.path.lexists(fixed)
        if probe.returncode == 0 or post_probe_exists:
            raise RuntimeError("independent fixed-root denial probe failed")
        output = graph_root / "qualification.json"
        stderr_path = graph_root / "child.stderr"
        environment = {
            "TMPDIR": str(graph_root),
            "PYTHONPATH": os.pathsep.join((
                str(ROOT / "scripts/research"),
                str(ROOT / ".venv/lib/python3.13/site-packages"),
            )),
        }
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
        if exit_status != 0:
            diagnostic = stderr_path.read_text(encoding="utf-8", errors="replace")[-1000:]
            raise RuntimeError(
                f"sandboxed qualification child exit {exit_status}: {diagnostic}"
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
    args.output.write_text(json.dumps(run(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

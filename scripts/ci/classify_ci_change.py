#!/usr/bin/env python3
"""Fail-closed CI routing from an exact Git diff.

The classifier has no network or third-party Python dependencies.  Unknown,
executable documentation, contract, fixture, build, and workflow changes route
to native CI. Evidence mixed with docs stays on the strict integrity path.
The closed historical F017 branch refuses automatic source
qualification and requires an explicit manual full dispatch.
Documentation, evidence and their mixture remain cheap integrity surfaces there.
Noncanonical/control-character/backslash paths fail closed, not NO_CHANGES.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Iterable, Sequence


FULL_NATIVE = "FULL_NATIVE"
EVIDENCE_ONLY = "EVIDENCE_ONLY"
DOCS_ONLY = "DOCS_ONLY"
CLOSED_BRANCH_GUARD = "CLOSED_BRANCH_GUARD"
NO_CHANGES = "NO_CHANGES"
UNKNOWN_DEFAULT_FULL = "UNKNOWN_DEFAULT_FULL"

VALID_MODES = {
    FULL_NATIVE,
    EVIDENCE_ONLY,
    DOCS_ONLY,
    CLOSED_BRANCH_GUARD,
    NO_CHANGES,
    UNKNOWN_DEFAULT_FULL,
}

CLOSED_BRANCH = "feat/017-real-checkpoint-runner"
EVIDENCE_PREFIX = "docs/architecture/reviews/evidence/"
FULL_PREFIXES = (
    ".github/workflows/",
    "crates/",
    "python/",
    "scripts/ci/",
    "scripts/research/",
    "schemas/",
    "fixtures/",
    "specs/",
)
FULL_EXACT = {
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "uv.lock",
    "build.rs",
}
TOP_LEVEL_DOCS = {
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "LICENSE",
    "LICENSE.md",
}
DOC_SUFFIXES = {".md", ".txt", ".rst", ".png", ".jpg", ".jpeg", ".svg"}


class ClassificationError(RuntimeError):
    """The requested routing mode is unsafe or malformed."""


def _safe_path(raw: str) -> str:
    path = PurePosixPath(raw)
    if (path.is_absolute() or not raw or path.as_posix() != raw
            or ".." in path.parts or "\\" in raw
            or any(ord(c) < 32 or ord(c) == 127 for c in raw)):
        raise ClassificationError(f"unsafe changed path: {raw!r}")
    return path.as_posix()


def path_class(path: str) -> str:
    """Classify one repository-relative path."""

    path = _safe_path(path)
    if path.startswith(EVIDENCE_PREFIX):
        return EVIDENCE_ONLY
    if path in FULL_EXACT or path.endswith("/build.rs"):
        return FULL_NATIVE
    if path.startswith(FULL_PREFIXES):
        return FULL_NATIVE
    if path in TOP_LEVEL_DOCS:
        return DOCS_ONLY
    suffix = PurePosixPath(path).suffix.lower()
    if path.startswith("docs/") and suffix in DOC_SUFFIXES:
        return DOCS_ONLY
    return UNKNOWN_DEFAULT_FULL


def classify_paths(
    paths: Sequence[str],
    *,
    branch: str,
    requested_mode: str = "auto",
) -> tuple[str, list[dict[str, str]]]:
    """Return the fail-closed mode and a per-path explanation."""

    requested_mode = requested_mode.lower()
    if requested_mode not in {"auto", "full", "evidence"}:
        raise ClassificationError(f"unknown requested mode: {requested_mode}")
    rows = [{"path": _safe_path(path), "class": path_class(path)} for path in paths]
    if requested_mode == "full":
        return FULL_NATIVE, rows
    if not rows:
        if requested_mode == "evidence":
            raise ClassificationError("manual evidence mode requires an evidence diff")
        return NO_CHANGES, rows

    classes = {row["class"] for row in rows}
    if FULL_NATIVE in classes:
        automatic = FULL_NATIVE
    elif UNKNOWN_DEFAULT_FULL in classes:
        automatic = UNKNOWN_DEFAULT_FULL
    elif EVIDENCE_ONLY in classes and classes <= {EVIDENCE_ONLY, DOCS_ONLY}:
        automatic = EVIDENCE_ONLY
    elif classes == {DOCS_ONLY}:
        automatic = DOCS_ONLY
    else:
        automatic = FULL_NATIVE

    if requested_mode == "evidence":
        if automatic != EVIDENCE_ONLY:
            raise ClassificationError(
                f"manual evidence mode cannot override {automatic} classification"
            )
        return EVIDENCE_ONLY, rows

    if branch == CLOSED_BRANCH and automatic in {FULL_NATIVE, UNKNOWN_DEFAULT_FULL}:
        return CLOSED_BRANCH_GUARD, rows
    return automatic, rows


def _git(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def changed_entries(repository: Path, base: str, head: str) -> list[dict]:
    """Read the complete committed diff with NUL paths and both file modes."""
    for ref in (base, head):
        if not ref or ref.startswith("-") or set(ref) == {"0"}:
            raise ClassificationError("missing or zero diff authority")
        _git("cat-file", "-e", f"{ref}^{{commit}}", cwd=repository)
    output = _git("diff", "--raw", "-z", "--no-abbrev", "--find-renames",
                  base, head, "--", cwd=repository)
    fields = output.split("\0")
    if fields.pop() != "":
        raise ClassificationError("unterminated Git diff")
    rows = []
    while fields:
        header = fields.pop(0).split()
        if len(header) != 5 or not header[0].startswith(":"):
            raise ClassificationError("malformed raw Git diff")
        old_mode, new_mode, _, _, status = header
        count = 2 if status.startswith(("R", "C")) else 1
        if len(fields) < count:
            raise ClassificationError("missing Git diff path")
        paths = [_safe_path(fields.pop(0)) for _ in range(count)]
        rows.append({"status": status, "old_mode": old_mode[1:],
                     "new_mode": new_mode, "paths": paths})
    return rows


def changed_paths(repository: Path, base: str, head: str) -> list[str]:
    """Resolve both sides of every rename without Git path quoting ambiguity."""
    return sorted({p for row in changed_entries(repository, base, head) for p in row["paths"]})


def classify_change(repository: Path, base: str, head: str, *, branch: str,
                    requested_mode: str = "auto") -> tuple[str, list[dict[str, str]]]:
    entries = changed_entries(repository, base, head)
    paths = sorted({p for row in entries for p in row["paths"]})
    mode, rows = classify_paths(paths, branch=branch, requested_mode=requested_mode)
    unsafe_docs = any(
        any(path_class(p) == DOCS_ONLY for p in entry["paths"])
        and any(m not in {"000000", "100644"} for m in (entry["old_mode"], entry["new_mode"]))
        for entry in entries
    )
    if unsafe_docs:
        if requested_mode == "evidence":
            raise ClassificationError("manual evidence mode cannot override unsafe document modes")
        mode = (CLOSED_BRANCH_GUARD if branch == CLOSED_BRANCH and requested_mode != "full"
                else FULL_NATIVE)
    # Invalid evidence modes still reach inexpensive integrity rejection.
    return mode, rows


def _write_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--requested-mode", choices=("auto", "full", "evidence"), default="auto")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--github-output", type=Path)
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    repository = arguments.repository.resolve(strict=True)
    mode, rows = classify_change(
        repository, arguments.base, arguments.head,
        branch=arguments.branch,
        requested_mode=arguments.requested_mode,
    )
    if mode not in VALID_MODES:
        raise AssertionError(mode)
    result = {
        "schema": "pulsarmlx.ci.change-classification/1.0.0",
        "base": arguments.base,
        "head": arguments.head,
        "branch": arguments.branch,
        "requested_mode": arguments.requested_mode,
        "mode": mode,
        "changed_path_count": len(rows),
        "changed_paths": rows,
        "unknown_defaults_full": True,
        "closed_branch": arguments.branch == CLOSED_BRANCH,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output_json:
        arguments.output_json.write_text(encoded, encoding="utf-8")
    if arguments.github_output:
        _write_github_output(
            arguments.github_output,
            {"mode": mode, "base": arguments.base, "head": arguments.head},
        )
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ClassificationError, subprocess.CalledProcessError, OSError) as error:
        print(f"CI classification failed closed: {error}", file=sys.stderr)
        raise SystemExit(2)

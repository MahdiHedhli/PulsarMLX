#!/usr/bin/env python3
"""Lightweight append-only evidence validation for CI routing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

from scripts.ci.classify_ci_change import EVIDENCE_ONLY, changed_paths, classify_paths


EVIDENCE_PREFIX = "docs/architecture/reviews/evidence/"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CREDENTIAL_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
}


class ValidationError(RuntimeError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid JSON {label}: {error}") from error


def _git(repository: Path, *arguments: str, binary: bool = False):
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return completed.stdout


def _diff_rows(repository: Path, base: str, head: str) -> list[tuple[str, str]]:
    output = _git(repository, "diff", "--name-status", "--find-renames", base, head)
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 2:
            raise ValidationError(f"renames/copies and malformed rows prohibited: {line!r}")
        rows.append((fields[0], fields[1]))
    return rows


def _committed_bytes(repository: Path, head: str, path: str) -> bytes:
    return _git(repository, "show", f"{head}:{path}", binary=True)


def _resolve_binding(repository: Path, head: str, binding: dict[str, Any]) -> bool:
    path = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(path, str) or not isinstance(expected_sha, str) or not SHA256.fullmatch(expected_sha):
        return False
    posix = PurePosixPath(path)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValidationError(f"unsafe bound path: {path}")
    commit = binding.get("commit") or binding.get("source_commit")
    authority = str(commit) if commit is not None else head
    try:
        data = _git(repository, "show", f"{authority}:{path}", binary=True)
    except subprocess.CalledProcessError as error:
        raise ValidationError(f"unresolved bound path {authority}:{path}") from error
    if hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValidationError(f"bound SHA mismatch: {authority}:{path}")

    field = binding.get("field", binding.get("json_path"))
    if field is not None:
        expected_present = [key for key in ("value", "expected", "equals") if key in binding]
        if len(expected_present) != 1:
            raise ValidationError(f"bound field requires exactly one expected value: {path}")
        document = strict_json(data, f"{authority}:{path}")
        components = field if isinstance(field, list) else str(field).lstrip("$").lstrip(".").split(".")
        value: Any = document
        for component in components:
            if component == "":
                continue
            if isinstance(value, list):
                try:
                    value = value[int(component)]
                except (ValueError, IndexError) as error:
                    raise ValidationError(f"unresolved list field {field!r}: {path}") from error
            elif isinstance(value, dict) and component in value:
                value = value[component]
            else:
                raise ValidationError(f"unresolved field {field!r}: {path}")
        if value != binding[expected_present[0]]:
            raise ValidationError(f"bound field value mismatch {field!r}: {path}")
    return True


def _walk_bindings(repository: Path, head: str, value: Any) -> int:
    count = 0
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            count += int(_resolve_binding(repository, head, value))
        for nested in value.values():
            count += _walk_bindings(repository, head, nested)
    elif isinstance(value, list):
        for nested in value:
            count += _walk_bindings(repository, head, nested)
    return count


def validate_change(
    repository: Path,
    *,
    base: str,
    head: str,
    branch: str,
    run_attempt1: bool = True,
) -> dict[str, Any]:
    repository = repository.resolve(strict=True)
    _git(repository, "cat-file", "-e", f"{base}^{{commit}}")
    _git(repository, "cat-file", "-e", f"{head}^{{commit}}")
    paths = changed_paths(repository, base, head)
    mode, _ = classify_paths(paths, branch=branch)
    if mode != EVIDENCE_ONLY:
        raise ValidationError(f"evidence validator received {mode} diff")
    rows = _diff_rows(repository, base, head)
    if not rows:
        raise ValidationError("evidence validation requires changed evidence")
    completed = subprocess.run(
        ["git", "diff", "--check", base, head],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise ValidationError(f"git diff --check failed: {completed.stdout}{completed.stderr}")

    json_count = 0
    binding_count = 0
    byte_count = 0
    for status_code, path in rows:
        if status_code != "A":
            raise ValidationError(f"immutable evidence must be append-only, got {status_code}: {path}")
        if not path.startswith(EVIDENCE_PREFIX):
            raise ValidationError(f"path outside approved evidence root: {path}")
        tree_row = _git(repository, "ls-tree", head, "--", path).strip().split()
        if len(tree_row) < 3 or tree_row[0] != "100644" or tree_row[1] != "blob":
            raise ValidationError(f"evidence must be a regular non-executable file: {path}")
        data = _committed_bytes(repository, head, path)
        byte_count += len(data)
        for name, pattern in CREDENTIAL_PATTERNS.items():
            if pattern.search(data.decode("utf-8", errors="ignore")):
                raise ValidationError(f"credential-shaped material ({name}) in {path}")
        if path.endswith(".json"):
            document = strict_json(data, path)
            json_count += 1
            binding_count += _walk_bindings(repository, head, document)

    attempt1 = None
    if run_attempt1:
        from scripts.ci.validate_f017_attempt1_evidence import validate

        attempt1 = validate(repository)
    return {
        "schema": "pulsarmlx.ci.evidence-change-validation/1.0.0",
        "result": "PASS",
        "base": base,
        "head": head,
        "branch": branch,
        "mode": EVIDENCE_ONLY,
        "changed_file_count": len(rows),
        "json_file_count": json_count,
        "total_changed_bytes": byte_count,
        "resolved_binding_count": binding_count,
        "append_only": True,
        "regular_non_symlink": True,
        "duplicate_keys_rejected": True,
        "credential_scan": "PASS",
        "native_builds": 0,
        "checkpoint_opens": 0,
        "attempt1_validation": attempt1,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-attempt1", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    result = validate_change(
        arguments.repository,
        base=arguments.base,
        head=arguments.head,
        branch=arguments.branch,
        run_attempt1=not arguments.skip_attempt1,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    arguments.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"evidence validation failed closed: {error}", file=sys.stderr)
        raise SystemExit(2)

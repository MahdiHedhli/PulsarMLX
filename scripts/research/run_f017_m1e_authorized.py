#!/usr/bin/env python3
"""Canonical config-only M1-E launch orchestration.

No execution-controlling path is accepted on this command line. The immutable
config binds the runner, independent preparer, repository/package roots, and
all numerical contracts. Preflight is non-consuming; production creates the
exclusive execution-state marker before any real payload preparation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path, expected: str) -> dict[str, object]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("immutable M1-E execution config hash mismatch")
    document = json.loads(raw, object_pairs_hook=_no_duplicates)
    if (
        document.get("schema") != "pulsarmlx.f017.m1e-execution-config"
        or document.get("schema_version") != "3.0.0"
        or document.get("attempt") != 3
        or document.get("attempt_consumed") is not False
    ):
        raise ValueError("wrong M1-E execution config schema")
    return document


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def checked_local(document: dict[str, object], role: str) -> Path:
    artifact = document["local_artifacts"][role]
    if artifact["path_kind"] != "absolute_private_local":
        raise ValueError(f"{role} has wrong path kind")
    path = Path(artifact["path"])
    if not path.is_absolute() or path.is_symlink() or sha(path) != artifact["content_sha256"]:
        raise ValueError(f"{role} identity mismatch")
    return path


def checked_repository(document: dict[str, object], role: str) -> Path:
    artifact = document["repository_artifacts"][role]
    if artifact["path_kind"] != "repository_relative":
        raise ValueError(f"{role} has wrong path kind")
    symbolic = Path(artifact["symbolic_path"])
    if symbolic.is_absolute() or ".." in symbolic.parts:
        raise ValueError(f"{role} symbolic path is unsafe")
    path = Path(document["repository_root"]["path"]) / symbolic
    if path.is_symlink() or sha(path) != artifact["content_sha256"]:
        raise ValueError(f"{role} identity mismatch")
    return path


def write_state(path: Path, config_sha: str) -> None:
    payload = json.dumps(
        {
            "schema": "pulsarmlx.f017.m1e-attempt-state",
            "schema_version": "1.0.0",
            "attempt": 3,
            "state": "EXECUTION_STARTED",
            "execution_config_sha256": config_sha,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--execution-config-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    document = load(args.execution_config, args.execution_config_sha256)
    runner = checked_local(document, "runner_binary")
    preflight = subprocess.run(
        [str(runner), "--m1e-preflight-only", str(args.execution_config), "--execution-config-sha256", args.execution_config_sha256],
        cwd="/private/tmp",
        text=True,
        capture_output=True,
        check=False,
    )
    if preflight.returncode != 0 or preflight.stdout.strip() != "READY_TO_EXECUTE_M1_E":
        raise RuntimeError(f"M1-E preflight failed: {preflight.stderr.strip()}")
    if args.preflight_only:
        print("READY_TO_EXECUTE_M1_E")
        return 0

    state_path = Path(document["local_artifacts"]["attempt_state_output"])
    write_state(state_path, args.execution_config_sha256)
    package_output = Path(document["local_artifacts"]["package_output"])
    if document["runner"]["mode"] == "real_expert" or not package_output.exists():
        launcher = checked_local(document, "oracle_launcher")
        preparer = checked_repository(document, "real_reference_preparer")
        prepared = subprocess.run(
            [str(launcher), "run", "--frozen", "--python", "3.13.13", "python", str(preparer), "--execution-config", str(args.execution_config), "--execution-config-sha256", args.execution_config_sha256],
            cwd=document["repository_root"]["path"],
            check=False,
        )
        if prepared.returncode != 0:
            raise RuntimeError("independent M1-E oracle preparation failed")
    candidate = subprocess.run(
        [str(runner), "--m1e-execution-config", str(args.execution_config), "--execution-config-sha256", args.execution_config_sha256],
        cwd="/private/tmp",
        check=False,
    )
    return candidate.returncode


if __name__ == "__main__":
    raise SystemExit(main())

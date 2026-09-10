#!/usr/bin/env python3
"""Prove critical tests fail when their guarded behavior is removed."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError(f"mutation anchor count for {path.name}: {source.count(old)}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def replace_exact(path: Path, old: str, new: str, expected: int) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(old) != expected:
        raise RuntimeError(f"mutation anchor count for {path.name}: {source.count(old)}")
    path.write_text(source.replace(old, new), encoding="utf-8")


def expect_failure(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=90,
        check=False,
    )
    if result.returncode == 0:
        raise RuntimeError(f"mutation survived: {command[-1]}")


def rust_mutation(
    pristine: Path,
    scratch: Path,
    target: Path,
    name: str,
    old: str,
    new: str,
    test_name: str,
    count: int = 1,
) -> None:
    mutant = scratch / name
    shutil.copytree(pristine, mutant)
    replace_exact(mutant / "src/lib.rs", old, new, count)
    if name == "excess-body":
        replace_once(
            mutant / "src/lib.rs",
            "if bytes.len().saturating_add(data.len()) > MAX_BODY_BYTES {",
            "if bytes.len().saturating_add(data.len()) > usize::MAX {",
        )
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(target)
    expect_failure(
        ["cargo", "test", "--offline", "--test", "raw_http", test_name, "--", "--exact"],
        mutant,
        env,
    )


def python_mutation(pristine: Path, scratch: Path, python: str, name: str, old: str, new: str) -> None:
    mutant = scratch / f"{name}.py"
    shutil.copy2(pristine / "tests/sdk_client.py", mutant)
    replace_once(mutant, old, new)
    expect_failure(
        [python, "-c", f"exec(open({str(mutant)!r}).read().split('def main()')[0]); prove_destination_and_redirect_guards()"],
        pristine,
        os.environ.copy(),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    pristine = Path(__file__).resolve().parents[1]
    if args.scratch.exists():
        raise RuntimeError("scratch path must not exist")
    args.scratch.mkdir(parents=True, mode=0o700)
    args.target.mkdir(parents=True, exist_ok=True)

    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "missing-auth",
        "if !valid_auth(request.headers().get(AUTHORIZATION), &state.token) {",
        "if false {",
        "health_and_models_enforce_the_boundary",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "excess-body",
        "if length > MAX_BODY_BYTES {",
        "if length > usize::MAX {",
        "invalid_and_oversized_requests_never_start_backend",
        1,
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "missing-release",
        ".fetch_sub(1, Ordering::SeqCst);",
        ".fetch_add(1, Ordering::SeqCst);",
        "disconnect_releases_stream_ownership",
    )
    rust_mutation(
        pristine,
        args.scratch,
        args.target,
        "false-terminal",
        "let _ = send_event(&sender, \"error\", &error).await;\n                return;",
        "let _ = send_event(&sender, \"error\", &error).await;",
        "stream_failure_has_no_success_terminal",
    )
    python_mutation(
        pristine,
        args.scratch,
        args.python,
        "cloud-destination",
        "        self.require_loopback(request)\n",
        "        pass\n",
    )
    python_mutation(
        pristine,
        args.scratch,
        args.python,
        "redirect-follow",
        "        transport=LoopbackGuardTransport(redirect_inner),\n        follow_redirects=False,\n",
        "        transport=LoopbackGuardTransport(redirect_inner),\n        follow_redirects=True,\n",
    )
    print("MUTATION_GUARDS_OK count=6")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rebind an inert synthetic authority to one exact source-built executable.

This helper cannot create a real P1 authority: it requires and preserves
`real_event_authorized == false`, retries zero, resume false, and mandatory
stop. It changes only the inert identifiers, executable SHA, and source head.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_identifier(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(
        c.isascii() and (c.isalnum() or c in "-_") for c in value
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--execution-code-head", required=True)
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.execution_code_head) != 40 or any(
        character not in "0123456789abcdef" for character in args.execution_code_head
    ):
        raise SystemExit("execution-code head must be a full lowercase Git SHA")
    if not safe_identifier(args.authorization_id) or not safe_identifier(args.attempt_id):
        raise SystemExit("unsafe inert authority identifier")
    if not args.binary.is_file() or args.binary.is_symlink():
        raise SystemExit("synthetic executable must be a regular non-symlink file")
    value = json.loads(args.template.read_text(), object_pairs_hook=strict_object)
    if not isinstance(value, dict) or value.get("real_event_authorized") is not False \
            or value.get("attempts") != 1 or value.get("retries") != 0 \
            or value.get("resume") is not False or value.get("mandatory_stop") is not True:
        raise SystemExit("template is not an inert one-shot authority")
    value["authorization_id"] = args.authorization_id
    value["attempt_id"] = args.attempt_id
    value["executor_sha256"] = sha256(args.binary)
    value["git_head"] = args.execution_code_head
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


if __name__ == "__main__":
    main()

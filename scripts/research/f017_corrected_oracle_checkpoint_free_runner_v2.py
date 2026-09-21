#!/usr/bin/env python3
"""Checkpoint-free subprocess runner for the v2 pure numerical authorities."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import f017_corrected_oracle_primary_numerics_v2 as primary
import f017_corrected_oracle_secondary_numerics_v2 as secondary


def strict(path: Path) -> dict:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(path.read_text(), object_pairs_hook=pairs)


def bank(path: Path, value: dict) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
        read_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(read_descriptor, "rb") as source:
            observed = source.read()
    finally:
        os.close(parent)
    if observed != data or strict(path) != value:
        raise ValueError("checkpoint-free result exact readback")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("consumer", choices=("primary", "secondary"))
    parser.add_argument("fixture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("numpy", "mlx"), default="numpy")
    arguments = parser.parse_args()
    document = strict(arguments.fixture)
    if arguments.consumer == "primary":
        result = primary.execute(
            primary.JsonSource(document["tensors"]),
            primary.Geometry.from_json(document["geometry"]),
            document["token"],
            document.get("position", 0),
        )
    else:
        result = secondary.execute(document, arguments.backend == "mlx")
    bank(arguments.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

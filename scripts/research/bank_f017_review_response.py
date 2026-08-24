#!/usr/bin/env python3
"""Exclusively bank exact reviewer bytes with durable readback."""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path)
    arguments = parser.parse_args()
    data = arguments.source.read_bytes() if arguments.source else sys.stdin.buffer.read()
    arguments.output.parent.resolve(strict=True)
    descriptor = os.open(arguments.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    parent = os.open(arguments.output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
        read_descriptor = os.open(arguments.output.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(read_descriptor, "rb") as source:
            readback = source.read()
    finally:
        os.close(parent)
    if readback != data:
        raise ValueError("review response readback mismatch")
    print(hashlib.sha256(readback).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

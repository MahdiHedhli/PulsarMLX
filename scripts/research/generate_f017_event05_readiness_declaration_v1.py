#!/usr/bin/env python3
"""Exclusive canonical producer for Event-05 readiness declarations."""
from __future__ import annotations

import argparse
from pathlib import Path

from f017_bounded_artifact_decode_v1 import read_artifact
from f017_canonical_serialization_v10 import bank_exclusive
from f017_event05_readiness_authority_v1 import validate_readiness_value


def emit_readiness_declaration(output: Path, value: object) -> str:
    validated = validate_readiness_value(value)
    return bank_exclusive(output, validated)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(emit_readiness_declaration(args.output, read_artifact(args.input)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compatibility entry point for the canonical lifecycle-v6 generator.

There is exactly one v6 interface derivation.  This entry point intentionally
delegates to the complete lifecycle authority generator so it cannot drift.
"""
from __future__ import annotations

from generate_f017_lifecycle_v6_authorities import main as generate_lifecycle_v6


def main() -> int:
    return generate_lifecycle_v6()


if __name__ == "__main__":
    raise SystemExit(main())

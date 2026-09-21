#!/usr/bin/env python3
"""Historical-only tombstone for the combined v1 secondary target surface."""
from __future__ import annotations

HISTORICAL_COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
HISTORICAL_SHA256 = "8c4f9fde6991369bbc2549e2daa05896a9d38626bb080ca4f25b715d07bb6e29"


def main() -> int:
    raise SystemExit(
        "HISTORICAL_ONLY: combined secondary numerical/target surface is retired; "
        f"reconstruct {HISTORICAL_COMMIT}:scripts/research/f017_corrected_oracle_secondary.py "
        f"with SHA-256 {HISTORICAL_SHA256} for checkpoint-free historical validation"
    )


if __name__ == "__main__":
    raise SystemExit(main())

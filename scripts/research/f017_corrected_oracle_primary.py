#!/usr/bin/env python3
"""Historical-only tombstone for the combined v1 primary target surface."""
from __future__ import annotations

HISTORICAL_COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
HISTORICAL_SHA256 = "2041c0337ab6f3d98c342f2b0177b5f0cfb249bfed3b4aba8989afdd9396cdf1"


def main() -> int:
    raise SystemExit(
        "HISTORICAL_ONLY: combined primary numerical/target surface is retired; "
        f"reconstruct {HISTORICAL_COMMIT}:scripts/research/f017_corrected_oracle_primary.py "
        f"with SHA-256 {HISTORICAL_SHA256} for checkpoint-free historical validation"
    )


if __name__ == "__main__":
    raise SystemExit(main())

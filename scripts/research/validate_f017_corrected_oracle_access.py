#!/usr/bin/env python3
"""Historical-only tombstone installed by the F017 v6 supersession."""
from __future__ import annotations

HISTORICAL_COMMIT = '84f0d1dc3e60a4151329ed82773880951ee3e618'
HISTORICAL_SURFACE = 'V1_LIVE_MINT'
HISTORICAL_COMPATIBILITY_SENTINEL = 'HISTORICAL_ONLY: v1 live mint is permanently retired'


def main() -> int:
    raise SystemExit(
        f"HISTORICAL_ONLY: {HISTORICAL_SURFACE} is retired; "
        f"reconstruct exact bytes from {HISTORICAL_COMMIT}; "
        "current live authority, target execution, checkpoint access, and state creation are prohibited"
    )


if __name__ == "__main__":
    raise SystemExit(main())

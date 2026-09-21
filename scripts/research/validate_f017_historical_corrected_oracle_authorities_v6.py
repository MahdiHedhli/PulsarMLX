#!/usr/bin/env python3
"""Validate superseded corrected-oracle generations from immutable Git bytes."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
EXPECTED = {
    "scripts/research/f017_corrected_oracle_primary.py": "2041c0337ab6f3d98c342f2b0177b5f0cfb249bfed3b4aba8989afdd9396cdf1",
    "scripts/research/f017_corrected_oracle_secondary.py": "8c4f9fde6991369bbc2549e2daa05896a9d38626bb080ca4f25b715d07bb6e29",
    "scripts/research/f017_oracle_primary_decoders.py": "60a4b4e7d973edc41383e20d6d3413d4f658bf4a34dc9132529a6c702b44e11e",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json": "7c22507f15c79713a0f81dcf14ea3472aafef3cf43c09d388a6c021b3f1069c4",
    "docs/architecture/reviews/evidence/f017-corrected-oracle-checkpoint-free-qualification-v1.json": "b9c2f7dcd9982120f804594e9e268b7d0d764190625789717d104f4e4829c052",
    "docs/architecture/reviews/evidence/f017-corrected-oracle-event-02-execution-failure-summary-v1.json": "617cb92605eb93cba3f24e7395a1a12ba0797ac2130213e2a72b5e83b87381eb",
    "docs/architecture/reviews/evidence/f017-corrected-oracle-event-03-pre-mint-interface-failure-v1.json": "e2dcbec3b5ad4edb088e58b13f18fcd4a020b2ae5c7230694e5b3ede9c89135b",
}


def git_bytes(path: str) -> bytes:
    return subprocess.run(["git", "show", f"{COMMIT}:{path}"], cwd=ROOT, check=True, capture_output=True).stdout


def main() -> int:
    for path, expected in EXPECTED.items():
        if hashlib.sha256(git_bytes(path)).hexdigest() != expected:
            raise ValueError(f"historical Git authority drift: {path}")
    print(json.dumps({"result": "PASS", "commit": COMMIT, "historical_path_count": len(EXPECTED), "current_tree_mixed_authority": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

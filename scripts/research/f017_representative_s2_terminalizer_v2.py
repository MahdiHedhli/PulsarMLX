#!/usr/bin/env python3
"""Read-only reconciliation for representative S2 release v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import f017_representative_s2_terminalizer_v1 as terminalizer_v1


EVENT_ID = "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1"
RELEASE_ID = EVENT_ID + "-RELEASE-2"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
ReconciliationError = terminalizer_v1.ReconciliationError

terminalizer_v1.EVENT_ID = EVENT_ID
terminalizer_v1.RELEASE_ID = RELEASE_ID
terminalizer_v1.ATTEMPT_ID = ATTEMPT_ID

validate_output = terminalizer_v1.validate_output
reconcile = terminalizer_v1.reconcile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.state_root, args.output, args.manifest, args.release), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReconciliationError, FileNotFoundError, PermissionError) as error:
        print(json.dumps({"disposition": "ACCOUNTING_INTEGRITY_BLOCKER", "error": type(error).__name__, "retry": False}, sort_keys=True))
        raise SystemExit(2)

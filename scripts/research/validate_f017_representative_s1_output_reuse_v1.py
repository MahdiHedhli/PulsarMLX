#!/usr/bin/env python3
"""Validate the representative S1 cross-event reuse authorization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from f017_representative_expert_ledger_adapter_v1 import current_ledger
from f017_representative_s1_output_reuse_v1 import (
    AUTH,
    EVIDENCE_SHA,
    ROOT,
    load,
    resolve,
    sha256_path,
    validate_authorization,
    validate_evidence,
)


def validate(authorization_path: Path, check_retained: bool = False) -> dict[str, object]:
    authorization = load(authorization_path)
    validate_authorization(authorization)
    evidence_path = ROOT / authorization["source_authority"]["execution_evidence"]["path"]
    if sha256_path(evidence_path) != EVIDENCE_SHA:
        raise ValueError("EXECUTION_EVIDENCE_SHA")
    validate_evidence(load(evidence_path))
    if current_ledger() != 175:
        raise ValueError("LEDGER")
    retained = resolve(authorization_path) if check_retained else None
    return {
        "result": "REPRESENTATIVE_S1_OUTPUT_REUSE_AUTHORIZATION_VALID",
        "ledger": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "new_attention_executions": 0,
        "s1_release_v2_reruns": 0,
        "new_s1_materializations": 0,
        "ffn_compositions": 0,
        "s2_constructions": 0,
        "retained_preflight": retained["result"] if retained else "NOT_REQUESTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    parser.add_argument("--check-retained", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.authorization, args.check_retained), sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"result":"REJECT","error":str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

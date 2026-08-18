#!/usr/bin/env python3
"""Narrow CLI for the reviewed F017 shared-expert recovery event."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research.f017_shared_expert_recovery import (
    ATTEMPT_ID, EVENT_ID, EXECUTION_RELEASE, LEDGER_BEFORE, PRIVATE_ROOT_ENV,
    RELEASE_ENV, SHARD_PATH_ENV, SHARD_SHA256, SharedOutputStage,
    SharedPublicEvidenceWriter, SharedRecoveryExecutor, production_preflight,
    reproduce_once, run_synthetic_rehearsal,
)
from scripts.research.f017_canonical_expert_output_production import ProductionShardProvider
from scripts.research.f017_canonical_expert_output_recovery_executor import RecoveryExecutionError


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--synthetic-rehearsal", action="store_true")
    modes.add_argument("--execute-reviewed-event", action="store_true")
    modes.add_argument("--internal-reproduce-once", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.preflight_only:
        print(json.dumps(production_preflight(), sort_keys=True, separators=(",", ":")))
        return 0
    if args.synthetic_rehearsal:
        result = run_synthetic_rehearsal()
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["status"] == "PASS" else 1
    if args.internal_reproduce_once:
        if os.environ.get("PULSARMLX_F017_INTERNAL_SHARED_REPRODUCTION") != "1":
            raise RecoveryExecutionError("INTERNAL_REPRODUCTION_GUARD")
        private = os.environ.get(PRIVATE_ROOT_ENV)
        if not private:
            raise RecoveryExecutionError("PRIVATE_BINDING_UNRESOLVED")
        print(json.dumps({"output_sha256": reproduce_once(Path(private))}, sort_keys=True))
        return 0
    if os.environ.get(RELEASE_ENV) != EXECUTION_RELEASE:
        raise RecoveryExecutionError("INDEPENDENT_EXECUTION_RELEASE_REQUIRED")
    preflight = production_preflight()
    if preflight["status"] != "PRODUCTION_BINDINGS_RESOLVED":
        raise RecoveryExecutionError("PRODUCTION_PREFLIGHT")
    private = os.environ.get(PRIVATE_ROOT_ENV)
    shard = os.environ.get(SHARD_PATH_ENV)
    if not private or not shard:
        raise RecoveryExecutionError("PRIVATE_BINDING_UNRESOLVED")
    root = Path(private)
    provider = ProductionShardProvider(Path(shard))
    stage = SharedOutputStage(root / "package", state_root=root / "state")
    executor = SharedRecoveryExecutor(root / "state", root / "package", provider, stage)
    terminal = executor.execute()
    SharedPublicEvidenceWriter(
        ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-recovery-result-v1.json"
    ).write(terminal)
    print(json.dumps(terminal, sort_keys=True, separators=(",", ":")))
    return 0 if terminal["classification"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())

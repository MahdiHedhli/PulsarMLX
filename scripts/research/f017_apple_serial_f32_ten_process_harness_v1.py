#!/usr/bin/env python3
"""Future ten-fresh-process determinism harness; inert without a live GO."""

from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def earliest_divergence(run_roots: list[Path], stage_ids: list[str]):
    hashes = []
    for root in run_roots:
        manifest = json.loads((root / "capture-manifest.json").read_text())
        hashes.append({row["stage_id"]: row["sha256"] for row in manifest["stages"]})
    for stage in stage_ids:
        values = [row[stage] for row in hashes]
        if len(set(values)) != 1:
            return {"stage_id":stage,"run_hashes":values}
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--live-go", type=Path)
    parser.add_argument("--execute-representative", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    if args.self_test:
        if contract["fresh_processes"] != 10 or contract["stage_count"] != 34 or contract["comparison"] != "BYTE_IDENTITY_ALL_STAGES_ALL_RUNS":
            raise SystemExit("contract")
        print("TEN_PROCESS_HARNESS_STRUCTURE_PASS_NO_REPRESENTATIVE_RUN")
        return 0
    if not args.execute_representative or args.live_go is None:
        raise SystemExit("LIVE_GO_AND_EXPLICIT_REPRESENTATIVE_MODE_REQUIRED")
    raise SystemExit("FUTURE_OPERATOR_WRAPPER_MUST_INJECT_TEN_DISTINCT_ONE_RUN_AUTHORIZATIONS")


if __name__ == "__main__":
    raise SystemExit(main())

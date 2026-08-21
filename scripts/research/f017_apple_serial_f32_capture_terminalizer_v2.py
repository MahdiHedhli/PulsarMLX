#!/usr/bin/env python3
"""Read-only RN1 reconciliation for Apple serial-f32 attempts."""

from __future__ import annotations
import argparse
from pathlib import Path
try:
    from .f017_apple_serial_f32_capture_wrapper_v2 import GateError, load_unique, owner_matches, sha
except ImportError:  # Direct CLI execution from scripts/research.
    from f017_apple_serial_f32_capture_wrapper_v2 import GateError, load_unique, owner_matches, sha


def reconcile(root: Path) -> dict:
    owner_path = root / "owner.json"
    start_path = root / "attempt-start.json"
    terminal_path = root / "terminal.json"
    if not owner_path.is_file() or not start_path.is_file():
        raise GateError("DURABLE_START_INCOMPLETE_OPERATOR_ADJUDICATION_REQUIRED")
    owner = load_unique(owner_path)
    start = load_unique(start_path)
    owner_sha = sha(owner_path)
    invocation = owner.get("invocation_id")
    if not isinstance(invocation, str) or not owner_matches(root, invocation, owner_sha):
        raise GateError("OWNER_IDENTITY")
    if start.get("owner_sha256") != owner_sha or start.get("invocation_id") != invocation:
        raise GateError("START_OWNER_MISMATCH")
    receipts_dir = root / "payload-receipts"
    receipts = [] if not receipts_dir.exists() else sorted(p for p in receipts_dir.iterdir() if p.is_file())
    receipt_inventory = [{"path": p.name, "sha256": sha(p)} for p in receipts]
    terminal = load_unique(terminal_path) if terminal_path.is_file() else None
    if terminal is not None:
        if terminal.get("owner_sha256") != owner_sha or terminal.get("invocation_id") != invocation:
            raise GateError("TERMINAL_OWNER_MISMATCH")
        if terminal.get("consumed_reads") != len(receipts):
            raise GateError("TERMINAL_RECEIPT_COUNT_MISMATCH")
        if terminal.get("receipt_inventory") != receipt_inventory:
            raise GateError("TERMINAL_ORPHAN_INVENTORY_MISMATCH")
        if terminal.get("ledger_after") != 175 + len(receipts):
            raise GateError("TERMINAL_LEDGER_NOT_RECEIPT_DERIVED")
    inventory_path = root / "artifact-inventory.json"
    if inventory_path.is_file():
        inventory = load_unique(inventory_path)
        actual = sorted(p.name for p in root.iterdir() if p.is_file() and p.name != "artifact-inventory.json")
        declared = sorted(row["path"] for row in inventory.get("artifacts", []))
        if actual != declared:
            raise GateError("ORPHAN_OR_MISSING_ARTIFACT")
        for row in inventory["artifacts"]:
            if sha(root / row["path"]) != row["sha256"]:
                raise GateError("INVENTORY_HASH")
    return {"status": "RECONCILED_READ_ONLY", "attempt_owned": True, "receipt_derived_consumed_reads": len(receipts), "terminal_present": terminal is not None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-root", required=True, type=Path)
    args = parser.parse_args()
    print(reconcile(args.attempt_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

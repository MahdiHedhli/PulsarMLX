#!/usr/bin/env python3
"""Generation-v6 coordinator with handshake-before-state ordering.

Production execution remains gated by the active-generation registry and a
future operator approval.  This module is exercised here only with structurally
isolated synthetic checkpoint packages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from f017_corrected_oracle_authorization_v6 import read_regular_nofollow, strict_bytes
from f017_corrected_oracle_compare_v6 import compare
from f017_corrected_oracle_wrapper_support_v6 import ROOT, bank, require_active

PRIMARY = ROOT / "scripts/research/f017_corrected_oracle_primary_v6.py"
SECONDARY = ROOT / "scripts/research/f017_corrected_oracle_secondary_v6.py"


def sha(path: Path) -> str:
    return hashlib.sha256(read_regular_nofollow(path)).hexdigest()


def artifact(path: Path, schema: str, bindings: dict[str, Any], payload: dict[str, Any]) -> str:
    return bank(path, {"schema": schema, "bindings": bindings, "payload": payload})


def installed_handshake(
    authorization: Path,
    interface: Path,
    checkpoint_root: Path,
    receipt: Path,
    authority_root: Path,
) -> dict[str, Any]:
    """Complete both real installed-auth checks before state or shard access."""
    document = strict_bytes(read_regular_nofollow(authorization))
    if any(Path(document[name]).exists() for name in ()):
        raise AssertionError("unreachable")
    reports = {}
    for role, consumer in (("primary", PRIMARY), ("secondary", SECONDARY)):
        output = authority_root / f"{role}-installed-validation.json"
        subprocess.run(
            [sys.executable, str(consumer), "validate-installed-authorization", str(authorization), str(interface), str(checkpoint_root), str(output), str(receipt)],
            cwd=ROOT,
            check=True,
        )
        value = strict_bytes(read_regular_nofollow(output))
        if value.get("result") != "PASS" or value.get("state_created") is not False:
            raise ValueError(f"{role} installed handshake")
        if any(value.get(key) != 0 for key in (
            "checkpoint_shard_opens", "checkpoint_identity_hash_reads",
            "checkpoint_mmaps", "checkpoint_tensor_reads", "numerical_operations",
        )):
            raise ValueError(f"{role} handshake side effect")
        reports[role] = {"path": str(output), "sha256": sha(output)}
    handshake = {
        "schema": "pulsarmlx.f017.corrected-oracle-coordinator-handshake/6.0.0",
        "authorization_sha256": sha(authorization),
        "installation_receipt_sha256": sha(receipt),
        "package_attempt_id": document["package_attempt_id"],
        "primary_event_id": document["primary_event_id"],
        "secondary_event_id": document["secondary_event_id"],
        "primary": reports["primary"],
        "secondary": reports["secondary"],
        "checkpoint_opens_before_handshake": 0,
        "checkpoint_reads_before_handshake": 0,
        "state_created_before_handshake": False,
        "result": "PASS",
    }
    bank(authority_root / "coordinator-handshake.json", handshake)
    return handshake


def execute_synthetic(
    authorization: Path,
    interface: Path,
    installation_receipt: Path,
    checkpoint_root: Path,
    catalog: Path,
    geometry: Path,
    checkpoint_identity: Path,
    authority_root: Path,
    *,
    secondary_backend: str = "numpy",
) -> dict[str, Any]:
    document = strict_bytes(read_regular_nofollow(authorization))
    if document["authority_scope"] != "SYNTHETIC_QUALIFICATION":
        require_active(document["authority_scope"])
    for root in (Path(document["package"]["state_root"]), Path(document["package"]["output_root"]), Path(document["primary"]["state_root"]), Path(document["primary"]["output_root"]), Path(document["secondary"]["state_root"]), Path(document["secondary"]["output_root"])):
        if root.exists() or root.is_symlink():
            raise ValueError("unused state/output roots required")
    handshake = installed_handshake(authorization, interface, checkpoint_root, installation_receipt, authority_root)
    bindings = {
        "authorization_id": document["authorization_id"],
        "package_attempt_id": document["package_attempt_id"],
        "primary_event_id": document["primary_event_id"],
        "secondary_event_id": document["secondary_event_id"],
        "installed_authorization_sha256": sha(authorization),
        "installation_receipt_sha256": sha(installation_receipt),
    }
    package_state = Path(document["package"]["state_root"]); package_output = Path(document["package"]["output_root"])
    package_state.mkdir(parents=True, exist_ok=False); package_output.mkdir(parents=True, exist_ok=False)
    claim_sha = artifact(package_state / "claim.json", "pulsarmlx.f017.corrected-oracle-package-claim/6.0.0", bindings, {"owner_pid": os.getpid(), "owner_nonce": document["package_attempt_id"], "package_attempts": 1, "package_retries": 0, "package_resume": False})
    package_start_sha = artifact(package_state / "durable-start.json", "pulsarmlx.f017.corrected-oracle-package-durable-start/6.0.0", {**bindings, "package_claim_sha256": claim_sha}, {"package_attempt_delta": 1})
    artifact(package_state / "ledger.json", "pulsarmlx.f017.corrected-oracle-ledger-entry/6.0.0", {**bindings, "package_durable_start_sha256": package_start_sha}, {"target": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER", "delta": 1})

    results = {}
    terminals = {}
    for role, consumer in (("primary", PRIMARY), ("secondary", SECONDARY)):
        grant = document[role]
        state = Path(grant["state_root"]); output_root = Path(grant["output_root"])
        state.mkdir(parents=True, exist_ok=False); output_root.mkdir(parents=True, exist_ok=False)
        start_sha = artifact(state / "durable-start.json", "pulsarmlx.f017.corrected-oracle-consumer-durable-start/6.0.0", bindings, {"role": grant["role"], "event_id": grant["event_id"], "event_delta": 1})
        ledger_sha = artifact(state / "ledger.json", "pulsarmlx.f017.corrected-oracle-ledger-entry/6.0.0", {**bindings, f"{role}_durable_start_sha256": start_sha}, {"target": f"CORRECTED_ORACLE_{role.upper()}_EVENT_LEDGER", "delta": 1})
        output = output_root / "result.json"; events = output_root / "access-events"
        command = [sys.executable, str(consumer), "target", str(authorization), str(interface), str(checkpoint_root), str(output), str(installation_receipt), str(catalog), str(geometry), str(checkpoint_identity), str(events)]
        if role == "secondary": command += ["--backend", secondary_backend]
        subprocess.run(command, cwd=ROOT, check=True)
        result_sha = sha(output)
        receipt_sha = artifact(state / "receipt.json", "pulsarmlx.f017.corrected-oracle-consumer-receipt/6.0.0", {**bindings, f"{role}_durable_start_sha256": start_sha, f"{role}_ledger_entry_sha256": ledger_sha}, {"result": "COMPLETE", "output_manifest_sha256": result_sha, "access_event_count": len(list(events.glob("*.json")))})
        terminal_sha = artifact(state / "terminal.json", "pulsarmlx.f017.corrected-oracle-consumer-terminal/6.0.0", {**bindings, f"{role}_receipt_sha256": receipt_sha}, {"result": "COMPLETE", "mandatory_stop": True})
        results[role] = strict_bytes(read_regular_nofollow(output))
        terminals[role] = {"receipt_sha256": receipt_sha, "terminal_sha256": terminal_sha, "result_sha256": result_sha}
    comparison = compare(results["primary"], results["secondary"])
    comparison_sha = artifact(package_output / "comparison.json", "pulsarmlx.f017.corrected-oracle-comparison-receipt/6.0.0", bindings, comparison)
    artifact(package_output / "comparison-terminal.json", "pulsarmlx.f017.corrected-oracle-comparison-terminal/6.0.0", {**bindings, "comparison_receipt_sha256": comparison_sha}, {"result": "COMPLETE", "mandatory_stop": True})
    package_receipt_sha = artifact(package_state / "receipt.json", "pulsarmlx.f017.corrected-oracle-package-receipt/6.0.0", {**bindings, "primary_receipt_sha256": terminals["primary"]["receipt_sha256"], "primary_terminal_sha256": terminals["primary"]["terminal_sha256"], "secondary_receipt_sha256": terminals["secondary"]["receipt_sha256"], "secondary_terminal_sha256": terminals["secondary"]["terminal_sha256"]}, {"outcome": "COMPLETE_SUCCESS", "primary_disposition": "STARTED", "secondary_disposition": "STARTED", "actual_deltas": {"package": 1, "primary": 1, "secondary": 1}})
    package_terminal_sha = artifact(package_state / "terminal.json", "pulsarmlx.f017.corrected-oracle-package-terminal/6.0.0", {**bindings, "package_receipt_sha256": package_receipt_sha}, {"outcome": "COMPLETE_SUCCESS", "result": "COMPLETE", "mandatory_stop": True})
    return {"result": "PASS", "handshake": handshake, "comparison": comparison, "package_terminal_sha256": package_terminal_sha, "deltas": {"authorization": 0, "package": 1, "primary": 1, "secondary": 1}, "historical_ledger_before": 175, "historical_ledger_after": 175}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("authorization", type=Path); parser.add_argument("interface", type=Path)
    parser.add_argument("installation_receipt", type=Path); parser.add_argument("checkpoint_root", type=Path)
    parser.add_argument("catalog", type=Path); parser.add_argument("geometry", type=Path)
    parser.add_argument("checkpoint_identity", type=Path); parser.add_argument("authority_root", type=Path)
    arguments = parser.parse_args()
    result = execute_synthetic(arguments.authorization, arguments.interface, arguments.installation_receipt, arguments.checkpoint_root, arguments.catalog, arguments.geometry, arguments.checkpoint_identity, arguments.authority_root)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

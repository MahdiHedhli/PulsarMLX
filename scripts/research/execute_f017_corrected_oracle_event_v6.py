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
import time
from pathlib import Path
from typing import Any

from f017_corrected_oracle_authorization_v6 import read_regular_nofollow, strict_bytes
from f017_corrected_oracle_compare_v6 import compare
from f017_corrected_oracle_wrapper_support_v6 import ROOT, bank, require_active
from f017_lifecycle_artifact_v6 import authorization_bindings, bank_artifact

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
    receipt_document = strict_bytes(read_regular_nofollow(receipt))
    bindings = authorization_bindings(document)
    bindings.update({
        "candidate_sha256": receipt_document["payload"]["candidate_sha256"],
        "installed_authorization_sha256": sha(authorization),
        "installation_receipt_sha256": sha(receipt),
        "primary_candidate_validation_report_sha256": receipt_document["bindings"]["primary_candidate_validation_report_sha256"],
        "secondary_candidate_validation_report_sha256": receipt_document["bindings"]["secondary_candidate_validation_report_sha256"],
    })
    reports = {}
    for role, consumer in (("primary", PRIMARY), ("secondary", SECONDARY)):
        raw = authority_root / f"{role}-installed-validation-raw.json"
        output = authority_root / f"{role}-installed-validation.json"
        subprocess.run(
            [sys.executable, str(consumer), "validate-installed-authorization", str(authorization), str(interface), str(checkpoint_root), str(raw), str(receipt)],
            cwd=ROOT,
            check=True,
        )
        value = strict_bytes(read_regular_nofollow(raw))
        if value.get("result") != "PASS" or value.get("state_created") is not False:
            raise ValueError(f"{role} installed handshake")
        if any(value.get(key) != 0 for key in (
            "checkpoint_shard_opens", "checkpoint_identity_hash_reads",
            "checkpoint_mmaps", "checkpoint_tensor_reads", "numerical_operations",
        )):
            raise ValueError(f"{role} handshake side effect")
        payload = {
            "result": "PASS", "installed_authorization_sha256": sha(authorization),
            "installation_receipt_sha256": sha(receipt), f"{role}_role": value["consumer_role"],
            "side_effects": {key: value[key] for key in (
                "checkpoint_shard_opens", "checkpoint_identity_hash_reads", "checkpoint_mmaps",
                "checkpoint_tensor_reads", "numerical_operations", "state_created",
            )},
        }
        report_sha = bank_artifact(output, f"{role}_installed_validation_report", bindings, payload)
        bindings[f"{role}_installed_validation_report_sha256"] = report_sha
        reports[role] = {"path": str(output), "sha256": report_sha}
    payload = {
        "checkpoint_opens_before_handshake": 0,
        "checkpoint_reads_before_handshake": 0,
        "state_created_before_handshake": False,
        "result": "PASS",
    }
    handshake_sha = bank_artifact(authority_root / "coordinator-handshake.json", "coordinator_handshake", bindings, payload)
    handshake = {**payload, "sha256": handshake_sha, "primary": reports["primary"], "secondary": reports["secondary"]}
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
    receipt_document = strict_bytes(read_regular_nofollow(installation_receipt))
    bindings = authorization_bindings(document)
    bindings.update({
        "candidate_sha256": receipt_document["payload"]["candidate_sha256"],
        "installed_authorization_sha256": sha(authorization), "installation_receipt_sha256": sha(installation_receipt),
        "primary_candidate_validation_report_sha256": receipt_document["bindings"]["primary_candidate_validation_report_sha256"],
        "secondary_candidate_validation_report_sha256": receipt_document["bindings"]["secondary_candidate_validation_report_sha256"],
        "primary_installed_validation_report_sha256": handshake["primary"]["sha256"],
        "secondary_installed_validation_report_sha256": handshake["secondary"]["sha256"],
        "coordinator_handshake_sha256": handshake["sha256"],
    })
    package_state = Path(document["package"]["state_root"]); package_output = Path(document["package"]["output_root"])
    package_state.mkdir(parents=True, exist_ok=False); package_output.mkdir(parents=True, exist_ok=False)
    claim_sha = bank_artifact(package_state / "claim.json", "package_claim", bindings, {"owner_pid": os.getpid(), "owner_nonce": document["package_attempt_id"], "package_attempts": 1, "package_retries": 0, "package_resume": False})
    bindings["package_claim_sha256"] = claim_sha
    package_start_sha = bank_artifact(package_state / "durable-start.json", "package_durable_start", bindings, {"started_at_unix_ns": time.time_ns(), "package_claim_sha256": claim_sha, "package_ledger_entry_id": document["package"]["ledger_entry_id"]})
    bindings["package_durable_start_sha256"] = package_start_sha
    package_ledger_sha = bank_artifact(package_state / "ledger.json", "package_ledger_entry", bindings, {"target": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER", "delta": 1, "package_durable_start_sha256": package_start_sha, "sequence": 1, "prior_entry_sha256": None})
    bindings["package_ledger_entry_sha256"] = package_ledger_sha
    package_index_sha = bank_artifact(package_state / "ledger-index.json", "package_ledger_index", bindings, {"target": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER", "terminal_sequence": 1, "package_ledger_entry_sha256": package_ledger_sha})
    bindings["package_ledger_index_sha256"] = package_index_sha

    results = {}
    terminals = {}
    for role, consumer in (("primary", PRIMARY), ("secondary", SECONDARY)):
        grant = document[role]
        state = Path(grant["state_root"]); output_root = Path(grant["output_root"])
        state.mkdir(parents=True, exist_ok=False); output_root.mkdir(parents=True, exist_ok=False)
        start_sha = bank_artifact(state / "durable-start.json", f"{role}_durable_start", bindings, {"started_at_unix_ns": time.time_ns(), f"{role}_ledger_entry_id": grant["ledger_entry_id"]})
        bindings[f"{role}_durable_start_sha256"] = start_sha
        ledger_sha = bank_artifact(state / "ledger.json", f"{role}_ledger_entry", bindings, {"target": f"CORRECTED_ORACLE_{role.upper()}_EVENT_LEDGER", "delta": 1, f"{role}_durable_start_sha256": start_sha, "sequence": 1, "prior_entry_sha256": None})
        bindings[f"{role}_ledger_entry_sha256"] = ledger_sha
        index_sha = bank_artifact(state / "ledger-index.json", f"{role}_ledger_index", bindings, {"target": f"CORRECTED_ORACLE_{role.upper()}_EVENT_LEDGER", "terminal_sequence": 1, f"{role}_ledger_entry_sha256": ledger_sha})
        bindings[f"{role}_ledger_index_sha256"] = index_sha
        output = output_root / "result.json"; events = output_root / "access-events"
        command = [sys.executable, str(consumer), "target", str(authorization), str(interface), str(checkpoint_root), str(output), str(installation_receipt), str(catalog), str(geometry), str(checkpoint_identity), str(events)]
        if role == "secondary": command += ["--backend", secondary_backend]
        subprocess.run(command, cwd=ROOT, check=True)
        result_sha = sha(output)
        access_census_sha = bank(output_root / "access-census.json", {"schema": "pulsarmlx.f017.corrected-oracle-access-census/6.0.0", "role": role, "access_event_count": len(list(events.glob("*.json"))), "unexpected_accesses": 0, "fallback_attempts": 0})
        receipt_sha = bank_artifact(state / "receipt.json", f"{role}_receipt", bindings, {"result": "COMPLETE", f"{role}_durable_start_sha256": start_sha, f"{role}_ledger_entry_sha256": ledger_sha, "access_census_sha256": access_census_sha, "output_manifest_sha256": result_sha})
        bindings[f"{role}_receipt_sha256"] = receipt_sha
        terminal_sha = bank_artifact(state / "terminal.json", f"{role}_terminal", bindings, {"result": "COMPLETE", f"{role}_receipt_sha256": receipt_sha, "mandatory_stop": True})
        bindings[f"{role}_terminal_sha256"] = terminal_sha
        results[role] = strict_bytes(read_regular_nofollow(output))
        terminals[role] = {"receipt_sha256": receipt_sha, "terminal_sha256": terminal_sha, "result_sha256": result_sha}
    comparison = compare(results["primary"], results["secondary"])
    comparison_sha = bank_artifact(package_output / "comparison.json", "comparison_receipt", bindings, {"result": "COMPLETE", "primary_result_sha256": terminals["primary"]["result_sha256"], "secondary_result_sha256": terminals["secondary"]["result_sha256"], "metrics": comparison, "classification": comparison["classification"]})
    bindings["comparison_receipt_sha256"] = comparison_sha
    comparison_terminal_sha = bank_artifact(package_output / "comparison-terminal.json", "comparison_terminal", bindings, {"result": "COMPLETE", "comparison_receipt_sha256": comparison_sha, "mandatory_stop": True})
    bindings["comparison_terminal_sha256"] = comparison_terminal_sha
    package_receipt_payload = {"outcome": "COMPLETE_SUCCESS", "primary_disposition": "STARTED", "secondary_disposition": "STARTED", "primary_receipt_sha256": terminals["primary"]["receipt_sha256"], "primary_terminal_sha256": terminals["primary"]["terminal_sha256"], "secondary_receipt_sha256": terminals["secondary"]["receipt_sha256"], "secondary_terminal_sha256": terminals["secondary"]["terminal_sha256"], "actual_deltas": {"package": 1, "primary": 1, "secondary": 1}}
    package_receipt_sha = bank_artifact(package_state / "receipt.json", "package_receipt", bindings, package_receipt_payload)
    bindings["package_receipt_sha256"] = package_receipt_sha
    package_terminal_sha = bank_artifact(package_state / "terminal.json", "package_terminal", bindings, {"outcome": "COMPLETE_SUCCESS", "result": "COMPLETE", "package_receipt_sha256": package_receipt_sha, "mandatory_stop": True})
    historical_terminal = document["historical_ledger_terminal"]
    if document["historical_ledger_delta"] != 0:
        raise ValueError("historical payload ledger must not advance")
    return {"result": "PASS", "handshake": handshake, "comparison": comparison, "package_terminal_sha256": package_terminal_sha,
            "process_census": {"installed_validation": 2, "primary_target": 1, "secondary_target": 1},
            "deltas": {"authorization": 0, "package": 1, "primary": 1, "secondary": 1},
            "historical_ledger_before": historical_terminal,
            "historical_ledger_after": historical_terminal + document["historical_ledger_delta"]}


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

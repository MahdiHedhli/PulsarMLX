#!/usr/bin/env python3
"""Fail-closed DPREFIX-REAL-1 execution-infrastructure validator.

This validator is checkpoint-free.  It prevents the authorization/package
preflight from being treated as proof that a reviewed candidate executable and
an instantiated independent-oracle package exist.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-execution-config-v2.json"
ORACLE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-oracle-package-v1.json"
AUTH_TOOL = ROOT / "scripts/research/f017_dense_prefix_40_read_authorization.py"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-not-executed-v1.json"
ATTEMPT_LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v1.json"
PAYLOAD_LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_checkpoint_free() -> dict:
    config = load(CONFIG)
    oracle = load(ORACLE)
    blockers: list[dict[str, str]] = []

    if not config.get("candidate_executable_sha256"):
        blockers.append({
            "code": "CANDIDATE_EXECUTABLE_UNBOUND",
            "detail": "execution config has no candidate executable content identity",
        })
    if not config.get("candidate_source_surface_sha256"):
        blockers.append({
            "code": "CANDIDATE_SOURCE_SURFACE_UNBOUND",
            "detail": "execution config has no reviewed production/native candidate source-surface identity",
        })
    if oracle.get("status") != "INSTANTIATED_FROZEN_BEFORE_CANDIDATE":
        blockers.append({
            "code": "ORACLE_PACKAGE_NOT_INSTANTIATED",
            "detail": f"oracle contract status is {oracle.get('status')!r}",
        })
    if not oracle.get("instantiated_package_sha256"):
        blockers.append({
            "code": "ORACLE_PACKAGE_IDENTITY_ABSENT",
            "detail": "oracle contract defines a future package but no instantiated package identity",
        })

    if not blockers:
        return {"result": "EXECUTION_INFRASTRUCTURE_READY", "checkpoint_reads": 0, "blockers": []}
    return {
        "result": "NOT_EXECUTED_INFRASTRUCTURE",
        "terminal_class": "INFRASTRUCTURE",
        "checkpoint_reads": 0,
        "attempt_consumed": False,
        "ledger": 59,
        "blockers": blockers,
        "bindings": {
            "execution_config_sha256": sha256(CONFIG),
            "oracle_contract_sha256": sha256(ORACLE),
            "authorization_tool_sha256": sha256(AUTH_TOOL),
        },
    }


def validate_banked_nonexecution() -> dict:
    evidence = load(EVIDENCE)
    attempt = load(ATTEMPT_LEDGER)["events"][-1]
    payload_ledger = load(PAYLOAD_LEDGER)
    q6_events = [event for event in payload_ledger["events"] if event.get("attempt") == "Q6K-REAL-1"]

    expected = {
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
        "payloads_read": 0,
        "ledger_before": 59,
        "ledger_after": 59,
    }
    state = evidence["state"]
    for key, value in expected.items():
        if state.get(key) != value:
            raise ValueError(f"evidence {key} mismatch")
    if evidence.get("attempt_id") != "DPREFIX-REAL-1":
        raise ValueError("evidence attempt_id mismatch")
    if evidence["terminal_class"] != "INFRASTRUCTURE" or evidence["verdict"] != "NOT_EXECUTED":
        raise ValueError("terminal evidence classification mismatch")
    if attempt.get("attempt_id") != "DPREFIX-REAL-1":
        raise ValueError("attempt-ledger ID mismatch")
    for key in ("consumed", "executed", "checkpoint_accessed", "ledger_before"):
        if attempt.get(key) != expected[key]:
            raise ValueError(f"attempt-ledger {key} mismatch")
    if attempt.get("actual_payload_reads") != 0:
        raise ValueError("attempt-ledger payload mismatch")
    if attempt.get("status") != "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW":
        raise ValueError("attempt-ledger preserved-state mismatch")
    if sha256(ATTEMPT_LEDGER) != evidence["preserved_bindings"]["attempt_ledger_sha256_before"]:
        raise ValueError("attempt-ledger immutable identity mismatch")
    if payload_ledger.get("cumulative_tensor_payloads") != sum(
        event["tensor_payload_count"] for event in payload_ledger["events"]
    ):
        raise ValueError("payload-ledger cumulative total mismatch")
    if len(q6_events) != 1 or q6_events[0].get("cumulative_tensor_payloads_after_event") != 59:
        raise ValueError("payload-ledger Q6 boundary mismatch")
    if any(event.get("evidence", {}).get("sha256") == sha256(EVIDENCE) for event in payload_ledger["events"]):
        raise ValueError("zero-read evidence must not add a payload event")
    return {
        "result": "BANKED_NONEXECUTION_RECONCILED",
        "terminal_class": "INFRASTRUCTURE",
        "payloads": 0,
        "ledger": 59,
        "checkpoint_reads": 0,
    }


def main() -> None:
    print(json.dumps({"infrastructure": validate_checkpoint_free(), "banked": validate_banked_nonexecution()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

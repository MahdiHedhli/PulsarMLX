#!/usr/bin/env python3
"""Independent, non-generated lifecycle-V6 correspondence checker.

This checker deliberately imports neither lifecycle semantics nor generator
code.  It replays the transition graph and checks the generated registry and
matrix as hostile inputs against fixed semantic rules.
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
MODEL = CONTRACTS / "f017-corrected-oracle-lifecycle-semantic-model-v6.json"
REGISTRY = CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v6.json"
MATRIX = CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v6.json"
INTERFACE = CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v6.json"


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    if type(value) is not dict:
        raise ValueError("object required")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reachable(states: set[str], transitions: list[dict], initial: str) -> set[str]:
    graph: dict[str, set[str]] = {state: set() for state in states}
    for transition in transitions:
        graph[transition["source"]].add(transition["destination"])
    seen = {initial}; queue = deque([initial])
    while queue:
        for destination in graph[queue.popleft()]:
            if destination not in seen:
                seen.add(destination); queue.append(destination)
    return seen


def validate() -> dict:
    model = _load(MODEL); registry = _load(REGISTRY); matrix = _load(MATRIX); interface = _load(INTERFACE)
    states = set(model["states"]); actors = set(model["actors"]); transitions = model["transitions"]
    transition_ids = {item["id"] for item in transitions}
    if len(transition_ids) != len(transitions):
        raise ValueError("duplicate transition")
    for transition in transitions:
        if transition["source"] not in states or transition["destination"] not in states or transition["actor"] not in actors:
            raise ValueError("transition references unknown state or actor")
    if _reachable(states, transitions, model["initial_state"]) != states:
        raise ValueError("unreachable lifecycle state")
    if any("P1" in state or "P1" in transition["destination"] for state in states for transition in transitions):
        raise ValueError("P1 state reachable")
    routed = set(model["failure_routes"])
    required_routes = {item["id"] for item in transitions if item["failure_outcome"] != "EVIDENCE_BANKING_FAILURE"}
    if routed != required_routes or any(route not in transition_ids for route in model["failure_routes"].values()):
        raise ValueError("failure routes are not total")
    expected_accounting = {
        "HISTORICAL_REAL_PAYLOAD_LEDGER": (None, 0),
        "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER": ("T11_START_PACKAGE", 1),
        "CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER": ("T12_START_PRIMARY", 1),
        "CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER": ("T14_START_SECONDARY", 1),
    }
    for name, (transition, delta) in expected_accounting.items():
        item = model["ledger_targets"][name]
        if item["advance_transition"] != transition or item["delta"] != delta:
            raise ValueError("accounting mismatch")
    pairs = model["authorization_document"]["authority_path_sha_pairs"]
    if interface.get("authority_path_sha_pairs") != pairs or len(pairs) != 13:
        raise ValueError("authority path/SHA projection")
    for transition in transitions:
        if transition["id"] in {"T03_RENDER_CANDIDATE", "T04_PRIMARY_VALIDATE_CANDIDATE", "T05_SECONDARY_VALIDATE_CANDIDATE", "T06_INSTALL_AUTHORIZATION"} and "ALL_AUTHORITY_PATH_SHA_PAIRS_MATCH_EXACT_READBACK_BYTES" not in transition["preconditions"]:
            raise ValueError("authority-byte gate absent")
    identities = registry["identities"]
    if registry["identity_count"] != len(identities) or len({item["name"] for item in identities}) != len(identities):
        raise ValueError("identity registry census")
    exact_fields = {"source", "equality_rule", "validator", "failure_classification", "json_path", "type", "required_outcomes"}
    rows = matrix["rows"]
    if matrix["row_count"] != len(rows) or {row["identity"] for row in rows} != {item["name"] for item in identities}:
        raise ValueError("matrix/registry identity correspondence")
    for row in rows:
        for cell in row["cells"].values():
            if set(cell) != exact_fields or cell["equality_rule"] not in {"EXACT_TYPED_EQUALITY_TO_FIRST_INTRODUCTION", None}:
                raise ValueError("matrix semantic column drift")
            if cell["failure_classification"] in {"WARN_ONLY", "IGNORE"} or "attacker" in (cell["validator"] or "").lower():
                raise ValueError("fail-open matrix cell")
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-independent-lifecycle-check/1.0.0",
        "result": "PASS",
        "model_sha256": _sha(MODEL),
        "registry_sha256": _sha(REGISTRY),
        "matrix_sha256": _sha(MATRIX),
        "states": len(states),
        "transitions": len(transitions),
        "identities": len(identities),
        "imports_generator_or_semantic_derivation": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))

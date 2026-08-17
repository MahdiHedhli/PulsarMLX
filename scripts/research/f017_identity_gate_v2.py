#!/usr/bin/env python3
"""Validator for F017 identity-gate contract v2."""

from __future__ import annotations

from typing import Any

CLASSES = {"EXACT_CLASS", "BOUNDED_CLASS", "PERSISTED_AUTHORITY"}
REQUIRED = {
    "gate_id", "artifact", "reproducibility_class", "mechanism", "scope",
    "environment_requirements", "comparison_rule", "failure_rule",
}


def validate_gate(gate: dict[str, Any]) -> None:
    if set(gate) != REQUIRED:
        raise ValueError("identity gate fields")
    if gate["reproducibility_class"] not in CLASSES:
        raise ValueError("identity gate class")
    if not all(isinstance(gate[field], str) and gate[field].strip() for field in REQUIRED):
        raise ValueError("identity gate mechanism completeness")
    rule = gate["comparison_rule"]
    kind = gate["reproducibility_class"]
    if kind == "BOUNDED_CLASS" and rule.strip() == "SHA-256 exact equality":
        raise ValueError("bounded artifact exact-SHA gate")
    if kind == "EXACT_CLASS" and "SHA-256 exact equality" not in rule:
        raise ValueError("exact artifact lacks exact comparison")
    if kind == "PERSISTED_AUTHORITY" and "persisted object SHA" not in rule:
        raise ValueError("persisted authority comparison")


def validate_contract(document: dict[str, Any]) -> None:
    if document.get("schema") != "pulsarmlx.f017.identity-gate-contract" or document.get("schema_version") != "2.0.0":
        raise ValueError("identity gate contract identity")
    gates = document.get("gate_audit")
    if not isinstance(gates, list) or not gates:
        raise ValueError("identity gate audit absent")
    seen: set[str] = set()
    for gate in gates:
        validate_gate(gate)
        if gate["gate_id"] in seen:
            raise ValueError("duplicate identity gate")
        seen.add(gate["gate_id"])
    if not document.get("historical_real3_rejected_unchanged"):
        raise ValueError("historical REAL-3 mutation")

#!/usr/bin/env python3
"""Runtime construction and strict validation of V6 lifecycle artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from f017_corrected_oracle_authorization_v6 import ROOT, strict_bytes
from f017_corrected_oracle_wrapper_support_v6 import bank

SCHEMAS = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-artifact-schemas-v6.json"
SUCCESS_OUTCOME = "TERMINAL::COMPLETE_SUCCESS"


def authorization_bindings(document: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: value for key, value in document.items()
        if key not in {"schema", "state", "live", "package", "primary", "secondary", "context", "limits", "shards"}
    }
    result.update({
        "authorization_schema": document["schema"],
        "authorization_state": document["state"],
        "authorization_live": document["live"],
    })
    for prefix in ("package", "primary", "secondary"):
        result.update({f"{prefix}_{key}": value for key, value in document[prefix].items()})
    result.update(document["context"])
    result.update(document["limits"])
    # The authorization names the memory-preflight bytes; the semantic model
    # names their artifact readback identity explicitly.
    result["preflight_report_sha256"] = document["memory_preflight_sha256"]
    return result


def artifact_document(
    kind: str,
    bindings: dict[str, Any],
    payload: dict[str, Any],
    *,
    outcome: str = SUCCESS_OUTCOME,
) -> dict[str, Any]:
    authority = strict_bytes(SCHEMAS.read_bytes())
    schema = authority["artifacts"].get(kind)
    if schema is None:
        raise ValueError(f"unknown lifecycle artifact kind: {kind}")
    required = sorted(
        name for name, outcomes in schema["identity_required_outcomes"].items()
        if outcome in outcomes
    )
    missing = [name for name in required if name not in bindings]
    if missing:
        raise ValueError(f"missing lifecycle bindings for {kind}: {missing}")
    selected = {name: bindings[name] for name in required}
    if set(payload) != set(schema["payload_key_census"]):
        raise ValueError(f"payload key census for {kind}")
    for key, path in schema["payload_binding_equality"].items():
        prefix = "$.bindings."
        if not path.startswith(prefix) or payload[key] != selected[path[len(prefix):]]:
            raise ValueError(f"payload/binding mismatch for {kind}/{key}")
    return {"schema": schema["artifact_schema_id"], "bindings": selected, "payload": payload}


def bank_artifact(
    path: Path,
    kind: str,
    bindings: dict[str, Any],
    payload: dict[str, Any],
    *,
    outcome: str = SUCCESS_OUTCOME,
) -> str:
    value = artifact_document(kind, bindings, payload, outcome=outcome)
    return bank(path, value)

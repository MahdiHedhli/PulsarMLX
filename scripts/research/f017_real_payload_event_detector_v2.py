#!/usr/bin/env python3
"""Schema-based discovery of future real-payload advancing events."""

from __future__ import annotations
from dataclasses import dataclass
import json


class EventDetectionError(RuntimeError):
    pass


ADVANCING_SCHEMAS = {
    "pulsarmlx.f017.representative-m1f0-real-execution-result",
    "pulsarmlx.f017.real-payload-event-result",
}
ADVANCING_SEMANTIC_TYPE = "REAL_PAYLOAD_ADVANCING_EVENT"


def unique(items):
    out = {}
    for key, value in items:
        if key in out:
            raise EventDetectionError(f"duplicate key: {key}")
        out[key] = value
    return out


def strict_int(value, name):
    if type(value) is not int:
        raise EventDetectionError(f"{name} must be strict integer")
    return value


@dataclass(frozen=True)
class AdvancingEvent:
    event_id: str
    ledger_before: int
    ledger_after: int
    consumed_reads: int
    receipt_count: int


def detect(raw: bytes) -> AdvancingEvent | None:
    try:
        document = json.loads(raw, object_pairs_hook=unique)
    except json.JSONDecodeError as exc:
        raise EventDetectionError(str(exc)) from exc
    if not isinstance(document, dict):
        return None
    recognized = (
        document.get("schema") in ADVANCING_SCHEMAS
        or document.get("semantic_type") == ADVANCING_SEMANTIC_TYPE
    )
    accounting_candidate = document.get("access_accounting")
    if not recognized:
        if isinstance(accounting_candidate, dict):
            before = accounting_candidate.get("ledger_before")
            after = accounting_candidate.get("ledger_after")
            reads = accounting_candidate.get("consumed_reads")
            if all(type(value) is int for value in (before, after, reads)) and after > before and reads > 0:
                raise EventDetectionError("unrecognized advancing event schema")
        return None
    accounting = document.get("access_accounting")
    receipts = document.get("receipts")
    if not isinstance(accounting, dict) or not isinstance(receipts, list):
        raise EventDetectionError("event/result/receipt relationship")
    before = strict_int(accounting.get("ledger_before"), "ledger_before")
    after = strict_int(accounting.get("ledger_after"), "ledger_after")
    consumed = strict_int(accounting.get("consumed_reads"), "consumed_reads")
    if consumed <= 0 or after != before + consumed or len(receipts) != consumed:
        raise EventDetectionError("advancing continuity")
    ordinals = [strict_int(row.get("ordinal"), "receipt.ordinal") for row in receipts if isinstance(row, dict)]
    counts = [strict_int(row.get("ledger_after"), "receipt.ledger_after") for row in receipts if isinstance(row, dict)]
    if len(ordinals) != consumed or ordinals != list(range(consumed)) or counts != list(range(before + 1, after + 1)):
        raise EventDetectionError("receipt continuity")
    event_id = document.get("event_id") or document.get("attempt_id") or document.get("event", {}).get("event_id")
    if not isinstance(event_id, str) or not event_id or any(ch.isspace() for ch in event_id):
        raise EventDetectionError("event identity")
    receipt_ids = [row.get("receipt_sha256") for row in receipts]
    if any(not isinstance(value, str) or len(value) != 64 for value in receipt_ids) or len(set(receipt_ids)) != consumed:
        raise EventDetectionError("receipt identity")
    return AdvancingEvent(event_id, before, after, consumed, len(receipts))

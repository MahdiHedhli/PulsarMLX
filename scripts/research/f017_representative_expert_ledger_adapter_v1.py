#!/usr/bin/env python3
"""Exact committed ledger-175 adapter for retained-only expert recovery."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"
SOURCE_SHA256 = "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190"

class LedgerError(RuntimeError): pass
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def current_ledger(root: Path = ROOT) -> int:
    path = root / SOURCE.relative_to(ROOT)
    if not path.is_file() or sha(path) != SOURCE_SHA256: raise LedgerError("LEDGER_SOURCE_IDENTITY")
    doc = json.loads(path.read_text(), object_pairs_hook=lambda pairs: _unique(pairs))
    if doc.get("schema") != "pulsarmlx.f017.representative-m1f0-real-execution-result" or doc.get("schema_version") != "1.0.0": raise LedgerError("LEDGER_SOURCE_SCHEMA")
    accounting = doc.get("access_accounting")
    receipts = doc.get("receipts")
    if not isinstance(accounting, dict) or accounting.get("ledger_before") != 166 or accounting.get("ledger_after") != 175: raise LedgerError("LEDGER_ACCOUNTING")
    if accounting.get("consumed_reads") != 9 or accounting.get("packed_bytes_consumed") != 132900864: raise LedgerError("LEDGER_ACCOUNTING")
    if not isinstance(receipts, list) or len(receipts) != 9 or [r.get("ledger_after") for r in receipts] != list(range(167,176)): raise LedgerError("LEDGER_RECEIPTS")
    if doc.get("terminal", {}).get("status") != "COMPLETE": raise LedgerError("LEDGER_TERMINAL")
    return 175
def _unique(pairs):
    out = {}
    for k,v in pairs:
        if k in out: raise LedgerError("DUPLICATE_KEY")
        out[k]=v
    return out
if __name__ == "__main__": print(json.dumps({"result":"PASS","current_ledger":current_ledger(),"checkpoint_reads":0,"shard_opens":0},sort_keys=True))

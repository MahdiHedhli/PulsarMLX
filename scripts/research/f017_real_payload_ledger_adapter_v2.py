#!/usr/bin/env python3
"""Current authoritative F017 ledger adapter, receipt-reconciled at 175."""

from __future__ import annotations

import json
import pathlib

from f017_bound_authority_resolver_v1 import load_json, validate_bound_fields


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-real-payload-ledger-adapter-v2.json"


def current_ledger(root: pathlib.Path = ROOT) -> int:
    contract = load_json(root / CONTRACT.relative_to(ROOT))
    if contract.get("schema") != "pulsarmlx.f017.real-payload-ledger-adapter" or contract.get("schema_version") != "2.0.0":
        raise RuntimeError("LEDGER_ADAPTER_SCHEMA")
    observations = validate_bound_fields(root, contract)
    values = {item["resolved"] for item in observations}
    if values != {175} or contract.get("expected_current_ledger") != 175 or contract.get("source_agreement_required") is not True:
        raise RuntimeError("LEDGER_SOURCE_DISAGREEMENT")
    return 175


if __name__ == "__main__":
    print(json.dumps({"result":"PASS","current_ledger":current_ledger(),"checkpoint_reads":0,"shard_opens":0}, sort_keys=True))

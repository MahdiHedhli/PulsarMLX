#!/usr/bin/env python3
"""Check that bridge contracts and implementation censuses remain identical."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from f017_event06_numerical_bridge_v1 import BRIDGE_KEYS, PHASES, VIEW_KEYS

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-numerical-authority-bridge-v2.json"
SUCCESSOR = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-numerical-authority-bridge-v3.json"


def check() -> dict:
    base = json.loads(CONTRACT.read_text()); successor = json.loads(SUCCESSOR.read_text())
    if set(base["canonical_document"]["fields"]) != BRIDGE_KEYS:
        raise ValueError("bridge contract/implementation census")
    for role, fields in successor["consumer_views"].items():
        if set(fields) != VIEW_KEYS[role]:
            raise ValueError(f"bridge view contract/implementation: {role}")
    if tuple(base["transition_binding_journal"]["phases"]) != PHASES:
        raise ValueError("bridge phase contract/implementation")
    return {"result":"PASS","bridge_fields":len(BRIDGE_KEYS),"consumer_views":len(VIEW_KEYS),
            "transition_phases":len(PHASES)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(); print(json.dumps(check(), sort_keys=True, separators=(",",":")))

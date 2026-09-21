#!/usr/bin/env python3
"""Deterministic consistency check for V12 identity-authority sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from f017_checkpoint_identity_authority_v12 import CANDIDATE_KEYS, INSTALLED_EXTRA_KEYS
from f017_checkpoint_identity_capability_v12 import validate_capability
from f017_checkpoint_identity_lifecycle_v12 import OUTCOMES, OUTCOME_DETAILS
from f017_event06_readiness_authority_v1 import CONTRACT as READINESS_CONTRACT
from rehearse_f017_event06_no_access_v12 import rehearse

ROOT = Path(__file__).resolve().parents[2]


def check() -> dict:
    contract = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-authority-v12.json").read_text())
    lifecycle = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-lifecycle-outcomes-v12.json").read_text())
    if contract["candidate_field_count"] != len(CANDIDATE_KEYS):
        raise ValueError("V12 candidate field census")
    if contract["installed_field_count"] != len(CANDIDATE_KEYS | INSTALLED_EXTRA_KEYS):
        raise ValueError("V12 installed field census")
    if set(lifecycle["modeled_outcomes"]) != set(OUTCOMES):
        raise ValueError("V12 lifecycle outcome census")
    failure_transitions = {details[0] for details in OUTCOME_DETAILS.values()}
    if set(lifecycle.get("modeled_failure_transitions", ())) != failure_transitions:
        raise ValueError("V12 lifecycle failure transition census")
    if not failure_transitions.issubset(set(lifecycle["ordered_transitions"])):
        raise ValueError("V12 lifecycle ordered transition coverage")
    if lifecycle["modeled_outcomes_use_generic_fallback"] is not False:
        raise ValueError("V12 modeled fallback policy")
    readiness = json.loads(READINESS_CONTRACT.read_text())
    typed_readiness = {name for names in readiness["exact_types"].values() for name in names}
    if set(readiness["required_fields"]) != typed_readiness or readiness.get("unknown_keys_permitted") is not False:
        raise ValueError("V12 Event 06 readiness interface census")
    historical = {
        "scripts/research/f017_checkpoint_identity_producer_v10.py":"d33fd06705245b0f623e46b828bd20373fa2e691834918a2f715f50731b2cc9f",
        "scripts/research/execute_f017_corrected_oracle_event_v11.py":"967c1d5566e9faae801d1641c9839497d9ecc79aae28b34f1d6dba6679aba1fe",
    }
    for relative, expected in historical.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("historical V10/V11 identity bytes changed")
    capability = validate_capability()
    rehearsal = rehearse()
    return {
        "candidate_fields":len(CANDIDATE_KEYS), "installed_fields":len(CANDIDATE_KEYS | INSTALLED_EXTRA_KEYS),
        "modeled_outcomes":len(OUTCOMES), "capability":capability["result"],
        "readiness_fields":len(readiness["required_fields"]),
        "no_access_rehearsal":rehearsal["result"], "original_checkpoint_access":0,
        "result":"PASS",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(check(), sort_keys=True, separators=(",", ":")))

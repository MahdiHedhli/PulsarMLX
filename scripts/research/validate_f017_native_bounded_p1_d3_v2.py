#!/usr/bin/env python3
"""Validate the append-only instantiable F017 native D3 architecture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D3 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-execution-architecture-v2.json"
P1 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json"


def strict(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key: {key}")
        out[key] = value
    return out


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(), object_pairs_hook=strict)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    d3, p1 = load(D3), load(P1)
    if d3["schema"] != "pulsarmlx.f017.native-bounded-p1-execution-architecture" or d3["schema_version"] != "2.0.0":
        raise SystemExit("D3-v2 schema")
    if d3["status"] != "FULL_PRODUCER_INSTANTIABLE_REAL_P1_HUMAN_AUTHORIZATION_NOT_CREATED":
        raise SystemExit("D3-v2 status")
    if p1["authorities"]["execution_architecture"] != {
        "path": str(D3.relative_to(ROOT)), "sha256": sha(D3)
    }:
        raise SystemExit("admission contract does not bind D3-v2")
    code = {row["path"] for row in p1["code_manifest"]}
    producer = d3["producer"]
    for value in producer.values():
        path = str(value).split("::", 1)[0]
        if path not in code:
            raise SystemExit(f"producer source not in exact code manifest: {path}")
    graph = d3["graph"]
    if graph != {
        "model": "GLM-5.2", "layers": 79, "checkpoint_tensors": 1809,
        "checkpoint_shards": 6, "prompt_token": 9703,
        "expected_first_output_token": 21615, "generated_token_limit": 1,
        "initial_kv_state": "EMPTY_CLEAN_PROCESS", "sequence_position": 0,
        "continuation": False,
    }:
        raise SystemExit("bounded graph")
    lifecycle = d3["attempt_lifecycle"]
    if lifecycle != {
        "claim": "EXCLUSIVE_OWNED_DURABLE_CLAIM_BEFORE_EXECUTION",
        "terminalizer": "THIS_INVOCATION_ONLY",
        "terminal_receipt_census": "REQUIRED_AND_FAIL_CLOSED",
        "attempts": 1, "retries": 0, "resume": False, "mandatory_stop": True,
    }:
        raise SystemExit("RN1 lifecycle")
    mock = d3["mock_boundary"]
    if mock["substituted"] != "TENSOR_MATH_ONLY" or mock["checkpoint_reachable"] or mock["fresh_processes"] != 10 or mock["result"] != "PASS":
        raise SystemExit("math-only mock")
    scope = d3["retained_qualification_scope"]
    if scope["qualified"] != "REPRESENTATIVE_LAYER3_S0_TO_S2_SURFACE" or scope["not_qualified"] != "REMAINING_FULL_79_LAYER_FORWARD" or scope["production_equivalence_overclaim"]:
        raise SystemExit("scope honesty")
    accounting = d3["accounting"]
    if accounting["historical_master_ledger_sha256"] != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e" or accounting["historical_terminal_value"] != 175 or accounting["historical_payload_delta"] != 0 or accounting["native_event_delta"] != 1:
        raise SystemExit("accounting")
    if any(d3["phase_invariants"].values()) or p1["live_authorization_present"] or p1["normal_validation_can_authorize"]:
        raise SystemExit("phase invariants")
    print(f"PASS: instantiable D3-v2 bound by admission contract {sha(P1)}")


if __name__ == "__main__":
    main()

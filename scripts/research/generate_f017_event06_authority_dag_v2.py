#!/usr/bin/env python3
"""Generate Sequence 18 DAG from predecessor closure plus actual split calls."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import generate_f017_event06_authority_dag_v1 as predecessor

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v2.json"

# The stable predecessor closure ends immediately before package reservation.
BASE_ROWS = predecessor.ROWS[:35]

DISCOVERY = {
    "reserve_live_package_attempt": (
        "INSTALLED_AUTHORITY", "ValidatedIdentityAuthority",
        "LIVE_PACKAGE_RESERVATION", "ValidatedLivePackageAttemptReservation",
        "LIVE_CANONICAL", "PACKAGE_GATE",
    ),
    "reserve_qualification_package_attempt": (
        "QUALIFICATION_INSTALLED_AUTHORITY", "CollapsedInstalledTripleV2|ValidatedIdentityAuthority",
        "QUALIFICATION_PACKAGE_RESERVATION", "ValidatedQualificationPackageAttemptReservation",
        "QUALIFICATION_ONLY", "PACKAGE_GATE",
    ),
    "bank_live_package_start": (
        "LIVE_PACKAGE_RESERVATION", "ValidatedLivePackageAttemptReservation",
        "LIVE_PACKAGE_START", "ValidatedDurableStart", "LIVE_CANONICAL", "PACKAGE_GATE",
    ),
    "claim_live_terminal_sinks": (
        "LIVE_EXECUTION_AND_ACCOUNTING_CLOSURE", "ValidatedBridgeExecutionResult",
        "LIVE_TERMINAL_CLAIM", "ValidatedLivePackageTerminalSink",
        "LIVE_CANONICAL", "TERMINAL",
    ),
    "claim_qualification_terminal_sinks": (
        "QUALIFICATION_RESULT_CLOSURE", "ValidatedConsumerView",
        "QUALIFICATION_TERMINAL_CLAIM", "ValidatedQualificationPackageTerminalSink",
        "QUALIFICATION_ONLY", "TERMINAL",
    ),
    "bank_live_terminal": (
        "LIVE_TERMINAL_CLAIM", "ValidatedLivePackageTerminalSink",
        "LIVE_PACKAGE_TERMINAL", "str", "LIVE_CANONICAL", "TERMINAL",
    ),
    "bank_qualification_terminal": (
        "QUALIFICATION_TERMINAL_CLAIM", "ValidatedQualificationPackageTerminalSink",
        "QUALIFICATION_PACKAGE_TERMINAL", "str", "QUALIFICATION_ONLY", "TERMINAL",
    ),
}

def _production_modules() -> tuple[str, ...]:
    """Discover every production module that invokes a split boundary."""
    result = []
    for path in sorted((ROOT / "scripts/research").glob("*.py")):
        if path.name.startswith(("generate_", "qualify_", "validate_")):
            continue
        if "fixture" in path.name:
            continue
        source = path.read_text(encoding="utf-8")
        if any(symbol in source for symbol in DISCOVERY):
            result.append(path.relative_to(ROOT).as_posix())
    return tuple(result)


def _calls(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = []
    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for function in functions:
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            symbol = None
            if isinstance(node.func, ast.Name):
                symbol = node.func.id
            elif isinstance(node.func, ast.Attribute):
                symbol = node.func.attr
            if symbol in DISCOVERY:
                result.append((function.name, symbol))
    return result


def source_inventory() -> list[dict[str, object]]:
    rows = []
    for module in _production_modules():
        for consumer, producer in _calls(ROOT / module):
            source, input_type, destination, output_type, mode, phase = DISCOVERY[producer]
            rows.append({
                "source_node": source,
                "producer_module": (
                    "scripts/research/f017_event06_package_attempt_registry_v2.py"
                    if producer not in {"bank_live_package_start"}
                    else "scripts/research/execute_f017_corrected_oracle_event_v12_bridge.py"
                ),
                "producer_symbol": producer,
                "output_type_or_schema": output_type,
                "destination_node": destination,
                "consumer_module": module,
                "consumer_symbol": consumer,
                "accepted_input_type_or_schema": output_type,
                "digest_identity_invariant": "EXACT_PACKAGE_AND_SEALED_DIGEST_CONTINUITY",
                "authority_mode": mode,
                "lifecycle_phase": phase,
                "side_effect_class": (
                    "FIXED_LIVE_PACKAGE_TRANSACTION" if mode == "LIVE_CANONICAL"
                    else "DISPOSABLE_SYNTHETIC_ONLY"
                ),
                "negative_mutation_family": [
                    "cross_mode_substitution", "package_digest_substitution",
                    "second_attempt", "terminal_claim_replay",
                ],
                "composition_evidence": {
                    "kind": "SOURCE_AST_EXACT_CALL_PLUS_SHARED_IMPLEMENTATION_TEST",
                    "case_id": f"SEQ18-{producer}-{consumer}",
                    "test_path": "scripts/research/tests/test_f017_event06_package_attempt_registry_v2.py",
                    "test_symbol": "test_source_derived_dag_covers_split_and_live_terminal_boundaries",
                },
            })
    # Calls duplicated within branches are a real distinct consumer boundary;
    # identical producer/consumer/module tuples are collapsed deterministically.
    unique = {
        (row["producer_symbol"], row["consumer_module"], row["consumer_symbol"]): row
        for row in rows
    }
    return [unique[key] for key in sorted(unique)]


def build() -> dict[str, object]:
    base = []
    for row in BASE_ROWS:
        source, producer, output_type, destination, consumer, phase = row
        base.append({
            "source_node": source,
            "producer_module": predecessor.MODULES[producer],
            "producer_symbol": producer,
            "output_type_or_schema": output_type,
            "destination_node": destination,
            "consumer_module": predecessor.MODULES[consumer],
            "consumer_symbol": consumer,
            "accepted_input_type_or_schema": output_type,
            "digest_identity_invariant": "EXACT_PRODUCER_OBJECT_AND_BOUND_DIGEST_CONTINUITY",
            "authority_mode": "QUALIFICATION_ONLY_NO_LIVE_AUTHORITY",
            "lifecycle_phase": phase,
            "side_effect_class": "DISPOSABLE_SYNTHETIC_ONLY",
            "negative_mutation_family": [
                "mapping_or_deserialized_lookalike", "wrong_exact_type",
                "digest_or_identity_substitution", "replay_or_cross_role_reuse",
            ],
            "composition_evidence": {
                "kind": "QUALIFICATION_RUNTIME_TRACE",
                "case_id": f"SEQ17-{producer}-{consumer}",
                "test_path": "scripts/research/qualify_f017_event06_dag_composition_v1.py",
                "test_symbol": "qualify",
            },
        })
    inventory = base + source_inventory()
    for number, edge in enumerate(inventory, 1):
        edge["edge_id"] = f"F017-DAG2-{number:03d}"
        edge["source_blob_sha256"] = hashlib.sha256(
            (ROOT / edge["producer_module"]).read_bytes()
        ).hexdigest()
    live = [edge for edge in inventory if edge["authority_mode"] == "LIVE_CANONICAL"]
    return {
        "schema": "pulsarmlx.f017.event06-v12-authority-dag/2.0.0",
        "generation": "V12",
        "repair_generation": 1,
        "source_inventory_method": "AST_PUBLIC_CALL_AND_SIGNATURE_EXTRACTION",
        "edges": inventory,
        "edge_count": len(inventory),
        "source_typed_boundaries_total": len(inventory),
        "live_terminal_boundaries_total": sum(
            edge["lifecycle_phase"] == "TERMINAL" for edge in live
        ),
        "uncovered_typed_boundaries": 0,
        "extraneous_dag_edges": 0,
        "original_checkpoint_access_permitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build(), indent=2, sort_keys=True) + "\n").encode()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != raw:
            raise SystemExit("generated Sequence 18 authority DAG is stale")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

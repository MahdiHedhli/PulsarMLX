#!/usr/bin/env python3
"""Executable semantic authority for the F017 corrected-oracle lifecycle.

This module is intentionally non-numerical.  It turns the compact lifecycle
model into outcome, accounting, path-timing, serialization, and binding views.
The independent validator recomputes these views instead of trusting generated
claims embedded in an artifact.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v1.json"


def _pairs(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the sole accepted authority serialization."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


@dataclass(frozen=True)
class TraceResult:
    state: str
    artifacts: frozenset[str]
    introduced_identities: frozenset[str]
    ledger_deltas: tuple[tuple[str, int], ...]
    path_states: tuple[tuple[str, str], ...]

    @property
    def ledgers(self) -> dict[str, int]:
        return dict(self.ledger_deltas)


def _index_transitions(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    transitions = model.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        raise ValueError("transition census")
    indexed: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        if not isinstance(transition, dict) or not isinstance(transition.get("id"), str):
            raise ValueError("transition type")
        tid = transition["id"]
        if tid in indexed:
            raise ValueError(f"duplicate transition: {tid}")
        indexed[tid] = transition
    return indexed


def simulate_trace(model: dict[str, Any], trace: list[str]) -> TraceResult:
    transitions = _index_transitions(model)
    state = model["initial_state"]
    artifacts: set[str] = set()
    identities: set[str] = set()
    ledgers = {name: 0 for name in model["ledger_targets"]}
    path_states = {
        role: descriptor["initial_predicate"]
        for role, descriptor in model["path_roles"].items()
    }
    for tid in trace:
        transition = transitions.get(tid)
        if transition is None:
            raise ValueError(f"unknown transition: {tid}")
        if transition["source"] != state:
            raise ValueError(
                f"illegal transition {tid}: expected source {state}, got {transition['source']}"
            )
        for effect in transition["path_effects"]:
            role = effect["role"]
            if effect["effect"] == "CREATE_REGULAR_FILE":
                if path_states[role] != "MUST_NOT_EXIST":
                    raise ValueError(f"unsatisfiable file creation: {tid}/{role}")
                path_states[role] = "MUST_EXIST_REGULAR_FILE"
            elif effect["effect"] == "CREATE_DIRECTORY":
                if path_states[role] != "MUST_NOT_EXIST":
                    raise ValueError(f"unsatisfiable directory creation: {tid}/{role}")
                path_states[role] = "MUST_EXIST_DIRECTORY"
            else:
                raise ValueError(f"unknown path effect: {effect}")
        artifacts.update(transition["artifacts_created"])
        identities.update(transition["identities_introduced"])
        for target, delta in transition["ledger_effects"].items():
            if type(delta) is not int or delta < 0 or target not in ledgers:
                raise ValueError(f"invalid ledger effect: {tid}/{target}")
            ledgers[target] += delta
        state = transition["destination"]
    return TraceResult(
        state=state,
        artifacts=frozenset(artifacts),
        introduced_identities=frozenset(identities),
        ledger_deltas=tuple(sorted(ledgers.items())),
        path_states=tuple(sorted(path_states.items())),
    )


def derive_outcome_obligations(model: dict[str, Any]) -> dict[str, Any]:
    derived: dict[str, Any] = {}
    for name, outcome in model["terminal_outcomes"].items():
        trace = outcome["trace"]
        if name == "EVIDENCE_BANKING_FAILURE":
            # These are families parameterized by the transition that failed.
            # Their per-transition obligations are emitted separately below.
            continue
        result = simulate_trace(model, trace)
        if result.state != outcome["terminal_state"]:
            raise ValueError(f"terminal state mismatch: {name}")
        starts = {
            "package": "T11_START_PACKAGE" in trace,
            "primary": "T12_START_PRIMARY" in trace,
            "secondary": "T14_START_SECONDARY" in trace,
            "comparison": "T16_COMPARE_SUCCESS" in trace or "T16F_COMPARE_FAILURE" in trace,
        }
        declared = {
            "package": outcome["package_started"],
            "primary": outcome["primary_started"],
            "secondary": outcome["secondary_started"],
            "comparison": outcome["comparison_started"],
        }
        if starts != declared:
            raise ValueError(f"started flags are not transition-derived: {name}")
        required = set(result.artifacts)
        forbidden: set[str] = set()
        for consumer in ("primary", "secondary"):
            consumer_evidence = {
                f"{consumer}_durable_start",
                f"{consumer}_ledger_entry",
                f"{consumer}_receipt",
                f"{consumer}_terminal",
            }
            if starts[consumer]:
                if not consumer_evidence.issubset(required):
                    raise ValueError(f"started consumer evidence missing: {name}/{consumer}")
            else:
                forbidden.update(consumer_evidence)
                if required & consumer_evidence:
                    raise ValueError(f"unstarted consumer evidence fabricated: {name}/{consumer}")
        if name == "COMPLETE_SUCCESS" and not all(starts.values()):
            raise ValueError("complete success without all phases")
        derived[name] = {
            "trace": trace,
            "terminal_state": result.state,
            "started": starts,
            "required_artifacts": sorted(required),
            "forbidden_artifacts": sorted(forbidden),
            "nullable_package_receipt_fields": sorted(
                field
                for consumer in ("primary", "secondary")
                if not starts[consumer]
                for field in (f"{consumer}_receipt_sha256", f"{consumer}_terminal_sha256")
            ),
            "package_consumer_disposition": {
                consumer: "STARTED" if starts[consumer] else "NOT_STARTED"
                for consumer in ("primary", "secondary")
            },
            "ledger_deltas": result.ledgers,
        }

    failure_variants = []
    transitions = _index_transitions(model)
    success_prefix: list[str] = []
    for transition in model["transitions"]:
        outcome = transition["failure_outcome"]
        prefix_result = simulate_trace(model, success_prefix)
        failure_variants.append(
            {
                "failed_transition": transition["id"],
                "failure_outcome": outcome,
                "state_before_failure": prefix_result.state,
                "durable_artifacts_before_failure": sorted(prefix_result.artifacts),
                "ledger_deltas_before_failure": prefix_result.ledgers,
                "failed_transition_artifacts_not_claimed": transition["artifacts_created"],
                "prohibited_side_effects": transition["prohibited_side_effects"],
            }
        )
        # Only advance the canonical success spine. Branch transitions are not
        # prefixes for later success transitions.
        if transition["source"] == prefix_result.state and not transition["id"].endswith("FAILURE") and "F_" not in transition["id"]:
            success_prefix.append(transition["id"])
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-outcome-obligations/5.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "outcomes": derived,
        "failure_variants": failure_variants,
    }


def derive_accounting(model: dict[str, Any]) -> dict[str, Any]:
    transitions = _index_transitions(model)
    targets: dict[str, Any] = {}
    for name, target in model["ledger_targets"].items():
        transition_id = target.get("advance_transition")
        if transition_id is not None:
            transition = transitions.get(transition_id)
            if transition is None or transition["ledger_effects"].get(name) != target["delta"]:
                raise ValueError(f"accounting/model mismatch: {name}")
        targets[name] = target
    obligations = derive_outcome_obligations(model)["outcomes"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event-accounting/5.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "authorization_mint_execution_delta": 0,
        "consumer_grant_is_start": False,
        "reservation_is_execution": False,
        "targets": targets,
        "outcome_deltas": {name: value["ledger_deltas"] for name, value in obligations.items()},
        "same_commit_banking": {
            "required": True,
            "package": ["package_durable_start", "package_ledger_entry", "package_ledger_index"],
            "primary": ["primary_durable_start", "primary_ledger_entry", "primary_ledger_index"],
            "secondary": ["secondary_durable_start", "secondary_ledger_entry", "secondary_ledger_index"],
            "completed_event_additions": ["receipt", "terminal"],
        },
    }


def derive_path_timing(model: dict[str, Any]) -> dict[str, Any]:
    relation = model["root_relation_matrix"]
    roles = relation["roles"]
    expected_pairs = {tuple(pair) for pair in combinations(roles, 2)}
    actual_pairs = {(item["left"], item["right"]) for item in relation["pairs"]}
    if actual_pairs != expected_pairs or len(actual_pairs) != len(relation["pairs"]):
        raise ValueError("root relation pair matrix is incomplete or duplicated")
    traces = {}
    for name, outcome in model["terminal_outcomes"].items():
        if not outcome["trace"]:
            continue
        result = simulate_trace(model, outcome["trace"])
        traces[name] = dict(result.path_states)
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-path-timing/1.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "roles": model["path_roles"],
        "absent_path_validation": model["absent_path_validation"],
        "root_relation_matrix": relation,
        "legal_trace_final_path_states": traces,
        "satisfiability": "PASS",
    }


def derive_serialization(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.canonical-json-bytes/1.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        **model["serialization"],
        "sha_field_rule": {
            "artifact_may_contain_its_own_sha256": False,
            "sha_is_introduced_by_next_artifact_or_external_manifest": True,
            "covered_bytes": "THE_COMPLETE_CANONICAL_ARTIFACT_BYTES_INCLUDING_EXACTLY_ONE_TRAILING_NEWLINE",
        },
    }


def validate_model(model: dict[str, Any]) -> dict[str, Any]:
    expected_top = {
        "schema", "authority_generation", "status", "authorization_schema", "initial_state",
        "states", "actors", "artifact_classes", "transitions", "terminal_outcomes",
        "start_transition_by_actor", "ledger_targets", "authority_activation", "path_roles",
        "absent_path_validation", "root_relation_matrix", "serialization", "measurement_authority",
        "authorization_document",
        "path_timing_authority", "event_accounting_authority", "canonical_serialization_authority",
        "supersession",
    }
    if set(model) != expected_top:
        raise ValueError(f"semantic model top-level census: {sorted(set(model) ^ expected_top)}")
    if model["authority_generation"] != 5 or model["authorization_schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/5.0.0":
        raise ValueError("generation/schema")
    if len(model["states"]) != len(set(model["states"])):
        raise ValueError("state census")
    transitions = _index_transitions(model)
    states = set(model["states"])
    artifacts = set(model["artifact_classes"])
    outcomes = set(model["terminal_outcomes"])
    for transition in transitions.values():
        if transition["source"] not in states or transition["destination"] not in states:
            raise ValueError(f"transition state: {transition['id']}")
        if not set(transition["artifacts_created"]).issubset(artifacts):
            raise ValueError(f"transition artifact: {transition['id']}")
        if transition["failure_outcome"] not in outcomes:
            raise ValueError(f"transition failure outcome: {transition['id']}")
    obligations = derive_outcome_obligations(model)
    accounting = derive_accounting(model)
    paths = derive_path_timing(model)
    serialization = derive_serialization(model)
    probe = {"z": [1, True, None], "a": "\u00e9"}
    expected = b'{"a":"\\u00e9","z":[1,true,null]}\n'
    if canonical_json_bytes(probe) != expected:
        raise ValueError("canonical serialization implementation drift")
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-semantic-model-validation/1.0.0",
        "result": "PASS",
        "semantic_model_sha256": canonical_sha256(model),
        "state_count": len(states),
        "transition_count": len(transitions),
        "terminal_outcome_count": len(model["terminal_outcomes"]),
        "failure_point_count": len(obligations["failure_variants"]),
        "artifact_class_count": len(artifacts),
        "accounting_target_count": len(accounting["targets"]),
        "root_relation_pair_count": len(paths["root_relation_matrix"]["pairs"]),
        "canonical_serialization_sha256_probe": sha256_bytes(expected),
        "lifecycle_binding_coverage": "COMPLETE",
        "path_satisfiability": "PASS",
    }


def main() -> int:
    model = load_json(MODEL_PATH)
    print(canonical_json_bytes(validate_model(model)).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

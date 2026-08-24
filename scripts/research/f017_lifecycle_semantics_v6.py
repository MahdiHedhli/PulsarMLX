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
MODEL_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json"


def _pairs(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def load_json(path: Path) -> dict[str, Any]:
    return strict_json_bytes(path.read_bytes())


def strict_json_bytes(data: bytes, *, require_canonical: bool = False, maximum: int = 16 * 1024 * 1024) -> dict[str, Any]:
    if len(data) > maximum or data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("bounded BOM-free JSON bytes required")
    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    if require_canonical and data != canonical_json_bytes(value):
        raise ValueError("noncanonical JSON authority bytes")
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
    path_states.update({f"ARTIFACT::{name}": "MUST_NOT_EXIST" for name in model["artifact_path_descriptors"]})
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
            elif effect["effect"] == "REMOVE_FILE":
                if path_states[role] != "MUST_EXIST_REGULAR_FILE":
                    raise ValueError(f"unsatisfiable file removal: {tid}/{role}")
                path_states[role] = "MUST_NOT_EXIST"
            else:
                raise ValueError(f"unknown path effect: {effect}")
        for artifact in transition["artifacts_created"]:
            key = f"ARTIFACT::{artifact}"
            if key not in path_states or path_states[key] != "MUST_NOT_EXIST":
                raise ValueError(f"unsatisfiable artifact creation: {tid}/{artifact}")
            path_states[key] = "MUST_EXIST_REGULAR_FILE"
            artifacts.add(artifact)
        for artifact in model["artifact_removals"].get(tid, []):
            key = f"ARTIFACT::{artifact}"
            if path_states.get(key) != "MUST_EXIST_REGULAR_FILE":
                raise ValueError(f"unsatisfiable artifact removal: {tid}/{artifact}")
            path_states[key] = "MUST_NOT_EXIST"
            artifacts.discard(artifact)
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


def _started_flags(trace: list[str]) -> dict[str, bool]:
    return {
        "package": "T11_START_PACKAGE" in trace,
        "primary": "T12_START_PRIMARY" in trace,
        "secondary": "T14_START_SECONDARY" in trace,
        "comparison": "T16_COMPARE_SUCCESS" in trace or "T16F_COMPARE_FAILURE" in trace,
    }


def _variant_obligation(
    model: dict[str, Any],
    *,
    variant_id: str,
    outcome_class: str,
    trace: list[str],
    terminalized: bool,
    failed_transition: str | None,
) -> dict[str, Any]:
    result = simulate_trace(model, trace)
    starts = _started_flags(trace)
    required = set(result.artifacts)
    forbidden = set(model["artifact_classes"]) - required
    for consumer in ("primary", "secondary"):
        consumer_evidence = {
            f"{consumer}_durable_start",
            f"{consumer}_ledger_entry",
            f"{consumer}_ledger_index",
            f"{consumer}_receipt",
            f"{consumer}_terminal",
        }
        if starts[consumer] and terminalized and result.state in {
            "PACKAGE_TERMINAL_SUCCESS", "PACKAGE_TERMINAL_FAILURE"
        }:
            if not consumer_evidence.issubset(required):
                raise ValueError(f"started consumer evidence missing: {variant_id}/{consumer}")
        if not starts[consumer] and required & consumer_evidence:
            raise ValueError(f"unstarted consumer evidence fabricated: {variant_id}/{consumer}")
    return {
        "variant_id": variant_id,
        "outcome_class": outcome_class,
        "trace": trace,
        "state_reached": result.state,
        "terminalized": terminalized,
        "failed_transition": failed_transition,
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


def derive_outcome_obligations(model: dict[str, Any]) -> dict[str, Any]:
    variants: dict[str, Any] = {}
    for name, outcome in model["terminal_branches"].items():
        trace = outcome["trace"]
        result = simulate_trace(model, trace)
        if result.state != outcome["terminal_state"]:
            raise ValueError(f"terminal state mismatch: {name}")
        starts = _started_flags(trace)
        declared = {
            "package": outcome["package_started"],
            "primary": outcome["primary_started"],
            "secondary": outcome["secondary_started"],
            "comparison": outcome["comparison_started"],
        }
        if starts != declared:
            raise ValueError(f"started flags are not transition-derived: {name}")
        if name == "COMPLETE_SUCCESS" and not all(starts.values()):
            raise ValueError("complete success without all phases")
        variant_id = f"TERMINAL::{name}"
        variants[variant_id] = _variant_obligation(
            model,
            variant_id=variant_id,
            outcome_class=name,
            trace=trace,
            terminalized=True,
            failed_transition=None,
        )

    def shortest_trace_to(target_state: str) -> list[str]:
        queue: list[tuple[str, list[str]]] = [(model["initial_state"], [])]
        seen = {model["initial_state"]}
        while queue:
            state, trace = queue.pop(0)
            if state == target_state:
                return trace
            for transition in model["transitions"]:
                if transition["source"] == state and transition["destination"] not in seen:
                    seen.add(transition["destination"])
                    queue.append((transition["destination"], trace + [transition["id"]]))
        raise ValueError(f"unreachable transition source: {target_state}")

    for transition in model["transitions"]:
        prefix = shortest_trace_to(transition["source"])
        variant_id = f"FAILED::{transition['id']}"
        variants[variant_id] = _variant_obligation(
            model,
            variant_id=variant_id,
            outcome_class=transition["failure_outcome"],
            trace=prefix,
            terminalized=False,
            failed_transition=transition["id"],
        )
        variants[variant_id]["failed_transition_artifacts_not_claimed"] = transition["artifacts_created"]
        variants[variant_id]["prohibited_side_effects"] = transition["prohibited_side_effects"]

    by_class: dict[str, list[str]] = {name: [] for name in model["outcome_classes"]}
    for variant_id, variant in variants.items():
        by_class[variant["outcome_class"]].append(variant_id)
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-outcome-obligations/6.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "variants": variants,
        "variants_by_outcome_class": {name: sorted(values) for name, values in by_class.items()},
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
    obligations = derive_outcome_obligations(model)["variants"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-event-accounting/6.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        **model["accounting_semantics"],
        "targets": targets,
        "variant_deltas": {name: value["ledger_deltas"] for name, value in obligations.items()},
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
    for name, outcome in derive_outcome_obligations(model)["variants"].items():
        result = simulate_trace(model, outcome["trace"])
        traces[name] = dict(result.path_states)
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-path-timing/1.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "roles": model["path_roles"],
        "artifact_paths": model["artifact_path_descriptors"],
        "artifact_file_validation": model["artifact_file_validation"],
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
        "schema", "authority_generation", "status", "authorization_schema", "initial_state", "accounting_semantics",
        "states", "actors", "artifact_classes", "artifact_payload_key_census", "artifact_removals", "artifact_self_sha_identities", "artifact_file_validation", "transitions", "outcome_classes", "terminal_branches",
        "start_transition_by_actor", "ledger_targets", "authority_activation", "path_roles",
        "absent_path_validation", "root_relation_matrix", "serialization", "measurement_authority", "artifact_path_descriptors",
        "authorization_document",
        "path_timing_authority", "event_accounting_authority", "canonical_serialization_authority",
        "supersession", "numerical_authority",
    }
    if set(model) != expected_top:
        raise ValueError(f"semantic model top-level census: {sorted(set(model) ^ expected_top)}")
    if model["authority_generation"] != 6 or model["authorization_schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0":
        raise ValueError("generation/schema")
    numerical = model["numerical_authority"]
    if numerical != {
        "contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json",
        "contract_sha256": "84ff9ba061952e4aa9fe4fe2c76ac6cafa3f03eb74a37ac1056c2a44b5003cf9",
        "capability_policy_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json",
        "capability_policy_sha256": "5ca6576781e269c18671b834b5d115494ec95462a17a59045e930eb256ce4d13",
        "requalification_path": "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json",
        "requalification_sha256": "5a0257803d7af03f091c0dfc438be0727dc567b465c82a8dfcdf83f847e80c49",
        "primary_pure_core_path": "scripts/research/f017_corrected_oracle_primary_numerics_v2.py",
        "primary_pure_core_sha256": "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767",
        "secondary_pure_core_path": "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py",
        "secondary_pure_core_sha256": "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791",
        "gemini_acceptance_path": "docs/architecture/reviews/evidence/f017-corrected-oracle-capability-closure-gemini-cycle-03-normalized-result.json",
        "gemini_acceptance_sha256": "fd8e4839cb0fc6e1f21259111d99778ff854e80ff8b47d3f503b2acce9f08d99",
        "opus_acceptance_path": "docs/architecture/reviews/evidence/f017-corrected-oracle-capability-closure-opus-cycle-03-normalized-result.json",
        "opus_acceptance_sha256": "bfc96a5b93eca41d6b27bf70bba1d42e2f51a35fc7850f8b7d82cd0a27706052",
        "formulas_changed": False,
        "methodology_changed": False,
        "thresholds_changed": False,
        "original_checkpoint_access": 0,
    }:
        raise ValueError("numerical v3 authority binding")
    if len(model["states"]) != len(set(model["states"])):
        raise ValueError("state census")
    transitions = _index_transitions(model)
    states = set(model["states"])
    artifacts = set(model["artifact_classes"])
    if (
        set(model["artifact_payload_key_census"]) != artifacts
        or set(model["artifact_path_descriptors"]) != artifacts
        or set(model["artifact_self_sha_identities"]) != artifacts
    ):
        raise ValueError("artifact payload/path/self-SHA bidirectional census")
    if model["artifact_file_validation"] != {
        "create_mode": "EXCLUSIVE_NO_REPLACE",
        "file_type": "REGULAR_FILE_NOFOLLOW",
        "parent_validation": "STRICT_CANONICAL_NONSYMLINK_ANCESTRY",
        "post_create_validation": "DESCRIPTOR_RELATIVE_REGULAR_FILE_NOFOLLOW",
        "durability_and_readback": "F017_CANONICAL_JSON_BYTES_V1_READBACK_SEQUENCE",
    }:
        raise ValueError("artifact post-create validation authority")
    outcomes = set(model["outcome_classes"])
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
        "terminal_outcome_count": len(model["outcome_classes"]),
        "failure_point_count": sum(1 for name in obligations["variants"] if name.startswith("FAILED::")),
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

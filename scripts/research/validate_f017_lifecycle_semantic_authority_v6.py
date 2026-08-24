#!/usr/bin/env python3
"""Executable semantic authority for the F017 corrected-oracle lifecycle.

This module is intentionally non-numerical.  It turns the compact lifecycle
model into outcome, accounting, path-timing, serialization, and binding views.
The independent validator recomputes these views instead of trusting generated
claims embedded in an artifact.
"""
from __future__ import annotations

import argparse
import copy
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


CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
PATHS = {
    "outcomes": CONTRACTS / "f017-corrected-oracle-outcome-obligations-v6.json",
    "accounting": CONTRACTS / "f017-corrected-oracle-event-accounting-v6.json",
    "paths": CONTRACTS / "f017-corrected-oracle-path-timing-v6.json",
    "serialization": CONTRACTS / "f017-canonical-json-bytes-v6.json",
    "interface": CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v6.json",
    "registry": CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v6.json",
    "matrix": CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v6.json",
    "schemas": CONTRACTS / "f017-corrected-oracle-artifact-schemas-v6.json",
}
MANIFEST_PATH = CONTRACTS / "f017-corrected-oracle-lifecycle-v6-authority-manifest.json"

EXPECTED_ACCOUNTING = {
    "HISTORICAL_REAL_PAYLOAD_LEDGER": (None, 0),
    "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER": ("T11_START_PACKAGE", 1),
    "CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER": ("T12_START_PRIMARY", 1),
    "CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER": ("T14_START_SECONDARY", 1),
}
EXPECTED_SERIALIZATION = {
    "identity": "F017_CANONICAL_JSON_BYTES_V1",
    "encoding": "UTF-8",
    "bom": False,
    "ensure_ascii": True,
    "duplicate_keys": "REJECT",
    "nonfinite_numbers": "REJECT",
    "sort_keys": True,
    "separators": [",", ":"],
    "insignificant_whitespace": False,
    "trailing_newline_count": 1,
    "artifact_sha256_domain": "SHA256_EXACT_CANONICAL_BYTES_OF_COMPLETE_ARTIFACT",
    "self_sha_inside_artifact": False,
}

# These fixed digests are the independent reviewed semantic anchor.  Generated
# views may change only when this validator is deliberately revised and reviewed;
# regenerating documents from a coordinated model mutation is insufficient.
EXPECTED_SEMANTIC_PROJECTION_SHAS = {
    "authorization_document": "79776a1c1ac0f1aa72ae626feaf575aa0e4d02720059b94ea612ebf0f937d415",
    "transitions": "4f5d08ac6c5e2a963581285dc7abdaa91853cc181d06a8a87c327e5f3655197c",
    "outcomes": "73d636a9b24e1d317c8870dbe90b47d06d1cff7559bb25983309175f70ba7494",
    "artifact_authority": "6cc201896e67f3d5558f4d84302e810b449185d05c7db2d7a105f801c031b48e",
    "path_authority": "12c215e3aa2f4d8f734e5f93daf8ff3360c49d1f4abd84a7c3f8a274523add74",
    "serialization": "24fff464845971036876016a93401fee9bb239d08f5111798ae7eeabba857975",
    "measurement_authority": "9f039d605b43b723cc96feed486a12de7cde2526a6593f0c18c8b5e23de13ac7",
    "accounting": "1de6086dade7f80c32d0b1f855137c7c21d41edc06cbfb8b4d01884a5daf98e9",
    "activation_supersession": "6b3bfeb3b7262a19c27fe41614e11f5b4c85a4bcf0f2001467fab5fafdf5a46b",
    "registry_grammars": "4b822649c36b1fc5e75bd600a0266cf2f93607720a3063f3dc74af3ca66f2129",
    "numerical_authority": "d60a187fbac7a762e2db49eb4f3ef761ba68c9fee45df94a3a0b08d13ba12d8a",
}

EXPECTED_AUTHORITY_FILE_SHAS = {
    "model": "54fb83da40f953ee5bad66c8076245a974f2aefa0215eea49df2b17f6442fc12",
    "outcomes": "e9de4660d1994e91224f1363044ad9df7bca1f96ed95269ef863c76385fbbf9a",
    "accounting": "049815711b9bc22cfce9e8737e8028134f1f77306f2f5b8625c5821d75f982d1",
    "paths": "363b5a7f15e12cafd6f67bb8838786e212ea80c0789ddaf9c0a43874ad484ea4",
    "serialization": "de301340c82d1eba7fb49abbcafaea8bb248ab0b6602b0c876ccd2d7c27eee1f",
    "interface": "8313cf6d56f5a5a45bb42641eb463fce20c788136cc95bfe4213d72a9964c577",
    "registry": "581e7fb2328f6433fe283e3fc6680d6ab7877fa18170f93852963f0cee3caac7",
    "matrix": "c20c2b7688ea8a94ba4d7a2e06073736d3849c4396c10212a253715456fcba9c",
    "schemas": "189eeea17975f0c11300b9bb4e5d294772d3591ede3f12e07bad562227a2664d",
}


def _semantic_projections(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorization_document": model["authorization_document"],
        "transitions": model["transitions"],
        "outcomes": {
            "outcome_classes": model["outcome_classes"],
            "terminal_branches": model["terminal_branches"],
        },
        "artifact_authority": {
            "artifact_classes": model["artifact_classes"],
            "artifact_payload_key_census": model["artifact_payload_key_census"],
            "artifact_self_sha_identities": model["artifact_self_sha_identities"],
            "artifact_file_validation": model["artifact_file_validation"],
            "artifact_path_descriptors": model["artifact_path_descriptors"],
            "artifact_removals": model["artifact_removals"],
        },
        "path_authority": {
            "path_roles": model["path_roles"],
            "absent_path_validation": model["absent_path_validation"],
            "root_relation_matrix": model["root_relation_matrix"],
        },
        "serialization": model["serialization"],
        "measurement_authority": model["measurement_authority"],
        "accounting": {
            "accounting_semantics": model["accounting_semantics"],
            "ledger_targets": model["ledger_targets"],
            "start_transition_by_actor": model["start_transition_by_actor"],
        },
        "activation_supersession": {
            "authority_activation": model["authority_activation"],
            "supersession": model["supersession"],
        },
        "numerical_authority": model["numerical_authority"],
    }


def _identity_type(name: str) -> str:
    if name.endswith("_sha256"): return "SHA256"
    if name.endswith("_id"): return "LIVE_ID"
    if name.endswith("_root") or name.endswith("_path"): return "PATH_DESCRIPTOR"
    if name.endswith("_head"): return "GIT_COMMIT"
    if name.endswith("_terminal") or name.endswith("_delta") or name.endswith("_count") or name.endswith("_ns") or name in {"prompt_token", "position", "top_n"}: return "INTEGER"
    if name.endswith("_role"): return "ROLE"
    return "EXACT_SCALAR"


def _authorization_identities(model: dict[str, Any]) -> set[str]:
    doc = model["authorization_document"]
    result = {key for key in doc["top_level_keys"] if key not in {"schema", "package", "primary", "secondary", "context", "limits", "shards", "state", "live"}}
    result.update(f"package_{key}" for key in doc["package_keys"])
    result.update(f"primary_{key}" for key in doc["consumer_keys"])
    result.update(f"secondary_{key}" for key in doc["consumer_keys"])
    result.update(doc["context_keys"])
    result.update(doc["limits_keys"])
    result.update({"authorization_schema", "authorization_state", "authorization_live"})
    return result


def _authorization_json_path(model: dict[str, Any], name: str) -> str:
    doc = model["authorization_document"]
    if name == "authorization_schema": return "$.schema"
    if name == "authorization_state": return "$.state"
    if name == "authorization_live": return "$.live"
    if name in doc["top_level_keys"]: return f"$.{name}"
    for prefix, keys in (("package", doc["package_keys"]), ("primary", doc["consumer_keys"]), ("secondary", doc["consumer_keys"])):
        marker = prefix + "_"
        if name.startswith(marker) and name[len(marker):] in keys:
            return f"$.{prefix}.{name[len(marker):]}"
    if name in doc["context_keys"]: return f"$.context.{name}"
    if name in doc["limits_keys"]: return f"$.limits.{name}"
    raise ValueError(f"authorization path absent: {name}")


def _expected_binding_surface(model: dict[str, Any], obligations: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, set[str]]]]:
    transitions = {item["id"]: item for item in model["transitions"]}
    base = _authorization_identities(model)
    all_names = set(base)
    by_artifact: dict[str, dict[str, set[str]]] = {name: {} for name in model["artifact_classes"]}
    authorization_artifacts = {"candidate_authorization", "installed_authorization"}
    for outcome_name, outcome in obligations["variants"].items():
        visible = set(base)
        for tid in outcome["trace"]:
            transition = transitions[tid]
            introduced = set(transition["identities_introduced"])
            all_names.update(introduced)
            for artifact in transition["artifacts_created"]:
                own_sha = model["artifact_self_sha_identities"][artifact]
                by_artifact[artifact][outcome_name] = base if artifact in authorization_artifacts else (visible | introduced) - {own_sha}
            visible.update(introduced)
    for transition in model["transitions"]:
        all_names.update(transition["identities_introduced"])
    return all_names, by_artifact


def _expected_interface(model: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    doc = model["authorization_document"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/6.0.0",
        "authorization_schema": model["authorization_schema"],
        "interface_scope": "PRODUCTION",
        "semantic_model_path": str(MODEL_PATH.relative_to(ROOT)),
        "semantic_model_sha256": canonical_sha256(model),
        "top_level_keys": doc["top_level_keys"],
        "package_keys": doc["package_keys"],
        "consumer_keys": doc["consumer_keys"],
        "context_keys": doc["context_keys"],
        "limits_keys": doc["limits_keys"],
        "shard_keys": doc["shard_keys"],
        "pinned_values": doc["pinned_values"],
        "pinned_context": {
            key: doc["pinned_values"][key]
            for key in doc["context_keys"]
        },
        "pinned_limits": {
            "checkpoint_shard_count": 6,
            "graph_payload_shard_count": 5,
            "identity_only_shard_count": 1,
            "graph_tensor_count": 1410,
            "non_access_tensor_count": 399,
            "expected_token_field_permitted": False,
            "p1_authority": "PROHIBITED",
        },
        "artifact_schema_authority": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-artifact-schemas-v6.json",
        "artifact_schema_authority_sha256": canonical_sha256(schemas),
        "candidate_authority": False,
        "live_authority_requirements": ["CANONICAL_INSTALL_PATH", "CANDIDATE_INSTALL_BYTE_IDENTITY", "INSTALLATION_RECEIPT", "OPERATOR_APPROVAL", "DUAL_CONSUMER_VALIDATION", "UNUSED_ROOTS"],
        "target_mode_requires_installation_receipt": True,
        "candidate_path_descriptor": {**model["artifact_path_descriptors"]["candidate_authorization"], "authority": False},
        "installed_path_descriptor": {**model["artifact_path_descriptors"]["installed_authorization"], "authorization_field": "canonical_install_path", "exact_path_equality": True},
        "expected_token_field_permitted": False,
        "validation_side_effect_limits": {"checkpoint_opens": 0, "checkpoint_reads": 0, "checkpoint_mmaps": 0, "state_roots_created": 0, "numerical_operations": 0},
    }


def _exact_canonical(path: Path, value: Any) -> None:
    if path.read_bytes() != canonical_json_bytes(value):
        raise ValueError(f"noncanonical or readback byte drift: {path.relative_to(ROOT)}")


def _expected_authority_manifest(model: dict[str, Any], documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    authorities = {
        "model": {"path": str(MODEL_PATH.relative_to(ROOT)), "sha256": canonical_sha256(model)}
    }
    for name, path in PATHS.items():
        authorities[name] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": canonical_sha256(documents[name]),
        }
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-v6-authority-manifest/1.0.0",
        "authority_generation": 6,
        "authorities": authorities,
        "semantic_columns": [
            "source", "equality_rule", "validator", "failure_classification",
            "authority_status", "schema", "json_path", "type",
        ],
        "validation_rule": "EXACT_FULL_FILE_BYTES_AND_EXACT_SEMANTIC_FIELD_EQUALITY",
        "generator_is_validation_authority": False,
    }


def validate_semantics(model: dict[str, Any]) -> None:
    validate_model(model)
    for name, projection in _semantic_projections(model).items():
        if canonical_sha256(projection) != EXPECTED_SEMANTIC_PROJECTION_SHAS[name]:
            raise ValueError(f"independently anchored semantic projection drift: {name}")
    if model["authorization_schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0":
        raise ValueError("authorization generation")
    if model["supersession"] != {
        "v1_v2_v3_live_mint": "HISTORICAL_ONLY_REJECT_LIVE_MINT",
        "v1_v2_v3_target_execution": "HISTORICAL_ONLY_REJECT_NEW_EXECUTION",
        "v4_design": "REJECTED_HISTORICAL_DESIGN_ONLY",
        "v5_design": "REJECTED_HISTORICAL_DESIGN_ONLY",
        "event_04_requires_generation": 6,
    }:
        raise ValueError("supersession semantics")
    if model.get("accounting_semantics") != {"authorization_mint_execution_delta": 0, "consumer_grant_is_start": False, "reservation_is_execution": False}:
        raise ValueError("reservation/execution semantic drift")
    for target, (transition, delta) in EXPECTED_ACCOUNTING.items():
        actual = model["ledger_targets"].get(target)
        if actual is None or actual.get("advance_transition") != transition or actual.get("delta") != delta:
            raise ValueError(f"accounting semantic drift: {target}")
    historical = model["ledger_targets"]["HISTORICAL_REAL_PAYLOAD_LEDGER"]
    if historical.get("before") != 175 or historical.get("after") != 175 or historical.get("authority_sha256") != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e":
        raise ValueError("historical ledger drift")
    if any(model["serialization"].get(key) != value for key, value in EXPECTED_SERIALIZATION.items()):
        raise ValueError("serialization semantic drift")
    absent = model["absent_path_validation"]
    if absent.get("resolve_absent_leaf_strictly") is not False or absent.get("resolve_parent_strictly") is not True or absent.get("leaf_absence_check") != "LSTAT_ENOENT":
        raise ValueError("absent path timing drift")
    if model["authority_activation"].get("candidate_is_authority") is not False or model["authority_activation"].get("requires_installation_receipt") is not True:
        raise ValueError("candidate/live authority drift")
    doc = model["authorization_document"]
    if "package_attempt_id" not in doc["top_level_keys"] or doc["top_level_keys"].count("package_attempt_id") != 1:
        raise ValueError("package attempt identity not canonical")
    if doc["pinned_values"].get("expected_token_field_permitted") is not False:
        raise ValueError("expected-token quarantine drift")
    if doc["pinned_values"].get("p1_authority") != "PROHIBITED" or doc["pinned_values"].get("authority_generation") != 6:
        raise ValueError("generation/P1 authority drift")
    if set(model["artifact_payload_key_census"]) != set(model["artifact_classes"]):
        raise ValueError("payload census authority")
    required_measurements = {
        "scripts/research/f017_lifecycle_semantics_v6.py",
        "scripts/research/generate_f017_lifecycle_v6_authorities.py",
        "scripts/research/generate_f017_corrected_oracle_interface_v6.py",
        "scripts/research/validate_f017_lifecycle_semantic_authority_v6.py",
        "scripts/research/validate_f017_corrected_oracle_access.py",
        "scripts/research/execute_f017_corrected_oracle_event.py",
        "scripts/research/validate_f017_corrected_oracle_access_v2.py",
        "scripts/research/execute_f017_corrected_oracle_event_v2.py",
        "scripts/research/validate_f017_corrected_oracle_access_v3.py",
        "scripts/research/execute_f017_corrected_oracle_event_v3.py",
        "scripts/research/f017_corrected_oracle_primary_v3.py",
        "scripts/research/f017_corrected_oracle_secondary_v3.py",
        "scripts/research/f017_corrected_oracle_authorization_v6.py",
        "scripts/research/f017_corrected_oracle_primary_v6.py",
        "scripts/research/f017_corrected_oracle_secondary_v6.py",
        "scripts/research/f017_corrected_oracle_wrapper_support_v6.py",
        "scripts/research/validate_f017_corrected_oracle_access_v6.py",
        "scripts/research/execute_f017_corrected_oracle_event_v6.py",
        "scripts/research/f017_corrected_oracle_primary.py",
        "scripts/research/f017_corrected_oracle_secondary.py",
        "scripts/research/f017_oracle_primary_decoders.py",
        "scripts/research/f017_macos_memory_observation_v1.py",
        "scripts/research/f017_corrected_oracle_primary_numerics_v2.py",
        "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py",
        "scripts/research/f017_corrected_oracle_primary_target_source_v6.py",
        "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py",
        "scripts/research/f017_numerical_capability_analysis_v1.py",
        "scripts/research/f017_numerical_capability_structural_check_v1.py",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v6.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json",
    }
    if set(model["measurement_authority"].get("required_entries", [])) != required_measurements:
        raise ValueError("implementation measurement entry census")
    retirement_sentinels = {
        "scripts/research/validate_f017_corrected_oracle_access.py": "V1_LIVE_MINT",
        "scripts/research/execute_f017_corrected_oracle_event.py": "V1_COORDINATOR",
        "scripts/research/validate_f017_corrected_oracle_access_v2.py": "V2_LIVE_MINT",
        "scripts/research/execute_f017_corrected_oracle_event_v2.py": "V2_COORDINATOR",
        "scripts/research/validate_f017_corrected_oracle_access_v3.py": "V3_LIVE_MINT",
        "scripts/research/execute_f017_corrected_oracle_event_v3.py": "V3_COORDINATOR",
        "scripts/research/f017_corrected_oracle_primary_v3.py": "V3_PRIMARY_TARGET",
        "scripts/research/f017_corrected_oracle_secondary_v3.py": "V3_SECONDARY_TARGET",
    }
    for relative, sentinel in retirement_sentinels.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        if not all(marker in source for marker in (
            "HISTORICAL_ONLY", sentinel,
            "84f0d1dc3e60a4151329ed82773880951ee3e618",
            "checkpoint access, and state creation are prohibited",
        )):
            raise ValueError(f"historical live surface remains reachable: {relative}")


def validate_bundle(model: dict[str, Any], documents: dict[str, dict[str, Any]]) -> dict[str, int]:
    validate_semantics(model)
    expected = {
        "outcomes": derive_outcome_obligations(model),
        "accounting": derive_accounting(model),
        "paths": derive_path_timing(model),
        "serialization": derive_serialization(model),
    }
    for name, value in expected.items():
        if documents[name] != value:
            raise ValueError(f"generated semantic authority drift: {name}")
    model_sha = canonical_sha256(model)
    for name, document in documents.items():
        if name in {"registry", "matrix", "schemas", "interface"} and document.get("semantic_model_sha256") != model_sha:
            raise ValueError(f"unbound semantic model: {name}")
    registry, matrix, schemas, interface = (documents[name] for name in ("registry", "matrix", "schemas", "interface"))
    if set(registry) != {"schema", "semantic_model_sha256", "grammars", "identity_count", "identities", "status"} or registry.get("status") != "GENERATED_VIEW_NOT_PRIMARY_AUTHORITY":
        raise ValueError("identity registry authority/key census")
    if set(matrix) != {"schema", "semantic_model_sha256", "columns", "row_count", "required_cell_count", "rows", "status", "authority_status"}:
        raise ValueError("binding matrix top-level key census")
    if matrix.get("authority_status") != "GENERATED_VIEW_NOT_PRIMARY_AUTHORITY":
        raise ValueError("binding matrix authority status")
    expected_names, expected_bindings = _expected_binding_surface(model, expected["outcomes"])
    identities = registry.get("identities")
    if not isinstance(identities, list) or registry.get("identity_count") != len(identities):
        raise ValueError("identity registry census")
    names = [item.get("name") for item in identities]
    if len(names) != len(set(names)) or set(names) != expected_names:
        raise ValueError("identity registry completeness")
    if canonical_sha256(registry.get("grammars")) != EXPECTED_SEMANTIC_PROJECTION_SHAS["registry_grammars"]:
        raise ValueError("independently anchored registry grammar drift")
    identity_key_census = {
        "name", "type", "grammar", "authority_source", "derivation_permitted",
        "mismatch_behavior", "bound_artifact_outcomes",
    }
    authorization_names = _authorization_identities(model)
    for identity in identities:
        if set(identity) != identity_key_census:
            raise ValueError(f"identity record key census: {identity.get('name')}")
        name = identity["name"]
        expected_bound = {
            artifact: sorted(outcome for outcome, values in outcomes.items() if name in values)
            for artifact, outcomes in expected_bindings.items()
            if any(name in values for values in outcomes.values())
        }
        expected_source = "AUTHORIZATION_DOCUMENT" if name in authorization_names else "SEMANTIC_TRANSITION_READBACK"
        expected_grammar = registry["grammars"][_identity_type(name)]
        if identity.get("type") != _identity_type(name) or identity.get("grammar") != expected_grammar or identity.get("authority_source") != expected_source or identity.get("derivation_permitted") is not False or identity.get("mismatch_behavior") != "FAIL_CLOSED_BEFORE_NEXT_TRANSITION" or identity.get("bound_artifact_outcomes") != expected_bound:
            raise ValueError(f"identity semantic drift: {name}")
    artifact_names = set(model["artifact_classes"])
    if matrix.get("columns") != sorted(artifact_names) or matrix.get("row_count") != len(matrix.get("rows", [])):
        raise ValueError("binding matrix census")
    if {row.get("identity") for row in matrix["rows"]} != set(names):
        raise ValueError("binding registry/matrix mismatch")
    required_cells = 0
    for row in matrix["rows"]:
        if set(row) != {"identity", "cells"}:
            raise ValueError(f"matrix row key census: {row.get('identity')}")
        if set(row.get("cells", {})) != artifact_names:
            raise ValueError(f"matrix artifact census: {row.get('identity')}")
        for artifact, cell in row["cells"].items():
            if set(cell) != {
                "required_outcomes", "json_path", "type", "source",
                "equality_rule", "validator", "failure_classification",
            }:
                raise ValueError(f"matrix cell key census: {row['identity']}/{artifact}")
            outcomes = cell.get("required_outcomes")
            expected_outcomes = sorted(outcome for outcome, values in expected_bindings[artifact].items() if row["identity"] in values)
            if outcomes != expected_outcomes:
                raise ValueError(f"matrix outcome: {row['identity']}/{artifact}")
            if outcomes:
                required_cells += 1
                expected_path = _authorization_json_path(model, row["identity"]) if artifact in {"candidate_authorization", "installed_authorization"} and row["identity"] in _authorization_identities(model) else f"$.bindings.{row['identity']}"
                expected_cell = {
                    "required_outcomes": expected_outcomes,
                    "json_path": expected_path,
                    "type": _identity_type(row["identity"]),
                    "source": "AUTHORIZATION_DOCUMENT" if row["identity"] in authorization_names else "SEMANTIC_TRANSITION_READBACK",
                    "equality_rule": "EXACT_TYPED_EQUALITY_TO_FIRST_INTRODUCTION",
                    "validator": "validate_f017_lifecycle_semantic_authority_v6.py",
                    "failure_classification": "LIFECYCLE_BINDING_MISMATCH",
                }
                if cell != expected_cell:
                    raise ValueError(f"unresolved binding cell: {row['identity']}/{artifact}")
            elif any(cell.get(key) is not None for key in ("json_path", "type", "source", "equality_rule", "validator", "failure_classification")):
                raise ValueError(f"spurious optional binding cell: {row['identity']}/{artifact}")
    if matrix.get("required_cell_count") != required_cells or matrix.get("status") != "LIFECYCLE_BINDING_COVERAGE: COMPLETE":
        raise ValueError("binding coverage count/status")
    artifact_schemas = schemas.get("artifacts")
    if not isinstance(artifact_schemas, dict) or set(artifact_schemas) != artifact_names:
        raise ValueError("artifact schema bidirectional census")
    for artifact, schema in artifact_schemas.items():
        if schema.get("artifact_schema_id") != model["artifact_classes"][artifact]["schema"]:
            raise ValueError(f"artifact schema ID drift: {artifact}")
        authorization_artifact = artifact in {"candidate_authorization", "installed_authorization"}
        expected_top = model["authorization_document"]["top_level_keys"] if authorization_artifact else ["schema", "bindings", "payload"]
        if schema.get("top_level_keys") != expected_top or schema.get("payload_key_census") != model["artifact_payload_key_census"][artifact]:
            raise ValueError(f"artifact key census: {artifact}")
        expected_identity_names = sorted(set().union(*expected_bindings[artifact].values()) if expected_bindings[artifact] else set())
        if authorization_artifact and set(expected_identity_names) != _authorization_identities(model):
            raise ValueError(f"authorization document contains non-document lifecycle bindings: {artifact}")
        expected_paths = {
            name: _authorization_json_path(model, name) if authorization_artifact and name in _authorization_identities(model) else f"$.bindings.{name}"
            for name in expected_identity_names
        }
        expected_required = {
            name: sorted(outcome for outcome, values in expected_bindings[artifact].items() if name in values)
            for name in expected_identity_names
        }
        expected_payload_equality = {
            key: expected_paths[key]
            for key in model["artifact_payload_key_census"][artifact]
            if key in expected_paths
        }
        if schema.get("identity_paths") != expected_paths or schema.get("identity_required_outcomes") != expected_required or schema.get("payload_binding_equality") != expected_payload_equality:
            raise ValueError(f"artifact binding channel drift: {artifact}")
        if authorization_artifact and any(path.startswith("$.bindings") for path in schema["identity_paths"].values()):
            raise ValueError(f"authorization document has unrealizable bindings channel: {artifact}")
    if interface != _expected_interface(model, schemas):
        raise ValueError("authorization interface semantic drift")
    accounting = documents["accounting"]
    if accounting.get("authorization_mint_execution_delta") != 0 or accounting.get("consumer_grant_is_start") is not False or accounting.get("reservation_is_execution") is not False:
        raise ValueError("reservation/execution semantic drift")
    paths = documents["paths"]
    for outcome_name, obligation in expected["outcomes"]["variants"].items():
        final = paths["legal_trace_final_path_states"][outcome_name]
        for artifact in obligation["required_artifacts"]:
            if final.get(f"ARTIFACT::{artifact}") != "MUST_EXIST_REGULAR_FILE":
                raise ValueError(f"required artifact path unsatisfied: {outcome_name}/{artifact}")
        for artifact in obligation["forbidden_artifacts"]:
            if final.get(f"ARTIFACT::{artifact}") != "MUST_NOT_EXIST":
                raise ValueError(f"forbidden artifact path present: {outcome_name}/{artifact}")
    return {"identity_count": len(names), "required_cell_count": required_cells, "artifact_count": len(artifact_names)}


def assert_mutations_rejected(model: dict[str, Any], docs: dict[str, dict[str, Any]]) -> int:
    mutations: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    def add_model(mutator):
        bad = copy.deepcopy(model); mutator(bad); mutations.append((bad, copy.deepcopy(docs)))
    def add_doc(name, mutator):
        bad_docs = copy.deepcopy(docs); mutator(bad_docs[name]); mutations.append((copy.deepcopy(model), bad_docs))

    def mutate_first_required_cell(document: dict[str, Any], key: str, value: Any) -> None:
        for row in document["rows"]:
            for cell in row["cells"].values():
                if cell["required_outcomes"]:
                    cell[key] = value
                    return
        raise AssertionError("required matrix cell absent")

    add_model(lambda m: m["ledger_targets"]["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"].update(delta=0))
    add_model(lambda m: m["ledger_targets"]["HISTORICAL_REAL_PAYLOAD_LEDGER"].update(after=176, delta=1))
    add_model(lambda m: m["ledger_targets"]["CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER"].update(advance_transition="T06_INSTALL_AUTHORIZATION"))
    add_model(lambda m: m["terminal_branches"]["SECONDARY_PRE_START_FAILURE"].update(secondary_started=True))
    add_model(lambda m: m["terminal_branches"]["COMPLETE_SUCCESS"].update(primary_started=False))
    add_model(lambda m: m["absent_path_validation"].update(resolve_absent_leaf_strictly=True))
    add_model(lambda m: m["root_relation_matrix"]["pairs"].pop())
    add_model(lambda m: m["serialization"].update(sort_keys=False))
    add_model(lambda m: m["authorization_document"]["top_level_keys"].remove("package_attempt_id"))
    add_model(lambda m: m["authority_activation"].update(candidate_is_authority=True))
    add_model(lambda m: m["supersession"].update(v1_v2_v3_live_mint="ACTIVE"))
    add_model(lambda m: m["accounting_semantics"].update(authorization_mint_execution_delta=1, consumer_grant_is_start=True, reservation_is_execution=True))
    add_model(lambda m: m["artifact_payload_key_census"].__setitem__("package_terminal", ["result"]))
    add_model(lambda m: m["artifact_path_descriptors"].pop("package_terminal"))
    add_model(lambda m: m["artifact_removals"].clear())
    add_model(lambda m: m["measurement_authority"].update(required_entries=[]))
    add_model(lambda m: m["transitions"][1].update(preconditions=[]))
    add_model(lambda m: m["transitions"][1].update(prohibited_side_effects=[]))
    add_model(lambda m: m["states"].append("P1_EXECUTION_AUTHORIZED"))
    add_model(lambda m: m["authorization_document"]["pinned_values"].update(prompt_token=9704))
    add_model(lambda m: m["root_relation_matrix"]["pairs"][0].update(relation="EQUAL"))
    add_model(lambda m: m["serialization"]["readback_sequence"].remove("DESCRIPTOR_RELATIVE_REOPEN"))
    add_model(lambda m: m["measurement_authority"].update(measurement_head_semantics="UNDEFINED"))
    add_model(lambda m: m["start_transition_by_actor"].update(secondary="T12_START_PRIMARY"))
    add_model(lambda m: m["artifact_file_validation"].update(post_create_validation="NONE"))
    add_model(lambda m: m["artifact_self_sha_identities"].update(candidate_authorization="installed_authorization_sha256"))
    add_doc("accounting", lambda d: d["variant_deltas"]["TERMINAL::SECONDARY_PRE_START_FAILURE"].update(CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER=1))
    add_doc("outcomes", lambda d: d["variants"]["TERMINAL::SECONDARY_PRE_START_FAILURE"]["forbidden_artifacts"].remove("secondary_terminal"))
    add_doc("outcomes", lambda d: d["variants"]["TERMINAL::PRIMARY_POST_START_FAILURE"]["required_artifacts"].remove("primary_receipt"))
    add_doc("schemas", lambda d: d["artifacts"]["package_terminal"].update(artifact_schema_id="forged/1.0.0"))
    add_doc("interface", lambda d: d["top_level_keys"].append("unknown"))
    add_doc("interface", lambda d: d["pinned_values"].update(p1_authority="PERMITTED"))
    add_doc("interface", lambda d: d.update(expected_token_field_permitted=True, candidate_authority=True, target_mode_requires_installation_receipt=False))
    add_doc("interface", lambda d: d["validation_side_effect_limits"].update(checkpoint_opens=999, checkpoint_reads=999, state_roots_created=7))
    add_doc("interface", lambda d: d.update(live_authority_requirements=[]))
    add_doc("matrix", lambda d: d["rows"][0]["cells"].pop(next(iter(d["rows"][0]["cells"]))))
    add_doc("matrix", lambda d: mutate_first_required_cell(d, "source", "SUBSTRING_MATCH_OK"))
    add_doc("matrix", lambda d: mutate_first_required_cell(d, "equality_rule", "WARN_ONLY"))
    add_doc("matrix", lambda d: mutate_first_required_cell(d, "validator", "attacker_validator.py"))
    add_doc("matrix", lambda d: mutate_first_required_cell(d, "failure_classification", "WARN_ONLY"))
    add_doc("matrix", lambda d: d["rows"][0].update(attacker_extra=True))
    add_doc("matrix", lambda d: next(iter(d["rows"][0]["cells"].values())).update(attacker_extra=True))
    add_doc("matrix", lambda d: d.update(authority_status="FORGED_ACTIVE_AUTHORITY"))
    add_doc("registry", lambda d: d.update(status="FORGED_ACTIVE_AUTHORITY"))
    add_doc("serialization", lambda d: d.update(artifact_sha256_domain="UNDEFINED"))
    add_doc("registry", lambda d: d["identities"][0].update(derivation_permitted=True, mismatch_behavior="IGNORE"))
    add_doc("schemas", lambda d: d["artifacts"]["package_terminal"].update(payload_key_census=["result"]))
    add_doc("schemas", lambda d: d["artifacts"]["candidate_authorization"]["identity_paths"].update(candidate_sha256="$.bindings.candidate_sha256"))
    add_doc("outcomes", lambda d: d["variants"]["FAILED::T07_BANK_INSTALL_RECEIPT"]["required_artifacts"].remove("installed_authorization"))
    add_doc("outcomes", lambda d: d["variants"]["TERMINAL::SECONDARY_PRE_START_FAILURE"]["required_artifacts"].append("secondary_terminal"))
    add_doc("paths", lambda d: d["artifact_file_validation"].update(create_mode="REPLACE_ALLOWED"))
    add_doc("registry", lambda d: d["grammars"]["LIVE_ID"].update(pattern=".*"))
    add_doc("registry", lambda d: d["identities"][0].pop("authority_source"))
    bad_docs = copy.deepcopy(docs)
    removed = "primary_terminal_sha256"
    bad_docs["registry"]["identities"] = [item for item in bad_docs["registry"]["identities"] if item["name"] != removed]
    bad_docs["registry"]["identity_count"] -= 1
    bad_docs["matrix"]["rows"] = [row for row in bad_docs["matrix"]["rows"] if row["identity"] != removed]
    bad_docs["matrix"]["row_count"] -= 1
    for schema in bad_docs["schemas"]["artifacts"].values():
        schema["identity_paths"].pop(removed, None)
        schema["identity_required_outcomes"].pop(removed, None)
    mutations.append((copy.deepcopy(model), bad_docs))

    rejected = 0
    for bad_model, bad_docs in mutations:
        try:
            validate_bundle(bad_model, bad_docs)
        except (ValueError, KeyError):
            rejected += 1
        else:
            raise ValueError("semantic mutation unexpectedly accepted")
    return rejected


def validate() -> dict[str, Any]:
    observed_file_shas = {
        "model": sha256_bytes(MODEL_PATH.read_bytes()),
        **{name: sha256_bytes(path.read_bytes()) for name, path in PATHS.items()},
    }
    if observed_file_shas != EXPECTED_AUTHORITY_FILE_SHAS:
        changed = sorted(
            name for name in set(observed_file_shas) | set(EXPECTED_AUTHORITY_FILE_SHAS)
            if observed_file_shas.get(name) != EXPECTED_AUTHORITY_FILE_SHAS.get(name)
        )
        raise ValueError(f"byte-anchored lifecycle authority drift: {changed}")
    model = load_json(MODEL_PATH)
    _exact_canonical(MODEL_PATH, model)
    documents = {name: load_json(path) for name, path in PATHS.items()}
    for name, path in PATHS.items():
        _exact_canonical(path, documents[name])
    manifest = load_json(MANIFEST_PATH)
    _exact_canonical(MANIFEST_PATH, manifest)
    if manifest != _expected_authority_manifest(model, documents):
        raise ValueError("lifecycle authority manifest exact-byte binding drift")
    counts = validate_bundle(model, documents)
    mutations = assert_mutations_rejected(model, documents)
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-semantic-authority-validation/6.0.0",
        "result": "PASS",
        "semantic_model_sha256": canonical_sha256(model),
        **counts,
        "semantic_mutations_rejected": mutations,
        "event_accounting_loaded_and_pinned": True,
        "conditional_outcome_validation": "PASS",
        "path_satisfiability": "PASS",
        "readback_sha_domain": "EXACT_CANONICAL_COMPLETE_ARTIFACT_BYTES",
        "whole_model_byte_anchor": "PASS",
        "registry_matrix_byte_anchors": "PASS",
        "semantic_columns_exact": "PASS",
        "independent_derivation_imports_generator": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    encoded = canonical_json_bytes(result)
    if args.output:
        args.output.write_bytes(encoded)
    print(encoded.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

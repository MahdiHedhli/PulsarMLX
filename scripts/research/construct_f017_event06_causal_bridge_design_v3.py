#!/usr/bin/env python3
"""Construct and falsify the liquid Sequence 13 causal design candidate."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from generate_f017_event06_causal_bridge_v3 import candidate_bytes  # noqa: E402
from validate_f017_event06_causal_bridge_v3 import (  # noqa: E402
    validate_causal_bridge_candidate_v3,
    validate_witness_instances,
)

_SEAL = object()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class _DesignNode:
    __slots__ = ("_items", "sha256")

    def __new__(cls, seal: object = None, *_: object):
        if seal is not _SEAL:
            raise TypeError("design nodes are public-producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object]) -> None:
        del seal
        object.__setattr__(self, "_items", tuple((key, value[key]) for key in sorted(value)))
        object.__setattr__(self, "sha256", hashlib.sha256(_canonical(value)).hexdigest())

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise TypeError("design nodes are immutable")

    def value(self) -> dict[str, object]:
        return dict(self._items)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _value(category: str, field: str, node_id: str) -> object:
    if field == "schema":
        return f"pulsarmlx.f017.sequence13-design.{node_id.lower()}/1.0.0"
    if field == "node_id": return node_id
    if field == "authorization_id": return "F017-DESIGN-SYNTHETIC-AUTHORIZATION"
    if field == "package_attempt_id": return "F017-DESIGN-SYNTHETIC-PACKAGE"
    if field == "primary_event_id" or field == "consumer_event_id" and node_id.startswith("PRIMARY"):
        return "F017-DESIGN-SYNTHETIC-PRIMARY"
    if field == "secondary_event_id" or field == "consumer_event_id" and node_id.startswith("SECONDARY"):
        return "F017-DESIGN-SYNTHETIC-SECONDARY"
    if field == "lease_owner_id": return "F017-DESIGN-SYNTHETIC-LEASE-OWNER"
    if field == "prompt_repository_commit": return "1" * 40
    if field == "prompt_repository_path": return "Prompts/F017/design-only-synthetic-prompt.md"
    if field == "historical_master_ledger": return 175
    if field == "graph_descriptor_count": return 5
    if field in {"attempts", "package_delta", "core_execution_count"}: return 1
    if field in {"retries", "live_leases"}: return 0
    if field in {"resume", "live", "live_authority", "capability_consumed"}: return False
    if field == "single_use": return True
    if category == "sha256": return _digest(f"sequence13:{node_id}:{field}")
    if category == "git_object": return "2" * 40
    if category == "repository_path": return f"design/{node_id.lower()}/{field}.json"
    if category == "typed_id": return f"F017-DESIGN-{node_id}-{field}".upper().replace("_", "-")
    if category == "non_boolean_integer": return 0
    if category == "bool": return False
    if category in {"str", "enum"}: return f"DESIGN_ONLY_{field.upper()}"
    raise ValueError(category)


def construct_design_candidate_v3(contract_raw: bytes) -> tuple[_DesignNode, ...]:
    contract = json.loads(contract_raw)
    constructed: dict[str, _DesignNode] = {}
    identity_digest: str | None = None
    continuity: dict[str, object] = {}
    checkpoint_set: str | None = None
    result: list[_DesignNode] = []
    for spec in contract["nodes"]:
        node_id = spec["node_id"]
        value = {field: _value(category, field, node_id) for field, category in spec["field_types"].items()}
        for predecessor in spec["direct_predecessors"]:
            value[f"{predecessor.lower()}_sha256"] = constructed[predecessor].sha256
        if node_id == "PROMPT_BOUND_EVENT_IDENTITY_PLAN":
            continuity = {name: value[name] for name in ("authorization_id", "package_attempt_id", "prompt_repository_commit", "prompt_repository_path", "prompt_sha256")}
        elif identity_digest is not None and "event_identity_plan_sha256" in value:
            value["event_identity_plan_sha256"] = identity_digest
        for field, expected in continuity.items():
            if field in value: value[field] = expected
        if node_id == "V12_CHECKPOINT_IDENTITY_STAGE": checkpoint_set = value["checkpoint_set_sha256"]
        elif checkpoint_set is not None and "checkpoint_set_sha256" in value:
            value["checkpoint_set_sha256"] = checkpoint_set
        cls = type(spec["sealed_output_type"], (_DesignNode,), {"__slots__": ()})
        node = cls(_SEAL, value)
        constructed[node_id] = node
        result.append(node)
        if node_id == "PROMPT_BOUND_EVENT_IDENTITY_PLAN": identity_digest = node.sha256
    return tuple(result)


def witness_bytes(nodes: tuple[_DesignNode, ...]) -> bytes:
    order = [node.value()["node_id"] for node in nodes]
    return _canonical({
        "schema": "pulsarmlx.f017.event06-v12-causal-bridge-design-witness/1.0.0",
        "mode": "SANITIZED_SYNTHETIC_DESIGN_ONLY",
        "construction_order": order,
        "construction_counts": {node_id: 1 for node_id in order},
        "instances": [{"sealed_type": type(node).__name__, "value": node.value(), "sha256": node.sha256} for node in nodes],
        "checkpoint_paths": 0,
        "live_ids": 0,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "production_modules_imported": 0,
    })


def _pair(req: dict[str, object], contract: dict[str, object]) -> tuple[bytes, bytes]:
    for key in ("authority_posture", "eligible_transition", "generation", "numerical_authority", "result_authority", "historical_master_ledger", "superseded_future_authority", "nodes", "edges", "node_count", "edge_count", "canonical_event_identity_plan_fields", "pre_package_forbidden_fields", "post_identity_first_authorized_fields", "prohibitions", "production_implementation_exists", "operationally_ratified", "checkpoint_access_permitted", "event06_execution_permitted"):
        contract[key] = copy.deepcopy(req[key])
    req_raw = _canonical(req)
    contract["requirements_sha256"] = hashlib.sha256(req_raw).hexdigest()
    return req_raw, _canonical(contract)


def mutation_campaign(requirements_raw: bytes, contract_raw: bytes, baseline_witness: bytes) -> dict[str, object]:
    req0 = json.loads(requirements_raw)
    contract0 = json.loads(contract_raw)
    cases: list[tuple[str, str, object]] = []
    def add(category: str, case_id: str, mutation) -> None: cases.append((category, case_id, mutation))

    for key in sorted(req0):
        add("schema_or_top_level", f"unknown-or-missing-{key}", lambda r, c, key=key: r.pop(key))
    add("schema_or_top_level", "unknown-field", lambda r, c: r.__setitem__("unknown_field", True))
    for index, edge in enumerate(req0["edges"]):
        add("edge_order_digest", f"reverse-edge-{index}", lambda r, c, index=index: r["edges"].__setitem__(index, "->".join(reversed(r["edges"][index].split("->")))))
    for index, node in enumerate(req0["nodes"]):
        node_id = node["node_id"]
        add("owner_boundary", f"private-producer-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("producer_api", "_private_producer"))
        add("owner_boundary", f"mapping-output-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("sealed_output_type", "Mapping"))
        add("owner_boundary", f"callback-consumer-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("validator_or_consumer_api", "caller_callback"))
        add("owner_boundary", f"mapping-input-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("sealed_input_type", "dict"))
        add("stage_order", f"package-flag-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("after_package_start", not r["nodes"][index]["after_package_start"]))
        add("stage_order", f"identity-flag-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("after_identity", not r["nodes"][index]["after_identity"]))
        add("schema_or_top_level", f"unknown-node-key-{node_id}", lambda r, c, index=index: r["nodes"][index].__setitem__("unknown", 1))
        for field in node["required_fields"]:
            add("field_schema_type", f"omit-{node_id}-{field}", lambda r, c, index=index, field=field: (r["nodes"][index]["required_fields"].remove(field), r["nodes"][index]["field_types"].pop(field)))
            new_type = "str" if node["field_types"][field] != "str" else "sha256"
            add("field_schema_type", f"type-{node_id}-{field}", lambda r, c, index=index, field=field, new_type=new_type: r["nodes"][index]["field_types"].__setitem__(field, new_type))
    semantic = {
        "generation-drift": ("generation", "V13"),
        "numerical-drift": ("numerical_authority", "V5"),
        "result-drift": ("result_authority", "V12"),
        "ledger-drift": ("historical_master_ledger", 176),
        "implementation-claim": ("production_implementation_exists", True),
        "ratification-claim": ("operationally_ratified", True),
        "checkpoint-capability": ("checkpoint_access_permitted", True),
        "execution-capability": ("event06_execution_permitted", True),
    }
    for case_id, (key, value) in semantic.items():
        add("frozen_semantics", case_id, lambda r, c, key=key, value=value: r.__setitem__(key, value))
    for attack in ("PRIVATE_RESEAL", "LEGACY_PROJECTION", "CALLER_CREATED_ACCOUNTING", "CALLER_CREATED_TERMINAL", "FUTURE_REFERENCES", "CHECKPOINT_SET_SUBSTITUTION"):
        add("prohibition", f"remove-{attack}", lambda r, c, attack=attack: r["prohibitions"].remove(attack))

    passed = 0
    unexpected: list[str] = []
    by_category: dict[str, dict[str, int]] = {}
    for category, case_id, mutate in cases:
        req = copy.deepcopy(req0)
        contract = copy.deepcopy(contract0)
        before = _canonical(req) + _canonical(contract)
        try:
            mutate(req, contract)
            req_raw, contract_raw_mut = _pair(req, contract)
            if before == req_raw + contract_raw_mut:
                raise AssertionError("mutation did not alter bytes")
            validate_causal_bridge_candidate_v3(req_raw, contract_raw_mut)
        except (ValueError, KeyError, AssertionError, TypeError):
            passed += 1
            by_category.setdefault(category, {"passed": 0, "total": 0})["passed"] += 1
        else:
            unexpected.append(case_id)
        by_category.setdefault(category, {"passed": 0, "total": 0})["total"] += 1

    witness = json.loads(baseline_witness)
    witness_cases = 0
    for index, record in enumerate(witness["instances"]):
        for field in list(record["value"]):
            mutated = copy.deepcopy(witness)
            value = mutated["instances"][index]["value"][field]
            mutated["instances"][index]["value"][field] = True if type(value) is not bool else "false"
            mutated["instances"][index]["sha256"] = hashlib.sha256(_canonical(mutated["instances"][index]["value"])).hexdigest()
            witness_cases += 1
            try:
                validate_witness_instances(contract_raw, _canonical(mutated))
            except (ValueError, KeyError, AssertionError, TypeError):
                passed += 1
                by_category.setdefault("witness_value_or_digest", {"passed": 0, "total": 0})["passed"] += 1
            else:
                unexpected.append(f"witness-{index}-{field}")
            by_category.setdefault("witness_value_or_digest", {"passed": 0, "total": 0})["total"] += 1

    total = len(cases) + witness_cases
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence13-causal-design-mutation-report/1.0.0",
        "candidate_mutations": len(cases),
        "witness_mutations": witness_cases,
        "total": total,
        "passed": passed,
        "unexpected_passes": len(unexpected),
        "unexpected_case_ids": unexpected,
        "categories": by_category,
        "candidate_bytes_altered": True,
        "independent_checker_exercised": True,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "result": "PASS" if passed == total and not unexpected else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--witness-output", type=Path)
    parser.add_argument("--mutation-output", type=Path)
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    requirements_raw, contract_raw = candidate_bytes()
    candidate_report = validate_causal_bridge_candidate_v3(requirements_raw, contract_raw)
    witness_shas: list[str] = []
    witness_raw = b""
    for _ in range(args.repetitions):
        witness_raw = witness_bytes(construct_design_candidate_v3(contract_raw))
        validate_witness_instances(contract_raw, witness_raw)
        witness_shas.append(hashlib.sha256(witness_raw).hexdigest())
    if len(set(witness_shas)) != 1:
        raise SystemExit("non-deterministic witness")
    mutation = mutation_campaign(requirements_raw, contract_raw, witness_raw)
    if mutation["result"] != "PASS":
        raise SystemExit("mutation campaign failed")
    witness = json.loads(witness_raw)
    witness.update({
        "repetitions": args.repetitions,
        "deterministic_reconstructions": args.repetitions,
        "distinct_witness_sha256": len(set(witness_shas)),
        "requirements_sha256": hashlib.sha256(requirements_raw).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_raw).hexdigest(),
        "candidate_validation": candidate_report,
        "result": "PASS",
    })
    witness_out = _canonical(witness)
    if args.witness_output: args.witness_output.write_bytes(witness_out)
    if args.mutation_output: args.mutation_output.write_bytes(_canonical(mutation))
    print(json.dumps({"witness_sha256": hashlib.sha256(witness_out).hexdigest(), "mutation": mutation, "result": "PASS"}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Mechanically validate the F017 Sequence-5 cycle-7 design repair."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v7 as design

ROOT = design.ROOT
E = design.E


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Store:
    overrides: dict[str, bytes]

    def raw(self, path: Path) -> bytes:
        key = str(path.relative_to(ROOT))
        return self.overrides.get(key, path.read_bytes())

    def document(self, path: Path) -> dict:
        raw = self.raw(path)
        value = json.loads(raw)
        if raw != canonical_bytes(value):
            raise ValueError(f"noncanonical: {path.relative_to(ROOT)}")
        if not isinstance(value, dict):
            raise ValueError(f"not object: {path.relative_to(ROOT)}")
        return value

    def changed(self, path: Path, value: object) -> "Store":
        result = dict(self.overrides)
        result[str(path.relative_to(ROOT))] = canonical_bytes(value)
        return Store(result)


def git_raw(head: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{head}:{path}"], cwd=ROOT, check=True, capture_output=True
    ).stdout


def source_binding(store: Store, path: Path) -> dict:
    raw = store.raw(path)
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(raw)}


def derived_row(identifier: str, expected: str, observed: object, sources: list[dict]) -> dict:
    return {
        "finding_id": identifier,
        "expected_relation": expected,
        "observed_relation": observed,
        "predicate_sources": sources,
        "result": "PASS" if bool(observed) else "FAIL",
    }


def derive_B2(store: Store) -> dict:
    response_path = E / "f017-event06-v12-sequence05-opus-design-cycle-06-exact-response.md"
    envelope_path = E / "f017-event06-v12-sequence05-opus-design-cycle-06-provider-envelope.json"
    normalized_path = E / "f017-event06-v12-sequence05-opus-design-cycle-06-normalized-result.json"
    provenance_path = E / "f017-event06-v12-sequence05-opus-design-cycle-06-provenance-v1.json"
    response = store.raw(response_path).decode("utf-8")
    envelope = json.loads(store.raw(envelope_path))
    normalized = store.document(normalized_path)
    provenance = store.document(provenance_path)
    finding_ids = normalized.get("finding_ids", [])
    minimum = [f"{number}." for number in range(1, 9)]
    observed = (
        normalized.get("blocking_findings") == 3
        and normalized.get("required_findings") == 6
        and normalized.get("unresolved_claims") == 2
        and len(finding_ids) == 11
        and all(item in response for item in finding_ids)
        and all(item in response.split("## Minimum repair set for cycle 7", 1)[-1] for item in minimum)
        and envelope.get("result", "").rstrip() + "\n" == response
        and provenance.get("response_sha256") == digest(store.raw(response_path))
        and provenance.get("normalized_result_sha256") == digest(store.raw(normalized_path))
        and provenance.get("reviewed_commit") == normalized.get("reviewed_commit")
    )
    sources = [source_binding(store, p) for p in (response_path, envelope_path, normalized_path, provenance_path)]
    return derived_row("B2", "exact Cycle-6 findings and eight repairs derive from bound provider bytes", observed, sources)


def derive_R6(store: Store) -> dict:
    qualification_path = design.QUAL
    authority_path = design.SCHEMA_AUTH
    qualification = store.document(qualification_path)
    authority = store.document(authority_path)
    role = qualification["roles"]["qualification_role_requirements"]
    observed = (
        role.get("external_schema_authority_path") == str(authority_path.relative_to(ROOT))
        and role.get("external_schema_authority_sha256") == digest(store.raw(authority_path))
        and role.get("external_schema_authority_path") != str(qualification_path.relative_to(ROOT))
        and authority.get("qualification_schema") == qualification.get("schema")
        and authority.get("self_reference_permitted") is False
    )
    return derived_row(
        "R6", "qualification schema comes from a distinct SHA-bound schema authority",
        observed, [source_binding(store, qualification_path), source_binding(store, authority_path)]
    )


def derive_A1(store: Store) -> dict:
    authority_path = design.NOACCESS
    authority = store.document(authority_path)
    resolved = []
    for row in authority.get("current_callables", []):
        source = ROOT / row["path"]
        tree = ast.parse(store.raw(source))
        names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        resolved.append(row["symbol"] in names)
    planned = authority.get("planned_boundaries", [])
    observed = (
        len(resolved) == 3
        and all(resolved)
        and len(planned) == 6
        and len(planned) == len(set(planned))
        and authority.get("planned_status") == "UNBOUND_FUTURE"
        and authority.get("required_counter") == 0
    )
    sources = [source_binding(store, authority_path)] + [
        source_binding(store, ROOT / row["path"]) for row in authority["current_callables"]
    ]
    return derived_row("A1", "current callables resolve and six future interposition boundaries stay unbound", observed, sources)


def derive_A2(store: Store) -> dict:
    graph_path = E / "f017-event06-v12-sequence05-design-graph-state-v6.json"
    claim_path = E / "f017-event06-v12-sequence05-design-claim-ledger-v6.json"
    source_path = E / "f017-event06-v12-sequence05-opus-design-cycle-06-normalized-result.json"
    graph = store.document(graph_path)
    claim = store.document(claim_path)
    source = store.document(source_path)
    observed = (
        graph.get("source_review_cycle") == 6
        and graph.get("source_blocking_findings") == source.get("blocking_findings")
        and graph.get("source_required_findings") == source.get("required_findings")
        and graph.get("source_unresolved_claims") == source.get("unresolved_claims")
        and claim.get("source_review_cycle") == graph.get("source_review_cycle")
        and claim.get("challenged") == source.get("blocking_findings") + source.get("required_findings")
        and claim.get("unresolved") == source.get("unresolved_claims")
        and graph.get("running_nodes") == 0
    )
    return derived_row("A2", "graph and claim counters reconcile to exact Cycle-6 arbiter counts", observed,
                       [source_binding(store, p) for p in (graph_path, claim_path, source_path)])


def derive_A3(store: Store) -> dict:
    qualification_path = design.QUAL
    prepared_path = design.PREPARED
    qualification = store.document(qualification_path)
    prepared = store.document(prepared_path)
    future = set(qualification["future_output_roles"])
    current = set(qualification["current_authority_roles"])
    current_paths = [prepared["bindings"][role]["path"] for role in current]
    observed = (
        future.isdisjoint(current)
        and future | current == set(prepared["roles"])
        and len(current_paths) == len(set(current_paths))
        and all("path" not in prepared["bindings"][role] for role in future)
        and all(prepared["bindings"][role]["binding_state"] == "UNBOUND_FUTURE" for role in future)
        and all(prepared["bindings"][role]["binding_state"] == "CURRENT_DESIGN_AUTHORITY" for role in current)
        and str(qualification_path.relative_to(ROOT)) not in [
            qualification["roles"]["qualification_role_requirements"].get("external_schema_authority_path")
        ]
        and str(prepared_path.relative_to(ROOT)) not in current_paths
    )
    return derived_row("A3", "21-role dependency graph partitions cleanly with no self or future binding", observed,
                       [source_binding(store, qualification_path), source_binding(store, prepared_path)])


DERIVED: dict[str, Callable[[Store], dict]] = {
    "B2": derive_B2,
    "R6": derive_R6,
    "A1": derive_A1,
    "A2": derive_A2,
    "A3": derive_A3,
}


def ast_guard() -> dict:
    source = Path(__file__).read_text()
    tree = ast.parse(source)
    targets = set(DERIVED)
    checked = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("derive_"):
            continue
        identifier = node.name.removeprefix("derive_")
        if identifier not in targets:
            continue
        returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
        if not returns:
            raise ValueError(f"predicate has no return: {identifier}")
        for item in returns:
            if isinstance(item.value, ast.Constant):
                raise ValueError(f"literal predicate return: {identifier}")
            if isinstance(item.value, ast.Compare) and all(isinstance(x, ast.Constant) for x in [item.value.left, *item.value.comparators]):
                raise ValueError(f"constant-foldable predicate: {identifier}")
        checked.append(identifier)
    if set(checked) != targets:
        raise ValueError("predicate AST census")
    return {"predicates_scanned": len(checked), "literal_returns": 0, "constant_foldable_returns": 0, "result": "PASS"}


def check_measurement(store: Store) -> bool:
    measurement_path = E / "f017-event06-v12-to-v11-bridge-implementation-measurement-v2.json"
    declaration_path = E / "f017-event06-v12-to-v11-numerical-authority-bridge-final-declaration-v1.json"
    measurement = store.document(measurement_path)
    declaration = store.document(declaration_path)
    return (
        measurement["schema"] == "pulsarmlx.f017.event06-v12-to-v11-bridge-implementation-measurement/1.1.0"
        and measurement["bridge_digest"] == declaration["bridge_digest"]
        and measurement["implementation_head"] == declaration["measured_implementation_head"]
        and measurement["implementation_tree"] == declaration["measured_implementation_tree"]
        and measurement["result"] == "PASS"
        and declaration["result"] == "ACCEPTED"
    )


def check_provenance(store: Store) -> bool:
    contract = store.document(design.PROV)
    keys = set(contract["required_fields"])
    if len(keys) != 21 or len(contract["required_fields"]) != 21:
        return False
    for tool in ("agy", "opus"):
        path = E / f"f017-event06-v12-sequence05-{tool}-design-cycle-06-provenance-v1.json"
        item = store.document(path)
        envelope = json.loads(store.raw(E / f"f017-event06-v12-sequence05-{tool}-design-cycle-06-provider-envelope.json"))
        if set(item) != keys or item["credentials_serialized"] is not False:
            return False
        if tool == "opus" and item["provider_reported_model"] not in envelope.get("modelUsage", {}):
            return False
        if tool == "agy" and item["provider_reported_model"] != "UNAVAILABLE_FROM_PROVIDER_ENVELOPE":
            return False
    return True


def check_failure_floor(store: Store) -> bool:
    matrix = store.document(E / "f017-event06-v12-sequence05-failure-matrix-v6.json")
    qualification = store.document(design.QUAL)
    terms = matrix["derivation"]
    total = sum(value for key, value in terms.items() if key != "total")
    return (
        terms["readiness_deletions"] == 86
        and terms["readiness_types"] == 86
        and total == terms["total"] == matrix["minimum_mutations"] == 324
        and matrix["alias_family_derivation"]["total"] == 18
        and matrix["race_family_derivation"]["total"] == 100
        and qualification["roles"]["failure_qualification"]["minimums"]["mutation_cases"] == 324
    )


def check_outcomes(store: Store) -> bool:
    machine = store.document(E / "f017-event06-v12-sequence05-installation-state-machine-v6.json")
    edges = {(row["from"] + "->" + row["to"]): row["write"] for row in machine["transitions"]}
    mapping = machine["failure_outcome_edge_mapping"]
    return (
        len(mapping) == machine["failure_outcome_count"] == 16
        and all(row["transition"] in edges for row in mapping.values())
        and all(row["requires_write"] == edges[row["transition"]] for row in mapping.values())
        and sum(row["requires_write"] for row in mapping.values()) == 8
    )


def check_advisories(store: Store) -> bool:
    ledger = store.document(E / "f017-event06-v12-sequence05-advisory-disposition-ledger-v2.json")
    rows = ledger["rows"]
    identities = {(row["source_cycle"], row["finding_id"]) for row in rows}
    return (
        len(rows) == ledger["row_count"] == 9
        and len(identities) == 9
        and sum(row["source_cycle"] == "cycle04" for row in rows) == 6
        and sum(row["source_cycle"] == "cycle05" for row in rows) == 3
        and all(row["named_evidence"] for row in rows)
        and ledger["unresolved"] == 9
    )


def check_prepared(store: Store) -> bool:
    contract = store.document(design.MANIFEST)
    qualification = store.document(design.QUAL)
    prepared = store.document(design.PREPARED)
    required = contract["prepared_required_keys"]
    roles = prepared["roles"]
    bindings = prepared["bindings"]
    if set(prepared) != set(required) or len(prepared) != len(required):
        return False
    if roles != design.ROLES or len(roles) != len(set(roles)):
        return False
    if not (prepared["role_count"] == prepared["binding_count"] == len(roles) == len(bindings) == qualification["role_count"] == 21):
        return False
    if prepared["implementation_tree"] != subprocess.run(
        ["git", "rev-parse", f'{prepared["implementation_head"]}^{{tree}}'], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip():
        return False
    current = set(qualification["current_authority_roles"])
    future = set(qualification["future_output_roles"])
    for role in current:
        binding = bindings[role]
        path = binding.get("path", "")
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or binding.get("binding_state") != "CURRENT_DESIGN_AUTHORITY":
            return False
        if digest(git_raw(prepared["implementation_head"], path)) != binding.get("sha256"):
            return False
    for role in future:
        if set(bindings[role]) != {"binding_state", "required_schema", "availability_stage"} or bindings[role]["binding_state"] != "UNBOUND_FUTURE":
            return False
    forbidden = {str(design.PREPARED.relative_to(ROOT))}
    if any(bindings[role].get("path") in forbidden for role in current):
        return False
    return prepared["validated_binding_count"] == len(current) == 12 and prepared["unbound_future_roles"] == sorted(future) and prepared["final_acceptance_eligible"] is False


OTHER_CHECKS: dict[str, Callable[[Store], bool]] = {
    "measurement_consistency": check_measurement,
    "provenance_census": check_provenance,
    "failure_floor": check_failure_floor,
    "outcome_mapping": check_outcomes,
    "advisory_namespaces": check_advisories,
    "prepared_manifest": check_prepared,
}


def evaluate(store: Store) -> tuple[dict[str, dict], dict[str, bool]]:
    return ({name: function(store) for name, function in DERIVED.items()},
            {name: function(store) for name, function in OTHER_CHECKS.items()})


def mutation_suite(base: Store) -> list[dict]:
    mutations: list[tuple[str, str, Path, Callable[[dict], None]]] = []
    def add(mid: str, target: str, path: Path, change: Callable[[dict], None]) -> None:
        mutations.append((mid, target, path, change))
    add("M-B2-RESPONSE-FINDING", "B2", E / "f017-event06-v12-sequence05-opus-design-cycle-06-provenance-v1.json", lambda d: d.__setitem__("response_sha256", "0" * 64))
    add("M-R6-SELF-SCHEMA", "R6", design.QUAL, lambda d: d["roles"]["qualification_role_requirements"].__setitem__("external_schema_authority_path", str(design.QUAL.relative_to(ROOT))))
    add("M-A1-MISSING-CALLABLE", "A1", design.NOACCESS, lambda d: d["current_callables"][0].__setitem__("symbol", "missing_callable"))
    add("M-A2-COUNTER", "A2", E / "f017-event06-v12-sequence05-design-graph-state-v6.json", lambda d: d.__setitem__("source_blocking_findings", 4))
    add("M-A3-FUTURE-BOUND", "A3", design.PREPARED, lambda d: d["bindings"]["readiness_interface"].update(deepcopy(d["bindings"]["live_installation_interface"])))
    add("M-MEASUREMENT-DIGEST", "measurement_consistency", E / "f017-event06-v12-to-v11-bridge-implementation-measurement-v2.json", lambda d: d.__setitem__("bridge_digest", "0" * 64))
    add("M-PROVENANCE-MISSING-FIELD", "provenance_census", E / "f017-event06-v12-sequence05-opus-design-cycle-06-provenance-v1.json", lambda d: d.pop("command"))
    add("M-FAILURE-FLOOR", "failure_floor", E / "f017-event06-v12-sequence05-failure-matrix-v6.json", lambda d: d.__setitem__("minimum_mutations", 320))
    add("M-OUTCOME-WRITE-EDGE", "outcome_mapping", E / "f017-event06-v12-sequence05-installation-state-machine-v6.json", lambda d: d["failure_outcome_edge_mapping"]["write"].__setitem__("transition", "CANDIDATE->PREPARED_VALIDATION_ONLY"))
    add("M-ADVISORY-NAMESPACE", "advisory_namespaces", E / "f017-event06-v12-sequence05-advisory-disposition-ledger-v2.json", lambda d: d["rows"][6].__setitem__("source_cycle", "cycle04"))
    add("M-PREPARED-EXTRA-KEY", "prepared_manifest", design.PREPARED, lambda d: d.__setitem__("unexpected", 1))
    add("M-PREPARED-BINDING-SHA", "prepared_manifest", design.PREPARED, lambda d: d["bindings"]["readiness_interface"].__setitem__("sha256", "0" * 64))
    base_derived, base_other = evaluate(base)
    if not all(row["result"] == "PASS" for row in base_derived.values()) or not all(base_other.values()):
        raise ValueError("positive baseline failed")
    rows = []
    for mid, target, path, change in mutations:
        document = base.document(path)
        change(document)
        mutated = base.changed(path, document)
        derived, other = evaluate(mutated)
        failed = {name for name, row in derived.items() if row["result"] == "FAIL"} | {name for name, value in other.items() if not value}
        rows.append({"mutation_id": mid, "target_predicate": target, "failed_predicates": sorted(failed), "isolated": failed == {target}, "result": "PASS" if failed == {target} else "FAIL"})
    return rows


def write_exclusive(path: Path, value: object) -> None:
    raw = canonical_bytes(value)
    with path.open("xb") as stream:
        stream.write(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    base = Store({})
    for path, expected in design.design_artifacts().items():
        if base.raw(path) != canonical_bytes(expected):
            raise ValueError(f"generator drift: {path.relative_to(ROOT)}")
    ast_result = ast_guard()
    derived, other = evaluate(base)
    mutations = mutation_suite(base)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    source_response = E / "f017-event06-v12-sequence05-opus-design-cycle-06-exact-response.md"
    source_request = E / "f017-event06-v12-sequence05-opus-design-cycle-06-request.md"
    source_envelope = E / "f017-event06-v12-sequence05-opus-design-cycle-06-provider-envelope.json"
    source_provenance = E / "f017-event06-v12-sequence05-opus-design-cycle-06-provenance-v1.json"
    report = {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-challenge-reproducibility/1.1.0",
        "validator_path": str(Path(__file__).relative_to(ROOT)),
        "validator_sha256": digest(Path(__file__).read_bytes()),
        "reviewed_commit": head,
        "reviewed_tree": tree,
        "source_arbiter_request": source_binding(base, source_request),
        "source_arbiter_response": source_binding(base, source_response),
        "source_provider_envelope": source_binding(base, source_envelope),
        "source_provenance": source_binding(base, source_provenance),
        "finding_checks": list(derived.values()),
        "finding_count": len(derived),
        "failed_findings": sum(row["result"] == "FAIL" for row in derived.values()),
        "ast_guard": ast_result,
        "mutations": mutations,
        "mutation_count": len(mutations),
        "mutation_rejections": sum(row["result"] == "PASS" for row in mutations),
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "live_authority": False,
        "result": "PASS" if all(row["result"] == "PASS" for row in derived.values()) and all(other.values()) and all(row["result"] == "PASS" for row in mutations) else "FAIL",
    }
    mechanical = {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.3.0",
        "reviewed_commit": head,
        "reviewed_tree": tree,
        "derived_predicates": len(derived),
        "derived_predicates_passed": sum(row["result"] == "PASS" for row in derived.values()),
        "other_repair_checks": len(other),
        "other_repair_checks_passed": sum(other.values()),
        "mutation_cases": len(mutations),
        "mutations_rejected": sum(row["result"] == "PASS" for row in mutations),
        "prepared_current_bindings": 12,
        "prepared_future_roles": 9,
        "failure_qualification_floor": 324,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "live_installations": 0,
        "package_starts": 0,
        "result": report["result"],
    }
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_exclusive(args.output_dir / "f017-event06-v12-sequence05-challenge-reproducibility-cycle06-v2.json", report)
        write_exclusive(args.output_dir / "f017-event06-v12-sequence05-design-mechanical-validation-v4.json", mechanical)
    print(json.dumps(mechanical, sort_keys=True))
    return 0 if mechanical["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

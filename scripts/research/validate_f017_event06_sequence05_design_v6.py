#!/usr/bin/env python3
"""Mechanically validate the F017 Sequence-5 Cycle-9 design repair."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v9 as design


ROOT = design.ROOT
E = design.E


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Store:
    overrides: dict[str, bytes]

    def raw(self, path: Path) -> bytes:
        key = str(path.relative_to(ROOT))
        return self.overrides.get(key, path.read_bytes())

    def document(self, path: Path, canonical: bool = True) -> dict:
        raw = self.raw(path)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"not object: {path.relative_to(ROOT)}")
        if canonical and raw != canonical_bytes(value):
            raise ValueError(f"noncanonical: {path.relative_to(ROOT)}")
        return value

    def changed(self, path: Path, change: Callable[[dict], None]) -> "Store":
        value = self.document(path)
        change(value)
        updated = dict(self.overrides)
        updated[str(path.relative_to(ROOT))] = canonical_bytes(value)
        return Store(updated)


def git_raw(head: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{head}:{path}"], cwd=ROOT, check=True, capture_output=True
    ).stdout


def git_mode(head: str, path: str) -> str:
    output = subprocess.run(
        ["git", "ls-tree", head, "--", path], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.split()
    return output[0] if output else ""


def predicate_repair_ledger(store: Store) -> bool:
    ledger = store.document(design.REPAIR_LEDGER)
    rows = ledger["rows"]
    expected_ids = [row[0] for row in design.OPUS_ROWS]
    expected_severities = {row[0]: row[1] for row in design.OPUS_ROWS}
    overlap = {"C8-F1": "C8-OPUS-B1", "C8-F2": "C8-OPUS-B2", "C8-F3": "C8-OPUS-B3", "C8-F4": "C8-OPUS-R1"}
    return (
        ledger["opus_row_count"] == len(rows) == 15
        and ledger["agy_row_count"] == len(overlap) == 4
        and [row["finding_id"] for row in rows] == expected_ids
        and all(row["severity"] == expected_severities[row["finding_id"]] for row in rows)
        and ledger["agy_overlap_map"] == overlap
        and all(row["mechanical_disposition"] == "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW" for row in rows)
        and ledger["mechanically_closed_rows"] == len(rows)
        and ledger["independently_accepted_rows"] == 0
        and ledger["opus_source_response_sha256"] == digest(store.raw(design.OPUS8))
        and ledger["agy_source_response_sha256"] == digest(store.raw(design.AGY8))
    )


def predicate_schema_externality(store: Store) -> bool:
    authority = store.document(design.SCHEMA)
    qualification = store.document(design.QUAL)
    readiness = store.document(design.READINESS)
    installation = store.document(design.INSTALL)
    path = str(design.SCHEMA.relative_to(ROOT))
    authority_sha = digest(store.raw(design.SCHEMA))
    roles = qualification["roles"]
    mapping = {
        "qualification_role_requirements": ("qualification_schema", qualification["schema"]),
        "readiness_interface": ("readiness_schema", readiness["schema"]),
        "live_installation_interface": ("installation_schema", installation["schema"]),
    }
    for role, (field, actual_schema) in mapping.items():
        item = roles[role]
        path_key = "external_schema_authority_path" if role == "qualification_role_requirements" else "schema_authority_path"
        sha_key = "external_schema_authority_sha256" if role == "qualification_role_requirements" else "schema_authority_sha256"
        if item[path_key] != path or item[sha_key] != authority_sha or item["schema_authority_field"] != field:
            return False
        if authority[field] != actual_schema:
            return False
    return authority["artifact_schema_equality_required"] and not authority["self_reference_permitted"]


def predicate_provenance_contract(store: Store) -> bool:
    contract = store.document(design.PROV)
    fields = contract["required_fields"]
    if len(fields) != contract["required_field_count"] or len(fields) != len(set(fields)):
        return False
    if set(fields) != set(contract["field_types"]):
        return False
    forbidden = set(contract["filesystem_time_sources_forbidden"])
    if not {"st_mtime", "st_ctime", "current_clock", "checkout_time"}.issubset(forbidden):
        return False
    for tool in ("agy", "opus"):
        path = E / f"f017-event06-v12-sequence05-{tool}-design-cycle-07-provenance-v2.json"
        item = store.document(path)
        normalized = store.document(E / f"f017-event06-v12-sequence05-{tool}-design-cycle-07-normalized-result.json")
        if set(item) != set(fields):
            return False
        if item["provider_timing_status"] != "UNAVAILABLE_FROM_PROVIDER_ENVELOPE":
            return False
        if item["provider_started_at_utc"] is not None or item["provider_completed_at_utc"] is not None:
            return False
        if item["capture_source_semantics"] != "RAW_PROVIDER_ENVELOPE_FIELDS_ONLY_NO_FILESYSTEM_TIMES":
            return False
        if item["result"] != "REJECT_REVIEW_BANKED":
            return False
        if item["reviewed_commit"] != normalized["reviewed_commit"] or item["reviewed_tree"] != normalized["reviewed_tree"]:
            return False
        for key in ("request", "response", "normalized_result"):
            if digest(store.raw(ROOT / item[f"{key}_path"])) != item[f"{key}_sha256"]:
                return False
    return contract["raw_provider_envelope_required"] and contract["credentials_serialized"] is False


def predicate_graph_claim_state(store: Store) -> bool:
    graph7 = store.document(E / "f017-event06-v12-sequence05-design-graph-state-v7.json")
    claims7 = store.document(E / "f017-event06-v12-sequence05-design-claim-ledger-v7.json")
    correction_graph = store.document(design.GRAPH8)
    correction_claims = store.document(design.CLAIMS8)
    graph9 = store.document(design.GRAPH9)
    claims9 = store.document(design.CLAIMS9)
    return (
        graph7["status"] == "PASS_PENDING_INDEPENDENT_REVIEW"
        and claims7["status"] == "PASS_PENDING_INDEPENDENT_REVIEW"
        and correction_graph["status"] == "REJECTED"
        and correction_graph["agy"] == {"blocking": 2, "required": 0, "advisory": 0, "unresolved": 0, "verdict": "REJECT"}
        and correction_graph["opus"] == {"blocking": 3, "required": 7, "advisory": 4, "unresolved": 2, "verdict": "REJECT"}
        and correction_claims["status"] == "REJECTED"
        and correction_claims["challenged"] == 10
        and correction_claims["advisory"] == 4
        and correction_claims["unresolved"] == 2
        and graph9["status"] == "PENDING_INDEPENDENT_REVIEW"
        and graph9["source_opus_counts"] == {"blocking": 5, "required": 5, "advisory": 3, "unresolved": 2}
        and graph9["source_agy_counts"] == {"blocking": 4, "required": 0, "advisory": 0, "unresolved": 0}
        and claims9["status"] == "PENDING_INDEPENDENT_REVIEW"
        and claims9["row_count"] == claims9["mechanically_supported"] == 15
        and claims9["independently_accepted"] == 0
        and claims9["prior_unresolved_claims"] == 2
    )


def predicate_qualification_truth(store: Store) -> bool:
    qualification = store.document(design.QUAL)
    return (
        qualification["all_requirements_mechanically_validated"] is False
        and qualification["validation_gap_count"] == len(qualification["active_validation_gap_ids"]) == 1
        and qualification["active_validation_gap_ids"] == ["PENDING_CYCLE9_MECHANICAL_VALIDATION"]
        and qualification["validation_state"] == "PENDING_EXTERNAL_VALIDATOR_EXECUTION"
        and qualification["validation_result_source"] == str(Path(__file__).relative_to(ROOT))
    )


def predicate_advisory_support(store: Store) -> bool:
    vocabulary = store.document(design.DISPOSITION)
    ledger = store.document(design.ADVISORY_LEDGER)
    rows = ledger["rows"]
    identities = {(row["source_cycle"], row["finding_id"]) for row in rows}
    support_paths = [row["support_path"] for row in rows]
    support_shas = [row["support_sha256"] for row in rows]
    if ledger["disposition_vocabulary_sha256"] != digest(store.raw(design.DISPOSITION)):
        return False
    if len(rows) != ledger["row_count"] or ledger["row_count"] == 0 or len(rows) != 12 or len(identities) != 12:
        return False
    if len(support_paths) != len(set(support_paths)) or len(support_shas) != len(set(support_shas)):
        return False
    if any(row["disposition"] not in vocabulary["closed_values"] for row in rows):
        return False
    for row in rows:
        support = store.document(ROOT / row["support_path"])
        if digest(store.raw(ROOT / row["support_path"])) != row["support_sha256"]:
            return False
        if (support["source_cycle"], support["finding_id"]) != (row["source_cycle"], row["finding_id"]):
            return False
        if support["disposition"] != row["disposition"] or not support["finding_specific_claim"]:
            return False
        if digest(store.raw(ROOT / support["support_authority_path"])) != support["support_authority_sha256"]:
            return False
        if support["support_authority_path"] == str(Path(__file__).relative_to(ROOT)):
            return False
    return (
        ledger["mechanically_resolved_pending_review"] == sum(row["disposition"] == vocabulary["pre_review_value"] for row in rows)
        and ledger["independently_accepted"] == sum(row["disposition"] == vocabulary["acceptance_value"] for row in rows)
        and ledger["unresolved"] == sum(row["disposition"] == "UNRESOLVED" for row in rows)
        and ledger["counters_derived_from_rows"]
    )


def predicate_generator_policy(store: Store) -> bool:
    policy = store.document(design.GENERATOR_POLICY)
    return (
        policy["filesystem_timestamps_as_authority"] is False
        and policy["working_tree_must_remain_clean"]
        and policy["registered_validator_predicate_required"]
        and policy["negative_mutation_required"]
        and policy["generator_path"] == str(Path(design.__file__).relative_to(ROOT))
    )


@lru_cache(maxsize=1)
def actual_clean_clone_reproducibility() -> bool:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    results = []
    for stamp in ("200101010101", "203512312359"):
        temporary = Path(tempfile.mkdtemp(prefix="f017-seq7-generator-check-"))
        clone = temporary / "repo"
        try:
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(ROOT), str(clone)], check=True)
            subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", "--detach", head], check=True)
            for tool in ("agy", "opus"):
                envelope = clone / "docs/architecture/reviews/evidence" / f"f017-event06-v12-sequence05-{tool}-design-cycle-07-provider-envelope.json"
                subprocess.run(["touch", "-t", stamp, str(envelope)], check=True)
            run = subprocess.run(
                ["python3", "scripts/research/generate_f017_event06_sequence05_design_v9.py", "--check"],
                cwd=clone, capture_output=True, text=True,
            )
            clean = not subprocess.run(["git", "status", "--porcelain"], cwd=clone, check=True, capture_output=True, text=True).stdout
            results.append(run.returncode == 0 and clean)
        finally:
            shutil.rmtree(temporary)
    return len(results) == 2 and all(results)


def predicate_generator_reproducibility(store: Store) -> bool:
    policy = store.document(design.GENERATOR_POLICY)
    return (
        policy["clean_clone_check_required"]
        and policy["different_filesystem_mtimes_required"]
        and policy["repetitions"] == 2
        and actual_clean_clone_reproducibility()
    )


def predicate_review_head_identity(store: Store) -> bool:
    policy = store.document(design.GENERATOR_POLICY)
    graph = store.document(design.GRAPH9)
    return (
        policy["review_identity_policy"] == "EXACT_REVIEWED_HEAD_TREE_DISTINCT_FROM_LATER_EVIDENCE_PUBLICATION_HEAD_TREE"
        and policy["review_request_must_bind_exact_head_tree"]
        and policy["normalized_result_must_bind_exact_head_tree"]
        and graph["independent_review_status"] == "PENDING"
        and graph["status"] == "PENDING_INDEPENDENT_REVIEW"
    )


def predicate_alias_axes(store: Store) -> bool:
    authority = store.document(design.ALIAS)
    matrix = store.document(design.FAILURE_MATRIX)
    semantic = authority["semantic_families"]
    structural = authority["independent_structural_locations"]
    expected = [
        {"case_id": f"ALIAS-{family}-{location}", "semantic_family": family, "structural_location": location}
        for family in semantic for location in structural
    ]
    binding = matrix["alias_family_derivation"]
    return (
        authority["semantic_family_count"] == len(semantic) == len(set(semantic)) == 6
        and authority["structural_location_count"] == len(structural) == len(set(structural)) == 3
        and authority["axis_namespaces_disjoint"] == (not set(semantic).intersection(structural))
        and authority["cases"] == expected
        and authority["derived_case_count"] == len(expected) == 18
        and authority["duplicate_case_ids"] == len(expected) - len({row["case_id"] for row in expected}) == 0
        and binding["authority_sha256"] == digest(store.raw(design.ALIAS))
        and binding["semantic_families"] == semantic
        and binding["independent_structural_locations"] == structural
        and binding["total"] == len(expected)
    )


def predicate_failure_arithmetic(store: Store) -> bool:
    readiness = store.document(design.READINESS)
    matrix = store.document(design.FAILURE_MATRIX)
    qualification = store.document(design.QUAL)
    terms = matrix["derivation"]
    expected = (
        len(readiness["required_fields"])
        + sum(len(items) for items in readiness["exact_types"].values())
        + len(readiness["exact_predicates"])
        + matrix["alias_family_derivation"]["total"]
        + len(matrix["race_family_derivation"]["families"]) * matrix["race_family_derivation"]["repetitions_per_family"]
    )
    return (
        terms["total"] == expected == matrix["minimum_mutations"]
        and terms["alternate_encoding_alias_binding_floor"] == matrix["alias_family_derivation"]["total"]
        and terms["installation_and_race_floor"] == matrix["race_family_derivation"]["total"]
        and qualification["roles"]["failure_qualification"]["minimums"]["mutation_cases"] == expected
    )


def predicate_outcome_mapping(store: Store) -> bool:
    machine = store.document(design.STATE_MACHINE)
    matrix = store.document(design.FAILURE_MATRIX)
    edges = {row["from"] + "->" + row["to"]: row["write"] for row in machine["transitions"]}
    mapping = machine["failure_outcome_edge_mapping"]
    return (
        set(mapping) == set(matrix["category_outcomes"])
        and len(mapping) == machine["failure_outcome_count"] == 16
        and all(row["transition"] in edges and row["requires_write"] == edges[row["transition"]] for row in mapping.values())
    )


def predicate_prepared_manifest(store: Store) -> bool:
    if not design.PREPARED.is_file():
        return False
    prepared = store.document(design.PREPARED)
    manifest = store.document(design.MANIFEST)
    qualification = store.document(design.QUAL)
    current = set(qualification["current_authority_roles"])
    future = set(qualification["future_output_roles"])
    bindings = prepared["bindings"]
    if prepared["schema"] != manifest["prepared_instance_schema"] or prepared["roles"] != design.ROLES:
        return False
    if current.intersection(future) or current.union(future) != set(design.ROLES):
        return False
    if prepared["role_count"] != prepared["binding_count"] or prepared["role_count"] != len(bindings):
        return False
    tree = subprocess.run(["git", "rev-parse", f"{prepared['implementation_head']}^{{tree}}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    if tree != prepared["implementation_tree"]:
        return False
    forbidden = set(manifest["forbidden_current_binding_paths"])
    for role in current:
        binding = bindings[role]
        path = binding.get("path", "")
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or path in forbidden:
            return False
        if binding.get("binding_state") != "CURRENT_DESIGN_AUTHORITY" or git_mode(prepared["implementation_head"], path) == "120000":
            return False
        if digest(git_raw(prepared["implementation_head"], path)) != binding.get("sha256"):
            return False
    for role in future:
        if set(bindings[role]) != {"binding_state", "required_schema", "availability_stage"}:
            return False
        if bindings[role]["binding_state"] != "UNBOUND_FUTURE":
            return False
    return prepared["validated_binding_count"] == len(current) and not prepared["final_acceptance_eligible"] and not prepared["live_authority"]


def predicate_measurement_consistency(store: Store) -> bool:
    summary = store.document(design.v8.BRIDGE_SUMMARY)
    declaration = store.document(ROOT / summary["historical_declaration_path"], canonical=False)
    measurement = store.document(ROOT / summary["implementation_measurement_v2_path"], canonical=False)
    return (
        summary["historical_declaration_sha256"] == digest(store.raw(ROOT / summary["historical_declaration_path"]))
        and summary["implementation_measurement_v2_sha256"] == digest(store.raw(ROOT / summary["implementation_measurement_v2_path"]))
        and summary["bridge_digest"] == declaration["bridge_digest"] == measurement["bridge_digest"]
        and summary["implementation_head"] == declaration["measured_implementation_head"] == measurement["implementation_head"]
        and summary["implementation_tree"] == declaration["measured_implementation_tree"] == measurement["implementation_tree"]
        and summary["source_values_consistent"]
    )


def predicate_no_access(store: Store) -> bool:
    authority = store.document(design.v8.NOACCESS)
    resolved = []
    for row in authority["current_callables"]:
        tree = ast.parse(store.raw(ROOT / row["path"]))
        names = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        resolved.append(row["symbol"] in names)
    return (
        len(resolved) == 3 and all(resolved)
        and len(authority["planned_boundaries"]) == len(set(authority["planned_boundaries"])) == 6
        and authority["planned_status"] == "UNBOUND_FUTURE"
        and authority["required_counter"] == 0
    )


PREDICATES: dict[str, Callable[[Store], bool]] = {
    "repair_ledger": predicate_repair_ledger,
    "schema_externality": predicate_schema_externality,
    "provenance_contract": predicate_provenance_contract,
    "graph_claim_state": predicate_graph_claim_state,
    "qualification_truth": predicate_qualification_truth,
    "advisory_support": predicate_advisory_support,
    "generator_policy": predicate_generator_policy,
    "generator_reproducibility": predicate_generator_reproducibility,
    "review_head_identity": predicate_review_head_identity,
    "alias_axes": predicate_alias_axes,
    "failure_arithmetic": predicate_failure_arithmetic,
    "outcome_mapping": predicate_outcome_mapping,
    "prepared_manifest": predicate_prepared_manifest,
    "measurement_consistency": predicate_measurement_consistency,
    "no_access": predicate_no_access,
}


def _truthy_constant_return(node: ast.Return) -> bool:
    value = node.value
    if isinstance(value, ast.Constant):
        return bool(value.value)
    if isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return bool(value.elts if not isinstance(value, ast.Dict) else value.keys)
    if isinstance(value, ast.BinOp):
        operands = [item for item in ast.walk(value) if isinstance(item, ast.Name)]
        return not operands
    return False


def _scan_registry(path: Path, registry: dict, prefix: str) -> list[str]:
    tree = ast.parse(path.read_text())
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    registered_names = [function.__name__ for function in registry.values()]
    if len(registered_names) != len(set(registered_names)):
        raise ValueError("duplicate registered predicate implementation")
    discovered = {name for name in functions if name.startswith(prefix)}
    if discovered != set(registered_names):
        raise ValueError(f"registry mismatch: {path.name}")
    scanned = []
    normalized_bodies = set()
    for name in registered_names:
        node = functions[name]
        returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
        if not returns or any(_truthy_constant_return(item) for item in returns):
            raise ValueError(f"constant or missing predicate return: {name}")
        for item in ast.walk(node):
            if isinstance(item, ast.ExceptHandler):
                if any(isinstance(statement, ast.Pass) for statement in item.body):
                    raise ValueError(f"swallowed exception: {name}")
                if any(isinstance(statement, ast.Return) and _truthy_constant_return(statement) for statement in item.body):
                    raise ValueError(f"success from exception: {name}")
        body = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
        if body in normalized_bodies:
            raise ValueError(f"duplicate predicate body: {name}")
        normalized_bodies.add(body)
        scanned.append(name)
    return sorted(scanned)


def ast_guard() -> dict:
    validator_scanned = _scan_registry(Path(__file__), PREDICATES, "predicate_")
    generator_scanned = _scan_registry(Path(design.__file__), design.GENERATOR_PREDICATES, "generator_predicate_")
    return {
        "validator_registry_count": len(PREDICATES),
        "validator_predicates_scanned": validator_scanned,
        "generator_registry_count": len(design.GENERATOR_PREDICATES),
        "generator_predicates_scanned": generator_scanned,
        "unregistered_predicates": 0,
        "duplicate_predicate_bodies": 0,
        "literal_or_constant_foldable_success_returns": 0,
        "swallowed_success_exceptions": 0,
        "result": "PASS",
    }


def evaluate(store: Store) -> dict[str, bool]:
    return {name: predicate(store) for name, predicate in PREDICATES.items()}


def mutation_suite(base: Store) -> list[dict]:
    cases: list[tuple[str, str, Path, Callable[[dict], None]]] = [
        ("M-PRED-REPAIR", "repair_ledger", design.REPAIR_LEDGER, lambda d: d.__setitem__("opus_row_count", 14)),
        ("M-PRED-SCHEMA", "schema_externality", design.SCHEMA, lambda d: d.__setitem__("readiness_schema", "pulsarmlx.f017.BOGUS/9.9.9")),
        ("M-PRED-PROVENANCE", "provenance_contract", design.PROV, lambda d: d["required_fields"].pop()),
        ("M-PRED-GRAPH", "graph_claim_state", design.GRAPH9, lambda d: d.__setitem__("status", "FABRICATED")),
        ("M-PRED-QUALIFICATION", "qualification_truth", design.QUAL, lambda d: d.__setitem__("validation_gap_count", 0)),
        ("M-PRED-ADVISORY", "advisory_support", design.ADVISORY_LEDGER, lambda d: d["rows"][0].__setitem__("disposition", "UNRESOLVED")),
        ("M-PRED-GENERATOR-POLICY", "generator_policy", design.GENERATOR_POLICY, lambda d: d.__setitem__("filesystem_timestamps_as_authority", True)),
        ("M-PRED-GENERATOR-REPRO", "generator_reproducibility", design.GENERATOR_POLICY, lambda d: d.__setitem__("repetitions", 1)),
        ("M-PRED-REVIEW-HEAD", "review_head_identity", design.GENERATOR_POLICY, lambda d: d.__setitem__("review_request_must_bind_exact_head_tree", False)),
        ("M-PRED-ALIAS", "alias_axes", design.ALIAS, lambda d: d.__setitem__("derived_case_count", 999)),
        ("M-PRED-FAILURE", "failure_arithmetic", design.FAILURE_MATRIX, lambda d: d["derivation"].__setitem__("total", 999)),
        ("M-PRED-OUTCOME", "outcome_mapping", design.STATE_MACHINE, lambda d: d["failure_outcome_edge_mapping"]["write"].__setitem__("transition", "CANDIDATE->PREPARED_VALIDATION_ONLY")),
        ("M-PRED-PREPARED", "prepared_manifest", design.PREPARED, lambda d: d["bindings"]["readiness_interface"].__setitem__("sha256", "0" * 64)),
        ("M-PRED-MEASUREMENT", "measurement_consistency", design.v8.BRIDGE_SUMMARY, lambda d: d.__setitem__("bridge_digest", "0" * 64)),
        ("M-PRED-NOACCESS", "no_access", design.v8.NOACCESS, lambda d: d["current_callables"][0].__setitem__("symbol", "missing_callable")),
    ]
    baseline = evaluate(base)
    if not all(baseline.values()):
        raise ValueError(f"positive baseline failed: {[key for key, value in baseline.items() if not value]}")
    rows = []
    dependency_sets = {
        "repair_ledger": {"repair_ledger", "advisory_support"},
        "schema_externality": {"schema_externality", "advisory_support"},
        "provenance_contract": {"provenance_contract", "advisory_support"},
        "graph_claim_state": {"graph_claim_state", "review_head_identity"},
        "qualification_truth": {"qualification_truth"},
        "advisory_support": {"advisory_support"},
        "generator_policy": {"generator_policy", "advisory_support"},
        "generator_reproducibility": {"generator_reproducibility", "advisory_support"},
        "review_head_identity": {"review_head_identity", "advisory_support"},
        "alias_axes": {"alias_axes"},
        "failure_arithmetic": {"failure_arithmetic"},
        "outcome_mapping": {"outcome_mapping", "advisory_support"},
        "prepared_manifest": {"prepared_manifest"},
        "measurement_consistency": {"measurement_consistency"},
        "no_access": {"no_access", "advisory_support"},
    }
    for mutation_id, target, path, change in cases:
        values = evaluate(base.changed(path, change))
        failed = sorted(name for name, value in values.items() if not value)
        expected = sorted(dependency_sets[target])
        rows.append({
            "mutation_id": mutation_id, "target": target, "failed_predicates": failed,
            "declared_dependency_set": expected,
            "isolated": failed == [target],
            "result": "PASS" if failed == expected else "FAIL",
        })
    for index, row in enumerate(design.OPUS_ROWS, 1):
        finding_id = row[0]
        def alter(document: dict, finding_id: str = finding_id) -> None:
            next(item for item in document["rows"] if item["finding_id"] == finding_id)["mechanical_disposition"] = "OPEN"
        values = evaluate(base.changed(design.REPAIR_LEDGER, alter))
        failed = sorted(name for name, value in values.items() if not value)
        rows.append({
            "mutation_id": f"M-ROW-{index:02d}-{finding_id}",
            "target": f"repair_row:{finding_id}",
            "failed_predicates": failed,
            "declared_dependency_set": ["advisory_support", "repair_ledger"],
            "isolated": False,
            "result": "PASS" if failed == ["advisory_support", "repair_ledger"] else "FAIL",
        })
    return rows


def report(store: Store) -> dict:
    values = evaluate(store)
    mutations = mutation_suite(Store({}))
    guard = ast_guard()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    ok = all(values.values()) and all(row["result"] == "PASS" for row in mutations) and guard["result"] == "PASS"
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.5.0",
        "validation_subject_head": head,
        "validation_subject_tree": tree,
        "later_review_evidence_publication_head": "NOT_YET_CREATED",
        "predicate_results": values,
        "registered_predicates": len(values),
        "registered_predicate_passes": sum(values.values()),
        "ast_guard": guard,
        "mutations": mutations,
        "mutation_count": len(mutations),
        "mutation_rejections": sum(row["result"] == "PASS" for row in mutations),
        "cycle8_opus_rows_closed": 15 if values["repair_ledger"] else 0,
        "cycle8_agy_rows_closed": 4 if values["repair_ledger"] else 0,
        "generator_clean_clone_repetitions": 2,
        "generator_clean_clone_reproducibility": "PASS" if values["generator_reproducibility"] else "FAIL",
        "all_requirements_mechanically_validated": all(values.values()),
        "validation_gap_count": sum(not value for value in values.values()),
        "validation_gap_ids": sorted(name for name, value in values.items() if not value),
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "live_authority": False,
        "event_06_executed": False,
        "result": "PASS" if ok else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inject-defect", action="store_true")
    args = parser.parse_args()
    store = Store({})
    if args.inject_defect:
        store = store.changed(design.SCHEMA, lambda d: d.__setitem__("readiness_schema", "pulsarmlx.f017.INJECTED/0.0.0"))
    value = report(store)
    if args.output:
        with args.output.open("xb") as stream:
            stream.write(canonical_bytes(value))
    print(json.dumps(value, sort_keys=True))
    return 0 if value["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

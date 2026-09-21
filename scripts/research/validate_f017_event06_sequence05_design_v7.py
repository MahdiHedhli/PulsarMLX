#!/usr/bin/env python3
"""Validate the Cycle-10 repair of the Event-06 Sequence-5 design authority."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import operator
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Callable

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v10 as design
import validate_f017_event06_sequence05_design_v6 as prior


ROOT = design.ROOT
Store = prior.Store
UNKNOWN = object()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, check=check, capture_output=True, text=True
    )


def predicate_advisory_source_response(store: Store) -> bool:
    ledger = store.document(design.v9.ADVISORY_LEDGER)
    vocabulary = store.document(design.v9.DISPOSITION)
    rows = ledger["rows"]
    identities = {(row["source_cycle"], row["finding_id"]) for row in rows}
    if ledger["disposition_vocabulary_sha256"] != digest(store.raw(design.v9.DISPOSITION)):
        return False
    if len(rows) != ledger["row_count"] or len(rows) != len(identities) or len(rows) != 12:
        return False
    for row in rows:
        support_path = ROOT / row["support_path"]
        support = store.document(support_path)
        if digest(store.raw(support_path)) != row["support_sha256"]:
            return False
        if (support["source_cycle"], support["finding_id"]) != (row["source_cycle"], row["finding_id"]):
            return False
        if support["disposition"] != row["disposition"]:
            return False
        source_path = ROOT / support["source_response_path"]
        authority_path = ROOT / support["support_authority_path"]
        if not source_path.is_file() or not authority_path.is_file():
            return False
        if digest(store.raw(source_path)) != support["source_response_sha256"]:
            return False
        if digest(store.raw(authority_path)) != support["support_authority_sha256"]:
            return False
        if not support["finding_specific_claim"]:
            return False
        if row["disposition"] not in vocabulary["closed_values"]:
            return False
    return (
        ledger["mechanically_resolved_pending_review"]
        == sum(row["disposition"] == vocabulary["pre_review_value"] for row in rows)
        and ledger["independently_accepted"]
        == sum(row["disposition"] == vocabulary["acceptance_value"] for row in rows)
        and ledger["unresolved"] == sum(row["disposition"] == "UNRESOLVED" for row in rows)
        and ledger["counters_derived_from_rows"]
    )


def predicate_cycle8_source_derivation(store: Store) -> bool:
    counts = store.document(design.CYCLE8_COUNTS)
    ids = store.document(design.CYCLE8_IDS)
    expected_counts = design.build_cycle8_counts()
    expected_ids = design.build_cycle8_ids()
    response = store.raw(design.v9.OPUS8).decode()
    return (
        counts == expected_counts
        and ids == expected_ids
        and counts["counts_derived_from_normalized_results"]
        and ids["row_count"] == len(ids["rows"]) == 15
        and ids["ledger_ids_unique"]
        and ids["source_ids_unique"]
        and all(row["source_id"] in response for row in ids["rows"])
        and all(digest(store.raw(ROOT / row["source_response_path"])) == row["source_response_sha256"] for row in ids["rows"])
    )


def predicate_cycle9_repair_ledger(store: Store) -> bool:
    ledger = store.document(design.CYCLE9_REPAIR)
    normalized = store.document(ROOT / ledger["source_normalized_path"])
    response = store.raw(ROOT / ledger["source_response_path"]).decode()
    ids = [row["finding_id"] for row in ledger["rows"]]
    return (
        digest(store.raw(ROOT / ledger["source_response_path"])) == ledger["source_response_sha256"]
        and digest(store.raw(ROOT / ledger["source_normalized_path"])) == ledger["source_normalized_sha256"]
        and ids == normalized["finding_ids"]
        and ledger["row_count"] == len(ids) == 5
        and all(finding_id in response for finding_id in ids)
        and all(row["disposition"] == "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW" for row in ledger["rows"])
        and ledger["unresolved_attack_batteries_from_review"] == normalized["unresolved_claims"] == 15
    )


def _prepared_valid(store: Store) -> bool:
    try:
        prepared = store.document(design.v9.PREPARED)
        manifest = store.document(design.v9.MANIFEST)
        qualification = store.document(design.v9.QUAL)
        head = prepared["implementation_head"]
        current_head = _git("rev-parse", "HEAD").stdout.strip()
        if _git("merge-base", "--is-ancestor", head, current_head, check=False).returncode != 0:
            return False
        tree = _git("rev-parse", f"{head}^{{tree}}").stdout.strip()
        if tree != prepared["implementation_tree"]:
            return False
        current = set(qualification["current_authority_roles"])
        future = set(qualification["future_output_roles"])
        bindings = prepared["bindings"]
        if current.intersection(future) or current.union(future) != set(design.v9.ROLES):
            return False
        if prepared["roles"] != design.v9.ROLES or prepared["schema"] != manifest["prepared_instance_schema"]:
            return False
        if prepared["binding_count"] != prepared["role_count"] or len(bindings) != prepared["role_count"]:
            return False
        forbidden = set(manifest["forbidden_current_binding_paths"])
        for role in current:
            binding = bindings[role]
            path = binding.get("path", "")
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts or path in forbidden:
                return False
            if binding.get("binding_state") != "CURRENT_DESIGN_AUTHORITY":
                return False
            if prior.git_mode(head, path) == "120000" or not (ROOT / path).is_file():
                return False
            expected = binding.get("sha256")
            if digest(prior.git_raw(head, path)) != expected:
                return False
            if digest(prior.git_raw(current_head, path)) != expected:
                return False
            if digest(store.raw(ROOT / path)) != expected:
                return False
        for role in future:
            if set(bindings[role]) != {"binding_state", "required_schema", "availability_stage"}:
                return False
            if bindings[role]["binding_state"] != "UNBOUND_FUTURE":
                return False
        return (
            prepared["validated_binding_count"] == len(current)
            and not prepared["final_acceptance_eligible"]
            and not prepared["live_authority"]
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return False


def predicate_prepared_fail_closed(store: Store) -> bool:
    if not _prepared_valid(store):
        return False
    missing = store.changed(
        design.v9.PREPARED,
        lambda value: value["bindings"]["readiness_interface"].__setitem__("path", "specs/017-rust-native-inference-runtime/contracts/DOES-NOT-EXIST.json"),
    )
    return not _prepared_valid(missing)


@lru_cache(maxsize=1)
def actual_generator_behavior() -> bool:
    head = _git("rev-parse", "HEAD").stdout.strip()
    results: list[bool] = []
    for stamp in ("200101010101", "203512312359"):
        temporary = Path(tempfile.mkdtemp(prefix="f017-seq7-c10-generator-"))
        clone = temporary / "repo"
        try:
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(ROOT), str(clone)], check=True)
            subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", "--detach", head], check=True)
            for tool in ("agy", "opus"):
                envelope = clone / "docs/architecture/reviews/evidence" / f"f017-event06-v12-sequence05-{tool}-design-cycle-07-provider-envelope.json"
                subprocess.run(["touch", "-t", stamp, str(envelope)], check=True)
            run = subprocess.run(["python3", "scripts/research/generate_f017_event06_sequence05_design_v10.py", "--check"], cwd=clone, capture_output=True, text=True)
            clean = not subprocess.run(["git", "status", "--porcelain"], cwd=clone, check=True, capture_output=True, text=True).stdout
            results.append(run.returncode == 0 and clean)
        finally:
            shutil.rmtree(temporary)
    temporary = Path(tempfile.mkdtemp(prefix="f017-seq7-c10-generator-negative-"))
    clone = temporary / "repo"
    try:
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(ROOT), str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", "--detach", head], check=True)
        target = clone / design.GRAPH11.relative_to(ROOT)
        target.write_bytes(target.read_bytes() + b"\n")
        negative = subprocess.run(["python3", "scripts/research/generate_f017_event06_sequence05_design_v10.py", "--check"], cwd=clone, capture_output=True, text=True)
        results.append(negative.returncode != 0 and "drift:" in (negative.stdout + negative.stderr))
    finally:
        shutil.rmtree(temporary)
    return len(results) == 3 and all(results)


def predicate_generator_behavioral_reproduction(store: Store) -> bool:
    policy = store.document(design.BEHAVIOR_POLICY)
    return (
        policy["success_repetitions"] == 2
        and len(policy["success_mtime_profiles"]) == 2
        and policy["negative_case"] == "CORRUPT_ONE_GENERATED_ARTIFACT_THEN_REQUIRE_GENERATOR_CHECK_NONZERO"
        and policy["negative_generator_exit_must_be_nonzero"]
        and policy["authoritative_worktree_must_remain_clean"]
        and actual_generator_behavior()
    )


def predicate_cycle10_graph_state(store: Store) -> bool:
    graph9 = store.document(design.GRAPH10)
    graph10 = store.document(design.GRAPH11)
    claims10 = store.document(design.CLAIMS11)
    return (
        graph9["review_cycle"] == 9
        and graph9["status"] == "REPAIR_REQUIRED"
        and graph9["opus_counts"] == {"blocking": 0, "required": 0, "advisory": 5, "unresolved": 15}
        and graph10["source_review_cycle"] == 9
        and graph10["repair_rows"] == graph10["mechanically_closed_rows"] == 5
        and graph10["status"] == "PENDING_INDEPENDENT_REVIEW"
        and claims10["row_count"] == claims10["mechanically_supported"] == 5
        and claims10["independently_accepted"] == 0
    )


def _static(node: ast.AST | None) -> object:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_static(item) for item in node.elts]
        if UNKNOWN in values:
            return UNKNOWN
        constructor = {ast.List: list, ast.Tuple: tuple, ast.Set: set}[type(node)]
        return constructor(values)
    if isinstance(node, ast.Dict):
        keys = [_static(item) for item in node.keys]
        values = [_static(item) for item in node.values]
        if UNKNOWN in keys or UNKNOWN in values:
            return UNKNOWN
        return dict(zip(keys, values, strict=True))
    if isinstance(node, ast.UnaryOp):
        value = _static(node.operand)
        if value is UNKNOWN:
            return UNKNOWN
        operations = {ast.Not: operator.not_, ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Invert: operator.invert}
        function = operations.get(type(node.op))
        try:
            return UNKNOWN if function is None else function(value)
        except (TypeError, ValueError):
            return UNKNOWN
    if isinstance(node, ast.BinOp):
        left, right = _static(node.left), _static(node.right)
        function = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}.get(type(node.op))
        try:
            return UNKNOWN if UNKNOWN in (left, right) or function is None else function(left, right)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            return UNKNOWN
    if isinstance(node, ast.BoolOp):
        values = [_static(item) for item in node.values]
        if UNKNOWN in values:
            return UNKNOWN
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        values = [_static(node.left), *(_static(item) for item in node.comparators)]
        if UNKNOWN in values:
            return UNKNOWN
        functions = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Is: operator.is_, ast.IsNot: operator.is_not, ast.In: operator.contains, ast.NotIn: lambda right, left: left not in right}
        try:
            return all(functions[type(op)](values[index], values[index + 1]) for index, op in enumerate(node.ops))
        except (KeyError, TypeError, ValueError):
            return UNKNOWN
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool" and len(node.args) == 1 and not node.keywords:
        value = _static(node.args[0])
        return UNKNOWN if value is UNKNOWN else bool(value)
    return UNKNOWN


def _guard_source(source: str, registry_names: list[str], prefix: str) -> dict:
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    discovered = {name for name in functions if name.startswith(prefix)}
    failures: list[str] = []
    if discovered != set(registry_names) or len(registry_names) != len(set(registry_names)):
        failures.append("registry")
    bodies: set[str] = set()
    for name in registry_names:
        node = functions.get(name)
        if node is None:
            failures.append(f"missing:{name}")
            continue
        returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
        if not returns:
            failures.append(f"return:{name}")
        for item in returns:
            value = _static(item.value)
            if value is not UNKNOWN and bool(value):
                failures.append(f"constant:{name}")
        for item in ast.walk(node):
            if isinstance(item, ast.ExceptHandler):
                if any(isinstance(statement, ast.Pass) for statement in item.body):
                    failures.append(f"swallowed:{name}")
                for statement in item.body:
                    if isinstance(statement, ast.Return):
                        value = _static(statement.value)
                        if value is not UNKNOWN and bool(value):
                            failures.append(f"exception-success:{name}")
        body = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
        if body in bodies:
            failures.append(f"duplicate:{name}")
        bodies.add(body)
    return {"failures": sorted(set(failures)), "result": not failures}


def ast_guard() -> dict:
    local_validator_names = [
        function.__name__ for function in PREDICATES.values() if function.__module__ == __name__
    ]
    prior_validator_names = [function.__name__ for function in prior.PREDICATES.values()]
    generator_names = [function.__name__ for function in design.GENERATOR_PREDICATES.values()]
    actual_validator = _guard_source(Path(__file__).read_text(), local_validator_names, "predicate_")
    actual_prior = _guard_source(Path(prior.__file__).read_text(), prior_validator_names, "predicate_")
    actual_generator = _guard_source(Path(design.__file__).read_text(), generator_names, "generator_predicate_")
    attacks = {
        "literal": "def predicate_x():\n return True\n",
        "compare": "def predicate_x():\n return 1 == 1\n",
        "unary": "def predicate_x():\n return not False\n",
        "boolop": "def predicate_x():\n return True and True\n",
        "boolcall": "def predicate_x():\n return bool(1)\n",
        "binop": "def predicate_x():\n return 1 + 1\n",
        "swallowed": "def predicate_x():\n try:\n  return value\n except Exception:\n  pass\n",
        "exception_success": "def predicate_x():\n try:\n  return value\n except Exception:\n  return 1 == 1\n",
        "unregistered": "def predicate_x():\n return value\ndef predicate_y():\n return value\n",
    }
    attack_results = {name: not _guard_source(source, ["predicate_x"], "predicate_")["result"] for name, source in attacks.items()}
    passed = actual_validator["result"] and actual_prior["result"] and actual_generator["result"] and all(attack_results.values())
    return {
        "validator_registry_count": len(PREDICATES),
        "generator_registry_count": len(generator_names),
        "validator_failures": actual_validator["failures"],
        "predecessor_validator_failures": actual_prior["failures"],
        "generator_failures": actual_generator["failures"],
        "attack_results": attack_results,
        "attack_count": len(attack_results),
        "attack_rejections": sum(attack_results.values()),
        "result": "PASS" if passed else "FAIL",
    }


PREDICATES: dict[str, Callable[[Store], bool]] = {
    "repair_ledger": prior.predicate_repair_ledger,
    "schema_externality": prior.predicate_schema_externality,
    "provenance_contract": prior.predicate_provenance_contract,
    "graph_claim_state": prior.predicate_graph_claim_state,
    "qualification_truth": prior.predicate_qualification_truth,
    "advisory_source_response": predicate_advisory_source_response,
    "generator_policy": prior.predicate_generator_policy,
    "review_head_identity": prior.predicate_review_head_identity,
    "alias_axes": prior.predicate_alias_axes,
    "failure_arithmetic": prior.predicate_failure_arithmetic,
    "outcome_mapping": prior.predicate_outcome_mapping,
    "measurement_consistency": prior.predicate_measurement_consistency,
    "no_access": prior.predicate_no_access,
    "cycle8_source_derivation": predicate_cycle8_source_derivation,
    "cycle9_repair_ledger": predicate_cycle9_repair_ledger,
    "prepared_fail_closed": predicate_prepared_fail_closed,
    "generator_behavioral_reproduction": predicate_generator_behavioral_reproduction,
    "cycle10_graph_state": predicate_cycle10_graph_state,
}


def evaluate(store: Store) -> dict[str, bool]:
    return {name: predicate(store) for name, predicate in PREDICATES.items()}


def mutation_suite(base: Store) -> list[dict]:
    cases: list[tuple[str, str, Path, Callable[[dict], None]]] = [
        ("M-ADVISORY-SOURCE", "advisory_source_response", design.v9.ADVISORY_LEDGER, lambda d: d["rows"][0].__setitem__("support_sha256", "0" * 64)),
        ("M-C8-COUNT", "cycle8_source_derivation", design.CYCLE8_COUNTS, lambda d: d["opus_counts"].__setitem__("blocking", 0)),
        ("M-C8-ID", "cycle8_source_derivation", design.CYCLE8_IDS, lambda d: d["rows"][0].__setitem__("source_id", "ABSENT-ID")),
        ("M-C9-ROW", "cycle9_repair_ledger", design.CYCLE9_REPAIR, lambda d: d["rows"][0].__setitem__("disposition", "OPEN")),
        ("M-PREPARED-MISSING", "prepared_fail_closed", design.v9.PREPARED, lambda d: d["bindings"]["readiness_interface"].__setitem__("path", "missing.json")),
        ("M-GENERATOR-POLICY", "generator_behavioral_reproduction", design.BEHAVIOR_POLICY, lambda d: d.__setitem__("negative_generator_exit_must_be_nonzero", False)),
        ("M-GRAPH", "cycle10_graph_state", design.GRAPH11, lambda d: d.__setitem__("status", "FABRICATED")),
    ]
    baseline = evaluate(base)
    if not all(baseline.values()):
        raise ValueError(f"positive baseline failed: {[name for name, passed in baseline.items() if not passed]}")
    rows = []
    for mutation_id, target, path, change in cases:
        values = evaluate(base.changed(path, change))
        failures = sorted(name for name, passed in values.items() if not passed)
        rows.append({
            "mutation_id": mutation_id,
            "target": target,
            "failed_predicates": failures,
            "result": "PASS" if target in failures else "FAIL",
        })
    for index, finding_id in enumerate(["C9-OPUS-P1", "C9-OPUS-P2", "C9-OPUS-P3", "C9-OPUS-P4", "C9-OPUS-P5"], 1):
        def alter(document: dict, finding_id: str = finding_id) -> None:
            next(row for row in document["rows"] if row["finding_id"] == finding_id)["disposition"] = "OPEN"
        values = evaluate(base.changed(design.CYCLE9_REPAIR, alter))
        failures = sorted(name for name, passed in values.items() if not passed)
        rows.append({"mutation_id": f"M-C9-ROW-{index}", "target": finding_id, "failed_predicates": failures, "result": "PASS" if "cycle9_repair_ledger" in failures else "FAIL"})
    return rows


def report(store: Store) -> dict:
    values = evaluate(store)
    mutations = mutation_suite(Store({}))
    guard = ast_guard()
    head = _git("rev-parse", "HEAD").stdout.strip()
    tree = _git("rev-parse", "HEAD^{tree}").stdout.strip()
    ok = all(values.values()) and all(row["result"] == "PASS" for row in mutations) and guard["result"] == "PASS"
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.6.0",
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
        "cycle9_opus_rows_closed": 5 if values["cycle9_repair_ledger"] else 0,
        "generator_clean_clone_success_repetitions": 2,
        "generator_behavioral_negative_cases": 1,
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
        store = store.changed(design.CYCLE9_REPAIR, lambda d: d["rows"][0].__setitem__("disposition", "INJECTED_OPEN"))
    value = report(store)
    if args.output:
        with args.output.open("xb") as stream:
            stream.write(canonical_bytes(value))
    print(json.dumps(value, sort_keys=True))
    return 0 if value["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

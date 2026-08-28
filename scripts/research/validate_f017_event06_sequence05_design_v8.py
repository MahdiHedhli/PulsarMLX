#!/usr/bin/env python3
"""Validate the Cycle-11 repair of the Event-06 Sequence-5 design authority."""
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
import generate_f017_event06_sequence05_design_v11 as design
import validate_f017_event06_sequence05_design_v7 as prior


ROOT = design.ROOT
Store = prior.Store
UNKNOWN = object()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=ROOT, check=check, capture_output=True, text=True)


def predicate_advisory_source_membership(store: Store) -> bool:
    ledger = store.document(design.ADVISORY5)
    vocabulary = store.document(design.v10.v9.DISPOSITION)
    identities = {(row["source_cycle"], row["finding_id"]) for row in ledger["rows"]}
    if len(identities) != ledger["row_count"] or ledger["row_count"] != 12:
        return False
    for row in ledger["rows"]:
        support_path = ROOT / row["support_path"]
        support = store.document(support_path)
        source_path = ROOT / support["source_response_path"]
        authority_path = ROOT / support["support_authority_path"]
        if digest(store.raw(support_path)) != row["support_sha256"]:
            return False
        if digest(store.raw(source_path)) != support["source_response_sha256"]:
            return False
        if digest(store.raw(authority_path)) != support["support_authority_sha256"]:
            return False
        if support["finding_id"] not in store.raw(source_path).decode():
            return False
        if (support["source_cycle"], support["finding_id"]) != (row["source_cycle"], row["finding_id"]):
            return False
        if support["disposition"] != row["disposition"] or row["disposition"] not in vocabulary["closed_values"]:
            return False
        if row["source_cycle"] == "cycle04":
            disposition = store.document(ROOT / support["source_transport_disposition_path"])
            if digest(store.raw(ROOT / support["source_transport_disposition_path"])) != support["source_transport_disposition_sha256"]:
                return False
            if disposition["exact_response_bytes_retained"] or disposition["source_use"] != "FINDING_ID_CENSUS_ONLY_NOT_EXACT_RESPONSE_SUBSTITUTE":
                return False
    return (
        ledger["mechanically_resolved_pending_review"] == sum(row["disposition"] == vocabulary["pre_review_value"] for row in ledger["rows"])
        and ledger["independently_accepted"] == 0
        and ledger["unresolved"] == 0
        and ledger["counters_derived_from_rows"]
    )


def predicate_schema_externality_v4(store: Store) -> bool:
    authority = store.document(design.SCHEMA4)
    qualification = store.document(design.QUAL8)
    readiness = store.document(design.v10.v9.READINESS)
    installation = store.document(design.INSTALL10)
    authority_path = str(design.SCHEMA4.relative_to(ROOT))
    authority_sha = digest(store.raw(design.SCHEMA4))
    mapping = {
        "qualification_role_requirements": ("qualification_schema", qualification["schema"]),
        "readiness_interface": ("readiness_schema", readiness["schema"]),
        "live_installation_interface": ("installation_schema", installation["schema"]),
    }
    for role, (field, schema) in mapping.items():
        item = qualification["roles"][role]
        path_key = "external_schema_authority_path" if role == "qualification_role_requirements" else "schema_authority_path"
        sha_key = "external_schema_authority_sha256" if role == "qualification_role_requirements" else "schema_authority_sha256"
        if item[path_key] != authority_path or item[sha_key] != authority_sha or item["schema_authority_field"] != field:
            return False
        if authority[field] != schema:
            return False
    return authority["artifact_schema_equality_required"] and not authority["self_reference_permitted"]


def predicate_qualification_v8(store: Store) -> bool:
    value = store.document(design.QUAL8)
    return (
        value["validation_result_source"] == str(Path(__file__).relative_to(ROOT))
        and value["active_validation_gap_ids"] == ["PENDING_CYCLE11_MECHANICAL_VALIDATION"]
        and value["validation_gap_count"] == 1
        and not value["all_requirements_mechanically_validated"]
        and value["validation_state"] == "PENDING_EXTERNAL_VALIDATOR_EXECUTION"
    )


def predicate_posture_mapping(store: Store) -> bool:
    mapping = store.document(design.INSTALL10)["posture_mapping"]
    return (
        set(mapping) == {"CANDIDATE", "PREPARED_VALIDATION_ONLY", "PRODUCTION_INSTALLED", "SYNTHETIC_INSTALLED"}
        and all(type(item["live_authority"]) is bool for item in mapping.values())
        and all(isinstance(item["authority_scope"], list) and item["authority_scope"] for item in mapping.values())
        and [posture for posture, item in mapping.items() if item["live_authority"]] == ["PRODUCTION_INSTALLED"]
    )


def predicate_cycle10_repair(store: Store) -> bool:
    ledger = store.document(design.CYCLE10_REPAIR)
    normalized = store.document(ROOT / ledger["source_normalized_path"], canonical=False)
    response = store.raw(ROOT / ledger["source_response_path"]).decode()
    ids = [row["finding_id"] for row in ledger["rows"]]
    return (
        digest(store.raw(ROOT / ledger["source_response_path"])) == ledger["source_response_sha256"]
        and digest(store.raw(ROOT / ledger["source_normalized_path"])) == ledger["source_normalized_sha256"]
        and ids == normalized["finding_ids"]
        and ledger["row_count"] == len(ids) == 5
        and ledger["source_counts"] == {"blocking": 1, "required": 3, "advisory": 1, "unresolved": 0}
        and all(finding_id in response for finding_id in ids)
        and all(row["disposition"] == "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW" for row in ledger["rows"])
    )


def _prepared_valid(store: Store) -> bool:
    try:
        prepared = store.document(design.PREPARED6)
        manifest = store.document(design.MANIFEST9)
        qualification = store.document(design.QUAL8)
        head = prepared["implementation_head"]
        current_head = git("rev-parse", "HEAD").stdout.strip()
        if git("merge-base", "--is-ancestor", head, current_head, check=False).returncode:
            return False
        if git("rev-parse", f"{head}^{{tree}}").stdout.strip() != prepared["implementation_tree"]:
            return False
        current = set(qualification["current_authority_roles"])
        future = set(qualification["future_output_roles"])
        if current.intersection(future) or current.union(future) != set(prepared["roles"]):
            return False
        if prepared["schema"] != manifest["prepared_instance_schema"] or prepared["binding_count"] != len(prepared["bindings"]):
            return False
        forbidden = set(manifest["forbidden_current_binding_paths"])
        for role in current:
            binding = prepared["bindings"][role]
            path = binding.get("path", "")
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts or path in forbidden or not (ROOT / path).is_file():
                return False
            expected = binding.get("sha256")
            if binding.get("binding_state") != "CURRENT_DESIGN_AUTHORITY" or prior.prior.git_mode(head, path) == "120000":
                return False
            if digest(prior.prior.git_raw(head, path)) != expected or digest(prior.prior.git_raw(current_head, path)) != expected:
                return False
            if digest(store.raw(ROOT / path)) != expected:
                return False
        for role in future:
            if set(prepared["bindings"][role]) != {"binding_state", "required_schema", "availability_stage"}:
                return False
            if prepared["bindings"][role]["binding_state"] != "UNBOUND_FUTURE":
                return False
        return prepared["validated_binding_count"] == len(current) and not prepared["final_acceptance_eligible"] and not prepared["live_authority"]
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return False


def predicate_prepared_v6(store: Store) -> bool:
    if not _prepared_valid(store):
        return False
    missing = store.changed(design.PREPARED6, lambda d: d["bindings"]["readiness_interface"].__setitem__("path", "missing.json"))
    return not _prepared_valid(missing)


@lru_cache(maxsize=1)
def actual_generator_behavior() -> bool:
    head = git("rev-parse", "HEAD").stdout.strip()
    results: list[bool] = []
    for stamp in ("200101010101", "203512312359"):
        temporary = Path(tempfile.mkdtemp(prefix="f017-seq7-c11-generator-"))
        clone = temporary / "repo"
        try:
            subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(ROOT), str(clone)], check=True)
            subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", "--detach", head], check=True)
            for tool in ("agy", "opus"):
                envelope = clone / "docs/architecture/reviews/evidence" / f"f017-event06-v12-sequence05-{tool}-design-cycle-07-provider-envelope.json"
                subprocess.run(["touch", "-t", stamp, str(envelope)], check=True)
            run = subprocess.run(["python3", "scripts/research/generate_f017_event06_sequence05_design_v11.py", "--check"], cwd=clone, capture_output=True, text=True)
            clean = not subprocess.run(["git", "status", "--porcelain"], cwd=clone, check=True, capture_output=True, text=True).stdout
            results.append(run.returncode == 0 and clean)
        finally:
            shutil.rmtree(temporary)
    temporary = Path(tempfile.mkdtemp(prefix="f017-seq7-c11-generator-negative-"))
    clone = temporary / "repo"
    try:
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(ROOT), str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", "--detach", head], check=True)
        target = clone / design.GRAPH13.relative_to(ROOT)
        target.write_bytes(target.read_bytes() + b"\n")
        run = subprocess.run(["python3", "scripts/research/generate_f017_event06_sequence05_design_v11.py", "--check"], cwd=clone, capture_output=True, text=True)
        results.append(run.returncode != 0 and "drift:" in run.stdout + run.stderr)
    finally:
        shutil.rmtree(temporary)
    return len(results) == 3 and all(results)


def predicate_generator_v11(store: Store) -> bool:
    policy = store.document(design.BEHAVIOR2)
    return (
        policy["generator_path"] == str(Path(design.__file__).relative_to(ROOT))
        and policy["success_repetitions"] == 2
        and policy["negative_generator_exit_must_be_nonzero"]
        and actual_generator_behavior()
    )


def predicate_cycle11_graph(store: Store) -> bool:
    rejected = store.document(design.GRAPH12)
    pending = store.document(design.GRAPH13)
    claims = store.document(design.CLAIMS13)
    return (
        rejected["status"] == "REPAIR_REQUIRED"
        and rejected["opus_counts"] == {"blocking": 1, "required": 3, "advisory": 1, "unresolved": 0}
        and pending["status"] == "PENDING_INDEPENDENT_REVIEW"
        and pending["repair_rows"] == pending["mechanically_closed_rows"] == 5
        and claims["row_count"] == claims["mechanically_supported"] == 5
        and claims["independently_accepted"] == 0
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
        return {ast.List: list, ast.Tuple: tuple, ast.Set: set}[type(node)](values)
    if isinstance(node, ast.Dict):
        keys, values = [_static(item) for item in node.keys], [_static(item) for item in node.values]
        return UNKNOWN if UNKNOWN in keys or UNKNOWN in values else dict(zip(keys, values, strict=True))
    if isinstance(node, ast.UnaryOp):
        value = _static(node.operand)
        function = {ast.Not: operator.not_, ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Invert: operator.invert}.get(type(node.op))
        try:
            return UNKNOWN if value is UNKNOWN or function is None else function(value)
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
        return UNKNOWN if UNKNOWN in values else (all(values) if isinstance(node.op, ast.And) else any(values))
    if isinstance(node, ast.Compare):
        values = [_static(node.left), *(_static(item) for item in node.comparators)]
        if UNKNOWN in values:
            return UNKNOWN
        functions = {
            ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
            ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Is: operator.is_, ast.IsNot: operator.is_not,
            ast.In: lambda left, right: left in right, ast.NotIn: lambda left, right: left not in right,
        }
        try:
            return all(functions[type(op)](values[index], values[index + 1]) for index, op in enumerate(node.ops))
        except (KeyError, TypeError, ValueError):
            return UNKNOWN
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool" and len(node.args) == 1 and not node.keywords:
        value = _static(node.args[0])
        return UNKNOWN if value is UNKNOWN else bool(value)
    return UNKNOWN


def _guard_source(source: str, names: list[str], prefix: str) -> bool:
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    if {name for name in functions if name.startswith(prefix)} != set(names) or len(names) != len(set(names)):
        return False
    bodies: set[str] = set()
    for name in names:
        node = functions[name]
        returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
        if not returns or any((value := _static(item.value)) is not UNKNOWN and bool(value) for item in returns):
            return False
        for handler in (item for item in ast.walk(node) if isinstance(item, ast.ExceptHandler)):
            if any(isinstance(statement, ast.Pass) for statement in handler.body):
                return False
            for statement in handler.body:
                if isinstance(statement, ast.Return):
                    value = _static(statement.value)
                    if value is not UNKNOWN and bool(value):
                        return False
        body = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
        if body in bodies:
            return False
        bodies.add(body)
    return True


def ast_guard() -> dict:
    modules = [
        (Path(__file__), [function.__name__ for function in PREDICATES.values() if function.__module__ == __name__], "predicate_"),
        (Path(prior.__file__), [function.__name__ for function in prior.PREDICATES.values()], "predicate_"),
        (Path(design.__file__), [function.__name__ for function in design.GENERATOR_PREDICATES.values()], "generator_predicate_"),
        (Path(design.v10.__file__), [function.__name__ for function in design.v10.GENERATOR_PREDICATES.values()], "generator_predicate_"),
        (Path(design.v10.v9.__file__), [function.__name__ for function in design.v10.v9.GENERATOR_PREDICATES.values()], "generator_predicate_"),
    ]
    module_results = [_guard_source(path.read_text(), names, prefix) for path, names, prefix in modules]
    attacks = {
        "literal": "return True", "compare": "return 1 == 1", "membership": "return 'a' in 'abc'",
        "not_membership": "return 'z' not in 'abc'", "unary": "return not False", "boolop": "return True and True",
        "boolcall": "return bool(1)", "binop": "return 1 + 1",
    }
    attack_results = {name: not _guard_source(f"def predicate_x():\n {body}\n", ["predicate_x"], "predicate_") for name, body in attacks.items()}
    special = {
        "swallowed": not _guard_source("def predicate_x():\n try:\n  return value\n except Exception:\n  pass\n", ["predicate_x"], "predicate_"),
        "exception_success": not _guard_source("def predicate_x():\n try:\n  return value\n except Exception:\n  return 1 == 1\n", ["predicate_x"], "predicate_"),
        "unregistered": not _guard_source("def predicate_x():\n return value\ndef predicate_y():\n return value\n", ["predicate_x"], "predicate_"),
    }
    attack_results.update(special)
    passed = all(module_results) and all(attack_results.values())
    return {"module_results": module_results, "attack_results": attack_results, "attack_count": len(attack_results), "attack_rejections": sum(attack_results.values()), "result": "PASS" if passed else "FAIL"}


PREDICATES: dict[str, Callable[[Store], bool]] = {
    "repair_ledger": prior.PREDICATES["repair_ledger"],
    "provenance_contract": prior.PREDICATES["provenance_contract"],
    "graph_claim_state": prior.PREDICATES["graph_claim_state"],
    "alias_axes": prior.PREDICATES["alias_axes"],
    "failure_arithmetic": prior.PREDICATES["failure_arithmetic"],
    "outcome_mapping": prior.PREDICATES["outcome_mapping"],
    "measurement_consistency": prior.PREDICATES["measurement_consistency"],
    "no_access": prior.PREDICATES["no_access"],
    "cycle8_source_derivation": prior.PREDICATES["cycle8_source_derivation"],
    "cycle9_repair_ledger": prior.PREDICATES["cycle9_repair_ledger"],
    "advisory_source_membership": predicate_advisory_source_membership,
    "schema_externality_v4": predicate_schema_externality_v4,
    "qualification_v8": predicate_qualification_v8,
    "posture_mapping": predicate_posture_mapping,
    "cycle10_repair": predicate_cycle10_repair,
    "prepared_v6": predicate_prepared_v6,
    "generator_v11": predicate_generator_v11,
    "cycle11_graph": predicate_cycle11_graph,
}


def evaluate(store: Store) -> dict[str, bool]:
    return {name: predicate(store) for name, predicate in PREDICATES.items()}


def mutation_suite(base: Store) -> list[dict]:
    cases: list[tuple[str, str, Path, Callable[[dict], None]]] = [
        ("M-SOURCE-MEMBERSHIP", "advisory_source_membership", design.support_path("A1"), lambda d: d.__setitem__("finding_id", "ABSENT")),
        ("M-SCHEMA", "schema_externality_v4", design.SCHEMA4, lambda d: d.__setitem__("installation_schema", "BOGUS")),
        ("M-QUAL", "qualification_v8", design.QUAL8, lambda d: d.__setitem__("validation_result_source", "v6.py")),
        ("M-POSTURE-TYPE", "posture_mapping", design.INSTALL10, lambda d: d["posture_mapping"]["CANDIDATE"].__setitem__("live_authority", "ABSENT")),
        ("M-POSTURE-LIVE", "posture_mapping", design.INSTALL10, lambda d: d["posture_mapping"]["SYNTHETIC_INSTALLED"].__setitem__("live_authority", True)),
        ("M-C10", "cycle10_repair", design.CYCLE10_REPAIR, lambda d: d["rows"][0].__setitem__("disposition", "OPEN")),
        ("M-PREPARED", "prepared_v6", design.PREPARED6, lambda d: d["bindings"]["readiness_interface"].__setitem__("path", "missing.json")),
        ("M-GENERATOR", "generator_v11", design.BEHAVIOR2, lambda d: d.__setitem__("generator_path", "v10.py")),
        ("M-GRAPH", "cycle11_graph", design.GRAPH13, lambda d: d.__setitem__("status", "FABRICATED")),
    ]
    baseline = evaluate(base)
    if not all(baseline.values()):
        raise ValueError(f"positive baseline failed: {[name for name, passed in baseline.items() if not passed]}")
    rows = []
    for mutation_id, target, path, change in cases:
        values = evaluate(base.changed(path, change))
        failures = sorted(name for name, passed in values.items() if not passed)
        rows.append({"mutation_id": mutation_id, "target": target, "failed_predicates": failures, "result": "PASS" if target in failures else "FAIL"})
    return rows


def report(store: Store) -> dict:
    values = evaluate(store)
    mutations = mutation_suite(Store({}))
    guard = ast_guard()
    head = git("rev-parse", "HEAD").stdout.strip()
    tree = git("rev-parse", "HEAD^{tree}").stdout.strip()
    ok = all(values.values()) and all(row["result"] == "PASS" for row in mutations) and guard["result"] == "PASS"
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.7.0",
        "validation_subject_head": head,
        "validation_subject_tree": tree,
        "predicate_results": values,
        "registered_predicates": len(values),
        "registered_predicate_passes": sum(values.values()),
        "ast_guard": guard,
        "mutations": mutations,
        "mutation_count": len(mutations),
        "mutation_rejections": sum(row["result"] == "PASS" for row in mutations),
        "cycle10_opus_rows_closed": 5 if values["cycle10_repair"] else 0,
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
        store = store.changed(design.INSTALL10, lambda d: d["posture_mapping"]["CANDIDATE"].__setitem__("live_authority", "ABSENT"))
    value = report(store)
    if args.output:
        with args.output.open("xb") as stream:
            stream.write(canonical_bytes(value))
    print(json.dumps(value, sort_keys=True))
    return 0 if value["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

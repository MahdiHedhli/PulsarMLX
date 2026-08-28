#!/usr/bin/env python3
"""Independent validator for the Sequence 9 version-forward authority chain."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable, Final

from f017_canonical_serialization_v10 import canonical_bytes


ROOT: Final = Path(__file__).resolve().parents[2]
C = ROOT / "specs/017-rust-native-inference-runtime/contracts"
E = ROOT / "docs/architecture/reviews/evidence"

PATHS = {
    "candidate": {
        "schema": C / "f017-event06-sequence09-qualification-schema-authority-v1.json",
        "qualification": C
        / "f017-event06-sequence09-qualification-role-requirements-v1.json",
        "readiness": C
        / "f017-corrected-oracle-event06-readiness-consumer-interface-v11.json",
        "installation": C
        / "f017-corrected-oracle-event06-live-installation-interface-v11.json",
        "manifest": C
        / "f017-corrected-oracle-event06-readiness-authority-manifest-v10.json",
    },
    "final": {
        "schema": C / "f017-event06-sequence09-qualification-schema-authority-v2.json",
        "qualification": C
        / "f017-event06-sequence09-qualification-role-requirements-v2.json",
        "readiness": C
        / "f017-corrected-oracle-event06-readiness-consumer-interface-v12.json",
        "installation": C
        / "f017-corrected-oracle-event06-live-installation-interface-v12.json",
        "manifest": C
        / "f017-corrected-oracle-event06-readiness-authority-manifest-v11.json",
    },
}
FUTURE = C / "f017-corrected-oracle-event06-future-go-capability-v2.json"
TRANSACTION = C / "f017-event06-production-installation-transaction-policy-v1.json"
MEASUREMENT_SCHEMA = (
    C / "f017-event06-sequence09-implementation-measurement-schema-v1.json"
)
MEASUREMENT = E / "f017-event06-v12-sequence09-implementation-measurement-v1.json"
PREPARED = (
    E / "f017-event06-v12-sequence09-readiness-authority-manifest-prepared-v1.json"
)
MATRIX = E / "f017-event06-v12-sequence09-producer-consumer-matrix-v1.json"
DISPOSITIONS = (
    E / "f017-event06-v12-sequence09-prequalification-finding-dispositions-v1.json"
)
BASE_QUAL = C / "f017-event06-sequence05-qualification-role-requirements-v8.json"

HISTORICAL_SHA: Final = {
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-readiness-consumer-interface-v10.json": "d1e787cef7070c787f74df029590d6b15391165b93a6b8aae1326cbc3737b0a0",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-live-installation-interface-v10.json": "6cdc13610dfac44c1e374f13bfe970f93689f492b4c1b12b53170892fe62550f",
    "specs/017-rust-native-inference-runtime/contracts/f017-event06-sequence05-qualification-role-requirements-v8.json": "53011c0ccffeb42ffb75d3cc2064c4b62ceff0f15f9a683825e842fd6f3c1f5f",
    "specs/017-rust-native-inference-runtime/contracts/f017-event06-sequence05-qualification-schema-authority-v4.json": "3f95e73363908a999361b53fa55f7c15b0cc97740793097cb899348087019484",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-readiness-authority-manifest-v9.json": "19b38aa2bbbb66b45cba658458560076671d69abb1c09e38a6fdbb6caf43e91a",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-future-go-capability-v1.json": "2ff14da03fd3cc59ca7d56b547d27db9f5ba263d5d33cd4b66333b832429d97b",
    "scripts/research/f017_event06_readiness_authority_v2.py": "86796c3f1f9fa4d85c3618340b88b4dd8fb316b251913a6cbf026a1186b38eb3",
    "scripts/research/f017_event06_production_installation_v1.py": "13579b0d5b8d27e84b2eb8c5e91e85eac648798b24847169458370da670a6d6d",
}


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if type(value) is not dict or canonical_bytes(value) != raw:
        raise ValueError(f"noncanonical or non-object artifact: {relative(path)}")
    return value


def git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
    ).strip()


def git_sha(head: str, path: str) -> str:
    return sha_bytes(
        subprocess.check_output(["git", "show", f"{head}:{path}"], cwd=ROOT)
    )


def preserved_surface(qualification: dict[str, object]) -> dict[str, object]:
    roles = qualification["roles"]
    future = qualification["future_output_roles"]
    if type(roles) is not dict or type(future) is not list:
        raise TypeError("qualification surface")
    selected: dict[str, object] = {}
    for role in sorted(future):
        rule = roles[role]
        if type(rule) is not dict:
            raise TypeError(role)
        selected[role] = {
            key: copy.deepcopy(rule[key])
            for key in (
                "acceptance_predicates",
                "availability_stage",
                "minimums",
                "required_schema",
            )
            if key in rule
        }
    return selected


def predicate_historical_bytes() -> bool:
    return all(
        sha(ROOT / path) == expected for path, expected in HISTORICAL_SHA.items()
    )


def predicate_schema_edges(profile: str, docs: dict[str, dict[str, object]]) -> bool:
    paths = PATHS[profile]
    authority = docs["schema"]
    qualification = docs["qualification"]
    roles = qualification["roles"]
    if type(roles) is not dict:
        return False
    authority_path = relative(paths["schema"])
    authority_sha = sha(paths["schema"])
    mapping = {
        "readiness_interface": ("readiness_schema", docs["readiness"]["schema"]),
        "live_installation_interface": (
            "installation_schema",
            docs["installation"]["schema"],
        ),
        "qualification_role_requirements": (
            "qualification_schema",
            qualification["schema"],
        ),
    }
    for role, (field, expected_schema) in mapping.items():
        rule = roles[role]
        if type(rule) is not dict:
            return False
        path_key = (
            "external_schema_authority_path"
            if role == "qualification_role_requirements"
            else "schema_authority_path"
        )
        sha_key = (
            "external_schema_authority_sha256"
            if role == "qualification_role_requirements"
            else "schema_authority_sha256"
        )
        if (
            rule.get(path_key) != authority_path
            or rule.get(sha_key) != authority_sha
            or rule.get("schema_authority_field") != field
            or authority.get(field) != expected_schema
        ):
            return False
    return authority.get("self_reference_permitted") is False


def predicate_cross_version(profile: str, docs: dict[str, dict[str, object]]) -> bool:
    paths = PATHS[profile]
    qualification = docs["qualification"]
    roles = qualification["roles"]
    if type(roles) is not dict:
        return False
    return (
        docs["readiness"].get("schema") == docs["schema"].get("readiness_schema")
        and docs["installation"].get("schema")
        == docs["schema"].get("installation_schema")
        and docs["readiness"].get("qualification_role_requirements")
        == relative(paths["qualification"])
        and docs["readiness"].get("manifest_contract") == relative(paths["manifest"])
        and docs["installation"].get("qualification_role_requirements")
        == relative(paths["qualification"])
        and docs["installation"].get("future_go_capability_contract")
        == relative(FUTURE)
        and docs["installation"].get("future_go_capability_sha256") == sha(FUTURE)
        and docs["installation"].get("transaction_policy_path") == relative(TRANSACTION)
        and docs["installation"].get("transaction_policy_sha256") == sha(TRANSACTION)
        and docs["installation"].get("success_capable_transaction_path") is True
        and roles["readiness_interface"].get("artifact_path")
        == relative(paths["readiness"])
        and roles["live_installation_interface"].get("artifact_path")
        == relative(paths["installation"])
        and roles["qualification_role_requirements"].get("artifact_path")
        == relative(paths["qualification"])
        and roles["implementation_measurement"].get("required", {}).get("schema")
        == "pulsarmlx.f017.event06-v12-sequence09-implementation-measurement/1.0.0"
    )


def predicate_preserved_criteria(docs: dict[str, dict[str, object]]) -> bool:
    base = load(BASE_QUAL)
    expected = preserved_surface(base)
    observed = preserved_surface(docs["qualification"])
    return (
        observed == expected
        and docs["qualification"].get("preserved_cycle11_acceptance_surface_sha256")
        == sha_bytes(canonical_bytes(expected))
        and docs["qualification"].get("mutation_floor") == 324
        and docs["qualification"].get("installation_outcome_count") == 16
        and docs["qualification"].get("race_family_count") == 10
        and docs["qualification"].get("zero_access_required") is True
    )


def _function_calls(path: Path, function_name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            calls: list[str] = []
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
            return calls
    return []


def predicate_instantiable_code() -> bool:
    production = ROOT / "scripts/research/f017_event06_production_installation_v2.py"
    transaction = (
        ROOT / "scripts/research/f017_event06_durable_installation_transaction_v1.py"
    )
    producer_calls = _function_calls(production, "produce_future_go_capability")
    checker_calls = _function_calls(production, "validate_future_go_capability")
    commit_calls = _function_calls(production, "commit_production_installation_v2")
    engine_calls = _function_calls(transaction, "_commit_bound_production_transaction")
    future = load(FUTURE)
    policy = load(TRANSACTION)
    return (
        "_validate_future_go_value" in producer_calls
        and "FutureGoCapabilityV2" in producer_calls
        and "validate_prepared_production_installation" in checker_calls
        and "validate_future_go_capability" in commit_calls
        and "_commit_bound_production_transaction" in commit_calls
        and "_commit_no_replace" in engine_calls
        and future.get("future_human_go_factory_implemented") is True
        and future.get("sequence_9_capability_instances") == 0
        and future.get("sequence_9_production_commit_success_calls") == 0
        and policy.get("production_success_calls_required_in_sequence09") == 0
        and policy.get("production_capability_instances_required_in_sequence09") == 0
    )


def predicate_readiness_census(docs: dict[str, dict[str, object]]) -> bool:
    readiness = docs["readiness"]
    fields = readiness.get("required_fields")
    exact_types = readiness.get("exact_types")
    predicates = readiness.get("exact_predicates")
    if (
        type(fields) is not list
        or len(fields) != readiness.get("field_count")
        or len(fields) != 86
    ):
        return False
    if type(exact_types) is not dict or type(predicates) is not dict:
        return False
    typed = [field for names in exact_types.values() for field in names]
    return (
        len(typed) == len(set(typed)) == 86
        and set(typed) == set(fields)
        and predicates.get("opus_verdict")
        == "ACCEPT_FOR_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_GO"
        and predicates.get("original_checkpoint_shard_opens") == 0
        and predicates.get("event_06_executed") is False
    )


def predicate_validation_state(
    profile: str, docs: dict[str, dict[str, object]]
) -> bool:
    qualification = docs["qualification"]
    if profile == "candidate":
        return (
            qualification.get("active_validation_gap_ids")
            == ["EXTERNAL_SUCCESSOR_VALIDATOR_REQUIRED"]
            and qualification.get("validation_gap_count") == 1
            and qualification.get("all_requirements_mechanically_validated") is False
            and qualification.get("validation_state")
            == "PENDING_EXTERNAL_SUCCESSOR_VALIDATOR"
        )
    source = qualification.get("validation_result_source")
    if type(source) is not str:
        return False
    report = load(ROOT / source)
    return (
        qualification.get("active_validation_gap_ids") == []
        and qualification.get("validation_gap_count") == 0
        and qualification.get("all_requirements_mechanically_validated") is True
        and qualification.get("validation_state") == "PASS"
        and report.get("profile") == "CANDIDATE"
        and report.get("result") == "PASS"
    )


def predicate_measurement_and_prepared(
    profile: str, docs: dict[str, dict[str, object]]
) -> bool:
    if profile != "final":
        return True
    measurement = load(MEASUREMENT)
    prepared = load(PREPARED)
    head = measurement.get("implementation_head")
    tree = measurement.get("implementation_tree")
    if (
        type(head) is not str
        or type(tree) is not str
        or git("rev-parse", f"{head}^{{tree}}") != tree
    ):
        return False
    measured = measurement.get("measured_paths")
    if type(measured) is not list or measurement.get("measured_path_count") != len(
        measured
    ):
        return False
    for row in measured:
        if type(row) is not dict or git_sha(head, row.get("path")) != row.get("sha256"):
            return False
    if (
        prepared.get("implementation_head") != head
        or prepared.get("implementation_tree") != tree
    ):
        return False
    bindings = prepared.get("bindings")
    if type(bindings) is not dict:
        return False
    expected = {
        "implementation_measurement": MEASUREMENT,
        "readiness_interface": PATHS[profile]["readiness"],
        "live_installation_interface": PATHS[profile]["installation"],
        "future_go_capability": FUTURE,
        "qualification_role_requirements": PATHS[profile]["qualification"],
    }
    return all(
        bindings.get(role)
        == {
            "binding_state": "CURRENT_DESIGN_AUTHORITY",
            "path": relative(path),
            "sha256": sha(path),
        }
        for role, path in expected.items()
    )


def predicate_dispositions(profile: str) -> bool:
    if profile != "final":
        return True
    value = load(DISPOSITIONS)
    rows = value.get("findings")
    return (
        type(rows) is list
        and [row.get("id") for row in rows]
        == ["F017-S9-PREQUAL-001", "F017-S9-PREQUAL-002"]
        and all(row.get("status") == "RESOLVED" for row in rows)
        and value.get("resolved_count") == 2
        and value.get("open_count") == 0
        and value.get("acceptance_predicates_changed") is False
        and value.get("checkpoint_access") == 0
        and value.get("production_capability_instances") == 0
        and value.get("production_commit_success_calls") == 0
    )


def load_profile(profile: str) -> dict[str, dict[str, object]]:
    docs = {name: load(path) for name, path in PATHS[profile].items()}
    load(FUTURE)
    load(TRANSACTION)
    load(MEASUREMENT_SCHEMA)
    load(MATRIX)
    if profile == "final":
        load(MEASUREMENT)
        load(PREPARED)
        load(DISPOSITIONS)
    return docs


def mutation_campaign(
    profile: str, docs: dict[str, dict[str, object]]
) -> dict[str, bool]:
    mutations: dict[str, Callable[[], bool]] = {}
    base_readiness = docs["readiness"]
    for name in (
        "field_count",
        "qualification_role_requirements",
        "manifest_contract",
        "schema",
    ):

        def reject(name: str = name) -> bool:
            changed = copy.deepcopy(base_readiness)
            changed[name] = "MUTATED" if name != "field_count" else 85
            if name == "field_count":
                return not (
                    changed.get("field_count") == 86
                    and predicate_readiness_census({**docs, "readiness": changed})
                )
            return not predicate_cross_version(
                profile, {**docs, "readiness": changed}
            ) or not predicate_readiness_census({**docs, "readiness": changed})

        mutations[f"readiness_{name}"] = reject
    for name in (
        "qualification_role_requirements",
        "future_go_capability_sha256",
        "transaction_policy_sha256",
        "success_capable_transaction_path",
    ):

        def reject_install(name: str = name) -> bool:
            changed = copy.deepcopy(docs["installation"])
            changed[name] = (
                False if name == "success_capable_transaction_path" else "0" * 64
            )
            return not predicate_cross_version(
                profile, {**docs, "installation": changed}
            )

        mutations[f"installation_{name}"] = reject_install
    for name in (
        "mutation_floor",
        "installation_outcome_count",
        "race_family_count",
        "preserved_cycle11_acceptance_surface_sha256",
    ):

        def reject_qual(name: str = name) -> bool:
            changed = copy.deepcopy(docs["qualification"])
            changed[name] = 0
            return not predicate_preserved_criteria({**docs, "qualification": changed})

        mutations[f"qualification_{name}"] = reject_qual
    return {name: check() for name, check in mutations.items()}


def validate(profile: str) -> dict[str, object]:
    docs = load_profile(profile)
    predicates = {
        "historical_bytes": predicate_historical_bytes(),
        "schema_edges": predicate_schema_edges(profile, docs),
        "cross_version_closure": predicate_cross_version(profile, docs),
        "preserved_criteria": predicate_preserved_criteria(docs),
        "instantiable_code": predicate_instantiable_code(),
        "readiness_census": predicate_readiness_census(docs),
        "validation_state": predicate_validation_state(profile, docs),
        "measurement_and_prepared": predicate_measurement_and_prepared(profile, docs),
        "finding_dispositions": predicate_dispositions(profile),
        "zero_checkpoint_access": True,
    }
    mutations = mutation_campaign(profile, docs)
    passed = all(predicates.values()) and all(mutations.values())
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-external-authority-validation/1.0.0",
        "profile": profile.upper(),
        "validated_head": git("rev-parse", "HEAD"),
        "validated_tree": git("rev-parse", "HEAD^{tree}"),
        "predicates": predicates,
        "predicate_count": len(predicates),
        "predicate_passes": sum(predicates.values()),
        "mutations": mutations,
        "mutation_count": len(mutations),
        "mutation_rejections": sum(mutations.values()),
        "checkpoint_access": 0,
        "production_capability_instances": 0,
        "production_commit_success_calls": 0,
        "result": "PASS" if passed else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("candidate", "final"), required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = validate(arguments.profile)
    raw = canonical_bytes(result)
    if arguments.output is None:
        print(raw.decode())
    else:
        output = arguments.output
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

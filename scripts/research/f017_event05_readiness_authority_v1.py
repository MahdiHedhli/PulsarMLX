#!/usr/bin/env python3
"""Canonical typed Event-05 readiness declaration authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
from types import MappingProxyType
from typing import Any, Mapping

from f017_bounded_artifact_decode_v1 import read_artifact

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v3.json"

CANONICAL_MANIFEST_ROLES = {
    "implementation_measurement",
    "scientific_access",
    "numerical_contract_v4",
    "result_authority",
    "full_native_ci",
    "evidence_only_ci",
    "gemini_readiness_interface_challenge",
    "opus_readiness_interface_implementation_arbiter",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(value: object) -> bool:
    if type(value) is not str or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def _resolve(root: Path, value: object) -> Path:
    if not _relative_path(value):
        raise ValueError("readiness repository path")
    root = root.resolve(strict=True)
    target = (root / str(value)).resolve(strict=True)
    if target == root or root not in target.parents or not target.is_file():
        raise ValueError("readiness repository path")
    return target


@dataclass(frozen=True, slots=True)
class ValidatedReadiness:
    values: Mapping[str, Any]
    source_path: Path
    source_sha256: str

    @property
    def authority_scope(self) -> str:
        return str(self.values["authority_scope"])

    @property
    def measured_implementation_head(self) -> str:
        return str(self.values["measured_implementation_head"])

    @property
    def measured_implementation_tree(self) -> str:
        return str(self.values["measured_implementation_tree"])

    @property
    def authority_manifest_sha256(self) -> str:
        return str(self.values["authority_manifest_sha256"])

    @property
    def full_native_run(self) -> int:
        return int(self.values["full_native_run"])


def _validate_type(name: str, value: object, category: str) -> None:
    valid = False
    if category == "boolean_fields":
        valid = type(value) is bool
    elif category == "non_boolean_nonnegative_integer_fields":
        valid = type(value) is int and type(value) is not bool and value >= 0
    elif category == "positive_integer_fields":
        valid = type(value) is int and type(value) is not bool and value > 0
    elif category == "sha256_fields":
        valid = type(value) is str and len(value) == 64 and value == value.lower() and all(c in "0123456789abcdef" for c in value)
    elif category == "git_object_fields":
        valid = type(value) is str and len(value) == 40 and value == value.lower() and all(c in "0123456789abcdef" for c in value)
    elif category == "repository_relative_path_fields":
        valid = _relative_path(value)
    elif category == "exact_string_fields":
        valid = type(value) is str and bool(value)
    if not valid:
        raise ValueError(f"readiness field type: {name}")


def _artifact_map(manifest: object, root: Path) -> dict[str, dict]:
    if type(manifest) is not dict or type(manifest.get("artifacts")) is not list:
        raise ValueError("readiness authority manifest")
    artifacts = manifest["artifacts"]
    if manifest.get("binding_count") != len(artifacts):
        raise ValueError("readiness authority manifest")
    result: dict[str, dict] = {}
    for item in artifacts:
        if type(item) is not dict or set(item) != {"role", "path", "sha256"}:
            raise ValueError("readiness authority manifest")
        role = item["role"]
        if type(role) is not str or role in result:
            raise ValueError("readiness authority manifest")
        target = _resolve(root, item["path"])
        if _sha(target) != item["sha256"]:
            raise ValueError("readiness authority manifest sha")
        result[role] = item
    if set(result) != CANONICAL_MANIFEST_ROLES:
        raise ValueError("readiness authority manifest role census")
    return result


def _require_role_binding(values: Mapping[str, Any], artifacts: Mapping[str, dict], role: str,
                          path_field: str, sha_field: str) -> None:
    item = artifacts[role]
    if item["path"] != values[path_field] or item["sha256"] != values[sha_field]:
        raise ValueError(f"readiness authority role binding: {role}")


def _git_object(object_name: str, expected_type: str) -> None:
    try:
        actual = subprocess.check_output(
            ["git", "cat-file", "-t", object_name], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("readiness implementation git object") from exc
    if actual != expected_type:
        raise ValueError("readiness implementation git object")


def _validate_review_artifact(value: object, *, scope: str, role: str,
                              policy: Mapping[str, Any], root: Path,
                              measured_implementation_head: str) -> None:
    if type(value) is not dict:
        raise ValueError(f"readiness {role} evidence")
    expected_schema = policy[f"{role}_schema"]
    if value.get("schema") != expected_schema:
        raise ValueError(f"readiness {role} evidence schema")
    if scope == "VALIDATION_ONLY_PREPARED":
        required = {
            "authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
            "live_authority_permitted":False, "verdict":"VALIDATION_ONLY_PREPARED",
        }
        for name, expected in required.items():
            if value.get(name) != expected or type(value.get(name)) is not type(expected):
                raise ValueError(f"readiness {role} prepared evidence")
        return
    expected_model = "gemini-3.1-pro-high" if role == "gemini" else "claude-opus-5"
    verdict_field = "verdict" if role == "gemini" else "global_verdict"
    expected_verdict = "NO_UNRESOLVED_MATERIAL_CHALLENGE" if role == "gemini" else "ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION"
    required = {
        "authority_scope":"FINAL_EVENT05_EXECUTION_READINESS", "final_authority":True,
        "model":expected_model, verdict_field:expected_verdict,
        "blocking_findings":0, "non_blocking_required_findings":0, "unresolved_claims":0,
    }
    for name, expected in required.items():
        if value.get(name) != expected or type(value.get(name)) is not type(expected):
            raise ValueError(f"readiness {role} final evidence")
    for name, length in (("reviewed_head", 40), ("exact_response_sha256", 64)):
        field = value.get(name)
        if type(field) is not str or len(field) != length or field != field.lower() or any(c not in "0123456789abcdef" for c in field):
            raise ValueError(f"readiness {role} final evidence")
    reviewed_head = value["reviewed_head"]
    _git_object(reviewed_head, "commit")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", measured_implementation_head, reviewed_head],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        raise ValueError(f"readiness {role} reviewed head ancestry")
    response_path = _resolve(root, value.get("exact_response_path"))
    if _sha(response_path) != value["exact_response_sha256"]:
        raise ValueError(f"readiness {role} exact response binding")


def _validate_bound_authority(values: Mapping[str, Any], root: Path, contract: Mapping[str, Any]) -> None:
    path_sha_fields = (
        ("authority_manifest_path", "authority_manifest_sha256"),
        ("scientific_access_contract_path", "scientific_access_contract_sha256"),
        ("result_authority_path", "result_authority_sha256"),
        ("numerical_contract_path", "numerical_contract_sha256"),
        ("full_native_evidence_path", "full_native_evidence_sha256"),
        ("evidence_only_evidence_path", "evidence_only_evidence_sha256"),
        ("gemini_result_path", "gemini_result_sha256"),
        ("opus_result_path", "opus_result_sha256"),
    )
    resolved: dict[str, Path] = {}
    for path_field, sha_field in path_sha_fields:
        target = _resolve(root, values[path_field])
        if _sha(target) != values[sha_field]:
            raise ValueError(f"readiness bound artifact sha: {path_field}")
        resolved[path_field] = target

    manifest = read_artifact(resolved["authority_manifest_path"])
    scope = values["authority_scope"]
    policy = contract["scope_policy"][scope]
    if (manifest.get("schema") != policy["manifest_schema"]
            or manifest.get("authority_scope") != scope
            or manifest.get("final_authority") is not policy["final_authority"]):
        raise ValueError("readiness authority manifest scope")
    if scope == "VALIDATION_ONLY_PREPARED" and manifest.get("live_authority_permitted") is not False:
        raise ValueError("readiness authority manifest scope")
    artifacts = _artifact_map(manifest, root)
    _require_role_binding(values, artifacts, "scientific_access", "scientific_access_contract_path", "scientific_access_contract_sha256")
    _require_role_binding(values, artifacts, "result_authority", "result_authority_path", "result_authority_sha256")
    _require_role_binding(values, artifacts, "numerical_contract_v4", "numerical_contract_path", "numerical_contract_sha256")
    _require_role_binding(values, artifacts, "full_native_ci", "full_native_evidence_path", "full_native_evidence_sha256")
    _require_role_binding(values, artifacts, "evidence_only_ci", "evidence_only_evidence_path", "evidence_only_evidence_sha256")
    _require_role_binding(values, artifacts, "gemini_readiness_interface_challenge", "gemini_result_path", "gemini_result_sha256")
    _require_role_binding(values, artifacts, "opus_readiness_interface_implementation_arbiter", "opus_result_path", "opus_result_sha256")

    measurement_item = artifacts["implementation_measurement"]
    measurement = read_artifact(_resolve(root, measurement_item["path"]))
    if (type(measurement) is not dict
            or measurement.get("implementation_head") != values["measured_implementation_head"]
            or measurement.get("implementation_tree") != values["measured_implementation_tree"]
            or manifest.get("implementation_head") != values["measured_implementation_head"]
            or manifest.get("implementation_tree") != values["measured_implementation_tree"]):
        raise ValueError("readiness implementation measurement")
    head = values["measured_implementation_head"]
    tree = values["measured_implementation_tree"]
    _git_object(head, "commit")
    _git_object(tree, "tree")
    actual_tree = subprocess.check_output(["git", "rev-parse", f"{head}^{{tree}}"], cwd=ROOT, text=True).strip()
    if actual_tree != tree:
        raise ValueError("readiness implementation git tree")

    full_native = read_artifact(resolved["full_native_evidence_path"])
    evidence_only = read_artifact(resolved["evidence_only_evidence_path"])
    gemini = read_artifact(resolved["gemini_result_path"])
    opus = read_artifact(resolved["opus_result_path"])
    if (full_native.get("run_id", full_native.get("run")) != values["full_native_run"]
            or full_native.get("required_native_skips") != values["full_native_required_skips"]
            or full_native.get("result") != "PASS"):
        raise ValueError("readiness FULL_NATIVE evidence")
    if (evidence_only.get("run_id", evidence_only.get("run")) != values["evidence_only_run"]
            or evidence_only.get("native_jobs_launched") != values["evidence_only_native_jobs"]
            or evidence_only.get("result") != "PASS"):
        raise ValueError("readiness EVIDENCE_ONLY evidence")
    _validate_review_artifact(
        gemini, scope=scope, role="gemini", policy=policy, root=root,
        measured_implementation_head=values["measured_implementation_head"],
    )
    _validate_review_artifact(
        opus, scope=scope, role="opus", policy=policy, root=root,
        measured_implementation_head=values["measured_implementation_head"],
    )
    if gemini.get("verdict") != values["gemini_verdict"]:
        raise ValueError("readiness Gemini evidence")
    opus_verdict = opus["global_verdict"] if scope == "FINAL_EVENT05_EXECUTION_READINESS" else opus["verdict"]
    if opus_verdict != values["opus_verdict"]:
        raise ValueError("readiness Opus evidence")


def validate_readiness_value(value: object, expected_scope: str | None = None) -> dict[str, Any]:
    contract = read_artifact(CONTRACT)
    fields = contract["required_fields"]
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("readiness declaration key census")
    type_map = {name: category for category, names in contract["exact_types"].items() for name in names}
    if set(type_map) != set(fields):
        raise ValueError("readiness contract type census")
    for name in fields:
        _validate_type(name, value[name], type_map[name])
    scope = value.get("authority_scope") if type(value) is dict else None
    predicates_name = {
        "FINAL_EVENT05_EXECUTION_READINESS":"exact_final_predicates",
        "VALIDATION_ONLY_PREPARED":"exact_prepared_predicates",
    }.get(scope)
    if predicates_name is None or (expected_scope is not None and scope != expected_scope):
        raise ValueError("readiness authority scope")
    for name, required in contract[predicates_name].items():
        if value[name] != required or type(value[name]) is not type(required):
            raise ValueError(f"readiness predicate: {name}")
    return dict(value)


def validate_readiness_declaration(path: Path, expected: Mapping[str, object] | None = None,
                                   expected_scope: str | None = None,
                                   *, repository_root: Path = ROOT) -> ValidatedReadiness:
    contract = read_artifact(CONTRACT)
    value = validate_readiness_value(read_artifact(path), expected_scope)
    if expected is not None:
        for name, required in expected.items():
            if name not in value or value[name] != required or type(value[name]) is not type(required):
                raise ValueError(f"readiness expected binding: {name}")
    _validate_bound_authority(value, repository_root, contract)
    return ValidatedReadiness(
        values=MappingProxyType(dict(value)),
        source_path=path.resolve(strict=True),
        source_sha256=_sha(path),
    )

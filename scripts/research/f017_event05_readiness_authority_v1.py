#!/usr/bin/env python3
"""Canonical typed Event-05 readiness declaration authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from f017_bounded_artifact_decode_v1 import read_artifact

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v1.json"

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


def _validate_bound_authority(values: Mapping[str, Any], root: Path) -> None:
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
    if gemini.get("verdict") != values["gemini_verdict"]:
        raise ValueError("readiness Gemini evidence")
    if opus.get("global_verdict") != values["opus_verdict"]:
        raise ValueError("readiness Opus evidence")


def validate_readiness_value(value: object) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    fields = contract["required_fields"]
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("readiness declaration key census")
    type_map = {name: category for category, names in contract["exact_types"].items() for name in names}
    if set(type_map) != set(fields):
        raise ValueError("readiness contract type census")
    for name in fields:
        _validate_type(name, value[name], type_map[name])
    for name, required in contract["exact_final_predicates"].items():
        if value[name] != required or type(value[name]) is not type(required):
            raise ValueError(f"readiness predicate: {name}")
    return dict(value)


def validate_readiness_declaration(path: Path, expected: Mapping[str, object] | None = None,
                                   *, repository_root: Path = ROOT) -> ValidatedReadiness:
    value = validate_readiness_value(read_artifact(path))
    if expected is not None:
        for name, required in expected.items():
            if name not in value or value[name] != required or type(value[name]) is not type(required):
                raise ValueError(f"readiness expected binding: {name}")
    _validate_bound_authority(value, repository_root)
    return ValidatedReadiness(
        values=MappingProxyType(dict(value)),
        source_path=path.resolve(strict=True),
        source_sha256=_sha(path),
    )

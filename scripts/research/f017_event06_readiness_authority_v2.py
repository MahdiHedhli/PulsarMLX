#!/usr/bin/env python3
"""Closed Event 06 V12 readiness consumer for the accepted Sequence 5 design."""

from __future__ import annotations

import copy
import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Final, Never, Self, SupportsIndex, cast

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes

ROOT: Final = Path(__file__).resolve().parents[2]
INTERFACE: Final = ROOT / (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-event06-readiness-consumer-interface-v10.json"
)
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
_SEAL = object()


class Event06ReadinessError(ValueError):
    """Stable fail-closed readiness outcome."""

    def __init__(self, outcome_id: str, detail: str):
        super().__init__(f"{outcome_id}: {detail}")
        self.outcome_id = outcome_id
        self.detail = detail


def _fail(category: str, detail: str) -> Event06ReadinessError:
    outcomes = {
        "binding": "F017_EVENT06_READINESS_BINDING",
        "canonical": "F017_EVENT06_READINESS_NONCANONICAL",
        "field": "F017_EVENT06_READINESS_FIELD",
        "predicate": "F017_EVENT06_READINESS_PREDICATE",
        "schema": "F017_EVENT06_READINESS_SCHEMA",
        "type": "F017_EVENT06_READINESS_TYPE",
    }
    return Event06ReadinessError(outcomes[category], detail)


def _freeze(value: object) -> object:
    if type(value) is dict:
        return tuple((key, _freeze(value[key])) for key in sorted(value))
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if type(value) is tuple:
        if value and all(
            type(item) is tuple and len(item) == 2 and type(item[0]) is str
            for item in value
        ):
            return {key: _thaw(item) for key, item in value}
        return [_thaw(item) for item in value]
    return value


class ValidatedEvent06ReadinessV2:
    """Opaque validator-created authority; intentionally not a Mapping."""

    __slots__ = ("_items", "source_sha256", "_locked")
    _items: tuple[tuple[str, object], ...]
    source_sha256: str
    _locked: bool

    def __new__(cls, seal: object = None, value: object = None) -> Self:
        if seal is not _SEAL:
            raise TypeError("Event 06 readiness is validator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object]) -> None:
        del seal
        object.__setattr__(
            self, "_items", cast(tuple[tuple[str, object], ...], _freeze(value))
        )
        object.__setattr__(
            self, "source_sha256", hashlib.sha256(canonical_bytes(value)).hexdigest()
        )
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        if getattr(self, "_locked", False):
            raise TypeError("Event 06 readiness is immutable")
        raise TypeError("Event 06 readiness is validator-created")

    def get(self, key: str) -> object:
        for name, value in self._items:
            if name == key:
                return _thaw(value)
        raise KeyError(key)

    def __copy__(self) -> Never:
        raise TypeError("Event 06 readiness cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("Event 06 readiness cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("Event 06 readiness cannot be pickled")


def _load_contract(path: Path) -> dict[str, object]:
    value = parse_artifact_bytes(path.read_bytes())
    if type(value) is not dict:
        raise _fail("binding", "readiness interface")
    return value


def _valid_repo_path(value: object) -> bool:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and all(
        part not in {"", ".", ".."} for part in pure.parts
    )


def _resolve_repo_file(root: Path, value: object) -> Path:
    if not _valid_repo_path(value):
        raise _fail("type", "repository path")
    text = cast(str, value)
    root = root.resolve(strict=True)
    cursor = root
    for part in PurePosixPath(text).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise _fail("binding", f"symlink path: {value}")
    try:
        resolved = cursor.resolve(strict=True)
    except OSError as exc:
        raise _fail("binding", f"missing path: {value}") from exc
    if root not in resolved.parents or not resolved.is_file():
        raise _fail("binding", f"path escapes repository: {value}")
    return resolved


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _type_is_valid(category: str, value: object) -> bool:
    if category == "boolean":
        return type(value) is bool
    if category == "nonnegative_integer":
        return type(value) is int and type(value) is not bool and value >= 0
    if category == "git_object":
        return type(value) is str and HEX40.fullmatch(value) is not None
    if category == "sha256":
        return type(value) is str and HEX64.fullmatch(value) is not None
    if category == "repository_path":
        return _valid_repo_path(value)
    if category == "string":
        return type(value) is str and bool(value)
    return False


def _nested_get(value: dict[str, object], dotted: str) -> object:
    current: object = value
    for part in dotted.split("."):
        if type(current) is not dict or part not in current:
            raise _fail("binding", f"missing role predicate: {dotted}")
        current = current[part]
    return current


def _validate_role_requirement(
    role: str,
    artifact: dict[str, object],
    rule: dict[str, object],
    declaration: dict[str, object],
) -> None:
    required = rule.get("required", {})
    if type(required) is dict:
        for name, expected in required.items():
            if artifact.get(name) != expected or type(artifact.get(name)) is not type(
                expected
            ):
                raise _fail("binding", f"role predicate: {role}.{name}")
    acceptance = rule.get("acceptance_predicates", {})
    if type(acceptance) is dict:
        for name, expected in acceptance.items():
            if artifact.get(name) != expected or type(artifact.get(name)) is not type(
                expected
            ):
                raise _fail("binding", f"role acceptance: {role}.{name}")
    minimums = rule.get("minimums", {})
    if type(minimums) is dict:
        for name, floor in minimums.items():
            actual = artifact.get(name)
            if type(actual) is not int or type(actual) is bool or actual < floor:
                raise _fail("binding", f"role minimum: {role}.{name}")
    nested = rule.get("nested_required", {})
    if type(nested) is dict:
        for name, expected in nested.items():
            if type(expected) is dict:
                for child, child_expected in expected.items():
                    if _nested_get(artifact, f"{name}.{child}") != child_expected:
                        raise _fail(
                            "binding", f"role nested predicate: {role}.{name}.{child}"
                        )
    schema = rule.get("required_schema")
    if schema is not None and artifact.get("schema") != schema:
        raise _fail("binding", f"role schema: {role}")
    cross = rule.get("cross_bindings", {})
    if type(cross) is dict:
        for source_field, declaration_field in cross.items():
            if artifact.get(source_field) != declaration.get(declaration_field):
                raise _fail("binding", f"role cross-binding: {role}.{source_field}")
    elif type(cross) is list:
        for declaration_field in cross:
            if (
                declaration_field in artifact
                and artifact[declaration_field] != declaration[declaration_field]
            ):
                raise _fail(
                    "binding", f"role cross-binding: {role}.{declaration_field}"
                )


def _validate_manifest_and_roles(
    value: dict[str, object],
    root: Path,
    resolved: dict[str, Path],
    interface_contract: dict[str, object],
) -> None:
    manifest = parse_artifact_bytes(resolved["authority_manifest_path"].read_bytes())
    if type(manifest) is not dict:
        raise _fail("binding", "authority manifest type")
    contract = _load_contract(
        _resolve_repo_file(
            root,
            interface_contract["manifest_contract"],
        )
    )
    required_keys = contract["required_keys"]
    required_roles = contract["required_roles"]
    if (
        type(required_keys) is not list
        or set(manifest) != set(required_keys)
        or type(required_roles) is not list
        or manifest.get("roles") != required_roles
        or manifest.get("role_count") != len(required_roles)
        or manifest.get("binding_count") != len(required_roles)
        or manifest.get("result") != "PASS"
        or manifest.get("schema") != contract["manifest_schema"]
        or manifest.get("implementation_head") != value["implementation_head"]
        or manifest.get("implementation_tree") != value["implementation_tree"]
    ):
        raise _fail("binding", "authority manifest census")
    bindings = manifest.get("bindings")
    if type(bindings) is not dict or set(bindings) != set(required_roles):
        raise _fail("binding", "authority manifest roles")

    role_fields = {role: (f"{role}_path", f"{role}_sha256") for role in required_roles}
    role_fields["implementation_measurement"] = (
        "implementation_measurement_path",
        "implementation_measurement_sha256",
    )
    for role, (path_field, sha_field) in role_fields.items():
        binding = bindings.get(role)
        if (
            type(binding) is not dict
            or set(binding) != {"binding_state", "path", "sha256"}
            or binding.get("binding_state") != "FINAL_ACCEPTED"
            or binding.get("path") != value[path_field]
            or binding.get("sha256") != value[sha_field]
        ):
            raise _fail("binding", f"manifest binding: {role}")

    requirements = parse_artifact_bytes(
        resolved["qualification_role_requirements_path"].read_bytes()
    )
    if type(requirements) is not dict or type(requirements.get("roles")) is not dict:
        raise _fail("binding", "qualification role requirements")
    rules = requirements["roles"]
    if set(rules) != set(required_roles):
        raise _fail("binding", "qualification role census")
    for role, (path_field, _) in role_fields.items():
        artifact = parse_artifact_bytes(resolved[path_field].read_bytes())
        if type(artifact) is not dict:
            raise _fail("binding", f"role artifact type: {role}")
        _validate_role_requirement(role, artifact, rules[role], value)

    challenge = parse_artifact_bytes(resolved["challenge_result_path"].read_bytes())
    if type(challenge) is not dict:
        raise _fail("binding", "challenge result")
    reproduction_path = _resolve_repo_file(
        root, challenge.get("reproduction_report_path")
    )
    if _sha(reproduction_path) != value["challenge_reproduction_sha256"]:
        raise _fail("binding", "challenge reproduction")


def validate_event06_readiness_value_v2(
    value: object,
    *,
    contract_path: Path = INTERFACE,
) -> dict[str, object]:
    contract = _load_contract(contract_path)
    fields = contract.get("required_fields")
    if type(value) is not dict or type(fields) is not list or set(value) != set(fields):
        raise _fail("field", "exact 86-field census")
    if len(fields) != contract.get("field_count") or len(fields) != 86:
        raise _fail("field", "interface field count")
    type_map: dict[str, str] = {}
    exact_types = contract.get("exact_types")
    if type(exact_types) is not dict:
        raise _fail("type", "interface type map")
    for category, names in exact_types.items():
        if type(names) is not list:
            raise _fail("type", "interface type category")
        for name in names:
            if name in type_map:
                raise _fail("type", f"duplicate type assignment: {name}")
            type_map[name] = category
    if set(type_map) != set(fields):
        raise _fail("type", "exact type census")
    for name, category in type_map.items():
        if not _type_is_valid(category, value[name]):
            raise _fail("type", name)
    predicates = contract.get("exact_predicates")
    if type(predicates) is not dict:
        raise _fail("predicate", "interface predicates")
    for name, expected in predicates.items():
        if value[name] != expected or type(value[name]) is not type(expected):
            category = "schema" if name == "schema" else "predicate"
            raise _fail(category, name)
    return dict(value)


def validate_event06_readiness_declaration_v2(
    raw: bytes,
    *,
    repository_root: Path = ROOT,
    contract_path: Path = INTERFACE,
) -> ValidatedEvent06ReadinessV2:
    try:
        decoded = parse_artifact_bytes(raw)
    except Exception as exc:
        if isinstance(exc, Event06ReadinessError):
            raise
        raise _fail("canonical", str(exc)) from exc
    value = validate_event06_readiness_value_v2(decoded, contract_path=contract_path)
    if canonical_bytes(value) != raw:
        raise _fail("canonical", "readiness bytes")

    resolved: dict[str, Path] = {}
    for name in value:
        if not name.endswith("_path"):
            continue
        sha_field = name.removesuffix("_path") + "_sha256"
        if sha_field not in value:
            raise _fail("binding", f"path without SHA: {name}")
        path = _resolve_repo_file(repository_root, value[name])
        if _sha(path) != value[sha_field]:
            raise _fail("binding", f"SHA mismatch: {name}")
        resolved[name] = path

    declared_interface = resolved.get("readiness_interface_path")
    if (
        declared_interface is None
        or declared_interface.read_bytes() != contract_path.read_bytes()
    ):
        raise _fail("binding", "readiness interface identity")

    measurement = parse_artifact_bytes(
        resolved["implementation_measurement_path"].read_bytes()
    )
    if (
        type(measurement) is not dict
        or measurement.get("implementation_head") != value["implementation_head"]
        or measurement.get("implementation_tree") != value["implementation_tree"]
    ):
        raise _fail("binding", "implementation measurement")
    try:
        actual_tree = subprocess.check_output(
            ["git", "rev-parse", f"{value['implementation_head']}^{{tree}}"],
            cwd=repository_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _fail("binding", "implementation Git object") from exc
    if actual_tree != value["implementation_tree"]:
        raise _fail("binding", "implementation Git tree")

    _validate_manifest_and_roles(
        value,
        repository_root,
        resolved,
        _load_contract(contract_path),
    )
    return ValidatedEvent06ReadinessV2(_SEAL, value)


def assert_readiness_sealed(value: object) -> ValidatedEvent06ReadinessV2:
    if type(value) is not ValidatedEvent06ReadinessV2:
        raise _fail("type", "sealed readiness required")
    return value


def assert_copy_pickle_closed(value: ValidatedEvent06ReadinessV2) -> None:
    for operation in (copy.copy, copy.deepcopy):
        try:
            operation(value)
        except TypeError:
            continue
        raise _fail("type", "readiness copy surface")

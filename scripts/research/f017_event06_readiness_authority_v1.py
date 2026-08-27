#!/usr/bin/env python3
"""Canonical typed Event-06 readiness authority for V12 candidate construction."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
from types import MappingProxyType
from typing import Any, Mapping

from f017_bounded_artifact_decode_v1 import read_artifact

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-readiness-consumer-interface-v1.json"
SUPERSEDED_DECLARATION_SHA256S = frozenset({
    "eca5b5d3b56a019b03654987eab512951afc08c52d805540c53e8ce77e2cdf0d",
})


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_path(value: object, root: Path) -> Path:
    if type(value) is not str or not value or "\\" in value:
        raise ValueError("Event 06 readiness repository path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("Event 06 readiness repository path")
    root = root.resolve(strict=True)
    target = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("Event 06 readiness repository path")
    try:
        resolved = target.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Event 06 readiness repository path") from exc
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError("Event 06 readiness repository path")
    return resolved


def _valid_hex(value: object, length: int) -> bool:
    return (type(value) is str and len(value) == length and value == value.lower()
            and all(character in "0123456789abcdef" for character in value))


@dataclass(frozen=True, slots=True)
class ValidatedEvent06Readiness:
    values: Mapping[str, Any]
    source_path: Path
    source_sha256: str


def validate_event06_readiness_value(value: object) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    fields = contract["required_fields"]
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("Event 06 readiness field census")
    type_map = {name: category for category, names in contract["exact_types"].items() for name in names}
    if set(type_map) != set(fields):
        raise ValueError("Event 06 readiness type census")
    for name, category in type_map.items():
        item = value[name]
        valid = {
            "boolean": type(item) is bool,
            "nonnegative_integer": type(item) is int and type(item) is not bool and item >= 0,
            "git_object": _valid_hex(item, 40),
            "sha256": _valid_hex(item, 64),
            "repository_path": type(item) is str and not item.startswith("/") and ".." not in PurePosixPath(item).parts,
            "string": type(item) is str and bool(item),
        }[category]
        if not valid:
            raise ValueError(f"Event 06 readiness type: {name}")
    if value["schema"] != "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.0.0":
        raise ValueError("Event 06 readiness schema")
    for name, expected in contract["exact_predicates"].items():
        if value[name] != expected or type(value[name]) is not type(expected):
            raise ValueError(f"Event 06 readiness predicate: {name}")
    if value["gemini_verdict"] != "NO_UNRESOLVED_MATERIAL_CHALLENGE":
        raise ValueError("Event 06 Gemini verdict")
    if value["opus_verdict"] != "ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION":
        raise ValueError("Event 06 Opus verdict")
    return dict(value)


def validate_event06_readiness_declaration(path: Path, *, repository_root: Path = ROOT,
                                           expected: Mapping[str, object] | None = None) -> ValidatedEvent06Readiness:
    source_sha256 = _sha(path)
    if source_sha256 in SUPERSEDED_DECLARATION_SHA256S:
        raise ValueError("Event 06 readiness declaration superseded")
    value = validate_event06_readiness_value(read_artifact(path))
    if expected is not None:
        for name, required in expected.items():
            if value.get(name) != required or type(value.get(name)) is not type(required):
                raise ValueError(f"Event 06 readiness expected binding: {name}")
    pairs = [(name, name.removesuffix("_path") + "_sha256") for name in value if name.endswith("_path")]
    resolved: dict[str, Path] = {}
    for path_field, sha_field in pairs:
        target = _repo_path(value[path_field], repository_root)
        if _sha(target) != value[sha_field]:
            raise ValueError(f"Event 06 readiness artifact SHA: {path_field}")
        resolved[path_field] = target
    measurement = read_artifact(resolved["implementation_measurement_path"])
    manifest = read_artifact(resolved["authority_manifest_path"])
    if (measurement.get("implementation_head") != value["implementation_head"]
            or measurement.get("implementation_tree") != value["implementation_tree"]
            or manifest.get("implementation_head") != value["implementation_head"]
            or manifest.get("implementation_tree") != value["implementation_tree"]):
        raise ValueError("Event 06 readiness implementation binding")
    bindings = manifest.get("bindings")
    if type(bindings) is not dict or manifest.get("binding_count") != len(bindings):
        raise ValueError("Event 06 readiness authority manifest")
    for path_field, sha_field in pairs:
        if path_field == "authority_manifest_path":
            continue
        if bindings.get(value[path_field]) != value[sha_field]:
            raise ValueError(f"Event 06 readiness manifest role: {path_field}")
    if subprocess.check_output(["git", "rev-parse", f"{value['implementation_head']}^{{tree}}"],
                               cwd=repository_root, text=True).strip() != value["implementation_tree"]:
        raise ValueError("Event 06 readiness Git tree")
    full_native = read_artifact(resolved["full_native_evidence_path"])
    if (full_native.get("run_id", full_native.get("run")) != value["full_native_run"]
            or full_native.get("required_native_skips") != value["required_native_skips"]
            or full_native.get("result") != "PASS"):
        raise ValueError("Event 06 readiness FULL_NATIVE binding")
    for name in ("synthetic_qualification_path", "failure_qualification_path", "no_access_rehearsal_path"):
        evidence = read_artifact(resolved[name])
        if evidence.get("result") != "PASS" or evidence.get("event_06_executed") is not False:
            raise ValueError(f"Event 06 readiness qualification: {name}")
    gemini = read_artifact(resolved["gemini_result_path"])
    opus = read_artifact(resolved["opus_result_path"])
    if (gemini.get("verdict") != value["gemini_verdict"]
            or opus.get("global_verdict") != value["opus_verdict"]
            or gemini.get("blocking_findings") != 0
            or gemini.get("non_blocking_required_findings") != 0
            or gemini.get("unresolved_claims") != 0
            or opus.get("blocking_findings") != 0
            or opus.get("non_blocking_required_findings") != 0
            or opus.get("unresolved_claims") != 0):
        raise ValueError("Event 06 readiness reviewer binding")
    return ValidatedEvent06Readiness(MappingProxyType(value), path.resolve(strict=True), source_sha256)

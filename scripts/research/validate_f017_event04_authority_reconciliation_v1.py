#!/usr/bin/env python3
"""Validate Event-04 authority bindings against exact measured Git bytes.

This validator is intentionally independent of the V6 contract generator and
runtime authorization parser.  An outer JSON SHA never substitutes for
validation of the path/SHA pairs inside the scientific-access authority.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCIENTIFIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6-binding-reconciliation-v1.json"
DEFAULT_MEASUREMENT = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v6-implementation-measurement-v3.json"
DEFAULT_DECLARATION = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-semantic-authority-declaration-v1.json"
DEFAULT_INERT = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v6-binding-reconciliation-v1.json"
DEFAULT_MANIFEST = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event04-load-bearing-authority-manifest-v1.json"
DEFAULT_ACTIVE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v1.json"

MEASURED_BINDINGS = {
    "parser": "scripts/research/f017_corrected_oracle_authorization_v6.py",
    "authorizer": "scripts/research/validate_f017_corrected_oracle_access_v6.py",
    "coordinator": "scripts/research/execute_f017_corrected_oracle_event_v6.py",
    "primary": "scripts/research/f017_corrected_oracle_primary_v6.py",
    "secondary": "scripts/research/f017_corrected_oracle_secondary_v6.py",
    "primary_target_source": "scripts/research/f017_corrected_oracle_primary_target_source_v6.py",
    "secondary_target_source": "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py",
    "primary_numerical": "scripts/research/f017_corrected_oracle_primary_numerics_v2.py",
    "secondary_numerical": "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py",
    "primary_capability": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-primary-capability-v6.json",
    "secondary_capability": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v6.json",
}

DECLARATION_BINDINGS = {
    "parser": "shared_parser",
    "authorizer": "authorizer",
    "coordinator": "coordinator",
    "primary": "primary_consumer",
    "secondary": "secondary_consumer",
}


class ValidationError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def load(path: Path, *, canonical: bool = True) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValidationError(f"nonfinite JSON: {token}")))
    if type(value) is not dict:
        raise ValidationError(f"{path}: top level must be object")
    if canonical and raw != canonical_bytes(value):
        raise ValidationError(f"{path}: noncanonical bytes")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git(*arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def git_bytes(head: str, path: str) -> bytes:
    return git("show", f"{head}:{path}")


def git_blob(head: str, path: str) -> str:
    output = git("ls-tree", head, "--", path).decode().strip().split()
    if len(output) < 3 or output[1] != "blob":
        raise ValidationError(f"no measured Git blob: {path}")
    return output[2]


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValidationError(f"{label}: key census mismatch")


def _string(value: Any, label: str, length: int | None = None) -> str:
    if type(value) is not str or (length is not None and len(value) != length):
        raise ValidationError(f"{label}: strict string required")
    return value


def _binding(value: Any, label: str) -> tuple[str, str]:
    if type(value) is not dict:
        raise ValidationError(f"{label}: object required")
    _exact_keys(value, {"path", "sha256"}, label)
    return _string(value["path"], f"{label}.path"), _string(value["sha256"], f"{label}.sha256", 64)


def _measurement_entries(measurement: dict[str, Any]) -> dict[str, dict[str, str]]:
    entries = measurement.get("entries")
    if type(entries) is not list or measurement.get("entry_count") != len(entries):
        raise ValidationError("measurement entry census")
    result: dict[str, dict[str, str]] = {}
    for item in entries:
        if type(item) is not dict:
            raise ValidationError("measurement entry object")
        _exact_keys(item, {"git_blob_sha", "path", "semantic_role", "sha256"}, "measurement entry")
        path = _string(item["path"], "measurement path")
        if path in result:
            raise ValidationError("duplicate measurement path")
        result[path] = item
    return result


def validate_documents(
    scientific: dict[str, Any],
    measurement: dict[str, Any],
    declaration: dict[str, Any],
    inert: dict[str, Any],
    authority_manifest: dict[str, Any],
    active: dict[str, Any],
    *,
    file_shas: dict[str, str],
    check_worktree: bool,
) -> dict[str, Any]:
    if scientific.get("schema") != "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/6.0.1":
        raise ValidationError("scientific schema")
    if type(scientific.get("authority_generation")) is not int or scientific["authority_generation"] != 6:
        raise ValidationError("scientific authority generation")
    if scientific.get("active_generation_required") != "V6" or active.get("active_live_generation") != "V6":
        raise ValidationError("active generation")
    measurement_head = _string(measurement.get("implementation_head"), "measurement head", 40)
    measurement_tree = _string(measurement.get("git_tree_sha"), "measurement tree", 40)
    source = scientific.get("source_of_truth")
    if type(source) is not dict:
        raise ValidationError("source_of_truth object")
    _exact_keys(source, {"git_tree_sha", "implementation_measurement_head", "implementation_measurement_manifest_path", "implementation_measurement_manifest_sha256", "rule"}, "source_of_truth")
    if source["rule"] != "EXACT_GIT_BYTES_AT_ACCEPTED_IMPLEMENTATION_MEASUREMENT_HEAD":
        raise ValidationError("source-of-truth rule")
    if source["implementation_measurement_head"] != measurement_head or source["git_tree_sha"] != measurement_tree:
        raise ValidationError("scientific measurement identity")
    if source["implementation_measurement_manifest_path"] != file_shas["measurement_path"] or source["implementation_measurement_manifest_sha256"] != file_shas["measurement_sha256"]:
        raise ValidationError("scientific measurement manifest binding")
    if git("rev-parse", f"{measurement_head}^{{tree}}").decode().strip() != measurement_tree:
        raise ValidationError("Git measurement tree")

    entries = _measurement_entries(measurement)
    if measurement.get("result") != "PASS" or measurement.get("branch") != "feat/017-rust-native-inference-runtime":
        raise ValidationError("measurement authority status")
    for path, entry in entries.items():
        exact_bytes = git_bytes(measurement_head, path)
        if entry["sha256"] != sha256_bytes(exact_bytes):
            raise ValidationError(f"measurement entry SHA: {path}")
        if entry["git_blob_sha"] != git_blob(measurement_head, path):
            raise ValidationError(f"measurement entry Git blob: {path}")
        if check_worktree and (ROOT / path).read_bytes() != exact_bytes:
            raise ValidationError(f"measured working-tree drift: {path}")
    bindings = scientific.get("bindings")
    if type(bindings) is not dict:
        raise ValidationError("scientific bindings object")
    expected_binding_names = set(MEASURED_BINDINGS) | {
        "active_generation", "accounting", "capability_policy", "interface", "lifecycle_manifest",
        "lifecycle_model", "numerical_contract", "path_timing", "serialization",
    }
    if set(bindings) != expected_binding_names:
        raise ValidationError("scientific binding census")
    measured_summary: dict[str, dict[str, str]] = {}
    for name, expected_path in MEASURED_BINDINGS.items():
        path, declared_sha = _binding(bindings[name], f"bindings.{name}")
        if path != expected_path or path not in entries:
            raise ValidationError(f"{name}: measured path")
        exact_bytes = git_bytes(measurement_head, path)
        exact_sha = sha256_bytes(exact_bytes)
        entry = entries[path]
        if declared_sha != exact_sha or entry["sha256"] != exact_sha:
            raise ValidationError(f"{name}: SHA does not equal measured Git bytes")
        if entry["git_blob_sha"] != git_blob(measurement_head, path):
            raise ValidationError(f"{name}: Git blob")
        if check_worktree and (ROOT / path).read_bytes() != exact_bytes:
            raise ValidationError(f"{name}: working tree differs from measurement")
        measured_summary[name] = {"path": path, "sha256": exact_sha, "git_blob_sha": entry["git_blob_sha"]}

    for name in expected_binding_names - set(MEASURED_BINDINGS):
        path, declared_sha = _binding(bindings[name], f"bindings.{name}")
        target = ROOT / path
        if not target.is_file() or target.is_symlink() or sha256_path(target) != declared_sha:
            raise ValidationError(f"{name}: authority file binding")

    implementation = declaration.get("implementation")
    if type(implementation) is not dict:
        raise ValidationError("declaration implementation")
    if declaration.get("implementation_head") != measurement_head or declaration.get("implementation_tree") != measurement_tree:
        raise ValidationError("declaration measurement identity")
    for contract_name, declaration_name in DECLARATION_BINDINGS.items():
        path, declared_sha = _binding(implementation.get(declaration_name), f"declaration.implementation.{declaration_name}")
        if {"path": path, "sha256": declared_sha} != {"path": MEASURED_BINDINGS[contract_name], "sha256": bindings[contract_name]["sha256"]}:
            raise ValidationError(f"declaration binding: {contract_name}")

    expected_scientific = {"path": file_shas["scientific_path"], "sha256": file_shas["scientific_sha256"]}
    if inert.get("scientific_access_contract_path") != expected_scientific["path"] or inert.get("scientific_access_contract_sha256") != expected_scientific["sha256"]:
        raise ValidationError("inert fixture scientific binding")
    if inert.get("implementation_measurement_head") != measurement_head:
        raise ValidationError("inert measurement head")
    if inert.get("implementation_measurement_manifest_path") != file_shas["measurement_path"] or inert.get("implementation_measurement_manifest_sha256") != file_shas["measurement_sha256"]:
        raise ValidationError("inert measurement manifest")
    if inert.get("live") is not False or inert.get("state") != "INERT_FIXTURE":
        raise ValidationError("inert state")

    if authority_manifest.get("schema") != "pulsarmlx.f017.event04-load-bearing-authority-manifest/1.0.0":
        raise ValidationError("authority manifest schema")
    manifest_authorities = authority_manifest.get("authorities")
    if type(manifest_authorities) is not dict:
        raise ValidationError("authority manifest authorities")
    required_manifest = {
        "scientific_access": expected_scientific,
        "measurement_manifest": {"path": file_shas["measurement_path"], "sha256": file_shas["measurement_sha256"]},
        "lifecycle_declaration": {"path": file_shas["declaration_path"], "sha256": file_shas["declaration_sha256"]},
        "inert_fixture": {"path": file_shas["inert_path"], "sha256": file_shas["inert_sha256"]},
    }
    for name, expected in required_manifest.items():
        if manifest_authorities.get(name) != expected:
            raise ValidationError(f"authority manifest {name}")
    for name, binding in manifest_authorities.items():
        path, declared_sha = _binding(binding, f"authority_manifest.{name}")
        target = ROOT / path
        if not target.is_file() or target.is_symlink() or sha256_path(target) != declared_sha:
            raise ValidationError(f"authority manifest file: {name}")

    return {
        "result": "PASS",
        "classification": "SCIENTIFIC_ACCESS_INTERNAL_BINDINGS_RECONCILED",
        "implementation_measurement_head": measurement_head,
        "implementation_tree": measurement_tree,
        "measured_bindings": measured_summary,
        "active_generation": "V6",
    }


def _file_shas(paths: dict[str, Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, path in paths.items():
        result[f"{name}_path"] = str(path.relative_to(ROOT))
        result[f"{name}_sha256"] = sha256_path(path)
    return result


def validate_paths(paths: dict[str, Path]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    canonical_authorities = {"scientific", "inert", "authority_manifest"}
    documents = {name: load(path, canonical=name in canonical_authorities) for name, path in paths.items()}
    file_shas = _file_shas(paths)
    result = validate_documents(
        documents["scientific"], documents["measurement"], documents["declaration"],
        documents["inert"], documents["authority_manifest"], documents["active"],
        file_shas=file_shas, check_worktree=True,
    )
    return result, documents, file_shas


def run_mutations(documents: dict[str, dict[str, Any]], file_shas: dict[str, str]) -> dict[str, Any]:
    cases: list[tuple[str, Callable[[dict[str, dict[str, Any]], dict[str, str]], None]]] = []
    def case(name: str):
        def register(function: Callable[[dict[str, dict[str, Any]], dict[str, str]], None]):
            cases.append((name, function)); return function
        return register

    @case("M01_PARSER_SHA_ONLY")
    def _(d, _s): d["scientific"]["bindings"]["parser"]["sha256"] = "0" * 64
    @case("M02_COORDINATOR_SHA_ONLY")
    def _(d, _s): d["scientific"]["bindings"]["coordinator"]["sha256"] = "0" * 64
    @case("M03_PARSER_PATH_ONLY")
    def _(d, _s): d["scientific"]["bindings"]["parser"]["path"] = MEASURED_BINDINGS["coordinator"]
    @case("M04_COORDINATOR_PATH_ONLY")
    def _(d, _s): d["scientific"]["bindings"]["coordinator"]["path"] = MEASURED_BINDINGS["parser"]
    @case("M05_CONTRACT_AND_OUTER_CONSISTENT")
    def _(d, s):
        d["scientific"]["bindings"]["parser"]["sha256"] = "1" * 64
        s["scientific_sha256"] = sha256_bytes(canonical_bytes(d["scientific"]))
        d["inert"]["scientific_access_contract_sha256"] = s["scientific_sha256"]
        d["authority_manifest"]["authorities"]["scientific_access"]["sha256"] = s["scientific_sha256"]
    @case("M06_MANIFEST_AND_CONTRACT_CONSISTENT")
    def _(d, s):
        for entry in d["measurement"]["entries"]:
            if entry["path"] == MEASURED_BINDINGS["parser"]: entry["sha256"] = "2" * 64
        d["scientific"]["bindings"]["parser"]["sha256"] = "2" * 64
        changed_manifest_sha = sha256_bytes(canonical_bytes(d["measurement"]))
        s["measurement_sha256"] = changed_manifest_sha
        d["scientific"]["source_of_truth"]["implementation_measurement_manifest_sha256"] = changed_manifest_sha
        d["inert"]["implementation_measurement_manifest_sha256"] = changed_manifest_sha
        d["authority_manifest"]["authorities"]["measurement_manifest"]["sha256"] = changed_manifest_sha
    @case("M07_MEASUREMENT_HEAD")
    def _(d, _s): d["measurement"]["implementation_head"] = "0" * 40
    @case("M08_IMPLEMENTATION_TREE")
    def _(d, _s): d["measurement"]["git_tree_sha"] = "0" * 40
    @case("M09_ACTIVE_GENERATION")
    def _(d, _s): d["active"]["active_live_generation"] = "V5"
    @case("M10_INERT_OLD_CONTRACT")
    def _(d, _s): d["inert"]["scientific_access_contract_path"] = "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6.json"
    @case("M11_DECLARATION_PARSER")
    def _(d, _s): d["declaration"]["implementation"]["shared_parser"]["sha256"] = "3" * 64
    @case("M12_BINDING_OMITTED")
    def _(d, _s): del d["scientific"]["bindings"]["coordinator"]
    @case("M13_BINDING_TYPE")
    def _(d, _s): d["scientific"]["bindings"]["parser"]["sha256"] = True
    @case("M14_GENERATION_BOOLEAN")
    def _(d, _s): d["scientific"]["authority_generation"] = True
    @case("M15_PARSER_STALE_WITH_VALID_OUTER")
    def _(d, _s): d["scientific"]["bindings"]["parser"]["sha256"] = "be4a52a0a8b8fdc7e146fffcdbce1b41f70130816db49542e4d3c2cf78e2981a"
    @case("M16_COORDINATOR_STALE_WITH_VALID_OUTER")
    def _(d, _s): d["scientific"]["bindings"]["coordinator"]["sha256"] = "5c80525fdf018c34d22a1bbf4ca2b1eec2c7d80ff3e743155262a2fddea4f673"
    @case("M17_UNBOUND_MEASUREMENT_ENTRY_SHA")
    def _(d, _s):
        target = next(entry for entry in d["measurement"]["entries"] if entry["path"] not in set(MEASURED_BINDINGS.values()))
        target["sha256"] = "4" * 64
    @case("M18_UNBOUND_MEASUREMENT_ENTRY_BLOB")
    def _(d, _s):
        target = next(entry for entry in d["measurement"]["entries"] if entry["path"] not in set(MEASURED_BINDINGS.values()))
        target["git_blob_sha"] = "5" * 40

    rejected: list[str] = []
    for name, mutate in cases:
        mutated = copy.deepcopy(documents); mutated_shas = dict(file_shas); mutate(mutated, mutated_shas)
        try:
            validate_documents(mutated["scientific"], mutated["measurement"], mutated["declaration"], mutated["inert"], mutated["authority_manifest"], mutated["active"], file_shas=mutated_shas, check_worktree=False)
        except (ValidationError, KeyError, FileNotFoundError, subprocess.CalledProcessError):
            rejected.append(name)
        else:
            raise ValidationError(f"mutation unexpectedly accepted: {name}")
    return {"result": "PASS", "mutation_count": len(cases), "rejected_count": len(rejected), "rejected": rejected}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scientific", type=Path, default=DEFAULT_SCIENTIFIC)
    parser.add_argument("--measurement", type=Path, default=DEFAULT_MEASUREMENT)
    parser.add_argument("--declaration", type=Path, default=DEFAULT_DECLARATION)
    parser.add_argument("--inert", type=Path, default=DEFAULT_INERT)
    parser.add_argument("--authority-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--active", type=Path, default=DEFAULT_ACTIVE)
    parser.add_argument("--run-mutations", action="store_true")
    arguments = parser.parse_args()
    paths = {
        "scientific": arguments.scientific.resolve(), "measurement": arguments.measurement.resolve(),
        "declaration": arguments.declaration.resolve(), "inert": arguments.inert.resolve(),
        "authority_manifest": arguments.authority_manifest.resolve(), "active": arguments.active.resolve(),
    }
    try:
        result, documents, file_shas = validate_paths(paths)
        if arguments.run_mutations:
            result["mutations"] = run_mutations(documents, file_shas)
    except (ValidationError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(json.dumps({"result": "FAIL", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

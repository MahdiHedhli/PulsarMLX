#!/usr/bin/env python3
"""Recursively validate a constructed F017 V8 artifact package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_package(package_root: Path, terminal_id: str, required: set[str], roots: dict[str, dict[str, str]], dag: dict, schemas: dict, outcome: str) -> dict:
    visiting: set[str] = set()
    visited: set[str] = set()
    maximum_depth = 0
    package_attempt_id: str | None = None
    authorization_id: str | None = None
    node_map = {item["artifact_id"]: item for item in dag["nodes"]}
    expected_roots = {key: item["sha256"] for key, item in roots.items()}
    if required != {artifact_id for artifact_id, node in node_map.items() if outcome in node["outcome_applicability"]}:
        raise ValueError("required set does not conform to DAG outcome applicability")
    actual_files = {path.stem for path in package_root.glob("*.json")}
    if actual_files != required:
        raise ValueError(f"package artifact census mismatch: missing={sorted(required-actual_files)} unexpected={sorted(actual_files-required)}")

    def walk(artifact_id: str, expected_sha: str | None, depth: int) -> None:
        nonlocal maximum_depth, package_attempt_id, authorization_id
        maximum_depth = max(maximum_depth, depth)
        if artifact_id in visiting:
            raise ValueError(f"artifact cycle: {artifact_id}")
        path = package_root / f"{artifact_id}.json"
        if not path.is_file():
            raise ValueError(f"missing artifact: {artifact_id}")
        raw = path.read_bytes()
        value = json.loads(raw)
        if raw != canonical(value):
            raise ValueError(f"noncanonical artifact: {artifact_id}")
        actual_sha = hashlib.sha256(raw).hexdigest()
        if expected_sha is not None and actual_sha != expected_sha:
            raise ValueError(f"artifact sha mismatch: {artifact_id}")
        if artifact_id not in node_map or artifact_id not in schemas["artifacts"]:
            raise ValueError(f"undeclared artifact: {artifact_id}")
        node = node_map[artifact_id]
        descriptor = schemas["artifacts"][artifact_id]
        if set(value) != set(descriptor["keys"]) or set(value["payload"]) != set(descriptor["payload_keys"]):
            raise ValueError(f"artifact key census mismatch: {artifact_id}")
        if value["schema"] != descriptor["schema_id"] or value["artifact_kind"] != node["artifact_kind"] or value["creation_rank"] != node["creation_rank"]:
            raise ValueError(f"artifact schema binding mismatch: {artifact_id}")
        if value["outcome"] != outcome:
            raise ValueError(f"artifact outcome mismatch: {artifact_id}")
        if value["payload"] | descriptor.get("payload_constants", {}) != value["payload"]:
            raise ValueError(f"payload constant mismatch: {artifact_id}")
        for key, expected in descriptor.get("payload_constants", {}).items():
            if value["payload"].get(key) != expected:
                raise ValueError(f"payload constant mismatch: {artifact_id}:{key}")
        if value["artifact_id"] != artifact_id:
            raise ValueError(f"artifact identity mismatch: {artifact_id}")
        if package_attempt_id is None:
            package_attempt_id = value["package_attempt_id"]
            authorization_id = value["authorization_id"]
        if value["package_attempt_id"] != package_attempt_id or value["authorization_id"] != authorization_id:
            raise ValueError(f"cross-package artifact splice: {artifact_id}")
        if artifact_id in visited:
            return
        visiting.add(artifact_id)
        if value["root_authorities"] != expected_roots:
            raise ValueError(f"root authority census mismatch: {artifact_id}")
        if set(value["dependencies"]) != set(node["dependencies"]):
            raise ValueError(f"dependency census mismatch: {artifact_id}")
        for dependency_id, dependency_sha in value["dependencies"].items():
            dependency_path = package_root / f"{dependency_id}.json"
            dependency_value = json.loads(dependency_path.read_bytes())
            if type(dependency_value.get("creation_rank")) is not int or dependency_value["creation_rank"] >= value["creation_rank"]:
                raise ValueError(f"noncausal dependency rank: {artifact_id}:{dependency_id}")
            walk(dependency_id, dependency_sha, depth + 1)
        visiting.remove(artifact_id)
        visited.add(artifact_id)

    walk(terminal_id, None, 1)
    missing = required - visited
    if missing:
        raise ValueError(f"required artifact outside terminal closure: {sorted(missing)}")
    return {"result": "PASS", "terminal_id": terminal_id, "artifacts_reached": len(visited), "maximum_closure_depth": maximum_depth, "cycles": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--terminal-id", required=True)
    parser.add_argument("--required-json", type=Path, required=True)
    parser.add_argument("--roots-json", type=Path, required=True)
    parser.add_argument("--dag-json", type=Path, required=True)
    parser.add_argument("--schemas-json", type=Path, required=True)
    parser.add_argument("--outcome", required=True)
    args = parser.parse_args()
    required = set(json.loads(args.required_json.read_bytes()))
    roots = json.loads(args.roots_json.read_bytes())
    dag = json.loads(args.dag_json.read_bytes())
    schemas = json.loads(args.schemas_json.read_bytes())
    print(json.dumps(validate_package(args.package_root, args.terminal_id, required, roots, dag, schemas, args.outcome), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

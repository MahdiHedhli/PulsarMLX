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
        terminal_artifact = artifact_id == terminal_id
        expected_artifact_outcome = outcome if terminal_artifact else "PENDING"
        if value["outcome"] != expected_artifact_outcome:
            raise ValueError(f"artifact outcome mismatch: {artifact_id}")
        if set(descriptor.get("payload_rules", {})) != set(descriptor["payload_keys"]):
            raise ValueError(f"payload rule census mismatch: {artifact_id}")
        for key, expected in descriptor.get("payload_constants", {}).items():
            if value["payload"].get(key) != expected:
                raise ValueError(f"payload constant mismatch: {artifact_id}:{key}")
        type_names = {"STRING": str, "INTEGER": int, "BOOLEAN": bool, "ARRAY": list, "OBJECT": dict}
        for key, rule in descriptor["payload_rules"].items():
            observed = value["payload"][key]
            kind = rule["kind"]
            if kind == "EXACT_CONSTANT" and observed != rule["value"]:
                raise ValueError(f"payload rule constant mismatch: {artifact_id}:{key}")
            if kind == "TYPE" and type(observed) is not type_names[rule["type"]]:
                raise ValueError(f"payload type mismatch: {artifact_id}:{key}")
            if kind == "NONNEGATIVE_INTEGER" and (type(observed) is not int or observed < 0):
                raise ValueError(f"payload nonnegative integer mismatch: {artifact_id}:{key}")
            if kind == "SHA256" and (type(observed) is not str or len(observed) != 64 or any(character not in "0123456789abcdef" for character in observed)):
                raise ValueError(f"payload sha256 mismatch: {artifact_id}:{key}")
            if kind == "ENUM" and observed not in rule["values"]:
                raise ValueError(f"payload enum mismatch: {artifact_id}:{key}")
            if kind == "ARRAY_EXACT_LENGTH" and (type(observed) is not list or len(observed) != rule["length"]):
                raise ValueError(f"payload array length mismatch: {artifact_id}:{key}")
            if kind == "DESCRIPTOR_IDENTITY_ARRAY":
                fields = {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal", "role", "lease_id"}
                if type(observed) is not list or len(observed) != rule["length"] or [item.get("shard_ordinal") for item in observed] != rule["ordinals"] or any(set(item) != fields or item["role"] != "GRAPH_PAYLOAD" for item in observed):
                    raise ValueError(f"descriptor identity array mismatch: {artifact_id}:{key}")
            if kind == "ARTIFACT_SHA256":
                reference_path = package_root / f"{rule['artifact_id']}.json"
                if not reference_path.is_file() or observed != digest(reference_path):
                    raise ValueError(f"artifact digest binding mismatch: {artifact_id}:{key}")
            if kind == "ARTIFACT_SHA256_SEQUENCE":
                expected_sequence = [digest(package_root / f"{item}.json") for item in rule["artifact_ids"]]
                if observed != expected_sequence:
                    raise ValueError(f"artifact digest sequence mismatch: {artifact_id}:{key}")
            if kind == "EQUAL_PAYLOAD_FIELD" and observed != value["payload"][rule["field"]]:
                raise ValueError(f"payload field equality mismatch: {artifact_id}:{key}")
            if kind == "EQUAL_ARTIFACT_PAYLOAD_FIELD":
                reference_path = package_root / f"{rule['artifact_id']}.json"
                if not reference_path.is_file() or observed != json.loads(reference_path.read_bytes())["payload"][rule["field"]]:
                    raise ValueError(f"payload artifact equality mismatch: {artifact_id}:{key}")
        if value["artifact_id"] != artifact_id:
            raise ValueError(f"artifact identity mismatch: {artifact_id}")
        if package_attempt_id is None:
            package_attempt_id = value["package_attempt_id"]
            authorization_id = value["authorization_id"]
        if value["package_attempt_id"] != package_attempt_id or value["authorization_id"] != authorization_id:
            raise ValueError(f"cross-package artifact splice: {artifact_id}")
        expected_result = "FAILURE_EVIDENCE" if artifact_id.startswith("failure_terminal_capsule__") else "PASS"
        if value["result"] != expected_result:
            raise ValueError(f"artifact result mismatch: {artifact_id}")
        if artifact_id.startswith("failure_terminal_capsule__"):
            payload = value["payload"]
            if payload["atomic_terminalization"] != "SINGLE_CANONICAL_TEMP_WRITE_FSYNC_EXCLUSIVE_RENAME_DIRECTORY_FSYNC":
                raise ValueError("failure capsule is not atomic")
            if payload["attempted_closures"] != payload["expected_leases"] or payload["attempted_closures"] != payload["successful_closures"] + payload["duplicate_closures"] + payload["unknown_leases"]:
                raise ValueError("failure capsule closure accounting mismatch")
            if payload["expected_leases"] != len(payload["lease_ordinals"]) or payload["expected_leases"] != len(payload["lease_evidence_artifact_ids"]):
                raise ValueError("failure capsule lease census mismatch")
            expected_evidence = [f"checkpoint_access_event_{ordinal}" for ordinal in payload["lease_ordinals"]]
            if payload["lease_evidence_artifact_ids"] != expected_evidence or not set(expected_evidence).issubset(required):
                raise ValueError("failure capsule lease authority mismatch")
            if payload["live_leases_after_release"] != 0 or payload["event_04_executed"] is not False or payload["original_checkpoint_access"] != 0 or payload["active_generation"] != "NONE":
                raise ValueError("failure capsule safety mismatch")
        if artifact_id == "descriptor_lease_manifest":
            payload = value["payload"]
            if payload["lease_count"] != len(payload["lease_ids"]) or payload["lease_count"] != len(payload["descriptor_identities"]) or len(set(payload["lease_ids"])) != payload["lease_count"] or [item["lease_id"] for item in payload["descriptor_identities"]] != payload["lease_ids"]:
                raise ValueError("descriptor lease manifest semantic mismatch")
        if artifact_id in visited:
            return
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

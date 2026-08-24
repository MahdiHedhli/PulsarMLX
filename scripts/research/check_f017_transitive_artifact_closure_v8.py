#!/usr/bin/env python3
"""Recursively validate a constructed F017 V8 artifact package."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path


DESCRIPTOR_FIELDS = {
    "device",
    "inode",
    "mode",
    "size",
    "mtime_ns",
    "ctime_ns",
    "shard_ordinal",
    "role",
    "lease_id",
}
DESCRIPTOR_INTEGER_FIELDS = {
    "device",
    "inode",
    "mode",
    "size",
    "mtime_ns",
    "ctime_ns",
    "shard_ordinal",
}
LIVE_ID_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")
FORBIDDEN_LIVE_ID_MARKERS = ("INERT", "FIXTURE", "TEST", "SYNTHETIC")


def _validate_lease_id(value: object, context: str) -> str:
    if (type(value) is not str or LIVE_ID_PATTERN.fullmatch(value) is None
            or any(marker in value for marker in FORBIDDEN_LIVE_ID_MARKERS)):
        raise ValueError(f"lease id type or grammar mismatch: {context}")
    return value


def _validate_descriptor_identities(observed: object, rule: dict, context: str) -> list[dict]:
    """Validate untrusted descriptor bytes in type/census/semantic order."""
    if type(observed) is not list or len(observed) != rule["length"]:
        raise ValueError(f"descriptor identity array mismatch: {context}")
    if any(type(item) is not dict for item in observed):
        raise ValueError(f"descriptor identity entry type mismatch: {context}")
    entries: list[dict] = observed
    if any(set(item) != DESCRIPTOR_FIELDS for item in entries):
        raise ValueError(f"descriptor identity key census mismatch: {context}")
    for item in entries:
        if any(type(item[field]) is not int for field in DESCRIPTOR_INTEGER_FIELDS):
            raise ValueError(f"descriptor identity integer type mismatch: {context}")
        if any(item[field] < 0 for field in ("device", "inode", "size", "mtime_ns", "ctime_ns")):
            raise ValueError(f"descriptor identity integer range mismatch: {context}")
        mode = item["mode"]
        if mode < 0 or mode >= 2**16:
            raise ValueError(f"descriptor mode domain mismatch: {context}")
        # S_ISREG is deliberately unreachable until the portable mode_t domain
        # has been established.  Darwin raises OverflowError outside it.
        if not stat.S_ISREG(mode):
            raise ValueError(f"descriptor mode is not regular: {context}")
        if type(item["role"]) is not str or item["role"] != "GRAPH_PAYLOAD":
            raise ValueError(f"descriptor role mismatch: {context}")
        _validate_lease_id(item["lease_id"], context)
    if [item["shard_ordinal"] for item in entries] != rule["ordinals"]:
        raise ValueError(f"descriptor ordinal mismatch: {context}")
    if [item["size"] for item in entries] != rule["sizes"]:
        raise ValueError(f"descriptor size mismatch: {context}")
    if len({(item["device"], item["inode"]) for item in entries}) != len(entries):
        raise ValueError(f"descriptor identity duplicate mismatch: {context}")
    if len({item["device"] for item in entries}) != 1:
        raise ValueError(f"descriptor device-set mismatch: {context}")
    return entries


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_package(package_root: Path, terminal_id: str, required: set[str], roots: dict[str, dict[str, str]], dag: dict, schemas: dict, outcome: str) -> dict:
    visited: set[str] = set()
    maximum_depth = 0
    package_attempt_id: str | None = None
    authorization_id: str | None = None
    strict_rank_edges_validated = 0
    node_map = {item["artifact_id"]: item for item in dag["nodes"]}
    expected_roots = {key: item["sha256"] for key, item in roots.items()}
    if required != {artifact_id for artifact_id, node in node_map.items() if outcome in node["outcome_applicability"]}:
        raise ValueError("required set does not conform to DAG outcome applicability")
    actual_files = {path.stem for path in package_root.glob("*.json")}
    if actual_files != required:
        raise ValueError(f"package artifact census mismatch: missing={sorted(required-actual_files)} unexpected={sorted(actual_files-required)}")

    def walk(artifact_id: str, expected_sha: str | None, depth: int) -> None:
        nonlocal maximum_depth, package_attempt_id, authorization_id, strict_rank_edges_validated
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
            if kind == "NONEMPTY_STRING" and (type(observed) is not str or re.fullmatch(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?", observed) is None):
                raise ValueError(f"payload nonempty string mismatch: {artifact_id}:{key}")
            if kind == "SHA256" and (type(observed) is not str or len(observed) != 64 or any(character not in "0123456789abcdef" for character in observed)):
                raise ValueError(f"payload sha256 mismatch: {artifact_id}:{key}")
            if kind == "ENUM" and observed not in rule["values"]:
                raise ValueError(f"payload enum mismatch: {artifact_id}:{key}")
            if kind == "OUTCOME_CLASSIFICATION_ENUM":
                permitted = rule["success_values"] if outcome == "COMPLETE_SUCCESS" else rule["failure_values"]
                if observed not in permitted:
                    raise ValueError(f"payload outcome classification mismatch: {artifact_id}:{key}")
            if kind == "ARRAY_EXACT_LENGTH" and (type(observed) is not list or len(observed) != rule["length"]):
                raise ValueError(f"payload array length mismatch: {artifact_id}:{key}")
            if kind == "DESCRIPTOR_IDENTITY_ARRAY":
                _validate_descriptor_identities(observed, rule, f"{artifact_id}:{key}")
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
            if kind == "EQUAL_ENVELOPE_FIELD" and observed != value[rule["field"]]:
                raise ValueError(f"payload envelope equality mismatch: {artifact_id}:{key}")
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
            if (payload["attempted_closures"] != payload["successful_closures"] + payload["duplicate_closures"] + payload["unknown_leases"]
                    or payload["live_leases_after_release"] != payload["expected_leases"] - payload["successful_closures"] - payload["duplicate_closures"]):
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
            lease_ids = payload["lease_ids"]
            if type(lease_ids) is not list:
                raise ValueError("descriptor lease manifest lease-id collection type mismatch")
            checked_lease_ids = [_validate_lease_id(item, "descriptor_lease_manifest:lease_ids") for item in lease_ids]
            if (payload["lease_count"] != len(checked_lease_ids)
                    or payload["lease_count"] != len(payload["descriptor_identities"])
                    or len(set(checked_lease_ids)) != payload["lease_count"]
                    or [item["lease_id"] for item in payload["descriptor_identities"]] != checked_lease_ids):
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
            strict_rank_edges_validated += 1
            walk(dependency_id, dependency_sha, depth + 1)
        visited.add(artifact_id)

    walk(terminal_id, None, 1)
    missing = required - visited
    if missing:
        raise ValueError(f"required artifact outside terminal closure: {sorted(missing)}")
    identity_values = [authorization_id, package_attempt_id]
    identity_sources = [
        ("operator_approval", "operator_approval_id"),
        ("package_claim", "owner_nonce"),
        ("package_durable_start", "package_ledger_entry_id"),
        ("primary_durable_start", "event_id"),
        ("secondary_durable_start", "event_id"),
    ]
    for source_id, field in identity_sources:
        source_path = package_root / f"{source_id}.json"
        if source_path.is_file():
            identity_values.append(json.loads(source_path.read_bytes())["payload"][field])
    if any(type(item) is not str or re.fullmatch(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?", item) is None for item in identity_values) or len(set(identity_values)) != len(identity_values):
        raise ValueError("package identifier grammar or uniqueness mismatch")
    return {"result": "PASS", "terminal_id": terminal_id, "artifacts_reached": len(visited), "maximum_closure_depth": maximum_depth, "strict_rank_edges_validated": strict_rank_edges_validated}


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

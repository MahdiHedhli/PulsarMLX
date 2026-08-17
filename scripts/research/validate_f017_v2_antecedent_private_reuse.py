#!/usr/bin/env python3
"""Validate F017 private antecedent reuse without performing route arithmetic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-private-reuse-authorization-v1.json"
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-v2-antecedent-private-reuse-authorization-v1.schema.json"
PRIVATE_MANIFEST = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-private-manifest-v1.json"
RECOVERY_RESULT = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
EXACT_DESCRIPTOR = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-exact1-descriptor-v1.json"

HEAD = "6633362af67e76f25ad06fcdca7f079a48ccacf7"
PRIVATE_MANIFEST_SHA = "1007112a0642919321d0081e79bba12fe3809c456e79a22b9623d19689b78112"
RETENTION_MANIFEST_SHA = "bd3cc6c10faee0d8c8072000403bbef68354286515482a6b78869ab02be81e13"
RECOVERY_RESULT_SHA = "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a"
EXACT_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
CONSUMER_ID = "F017-DPREFIX-ROUTE-AMBIGUITY-PROPAGATION-ANALYTICAL-1"
ALLOWED_PURPOSE = "ROUTE_AMBIGUITY_PROPAGATION_ANALYTICAL_ONLY"


class ReuseValidationError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReuseValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ReuseValidationError(f"expected object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_symbolic_name(value: str) -> PurePosixPath:
    symbolic = PurePosixPath(value)
    if symbolic.is_absolute() or not symbolic.parts or ".." in symbolic.parts:
        raise ReuseValidationError(f"unsafe private-package-relative path: {value}")
    if symbolic.parts[0] != "antecedents":
        raise ReuseValidationError(f"artifact outside antecedent namespace: {value}")
    return symbolic


def expected_inventory(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = manifest.get("artifacts")
    if manifest.get("artifact_count") != 8 or not isinstance(artifacts, list) or len(artifacts) != 8:
        raise ReuseValidationError("source private manifest must contain exactly eight artifacts")
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in artifacts:
        name = str(item.get("symbolic_name", ""))
        _safe_symbolic_name(name)
        if name in names:
            raise ReuseValidationError(f"duplicate artifact name: {name}")
        names.add(name)
        if item.get("path_kind") != "private_package_relative":
            raise ReuseValidationError(f"invalid path kind: {name}")
        if item.get("immutable") is not True or item.get("read_only") is not True:
            raise ReuseValidationError(f"source retention is not immutable: {name}")
        result.append({
            "symbolic_name": name,
            "byte_length": int(item["byte_length"]),
            "sha256": str(item["sha256"]),
        })
    return result


def validate_schema_contract(schema: dict[str, Any]) -> None:
    required = {
        "schema", "schema_version", "authorization_id", "status",
        "authoritative_before_head", "schema_contract", "source", "consumer", "package",
        "isolation", "historical_immutability", "result",
    }
    if schema.get("additionalProperties") is not False:
        raise ReuseValidationError("schema must fail closed on extra top-level fields")
    if set(schema.get("required", [])) != required:
        raise ReuseValidationError("schema required fields mismatch")
    props = schema.get("properties", {})
    if props.get("result", {}).get("const") != "PRIVATE REUSE AUTHORIZED":
        raise ReuseValidationError("schema result is not frozen")
    package = props.get("package", {}).get("properties", {})
    if package.get("artifact_count", {}).get("const") != 8:
        raise ReuseValidationError("schema artifact count is not frozen")
    if package.get("total_bytes", {}).get("const") != 6_418_614:
        raise ReuseValidationError("schema byte total is not frozen")


def validate_authorization_document(document: dict[str, Any], root: Path = ROOT) -> None:
    schema = load_json(root / SCHEMA.relative_to(ROOT))
    validate_schema_contract(schema)
    manifest_path = root / PRIVATE_MANIFEST.relative_to(ROOT)
    result_path = root / RECOVERY_RESULT.relative_to(ROOT)
    ledger_path = root / LEDGER.relative_to(ROOT)
    exact_path = root / EXACT_DESCRIPTOR.relative_to(ROOT)
    if sha256_path(manifest_path) != PRIVATE_MANIFEST_SHA:
        raise ReuseValidationError("source private manifest identity mismatch")
    if sha256_path(result_path) != RECOVERY_RESULT_SHA:
        raise ReuseValidationError("source recovery result identity mismatch")
    manifest = load_json(manifest_path)
    if manifest.get("retention_manifest_sha256") != RETENTION_MANIFEST_SHA:
        raise ReuseValidationError("embedded retention manifest identity mismatch")
    ledger = load_json(ledger_path)
    if ledger.get("cumulative_tensor_payloads") != 139:
        raise ReuseValidationError("real-payload ledger changed")
    exact = load_json(exact_path)
    if exact.get("layer3", {}).get("sha256") != EXACT_SHA:
        raise ReuseValidationError("canonical exact state changed")
    inventory = expected_inventory(manifest)

    if document.get("schema") != "pulsarmlx.f017.v2-antecedent-private-reuse-authorization":
        raise ReuseValidationError("authorization schema mismatch")
    if document.get("schema_version") != "1.0.0":
        raise ReuseValidationError("authorization schema version mismatch")
    if document.get("authorization_id") != "F017-DPREFIX-ANTECEDENT-REUSE-1":
        raise ReuseValidationError("authorization identity mismatch")
    if document.get("status") != "AUTHORIZED_NOT_EXECUTED" or document.get("result") != "PRIVATE REUSE AUTHORIZED":
        raise ReuseValidationError("authorization state mismatch")
    if document.get("authoritative_before_head") != HEAD:
        raise ReuseValidationError("authoritative predecessor mismatch")
    schema_binding = document.get("schema_contract", {})
    if schema_binding.get("path") != str(SCHEMA.relative_to(ROOT)):
        raise ReuseValidationError("schema path binding mismatch")
    if schema_binding.get("sha256") != sha256_path(root / SCHEMA.relative_to(ROOT)):
        raise ReuseValidationError("schema SHA binding mismatch")

    source = document.get("source", {})
    if source != {
        "source_event_id": "M1-F0-V2-ANTECEDENT-RECOVERY",
        "source_event_immutable": True,
        "source_event_terminal": True,
        "private_manifest_sha256": PRIVATE_MANIFEST_SHA,
        "embedded_retention_manifest_sha256": RETENTION_MANIFEST_SHA,
        "recovery_result_sha256": RECOVERY_RESULT_SHA,
        "retained_bytes_classification": "ANTECEDENT_EVIDENCE_NOT_REGENERATED_CHECKPOINT_EVIDENCE",
    }:
        raise ReuseValidationError("source binding mismatch")

    consumer = document.get("consumer", {})
    if consumer.get("consumer_id") != CONSUMER_ID or consumer.get("allowed_purpose") != ALLOWED_PURPOSE:
        raise ReuseValidationError("consumer binding mismatch")
    required_false = (
        "may_modify_artifacts_in_place", "candidate_or_model_dispatch_permitted",
        "numerical_route_evaluation_performed",
    )
    if consumer.get("distinct_from_source_event") is not True or consumer.get("may_read_only_authorized_inventory") is not True:
        raise ReuseValidationError("independent consumer boundary missing")
    if any(consumer.get(field) is not False for field in required_false):
        raise ReuseValidationError("consumer authority is too broad")
    prohibited = set(consumer.get("prohibited_purposes", []))
    if not {"CHECKPOINT_ACCESS", "CANDIDATE_OR_MODEL_EXECUTION", "ROUTE_SCORE_COMPUTATION", "MEMBERSHIP_INEQUALITY_EVALUATION"} <= prohibited:
        raise ReuseValidationError("prohibited purpose surface incomplete")

    package = document.get("package", {})
    if package.get("artifact_count") != 8 or package.get("total_bytes") != sum(item["byte_length"] for item in inventory):
        raise ReuseValidationError("package census mismatch")
    if package.get("path_policy") != "PRIVATE_PACKAGE_RELATIVE_ONLY_NO_PUBLIC_MACHINE_LOCAL_PATH":
        raise ReuseValidationError("public path policy mismatch")
    if package.get("identity_path_independent") is not True or package.get("active_analytical_output_tree_created") is not False:
        raise ReuseValidationError("path-independent inactive consumer boundary mismatch")
    records = package.get("artifacts")
    if not isinstance(records, list) or len(records) != 8:
        raise ReuseValidationError("authorization inventory must contain eight records")
    if [record.get("symbolic_name") for record in records] != [item["symbolic_name"] for item in inventory]:
        raise ReuseValidationError("authorization inventory order mismatch")
    for expected, record in zip(inventory, records):
        _safe_symbolic_name(str(record.get("symbolic_name", "")))
        if record.get("byte_length") != expected["byte_length"]:
            raise ReuseValidationError(f"artifact size mismatch: {expected['symbolic_name']}")
        for field in ("expected_sha256", "before_sha256", "after_sha256"):
            if record.get(field) != expected["sha256"]:
                raise ReuseValidationError(f"artifact identity mismatch: {expected['symbolic_name']}:{field}")
        for field in ("regular_file", "read_only", "no_symlink_indirection", "no_writable_hard_link_alias", "no_mutable_active_output_copy"):
            if record.get(field) is not True:
                raise ReuseValidationError(f"immutability assertion missing: {expected['symbolic_name']}:{field}")
        if record.get("hard_link_count") != 1:
            raise ReuseValidationError(f"hard-link alias present: {expected['symbolic_name']}")

    isolation = document.get("isolation", {})
    expected_isolation = {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
        "real_payload_ledger_entry_created": False,
        "checkpoint_access_event_created": False,
        "restoration_event_created": False,
        "candidate_or_model_dispatches": 0,
        "route_calculations": 0,
    }
    if isolation != expected_isolation:
        raise ReuseValidationError("isolation or ledger contract mismatch")
    history = document.get("historical_immutability", {})
    if set(history) != {"DPREFIX_REAL_1", "DPREFIX_REAL_2", "DPREFIX_REAL_3"} or not all(str(value).startswith("UNCHANGED_") for value in history.values()):
        raise ReuseValidationError("historical verdict preservation mismatch")

    raw = json.dumps(document, sort_keys=True)
    if "/Users/" in raw or "file://" in raw or ".." in raw:
        raise ReuseValidationError("machine-local or escaping path leaked into public evidence")


def _assert_no_symlink_chain(root: Path, relative: PurePosixPath) -> Path:
    current = root
    if stat.S_ISLNK(root.lstat().st_mode):
        raise ReuseValidationError("symlink package root")
    for part in relative.parts:
        current = current / part
        if stat.S_ISLNK(current.lstat().st_mode):
            raise ReuseValidationError(f"symlink package component: {relative}")
    return current


def verify_private_artifacts(package_root: Path, inventory: list[dict[str, Any]]) -> dict[str, str]:
    package_root = package_root.absolute()
    if not package_root.is_dir():
        raise ReuseValidationError("private package root missing")
    hashes: dict[str, str] = {}
    for item in inventory:
        relative = _safe_symbolic_name(item["symbolic_name"])
        target = _assert_no_symlink_chain(package_root, relative)
        metadata = target.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ReuseValidationError(f"not a regular file: {relative}")
        if metadata.st_size != item["byte_length"]:
            raise ReuseValidationError(f"private artifact size mismatch: {relative}")
        if metadata.st_mode & 0o222:
            raise ReuseValidationError(f"private artifact is writable: {relative}")
        if metadata.st_nlink != 1:
            raise ReuseValidationError(f"private artifact has hard-link alias: {relative}")
        actual = sha256_path(target)
        if actual != item["sha256"]:
            raise ReuseValidationError(f"private artifact SHA mismatch: {relative}")
        hashes[str(relative)] = actual
    return hashes


def validate_private_reuse(package_root: Path, active_output_root: Path | None = None) -> None:
    manifest = load_json(PRIVATE_MANIFEST)
    inventory = expected_inventory(manifest)
    before = verify_private_artifacts(package_root, inventory)
    if active_output_root is not None and active_output_root.exists():
        source_inodes = {(package_root / item["symbolic_name"]).stat().st_ino for item in inventory}
        for directory, _, files in os.walk(active_output_root):
            for name in files:
                candidate = Path(directory) / name
                metadata = candidate.lstat()
                if metadata.st_ino in source_inodes or (metadata.st_mode & 0o222 and name in {Path(item["symbolic_name"]).name for item in inventory}):
                    raise ReuseValidationError("mutable or aliased artifact in active analytical output tree")
    after = verify_private_artifacts(package_root, inventory)
    if before != after:
        raise ReuseValidationError("private artifact changed during authorization validation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--private-package-root", type=Path)
    parser.add_argument("--active-output-root", type=Path, default=ROOT / "target/f017-dprefix-route-ambiguity-propagation-analytical-1")
    args = parser.parse_args()
    document = load_json(args.evidence)
    validate_authorization_document(document)
    if args.private_package_root is not None:
        validate_private_reuse(args.private_package_root, args.active_output_root)
    print("PRIVATE_REUSE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

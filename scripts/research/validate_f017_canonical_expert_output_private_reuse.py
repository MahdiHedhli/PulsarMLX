#!/usr/bin/env python3
"""Validate canonical expert-output reuse without aggregate or checkpoint access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-private-reuse-authorization-v1.json"
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-expert-output-private-reuse-authorization-v1.schema.json"
RECOVERY_RESULT = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-recovery-result-v1.json"
RECOVERY_REVIEW = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-recovery-evidence-review-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
CI_LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-ci-run-head-binding-ledger-v1.json"
AGGREGATE_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-weighted-moe-aggregate-perturbation-v1.json"

HEAD = "2653debd594ccfa09d32b2e036dd528d5fd6bcc1"
RECOVERY_RESULT_SHA = "d0a2d8b26fb3d20e22d6b93b7d5b95a779d639a06d53aaae58e8f8b0173b2c74"
RECOVERY_REVIEW_SHA = "d633f459a5436a82669b8677511789707da7dc55fc3de122f35cd431dac7fe8b"
PRIVATE_MANIFEST_SHA = "86d577020ad3e5bf6480b774536416145a154104eac643b21df644044a55e99e"
TERMINAL_SHA = "3553609f2250d74002693f7b1152baa93dba84de26f99571784354c13ae70dc2"
JOURNAL_SHA = "93bd69e8c7e6204c46ffb5335edf07097985047afe7f425a931d13d03bc5b66b"
LEDGER_SHA = "5120b94e2f304237fb2dcbe04dd04fa4ed3647a23b5119b12776dd02428a345d"
CANONICAL_INPUT_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
AGGREGATE_SHA = "ff1a15c29b79681458d74452c8c72dde9c9bf5eb44637d05a7e4ea9eb1525fac"
CONSUMER_ID = "F017-WEIGHTED-MOE-AGGREGATE-SAFETY-ANALYTICAL-1"
ALLOWED_PURPOSE = "WEIGHTED_MOE_AGGREGATE_SAFETY_EVALUATION_ONLY"
SELECTED_IDS = [250, 10, 237, 73, 62, 177, 218, 28]


class ExpertOutputReuseValidationError(ValueError):
    """Fail-closed reuse validation error."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExpertOutputReuseValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ExpertOutputReuseValidationError(f"expected object: {path.name}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExpertOutputReuseValidationError(message)


def safe_symbolic_name(value: str) -> PurePosixPath:
    symbolic = PurePosixPath(value)
    require(not symbolic.is_absolute() and bool(symbolic.parts) and ".." not in symbolic.parts,
            f"unsafe private-package-relative path: {value}")
    require(symbolic.parts[0] == "expert_outputs", f"artifact outside expert-output namespace: {value}")
    return symbolic


def expected_inventory(review: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = review.get("outputs")
    payloads = review.get("payloads")
    require(isinstance(outputs, list) and len(outputs) == 8, "source output census")
    require(isinstance(payloads, list) and len(payloads) == 24, "source weight census")
    require([item.get("expert_id") for item in outputs] == SELECTED_IDS, "source expert ordering")
    result: list[dict[str, Any]] = []
    for output in outputs:
        expert = output.get("expert_id")
        weights = {item.get("role"): item.get("packed_sha256") for item in payloads if item.get("expert_id") == expert}
        require(set(weights) == {"gate", "up", "down"}, f"source three-weight provenance: {expert}")
        require(output.get("shape") == [6144] and output.get("dtype") == "f32", f"source output surface: {expert}")
        require(output.get("byte_length") == 24_576, f"source output size: {expert}")
        require(output.get("canonical_input_sha256") == CANONICAL_INPUT_SHA, f"source canonical input: {expert}")
        result.append({
            "expert_id": expert,
            "symbolic_name": f"expert_outputs/expert_{expert}_down_output.bin",
            "dtype": "f32",
            "shape": [6144],
            "byte_length": 24_576,
            "sha256": output.get("sha256"),
            "canonical_input_sha256": CANONICAL_INPUT_SHA,
            "source_weight_packed_sha256": weights,
        })
    return result


def validate_source_evidence() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    require(sha256_path(RECOVERY_RESULT) == RECOVERY_RESULT_SHA, "recovery result identity")
    require(sha256_path(RECOVERY_REVIEW) == RECOVERY_REVIEW_SHA, "recovery review identity")
    require(sha256_path(LEDGER) == LEDGER_SHA, "real-payload ledger identity")
    require(sha256_path(AGGREGATE_CONTRACT) == AGGREGATE_SHA, "aggregate theorem identity")
    result = load_json(RECOVERY_RESULT)
    review = load_json(RECOVERY_REVIEW)
    ledger = load_json(LEDGER)
    aggregate = load_json(AGGREGATE_CONTRACT)
    require(result.get("classification") == "COMPLETE", "source recovery not complete")
    require(result.get("private_manifest_sha256") == PRIVATE_MANIFEST_SHA, "source manifest binding")
    require(result.get("two_process_exact_reproduction") is True, "source exact reproduction")
    require(review.get("classification") == "CANONICAL EXPERT OUTPUT RECOVERY COMPLETE", "source review classification")
    require(review.get("terminal_record_sha256") == TERMINAL_SHA, "source terminal binding")
    require(review.get("journal", {}).get("sha256") == JOURNAL_SHA, "source journal binding")
    require(review.get("aggregate_evaluation") is False, "source aggregate isolation")
    require(review.get("historical_immutability", {}).get("route_disposition") == "ROUTE NOT PROVEN INVARIANT",
            "source route disposition")
    require(ledger.get("cumulative_tensor_payloads") == 163, "current real-payload ledger")
    recovery_events = [item for item in ledger.get("events", [])
                       if item.get("attempt") == "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1-ATTEMPT-1"]
    require(len(recovery_events) == 1 and recovery_events[0].get("cumulative_tensor_payloads_after_event") == 163,
            "recovery ledger event")
    require(aggregate.get("acceptance") == {
        "max_absolute_error": 0.015625,
        "rmse": 0.0078125,
        "cosine_similarity_minimum": 0.9999,
        "mathematical_pass": "all three routed_aggregate intermediate Tier-B bounds pass",
        "engineering_headroom": 2.0,
        "engineering_pass": "mathematical pass and the minimum aggregate safety factor is at least 2",
        "additional_tolerances": [],
        "zero_perturbation_factor": "positive infinity",
        "undefined_cosine": "fail closed",
    }, "aggregate budgets or semantics changed")
    require(aggregate.get("semantics", {}).get("protected_surface") == "routed_aggregate", "aggregate surface")
    ci = load_json(CI_LEDGER)
    bindings = [item for item in ci.get("bindings", []) if item.get("run_id") == 32085496220]
    require(len(bindings) == 1 and bindings[0].get("head_sha") == "a682855291e9194ab27af6efc19f7bbb26b78751"
            and bindings[0].get("conclusion") == "success", "recovery CI closeout binding")
    inventory = expected_inventory(review)
    require(result.get("output_sha256_by_expert") == {str(item["expert_id"]): item["sha256"] for item in inventory},
            "public result output identities")
    return result, review, inventory


def validate_schema_contract(schema: dict[str, Any]) -> None:
    required = {
        "schema", "schema_version", "authorization_id", "status", "authoritative_before_head",
        "schema_contract", "source", "consumer", "aggregate_theorem", "package", "isolation",
        "historical_immutability", "result",
    }
    require(schema.get("additionalProperties") is False, "schema top-level closure")
    require(set(schema.get("required", [])) == required, "schema required fields")
    props = schema.get("properties", {})
    require(props.get("result", {}).get("const") == "CANONICAL EXPERT OUTPUT REUSE AUTHORIZED", "schema result")
    package = props.get("package", {}).get("properties", {})
    require(package.get("artifact_count", {}).get("const") == 8, "schema artifact count")
    require(package.get("total_bytes", {}).get("const") == 196_608, "schema byte count")


def validate_authorization_document(document: dict[str, Any], root: Path = ROOT) -> None:
    _, review, inventory = validate_source_evidence()
    schema = load_json(root / SCHEMA.relative_to(ROOT))
    validate_schema_contract(schema)
    require(document.get("schema") == "pulsarmlx.f017.canonical-expert-output-private-reuse-authorization",
            "authorization schema")
    require(document.get("schema_version") == "1.0.0", "authorization schema version")
    require(document.get("authorization_id") == "F017-CANONICAL-EXPERT-OUTPUT-REUSE-1", "authorization identity")
    require(document.get("status") == "AUTHORIZED_NOT_EVALUATED", "authorization state")
    require(document.get("authoritative_before_head") == HEAD, "authoritative predecessor")
    require(document.get("result") == "CANONICAL EXPERT OUTPUT REUSE AUTHORIZED", "authorization result")
    schema_binding = document.get("schema_contract", {})
    require(schema_binding.get("path") == SCHEMA.relative_to(ROOT).as_posix(), "schema path")
    require(schema_binding.get("sha256") == sha256_path(root / SCHEMA.relative_to(ROOT)), "schema identity")

    source = document.get("source", {})
    expected_source = {
        "event_id": "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1",
        "attempt_id": "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1-ATTEMPT-1",
        "terminal": True,
        "immutable": True,
        "recovery_result_sha256": RECOVERY_RESULT_SHA,
        "evidence_review_sha256": RECOVERY_REVIEW_SHA,
        "private_package_manifest_sha256": PRIVATE_MANIFEST_SHA,
        "terminal_record_sha256": TERMINAL_SHA,
        "journal_sha256": JOURNAL_SHA,
        "ledger_evidence_sha256": LEDGER_SHA,
        "canonical_input_sha256": CANONICAL_INPUT_SHA,
        "reproducibility_class": "PERSISTED_AUTHORITY",
        "production_mechanism": "EXACT_CLASS_STRICT_F32_FIXED_ORDER_NO_BLAS_TWO_PROCESS_REPRODUCED",
        "historical_event_reopened": False,
    }
    require(source == expected_source, "source authority binding")

    consumer = document.get("consumer", {})
    require(consumer.get("consumer_id") == CONSUMER_ID, "consumer identity")
    require(consumer.get("allowed_purpose") == ALLOWED_PURPOSE, "consumer purpose")
    require(consumer.get("distinct_from_source_event") is True
            and consumer.get("may_read_only_authorized_inventory") is True, "independent read-only consumer")
    for field in ("may_modify_artifacts_in_place", "checkpoint_access_permitted",
                  "packed_expert_weight_access_permitted", "candidate_or_model_dispatch_permitted",
                  "aggregate_evaluation_performed"):
        require(consumer.get(field) is False, f"consumer authority too broad: {field}")
    prohibited = set(consumer.get("prohibited_purposes", []))
    require({"CHECKPOINT_ACCESS", "CHECKPOINT_SHARD_OPEN", "CHECKPOINT_PAYLOAD_READ",
             "PACKED_EXPERT_WEIGHT_ACCESS", "CANDIDATE_OR_MODEL_EXECUTION",
             "REPRESENTATIVE_M1_F0_EXECUTION"} <= prohibited, "prohibited purposes")

    theorem = document.get("aggregate_theorem", {})
    require(theorem == {
        "path": AGGREGATE_CONTRACT.relative_to(ROOT).as_posix(),
        "sha256": AGGREGATE_SHA,
        "protected_surface": "routed_aggregate",
        "budgets": {"max_absolute_error": 0.015625, "rmse": 0.0078125,
                    "cosine_similarity_minimum": 0.9999},
        "evaluation_performed": False,
        "weighted_products_computed": False,
    }, "aggregate theorem binding")

    package = document.get("package", {})
    require(package.get("artifact_count") == 8 and package.get("total_bytes") == 196_608, "package census")
    require(package.get("path_policy") == "PRIVATE_PACKAGE_RELATIVE_ONLY_NO_PUBLIC_MACHINE_LOCAL_PATH",
            "package path policy")
    require(package.get("identity_path_independent") is True
            and package.get("active_analytical_output_tree_created") is False, "inactive path-independent package")
    records = package.get("artifacts")
    require(isinstance(records, list) and len(records) == 8, "authorization artifact records")
    require([item.get("expert_id") for item in records] == SELECTED_IDS, "atomic expert ordering")
    require(len(set(item.get("expert_id") for item in records)) == 8, "duplicate expert ID")
    for expected, record in zip(inventory, records):
        safe_symbolic_name(str(record.get("symbolic_name", "")))
        for field in ("expert_id", "symbolic_name", "dtype", "shape", "byte_length",
                      "canonical_input_sha256", "source_weight_packed_sha256"):
            require(record.get(field) == expected[field], f"artifact provenance: {expected['expert_id']}:{field}")
        for field in ("expected_sha256", "before_sha256", "after_sha256"):
            require(record.get(field) == expected["sha256"], f"artifact identity: {expected['expert_id']}:{field}")
        for field in ("regular_file", "read_only", "no_symlink_indirection", "no_writable_hard_link_alias",
                      "no_mutable_active_output_copy"):
            require(record.get(field) is True, f"artifact immutability: {expected['expert_id']}:{field}")
        require(record.get("hard_link_count") == 1, f"artifact hard-link count: {expected['expert_id']}")

    require(document.get("isolation") == {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_payload_ledger_before": 163,
        "real_payload_ledger_after": 163,
        "real_payload_ledger_entry_created": False,
        "checkpoint_access_event_created": False,
        "source_recovery_event_reopened": False,
        "candidate_or_model_dispatches": 0,
        "aggregate_evaluations": 0,
        "weighted_products_computed": 0,
    }, "isolation or ledger contract")
    require(document.get("historical_immutability") == review.get("historical_immutability"),
            "historical immutability")
    raw = json.dumps(document, sort_keys=True)
    require("/Users/" not in raw and "file://" not in raw and ".." not in raw, "private path leak")


def assert_no_symlink_chain(root: Path, relative: PurePosixPath) -> Path:
    current = root
    require(current.exists() and not stat.S_ISLNK(current.lstat().st_mode), "symlink package root")
    for part in relative.parts:
        current = current / part
        require(current.exists() and not stat.S_ISLNK(current.lstat().st_mode), f"symlink package component: {relative}")
    return current


def verify_private_artifacts(package_root: Path, inventory: list[dict[str, Any]]) -> dict[int, str]:
    package_root = package_root.absolute()
    require(package_root.is_dir(), "private package root missing")
    hashes: dict[int, str] = {}
    for item in inventory:
        relative = safe_symbolic_name(item["symbolic_name"])
        target = assert_no_symlink_chain(package_root, relative)
        metadata = target.stat()
        require(stat.S_ISREG(metadata.st_mode), f"not a regular file: {relative}")
        require(metadata.st_size == item["byte_length"], f"private artifact size: {relative}")
        require(not metadata.st_mode & 0o222, f"private artifact writable: {relative}")
        require(metadata.st_nlink == 1, f"private artifact hard-link alias: {relative}")
        actual = sha256_path(target)
        require(actual == item["sha256"], f"private artifact SHA: {relative}")
        hashes[item["expert_id"]] = actual
    return hashes


def validate_private_reuse(private_root: Path, active_output_root: Path | None = None) -> dict[int, str]:
    _, review, inventory = validate_source_evidence()
    package_root = private_root / "recovery-package"
    manifest_path = package_root / "manifest.json"
    terminal_path = private_root / "event-state/terminal.json"
    require(sha256_path(manifest_path) == PRIVATE_MANIFEST_SHA, "private manifest identity")
    require(sha256_path(terminal_path) == TERMINAL_SHA, "private terminal identity")
    manifest = load_json(manifest_path)
    terminal = load_json(terminal_path)
    require(terminal.get("journal_digest") == JOURNAL_SHA, "private journal binding")
    journal_paths = sorted((private_root / "event-state/journal").glob("*.json"))
    require(len(journal_paths) == 24, "private journal census")
    require(canonical_sha256([load_json(path) for path in journal_paths]) == JOURNAL_SHA, "private journal identity")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == 8, "private manifest artifact census")
    require([item.get("expert_id") for item in artifacts] == SELECTED_IDS, "private manifest expert ordering")
    for expected, item in zip(inventory, artifacts):
        require(item.get("symbolic_path") == expected["symbolic_name"], f"private symbolic path: {expected['expert_id']}")
        require(item.get("sha256") == expected["sha256"], f"private manifest SHA: {expected['expert_id']}")
        require(item.get("shape") == [6144] and item.get("dtype") == "f32"
                and item.get("byte_length") == 24_576, f"private manifest surface: {expected['expert_id']}")
        require(item.get("canonical_input_sha256") == CANONICAL_INPUT_SHA, f"private canonical input: {expected['expert_id']}")
        require(item.get("packed_sha256_by_role") == expected["source_weight_packed_sha256"],
                f"private weight provenance: {expected['expert_id']}")
        require(item.get("immutable") is True and item.get("read_only") is True,
                f"private manifest immutability: {expected['expert_id']}")
    before = verify_private_artifacts(package_root, inventory)
    if active_output_root is not None and active_output_root.exists():
        source_inodes = {(package_root / item["symbolic_name"]).stat().st_ino for item in inventory}
        names = {Path(item["symbolic_name"]).name for item in inventory}
        for directory, _, files in os.walk(active_output_root):
            for name in files:
                candidate = Path(directory) / name
                metadata = candidate.lstat()
                require(metadata.st_ino not in source_inodes, "private artifact aliased into analytical output tree")
                require(not (metadata.st_mode & 0o222 and name in names), "writable expert-output copy in analytical tree")
    after = verify_private_artifacts(package_root, inventory)
    require(before == after, "private artifact changed during authorization")
    return after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--active-output-root", type=Path,
                        default=ROOT / "target/f017-weighted-moe-aggregate-safety-analytical-1")
    args = parser.parse_args()
    document = load_json(args.evidence)
    validate_authorization_document(document)
    if args.private_root is not None:
        validate_private_reuse(args.private_root, args.active_output_root)
    print("CANONICAL_EXPERT_OUTPUT_REUSE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

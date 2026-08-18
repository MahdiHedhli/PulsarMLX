#!/usr/bin/env python3
"""Validate shared-expert output reuse without aggregate or checkpoint access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-output-private-reuse-authorization-v1.json"
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-shared-expert-output-private-reuse-authorization-v1.schema.json"
RECOVERY_RESULT = ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-recovery-result-v1.json"
RECOVERY_REVIEW = ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-recovery-evidence-review-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
CI_LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-ci-run-head-binding-ledger-v1.json"
COMPLETE_LAYER_V2 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-complete-layer-aggregate-acceptance-v2.json"
ROUTED_REUSE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-private-reuse-authorization-v1.json"
ROUTED_EVALUATION = ROOT / "docs/architecture/reviews/evidence/f017-weighted-moe-aggregate-safety-evaluation-v1.json"

HEAD = "58b3577f0ad8793a981b1345c5012cf2bf6f08e5"
RECOVERY_RESULT_CANONICAL_SHA = "c245c7d73dc85ce576351a9a6c8904626ac912c8d2f404f0e301fe6d221275fb"
RECOVERY_RESULT_FILE_SHA = "971c371ce7b1220f612f941c76c0fe359f122c8ff6f3643711fab946d11eff24"
RECOVERY_REVIEW_SHA = "7107e690c4ad3ad951166e7045fcf4d1e034a12b8e94f8bc9de2a68d5551bc8a"
PRIVATE_MANIFEST_SHA = "f04707514ddb90fd0e70fb4aeb0fc471d5ee0f448ac4c0763b984fe050f57116"
TERMINAL_SHA = "89a8a24707227e130b6595503620e578f37e7d3e00646eb4adb6190520b1c4c9"
JOURNAL_SHA = "3920d0304078e9bd039c4a9155497996ced54c79c0e2f07e255200a586585ed3"
LEDGER_SHA = "c68be19f2840dea612e8b20ff2933751800555c80ae66fcfbbff02086bbe18c0"
OUTPUT_SHA = "01dbd9ac75091fcd452ac9bb1bc2479ccdebc0bc7ac46d79285ff45d70e5928d"
CANONICAL_INPUT_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
COMPLETE_LAYER_V2_SHA = "13896ac22c03d7354c25f4d182de828b44df0d7239dd7e269175f69d597209fe"
ROUTED_REUSE_SHA = "b370d3c3dd938eeadd18f34fabab89077319b979b994b97ffa33afddf2bffa28"
ROUTED_EVALUATION_SHA = "672884e0c217600f9104d7a4d6fdd27a87e0a73fac686044de86461af98781e7"
ROUTED_NOMINAL_SHA = "5a30a81b6e10b126ac22a3be991e5f5c6486372068888f699625b684eb85fc70"
ROUTED_INTERSECTION_SHA = "adbbbef090c4d10acc80d0216cc82b5a8dbe299dad4baad1a0d957f661762a50"
CONSUMER_ID = "F017-COMPLETE-LAYER-AGGREGATE-V2-ANALYTICAL-1"
ALLOWED_PURPOSE = "COMPLETE_LAYER_AGGREGATE_V2_EVALUATION_ONLY"
SYMBOLIC_NAME = "outputs/canonical_shared_expert_output.bin"


class SharedOutputReuseValidationError(ValueError):
    """Fail-closed shared-output reuse validation error."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SharedOutputReuseValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise SharedOutputReuseValidationError(f"expected object: {path.name}")
    return value


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SharedOutputReuseValidationError(message)


def safe_symbolic_name(value: str) -> PurePosixPath:
    symbolic = PurePosixPath(value)
    require(not symbolic.is_absolute() and bool(symbolic.parts) and ".." not in symbolic.parts,
            f"unsafe private-package-relative path: {value}")
    require(symbolic.parts[0] == "outputs", f"artifact outside output namespace: {value}")
    return symbolic


def validate_source_evidence() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    require(sha256_path(RECOVERY_RESULT) == RECOVERY_RESULT_FILE_SHA, "recovery result file identity")
    result = load_json(RECOVERY_RESULT)
    require(canonical_sha256(result) == RECOVERY_RESULT_CANONICAL_SHA, "recovery result canonical identity")
    require(sha256_path(RECOVERY_REVIEW) == RECOVERY_REVIEW_SHA, "recovery review identity")
    require(sha256_path(LEDGER) == LEDGER_SHA, "ledger evidence identity")
    require(sha256_path(COMPLETE_LAYER_V2) == COMPLETE_LAYER_V2_SHA, "complete-layer v2 identity")
    require(sha256_path(ROUTED_REUSE) == ROUTED_REUSE_SHA, "routed reuse identity")
    require(sha256_path(ROUTED_EVALUATION) == ROUTED_EVALUATION_SHA, "routed evaluation identity")
    review = load_json(RECOVERY_REVIEW)
    ledger = load_json(LEDGER)
    complete = load_json(COMPLETE_LAYER_V2)
    routed = load_json(ROUTED_EVALUATION)

    require(result.get("classification") == "COMPLETE", "source recovery not complete")
    output = result.get("output", {})
    require(output.get("output_sha256") == OUTPUT_SHA, "source output identity")
    require(output.get("private_manifest_sha256") == PRIVATE_MANIFEST_SHA, "source manifest identity")
    require(output.get("exact_reproduction") is True and output.get("fresh_processes") == 2,
            "source exact reproduction")
    require(review.get("classification") == "CANONICAL SHARED EXPERT RECOVERY COMPLETE",
            "source review classification")
    require(review.get("terminal_record_sha256") == TERMINAL_SHA, "source terminal identity")
    require(review.get("journal", {}).get("sha256") == JOURNAL_SHA, "source journal identity")
    require(review.get("shared_output") == {
        "byte_length": 24_576, "dtype": "f32", "immutable": True, "read_only": True,
        "sha256": OUTPUT_SHA, "shape": [6144],
    }, "source shared-output surface")
    require({item.get("role"): item.get("packed_sha256") for item in review.get("payloads", [])} == {
        "gate": "750b148ada60dbbfc9bd3b2d4c2bbfa70f304c34328b025f912626dea70c1414",
        "up": "13727df9b9129906538081fcef3a23d4db8ba37235bb96605c46b3ff683c59fe",
        "down": "48c5469bf71d1c5291f806a79388901f094d5fd7adaec5c25c0f3391b0d67083",
    }, "source three-weight provenance")
    require(review.get("complete_layer_v2_evaluation") is False, "source evaluation isolation")
    require(ledger.get("cumulative_tensor_payloads") == 166, "real-payload ledger")
    events = [item for item in ledger.get("events", []) if item.get("attempt") ==
              "F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1-ATTEMPT-1"]
    require(len(events) == 1 and events[0].get("cumulative_tensor_payloads_after_event") == 166,
            "shared recovery ledger event")

    ci = load_json(CI_LEDGER)
    bindings = [item for item in ci.get("bindings", []) if item.get("run_id") == 32148033478]
    require(len(bindings) == 1 and bindings[0].get("head_sha") ==
            "2b85b39a8554fecaa117dd5dde8a0363112cdccb" and
            bindings[0].get("conclusion") == "success", "shared recovery CI closeout")

    require(complete.get("surface", {}).get("formula") == "L=f32(f64(R)+(M+f64(S)))",
            "complete-layer formula")
    require(complete.get("acceptance", {}).get("max_absolute_error") == 0.0625 and
            complete.get("acceptance", {}).get("rmse") == 0.03125 and
            complete.get("acceptance", {}).get("cosine_similarity_minimum") == 0.999,
            "complete-layer thresholds")
    require(complete.get("shared_expert_ambiguity", {}).get("point_rule") ==
            "delta_S=0 for this routing-only ambiguity proof after the canonical shared output passes recovery and reuse authorization",
            "shared point-authority rule")
    require(routed.get("nominal_aggregate", {}).get("canonical_le_f64_sha256") == ROUTED_NOMINAL_SHA,
            "routed nominal identity")
    require(routed.get("enclosures", {}).get("sound_intersection", {}).get(
            "canonical_le_f64_interval_sha256") == ROUTED_INTERSECTION_SHA,
            "routed intersection identity")
    return result, review, routed


def validate_schema_contract(schema: dict[str, Any]) -> None:
    required = {
        "schema", "schema_version", "authorization_id", "status", "authoritative_before_head",
        "schema_contract", "source", "artifact", "authority_classification", "consumer",
        "complete_layer_v2", "routed_dependencies", "isolation", "historical_immutability", "result",
    }
    require(schema.get("additionalProperties") is False, "schema top-level closure")
    require(set(schema.get("required", [])) == required, "schema required fields")
    props = schema.get("properties", {})
    require(props.get("result", {}).get("const") ==
            "CANONICAL SHARED EXPERT OUTPUT REUSE AUTHORIZED", "schema result")
    artifact = props.get("artifact", {}).get("properties", {})
    require(artifact.get("byte_length", {}).get("const") == 24_576, "schema byte count")
    require(artifact.get("expected_sha256", {}).get("const") == OUTPUT_SHA, "schema output identity")


def validate_authorization_document(document: dict[str, Any], root: Path = ROOT) -> None:
    _, review, routed = validate_source_evidence()
    schema_path = root / SCHEMA.relative_to(ROOT)
    schema = load_json(schema_path)
    validate_schema_contract(schema)
    require(document.get("schema") ==
            "pulsarmlx.f017.canonical-shared-expert-output-private-reuse-authorization",
            "authorization schema")
    require(document.get("schema_version") == "1.0.0", "authorization schema version")
    require(document.get("authorization_id") == "F017-CANONICAL-SHARED-EXPERT-OUTPUT-REUSE-1",
            "authorization identity")
    require(document.get("status") == "AUTHORIZED_NOT_EVALUATED", "authorization status")
    require(document.get("authoritative_before_head") == HEAD, "authoritative predecessor")
    require(document.get("result") == "CANONICAL SHARED EXPERT OUTPUT REUSE AUTHORIZED",
            "authorization result")
    require(document.get("schema_contract") == {
        "path": SCHEMA.relative_to(ROOT).as_posix(), "sha256": sha256_path(schema_path),
    }, "schema binding")

    require(document.get("source") == {
        "event_id": "F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1",
        "attempt_id": "F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1-ATTEMPT-1",
        "terminal": True,
        "immutable": True,
        "recovery_result_canonical_sha256": RECOVERY_RESULT_CANONICAL_SHA,
        "recovery_result_file_sha256": RECOVERY_RESULT_FILE_SHA,
        "evidence_review_sha256": RECOVERY_REVIEW_SHA,
        "private_package_manifest_sha256": PRIVATE_MANIFEST_SHA,
        "terminal_record_sha256": TERMINAL_SHA,
        "journal_sha256": JOURNAL_SHA,
        "ledger_evidence_sha256": LEDGER_SHA,
        "canonical_input_sha256": CANONICAL_INPUT_SHA,
        "two_process_exact_reproduction": True,
        "historical_event_reopened": False,
    }, "source authority binding")

    artifact = document.get("artifact", {})
    safe_symbolic_name(str(artifact.get("symbolic_name", "")))
    expected_artifact = {
        "symbolic_name": SYMBOLIC_NAME, "dtype": "f32", "shape": [6144],
        "byte_length": 24_576, "expected_sha256": OUTPUT_SHA, "before_sha256": OUTPUT_SHA,
        "after_sha256": OUTPUT_SHA, "canonical_input_sha256": CANONICAL_INPUT_SHA,
        "source_weight_packed_sha256": {
            "gate": "750b148ada60dbbfc9bd3b2d4c2bbfa70f304c34328b025f912626dea70c1414",
            "up": "13727df9b9129906538081fcef3a23d4db8ba37235bb96605c46b3ff683c59fe",
            "down": "48c5469bf71d1c5291f806a79388901f094d5fd7adaec5c25c0f3391b0d67083",
        },
        "regular_file": True, "read_only": True, "no_symlink_indirection": True,
        "hard_link_count": 1, "no_writable_hard_link_alias": True,
        "no_mutable_active_output_copy": True,
    }
    require(artifact == expected_artifact, "artifact authority binding")

    require(document.get("authority_classification") == {
        "reproducibility_class": "PERSISTED_AUTHORITY",
        "production_mechanism": "EXACT_CLASS_STRICT_F32_FIXED_ORDER_NO_BLAS_TWO_PROCESS_REPRODUCED",
        "comparison_rule": "persisted object SHA-256 exact equality",
        "delta_s_rule": "delta_S=0",
        "delta_s_scope": "ROUTING_WEIGHT_ONLY_AMBIGUITY_PROOF_WITH_THIS_AUTHORIZED_CANONICAL_POINT_ARTIFACT",
        "generalization_permitted": False,
    }, "authority classification")

    consumer = document.get("consumer", {})
    require(consumer.get("consumer_id") == CONSUMER_ID, "consumer identity")
    require(consumer.get("allowed_purpose") == ALLOWED_PURPOSE, "consumer purpose")
    require(consumer.get("execution_state") == "AUTHORIZED_NOT_EVALUATED", "consumer state")
    require(consumer.get("allowed_inputs") == [
        "DPREFIX_EXACT_1_RESIDUAL", "CANONICAL_SHARED_EXPERT_OUTPUT",
        "AUTHORIZED_EIGHT_CANONICAL_ROUTED_EXPERT_OUTPUTS", "BANKED_EXACT_ROUTING_WEIGHTS",
        "BANKED_ROUTING_WEIGHT_INTERVALS", "FROZEN_ROUTED_PERTURBATION_ENCLOSURE",
        "COMPLETE_LAYER_AGGREGATE_ACCEPTANCE_V2",
    ], "consumer input inventory")
    for field in ("checkpoint_access_permitted", "candidate_execution_permitted",
                  "representative_m1_f0_permitted", "new_route_propagation_permitted",
                  "payload_decoding_permitted", "aggregate_evaluation_performed"):
        require(consumer.get(field) is False, f"consumer authority too broad: {field}")
    require(set(consumer.get("prohibited_purposes", [])) == {
        "CHECKPOINT_ACCESS", "CHECKPOINT_SHARD_OPEN", "CHECKPOINT_PAYLOAD_READ",
        "PAYLOAD_DECODING", "NEW_ROUTE_PROPAGATION", "CANDIDATE_OR_MODEL_EXECUTION",
        "REPRESENTATIVE_M1_F0_EXECUTION", "M1_F_EXECUTION", "M1_G_EXECUTION", "P1_EXECUTION",
    }, "consumer prohibited purposes")

    require(document.get("complete_layer_v2") == {
        "path": COMPLETE_LAYER_V2.relative_to(ROOT).as_posix(), "sha256": COMPLETE_LAYER_V2_SHA,
        "formula": "L=f32(f64(DPREFIX-EXACT-1)+(routed_aggregate+f64(canonical_shared_output)))",
        "thresholds": {"max_absolute": 0.0625, "rmse": 0.03125, "cosine_minimum": 0.999},
        "shared_point_rule": "delta_S=0 for this routing-weight-only ambiguity proof",
        "evaluation_performed": False, "metrics_computed": False,
    }, "complete-layer v2 binding")

    expected_outputs = routed.get("inputs", {}).get("expert_output_sha256_by_id")
    require(document.get("routed_dependencies") == {
        "expert_output_reuse_authorization_sha256": ROUTED_REUSE_SHA,
        "routed_evaluation_sha256": ROUTED_EVALUATION_SHA,
        "route_evidence_sha256": "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4",
        "weight_qualification_evidence_sha256": "834eefb7e0f127e12768285097dc3601135c1c1ff8ef0e871d65f59af1bc6b1f",
        "selected_expert_ids": [250, 10, 237, 73, 62, 177, 218, 28],
        "canonical_expert_output_sha256_by_id": expected_outputs,
        "exact_routing_weights_canonical_sha256": "635bae156717bfa43238fb17a0ebdfed65c6c6d462db7878cdc2120712354b3f",
        "routing_weight_intervals_canonical_sha256": "1b3aba25bf30047f66ee2ef03f6f0371a123998b10ac853416ffe13de2a47a0b",
        "joint_selected_weight_sum_interval_canonical_sha256": "c6b4dd4f5b149510c211ed99b04b985dc127abba5d80c80ba2d4414b81d10c15",
        "routed_nominal_aggregate_sha256": ROUTED_NOMINAL_SHA,
        "routed_sound_intersection_sha256": ROUTED_INTERSECTION_SHA,
        "recomputed": False,
    }, "routed dependency binding")

    require(document.get("isolation") == {
        "checkpoint_reads": 0, "shard_opens": 0, "payload_reads": 0,
        "real_payload_ledger_before": 166, "real_payload_ledger_after": 166,
        "real_payload_ledger_entry_created": False, "source_recovery_event_reopened": False,
        "candidate_or_model_dispatches": 0, "aggregate_evaluations": 0,
        "complete_layer_metrics_computed": 0,
    }, "isolation or ledger contract")
    require(document.get("historical_immutability") == {
        "REAL_1": "REJECTED_UNCHANGED", "REAL_2": "REJECTED_UNCHANGED",
        "REAL_3": "REJECTED_UNCHANGED", "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "membership": "1984_OF_1984_PASS_UNCHANGED",
        "coefficient_qualification": "0_OF_8_FAIL_UNCHANGED",
        "routed_aggregate_v1": "FAIL_UNCHANGED",
        "complete_layer_v2": "FROZEN_NOT_EVALUATED",
        "route_disposition": "ROUTE NOT PROVEN INVARIANT", "real_payload_ledger": 166,
    }, "historical immutability")
    require(document.get("historical_immutability", {}).get("route_disposition") ==
            review.get("historical_immutability", {}).get("route_disposition"),
            "source route disposition")
    raw = json.dumps(document, sort_keys=True)
    require("/Users/" not in raw and "file://" not in raw and ".." not in raw, "private path leak")


def assert_no_symlink_chain(root: Path, relative: PurePosixPath) -> Path:
    current = root
    require(current.exists() and not stat.S_ISLNK(current.lstat().st_mode), "symlink package root")
    for part in relative.parts:
        current = current / part
        require(current.exists() and not stat.S_ISLNK(current.lstat().st_mode),
                f"symlink package component: {relative}")
    return current


def verify_private_artifact(
    package_root: Path, *, expected_sha256: str = OUTPUT_SHA, expected_size: int = 24_576
) -> tuple[str, int]:
    target = assert_no_symlink_chain(package_root.absolute(), safe_symbolic_name(SYMBOLIC_NAME))
    metadata = target.stat()
    require(stat.S_ISREG(metadata.st_mode), "shared output is not a regular file")
    require(metadata.st_size == expected_size, "shared output byte size")
    require(not metadata.st_mode & 0o222, "shared output writable")
    require(metadata.st_nlink == 1, "shared output hard-link alias")
    actual = sha256_path(target)
    require(actual == expected_sha256, "shared output SHA")
    return actual, metadata.st_ino


def validate_private_reuse(private_root: Path, active_output_root: Path | None = None) -> str:
    validate_source_evidence()
    package_root = private_root / "package"
    manifest_path = package_root / "manifest.json"
    terminal_path = private_root / "state/terminal.json"
    require(sha256_path(manifest_path) == PRIVATE_MANIFEST_SHA, "private manifest identity")
    require(sha256_path(terminal_path) == TERMINAL_SHA, "private terminal identity")
    manifest = load_json(manifest_path)
    terminal = load_json(terminal_path)
    require(terminal.get("journal_digest") == JOURNAL_SHA, "private journal binding")
    journal_paths = sorted((private_root / "state/journal").glob("*.json"))
    require(len(journal_paths) == 3, "private journal census")
    require(canonical_sha256([load_json(path) for path in journal_paths]) == JOURNAL_SHA,
            "private journal identity")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list), "private manifest artifact list")
    packed = {item.get("role"): item for item in artifacts if item.get("kind") == "retained_packed_weight"}
    require(set(packed) == {"gate", "up", "down"}, "private packed-weight census")
    for role, expected_sha, expected_size in (
        ("gate", "750b148ada60dbbfc9bd3b2d4c2bbfa70f304c34328b025f912626dea70c1414", 8_650_752),
        ("up", "13727df9b9129906538081fcef3a23d4db8ba37235bb96605c46b3ff683c59fe", 8_650_752),
        ("down", "48c5469bf71d1c5291f806a79388901f094d5fd7adaec5c25c0f3391b0d67083", 10_321_920),
    ):
        require(packed[role].get("sha256") == expected_sha and
                packed[role].get("byte_length") == expected_size and
                packed[role].get("immutable") is True and packed[role].get("read_only") is True,
                f"private packed-weight provenance: {role}")
    outputs = [item for item in artifacts if item.get("symbolic_path") == SYMBOLIC_NAME]
    require(len(outputs) == 1, "private shared-output census")
    require(outputs[0] == {
        "byte_length": 24_576, "canonical_input_sha256": CANONICAL_INPUT_SHA, "dtype": "f32",
        "immutable": True, "read_only": True, "sha256": OUTPUT_SHA, "shape": [6144],
        "symbolic_path": SYMBOLIC_NAME,
    }, "private shared-output manifest binding")
    before, inode = verify_private_artifact(package_root)
    if active_output_root is not None and active_output_root.exists():
        for directory, _, files in os.walk(active_output_root):
            for name in files:
                candidate = Path(directory) / name
                metadata = candidate.lstat()
                require(metadata.st_ino != inode, "shared output aliased into analytical output tree")
                require(not (metadata.st_mode & 0o222 and name == Path(SYMBOLIC_NAME).name),
                        "writable shared-output copy in analytical tree")
    after, _ = verify_private_artifact(package_root)
    require(before == OUTPUT_SHA == after, "shared output changed during authorization")
    return after


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--active-output-root", type=Path,
                        default=ROOT / "target/f017-complete-layer-aggregate-v2-analytical-1")
    args = parser.parse_args()
    document = load_json(args.evidence)
    validate_authorization_document(document)
    if args.private_root is not None:
        validate_private_reuse(args.private_root, args.active_output_root)
    print("CANONICAL_SHARED_EXPERT_OUTPUT_REUSE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

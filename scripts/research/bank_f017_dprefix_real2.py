#!/usr/bin/env python3
"""Bank DPREFIX-REAL-2 from the immutable private runtime products.

This command is deliberately checkpoint-free.  It only validates and copies
descriptors from ``.pulsarmlx-local/dprefix-real-2``; it never resolves or
opens a GGUF shard.  The terminal disposition is fail closed when a reviewed
PASS-required runtime field was not persisted by the bound execution surface.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
PRIVATE = ROOT / ".pulsarmlx-local/dprefix-real-2"

ATTEMPT = "DPREFIX-REAL-2"
EXECUTION_HEAD = "acab5d4347c6af25ac3acb7bfa6e7b5dbe1257e7"
CHECKPOINT_REVISION = "abc55e72527792c6e77069c99b4cb7de16fa9f23"
CHECKPOINT_SET = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
CATALOG = "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0"
TENSOR_MAP = "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
PACKED_BYTES = 1_431_263_232

RAW_PATH = EVIDENCE / "f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json"
PACKED_DESCRIPTOR_PATH = EVIDENCE / "f017-dprefix-real2-packed-package-descriptor-v1.json"
ORACLE_DESCRIPTOR_PATH = EVIDENCE / "f017-dprefix-real2-oracle-retention-descriptor-v1.json"
CANDIDATE_DESCRIPTOR_PATH = EVIDENCE / "f017-dprefix-real2-candidate-retention-descriptor-v1.json"
ANALYTICAL_DESCRIPTOR_PATH = EVIDENCE / "f017-dprefix-real2-analytical-route-planning-descriptor-v1.json"
ATTEMPT_PATH = EVIDENCE / "f017-dense-prefix-attempt-ledger-v10.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {path}: {key}")
            value[key] = item
        return value

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(payload)


def readonly(path: Path) -> bool:
    return path.is_file() and not bool(path.stat().st_mode & 0o222)


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def private_binding(path: Path, symbolic: str) -> dict[str, Any]:
    return {
        "symbolic_private_path": symbolic,
        "sha256": digest(path),
        "bytes": path.stat().st_size,
        "read_only": readonly(path),
    }


def validate_private() -> tuple[dict[str, Any], ...]:
    terminal_path = PRIVATE / "terminal-evidence.json"
    journal_path = PRIVATE / "execution-start-and-read-journal.json"
    packed_manifest_path = PRIVATE / "material/packed/manifest.json"
    oracle_manifest_path = PRIVATE / "oracle-primary/manifest.json"
    candidate_manifest_path = PRIVATE / "candidate-primary/manifest.json"
    candidate_evidence_path = PRIVATE / "candidate-evidence.json"
    terminal = load(terminal_path)
    journal = load(journal_path)
    packed = load(packed_manifest_path)
    oracle = load(oracle_manifest_path)
    candidate_retention = load(candidate_manifest_path)
    candidate = load(candidate_evidence_path)
    expected = load(EVIDENCE / "f017-dprefix-real2-all40-packed-identity-manifest-v1.json")

    assert terminal["attempt_id"] == journal["attempt_id"] == packed["attempt_id"] == ATTEMPT
    assert terminal["terminal_class"] == "DENSE_PREFIX_EXACT_TIER_B_QUALIFIED"
    assert journal["consumed"] and journal["checkpoint_accessed"]
    assert journal["ledger_before"] == 99 and journal["ledger_after"] == 139
    assert len(journal["records"]) == 40
    assert sum(item["actual_length"] for item in journal["records"]) == PACKED_BYTES
    assert terminal["access"]["payloads"] == terminal["checkpoint_access"] == 40
    assert terminal["access"]["packed_bytes"] == PACKED_BYTES
    assert packed["payloads"] == len(packed["entries"]) == 40
    assert packed["logical_packed_bytes"] == PACKED_BYTES
    expected_hashes = {item["tensor"]: item["packed_sha256"] for item in expected["entries"]}
    actual_hashes = {item["tensor"]: item["packed_sha256"] for item in journal["records"]}
    assert actual_hashes == expected_hashes
    assert [item["ordinal"] for item in journal["records"]] == list(range(40))
    assert [item["ordinal"] for item in packed["entries"]] == list(range(40))

    for item in packed["entries"]:
        artifact = PRIVATE / "material/packed" / item["artifact"]["symbolic_path"]
        assert artifact.stat().st_size == item["artifact"]["bytes"] == item["logical_packed_bytes"]
        assert digest(artifact) == item["packed_sha256"] == item["artifact"]["sha256"]
        assert readonly(artifact) and item["immutable"] and item["read_only"]
    assert sum(item["artifact"]["bytes"] for item in packed["entries"]) == PACKED_BYTES

    for manifest, directory in ((oracle, "oracle-primary"), (candidate_retention, "candidate-primary")):
        for item in manifest["artifacts"].values():
            artifact = PRIVATE / directory / item["symbolic_path"]
            assert artifact.stat().st_size == item["bytes"] == 24_576
            assert digest(artifact) == item["sha256"]
            assert readonly(artifact) and item["immutable"] and item["read_only"]
            assert item["shape"] == [6144] and item["count"] == 6144 and item["dtype"] == "f32"

    assert oracle["persisted_before_candidate_spawn"] and oracle["fsync_complete"]
    assert terminal["oracle"]["rehash"] == "PASS"
    assert candidate["repeats"] == 10 and candidate["deterministic"]
    assert len(candidate["stage_hashes"]) == 10
    assert all(item == candidate["stage_hashes"][0] for item in candidate["stage_hashes"])
    assert candidate["identity_confirmations"] == {"Q4_K": True, "Q6_K": True}
    assert candidate["input_decoded_hashes"]["token_embd.weight"] == "e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1"
    assert candidate["input_decoded_hashes"]["blk.0.ffn_down.weight"] == "ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a"
    assert len(terminal["numerical_surfaces"]) == 8
    assert all(item["pass"] for item in terminal["numerical_surfaces"])
    assert candidate["dispatch"]["fallback"] == candidate["dispatch"]["backend_errors"] == 0

    # These fields were required for overall PASS by the released instruction,
    # but the bound success-path structs did not persist them.  They cannot be
    # reconstructed from hashes after the process has exited.
    assert "lifecycle_reconciled" not in candidate
    assert "lifecycle" not in terminal
    assert "host_copies" not in candidate["dispatch"]

    for path in (terminal_path, packed_manifest_path, oracle_manifest_path,
                 candidate_manifest_path, candidate_evidence_path):
        assert readonly(path)
    return terminal, journal, packed, oracle, candidate_retention, candidate


def bank() -> dict[str, str]:
    terminal, journal, packed, oracle, candidate_retention, candidate = validate_private()
    config_path = EVIDENCE / "f017-dense-prefix-execution-config-v6.json"
    auth_path = EVIDENCE / "f017-dense-prefix-authorization-binding-v5.json"
    attempt_v9_path = EVIDENCE / "f017-dense-prefix-attempt-ledger-v9.json"
    inventory_path = EVIDENCE / "f017-dense-prefix-40-read-allowlist-v1.json"
    prompt_path = EVIDENCE / "f017-m1f-minus1-prompt-token-package-v1.json"
    packed_gate_path = EVIDENCE / "f017-dprefix-real2-all40-packed-identity-manifest-v1.json"
    terminal_path = PRIVATE / "terminal-evidence.json"
    journal_path = PRIVATE / "execution-start-and-read-journal.json"
    packed_manifest_path = PRIVATE / "material/packed/manifest.json"
    oracle_manifest_path = PRIVATE / "oracle-primary/manifest.json"
    candidate_manifest_path = PRIVATE / "candidate-primary/manifest.json"
    candidate_evidence_path = PRIVATE / "candidate-evidence.json"

    packed_descriptor = {
        "schema": "pulsarmlx.f017.dprefix-real2-packed-package-descriptor",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "checkpoint_set_sha256": CHECKPOINT_SET,
        "package_identity": digest(packed_manifest_path),
        "manifest_sha256": digest(packed_manifest_path),
        "symbolic_private_package": "f017-private/dprefix-real-2/packed-payloads",
        "payloads": 40,
        "packed_bytes": PACKED_BYTES,
        "immutable": True,
        "read_only": True,
        "cross_event_reuse": "REQUIRES_SEPARATE_EXPLICIT_AUTHORIZATION",
        "entries": packed["entries"],
    }
    write(PACKED_DESCRIPTOR_PATH, packed_descriptor)

    oracle_descriptor = {
        "schema": "pulsarmlx.f017.dprefix-real2-oracle-retention-descriptor",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "package_identity": digest(oracle_manifest_path),
        "manifest_sha256": digest(oracle_manifest_path),
        "symbolic_private_package": "f017-private/dprefix-real-2/oracle-primary",
        "persisted_before_candidate_spawn": True,
        "fsync_complete": True,
        "post_candidate_rehash": "PASS",
        "immutable": True,
        "read_only": True,
        "artifacts": oracle["artifacts"],
        "downstream_policy": "ANALYTICAL_ROUTE_PLANNING_ONLY",
    }
    write(ORACLE_DESCRIPTOR_PATH, oracle_descriptor)

    candidate_descriptor = {
        "schema": "pulsarmlx.f017.dprefix-real2-candidate-retention-descriptor",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "package_identity": digest(candidate_manifest_path),
        "manifest_sha256": digest(candidate_manifest_path),
        "symbolic_private_package": "f017-private/dprefix-real-2/candidate-primary",
        "immutable": True,
        "read_only": True,
        "artifacts": candidate_retention["artifacts"],
    }
    write(CANDIDATE_DESCRIPTOR_PATH, candidate_descriptor)

    expected = load(packed_gate_path)
    expected_hashes = {item["tensor"]: item["packed_sha256"] for item in expected["entries"]}
    decoded = candidate["input_decoded_hashes"]
    numerical = terminal["numerical_surfaces"]
    dispatch = candidate["dispatch"]
    raw = {
        "schema": "pulsarmlx.f017.dprefix-real2-terminal-evidence",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "verdict": "REJECTED",
        "terminal_class": "EVIDENCE_VALIDATION",
        "reason_code": "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING",
        "reason": "the bound runtime numerically qualified all eight Tier-B surfaces but did not persist success-path lifecycle reconciliation or actual host-copy accounting required for terminal PASS",
        "release": {
            "verdict": "GO — EXECUTE DPREFIX-REAL-2",
            "release_head": EXECUTION_HEAD,
            "execution_head": EXECUTION_HEAD,
        },
        "bindings": {
            "config_v6": binding(config_path),
            "authorization_v5": binding(auth_path),
            "candidate_binary_sha256": journal["candidate_sha256"],
            "candidate_source_manifest_sha256": "8424c709ce252d64adc74775b2e6b6a5ec099e6e687b238f7c70fd0dd868b5d9",
            "orchestrator_sha256": journal["orchestrator_sha256"],
            "orchestrator_source_manifest_sha256": "330cc73b6cda9a2d86ace0a6a47ffdbf2addda044a76d1c96617fd162c35f395",
            "real_shape_contract_sha256": digest(CONTRACTS / "f017-dprefix-real-shape-contract-v1.json"),
            "packed_identity_manifest": binding(packed_gate_path),
            "packed_retention_contract_sha256": digest(CONTRACTS / "f017-dprefix-packed-payload-retention-v1.json"),
            "oracle_persist_contract_sha256": digest(CONTRACTS / "f017-dprefix-oracle-persist-on-finalize-v1.json"),
            "hardened_terminal_banker_sha256": digest(CONTRACTS / "f017-dprefix-terminal-failure-banker-v1.json"),
            "oracle_package_sha256": "9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b",
            "metric_engine_sha256": "cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738",
            "tier_b_sha256": "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a",
            "inventory": binding(inventory_path),
            "prompt_package": binding(prompt_path),
        },
        "checkpoint": {
            "revision": CHECKPOINT_REVISION,
            "checkpoint_set_sha256": CHECKPOINT_SET,
            "catalog_sha256": CATALOG,
            "tensor_map_sha256": TENSOR_MAP,
            "mount_admission": "PASSED_REVIEWED_SIX_REGULAR_FILES_NO_SYMLINK_SUBSTITUTION",
        },
        "access": {
            "shard_opens": 1,
            "positional_reads": 40,
            "payloads": 40,
            "packed_bytes": PACKED_BYTES,
            "all_40_packed_identity_exact": True,
            "read_records": journal["records"],
        },
        "identity_confirmations": {
            "packed_manifest_expected_count": 40,
            "packed_manifest_actual_count": 40,
            "all_40_packed_exact": True,
            "Q4_K": {
                "tensor": "token_embd.weight",
                "expected_packed_sha256": expected_hashes["token_embd.weight"],
                "actual_packed_sha256": candidate["input_packed_hashes"]["token_embd.weight"],
                "expected_decoded_sha256": "e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1",
                "actual_decoded_sha256": decoded["token_embd.weight"],
                "exact": True,
            },
            "Q6_K": {
                "tensor": "blk.0.ffn_down.weight",
                "expected_packed_sha256": expected_hashes["blk.0.ffn_down.weight"],
                "actual_packed_sha256": candidate["input_packed_hashes"]["blk.0.ffn_down.weight"],
                "expected_decoded_sha256": "ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a",
                "actual_decoded_sha256": decoded["blk.0.ffn_down.weight"],
                "exact": True,
            },
        },
        "decoded_identities": decoded,
        "packed_retention": {
            "descriptor": binding(PACKED_DESCRIPTOR_PATH),
            "private_manifest_sha256": digest(packed_manifest_path),
            "private_package_identity": digest(packed_manifest_path),
            "retained_bytes": PACKED_BYTES,
            "payloads": 40,
            "immutable": True,
            "read_only": True,
            "rehash": "PASS",
        },
        "oracle": {
            "finalized": True,
            "persisted_before_candidate": True,
            "fsync_complete": True,
            "post_candidate_rehash": "PASS",
            "descriptor": binding(ORACLE_DESCRIPTOR_PATH),
            "layer_2_output": oracle["artifacts"]["layer_2_output"],
            "layer_3_entry": oracle["artifacts"]["layer_3_entry"],
        },
        "candidate": {
            "launched": True,
            "completion_derived_from_bound_orchestrator_success_branch": True,
            "result": candidate["result"],
            "root_cause_regression": "PASS",
            "native_shape_checks": "ALL_27_CONTRACTIONS_REACHED_SUCCESSFUL_COMPLETION",
            "repeats_completed": candidate["repeats"],
            "repeat_determinism": candidate["deterministic"],
            "stage_hashes": candidate["stage_hashes"],
            "retention_descriptor": binding(CANDIDATE_DESCRIPTOR_PATH),
        },
        "numerical_surfaces": numerical,
        "numerical_result": {
            "all_required_surfaces_present": len(numerical) == 8,
            "all_required_surfaces_pass": all(item["pass"] for item in numerical),
            "classification": "ALL_EIGHT_REAL_TIER_B_SURFACES_QUALIFIED",
        },
        "runtime_accounting": {
            "native_matvecs": dispatch["native_matvecs"],
            "cpu_rms_norm": dispatch["cpu_rms_norm"],
            "cpu_attention": dispatch["cpu_attention"],
            "cpu_activation": dispatch["cpu_activation"],
            "synchronizations": dispatch["synchronizations"],
            "readbacks": dispatch["readbacks"],
            "fallback": dispatch["fallback"],
            "backend_errors": dispatch["backend_errors"],
            "host_copies": "NOT_RECORDED_BY_BOUND_SUCCESS_PATH",
        },
        "lifecycle": {
            "candidate_process_completed": True,
            "complete_success_path_reconciliation": "NOT_RECORDED_BY_BOUND_SUCCESS_PATH",
            "terminal_pass_requirement_satisfied": False,
        },
        "evidence_validation": {
            "private_terminal_sha256": digest(terminal_path),
            "execution_start_and_read_journal_sha256": digest(journal_path),
            "candidate_evidence_sha256": digest(candidate_evidence_path),
            "missing_pass_required_fields": [
                "success_path_lifecycle_reconciliation",
                "actual_host_copy_count",
            ],
            "raw_immutable_runtime_evidence_sufficient_to_reconstruct": False,
            "checkpoint_free_repair_possible_without_recomputation": False,
            "result": "FAIL_CLOSED",
        },
        "state": {
            "authorized": True,
            "consumed": True,
            "executed": True,
            "checkpoint_accessed": True,
            "payloads_read": 40,
            "packed_bytes_read": PACKED_BYTES,
            "ledger_before": 99,
            "ledger_after": 139,
            "automatic_retry": False,
            "automatic_m1f0_continuation": False,
        },
        "private_runtime_sources": {
            "terminal": private_binding(terminal_path, "f017-private/dprefix-real-2/terminal-evidence.json"),
            "journal": private_binding(journal_path, "f017-private/dprefix-real-2/execution-start-and-read-journal.json"),
            "packed_manifest": private_binding(packed_manifest_path, "f017-private/dprefix-real-2/packed-payloads/manifest.json"),
            "oracle_manifest": private_binding(oracle_manifest_path, "f017-private/dprefix-real-2/oracle-primary/manifest.json"),
            "candidate_manifest": private_binding(candidate_manifest_path, "f017-private/dprefix-real-2/candidate-primary/manifest.json"),
            "candidate_evidence": private_binding(candidate_evidence_path, "f017-private/dprefix-real-2/candidate-evidence.json"),
        },
        "downstream": {
            "oracle_state_policy": "ANALYTICAL_ROUTE_PLANNING_ONLY",
            "representative_m1f0": "NOT_AUTHORIZED_NOT_EXECUTED",
            "automatic_continuation": False,
        },
    }
    write(RAW_PATH, raw)
    raw_sha = digest(RAW_PATH)

    analytical = {
        "schema": "pulsarmlx.f017.dprefix-real2-analytical-route-planning-descriptor",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "source_evidence": {"path": str(RAW_PATH.relative_to(ROOT)), "sha256": raw_sha},
        "oracle_layer_3_sha256": oracle["artifacts"]["layer_3_entry"]["sha256"],
        "oracle_retention_manifest_sha256": digest(oracle_manifest_path),
        "policy": "ANALYTICAL_ROUTE_PLANNING_ONLY",
        "representative_m1f0": "NOT_AUTHORIZED_NOT_EXECUTED",
        "checkpoint_access_authorized": False,
        "execution_authorized": False,
    }
    write(ANALYTICAL_DESCRIPTOR_PATH, analytical)

    attempt_v9 = load(attempt_v9_path)
    attempt = {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger",
        "schema_version": "10.0.0",
        "append_only_predecessor": binding(attempt_v9_path),
        "prior_terminal_attempt": attempt_v9["prior_terminal_attempt"],
        "current_state": {
            "attempt_id": ATTEMPT,
            "authorized": True,
            "consumed": True,
            "executed": True,
            "checkpoint_accessed": True,
            "terminal_class": "EVIDENCE_VALIDATION",
            "reason_code": "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING",
            "evidence_path": str(RAW_PATH.relative_to(ROOT)),
            "evidence_sha256": raw_sha,
            "payloads_read": 40,
            "packed_bytes_read": PACKED_BYTES,
            "ledger_before": 99,
            "ledger_after": 139,
            "ledger": 139,
            "numerical_classification": "ALL_EIGHT_REAL_TIER_B_SURFACES_QUALIFIED",
            "packed_package_sha256": digest(packed_manifest_path),
            "oracle_layer_3_sha256": oracle["artifacts"]["layer_3_entry"]["sha256"],
            "automatic_retry": False,
            "automatic_m1f0_continuation": False,
        },
        "history": [
            {
                "event": "REAL2_RELEASE_AUTHORIZATION",
                "config_sha256": digest(config_path),
                "authorization_sha256": digest(auth_path),
                "release_head": EXECUTION_HEAD,
            },
            {
                "event": "REAL2_SINGLE_CONSUMED_EXECUTION_TERMINAL_REJECTION",
                "terminal_class": "EVIDENCE_VALIDATION",
                "reason_code": "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING",
                "numerical_classification": "ALL_EIGHT_REAL_TIER_B_SURFACES_QUALIFIED",
                "consumed": True,
                "executed": True,
                "checkpoint_accessed": True,
                "payloads_read": 40,
                "packed_bytes_read": PACKED_BYTES,
                "ledger_before": 99,
                "ledger_after": 139,
                "evidence_sha256": raw_sha,
                "automatic_retry": False,
                "automatic_m1f0_continuation": False,
            },
        ],
        "checkpoint_access": 40,
        "ledger": 139,
    }
    write(ATTEMPT_PATH, attempt)
    return {
        "raw_evidence_sha256": raw_sha,
        "packed_descriptor_sha256": digest(PACKED_DESCRIPTOR_PATH),
        "oracle_descriptor_sha256": digest(ORACLE_DESCRIPTOR_PATH),
        "candidate_descriptor_sha256": digest(CANDIDATE_DESCRIPTOR_PATH),
        "analytical_descriptor_sha256": digest(ANALYTICAL_DESCRIPTOR_PATH),
        "attempt_ledger_sha256": digest(ATTEMPT_PATH),
    }


if __name__ == "__main__":
    print(json.dumps(bank(), indent=2, sort_keys=True))

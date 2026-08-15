#!/usr/bin/env python3
"""Checkpoint-free Q4 state reconciliation and Q6 authorization preparation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "docs/architecture/reviews/evidence"
CONTRACT_DIR = ROOT / "specs/017-rust-native-inference-runtime/contracts"

Q4_EVIDENCE = EVIDENCE_DIR / "f017-q4-k-real-byte-qualification-attempt-1-v1.json"
Q4_LEDGER_V2 = EVIDENCE_DIR / "f017-q4-k-attempt-ledger-v2.json"
Q4_LEDGER_V3 = EVIDENCE_DIR / "f017-q4-k-attempt-ledger-v3.json"
REAL_LEDGER = EVIDENCE_DIR / "f017-real-payload-access-ledger-v1.json"
Q6_DEFECT = EVIDENCE_DIR / "f017-q6-k-decoder-defect-v1.json"
Q6_FORMAT = CONTRACT_DIR / "f017-q6-k-format-contract-v1.json"
Q6_HANDOFF = CONTRACT_DIR / "f017-q6-k-qualification-handoff-v3.json"
Q6_CONFIG = EVIDENCE_DIR / "f017-q6-k-execution-config-v1.json"
Q6_BINDING = EVIDENCE_DIR / "f017-q6-k-authorization-binding-v1.json"
Q6_ATTEMPT = EVIDENCE_DIR / "f017-q6-k-attempt-ledger-v1.json"
Q6_SCHEMA = CONTRACT_DIR / "f017-q6-k-evidence-v1.schema.json"
TRIAD_EVIDENCE = EVIDENCE_DIR / "f017-q4-k-state-triad-reconciliation-v1.json"
PACKET_CONTRACT = CONTRACT_DIR / "f017-real-event-packet-provenance-v1.json"
CI_LEDGER = EVIDENCE_DIR / "f017-ci-run-head-binding-ledger-v1.json"

Q4_EVIDENCE_SHA = "035ad4351406c24c65667a5322f1ffae71589f046a5ba3f591b8a4e3f6140994"
Q4_EVIDENCE_COMMIT = "45f27650a019d8d10aa48032fe7a78b81e767ab4"
Q4_ATTEMPT_ID = "Q4K-REAL-1"
Q6_ATTEMPT_ID = "Q6K-REAL-1"
CHECKPOINT_SHA = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
CATALOG_SHA = "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0"
TENSOR_MAP_SHA = "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
CORRECTED_Q6_SHA = "1d285e58d5b5c55368191cccb881a56dc78560d7e2541e8d94b5217cd382548d"
Q6_TARGET = {
    "tensor_name": "blk.0.ffn_down.weight",
    "shard_ordinal": 2,
    "offset": 1_203_482_464,
    "packed_length": 61_931_520,
    "gguf_shape": [12_288, 6_144],
    "logical_shape": [6_144, 12_288],
    "quantization": "Q6_K",
    "elements": 75_497_472,
    "elements_per_block": 256,
    "blocks": 294_912,
    "packed_bytes_per_block": 210,
    "packed_row_width": 10_080,
    "decoded_f32_bytes": 301_989_888,
    "catalog_entry_sha256": "cf149dbb546c312948bf77c4064d9f48ef8021d5ad4d0a3e9a9f414d9678bc54",
}
Q6_DECODERS = [
    {
        "name": "A_corrected_python_grouped",
        "language": "Python",
        "path": "scripts/research/ggml_kquants.py",
        "symbol": "dequantize_row_q6_k",
        "source_sha256": CORRECTED_Q6_SHA,
        "provenance": "corrected independent grouped implementation",
        "imports_another_decoder": False,
        "generated_real_expected_output": False,
    },
    {
        "name": "B_python_index_driven_spec",
        "language": "Python",
        "path": "scripts/research/f017_m1f_minus1_dense_prefix_prep.py",
        "symbol": "decode_q6_k_independent",
        "source_sha256": "cfac692461a8772bf7c0d1605b78ab88c43ac593c4431236453e0c8902f51501",
        "implementation_sha256": "999f228465cc2c805da456413872f327d1437e8651f772a555b94f06363f1b76",
        "provenance": "index-driven specification derivation",
        "imports_another_decoder": False,
        "generated_real_expected_output": False,
    },
    {
        "name": "C_rust_reference",
        "language": "Rust",
        "path": "crates/quant/src/q6_k_ref.rs",
        "symbol": "decode_q6_k_matrix",
        "source_sha256": "a4d308ef1aa874865e668002a8911d8247247dd490e301018f730aeb06ab35fd",
        "provenance": "independent Rust row/matrix reference",
        "imports_another_decoder": False,
        "generated_real_expected_output": False,
    },
]


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return file_sha256(path)


def _attempt_record(ledger: dict[str, Any], attempt_id: str) -> dict[str, Any]:
    matches = [row for row in ledger.get("attempts", []) if row.get("attempt_id") == attempt_id]
    require(len(matches) == 1, f"{attempt_id} attempt record count")
    return matches[0]


def validate_q4_triad_objects(
    attempt_ledger: dict[str, Any],
    real_ledger: dict[str, Any],
    evidence: dict[str, Any] | None,
    evidence_sha: str | None,
) -> str:
    require(evidence is not None and evidence_sha is not None, "terminal evidence artifact absent")
    require(evidence_sha == Q4_EVIDENCE_SHA, "terminal evidence SHA mismatch")
    attempt = _attempt_record(attempt_ledger, Q4_ATTEMPT_ID)
    events = [row for row in real_ledger.get("events", []) if row.get("attempt") == Q4_ATTEMPT_ID]
    require(len(events) == 1, "Q4 real-payload event count")
    event = events[0]
    raw_attempt = evidence.get("attempt", {})
    raw_ledger = evidence.get("ledger", {})
    require(raw_attempt.get("attempt_id") == Q4_ATTEMPT_ID, "attempt ID mismatch")
    require(attempt.get("attempt_id") == raw_attempt.get("attempt_id"), "attempt ID disagreement")
    for field in ("authorized", "consumed", "executed", "checkpoint_accessed"):
        require(attempt.get(field) is raw_attempt.get(field), f"{field} disagreement")
        require(attempt.get(field) is True, f"Q4 {field} must be true")
    require(raw_attempt.get("terminal_class") == "EXACT_REAL_BYTE_QUALIFIED", "raw terminal class")
    require(attempt.get("terminal_classification") == raw_attempt.get("terminal_class"), "terminal classification mismatch")
    require(attempt.get("evidence_artifact_sha256") == evidence_sha, "attempt evidence SHA mismatch")
    require(event.get("evidence", {}).get("sha256") == evidence_sha, "payload event evidence SHA mismatch")
    require(attempt.get("ledger_before") == raw_ledger.get("before") == 57, "ledger before mismatch")
    require(attempt.get("ledger_after") == raw_ledger.get("after") == 58, "ledger after mismatch")
    require(raw_ledger.get("actual_payloads") == 1, "raw payload count")
    require(event.get("tensor_payload_count") == 1, "payload event count")
    require(event.get("cumulative_tensor_payloads_after_event") == 58, "payload event cumulative count")
    require(real_ledger.get("cumulative_tensor_payloads") == 58, "real-payload ledger cumulative count")
    require(event.get("consumed_attempt") is True, "payload event consumed state")
    require(event.get("tensor_symbolic_names") == ["token_embd.weight"], "payload event target")
    require(attempt.get("automatic_retry") is False, "automatic retry")
    require(attempt.get("automatic_q6_continuation") is False, "automatic Q6 continuation")
    require(attempt.get("automatic_dense_prefix_continuation") is False, "automatic dense-prefix continuation")
    return "Q4_K STATE TRIAD RECONCILED"


def validate_q4_triad(root: Path = ROOT) -> str:
    evidence_path = root / Q4_EVIDENCE.relative_to(ROOT)
    evidence = load_json(evidence_path) if evidence_path.exists() else None
    return validate_q4_triad_objects(
        load_json(root / Q4_LEDGER_V3.relative_to(ROOT)),
        load_json(root / REAL_LEDGER.relative_to(ROOT)),
        evidence,
        file_sha256(evidence_path) if evidence is not None else None,
    )


def q4_ledger_v3() -> dict[str, Any]:
    prior = load_json(Q4_LEDGER_V2)
    require(validate_q4_triad_objects(prior, load_json(REAL_LEDGER), load_json(Q4_EVIDENCE), file_sha256(Q4_EVIDENCE)) == "Q4_K STATE TRIAD RECONCILED", "v2 triad")
    prior_attempt = _attempt_record(prior, Q4_ATTEMPT_ID)
    reconciled_attempt = {
        "attempt_id": prior_attempt["attempt_id"],
        "gate": prior_attempt["gate"],
        "authorized": prior_attempt["authorized"],
        "consumed": prior_attempt["consumed"],
        "executed": prior_attempt["executed"],
        "checkpoint_accessed": prior_attempt["checkpoint_accessed"],
        "reviewed_control_head": prior_attempt["authorization_head"],
        "execution_head": prior_attempt["execution_head"],
        "control_artifact_sha256": prior_attempt["authorization_artifact_sha256"],
        "execution_config_sha256": prior_attempt["execution_config_sha256"],
        "control_binding_sha256": prior_attempt["authorization_binding_sha256"],
        "handoff_sha256": prior_attempt["handoff_sha256"],
        "terminal_classification": prior_attempt["terminal_classification"],
        "packed_sha256": prior_attempt["packed_sha256"],
        "evidence_artifact_sha256": prior_attempt["evidence_artifact_sha256"],
        "ledger_before": prior_attempt["ledger_before"],
        "ledger_after": prior_attempt["ledger_after"],
        "automatic_retry": prior_attempt["automatic_retry"],
        "automatic_q6_continuation": prior_attempt["automatic_q6_continuation"],
        "automatic_dense_prefix_continuation": prior_attempt["automatic_dense_prefix_continuation"],
    }
    return {
        "schema": "pulsarmlx.f017.q4-k-attempt-ledger",
        "schema_version": "3.0.0",
        "predecessor": {
            "path": Q4_LEDGER_V2.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(Q4_LEDGER_V2),
            "status": prior["status"],
        },
        "append_only_reconciliation": {
            "kind": "CROSS_ARTIFACT_STATE_RECONCILIATION",
            "evidence_path": Q4_EVIDENCE.relative_to(ROOT).as_posix(),
            "evidence_sha256": Q4_EVIDENCE_SHA,
            "evidence_commit": Q4_EVIDENCE_COMMIT,
            "real_payload_ledger_path": REAL_LEDGER.relative_to(ROOT).as_posix(),
            "real_payload_ledger_sha256": file_sha256(REAL_LEDGER),
            "result": "Q4_K STATE TRIAD RECONCILED",
        },
        "historical_events": copy.deepcopy(prior["historical_events"]),
        "attempts": [reconciled_attempt],
        "real_checkpoint_access": 1,
        "real_payload_ledger": 58,
        "status": "CONSUMED_EXECUTED_EXACT_REAL_BYTE_QUALIFIED",
        "next_attempt_id": None,
        "automatic_retry": False,
        "q6_k_status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "dense_prefix_status": "BLOCKED_NOT_EXECUTED",
    }


def packet_provenance_contract() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.real-event-packet-provenance",
        "schema_version": "1.0.0",
        "authority": "COMMITTED_REPOSITORY_EVIDENCE",
        "real_event_claims_requiring_provenance": [
            "real_checkpoint_access",
            "attempt_consumption",
            "ledger_transition",
            "real_payload_sha256",
            "decoded_sha256",
            "terminal_pass_or_fail",
        ],
        "required_bindings": ["committed_evidence_artifact_sha256", "git_commit_containing_evidence"],
        "conflict_precedence": ["git", "terminal_evidence", "attempt_ledger", "real_payload_ledger", "packet_prose"],
        "contradiction_disposition": "PACKET CLAIMS REJECTED — BANKED EVIDENCE CONTRADICTS PACKET",
        "generation_rule": "Real-event packets are generated from committed repository evidence and may not invent execution claims independently.",
        "validator": "scripts/research/f017_q4_state_q6_authorization.py::validate_real_event_claim",
    }


def validate_real_event_claim(root: Path, claim: dict[str, Any]) -> None:
    path_text = claim.get("committed_evidence_path")
    evidence_sha = claim.get("committed_evidence_artifact_sha256")
    commit = claim.get("git_commit_containing_evidence")
    require(isinstance(path_text, str) and not path_text.startswith("/") and ".." not in Path(path_text).parts, "unsafe evidence path")
    require(isinstance(evidence_sha, str) and len(evidence_sha) == 64, "evidence SHA binding")
    require(isinstance(commit, str) and len(commit) == 40, "evidence commit binding")
    result = subprocess.run(["git", "show", f"{commit}:{path_text}"], cwd=root, check=False, capture_output=True)
    require(result.returncode == 0, "evidence absent from bound commit")
    require(sha256_bytes(result.stdout) == evidence_sha, "committed evidence SHA mismatch")
    current = root / path_text
    require(current.is_file() and not current.is_symlink(), "current evidence artifact absent")
    require(file_sha256(current) == evidence_sha, "current evidence differs from committed artifact")


def ci_binding_ledger() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.ci-run-head-binding-ledger",
        "schema_version": "1.0.0",
        "append_only": True,
        "bindings": [
            {
                "phase": "Q4K-REAL-1-EVIDENCE",
                "run_id": 31_885_171_838,
                "head_sha": Q4_EVIDENCE_COMMIT,
                "workflow": "macOS baseline",
                "conclusion": "success",
                "jobs": [
                    {"job_id": 95_013_318_666, "name": "Apple Silicon workspace baseline", "conclusion": "success"},
                    {"job_id": 95_013_318_667, "name": "Apple MLX small-fixture validation", "conclusion": "success"},
                ],
                "source": "GitHub Actions run 31885171838 queried after the evidence push",
            }
        ],
        "backfill_policy": "Only append a prior binding when authoritative run and exact head identities are both available; no guessed pairs.",
    }


def validate_ci_ledger(value: dict[str, Any]) -> None:
    require(value.get("append_only") is True, "CI ledger append-only")
    bindings = value.get("bindings", [])
    require(len(bindings) >= 1, "CI binding count")
    pairs = [(row.get("run_id"), row.get("head_sha")) for row in bindings]
    require(len(pairs) == len(set(pairs)), "duplicate CI run/head binding")
    require((31_885_171_838, Q4_EVIDENCE_COMMIT) in pairs, "Q4 final-head CI binding")
    for row in bindings:
        require(isinstance(row.get("run_id"), int) and row["run_id"] > 0, "CI run ID")
        require(isinstance(row.get("head_sha"), str) and len(row["head_sha"]) == 40, "CI head")
        require(row.get("conclusion") == "success", "CI conclusion")


def q6_format_contract() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.q6-k-format-contract",
        "schema_version": "1.0.0",
        "contract_id": "GGUF_Q6_K_256x210_F32LE_V1",
        "quantization": "Q6_K",
        "elements_per_block": 256,
        "packed_bytes_per_block": 210,
        "layout": {"ql": [0, 128], "qh": [128, 192], "scales_i8": [192, 208], "d_f16_le": [208, 210]},
        "lane_map": load_json(Q6_DEFECT)["corrected_lane_map"],
        "canonical_output": "row_major_logical_little_endian_ieee754_binary32_no_padding",
        "row_policy": "row element count must be divisible by 256; no tail path",
        "non_finite_policy": "REJECT",
        "signed_zero_policy": "PRESERVE_AND_COUNT_EXACT_F32_BITS",
        "comparison": "EXACT_A_EQ_B_EQ_C_NO_TOLERANCE_NO_MAJORITY_VOTE",
        "upstream": copy.deepcopy(load_json(Q6_DEFECT)["upstream"]),
        "defect_id": "F017-Q6K-LANE-ORDER-001",
    }


def _q6_candidates() -> list[dict[str, Any]]:
    package = load_json(EVIDENCE_DIR / "f017-q6-k-future-package-v2.json")
    return copy.deepcopy(package["candidates"])


def q6_handoff_v3(format_sha: str) -> dict[str, Any]:
    defect = load_json(Q6_DEFECT)
    candidates = _q6_candidates()
    selected = sorted(candidates, key=lambda row: (-row["decoded_f32_bytes"], -row["packed_length"], row["tensor_name"]))[0]
    require(selected["tensor_name"] == Q6_TARGET["tensor_name"], "Q6 target-selection rule")
    return {
        "schema": "pulsarmlx.f017.q6-k-qualification-handoff",
        "schema_version": "3.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "predecessor": {
            "path": "specs/017-rust-native-inference-runtime/contracts/f017-q6-k-qualification-handoff-v2.json",
            "sha256": file_sha256(CONTRACT_DIR / "f017-q6-k-qualification-handoff-v2.json"),
        },
        "checkpoint_bindings": {"checkpoint_set_sha256": CHECKPOINT_SHA, "catalog_sha256": CATALOG_SHA, "tensor_map_sha256": TENSOR_MAP_SHA},
        "defect_closure": {
            "defect_id": defect["defect_id"],
            "evidence_path": Q6_DEFECT.relative_to(ROOT).as_posix(),
            "evidence_sha256": file_sha256(Q6_DEFECT),
            "corrected_decoder_source_sha256": CORRECTED_Q6_SHA,
            "upstream": copy.deepcopy(defect["upstream"]),
            "future_real_result_must_close_defect": True,
            "disagreement_classification": "Q6_K_DECODER_TRUTH_UNRESOLVED",
        },
        "format_contract": {"path": Q6_FORMAT.relative_to(ROOT).as_posix(), "sha256": format_sha},
        "candidates": candidates,
        "selection_rule": "largest decoded footprint; then largest packed footprint; then lexicographically lowest tensor name",
        "target": copy.deepcopy(Q6_TARGET),
        "decoder_truth_chain": copy.deepcopy(Q6_DECODERS),
        "pairwise_independence": [
            {"left": Q6_DECODERS[0]["name"], "right": Q6_DECODERS[1]["name"], "classification": "INDEPENDENT", "reason": "separate files and grouped versus index-driven control structures; neither imports the other"},
            {"left": Q6_DECODERS[0]["name"], "right": Q6_DECODERS[2]["name"], "classification": "INDEPENDENT", "reason": "different languages, files, control structures, and serialization paths"},
            {"left": Q6_DECODERS[1]["name"], "right": Q6_DECODERS[2]["name"], "classification": "INDEPENDENT", "reason": "different languages, files, control structures, and serialization paths"},
        ],
        "one_payload_sufficiency": {
            "verdict": "ONE Q6_K PAYLOAD SUFFICIENT",
            "block_elements": 256,
            "packed_block_bytes": 210,
            "row_elements": 12_288,
            "blocks_per_row": 48,
            "row_packed_bytes": 10_080,
            "rows": 6_144,
            "tail_path": False,
            "all_lane_groups_visited_per_block": True,
            "scale_and_high_bit_paths_visited_per_block": True,
            "synthetic_branch_coverage_bound_by_defect_evidence": True,
            "tensor_role_changes_decoder_semantics": False,
        },
        "access_budget": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "packed_bytes": 61_931_520, "model_compute": 0, "mlx_candidate_dispatches": 0},
        "ledger": {"before": 58, "after_real_payload_read": 59},
        "acceptance": "EXACT_CANONICAL_LE_F32_A_EQ_B_EQ_C_NO_TOLERANCE_NO_MAJORITY_VOTE",
        "automatic_retry": False,
        "automatic_dense_prefix_continuation": False,
        "execution_authorized": True,
        "real_checkpoint_access_this_preparation": 0,
    }


def q6_evidence_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "pulsarmlx.f017.q6-k-real-byte-evidence.v1",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "attempt", "identity", "access", "decoder_outputs", "comparison", "isolation", "ledger", "verdict"],
        "properties": {
            "schema": {"const": "pulsarmlx.f017.q6-k-real-byte-qualification-evidence"},
            "attempt": {"type": "object", "required": ["attempt_id", "authorized", "consumed", "executed", "checkpoint_accessed", "terminal_class"]},
            "identity": {"type": "object", "required": ["checkpoint_set_sha256", "tensor_name", "shard_ordinal", "offset", "packed_length", "packed_sha256", "format_contract_sha256", "corrected_decoder_source_sha256", "defect_evidence_sha256"]},
            "access": {"type": "object", "required": ["shard_opens", "positional_reads", "tensor_payloads", "packed_bytes"]},
            "decoder_outputs": {"type": "array", "minItems": 3, "maxItems": 3},
            "comparison": {"type": "object", "required": ["bitwise_equal", "first_divergence"]},
            "isolation": {"type": "object", "required": ["model_compute", "mlx_candidate_dispatches", "dense_prefix_executed"]},
            "ledger": {"type": "object", "required": ["before", "actual_payloads", "after"]},
            "verdict": {"enum": ["EXACT_REAL_BYTE_QUALIFIED", "Q6_K_DECODER_TRUTH_UNRESOLVED", "REJECTED"]},
        },
    }


def q6_execution_config(handoff_sha: str, format_sha: str, schema_sha: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.q6-k-execution-config",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED",
        "reviewed_base_head": Q4_EVIDENCE_COMMIT,
        "head_policy": "execution head must equal the authoritative remote head and descend from reviewed_base_head; every execution-controlling artifact hash must match",
        "checkpoint_bindings": {"checkpoint_set_sha256": CHECKPOINT_SHA, "catalog_sha256": CATALOG_SHA, "tensor_map_sha256": TENSOR_MAP_SHA},
        "handoff": {"path": Q6_HANDOFF.relative_to(ROOT).as_posix(), "sha256": handoff_sha},
        "format_contract": {"path": Q6_FORMAT.relative_to(ROOT).as_posix(), "sha256": format_sha},
        "defect_evidence": {"path": Q6_DEFECT.relative_to(ROOT).as_posix(), "sha256": file_sha256(Q6_DEFECT)},
        "corrected_decoder_source_sha256": CORRECTED_Q6_SHA,
        "target": copy.deepcopy(Q6_TARGET),
        "decoders": copy.deepcopy(Q6_DECODERS),
        "access_budget": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "packed_bytes": 61_931_520, "model_compute": 0, "mlx_candidate_dispatches": 0},
        "attempt": {"attempt_id": Q6_ATTEMPT_ID, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "automatic_retry": False},
        "continuation": {"q6_second_payload": False, "dense_prefix": False, "m1_f": False, "m1_g": False, "p1": False},
        "evidence_schema": {"path": Q6_SCHEMA.relative_to(ROOT).as_posix(), "sha256": schema_sha},
        "evidence_destination": "docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-v1.json",
        "ledger": {"before": 58, "after_real_payload_read": 59},
        "allow_cli_target_override": False,
        "allow_environment_target_override": False,
        "execution_authorized": True,
    }


def q6_authorization_binding(config_sha: str, handoff_sha: str, format_sha: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.q6-k-authorization-binding",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED_FOR_EXACTLY_ONE_ATTEMPT_NOT_EXECUTED",
        "attempt_id": Q6_ATTEMPT_ID,
        "execution_authorized": True,
        "execution_config_sha256": config_sha,
        "handoff_v3_sha256": handoff_sha,
        "format_contract_sha256": format_sha,
        "corrected_decoder_source_sha256": CORRECTED_Q6_SHA,
        "defect_evidence_sha256": file_sha256(Q6_DEFECT),
        "target": copy.deepcopy(Q6_TARGET),
        "access_budget": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "packed_bytes": 61_931_520},
        "ledger": {"before": 58, "after_real_payload_read": 59},
        "automatic_retry": False,
        "automatic_dense_prefix_continuation": False,
        "automatic_other_gate_continuation": False,
        "separate_operator_execution_instruction_required": True,
        "real_checkpoint_access_this_preparation": 0,
    }


def q6_attempt_ledger(config_sha: str, binding_sha: str, handoff_sha: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.q6-k-attempt-ledger",
        "schema_version": "1.0.0",
        "append_only": True,
        "attempts": [
            {
                "attempt_id": Q6_ATTEMPT_ID,
                "gate": "Q6_K_REAL_BYTE_QUALIFICATION",
                "authorized": True,
                "consumed": False,
                "executed": False,
                "checkpoint_accessed": False,
                "reviewed_base_head": Q4_EVIDENCE_COMMIT,
                "execution_config_sha256": config_sha,
                "control_binding_sha256": binding_sha,
                "handoff_v3_sha256": handoff_sha,
                "ledger_before": 58,
                "expected_real_payload_ledger_after": 59,
                "automatic_retry": False,
                "automatic_dense_prefix_continuation": False,
                "automatic_other_gate_continuation": False,
            }
        ],
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED",
        "next_attempt_id": Q6_ATTEMPT_ID,
        "real_checkpoint_access": 0,
        "real_payload_ledger": 58,
    }


def validate_q6_package(root: Path = ROOT) -> None:
    handoff = load_json(root / Q6_HANDOFF.relative_to(ROOT))
    config = load_json(root / Q6_CONFIG.relative_to(ROOT))
    binding = load_json(root / Q6_BINDING.relative_to(ROOT))
    attempt_ledger = load_json(root / Q6_ATTEMPT.relative_to(ROOT))
    format_contract = load_json(root / Q6_FORMAT.relative_to(ROOT))
    require(file_sha256(root / Q6_DEFECT.relative_to(ROOT)) == handoff["defect_closure"]["evidence_sha256"], "Q6 defect evidence binding")
    require(handoff["defect_closure"]["corrected_decoder_source_sha256"] == CORRECTED_Q6_SHA, "corrected decoder direct binding")
    require(file_sha256(root / "scripts/research/ggml_kquants.py") == CORRECTED_Q6_SHA, "corrected decoder source drift")
    require(handoff["target"] == Q6_TARGET == config["target"] == binding["target"], "Q6 target identity")
    require(Q6_TARGET["blocks"] * Q6_TARGET["packed_bytes_per_block"] == Q6_TARGET["packed_length"], "Q6 block arithmetic")
    require(Q6_TARGET["packed_row_width"] * Q6_TARGET["logical_shape"][0] == Q6_TARGET["packed_length"], "Q6 row arithmetic")
    require(format_contract["elements_per_block"] == 256 and format_contract["packed_bytes_per_block"] == 210, "Q6 format block")
    require(handoff["one_payload_sufficiency"]["verdict"] == "ONE Q6_K PAYLOAD SUFFICIENT", "one-payload sufficiency")
    require(handoff["one_payload_sufficiency"]["tail_path"] is False, "Q6 tail path")
    require([row["name"] for row in config["decoders"]] == [row["name"] for row in Q6_DECODERS], "Q6 decoder identities")
    require(all(not row["imports_another_decoder"] and not row["generated_real_expected_output"] for row in config["decoders"]), "Q6 decoder independence")
    require(config["access_budget"] == {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "packed_bytes": 61_931_520, "model_compute": 0, "mlx_candidate_dispatches": 0}, "Q6 access budget")
    require(binding["execution_config_sha256"] == file_sha256(root / Q6_CONFIG.relative_to(ROOT)), "Q6 config binding")
    require(binding["handoff_v3_sha256"] == file_sha256(root / Q6_HANDOFF.relative_to(ROOT)), "Q6 handoff binding")
    require(binding["format_contract_sha256"] == file_sha256(root / Q6_FORMAT.relative_to(ROOT)), "Q6 format binding")
    require(config["execution_authorized"] is True and binding["execution_authorized"] is True, "Q6 execution authorization")
    attempt = _attempt_record(attempt_ledger, Q6_ATTEMPT_ID)
    require(attempt["authorized"] is True and attempt["consumed"] is False and attempt["executed"] is False and attempt["checkpoint_accessed"] is False, "Q6 attempt state")
    require(attempt["execution_config_sha256"] == file_sha256(root / Q6_CONFIG.relative_to(ROOT)), "Q6 attempt config")
    require(attempt["control_binding_sha256"] == file_sha256(root / Q6_BINDING.relative_to(ROOT)), "Q6 attempt binding")
    require(attempt["handoff_v3_sha256"] == file_sha256(root / Q6_HANDOFF.relative_to(ROOT)), "Q6 attempt handoff")
    require(attempt["ledger_before"] == 58 and attempt["expected_real_payload_ledger_after"] == 59, "Q6 attempt ledger transition")
    require(attempt["automatic_retry"] is False and attempt["automatic_dense_prefix_continuation"] is False and attempt["automatic_other_gate_continuation"] is False, "Q6 automatic continuation")
    require(load_json(root / REAL_LEDGER.relative_to(ROOT))["cumulative_tensor_payloads"] == 58, "Q6 preflight real ledger")


def canonical_preflight(root: Path = ROOT, check_git: bool = True) -> str:
    require(validate_q4_triad(root) == "Q4_K STATE TRIAD RECONCILED", "Q4 state triad")
    validate_q6_package(root)
    if check_git:
        local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        remote = subprocess.check_output(["git", "rev-parse", "origin/feat/017-real-checkpoint-runner"], cwd=root, text=True).strip()
        require(local == remote, "local/remote parity")
        require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip(), "worktree clean")
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", Q4_EVIDENCE_COMMIT, local], cwd=root, check=False)
        require(ancestor.returncode == 0, "authorization-head ancestry")
    return "READY_TO_EXECUTE_Q6_K_REAL_BYTE_QUALIFICATION"


def generate() -> dict[str, str]:
    hashes: dict[str, str] = {}
    hashes[Q4_LEDGER_V3.relative_to(ROOT).as_posix()] = write_json(Q4_LEDGER_V3, q4_ledger_v3())
    hashes[PACKET_CONTRACT.relative_to(ROOT).as_posix()] = write_json(PACKET_CONTRACT, packet_provenance_contract())
    ci = ci_binding_ledger()
    validate_ci_ledger(ci)
    hashes[CI_LEDGER.relative_to(ROOT).as_posix()] = write_json(CI_LEDGER, ci)
    hashes[Q6_FORMAT.relative_to(ROOT).as_posix()] = write_json(Q6_FORMAT, q6_format_contract())
    hashes[Q6_SCHEMA.relative_to(ROOT).as_posix()] = write_json(Q6_SCHEMA, q6_evidence_schema())
    hashes[Q6_HANDOFF.relative_to(ROOT).as_posix()] = write_json(Q6_HANDOFF, q6_handoff_v3(hashes[Q6_FORMAT.relative_to(ROOT).as_posix()]))
    hashes[Q6_CONFIG.relative_to(ROOT).as_posix()] = write_json(Q6_CONFIG, q6_execution_config(hashes[Q6_HANDOFF.relative_to(ROOT).as_posix()], hashes[Q6_FORMAT.relative_to(ROOT).as_posix()], hashes[Q6_SCHEMA.relative_to(ROOT).as_posix()]))
    hashes[Q6_BINDING.relative_to(ROOT).as_posix()] = write_json(Q6_BINDING, q6_authorization_binding(hashes[Q6_CONFIG.relative_to(ROOT).as_posix()], hashes[Q6_HANDOFF.relative_to(ROOT).as_posix()], hashes[Q6_FORMAT.relative_to(ROOT).as_posix()]))
    hashes[Q6_ATTEMPT.relative_to(ROOT).as_posix()] = write_json(Q6_ATTEMPT, q6_attempt_ledger(hashes[Q6_CONFIG.relative_to(ROOT).as_posix()], hashes[Q6_BINDING.relative_to(ROOT).as_posix()], hashes[Q6_HANDOFF.relative_to(ROOT).as_posix()]))
    triad = {
        "schema": "pulsarmlx.f017.q4-k-state-triad-reconciliation",
        "schema_version": "1.0.0",
        "result": validate_q4_triad(),
        "attempt_ledger": {"path": Q4_LEDGER_V3.relative_to(ROOT).as_posix(), "sha256": hashes[Q4_LEDGER_V3.relative_to(ROOT).as_posix()]},
        "real_payload_ledger": {"path": REAL_LEDGER.relative_to(ROOT).as_posix(), "sha256": file_sha256(REAL_LEDGER), "cumulative_payloads": 58},
        "terminal_evidence": {"path": Q4_EVIDENCE.relative_to(ROOT).as_posix(), "sha256": Q4_EVIDENCE_SHA, "commit": Q4_EVIDENCE_COMMIT},
        "derived_state": {"attempt_id": Q4_ATTEMPT_ID, "authorized": True, "consumed": True, "executed": True, "checkpoint_accessed": True, "terminal_classification": "EXACT_REAL_BYTE_QUALIFIED", "payloads": 1, "ledger_before": 57, "ledger_after": 58},
        "real_checkpoint_access_this_phase": 0,
    }
    hashes[TRIAD_EVIDENCE.relative_to(ROOT).as_posix()] = write_json(TRIAD_EVIDENCE, triad)
    validate_q4_triad()
    validate_q6_package()
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--skip-git-state", action="store_true")
    args = parser.parse_args()
    if args.generate:
        print(json.dumps({"generated": generate(), "checkpoint_reads": 0, "ledger": 58}, sort_keys=True))
    elif args.preflight:
        print(canonical_preflight(check_git=not args.skip_git_state))
    else:
        print(json.dumps({"q4": validate_q4_triad(), "q6": "VALID"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

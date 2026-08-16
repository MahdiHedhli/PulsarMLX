#!/usr/bin/env python3
"""Fail closed when reviewed DPREFIX surfaces cannot instantiate Tier-B.

This validator is checkpoint-free.  It distinguishes stage identity hashes
from the stage values required to derive max-absolute-error, RMSE, and cosine
metrics under the frozen real Tier-B contract.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
CANDIDATE = ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs"
ORACLE = ROOT / "scripts/research/f017_dprefix_oracle_runtime.py"
TIER_B = CONTRACTS / "f017-dense-prefix-real-tier-b-v1.json"
EVIDENCE_V2 = CONTRACTS / "f017-dense-prefix-evidence-v2.schema.json"
CONFIG = EVIDENCE / "f017-dense-prefix-execution-config-v3.json"
AUTH = EVIDENCE / "f017-dense-prefix-authorization-binding-v2.json"
ATTEMPT = EVIDENCE / "f017-dense-prefix-attempt-ledger-v2.json"
PAYLOAD_LEDGER = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
BANKED = EVIDENCE / "f017-dense-prefix-real-attempt-1-not-executed-numerical-surface-v1.json"
ATTEMPT_V3 = EVIDENCE / "f017-dense-prefix-attempt-ledger-v3.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_checkpoint_free() -> dict:
    candidate = CANDIDATE.read_text(encoding="utf-8")
    oracle = ORACLE.read_text(encoding="utf-8")
    tier_b = load(TIER_B)
    evidence_schema = load(EVIDENCE_V2)
    config = load(CONFIG)
    authorization = load(AUTH)
    attempt = load(ATTEMPT)["events"][-1]
    payload_ledger = load(PAYLOAD_LEDGER)

    if sha256(CONFIG) != "1ec301f23735dbebd7360ef58f38ba78cfc89dad878f3b6c63686ac63952a806":
        raise ValueError("reviewed config drift")
    if sha256(AUTH) != "68e37070e50c96cd57d2e0dd79199f1a63952163adfd614f7200907ca3b3d248":
        raise ValueError("reviewed authorization drift")
    if config["attempt_id"] != "DPREFIX-REAL-1" or not config["execution_authorized"]:
        raise ValueError("attempt authorization")
    if attempt["consumed"] or attempt["executed"] or attempt["checkpoint_accessed"]:
        raise ValueError("attempt already consumed")
    if payload_ledger["cumulative_tensor_payloads"] != 59:
        raise ValueError("real payload ledger")

    candidate_struct = candidate.split("struct RealCandidateEvidence", 1)[1].split(
        "fn sha_bytes", 1
    )[0]
    if "stage_hashes" not in candidate_struct or "retained_state" not in candidate_struct:
        raise ValueError("candidate result identity surface")
    if any(
        field in candidate_struct
        for field in ("numerical_surfaces", "max_absolute_error", "rmse", "cosine")
    ):
        raise ValueError("candidate numerical surface unexpectedly changed")
    if "def dense_prefix(" not in oracle or "dict[str, str]" not in oracle:
        raise ValueError("oracle stage-hash surface")
    if "max_absolute_error" in oracle or "candidate_values" in oracle:
        raise ValueError("oracle comparison surface unexpectedly changed")

    required_candidate = evidence_schema["properties"]["candidate"]["required"]
    if "numerical_surfaces" not in required_candidate:
        raise ValueError("evidence contract no longer requires numerical surfaces")
    if evidence_schema["properties"]["candidate"]["properties"]["numerical_surfaces"][
        "minItems"
    ] < 5:
        raise ValueError("numerical evidence surface weakened")
    for required in ("per_layer", "intermediate_attention_each_layer"):
        if required not in tier_b:
            raise ValueError(f"Tier-B surface missing: {required}")
    for metric in ("max_absolute_error", "rmse", "cosine_similarity_minimum"):
        if metric not in tier_b["per_layer"] or metric not in tier_b[
            "intermediate_attention_each_layer"
        ]:
            raise ValueError(f"Tier-B metric missing: {metric}")

    return {
        "result": "NOT_READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE",
        "terminal_class": "INFRASTRUCTURE",
        "reason_code": "TIER_B_NUMERICAL_SURFACE_UNINSTANTIABLE",
        "attempt_id": "DPREFIX-REAL-1",
        "attempt_consumed": False,
        "checkpoint_reads": 0,
        "ledger": 59,
        "facts": {
            "candidate_intermediate_values_retained": False,
            "candidate_intermediate_stage_hashes_retained": True,
            "oracle_intermediate_values_retained": False,
            "oracle_intermediate_stage_hashes_retained": True,
            "final_candidate_values_retained": True,
            "hashes_can_derive_error_metrics": False,
            "tier_b_requires_per_layer_metrics": True,
            "tier_b_requires_intermediate_attention_metrics": True,
        },
        "bindings": {
            "candidate_source_sha256": sha256(CANDIDATE),
            "oracle_source_sha256": sha256(ORACLE),
            "tier_b_sha256": sha256(TIER_B),
            "evidence_v2_schema_sha256": sha256(EVIDENCE_V2),
            "execution_config_sha256": sha256(CONFIG),
            "authorization_binding_sha256": sha256(AUTH),
            "attempt_ledger_sha256": sha256(ATTEMPT),
            "real_payload_ledger_sha256": sha256(PAYLOAD_LEDGER),
        },
    }


def validate_banked_nonexecution() -> dict:
    evidence = load(BANKED)
    attempt_ledger = load(ATTEMPT_V3)
    event = attempt_ledger["events"][-1]
    payload_ledger = load(PAYLOAD_LEDGER)
    state = evidence["state"]
    expected = {
        "authorized": True,
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
        "payloads_read": 0,
        "packed_bytes_read": 0,
        "ledger_before": 59,
        "ledger_after": 59,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
    }
    if state != expected:
        raise ValueError("banked nonexecution state")
    if evidence["verdict"] != "NOT_EXECUTED" or evidence["terminal_class"] != "INFRASTRUCTURE":
        raise ValueError("banked terminal classification")
    if evidence["reason_code"] != "TIER_B_NUMERICAL_SURFACE_UNINSTANTIABLE":
        raise ValueError("banked reason")
    if attempt_ledger["append_only_predecessor"]["sha256"] != sha256(ATTEMPT):
        raise ValueError("attempt predecessor")
    if event["attempt_id"] != "DPREFIX-REAL-1" or event["evidence_sha256"] != sha256(BANKED):
        raise ValueError("attempt evidence binding")
    for key in ("authorized", "consumed", "executed", "checkpoint_accessed"):
        if event[key] != expected[key]:
            raise ValueError(f"attempt state: {key}")
    if event["actual_payload_reads"] != 0 or event["ledger_before"] != 59 or event["ledger_after"] != 59:
        raise ValueError("attempt access accounting")
    if payload_ledger["cumulative_tensor_payloads"] != 59:
        raise ValueError("payload ledger changed")
    if any(item.get("attempt") == "DPREFIX-REAL-1" for item in payload_ledger["events"]):
        raise ValueError("zero-read attempt added to payload ledger")
    return {
        "result": "BANKED_NONEXECUTION_RECONCILED",
        "terminal_class": "INFRASTRUCTURE",
        "attempt_consumed": False,
        "payloads": 0,
        "ledger": 59,
    }


def main() -> None:
    result = {"preflight": validate_checkpoint_free()}
    if BANKED.exists() and ATTEMPT_V3.exists():
        result["banked"] = validate_banked_nonexecution()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

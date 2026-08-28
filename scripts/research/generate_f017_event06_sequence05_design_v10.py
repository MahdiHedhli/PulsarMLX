#!/usr/bin/env python3
"""Generate the Cycle-10 design-only repair projection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v9 as v9


ROOT = v9.ROOT
C = v9.C
E = v9.E

CYCLE8_COUNTS = E / "f017-event06-v12-sequence05-cycle8-review-count-derivation-v1.json"
CYCLE8_IDS = E / "f017-event06-v12-sequence05-cycle8-finding-id-authority-v1.json"
CYCLE9_REPAIR = E / "f017-event06-v12-sequence05-cycle9-repair-ledger-v1.json"
BEHAVIOR_POLICY = C / "f017-event06-sequence05-generator-behavioral-reproduction-policy-v1.json"
GRAPH10 = E / "f017-event06-v12-sequence05-design-graph-state-v10.json"
CLAIMS10 = E / "f017-event06-v12-sequence05-design-claim-ledger-v10.json"
GRAPH11 = E / "f017-event06-v12-sequence05-design-graph-state-v11.json"
CLAIMS11 = E / "f017-event06-v12-sequence05-design-claim-ledger-v11.json"


def sha_raw(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha(path: Path) -> str:
    return sha_raw(path.read_bytes())


def load(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"not object: {path.relative_to(ROOT)}")
    return value


def write(path: Path, value: object, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not path.is_file() or path.read_bytes() != raw:
            raise SystemExit(f"drift: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def _counts(value: dict) -> dict:
    return {
        "blocking": value["blocking_findings"],
        "required": value["required_findings"],
        "advisory": value["advisory_findings"],
        "unresolved": value["unresolved_claims"],
    }


def build_cycle8_counts() -> dict:
    agy_path = E / "f017-event06-v12-sequence05-agy-design-cycle-08-normalized-result.json"
    opus_path = E / "f017-event06-v12-sequence05-opus-design-cycle-08-normalized-result.json"
    agy = load(agy_path)
    opus = load(opus_path)
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-review-count-derivation/1.0.0",
        "review_cycle": 8,
        "agy_source_path": str(agy_path.relative_to(ROOT)),
        "agy_source_sha256": sha(agy_path),
        "agy_counts": _counts(agy),
        "agy_verdict": agy["verdict"],
        "opus_source_path": str(opus_path.relative_to(ROOT)),
        "opus_source_sha256": sha(opus_path),
        "opus_counts": _counts(opus),
        "opus_verdict": opus["verdict"],
        "counts_derived_from_normalized_results": True,
    }


def build_cycle8_ids() -> dict:
    rows = []
    for ledger_id, severity, _summary, _predicate in v9.OPUS_ROWS:
        if ledger_id.startswith("C8-OPUS-B"):
            source_id = ledger_id
        elif ledger_id.startswith("C8-OPUS-"):
            source_id = ledger_id.removeprefix("C8-OPUS-")
        else:
            source_id = ledger_id
        rows.append({
            "ledger_id": ledger_id,
            "source_id": source_id,
            "severity": severity,
            "source_response_path": str(v9.OPUS8.relative_to(ROOT)),
            "source_response_sha256": sha(v9.OPUS8),
        })
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-finding-id-authority/1.0.0",
        "review_cycle": 8,
        "rows": rows,
        "row_count": len(rows),
        "ledger_ids_unique": len({row["ledger_id"] for row in rows}) == len(rows),
        "source_ids_unique": len({row["source_id"] for row in rows}) == len(rows),
    }


def build_behavior_policy() -> dict:
    return {
        "schema": "pulsarmlx.f017.event06-sequence05-generator-behavioral-reproduction-policy/1.0.0",
        "success_repetitions": 2,
        "success_mtime_profiles": ["200101010101", "203512312359"],
        "negative_case": "CORRUPT_ONE_GENERATED_ARTIFACT_THEN_REQUIRE_GENERATOR_CHECK_NONZERO",
        "negative_generator_exit_must_be_nonzero": True,
        "negative_clone_must_remain_confined_to_disposable_root": True,
        "authoritative_worktree_must_remain_clean": True,
    }


def build_cycle9_repair() -> dict:
    response = E / "f017-event06-v12-sequence05-opus-design-cycle-09-exact-response.md"
    normalized = E / "f017-event06-v12-sequence05-opus-design-cycle-09-normalized-result.json"
    findings = [
        ("C9-OPUS-P1", "bind every advisory support row to its exact source response path and SHA", "advisory_source_response"),
        ("C9-OPUS-P2", "derive Cycle-8 counts and finding IDs from exact normalized results and response bytes", "cycle8_source_derivation"),
        ("C9-OPUS-P3", "reject Compare, UnaryOp, BoolOp, and bool-call constant truth in the AST guard", "ast_constant_battery"),
        ("C9-OPUS-P4", "exercise a behavioral generator corruption and require nonzero --check", "generator_behavioral_reproduction"),
        ("C9-OPUS-P5", "fail closed for missing prepared bindings and require ancestry plus reviewed-tree byte equality", "prepared_fail_closed"),
    ]
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-cycle9-repair-ledger/1.0.0",
        "source_response_path": str(response.relative_to(ROOT)),
        "source_response_sha256": sha(response),
        "source_normalized_path": str(normalized.relative_to(ROOT)),
        "source_normalized_sha256": sha(normalized),
        "rows": [
            {"finding_id": finding, "severity": "ADVISORY_ACTIONABLE", "repair_requirement": requirement,
             "validator_predicate": predicate, "disposition": "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW"}
            for finding, requirement, predicate in findings
        ],
        "row_count": len(findings),
        "unresolved_attack_batteries_from_review": 15,
        "status": "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW",
    }


def build_graph10() -> dict:
    agy = load(E / "f017-event06-v12-sequence05-agy-design-cycle-09-normalized-result.json")
    opus = load(E / "f017-event06-v12-sequence05-opus-design-cycle-09-normalized-result.json")
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.9.0",
        "review_cycle": 9,
        "reviewed_commit": opus["reviewed_commit"],
        "reviewed_tree": opus["reviewed_tree"],
        "agy_counts": _counts(agy),
        "agy_verdict": agy["verdict"],
        "opus_counts": _counts(opus),
        "opus_verdict": opus["global_verdict"],
        "running_nodes": 0,
        "status": "REPAIR_REQUIRED",
    }


def build_claims10() -> dict:
    opus = load(E / "f017-event06-v12-sequence05-opus-design-cycle-09-normalized-result.json")
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.9.0",
        "review_cycle": 9,
        "finding_ids": opus["finding_ids"],
        "advisory_actionable": opus["advisory_findings"],
        "unresolved": opus["unresolved_claims"],
        "independently_accepted": 0,
        "status": "REPAIR_REQUIRED",
    }


def build_graph11() -> dict:
    source = build_graph10()
    repair = build_cycle9_repair()
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.10.0",
        "source_review_cycle": 9,
        "source_opus_counts": source["opus_counts"],
        "repair_rows": repair["row_count"],
        "mechanically_closed_rows": repair["row_count"],
        "unresolved_attack_batteries_pending_fresh_review": repair["unresolved_attack_batteries_from_review"],
        "independent_review_status": "PENDING",
        "running_nodes": 0,
        "status": "PENDING_INDEPENDENT_REVIEW",
    }


def build_claims11() -> dict:
    rows = build_cycle9_repair()["rows"]
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.10.0",
        "source_review_cycle": 9,
        "rows": [{"claim_id": row["finding_id"], "state": "MECHANICALLY_SUPPORTED_PENDING_INDEPENDENT_REVIEW"} for row in rows],
        "row_count": len(rows),
        "mechanically_supported": len(rows),
        "independently_accepted": 0,
        "status": "PENDING_INDEPENDENT_REVIEW",
    }


def generator_predicate_cycle8_counts() -> bool:
    derived = build_cycle8_counts()
    return derived["opus_counts"] == {"blocking": 5, "required": 5, "advisory": 3, "unresolved": 2} and derived["agy_counts"] == {"blocking": 4, "required": 0, "advisory": 0, "unresolved": 0}


def generator_predicate_cycle8_ids() -> bool:
    authority = build_cycle8_ids()
    response = v9.OPUS8.read_text()
    return authority["row_count"] == 15 and all(row["source_id"] in response for row in authority["rows"])


GENERATOR_PREDICATES = {
    "cycle8_counts": generator_predicate_cycle8_counts,
    "cycle8_ids": generator_predicate_cycle8_ids,
}


ARTIFACT_BUILDERS = {
    CYCLE8_COUNTS: build_cycle8_counts,
    CYCLE8_IDS: build_cycle8_ids,
    CYCLE9_REPAIR: build_cycle9_repair,
    BEHAVIOR_POLICY: build_behavior_policy,
    GRAPH10: build_graph10,
    CLAIMS10: build_claims10,
    GRAPH11: build_graph11,
    CLAIMS11: build_claims11,
}


def artifacts() -> dict[Path, object]:
    return {path: builder() for path, builder in ARTIFACT_BUILDERS.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not all(predicate() for predicate in v9.GENERATOR_PREDICATES.values()):
        raise SystemExit("predecessor generator predicate failure")
    if not all(predicate() for predicate in GENERATOR_PREDICATES.values()):
        raise SystemExit("successor generator predicate failure")
    for path, value in v9.artifacts().items():
        write(path, value, True if args.check else path.is_file())
    if v9.PREPARED.is_file():
        prepared_head = v9.load(v9.PREPARED)["implementation_head"]
        write(v9.PREPARED, v9.prepared(prepared_head), True)
    for path, value in artifacts().items():
        write(path, value, args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

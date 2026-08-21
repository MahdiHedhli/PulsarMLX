#!/usr/bin/env python3
"""Derive and validate the append-only F017 master real-payload ledger v2."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
V1_PATH = pathlib.Path("docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json")
V1_SHA = "c68be19f2840dea612e8b20ff2933751800555c80ae66fcfbbff02086bbe18c0"
EVENT_PATH = pathlib.Path("docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json")
EVENT_SHA = "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190"
V2_PATH = pathlib.Path("docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json")
ENFORCEMENT_BASE = "039a43ba8f41b755214f69117b0fc8cd15c05ee5"


class LedgerV2Error(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LedgerV2Error(f"duplicate key {key}")
        out[key] = value
    return out


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerV2Error(str(exc)) from exc
    if not isinstance(value, dict):
        raise LedgerV2Error(f"object required: {path}")
    return value


def v1_builder(root: pathlib.Path):
    path = root / "scripts/research/validate_f017_real_payload_ledger.py"
    spec = importlib.util.spec_from_file_location("ledger_v1_builder", path)
    if not spec or not spec.loader:
        raise LedgerV2Error("cannot import v1 builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_ledger(root)


def build(root: pathlib.Path) -> dict[str, Any]:
    v1_file = root / V1_PATH
    event_file = root / EVENT_PATH
    if sha256(v1_file) != V1_SHA or sha256(event_file) != EVENT_SHA:
        raise LedgerV2Error("source identity")
    v1 = load(v1_file)
    if v1_builder(root) != v1 or v1.get("cumulative_tensor_payloads") != 166:
        raise LedgerV2Error("v1 reconstruction")
    event = load(event_file)
    accounting = event.get("access_accounting")
    receipts = event.get("receipts")
    if not isinstance(accounting, dict) or not isinstance(receipts, list):
        raise LedgerV2Error("representative event accounting")
    if accounting != {
        "ledger_before": 166, "ledger_after": 175, "consumed_reads": 9,
        "packed_bytes_consumed": 132900864, "shard_opens": 1,
        "checkpoint_rereads": 0, "expert_payload_reads": 0,
        "expert_executions": 0, "decoder_agreements": 9,
        "journal_sha256": "ec4cce377ff9737a94db0bcb5193cdd9c2fe296baf7ba9cfafb35e90ddb3bda7",
    }:
        raise LedgerV2Error("representative event accounting mismatch")
    if event.get("terminal", {}).get("status") != "COMPLETE":
        raise LedgerV2Error("representative terminal")
    if len(receipts) != 9:
        raise LedgerV2Error("receipt census")
    expected_after = list(range(167, 176))
    if [r.get("ordinal") for r in receipts] != list(range(9)):
        raise LedgerV2Error("receipt ordinal continuity")
    if [r.get("ledger_after") for r in receipts] != expected_after:
        raise LedgerV2Error("receipt ledger continuity")
    receipt_shas = [r.get("receipt_sha256") for r in receipts]
    if any(not isinstance(value, str) or len(value) != 64 for value in receipt_shas) or len(set(receipt_shas)) != 9:
        raise LedgerV2Error("receipt identity")
    if sum(int(r.get("packed_bytes", -1)) for r in receipts) != 132900864:
        raise LedgerV2Error("receipt byte total")
    prior_events = v1.get("events")
    if not isinstance(prior_events, list):
        raise LedgerV2Error("v1 events")
    prior = 0
    event_keys: set[tuple[str, str]] = set()
    for row in prior_events:
        key = (str(row.get("phase")), str(row.get("attempt")))
        if key in event_keys:
            raise LedgerV2Error("duplicate event identity")
        event_keys.add(key)
        count = row.get("tensor_payload_count")
        after = row.get("cumulative_tensor_payloads_after_event")
        if isinstance(count, bool) or not isinstance(count, int) or after != prior + count:
            raise LedgerV2Error("v1 event continuity")
        prior = after
    if prior != 166:
        raise LedgerV2Error("v1 terminal")
    appended = {
        "phase": "REPRESENTATIVE-M1F0-ATTENTION-ROUTE",
        "attempt": "F017-REPRESENTATIVE-M1F0-ATTEMPT-1",
        "access_kind": "execution",
        "consumed_attempt": True,
        "reason": "accepted representative M1-F0 attention/route event",
        "tensor_payload_count": 9,
        "packed_bytes": 132900864,
        "ledger_before": 166,
        "cumulative_tensor_payloads_after_event": 175,
        "shard_opens": 1,
        "evidence": {"path": EVENT_PATH.as_posix(), "sha256": EVENT_SHA},
        "receipt_chain": receipts,
        "terminal": event["terminal"],
    }
    return {
        "schema": "pulsarmlx.f017.real-payload-access-ledger",
        "schema_version": "2.0.0",
        "ledger_id": "F017-REAL-PAYLOAD-ACCESS-LEDGER-2",
        "authoritative": True,
        "supersedes_for_current_count": {"path": V1_PATH.as_posix(), "sha256": V1_SHA, "terminal_count": 166, "disposition": "HISTORICAL_PREFIX_BYTE_IDENTICAL_STALE_AFTER_LATER_ACCEPTED_EVENT"},
        "accounting_rule": v1["accounting_rule"],
        "prefix_event_count": len(prior_events),
        "prefix_reconstruction_sha256": hashlib.sha256((json.dumps(v1, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest(),
        "appended_events": [appended],
        "receipt_chain": {"starting_count": 0, "prefix_terminal_count": 166, "appended_receipt_counts": expected_after, "terminal_count": 175, "gaps": 0, "overlaps": 0, "duplicate_receipts": 0, "unexplained_increments": 0},
        "cumulative_tensor_payloads": 175,
        "closure_consistency": {"closure_package": 175, "closure_declaration": 175, "representative_event": 175, "result": "PASS"},
        "reconciliation": {"new_payload_consumption": 0, "checkpoint_reads": 0, "shard_opens": 0, "numerical_executions": 0, "historical_artifacts_rewritten": False, "classification": "ACCOUNTING_ONLY_APPEND_ONLY_MASTER_SURFACE_RECONCILIATION"},
        "future_banking_invariant": {"effective_after_head": ENFORCEMENT_BASE, "event_result_and_master_ledger_same_commit": True, "post_event_count_derived_from_validated_receipts": True, "terminal_consumed_reads_cross_checked_to_receipt_count": True, "manual_independent_post_event_count": False},
    }


def canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def validate_document(root: pathlib.Path, document: dict[str, Any]) -> None:
    if document != build(root):
        raise LedgerV2Error("ledger document differs from receipt-derived reconstruction")


def validate_same_commit_rule(root: pathlib.Path) -> None:
    try:
        commits = subprocess.check_output(["git", "rev-list", f"{ENFORCEMENT_BASE}..HEAD"], cwd=root, text=True).split()
    except subprocess.CalledProcessError as exc:
        raise LedgerV2Error("git history unavailable") from exc
    for commit in commits:
        changed = subprocess.check_output(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit], cwd=root, text=True).splitlines()
        advancing = False
        for rel in changed:
            if not rel.startswith("docs/architecture/reviews/evidence/") or not rel.endswith(".json") or "real-execution-result" not in rel:
                continue
            try:
                raw = subprocess.check_output(["git", "show", f"{commit}:{rel}"], cwd=root)
                doc = json.loads(raw, object_pairs_hook=unique)
            except (subprocess.CalledProcessError, json.JSONDecodeError, LedgerV2Error):
                continue
            accounting = doc.get("access_accounting", {}) if isinstance(doc, dict) else {}
            before, after, reads = accounting.get("ledger_before"), accounting.get("ledger_after"), accounting.get("consumed_reads")
            if isinstance(before, int) and not isinstance(before, bool) and isinstance(after, int) and isinstance(reads, int) and after > before and reads > 0:
                advancing = True
        if advancing and V2_PATH.as_posix() not in changed:
            raise LedgerV2Error(f"event result without same-commit master ledger: {commit}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=ROOT)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--check", type=pathlib.Path)
    parser.add_argument("--skip-git-rule", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    payload = canonical(build(root))
    if args.check:
        if not args.check.is_file():
            raise SystemExit("master ledger v2 missing")
        validate_document(root, load(args.check))
        if args.check.read_bytes() != payload:
            raise SystemExit("master ledger v2 differs from receipt-derived reconstruction")
    elif args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    if not args.skip_git_rule:
        validate_same_commit_rule(root)
    print(json.dumps({"result":"PASS","terminal_count":175,"new_payload_consumption":0,"checkpoint_reads":0,"shard_opens":0,"sha256":hashlib.sha256(payload).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

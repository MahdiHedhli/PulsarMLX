#!/usr/bin/env python3
"""Checkpoint-free validator for authoritative F017 v2 recovery summaries."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


RAW_SHA256 = "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a"
REVIEW_SHA256 = "dd235d3e006e8721cf2f3decb1ea822c76cbce65a1660941661e7f68816f76ea"


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    return raw, json.loads(raw, object_pairs_hook=reject_duplicates)


def load_recovery(root: Path):
    path = root / "scripts/research/f017_v2_antecedent_recovery.py"
    spec = importlib.util.spec_from_file_location("f017_v2_summary_integrity_recovery", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(root: Path) -> dict[str, Any]:
    evidence = root / "docs/architecture/reviews/evidence"
    raw_bytes, raw = read_json(evidence / "f017-v2-antecedent-recovery-result-v1.json")
    review_bytes, review = read_json(evidence / "f017-v2-antecedent-recovery-review-v1.json")
    if hashlib.sha256(raw_bytes).hexdigest() != RAW_SHA256:
        raise ValueError("historical raw recovery mutation")
    if hashlib.sha256(review_bytes).hexdigest() != REVIEW_SHA256:
        raise ValueError("accepted evidence-review mutation")
    recovery = load_recovery(root)
    surface = raw["antecedent_retention"]["pairwise_surface"]
    derived = recovery.derive_pairwise_summary(surface)
    accepted = review["pairwise_summary"]
    comparisons = {
        "membership minimum pair": (derived["membership"]["minimum_pair"], accepted["worst_membership_pair"]),
        "ordered minimum pair": (derived["ordered"]["minimum_pair"], accepted["worst_ordered_selected_pair"]),
        "global minimum pair": (derived["global_minimum_pair"], accepted["global_worst_pair"]),
        "minimum mathematical factor": (derived["minimum_mathematical_safety_factor"], accepted["minimum_mathematical_safety_factor"]),
        "minimum engineering factor": (derived["minimum_engineering_safety_factor"], accepted["minimum_engineering_safety_factor"]),
        "membership stable": (derived["route_set_stable"], accepted["membership_stable"]),
        "membership headroom": (derived["membership"]["engineering_headroom"], accepted["membership_engineering_headroom"]),
        "ordered stable": (derived["route_order_stable"], accepted["ordered_selected_stable"]),
        "ordered headroom": (derived["ordered"]["engineering_headroom"], accepted["ordered_selected_engineering_headroom"]),
        "overall mathematical": (derived["overall_mathematical_classification"], accepted["mathematical_classification"]),
        "overall engineering": (derived["overall_engineering_classification"], accepted["engineering_classification"]),
    }
    for label, (actual, expected) in comparisons.items():
        if recovery.canonical_json(actual) != recovery.canonical_json(expected):
            raise ValueError(f"accepted derived summary mismatch: {label}")
    ledger = json.loads((evidence / "f017-real-payload-access-ledger-v1.json").read_text())
    recovery_events = [
        event for event in ledger["events"]
        if event.get("attempt") == "analytical-antecedent-recovery-1"
    ]
    if len(recovery_events) != 1 or recovery_events[0]["cumulative_tensor_payloads_after_event"] != 57:
        raise ValueError("ledger integrity")
    if ledger["cumulative_tensor_payloads"] < 57:
        raise ValueError("ledger regression")
    expected = {
        "membership_worst_pair": [177, 98],
        "membership_minimum_safety_factor": 1.2497550469932908,
        "route_set_stable": True,
        "ordered_worst_pair": [233, 177],
        "ordered_minimum_safety_factor": 0.22551544432236478,
        "ordered_minimum_engineering_safety_factor": 0.11275772216118239,
        "route_order_stable": False,
        "overall_mathematical_classification": "NOT_MATHEMATICALLY_STABLE",
        "overall_engineering_classification": "NO_ENGINEERING_HEADROOM",
    }
    actual = {
        "membership_worst_pair": [derived["membership"]["minimum_pair"]["selected"], derived["membership"]["minimum_pair"]["challenger"]],
        "membership_minimum_safety_factor": derived["membership"]["minimum_mathematical_safety_factor"],
        "route_set_stable": derived["route_set_stable"],
        "ordered_worst_pair": [derived["ordered"]["minimum_pair"]["selected"], derived["ordered"]["minimum_pair"]["challenger"]],
        "ordered_minimum_safety_factor": derived["ordered"]["minimum_mathematical_safety_factor"],
        "ordered_minimum_engineering_safety_factor": derived["ordered"]["minimum_engineering_safety_factor"],
        "route_order_stable": derived["route_order_stable"],
        "overall_mathematical_classification": derived["overall_mathematical_classification"],
        "overall_engineering_classification": derived["overall_engineering_classification"],
    }
    if recovery.canonical_json(actual) != recovery.canonical_json(expected):
        raise ValueError("banked recovery regression")
    return {
        "result": "PASS",
        "raw_recovery_sha256": RAW_SHA256,
        "raw_immutable": True,
        "summary_authority": "derived_detail_summary",
        "detail_records_validated": 1991,
        "ledger_at_recovery": 57,
        "current_ledger": ledger["cumulative_tensor_payloads"],
        **actual,
        "checkpoint_access": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(validate(arguments.repository_root.resolve()), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

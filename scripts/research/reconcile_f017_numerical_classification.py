#!/usr/bin/env python3
"""Mechanically reconcile F017 R7-R10 greedy applicability metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

BASELINE_REF = "a572a2d560f5bc33f823e74c3bbc95ff2b164314"
CLASSIFICATION = "numerically_qualified_greedy_not_applicable"
APPLICABILITY = "not_applicable"
TARGETS = (
    "specs/017-rust-native-inference-runtime/fixtures/f017-r7-tier-b-result-v1.json",
    "docs/architecture/reviews/evidence/f017-r8-top8-shared-production-v1.json",
    "docs/architecture/reviews/evidence/f017-r9-mla-dsa-production-v1.json",
    "docs/architecture/reviews/evidence/f017-r10-complete-layer-production-v1.json",
)


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(data: bytes) -> dict[str, Any]:
    value = json.loads(data, object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError("evidence root must be an object")
    return value


def encode(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def numerical_payload(value: dict[str, Any]) -> bytes:
    retained = {
        key: item
        for key, item in value.items()
        if key
        not in {
            "classification",
            "greedy_applicability",
            "frozen_contract_version",
            "frozen_contract_versions",
        }
    }
    return json.dumps(retained, sort_keys=True, separators=(",", ":")).encode()


def baseline(root: Path, relative: str, ref: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def reconcile(relative: str, value: dict[str, Any]) -> dict[str, Any]:
    value["classification"] = CLASSIFICATION
    value["greedy_applicability"] = APPLICABILITY
    if relative.endswith("f017-r9-mla-dsa-production-v1.json"):
        value["frozen_contract_version"] = "f017-production-r9-tier-b-v2"
    if relative.endswith("f017-r10-complete-layer-production-v1.json"):
        value["frozen_contract_versions"] = [
            "f017-production-expert-tier-b-v1",
            "f017-production-r9-tier-b-v2",
            "f017-production-r10-tier-b-v2",
        ]
    return value


def reconcile_bytes(relative: str, old_bytes: bytes) -> bytes:
    old_classification = b'"classification": "numerically_qualified_greedy_identical"'
    new_classification = (
        b'"classification": "numerically_qualified_greedy_not_applicable"'
    )
    if old_bytes.count(old_classification) != 1:
        raise ValueError(f"expected one legacy classification in {relative}")
    result = old_bytes.replace(old_classification, new_classification, 1)
    if relative.endswith("f017-r7-tier-b-result-v1.json"):
        if result.count(b'"greedy_applicability": "not_applicable"') != 1:
            raise ValueError(f"R7 applicability is missing or ambiguous in {relative}")
        return result
    marker = new_classification + b",\n"
    if result.count(marker) != 1:
        raise ValueError(f"cannot place applicability beside classification in {relative}")
    result = result.replace(
        marker,
        marker + b'  "greedy_applicability": "not_applicable",\n',
        1,
    )
    if relative.endswith("f017-r9-mla-dsa-production-v1.json"):
        result = result.replace(
            b'"frozen_contract_version": "f017-production-r9-tier-b-v1"',
            b'"frozen_contract_version": "f017-production-r9-tier-b-v2"',
            1,
        )
    if relative.endswith("f017-r10-complete-layer-production-v1.json"):
        result = result.replace(
            b'"f017-production-r9-tier-b-v1",\n    "f017-production-r10-tier-b-v1"',
            b'"f017-production-r9-tier-b-v2",\n    "f017-production-r10-tier-b-v2"',
            1,
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--baseline-ref", default=BASELINE_REF)
    parser.add_argument("--report")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    records: list[dict[str, Any]] = []

    for relative in TARGETS:
        path = root / relative
        old_bytes = baseline(root, relative, args.baseline_ref)
        old = parse(old_bytes)
        current = parse(path.read_bytes())
        expected_bytes = reconcile_bytes(relative, old_bytes)
        expected = reconcile(relative, parse(old_bytes))
        if args.write:
            path.write_bytes(expected_bytes)
            current = parse(path.read_bytes())
        if current != expected:
            raise SystemExit(f"classification reconciliation drift: {relative}")
        old_payload = sha256(numerical_payload(old))
        new_payload = sha256(numerical_payload(current))
        if old_payload != new_payload:
            raise SystemExit(f"numerical payload changed: {relative}")
        records.append(
            {
                "path": relative,
                "old_sha256": sha256(old_bytes),
                "new_sha256": sha256(path.read_bytes()),
                "unchanged_numerical_payload_sha256": old_payload,
                "old_classification": old.get("classification"),
                "new_classification": current["classification"],
                "greedy_applicability": current["greedy_applicability"],
            }
        )

    report = {
        "schema": "pulsarmlx.f017.numerical-classification-reconciliation",
        "schema_version": "1.0.0",
        "baseline_ref": args.baseline_ref,
        "allowed_changes": [
            "classification",
            "greedy_applicability",
            "frozen_contract_version",
            "frozen_contract_versions",
        ],
        "numerical_payload_unchanged": True,
        "files": records,
    }
    report_bytes = encode(report)
    if args.report:
        report_path = root / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_bytes(report_bytes)
    else:
        print(report_bytes.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

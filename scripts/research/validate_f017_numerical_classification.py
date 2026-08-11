#!/usr/bin/env python3
"""Fail-closed validator for F017 numerical classification metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_record(record: dict[str, Any]) -> None:
    classification = record.get("classification")
    applicability = record.get("greedy_applicability")
    identity = record.get("greedy_identity")

    if classification == "numerically_qualified_greedy_not_applicable":
        if applicability != "not_applicable" or identity is not None:
            raise ValueError("greedy-not-applicable classification is inconsistent")
        return
    if classification == "numerically_qualified_greedy_identical":
        if applicability != "applicable":
            raise ValueError("greedy-identical classification requires applicability")
        if not isinstance(identity, dict):
            raise ValueError("greedy-identical classification requires identity evidence")
        if identity.get("top_k_ids_exact") is not True or identity.get("argmax_exact") is not True:
            raise ValueError("top-k and argmax identity must both be exact")
        return
    if classification == "numerically_qualified_greedy_divergent":
        if applicability != "applicable" or not isinstance(identity, dict):
            raise ValueError("greedy divergence requires applicable identity evidence")
        if identity.get("top_k_ids_exact") is not False and identity.get("argmax_exact") is not False:
            raise ValueError("greedy divergence requires a changed top-k or argmax")
        return
    if classification == "golden_identical":
        if applicability == "not_applicable" and identity is None:
            return
        if (
            applicability == "applicable"
            and isinstance(identity, dict)
            and identity.get("top_k_ids_exact") is True
            and identity.get("argmax_exact") is True
        ):
            return
        raise ValueError("golden-identical classification has inconsistent greedy evidence")
    if classification == "numerically_failed":
        return
    raise ValueError(f"unknown numerical classification: {classification!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    for value in args.paths:
        path = Path(value)
        record = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
        if not isinstance(record, dict):
            raise ValueError(f"{path}: evidence root must be an object")
        validate_record(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

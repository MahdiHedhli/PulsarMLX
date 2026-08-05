#!/usr/bin/env python3
"""Read-only verification boundary for Feature 002 evidence candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import generate_figures
import generate_tables
from publish_evidence import PublicationError, _read_candidate, sanitize_candidate


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_RAW_DIRECTORY = (
    REPOSITORY_ROOT / "fixtures" / "research" / "router-v1" / "evidence"
)
CLAIMS_LEDGER = REPOSITORY_ROOT / "docs" / "research" / "CLAIMS_LEDGER.md"
REVIEWER_INDEX = REPOSITORY_ROOT / "docs" / "research" / "REVIEWER_INDEX.md"


class VerificationError(ValueError):
    """A bounded package-verification failure."""


def verify_candidate(
    candidate_path: Path | str,
    *,
    expected_feature: str,
) -> dict[str, Any]:
    """Verify one candidate without modifying it or creating sidecar state."""

    path = Path(candidate_path)
    try:
        record, raw = _read_candidate(path)
        sanitized = sanitize_candidate(record)
    except PublicationError as error:
        raise VerificationError(str(error)) from error
    if sanitized["feature_id"] != expected_feature:
        raise VerificationError("candidate feature identity does not match")

    sanitized_bytes = (
        json.dumps(sanitized, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return {
        "passed": True,
        "experiment_id": sanitized["experiment_id"],
        "feature_id": sanitized["feature_id"],
        "candidate_sha256": hashlib.sha256(raw).hexdigest(),
        "sanitized_sha256": hashlib.sha256(sanitized_bytes).hexdigest(),
        "full_schema": "evidence_schema" in sanitized,
    }


def verify_candidate_collection(
    candidate: Path | str,
    *,
    expected_feature: str,
) -> list[dict[str, Any]]:
    """Verify a candidate file or a flat append-only candidate directory."""

    path = Path(candidate)
    if path.is_symlink():
        raise VerificationError("candidate collection cannot be a symbolic link")
    if path.is_file():
        return [verify_candidate(path, expected_feature=expected_feature)]
    if not path.is_dir():
        raise VerificationError("candidate collection is unavailable")
    files = sorted(path.glob("*.json"))
    if not files:
        raise VerificationError("candidate collection contains no JSON records")

    results = [
        verify_candidate(item, expected_feature=expected_feature)
        for item in files
    ]
    identities = [result["experiment_id"] for result in results]
    if len(identities) != len(set(identities)):
        raise VerificationError("candidate collection repeats an experiment identity")
    for item, identity in zip(files, identities, strict=True):
        if item.stem != identity:
            raise VerificationError("candidate filename and experiment identity differ")
    return results


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify_deterministic_regeneration(raw_directory: Path | str) -> dict[str, Any]:
    """Regenerate tables and figures twice and compare every output byte."""

    raw_path = Path(raw_directory)
    with tempfile.TemporaryDirectory(prefix="pulsarmlx-verify-a-") as first_temp:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-verify-b-") as second_temp:
            first = Path(first_temp)
            second = Path(second_temp)
            try:
                generate_tables.generate_tables(raw_path, first / "tables")
                generate_figures.generate_figures(raw_path, first / "figures")
                generate_tables.generate_tables(raw_path, second / "tables")
                generate_figures.generate_figures(raw_path, second / "figures")
            except (generate_tables.GenerationError, generate_figures.GenerationError) as error:
                raise VerificationError("deterministic regeneration failed") from error
            first_files = _tree_bytes(first)
            second_files = _tree_bytes(second)
            if not first_files or first_files != second_files:
                raise VerificationError("generated package is not byte-for-byte deterministic")
            return {
                "artifact_count": len(first_files),
                "artifact_sha256": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in sorted(first_files.items())
                },
            }


def verify_publication_index() -> dict[str, int]:
    """Check the committed claims-table and reviewer-index scaffolding."""

    try:
        claims_text = CLAIMS_LEDGER.read_text(encoding="utf-8")
        reviewer_text = REVIEWER_INDEX.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise VerificationError("publication index documentation is unavailable") from error

    header = "| Claim | Evidence files | Commit | Scope | Status | Caveat |"
    if header not in claims_text:
        raise VerificationError("claims ledger has an invalid table header")
    for heading in (
        "## Raw evidence",
        "## Generated tables",
        "## Generated figures",
        "## Claims and reproduction links",
    ):
        if heading not in reviewer_text:
            raise VerificationError("reviewer index is missing a required section")

    claim_rows = 0
    lines = claims_text.splitlines()
    try:
        header_index = lines.index(header)
    except ValueError as error:  # Defensive; the containment check above is public-facing.
        raise VerificationError("claims ledger table cannot be located") from error
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            if claim_rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            raise VerificationError("claims ledger row has the wrong field count")
        claim, evidence, commit, scope, status, caveat = cells
        if (
            not claim.startswith("F002-C")
            or not evidence
            or not commit
            or not scope
            or status not in {"verified", "provisional", "rejected", "unsupported"}
            or not caveat
        ):
            raise VerificationError("claims ledger row is incomplete or invalid")
        claim_rows += 1
    return {"claim_count": claim_rows}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only verification of a bounded Feature 002 evidence package."
    )
    parser.add_argument("--feature", required=True)
    parser.add_argument(
        "--candidate",
        type=Path,
        help=(
            "Candidate JSON file or directory. If omitted, verify the committed "
            "raw directory for the requested feature."
        ),
    )
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help=(
            "Verify the committed model-free evidence fixture, regenerate its "
            "artifacts twice, and check publication index scaffolding."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.fixture_only and arguments.candidate is not None:
        print(
            "verification_error: --fixture-only and --candidate are mutually exclusive",
            file=os.sys.stderr,
        )
        return 2
    candidate = arguments.candidate
    if arguments.fixture_only:
        candidate = FIXTURE_RAW_DIRECTORY
    elif candidate is None:
        candidate = Path("docs/research/raw") / arguments.feature.removeprefix("002-")
        if arguments.feature == "002-qwen-router-parity":
            candidate = Path("docs/research/raw/002-router-parity")
    try:
        results = verify_candidate_collection(
            candidate,
            expected_feature=arguments.feature,
        )
        regeneration: dict[str, Any] | None = None
        publication_index: dict[str, int] | None = None
        if arguments.fixture_only:
            if not results or any(not result["full_schema"] for result in results):
                raise VerificationError("fixture-only input is not full-schema evidence")
            regeneration = verify_deterministic_regeneration(candidate)
            publication_index = verify_publication_index()
    except VerificationError as error:
        print(f"verification_error: {error}", file=os.sys.stderr)
        return 1
    output: dict[str, Any] = {
        "fixture_only": arguments.fixture_only,
        "passed": True,
        "record_count": len(results),
        "records": results,
    }
    if regeneration is not None:
        output["regeneration"] = regeneration
    if publication_index is not None:
        output["publication_index"] = publication_index
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

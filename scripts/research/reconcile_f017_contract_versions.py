#!/usr/bin/env python3
"""Preserve F017 R9/R10 v1 and publish the reviewed v2 bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

BASELINE_REF = "a572a2d560f5bc33f823e74c3bbc95ff2b164314"
REMEDIATION_REF = "dda37f97e571c32ea469fba1e4e869e9dba8d415"
AMENDMENT_TIME = "2026-08-11T19:22:10Z"
CONTRACT_DIR = Path("specs/017-rust-native-inference-runtime/contracts")
R7_JSON = CONTRACT_DIR / "production-expert-tier-b-v1.json"
R9_V1_JSON = CONTRACT_DIR / "production-r9-tier-b-v1.json"
R10_V1_JSON = CONTRACT_DIR / "production-r10-tier-b-v1.json"
R9_V1_MD = CONTRACT_DIR / "production-r9-tier-b-v1.md"
R10_V1_MD = CONTRACT_DIR / "production-r10-tier-b-v1.md"
R9_V2_JSON = CONTRACT_DIR / "production-r9-tier-b-v2.json"
R10_V2_JSON = CONTRACT_DIR / "production-r10-tier-b-v2.json"
R9_V2_MD = CONTRACT_DIR / "production-r9-tier-b-v2.md"
R10_V2_MD = CONTRACT_DIR / "production-r10-tier-b-v2.md"
R7_AMENDMENT = CONTRACT_DIR / "production-expert-tier-b-v1-amendment-001.json"
R9_EVIDENCE = Path(
    "docs/architecture/reviews/evidence/f017-r9-mla-dsa-production-v1.json"
)
R10_EVIDENCE = Path(
    "docs/architecture/reviews/evidence/f017-r10-complete-layer-production-v1.json"
)
REPORT = Path(
    "docs/architecture/reviews/evidence/f017-contract-version-reconciliation-v2.json"
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
        raise ValueError("JSON root must be an object")
    return value


def encode(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_bytes(root: Path, ref: str, path: Path) -> bytes:
    return subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


def contract_numeric_payload(value: dict[str, Any]) -> bytes:
    allowed_metadata = {
        "contract_version",
        "status",
        "required_contracts",
        "classification",
        "greedy_applicability",
        "selection_evidence",
        "versioning",
        "review_status",
    }
    retained = {k: v for k, v in value.items() if k not in allowed_metadata}
    return json.dumps(retained, sort_keys=True, separators=(",", ":")).encode()


def evidence_numeric_payload(value: dict[str, Any]) -> bytes:
    allowed_metadata = {
        "frozen_contract_version",
        "frozen_contract_versions",
        "classification",
        "greedy_applicability",
    }
    retained = {k: v for k, v in value.items() if k not in allowed_metadata}
    return json.dumps(retained, sort_keys=True, separators=(",", ":")).encode()


def r9_v2(value: dict[str, Any]) -> dict[str, Any]:
    value["contract_version"] = "f017-production-r9-tier-b-v2"
    value["status"] = "reviewed_semantic_tightening_of_frozen_v1"
    value["classification"] = {
        "pass": "numerically_qualified_greedy_not_applicable",
        "exact_pass": "golden_identical",
        "selection_divergence": "numerically_failed",
        "failure": "numerically_failed",
    }
    value["greedy_applicability"] = "not_applicable"
    value["selection_evidence"] = (
        "DSA/index selections are exact internal architecture evidence; "
        "no model-token top-k or argmax exists in R9"
    )
    value["versioning"] = {
        "supersedes": "f017-production-r9-tier-b-v1",
        "reason": (
            "reviewed semantic tightening: internal DSA/index selection "
            "divergence is a hard numerical failure and model-token greedy "
            "selection is not applicable"
        ),
        "thresholds_unchanged": True,
        "candidate_outputs_unchanged": True,
        "rerun_required": False,
    }
    value["review_status"] = "accepted_after_contract_version_cleanup"
    return value


def r10_v2(value: dict[str, Any]) -> dict[str, Any]:
    value["contract_version"] = "f017-production-r10-tier-b-v2"
    value["status"] = "reviewed_semantic_tightening_of_frozen_v1"
    value["required_contracts"] = [
        "f017-production-expert-tier-b-v1",
        "f017-production-r9-tier-b-v2",
    ]
    value["classification"] = {
        "pass": "numerically_qualified_greedy_not_applicable",
        "exact_pass": "golden_identical",
        "routing_divergence": "numerically_failed",
        "failure": "numerically_failed",
    }
    value["greedy_applicability"] = "not_applicable"
    value["selection_evidence"] = (
        "router expert IDs are exact internal architecture evidence; "
        "no model-token top-k or argmax exists in R10"
    )
    value["versioning"] = {
        "supersedes": "f017-production-r10-tier-b-v1",
        "reason": (
            "reviewed semantic tightening: internal expert-routing "
            "divergence is a hard numerical failure and model-token greedy "
            "selection is not applicable"
        ),
        "thresholds_unchanged": True,
        "candidate_outputs_unchanged": True,
        "rerun_required": False,
    }
    value["review_status"] = "accepted_after_contract_version_cleanup"
    return value


R9_V2_MD_TEXT = """# Feature 017 production R9 Tier-B contract v2

Status: **reviewed semantic tightening of immutable v1**. This contract
supersedes `f017-production-r9-tier-b-v1` for current evidence bindings. The
historical v1 remains byte-for-byte preserved.

The scope, oracle, exact scaffold, required repeats, numerical thresholds,
operand-conditioned matvec rule, exact requirements, and retuning policy are
unchanged from v1. The observed R9 result also remains unchanged and satisfies
both versions, so no numerical rerun is required.

## Semantic tightening

- A passing production result is
  `numerically_qualified_greedy_not_applicable` because R9 defines no
  model-token top-k or argmax decision.
- Exact DSA/indexer selections remain separate architecture evidence.
- Any `selection_divergence` is `numerically_failed`; it is not a qualified
  greedy divergence.
- `golden_identical` remains available for a bit-identical production result.

This is a failure-semantics tightening, not numerical retuning. The fixed
intermediate and final error envelopes, deterministic-repeat requirement,
signed-zero rule, fallback/error gates, and lifecycle requirements are exactly
the v1 values.
"""


R10_V2_MD_TEXT = """# Feature 017 production R10 Tier-B contract v2

Status: **reviewed semantic tightening of immutable v1**. This contract
supersedes `f017-production-r10-tier-b-v1` and inherits
`f017-production-r9-tier-b-v2`. Both historical v1 contracts remain
byte-for-byte preserved.

The scope, oracle, exact scaffold, required repeats, router thresholds,
intermediate/final numerical thresholds, exact requirements, and retuning
policy are unchanged from v1. The banked R10 candidate output and metrics
satisfy both versions, so no numerical rerun is required.

## Semantic tightening

- A passing production result is
  `numerically_qualified_greedy_not_applicable` because R10 defines no
  model-token top-k or argmax decision.
- Exact routed expert IDs remain separate architecture evidence.
- Any `routing_divergence` is `numerically_failed`; it is not a qualified
  greedy divergence.
- `golden_identical` remains available for a bit-identical production result.

This is a failure-semantics tightening, not numerical retuning. Every numeric
bound and every observed output remains unchanged.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]

    original = {
        path: git_bytes(root, BASELINE_REF, path)
        for path in (R7_JSON, R9_V1_JSON, R10_V1_JSON, R9_V1_MD, R10_V1_MD)
    }
    remediated = {
        path: git_bytes(root, REMEDIATION_REF, path)
        for path in (R7_JSON, R9_V1_JSON, R10_V1_JSON, R9_EVIDENCE, R10_EVIDENCE)
    }

    r9_new = r9_v2(parse(original[R9_V1_JSON]))
    r10_new = r10_v2(parse(original[R10_V1_JSON]))
    if contract_numeric_payload(parse(original[R9_V1_JSON])) != contract_numeric_payload(r9_new):
        raise SystemExit("R9 v2 numerical contract payload changed")
    if contract_numeric_payload(parse(original[R10_V1_JSON])) != contract_numeric_payload(r10_new):
        raise SystemExit("R10 v2 numerical contract payload changed")

    r9_evidence_bytes = remediated[R9_EVIDENCE].replace(
        b'"frozen_contract_version": "f017-production-r9-tier-b-v1"',
        b'"frozen_contract_version": "f017-production-r9-tier-b-v2"',
        1,
    )
    if r9_evidence_bytes == remediated[R9_EVIDENCE]:
        raise SystemExit("R9 evidence v1 binding was not found exactly once")
    r10_evidence_bytes = remediated[R10_EVIDENCE].replace(
        b'"f017-production-r9-tier-b-v1",\n    "f017-production-r10-tier-b-v1"',
        b'"f017-production-r9-tier-b-v2",\n    "f017-production-r10-tier-b-v2"',
        1,
    )
    if r10_evidence_bytes == remediated[R10_EVIDENCE]:
        raise SystemExit("R10 evidence v1 bindings were not found exactly once")
    r9_evidence = parse(r9_evidence_bytes)
    r10_evidence = parse(r10_evidence_bytes)
    if evidence_numeric_payload(parse(git_bytes(root, BASELINE_REF, R9_EVIDENCE))) != evidence_numeric_payload(r9_evidence):
        raise SystemExit("R9 evidence numerical payload changed")
    if evidence_numeric_payload(parse(git_bytes(root, BASELINE_REF, R10_EVIDENCE))) != evidence_numeric_payload(r10_evidence):
        raise SystemExit("R10 evidence numerical payload changed")

    amendment = {
        "schema": "pulsarmlx.f017.contract-amendment",
        "schema_version": "1.0.0",
        "amendment_id": "f017-production-expert-tier-b-v1-amendment-001",
        "contract_id": "f017-production-expert-tier-b-v1",
        "amendment_time_utc": AMENDMENT_TIME,
        "source_commit": REMEDIATION_REF,
        "reviewer_finding": "f017-r7-r8-greedy-applicability-vocabulary",
        "original_contract_sha256": digest(original[R7_JSON]),
        "amended_contract_sha256": digest(remediated[R7_JSON]),
        "fields_changed": [
            {
                "path": "scope.greedy_applicability",
                "old": "not_applicable_at_r7",
                "new": "not_applicable",
                "category": "vocabulary_normalization",
            },
            {
                "path": "classification_names",
                "old": [
                    "golden_identical",
                    "numerically_qualified_greedy_identical",
                    "numerically_qualified_greedy_divergent",
                    "numerically_failed",
                ],
                "new": [
                    "golden_identical",
                    "numerically_qualified_greedy_not_applicable",
                    "numerically_qualified_greedy_identical",
                    "numerically_qualified_greedy_divergent",
                    "numerically_failed",
                ],
                "category": "vocabulary_extension",
            },
        ],
        "thresholds_unchanged": True,
        "numerical_payload_unchanged": True,
        "accepted_numerical_bindings_remain_valid": True,
        "contract_version_bumped": False,
        "reason_no_version_bump": (
            "reviewer requested an explicit vocabulary amendment for the "
            "accepted R7 v1 numerical contract; no failure semantics or "
            "numerical threshold changed"
        ),
        "review_packet": "docs/architecture/reviews/f017-r7-numerical-review-packet.md",
        "checkpoint_accessed": False,
    }

    outputs = {
        R9_V1_JSON: original[R9_V1_JSON],
        R10_V1_JSON: original[R10_V1_JSON],
        R9_V1_MD: original[R9_V1_MD],
        R10_V1_MD: original[R10_V1_MD],
        R9_V2_JSON: encode(r9_new),
        R10_V2_JSON: encode(r10_new),
        R9_V2_MD: R9_V2_MD_TEXT.encode(),
        R10_V2_MD: R10_V2_MD_TEXT.encode(),
        R7_AMENDMENT: encode(amendment),
        R9_EVIDENCE: r9_evidence_bytes,
        R10_EVIDENCE: r10_evidence_bytes,
    }

    report = {
        "schema": "pulsarmlx.f017.contract-version-reconciliation",
        "schema_version": "2.0.0",
        "baseline_ref": BASELINE_REF,
        "remediation_ref": REMEDIATION_REF,
        "r7_amendment": {
            "artifact": R7_AMENDMENT.as_posix(),
            "original_contract_sha256": digest(original[R7_JSON]),
            "amended_contract_sha256": digest(remediated[R7_JSON]),
            "thresholds_unchanged": True,
            "numerical_payload_unchanged": True,
        },
        "r8_audit": {
            "independent_immutable_contract": False,
            "contract_inherited": "f017-production-expert-tier-b-v1",
            "version_or_amendment_required": False,
            "reason": "R8 did not publish or mutate an independent retuning-policy contract",
        },
        "contracts": [
            {
                "boundary": "R9",
                "v1_path": R9_V1_JSON.as_posix(),
                "v1_sha256": digest(original[R9_V1_JSON]),
                "mutated_v1_sha256_at_remediation_ref": digest(remediated[R9_V1_JSON]),
                "v2_path": R9_V2_JSON.as_posix(),
                "v2_sha256": digest(outputs[R9_V2_JSON]),
                "mutated_v1_field_diff": [
                    {
                        "path": "classification.pass",
                        "category": "vocabulary_normalization",
                        "old": "numerically_qualified_greedy_identical",
                        "new": "numerically_qualified_greedy_not_applicable",
                    },
                    {
                        "path": "classification.selection_divergence",
                        "category": "semantic_tightening",
                        "old": "numerically_qualified_greedy_divergent",
                        "new": "numerically_failed",
                    },
                    {
                        "path": "greedy_applicability",
                        "category": "vocabulary_normalization",
                        "old": "DSA/index selections only; no vocabulary argmax in R9",
                        "new": "not_applicable",
                    },
                    {
                        "path": "selection_evidence",
                        "category": "metadata_provenance",
                        "old": None,
                        "new": "explicit internal-selection scope statement",
                    },
                ],
                "formatting_only_changes": [],
                "semantic_tightening": {
                    "selection_divergence": {
                        "old": "numerically_qualified_greedy_divergent",
                        "new": "numerically_failed",
                    }
                },
                "thresholds_unchanged": True,
            },
            {
                "boundary": "R10",
                "v1_path": R10_V1_JSON.as_posix(),
                "v1_sha256": digest(original[R10_V1_JSON]),
                "mutated_v1_sha256_at_remediation_ref": digest(remediated[R10_V1_JSON]),
                "v2_path": R10_V2_JSON.as_posix(),
                "v2_sha256": digest(outputs[R10_V2_JSON]),
                "mutated_v1_field_diff": [
                    {
                        "path": "classification.pass",
                        "category": "vocabulary_normalization",
                        "old": "numerically_qualified_greedy_identical",
                        "new": "numerically_qualified_greedy_not_applicable",
                    },
                    {
                        "path": "classification.routing_divergence",
                        "category": "semantic_tightening",
                        "old": "numerically_qualified_greedy_divergent",
                        "new": "numerically_failed",
                    },
                    {
                        "path": "greedy_applicability",
                        "category": "vocabulary_normalization",
                        "old": None,
                        "new": "not_applicable",
                    },
                    {
                        "path": "selection_evidence",
                        "category": "metadata_provenance",
                        "old": None,
                        "new": "explicit internal-routing scope statement",
                    },
                ],
                "formatting_only_changes": [],
                "semantic_tightening": {
                    "routing_divergence": {
                        "old": "numerically_qualified_greedy_divergent",
                        "new": "numerically_failed",
                    }
                },
                "thresholds_unchanged": True,
            },
        ],
        "evidence": [
            {
                "boundary": "R9",
                "path": R9_EVIDENCE.as_posix(),
                "old_sha256": digest(remediated[R9_EVIDENCE]),
                "new_sha256": digest(outputs[R9_EVIDENCE]),
                "old_contract_binding": "f017-production-r9-tier-b-v1",
                "new_contract_binding": "f017-production-r9-tier-b-v2",
                "numerical_metrics_unchanged": True,
                "candidate_outputs_unchanged": True,
            },
            {
                "boundary": "R10",
                "path": R10_EVIDENCE.as_posix(),
                "old_sha256": digest(remediated[R10_EVIDENCE]),
                "new_sha256": digest(outputs[R10_EVIDENCE]),
                "old_contract_bindings": [
                    "f017-production-expert-tier-b-v1",
                    "f017-production-r9-tier-b-v1",
                    "f017-production-r10-tier-b-v1",
                ],
                "new_contract_bindings": [
                    "f017-production-expert-tier-b-v1",
                    "f017-production-r9-tier-b-v2",
                    "f017-production-r10-tier-b-v2",
                ],
                "numerical_metrics_unchanged": True,
                "candidate_outputs_unchanged": True,
            },
        ],
        "thresholds_unchanged": True,
        "numerical_metrics_unchanged": True,
        "checkpoint_accessed": False,
    }
    outputs[REPORT] = encode(report)

    if args.write:
        for path, data in outputs.items():
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    else:
        for path, data in outputs.items():
            current = (root / path).read_bytes() if (root / path).exists() else None
            if current != data:
                raise SystemExit(f"generated contract-version artifact drift: {path}")

    if (root / R9_V1_JSON).read_bytes() != original[R9_V1_JSON]:
        raise SystemExit("immutable R9 v1 was not restored byte-for-byte")
    if (root / R10_V1_JSON).read_bytes() != original[R10_V1_JSON]:
        raise SystemExit("immutable R10 v1 was not restored byte-for-byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

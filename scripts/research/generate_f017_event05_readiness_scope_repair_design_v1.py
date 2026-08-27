#!/usr/bin/env python3
"""Generate append-only scope-separation design successors."""
from __future__ import annotations

import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def main() -> int:
    design = json.loads((EVIDENCE / "f017-event05-readiness-interface-design-authority-v1.json").read_text())
    design.update({
        "schema":"pulsarmlx.f017.event05-readiness-interface-design-authority/1.1.0",
        "supersedes":"docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v1.json",
        "canonical_contract":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v2.json",
        "prepared_fixture":{"authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
            "schema_valid":True, "live_authorizer_acceptance":False,
            "validation_only_validator_acceptance":True,
            "review_fixture_verdicts_are_final_authority":False},
        "scope_separation":{"prepared_and_final_are_distinct_predicate_sets":True,
            "live_approval_requires_final_scope":True, "prepared_manifest_final_authority":False,
            "prepared_reviewer_fixtures_final_authority":False,
            "final_review_requires_exact_schema_model_head_response_and_zero_open_findings":True},
        "result":"READY_FOR_SCOPE_REPAIR_IMPLEMENTATION_REVIEW",
    })
    (EVIDENCE / "f017-event05-readiness-interface-design-authority-v2.json").write_bytes(canonical_bytes(design))

    plan = json.loads((EVIDENCE / "f017-event05-readiness-interface-mutation-plan-v1.json").read_text())
    plan.update({
        "schema":"pulsarmlx.f017.event05-readiness-interface-mutation-plan/1.1.0",
        "supersedes":"docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v1.json",
        "preregistered_before_scope_repair":True,
        "minimum_substantive_cases":225,
        "minimum_planned_cases":231,
    })
    plan["categories"]["production_boundary"] = 5
    (EVIDENCE / "f017-event05-readiness-interface-mutation-plan-v2.json").write_bytes(canonical_bytes(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

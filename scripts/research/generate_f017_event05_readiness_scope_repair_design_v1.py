#!/usr/bin/env python3
"""Generate append-only scope-separation design successors."""
from __future__ import annotations

import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def main() -> int:
    design = json.loads((EVIDENCE / "f017-event05-readiness-interface-design-authority-v2.json").read_text())
    design.update({
        "schema":"pulsarmlx.f017.event05-readiness-interface-design-authority/1.2.0",
        "supersedes":"docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v2.json",
        "canonical_contract":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v3.json",
        "prepared_fixture":{"authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
            "schema_valid":True, "live_authorizer_acceptance":False,
            "validation_only_validator_acceptance":True,
            "review_fixture_verdicts_are_final_authority":False},
        "scope_separation":{"prepared_and_final_are_distinct_predicate_sets":True,
            "live_approval_requires_final_scope":True, "prepared_manifest_final_authority":False,
            "prepared_reviewer_fixtures_final_authority":False,
            "final_review_requires_exact_schema_model_head_response_and_zero_open_findings":True},
        "review_provenance_enforcement":{
            "reviewed_head":"REAL_COMMIT_DESCENDING_FROM_MEASURED_IMPLEMENTATION_HEAD",
            "exact_response":"REPOSITORY_RELATIVE_PATH_WITH_VERIFIED_SHA256",
            "final_scope_generated_mutations":20,
        },
        "result":"READY_FOR_FINAL_REVIEW_PROVENANCE_IMPLEMENTATION_REVIEW",
    })
    (EVIDENCE / "f017-event05-readiness-interface-design-authority-v3.json").write_bytes(canonical_bytes(design))

    plan = json.loads((EVIDENCE / "f017-event05-readiness-interface-mutation-plan-v2.json").read_text())
    plan.update({
        "schema":"pulsarmlx.f017.event05-readiness-interface-mutation-plan/1.2.0",
        "supersedes":"docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v2.json",
        "preregistered_before_final_scope_provenance_repair":True,
        "minimum_substantive_cases":245,
        "minimum_planned_cases":251,
    })
    plan["categories"]["final_review_bindings"] = 20
    (EVIDENCE / "f017-event05-readiness-interface-mutation-plan-v3.json").write_bytes(canonical_bytes(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

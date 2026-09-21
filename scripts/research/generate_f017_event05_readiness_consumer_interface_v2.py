#!/usr/bin/env python3
"""Generate the scope-separated Event-05 readiness consumer interface."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v2.json"
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v3.json"


def build() -> dict:
    value = json.loads(SOURCE.read_text())
    value["schema"] = "pulsarmlx.f017.corrected-oracle-event05-readiness-consumer-interface/1.2.0"
    value["supersedes"] = str(SOURCE.relative_to(ROOT))
    value["prepared_fixture_scope"] = "VALIDATION_ONLY_PREPARED_ENFORCED_AND_LIVE_PROHIBITED"
    prepared = copy.deepcopy(value["exact_prepared_predicates"])
    prepared.update({
        "authority_scope":"VALIDATION_ONLY_PREPARED",
        "declaration":"F017_CORRECTED_ORACLE_EVENT05_EXECUTION_READINESS: VALIDATION_ONLY_PREPARED",
        "graph_verdict":"F017_EVENT05_READINESS_AUTHORITY_INTERFACE_GRAPH: VALIDATION_ONLY_PREPARED",
        "gemini_verdict":"VALIDATION_ONLY_PREPARED",
        "opus_verdict":"VALIDATION_ONLY_PREPARED",
        "ready_for_corrected_full_checkpoint_oracle_event_05_execution_go":False,
        "exact_next_safe_action":"COMPLETE_INDEPENDENT_REVIEW_BEFORE_FINAL_READINESS_BANKING",
    })
    value["exact_prepared_predicates"] = prepared
    value["scope_policy"] = {
        "FINAL_EVENT05_EXECUTION_READINESS":{
            "final_authority":True,
            "live_candidate_rendering_permitted_after_fresh_go":True,
            "reviewed_head_binding":"REAL_COMMIT_DESCENDING_FROM_MEASURED_IMPLEMENTATION_HEAD",
            "exact_response_binding":"REPOSITORY_RELATIVE_PATH_AND_SHA256_REQUIRED",
            "manifest_schema":"pulsarmlx.f017.event05-readiness-interface-runtime-authority-manifest/1.0.0",
            "gemini_schema":"pulsarmlx.f017.event05-readiness-interface-gemini-whole-domain-repair-confirmation/1.0.0",
            "opus_schema":"pulsarmlx.f017.event05-readiness-interface-opus-implementation-result/1.1.0",
        },
        "VALIDATION_ONLY_PREPARED":{
            "final_authority":False,
            "live_authority_permitted":False,
            "manifest_schema":"pulsarmlx.f017.event05-readiness-interface-prepared-runtime-authority-manifest/1.2.0",
            "gemini_schema":"pulsarmlx.f017.event05-readiness-interface-prepared-gemini-fixture/1.0.0",
            "opus_schema":"pulsarmlx.f017.event05-readiness-interface-prepared-opus-fixture/1.0.0",
        },
    }
    value["review_protocols"]["runtime_enforcement"] = "EXACT_SCHEMA_MODEL_HEAD_RESPONSE_AND_ZERO_OPEN_FINDINGS"
    return value


def main() -> int:
    OUTPUT.write_bytes(canonical_bytes(build()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

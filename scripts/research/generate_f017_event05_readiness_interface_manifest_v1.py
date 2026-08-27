#!/usr/bin/env python3
"""Generate/check the repaired Event-05 readiness-interface design manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-authority-manifest-v4.json"
ARTIFACTS = (
    ("terminal_pre_mint_failure", "docs/architecture/reviews/evidence/f017-event05-v11-terminal-failure-authority-manifest-v2.json"),
    ("accepted_predecessor_authority_manifest", "docs/architecture/reviews/evidence/f017-event05-result-envelope-authority-manifest-v3.json"),
    ("accepted_implementation_measurement", "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v4.json"),
    ("accepted_scientific_access", "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v4.json"),
    ("accepted_numerical_contract_v4", "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json"),
    ("accepted_result_authority_v11", "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json"),
    ("accepted_full_native_ci", "docs/architecture/reviews/evidence/f017-v11-event05-full-native-ci-v2.json"),
    ("mismatch_reproduction", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-mismatch-reproduction-v1.json"),
    ("versioning_decision", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-versioning-decision-v1.json"),
    ("consumer_interface", "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v2.json"),
    ("approval_interface", "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-approval-interface-v1.json"),
    ("design_authority", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v2.json"),
    ("mutation_plan", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v2.json"),
    ("review_protocol", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-review-protocol-v1.json"),
    ("historical_tombstone", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-historical-tombstone-v1.json"),
    ("design_validator", "scripts/research/validate_f017_event05_readiness_interface_design_v1.py"),
    ("design_tests", "scripts/research/tests/test_f017_event05_readiness_interface_design_v1.py"),
    ("claim_ledger", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-claim-ledger-v1.json"),
    ("challenge_ledger", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-challenge-ledger-v5.json"),
    ("support_ledger", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-support-ledger-v4.json"),
    ("arbiter_ledger", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-arbiter-ledger-v2.json"),
    ("graph_state", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-graph-state-v6.json"),
    ("r1_repair_receipt", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-node-r1-repair-receipt-v2.json"),
    ("r2_repair_receipt", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-node-r2-repair-receipt-v2.json"),
    ("r3_receipt", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-node-r3-cycle-03-receipt-v2.json"),
    ("r4_receipt", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-node-r4-receipt-v1.json"),
    ("opus_design_exact_response", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-opus-design-cycle-01-exact-response.md"),
    ("opus_design_normalized_result", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-opus-design-cycle-02-normalized-result.json"),
    ("opus_implementation_cycle_02_exact_response", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-opus-implementation-cycle-02-exact-response.json"),
    ("opus_implementation_cycle_02_normalized_result", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-opus-implementation-cycle-02-normalized-result.json"),
    ("gemini_design_cycle_03_exact_response", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-gemini-design-cycle-03-exact-response.md"),
    ("gemini_design_cycle_03_normalized_result", "docs/architecture/reviews/evidence/f017-event05-readiness-interface-gemini-design-cycle-03-normalized-result.json"),
    ("inert_go_template", "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-execution-go-template-v11-v2.json"),
)


def _git(*args: str, binary: bool = False):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=not binary).strip() if not binary else subprocess.check_output(["git", *args], cwd=ROOT)


def generate(binding_head: str | None = None) -> dict:
    head = binding_head or _git("rev-parse", "HEAD")
    tree = _git("rev-parse", f"{head}^{{tree}}")
    artifacts = []
    for role, path in ARTIFACTS:
        raw = _git("show", f"{head}:{path}", binary=True)
        if (ROOT / path).read_bytes() != raw:
            raise ValueError(f"readiness manifest working-tree drift: {path}")
        artifacts.append({"role":role, "path":path, "sha256":hashlib.sha256(raw).hexdigest()})
    return {
        "schema":"pulsarmlx.f017.event05-readiness-interface-authority-manifest/1.3.0",
        "supersedes":"docs/architecture/reviews/evidence/f017-event05-readiness-interface-authority-manifest-v3.json",
        "graph_id":"F017-EVENT05-READINESS-AUTHORITY-INTERFACE-GRAPH-01",
        "status":"DESIGN_ACCEPTED_IMPLEMENTATION_MEASURED",
        "authority_entry_head":head, "authority_entry_tree":tree,
        "binding_head":head, "binding_tree":tree,
        "artifacts":artifacts, "binding_count":len(artifacts),
        "self_exclusion":"THIS_MANIFEST_DOES_NOT_HASH_BIND_ITS_OWN_BYTES",
        "event_04_retry":False, "event_05_retry":False, "event_05_executed":False,
        "live_event_05_authorization_created":False, "original_checkpoint_access":0,
        "p1_attempt_2_executed":False, "historical_master_ledger":175,
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    head = json.loads(OUTPUT.read_text())["binding_head"] if args.check and OUTPUT.is_file() else None
    raw = json.dumps(generate(head), sort_keys=True, separators=(",", ":")) + "\n"
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text() != raw:
            raise ValueError("readiness interface authority manifest drift")
    else:
        OUTPUT.write_text(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

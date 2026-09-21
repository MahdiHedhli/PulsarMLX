#!/usr/bin/env python3
"""Generate/check the exact Git-byte V11 Event-05 implementation measurement."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json"
PATHS = (
    "scripts/research/f017_corrected_oracle_primary_numerics_v3.py",
    "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py",
    "scripts/research/f017_corrected_oracle_authorization_v11.py",
    "scripts/research/f017_event05_readiness_authority_v1.py",
    "scripts/research/f017_event05_candidate_builder_v1.py",
    "scripts/research/generate_f017_event05_readiness_consumer_interface_v2.py",
    "scripts/research/generate_f017_event05_readiness_declaration_v1.py",
    "scripts/research/qualify_f017_event05_readiness_interface_v1.py",
    "scripts/research/validate_f017_corrected_oracle_access_v11.py",
    "scripts/research/execute_f017_corrected_oracle_event_v11.py",
    "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py",
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py",
    "scripts/research/f017_corrected_oracle_primary_target_source_v11.py",
    "scripts/research/f017_corrected_oracle_secondary_target_source_v11.py",
    "scripts/research/f017_result_envelope_v11.py",
    "scripts/research/f017_result_artifacts_v11.py",
    "scripts/research/f017_result_bundle_builder_v11.py",
    "scripts/research/f017_result_bundle_authority_v11.py",
    "scripts/research/f017_binary_comparator_v11.py",
    "scripts/research/f017_binary_comparison_authority_v11.py",
    "scripts/research/f017_canonical_serialization_v10.py",
    "scripts/research/f017_bounded_artifact_decode_v1.py",
    "scripts/research/f017_accounting_root_continuity_v1.py",
    "scripts/research/f017_checkpoint_identity_producer_v10.py",
    "scripts/research/f017_descriptor_lease_manager_v10.py",
    "scripts/research/f017_memory_gate_v9.py",
    "scripts/research/f017_event04_tensor_plan_v9.py",
    "scripts/research/glm52_tensor_store.py",
    "scripts/research/qualify_f017_event04_diagnostic_v11.py",
    "scripts/research/qualify_f017_v11_full_geometry_v1.py",
    "scripts/research/f017_v11_full_geometry_fixture.py",
    "scripts/research/qualify_f017_v11_failure_campaign_v1.py",
    "scripts/research/rehearse_f017_event05_v11.py",
    "scripts/research/validate_f017_v11_execution_authority_v1.py",
    "scripts/research/validate_f017_result_authority_v11.py",
    "scripts/research/validate_f017_result_envelope_design_v11.py",
)


def _git(*arguments: str, binary: bool = False):
    return subprocess.check_output(["git", *arguments], cwd=ROOT,
        text=not binary).strip() if not binary else subprocess.check_output(["git", *arguments], cwd=ROOT)


def generate(head: str | None = None) -> dict:
    head = head or _git("rev-parse", "HEAD")
    tree = _git("rev-parse", f"{head}^{{tree}}")
    records = []
    for path in PATHS:
        raw = _git("show", f"{head}:{path}", binary=True)
        current = (ROOT / path).read_bytes()
        if raw != current:
            raise ValueError(f"working tree differs from measurement head: {path}")
        records.append({
            "path":path,
            "git_blob_sha":_git("rev-parse", f"{head}:{path}"),
            "sha256":hashlib.sha256(raw).hexdigest(),
        })
    return {
        "schema":"pulsarmlx.f017.v11-result-envelope-implementation-measurement/8.0.0",
        "supersedes":"docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v7.json",
        "branch":"feat/017-rust-native-inference-runtime",
        "implementation_head":head,
        "implementation_tree":tree,
        "measured_path_count":len(records),
        "measured_paths":records,
        "historical_primary_v2_sha256":"657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767",
        "historical_secondary_v2_sha256":"e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791",
        "event_04_retry":False,
        "event_05_executed":False,
        "live_event_05_authorization_created":False,
        "original_checkpoint_access":0,
        "historical_master_ledger":175,
        "result":"PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    measured_head = None
    if arguments.check and OUTPUT.is_file():
        measured_head = json.loads(OUTPUT.read_text())["implementation_head"]
    raw = json.dumps(generate(measured_head), sort_keys=True, separators=(",", ":")) + "\n"
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_text() != raw:
            raise ValueError("V11 implementation measurement drift")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True); OUTPUT.write_text(raw)
    return 0


if __name__ == "__main__": raise SystemExit(main())

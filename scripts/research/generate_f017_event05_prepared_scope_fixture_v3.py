#!/usr/bin/env python3
"""Bank the non-live prepared-scope production-boundary fixture."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile

from f017_bounded_artifact_decode_v1 import read_artifact
from f017_canonical_serialization_v10 import canonical_bytes
from f017_event05_readiness_authority_v1 import CONTRACT
from validate_f017_corrected_oracle_access_v11 import render_validation_only_operator_go_candidate

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
MEASUREMENT = EVIDENCE / "f017-v11-result-envelope-implementation-measurement-v7.json"
SCIENTIFIC = CONTRACTS / "f017-corrected-full-checkpoint-oracle-scientific-access-v11-v7.json"
NUMERICAL = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json"
RESULT = CONTRACTS / "f017-corrected-oracle-result-authority-v11-v2.json"
FULL_NATIVE = EVIDENCE / "f017-event05-readiness-interface-full-native-ci-v6.json"
EVIDENCE_ONLY = EVIDENCE / "f017-event05-v11-terminal-failure-evidence-only-ci-v2.json"
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.write_bytes(canonical_bytes(value))


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def main() -> int:
    contract = read_artifact(CONTRACT)
    measurement = read_artifact(MEASUREMENT)
    gemini = EVIDENCE / "f017-event05-readiness-interface-prepared-gemini-fixture-v3.json"
    opus = EVIDENCE / "f017-event05-readiness-interface-prepared-opus-fixture-v4.json"
    _write(gemini, {"schema":contract["scope_policy"]["VALIDATION_ONLY_PREPARED"]["gemini_schema"],
        "authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
        "live_authority_permitted":False, "verdict":"VALIDATION_ONLY_PREPARED"})
    _write(opus, {"schema":contract["scope_policy"]["VALIDATION_ONLY_PREPARED"]["opus_schema"],
        "authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
        "live_authority_permitted":False, "verdict":"VALIDATION_ONLY_PREPARED"})
    bindings = (
        ("implementation_measurement", MEASUREMENT), ("scientific_access", SCIENTIFIC),
        ("numerical_contract_v4", NUMERICAL), ("result_authority", RESULT),
        ("full_native_ci", FULL_NATIVE), ("evidence_only_ci", EVIDENCE_ONLY),
        ("gemini_readiness_interface_challenge", gemini),
        ("opus_readiness_interface_implementation_arbiter", opus),
    )
    manifest = EVIDENCE / "f017-event05-readiness-interface-prepared-runtime-authority-manifest-v5.json"
    _write(manifest, {"schema":contract["scope_policy"]["VALIDATION_ONLY_PREPARED"]["manifest_schema"],
        "supersedes":"docs/architecture/reviews/evidence/f017-event05-readiness-interface-prepared-runtime-authority-manifest-v4.json",
        "authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
        "live_authority_permitted":False, "implementation_head":measurement["implementation_head"],
        "implementation_tree":measurement["implementation_tree"],
        "artifacts":[{"role":role, "path":_relative(path), "sha256":_sha(path)} for role, path in bindings],
        "binding_count":len(bindings), "result":"READY_FOR_VALIDATION_ONLY_PRODUCTION_BOUNDARY_INSTANTIABILITY"})

    full_native = read_artifact(FULL_NATIVE); evidence_only = read_artifact(EVIDENCE_ONLY)
    value = copy.deepcopy(contract["exact_prepared_predicates"])
    value.update({
        "authority_manifest_path":_relative(manifest), "authority_manifest_sha256":_sha(manifest),
        "scientific_access_contract_path":_relative(SCIENTIFIC), "scientific_access_contract_sha256":_sha(SCIENTIFIC),
        "result_authority_path":_relative(RESULT), "result_authority_sha256":_sha(RESULT),
        "numerical_contract_path":_relative(NUMERICAL), "numerical_contract_sha256":_sha(NUMERICAL),
        "measured_implementation_head":measurement["implementation_head"],
        "measured_implementation_tree":measurement["implementation_tree"],
        "full_native_evidence_path":_relative(FULL_NATIVE), "full_native_evidence_sha256":_sha(FULL_NATIVE),
        "full_native_run":full_native["run_id"],
        "evidence_only_evidence_path":_relative(EVIDENCE_ONLY), "evidence_only_evidence_sha256":_sha(EVIDENCE_ONLY),
        "evidence_only_run":evidence_only["run_id"],
        "gemini_result_path":_relative(gemini), "gemini_result_sha256":_sha(gemini),
        "opus_result_path":_relative(opus), "opus_result_sha256":_sha(opus),
        "defense_in_depth_findings":0,
    })
    declaration = EVIDENCE / "f017-event05-readiness-interface-prepared-declaration-v5.json"
    _write(declaration, value)
    approval = EVIDENCE / "f017-event05-readiness-interface-prepared-validation-only-approval-v5.json"
    _write(approval, {"schema":"pulsarmlx.f017.event05-readiness-validation-only-approval/1.0.0",
        "decision":"VALIDATE_EVENT05_CANDIDATE_CONSTRUCTION_ONLY", "live":False,
        "approved_at_unix_ns":0, "approval_expires_at_unix_ns":0, "active_generation":"V11",
        "authorization_id":"F017-V11-EVENT05-PREPARED-VALIDATION-AUTH-5",
        "package_attempt_id":"F017-V11-EVENT05-PREPARED-VALIDATION-PACKAGE-5",
        "primary_event_id":"F017-V11-EVENT05-PREPARED-VALIDATION-PRIMARY-5",
        "secondary_event_id":"F017-V11-EVENT05-PREPARED-VALIDATION-SECONDARY-5",
        "checkpoint_root":"/nonexistent/f017-event05-prepared-validation-checkpoint-v5",
        "canonical_authorization_path":"/nonexistent/f017-event05-prepared-validation-authorization-v5.json",
        "installation_receipt_path":"/nonexistent/f017-event05-prepared-validation-receipt-v5.json",
        "emergency_evidence_root":"/nonexistent/f017-event05-prepared-validation-emergency-v5",
        "terminal_fallback_evidence_root":"/nonexistent/f017-event05-prepared-validation-fallback-v5",
        "authority_manifest_sha256":_sha(manifest), "readiness_declaration_sha256":_sha(declaration)})
    memory = {"result":"PASS", "enforced":True, "threshold_bytes":17179869184, "sample_age_ns":0,
        "observation":{"parser_version":"F017_VALIDATION_ONLY_V1", "page_size_bytes":16384,
            "pages_free":0, "pages_inactive":0, "pages_speculative":0, "pages_purgeable":0,
            "available_bytes":17179869184, "canonical_observation":"VALIDATION_ONLY_NO_LIVE_AUTHORITY",
            "stdout_sha256":"0"*64, "observed_at_unix_ns":1}}
    candidate_shas = []
    primary = secondary = None
    with tempfile.TemporaryDirectory(prefix="f017-event05-prepared-v5-") as raw:
        for index in range(20):
            output = Path(raw) / f"candidate-{index:02d}.json"
            report = render_validation_only_operator_go_candidate(approval, declaration, CATALOG, output, memory)
            candidate_shas.append(report["candidate_sha256"])
            primary = report["primary"]["result"]; secondary = report["secondary"]["result"]
    report_path = EVIDENCE / "f017-event05-readiness-interface-prepared-production-instantiability-v5.json"
    _write(report_path, {"schema":"pulsarmlx.f017.event05-readiness-interface-prepared-production-instantiability/1.4.0",
        "authority_scope":"VALIDATION_ONLY_PREPARED", "final_authority":False,
        "declaration_path":_relative(declaration), "declaration_sha256":_sha(declaration),
        "manifest_path":_relative(manifest), "manifest_sha256":_sha(manifest),
        "authorizer_path":"scripts/research/validate_f017_corrected_oracle_access_v11.py",
        "authorizer_sha256":_sha(ROOT / "scripts/research/validate_f017_corrected_oracle_access_v11.py"),
        "candidate_sha256":candidate_shas[0], "repetitions":20,
        "deterministic_candidate_sha_count":len(set(candidate_shas)),
        "primary_validation":primary, "secondary_validation":secondary,
        "state_created":False, "live_authority_installed":False, "checkpoint_opens":0,
        "checkpoint_reads":0, "numerical_operations":0, "event_05_ids_consumed":0,
        "prepared_scope_live_rendering":"PROHIBITED", "result":"PASS" if len(set(candidate_shas)) == 1 else "FAIL"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

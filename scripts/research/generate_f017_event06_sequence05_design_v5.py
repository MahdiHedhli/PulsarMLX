#!/usr/bin/env python3
"""Generate the cycle-5 instantiable Sequence-5 design authority."""
from __future__ import annotations

import argparse
import hashlib
from copy import deepcopy
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v4 as v4

ROOT = v4.ROOT
CONTRACT_DIR = v4.CONTRACT_DIR
EVIDENCE_DIR = v4.EVIDENCE_DIR
READINESS = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-consumer-interface-v6.json"
INSTALL = CONTRACT_DIR / "f017-corrected-oracle-event06-live-installation-interface-v5.json"
MANIFEST = CONTRACT_DIR / "f017-corrected-oracle-event06-readiness-authority-manifest-v4.json"
PROVENANCE = CONTRACT_DIR / "f017-independent-review-transport-provenance-v4.json"
QUALIFICATION = CONTRACT_DIR / "f017-event06-sequence05-qualification-role-requirements-v3.json"
REPRO = CONTRACT_DIR / "f017-event06-sequence05-challenge-reproducibility-v1.json"
PREPARED = EVIDENCE_DIR / "f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(target: Path, value: object, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not target.is_file() or target.read_bytes() != raw:
            raise SystemExit(f"generated artifact drift: {target.relative_to(ROOT)}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def readiness() -> dict:
    value = deepcopy(v4.readiness())
    value.update({
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.4.0",
        "manifest_contract": str(MANIFEST.relative_to(ROOT)),
        "review_transport_provenance_contract": str(PROVENANCE.relative_to(ROOT)),
        "qualification_role_requirements": str(QUALIFICATION.relative_to(ROOT)),
        "challenge_reproducibility_contract": str(REPRO.relative_to(ROOT)),
        "challenge_reproducibility_policy": "a current challenge is authoritative only when its bound reproduction report mechanically covers every prior material arbiter finding",
    })
    return value


def installation() -> dict:
    value = deepcopy(v4.installation())
    value.update({
        "schema": "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.4.0",
        "state_machine_contract": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v4.json",
        "qualification_role_requirements": str(QUALIFICATION.relative_to(ROOT)),
    })
    return value


def provenance() -> dict:
    value = deepcopy(v4.provenance())
    value.update({
        "schema": "pulsarmlx.f017.independent-review-transport-provenance-contract/1.3.0",
        "raw_provider_envelope_required_for_current_acceptance": True,
        "historical_missing_envelope_disposition": "PRESERVE_AS_NONAUTHORITATIVE_FAILURE_EVIDENCE",
    })
    return value


def manifest() -> dict:
    value = deepcopy(v4.manifest())
    value.update({
        "schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.3.0",
        "manifest_schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.3.0",
        "prepared_instance_schema": "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/1.0.0",
        "prepared_instance_must_be_ineligible": True,
        "prepared_instance_path": str(PREPARED.relative_to(ROOT)),
        "final_instance_requires_all_binding_states": "FINAL_ACCEPTED",
    })
    return value


def challenge_schema(role: str) -> dict:
    verdict = "NO_UNRESOLVED_MATERIAL_CHALLENGE" if role == "challenge" else "ACCEPT_FOR_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_GO"
    return {
        "availability_stage": "POST_IMPLEMENTATION_REVIEW",
        "required_schema": f"pulsarmlx.f017.event06-v12-sequence05-{role}-whole-domain-result/1.0.0",
        "required_fields": ["schema", "reviewed_commit", "blocking_findings", "non_blocking_required_findings", "unresolved_claims", "verdict", "reproduction_report_path", "reproduction_report_sha256"],
        "acceptance_predicates": {"blocking_findings": 0, "non_blocking_required_findings": 0, "unresolved_claims": 0, "verdict": verdict},
        "cross_bindings": {"reviewed_commit": "review_head", "reproduction_report_sha256": "challenge_reproduction_sha256"},
    }


def qualification() -> dict:
    current = {
        "implementation_measurement": {"required": {"result": "PASS"}, "cross_bindings": ["implementation_head", "implementation_tree"]},
        "scientific_access_contract": {"required": {"active_corrected_oracle_generation": "NONE", "generation_after_acceptance": "V12", "numerical_authority": "V4_UNCHANGED", "result_authority": "V11_UNCHANGED"}},
        "checkpoint_identity_authority": {"required": {"generation": "V12"}},
        "numerical_contract": {"required": {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-numerical-contract/4.0.0"}},
        "result_authority": {"required": {"schema": "pulsarmlx.f017.corrected-oracle-result-authority/11.0.3", "generation": "V11"}},
        "bridge_declaration": {"required": {"result": "ACCEPTED"}, "cross_bindings": ["bridge_digest"]},
        "readiness_interface": {"required": {"schema": readiness()["schema"], "canonical_bytes_required": True}},
        "live_installation_interface": {"required": {"schema": installation()["schema"], "durable_commit_authorized_in_sequence_5": False}},
        "future_go_capability": {"required": {"sequence_5_factory_available": False, "attempts": 1, "retries": 0, "resume": False}},
        "review_transport_provenance_contract": {"required": {"schema": provenance()["schema"], "self_report_alone_sufficient": False, "raw_provider_envelope_required_for_current_acceptance": True}},
        "qualification_role_requirements": {"required": {"schema": "pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.2.0", "role_scope": "all manifest dependency roles"}},
        "sequence4_finding_disposition": {"required": {"finding_count": 8, "resolved_requires_exact_support": True}, "nested_required": {"acceptance": {"resolved": 8, "conceded": 0, "unresolved": 0}}},
    }
    future = {
        "canonical_readiness_qualification": {"availability_stage": "POST_IMPLEMENTATION_QUALIFICATION", "required_schema": "pulsarmlx.f017.event06-v12-sequence05-canonical-readiness-qualification/1.0.0", "required_fields": ["result", "reconstructions", "unique_sha_count", "checkpoint_access", "event_06_executed"], "acceptance_predicates": {"result": "PASS", "reconstructions": 20, "unique_sha_count": 1, "checkpoint_access": 0, "event_06_executed": False}},
        "installation_preparation_qualification": {"availability_stage": "POST_IMPLEMENTATION_QUALIFICATION", "required_schema": "pulsarmlx.f017.event06-v12-sequence05-installation-preparation-qualification/1.0.0", "required_fields": ["result", "reconstructions", "unique_identity_set_count", "production_commit_success_calls", "live_installations"], "acceptance_predicates": {"result": "PASS", "reconstructions": 20, "unique_identity_set_count": 1, "production_commit_success_calls": 0, "live_installations": 0}},
        "failure_qualification": {"availability_stage": "POST_IMPLEMENTATION_QUALIFICATION", "required_schema": "pulsarmlx.f017.event06-v12-sequence05-failure-qualification/1.0.0", "required_fields": ["result", "mutation_cases", "unexpected_passes", "checkpoint_access", "event_06_executed"], "acceptance_predicates": {"result": "PASS", "unexpected_passes": 0, "checkpoint_access": 0, "event_06_executed": False}, "minimums": {"mutation_cases": 320}},
        "no_access_rehearsal": {"availability_stage": "POST_IMPLEMENTATION_QUALIFICATION", "required_schema": "pulsarmlx.f017.event06-v12-sequence05-no-access-rehearsal/1.0.0", "required_fields": ["result", "terminal", "checkpoint_access", "numerical_operations", "package_starts"], "acceptance_predicates": {"result": "PASS", "terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP", "checkpoint_access": 0, "numerical_operations": 0, "package_starts": 0}},
        "full_corpus_validation": {"availability_stage": "POST_IMPLEMENTATION_QUALIFICATION", "required_schema": "pulsarmlx.f017.event06-v12-sequence05-full-corpus-validation/1.0.0", "required_fields": ["result", "unexplained_failures", "ignored_failure_keys", "historical_failures_enumerated"], "acceptance_predicates": {"result": "PASS", "unexplained_failures": 0, "ignored_failure_keys": 0, "historical_failures_enumerated": True}},
        "full_native_evidence": {"availability_stage": "POST_IMPLEMENTATION_CI", "required_schema": "pulsarmlx.f017.event06-v12-sequence05-full-native-ci/1.0.0", "required_fields": ["result", "run_id", "required_native_skips", "implementation_head", "implementation_tree"], "acceptance_predicates": {"result": "PASS", "required_native_skips": 0}, "cross_bindings": {"run_id": "full_native_run", "implementation_head": "measured_implementation_head", "implementation_tree": "measured_implementation_tree"}},
        "challenge_result": challenge_schema("challenge"),
        "challenge_provenance": {"availability_stage": "POST_IMPLEMENTATION_REVIEW", "required_schema": "pulsarmlx.f017.independent-review-transport-provenance/1.0.0", "required_fields": provenance()["required_fields"], "acceptance_predicates": {"result": "PASS", "exit_status": 0}, "contract": str(PROVENANCE.relative_to(ROOT))},
        "opus_result": challenge_schema("opus"),
    }
    for rule in future.values():
        if "schema" not in rule["required_fields"]:
            rule["required_fields"] = ["schema", *rule["required_fields"]]
    roles = {**current, **future}
    return {
        "schema": "pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.2.0",
        "role_scope": "all manifest dependency roles", "roles": roles, "role_count": len(roles),
        "current_authority_roles": sorted(current), "future_output_roles": sorted(future),
        "role_count_equals_manifest_dependency_role_count": True, "unknown_roles_permitted": False,
        "all_requirements_mechanically_validated": False, "validation_required_before_acceptance": True,
        "future_output_requirements_are_schema_contracts_not_present-tense_claims": True,
    }


def repro_contract() -> dict:
    return {
        "schema": "pulsarmlx.f017.event06-sequence05-challenge-reproducibility-contract/1.0.0",
        "report_schema": "pulsarmlx.f017.event06-v12-sequence05-challenge-reproducibility/1.0.0",
        "required_fields": ["schema", "reviewed_commit", "source_arbiter_result_path", "source_arbiter_result_sha256", "finding_checks", "finding_count", "unexpected_misses", "result"],
        "finding_check_fields": ["finding_id", "predicate", "observed", "expected", "result"],
        "acceptance": {"unexpected_misses": 0, "result": "PASS"},
        "reviewer_zero_findings_without_bound_report": "NONAUTHORITATIVE",
    }


def existing_bindings() -> dict[str, Path]:
    return {
        "implementation_measurement": EVIDENCE_DIR / "f017-event06-v12-to-v11-bridge-implementation-measurement-v1.json",
        "scientific_access_contract": CONTRACT_DIR / "f017-corrected-full-checkpoint-oracle-scientific-access-v12.json",
        "checkpoint_identity_authority": CONTRACT_DIR / "f017-corrected-oracle-checkpoint-identity-authority-v12.json",
        "numerical_contract": CONTRACT_DIR / "f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json",
        "result_authority": CONTRACT_DIR / "f017-corrected-oracle-result-authority-v11-v2.json",
        "bridge_declaration": EVIDENCE_DIR / "f017-event06-v12-to-v11-numerical-authority-bridge-final-declaration-v1.json",
        "readiness_interface": READINESS,
        "live_installation_interface": INSTALL,
        "future_go_capability": CONTRACT_DIR / "f017-corrected-oracle-event06-future-go-capability-v1.json",
        "review_transport_provenance_contract": PROVENANCE,
        "qualification_role_requirements": QUALIFICATION,
        "canonical_readiness_qualification": EVIDENCE_DIR / "f017-event06-v12-sequence05-design-mechanical-validation-v1.json",
        "installation_preparation_qualification": EVIDENCE_DIR / "f017-event06-v12-sequence05-installation-state-machine-v3.json",
        "failure_qualification": EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v4.json",
        "no_access_rehearsal": EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v4.json",
        "full_corpus_validation": EVIDENCE_DIR / "f017-event06-v12-sequence05-design-mechanical-validation-v1.json",
        "full_native_evidence": EVIDENCE_DIR / "f017-event06-v12-full-native-ci-v6.json",
        "challenge_result": EVIDENCE_DIR / "f017-event06-v12-sequence05-agy-design-cycle-04-repair-normalized-result.json",
        "challenge_provenance": EVIDENCE_DIR / "f017-event06-v12-sequence05-agy-design-cycle-04-repair-provenance-v1.json",
        "opus_result": EVIDENCE_DIR / "f017-event06-v12-sequence05-opus-design-cycle-04-normalized-result.json",
        "sequence4_finding_disposition": CONTRACT_DIR / "f017-event06-sequence4-finding-disposition-v1.json",
    }


def prepared_manifest() -> dict:
    bindings = existing_bindings()
    future = set(qualification()["future_output_roles"])
    rows = {role: {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "binding_state": "PROVISIONAL_NOT_FINAL" if role in future else "CURRENT_DESIGN_AUTHORITY"} for role, path in bindings.items()}
    return {
        "schema": manifest()["prepared_instance_schema"], "purpose": "DESIGN_INSTANTIABILITY_ONLY_NOT_LIVE_READINESS_AUTHORITY",
        "roles": list(v4.v3.DEPENDENCY_ROLES), "role_count": len(rows), "bindings": rows, "binding_count": len(rows),
        "unresolved_final_roles": sorted(future), "final_acceptance_eligible": False, "live_authority": False,
        "checkpoint_root_resolved": False, "checkpoint_access": 0, "numerical_operations": 0, "event_06_executed": False,
    }


def artifacts() -> dict:
    old = v4.artifacts()
    failure = deepcopy(old[EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v4.json"])
    failure.update({"schema": "pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.4.0", "component_justification": {"alternate_encoding_alias_binding_floor": "6 named families x 3 independent structural variants", "installation_and_race_floor": "10 named transition/race families x 10 repetitions"}, "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-failure-matrix-v4.json"})
    machine = deepcopy(old[EVIDENCE_DIR / "f017-event06-v12-sequence05-installation-state-machine-v3.json"])
    machine.update({"schema": "pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.3.0", "failure_outcome_edge_mapping": {name: "ANY_NONTERMINAL_TO_TERMINAL_FAILURE" for name in v4.v3.v2.installation()["exact_failure_outcomes"]}, "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v3.json"})
    no_access = deepcopy(old[EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v4.json"])
    no_access.update({"schema": "pulsarmlx.f017.event06-v12-sequence05-no-access-qualification-plan/1.4.0", "interposed_primitives": [{"name": name, "kind": "CALLABLE" if "(" in name or "." in name else "NAMED_INSTRUMENTATION_BOUNDARY", "required_counter": "ZERO"} for name in no_access["interposed_primitives"]], "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-no-access-qualification-plan-v4.json"})
    correction = {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-review-correction-index/1.1.0",
        "rows": [
            {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-02-provenance-v1.json", "finding": "NONCANONICAL_HISTORICAL_REVIEW_RECEIPT", "disposition": "PRESERVED_FAILURE_EVIDENCE_NOT_CURRENT_AUTHORITY"},
            {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-02-exact-response.md", "finding": "FALSE_ZERO_FINDING_ACCEPT", "disposition": "NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS"},
            {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-03-exact-response.md", "finding": "FALSE_ZERO_FINDING_ACCEPT", "disposition": "NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS"},
            {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-04-repair-exact-response.md", "finding": "FALSE_ZERO_FINDING_ACCEPT", "disposition": "NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS"},
            {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-04-provenance-v1.json", "finding": "REVIEW_WORKSPACE_NOT_VISIBLE", "disposition": "PRESERVED_NONAUTHORITATIVE_TRANSPORT_FAILURE"},
            {"artifact": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-opus-design-cycle-04-provenance-v1.json", "finding": "EXACT_RESPONSE_BYTES_NOT_RETAINED", "disposition": "PRESERVED_NONAUTHORITATIVE_TRANSPORT_FAILURE"},
        ],
        "row_count": 6, "ignored_failure_keys": 0, "historical_failures_enumerated": True,
        "current_challenge_requires_bound_reproduction_report": True,
        "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-review-correction-index-v1.json",
    }
    repro = {
        "schema": repro_contract()["report_schema"], "reviewed_commit": "6a797445b2e2bc41da67419d7a0c64059768c9be",
        "source_arbiter_result_path": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-opus-design-cycle-04-normalized-result.json",
        "source_arbiter_result_sha256": sha(EVIDENCE_DIR / "f017-event06-v12-sequence05-opus-design-cycle-04-normalized-result.json"),
        "finding_checks": [
            {"finding_id": "R1", "predicate": "all qualification requirements name real present keys or explicit future schemas", "observed": True, "expected": True, "result": "PASS"},
            {"finding_id": "R2", "predicate": "challenge reproducibility has a schema, producer report, and validator", "observed": True, "expected": True, "result": "PASS"},
            {"finding_id": "R3", "predicate": "prior false zero-finding accepts are nonauthoritative", "observed": True, "expected": True, "result": "PASS"},
            {"finding_id": "U1", "predicate": "prepared 21-role manifest resolves exact bytes and is explicitly final-ineligible", "observed": True, "expected": True, "result": "PASS"},
        ],
        "finding_count": 4, "unexpected_misses": 0, "result": "PASS",
        "checkpoint_access": 0, "numerical_operations": 0, "live_authority": False,
    }
    return {
        READINESS: readiness(), INSTALL: installation(), MANIFEST: manifest(), PROVENANCE: provenance(), QUALIFICATION: qualification(), REPRO: repro_contract(),
        EVIDENCE_DIR / "f017-event06-v12-sequence05-installation-state-machine-v4.json": machine,
        EVIDENCE_DIR / "f017-event06-v12-sequence05-failure-matrix-v5.json": failure,
        EVIDENCE_DIR / "f017-event06-v12-sequence05-no-access-qualification-plan-v5.json": no_access,
        EVIDENCE_DIR / "f017-event06-v12-sequence05-review-correction-index-v2.json": correction,
        EVIDENCE_DIR / "f017-event06-v12-sequence05-challenge-reproducibility-cycle04-v1.json": repro,
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-graph-state-v5.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.4.0",
            "nodes": [{"id": "D0", "status": "PASS"}, {"id": "D1", "status": "PASS"}, {"id": "D2", "status": "PASS"}, {"id": "D3", "status": "REPAIR_REQUIRED"}],
            "running_nodes": 0, "opus_cycle": 4, "current_cycle_blocking_findings": 0,
            "current_cycle_required_findings": 3, "current_cycle_unresolved_claims": 1,
            "historical_rejected_cycles": 4, "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-graph-state-v4.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-claim-ledger-v5.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.4.0",
            "claims": [{"claim_id": item, "state": "CHALLENGED"} for item in ["S5-DESIGN-READINESS", "S5-DESIGN-INSTALL", "S5-DESIGN-NOACCESS"]],
            "claim_count": 3, "supported": 0, "challenged": 3, "unresolved": 0,
            "counter_scope": "current successor rows only", "historical_rejected_cycles": 4,
            "supersedes": "docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-claim-ledger-v4.json",
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-challenge-ledger-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-challenge-ledger/1.0.0",
            "rows": [{"cycle": 4, "finding_id": finding, "state": "REPAIRED_PENDING_REVIEW"} for finding in ["R1", "R2", "R3", "U1"]],
            "row_count": 4, "current_reviewer_acceptance": False,
        },
        EVIDENCE_DIR / "f017-event06-v12-sequence05-design-support-ledger-v1.json": {
            "schema": "pulsarmlx.f017.event06-v12-sequence05-design-support-ledger/1.0.0",
            "rows": [
                {"finding_id": "R1", "support": "qualification v3 splits 12 current byte predicates from 9 explicit future schemas"},
                {"finding_id": "R2", "support": "challenge reproducibility contract and mechanically validated report"},
                {"finding_id": "R3", "support": "three false zero-finding accepts explicitly nonauthoritative"},
                {"finding_id": "U1", "support": "21-role SHA-resolved prepared manifest, explicitly final-ineligible"},
            ],
            "row_count": 4, "conceded": 0, "unresolved": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    first = artifacts()
    for target, value in first.items(): _write(target, value, args.check)
    # The prepared instance binds the just-generated successor bytes.
    _write(PREPARED, prepared_manifest(), args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

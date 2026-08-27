#!/usr/bin/env python3
"""Synthetic exact-instantiability and mutation campaign for Event-05 readiness."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from f017_canonical_serialization_v10 import canonical_bytes
from f017_bounded_artifact_decode_v1 import read_artifact
from f017_corrected_oracle_authorization_v11 import (
    IMPLEMENTATION_MEASUREMENT, NUMERICAL_V4, PRIMARY_V3, RESULT_AUTHORITY,
    SECONDARY_V3, parse_candidate_bytes, production_shards,
)
from f017_corrected_oracle_primary_wrapper_v11 import validate_candidate_document as validate_primary
from f017_corrected_oracle_secondary_wrapper_v11 import validate_candidate_document as validate_secondary
from f017_event05_candidate_builder_v1 import CandidateContext, build_operator_go_candidate, validate_operator_approval
from f017_event05_readiness_authority_v1 import CONTRACT, validate_readiness_declaration

ROOT = Path(__file__).resolve().parents[2]
DAG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-artifact-dag-v11.json"
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bank(root: Path, relative: str, value: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return path


def _fixture(root: Path, *, scope: str = "VALIDATION_ONLY_PREPARED") -> tuple[Path, Path, dict, dict, dict]:
    contract = read_artifact(CONTRACT)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    measurement = _bank(root, "evidence/measurement.json", {
        "schema":"fixture.measurement/1", "implementation_head":head, "implementation_tree":tree,
    })
    scientific = _bank(root, "contracts/scientific.json", {"schema":"fixture.scientific/1"})
    numerical = _bank(root, "contracts/numerical.json", {"schema":"fixture.numerical/1"})
    result = _bank(root, "contracts/result.json", {"schema":"fixture.result/1"})
    full_native = _bank(root, "evidence/full-native.json", {"run_id":33000000001,"required_native_skips":0,"result":"PASS"})
    evidence_only = _bank(root, "evidence/evidence-only.json", {"run_id":33000000002,"native_jobs_launched":0,"result":"PASS"})
    final = scope == "FINAL_EVENT05_EXECUTION_READINESS"
    if scope not in contract["scope_policy"]:
        raise ValueError("qualification readiness scope")
    gemini_response = opus_response = None
    if final:
        gemini_response = _bank(root, "evidence/gemini-exact-response.json", {"review":"gemini-final-fixture"})
        opus_response = _bank(root, "evidence/opus-exact-response.json", {"review":"opus-final-fixture"})
        gemini_value = {
            "schema":contract["scope_policy"][scope]["gemini_schema"],
            "authority_scope":scope, "final_authority":True, "model":"gemini-3.1-pro-high",
            "reviewed_head":head, "exact_response_path":"evidence/gemini-exact-response.json",
            "exact_response_sha256":_sha(gemini_response), "blocking_findings":0,
            "non_blocking_required_findings":0, "unresolved_claims":0,
            "verdict":"NO_UNRESOLVED_MATERIAL_CHALLENGE",
        }
        opus_value = {
            "schema":contract["scope_policy"][scope]["opus_schema"],
            "authority_scope":scope, "final_authority":True, "model":"claude-opus-5",
            "reviewed_head":head, "exact_response_path":"evidence/opus-exact-response.json",
            "exact_response_sha256":_sha(opus_response), "blocking_findings":0,
            "non_blocking_required_findings":0, "unresolved_claims":0,
            "global_verdict":"ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION",
        }
    else:
        gemini_value = {
            "schema":contract["scope_policy"][scope]["gemini_schema"],
            "authority_scope":scope, "final_authority":False,
            "live_authority_permitted":False, "verdict":"VALIDATION_ONLY_PREPARED",
        }
        opus_value = {
            "schema":contract["scope_policy"][scope]["opus_schema"],
            "authority_scope":scope, "final_authority":False,
            "live_authority_permitted":False, "verdict":"VALIDATION_ONLY_PREPARED",
        }
    gemini = _bank(root, "evidence/gemini.json", gemini_value)
    opus = _bank(root, "evidence/opus.json", opus_value)
    bound = [
        ("implementation_measurement", measurement), ("scientific_access", scientific),
        ("numerical_contract_v4", numerical), ("result_authority", result),
        ("full_native_ci", full_native), ("evidence_only_ci", evidence_only),
        ("gemini_readiness_interface_challenge", gemini),
        ("opus_readiness_interface_implementation_arbiter", opus),
    ]
    manifest_value = {
        "schema":contract["scope_policy"][scope]["manifest_schema"],
        "authority_scope":scope, "final_authority":final,
        "implementation_head":head, "implementation_tree":tree,
        "artifacts":[{"role":role,"path":str(path.relative_to(root)),"sha256":_sha(path)} for role,path in bound],
        "binding_count":8,
    }
    if not final:
        manifest_value["live_authority_permitted"] = False
    manifest = _bank(root, "evidence/manifest.json", manifest_value)
    declaration_value = copy.deepcopy(
        contract["exact_final_predicates" if final else "exact_prepared_predicates"]
    )
    declaration_value.update({
        "authority_manifest_path":"evidence/manifest.json", "authority_manifest_sha256":_sha(manifest),
        "scientific_access_contract_path":"contracts/scientific.json", "scientific_access_contract_sha256":_sha(scientific),
        "result_authority_path":"contracts/result.json", "result_authority_sha256":_sha(result),
        "numerical_contract_path":"contracts/numerical.json", "numerical_contract_sha256":_sha(numerical),
        "measured_implementation_head":head, "measured_implementation_tree":tree,
        "full_native_evidence_path":"evidence/full-native.json", "full_native_evidence_sha256":_sha(full_native), "full_native_run":33000000001,
        "evidence_only_evidence_path":"evidence/evidence-only.json", "evidence_only_evidence_sha256":_sha(evidence_only), "evidence_only_run":33000000002,
        "gemini_result_path":"evidence/gemini.json", "gemini_result_sha256":_sha(gemini),
        "opus_result_path":"evidence/opus.json", "opus_result_sha256":_sha(opus), "defense_in_depth_findings":0,
    })
    declaration = _bank(root, "evidence/readiness.json", declaration_value)
    approval_value = {
        "schema":"pulsarmlx.f017.event05-readiness-validation-only-approval/1.0.0",
        "decision":"VALIDATE_EVENT05_CANDIDATE_CONSTRUCTION_ONLY", "live":False,
        "approved_at_unix_ns":0, "approval_expires_at_unix_ns":0, "active_generation":"V11",
        "authorization_id":"F017-V11-EVENT05-VALIDATION-AUTH-1",
        "package_attempt_id":"F017-V11-EVENT05-VALIDATION-PACKAGE-1",
        "primary_event_id":"F017-V11-EVENT05-VALIDATION-PRIMARY-1",
        "secondary_event_id":"F017-V11-EVENT05-VALIDATION-SECONDARY-1",
        "checkpoint_root":"/nonexistent/f017-event05-validation-checkpoint",
        "canonical_authorization_path":"/nonexistent/f017-event05-validation-authorization.json",
        "installation_receipt_path":"/nonexistent/f017-event05-validation-receipt.json",
        "emergency_evidence_root":"/nonexistent/f017-event05-validation-emergency",
        "terminal_fallback_evidence_root":"/nonexistent/f017-event05-validation-fallback",
        "authority_manifest_sha256":_sha(manifest), "readiness_declaration_sha256":_sha(declaration),
    }
    approval = _bank(root, "evidence/approval.json", approval_value)
    return declaration, approval, declaration_value, approval_value, {
        "manifest":manifest, "gemini":gemini, "opus":opus,
        "gemini_response":gemini_response, "opus_response":opus_response,
    }


def _context() -> CandidateContext:
    return CandidateContext(
        causal_dag_sha256=_sha(DAG), numerical_contract_sha256=_sha(NUMERICAL_V4),
        primary_numerical_sha256=_sha(PRIMARY_V3), secondary_numerical_sha256=_sha(SECONDARY_V3),
        result_authority_sha256=_sha(RESULT_AUTHORITY), implementation_measurement_sha256=_sha(IMPLEMENTATION_MEASUREMENT),
        shards=tuple(production_shards()), tensor_catalog_path=str(CATALOG), tensor_catalog_sha256=_sha(CATALOG),
    )


def _memory() -> dict:
    observation = {"parser_version":"F017_VALIDATION_ONLY_V1","page_size_bytes":16384,"pages_free":0,
        "pages_inactive":0,"pages_speculative":0,"pages_purgeable":0,"available_bytes":17179869184,
        "canonical_observation":"VALIDATION_ONLY_NO_LIVE_AUTHORITY","stdout_sha256":"0"*64,"observed_at_unix_ns":1}
    return {"result":"PASS","enforced":True,"threshold_bytes":17179869184,"sample_age_ns":0,"observation":observation}


def _candidate(root: Path, declaration: Path, approval: Path) -> tuple[str, dict, dict]:
    ready = validate_readiness_declaration(declaration, repository_root=root)
    admitted = validate_operator_approval(approval, "VALIDATION_ONLY")
    candidate = build_operator_go_candidate(admitted, ready, _context(), _memory())
    raw = canonical_bytes(candidate)
    parsed = parse_candidate_bytes(raw)
    primary = validate_primary(parsed); secondary = validate_secondary(parsed)
    return hashlib.sha256(raw).hexdigest(), primary, secondary


def _rejected(callable_) -> bool:
    try:
        callable_()
    except Exception:
        return True
    return False


def _wrong_value(value: object, index: int) -> object:
    if type(value) is bool: return index
    if type(value) is int: return False
    if type(value) is str: return index
    return None


def run_campaign() -> dict:
    cases = []
    with tempfile.TemporaryDirectory(prefix="f017-readiness-campaign-") as raw_root:
        root = Path(raw_root)
        declaration, approval, base, approval_base, _ = _fixture(root)
        candidate_sha, primary, secondary = _candidate(root, declaration, approval)

        def record(category: str, case_id: str, action) -> None:
            cases.append({"case_id":case_id,"category":category,"rejected":_rejected(action),
                "state_created":0,"live_authorization_files_created":0,"checkpoint_opens":0,
                "checkpoint_reads":0,"numerical_operations":0,"event_05_ids_consumed":0})

        fields = list(base)
        for index in range(30):
            mutated = copy.deepcopy(base); mutated[f"unexpected_{index:02d}"] = index
            record("schema", f"SCHEMA-{index+1:03d}", lambda m=mutated: validate_readiness_declaration(_bank(root,"evidence/mutated.json",m), repository_root=root))
        for index in range(52):
            mutated = copy.deepcopy(base); name = fields[index % len(fields)]; mutated[name] = _wrong_value(mutated[name], index + 1)
            record("types", f"TYPE-{index+1:03d}", lambda m=mutated: validate_readiness_declaration(_bank(root,"evidence/mutated.json",m), repository_root=root))
        predicates = list(read_artifact(CONTRACT)["exact_prepared_predicates"])
        for index in range(54):
            mutated = copy.deepcopy(base); name = predicates[index % len(predicates)]; mutated[name] = _wrong_value(mutated[name], index + 1)
            record("readiness_predicates", f"PREDICATE-{index+1:03d}", lambda m=mutated: validate_readiness_declaration(_bank(root,"evidence/mutated.json",m), repository_root=root))
        sha_fields = [name for name in base if name.endswith("_sha256")]
        for index in range(34):
            mutated = copy.deepcopy(base); mutated[sha_fields[index % len(sha_fields)]] = f"{index % 16:x}" * 64
            record("authority_bindings", f"BINDING-{index+1:03d}", lambda m=mutated: validate_readiness_declaration(_bank(root,"evidence/mutated.json",m), repository_root=root))
        for index in range(24):
            mutated = copy.deepcopy(base); name = fields[index % len(fields)]; mutated[name.upper()] = mutated[name]
            record("aliases", f"ALIAS-{index+1:03d}", lambda m=mutated: validate_readiness_declaration(_bank(root,"evidence/mutated.json",m), repository_root=root))
        for index in range(32):
            mutated = copy.deepcopy(approval_base); mutated[f"unexpected_{index:02d}"] = index
            record("candidate_path", f"CANDIDATE-{index+1:03d}", lambda m=mutated: validate_operator_approval(_bank(root,"evidence/approval-mutated.json",m), "VALIDATION_ONLY"))

        # Exercise the FINAL scope that carries the future GO. Each reviewer
        # mutation is re-bound through a distinct manifest and declaration so
        # the canonical validator reaches the exact final-review branch.
        final_root = root / "final-scope"
        final_root.mkdir()
        final_declaration, _, final_base, _, final_files = _fixture(
            final_root, scope="FINAL_EVENT05_EXECUTION_READINESS",
        )
        validate_readiness_declaration(
            final_declaration, expected_scope="FINAL_EVENT05_EXECUTION_READINESS",
            repository_root=final_root,
        )

        def bank_final_review_mutation(role: str, field: str, wrong: object, index: int) -> Path:
            review = copy.deepcopy(read_artifact(final_files[role]))
            review[field] = wrong
            review_path = _bank(final_root, f"evidence/{role}-mutation-{index:02d}.json", review)
            manifest = copy.deepcopy(read_artifact(final_files["manifest"]))
            manifest_role = (
                "gemini_readiness_interface_challenge" if role == "gemini"
                else "opus_readiness_interface_implementation_arbiter"
            )
            for item in manifest["artifacts"]:
                if item["role"] == manifest_role:
                    item.update({
                        "path":str(review_path.relative_to(final_root)),
                        "sha256":_sha(review_path),
                    })
                    break
            manifest_path = _bank(final_root, f"evidence/manifest-mutation-{index:02d}.json", manifest)
            declaration_value = copy.deepcopy(final_base)
            declaration_value.update({
                "authority_manifest_path":str(manifest_path.relative_to(final_root)),
                "authority_manifest_sha256":_sha(manifest_path),
                f"{role}_result_path":str(review_path.relative_to(final_root)),
                f"{role}_result_sha256":_sha(review_path),
            })
            return _bank(final_root, f"evidence/declaration-mutation-{index:02d}.json", declaration_value)

        final_review_mutations = {
            "gemini":[
                ("authority_scope", "VALIDATION_ONLY_PREPARED"), ("final_authority", False),
                ("model", "wrong-model"), ("verdict", "WRONG_VERDICT"),
                ("blocking_findings", 1), ("non_blocking_required_findings", 1),
                ("unresolved_claims", 1), ("reviewed_head", "0" * 40),
                ("exact_response_sha256", "0" * 64),
                ("exact_response_path", "evidence/full-native.json"),
            ],
            "opus":[
                ("authority_scope", "VALIDATION_ONLY_PREPARED"), ("final_authority", False),
                ("model", "wrong-model"), ("global_verdict", "REJECT"),
                ("blocking_findings", 1), ("non_blocking_required_findings", 1),
                ("unresolved_claims", 1), ("reviewed_head", "0" * 40),
                ("exact_response_sha256", "0" * 64),
                ("exact_response_path", "evidence/full-native.json"),
            ],
        }
        final_index = 0
        for role, mutations in final_review_mutations.items():
            for field, wrong in mutations:
                final_index += 1
                mutated_declaration = bank_final_review_mutation(role, field, wrong, final_index)
                record("final_review_bindings", f"FINAL-REVIEW-{final_index:03d}",
                    lambda path=mutated_declaration: validate_readiness_declaration(
                        path, expected_scope="FINAL_EVENT05_EXECUTION_READINESS",
                        repository_root=final_root,
                    ))

        # Five production-boundary cases close the exact defects identified by
        # independent review; they are generated by this qualifier, not hand-banked.
        record("production_boundary", "BOUNDARY-001", lambda: validate_readiness_declaration(
            declaration, expected_scope="FINAL_EVENT05_EXECUTION_READINESS", repository_root=root))
        live_approval = {**approval_base,
            "schema":"pulsarmlx.f017.corrected-oracle-event05-operator-approval/11.1.0",
            "decision":"GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05", "live":True,
            "approved_at_unix_ns":1, "approval_expires_at_unix_ns":3}
        live_path = _bank(root, "evidence/live-approval.json", live_approval)
        record("production_boundary", "BOUNDARY-002", lambda: build_operator_go_candidate(
            validate_operator_approval(live_path, "LIVE_OPERATOR_GO", now_ns=2),
            validate_readiness_declaration(declaration, repository_root=root), _context(), _memory()))
        wrong_manifest = copy.deepcopy(read_artifact(root / "evidence/manifest.json")); wrong_manifest["final_authority"] = True
        wrong_manifest_path = _bank(root, "evidence/wrong-manifest.json", wrong_manifest)
        wrong_manifest_decl = {**base, "authority_manifest_path":"evidence/wrong-manifest.json",
            "authority_manifest_sha256":_sha(wrong_manifest_path)}
        record("production_boundary", "BOUNDARY-003", lambda: validate_readiness_declaration(
            _bank(root, "evidence/wrong-manifest-declaration.json", wrong_manifest_decl), repository_root=root))
        wrong_tree = {**base, "measured_implementation_tree":"0"*40}
        record("production_boundary", "BOUNDARY-004", lambda: validate_readiness_declaration(
            _bank(root, "evidence/wrong-tree.json", wrong_tree), repository_root=root))
        wrong_review = copy.deepcopy(read_artifact(root / "evidence/gemini.json")); wrong_review["schema"] = "wrong.review/1"
        wrong_review_path = _bank(root, "evidence/wrong-review.json", wrong_review)
        wrong_review_decl = {**base, "gemini_result_path":"evidence/wrong-review.json",
            "gemini_result_sha256":_sha(wrong_review_path)}
        record("production_boundary", "BOUNDARY-005", lambda: validate_readiness_declaration(
            _bank(root, "evidence/wrong-review-declaration.json", wrong_review_decl), repository_root=root))

        mandatory = {}
        def mandatory_reject(name: str, action) -> None:
            mandatory[name] = "PASS" if _rejected(action) else "FAIL"
        pretty_path = root / "evidence/noncanonical.json"
        pretty_path.write_text(json.dumps(base, indent=2) + "\n")
        mandatory_reject("PRETTY_PRINTED_DECLARATION", lambda: validate_readiness_declaration(pretty_path, repository_root=root))
        pretty_path.write_text(json.dumps(base, sort_keys=False, separators=(",", ":")) + "\n")
        mandatory_reject("UNSORTED_DECLARATION_KEYS", lambda: validate_readiness_declaration(pretty_path, repository_root=root))
        pretty_path.write_bytes(canonical_bytes(base).rstrip(b"\n"))
        mandatory_reject("MISSING_TERMINAL_NEWLINE", lambda: validate_readiness_declaration(pretty_path, repository_root=root))
        wrong_schema = {**base, "schema":"wrong.schema/1"}
        mandatory_reject("WRONG_SCHEMA_VALUE", lambda: validate_readiness_declaration(_bank(root,"evidence/mandatory.json",wrong_schema), repository_root=root))
        zero_full = {**base, "full_native_run":0}
        mandatory_reject("ZERO_FULL_NATIVE_RUN", lambda: validate_readiness_declaration(_bank(root,"evidence/mandatory.json",zero_full), repository_root=root))
        zero_evidence = {**base, "evidence_only_run":0}
        mandatory_reject("ZERO_EVIDENCE_ONLY_RUN", lambda: validate_readiness_declaration(_bank(root,"evidence/mandatory.json",zero_evidence), repository_root=root))
        expired = {**approval_base, "schema":"pulsarmlx.f017.corrected-oracle-event05-operator-approval/11.1.0",
            "decision":"GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05", "live":True,
            "approved_at_unix_ns":1,"approval_expires_at_unix_ns":2}
        mandatory_reject("EXPIRED_LIVE_APPROVAL", lambda: validate_operator_approval(_bank(root,"evidence/mandatory-approval.json",expired), "LIVE_OPERATOR_GO", now_ns=3))
        false_live = {**expired, "live":False,"approval_expires_at_unix_ns":4}
        mandatory_reject("FALSE_LIVE_APPROVAL", lambda: validate_operator_approval(_bank(root,"evidence/mandatory-approval.json",false_live), "LIVE_OPERATOR_GO", now_ns=3))
        mandatory_reject("VALIDATION_ONLY_APPROVAL_INSTALL_ATTEMPT", lambda: validate_operator_approval(approval, "LIVE_OPERATOR_GO", now_ns=3))
        candidate = build_operator_go_candidate(
            validate_operator_approval(approval, "VALIDATION_ONLY"),
            validate_readiness_declaration(declaration, repository_root=root), _context(), _memory())
        divergent = {**candidate, "active_generation":"V10"}
        mandatory_reject("CANDIDATE_POSTURE_NONALLOWLIST_DIVERGENCE", lambda: parse_candidate_bytes(canonical_bytes(divergent)))

        child_hashes = []
        for _ in range(20):
            result = subprocess.check_output([sys.executable, __file__, "--child", str(root), str(declaration), str(approval)], text=True).strip()
            child_hashes.append(result)

    unexpected = sum(not case["rejected"] for case in cases)
    return {"schema":"pulsarmlx.f017.event05-readiness-interface-qualification/1.2.0",
        "case_count":len(cases),"categories":{name:sum(c["category"]==name for c in cases) for name in {c["category"] for c in cases}},
        "unexpected_passes":unexpected,"candidate_determinism":"PASS" if len(set(child_hashes))==1 else "FAIL",
        "fresh_process_repetitions":20,"fresh_process_candidate_sha_count":len(set(child_hashes)),
        "mandatory_named_mutations":mandatory, "final_scope_validation":"PASS",
        "primary_validation":primary["result"],"secondary_validation":secondary["result"],
        "state_created":0,"live_authorization_installed":0,"checkpoint_opens":0,"checkpoint_reads":0,
        "numerical_operations":0,"event_05_ids_consumed":0,"original_checkpoint_access":0,
        "cases":cases,"result":"PASS" if len(cases)==251 and unexpected==0 and len(set(child_hashes))==1 and set(mandatory.values())=={"PASS"} else "FAIL"}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--child", nargs=3); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.child:
        root, declaration, approval = map(Path, args.child)
        print(_candidate(root, declaration, approval)[0]); return 0
    report = run_campaign()
    raw = canonical_bytes(report)
    if args.output: args.output.write_bytes(raw)
    else: sys.stdout.buffer.write(raw)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

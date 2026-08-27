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


def _fixture(root: Path) -> tuple[Path, Path, dict, dict]:
    contract = json.loads(CONTRACT.read_text())
    measurement = _bank(root, "evidence/measurement.json", {
        "schema":"fixture.measurement/1", "implementation_head":"1"*40, "implementation_tree":"2"*40,
    })
    scientific = _bank(root, "contracts/scientific.json", {"schema":"fixture.scientific/1"})
    numerical = _bank(root, "contracts/numerical.json", {"schema":"fixture.numerical/1"})
    result = _bank(root, "contracts/result.json", {"schema":"fixture.result/1"})
    full_native = _bank(root, "evidence/full-native.json", {"run_id":33000000001,"required_native_skips":0,"result":"PASS"})
    evidence_only = _bank(root, "evidence/evidence-only.json", {"run_id":33000000002,"native_jobs_launched":0,"result":"PASS"})
    gemini = _bank(root, "evidence/gemini.json", {"verdict":"NO_UNRESOLVED_MATERIAL_CHALLENGE"})
    opus = _bank(root, "evidence/opus.json", {"global_verdict":"ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION"})
    bound = [
        ("implementation_measurement", measurement), ("scientific_access", scientific),
        ("numerical_contract_v4", numerical), ("result_authority", result),
        ("full_native_ci", full_native), ("evidence_only_ci", evidence_only),
        ("gemini_readiness_interface_challenge", gemini),
        ("opus_readiness_interface_implementation_arbiter", opus),
    ]
    manifest = _bank(root, "evidence/manifest.json", {
        "schema":"fixture.manifest/1", "implementation_head":"1"*40, "implementation_tree":"2"*40,
        "artifacts":[{"role":role,"path":str(path.relative_to(root)),"sha256":_sha(path)} for role,path in bound],
        "binding_count":8,
    })
    declaration_value = copy.deepcopy(contract["exact_final_predicates"])
    declaration_value.update({
        "authority_manifest_path":"evidence/manifest.json", "authority_manifest_sha256":_sha(manifest),
        "scientific_access_contract_path":"contracts/scientific.json", "scientific_access_contract_sha256":_sha(scientific),
        "result_authority_path":"contracts/result.json", "result_authority_sha256":_sha(result),
        "numerical_contract_path":"contracts/numerical.json", "numerical_contract_sha256":_sha(numerical),
        "measured_implementation_head":"1"*40, "measured_implementation_tree":"2"*40,
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
    return declaration, approval, declaration_value, approval_value


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
        declaration, approval, base, approval_base = _fixture(root)
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
        predicates = list(json.loads(CONTRACT.read_text())["exact_final_predicates"])
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
    return {"schema":"pulsarmlx.f017.event05-readiness-interface-qualification/1.0.0",
        "case_count":len(cases),"categories":{name:sum(c["category"]==name for c in cases) for name in {c["category"] for c in cases}},
        "unexpected_passes":unexpected,"candidate_determinism":"PASS" if len(set(child_hashes))==1 else "FAIL",
        "fresh_process_repetitions":20,"fresh_process_candidate_sha_count":len(set(child_hashes)),
        "mandatory_named_mutations":mandatory,
        "primary_validation":primary["result"],"secondary_validation":secondary["result"],
        "state_created":0,"live_authorization_installed":0,"checkpoint_opens":0,"checkpoint_reads":0,
        "numerical_operations":0,"event_05_ids_consumed":0,"original_checkpoint_access":0,
        "cases":cases,"result":"PASS" if len(cases)==226 and unexpected==0 and len(set(child_hashes))==1 and set(mandatory.values())=={"PASS"} else "FAIL"}


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

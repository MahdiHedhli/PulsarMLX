from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_canonical_serialization_v10 import canonical_bytes
from f017_bounded_artifact_decode_v1 import read_artifact

import f017_event05_candidate_builder_v1 as builder
import f017_event05_readiness_authority_v1 as readiness
import generate_f017_event05_readiness_declaration_v1 as generator
import validate_f017_corrected_oracle_access_v11 as authorizer


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Event05ReadinessAuthorityTests(unittest.TestCase):
    def _bank(self, root: Path, relative: str, value: dict) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
        return path

    def _fixture(self, root: Path, scope: str = "FINAL_EVENT05_EXECUTION_READINESS") -> tuple[Path, dict]:
        contract = read_artifact(readiness.CONTRACT)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
        measurement = self._bank(root, "evidence/measurement.json", {
            "schema":"test.measurement/1", "implementation_head":head,
            "implementation_tree":tree,
        })
        scientific = self._bank(root, "contracts/scientific.json", {"schema":"test.scientific/1"})
        numerical = self._bank(root, "contracts/numerical.json", {"schema":"test.numerical/1"})
        result_authority = self._bank(root, "contracts/result.json", {"schema":"test.result/1"})
        full_native = self._bank(root, "evidence/full-native.json", {"run":101,"required_native_skips":0,"result":"PASS"})
        evidence_only = self._bank(root, "evidence/evidence-only.json", {"run":102,"native_jobs_launched":0,"result":"PASS"})
        if scope == "FINAL_EVENT05_EXECUTION_READINESS":
            gemini_response = self._bank(root, "evidence/gemini-exact-response.json", {"review":"gemini"})
            opus_response = self._bank(root, "evidence/opus-exact-response.json", {"review":"opus"})
            gemini = self._bank(root, "evidence/gemini.json", {
                "schema":contract["scope_policy"][scope]["gemini_schema"], "authority_scope":scope,
                "final_authority":True, "model":"gemini-3.1-pro-high", "reviewed_head":head,
                "exact_response_path":"evidence/gemini-exact-response.json",
                "exact_response_sha256":_sha(gemini_response), "blocking_findings":0,
                "non_blocking_required_findings":0, "unresolved_claims":0,
                "verdict":"NO_UNRESOLVED_MATERIAL_CHALLENGE",
            })
            opus = self._bank(root, "evidence/opus.json", {
                "schema":contract["scope_policy"][scope]["opus_schema"], "authority_scope":scope,
                "final_authority":True, "model":"claude-opus-5", "reviewed_head":head,
                "exact_response_path":"evidence/opus-exact-response.json",
                "exact_response_sha256":_sha(opus_response), "blocking_findings":0,
                "non_blocking_required_findings":0, "unresolved_claims":0,
                "global_verdict":"ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION",
            })
        else:
            gemini = self._bank(root, "evidence/gemini.json", {
                "schema":contract["scope_policy"][scope]["gemini_schema"], "authority_scope":scope,
                "final_authority":False, "live_authority_permitted":False,
                "verdict":"VALIDATION_ONLY_PREPARED",
            })
            opus = self._bank(root, "evidence/opus.json", {
                "schema":contract["scope_policy"][scope]["opus_schema"], "authority_scope":scope,
                "final_authority":False, "live_authority_permitted":False,
                "verdict":"VALIDATION_ONLY_PREPARED",
            })
        artifacts = [
            ("implementation_measurement", measurement), ("scientific_access", scientific),
            ("numerical_contract_v4", numerical), ("result_authority", result_authority),
            ("full_native_ci", full_native), ("evidence_only_ci", evidence_only),
            ("gemini_readiness_interface_challenge", gemini),
            ("opus_readiness_interface_implementation_arbiter", opus),
        ]
        manifest = self._bank(root, "evidence/manifest.json", {
            "schema":contract["scope_policy"][scope]["manifest_schema"],
            "authority_scope":scope, "final_authority":scope == "FINAL_EVENT05_EXECUTION_READINESS",
            "live_authority_permitted":scope == "FINAL_EVENT05_EXECUTION_READINESS", "implementation_head":head,
            "implementation_tree":tree,
            "artifacts":[{"role":role,"path":str(path.relative_to(root)),"sha256":_sha(path)} for role,path in artifacts],
            "binding_count":len(artifacts),
        })
        value = copy.deepcopy(contract["exact_final_predicates" if scope == "FINAL_EVENT05_EXECUTION_READINESS" else "exact_prepared_predicates"])
        value.update({
            "authority_manifest_path":str(manifest.relative_to(root)), "authority_manifest_sha256":_sha(manifest),
            "scientific_access_contract_path":str(scientific.relative_to(root)), "scientific_access_contract_sha256":_sha(scientific),
            "result_authority_path":str(result_authority.relative_to(root)), "result_authority_sha256":_sha(result_authority),
            "numerical_contract_path":str(numerical.relative_to(root)), "numerical_contract_sha256":_sha(numerical),
            "measured_implementation_head":head, "measured_implementation_tree":tree,
            "full_native_evidence_path":str(full_native.relative_to(root)), "full_native_evidence_sha256":_sha(full_native),
            "full_native_run":101,
            "evidence_only_evidence_path":str(evidence_only.relative_to(root)), "evidence_only_evidence_sha256":_sha(evidence_only),
            "evidence_only_run":102,
            "gemini_result_path":str(gemini.relative_to(root)), "gemini_result_sha256":_sha(gemini),
            "opus_result_path":str(opus.relative_to(root)), "opus_result_sha256":_sha(opus),
            "defense_in_depth_findings":0,
        })
        declaration = self._bank(root, "evidence/readiness.json", value)
        return declaration, value

    def test_exact_typed_declaration_and_bindings_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path, _ = self._fixture(Path(raw))
            validated = readiness.validate_readiness_declaration(path, repository_root=Path(raw))
            self.assertEqual(validated.measured_implementation_head, subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
            self.assertEqual(validated.full_native_run, 101)
            with self.assertRaises(TypeError):
                validated.values["event_05_executed"] = True

    def test_uppercase_alias_and_type_substitution_fail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, value = self._fixture(root)
            alias = copy.deepcopy(value)
            alias["ACTIVE_CORRECTED_ORACLE_GENERATION"] = "V11"
            path.write_bytes(canonical_bytes(alias))
            with self.assertRaisesRegex(ValueError, "key census"):
                readiness.validate_readiness_declaration(path, repository_root=root)
            value["event_05_executed"] = 0
            path.write_bytes(canonical_bytes(value))
            with self.assertRaisesRegex(ValueError, "field type"):
                readiness.validate_readiness_declaration(path, repository_root=root)

    def test_bound_sha_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, value = self._fixture(root)
            value["scientific_access_contract_sha256"] = "0" * 64
            path.write_bytes(canonical_bytes(value))
            with self.assertRaisesRegex(ValueError, "bound artifact sha"):
                readiness.validate_readiness_declaration(path, repository_root=root)

    def test_approval_postures_and_shared_builder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            readiness_path, _ = self._fixture(root)
            validated_readiness = readiness.validate_readiness_declaration(readiness_path, repository_root=root)
            approval_value = {
                "schema":"pulsarmlx.f017.event05-readiness-validation-only-approval/1.0.0",
                "decision":"VALIDATE_EVENT05_CANDIDATE_CONSTRUCTION_ONLY", "live":False,
                "approved_at_unix_ns":0, "approval_expires_at_unix_ns":0,
                "active_generation":"V11", "authorization_id":"F017-V11-INERT-AUTH-1",
                "package_attempt_id":"F017-V11-INERT-PACKAGE-1", "primary_event_id":"F017-V11-INERT-PRIMARY-1",
                "secondary_event_id":"F017-V11-INERT-SECONDARY-1", "checkpoint_root":"/nonexistent/inert-checkpoint",
                "canonical_authorization_path":"/nonexistent/inert-auth.json", "installation_receipt_path":"/nonexistent/inert-receipt.json",
                "emergency_evidence_root":"/nonexistent/inert-emergency", "terminal_fallback_evidence_root":"/nonexistent/inert-fallback",
                "authority_manifest_sha256":validated_readiness.authority_manifest_sha256,
                "readiness_declaration_sha256":_sha(readiness_path),
            }
            approval_path = self._bank(root, "evidence/approval.json", approval_value)
            approval = builder.validate_operator_approval(approval_path, "VALIDATION_ONLY")
            context = builder.CandidateContext(
                causal_dag_sha256="3"*64, numerical_contract_sha256="4"*64,
                primary_numerical_sha256="5"*64, secondary_numerical_sha256="6"*64,
                result_authority_sha256="7"*64, implementation_measurement_sha256="8"*64,
                shards=tuple(), tensor_catalog_path="/nonexistent/catalog.json", tensor_catalog_sha256="9"*64,
            )
            memory = {"result":"PASS", "available_memory_bytes":17179869184}
            first = builder.build_operator_go_candidate(approval, validated_readiness, context, memory)
            second = builder.build_operator_go_candidate(approval, validated_readiness, context, memory)
            self.assertEqual(canonical_bytes(first), canonical_bytes(second))
            self.assertFalse(first["live"])
            with self.assertRaisesRegex(ValueError, "approval posture"):
                builder.validate_operator_approval(approval_path, "LIVE_OPERATOR_GO", now_ns=1)

    def test_prepared_readiness_cannot_cross_live_builder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            readiness_path, _ = self._fixture(root, "VALIDATION_ONLY_PREPARED")
            validated = readiness.validate_readiness_declaration(
                readiness_path, expected_scope="VALIDATION_ONLY_PREPARED", repository_root=root,
            )
            now = time.time_ns()
            approval = {
                "schema":"pulsarmlx.f017.corrected-oracle-event05-operator-approval/11.1.0",
                "decision":"GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05", "live":True,
                "approved_at_unix_ns":now - 1, "approval_expires_at_unix_ns":now + 1_000_000_000,
                "active_generation":"V11", "authorization_id":"F017-LIVE-AUTH-05-V11-PREPARED-REJECT",
                "package_attempt_id":"F017-LIVE-PACKAGE-05-V11-PREPARED-REJECT",
                "primary_event_id":"F017-LIVE-PRIMARY-05-V11-PREPARED-REJECT",
                "secondary_event_id":"F017-LIVE-SECONDARY-05-V11-PREPARED-REJECT",
                "checkpoint_root":"/nonexistent/checkpoint", "canonical_authorization_path":"/nonexistent/auth",
                "installation_receipt_path":"/nonexistent/receipt", "emergency_evidence_root":"/nonexistent/emergency",
                "terminal_fallback_evidence_root":"/nonexistent/fallback",
                "authority_manifest_sha256":validated.authority_manifest_sha256,
                "readiness_declaration_sha256":_sha(readiness_path),
            }
            approval_path = self._bank(root, "live-approval.json", approval)
            admitted = builder.validate_operator_approval(approval_path, "LIVE_OPERATOR_GO", now_ns=now)
            context = builder.CandidateContext(*(["3"*64]*6), tuple(), "/nonexistent/catalog", "4"*64)
            with self.assertRaisesRegex(ValueError, "requires final readiness"):
                builder.build_operator_go_candidate(admitted, validated, context, {"result":"PASS"})

    def test_generator_is_canonical_and_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, value = self._fixture(root)
            output = root / "generated.json"
            digest = generator.emit_readiness_declaration(output, value)
            self.assertEqual(digest, _sha(output))
            self.assertEqual(output.read_bytes(), canonical_bytes(value))
            with self.assertRaises(FileExistsError):
                generator.emit_readiness_declaration(output, value)

    def test_authorizer_has_one_readiness_path_and_no_uppercase_aliases(self) -> None:
        source = (ROOT / "scripts/research/validate_f017_corrected_oracle_access_v11.py").read_text()
        self.assertIn("validate_readiness_declaration", source)
        self.assertIn("build_operator_go_candidate", source)
        self.assertNotIn("F017_CORRECTED_ORACLE_EVENT05_EXECUTION_READINESS", source)
        self.assertNotIn("READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05_EXECUTION_GO", source)
        self.assertNotIn("ACTIVE_CORRECTED_ORACLE_GENERATION", source)

    def test_live_install_rederives_candidate_and_rejects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            readiness_path, _ = self._fixture(root)
            validated_readiness = readiness.validate_readiness_declaration(
                readiness_path, repository_root=root,
            )
            now = time.time_ns()
            approval_value = {
                "schema":"pulsarmlx.f017.corrected-oracle-event05-operator-approval/11.1.0",
                "decision":"GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05", "live":True,
                "approved_at_unix_ns":now - 1, "approval_expires_at_unix_ns":now + 10_000_000_000,
                "active_generation":"V11", "authorization_id":"F017-LIVE-AUTHORITY-05-V11-1",
                "package_attempt_id":"F017-LIVE-PACKAGE-05-V11-1",
                "primary_event_id":"F017-LIVE-PRIMARY-05-V11-1",
                "secondary_event_id":"F017-LIVE-SECONDARY-05-V11-1",
                "checkpoint_root":str(root / "checkpoint"),
                "canonical_authorization_path":str(root / "live-authorization.json"),
                "installation_receipt_path":str(root / "installation-receipt.json"),
                "emergency_evidence_root":str(root / "emergency"),
                "terminal_fallback_evidence_root":str(root / "fallback"),
                "authority_manifest_sha256":validated_readiness.authority_manifest_sha256,
                "readiness_declaration_sha256":_sha(readiness_path),
            }
            approval_path = self._bank(root, "approval.json", approval_value)
            approval = builder.validate_operator_approval(
                approval_path, "LIVE_OPERATOR_GO", now_ns=now,
            )
            context = builder.CandidateContext(
                causal_dag_sha256=_sha(authorizer.DAG),
                numerical_contract_sha256=_sha(authorizer.NUMERICAL_V4),
                primary_numerical_sha256=_sha(authorizer.PRIMARY_V3),
                secondary_numerical_sha256=_sha(authorizer.SECONDARY_V3),
                result_authority_sha256=_sha(authorizer.RESULT_AUTHORITY),
                implementation_measurement_sha256=_sha(authorizer.IMPLEMENTATION_MEASUREMENT),
                shards=tuple(authorizer.production_shards()),
                tensor_catalog_path=str(authorizer.PRODUCTION_CATALOG),
                tensor_catalog_sha256=_sha(authorizer.PRODUCTION_CATALOG),
            )
            memory = {
                "result":"PASS", "enforced":True, "threshold_bytes":17179869184,
                "sample_age_ns":0,
                "observation":{"parser_version":"F017_VALIDATION_ONLY_V1", "page_size_bytes":16384,
                    "pages_free":0, "pages_inactive":0, "pages_speculative":0, "pages_purgeable":0,
                    "available_bytes":17179869184, "canonical_observation":"VALIDATION_ONLY_NO_LIVE_AUTHORITY",
                    "stdout_sha256":"0"*64, "observed_at_unix_ns":1},
            }
            candidate = builder.build_operator_go_candidate(
                approval, validated_readiness, context, memory,
            )
            self.assertFalse(candidate["live"])
            candidate_path = self._bank(root, "candidate.json", candidate)
            with (mock.patch.object(authorizer, "validate_readiness_declaration", return_value=validated_readiness),
                  mock.patch.object(authorizer, "_candidate_context", return_value=context)):
                report = authorizer.validate_live_candidate_for_install(candidate_path)
                self.assertEqual(report["candidate_sha256"], _sha(candidate_path))
                candidate["checkpoint_root"] = str(root / "forged-checkpoint")
                candidate_path.write_bytes(canonical_bytes(candidate))
                with self.assertRaisesRegex(ValueError, "candidate rederivation"):
                    authorizer.validate_live_candidate_for_install(candidate_path)
            self.assertFalse(Path(approval_value["canonical_authorization_path"]).exists())
            self.assertFalse(Path(approval_value["installation_receipt_path"]).exists())

    def test_repository_bound_artifacts_are_canonical_and_tree_exact(self) -> None:
        current_measurement = read_artifact(
            ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json"
        )
        full_native = read_artifact(
            ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-full-native-ci-v6.json"
        )
        evidence_only = read_artifact(
            ROOT / "docs/architecture/reviews/evidence/f017-event05-v11-terminal-failure-evidence-only-ci-v2.json"
        )
        prepared_declaration = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-prepared-declaration-v5.json"
        prepared = readiness.validate_readiness_declaration(
            prepared_declaration, expected_scope="VALIDATION_ONLY_PREPARED",
        )
        prepared_manifest = read_artifact(
            ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-prepared-runtime-authority-manifest-v6.json"
        )
        instantiability = read_artifact(
            ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-prepared-production-instantiability-v6.json"
        )
        qualification = read_artifact(
            ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-qualification-v4.json"
        )
        self.assertEqual(full_native["result"], "PASS")
        self.assertEqual(full_native["required_native_skips"], 0)
        self.assertEqual(evidence_only["native_jobs_launched"], 0)
        self.assertEqual(prepared.authority_scope, "VALIDATION_ONLY_PREPARED")
        self.assertFalse(prepared_manifest["final_authority"])
        self.assertFalse(prepared_manifest["live_authority_permitted"])
        self.assertEqual(instantiability["repetitions"], 20)
        self.assertEqual(instantiability["deterministic_candidate_sha_count"], 1)
        self.assertEqual(qualification["case_count"], 251)
        self.assertEqual(qualification["categories"]["final_review_bindings"], 20)
        self.assertEqual(qualification["final_scope_validation"], "PASS")
        self.assertEqual(qualification["unexpected_passes"], 0)
        exact_tree = subprocess.check_output(
            ["git", "rev-parse", f"{current_measurement['implementation_head']}^{{tree}}"],
            cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(exact_tree, current_measurement["implementation_tree"])


if __name__ == "__main__":
    unittest.main()

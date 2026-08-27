from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_canonical_serialization_v10 import canonical_bytes

import f017_event05_candidate_builder_v1 as builder
import f017_event05_readiness_authority_v1 as readiness
import generate_f017_event05_readiness_declaration_v1 as generator


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Event05ReadinessAuthorityTests(unittest.TestCase):
    def _bank(self, root: Path, relative: str, value: dict) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
        return path

    def _fixture(self, root: Path) -> tuple[Path, dict]:
        contract = json.loads(readiness.CONTRACT.read_text())
        head = "1" * 40
        tree = "2" * 40
        measurement = self._bank(root, "evidence/measurement.json", {
            "schema":"test.measurement/1", "implementation_head":head,
            "implementation_tree":tree,
        })
        scientific = self._bank(root, "contracts/scientific.json", {"schema":"test.scientific/1"})
        numerical = self._bank(root, "contracts/numerical.json", {"schema":"test.numerical/1"})
        result_authority = self._bank(root, "contracts/result.json", {"schema":"test.result/1"})
        full_native = self._bank(root, "evidence/full-native.json", {"run":101,"required_native_skips":0,"result":"PASS"})
        evidence_only = self._bank(root, "evidence/evidence-only.json", {"run":102,"native_jobs_launched":0,"result":"PASS"})
        gemini = self._bank(root, "evidence/gemini.json", {"verdict":"NO_UNRESOLVED_MATERIAL_CHALLENGE"})
        opus = self._bank(root, "evidence/opus.json", {"global_verdict":"ACCEPT_F017_EVENT05_READINESS_INTERFACE_IMPLEMENTATION"})
        artifacts = [
            ("implementation_measurement", measurement), ("scientific_access", scientific),
            ("numerical_contract_v4", numerical), ("result_authority", result_authority),
            ("full_native_ci", full_native), ("evidence_only_ci", evidence_only),
            ("gemini_readiness_interface_challenge", gemini),
            ("opus_readiness_interface_implementation_arbiter", opus),
        ]
        manifest = self._bank(root, "evidence/manifest.json", {
            "schema":"test.manifest/1", "implementation_head":head,
            "implementation_tree":tree,
            "artifacts":[{"role":role,"path":str(path.relative_to(root)),"sha256":_sha(path)} for role,path in artifacts],
            "binding_count":len(artifacts),
        })
        value = copy.deepcopy(contract["exact_final_predicates"])
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
            self.assertEqual(validated.measured_implementation_head, "1" * 40)
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


if __name__ == "__main__":
    unittest.main()

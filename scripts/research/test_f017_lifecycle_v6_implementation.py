#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from f017_corrected_oracle_compare_v6 import MAX_ABS, RMSE_MAX, COSINE_MIN, TOP_N, compare
from f017_corrected_oracle_authorization_v6 import PRIMARY_ROLE, PRODUCTION_GEOMETRY_PATH, canonical_bytes, load_interface, parse_authorization, validate_authority_bindings, validate_checkpoint_root_descriptor, validate_implementation_measurement
from f017_corrected_oracle_wrapper_support_v6 import require_active
from f017_lifecycle_semantics_v6 import MODEL_PATH, derive_outcome_obligations, load_json
from qualify_f017_lifecycle_v6 import execute_failure_variant, qualify_outcomes, run_package
from qualify_f017_corrected_oracle_target_adapters_v6 import run_once as run_adapter
from validate_f017_corrected_oracle_access_v6 import validate_operator_approval

ROOT = Path(__file__).resolve().parents[2]


class LifecycleV6ImplementationTests(unittest.TestCase):
    def test_real_synthetic_control_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-v6-test-") as temporary:
            result = run_package(Path(temporary), 18101)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["handshake_checkpoint_opens"], 0)
        self.assertEqual(result["handshake_checkpoint_reads"], 0)
        self.assertEqual(result["historical_ledger_before"], 175)
        self.assertEqual(result["historical_ledger_after"], 175)

    def test_success_artifacts_match_generated_schema_censuses(self) -> None:
        schemas = load_json(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-artifact-schemas-v6.json")["artifacts"]
        with tempfile.TemporaryDirectory(prefix="f017-v6-artifacts-") as temporary:
            work = Path(temporary)
            run_package(work, 18101)
            paths = {
                "primary_candidate_validation_report": work / "candidate-reports/primary-candidate-validation.json",
                "secondary_candidate_validation_report": work / "candidate-reports/secondary-candidate-validation.json",
                "installation_receipt": work / "installation-receipt.json",
                "primary_installed_validation_report": work / "lifecycle-authority/primary-installed-validation.json",
                "secondary_installed_validation_report": work / "lifecycle-authority/secondary-installed-validation.json",
                "coordinator_handshake": work / "lifecycle-authority/coordinator-handshake.json",
                "package_claim": work / "package-state/claim.json",
                "package_durable_start": work / "package-state/durable-start.json",
                "package_ledger_entry": work / "package-state/ledger.json",
                "package_ledger_index": work / "package-state/ledger-index.json",
                "primary_durable_start": work / "package-state/primary/durable-start.json",
                "primary_ledger_entry": work / "package-state/primary/ledger.json",
                "primary_ledger_index": work / "package-state/primary/ledger-index.json",
                "primary_receipt": work / "package-state/primary/receipt.json",
                "primary_terminal": work / "package-state/primary/terminal.json",
                "secondary_durable_start": work / "package-state/secondary/durable-start.json",
                "secondary_ledger_entry": work / "package-state/secondary/ledger.json",
                "secondary_ledger_index": work / "package-state/secondary/ledger-index.json",
                "secondary_receipt": work / "package-state/secondary/receipt.json",
                "secondary_terminal": work / "package-state/secondary/terminal.json",
                "comparison_receipt": work / "package-output/comparison.json",
                "comparison_terminal": work / "package-output/comparison-terminal.json",
                "package_receipt": work / "package-state/receipt.json",
                "package_terminal": work / "package-state/terminal.json",
            }
            for kind, path in paths.items():
                value = load_json(path)
                self.assertEqual(set(value), {"schema", "bindings", "payload"}, kind)
                self.assertEqual(value["schema"], schemas[kind]["artifact_schema_id"], kind)
                self.assertEqual(set(value["payload"]), set(schemas[kind]["payload_key_census"]), kind)

    def test_every_outcome_trace_obligation(self) -> None:
        model = load_json(MODEL_PATH)
        expected = len(derive_outcome_obligations(model)["variants"])
        self.assertEqual(qualify_outcomes(), {"variant_count": expected, "result": "PASS"})

    def test_failure_trace_is_actually_file_backed_and_read_back(self) -> None:
        model = load_json(MODEL_PATH)
        variant_id = "TERMINAL::SECONDARY_PRE_START_FAILURE"
        obligation = derive_outcome_obligations(model)["variants"][variant_id]
        with tempfile.TemporaryDirectory(prefix="f017-v6-failure-execution-") as temporary:
            result = execute_failure_variant(Path(temporary) / "trace", variant_id, obligation)
            summaries = list((Path(temporary) / "trace").glob("summary.json"))
            receipts = list((Path(temporary) / "trace").glob("[0-9][0-9]-*.json"))
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["transition_count"], len(obligation["trace"]))
        self.assertEqual(len(summaries), 1)
        self.assertEqual(len(receipts), len(obligation["trace"]))

    def test_frozen_comparison(self) -> None:
        layer = {"selected_expert_ids": [1, 2]}
        result = compare(
            {"full_logits": [0.0, 1.0], "selected_token": 1, "top_1_margin": 1.0, "layers": [layer]},
            {"full_logits": [0.0, 1.0], "selected_token": 1, "top_1_margin": 1.0, "layers": [layer]},
        )
        self.assertEqual(result["classification"], "EXACT_EXPECTED_TOKEN_STABLE")
        self.assertEqual((MAX_ABS, RMSE_MAX, COSINE_MIN, TOP_N), (0.0065169706285814755, 0.003463567697419031, 0.9999999985448085, 32))

    def test_canonical_serializer_hex_encodes_every_float(self) -> None:
        encoded = canonical_bytes({"nested": [{"value": 0.5}], "negative": -0.0})
        self.assertEqual(encoded, b'{"negative":"-0x0.0p+0","nested":[{"value":"0x1.0000000000000p-1"}]}\n')

    def test_candidate_rejects_false_authority_sha_before_install(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-v6-authority-binding-") as temporary:
            work = Path(temporary)
            run_adapter(work, 18101)
            document = json.loads((work / "candidate.json").read_text(encoding="utf-8"))
            document["lifecycle_semantic_model_sha256"] = "0" * 64
            forged = work / "forged-candidate.json"
            forged.write_bytes(canonical_bytes(document))
            with self.assertRaisesRegex(ValueError, "authority byte binding"):
                parse_authorization(
                    forged,
                    work / "interface.json",
                    role=PRIMARY_ROLE,
                    executing_path=ROOT / "scripts/research/f017_corrected_oracle_primary_v6.py",
                    target_source_path=ROOT / "scripts/research/f017_corrected_oracle_primary_target_source_v6.py",
                    require_installed=False,
                )

    def test_production_capability_and_geometry_paths_are_canonical(self) -> None:
        interface_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"
        interface = load_interface(interface_path)
        document = {
            "authority_scope": "PRODUCTION",
            "geometry_path": PRODUCTION_GEOMETRY_PATH,
            "lifecycle_semantic_model_sha256": interface["semantic_model_sha256"],
            "primary": {"capability_path": "README.md"},
            "secondary": {"capability_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v6.json"},
        }
        with self.assertRaisesRegex(ValueError, "canonical production primary capability path"):
            validate_authority_bindings(document, interface, interface_path)

    def test_false_operator_go_cannot_install_production_authority(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-v6-false-go-") as temporary:
            approval_path = Path(temporary) / "approval.json"
            approval = {
                "schema": "pulsarmlx.f017.corrected-oracle-operator-approval/6.0.0",
                "bindings": {},
                "payload": {
                    "decision": "GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04",
                    "approved_at_utc": "2026-08-24T00:00:00Z",
                    "operator_identity": "synthetic-negative-test",
                    "new_go": False,
                    "prior_go_reused": False,
                    "p1_attempt_2": False,
                },
            }
            approval_path.write_bytes(canonical_bytes(approval))
            approval_sha = hashlib.sha256(approval_path.read_bytes()).hexdigest()
            document = {"authority_scope": "PRODUCTION", "operator_approval_sha256": approval_sha}
            with self.assertRaisesRegex(ValueError, "fresh Event-04 operator GO required"):
                validate_operator_approval(
                    document,
                    approval_path,
                    approval_sha,
                    allow_synthetic=False,
                    allow_rehearsal=False,
                )

    def test_measurement_manifest_binds_head_and_current_load_bearing_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-v6-measurement-substitution-") as temporary:
            prior = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v6-implementation-measurement-v2.json").read_text(encoding="utf-8"))
            entries = []
            for prior_entry in prior["entries"]:
                data = (ROOT / prior_entry["path"]).read_bytes()
                entries.append({
                    **prior_entry,
                    "git_blob_sha": hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest(),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
            manifest = {
                **prior,
                "implementation_head": "1" * 40,
                "git_tree_sha": "2" * 40,
                "entries": entries,
                "entry_count": len(entries),
            }
            manifest_path = Path(temporary) / "measurement.json"
            manifest_path.write_bytes(canonical_bytes(manifest))
            document = {
                "branch": manifest["branch"],
                "implementation_measurement_head": manifest["implementation_head"],
            }
            validate_implementation_measurement(document, manifest_path)
            forged_head = dict(document)
            forged_head["implementation_measurement_head"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "implementation measurement authority"):
                validate_implementation_measurement(forged_head, manifest_path)
            forged_manifest = dict(manifest)
            forged_manifest["entries"] = [dict(entry) for entry in manifest["entries"]]
            forged_manifest["entries"][0]["sha256"] = "0" * 64
            forged_path = Path(temporary) / "forged-measurement.json"
            forged_path.write_bytes(canonical_bytes(forged_manifest))
            with self.assertRaisesRegex(ValueError, "implementation measurement byte substitution"):
                validate_implementation_measurement(document, forged_path)

    def test_synthetic_coordinator_obeys_active_generation_kill_switch(self) -> None:
        source = (ROOT / "scripts/research/execute_f017_corrected_oracle_event_v6.py").read_text(encoding="utf-8")
        self.assertNotIn('if document["authority_scope"] != "SYNTHETIC_QUALIFICATION"', source)
        self.assertIn('require_active(document["authority_scope"])', source)

    def test_only_reviewed_v6_production_generation_is_active(self) -> None:
        require_active("PRODUCTION")

    def test_no_access_rehearsal_accepts_absent_production_path_descriptor(self) -> None:
        absent = Path("/Users/runner/f017-production-checkpoint-intentionally-absent")
        self.assertFalse(absent.exists())
        validate_checkpoint_root_descriptor(
            {"authority_scope": "PRODUCTION_SHAPED_REHEARSAL", "checkpoint_root": str(absent)},
            absent,
        )
        with self.assertRaises(FileNotFoundError):
            validate_checkpoint_root_descriptor(
                {"authority_scope": "PRODUCTION", "checkpoint_root": str(absent)},
                absent,
            )

    def test_shadow_rehearsal_cannot_turn_low_memory_into_authority(self) -> None:
        source = (ROOT / "scripts/research/rehearse_f017_corrected_oracle_event04_v6.py").read_text(encoding="utf-8")
        self.assertIn('future_memory_gate = "PASS" if observation.available_bytes >= THRESHOLD else "FAIL_CLOSED"', source)
        self.assertIn('"event_04_authorization_created": False', source)
        self.assertIn('"operator_go": False', source)

    def test_authorizer_and_coordinator_do_not_import_numerical_cores(self) -> None:
        for relative in (
            "scripts/research/validate_f017_corrected_oracle_access_v6.py",
            "scripts/research/execute_f017_corrected_oracle_event_v6.py",
        ):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            self.assertFalse(any("numerics_v2" in name for name in imported))

    def test_no_event04_or_original_checkpoint_literals(self) -> None:
        for relative in (
            "scripts/research/validate_f017_corrected_oracle_access_v6.py",
            "scripts/research/execute_f017_corrected_oracle_event_v6.py",
            "scripts/research/qualify_f017_lifecycle_v6.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("F017-CORRECTED-ORACLE-LIVE-AUTHORIZATION-04", source)
            self.assertNotIn("GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf", source)


if __name__ == "__main__":
    unittest.main()

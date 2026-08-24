#!/usr/bin/env python3
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from f017_corrected_oracle_compare_v6 import MAX_ABS, RMSE_MAX, COSINE_MIN, TOP_N, compare
from f017_corrected_oracle_authorization_v6 import validate_checkpoint_root_descriptor
from f017_corrected_oracle_wrapper_support_v6 import require_active
from f017_lifecycle_semantics_v6 import MODEL_PATH, derive_outcome_obligations, load_json
from qualify_f017_lifecycle_v6 import execute_failure_variant, qualify_outcomes, run_package

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

    def test_production_is_inactive_before_final_acceptance(self) -> None:
        with self.assertRaises(ValueError):
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

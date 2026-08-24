#!/usr/bin/env python3
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from f017_corrected_oracle_compare_v6 import MAX_ABS, RMSE_MAX, COSINE_MIN, TOP_N, compare
from f017_corrected_oracle_wrapper_support_v6 import require_active
from f017_lifecycle_semantics_v6 import MODEL_PATH, derive_outcome_obligations, load_json
from qualify_f017_lifecycle_v6 import qualify_outcomes, run_package

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

    def test_every_outcome_trace_obligation(self) -> None:
        model = load_json(MODEL_PATH)
        expected = len(derive_outcome_obligations(model)["variants"])
        self.assertEqual(qualify_outcomes(), {"variant_count": expected, "result": "PASS"})

    def test_frozen_comparison(self) -> None:
        layer = {"selected_expert_ids": [1, 2]}
        result = compare(
            {"full_logits": [0.0, 1.0], "selected_token": 1, "layers": [layer]},
            {"full_logits": [0.0, 1.0], "selected_token": 1, "layers": [layer]},
        )
        self.assertEqual(result["classification"], "EXACT_EXPECTED_TOKEN_STABLE")
        self.assertEqual((MAX_ABS, RMSE_MAX, COSINE_MIN, TOP_N), (0.0065169706285814755, 0.003463567697419031, 0.9999999985448085, 32))

    def test_production_is_inactive_before_final_acceptance(self) -> None:
        with self.assertRaises(ValueError):
            require_active("PRODUCTION")

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

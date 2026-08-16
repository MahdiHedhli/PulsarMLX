from __future__ import annotations

import unittest

from scripts.research import validate_f017_dprefix_real_numerical_surface as V


class DensePrefixRealNumericalSurfaceTests(unittest.TestCase):
    def test_reviewed_release_fails_before_consumption(self) -> None:
        result = V.validate_checkpoint_free()
        self.assertEqual(result["result"], "NOT_READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE")
        self.assertEqual(result["reason_code"], "TIER_B_NUMERICAL_SURFACE_UNINSTANTIABLE")
        self.assertFalse(result["attempt_consumed"])
        self.assertEqual(result["checkpoint_reads"], 0)
        self.assertEqual(result["ledger"], 59)

    def test_hash_only_surfaces_cannot_establish_tier_b(self) -> None:
        facts = V.validate_checkpoint_free()["facts"]
        self.assertTrue(facts["candidate_intermediate_stage_hashes_retained"])
        self.assertTrue(facts["oracle_intermediate_stage_hashes_retained"])
        self.assertFalse(facts["candidate_intermediate_values_retained"])
        self.assertFalse(facts["oracle_intermediate_values_retained"])
        self.assertFalse(facts["hashes_can_derive_error_metrics"])
        self.assertTrue(facts["tier_b_requires_per_layer_metrics"])
        self.assertTrue(facts["tier_b_requires_intermediate_attention_metrics"])

    def test_banked_nonexecution_reconciles_without_payload_event(self) -> None:
        result = V.validate_banked_nonexecution()
        self.assertEqual(result["result"], "BANKED_NONEXECUTION_RECONCILED")
        self.assertFalse(result["attempt_consumed"])
        self.assertEqual(result["payloads"], 0)
        self.assertEqual(result["ledger"], 59)


if __name__ == "__main__":
    unittest.main()

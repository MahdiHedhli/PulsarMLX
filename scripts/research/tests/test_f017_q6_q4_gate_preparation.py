from __future__ import annotations

import copy
import hashlib
import json
import struct
import unittest
from pathlib import Path

from scripts.research import f017_q6_q4_gate_preparation as M


ROOT = Path(__file__).resolve().parents[3]


class Q6DefectAndQ4GatePreparationTests(unittest.TestCase):
    def test_minimized_fixture_exposes_q2_then_q3_lane_swap(self):
        fixture = M.minimized_q6_fixture()
        old = M.f32le(M.decode_q6_old(fixture))
        corrected = M.f32le(M.decode_q6_corrected(fixture))
        self.assertNotEqual(old, corrected)
        old_values = struct.unpack("<256f", old)
        corrected_values = struct.unpack("<256f", corrected)
        self.assertEqual(old_values[32], -22.0)
        self.assertEqual(corrected_values[32], -30.0)
        self.assertEqual(old_values[64], -30.0)
        self.assertEqual(corrected_values[64], -22.0)
        self.assertEqual(struct.pack("<f", corrected_values[32]).hex(), "0000f0c1")

    def test_corrected_q2_lane_uses_l_plus_32_low_nibble(self):
        values = M.decode_q6_corrected(M.minimized_q6_fixture())
        self.assertEqual(values[32], -30.0)

    def test_corrected_q3_lane_uses_l_high_nibble(self):
        values = M.decode_q6_corrected(M.minimized_q6_fixture())
        self.assertEqual(values[64], -22.0)

    def test_multiple_groups_sign_bits_and_scales_match_three_paths(self):
        block = M.patterned_q6_fixture()
        a, b, c = M.q6_python_decoded_paths(block)
        self.assertEqual(M.f32le(a), M.f32le(b))
        self.assertEqual(M.f32le(a), M.f32le(c))
        self.assertTrue(any(value < 0 for value in a))
        self.assertTrue(any(value > 0 for value in a))

    def test_two_block_boundary_and_canonical_serialization(self):
        block = M.patterned_q6_fixture()
        decoded = M.decode_q6_blocks(block + block)
        self.assertEqual(len(decoded), 512)
        self.assertEqual(M.f32le(decoded[:256]), M.f32le(decoded[256:]))
        self.assertEqual(len(M.f32le(decoded)), 2048)

    def test_q6_three_way_independence_is_fail_closed(self):
        value = M.q6_defect_record()
        self.assertEqual(value["independence_verdict"], "THREE_WAY_INDEPENDENCE_ESTABLISHED")
        self.assertEqual({row["classification"] for row in value["pairwise_independence"]}, {"INDEPENDENT"})
        mutation = copy.deepcopy(value)
        mutation["implementations"][1]["imports"].append("decode_q6_k_spec")
        with self.assertRaisesRegex(ValueError, "decoder independence"):
            M.validate_q6_defect_record(mutation)

    def test_f017_impact_scan_is_unaffected_and_f016_is_annotated(self):
        impact = M.historical_impact()
        self.assertEqual(impact["f017_verdict"], "F017_ACCEPTED_EVIDENCE_UNAFFECTED")
        self.assertTrue(all("Q6_K" not in row["real_quantizations"] for row in impact["f017_surfaces"]))
        self.assertEqual(impact["f016_annotation"]["absolute_q6_decoder_truth"], "NOT_ESTABLISHED")
        self.assertTrue(impact["historical_artifacts_rewritten"] is False)

    def test_q6_target_is_reselected_mechanically_and_not_authorized(self):
        package = M.q6_future_package()
        self.assertEqual(package["status"], "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED")
        self.assertEqual(package["selected_target"]["tensor_name"], "blk.0.ffn_down.weight")
        self.assertEqual(package["selected_target"]["offset"], 1_203_482_464)
        self.assertEqual(package["selected_target"]["packed_length"], 61_931_520)
        self.assertEqual(len(package["candidates"]), 3)
        self.assertEqual(package["future_budget"]["tensor_payloads"], 1)

    def test_q4_authorization_package_is_one_payload_zero_compute_and_unconsumed(self):
        package = M.q4_authorization_package()
        self.assertEqual(package["status"], "PREPARED_FOR_AUTHORIZATION_NOT_AUTHORIZED_NOT_EXECUTED")
        self.assertEqual(package["target"]["tensor_name"], "token_embd.weight")
        self.assertEqual(package["target"]["offset"], 535_316_320)
        self.assertEqual(package["target"]["packed_length"], 535_265_280)
        self.assertEqual(package["future_access_budget"]["tensor_payloads"], 1)
        self.assertEqual(package["future_access_budget"]["model_compute"], 0)
        self.assertEqual(package["future_ledger"], {"before": 57, "after_success": 58})
        self.assertFalse(package["attempt"]["consumed"])
        self.assertFalse(package["execution_authorized"])

    def test_q4_truth_chain_requires_exact_three_way_equality(self):
        value = M.q4_authorization_package()
        self.assertEqual(len(value["decoder_truth_chain"]), 3)
        self.assertEqual(value["acceptance"]["comparison"], "EXACT_LE_F32_A_EQ_B_EQ_C")
        self.assertEqual(value["acceptance"]["disagreement"], "DECODER_TRUTH_UNRESOLVED")
        self.assertEqual({row["classification"] for row in value["decoder_truth_chain"]}, {"INDEPENDENT"})
        self.assertEqual(len(value["pairwise_independence"]), 3)
        mutation = copy.deepcopy(value)
        mutation["decoder_truth_chain"][1]["imports"].append("dequantize_row_q4_k")
        with self.assertRaisesRegex(ValueError, "Q4_K decoder independence"):
            M.validate_q4_authorization_package(mutation)

    def test_q4_config_and_attempt_ledger_remain_non_executable(self):
        config = M.q4_execution_config()
        binding = M.q4_authorization_binding()
        ledger = M.q4_attempt_ledger()
        self.assertEqual(config["status"], "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED")
        self.assertFalse(config["execution_authorized"])
        self.assertFalse(config["attempt"]["automatic_retry"])
        self.assertEqual(config["access_budget"]["candidate_model_compute"], 0)
        self.assertEqual(binding["review_required"], "GO FOR ONE Q4_K REAL-BYTE QUALIFICATION")
        self.assertTrue(binding["separate_operator_execution_instruction_required"])
        self.assertEqual(ledger["attempts"], [])
        self.assertEqual(ledger["real_payload_ledger"], 57)

    def test_banked_artifacts_regenerate_and_ledger_remains_57(self):
        generated = M.package()
        for filename, value in generated["artifacts"].items():
            banked = json.loads((ROOT / "docs/architecture/reviews/evidence" / filename).read_text())
            self.assertEqual(banked, value)
        self.assertEqual(generated["ledger"], 57)
        self.assertEqual(generated["real_checkpoint_access"], 0)

    def test_historical_and_dense_prefix_bindings_are_immutable(self):
        manifest = M.immutability_manifest()
        for row in manifest["artifacts"]:
            actual = hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
            self.assertEqual(actual, row["sha256"])
        self.assertFalse(manifest["dense_prefix_numerical_semantics_changed"])


if __name__ == "__main__":
    unittest.main()

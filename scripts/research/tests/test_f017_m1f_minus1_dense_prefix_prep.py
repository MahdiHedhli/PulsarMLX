from __future__ import annotations

import copy
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from scripts.research import f017_m1f_minus1_dense_prefix_prep as M


ROOT = Path(__file__).resolve().parents[3]


class M1FMinus1DensePrefixPrepTests(unittest.TestCase):
    def test_preparation_contract_binds_every_generated_artifact(self):
        contract = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f-minus1-preparation-v1.json").read_text())
        self.assertEqual(contract["status"], "PREPARED_NOT_AUTHORIZED")
        self.assertEqual(contract["checkpoint_access"], 0)
        self.assertEqual(contract["decoder_gate_sequence"], ["Q4_K", "Q6_K"])
        self.assertEqual(contract["exact_logical_tensor_count"], 40)
        self.assertTrue(contract["reuse_requires_separate_review_and_authorization"])
        for binding in contract["artifacts"].values():
            payload = (ROOT / binding["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), binding["sha256"])

    def test_prompt_package_is_exact_public_safe_and_preobserved(self):
        value = M.prompt_package()
        self.assertEqual(value["payload"]["prompt_text"], "Hello")
        self.assertEqual(value["payload"]["prompt_utf8_hex"], "48656c6c6f")
        self.assertEqual(value["payload"]["token_ids"], [9703])
        self.assertEqual(value["payload"]["token_bytes_hex"], struct.pack("<I", 9703).hex())
        self.assertFalse(value["selection_policy"]["best_of_n"])
        self.assertEqual(value["checkpoint_access"], 0)
        self.assertEqual(value["payload_sha256"], M.sha256(M.canonical_bytes(value["payload"])))

    def test_independent_inventory_has_all_40_full_metadata_records(self):
        value = M.reconstruct_inventory()
        self.assertEqual(value["tensor_count"], 40)
        self.assertEqual(value["access_budget"]["packed_bytes"], 1_431_263_232)
        self.assertEqual(value["access_budget"]["decoded_f32_bytes_upper_bound"], 8_504_653_824)
        self.assertEqual(value["unqualified_real_families"], ["Q4_K", "Q6_K"])
        self.assertEqual(len({row["metadata_identity_sha256"] for row in value["tensors"]}), 40)
        for row in value["tensors"]:
            self.assertEqual(len(row["catalog_entry_sha256"]), 64)
            self.assertEqual(len(row["map_contract_sha256"]), 64)
            self.assertIsNone(row["packed_sha256"])
            self.assertIsNone(row["decoded_sha256"])
            self.assertNotIn("indexer", row["name"])

    def test_inventory_matches_independent_earlier_summary_but_not_generator(self):
        prior = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-fallback-inventory-v1.json").read_text())
        actual = M.reconstruct_inventory()
        self.assertEqual(actual["access_budget"]["tensor_payloads"], prior["access_budget"]["tensor_payloads"])
        self.assertEqual(actual["access_budget"]["packed_bytes"], prior["access_budget"]["packed_bytes"])
        for family, row in actual["quantization_table"].items():
            self.assertEqual(row["tensor_count"], prior["quantization_inventory"][family]["tensor_count"])
            self.assertEqual(row["packed_bytes"], prior["quantization_inventory"][family]["packed_bytes"])

    def test_inventory_fails_on_missing_shape_quant_or_alignment(self):
        original = json.loads(M.CATALOG.read_text())
        mutations = []
        missing = copy.deepcopy(original); missing["tensors"] = [row for row in missing["tensors"] if row["name"] != "blk.2.ffn_up.weight"]
        mutations.append((missing, "missing dense-prefix"))
        shape = copy.deepcopy(original); next(row for row in shape["tensors"] if row["name"] == "blk.1.attn_q_b.weight")["dims"][0] = 2047
        mutations.append((shape, "catalog/map mismatch"))
        quant = copy.deepcopy(original); next(row for row in quant["tensors"] if row["name"] == "blk.0.ffn_down.weight")["type"] = "Q5_K"
        mutations.append((quant, "catalog/map mismatch"))
        for value, error in mutations:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "catalog.json"; path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, error): M.reconstruct_inventory(path)

    def test_decoder_targets_are_mechanical_and_sequenced(self):
        targets = M.select_decoder_targets(M.reconstruct_inventory())
        self.assertEqual(targets["sequence"], ["Q4_K", "Q6_K"])
        self.assertEqual(targets["targets"]["Q4_K"]["tensor_name"], "token_embd.weight")
        self.assertEqual(targets["targets"]["Q6_K"]["tensor_name"], "blk.0.ffn_down.weight")
        self.assertEqual(targets["qualification_scope"]["real_payloads_per_family"], 1)
        self.assertTrue(all(row["packed_sha256"] is None for row in targets["targets"].values()))

    def test_qualified_payload_reuse_partitions_40_into_two_plus_38(self):
        inventory = M.reconstruct_inventory()
        plan = M.qualification_reuse_plan(inventory, M.select_decoder_targets(inventory))
        self.assertEqual(plan["retained_tensor_names"], ["token_embd.weight", "blk.0.ffn_down.weight"])
        self.assertEqual(plan["retained_payload_count"], 2)
        self.assertEqual(plan["future_dense_prefix_new_payload_reads"], 38)
        self.assertEqual(plan["future_dense_prefix_logical_tensor_count"], 40)
        self.assertIn("REQUIRES_SEPARATE", plan["status"])

    def test_q4_q6_synthetic_a_b_exact_and_c_source_bound(self):
        value = M.synthetic_decoder_scaffold()
        self.assertEqual(value["checkpoint_access"], 0)
        for family in ("Q4_K", "Q6_K"):
            row = value["formats"][family]
            self.assertTrue(row["a_b_exact"])
            self.assertEqual(row["real_byte_status"], "UNQUALIFIED_REAL_GATE")
            self.assertEqual(len(row["decoder_c"]["sha256"]), 64)
        legacy = value["formats"]["Q6_K"]["legacy_research_decoder_audit"]
        self.assertTrue(legacy["matches_spec"])
        self.assertEqual(legacy["status"], "REMEDIATED_SYNTHETIC_EXACT_REAL_BYTE_UNQUALIFIED")
        self.assertEqual(legacy["pre_remediation_first_divergence"]["element"], 32)
        with self.assertRaisesRegex(ValueError, "block length"): M.decode_q4_k_spec(b"\0" * 143)
        with self.assertRaisesRegex(ValueError, "block length"): M.decode_q6_k_spec(b"\0" * 209)

    def test_legacy_q6_group_order_matches_two_independent_decoders(self):
        from scripts.research.ggml_kquants import dequantize_row_q6_k

        quantized = [((index * 17 + 5) & 63) - 32 for index in range(256)]
        scales = [index - 8 for index in range(16)]
        ql = bytearray(128)
        qh = bytearray(64)
        for half in range(2):
            for lane in range(32):
                values = [quantized[128 * half + 32 * group + lane] + 32 for group in range(4)]
                ql[64 * half + lane] = (values[0] & 15) | ((values[2] & 15) << 4)
                ql[64 * half + 32 + lane] = (values[1] & 15) | ((values[3] & 15) << 4)
                qh[32 * half + lane] = (values[0] >> 4) | ((values[1] >> 4) << 2) | ((values[2] >> 4) << 4) | ((values[3] >> 4) << 6)
        block = bytes(ql + qh + bytearray(value & 255 for value in scales) + struct.pack("<e", 0.5))
        legacy = M._lef32(dequantize_row_q6_k(block, 256))
        grouped = M._lef32(M.decode_q6_k_spec(block))
        indexed = M._lef32(M.decode_q6_k_independent(block))
        self.assertEqual(legacy, grouped)
        self.assertEqual(legacy, indexed)

    def test_residency_floor_is_preobserved_conservative_and_immutable(self):
        value = M.residency_contract(M.reconstruct_inventory())
        method = value["admission_floor_method"]
        self.assertTrue(method["frozen_before_candidate_telemetry"])
        self.assertEqual(method["post_observation_lowering"], "FORBIDDEN")
        modeled = (method["packed_inventory_bytes"] + method["decoded_cpu_all_upper_bound_bytes"]
                   + method["decoded_equivalent_mlx_all_upper_bound_bytes"]
                   + method["fixed_runtime_reserve_bytes"])
        self.assertGreater(method["required_available_memory_bytes"], modeled)
        self.assertEqual(method["required_available_memory_gib"], 27)
        self.assertTrue(all(phase["bytes_upper"] is not None for phase in value["liveness_phases"]))
        self.assertEqual(method["required_available_memory_bytes"] % (1024 ** 3), 0)

    def test_boundary_is_honest_and_ledger_unchanged_in_preparation(self):
        value = M.package()["boundary"]
        self.assertIn("M1-F(-1)", value["honest_name"])
        self.assertTrue(value["not_fixture_capture"])
        self.assertEqual(value["tensor_count"], 40)
        self.assertFalse(value["real_payload_ledger"]["changed_in_preparation"])
        self.assertEqual(value["real_payload_ledger"]["current"], 57)
        self.assertEqual(value["real_payload_ledger"]["future_after_38_new_payload_dense_prefix_with_reviewed_reuse"], 97)
        self.assertEqual(value["execution_access_after_separately_qualified_payload_reuse"]["new_tensor_payloads"], 38)
        self.assertIn("complete dense layer 2", value["computation"])

    def test_banked_artifacts_regenerate_exactly(self):
        generated = M.package()
        mapping = {
            "f017-m1f-minus1-prompt-token-package-v1.json": "prompt",
            "f017-m1f-minus1-exact-inventory-v1.json": "inventory",
            "f017-m1f-minus1-decoder-scaffold-v1.json": "decoder",
            "f017-m1f-minus1-residency-admission-v1.json": "residency",
            "f017-m1f-minus1-decoder-targets-v1.json": "targets",
            "f017-m1f-minus1-boundary-v1.json": "boundary",
            "f017-m1f-minus1-qualification-reuse-plan-v1.json": "reuse",
        }
        for name, key in mapping.items():
            with self.subTest(name=name):
                banked = json.loads((ROOT / "docs/architecture/reviews/evidence" / name).read_text())
                self.assertEqual(banked, generated[key])


if __name__ == "__main__":
    unittest.main()

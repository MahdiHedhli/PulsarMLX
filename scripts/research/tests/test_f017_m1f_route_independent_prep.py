from __future__ import annotations

import copy
import importlib.util
import json
import math
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("m1f_prep", ROOT / "scripts/research/f017_m1f_route_independent_prep.py")
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


def dispatch_records(selected: int = 8):
    conceptual = [{"stage": stage, "multiplicity": selected if stage.startswith("routed_expert_") else 1}
                  for stage in M.DISPATCH_STAGES]
    native = [
        {"event": "attention_pipeline", "backend": "MLX_NATIVE", "dispatches_per_unit": 6, "scaling": "constant_per_repeat"},
        {"event": "router_projection", "backend": "MLX_NATIVE", "dispatches_per_unit": 1, "scaling": "constant_per_repeat"},
        {"event": "routed_gate_up_fused", "backend": "MLX_NATIVE", "dispatches_per_unit": 1, "scaling": "constant_per_repeat"},
        {"event": "routed_down_fused", "backend": "MLX_NATIVE", "dispatches_per_unit": 1, "scaling": "constant_per_repeat"},
        {"event": "shared_triplet", "backend": "MLX_NATIVE", "dispatches_per_unit": 3, "scaling": "constant_per_repeat"},
        {"event": "non_mlx", "backend": "CPU_NON_MODEL", "dispatches_per_unit": 0, "scaling": "constant_per_repeat"},
    ]
    return conceptual, native


class RouteIndependentM1FPrepTests(unittest.TestCase):
    def test_expert_slices_cover_boundaries_catalog_and_no_overlap(self):
        metadata = M.load_catalog_metadata(ROOT)
        self.assertEqual(metadata["expert_count"], 256)
        for expert in (0, 1, 15, 166, 255):
            triplet = M.derive_expert_triplet(metadata, expert)
            self.assertEqual(set(triplet), set(M.ROLES))
            self.assertTrue(all(item["quant_block_aligned"] for item in triplet.values()))
        M.validate_all_expert_slices(metadata)

    def test_expert_slice_rejects_indexing_layout_alignment_truncation_and_bounds(self):
        base = M.load_catalog_metadata(ROOT)
        for key, value, error in (
            ("indexing", "one_based", "zero-based"),
            ("layout", "expert_major_then_projection_major", "projection-major"),
        ):
            mutated = copy.deepcopy(base); mutated[key] = value
            with self.assertRaisesRegex(ValueError, error): M.validate_aggregate_metadata(mutated)
        bad = copy.deepcopy(base); bad["projections"]["gate"]["stride"] += 1
        with self.assertRaisesRegex(ValueError, "stride"): M.validate_aggregate_metadata(bad)
        bad = copy.deepcopy(base); bad["projections"]["up"]["packed_total_length"] -= 1
        with self.assertRaisesRegex(ValueError, "truncated"): M.validate_aggregate_metadata(bad)
        for expert in (-1, 256, 2**63):
            with self.assertRaisesRegex(ValueError, "expert id"): M.derive_expert_triplet(base, expert)

    def test_dispatch_formula_is_mechanical_not_frozen_constant(self):
        recorder = M.DispatchRecorder()
        conceptual, native = dispatch_records(8)
        for record in conceptual: recorder.record_conceptual(**record)
        for record in native: recorder.record_native(**record)
        eight = recorder.reconcile(8)
        conceptual3, native3 = dispatch_records(3)
        three = M.reconcile_dispatches(conceptual3, native3, 3)
        self.assertEqual(eight["expected_native_dispatches"], eight["constant_native_dispatches"])
        self.assertEqual(three["expected_native_dispatches"], three["constant_native_dispatches"])
        self.assertNotEqual(eight["conceptual_operations"], three["conceptual_operations"])
        bad_c, bad_n = dispatch_records(); bad_c[3]["multiplicity"] = 7
        with self.assertRaisesRegex(ValueError, "multiplicity"): M.reconcile_dispatches(bad_c, bad_n, 8)
        bad_c, bad_n = dispatch_records(); bad_n[0]["fallback"] = True
        with self.assertRaisesRegex(ValueError, "forbidden"): M.reconcile_dispatches(bad_c, bad_n, 8)

    def test_decoder_harness_requires_independence_and_exact_f32_bytes(self):
        packed = bytes(range(8))
        expected = struct.pack("<2f", 1.25, -0.0)
        a = M.DecoderImplementation("scalar-a", "a" * 64, "independent-a", lambda _: expected)
        b = M.DecoderImplementation("scalar-b", "b" * 64, "independent-b", lambda _: bytes(expected))
        result = M.qualify_decoder_exact(packed, (a, b), 2)
        self.assertEqual(result["implementation_count"], 2)
        self.assertEqual(result["signed_zero_count"], 1)
        same = M.DecoderImplementation("wrapper", "a" * 64, "independent-a", lambda _: expected)
        with self.assertRaisesRegex(ValueError, "not independent"): M.qualify_decoder_exact(packed, (a, same), 2)
        wrong = M.DecoderImplementation("wrong", "c" * 64, "independent-c", lambda _: struct.pack("<2f", 1.0, 0.0))
        with self.assertRaisesRegex(ValueError, "byte mismatch"): M.qualify_decoder_exact(packed, (a, wrong), 2)
        with self.assertRaisesRegex(ValueError, "empty/truncated"): M.qualify_decoder_exact(b"", (a, b), 2)
        nonfinite = M.DecoderImplementation("nan", "d" * 64, "independent-d", lambda _: struct.pack("<2f", math.nan, 0.0))
        with self.assertRaisesRegex(ValueError, "non-finite"): M.qualify_decoder_exact(packed, (a, nonfinite), 2)

    def test_numerical_metrics_stress_and_nonfinite_rejection(self):
        for oracle, candidate in (
            ([1e20, -1e20, 1.0], [1e20, -1e20, 1.000001]),
            ([0.0, -0.0, 1e-44], [-0.0, 0.0, 2e-44]),
            ([1e-30, -1e-30], [1.1e-30, -0.9e-30]),
            ([3.29e38, -3.29e38], [3.28e38, -3.28e38]),
        ):
            metrics = M.tier_b_metrics(candidate, oracle)
            self.assertGreaterEqual(metrics["max_abs"], 0.0)
            self.assertTrue(math.isfinite(metrics["rmse"]))
        with self.assertRaisesRegex(ValueError, "non-finite"): M.tier_b_metrics([math.inf], [0.0])

    def test_repeat_lifecycle_requires_ten_equal_complete_repeats_and_teardown(self):
        stages = {"attention_residual": "a" * 64, "route_pairs": "b" * 64, "layer_output": "c" * 64}
        conceptual, native = dispatch_records(8)
        expected_dispatches = M.reconcile_dispatches(conceptual, native, 8)["expected_native_dispatches"]
        evidence = {
            "required_stage_hashes": list(stages),
            "repeats": [{"ordinal": i, "stage_hashes": dict(stages), "native_dispatches": expected_dispatches, "expected_native_dispatches": expected_dispatches,
                         "fallback": 0, "reference": 0, "scaffold": 0, "backend_errors": 0} for i in range(10)],
            "lifecycle": {"teardown_complete": True, "in_flight_work": 0, "stale_generations": 0},
        }
        M.validate_repeat_lifecycle(evidence)
        bad = copy.deepcopy(evidence)
        bad["repeats"][7]["stage_hashes"]["layer_output"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "nondeterminism"): M.validate_repeat_lifecycle(bad)
        bad = copy.deepcopy(evidence); bad["lifecycle"]["in_flight_work"] = 1
        with self.assertRaisesRegex(ValueError, "lifecycle"): M.validate_repeat_lifecycle(bad)

    def test_schemas_are_closed_and_q6k_target_is_unresolved(self):
        schema_names = (
            "f017-m1f-evidence-v1.schema.json", "f017-m1f-execution-config-v1.schema.json",
            "f017-generic-decoder-qualification-v1.schema.json",
        )
        for name in schema_names:
            document = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts" / name).read_text())
            self.assertFalse(document["additionalProperties"])
        q6k = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-q6-k-qualification-handoff-template-v1.json").read_text())
        self.assertEqual(q6k["status"], "PREPARED_NOT_AUTHORIZED")
        self.assertIsNone(q6k["target_tensor"])
        self.assertEqual(q6k["real_payload_reads"], 0)
        dispatch = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f-dispatch-reconciliation-v1.json").read_text())
        self.assertIsNone(dispatch["route_specific_total"])
        self.assertTrue(dispatch["route_specific_total_must_be_derived"])

    def test_readiness_manifest_has_no_route_or_real_access_claim(self):
        evidence = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-m1f-route-independent-preparation-v1.json").read_text())
        self.assertEqual(evidence["status"], "ROUTE_INDEPENDENT_M1F_SCAFFOLD_READY")
        self.assertEqual(evidence["scope"]["checkpoint_payload_reads"], 0)
        self.assertFalse(evidence["scope"]["route_selected"])
        self.assertFalse(evidence["scope"]["q6_k_target_selected"])
        for binding in evidence["source_trace"].values():
            self.assertEqual(M.sha256((ROOT / binding["path"]).read_bytes()), binding["sha256"])
        self.assertEqual(M.sha256((ROOT / evidence["implementation"]["path"]).read_bytes()), evidence["implementation"]["sha256"])
        dispatch = evidence["implementation"]["production_dispatch_instrumentation"]
        self.assertEqual(M.sha256((ROOT / dispatch["path"]).read_bytes()), dispatch["sha256"])

    def test_typed_config_rejects_loose_override(self):
        config = {
            "schema": "pulsarmlx.f017.m1f-execution-config", "schema_version": "1.0.0", "status": "PREPARED_NOT_AUTHORIZED",
            "identities": {}, "checkpoint_bindings": {}, "contracts": {}, "input_fixture": {}, "route_artifact": {},
            "selected_experts": list(range(8)),
            "routing_pairs": [
                {"expert_id": expert_id, "routing_weight": 0.1 + expert_id * 0.01}
                for expert_id in range(8)
            ],
            "tensor_allowlist": [], "decoder_contracts": [], "oracle": {},
            "numerical_contract": {}, "execution": {"repeat_count": 10, "auto_retry": False}, "attempt_state": {},
            "evidence_destination": {},
        }
        M.validate_execution_config_shape(config)
        config["expert_override"] = [166]
        with self.assertRaisesRegex(ValueError, "loose overrides"): M.validate_execution_config_shape(config)

    def test_typed_config_rejects_non_atomic_or_non_top8_route(self):
        config = {
            "schema": "pulsarmlx.f017.m1f-execution-config", "schema_version": "1.0.0", "status": "PREPARED_NOT_AUTHORIZED",
            "identities": {}, "checkpoint_bindings": {}, "contracts": {}, "input_fixture": {}, "route_artifact": {},
            "selected_experts": list(range(8)),
            "routing_pairs": [{"expert_id": i, "routing_weight": 0.1 + i * 0.01} for i in range(8)],
            "tensor_allowlist": [], "decoder_contracts": [], "oracle": {}, "numerical_contract": {},
            "execution": {"repeat_count": 10, "auto_retry": False}, "attempt_state": {}, "evidence_destination": {},
        }
        M.validate_execution_config_shape(config)
        duplicate = copy.deepcopy(config)
        duplicate["routing_pairs"][-1]["expert_id"] = 0
        with self.assertRaisesRegex(ValueError, "disagree"):
            M.validate_execution_config_shape(duplicate)
        short = copy.deepcopy(config)
        short["selected_experts"] = list(range(7))
        with self.assertRaisesRegex(ValueError, "eight"):
            M.validate_execution_config_shape(short)


if __name__ == "__main__":
    unittest.main()

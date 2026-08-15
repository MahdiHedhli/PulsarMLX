import copy
import inspect
import math
import unittest

import numpy as np

from scripts.research import f017_dense_prefix_preparation as dense


class SyntheticRealShapedOracleTests(unittest.TestCase):
    def test_real_shapes_and_position_zero_path(self) -> None:
        result = dense.run_synthetic_dense_prefix(dtype=np.float32)
        self.assertEqual(result["position"], 0)
        self.assertEqual(result["dsa"], "range_fill([0])")
        self.assertEqual(result["layer3_entry"].shape, (dense.HIDDEN,))
        self.assertEqual(len(result["layers"]), 3)
        expected_shapes = {
            "q_a": [dense.Q_LORA], "q_b": [dense.Q_OUT],
            "kv_a_mqa": [dense.KV_LORA + dense.KV_ROPE],
            "k_b": [dense.K_OUT], "v_b": [dense.V_OUT],
            "ffn_gate": [dense.FFN], "ffn_up": [dense.FFN],
            "ffn_down": [dense.HIDDEN], "output": [dense.HIDDEN],
        }
        for layer in result["layers"]:
            for name, shape in expected_shapes.items():
                self.assertEqual(layer["stage_shapes"][name], shape)

    def test_ten_repeat_numerical_qualification(self) -> None:
        result = dense.synthetic_qualification()
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["repeat_count"], 10)
        self.assertEqual(len(set(result["repeat_hashes"])), 1)
        self.assertNotIn("structured_project(", inspect.getsource(dense.oracle_structured_project).split("def oracle_structured_project", 1)[1])
        self.assertTrue(result["deterministic"])
        dense.qualify_numerical(result["metrics"])

    def test_numerical_contract_fails_closed(self) -> None:
        for key, value in (
            ("max_abs_error", dense.NUMERICAL_THRESHOLDS["max_abs_error"] * 2),
            ("rmse", dense.NUMERICAL_THRESHOLDS["rmse"] * 2),
        ):
            metrics = {"max_abs_error": 0.0, "rmse": 0.0, "cosine": 1.0}
            metrics[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                dense.qualify_numerical(metrics)
        with self.assertRaises(ValueError):
            dense.qualify_numerical({"max_abs_error": 0.0, "rmse": 0.0, "cosine": 0.0})

    def test_wrong_token_or_repeat_count_rejected(self) -> None:
        with self.assertRaises(ValueError):
            dense.synthetic_embedding(1, dtype=np.float32)
        with self.assertRaises(ValueError):
            dense.synthetic_qualification(9)


class DensePrefixDispatchTests(unittest.TestCase):
    def test_exact_reconciliation_formula(self) -> None:
        events = dense.expected_dispatch_events()
        result = dense.reconcile_dispatch_events(events)
        self.assertEqual(result["synthetic_observed_native_per_repeat"], 28)
        self.assertEqual(result["synthetic_observed_native_total"], 280)
        self.assertFalse(result["future_real_count_frozen"])
        self.assertTrue(all(event.backend != "MLX_NATIVE" for event in events))
        self.assertEqual(result["fallback"], 0)

    def test_missing_extra_or_reordered_event_fails(self) -> None:
        events = list(dense.expected_dispatch_events())
        for mutated in (events[:-1], events + [events[-1]], list(reversed(events))):
            with self.subTest(size=len(mutated)), self.assertRaises(ValueError):
                dense.reconcile_dispatch_events(mutated)


class DensePrefixSchemaTests(unittest.TestCase):
    def test_prepared_config_is_non_consuming(self) -> None:
        value = dense.dense_prefix_config_template()
        self.assertEqual(value["status"], "PREPARED_NOT_AUTHORIZED")
        self.assertFalse(value["attempt"]["authorized"])
        self.assertFalse(value["attempt"]["consumed"])
        dense.validate_dense_prefix_config(value)

    def test_config_rejects_override_mutation_and_incomplete_authorization(self) -> None:
        value = dense.dense_prefix_config_template()
        value["tensor_override"] = "unexpected"
        with self.assertRaises(ValueError):
            dense.validate_dense_prefix_config(value)
        value = dense.dense_prefix_config_template()
        value["status"] = "AUTHORIZED_NOT_EXECUTED"
        value["attempt"]["authorized"] = True
        with self.assertRaisesRegex(ValueError, "identity incomplete"):
            dense.validate_dense_prefix_config(value)

    def test_authorized_config_requires_every_execution_binding(self) -> None:
        value = dense.dense_prefix_config_template()
        value.update({
            "status": "AUTHORIZED_NOT_EXECUTED",
            "numerical_contract": "1" * 64,
            "dispatch_contract": "2" * 64,
            "hidden_retention": "3" * 64,
            "decoder_contracts": {family: str(index) * 64 for index, family in enumerate(("F32", "Q8_0", "Q5_K", "Q6_K", "Q4_K"), 4)},
        })
        value["identity"] = {
            "tooling_sha": "a" * 40,
            "tooling_tree": "b" * 40,
            "authorization_head": "c" * 40,
            "environment_sha256": "d" * 64,
        }
        value["tensor_inventory"]["sha256"] = "e" * 64
        value["access_budget"] = {
            "shard_opens": 1,
            "positional_reads": 40,
            "payloads": 40,
            "compressed_bytes": 1_431_263_232,
            "decoded_bytes": 8_504_653_824,
        }
        value["attempt"].update(number=1, authorized=True)
        value["oracle_package"] = {
            "package_sha256": "f" * 64,
            "source_surface_sha256": "0" * 64,
            "decoded_tensor_set_sha256": "9" * 64,
            "completed_before_candidate": True,
            "rust_or_mlx": False,
            "candidate_metrics": False,
        }
        value["evidence_destination"]["symbolic_path"] = "docs/architecture/reviews/evidence/f017-future-dense-prefix-result.json"
        dense.validate_dense_prefix_config(value)

        mutations = (
            lambda v: v["identity"].update(environment_sha256=None),
            lambda v: v["access_budget"].update(positional_reads=39),
            lambda v: v["decoder_contracts"].pop("Q6_K"),
            lambda v: v.update(numerical_contract=None),
            lambda v: v["attempt"].update(number=None),
            lambda v: v["evidence_destination"].update(symbolic_path=None),
        )
        for mutation in mutations:
            candidate = copy.deepcopy(value)
            mutation(candidate)
            with self.assertRaises(ValueError):
                dense.validate_dense_prefix_config(candidate)

    def test_hidden_manifest_privacy_and_shape(self) -> None:
        manifest = {
            "schema": "pulsarmlx.f017.layer3-entry-hidden-retention",
            "schema_version": "1.0.0",
            "status": "SYNTHETIC",
            "source": {"evidence_sha256": "a" * 64},
            "hidden": {"dtype": "little_endian_f32", "shape": [6144], "element_count": 6144, "sha256": "b" * 64},
            "state": {"position": 0, "dsa": "range_fill([0])"},
            "immutability": {"read_only": True, "absolute_path_public": False},
            "checkpoint_access": 0,
        }
        dense.validate_hidden_manifest(manifest)
        for mutation in (
            lambda v: v["hidden"].update(shape=[1]),
            lambda v: v["immutability"].update(read_only=False),
            lambda v: v["immutability"].update(absolute_path_public=True),
        ):
            value = copy.deepcopy(manifest)
            mutation(value)
            with self.assertRaises(ValueError):
                dense.validate_hidden_manifest(value)

    def test_route_binding_requires_h2_atomic_pairs_and_never_authorizes_m1f(self) -> None:
        value = {
            "schema": "pulsarmlx.f017.m1f-representative-route-binding",
            "schema_version": "1.0.0",
            "status": "ACCEPTED_REPRESENTATIVE_ROUTE",
            "dense_prefix_evidence_sha256": "a" * 64,
            "layer3_entry_sha256": "b" * 64,
            "m1f0_route_artifact_sha256": "c" * 64,
            "routing_v3_sha256": dense.V3_SHA256,
            "membership_h2_pass": True,
            "atomic_pairs_sha256": "d" * 64,
            "analytical_retention_complete": True,
            "m1_f_authorized": False,
        }
        dense.validate_representative_route_binding(value)
        for key in ("membership_h2_pass", "analytical_retention_complete"):
            bad = copy.deepcopy(value)
            bad[key] = False
            with self.assertRaises(ValueError):
                dense.validate_representative_route_binding(bad)
        bad = copy.deepcopy(value)
        bad["m1_f_authorized"] = True
        with self.assertRaises(ValueError):
            dense.validate_representative_route_binding(bad)

    def test_representative_handoff_keeps_phases_separate(self) -> None:
        handoff = dense.representative_route_handoff()
        self.assertEqual(handoff["checkpoint_access"], 0)
        self.assertFalse(handoff["phase_separation"]["dense_prefix_and_route_share_authorization"])
        self.assertFalse(handoff["phase_separation"]["route_and_m1_f_share_authorization"])
        self.assertTrue(handoff["input_binding"]["accepted_hidden_retention_manifest_required"])
        self.assertEqual(handoff["input_binding"]["alternate_prompt_or_hidden_substitution"], "FAIL_CLOSED")
        self.assertFalse(handoff["phase_separation"]["m1_f_authorized"])


if __name__ == "__main__":
    unittest.main()

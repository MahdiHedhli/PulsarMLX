from __future__ import annotations

import importlib.util
import json
import copy
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEDGER = load("f017_real_payload_ledger", "scripts/research/validate_f017_real_payload_ledger.py")
INPUT = load("f017_m1f0_input", "scripts/research/generate_f017_m1f0_input.py")
LADDER_INPUT = load("f017_m1f0_ladder_input", "scripts/research/generate_f017_m1f0_ladder_input.py")
LADDER = load("f017_m1f0_ladder", "scripts/research/prepare_f017_m1f0_input_ladder.py")
ESTIMATOR = load("f017_m1f0_estimator", "scripts/research/estimate_f017_m1f0_qualification_rate.py")
RETENTION = load("f017_retention", "scripts/research/validate_f017_analytical_retention.py")
SLICES = load("f017_expert_slices", "scripts/research/validate_f017_expert_slices.py")
BINDING = load("f017_estimator_binding", "scripts/research/validate_f017_estimator_ladder_binding.py")


class M1F0NewInputSelectionTests(unittest.TestCase):
    def test_complete_real_payload_ledger_reconciles_to_45(self):
        document = LEDGER.build_ledger(ROOT)
        self.assertEqual(document["cumulative_tensor_payloads"], 45)
        self.assertEqual(document["prior_m1f0_scoped_total"], 37)
        self.assertEqual(document["prior_scope_omissions_total"], 8)
        self.assertEqual(sum(event["tensor_payload_count"] for event in document["events"]), 45)
        self.assertEqual(document["checkpoint_identity_only"]["tensor_payload_count"], 0)
        self.assertEqual(document["checkpoint_identity_only"]["storage_read_count"], 28_444)

    def test_default_fixture_is_unchanged_and_new_seeds_are_distinct(self):
        old = INPUT.canonical_json(INPUT.document())
        self.assertEqual(
            INPUT.sha256(old),
            "33be5f7ed93a29621b39034246a8bf088111fa4138b0966179aad94a138e63c4",
        )
        first = LADDER_INPUT.document(seed=17_017_007)
        again = LADDER_INPUT.document(seed=17_017_007)
        second = LADDER_INPUT.document(seed=17_017_008)
        self.assertEqual(first, again)
        self.assertNotEqual(first["state"]["hidden"]["sha256"], second["state"]["hidden"]["sha256"])
        self.assertEqual(first["generator"]["seed"], 17_017_007)

    def test_ladder_is_ordered_complete_and_non_optimizing(self):
        fixtures = [LADDER_INPUT.document(seed=seed) for seed in LADDER.SEEDS]
        document = LADDER.build_ladder(ROOT, fixtures)
        self.assertEqual([entry["seed"] for entry in document["fixtures"]], list(LADDER.SEEDS))
        self.assertEqual(document["selection_rule"], "first_qualifying_fixture_in_ordinal_order")
        self.assertEqual(document["execution_stopping_rule"], "evaluate_and_bank_all_precommitted_fixtures")
        outcomes = [False, False, True, True, False, False, False, False]
        self.assertEqual(LADDER.select_fixture(outcomes), 2)
        with self.assertRaisesRegex(ValueError, "complete ladder"):
            LADDER.select_fixture(outcomes[:-1])

    def test_extensible_retention_rejects_omitted_declared_value(self):
        config = {
            "required_analytical_retention": [
                {"name": "router_scores", "value_path": "/analytics/scores", "hash_path": "/analytics/scores_sha256"},
                {"name": "future_margin", "value_path": "/analytics/margin", "hash_path": "/analytics/margin_sha256"},
            ]
        }
        evidence = {"analytics": {"scores": [1.0, 0.5], "scores_sha256": "a" * 64}}
        with self.assertRaisesRegex(ValueError, "future_margin"):
            RETENTION.validate_declared_retention(config, evidence)
        evidence["analytics"].update({"margin": 0.5, "margin_sha256": "b" * 64})
        RETENTION.validate_declared_retention(config, evidence)

    def test_extensible_retention_rejects_arbitrary_future_fields(self):
        for field in (
            "rank_boundary_pairwise_bound",
            "top1_top2_margin",
            "runner_up_token_margin",
        ):
            config = {"required_analytical_retention": [{
                "name": field,
                "value_path": f"/analytics/{field}",
                "hash_path": f"/analytics/{field}_sha256",
            }]}
            with self.assertRaisesRegex(ValueError, field):
                RETENTION.validate_declared_retention(config, {"analytics": {}})
            evidence = {"analytics": {field: 1.0, f"{field}_sha256": "c" * 64}}
            RETENTION.validate_declared_retention(config, evidence)

    def test_estimator_ladder_binding_rejects_stale_or_mixed_inputs(self):
        document = json.loads((ROOT / BINDING.BINDING).read_text())
        BINDING.validate(ROOT, document)
        for binding_name in ("fixture_generator", "ladder_artifact", "estimator_implementation"):
            mutated = copy.deepcopy(document)
            mutated["bindings"][binding_name]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "stale estimator binding"):
                BINDING.validate(ROOT, mutated)
        mixed = copy.deepcopy(document)
        mixed["environment"]["seeds"][-1] += 1
        with self.assertRaisesRegex(ValueError, "mixed ladder version"):
            BINDING.validate(ROOT, mixed)
        wrong_environment = copy.deepcopy(document)
        wrong_environment["environment"]["numpy"] = "2.4.4"
        with self.assertRaisesRegex(ValueError, "mixed ladder environment"):
            BINDING.validate(ROOT, wrong_environment)

    def test_estimator_is_deterministic_and_preserves_frozen_threshold(self):
        contract = ESTIMATOR.load_contract(ROOT)
        self.assertEqual(contract["stability_contract_sha256"], "da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7")
        self.assertEqual(contract["minimum_safety_factor"], 4.0)
        left = ESTIMATOR.simulate(ROOT, sample_count=2_048, seed=9191)
        right = ESTIMATOR.simulate(ROOT, sample_count=2_048, seed=9191)
        self.assertEqual(left, right)
        self.assertEqual(left["checkpoint_access"], 0)

    def test_official_estimator_blocks_an_underpowered_ladder(self):
        result = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-m1-f0-fixture-qualification-estimate-v1.json").read_text()
        )
        self.assertFalse(result["adequate"])
        self.assertEqual(result["qualifying_samples"], 0)
        self.assertLess(result["p_at_least_one_using_wilson_upper"], 0.001)

    def test_expert_slice_formula_covers_boundaries_and_rejects_overflow(self):
        metadata = SLICES.aggregate_metadata(ROOT)
        for expert in (0, 1, 15, 166, 255):
            triplet = SLICES.derive_triplet(metadata, expert)
            self.assertEqual(set(triplet), {"gate", "up", "down"})
            self.assertTrue(all(item["end"] > item["start"] for item in triplet.values()))
            self.assertTrue(all(item["quant_block_aligned"] for item in triplet.values()))
        expert166 = SLICES.derive_triplet(metadata, 166)
        proof = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-expert-166-catalog-slice-crosscheck-v2.json").read_text())
        for role in ("gate", "up", "down"):
            self.assertEqual(expert166[role]["start"], proof["projections"][role]["catalog_inventory_start"])
            self.assertEqual(expert166[role]["packed_length"], proof["projections"][role]["catalog_inventory_length"])
        with self.assertRaisesRegex(ValueError, "expert id"):
            SLICES.derive_triplet(metadata, -1)
        with self.assertRaisesRegex(ValueError, "expert id"):
            SLICES.derive_triplet(metadata, 256)


if __name__ == "__main__":
    unittest.main()

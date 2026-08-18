from __future__ import annotations

import copy
import unittest

from scripts.research import validate_f017_complete_layer_aggregate_acceptance_v2 as validator


class CompleteLayerV2ValidatorTests(unittest.TestCase):
    def test_public_package_validates(self):
        validator.validate_contract()
        validator.validate_history()
        validator.validate_evidence()

    def test_intermediate_threshold_family_mutation_fails(self):
        contract = validator.load_json(validator.CONTRACT)
        mutated = copy.deepcopy(contract)
        mutated["r10_final_output_authority"].update({
            "family": "intermediate",
            "max_absolute_error": 0.015625,
            "rmse": 0.0078125,
            "cosine_similarity_minimum": 0.9999,
        })
        with self.assertRaises(validator.CompleteLayerFreezeValidationError):
            validator.validate_contract_dict(mutated)

    def test_residual_double_count_mutation_fails(self):
        contract = validator.load_json(validator.CONTRACT)
        mutated = copy.deepcopy(contract)
        mutated["surface"]["residual"] = "R is added twice"
        with self.assertRaises(validator.CompleteLayerFreezeValidationError):
            validator.validate_contract_dict(mutated)

    def test_routed_interval_mutation_fails(self):
        contract = validator.load_json(validator.CONTRACT)
        mutated = copy.deepcopy(contract)
        mutated["routed_uncertainty_reuse"]["v1_sound_intersection_sha256"] = "0" * 64
        with self.assertRaises(validator.CompleteLayerFreezeValidationError):
            validator.validate_contract_dict(mutated)

    def test_inventory_duplicate_and_byte_mutations_fail(self):
        contract = validator.load_json(validator.CONTRACT)
        mutated = copy.deepcopy(contract)
        mutated["future_shared_payload_inventory"]["payloads"][1]["key"] = mutated["future_shared_payload_inventory"]["payloads"][0]["key"]
        with self.assertRaises(validator.CompleteLayerFreezeValidationError):
            validator.validate_contract_dict(mutated)
        mutated = copy.deepcopy(contract)
        mutated["future_shared_payload_inventory"]["packed_bytes"] += 1
        with self.assertRaises(validator.CompleteLayerFreezeValidationError):
            validator.validate_contract_dict(mutated)


if __name__ == "__main__":
    unittest.main()

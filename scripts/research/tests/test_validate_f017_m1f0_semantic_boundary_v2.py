from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_m1f0_semantic_boundary_v2 as validator


class RepresentativeM1F0SemanticBoundaryV2Tests(unittest.TestCase):
    def test_public_package_validates(self):
        validator.validate_all()

    def test_attention_bypass_mutation_fails(self):
        graph = validator.load_json(validator.GRAPH)
        mutated = copy.deepcopy(graph)
        mutated["boundaries"]["F_norm"]["input"] = "S0"
        with self.assertRaises(validator.SemanticBoundaryValidationError):
            validator.validate_graph_dict(mutated)

    def test_e942_production_role_mutation_fails(self):
        correction = validator.load_json(validator.CORRECTION)
        mutated = copy.deepcopy(correction)
        mutated["corrections"]["e942_complete_layer"]["corrected_role"] = "PRODUCTION_COMPLETE_LAYER3_OUTPUT"
        with self.assertRaises(validator.SemanticBoundaryValidationError):
            validator.validate_correction_dict(mutated)

    def test_inventory_duplicate_and_budget_mutations_fail(self):
        boundary = validator.load_json(validator.BOUNDARY)
        mutated = copy.deepcopy(boundary)
        mutated["future_real_event_shape"]["attention_payloads"][1]["key"] = mutated["future_real_event_shape"]["attention_payloads"][0]["key"]
        with self.assertRaises(validator.SemanticBoundaryValidationError):
            validator.validate_boundary_dict(mutated)
        mutated = copy.deepcopy(boundary)
        mutated["future_real_event_shape"]["packed_bytes"] += 1
        with self.assertRaises(validator.SemanticBoundaryValidationError):
            validator.validate_boundary_dict(mutated)

    def test_direct_route_transfer_mutation_fails(self):
        boundary = validator.load_json(validator.BOUNDARY)
        mutated = copy.deepcopy(boundary)
        mutated["future_stability_work"]["direct_dprefix_v31_transfer"] = "ALLOWED"
        with self.assertRaises(validator.SemanticBoundaryValidationError):
            validator.validate_boundary_dict(mutated)

    def test_execution_authority_mutation_fails(self):
        boundary = validator.load_json(validator.BOUNDARY)
        mutated = copy.deepcopy(boundary)
        mutated["authorization"]["real_event_authorized"] = True
        with self.assertRaises(validator.SemanticBoundaryValidationError):
            validator.validate_boundary_dict(mutated)

    def test_duplicate_json_key_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"one","schema":"two"}')
            with self.assertRaises(validator.SemanticBoundaryValidationError):
                validator.load_json(path)


if __name__ == "__main__":
    unittest.main()

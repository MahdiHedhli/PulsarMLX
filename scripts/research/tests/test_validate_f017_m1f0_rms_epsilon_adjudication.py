from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_m1f0_rms_epsilon_adjudication as validator


class RepresentativeM1F0RmsEpsilonAdjudicationTests(unittest.TestCase):
    def test_public_package_validates(self):
        validator.validate_all()

    def test_graph_epsilon_regression_fails(self):
        graph = validator.load_json(validator.GRAPH_V2)
        mutated = copy.deepcopy(graph)
        mutated["rmsnorm_epsilon"]["source_decimal"] = "1e-6"
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_graph_dict(mutated)

    def test_graph_internal_attention_epsilon_regression_fails(self):
        graph = validator.load_json(validator.GRAPH_V2)
        mutated = copy.deepcopy(graph)
        mutated["boundaries"]["A"]["formula"] = "q_a_norm and kv_a_norm use epsilon=1e-6"
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_graph_dict(mutated)

    def test_site_specific_override_fails(self):
        graph = validator.load_json(validator.GRAPH_V2)
        mutated = copy.deepcopy(graph)
        mutated["rmsnorm_epsilon"]["site_specific_override"] = True
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_graph_dict(mutated)

    def test_boundary_epsilon_replacement_regression_fails(self):
        boundary = validator.load_json(validator.BOUNDARY_V3)
        mutated = copy.deepcopy(boundary)
        mutated["effective_contract_construction"]["replace_only"][0]["value"] = "epsilon=1e-6"
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_boundary_dict(mutated)

    def test_boundary_execution_authority_fails(self):
        boundary = validator.load_json(validator.BOUNDARY_V3)
        mutated = copy.deepcopy(boundary)
        mutated["authorization"]["real_event_authorized"] = True
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_boundary_dict(mutated)

    def test_adjudication_choice_regression_fails(self):
        evidence = validator.load_json(validator.ADJUDICATION)
        mutated = copy.deepcopy(evidence)
        mutated["question"]["option_a_1e_minus_6"] = True
        mutated["question"]["option_b_f32_1e_minus_5"] = False
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_adjudication_dict(mutated)

    def test_synthetic_1e_minus_6_cannot_be_promoted(self):
        evidence = validator.load_json(validator.ADJUDICATION)
        mutated = copy.deepcopy(evidence)
        target = next(item for item in mutated["evidence_inventory"] if item["path"] == "scripts/research/f017_dense_prefix_preparation.py")
        target["kind"] = "executable_same_surface_oracle"
        with self.assertRaises(validator.EpsilonAdjudicationValidationError):
            validator.validate_adjudication_dict(mutated)

    def test_binary32_bit_identity(self):
        validator.validate_executable_authority()

    def test_duplicate_json_key_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"epsilon":"1e-5","epsilon":"1e-6"}', encoding="utf-8")
            with self.assertRaises(validator.EpsilonAdjudicationValidationError):
                validator.load_json(path)


if __name__ == "__main__":
    unittest.main()

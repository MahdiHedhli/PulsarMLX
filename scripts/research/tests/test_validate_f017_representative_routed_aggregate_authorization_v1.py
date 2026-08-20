from __future__ import annotations

import copy
import unittest

from scripts.research.validate_f017_representative_routed_aggregate_authorization_v1 import AUTH_PATH, ValidationError, load, validate


class AuthorizationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = load(AUTH_PATH)

    def rejects(self, mutation) -> None:
        doc = copy.deepcopy(self.base)
        mutation(doc)
        with self.assertRaises(ValidationError):
            validate(doc, repo=False)

    def test_repository(self) -> None:
        validate(self.base, repo=True)

    def test_load_bearing_mutations(self) -> None:
        mutations = [
            lambda x: x.__setitem__("preparation_head", "0" * 40),
            lambda x: x["expert_output_reuse_authorization"].__setitem__("sha256", "0" * 64),
            lambda x: x["expert_output_reuse_review"].__setitem__("sha256", "0" * 64),
            lambda x: x["expert_execution_evidence"].__setitem__("sha256", "0" * 64),
            lambda x: x["private_output_package"].__setitem__("manifest_sha256", "0" * 64),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("expert_id", 1),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("routing_weight", 0.0),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("output_sha256", "0" * 64),
            lambda x: x["atomic_id_weight_output_triples"].__setitem__(slice(3, 5), [x["atomic_id_weight_output_triples"][4], x["atomic_id_weight_output_triples"][3]]),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("output_sha256", "6479a8352a355d5f979172bc19038d44b4df992925fab427d2caeaf24445efdc"),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("dtype", "native-f32"),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("shape", [1, 6144]),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("byte_length", 1),
            lambda x: x["preflight"].__setitem__("same_validated_descriptor_consumed", False),
            lambda x: x["semantic_adjudication"].__setitem__("sha256", "0" * 64),
            lambda x: x["arithmetic_contract"].__setitem__("sha256", "0" * 64),
            lambda x: x["executor"].__setitem__("sha256", "0" * 64),
            lambda x: x["executor"].__setitem__("blas", True),
            lambda x: x["executor"].__setitem__("parallel_reduction", True),
            lambda x: x["executor"].__setitem__("gpu", True),
            lambda x: x["synthetic_rehearsal"].__setitem__("sha256", "0" * 64),
            lambda x: x["future_output"].__setitem__("dtype", "little-endian-f32"),
            lambda x: x["future_output"].__setitem__("serialization", "native"),
            lambda x: x["accounting"].__setitem__("starting_ledger", 176),
            lambda x: x["accounting"].__setitem__("preparation_checkpoint_reads", 1),
            lambda x: x["accounting"].__setitem__("preparation_shard_opens", 1),
            lambda x: x["accounting"].__setitem__("preparation_expert_executions", 1),
            lambda x: x["accounting"].__setitem__("future_aggregate_execution_count", 2),
            lambda x: x["prohibitions"].__setitem__("shared_expert", False),
            lambda x: x.__setitem__("stop_boundary", "AFTER_FFN"),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.rejects(mutation)


if __name__ == "__main__":
    unittest.main()

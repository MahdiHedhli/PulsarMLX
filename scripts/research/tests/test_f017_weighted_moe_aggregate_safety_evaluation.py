import copy
import unittest

from scripts.research import evaluate_f017_weighted_moe_aggregate_safety as evaluator
from scripts.research import validate_f017_weighted_moe_aggregate_safety_evaluation as validator


class WeightedMoeAggregateSafetyEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = evaluator.load_json(validator.EVIDENCE)

    def test_committed_public_evidence(self):
        validator.validate_document(self.document)

    def test_cosine_failure_is_load_bearing(self):
        self.assertTrue(self.document["budgets"]["maximum_absolute"]["pass"])
        self.assertTrue(self.document["budgets"]["rmse"]["pass"])
        self.assertFalse(self.document["budgets"]["cosine"]["pass"])
        self.assertEqual(self.document["qualifications"]["aggregate_mathematical"], "FAIL")
        self.assertEqual(self.document["qualifications"]["final_route_disposition"],
                         "ROUTE NOT PROVEN INVARIANT")

    def test_budget_mutation_fails_closed(self):
        mutated = copy.deepcopy(self.document)
        mutated["budgets"]["cosine"]["minimum"] = 0.999
        with self.assertRaises(validator.AggregateEvaluationValidationError):
            validator.validate_document(mutated)

    def test_ledger_or_access_mutation_fails_closed(self):
        for key, value in (("checkpoint_reads", 1), ("shard_opens", 1),
                           ("real_payload_ledger_after", 164)):
            mutated = copy.deepcopy(self.document)
            mutated["isolation"][key] = value
            with self.assertRaises(validator.AggregateEvaluationValidationError):
                validator.validate_document(mutated)

    def test_private_hash_or_expert_id_mutation_fails_closed(self):
        mutated = copy.deepcopy(self.document)
        mutated["private_artifact_verification"]["after_sha256_by_id"]["250"] = "0" * 64
        with self.assertRaises(validator.AggregateEvaluationValidationError):
            validator.validate_document(mutated)
        mutated = copy.deepcopy(self.document)
        mutated["inputs"]["selected_expert_ids"][-1] = 29
        with self.assertRaises(validator.AggregateEvaluationValidationError):
            validator.validate_document(mutated)

    def test_public_document_has_no_private_path(self):
        raw = validator.EVIDENCE.read_text()
        self.assertNotIn("/Users/", raw)
        self.assertNotIn("file://", raw)

    def test_consumer_has_no_checkpoint_or_model_capability(self):
        source = (evaluator.ROOT / "scripts/research/evaluate_f017_weighted_moe_aggregate_safety.py").read_text()
        for forbidden in (".gguf", "ShardProvider", "read_at(", "os.pread", "mmap("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "scripts/research/generate_f017_independent_oracle.py"
SPEC = importlib.util.spec_from_file_location("f017_independent_oracle", GENERATOR)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class IndependentOracleTests(unittest.TestCase):
    def test_oracle_is_deterministic_and_covers_every_boundary(self):
        first = MODULE.build_oracle("0" * 40)
        second = MODULE.build_oracle("0" * 40)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first["boundaries"]),
            {
                "projection",
                "router",
                "complete_expert",
                "top8_shared",
                "mla_dense",
                "complete_layer",
                "final_norm_logits_topk",
            },
        )
        self.assertEqual(first["independence"]["classification"], "INDEPENDENT")
        self.assertFalse(first["independence"]["uses_rust_candidate"])
        self.assertFalse(first["independence"]["uses_rust_reference_functions"])

    def test_edge_distribution_contract_is_public_safe_and_fixed(self):
        oracle = MODULE.build_oracle("0" * 40)
        self.assertEqual(len(oracle["edge_distributions"]["q8_0"]), 5)
        self.assertEqual(
            [case["name"] for case in oracle["edge_distributions"]["router"]],
            ["exact_tie", "near_tie"],
        )
        self.assertNotIn("checkpoint", "".join(oracle["edge_distributions"].keys()).lower())


if __name__ == "__main__":
    unittest.main()

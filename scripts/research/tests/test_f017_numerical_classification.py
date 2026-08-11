from __future__ import annotations

import unittest

from scripts.research.validate_f017_numerical_classification import validate_record


class NumericalClassificationInvariantTests(unittest.TestCase):
    def assert_invalid(self, record: dict[str, object]) -> None:
        with self.assertRaises(ValueError):
            validate_record(record)

    def test_non_applicable_rejects_greedy_identical(self) -> None:
        self.assert_invalid(
            {
                "classification": "numerically_qualified_greedy_identical",
                "greedy_applicability": "not_applicable",
            }
        )

    def test_applicable_greedy_identical_requires_identity_evidence(self) -> None:
        self.assert_invalid(
            {
                "classification": "numerically_qualified_greedy_identical",
                "greedy_applicability": "applicable",
            }
        )

    def test_non_applicable_qualified_record_passes(self) -> None:
        validate_record(
            {
                "classification": "numerically_qualified_greedy_not_applicable",
                "greedy_applicability": "not_applicable",
            }
        )

    def test_applicable_exact_top_k_and_argmax_pass(self) -> None:
        validate_record(
            {
                "classification": "numerically_qualified_greedy_identical",
                "greedy_applicability": "applicable",
                "greedy_identity": {"top_k_ids_exact": True, "argmax_exact": True},
            }
        )

    def test_changed_choice_is_failure_not_not_applicable(self) -> None:
        changed = {"top_k_ids_exact": False, "argmax_exact": False}
        self.assert_invalid(
            {
                "classification": "numerically_qualified_greedy_not_applicable",
                "greedy_applicability": "applicable",
                "greedy_identity": changed,
            }
        )
        validate_record(
            {
                "classification": "numerically_qualified_greedy_divergent",
                "greedy_applicability": "applicable",
                "greedy_identity": changed,
            }
        )


if __name__ == "__main__":
    unittest.main()

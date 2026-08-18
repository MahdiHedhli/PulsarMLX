from __future__ import annotations

import unittest

from scripts.research import validate_f017_complete_layer_aggregate_v2_evaluation as validator


class CompleteLayerV2EvaluationValidatorTests(unittest.TestCase):
    def test_public_release_validates(self):
        self.assertEqual(validator.validate(), "F017_COMPLETE_LAYER_AGGREGATE_V2_EVALUATION_VALID")

    def test_private_path_leaks_fail_closed(self):
        for value in ({"absolute_path": "redacted"}, {"path": "/Users/example/private"}, {"path": ".pulsarmlx-local/private"}):
            with self.assertRaises(Exception):
                validator._no_private_path(value)


if __name__ == "__main__":
    unittest.main()

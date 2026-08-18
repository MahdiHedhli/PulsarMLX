from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import unittest

from scripts.research import evaluate_f017_complete_layer_aggregate_v2 as evaluation


class CompleteLayerProductionEvaluationTests(unittest.TestCase):
    def test_constants_are_frozen(self):
        self.assertEqual(evaluation.STARTING_HEAD, "d4ce39f4d47503195e3d47cddc0280890cc0bda3")
        self.assertEqual(evaluation.V2_CONTRACT_SHA, "13896ac22c03d7354c25f4d182de828b44df0d7239dd7e269175f69d597209fe")
        self.assertEqual(evaluation.RESIDUAL_SHA, "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11")
        self.assertEqual(evaluation.SHARED_SHA, "01dbd9ac75091fcd452ac9bb1bc2479ccdebc0bc7ac46d79285ff45d70e5928d")
        self.assertEqual(evaluation.ROUTED_NOMINAL_SHA, "5a30a81b6e10b126ac22a3be991e5f5c6486372068888f699625b684eb85fc70")
        self.assertEqual(evaluation.ROUTED_INTERSECTION_SHA, "adbbbef090c4d10acc80d0216cc82b5a8dbe299dad4baad1a0d957f661762a50")

    def test_duplicate_json_rejected(self):
        with self.assertRaises(evaluation.EvaluationError):
            json.loads('{"a":1,"a":2}', object_pairs_hook=evaluation.reject_duplicates)

    def test_symbolic_path_rejects_escape_and_wrong_surface(self):
        with self.assertRaises(evaluation.EvaluationError):
            evaluation._safe_relative("../secret.bin", "outputs")
        with self.assertRaises(evaluation.EvaluationError):
            evaluation._safe_relative("packed/secret.bin", "outputs")

    def test_immutable_loader_rejects_writable_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "point.bin"
            path.write_bytes(b"abcd")
            with self.assertRaisesRegex(evaluation.EvaluationError, "writable"):
                evaluation._regular_immutable(path, 4, evaluation.sha256_bytes(b"abcd"), "fixture")

    def test_private_manifest_has_no_absolute_path(self):
        source = Path(evaluation.__file__).read_text()
        self.assertNotIn('"absolute_path"', source)
        self.assertNotIn("GLM-5.2-UD-IQ2_XXS", source)
        self.assertNotIn("SHARD_PATH", source)

    def test_canonical_json_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            evaluation.canonical_bytes({"value": math.inf})


if __name__ == "__main__":
    unittest.main()

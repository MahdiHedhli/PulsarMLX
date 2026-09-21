"""Independent reference anchors and prospective-generation integrity, no model."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / 'scripts/research/glm53_flash/convolution_state'
spec = importlib.util.spec_from_file_location('convolution_scalar_oracle', PACKAGE / 'oracle.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class ScalarReferenceTests(unittest.TestCase):
    def test_signed_channel_impulse_anchor(self):
        inputs = [[[1.0, -1.0, 0.5], [0.0, 0.0, 0.0]]]
        weights = [[[0.25], [0.5]], [[-0.5], [0.25]], [[0.75], [-0.5]]]
        value = oracle.transition(inputs, weights, None, 2)
        self.assertEqual(value['raw']['values'], [[[0.5, -0.25, -0.25], [0.25, 0.5, 0.375]]])
        self.assertEqual(value['state'], {'shape': [1, 1, 3], 'values': [[[0.0, 0.0, 0.0]]]})
        self.assertAlmostEqual(value['activated']['values'][0][0][0], 0.5 / (1 + math.exp(-0.5)))

    def test_short_chunk_retains_older_state(self):
        inputs = [[[0.5, 0.25, -0.5]]]
        initial = [[[-1.0, 0.0, 1.0], [0.25, -0.25, 0.5]]]
        weights = [[[0.125], [0.25], [0.5]]] * 3
        value = oracle.transition(inputs, weights, initial, 3)
        self.assertEqual(value['raw']['values'], [[[0.1875, 0.0625, 0.0]]])
        self.assertEqual(value['state']['values'], [[[0.25, -0.25, 0.5], [0.5, 0.25, -0.5]]])

    def test_committed_source_capsule_and_finite_generation(self):
        raw = (ROOT / 'fixtures/research/glm53-flash-convolution-state-v1/fixtures.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '3ef5266921478b31a247761111dddcc88ae2942e8420ad3d6f481b3c76fc891a')
        fixtures = json.loads(raw)
        self.assertEqual(hashlib.sha256((PACKAGE / 'capsule.py').read_bytes()).hexdigest(), fixtures['source_capsule_sha256'])
        for case in fixtures['cases']:
            for parts in case['partitions']:
                self.assertEqual(sum(parts), case['T'])
                self.assertTrue(all(type(n) is int and n > 0 for n in parts))
        self.assertEqual({c['K'] for c in fixtures['cases']}, {2, 3, 4})


if __name__ == '__main__':
    unittest.main()

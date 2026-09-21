"""Independent fixture/oracle and fail-closed generation regression checks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ROOT / 'scripts/research/glm53_flash/router_caller'
FIXTURE = ROOT / 'fixtures/research/glm53-flash-router-caller-v1/successor-discrimination-v1/fixtures.json'


def module(name):
    spec = importlib.util.spec_from_file_location('tested_' + name, COMPONENTS / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


oracle = module('successor_discrimination_oracle')
controls = module('successor_discrimination')
entry = module('successor')


class GenerationTests(unittest.TestCase):
    def test_frozen_fixture_body_and_complete_cartesian_domain(self):
        raw = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), controls.FIXTURE_SHA256)
        fixture = json.loads(raw)
        expected = {f'cast-{dtype}-{i}-{j}' for dtype in ('float32', 'bfloat16') for i in range(9) for j in range(9)}
        self.assertEqual({c['name'] for c in fixture['cast_cases']}, expected)
        self.assertEqual(len(fixture['cast_cases']), len(expected))
        self.assertEqual(len(fixture['grouped_cases']), 6)
        self.assertEqual(len(fixture['e288_cases']), 3)

    def test_bf16_rounding_midpoints_neighbors_and_signed_zero(self):
        # Independent literal IEEE bit expectations, including round-to-even
        # on either side of a representable midpoint and cancellation inputs.
        cases = [(1.00390625, 0x3f800000), (1.01171875, 0x3f820000),
                 (-1.00390625, 0xbf800000), (-1.01171875, 0xbf820000),
                 (1.0078125, 0x3f810000), (-0.0, 0x80000000)]
        for value, expected in cases:
            with self.subTest(value=value):
                actual = struct.unpack('>I', struct.pack('>f', oracle.represented(value, 'bfloat16')))[0]
                self.assertEqual(actual, expected)

    def test_zero_mask_and_exclusion_have_distinct_literal_ids(self):
        config = {'n_group': 3, 'topk_group': 2, 'num_experts_per_tok': 2,
                  'routed_scaling_factor': 2.5, 'norm_topk_prob': True}
        bias = [-0.75, -0.625, -0.7490234375, -0.6240234375, -0.748046875, -0.623046875]
        zero = oracle.selection([0.0]*6, bias, config, 'zero')
        excluded = oracle.selection([0.0]*6, bias, config, 'exclude')
        self.assertEqual(set(zero['selected_ids']), {0, 1})
        self.assertEqual(set(excluded['selected_ids']), {3, 5})
        self.assertTrue(all(v < 0 for v in zero['group_scores']))
        oracle.check_output([1, 0], [1.25, 1.25], zero, config, {'absolute': 0, 'relative': 0})
        with self.assertRaisesRegex(AssertionError, 'SELECTION_MISMATCH'):
            oracle.check_output([3, 5], [1.25, 1.25], zero, config, {'absolute': 0, 'relative': 0})
        with self.assertRaisesRegex(AssertionError, 'SCORE_MISMATCH'):
            oracle.check_output([0, 1], [1.25, 1.26], zero, config, {'absolute': 0, 'relative': 0})

    def test_wrong_generation_and_changed_inputs_refuse(self):
        class FakeContext:
            roots = {'fixtures': Path('/fabricated-owned-fixture')}
            def __init__(self, raw): self.raw = raw
            def read_verified(self, path): return self.raw
            def parse(self, raw): return json.loads(raw)
        value = json.loads(FIXTURE.read_bytes())
        for changed in ({**value, 'generation': 2}, {**value, 'cast_cases': value['cast_cases'][:-1]}):
            with self.assertRaisesRegex(ValueError, 'WRONG_GENERATION_BYTES'):
                controls.fixtures(FakeContext(json.dumps(changed).encode()))

    def test_failed_or_incomplete_new_producer_never_passes(self):
        for raw in (b'', b'{', b'{"event":"result","status":"FAIL"}\n',
                    b'{"event":"result","status":"PASS","tests_run":4}\ntruncated'):
            self.assertFalse(entry.producer_pass(raw, b'', {}, 'discrimination'))


if __name__ == '__main__':
    unittest.main()

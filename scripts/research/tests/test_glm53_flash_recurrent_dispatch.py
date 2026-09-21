"""Binary64/rational expectations and source/geometry refusals, no MLX import."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[3]
D = ROOT / 'scripts/research/glm53_flash/recurrent_dispatch'


def module(name):
    spec = importlib.util.spec_from_file_location('dispatch_contract_' + name, D / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class DispatchContract(unittest.TestCase):
    def setUp(self):
        self.oracle = module('oracle')
        self.source = module('source')
        self.fixture = json.loads((ROOT / 'fixtures/research/glm53-flash-recurrent-dispatch-v1/fixtures.json').read_bytes())
        self.cases = {c['name']: c for c in self.fixture['cases']}

    def test_exact_complete_factory_initializers_and_caller(self):
        tree = self.source.verify((D / 'capsule.py').read_bytes(), (D / 'upstream-gated-delta.txt').read_bytes(),
                                  (D / 'upstream-language.txt').read_bytes(), json.loads((D / 'provenance.json').read_bytes()))
        self.assertEqual(len(tree.body), 12)

    def repinned_refused(self, before, after):
        raw = (D / 'capsule.py').read_bytes()
        changed = raw.replace(before, after)
        self.assertNotEqual(raw, changed)
        provenance = json.loads((D / 'provenance.json').read_bytes())
        provenance['capsule_sha256'] = hashlib.sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError, '^DISPATCH_ORIGINAL_NODE_OR_SPAN$'):
            self.source.verify(changed, (D / 'upstream-gated-delta.txt').read_bytes(),
                               (D / 'upstream-language.txt').read_bytes(), provenance)

    def test_repinned_initializer_change_refused(self):
        self.repinned_refused(b'_make_gated_delta_kernel(has_mask=False, vectorized=False)',
                              b'_make_gated_delta_kernel(has_mask=True, vectorized=False)')

    def test_repinned_kernel_arithmetic_change_refused(self):
        self.repinned_refused(b'state[i] = state[i] * {g_access};', b'state[i] = state[i];')

    def test_exact_rational_sparse32_anchor(self):
        c = self.cases['kernel32-rational-anchor']
        expected = self.oracle.transition(c, c['state'])
        decayed = Fraction(1, 4) * Fraction(1, 2)
        state = decayed + Fraction(1, 2) * Fraction(1, 2) * (Fraction(3, 4) - Fraction(1, 2) * decayed)
        self.assertEqual(state, Fraction(19, 64))
        self.assertEqual(expected['state'][0][0][0][0], float(state))
        self.assertEqual(expected['output'][0][0][0][0], float(state / 2))

    def test_distinct_masked_output_contracts(self):
        c = self.cases['scalar64-all-false-mask']
        ops = self.oracle.transition(c, c['state'])
        kernel = self.oracle.transition(c, c['state'], kernel_mask=True)
        self.assertEqual(ops['state'], c['state'])
        self.assertEqual(kernel['state'], c['state'])
        self.assertTrue(any(abs(v) > 2e-5 for v in self.oracle.flat(ops['output'])))
        self.assertTrue(all(v == 0 for v in self.oracle.flat(kernel['output'])))

    def test_research_refuses_unsafe_gpu_dimensions(self):
        for key, value in [('Dk', 33), ('Dv', 3), ('Hk', 0)]:
            c = copy.deepcopy(self.cases['vector32-grouped-safe'])
            c[key] = value
            with self.assertRaisesRegex(self.oracle.InputError, '^DOMAIN_SHAPE$'):
                self.oracle.validate(c, c['state'])

    def test_actual_buffer_metadata_refuses_wrong_grid(self):
        self.source.mx = types.SimpleNamespace(float32='FP32', bool_='BOOL')
        def array(shape):
            n = 1
            for value in shape: n *= value
            return types.SimpleNamespace(shape=shape, size=n, dtype='FP32')
        shapes = [(1, 1, 1, 32), (1, 1, 1, 32), (1, 1, 1, 4),
                  (1, 1, 1), (1, 1, 1), (1, 1, 4, 32)]
        arguments = {'inputs': [array(s) for s in shapes] + [1],
                     'grid': (32, 4, 1), 'threadgroup': (32, 4, 1),
                     'output_shapes': [(1, 1, 1, 4), (1, 1, 4, 32)],
                     'output_dtypes': ['FP32', 'FP32'],
                     'template': [('InT', 'FP32'), ('StT', 'FP32'), ('Dk', 32), ('Dv', 4), ('Hk', 1), ('Hv', 1)]}
        self.assertEqual(self.source.kernel_buffers(arguments, list('abcdefg'))['Dk'], 32)
        arguments['grid'] = (64, 4, 1)
        with self.assertRaisesRegex(ValueError, '^KERNEL_SOURCE_GEOMETRY$'):
            self.source.kernel_buffers(arguments, list('abcdefg'))

    def test_frozen_budget_within_declared_ceiling(self):
        budget = self.fixture['fp32_error_budget']
        self.assertLessEqual(4 * budget['max_state_absolute_budget'], 2e-5)
        self.assertLessEqual(4 * budget['max_output_absolute_budget'], 2e-5)
        self.assertEqual(len(self.fixture['cases']), 7)


if __name__ == '__main__':
    unittest.main()

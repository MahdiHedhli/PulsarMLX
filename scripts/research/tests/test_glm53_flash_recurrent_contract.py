"""Independent scalar anchors and source identity refusal, no MLX import."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
COMPONENT = ROOT / 'scripts/research/glm53_flash/recurrent_ops'


def module(name):
    spec = importlib.util.spec_from_file_location('recurrent_contract_' + name, COMPONENT / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class RecurrentContract(unittest.TestCase):
    def setUp(self):
        self.oracle = module('oracle')
        self.fixture = json.loads((ROOT / 'fixtures/research/glm53-flash-recurrent-ops-v1/fixtures.json').read_bytes())
        self.anchor = copy.deepcopy(self.fixture['cases'][0])

    def test_scalar_dyadic_anchor(self):
        actual = self.oracle.transition(self.anchor, self.anchor['state'])
        self.assertEqual(actual['g'], [[[.5]]])
        self.assertEqual(actual['beta'], [[[.5]]])
        self.assertEqual(actual['state'], [[[[.296875]]]])
        self.assertEqual(actual['output'], [[[[.1484375]]]])

    def test_mask_retains_state_but_not_zero_output(self):
        self.anchor['mask'] = [[False]]
        actual = self.oracle.transition(self.anchor, self.anchor['state'])
        self.assertEqual(actual['state'], self.anchor['state'])
        self.assertEqual(actual['output'], [[[[.1484375]]]])
        self.assertEqual(actual['traces'][0]['computed_state'], [[[[.296875]]]])

    def test_asymmetric_grouped_head_anchor(self):
        c = self.anchor
        c.update(Hv=2, Dk=2, Dv=1, q=[[[[.5, .25]]]], k=[[[[.25, .5]]]],
                 v=[[[[.5], [-.5]]]], a=[[[0.0, 0.0]]], b=[[[0.0, 0.0]]],
                 A_log=[0.0, 0.0], dt_bias=[0.0, 0.0], state=None)
        actual = self.oracle.transition(c)
        self.assertEqual(actual['state'], [[[[.0625, .125]], [[-.0625, -.125]]]])
        self.assertEqual(actual['output'], [[[[.0625], [-.0625]]]])

    def test_repinned_capsule_cannot_change_original_ast(self):
        source = module('source'); raw = (COMPONENT / 'capsule.py').read_bytes()
        original = (COMPONENT / 'upstream-gated-delta.txt').read_bytes()
        provenance = json.loads((COMPONENT / 'provenance.json').read_bytes())
        language = (COMPONENT / 'upstream-language.txt').read_bytes()
        changed = raw.replace(b'state = state * decay', b'state = state * decay * decay')
        self.assertNotEqual(changed, raw)
        provenance['capsule_sha256'] = hashlib.sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError, '^RECURRENT_SOURCE_AST_OR_SPAN$'):
            source.verify(changed, original, language, provenance)

    def test_exact_selected_functions_and_caller_ast(self):
        source = module('source')
        tree = source.verify((COMPONENT / 'capsule.py').read_bytes(),
                             (COMPONENT / 'upstream-gated-delta.txt').read_bytes(),
                             (COMPONENT / 'upstream-language.txt').read_bytes(),
                             json.loads((COMPONENT / 'provenance.json').read_bytes()))
        self.assertEqual(len(tree.body), 6)

    def test_domain_refuses_kernel_size_before_shapes(self):
        self.anchor['Dk'] = 32
        with self.assertRaisesRegex(self.oracle.InputError, '^DOMAIN_SHAPE$'):
            self.oracle.validate(self.anchor, self.anchor['state'])


if __name__ == '__main__':
    unittest.main()

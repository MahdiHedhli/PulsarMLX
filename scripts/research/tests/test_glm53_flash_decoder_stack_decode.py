"""Offline (mlx-free) checks for the stack-decode research track: frozen fixture recomputes from the
re-sliced stack reference; logits rows equal the graph-11 stack fixture's; the prospective matrix
reproduces from the recorded oracle variants; recipes hit their needles in the stack capsule and
are refused by its verifier."""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402
from scripts.research.glm53_flash.decoder_stack import source as stack_source  # noqa: E402
from scripts.research.glm53_flash.decoder_stack_decode import generate_fixtures as generator  # noqa: E402
from scripts.research.glm53_flash.decoder_stack_decode import oracle as decode_oracle  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-stack-decode-v1/fixtures.json'
STACK_FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_stack_decode/controls.py'
CELLS = ('KILL', 'INACTIVE', 'WEAK_STRUCTURAL')


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderStackDecodeOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes()); cls.stack = json.loads(STACK_FIXTURE.read_bytes())
        cls.case = cls.fixture['cases'][0]; cls.expected = cls.fixture['expected'][cls.case['fixture_id']]
        cls.capsule_raw = (ROOT / stack_source.CAPSULE).read_bytes(); cls.language_raw = (ROOT / ffn_source.LANGUAGE).read_bytes()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        got = decode_oracle.run(self.case, generator.REFS)
        self.assertEqual(got, self.expected)
        base = self.stack['expected'][self.case['derived_from']['case']]
        self.assertEqual(got['logits'], base['logits'])
        self.assertEqual([st['kind'] for st in got['steps']], ['prefill', 'decode', 'decode'])
        self.assertEqual([st['kv_offset_after'] for st in got['steps']], [2, 3, 4])

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        recipes = _recipes()
        self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        text = self.capsule_raw.decode(); oracle_text = Path(decode_oracle.__file__).read_text()
        for label, before, after in recipes:
            cell = matrix['matrix'][label][0]; self.assertIn(cell, CELLS, label)
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            with self.assertRaisesRegex(ValueError, 'DECODER_STACK_(CALLER_TRANSFORM|CLOSURE)'):
                stack_source.verify_capsule(text.replace(before, after, 1).encode(), self.language_raw, ffn_source)
            v = matrix['oracle_variants'][label]; self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant'}; exec(compile(oracle_text.replace(v['before'], v['after']), 'variant:' + label, 'exec'), ns)
            try:
                out = ns['run'](self.case, generator.REFS)
                rows = [(t, lg) for st in out['steps'] for t, lg in zip(st['tokens'], st['logits'])]
            except ValueError:
                self.assertEqual(cell, 'KILL', label); continue
            err = max(abs(a - b) for t, lg in rows for a, b in zip(lg, self.expected['logits'][t]))
            self.assertEqual(cell, 'KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', label)


if __name__ == '__main__':
    unittest.main()

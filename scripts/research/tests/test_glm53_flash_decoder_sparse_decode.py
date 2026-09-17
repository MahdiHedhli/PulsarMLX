"""Offline (mlx-free) checks for the sparse-attention decode research track.

Pins: the frozen decode fixture recomputes from the incremental oracle; every
decode row equals the frozen prefill reference's row (the incremental pooling
rule is equivalent to full pooling on this fixture, independently of any
candidate); the prospective matrix reproduces from the recorded oracle
variants; the recipes in `controls.py` hit their needles in the sparse capsule
and are refused by its verifier; labels equal matrix keys.
"""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import oracle as prefill_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import source as sparse_source  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse_decode import oracle as decode_oracle  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-sparse-decode-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_sparse_decode/controls.py'
CELLS = ('KILL', 'INACTIVE', 'WEAK_STRUCTURAL')


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderSparseDecodeOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes())
        cls.case = cls.fixture['cases'][0]
        cls.expected = cls.fixture['expected'][cls.case['fixture_id']]
        cls.capsule_raw = (ROOT / sparse_source.CAPSULE).read_bytes()
        cls.language_raw = (ROOT / ffn_source.LANGUAGE).read_bytes()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes_and_equals_prefill_reference(self):
        got = decode_oracle.run(self.case)
        self.assertEqual(got, self.expected)
        full = prefill_oracle.run({k: v for k, v in self.case.items() if k != 'prefill_tokens'})
        rows = [row for st in got['steps'] for row in st['rows']]
        kinds = [st['kind'] for st in got['steps']]
        self.assertEqual(kinds, ['prefill'] + ['decode'] * (self.case['tokens'] - self.case['prefill_tokens']))
        self.assertEqual([r['regime'] for r in rows], ['bypass'] * 2 + ['sparse'] * 5)
        self.assertEqual([r.get('pooling') for r in rows][2:], ['full'] + ['incremental'] * 4)
        for t, row in enumerate(rows):
            self.assertEqual(row['time'], t)
            if row['regime'] == 'sparse':
                self.assertEqual(row['topk'], full['topk'][t]); self.assertEqual(row['allowed'], full['allowed'][t])
            self.assertLessEqual(max(abs(a - b) for a, b in zip(row['output'], full['output'][t])), 1e-12)
        self.assertTrue(any(-1 in r['topk'] for r in rows if r['topk']))

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        recipes = _recipes()
        self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        text = self.capsule_raw.decode()
        oracle_text = Path(decode_oracle.__file__).read_text()
        expected_rows = [row for st in self.expected['steps'] for row in st['rows']]
        for label, before, after in recipes:
            cell = matrix['matrix'][label][0]
            self.assertIn(cell, CELLS, label)
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            with self.assertRaisesRegex(ValueError, 'DECODER_SPARSE_(CALLER_TRANSFORM|CLOSURE)'):
                sparse_source.verify_capsule(text.replace(before, after, 1).encode(), self.language_raw, ffn_source)
            v = matrix['oracle_variants'][label]
            self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant', 'prefill': prefill_oracle}
            src = oracle_text.replace(v['before'], v['after']).replace('from scripts.research.glm53_flash.decoder_sparse import oracle as prefill', '')
            exec(compile(src, 'variant:' + label, 'exec'), ns)
            try:
                rows = [row for st in ns['run'](self.case)['steps'] for row in st['rows']]
            except (ValueError, IndexError):
                self.assertEqual(cell, 'KILL', label); continue
            err = max(abs(a - b) for vr, er in zip(rows, expected_rows) for a, b in zip(vr['output'], er['output']))
            self.assertEqual(cell, 'KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', label)


if __name__ == '__main__':
    unittest.main()

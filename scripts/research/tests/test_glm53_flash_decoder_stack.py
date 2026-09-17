"""Offline (mlx-free) checks for the two-layer GLM-5.3-Flash stack research track.

The supervised `successor.py stack` operation is the qualification; this
module pins what the stdlib can check: the frozen fixture recomputes from the
composed oracle (accepted references only), the stack capsule and its retained
mlx-vlm dependencies pass admission, the prospective matrix reproduces from the
recorded oracle variants, every recipe in `controls.py` hits its needle and is
refused by the capsule verifier, and the recipe labels equal the matrix keys.
"""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import source as sparse_source  # noqa: E402
from scripts.research.glm53_flash.decoder_stack import generate_fixtures as generator  # noqa: E402
from scripts.research.glm53_flash.decoder_stack import oracle as stack_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_stack import source as stack_source  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_stack/controls.py'
CELLS = ('KILL', 'INACTIVE', 'WEAK_STRUCTURAL')


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderStackOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes())
        cls.capsule_raw = (ROOT / stack_source.CAPSULE).read_bytes()
        cls.language_raw = (ROOT / ffn_source.LANGUAGE).read_bytes()
        cls.cache_raw = (ROOT / stack_source.CACHE).read_bytes()
        cls.base_raw = (ROOT / sparse_source.BASE).read_bytes()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        for case in self.fixture['cases']:
            got = stack_oracle.run(case, generator.REFS)
            self.assertEqual(got, self.fixture['expected'][case['fixture_id']], case['fixture_id'])
            self.assertIsNotNone(got['layer1_topk'])
            self.assertGreater(got['layer0_clamp_active_elements'], 0)
            self.assertGreater(got['moe_clamp_active_elements'], 0)

    def test_admission(self):
        nodes, contract = stack_source.verify_capsule(self.capsule_raw, self.language_raw, ffn_source)
        self.assertEqual([n.name for n in nodes], ['Glm5NextDecoderLayer', 'Glm5NextModel', 'source_language_model'])
        dep, digests = stack_source.verify_dependencies(self.cache_raw, self.base_raw, ffn_source, sparse_source)
        self.assertEqual(sorted(dep), sorted(stack_source.DEPENDENCIES))
        with self.assertRaisesRegex(ValueError, 'DECODER_STACK_DEPENDENCY_DIGEST'):
            stack_source.verify_dependencies(self.cache_raw + b'\n', self.base_raw, ffn_source, sparse_source)
        with self.assertRaisesRegex(ValueError, 'DECODER_STACK_UPSTREAM_DIGEST'):
            stack_source.verify_capsule(self.capsule_raw, self.language_raw + b'\n', ffn_source)

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        recipes = _recipes()
        self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        text = self.capsule_raw.decode()
        oracle_text = Path(stack_oracle.__file__).read_text()
        for label, before, after in recipes:
            cells = matrix['matrix'][label]
            self.assertTrue(all(c in CELLS for c in cells), label)
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            with self.assertRaisesRegex(ValueError, 'DECODER_STACK_(CALLER_TRANSFORM|CLOSURE)'):
                stack_source.verify_capsule(text.replace(before, after, 1).encode(), self.language_raw, ffn_source)
            v = matrix['oracle_variants'][label]
            self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant'}; exec(compile(oracle_text.replace(v['before'], v['after']), 'variant:' + label, 'exec'), ns)
            for cell, case in zip(cells, self.fixture['cases']):
                exp = self.fixture['expected'][case['fixture_id']]['logits']
                try:
                    out = ns['run'](case, generator.REFS)['logits']
                except ValueError:
                    self.assertEqual(cell, 'KILL', label); continue
                err = max(abs(a - b) for ra, rb in zip(out, exp) for a, b in zip(ra, rb))
                self.assertEqual(cell, 'KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', label)


if __name__ == '__main__':
    unittest.main()

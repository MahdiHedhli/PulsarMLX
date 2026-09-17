"""Offline (mlx-free) checks for the Glm5NextSparseAttention research track.

The supervised `successor.py sparse` operation is the qualification; this
module pins what the stdlib can check: the frozen fixture recomputes from the
independent oracle, the retained mla/base texts and the capsule pass admission,
the prospective matrix reproduces from the recorded oracle variants, every
recipe in `controls.py` hits its needle and is refused by the capsule verifier,
and the recipe labels equal the matrix keys.
"""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import oracle as sparse_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import source as sparse_source  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-sparse-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_sparse/controls.py'
CELLS = ('KILL', 'INACTIVE', 'WEAK_STRUCTURAL')


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderSparseOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes())
        cls.capsule_raw = (ROOT / sparse_source.CAPSULE).read_bytes()
        cls.language_raw = (ROOT / ffn_source.LANGUAGE).read_bytes()
        cls.mla_raw = (ROOT / sparse_source.MLA).read_bytes()
        cls.base_raw = (ROOT / sparse_source.BASE).read_bytes()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        for case in self.fixture['cases']:
            got = sparse_oracle.run(case)
            self.assertEqual(got, self.fixture['expected'][case['fixture_id']], case['fixture_id'])
            for m in (got['selection_margins'] or []):
                if m is not None:
                    self.assertGreaterEqual(m, self.fixture['generator']['margin'])
        self.assertTrue(self.fixture['expected']['sparse-bypass-s4']['bypass'])
        self.assertFalse(self.fixture['expected']['sparse-kpool2-topk4-s7']['bypass'])

    def test_admission(self):
        nodes, contract = sparse_source.verify_capsule(self.capsule_raw, self.language_raw, ffn_source)
        self.assertEqual([n.name for n in nodes], ['Glm5NextIndexer', 'source_sparse_attention'])
        self.assertEqual(contract['digest_scheme'], ffn_source.DIGEST_SCHEME)
        for raw, sha, name, g in ((self.mla_raw, sparse_source.MLA_SHA256, 'MultiLinear', sparse_source.MULTILINEAR_GLOBALS),
                                  (self.base_raw, sparse_source.BASE_SHA256, 'scaled_dot_product_attention', sparse_source.SDPA_GLOBALS)):
            node, _ = sparse_source.verify_dependency(raw, sha, name, g, ffn_source)
            self.assertEqual(node.name, name)
        with self.assertRaisesRegex(ValueError, 'DECODER_SPARSE_DEPENDENCY_DIGEST'):
            sparse_source.verify_dependency(self.mla_raw + b'\n', sparse_source.MLA_SHA256, 'MultiLinear', sparse_source.MULTILINEAR_GLOBALS, ffn_source)
        with self.assertRaisesRegex(ValueError, 'DECODER_SPARSE_UPSTREAM_DIGEST'):
            sparse_source.verify_capsule(self.capsule_raw, self.language_raw + b'\n', ffn_source)

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        self.assertEqual(matrix['fixtures'], [c['fixture_id'] for c in self.fixture['cases']])
        recipes = _recipes()
        self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        text = self.capsule_raw.decode()
        oracle_text = Path(sparse_oracle.__file__).read_text()
        for label, before, after in recipes:
            cells = matrix['matrix'][label]
            self.assertTrue(all(c in CELLS for c in cells), label)
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            with self.assertRaisesRegex(ValueError, 'DECODER_SPARSE_(CALLER_TRANSFORM|CLOSURE)'):
                sparse_source.verify_capsule(text.replace(before, after, 1).encode(), self.language_raw, ffn_source)
            # The recorded oracle variant reproduces the frozen cell.
            v = matrix['oracle_variants'][label]
            self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant'}; exec(compile(oracle_text.replace(v['before'], v['after']), 'variant:' + label, 'exec'), ns)
            for cell, case in zip(cells, self.fixture['cases']):
                exp = self.fixture['expected'][case['fixture_id']]['output']
                try:
                    out = ns['run'](case)['output']
                except AssertionError:
                    self.assertEqual(cell, 'KILL', label); continue
                err = max(abs(a - b) for ra, rb in zip(out, exp) for a, b in zip(ra, rb))
                self.assertEqual(cell, 'KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', label)


if __name__ == '__main__':
    unittest.main()

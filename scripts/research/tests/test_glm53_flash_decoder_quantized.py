"""Offline (mlx-free) checks for the quantized-projection research track: the frozen fixtures recompute from the
affine-dequantization reference; the packing is little-endian (hand-constructed word); the prospective matrix
reproduces from the recorded reference variants; recipes hit their needles in the retained texts."""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_moe import source as moe_source  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import source as sparse_source  # noqa: E402
from scripts.research.glm53_flash.decoder_quantized import oracle as quantized_oracle  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_quantized/controls.py'


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


def _flat(v):
    if isinstance(v, list):
        return [x for y in v for x in _flat(y)]
    if isinstance(v, dict):
        if 'expert' in v:
            return [x for k in ('gate', 'up', 'output') for x in _flat(v[k])]
        return [x for y in v.values() for x in _flat(y)]
    return [v]


class DecoderQuantizedOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes()); cls.cases = {c['fixture_id']: c for c in cls.fixture['cases']}
        cls.switch_text = (ROOT / moe_source.SWITCH).read_text(); cls.mla_text = (ROOT / sparse_source.MLA).read_text()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        for fid, case in self.cases.items():
            self.assertEqual(quantized_oracle.run(case), self.fixture['expected'][fid], fid)
        for fid in ('switch-4bit-g64', 'switch-8bit-g32'):
            self.assertTrue(any(e['clamp_active'] > 0 for t in self.fixture['expected'][fid]['tokens'] for e in t), fid)
            cfg = self.cases[fid]['config']
            for p in ('gate', 'up', 'down'):
                for pack in self.cases[fid]['quantized'][p]:
                    per_word = 32 // cfg['bits']
                    self.assertEqual(len(pack['words'][0]) * per_word, len(pack['scales'][0]) * cfg['group_size'])

    def test_packing_is_little_endian(self):
        # 4-bit: codes [1, 2, 15, 0, 0, 0, 0, 0] -> word 0x0000_0F21 ; scale 0.5, bias -1 -> values
        pack = {'words': [[0x0F21]], 'scales': [[0.5]], 'biases': [[-1.0]]}
        self.assertEqual(quantized_oracle.unpack([0x0F21], 4), [1, 2, 15, 0, 0, 0, 0, 0])
        self.assertEqual(quantized_oracle.dequantize(pack, 4, 8), [[-0.5, 0.0, 6.5, -1.0, -1.0, -1.0, -1.0, -1.0]])
        self.assertEqual(quantized_oracle.unpack([0x0201], 8), [1, 2, 0, 0])

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        recipes = _recipes()
        self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        oracle_text = Path(quantized_oracle.__file__).read_text()
        for label, target, before, after in recipes:
            self.assertEqual(matrix['targets'][label], target, label)
            text = self.switch_text if target == 'switch' else self.mla_text
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            v = matrix['oracle_variants'][label]; self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant', 'moe': quantized_oracle.moe}
            exec(compile(oracle_text.replace(v['before'], v['after']).replace('from scripts.research.glm53_flash.decoder_moe import oracle as moe', ''), 'variant:' + label, 'exec'), ns)
            for cell, fid in zip(matrix['matrix'][label], matrix['cases_by_target'][target]):
                try:
                    out = ns['run'](self.cases[fid]); a, b = _flat(out), _flat(self.fixture['expected'][fid])
                    if len(a) != len(b):
                        self.assertEqual(cell, 'KILL', label); continue
                    err = max(abs(p - q) for p, q in zip(a, b))
                    self.assertEqual(cell, 'KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', label)
                except (ValueError, IndexError, TypeError):
                    self.assertEqual(cell, 'KILL', label)


if __name__ == '__main__':
    unittest.main()

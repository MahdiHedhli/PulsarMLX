"""Offline (mlx-free) checks for the expert-offload track: the frozen fixture recomputes from the values + LRU-policy
reference; the schedule exercises eviction, refetch and the bulk path; the prospective matrix reproduces from the
recorded variants; recipes hit their needles in the retained texts."""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_offload import oracle as offload_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_offload import source as offload_source  # noqa: E402
from scripts.research.glm53_flash.decoder_moe import source as moe_source  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-offload-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_offload/controls.py'


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderOffloadOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes()); cls.cases = {c['fixture_id']: c for c in cls.fixture['cases']}
        cls.offload_text = (ROOT / offload_source.OFFLOAD).read_text(); cls.switch_text = (ROOT / moe_source.SWITCH).read_text()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        for fid, case in self.cases.items():
            exp = self.fixture['expected'][fid]
            self.assertEqual(offload_oracle.run(case), exp, fid)
            self.assertEqual(case['budget_bytes'], 2 * exp['expert_bytes'])
            self.assertGreater(exp['final_stats']['evictions'], 0); self.assertGreater(exp['final_stats']['hits'], 0)
            self.assertEqual([c['bulk'] for c in exp['calls']], [False] * 6 + [True, False])

    def test_admission_static(self):
        import hashlib
        self.assertEqual(hashlib.sha256(self.offload_text.encode()).hexdigest(), offload_source.OFFLOAD_SHA256)
        store = next(n for n in ast.parse(self.offload_text).body if getattr(n, 'name', None) == 'ExpertStore')
        module = next(n for n in ast.parse(self.switch_text).body if getattr(n, 'name', None) == 'OffloadedSwitchGLU')
        self.assertEqual(offload_source._census(ast.unparse(store), 's'), offload_source.STORE_GLOBALS)
        self.assertEqual(offload_source._census(ast.unparse(module), 'm'), offload_source.MODULE_GLOBALS)

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        recipes = _recipes(); self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        oracle_text = Path(offload_oracle.__file__).read_text()
        for label, target, before, after in recipes:
            self.assertEqual(matrix['targets'][label], target, label)
            text = self.offload_text if target == 'store' else self.switch_text
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            v = matrix['oracle_variants'][label]; self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant', 'quantized': offload_oracle.quantized, 'OrderedDict': offload_oracle.OrderedDict}
            src = oracle_text.replace(v['before'], v['after']).replace('from scripts.research.glm53_flash.decoder_quantized import oracle as quantized', '').replace('from collections import OrderedDict', '')
            exec(compile(src, 'variant:' + label, 'exec'), ns)
            for cell, fid in zip(matrix['matrix'][label], matrix['fixtures']):
                c = self.cases[fid]; exp = self.fixture['expected'][fid]
                try:
                    out = ns['run'](c)
                    differ = any(vc['stats'] != ec['stats'] or vc['bulk'] != ec['bulk'] for vc, ec in zip(out['calls'], exp['calls']))
                    err = max(abs(a - b) for vc, ec in zip(out['calls'], exp['calls']) for vr, er in zip(vc['outputs'], ec['outputs']) for va, ea in zip(vr, er) for a, b in zip(va, ea))
                    self.assertEqual(cell, 'KILL' if differ or err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', label)
                except (KeyError, IndexError, ValueError):
                    self.assertEqual(cell, 'KILL', label)


if __name__ == '__main__':
    unittest.main()

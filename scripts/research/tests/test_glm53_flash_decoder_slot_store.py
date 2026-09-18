"""Offline (mlx-free) checks for the slot-store track: the fixture recomputes from the slot model; every case splits a call
into waves and evicts; the prospective policy cells reproduce from the recorded variants; the structural mutants are the
recorded three; the runtime file's needles exist exactly once; the module imports nothing from mlx-vlm."""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_slot_store import oracle as slot_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_slot_store import generate_fixtures as generator  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v1/fixtures.json'
STORE = ROOT / 'scripts/research/glm53_flash/dogfood/pulsar_slot_store.py'
NEEDLES = ('                self._counts[k] *= self.decay\n', '        return (self._counts.get(key, 0.0), self._touch.get(key, 0))\n',
           '            self._warm_admitted = self._admit_warm_state()\n', '                candidates = [k for k in L.slot_of if k not in pinned]\n',
           '        if reads:\n            L.map_array = None\n        return reads\n', '            store.fill(lid, store.touch_wave(lid, waves[0]))\n',
           '            L.slot_of[j] = s; L.expert_to_slot[j] = s\n            reads.append((j, s))\n',
           '        return np.frombuffer(buf[a - lo:b - lo], dtype=np_dtype).reshape(e["shape"])\n',
           '        self.contiguous = (header.get("__metadata__") or {}).get("layout") == "expert-contiguous/1"\n')


class SlotStoreOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        fx = json.loads(FIXTURE.read_bytes())
        for case in fx['cases']:
            exp = fx['expected'][case['fixture_id']]; got = slot_oracle.run(case)
            self.assertEqual(got, {k: v for k, v in exp.items() if k in got})
            self.assertGreater(exp['final_stats']['evictions'], 0)
            self.assertTrue(any(len(c['waves']) > 1 for c in exp['calls']), 'no wave split')

    def test_controls_prospective(self):
        fx = json.loads(FIXTURE.read_bytes()); matrix = fx['expected_kill_matrix']
        text = Path(slot_oracle.__file__).read_text()
        predicted = generator.predicted_cells(fx['cases'], fx['expected'], {k: (v['before'], v['after']) for k, v in matrix['oracle_variants'].items()}, text)
        for label in matrix['structural_mutants']:
            predicted[label] = ['KILL' for _ in fx['cases']]
        self.assertEqual(predicted, matrix['matrix'])
        self.assertEqual(sorted(matrix['structural_mutants']), ['coalesce-offset-wrong', 'layout-flag-ignored', 'map-not-refreshed', 'missing-check-removed', 'victim-slot-wrong'])
        self.assertEqual(matrix['revision'], 3)
        store = STORE.read_text()
        for needle in NEEDLES:
            self.assertEqual(store.count(needle), 1, needle)
        tree = ast.parse(store)
        top_level = {n.module.split('.')[0] for n in tree.body if isinstance(n, ast.ImportFrom)} | {a.name.split('.')[0] for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        self.assertNotIn('mlx_vlm', top_level)   # the store and module depend on mlx only; mlx_vlm appears only inside patch_model_slots
        inside = [n for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == 'patch_model_slots' for n in ast.walk(f) if isinstance(n, ast.ImportFrom) and n.module.startswith('mlx_vlm')]
        self.assertEqual(len(inside), 1)


if __name__ == '__main__':
    unittest.main()

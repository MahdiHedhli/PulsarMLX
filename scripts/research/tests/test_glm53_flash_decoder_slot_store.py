"""Offline (mlx-free) checks for the slot-store track: the fixture recomputes from the slot model; every case splits a call
into waves and evicts; the read-phase fault expectations (graph 31) recompute and satisfy the reservation invariants; the
prospective policy cells reproduce from the recorded variants; the structural mutants are the recorded seven; the runtime
file's needles exist exactly once; the module imports nothing from mlx-vlm."""
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
           '            store.fill(lid, store.touch_wave(lid, waves[0]))\n',
           '            reads.append((j, s))\n        return reads',
           '        return np.frombuffer(buf[a - lo:b - lo], dtype=np_dtype).reshape(e["shape"])\n',
           '        self.contiguous = (header.get("__metadata__") or {}).get("layout") == "expert-contiguous/1"\n',
           '            L.pending[j] = s                                                  # reserved, published by fill on success\n',
           '        if self.poisoned is not None:\n            raise RuntimeError(f"STORE_POISONED: {self.poisoned}")\n',
           '            L.free[0:0] = [s for _, s in reads]                               # a retry takes the same slots back\n')


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

    def test_fault_expectations_recompute(self):
        """Graph 31: the read-phase fault runs at the first miss and the first eviction reproduce from the model; the retry
        reproduces the fault-free slot map at the failing call, misses advance by the wave's misses twice, the victim of the
        first-eviction point stays evicted after the fault, and a fault never changes a value (the model has no output
        path that depends on it)."""
        fx = json.loads(FIXTURE.read_bytes())
        for case in fx['cases']:
            fid = case['fixture_id']; exp = fx['expected'][fid]; faults = fx['expected_faults'][fid]
            self.assertEqual(faults['points'], slot_oracle.fault_points(exp))
            for name, pt in faults['points'].items():
                got = slot_oracle.run(case, fault=pt); rec = faults['read_phase'][name]; ci = pt['call']
                self.assertEqual(got['final_stats'], rec['final_stats']); self.assertEqual(got['warm_state'], rec['warm_state']); self.assertEqual(got['fault'], rec['fault'])
                for g, r in zip(got['calls'], rec['calls']):
                    self.assertEqual({k: v for k, v in g.items() if k in r}, r)
                self.assertEqual(got['calls'][ci]['slot_of'], exp['calls'][ci]['slot_of'], 'retry must reproduce the slot map')
                after = got['calls'][ci]['after_fault']; wave = exp['calls'][ci]['waves'][pt['wave']]
                wave_misses = sum(1 for j in wave if j in exp['calls'][ci]['reads'])
                self.assertEqual(got['calls'][ci]['stats']['misses'], exp['calls'][ci]['stats']['misses'] + wave_misses)
                self.assertEqual(got['calls'][ci]['stats']['evictions'], exp['calls'][ci]['stats']['evictions'], 'no second eviction on retry')
                self.assertEqual(after['fill_failures'], 1); self.assertEqual(got['calls'][ci]['attempts'], 2)
                for j in wave:
                    if j in exp['calls'][ci]['reads']:
                        self.assertNotIn(str(j), after['slot_of'], 'a reserved (missed) expert must not be resident after the fault')
                    else:
                        self.assertIn(str(j), after['slot_of'], 'a hit of the failed wave stays resident')
                if name == 'first-eviction':
                    self.assertGreater(exp['calls'][ci]['wave_evictions'][pt['wave']], 0)
                    self.assertLess(after['stats']['resident_experts'], exp['capacity'])

    def test_controls_prospective(self):
        fx = json.loads(FIXTURE.read_bytes()); matrix = fx['expected_kill_matrix']
        text = Path(slot_oracle.__file__).read_text()
        predicted = generator.predicted_cells(fx['cases'], fx['expected'], {k: (v['before'], v['after']) for k, v in matrix['oracle_variants'].items()}, text)
        for label in matrix['structural_mutants']:
            predicted[label] = ['KILL' for _ in fx['cases']]
        self.assertEqual(predicted, matrix['matrix'])
        self.assertEqual(sorted(matrix['structural_mutants']), ['coalesce-offset-wrong', 'layout-flag-ignored', 'missing-check-removed', 'poison-not-checked',
                                                                 'publish-before-fill', 'release-slots-omitted', 'victim-slot-wrong'])
        self.assertEqual(matrix['revision'], 5)
        self.assertNotIn('map_array', STORE.read_text())   # no device mirror of the slot map (revision 5)
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

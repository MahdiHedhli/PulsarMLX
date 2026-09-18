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

from scripts.research.glm53_flash.decoder_slot_store import generate_fixtures_v2 as generator_v2  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v1/fixtures.json'
FIXTURE_V2 = ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v2/fixtures.json'
NEEDLES_V2 = ('            y = mx.unflatten(y[inv_order], 0, slots.shape)\n', '            inv_order = mx.argsort(order)\n', '        do_sort = slots.size >= 64\n',
              '        slots = self._layers[lid].expert_to_slot[idx_host]\n', '        pieces = [(i, off, min(off + chunk, hi - lo)) for i, (lo, hi) in enumerate(ranges) for off in range(0, hi - lo, chunk)]\n',
              '        elif n_cold >= self.bulk_min:\n', '            if runs and lo - runs[-1][1] <= gap_experts * (hi - lo):\n')
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

    def test_fixture_v2_recomputes_and_reaches_every_path(self):
        """Graph 33: values/policy from the slot model, the read-path predictions from predict_paths, the reachability constraints
        of the generator (56/64/72-index calls, evictions, two waves, bulk and pool waves, >= 2 coalesced runs, multi-chunk runs),
        the bf16 case's inputs bf16-representable, the policy cells from the oracle variants, the seven structural mutants and
        their needles."""
        fx = json.loads(FIXTURE_V2.read_bytes()); runtime = fx['runtime']
        self.assertEqual(sorted(c['fixture_id'] for c in fx['cases']), ['slot2-4bit-g32-bf16', 'slot2-4bit-g32-f32', 'slot2-8bit-g32-f32'])
        for case in fx['cases']:
            exp = fx['expected'][case['fixture_id']]; got = slot_oracle.run(case)
            self.assertEqual(got, {k: v for k, v in exp.items() if k in got})
            self.assertEqual(slot_oracle.predict_paths(case, exp, runtime), exp['paths'])
            nbytes = slot_oracle.expert_bytes_v2(case['config'])
            self.assertEqual(exp['capacity'], generator_v2.CAPACITY); self.assertEqual(case['budget_bytes'], generator_v2.CAPACITY * nbytes)
            reach = generator_v2.reachability(exp, nbytes)
            self.assertTrue(all(reach.values()), reach); self.assertEqual(reach, exp['reachability'])
            self.assertEqual(len(case['indices'][0]), 8)
            last = exp['paths']['per_call'][-1]
            self.assertGreater(last['sorted_gathers'], 0); self.assertGreater(last['hash_cold']['bulk_reads'], 0); self.assertGreater(last['hash_cold']['pool_reads'], 0)
            self.assertGreater(last['contig_cold']['chunks_read'], last['contig_cold']['coalesced_ranges']); self.assertGreater(last['contig_cold']['overread_bytes'], 0)
            self.assertEqual(last['hash_cold']['requested_read_bytes'], last['logical_admitted_bytes'])
            self.assertEqual(last['contig_cold']['requested_read_bytes'] - last['contig_cold']['overread_bytes'], last['logical_admitted_bytes'])
            self.assertEqual(case['tolerance'], generator_v2.TOL[case['config']['scales_dtype']])
            if case['config']['scales_dtype'] == 'bfloat16':
                for row in case['x']:
                    self.assertTrue(all(generator_v2.bf16(v) == v for v in row))
                for p in ('gate', 'up', 'down'):
                    for pack in case['quantized'][p]:
                        self.assertTrue(all(generator_v2.bf16(v) == v for row in pack['scales'] + pack['biases'] for v in row))
        matrix = fx['expected_kill_matrix']
        text = Path(slot_oracle.__file__).read_text()
        predicted = generator.predicted_cells(fx['cases'], fx['expected'], {k: (v['before'], v['after']) for k, v in matrix['oracle_variants'].items()}, text)
        for label in matrix['structural_mutants']:
            predicted[label] = ['KILL' for _ in fx['cases']]
        self.assertEqual(predicted, matrix['matrix'])
        self.assertEqual(sorted(matrix['structural_mutants']), sorted(generator_v2.STRUCTURAL))
        self.assertEqual({k: v['expected_reason'] for k, v in matrix['structural_mutants'].items() if v['expected_reason'] == 'counter'},
                         {'sort-threshold-raised': 'counter', 'bulk-threshold-ignored': 'counter', 'coalesce-gap-ignored': 'counter'})
        store = STORE.read_text()
        for needle in NEEDLES_V2:
            self.assertEqual(store.count(needle), 1, needle)
        for k in ('logical_admitted_bytes', 'requested_read_bytes', 'overread_bytes', 'hot_copy_bytes', 'sorted_gathers', 'chunks_read', 'pool_reads'):
            self.assertIn(f'"{k}"', store)


if __name__ == '__main__':
    unittest.main()

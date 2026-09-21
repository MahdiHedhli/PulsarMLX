"""Replay-harness controls on the frozen tiny fixture-v2 store (unpruned-fidelity G37). Needs mlx (the dogfood env) and
opts in with PULSAR_REPLAY_TEST=1: it imports mlx, which would break the `mlx not imported` assertions of the other
modules when everything runs in one `unittest discover` process (first contact at closeout). Skipped otherwise; the
slot-store counters themselves are qualified by the supervised operation.

Controls: (1) a trace captured from PulsarSwitchGLU over the fixture schedule replays with gap 0 / 1 / 2 and the
replay's counters equal oracle.predict_paths for that gap (counter reconciliation, phase separation, complete workload
execution, parameter reachability); (2) the footer policy counters are reproduced (policy_reproduced); (3) a second
fresh replay gives identical counters (state reset); (4) at gap 0 adjacent misses still merge (over-read 0, ranges <
cold experts); (5) two mutants are detected: a silently ignored gap option and an over-read counter forced to zero."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOGFOOD = ROOT / 'scripts/research/glm53_flash/dogfood'
sys.path.insert(0, str(ROOT))
import importlib.util
HAVE_MLX = importlib.util.find_spec('mlx') is not None and os.environ.get('PULSAR_REPLAY_TEST') == '1'
from scripts.research.glm53_flash.decoder_slot_store import oracle  # noqa: E402

FIXTURE_V2 = ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v2/fixtures.json'


def write_store(case, directory):
    import mlx.core as mx
    sys.path.insert(0, str(DOGFOOD)); import repack_v2
    hashdir = directory / 'hash'; (hashdir / 'experts').mkdir(parents=True)
    layer = {}
    for p in ('gate', 'up', 'down'):
        for j, pack in enumerate(case['quantized'][p]):
            layer[f'e{j}.{p}_proj.weight'] = mx.array(pack['words'], dtype=mx.uint32)
            layer[f'e{j}.{p}_proj.scales'] = mx.array(pack['scales'], dtype=mx.float32); layer[f'e{j}.{p}_proj.biases'] = mx.array(pack['biases'], dtype=mx.float32)
    mx.eval(list(layer.values()))
    mx.save_safetensors(str(hashdir / 'experts' / 'layer_0000.safetensors'), layer, metadata={'format': 'mlx'})
    (hashdir / 'offload_index.json').write_text(json.dumps({'layers': [0], 'num_experts': case['config']['num_experts']}))
    contig = directory / 'contig'; (contig / 'experts').mkdir(parents=True)
    repack_v2.write_contiguous(str(hashdir / 'experts' / 'layer_0000.safetensors'), str(contig / 'experts' / 'layer_0000.safetensors'))
    (contig / 'offload_index.json').write_text(json.dumps({'layers': [0], 'num_experts': case['config']['num_experts'], 'layout': repack_v2.LAYOUT}))
    return contig


@unittest.skipUnless(HAVE_MLX, 'mlx not installed or PULSAR_REPLAY_TEST != 1')
class ReplayTrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fx = json.loads(FIXTURE_V2.read_bytes()); cls.runtime = fx['runtime']
        cls.case = next(c for c in fx['cases'] if c['fixture_id'] == 'slot2-4bit-g32-f32'); cls.expected = fx['expected'][cls.case['fixture_id']]
        import mlx.core as mx
        cls.dir = Path(tempfile.mkdtemp(prefix='replay-')); cls.contig = write_store(cls.case, cls.dir)
        sys.path.insert(0, str(DOGFOOD)); import pulsar_slot_store as pss
        cfg = cls.case['config']; q = (cfg['group_size'], cfg['bits'], 'affine')
        store = pss.PulsarSlotStore(str(cls.contig), cls.case['budget_bytes'], 0, decay=cls.case['policy']['decay'], decay_every=cls.case['policy']['decay_every'], warm_start=False,
                                    coalesce_gap_experts=2, read_chunk_bytes=cls.runtime['read_chunk_bytes'])
        store.force_cold = True; store.trace = []
        module = pss.PulsarSwitchGLU(store, 0, q, q, q)
        phase_stats = {}
        for ci, call in enumerate(cls.case['schedule']):
            store.phase = 'prefill' if ci < 3 else 'decode'          # the first three calls stand in for prefill
            if ci == 3:
                phase_stats['prefill'] = store.stats()
            ts = call['tokens']
            y = module(mx.array([[cls.case['x'][t] for t in ts]], dtype=mx.float32), mx.array([[cls.case['indices'][t] for t in ts]], dtype=mx.int32)); mx.eval(y)
        phase_stats['final'] = store.stats()
        cls.trace = cls.dir / 'trace.jsonl'
        with open(cls.trace, 'w') as fh:
            fh.write(json.dumps({'header': True, 'offload': str(cls.contig), 'layout': store.layout, 'capacity_per_layer': store.capacity, 'expert_bytes': store.expert_bytes, 'budget_bytes': store._budget, 'num_experts': store.num_experts,
                                 'coalesce_gap_experts': 2, 'read_chunk_bytes': cls.runtime['read_chunk_bytes'], 'bulk_min': store.bulk_min, 'decay': store.decay, 'decay_every': store.decay_every}) + '\n')
            for ph, lid, wave in store.trace:
                fh.write(json.dumps({'p': ph, 'l': lid, 'w': wave}) + '\n')
            fh.write(json.dumps({'footer': True, 'phase_stats': phase_stats}) + '\n')
        cls.capture_final = phase_stats['final']

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def replay(self, gap, dogfood=DOGFOOD, label=None):
        log = self.dir / f'replay-{gap}-{label or "x"}.json'
        p = subprocess.run([sys.executable, '-I', '-B', str(dogfood / 'replay_trace.py'), '--trace', str(self.trace), '--coalesce-gap', str(gap), '--read-chunk-bytes', str(self.runtime['read_chunk_bytes']), '--force-cold', '--log', str(log)],
                           capture_output=True, text=True, timeout=300, env={**os.environ, 'PYTHONPATH': ''})
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        return json.load(open(log))

    def predicted(self, gap):
        return oracle.predict_paths(self.case, self.expected, {**self.runtime, 'coalesce_gap_experts': gap})['per_call'][-1]['contig_cold']

    def test_replay_counters_match_prediction_for_every_gap(self):
        for gap in (0, 1, 2):
            rec = self.replay(gap); st = rec['final_stats']; pred = self.predicted(gap)
            self.assertTrue(rec['policy_reproduced'], rec['policy_checks'])
            for k in ('cold_reads', 'coalesced_ranges', 'chunks_read', 'requested_read_bytes', 'overread_bytes'):
                self.assertEqual(st[k], pred[k], (gap, k))
            self.assertEqual(st['logical_admitted_bytes'], st['misses'] * st['expert_bytes'])
            self.assertEqual(st['requested_read_bytes'] - st['overread_bytes'] + st['hot_copy_bytes'], st['logical_admitted_bytes'])
            self.assertEqual(set(rec['phases']), {'prefill', 'decode'})
            self.assertEqual(sum(p['waves'] for p in rec['phases'].values()), self.capture_final['waves'])
            self.assertEqual(st['hits'] + st['misses'], self.capture_final['hits'] + self.capture_final['misses'])
            self.assertEqual(st['hits'], self.capture_final['hits']); self.assertEqual(st['evictions'], self.capture_final['evictions'])

    def test_gap0_still_merges_adjacent_misses(self):
        rec = self.replay(0, label='adj'); st = rec['final_stats']
        self.assertEqual(st['overread_bytes'], 0)
        self.assertLess(st['coalesced_ranges'], st['cold_reads'], 'adjacent cold experts must still merge at gap 0')
        self.assertEqual(st['requested_read_bytes'], st['logical_admitted_bytes'])

    def test_fresh_process_reset_is_identical(self):
        a = self.replay(2, label='a')['final_stats']; b = self.replay(2, label='b')['final_stats']
        for k in ('hits', 'misses', 'evictions', 'coalesced_ranges', 'chunks_read', 'requested_read_bytes', 'overread_bytes', 'waves'):
            self.assertEqual(a[k], b[k], k)

    def mutant_dir(self, before, after):
        d = Path(tempfile.mkdtemp(prefix='mutant-')); src = (DOGFOOD / 'pulsar_slot_store.py').read_text()
        self.assertEqual(src.count(before), 1)
        (d / 'pulsar_slot_store.py').write_text(src.replace(before, after)); shutil.copy(DOGFOOD / 'replay_trace.py', d / 'replay_trace.py')
        return d

    def test_mutant_gap_option_ignored_is_detected(self):
        d = self.mutant_dir('            if runs and lo - runs[-1][1] <= gap_experts * (hi - lo):\n', '            if runs:\n')
        rec = self.replay(0, dogfood=d, label='mut-gap'); st = rec['final_stats']; pred = self.predicted(0)
        self.assertNotEqual((st['coalesced_ranges'], st['overread_bytes']), (pred['coalesced_ranges'], pred['overread_bytes']), 'an ignored gap option went undetected')

    def test_mutant_overread_forced_zero_is_detected(self):
        d = self.mutant_dir('                self._overread_bytes += (hi - lo) - sum(f.expert_range(j)[1] - f.expert_range(j)[0] for j in js)\n', '                self._overread_bytes += 0\n')
        rec = self.replay(2, dogfood=d, label='mut-over'); st = rec['final_stats']
        self.assertNotEqual(st['requested_read_bytes'] - st['overread_bytes'] + st['hot_copy_bytes'], st['logical_admitted_bytes'], 'a zeroed over-read counter passed the reconciliation invariant')


if __name__ == '__main__':
    unittest.main()

"""Streaming prefill (item 1) on the frozen tiny fixture-v2 store: `--prefill-mode stream` must be a pure performance
change. Needs mlx (the dogfood env) and opts in with PULSAR_REPLAY_TEST=1, like test_glm53_flash_replay_trace: it
imports mlx, which would break the `mlx not imported` assertions of the other modules when everything runs in one
`unittest discover` process. Skipped otherwise.

Controls: (1) every fixture call that MLX computes consistently is BIT-identical between prefill_mode 'store' and
'stream', across the multi-wave schedule and on a hand-built single-wave multi-token call (the branch that skips the
mask multiply); (2) a multi-token stream call leaves the store's residency completely untouched (slot_of, pending,
free, expert_to_slot, hits, misses, evictions) while stream_waves / stream_experts / the stream byte counters record
what actually ran, and a 1-token call in the same store still fills slots as before; (3) the policy counts (_counts,
_touch, _accesses) after the schedule are exactly the store-mode counts, so decode's LFU victims stay informed;
(4) the stream byte accounting reconciles (requested - overread == experts x expert_bytes); (5) a wave shorter than
SORTED_GATHER_MIN_EXPERTS asks for the plain gather kernel; (6) the mode is refused for an unknown value and for a
non-contiguous (hash-ordered) layout, and 'store' is the default.

Why (1) excludes the fixture's calls of 64 or more (token, k) rows: those take mx.gather_qmm's sorted-index kernel,
which in MLX 0.32.2 does not agree with the plain kernel on a stack of fewer than 64 experts. This fixture's capacity
is 6, so in those calls the SLOT path is itself on the inconsistent branch while the stream path (correctly) is not,
and the two cannot agree. The accepted Studio configuration has capacity 100, where the slot path is on the
consistent branch and the whole real prefill is bit-identical - which is what the campaign measures."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOGFOOD = ROOT / 'scripts/research/glm53_flash/dogfood'
sys.path.insert(0, str(ROOT))
import importlib.util  # noqa: E402
HAVE_MLX = importlib.util.find_spec('mlx') is not None and os.environ.get('PULSAR_REPLAY_TEST') == '1'

FIXTURE_V2 = ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v2/fixtures.json'
SINGLE_WAVE_CALL = [[0, 1, 2, 3, 0, 1, 2, 3], [1, 2, 3, 0, 1, 2, 3, 0]]   # 2 tokens over 4 experts: one wave at capacity 6
SORT_THRESHOLD = 64        # PulsarSwitchGLU._experts sorts at this many (token, k) rows


def raw(y):
    """The array's bits as numpy (bf16 has no numpy dtype, so it is compared as its uint16 view)."""
    import mlx.core as mx
    import numpy as np

    return np.array(y.view(mx.uint16) if y.dtype == mx.bfloat16 else y)


@unittest.skipUnless(HAVE_MLX, 'mlx not installed or PULSAR_REPLAY_TEST != 1')
class StreamPrefill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'scripts/research/tests'))
        from test_glm53_flash_replay_trace import write_store   # the same contiguous tiny store the replay control uses
        cls.write_store = staticmethod(write_store)
        fx = json.loads(FIXTURE_V2.read_bytes())
        cls.runtime = fx['runtime']; cls.cases = fx['cases']
        cls.dir = Path(tempfile.mkdtemp(prefix='stream-prefill-'))
        cls.stores = {}
        for case in cls.cases:
            d = cls.dir / case['fixture_id']; d.mkdir()
            cls.stores[case['fixture_id']] = write_store(case, d)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def module(self, case, prefill_mode):
        sys.path.insert(0, str(DOGFOOD))
        import pulsar_slot_store as pss

        cfg = case['config']; q = (cfg['group_size'], cfg['bits'], 'affine')
        store = pss.PulsarSlotStore(str(self.stores[case['fixture_id']]), case['budget_bytes'], 0, decay=case['policy']['decay'],
                                    decay_every=case['policy']['decay_every'], warm_start=False, coalesce_gap_experts=2,
                                    read_chunk_bytes=self.runtime['read_chunk_bytes'], prefill_mode=prefill_mode)
        store.force_cold = True
        return store, pss.PulsarSwitchGLU(store, 0, q, q, q)

    def call(self, module, case, token_rows):
        import mlx.core as mx

        x = mx.array([[case['x'][t] for t in token_rows]], dtype=mx.float32)
        idx = mx.array([[case['indices'][t] for t in token_rows]], dtype=mx.int32)
        y = module(x, idx); mx.eval(y)
        return y

    def call_indices(self, module, case, rows, indices):
        import mlx.core as mx

        x = mx.array([[case['x'][t] for t in rows]], dtype=mx.float32)
        y = module(x, mx.array([indices], dtype=mx.int32)); mx.eval(y)
        return y

    def run_schedule(self, case, prefill_mode):
        store, module = self.module(case, prefill_mode)
        outs = [raw(self.call(module, case, call['tokens'])) for call in case['schedule']]
        return store, module, outs

    # --- (1) identity ---------------------------------------------------------------------
    def test_stream_prefill_is_bit_identical_to_store_prefill(self):
        import numpy as np

        for case in self.cases:
            with self.subTest(case['fixture_id']):
                _, _, a = self.run_schedule(case, 'store')
                _, _, b = self.run_schedule(case, 'stream')
                self.assertEqual(len(a), len(b))
                compared = multi_token = 0
                for i, (u, v) in enumerate(zip(a, b)):
                    rows = len(case['schedule'][i]['tokens']) * len(case['indices'][0])
                    if rows >= SORT_THRESHOLD:
                        continue                       # see the module docstring: MLX itself is not consistent here
                    self.assertEqual(u.shape, v.shape, i)
                    self.assertTrue(np.array_equal(u, v), f'call {i} of {case["fixture_id"]} differs')
                    compared += 1
                    multi_token += len(case['schedule'][i]['tokens']) > 1
                self.assertGreater(compared, 0); self.assertGreater(multi_token, 0, 'no multi-token call compared')

    def test_single_wave_multi_token_call_is_bit_identical(self):
        """The one-wave branch skips the mask multiply in both modes; the fixture schedule only reaches the two-wave one."""
        import numpy as np

        for case in self.cases:
            with self.subTest(case['fixture_id']):
                store_a, mod_a = self.module(case, 'store')
                store_b, mod_b = self.module(case, 'stream')
                self.assertLess(len(SINGLE_WAVE_CALL) * len(SINGLE_WAVE_CALL[0]), SORT_THRESHOLD)
                a = raw(self.call_indices(mod_a, case, [0, 1], SINGLE_WAVE_CALL))
                b = raw(self.call_indices(mod_b, case, [0, 1], SINGLE_WAVE_CALL))
                self.assertTrue(np.array_equal(a, b), case['fixture_id'])
                self.assertEqual(store_b.stats()['stream_waves'], 1, 'the call must have been one wave')
                self.assertEqual(store_b.stats()['stream_experts'], 4)
                self.assertGreater(store_a.stats()['waves'], 0)

    # --- (2) residency --------------------------------------------------------------------
    def test_stream_call_leaves_the_store_untouched_and_decode_still_fills(self):
        case = self.cases[0]
        store, module = self.module(case, 'stream')
        tokens = case['schedule'][0]['tokens']
        self.assertGreater(len(tokens), 1)
        self.call(module, case, tokens)
        L = store._layers[0]; st = store.stats()
        self.assertEqual(store.slot_of(0), {}); self.assertEqual(L.pending, {})
        self.assertEqual(L.free, list(range(store.capacity)))
        self.assertTrue((L.expert_to_slot == -1).all())
        self.assertEqual((st['hits'], st['misses'], st['evictions'], st['waves'], st['resident_experts']), (0, 0, 0, 0, 0))
        self.assertEqual(st['read_bytes'], 0); self.assertEqual(st['requested_read_bytes'], 0)
        uniq = sorted({e for t in tokens for e in case['indices'][t]})
        expected_waves = -(-len(uniq) // store.capacity)
        self.assertEqual(st['stream_waves'], expected_waves); self.assertGreater(expected_waves, 1)
        self.assertEqual(st['stream_experts'], len(uniq))
        self.assertEqual(st['prefill_mode'], 'stream')
        # a 1-token call in the SAME store takes the slot path exactly as before
        self.call(module, case, [case['schedule'][3]['tokens'][0]])
        after = store.stats()
        self.assertGreater(after['misses'], 0); self.assertGreater(after['waves'], 0)
        self.assertGreater(len(store.slot_of(0)), 0)
        self.assertEqual(after['stream_waves'], st['stream_waves'], 'a 1-token call must not stream')
        self.assertEqual(after['read_bytes'], after['misses'] * after['expert_bytes'])

    # --- (3) policy counts ----------------------------------------------------------------
    def test_policy_counts_match_store_mode(self):
        for case in self.cases:
            with self.subTest(case['fixture_id']):
                a, _, _ = self.run_schedule(case, 'store')
                b, _, _ = self.run_schedule(case, 'stream')
                self.assertEqual(a._counts, b._counts)
                self.assertEqual(a._touch, b._touch)
                self.assertEqual(a.stats()['accesses'], b.stats()['accesses'])
                self.assertGreater(b.stats()['accesses'], 0)

    # --- (4) byte accounting --------------------------------------------------------------
    def test_stream_byte_accounting_reconciles(self):
        case = self.cases[0]
        store, _, _ = self.run_schedule(case, 'stream')
        st = store.stats()
        self.assertEqual(st['stream_requested_bytes'] - st['stream_overread_bytes'], st['stream_experts'] * st['expert_bytes'])
        self.assertGreater(st['stream_requested_bytes'], 0)
        self.assertEqual(st['requested_read_bytes'] - st['overread_bytes'] + st['hot_copy_bytes'], st['logical_admitted_bytes'])

    # --- (5) the sorted-gather floor --------------------------------------------------------
    def test_short_wave_takes_the_plain_gather_kernel(self):
        """MLX 0.32's sorted-index gather_qmm does not agree with the plain kernel on a stack of fewer than 64 experts
        (measured on the Studio: with the wave split at capacity 100, the trailing wave of every multi-wave layer
        differed on every row it owned). The slot path is always `capacity` rows; a streaming wave is not, so the
        stream path must ask for the plain kernel below the floor. Recorded by intercepting mx.gather_qmm."""
        import mlx.core as mx
        sys.path.insert(0, str(DOGFOOD))
        import pulsar_slot_store as pss

        self.assertEqual(pss.SORTED_GATHER_MIN_EXPERTS, 64)
        case = self.cases[0]
        store, module = self.module(case, 'stream')
        seen = []
        real = mx.gather_qmm

        def spy(*a, **kw):
            seen.append(bool(kw.get('sorted_indices')))
            return real(*a, **kw)

        tokens = case['schedule'][1]['tokens']                       # 8 tokens -> 64 (token, k) rows: slots.size >= 64
        uniq = sorted({e for t in tokens for e in case['indices'][t]})
        self.assertGreaterEqual(len(tokens) * len(case['indices'][0]), 64)
        self.assertLess(store.capacity, pss.SORTED_GATHER_MIN_EXPERTS)
        mx.gather_qmm = spy
        try:
            self.call(module, case, tokens)
        finally:
            mx.gather_qmm = real
        self.assertGreater(len(seen), 0)
        self.assertFalse(any(seen), 'a wave under the floor asked for the sorted gather kernel')
        self.assertEqual(store.stats()['stream_experts'], len(uniq))

    # --- (6) refusals and the default -----------------------------------------------------
    def test_mode_is_validated_and_defaults_to_store(self):
        case = self.cases[0]
        sys.path.insert(0, str(DOGFOOD))
        import pulsar_slot_store as pss

        contig = str(self.stores[case['fixture_id']])
        default = pss.PulsarSlotStore(contig, case['budget_bytes'], 0, warm_start=False)
        self.assertEqual(default.prefill_mode, 'store'); self.assertEqual(default.stats()['prefill_mode'], 'store')
        with self.assertRaises(ValueError) as cm:
            pss.PulsarSlotStore(contig, case['budget_bytes'], 0, warm_start=False, prefill_mode='streaming')
        self.assertIn('PREFILL_MODE', str(cm.exception))
        hashdir = self.dir / case['fixture_id'] / 'hash'      # write_store leaves the hash-ordered store beside the contiguous one
        with self.assertRaises(ValueError) as cm:
            pss.PulsarSlotStore(str(hashdir), case['budget_bytes'], 0, warm_start=False, prefill_mode='stream')
        self.assertIn('STREAM_PREFILL_REQUIRES_CONTIGUOUS_LAYOUT', str(cm.exception))


if __name__ == '__main__':
    unittest.main()

"""Streaming prefill, corrections 1 and 4 of the item-1 run card: OBSERVATION IS NOT ADMISSION, and the dispatch rule
is by the call's token count - not by "phase".

Correction 1 (PulsarSlotStore.count_only): a streamed prefill must not call touch_wave. count_only advances the LFU
counts with exactly touch_wave's access order and decay schedule (same global `_accesses` ordinal, decay on the same
`_accesses % decay_every == 0` boundaries with the same factor) and mutates nothing else - no slot_of, pending, free,
expert_to_slot or slot tensor, no hit, miss, eviction or read admission. Its counters (observed_accesses, stream_waves,
stream_experts) are distinct from the admission counters. Covered on empty, partially populated and full stores, with
experts repeated within and across waves, across a decay boundary crossed mid-wave, and over the prefill -> decode
transition (after a streamed prefill the next 1-token call must fill exactly as a cold store would).

Correction 4 (dispatch and baseline preservation): a call whose token count is > 1 takes the stream path; a prefill
chunk of exactly ONE token takes the slot path and fills slots - so a prompt of length k * prefill_step_size + 1
streams its k full chunks and FILLS on its one-token remainder, and a one-token prompt never streams. `store` stays
the default and every call in store mode takes the slot path. Each test records which path every call actually took
by intercepting store.stream_wave / store.touch_wave, rather than inferring it from counters.

Needs mlx and opts in with PULSAR_REPLAY_TEST=1, exactly like test_glm53_flash_stream_prefill (importing mlx in the
shared `unittest discover` process breaks the other modules' `mlx not imported` assertions). Skipped otherwise.
"""
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


@unittest.skipUnless(HAVE_MLX, 'mlx not installed or PULSAR_REPLAY_TEST != 1')
class StreamPrefillPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'scripts/research/tests'))
        from test_glm53_flash_replay_trace import write_store

        fx = json.loads(FIXTURE_V2.read_bytes())
        cls.runtime = fx['runtime']
        cls.case = next(c for c in fx['cases'] if c['fixture_id'] == 'slot2-4bit-g32-f32')
        cls.dir = Path(tempfile.mkdtemp(prefix='stream-prefill-policy-'))
        cls.contig = write_store(cls.case, cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    # --- harness ---------------------------------------------------------------------------
    def module(self, prefill_mode='stream'):
        sys.path.insert(0, str(DOGFOOD))
        import pulsar_slot_store as pss

        cfg = self.case['config']
        q = (cfg['group_size'], cfg['bits'], 'affine')
        store = pss.PulsarSlotStore(str(self.contig), self.case['budget_bytes'], 0, decay=self.case['policy']['decay'],
                                    decay_every=self.case['policy']['decay_every'], warm_start=False, coalesce_gap_experts=2,
                                    read_chunk_bytes=self.runtime['read_chunk_bytes'], prefill_mode=prefill_mode)
        store.force_cold = True
        return store, pss.PulsarSwitchGLU(store, 0, q, q, q)

    def call(self, module, rows, indices=None):
        """One forward with len(rows) tokens. `indices` overrides the fixture's routing (as [token][k])."""
        import mlx.core as mx

        x = mx.array([[self.case['x'][t] for t in rows]], dtype=mx.float32)
        idx = indices if indices is not None else [self.case['indices'][t] for t in rows]
        y = module(x, mx.array([idx], dtype=mx.int32))
        mx.eval(y)
        return y

    def record_paths(self, store):
        """Record the path of every call: 'stream' per stream_wave, 'slot' per touch_wave. Returns the live list."""
        seen = []
        real_stream, real_touch = store.stream_wave, store.touch_wave

        def stream_spy(lid, wave):
            seen.append(('stream', lid, list(wave)))
            return real_stream(lid, wave)

        def touch_spy(lid, wave):
            seen.append(('slot', lid, list(wave)))
            return real_touch(lid, wave)

        store.stream_wave, store.touch_wave = stream_spy, touch_spy
        return seen

    def residency(self, store):
        """Everything count_only must not touch."""
        import numpy as np

        L = store._layers[0]
        st = store.stats()
        return (dict(L.slot_of), dict(L.pending), list(L.free), np.array(L.expert_to_slot).tolist(),
                st['hits'], st['misses'], st['evictions'], st['waves'], st['read_bytes'],
                st['requested_read_bytes'], st['resident_experts'], st['cold_reads'])

    def prime(self, module, state):
        """Drive the store into the requested residency state with 1-token (slot-path) calls only."""
        if state == 'empty':
            return
        if state == 'partial':                                   # three distinct experts, one token
            self.call(module, [0], [[2, 2, 2, 5, 5, 9, 9, 9]])
            return
        if state == 'full':                                      # capacity distinct experts, one token per wave
            self.call(module, [0], [[0, 1, 2, 3, 4, 5, 0, 1]])
            self.call(module, [1], [[0, 1, 2, 3, 4, 5, 0, 1]])
            return
        raise AssertionError(state)

    # --- correction 1: counts ---------------------------------------------------------------
    def test_count_only_matches_touch_wave_counts_on_empty_partial_and_full_stores(self):
        waves = [[1, 4, 7], [0, 1, 2, 3, 4, 5], [7, 9]]          # repeats within (none) and across (1, 4, 7) waves
        for state in ('empty', 'partial', 'full'):
            with self.subTest(state=state):
                a_store, a_mod = self.module('stream')
                b_store, b_mod = self.module('stream')
                self.prime(a_mod, state)
                self.prime(b_mod, state)
                self.assertEqual(len(a_store.slot_of(0)), len(b_store.slot_of(0)))
                if state == 'full':
                    self.assertEqual(len(a_store.slot_of(0)), a_store.capacity)
                elif state == 'partial':
                    self.assertEqual(len(a_store.slot_of(0)), 3)
                before = a_store.stats()['accesses']
                for w in waves:
                    a_store.count_only(0, w)
                    b_store.fill(0, b_store.touch_wave(0, w))    # the full legal slot cycle; only the counts are compared
                self.assertEqual(a_store._counts, b_store._counts)
                self.assertEqual(a_store._touch, b_store._touch)
                self.assertEqual(a_store.stats()['accesses'], b_store.stats()['accesses'])
                self.assertEqual(a_store.stats()['accesses'] - before, sum(len(w) for w in waves))
                self.assertEqual(a_store.stats()['observed_accesses'], sum(len(w) for w in waves))
                self.assertEqual(b_store.stats()['observed_accesses'], 0)

    def test_count_only_mutates_nothing_but_the_counts(self):
        for state in ('empty', 'partial', 'full'):
            with self.subTest(state=state):
                store, mod = self.module('stream')
                self.prime(mod, state)
                before = self.residency(store)
                tensors_before = [t.tolist() for parts in store.tensors(0).values() for t in parts]
                store.count_only(0, [0, 3, 6, 9])
                self.assertEqual(self.residency(store), before)
                self.assertEqual([t.tolist() for parts in store.tensors(0).values() for t in parts], tensors_before)
                st = store.stats()
                self.assertEqual(st['observed_accesses'], 4)
                self.assertEqual(st['stream_waves'], 0)          # count_only alone is not a streamed wave

    def test_repeated_experts_within_and_across_waves(self):
        """An expert repeated inside one wave is counted once by the caller's `uniq`; repeated across waves it is
        counted once per wave - identical under count_only and touch_wave."""
        a_store, _ = self.module('stream')
        b_store, _ = self.module('stream')
        for w in ([2, 5], [2, 5], [2, 7], [2]):
            a_store.count_only(0, w)
            b_store.fill(0, b_store.touch_wave(0, w))
        self.assertEqual(a_store._counts, b_store._counts)
        self.assertEqual(a_store._touch, b_store._touch)
        self.assertEqual(a_store.stats()['accesses'], 7)
        self.assertEqual(a_store._counts[(0, 5)], b_store._counts[(0, 5)])
        self.assertGreater(a_store._counts[(0, 2)], a_store._counts[(0, 7)])

    def test_decay_boundary_crossed_mid_wave_matches_touch_wave(self):
        """decay_every is 5 in the fixture, so a 6-expert observation from a fresh store crosses the boundary inside
        the wave: the first five counts decay by 0.5, the sixth does not."""
        a_store, _ = self.module('stream')
        b_store, _ = self.module('stream')
        self.assertEqual(a_store.decay_every, 5)
        self.assertEqual(a_store.decay, 0.5)
        wave = [0, 1, 2, 3, 4, 5]
        a_store.count_only(0, wave)
        b_store.fill(0, b_store.touch_wave(0, wave))
        self.assertEqual(a_store.stats()['accesses'] % a_store.decay_every, 1)   # the boundary is behind us, mid-wave
        self.assertEqual(a_store._counts, b_store._counts)
        self.assertEqual([a_store._counts[(0, j)] for j in wave], [0.5, 0.5, 0.5, 0.5, 0.5, 1.0])
        for extra in ([6, 7, 8, 9], [0, 6]):                     # keep crossing boundaries from a non-zero ordinal
            a_store.count_only(0, extra)
            b_store.fill(0, b_store.touch_wave(0, extra))
        self.assertEqual(a_store._counts, b_store._counts)
        self.assertEqual(a_store._touch, b_store._touch)

    def test_prefill_to_decode_transition_fills_like_a_cold_store(self):
        """After a streamed prefill: pending empty, slot_of unchanged, no false residency - and the next 1-token call
        must admit exactly what the same call admits in a store that never saw the prefill."""
        import numpy as np

        streamed, s_mod = self.module('stream')
        cold, c_mod = self.module('stream')
        decode_row = [[3, 3, 8, 8, 11, 11, 3, 8]]                # 3 distinct experts, one token -> one slot wave

        self.call(s_mod, [0, 1, 2, 3])                           # a 4-token prefill chunk: streamed
        L = streamed._layers[0]
        self.assertEqual(streamed.slot_of(0), {})
        self.assertEqual(L.pending, {})
        self.assertEqual(L.free, list(range(streamed.capacity)))
        self.assertTrue((np.array(L.expert_to_slot) == -1).all(), 'false residency after a streamed prefill')
        self.assertGreater(streamed.stats()['stream_waves'], 0)
        self.assertEqual(streamed.stats()['misses'], 0)
        self.assertEqual(streamed.stats()['read_bytes'], 0)

        paths_s, paths_c = self.record_paths(streamed), self.record_paths(cold)
        self.call(s_mod, [4], decode_row)
        self.call(c_mod, [4], decode_row)
        self.assertEqual([p[0] for p in paths_s], ['slot'], 'the 1-token call after a streamed prefill must fill')
        self.assertEqual([p[0] for p in paths_s], [p[0] for p in paths_c])
        self.assertEqual([p[2] for p in paths_s], [p[2] for p in paths_c])
        a, b = streamed.stats(), cold.stats()
        for k in ('misses', 'hits', 'evictions', 'read_bytes', 'cold_reads', 'resident_experts', 'waves'):
            self.assertEqual(a[k], b[k], f'{k} differs from a cold store')
        self.assertEqual(streamed.slot_of(0), cold.slot_of(0))
        self.assertEqual(a['misses'], 3)
        self.assertGreater(a['observed_accesses'], b['observed_accesses'])   # only the streamed one observed a prefill

    # --- correction 4: the dispatch rule ------------------------------------------------------
    def test_one_token_prompt_takes_the_slot_path(self):
        store, mod = self.module('stream')
        paths = self.record_paths(store)
        self.call(mod, [0])
        self.assertTrue(paths and all(p[0] == 'slot' for p in paths), paths)
        self.assertEqual(store.stats()['stream_waves'], 0)
        self.assertEqual(store.stats()['observed_accesses'], 0)
        self.assertGreater(store.stats()['misses'], 0)
        self.assertGreater(len(store.slot_of(0)), 0)

    def test_two_token_prompt_takes_the_stream_path(self):
        store, mod = self.module('stream')
        paths = self.record_paths(store)
        self.call(mod, [0, 1])
        self.assertTrue(paths and all(p[0] == 'stream' for p in paths), paths)
        self.assertGreater(store.stats()['stream_waves'], 0)
        self.assertEqual(store.stats()['misses'], 0)
        self.assertEqual(store.slot_of(0), {})

    def test_chunk_boundary_with_a_one_token_remainder(self):
        """A prompt of k * prefill_step_size + 1 tokens, chunked the way the runner chunks it: the k full chunks
        stream, the one-token remainder takes the slot path and fills."""
        step, k = 4, 2
        prompt = list(range(step * k + 1))
        self.assertEqual(len(prompt) % step, 1)
        store, mod = self.module('stream')
        paths = self.record_paths(store)
        per_call = []
        for i in range(0, len(prompt), step):
            chunk = prompt[i:i + step]
            before = len(paths)
            self.call(mod, chunk)
            per_call.append((len(chunk), sorted({p[0] for p in paths[before:]})))
        self.assertEqual([n for n, _ in per_call], [4, 4, 1])
        self.assertEqual([kinds for _, kinds in per_call], [['stream'], ['stream'], ['slot']])
        st = store.stats()
        self.assertGreater(st['stream_waves'], 0)
        self.assertGreater(st['misses'], 0, 'the one-token remainder must have filled slots')
        self.assertGreater(len(store.slot_of(0)), 0)
        self.assertEqual(st['read_bytes'], st['misses'] * st['expert_bytes'])

    def test_store_mode_is_the_default_and_never_streams(self):
        store, mod = self.module('store')
        self.assertEqual(store.prefill_mode, 'store')
        paths = self.record_paths(store)
        for rows in ([0], [0, 1], [0, 1, 2, 3, 4]):
            self.call(mod, rows)
        self.assertTrue(paths and all(p[0] == 'slot' for p in paths), paths)
        st = store.stats()
        self.assertEqual((st['stream_waves'], st['stream_experts'], st['observed_accesses']), (0, 0, 0))
        self.assertEqual(st['stream_requested_bytes'], 0)
        self.assertGreater(st['misses'], 0)


if __name__ == '__main__':
    unittest.main()

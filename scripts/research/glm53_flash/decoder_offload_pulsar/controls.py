"""PulsarExpertStore against the LFU-with-decay policy model and the graph-18 values, in the successor child.

The store class is the repository's own runtime file (read through the manifest, executed as a module in a fresh
namespace); the module is the admitted OffloadedSwitchGLU of graph 18; the on-disk store is written into the child's
work directory from the frozen arrays. After every call: outputs vs reference, stats vs the LFU model; then the warm
state is saved and a fresh store must re-admit exactly the model's set. Structural controls mutate the store text.
Graph 22: every case runs twice, under cache_clear_threshold_bytes=0 (upstream-equivalent: the store's cache_clears must
equal the model's eviction_events, i.e. one clear per evicting get) and under the fixture's bound (the tiny fixtures
never reach it: cache_clears must be 0); actual mx.clear_cache() invocations are counted through a wrapper and must
equal the store's counter; the two allocator-cache mutants are killed by those counts.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-offload-pulsar-v2/fixtures.json'
STORE = 'scripts/research/glm53_flash/dogfood/pulsar_expert_store.py'


def emit(event, **values):
    print(json.dumps({'event': event, **values}, sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def max_error(a, b):
    if type(a) is list:
        if type(b) is not list or len(a) != len(b):
            return float('inf')
        return max((max_error(x, y) for x, y in zip(a, b)), default=0.0)
    if not (math.isfinite(a) and math.isfinite(b)):
        return float('inf')
    return abs(a - b)


def load_store_class(text, name='PulsarExpertStore'):
    ns = {'__name__': 'pulsar_expert_store_verified'}
    exec(compile(text, 'pulsar-expert-store', 'exec'), ns)
    return ns[name]


def run(context, backend, mx, nn, np, ffn_source, moe_source, sparse_source, quantized_source, offload_source, offload_controls, pulsar_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    store_raw = context.read_verified(root / STORE); store_text = store_raw.decode()
    offload_raw = context.read_verified(root / offload_source.OFFLOAD); switch_raw = context.read_verified(root / moe_source.SWITCH)
    tol = fixture['tolerances']; matrix = fixture['expected_kill_matrix']; cache_bound = int(fixture['cache_bound_bytes'])
    cases = {c['fixture_id']: c for c in fixture['cases']}; expected = fixture['expected']
    work = context.roots['work'] / 'pulsar'
    emit('pulsar_binding', fixture_sha256=digest(raw), store_sha256=digest(store_raw), backend=backend, actual_default_device=str(mx.default_device()), store_root='work/pulsar')

    def admitted():
        ffn = ffn_source.load(root, mx, nn)
        bound = offload_source.load(offload_raw, switch_raw, mx, nn, np, ffn_source, moe_source)
        return bound, ffn.namespace['ClampedSwiGLU'], load_store_class(store_text)

    def make(bound, StoreClass, case, directory, activation, warm_start, threshold):
        cfg = case['config']; q = (cfg['group_size'], cfg['bits'], 'affine')
        store = StoreClass(str(directory), case['budget_bytes'], 0, decay=case['policy']['decay'], decay_every=case['policy']['decay_every'], warm_start=warm_start,
                           cache_clear_threshold_bytes=threshold)
        module = bound.module_namespace['OffloadedSwitchGLU'](store, case['layer_id'], q, q, q, activation=activation(cfg['swiglu_limit']))
        return store, module

    def evaluate_at(bound, StoreClass, activation, case, directory, threshold):
        import os
        ws = directory / 'pulsar-warm-state.json'
        if ws.exists():
            os.remove(ws)
        store, module = make(bound, StoreClass, case, directory, activation, warm_start=False, threshold=threshold)
        exp = expected[case['fixture_id']]['calls']
        rows = []; cache_after_evicting_calls = []; invoked = {'clear_cache': 0}
        real_clear_cache = mx.clear_cache

        def counting_clear_cache():
            invoked['clear_cache'] += 1
            real_clear_cache()
        mx.clear_cache = counting_clear_cache   # the store calls it through the same module object
        try:
            for call, e in zip(case['schedule'], exp):
                ts = call['tokens']
                x = mx.array([[case['x'][t] for t in ts]], dtype=mx.float32); inds = mx.array([[case['indices'][t] for t in ts]], dtype=mx.int32)
                y = module(x, inds); mx.eval(y); st = store.stats()
                if e['evicted']:
                    cache_after_evicting_calls.append(int(mx.get_cache_memory()))
                rows.append({'tokens': ts, 'output': y[0].tolist(), 'stats': {k: st[k] for k in ('hits', 'misses', 'evictions', 'resident_experts', 'resident_bytes')},
                             'cache_clears': st['cache_clears'], 'eviction_events': e['eviction_events']})
        finally:
            mx.clear_cache = real_clear_cache
        value_err = max(max_error(r['output'], e['outputs']) for r, e in zip(rows, exp))
        policy_ok = all(r['stats'] == e['stats'] for r, e in zip(rows, exp))
        resident_ok = sorted(j for (_, j) in store._resident) == exp[-1]['resident_set']
        eviction_events = exp[-1]['eviction_events']
        clears = store.stats()['cache_clears']
        cache_ok = clears == invoked['clear_cache'] and (clears == eviction_events if threshold == 0 else clears == 0)
        cache = {'threshold': threshold, 'cache_clears': clears, 'clear_cache_invocations': invoked['clear_cache'], 'eviction_events': eviction_events,
                 'cache_bytes_after_evicting_calls': cache_after_evicting_calls, 'cache_ok': cache_ok}
        store.save_warm_state()
        fresh, _ = make(bound, StoreClass, case, directory, activation, warm_start=True, threshold=threshold)
        warm = sorted(j for (_, j) in fresh._resident)
        warm_ok = warm == sorted(expected[case['fixture_id']]['warm_state']['admitted_on_restart']) and fresh.stats()['warm_admitted'] == len(warm)
        return rows, value_err, policy_ok, resident_ok, warm, warm_ok, cache

    def evaluate(bound, StoreClass, activation, case, directory):
        """Both threshold passes: upstream-equivalent (0) and the fixture's bound; every check must hold under both."""
        rows, value_err, policy_ok, resident_ok, warm, warm_ok, cache0 = evaluate_at(bound, StoreClass, activation, case, directory, 0)
        rows_b, value_err_b, policy_ok_b, resident_ok_b, warm_b, warm_ok_b, cache_b = evaluate_at(bound, StoreClass, activation, case, directory, cache_bound)
        return (rows, max(value_err, value_err_b), policy_ok and policy_ok_b, resident_ok and resident_ok_b, warm, warm_ok and warm_ok_b and warm_b == warm,
                {'threshold_0': cache0, 'bounded': cache_b, 'cache_ok': cache0['cache_ok'] and cache_b['cache_ok']})

    observations, control_rows = [], []

    class Pulsar(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for fid, case in cases.items():
                got = pulsar_oracle.run(case)
                self.assertEqual(got, {k: v for k, v in expected[fid].items() if k in got}, fid)  # the fixture adds LRU comparison keys
            emit('frozen_reference', status='RECOMPUTED_EQUAL', cases=len(cases))

        def test_lfu_store(self):
            bound, activation, StoreClass = admitted()
            for fid, case in cases.items():
                directory = work / fid; files = offload_controls.write_store(case, directory, mx)
                rows, value_err, policy_ok, resident_ok, warm, warm_ok, cache = evaluate(bound, StoreClass, activation, case, directory)
                exp = expected[fid]
                row = {'fixture_id': fid, 'store_files': files, 'max_value_error': value_err, 'policy_matches_lfu_model': policy_ok, 'final_resident_matches': resident_ok,
                       'final_stats': rows[-1]['stats'], 'lru_final_stats_for_reference': exp['lru_final_stats'], 'lru_differs_at_calls': exp['lru_differs_at_calls'],
                       'warm_readmitted': warm, 'warm_expected': exp['warm_state']['admitted_on_restart'], 'warm_ok': warm_ok, 'cache': cache, 'contract': bound.contract,
                       'pass': value_err <= tol['output'] and policy_ok and resident_ok and warm_ok and cache['cache_ok']}
                observations.append(row); emit('pulsar_observation', **{k: v for k, v in row.items() if k != 'contract'})
                self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k != 'contract'}))

        def test_structural_controls(self):
            recipes = [('decay-disabled', '                self._counts[k] *= self.decay\n', '                self._counts[k] *= 1.0\n'),
                       ('tie-break-most-recent', '        return (self._counts.get(key, 0.0), self._touch.get(key, 0))\n', '        return (self._counts.get(key, 0.0), -self._touch.get(key, 0))\n'),
                       ('warm-state-ignored', '            self._warm_admitted = self._admit_warm_state()\n', '            self._warm_admitted = 0\n'),
                       ('clear-always', '        if evicted and self._cache_over_threshold(mx):\n', '        if evicted:\n'),
                       ('never-clear', '        if evicted and self._cache_over_threshold(mx):\n', '        if False:\n')]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            bound, activation, _ = admitted()
            for label, before, after in recipes:
                self.assertEqual(store_text.count(before), 1, label)
                MutantClass = load_store_class(store_text.replace(before, after, 1))
                results = []
                for expected_cell, fid in zip(matrix['matrix'][label], matrix['fixtures']):
                    case = cases[fid]; directory = work / fid
                    try:
                        rows, value_err, policy_ok, resident_ok, warm, warm_ok, cache = evaluate(bound, MutantClass, activation, case, directory)
                        observed = 'INACTIVE' if (policy_ok and warm_ok and cache['cache_ok'] and value_err <= tol['output']) else 'KILL'
                        reason = 'policy-mismatch' if not policy_ok else ('warm-mismatch' if not warm_ok else ('cache-clears-mismatch' if not cache['cache_ok'] else 'value'))
                    except (RuntimeError, ValueError, TypeError, KeyError, IndexError) as exc:
                        observed, reason = 'KILL', 'rejected:' + type(exc).__name__
                    results.append({'fixture_id': fid, 'observed': observed, 'expected_cell': expected_cell, 'reason': reason, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                control_rows.append(row); emit('pulsar_control', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Pulsar)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('pulsar_summary', backend=backend, observations=[{k: v for k, v in o.items() if k != 'contract'} for o in observations], controls=control_rows,
         scope='PULSAR_EXPERT_STORE_LFU_DECAY_WARM_STATE_BOUNDED_CACHE_CLEAR_OVER_FROZEN_STORE; policy vs stdlib model; values vs graph-18 reference; cache clears vs eviction events under threshold 0 and the fixture bound; no throughput claim')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

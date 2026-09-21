"""Expert offload path against the value reference and the LRU store-policy model, in the successor child.

The on-disk store is written into the child's work directory from the frozen
quantized arrays in the repack file format; a byte-budgeted ExpertStore serves
it (mmap) and an OffloadedSwitchGLU with the admitted ClampedSwiGLU computes
only the selected experts. The frozen schedule drives decode-like single-token
calls (per-expert get with LRU eviction and refetch) and one bulk call
(get_all). After every call: outputs vs the reference, store.stats() and the
resident order vs the LRU model, and the offloaded output vs the resident
quantized SwitchGLU of graph 15. Mutants of the store and of the module are
decided against the matrix frozen from reference variants.
"""
import ast
import hashlib
import json
import math
import resource
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-offload-v1/fixtures.json'


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


def write_store(case, directory, mx):
    """The repack format: experts/layer_NNNN.safetensors with e{j}.{proj}.{weight,scales,biases}; offload_index.json."""
    (directory / 'experts').mkdir(parents=True, exist_ok=True)
    layer = {}
    for p in ('gate', 'up', 'down'):
        for j, pack in enumerate(case['quantized'][p]):
            layer[f'e{j}.{p}_proj.weight'] = mx.array(pack['words'], dtype=mx.uint32)
            layer[f'e{j}.{p}_proj.scales'] = mx.array(pack['scales'], dtype=mx.float32)
            layer[f'e{j}.{p}_proj.biases'] = mx.array(pack['biases'], dtype=mx.float32)
    mx.eval(list(layer.values()))
    mx.save_safetensors(str(directory / 'experts' / f"layer_{case['layer_id']:04d}.safetensors"), layer, metadata={'format': 'mlx'})
    (directory / 'offload_index.json').write_text(json.dumps({'layers': [case['layer_id']], 'num_experts': case['config']['num_experts']}, indent=2))
    return sorted(str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file())


def make_store_and_module(bound, case, directory, mx, activation, budget=None):
    store = bound.store_namespace['ExpertStore'](str(directory), case['budget_bytes'] if budget is None else budget, 0)
    cfg = case['config']; q = (cfg['group_size'], cfg['bits'], 'affine')
    module = bound.module_namespace['OffloadedSwitchGLU'](store, case['layer_id'], q, q, q, activation=activation)
    return store, module


def run_schedule(store, module, case, mx):
    rows = []
    for call in case['schedule']:
        ts = call['tokens']
        x = mx.array([[case['x'][t] for t in ts]], dtype=mx.float32); inds = mx.array([[case['indices'][t] for t in ts]], dtype=mx.int32)
        y = module(x, inds); mx.eval(y)
        st = store.stats()
        rows.append({'tokens': ts, 'output': y[0].tolist(), 'stats': {k: st[k] for k in ('hits', 'misses', 'evictions', 'resident_experts', 'resident_bytes')},
                     'resident_order': [j for (_, j) in store._lru]})
    return rows


def run(context, backend, mx, nn, np, ffn_source, moe_source, sparse_source, quantized_source, quantized_controls, offload_source, offload_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    offload_raw = context.read_verified(root / offload_source.OFFLOAD); switch_raw = context.read_verified(root / moe_source.SWITCH)
    mla_raw = context.read_verified(root / sparse_source.MLA)
    tol = fixture['tolerances']; matrix = fixture['expected_kill_matrix']
    cases = {c['fixture_id']: c for c in fixture['cases']}; expected = fixture['expected']
    work = context.roots['work'] / 'offload'
    emit('offload_binding', fixture_sha256=digest(raw), offload_sha256=digest(offload_raw), switch_sha256=digest(switch_raw), backend=backend,
         actual_default_device=str(mx.default_device()), store_root='work/offload')  # relative: the archive redacts absolute locators

    def admitted():
        ffn = ffn_source.load(root, mx, nn)
        bound = offload_source.load(offload_raw, switch_raw, mx, nn, np, ffn_source, moe_source)
        resident = quantized_source.load(switch_raw, mla_raw, mx, nn, ffn_source, moe_source, sparse_source, ffn.namespace)
        return bound, resident, ffn.namespace['ClampedSwiGLU']

    def evaluate(bound, activation, case, directory):
        store, module = make_store_and_module(bound, case, directory, mx, activation(case['config']['swiglu_limit']))
        rows = run_schedule(store, module, case, mx); exp = expected[case['fixture_id']]['calls']
        value_err = max(max_error(r['output'], e['outputs']) for r, e in zip(rows, exp))
        # the frozen matrix scopes a policy mismatch as hits/misses/evictions/bulk (counts); the resident order is a
        # separate boundary asserted on the unmutated path and reported for mutants
        policy_ok = all(r['stats'] == e['stats'] for r, e in zip(rows, exp))
        order_ok = all(r['resident_order'] == e['resident_order'] for r, e in zip(rows, exp))
        return rows, value_err, policy_ok, order_ok

    observations, mutant_rows = [], []

    class Offload(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for fid, case in cases.items():
                self.assertEqual(offload_oracle.run(case), expected[fid], fid)
            emit('frozen_reference', status='RECOMPUTED_EQUAL', cases=len(cases))

        def test_offloaded_path(self):
            bound, resident, activation = admitted()
            for fid, case in cases.items():
                directory = work / fid
                files = write_store(case, directory, mx)
                rows, value_err, policy_ok, order_ok = evaluate(bound, activation, case, directory)
                exp = expected[fid]['calls']
                # resident quantized SwitchGLU (graph 15) on the same calls
                glu = quantized_controls.build_switch(resident, case, mx)
                vs_resident = 0.0
                for r in rows:
                    ts = r['tokens']
                    y = glu(mx.array([[case['x'][t] for t in ts]], dtype=mx.float32), mx.array([[case['indices'][t] for t in ts]], dtype=mx.int32)); mx.eval(y)
                    vs_resident = max(vs_resident, max_error(r['output'], y[0].tolist()))
                per_call = [{'tokens': r['tokens'], 'bulk_expected': e['bulk'], 'value_error': max_error(r['output'], e['outputs']), 'stats': r['stats'],
                             'stats_expected': e['stats'], 'resident_order': r['resident_order'], 'resident_expected': e['resident_order']} for r, e in zip(rows, exp)]
                row = {'fixture_id': fid, 'store_files': files, 'expert_bytes': expected[fid]['expert_bytes'], 'budget_bytes': case['budget_bytes'],
                       'max_value_error': value_err, 'policy_matches_lru_model': policy_ok, 'resident_order_matches_lru_model': order_ok, 'offloaded_vs_resident_switchglu': vs_resident,
                       'final_stats': rows[-1]['stats'], 'calls': per_call, 'contract': bound.contract,
                       'pass': value_err <= tol['output'] and policy_ok and order_ok}
                observations.append(row); emit('offload_observation', **{k: v for k, v in row.items() if k != 'contract'})
                self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k not in ('contract', 'calls')}))
            with self.assertRaisesRegex(RuntimeError, '(AUTO_BUDGET|RESIDENT_BYTES_ON_DISK)_NOT_ADMITTED'):
                bound.store_namespace['ExpertStore'](str(work / 'offload-4bit-g64'))
            emit('refusal', auto_budget_helpers='REFUSED')

        def test_semantic_mutants(self):
            recipes = [
                ('lru-evicts-most-recent', 'store', '(lid, j), nbytes = self._lru.popitem(last=False)', '(lid, j), nbytes = self._lru.popitem(last=True)'),
                ('lru-no-touch-on-hit', 'store', '            self._lru.move_to_end(key)\n', '            pass\n'),
                ('refetch-after-evict-omitted', 'store', '        self._ensure_loaded(layer_id, j, m)\n', '        pass\n'),
                ('scatter-slot-ignored', 'module', 'out = out.at[mx.array(tok), mx.array(slot)].add(d)', 'out = out.at[mx.array(tok), 0].add(d)'),
                ('expert-rows-misgathered', 'module', 'xr = xf[mx.array(tok)]', 'xr = xf[mx.array(slot)]'),
                ('bulk-threshold-inverted', 'module', 'if len(uniq) * 2 > self.store.num_experts', 'if len(uniq) * 2 <= self.store.num_experts'),
            ]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            bound, _, activation = admitted()
            factor, allowance = matrix['kill_margin_factor'], tol['output']
            for label, target, before, after in recipes:
                text = bound.offload_text if target == 'store' else bound.switch_text
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_OFFLOAD_(SWITCH_)?DIGEST'):
                    offload_source.verify(mutated if target == 'store' else offload_raw, switch_raw if target == 'store' else mutated, ffn_source, moe_source)
                node_name = 'ExpertStore' if target == 'store' else 'OffloadedSwitchGLU'
                node = ffn_source._node(ast.parse(mutated), node_name)
                mutant = type(bound)(**vars(bound))
                if target == 'store':
                    ns = {k: v for k, v in bound.store_namespace.items() if k != 'ExpertStore'}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), 'test-only:ExpertStore', 'exec'), ns); mutant.store_namespace = ns
                else:
                    ns = {k: v for k, v in bound.module_namespace.items() if k != 'OffloadedSwitchGLU'}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), 'test-only:OffloadedSwitchGLU', 'exec'), ns); mutant.module_namespace = ns
                results = []
                for expected_cell, fid in zip(matrix['matrix'][label], matrix['fixtures']):
                    case = cases[fid]; directory = work / fid
                    try:
                        rows, value_err, policy_ok, order_ok = evaluate(mutant, activation, case, directory)
                        if not policy_ok:
                            err, reason = float('inf'), 'policy-mismatch'
                        elif not order_ok:
                            err, reason = value_err, 'value; resident order differs (outside the frozen cell scope)'
                        else:
                            err, reason = value_err, 'value' if value_err != float('inf') else 'nonfinite_or_shape'
                    except (RuntimeError, ValueError, TypeError, IndexError, KeyError) as exc:
                        err, reason = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)[:120]
                    observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                    results.append({'fixture_id': fid, 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason, 'observed': observed,
                                    'expected_cell': expected_cell, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'target': target, 'mutant_sha256': digest(mutated), 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                mutant_rows.append(row); emit('offload_mutant', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Offload)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('offload_summary', backend=backend, observations=[{k: v for k, v in o.items() if k != 'contract'} for o in observations], mutants=mutant_rows,
         scope='EXPERT_OFFLOAD_PATH_OVER_FROZEN_QUANTIZED_STORE; one layer, 4 experts, byte-budgeted LRU with eviction/refetch and the bulk path; no repack of a real checkpoint; no throughput claim')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

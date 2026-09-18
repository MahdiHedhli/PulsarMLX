"""PulsarSlotStore + PulsarSwitchGLU against the stdlib slot model and the graph-18 values, in the successor child.

The runtime file (store + module) is read through the manifest and executed as a module in a fresh namespace; the
activation is the admitted ClampedSwiGLU of graph 9; the on-disk store is written into the work directory from the
frozen arrays. After every call: outputs vs reference (the wave-split call included), stats and the slot map vs the
model; then the warm state is saved and a fresh store must re-admit the model's slot assignment. Structural controls
mutate the runtime text: four policy mutants predicted from oracle variants, three slot mutants recorded by
construction (value or rejection). Graph 29: every case also runs on an expert-contiguous copy of the store written
by repack_v2 (own safetensors writer, verified contiguous) and in forced-cold mode on both layouts, so the memmap,
per-tensor preadv and coalesced-range readers all produce the same values, stats and slot maps; two more structural
mutants (coalesce-offset-wrong, layout-flag-ignored) are killed on those passes. Graph 31: test_fault_injection raises
inside fill at read-done (before the first write), projection-written, before-eval and during mx.eval, at the first
miss and the first eviction of every case: a read-phase fault must leave the model's post-fault stats and slot map and
the retry must reproduce the model's outputs, stats and slot map (never a false hit); a write-phase fault must poison
the store (every later call, and the warm-state save, rejected with STORE_POISONED). Every structural mutant also runs
the fault schedule: the three residency-commit mutants of matrix revision 4 are killed there.
"""
import hashlib
import json
import math
import resource
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-slot-store-v1/fixtures.json'
STORE = 'scripts/research/glm53_flash/dogfood/pulsar_slot_store.py'
REPACK = 'scripts/research/glm53_flash/dogfood/repack_v2.py'


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


def load_runtime(text):
    ns = {'__name__': 'pulsar_slot_store_verified'}
    exec(compile(text, 'pulsar-slot-store', 'exec'), ns)
    return ns['PulsarSlotStore'], ns['PulsarSwitchGLU']


def load_repack(text):
    ns = {'__name__': 'repack_v2_verified'}
    exec(compile(text, 'repack-v2', 'exec'), ns)
    return ns


def run(context, backend, mx, nn, np, ffn_source, offload_controls, slot_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    store_raw = context.read_verified(root / STORE); store_text = store_raw.decode()
    repack_raw = context.read_verified(root / REPACK); repack = load_repack(repack_raw.decode())
    tol = fixture['tolerances']; matrix = fixture['expected_kill_matrix']
    cases = {c['fixture_id']: c for c in fixture['cases']}; expected = fixture['expected']
    work = context.roots['work'] / 'slot'
    emit('slot_binding', fixture_sha256=digest(raw), store_sha256=digest(store_raw), repack_sha256=digest(repack_raw), backend=backend, actual_default_device=str(mx.default_device()), store_root='work/slot')

    def contiguous_copy(case, directory):
        """repack_v2 of the tiny store into <directory>-contig; must verify contiguous while the source must not."""
        import os, shutil
        dst = directory.parent / (directory.name + '-contig')
        if dst.exists():
            shutil.rmtree(dst)
        os.makedirs(dst / 'experts')
        src_file = directory / 'experts' / f"layer_{case['layer_id']:04d}.safetensors"; dst_file = dst / 'experts' / src_file.name
        repack['write_contiguous'](str(src_file), str(dst_file))
        idx = json.loads((directory / 'offload_index.json').read_text()); (dst / 'offload_index.json').write_text(json.dumps({**idx, 'layout': repack['LAYOUT']}))
        return dst, repack['check_contiguous'](str(dst_file)), repack['check_contiguous'](str(src_file))

    def activation_class():
        return ffn_source.load(root, mx, nn).namespace['ClampedSwiGLU']

    def make(StoreClass, ModuleClass, case, directory, activation, warm_start, force_cold=False):
        cfg = case['config']; q = (cfg['group_size'], cfg['bits'], 'affine')
        store = StoreClass(str(directory), case['budget_bytes'], 0, decay=case['policy']['decay'], decay_every=case['policy']['decay_every'], warm_start=warm_start)
        store.force_cold = force_cold
        module = ModuleClass(store, case['layer_id'], q, q, q, activation=activation(cfg['swiglu_limit']))
        return store, module

    def evaluate_one(StoreClass, ModuleClass, activation, case, directory, force_cold):
        import os
        ws = directory / 'pulsar-slot-warm-state.json'
        if ws.exists():
            os.remove(ws)
        store, module = make(StoreClass, ModuleClass, case, directory, activation, warm_start=False, force_cold=force_cold)
        exp = expected[case['fixture_id']]
        rows = []
        for call, e in zip(case['schedule'], exp['calls']):
            ts = call['tokens']
            x = mx.array([[case['x'][t] for t in ts]], dtype=mx.float32); inds = mx.array([[case['indices'][t] for t in ts]], dtype=mx.int32)
            y = module(x, inds); mx.eval(y); st = store.stats()
            rows.append({'tokens': ts, 'waves': len(e['waves']), 'output': y[0].tolist(), 'stats': {k: st[k] for k in ('hits', 'misses', 'evictions', 'resident_experts', 'resident_bytes')},
                         'slot_of': {str(k): v for k, v in store.slot_of(case['layer_id']).items()}})
        value_err = max(max_error(r['output'], e['outputs']) for r, e in zip(rows, exp['calls']))
        policy_ok = all(r['stats'] == e['stats'] and r['slot_of'] == e['slot_of'] for r, e in zip(rows, exp['calls']))
        capacity_ok = store.capacity == exp['capacity']
        store.save_warm_state()
        fresh, _ = make(StoreClass, ModuleClass, case, directory, activation, warm_start=True, force_cold=force_cold)
        warm = {str(k): v for k, v in fresh.slot_of(case['layer_id']).items()}
        warm_ok = warm == exp['warm_state']['slot_on_restart'] and fresh.stats()['warm_admitted'] == len(warm)
        st = store.stats()
        return rows, value_err, policy_ok, capacity_ok, warm, warm_ok, {'layout': st['layout'], 'force_cold': force_cold, 'cold_reads': st['cold_reads'], 'coalesced_ranges': st['coalesced_ranges'], 'hot_reads': st['hot_reads']}

    def evaluate(StoreClass, ModuleClass, activation, case, directory):
        """Four passes: hash-ordered {resident, forced cold} and expert-contiguous {resident, forced cold}; every check must
        hold on each and the outputs of all four must agree with the first bit for bit."""
        contig, contig_ok, src_contig = contiguous_copy(case, directory)
        passes = []
        for d, fc in ((directory, False), (directory, True), (contig, False), (contig, True)):
            passes.append(evaluate_one(StoreClass, ModuleClass, activation, case, d, fc))
        rows, value_err, policy_ok, capacity_ok, warm, warm_ok, _ = passes[0]
        cross = max(max_error(p[0][i]['output'], rows[i]['output']) for p in passes[1:] for i in range(len(rows)))
        reads = [p[6] for p in passes]
        layout_ok = contig_ok and not src_contig and reads[2]['layout'] == 'expert-contiguous/1' and reads[3]['coalesced_ranges'] > 0 and reads[1]['cold_reads'] > 0 and reads[3]['cold_reads'] > 0
        all_ok = all(p[1] <= tol['output'] and p[2] and p[3] and p[5] for p in passes) and cross == 0.0 and layout_ok
        return rows, max(p[1] for p in passes), all(p[2] for p in passes), all(p[3] for p in passes), warm, all(p[5] for p in passes) and all(p[4] == warm for p in passes), {'cross_layout_max_diff': cross, 'contiguous_verified': contig_ok, 'source_not_contiguous': not src_contig, 'reads': reads, 'layout_ok': layout_ok, 'all_ok': all_ok}

    class FaultInjected(RuntimeError):
        pass

    def evaluate_faults(StoreClass, ModuleClass, activation, case, directory):
        """The fault schedule of the run card for one case on the hash layout, page-cache resident. Returns
        (record, ok); any deviation from the model (or a missing rejection) is recorded with its reason."""
        import os
        fid = case['fixture_id']; exp = expected[fid]; faults = fixture['expected_faults'][fid]; lid = case['layer_id']
        record = {'fixture_id': fid, 'points': faults['points'], 'runs': []}; ok = True

        def call(module, ci):
            ts = case['schedule'][ci]['tokens']
            x = mx.array([[case['x'][t] for t in ts]], dtype=mx.float32); inds = mx.array([[case['indices'][t] for t in ts]], dtype=mx.int32)
            y = module(x, inds); mx.eval(y)
            return y[0].tolist()

        def snapshot(store):
            st = store.stats()
            return {'stats': {k: st[k] for k in ('hits', 'misses', 'evictions', 'resident_experts', 'resident_bytes')}, 'slot_of': {str(k): v for k, v in store.slot_of(lid).items()},
                    'fill_failures': st['fill_failures'], 'poisoned': st['poisoned']}

        def fresh():
            ws = directory / 'pulsar-slot-warm-state.json'
            if ws.exists():
                os.remove(ws)
            return make(StoreClass, ModuleClass, case, directory, activation, warm_start=False)

        for point_name, pt in faults['points'].items():
            ci, wi = pt['call'], pt['wave']
            model_call = exp['calls'][ci]
            # which fill (among the call's waves that read) carries the fault: waves without a miss never reach fill
            target = sum(1 for w in model_call['waves'][:wi] if any(j in model_call['reads'] for j in w))
            for stage in ('read-done', 'projection-written', 'before-eval', 'during-eval'):
                row = {'point': point_name, 'call': ci, 'wave': wi, 'stage': stage, 'problems': []}
                store, module = fresh()
                for k in range(ci):
                    out = call(module, k)
                    if max_error(out, exp['calls'][k]['outputs']) > tol['output'] or snapshot(store)['stats'] != exp['calls'][k]['stats']:
                        row['problems'].append(f'pre-fault call {k} deviates')
                state = {'fills': 0, 'armed': False}
                hook_stage = 'before-eval' if stage == 'during-eval' else stage

                def hook(st, _state=state, _stage=hook_stage, _target=target):
                    if st == 'read-done':
                        _state['fills'] += 1
                    if st == _stage and _state['fills'] - 1 == _target:
                        if _stage == 'before-eval' and stage == 'during-eval':
                            _state['armed'] = True; return
                        raise FaultInjected(f'{stage} at wave {wi}')
                orig_eval = mx.eval

                def patched_eval(*a, **kw):
                    if state['armed']:
                        state['armed'] = False
                        raise FaultInjected(f'during-eval at wave {wi}')
                    return orig_eval(*a, **kw)
                store.fault_hook = hook
                if stage == 'during-eval':
                    mx.eval = patched_eval
                try:
                    try:
                        call(module, ci)
                        row['problems'].append('fault not raised')
                    except FaultInjected:
                        pass
                finally:
                    mx.eval = orig_eval
                    store.fault_hook = None
                after = snapshot(store); row['after_fault'] = after
                if stage == 'read-done':
                    model = faults['read_phase'][point_name]; m_after = model['calls'][ci]['after_fault']
                    if after['stats'] != m_after['stats'] or after['slot_of'] != m_after['slot_of'] or after['fill_failures'] != 1 or after['poisoned'] is not None:
                        row['problems'].append('post-fault state deviates from the model')
                    try:
                        for k in range(ci, len(case['schedule'])):
                            out = call(module, k); snap = snapshot(store)
                            err = max_error(out, exp['calls'][k]['outputs'])      # a fault changes no value
                            if err > tol['output']:
                                row['problems'].append(f'call {k} value error {err}')
                            if snap['stats'] != model['calls'][k]['stats'] or snap['slot_of'] != model['calls'][k]['slot_of']:
                                row['problems'].append(f'call {k} policy/slot map deviates from the model: {snap["stats"]} vs {model["calls"][k]["stats"]}')
                        row['retry'] = 'complete reload, model reproduced' if not row['problems'] else 'deviates'
                    except (RuntimeError, ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                        row['problems'].append(f'retry rejected: {type(exc).__name__}: {exc}')
                else:
                    if after['poisoned'] is None or after['fill_failures'] != 1:
                        row['problems'].append('store not poisoned after a write-phase fault')
                    for what, fn in (('retry', lambda: call(module, ci)), ('warm-state save', store.save_warm_state)):
                        try:
                            fn(); row['problems'].append(f'{what} served instead of STORE_POISONED')
                        except RuntimeError as exc:
                            if 'STORE_POISONED' not in str(exc):
                                row['problems'].append(f'{what} rejected with {exc!r}, not STORE_POISONED')
                        except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                            row['problems'].append(f'{what} rejected with {type(exc).__name__}, not STORE_POISONED')
                row['pass'] = not row['problems']; ok = ok and row['pass']
                record['runs'].append(row)
        record['pass'] = ok
        return record, ok

    observations, control_rows, fault_rows = [], [], []

    class Slot(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for fid, case in cases.items():
                got = slot_oracle.run(case)
                self.assertEqual(got, {k: v for k, v in expected[fid].items() if k in got}, fid)
            emit('frozen_reference', status='RECOMPUTED_EQUAL', cases=len(cases))

        def test_fault_injection(self):
            activation = activation_class(); StoreClass, ModuleClass = load_runtime(store_text)
            for fid, case in cases.items():
                directory = work / ('fault-' + fid); offload_controls.write_store(case, directory, mx)
                record, ok = evaluate_faults(StoreClass, ModuleClass, activation, case, directory)
                fault_rows.append(record); emit('slot_fault_injection', **record)
                self.assertTrue(ok, json.dumps(record))

        def test_slot_store(self):
            activation = activation_class(); StoreClass, ModuleClass = load_runtime(store_text)
            for fid, case in cases.items():
                directory = work / fid; files = offload_controls.write_store(case, directory, mx)
                rows, value_err, policy_ok, capacity_ok, warm, warm_ok, layouts = evaluate(StoreClass, ModuleClass, activation, case, directory)
                exp = expected[fid]
                row = {'fixture_id': fid, 'store_files': files, 'capacity': exp['capacity'], 'capacity_ok': capacity_ok, 'max_value_error': value_err,
                       'wave_split_calls': [i for i, c in enumerate(exp['calls']) if len(c['waves']) > 1], 'policy_and_slots_match_model': policy_ok,
                       'final_stats': rows[-1]['stats'], 'final_slot_of': rows[-1]['slot_of'], 'warm_readmitted': warm, 'warm_expected': exp['warm_state']['slot_on_restart'], 'warm_ok': warm_ok,
                       'layouts': layouts, 'pass': value_err <= tol['output'] and policy_ok and capacity_ok and warm_ok and layouts['all_ok']}
                observations.append(row); emit('slot_observation', **row)
                self.assertTrue(row['pass'], json.dumps(row))

        def test_structural_controls(self):
            recipes = [('decay-disabled', '                self._counts[k] *= self.decay\n', '                self._counts[k] *= 1.0\n'),
                       ('tie-break-most-recent', '        return (self._counts.get(key, 0.0), self._touch.get(key, 0))\n', '        return (self._counts.get(key, 0.0), -self._touch.get(key, 0))\n'),
                       ('warm-state-ignored', '            self._warm_admitted = self._admit_warm_state()\n', '            self._warm_admitted = 0\n'),
                       ('pin-ignored', '                candidates = [k for k in L.slot_of if k not in pinned]\n', '                candidates = list(L.slot_of)\n'),
                       ('missing-check-removed', '            store.fill(lid, store.touch_wave(lid, waves[0]))\n', '            store.touch_wave(lid, waves[0])\n'),
                       ('victim-slot-wrong', '            reads.append((j, s))\n        return reads', '            reads.append((j, (s + 1) % self.capacity))\n        return reads'),
                       ('coalesce-offset-wrong', '        return np.frombuffer(buf[a - lo:b - lo], dtype=np_dtype).reshape(e["shape"])\n', '        return np.frombuffer(buf[a - lo + 1:b - lo + 1], dtype=np_dtype).reshape(e["shape"])\n'),
                       ('layout-flag-ignored', '        self.contiguous = (header.get("__metadata__") or {}).get("layout") == "expert-contiguous/1"\n', '        self.contiguous = True\n'),
                       ('publish-before-fill', '            L.pending[j] = s                                                  # reserved, published by fill on success\n',
                        '            L.pending[j] = s; L.slot_of[j] = s; L.expert_to_slot[j] = s\n'),
                       ('poison-not-checked', '        if self.poisoned is not None:\n            raise RuntimeError(f"STORE_POISONED: {self.poisoned}")\n', '        if False:\n            raise RuntimeError(f"STORE_POISONED: {self.poisoned}")\n'),
                       ('release-slots-omitted', '            L.free[0:0] = [s for _, s in reads]                               # a retry takes the same slots back\n', '            pass\n')]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            activation = activation_class()
            for label, before, after in recipes:
                self.assertEqual(store_text.count(before), 1, label)
                MutantStore, MutantModule = load_runtime(store_text.replace(before, after, 1))
                results = []
                for expected_cell, fid in zip(matrix['matrix'][label], matrix['fixtures']):
                    case = cases[fid]; directory = work / fid
                    try:
                        rows, value_err, policy_ok, capacity_ok, warm, warm_ok, layouts = evaluate(MutantStore, MutantModule, activation, case, directory)
                        observed = 'INACTIVE' if (policy_ok and warm_ok and value_err <= tol['output'] and layouts['all_ok']) else 'KILL'
                        reason = 'policy-or-slot-mismatch' if not policy_ok else ('warm-mismatch' if not warm_ok else ('value' if value_err > tol['output'] or layouts['cross_layout_max_diff'] > 0 else 'layout-check'))
                        if observed == 'INACTIVE':      # the fault schedule is part of the cell (graph 31)
                            fdir = work / ('fault-' + fid); offload_controls.write_store(case, fdir, mx)
                            frecord, fok = evaluate_faults(MutantStore, MutantModule, activation, case, fdir)
                            if not fok:
                                observed = 'KILL'; reason = 'fault:' + '; '.join(p for r in frecord['runs'] for p in r['problems'])[:300]
                    except (RuntimeError, ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                        observed, reason = 'KILL', 'rejected:' + type(exc).__name__
                    results.append({'fixture_id': fid, 'observed': observed, 'expected_cell': expected_cell, 'reason': reason, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                control_rows.append(row); emit('slot_control', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Slot)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('slot_summary', backend=backend, observations=observations, controls=control_rows, fault_injection=fault_rows,
         scope='PULSAR_SLOT_STORE_AND_SWITCH_OVER_FROZEN_STORE; values vs graph-18 reference incl. wave split; slots and policy vs stdlib model; warm state; both layouts and both residency modes bit-identical; fault injection: read-phase retry reproduces the model, write-phase poisons; no throughput claim')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

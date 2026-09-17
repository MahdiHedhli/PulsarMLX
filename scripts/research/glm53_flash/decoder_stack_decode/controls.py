"""Two-layer stack prefill + decode with make_cache caches against the frozen stack reference, in the successor child.

The caches are exactly what the admitted LanguageModel.make_cache() returns
(no prepare/left_padding, as in single-stream generation): the linear layer
sees ssm_mask None; the sparse layer sees the causal mask at prefill and None
at decode (KVCache.make_mask). Observed per step: logits, the linear layer's
ArraysCache slots against the accepted linear reference's per-time cache
states, the KVCache offsets, and whether the compiled decode-step FFN was
taken. Mutants of the stack capsule are decided against the matrix frozen from
oracle variants over the whole schedule.
"""
import ast
import hashlib
import json
import math
import resource
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-stack-decode-v1/fixtures.json'


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


def schedule(model, case, mx, on_step=None):
    """Run prefill + decode with model.make_cache(); return per-step logits rows (and call on_step(t_list, caches))."""
    S0 = case['prefill_tokens']; ids = case['ids']
    caches = model.make_cache()
    rows = []
    for tokens in [list(range(S0))] + [[t] for t in range(S0, len(ids))]:
        out = model(mx.array([[ids[t] for t in tokens]], dtype=mx.int32), cache=caches)
        mx.eval(out.logits)
        for i, t in enumerate(tokens):
            rows.append({'time': t, 'logits': out.logits[0, i].tolist()})
        if on_step is not None:
            on_step(tokens, caches)
    return rows, caches


def run(context, backend, mx, nn, refs, sources, stack_controls, attention_oracle, decode_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    tol = fixture['tolerances']
    matrix = fixture['expected_kill_matrix']
    case = fixture['cases'][0]
    expected = fixture['expected'][case['fixture_id']]
    capsule_raw = context.read_verified(root / sources['stack'].CAPSULE)
    language_raw = context.read_verified(root / sources['ffn'].LANGUAGE)
    emit('stack_decode_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), backend=backend, actual_default_device=str(mx.default_device()))

    # The stack controls' admitted() assembly is reused through its module (same admitted classes).
    stack_run = stack_controls.run  # noqa: F841  (documented reuse; the admission helpers below mirror decoder_stack.controls)
    linear_fixture = json.loads(context.read_verified(root / stack_controls.LINEAR_FIXTURE))
    cache_fixture = json.loads(context.read_verified(root / stack_controls.CACHE_FIXTURE))
    cache_raw = context.read_verified(root / sources['stack'].CACHE)
    base_raw = context.read_verified(root / sources['sparse'].BASE)
    mla_raw = context.read_verified(root / sources['sparse'].MLA)
    switch_raw = context.read_verified(root / sources['moe'].SWITCH)
    moe_capsule = context.read_verified(root / sources['moe'].CAPSULE)
    sparse_capsule = context.read_verified(root / sources['sparse'].CAPSULE)

    def admitted(capsule=capsule_raw):
        ffn = sources['ffn'].load(root, mx, nn)
        attention = sources['attention'].load(context, linear_fixture, None)
        cache_ns, _, cache_binding = sources['cache'].load(context, cache_fixture)
        gate = sources['rc'].Builder(context.phase, mx, nn, context.verify_environment(context.phase)).new()
        moe = sources['moe'].load(moe_capsule, language_raw, switch_raw, mx, nn, sources['ffn'], ffn.namespace, gate['caller'])
        sparse = sources['sparse'].load(sparse_capsule, language_raw, mla_raw, base_raw, mx, nn, sources['ffn'])
        stack = sources['stack'].load(capsule, language_raw, cache_raw, base_raw, mx, nn, sources['ffn'], sources['sparse'],
                                      {'ffn_namespace': ffn.namespace, 'attention_namespace': attention.namespace, 'cache_namespace': cache_ns,
                                       'moe_class': moe.namespace['source_moe'], 'sparse_class': sparse.namespace['source_sparse_attention']})
        return stack, cache_binding

    def mutant_namespace(bound, mutated):
        ns = {k: v for k, v in bound.namespace.items() if k not in ('Glm5NextDecoderLayer', 'Glm5NextModel', 'source_language_model')}
        for n in ast.parse(mutated).body:
            exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
        return ns

    observations, mutant_rows = [], []

    class StackDecode(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            self.assertEqual(decode_oracle.run(case, refs), expected)
            emit('frozen_reference', status='RECOMPUTED_EQUAL')

        def test_decode_boundaries(self):
            bound, cache_binding = admitted()
            model = stack_controls.build(bound.namespace, case, mx)
            dep = bound.dependency_namespace
            steps = []
            step_index = [0]
            def on_step(tokens, caches):
                exp = expected['steps'][step_index[0]]; step_index[0] += 1
                c0, c1 = caches[0].cache
                mx.eval(c0, c1)
                ev = exp['linear_cache_after']
                kv = caches[1]
                l0, l1 = model.model.layers
                row = {'kind': exp['kind'], 'tokens': tokens,
                       'cache_types': [type(caches[0]).__name__, type(caches[1]).__name__],
                       'routing_ok': isinstance(caches[0], bound.namespace['ArraysCache']) and isinstance(caches[1], dep['CacheList'])
                                     and all(isinstance(kv[i], dep['KVCache']) for i in range(2)),
                       'cache0_ok': attention_oracle.close(c0.tolist(), ev['cache0'], tol['cache0_atol'], tol['cache0_rtol']),
                       'cache1_ok': attention_oracle.close(c1.tolist(), ev['cache1'], tol['cache1_atol'], tol['cache1_rtol']),
                       'cache0_shape': list(c0.shape), 'cache1_shape': list(c1.shape),
                       'kv_offsets': [kv[0].offset, kv[1].offset], 'kv_offset_expected': exp['kv_offset_after'],
                       'compiled_ffn_present': [l0._ffn_c is not None, l1._ffn_c is not None], 'compiled_ffn_expected': exp['compiled_ffn_used'],
                       'indexer_pool_T': None if getattr(kv[1], '_pool', None) is None else kv[1]._pool[3]}
                row['pass'] = (row['routing_ok'] and row['cache0_ok'] and row['cache1_ok'] and row['kv_offsets'] == [exp['kv_offset_after']] * 2
                               and all(p == exp['compiled_ffn_used'] for p in row['compiled_ffn_present']))
                steps.append(row)
            rows, caches = schedule(model, case, mx, on_step)
            for r in rows:
                r['logits_error'] = max_error(r['logits'], expected['logits'][r['time']]); r['pass'] = r['logits_error'] <= tol['logits']
                del r['logits']
            final_ok = (attention_oracle.close(caches[0].cache[0].tolist(), expected['final_linear_cache']['cache0'], tol['cache0_atol'], tol['cache0_rtol'])
                        and attention_oracle.close(caches[0].cache[1].tolist(), expected['final_linear_cache']['cache1'], tol['cache1_atol'], tol['cache1_rtol']))
            record = {'fixture_id': case['fixture_id'], 'token_rows': rows, 'steps': steps, 'final_linear_cache_ok': final_ok,
                      'contract': bound.contract, 'cache_binding': cache_binding}
            observations.append(record); emit('stack_decode_observation', **record)
            for r in rows:
                self.assertTrue(r['pass'], json.dumps(r))
            for s in steps:
                self.assertTrue(s['pass'], json.dumps(s))
            self.assertTrue(final_ok)

        def test_semantic_mutants(self):
            recipes = [
                ('compile-gate-forced-eager', 'if self.compile_ffn and x.shape[0] == 1 and x.shape[1] == 1:', 'if False:'),
                ('compile-cache-not-reused', 'if self._ffn_c is None:', 'if True:'),
                ('layer-cache-dropped', 'h = layer(h, mask=mask, cache=c)', 'h = layer(h, mask=mask, cache=None)'),
                ('norm-before-mean', '        h = h.mean(axis=2)\n        return self.norm(h)', '        return self.norm(h).mean(axis=2)'),
                ('cache-list-misrouted', 'for layer, c in zip(self.layers, cache):', 'for layer, c in zip(self.layers, reversed(cache)):'),
                ('make-cache-linear-size-1', 'caches.append(ArraysCache(size=2))', 'caches.append(ArraysCache(size=1))'),
            ]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            text = capsule_raw.decode()
            factor, allowance = matrix['kill_margin_factor'], tol['logits']
            bound, _ = admitted()
            for label, before, after in recipes:
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_STACK_(CALLER_TRANSFORM|CLOSURE)'):
                    sources['stack'].verify_capsule(mutated, language_raw, sources['ffn'])
                ns = mutant_namespace(bound, mutated)
                expected_cell = matrix['matrix'][label][0]
                try:
                    model = stack_controls.build(ns, case, mx)
                    rows, _ = schedule(model, case, mx)
                    per_step = [max_error(r['logits'], expected['logits'][r['time']]) for r in rows]
                    err = max(per_step); reason = 'value' if err != float('inf') else 'nonfinite_or_shape'
                    steps_changed = [r['time'] for r, e in zip(rows, per_step) if e > allowance]
                except (RuntimeError, ValueError, TypeError, AttributeError, IndexError) as exc:
                    err, reason, steps_changed = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)[:160], None
                observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                result = {'fixture_id': case['fixture_id'], 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason,
                          'steps_changed': steps_changed, 'predicted_steps_changed': matrix['predicted_steps_changed'][label],
                          'observed': observed, 'expected_cell': expected_cell, 'cell_pass': observed == expected_cell}
                row = {'label': label, 'mutant_sha256': digest(mutated), 'results': [result], 'all_cells_pass': result['cell_pass']}
                mutant_rows.append(row); emit('stack_decode_mutant', **row)
                self.assertEqual(observed, expected_cell, f"{label}: {result}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StackDecode)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('stack_decode_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='FINITE_FP32_GLM5NEXT_TWO_LAYER_STACK_DECODE_SYNTHETIC_ONLY; batch 1; make_cache caches; prefill 2 + decode 2; compiled decode FFN')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

"""Glm5NextSparseAttention decode with CacheList(KVCache(), KVCache()) against the incremental oracle, in the successor child.

Schedule: prefill S0 tokens with the causal mask and a fresh cache, then one
token per step with mask None (what KVCache.make_mask returns for N=1).
Observed per step: qr, kv latent, the indexer's token indices (or bypass), the
attention concat entering o_proj, the output, and after each non-bypass step
the candidate's cache[1]._pool against the oracle's pool state plus the
candidate-internal equality of the incremental pool with a full recomputation.
Mutants are decided against the matrix frozen from oracle variants over the
whole schedule.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-sparse-decode-v1/fixtures.json'
CACHE_FIXTURE = 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'


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


def schedule(block, case, cache, mx, sparse_controls, observe=True):
    """Run prefill + decode steps; return per-step observations (or outputs only when observe is False)."""
    S0 = case['prefill_tokens']; x = case['x']
    rows = []
    def one(tokens, mask):
        xa = mx.array([[x[t] for t in tokens]], dtype=mx.float32)
        if observe:
            seen = sparse_controls.observe_with_cache(block, xa, mask, cache, mx)
            for i, t in enumerate(tokens):
                rows.append({'time': t, 'qr': seen['qr'][i], 'kv_latent': seen['kv_latent'][i],
                             'topk': None if seen['topk'] is None else seen['topk'][i],
                             'attention_concat': seen['attention_concat'][i], 'output': seen['output'][i]})
        else:
            y = block(xa, mask, cache); mx.eval(y)
            for i, t in enumerate(tokens):
                rows.append({'time': t, 'output': y[0, i].tolist()})
    one(list(range(S0)), sparse_controls.causal_mask(S0, mx))
    for t in range(S0, len(x)):
        one([t], None)
    return rows


def pool_snapshot(cache1, mx):
    if getattr(cache1, '_pool', None) is None:
        return None
    pk, pi, pv, T = cache1._pool
    mx.eval(pk, pi, pv)
    return {'keys': pk[0].tolist(), 'indices': pi[0].tolist(), 'valid': pv[0].tolist(), 'T': T}


def run(context, backend, mx, nn, ffn_source, sparse_source, sparse_controls, decode_oracle, cache_source, stack_source):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    cache_fixture = json.loads(context.read_verified(root / CACHE_FIXTURE))
    capsule_raw = context.read_verified(root / sparse_source.CAPSULE)
    language_raw = context.read_verified(root / ffn_source.LANGUAGE)
    mla_raw = context.read_verified(root / sparse_source.MLA)
    base_raw = context.read_verified(root / sparse_source.BASE)
    cache_raw = context.read_verified(root / stack_source.CACHE)
    tol = fixture['tolerances']
    matrix = fixture['expected_kill_matrix']
    emit('sparse_decode_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), backend=backend, actual_default_device=str(mx.default_device()))

    def admitted(capsule=capsule_raw):
        bound = sparse_source.load(capsule, language_raw, mla_raw, base_raw, mx, nn, ffn_source)
        cache_ns, _, cache_binding = cache_source.load(context, cache_fixture)
        caches = stack_source.load_cache_classes(cache_raw, base_raw, mx, nn, ffn_source, sparse_source, cache_ns._BaseCache)
        return bound, caches, cache_binding

    def fresh_cache(caches):
        return caches.namespace['CacheList'](caches.namespace['KVCache'](), caches.namespace['KVCache']())

    def mutant_namespace(bound, mutated):
        ns = {k: v for k, v in bound.namespace.items() if k not in ('Glm5NextIndexer', 'source_sparse_attention')}
        for n in ast.parse(mutated).body:
            exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
        return ns

    observations, mutant_rows = [], []
    case = fixture['cases'][0]
    expected = fixture['expected'][case['fixture_id']]
    expected_rows = [row for st in expected['steps'] for row in st['rows']]

    class SparseDecode(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            self.assertEqual(decode_oracle.run(case), expected)
            emit('frozen_reference', status='RECOMPUTED_EQUAL')

        def test_decode_boundaries(self):
            bound, caches, cache_binding = admitted()
            block = sparse_controls.build(bound.namespace, case, mx)
            cache = fresh_cache(caches)
            S0 = case['prefill_tokens']
            steps = []
            x = case['x']
            for kind, tokens in [('prefill', list(range(S0)))] + [('decode', [t]) for t in range(S0, len(x))]:
                xa = mx.array([[x[t] for t in tokens]], dtype=mx.float32)
                mask = sparse_controls.causal_mask(len(tokens), mx) if kind == 'prefill' else None
                seen = sparse_controls.observe_with_cache(block, xa, mask, cache, mx)
                for i, t in enumerate(tokens):
                    exp = expected_rows[t]
                    topk = None if seen['topk'] is None else seen['topk'][i]
                    row = {'kind': kind, 'time': t, 'bypass_expected': exp['regime'] == 'bypass', 'bypass_observed': topk is None,
                           'topk_equal': topk == exp['topk'], 'candidate_topk': topk,
                           'qr_error': max_error(seen['qr'][i], expected['qr'][t]), 'kv_latent_error': max_error(seen['kv_latent'][i], expected['kv_latent'][t]),
                           'attention_concat_error': max_error(seen['attention_concat'][i], exp['attention_concat']),
                           'output_error': max_error(seen['output'][i], exp['output'])}
                    if exp['regime'] == 'sparse':
                        snap = pool_snapshot(cache[1], mx)
                        row['pool_indices_equal'] = snap['indices'] == exp['pool_state']['indices']
                        row['pool_valid_equal'] = snap['valid'] == exp['pool_state']['valid']
                        row['pool_keys_error'] = max_error(snap['keys'], exp['pool_state']['keys'])
                        row['pool_T'] = snap['T']
                        # candidate-internal: the incremental pool equals a full recomputation from the cache
                        packed = cache[1].keys[:, 0, :cache[1].offset]
                        hd = block.indexer.head_dim
                        k_full, gate_full, valid_ch = mx.split(packed, [hd, 2 * hd], axis=-1)
                        fk, fi, fv = block.indexer._pooled_states(k_full, gate_full, valid_ch[..., 0] > 0)
                        mx.eval(fk, fi, fv)
                        row['incremental_equals_full'] = (fi[0].tolist() == snap['indices'] and fv[0].tolist() == snap['valid']
                                                          and max_error(fk[0].tolist(), snap['keys']) <= 1e-6)
                        row['pooling_expected'] = exp['pooling']
                    ok = (row['bypass_observed'] == row['bypass_expected'] and row['topk_equal'] and row['qr_error'] <= tol['qr']
                          and row['kv_latent_error'] <= tol['kv_latent'] and row['attention_concat_error'] <= tol['attention_concat']
                          and row['output_error'] <= tol['output'])
                    if exp['regime'] == 'sparse':
                        ok = ok and row['pool_indices_equal'] and row['pool_valid_equal'] and row['pool_keys_error'] <= tol['pool_keys'] and row['incremental_equals_full']
                    row['pass'] = ok
                    steps.append(row); emit('sparse_decode_step', **row)
            self.assertEqual(cache[0].offset, len(x)); self.assertEqual(cache[1].offset, len(x))
            record = {'fixture_id': case['fixture_id'], 'steps': steps, 'contract': bound.contract, 'cache_binding': cache_binding,
                      'cache_dependency_ast_sha256': caches.digests, 'final_offsets': [cache[0].offset, cache[1].offset]}
            observations.append(record); emit('sparse_decode_observation', **{k: v for k, v in record.items() if k != 'steps'})
            for row in steps:
                self.assertTrue(row['pass'], json.dumps(row))

        def test_semantic_mutants(self):
            recipes = [
                ('incremental-suffix-offset-omitted', 'pi_s = mx.where(pi_s >= 0, pi_s + s0, -1)', 'pi_s = pi_s'),
                ('stale-partial-pool-kept', 'n_stable = t_prev // self.index_kpool', 'n_stable = t_prev // self.index_kpool + 1'),
                ('stable-pools-recomputed', 'n_stable = t_prev // self.index_kpool', 'n_stable = max(t_prev // self.index_kpool - 1, 0)'),
                ('incremental-path-disabled', 'cache._no_pad = bool(mx.all(valid))', 'cache._no_pad = False'),
                ('decode-selection-mask-ignored', 'attn_mask = sel_mask', 'attn_mask = None'),
                ('decode-unembed-omitted', '            output = self.unembed_out(output)\n', '            output = output\n'),
                ('latent-cache-not-fetched', 'kv_latent, _ = cache[0].update_and_fetch(kv_latent, kv_latent)', 'cache[0].update_and_fetch(kv_latent, kv_latent)'),
            ]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            text = capsule_raw.decode()
            factor, allowance = matrix['kill_margin_factor'], tol['output']
            bound, caches, _ = admitted()
            for label, before, after in recipes:
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_SPARSE_(CALLER_TRANSFORM|CLOSURE)'):
                    sparse_source.verify_capsule(mutated, language_raw, ffn_source)
                ns = mutant_namespace(bound, mutated)
                expected_cell = matrix['matrix'][label][0]
                try:
                    block = sparse_controls.build(ns, case, mx)
                    rows = schedule(block, case, fresh_cache(caches), mx, sparse_controls, observe=False)
                    per_step = [max_error(r['output'], expected_rows[r['time']]['output']) for r in rows]
                    err = max(per_step); reason = 'value' if err != float('inf') else 'nonfinite_or_shape'
                    steps_changed = [r['time'] for r, e in zip(rows, per_step) if e > allowance]
                except (RuntimeError, ValueError, TypeError, AttributeError, IndexError) as exc:
                    err, reason, steps_changed = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)[:160], None
                observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                result = {'fixture_id': case['fixture_id'], 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason,
                          'steps_changed': steps_changed, 'predicted_steps_changed': matrix['predicted_steps_changed'][label],
                          'observed': observed, 'expected_cell': expected_cell, 'cell_pass': observed == expected_cell}
                row = {'label': label, 'mutant_sha256': digest(mutated), 'results': [result], 'all_cells_pass': result['cell_pass']}
                mutant_rows.append(row); emit('sparse_decode_mutant', **row)
                self.assertEqual(observed, expected_cell, f"{label}: {result}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SparseDecode)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('sparse_decode_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='FINITE_FP32_GLM5NEXT_SPARSE_ATTENTION_DECODE_SYNTHETIC_ONLY; batch 1; no padding; prefill 2 + 5 decode steps; kpool 2 topk 2')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

"""Glm5NextSparseAttention (NoPE MLA + lightning indexer) against the frozen oracle, in the successor child.

Slice 1: prefill, batch 1, no cache, the causal boolean mask the model builds
(`create_causal_mask(N)`: linds >= rinds). Observed boundaries: qr (after the
q RMSNorm), kv latent (after its RMSNorm), the indexer's top-k token indices
(or bypass), the attention concat entering o_proj, and the output. Mutants are
decided cell by cell against the matrix frozen from oracle variants.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-sparse-v1/fixtures.json'


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


def build(ns, case, mx):
    config = types.SimpleNamespace(**case['config'], index_kpool_compress=True)
    block = ns['source_sparse_attention'](config)
    A = lambda v: mx.array(v, dtype=mx.float32)
    w, ix = case['weights'], case['indexer']
    block.q_a_proj.weight = A(w['q_a_proj']); block.q_a_layernorm.weight = A(w['q_a_layernorm']); block.q_b_proj.weight = A(w['q_b_proj'])
    block.kv_a_proj_with_mqa.weight = A(w['kv_a_proj_with_mqa']); block.kv_a_layernorm.weight = A(w['kv_a_layernorm'])
    block.embed_q.weight = A(w['embed_q']); block.unembed_out.weight = A(w['unembed_out']); block.o_proj.weight = A(w['o_proj'])
    idx = block.indexer
    idx.wq_b.weight = A(ix['wq_b']); idx.wk.weight = A(ix['wk']); idx.k_norm.weight = A(ix['k_norm_weight']); idx.k_norm.bias = A(ix['k_norm_bias'])
    idx.weights_proj.weight = A(ix['weights_proj']); idx.index_kpool_compress_ape = A(ix['compress_ape']); idx.index_kpool_compress_gate = A(ix['compress_gate'])
    return block


def causal_mask(S, mx):
    # create_causal_mask(N) upstream: linds >= rinds, boolean, offset 0.
    r = mx.arange(S)
    return r[:, None] >= r[None]


def observe(block, x, mask, mx):
    return observe_with_cache(block, x, mask, None, mx)


def observe_with_cache(block, x, mask, cache, mx):
    seen = {}
    q_norm, kv_norm, indexer, o_proj = block.q_a_layernorm, block.kv_a_layernorm, block.indexer, block.o_proj
    def observed_q_norm(v):
        r = q_norm(v); mx.eval(r); seen['qr'] = r[0].tolist(); return r
    def observed_kv_norm(v):
        r = kv_norm(v); mx.eval(r); seen['kv_latent'] = r[0].tolist(); return r
    def observed_indexer(xx, qr, m, cache=None):
        r = indexer(xx, qr, m, cache=cache)
        if r is None:
            seen['topk'] = None
        else:
            mx.eval(r); seen['topk'] = r[0, 0].tolist()  # [S][W]
        return r
    def observed_o_proj(v):
        mx.eval(v); seen['attention_concat'] = v[0].tolist(); r = o_proj(v); mx.eval(r); return r
    block.q_a_layernorm, block.kv_a_layernorm, block.indexer, block.o_proj = observed_q_norm, observed_kv_norm, observed_indexer, observed_o_proj
    try:
        y = block(x, mask, cache); mx.eval(y)
    finally:
        block.q_a_layernorm, block.kv_a_layernorm, block.indexer, block.o_proj = q_norm, kv_norm, indexer, o_proj
    seen['output'] = y[0].tolist()
    return seen


def run(context, backend, mx, nn, ffn_source, sparse_source, sparse_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    capsule_raw = context.read_verified(root / sparse_source.CAPSULE)
    language_raw = context.read_verified(root / ffn_source.LANGUAGE)
    mla_raw = context.read_verified(root / sparse_source.MLA)
    base_raw = context.read_verified(root / sparse_source.BASE)
    tol = fixture['tolerances']
    matrix = fixture['expected_kill_matrix']
    emit('sparse_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), mla_sha256=digest(mla_raw),
         base_sha256=digest(base_raw), backend=backend, actual_default_device=str(mx.default_device()))

    def admitted(capsule=capsule_raw):
        return sparse_source.load(capsule, language_raw, mla_raw, base_raw, mx, nn, ffn_source)

    def mutant_namespace(bound, mutated):
        # Both classes are re-executed into one fresh dict: classes resolve globals from
        # the dict they were executed in, so a mutated Indexer must be visible to the caller.
        ns = {k: v for k, v in bound.namespace.items() if k not in ('Glm5NextIndexer', 'source_sparse_attention')}
        for n in ast.parse(mutated).body:
            exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
        return ns

    observations, mutant_rows = [], []

    class Sparse(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for case in fixture['cases']:
                self.assertEqual(sparse_oracle.run(case), fixture['expected'][case['fixture_id']], case['fixture_id'])
            emit('frozen_reference', status='RECOMPUTED_EQUAL')

        def test_block_boundaries(self):
            bound = admitted()
            for case in fixture['cases']:
                exp = fixture['expected'][case['fixture_id']]
                block = build(bound.namespace, case, mx)
                x = mx.array([case['x']], dtype=mx.float32)
                seen = observe(block, x, causal_mask(case['tokens'], mx), mx)
                row = {'fixture_id': case['fixture_id'], 'bypass_expected': exp['bypass'], 'bypass_observed': seen['topk'] is None,
                       'topk_equal': seen['topk'] == exp['topk'], 'candidate_topk': seen['topk'],
                       'qr_error': max_error(seen['qr'], exp['qr']), 'kv_latent_error': max_error(seen['kv_latent'], exp['kv_latent']),
                       'attention_concat_error': max_error(seen['attention_concat'], exp['attention_concat']),
                       'output_error': max_error(seen['output'], exp['output']), 'contract': bound.contract}
                row['pass'] = (row['bypass_observed'] == row['bypass_expected'] and row['topk_equal'] and row['qr_error'] <= tol['qr']
                               and row['kv_latent_error'] <= tol['kv_latent'] and row['attention_concat_error'] <= tol['attention_concat']
                               and row['output_error'] <= tol['output'])
                observations.append(row); emit('sparse_observation', **row)
                self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k != 'contract'}))

        def test_semantic_mutants(self):
            recipes = [
                ('indexer-scale-omitted', 'scores = mx.maximum(scores * self.softmax_scale, 0.0)', 'scores = mx.maximum(scores, 0.0)'),
                ('indexer-relu-omitted', 'scores = mx.maximum(scores * self.softmax_scale, 0.0)', 'scores = scores * self.softmax_scale'),
                ('tail-selection-omitted', 'if tail_on:\n', 'if False:\n'),
                ('kv-latent-norm-omitted', 'kv_latent = self.kv_a_layernorm(compressed_kv)', 'kv_latent = compressed_kv'),
                ('sparse-mask-ignored', 'attn_mask = sparse_mask', 'attn_mask = mask'),
                ('embed-transpose-wrong', 'k = self.embed_q(kv_latent, transpose=False)', 'k = self.embed_q(kv_latent, transpose=True)'),
            ]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            text = capsule_raw.decode()
            factor, allowance = matrix['kill_margin_factor'], tol['output']
            bound = admitted()
            for label, before, after in recipes:
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_SPARSE_(CALLER_TRANSFORM|CLOSURE)'):
                    sparse_source.verify_capsule(mutated, language_raw, ffn_source)
                ns = mutant_namespace(bound, mutated)
                results = []
                for expected_cell, case in zip(matrix['matrix'][label], fixture['cases']):
                    expected = fixture['expected'][case['fixture_id']]['output']
                    block = build(ns, case, mx)
                    try:
                        y = block(mx.array([case['x']], dtype=mx.float32), causal_mask(case['tokens'], mx), None); mx.eval(y)
                        err = max_error(y[0].tolist(), expected); reason = 'value' if err != float('inf') else 'nonfinite_or_shape'
                    except (RuntimeError, ValueError) as exc:
                        err, reason = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)
                    observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                    results.append({'fixture_id': case['fixture_id'], 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason,
                                    'observed': observed, 'expected_cell': expected_cell, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'mutant_sha256': digest(mutated), 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                mutant_rows.append(row); emit('sparse_mutant', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

        def test_refusals(self):
            bound = admitted()
            dep = bound.dependency_namespace
            with self.assertRaisesRegex(RuntimeError, 'QUANTIZED_MULTILINEAR_NOT_ADMITTED'):
                dep['MultiLinear'](4, 4, 2).to_quantized(64, 4)
            q = mx.zeros((1, 2, 1, 4))
            with self.assertRaisesRegex(RuntimeError, 'QUANTIZED_SDPA_NOT_ADMITTED'):
                dep['scaled_dot_product_attention'](q, q, q, cache=types.SimpleNamespace(bits=4, group_size=64), scale=0.5, mask=None)
            with self.assertRaisesRegex(RuntimeError, 'TURBOQUANT_CACHE_NOT_ADMITTED'):
                dep['TurboQuantKVCache']()
            emit('refusal', quantized_multilinear='REFUSED', quantized_sdpa='REFUSED', turboquant_cache='REFUSED')

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Sparse)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('sparse_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='FINITE_FP32_GLM5NEXT_SPARSE_ATTENTION_PREFILL_SYNTHETIC_ONLY; batch 1; no cache; no padding; NoPE MLA; kpool 2 topk 4')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

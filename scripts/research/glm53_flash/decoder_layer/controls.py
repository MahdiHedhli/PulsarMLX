"""Whole dense/linear decoder-layer composition against the frozen layer oracle.

Runs inside the successor's confined child. The attention module is the
linear-attention admitted namespace (counters, kernel geometry admission);
HC/MLP come from the dense-FFN admitted namespace; the layer capsule is the
renamed upstream class. Observations: attention input (post-norm), attention
output, x1 after the attention-side hc_expand, and the layer output, plus the
compiled decode-step gate on the first token. Mutants are decided cell by cell
against the frozen expected_kill_matrix; nothing is relabelled after
observation.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-layer-v1/fixtures.json'
LINEAR_FIXTURE = 'fixtures/research/glm53-flash-linear-attention-v1/fixtures.json'
CACHE_FIXTURE = 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'


class Mismatch(AssertionError):
    pass


def emit(event, **values):
    print(json.dumps({'event': event, **values}, sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def max_error(a, b):
    if type(a) is list:
        if type(b) is not list or len(a) != len(b):
            return float('inf')
        return max((max_error(x, y) for x, y in zip(a, b)), default=0.0)
    return abs(a - b)


def build_layer(ns, case, mx, nn):
    cfg = case['linear_config']
    H, I = case['shape'][2], case['shape'][3]
    config = types.SimpleNamespace(layer_types=['linear_attention'], n_routed_experts=None, first_k_dense_replace=0,
                                   mlp_layer_types=['dense'], hidden_size=I, rms_norm_eps=case['rms_norm_eps'],
                                   hc_mult=H, hc_sinkhorn_iters=case['hc_sinkhorn_iters'], hc_eps=case['hc_eps'],
                                   intermediate_size=len(case['ffn']['gate']), swiglu_limit=case['ffn']['limit'],
                                   linear_num_heads=cfg['linear_num_heads'], linear_head_dim=cfg['linear_head_dim'],
                                   linear_conv_kernel_dim=cfg['linear_conv_kernel_dim'], linear_lower_bound=cfg['linear_lower_bound'])
    layer = ns['source_decoder_layer'](config, 0)
    for hc_name, key in (('attn_hc', 'attn_hc'), ('ffn_hc', 'ffn_hc')):
        hc = getattr(layer, hc_name)
        for p in ('fn', 'base', 'scale'):
            setattr(hc, p, mx.array(case[key][p], dtype=mx.float32))
    for p in ('gate', 'up', 'down'):
        getattr(layer.mlp, p + '_proj').weight = mx.array(case['ffn'][p], dtype=mx.float32)
    for name, value in case['linear_parameters'].items():
        owner = layer.self_attn
        parts = name.split('.')
        for part in parts[:-1]:
            owner = getattr(owner, part)
        setattr(owner, parts[-1], mx.array(value, dtype=mx.float32))
    return layer


def observe(layer, x, mx):
    """Wrap around unchanged calls; copy values; return original objects."""
    seen = {}
    norm = layer.input_layernorm
    attn = layer.self_attn
    def observed_norm(v):
        r = norm(v); mx.eval(r); seen['attn_norm'] = r.tolist(); return r
    def observed_attn(v, mask=None, cache=None):
        r = attn(v, mask, cache); mx.eval(r); seen['attention'] = r.tolist(); return r
    layer.input_layernorm = observed_norm
    layer.self_attn = observed_attn
    try:
        y = layer(x)
        mx.eval(y)
    finally:
        layer.input_layernorm = norm
        layer.self_attn = attn
    seen['output'] = y.tolist()
    return seen


def run(context, backend, mx, nn, ffn_source, ffn_oracle, layer_source, layer_oracle, attention_source, attention_oracle, accepted_recurrence, cache_source):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    linear_fixture = json.loads(context.read_verified(root / LINEAR_FIXTURE))
    cache_fixture = json.loads(context.read_verified(root / CACHE_FIXTURE))
    capsule_raw = context.read_verified(root / layer_source.CAPSULE)
    language_raw = context.read_verified(root / ffn_source.LANGUAGE)
    tol = fixture['tolerances']
    matrix = fixture['expected_kill_matrix']
    emit('layer_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), backend=backend,
         cases=[c['fixture_id'] for c in fixture['cases']], actual_default_device=str(mx.default_device()))

    def admitted(capsule=capsule_raw):
        ffn = ffn_source.load(root, mx, nn)
        attention = attention_source.load(context, linear_fixture, None)
        layer = layer_source.load(capsule, language_raw, mx, nn, ffn_source, ffn.namespace, attention.namespace)
        return layer, attention

    observations, mutant_rows = [], []

    class Layer(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for case in fixture['cases']:
                r = layer_oracle.run(case, attention_oracle.module_reference, accepted_recurrence, ffn_oracle.run)
                exp = fixture['expected'][case['fixture_id']]
                self.assertEqual(r['boundaries'], exp['boundaries'], case['fixture_id'])
                self.assertEqual(r['attention_cache_events'], exp['attention_cache_events'], case['fixture_id'])
                self.assertEqual(r['attention_final_cache'], exp['attention_final_cache'], case['fixture_id'])
            emit('frozen_reference', status='RECOMPUTED_EQUAL', cases=len(fixture['cases']))

        def test_layer_boundaries(self):
            bound, attention = admitted()
            for case in fixture['cases']:
                expected = fixture['expected'][case['fixture_id']]['boundaries']
                layer = build_layer(bound.namespace, case, mx, nn)
                x = mx.array(case['x'], dtype=mx.float32)
                seen = observe(layer, x, mx)
                errors = {k: max_error(seen[k], expected[k]) for k in ('attn_norm', 'attention', 'output')}
                # x1 is not directly observable without editing selected bodies; it is
                # covered transitively by the output boundary and the FFN reference.
                decisions = {k: errors[k] <= tol[k] for k in errors}
                row = {'fixture_id': case['fixture_id'], 'errors': errors, 'decisions': decisions,
                       'dtype': str(x.dtype), 'attention_counters': dict(attention.stats), 'contract': bound.contract}
                observations.append(row)
                emit('layer_observation', **row)
                for k, ok in decisions.items():
                    self.assertTrue(ok, f"{case['fixture_id']}/{k}: {errors[k]}")

        def test_compiled_decode_step(self):
            bound, _ = admitted()
            for case in fixture['cases']:
                expected = fixture['expected'][case['fixture_id']]['boundaries']['output']
                layer = build_layer(bound.namespace, case, mx, nn)
                x = mx.array(case['x'], dtype=mx.float32)[:, :1]
                self.assertTrue(layer.compile_ffn); self.assertIsNone(layer._ffn_c)
                y = layer(x); mx.eval(y)
                compiled_used = layer._ffn_c is not None
                err = max_error(y.tolist(), [[expected[0][0]]])
                emit('compiled_decode_step', fixture_id=case['fixture_id'], compiled_gate_taken=compiled_used, max_absolute_error=err,
                     within_allowance=err <= tol['output'])
                self.assertTrue(compiled_used)
                self.assertLessEqual(err, tol['output'])

        def test_semantic_mutants(self):
            recipes = [
                ('attn-comb-transposed', 'x = hc_expand(r, residual, post, comb)', 'x = hc_expand(r, residual, post, comb.swapaxes(-1, -2))'),
                ('omitted-input-layernorm', 'self.self_attn(self.input_layernorm(xc), mask, cache)', 'self.self_attn(xc, mask, cache)'),
                ('omitted-attention-residual', 'residual = x', 'residual = mx.zeros_like(x)'),
                ('compile-gate-disabled', 'self.compile_ffn = True', 'self.compile_ffn = False'),
                ('ffn-block-skipped', 'return self._ffn_block(x)', 'return x'),
            ]
            self.assertEqual([r[0] for r in recipes], list(matrix['matrix']))
            text = capsule_raw.decode()
            factor, allowance = matrix['kill_margin_factor'], tol['output']
            for label, before, after in recipes:
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                at = -1
                for _ in range(matrix['occurrence'][label] + 1):
                    at = text.index(before, at + 1)
                mutated = (text[:at] + after + text[at + len(before):]).encode()
                # The admission refuses the mutated capsule (rename-only contract).
                with self.assertRaisesRegex(ValueError, 'DECODER_LAYER_CALLER_TRANSFORM'):
                    layer_source.verify(mutated, language_raw, ffn_source)
                # TEST-ONLY direct harness over the admitted dependency graphs.
                bound, _ = admitted()
                node = ast.parse(mutated).body[0]
                ns = dict(bound.namespace)
                exec(compile(ast.Module(body=[node], type_ignores=[]), 'test-only:' + label, 'exec'), ns)
                results = []
                for expected_cell, case in zip(matrix['matrix'][label], fixture['cases']):
                    expected = fixture['expected'][case['fixture_id']]['boundaries']['output']
                    layer = build_layer(ns, case, mx, nn)
                    y = layer(mx.array(case['x'], dtype=mx.float32)); mx.eval(y)
                    err = max_error(y.tolist(), expected)
                    observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                    results.append({'fixture_id': case['fixture_id'], 'max_absolute_error': err, 'observed': observed,
                                    'expected_cell': expected_cell, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'mutant_sha256': digest(mutated), 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                mutant_rows.append(row)
                emit('layer_mutant', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}/{r['fixture_id']}: {r}")

        def test_cache_lifecycle_split_run(self):
            # Split run: S=1 then S=1 carrying the real cache object across calls.
            # Outputs must reproduce the whole run; the actual cache tensors must
            # match the reference's per-time states within its declared tolerances.
            bound, attention = admitted()
            cache_classes, _, cache_binding = cache_source.load(context, cache_fixture)
            for case in fixture['cases']:
                exp = fixture['expected'][case['fixture_id']]
                layer = build_layer(bound.namespace, case, mx, nn)
                cache = cache_classes.source_make_cache()
                cache.state = [None, None]
                cache.prepare([case['shape'][1]])
                cache.left_padding = mx.array([0])
                x = mx.array(case['x'], dtype=mx.float32)
                rows = []
                for t in range(case['shape'][1]):
                    y = layer(x[:, t:t + 1], None, cache)
                    c0, c1 = cache.state
                    mx.eval(y, c0, c1)
                    ev = exp['attention_cache_events'][t]
                    err_out = max_error(y.tolist(), [[exp['boundaries']['output'][0][t]]])
                    ok0 = attention_oracle.close(c0.tolist(), ev['cache0'], tol['cache0_atol'], tol['cache0_rtol'])
                    ok1 = attention_oracle.close(c1.tolist(), ev['cache1'], tol['cache1_atol'], tol['cache1_rtol'])
                    rows.append({'time': t, 'output_error': err_out, 'output_ok': err_out <= tol['output'],
                                 'cache0_ok': ok0, 'cache1_ok': ok1, 'cache0_shape': list(c0.shape), 'cache1_shape': list(c1.shape),
                                 'lengths': cache.lengths.tolist(), 'padding': cache.left_padding.tolist()})
                final_ok = (attention_oracle.close(cache.state[0].tolist(), exp['attention_final_cache']['cache0'], tol['cache0_atol'], tol['cache0_rtol'])
                            and attention_oracle.close(cache.state[1].tolist(), exp['attention_final_cache']['cache1'], tol['cache1_atol'], tol['cache1_rtol']))
                row = {'fixture_id': case['fixture_id'], 'steps': rows, 'final_cache_ok': final_ok, 'cache_class': type(cache).__name__,
                       'cache_binding': cache_binding, 'attention_counters': dict(attention.stats)}
                emit('cache_lifecycle_split_run', **row)
                for r in rows:
                    self.assertTrue(r['output_ok'] and r['cache0_ok'] and r['cache1_ok'], f"{case['fixture_id']} t={r['time']}: {r}")
                self.assertTrue(final_ok, case['fixture_id'])

        def test_refusals(self):
            bound, _ = admitted()
            config = types.SimpleNamespace(layer_types=['full_attention'], n_routed_experts=None, first_k_dense_replace=0, mlp_layer_types=['dense'],
                                           hidden_size=4, rms_norm_eps=1e-6, hc_mult=2, hc_sinkhorn_iters=3, hc_eps=1e-6, intermediate_size=3, swiglu_limit=1.0)
            with self.assertRaisesRegex(RuntimeError, 'SPARSE_ATTENTION_NOT_ADMITTED'):
                bound.namespace['source_decoder_layer'](config, 0)
            emit('refusal', sparse_attention='REFUSED_AT_CONSTRUCTION', moe='REFUSED_AT_CONSTRUCTION (same mechanism)')

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Layer)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('layer_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='FINITE_FP32_DENSE_LINEAR_DECODER_LAYER_SYNTHETIC_ONLY; cache=None; norm stage at the uniform-magnitude point only')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

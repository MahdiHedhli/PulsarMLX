"""Two-layer GLM-5.3-Flash stack (embedding -> (linear, dense) -> (sparse, MoE) -> mean -> norm -> lm_head)
against the composed frozen oracle, in the successor child; make_cache on the real LanguageModel.

Slice 1: prefill, batch 1, cache None (the model builds the causal mask for the
sparse layer and None for the linear layer). Observed boundaries: layer-0
output streams, layer-1 attention-input norm, indexer top-k, attention output,
x1 streams, FFN-input norm, MoE output, layer-1 output streams, pooled state,
final norm and logits. Mutants are decided cell by cell against the matrix
frozen from oracle variants.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json'
LINEAR_FIXTURE = 'fixtures/research/glm53-flash-linear-attention-v1/fixtures.json'
CACHE_FIXTURE = 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'
BOUNDARIES = ('layer0_output', 'layer1_attn_norm', 'layer1_attention', 'layer1_x1', 'layer1_ffn_norm', 'layer1_mlp',
              'layer1_output', 'pooled', 'final_norm', 'logits')


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


def assign(owner, dotted, value):
    parts = dotted.split('.')
    for part in parts[:-1]:
        owner = getattr(owner, part)
    setattr(owner, parts[-1], value)


def build(ns, case, mx):
    A = lambda v: mx.array(v, dtype=mx.float32)
    config = types.SimpleNamespace(**case['config'], index_kpool_compress=True)
    model = ns['source_language_model'](config)
    model.model.embed_tokens.weight = A(case['embedding']); model.lm_head.weight = A(case['lm_head']); model.model.norm.weight = A(case['norm_weight'])
    l0, l1 = model.model.layers
    for layer, spec in ((l0, case['layer0']), (l1, case['layer1'])):
        for hc_name in ('attn_hc', 'ffn_hc'):
            for p in ('fn', 'base', 'scale'):
                setattr(getattr(layer, hc_name), p, A(spec[hc_name][p]))
    for p in ('gate', 'up', 'down'):
        getattr(l0.mlp, p + '_proj').weight = A(case['layer0']['ffn'][p])
    for name, value in case['layer0']['linear_parameters'].items():
        assign(l0.self_attn, name, A(value))
    sw, ix = case['layer1']['sparse']['weights'], case['layer1']['sparse']['indexer']
    sa = l1.self_attn
    for name in ('q_a_proj', 'q_b_proj', 'kv_a_proj_with_mqa', 'embed_q', 'unembed_out', 'o_proj', 'q_a_layernorm', 'kv_a_layernorm'):
        getattr(sa, name).weight = A(sw[name])
    sa.indexer.wq_b.weight = A(ix['wq_b']); sa.indexer.wk.weight = A(ix['wk']); sa.indexer.k_norm.weight = A(ix['k_norm_weight'])
    sa.indexer.k_norm.bias = A(ix['k_norm_bias']); sa.indexer.weights_proj.weight = A(ix['weights_proj'])
    sa.indexer.index_kpool_compress_ape = A(ix['compress_ape']); sa.indexer.index_kpool_compress_gate = A(ix['compress_gate'])
    moe = case['layer1']['moe']
    l1.mlp.gate.weight = A(moe['gate_weight']); l1.mlp.gate.e_score_correction_bias = A(moe['gate_bias'])
    for p in ('gate', 'up', 'down'):
        getattr(l1.mlp.switch_mlp, p + '_proj').weight = A(moe['experts'][p])
        getattr(l1.mlp.shared_experts, p + '_proj').weight = A(moe['shared'][p])
    return model


def observe(model, ids, mx):
    """Wrap around unchanged calls; copy values; restore the original objects."""
    seen = {}
    inner = model.model
    l0, l1 = inner.layers
    saved = {'l0': l0, 'l1': l1, 'in_norm': l1.input_layernorm, 'attn': l1.self_attn, 'post_norm': l1.post_attention_layernorm,
             'mlp': l1.mlp, 'indexer': l1.self_attn.indexer, 'ffn_block': l1._ffn_block, 'norm': inner.norm, 'head': model.lm_head}
    def rec(key, r):
        mx.eval(r); seen[key] = r[0].tolist(); return r
    class ObservedLayer:
        def __init__(self, key, layer):
            self.key, self.layer, self.is_linear = key, layer, layer.is_linear
        def __call__(self, h, mask=None, cache=None):
            return rec(self.key, self.layer(h, mask=mask, cache=cache))
    inner.layers[0] = ObservedLayer('layer0_output', l0)
    inner.layers[1] = ObservedLayer('layer1_output', l1)
    l1.input_layernorm = lambda v: rec('layer1_attn_norm', saved['in_norm'](v))
    def observed_indexer(x, qr, m, cache=None):
        r = saved['indexer'](x, qr, m, cache=cache)
        if r is None:
            seen['layer1_topk'] = None
        else:
            mx.eval(r); seen['layer1_topk'] = r[0, 0].tolist()
        return r
    saved['attn'].indexer = observed_indexer
    l1.self_attn = lambda v, mask=None, cache=None: rec('layer1_attention', saved['attn'](v, mask, cache))
    l1._ffn_block = lambda x: saved['ffn_block'](rec('layer1_x1', x))
    l1.post_attention_layernorm = lambda v: rec('layer1_ffn_norm', saved['post_norm'](v))
    l1.mlp = lambda v: rec('layer1_mlp', saved['mlp'](v))
    inner.norm = lambda v: rec('final_norm', saved['norm'](rec('pooled', v)))
    model.lm_head = lambda v: rec('logits', saved['head'](v))
    try:
        out = model(mx.array([ids], dtype=mx.int32))
        mx.eval(out.logits)
    finally:
        inner.layers[0] = saved['l0']; inner.layers[1] = saved['l1']; l1.input_layernorm = saved['in_norm']; l1.self_attn = saved['attn']
        saved['attn'].indexer = saved['indexer']; l1._ffn_block = saved['ffn_block']; l1.post_attention_layernorm = saved['post_norm']
        l1.mlp = saved['mlp']; inner.norm = saved['norm']; model.lm_head = saved['head']
    return seen, out


def run(context, backend, mx, nn, refs, sources):
    """refs: layer_run, attention_reference, accepted_recurrence, ffn_run, hc, sparse_run, moe_run, router_reference, stack_run.
    sources: ffn, attention, cache, rc, moe, sparse, stack (component namespaces)."""
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    linear_fixture = json.loads(context.read_verified(root / LINEAR_FIXTURE))
    cache_fixture = json.loads(context.read_verified(root / CACHE_FIXTURE))
    capsule_raw = context.read_verified(root / sources['stack'].CAPSULE)
    language_raw = context.read_verified(root / sources['ffn'].LANGUAGE)
    cache_raw = context.read_verified(root / sources['stack'].CACHE)
    base_raw = context.read_verified(root / sources['sparse'].BASE)
    mla_raw = context.read_verified(root / sources['sparse'].MLA)
    switch_raw = context.read_verified(root / sources['moe'].SWITCH)
    moe_capsule = context.read_verified(root / sources['moe'].CAPSULE)
    sparse_capsule = context.read_verified(root / sources['sparse'].CAPSULE)
    tol = fixture['tolerances']
    matrix = fixture['expected_kill_matrix']
    emit('stack_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), backend=backend, actual_default_device=str(mx.default_device()))

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
        return stack, {'moe': moe.contract, 'sparse': sparse.contract, 'cache': cache_binding, 'gate': gate['record']}

    def mutant_namespace(bound, mutated):
        ns = {k: v for k, v in bound.namespace.items() if k not in ('Glm5NextDecoderLayer', 'Glm5NextModel', 'source_language_model')}
        for n in ast.parse(mutated).body:
            exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
        return ns

    observations, mutant_rows = [], []

    class Stack(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for case in fixture['cases']:
                self.assertEqual(refs['stack_run'](case, refs), fixture['expected'][case['fixture_id']], case['fixture_id'])
            emit('frozen_reference', status='RECOMPUTED_EQUAL')

        def test_stack_boundaries(self):
            bound, contracts = admitted()
            for case in fixture['cases']:
                exp = fixture['expected'][case['fixture_id']]
                model = build(bound.namespace, case, mx)
                seen, out = observe(model, case['ids'], mx)
                errors = {k: max_error(seen[k], exp[k]) for k in BOUNDARIES if k in seen}
                errors['logits_returned'] = max_error(out.logits[0].tolist(), exp['logits'])
                row = {'fixture_id': case['fixture_id'], 'errors': errors, 'topk_equal': seen['layer1_topk'] == exp['layer1_topk'],
                       'candidate_topk': seen['layer1_topk'], 'observed_boundaries': sorted(errors), 'contracts': contracts,
                       'layer0_clamp_active_elements': exp['layer0_clamp_active_elements'], 'moe_clamp_active_elements': exp['moe_clamp_active_elements']}
                row['pass'] = row['topk_equal'] and all(errors[k] <= tol.get(k, tol['logits']) for k in errors)
                observations.append(row); emit('stack_observation', **row)
                self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k != 'contracts'}))

        def test_make_cache_on_real_classes(self):
            bound, _ = admitted()
            model = build(bound.namespace, fixture['cases'][0], mx)
            caches = model.make_cache()
            dep = bound.dependency_namespace
            self.assertEqual(len(caches), 2)
            self.assertIsInstance(caches[0], bound.namespace['ArraysCache']); self.assertEqual(len(caches[0].cache), 2)
            self.assertIsInstance(caches[1], dep['CacheList'])
            self.assertTrue(all(isinstance(caches[1][i], dep['KVCache']) and caches[1][i].keys is None and caches[1][i].offset == 0 for i in range(2)))
            self.assertEqual([l.is_linear for l in model.layers], [True, False])
            with self.assertRaisesRegex(RuntimeError, 'DSV32_SANITIZE_NOT_ADMITTED'):
                model.sanitize({})
            with self.assertRaisesRegex(RuntimeError, 'QUANTIZED_KV_CACHE_NOT_ADMITTED'):
                caches[1][0].to_quantized()
            emit('make_cache', structure=['ArraysCache(size=2)', 'CacheList(KVCache(), KVCache())'], layer_types=[l.is_linear for l in model.layers],
                 sanitize='REFUSED', quantized_kv_cache='REFUSED')

        def test_semantic_mutants(self):
            recipes = [
                ('mean-replaced-by-stream0', 'h = h.mean(axis=2)', 'h = h[:, :, 0, :]'),
                ('mean-replaced-by-sum', 'h = h.mean(axis=2)', 'h = h.sum(axis=2)'),
                ('final-norm-omitted', 'return self.norm(h)', 'return h'),
                ('lm-head-tied-to-embedding', 'out = self.lm_head(out)', 'out = self.model.embed_tokens.as_linear(out)'),
                ('linear-layer-given-attention-mask', 'mask = ssm_mask if layer.is_linear else fa_mask', 'mask = fa_mask'),
                ('sparse-layer-mask-dropped', 'mask = ssm_mask if layer.is_linear else fa_mask', 'mask = ssm_mask'),
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
                results = []
                for expected_cell, case in zip(matrix['matrix'][label], fixture['cases']):
                    expected = fixture['expected'][case['fixture_id']]['logits']
                    try:
                        model = build(ns, case, mx)
                        out = model(mx.array([case['ids']], dtype=mx.int32)); mx.eval(out.logits)
                        err = max_error(out.logits[0].tolist(), expected); reason = 'value' if err != float('inf') else 'nonfinite_or_shape'
                    except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
                        err, reason = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)[:160]
                    observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                    results.append({'fixture_id': case['fixture_id'], 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason,
                                    'observed': observed, 'expected_cell': expected_cell, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'mutant_sha256': digest(mutated), 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                mutant_rows.append(row); emit('stack_mutant', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Stack)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('stack_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='FINITE_FP32_GLM5NEXT_TWO_LAYER_STACK_PREFILL_SYNTHETIC_ONLY; batch 1; cache None; make_cache structure only; no decode')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

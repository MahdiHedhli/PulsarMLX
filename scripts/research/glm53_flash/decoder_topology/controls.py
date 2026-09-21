"""45-layer topology at tiny width: structure and prefill/decode self-consistency, in the successor child.

NO numeric reference: this operation is structural and self-consistent by
construction and is never reported as an oracle qualification. The admitted
LanguageModel is instantiated with the retained config's real layer pattern
(45 layers, 34 linear / 11 sparse, dense MLP for the first 3), every width
tiny, parameters drawn by the candidate's mx.random from the frozen init
recipe. Checks: per-layer types and cache routing; finite logits; a 5-token
prefill followed by five decode steps equals ten single-token steps at every
position (every call inside the admitted linear kernel domain S <= 5) (causal self-consistency
through every layer, both cache kinds and the compiled decode FFN); linear
cache slots and KVCache offsets advance; two structural controls (mask routing
swapped; caches dropped) must break the equivalence or be rejected.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-topology-v1/fixtures.json'


def emit(event, **values):
    print(json.dumps({'event': event, **values}, sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _flatten(tree, prefix=''):
    if isinstance(tree, dict):
        for k, v in tree.items():
            yield from _flatten(v, prefix + k + '.')
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            yield from _flatten(v, prefix + str(i) + '.')
    else:
        yield prefix[:-1], tree


def build(ns, case, mx):
    config = types.SimpleNamespace(**case['config'], index_kpool_compress=True)
    model = ns['source_language_model'](config)
    mx.random.seed(case['init']['seed'])
    weights = []
    for name, value in _flatten(model.parameters()):
        for needle, kind, arg in case['init']['rules']:
            if needle in name:
                if kind == 'const':
                    new = mx.array(arg, dtype=mx.float32)
                elif kind == 'uniform':
                    new = mx.random.uniform(-arg, arg, value.shape)
                else:
                    new = 1.0 + mx.random.uniform(-arg, arg, value.shape)
                break
        weights.append((name, new.astype(mx.float32)))
    model.load_weights(weights, strict=True)
    mx.eval(model.parameters())
    return model


def max_abs_diff(a, b, mx):
    d = mx.abs(a - b); mx.eval(d); v = d.max().item()
    return v if math.isfinite(v) else float('inf')


def logits_paths(model, ids, S0, mx):
    """Returns (prefill+decode logits [T,V], stepwise logits [T,V], caches after path 1). Every call keeps S <= 5 (admitted kernel domain)."""
    x = lambda ts: mx.array([ts], dtype=mx.int32)
    caches = model.make_cache()
    pre = model(x(ids[:S0]), cache=caches).logits[0]
    rows = [pre]
    for t in range(S0, len(ids)):
        rows.append(model(x([ids[t]]), cache=caches).logits[0])
    mixed = mx.concatenate(rows, axis=0); mx.eval(mixed)
    caches2 = model.make_cache()
    steps = [model(x([ids[t]]), cache=caches2).logits[0] for t in range(len(ids))]
    stepwise = mx.concatenate(steps, axis=0); mx.eval(stepwise)
    return mixed, stepwise, caches


def run(context, backend, mx, nn, refs, sources, stack_controls):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    case = fixture['cases'][0]; expected = fixture['expected'][case['fixture_id']]
    capsule_raw = context.read_verified(root / sources['stack'].CAPSULE)
    language_raw = context.read_verified(root / sources['ffn'].LANGUAGE)
    linear_fixture = json.loads(context.read_verified(root / stack_controls.LINEAR_FIXTURE))
    cache_fixture = json.loads(context.read_verified(root / stack_controls.CACHE_FIXTURE))
    cache_raw = context.read_verified(root / sources['stack'].CACHE)
    base_raw = context.read_verified(root / sources['sparse'].BASE)
    mla_raw = context.read_verified(root / sources['sparse'].MLA)
    switch_raw = context.read_verified(root / sources['moe'].SWITCH)
    moe_capsule = context.read_verified(root / sources['moe'].CAPSULE)
    sparse_capsule = context.read_verified(root / sources['sparse'].CAPSULE)
    upstream_config = context.read_verified(root / 'scripts/research/glm53_flash/decoder_topology/upstream-config.json')
    emit('topology_binding', fixture_sha256=digest(raw), upstream_config_sha256=digest(upstream_config), backend=backend, actual_default_device=str(mx.default_device()),
         scope='STRUCTURAL AND SELF-CONSISTENT ONLY; no numeric reference')

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

    observations, control_rows = [], []
    ids, S0 = case['schedule']['ids'], case['schedule']['prefill_tokens']
    assert fixture['upstream_config_sha256'] == digest(upstream_config)

    class Topology(unittest.TestCase):
        def test_structure_and_self_consistency(self):
            bound, cache_binding = admitted()
            dep = bound.dependency_namespace
            model = build(bound.namespace, case, mx)
            layers = model.layers
            self.assertEqual(len(layers), 45)
            self.assertEqual([l.is_linear for l in layers], expected['is_linear'])
            self.assertEqual([type(l.mlp).__name__ for l in layers], ['ClampedMLP' if i not in expected['moe_layers'] else 'source_moe' for i in range(45)])
            caches = model.make_cache()
            self.assertEqual([type(c).__name__ for c in caches], expected['cache_types'])
            mixed, stepwise, caches_after = logits_paths(model, ids, S0, mx)
            finite = bool(mx.all(mx.isfinite(mixed)).item()) and bool(mx.all(mx.isfinite(stepwise)).item())
            d_mixed = d_step = max_abs_diff(mixed, stepwise, mx)
            per_position = [max_abs_diff(mixed[t], stepwise[t], mx) for t in range(len(ids))]
            lin_ok = all(caches_after[i].cache[0] is not None and caches_after[i].cache[1] is not None for i in expected['linear_layers'])
            kv_ok = all(caches_after[i][0].offset == len(ids) and caches_after[i][1].offset == len(ids) for i in expected['sparse_layers'])
            pool_T = [caches_after[i][1]._pool[3] if getattr(caches_after[i][1], '_pool', None) is not None else None for i in expected['sparse_layers']]
            compiled = all(l._ffn_c is not None for l in layers)
            row = {'fixture_id': case['fixture_id'], 'layers': 45, 'linear_layers': len(expected['linear_layers']), 'sparse_layers': len(expected['sparse_layers']),
                   'moe_layers': len(expected['moe_layers']), 'logits_finite': finite, 'prefill5_decode5_vs_stepwise10': d_step, 'paths': case['schedule']['paths'],
                   'per_position_prefill_decode': per_position, 'linear_cache_slots_present': lin_ok, 'kv_offsets_at_T': kv_ok, 'indexer_pool_T_after': pool_T,
                   'compiled_ffn_on_all_layers_after_decode': compiled, 'parameters': sum(1 for _ in _flatten(model.parameters())),
                   'contract': bound.contract, 'cache_binding': cache_binding}
            row['pass'] = (finite and d_step <= expected['equivalence_tolerance'] and lin_ok and kv_ok and compiled
                           and all(t == len(ids) for t in pool_T))
            observations.append(row); emit('topology_observation', **row)
            self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k not in ('contract', 'cache_binding')}))

        def test_structural_controls(self):
            recipes = [('mask-routing-swapped', 'mask = ssm_mask if layer.is_linear else fa_mask', 'mask = fa_mask if layer.is_linear else ssm_mask'),
                       ('layer-caches-dropped', 'h = layer(h, mask=mask, cache=c)', 'h = layer(h, mask=mask, cache=None)')]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(fixture['structural_controls']))
            text = capsule_raw.decode()
            bound, _ = admitted()
            for label, before, after in recipes:
                self.assertEqual(text.count(before), 1, label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_STACK_(CALLER_TRANSFORM|CLOSURE)'):
                    sources['stack'].verify_capsule(mutated, language_raw, sources['ffn'])
                ns = mutant_namespace(bound, mutated)
                try:
                    model = build(ns, case, mx)
                    mixed, stepwise, _ = logits_paths(model, ids, S0, mx)
                    d = max_abs_diff(mixed, stepwise, mx); outcome = 'EQUIVALENCE_BROKEN' if d > expected['equivalence_tolerance'] else 'EQUIVALENCE_HELD'
                except (RuntimeError, ValueError, TypeError, AttributeError, IndexError) as exc:
                    d, outcome = float('inf'), 'REJECTED:' + type(exc).__name__ + ':' + str(exc)[:120]
                row = {'label': label, 'mutant_sha256': digest(mutated), 'max_difference': d if d != float('inf') else 'inf', 'outcome': outcome, 'pass': outcome != 'EQUIVALENCE_HELD'}
                control_rows.append(row); emit('topology_control', **row)
                self.assertTrue(row['pass'], json.dumps(row))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Topology)
    ids_list = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('topology_summary', backend=backend, observations=observations, controls=control_rows,
         scope='STRUCTURAL AND SELF-CONSISTENT ONLY; 45-layer real pattern at tiny width; synthetic seeded parameters; no numeric reference; not an oracle qualification')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids_list,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

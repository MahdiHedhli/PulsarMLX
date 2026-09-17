"""Loading path end to end, in the successor child: synthetic converted checkpoint -> repack() -> ExpertStore ->
patch_model() over the admitted stack -> strict resident load -> forward == resident-quantized model.

STRUCTURAL + EQUIVALENCE (no numeric oracle at hidden 64). The checkpoint directory is written into the child's
work directory: the admitted LanguageModel's parameter names, the seeded-init resident tensors, and the graph-15
frozen 4-bit/g64 stacked routed experts (uint32 words, scales, biases) under model.layers.1.mlp.switch_mlp.*.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-load-offload-v1/fixtures.json'


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


def stacked_arrays(case, mx):
    q = case['quantized_experts']
    out = {}
    for p in ('gate', 'up', 'down'):
        out[f"{case['expert_key']}.{p}_proj.weight"] = mx.array([e['words'] for e in q[p]], dtype=mx.uint32)
        out[f"{case['expert_key']}.{p}_proj.scales"] = mx.array([e['scales'] for e in q[p]], dtype=mx.float32)
        out[f"{case['expert_key']}.{p}_proj.biases"] = mx.array([e['biases'] for e in q[p]], dtype=mx.float32)
    return out


def write_checkpoint(model, case, build, mx):
    build.mkdir(parents=True, exist_ok=True)
    tensors = {k: v for k, v in _flatten(model.parameters()) if not k.startswith(case['expert_key'] + '.')}
    tensors.update(stacked_arrays(case, mx))
    mx.eval(list(tensors.values()))
    mx.save_safetensors(str(build / 'model.safetensors'), tensors, metadata={'format': 'mlx'})
    (build / 'model.safetensors.index.json').write_text(json.dumps({'metadata': {'total_size': sum(v.nbytes for v in tensors.values())},
                                                                     'weight_map': {k: 'model.safetensors' for k in tensors}}, indent=1))
    (build / 'config.json').write_text(json.dumps(case['config'], indent=1))
    return sorted(tensors)


def resident_quantized(model, bound_quantized, case, mx):
    """Path A: the resident model with QuantizedSwitchLinear experts over the same frozen arrays (graph 15)."""
    ns = bound_quantized.switch_namespace; cfg = case['expert_config']; E = cfg['num_experts']
    glu = model.model.layers[1].mlp.switch_mlp
    arrays = stacked_arrays(case, mx)
    for p, in_dims, out_dims in (('gate', cfg['hidden'], cfg['intermediate']), ('up', cfg['hidden'], cfg['intermediate']), ('down', cfg['intermediate'], cfg['hidden'])):
        q = ns['QuantizedSwitchLinear'](in_dims, out_dims, E, bias=False, group_size=cfg['group_size'], bits=cfg['bits'])
        q.weight = arrays[f"{case['expert_key']}.{p}_proj.weight"]; q.scales = arrays[f"{case['expert_key']}.{p}_proj.scales"]; q.biases = arrays[f"{case['expert_key']}.{p}_proj.biases"]
        setattr(glu, p + '_proj', q)
    return model


def logits_paths(model, ids, S0, mx):
    x = lambda ts: mx.array([ts], dtype=mx.int32)
    caches = model.make_cache()
    rows = [model(x(ids[:S0]), cache=caches).logits[0]] + [model(x([ids[t]]), cache=caches).logits[0] for t in range(S0, len(ids))]
    out = mx.concatenate(rows, axis=0); mx.eval(out)
    return out, caches


def max_abs_diff(a, b, mx):
    d = mx.abs(a - b); mx.eval(d); v = d.max().item()
    return v if math.isfinite(v) else float('inf')


def run(context, backend, mx, nn, np, refs, sources, stack_controls, topology_controls, quantized_source, offload_source, load_source):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    case = fixture['cases'][0]; expected = fixture['expected'][case['fixture_id']]
    capsule_raw = context.read_verified(root / sources['stack'].CAPSULE); language_raw = context.read_verified(root / sources['ffn'].LANGUAGE)
    linear_fixture = json.loads(context.read_verified(root / stack_controls.LINEAR_FIXTURE)); cache_fixture = json.loads(context.read_verified(root / stack_controls.CACHE_FIXTURE))
    cache_raw = context.read_verified(root / sources['stack'].CACHE); base_raw = context.read_verified(root / sources['sparse'].BASE); mla_raw = context.read_verified(root / sources['sparse'].MLA)
    switch_raw = context.read_verified(root / sources['moe'].SWITCH); moe_capsule = context.read_verified(root / sources['moe'].CAPSULE); sparse_capsule = context.read_verified(root / sources['sparse'].CAPSULE)
    offload_raw = context.read_verified(root / offload_source.OFFLOAD); one_bit_raw = context.read_verified(root / load_source.ONE_BIT)
    work = context.roots['work'] / 'load-offload'
    ids, S0 = expected['schedule']['ids'], expected['schedule']['prefill_tokens']
    emit('load_offload_binding', fixture_sha256=digest(raw), offload_sha256=digest(offload_raw), one_bit_sha256=digest(one_bit_raw), backend=backend,
         actual_default_device=str(mx.default_device()), scope='STRUCTURAL + EQUIVALENCE; no numeric oracle; resident weights fp32')

    def admitted():
        ffn = sources['ffn'].load(root, mx, nn)
        attention = sources['attention'].load(context, linear_fixture, None)
        cache_ns, _, cache_binding = sources['cache'].load(context, cache_fixture)
        gate = sources['rc'].Builder(context.phase, mx, nn, context.verify_environment(context.phase)).new()
        moe = sources['moe'].load(moe_capsule, language_raw, switch_raw, mx, nn, sources['ffn'], ffn.namespace, gate['caller'])
        sparse = sources['sparse'].load(sparse_capsule, language_raw, mla_raw, base_raw, mx, nn, sources['ffn'])
        stack = sources['stack'].load(capsule_raw, language_raw, cache_raw, base_raw, mx, nn, sources['ffn'], sources['sparse'],
                                      {'ffn_namespace': ffn.namespace, 'attention_namespace': attention.namespace, 'cache_namespace': cache_ns,
                                       'moe_class': moe.namespace['source_moe'], 'sparse_class': sparse.namespace['source_sparse_attention']})
        quantized = quantized_source.load(switch_raw, mla_raw, mx, nn, sources['ffn'], sources['moe'], sources['sparse'], ffn.namespace)
        offload = offload_source.load(offload_raw, switch_raw, mx, nn, np, sources['ffn'], sources['moe'])
        loader = load_source.load(offload_raw, one_bit_raw, mx, nn, np, sources['ffn'], sources['moe'], offload_source, offload)
        return stack, quantized, offload, loader, cache_binding

    def build_fresh(stack):
        return topology_controls.build(stack.namespace, case, mx)

    def path_b(loader_ns, stack, build, out, budget_gb, eager_ffn_on_patched=True):
        loader_ns['repack'](str(build), str(out))
        model = build_fresh(stack)
        store = loader_ns['patch_model'](model, str(out), expert_cache_gb=budget_gb)
        if eager_ffn_on_patched:
            # FINDING (graph 19): OffloadedSwitchGLU evaluates the routing indices on the host (np.asarray), which
            # mx.compile forbids; the decoder layer compiles its FFN block at B=1,S=1 (compile_ffn). Offloaded
            # layers must therefore run the eager FFN path. This is a runtime configuration, not an edit to any
            # admitted node; the compiled-path crash is kept as a control below.
            for layer in model.layers:
                if type(layer.mlp).__name__ == 'source_moe' and type(layer.mlp.switch_mlp).__name__ == 'OffloadedSwitchGLU':
                    layer.compile_ffn = False
        resident = {}
        for f in sorted(out.glob('resident-*.safetensors')):
            resident.update(mx.load(str(f)))
        model.load_weights(list(resident.items()), strict=True)
        return model, store, sorted(resident)

    observations, control_rows = [], []

    class LoadOffload(unittest.TestCase):
        def test_loading_path(self):
            stack, quantized, offload, loader, cache_binding = admitted()
            build, out = work / 'build', work / 'offloaded'
            reference = build_fresh(stack)
            names = write_checkpoint(reference, case, build, mx)
            # path A: resident quantized experts over the same arrays
            model_a = build_fresh(stack)
            ckpt = mx.load(str(build / 'model.safetensors'))
            model_a.load_weights([(k, v) for k, v in ckpt.items() if not k.startswith(case['expert_key'] + '.')], strict=False)
            model_a = resident_quantized(model_a, quantized, case, mx)
            logits_a, _ = logits_paths(model_a, ids, S0, mx)
            # path B: repack -> patch_model -> strict resident load
            model_b, store, resident_keys = path_b(loader.namespace, stack, build, out, budget_gb=31000 / 1e9)
            files = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
            expert_file = mx.load(str(out / 'experts' / 'layer_0001.safetensors'))
            index = json.loads((out / 'offload_index.json').read_text())
            logits_b, caches_b = logits_paths(model_b, ids, S0, mx)
            glu = model_b.model.layers[1].mlp.switch_mlp
            d = max_abs_diff(logits_a, logits_b, mx)
            row = {'fixture_id': case['fixture_id'], 'checkpoint_tensors': len(names), 'repack_files': files, 'expert_file_keys_equal': sorted(expert_file) == expected['expert_file_keys'],
                   'expert_shapes': {k: list(expert_file['e0.' + k].shape) for k in expected['expert_shapes']}, 'offload_index': index,
                   'resident_keys_exclude_experts': not any(k.startswith(case['expert_key'] + '.') for k in resident_keys), 'resident_count': len(resident_keys),
                   'model_b_params_equal_resident_keys': sorted(k for k, _ in _flatten(model_b.parameters())) == resident_keys,
                   'patched_modules': store.swapped, 'patched_class': type(glu).__name__, 'resolved_quant': list(glu.gate_quant),
                   'store_stats': store.stats(), 'logits_finite': bool(mx.all(mx.isfinite(logits_b)).item()), 'resident_vs_offloaded_logits': d,
                   'contract': {'stack': stack.contract, 'loader': loader.contract}, 'cache_binding': cache_binding}
            row['pass'] = (row['expert_file_keys_equal'] and row['expert_shapes'] == expected['expert_shapes'] and index == expected['offload_index']
                           and row['resident_keys_exclude_experts'] and row['model_b_params_equal_resident_keys'] and store.swapped == expected['patched_modules']
                           and row['resolved_quant'] == expected['resolved_quant'] and row['logits_finite'] and d <= expected['equivalence_tolerance']
                           and all(f in files for f in expected['repack_files']))
            observations.append(row); emit('load_offload_observation', **{k: v for k, v in row.items() if k not in ('contract', 'cache_binding')})
            self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k not in ('contract', 'cache_binding')}))
            with self.assertRaisesRegex(RuntimeError, 'KV_RESERVE_AUTO_BUDGET_NOT_ADMITTED'):
                loader.namespace['patch_model'](build_fresh(stack), str(out))
            emit('refusal', auto_budget='REFUSED', sanitizer_fallback='REFUSED_BY_BINDING')
            # control: with the layer's compiled decode FFN left on, the offloaded decode step is rejected by MLX
            model_c, _, _ = path_b(loader.namespace, stack, build, work / 'offloaded-compiled', budget_gb=31000 / 1e9, eager_ffn_on_patched=False)
            try:
                logits_paths(model_c, ids, S0, mx); outcome = 'DECODE_SUCCEEDED_UNEXPECTEDLY'
            except ValueError as exc:
                outcome = 'REJECTED:' + str(exc)[:120]
            emit('compile_ffn_control', outcome=outcome, finding='OffloadedSwitchGLU inside mx.compile: host eval of indices is forbidden; offloaded layers must run the eager FFN path')
            self.assertTrue(outcome.startswith('REJECTED'), outcome)

        def test_structural_controls(self):
            recipes = [('plan-shared-experts-not-resident', '        if "shared_expert" in name:  # shared_expert / shared_experts -> resident', '        if False:'),
                       ('patch-expert-count-check-inverted', 'and _n_experts(child) == store.num_experts:', 'and _n_experts(child) != store.num_experts:'),
                       ('quant-bits-resolved-as-8', 'merged = {**default_quant, **_quantization_for_path(quantization, path)}', 'merged = {**default_quant, **_quantization_for_path(quantization, path), "bits": 8}'),
                       ('expand-expert-slices-rotated', 'layer[f"e{j}.{mm[\'proj\']}.{mm[\'kind\']}"] = arr[j]', 'layer[f"e{j}.{mm[\'proj\']}.{mm[\'kind\']}"] = arr[(j + 1) % E]')]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(fixture['structural_controls']))
            stack, quantized, offload, loader, _ = admitted()
            text = loader.offload_text
            build = work / 'build'
            if not (build / 'model.safetensors').exists():
                write_checkpoint(build_fresh(stack), case, build, mx)
            model_a = resident_quantized(build_fresh(stack), quantized, case, mx)
            ckpt = mx.load(str(build / 'model.safetensors')); model_a.load_weights([(k, v) for k, v in ckpt.items() if not k.startswith(case['expert_key'] + '.')], strict=False)
            logits_a, _ = logits_paths(model_a, ids, S0, mx)
            for label, before, after in recipes:
                self.assertEqual(text.count(before), 1, label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_LOAD_OFFLOAD_DIGEST'):
                    load_source.verify(mutated, one_bit_raw, sources['ffn'], offload_source)
                # re-execute every loading node from the mutated text into one fresh dict (functions resolve globals from their dict)
                mtree = ast.parse(mutated)
                ns = {k: v for k, v in loader.namespace.items() if k not in load_source.NODES and k not in load_source.CONSTANTS}
                for n in [n for n in mtree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in load_source.CONSTANTS]:
                    exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:constant', 'exec'), ns)
                for name in load_source.NODES:
                    node = sources['ffn']._node(mtree, name)
                    if name == 'patch_model':
                        node = ast.FunctionDef(name=node.name, args=node.args, body=[s for s in node.body if not isinstance(s, ast.ImportFrom)], decorator_list=[], returns=None,
                                               type_params=[]); ast.fix_missing_locations(ast.copy_location(node, sources['ffn']._node(mtree, 'patch_model')))
                    exec(compile(ast.Module(body=[node], type_ignores=[]), 'test-only:' + name, 'exec'), ns)
                out = work / ('mutant-' + label)
                try:
                    model_b, store, _ = path_b(ns, stack, build, out, budget_gb=31000 / 1e9)
                    logits_b, _ = logits_paths(model_b, ids, S0, mx)
                    d = max_abs_diff(logits_a, logits_b, mx); outcome = 'EQUIVALENCE_BROKEN' if d > expected['equivalence_tolerance'] else 'EQUIVALENCE_HELD'
                except (RuntimeError, ValueError, TypeError, AttributeError, IndexError, KeyError) as exc:
                    d, outcome = float('inf'), 'REJECTED:' + type(exc).__name__ + ':' + str(exc)[:140]
                row = {'label': label, 'mutant_sha256': digest(mutated), 'max_difference': d if d != float('inf') else 'inf', 'outcome': outcome,
                       'expected': fixture['structural_controls'][label], 'pass': outcome != 'EQUIVALENCE_HELD'}
                control_rows.append(row); emit('load_offload_control', **row)
                self.assertTrue(row['pass'], json.dumps(row))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LoadOffload)
    test_ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('load_offload_summary', backend=backend, observations=[{k: v for k, v in o.items() if k not in ('contract', 'cache_binding')} for o in observations], controls=control_rows,
         scope='STRUCTURAL + EQUIVALENCE; synthetic converted checkpoint at hidden 64 -> repack -> ExpertStore -> patch_model -> strict resident load -> prefill+decode == resident quantized; resident weights fp32; no real checkpoint; no throughput claim')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=test_ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

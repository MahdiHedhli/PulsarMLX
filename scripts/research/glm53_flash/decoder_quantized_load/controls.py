"""Quantized resident weights, in the successor child: nn.quantize with per-path bits from a config-style block, export,
strict reload (bit-identical), the mixed layout through repack/patch_model, and the DeepSeek-V3.2 quantized kv_b split.

STRUCTURAL + EQUIVALENCE (no numeric oracle at hidden 64). mlx core nn.quantize/QuantizedLinear/QuantizedEmbedding are
the admitted environment's MLX (identity-bound), not upstream code; the class predicate is built from the config block
through the retained _quantization_for_path exactly as mlx-vlm resolves per-path overrides.
"""
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-quantized-load-v1/fixtures.json'


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


def class_predicate(quantization, resolve):
    """mlx-vlm's rule: a module quantizes iff it has to_quantized; per-path overrides from the config block win."""
    def predicate(path, module):
        if not hasattr(module, 'to_quantized'):
            return False
        q = resolve(quantization, path)
        return {'group_size': q['group_size'], 'bits': q['bits']}
    return predicate


def quantize_model(model, quantization, resolve, nn):
    nn.quantize(model, group_size=quantization['group_size'], bits=quantization['bits'], class_predicate=class_predicate(quantization, resolve))
    return model


def logits_paths(model, ids, S0, mx):
    x = lambda ts: mx.array([ts], dtype=mx.int32)
    caches = model.make_cache()
    rows = [model(x(ids[:S0]), cache=caches).logits[0]] + [model(x([ids[t]]), cache=caches).logits[0] for t in range(S0, len(ids))]
    out = mx.concatenate(rows, axis=0); mx.eval(out)
    return out


def max_abs_diff(a, b, mx):
    d = mx.abs(a - b); mx.eval(d); v = d.max().item()
    return v if math.isfinite(v) else float('inf')


def run(context, backend, mx, nn, np, refs, sources, stack_controls, topology_controls, offload_source, load_source):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    case = fixture['cases'][0]; expected = fixture['expected'][case['fixture_id']]; quantization = case['config']['quantization']
    capsule_raw = context.read_verified(root / sources['stack'].CAPSULE); language_raw = context.read_verified(root / sources['ffn'].LANGUAGE)
    linear_fixture = json.loads(context.read_verified(root / stack_controls.LINEAR_FIXTURE)); cache_fixture = json.loads(context.read_verified(root / stack_controls.CACHE_FIXTURE))
    cache_raw = context.read_verified(root / sources['stack'].CACHE); base_raw = context.read_verified(root / sources['sparse'].BASE); mla_raw = context.read_verified(root / sources['sparse'].MLA)
    switch_raw = context.read_verified(root / sources['moe'].SWITCH); moe_capsule = context.read_verified(root / sources['moe'].CAPSULE); sparse_capsule = context.read_verified(root / sources['sparse'].CAPSULE)
    offload_raw = context.read_verified(root / offload_source.OFFLOAD); one_bit_raw = context.read_verified(root / load_source.ONE_BIT)
    dsv32_raw = context.read_verified(context.roots['upstream'] / sources['stack'].DSV32_LANGUAGE)
    work = context.roots['work'] / 'quantized-load'
    ids, S0 = case['schedule']['ids'], case['schedule']['prefill_tokens']
    emit('quantized_load_binding', fixture_sha256=digest(raw), backend=backend, actual_default_device=str(mx.default_device()), mlx_version=mx.__version__,
         scope='STRUCTURAL + EQUIVALENCE; no numeric oracle; nn.quantize is the environment MLX')

    def admitted(allow_quantized_sanitize=False):
        ffn = sources['ffn'].load(root, mx, nn)
        attention = sources['attention'].load(context, linear_fixture, None)
        cache_ns, _, cache_binding = sources['cache'].load(context, cache_fixture)
        gate = sources['rc'].Builder(context.phase, mx, nn, context.verify_environment(context.phase)).new()
        moe = sources['moe'].load(moe_capsule, language_raw, switch_raw, mx, nn, sources['ffn'], ffn.namespace, gate['caller'])
        sparse = sources['sparse'].load(sparse_capsule, language_raw, mla_raw, base_raw, mx, nn, sources['ffn'])
        dsv = sources['stack'].load_dsv32_sanitize(dsv32_raw, mx, sources['ffn'], allow_quantized=allow_quantized_sanitize)
        stack = sources['stack'].load(capsule_raw, language_raw, cache_raw, base_raw, mx, nn, sources['ffn'], sources['sparse'],
                                      {'ffn_namespace': ffn.namespace, 'attention_namespace': attention.namespace, 'cache_namespace': cache_ns,
                                       'moe_class': moe.namespace['source_moe'], 'sparse_class': sparse.namespace['source_sparse_attention'],
                                       'dsv32_model': types.SimpleNamespace(sanitize=dsv.sanitize)})
        offload = offload_source.load(offload_raw, switch_raw, mx, nn, np, sources['ffn'], sources['moe'])
        loader = load_source.load(offload_raw, one_bit_raw, mx, nn, np, sources['ffn'], sources['moe'], offload_source, offload)
        return stack, loader, dsv, cache_binding

    def build_fresh(stack):
        return topology_controls.build(stack.namespace, case, mx)

    observations, control_rows = [], []

    class QuantizedLoad(unittest.TestCase):
        def test_quantize_export_reload_and_mixed_layout(self):
            stack, loader, _, cache_binding = admitted()
            resolve = loader.namespace['_quantization_for_path']
            # (1) quantize the seeded model per the config block; export
            model_q = quantize_model(build_fresh(stack), quantization, resolve, nn)
            params = dict(_flatten(model_q.parameters())); mx.eval(list(params.values()))
            scales_for = sorted({k[:-len('.scales')] for k in params if k.endswith('.scales')})
            bits_by_module = {}
            for m in scales_for:
                w, s = params[m + '.weight'], params[m + '.scales']
                bits_by_module[m] = 32 * w.shape[-1] // (s.shape[-1] * resolve(quantization, m)['group_size'])
            build = work / 'build'; build.mkdir(parents=True, exist_ok=True)
            mx.save_safetensors(str(build / 'model.safetensors'), params, metadata={'format': 'mlx'})
            (build / 'model.safetensors.index.json').write_text(json.dumps({'metadata': {'total_size': sum(v.nbytes for v in params.values())}, 'weight_map': {k: 'model.safetensors' for k in params}}))
            (build / 'config.json').write_text(json.dumps(case['config']))
            logits_q = logits_paths(model_q, ids, S0, mx)
            # (2) fresh model quantized from the config alone, strict reload, bit-identical
            model_r = quantize_model(build_fresh(stack), quantization, resolve, nn)
            ckpt = mx.load(str(build / 'model.safetensors')); model_r.load_weights(list(ckpt.items()), strict=True)
            logits_r = logits_paths(model_r, ids, S0, mx); d_reload = max_abs_diff(logits_q, logits_r, mx)
            # (3) the mixed layout: repack -> quantize fresh -> patch_model -> eager FFN -> strict resident load
            out = work / 'offloaded'; loader.namespace['repack'](str(build), str(out))
            model_b = quantize_model(build_fresh(stack), quantization, resolve, nn)
            store = loader.namespace['patch_model'](model_b, str(out), expert_cache_gb=31000 / 1e9)
            for layer in model_b.layers:
                if type(getattr(layer.mlp, 'switch_mlp', None)).__name__ == 'OffloadedSwitchGLU':
                    layer.compile_ffn = False
            resident = {}
            for f in sorted(out.glob('resident-*.safetensors')):
                resident.update(mx.load(str(f)))
            model_b.load_weights(list(resident.items()), strict=True)
            logits_b = logits_paths(model_b, ids, S0, mx); d_mixed = max_abs_diff(logits_q, logits_b, mx)
            expert_file = mx.load(str(out / 'experts' / 'layer_0001.safetensors'))
            glu = model_b.model.layers[1].mlp.switch_mlp
            row = {'fixture_id': case['fixture_id'], 'scales_present_for': scales_for, 'bits_by_module': bits_by_module, 'parameters': len(params),
                   'reload_max_diff': d_reload, 'mixed_layout_max_diff': d_mixed, 'expert_file_keys_equal': sorted(expert_file) == expected['expert_file_keys'],
                   'resident_count': len(resident), 'resident_has_scales': any(k.endswith('.scales') for k in resident), 'patched_modules': store.swapped,
                   'resolved_expert_quant': [list(glu.gate_quant), list(glu.down_quant)], 'store_stats': store.stats(),
                   'router_gate_unquantized': 'model.layers.1.mlp.gate.scales' not in params, 'contract': {'stack': stack.contract, 'loader': loader.contract}, 'cache_binding': cache_binding}
            row['pass'] = (scales_for == expected['scales_present_for'] and bits_by_module == expected['bits_by_module'] and d_reload == 0.0
                           and d_mixed <= expected['mixed_layout_equivalence_tolerance'] and row['expert_file_keys_equal'] and row['resident_has_scales']
                           and store.swapped == 1 and row['router_gate_unquantized'] and glu.gate_quant == (64, 4, 'affine'))
            observations.append(row); emit('quantized_load_observation', **{k: v for k, v in row.items() if k not in ('contract', 'cache_binding')})
            self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k not in ('contract', 'cache_binding')}))

        def test_dsv32_quantized_kv_b_split(self):
            stack, _, dsv, _ = admitted(allow_quantized_sanitize=True)
            cfg = case['config']; H, dq, dv, kvr = cfg['num_attention_heads'], cfg['qk_nope_head_dim'], cfg['v_head_dim'], cfg['kv_lora_rank']
            mx.random.seed(case['init']['seed'] + 1)
            kv_b = mx.random.uniform(-0.25, 0.25, (H * (dq + dv), kvr))
            bits, g = case['kv_b']['bits'], case['kv_b']['group_size']
            w, s, b = mx.quantize(kv_b, group_size=g, bits=bits); mx.eval(w, s, b)
            model = build_fresh(stack)
            weights = {'model.layers.1.self_attn.kv_b_proj.weight': w, 'model.layers.1.self_attn.kv_b_proj.scales': s, 'model.layers.1.self_attn.kv_b_proj.biases': b}
            out = dsv.sanitize(model, dict(weights))
            p = 'model.layers.1.self_attn.'
            eq = mx.dequantize(out[p + 'embed_q.weight'], out[p + 'embed_q.scales'], out[p + 'embed_q.biases'], group_size=g, bits=bits)
            un = mx.dequantize(out[p + 'unembed_out.weight'], out[p + 'unembed_out.scales'], out[p + 'unembed_out.biases'], group_size=g, bits=bits)
            deq = mx.dequantize(w, s, b, group_size=g, bits=bits).reshape(H, dq + dv, kvr)
            wk = deq[:, :dq, :].swapaxes(-1, -2); wv = deq[:, dq:, :]
            mx.eval(eq, un, wk, wv)
            step = max(mx.abs(out[p + 'embed_q.scales']).max().item(), mx.abs(out[p + 'unembed_out.scales']).max().item())
            d_k, d_v = max_abs_diff(eq, wk, mx), max_abs_diff(un, wv, mx)
            row = {'kv_b_shape': list(kv_b.shape), 'embed_q_shape': list(eq.shape), 'unembed_out_shape': list(un.shape), 'dequantized_split_max_diff': [d_k, d_v],
                   'one_quantization_step': step, 'kv_b_keys_removed': not any(k.startswith(p + 'kv_b_proj') for k in out), 'refused_ops': dsv.refused_ops,
                   'pass': list(eq.shape) == [H, kvr, dq] and list(un.shape) == [H, dv, kvr] and d_k <= step and d_v <= step and not any(k.startswith(p + 'kv_b_proj') for k in out)}
            emit('dsv32_quantized_split', **row)
            self.assertTrue(row['pass'], json.dumps(row))

        def test_structural_controls(self):
            stack, loader, dsv, _ = admitted(allow_quantized_sanitize=True)
            resolve = loader.namespace['_quantization_for_path']
            build = work / 'build'
            if not (build / 'model.safetensors').exists():
                model_q = quantize_model(build_fresh(stack), quantization, resolve, nn); params = dict(_flatten(model_q.parameters())); mx.eval(list(params.values()))
                build.mkdir(parents=True, exist_ok=True); mx.save_safetensors(str(build / 'model.safetensors'), params, metadata={'format': 'mlx'})
            ckpt = mx.load(str(build / 'model.safetensors'))
            outcomes = {}
            # predicate-bits-swapped: experts 8-bit, resident 4-bit -> the checkpoint's scales shapes no longer match
            swapped = {k: ({**v, 'bits': (4 if v.get('bits') == 8 else 8)} if isinstance(v, dict) else v) for k, v in quantization.items()}; swapped['bits'] = 8
            try:
                m = quantize_model(build_fresh(stack), swapped, resolve, nn); m.load_weights(list(ckpt.items()), strict=True); outcomes['predicate-bits-swapped'] = 'LOADED_UNEXPECTEDLY'
            except (ValueError, RuntimeError) as exc:
                outcomes['predicate-bits-swapped'] = 'REJECTED:' + str(exc)[:100]
            # resident-scales-dropped: strip a resident module's scales/biases from the checkpoint
            dropped = {k: v for k, v in ckpt.items() if not (k.startswith('lm_head.') and k.endswith(('scales', 'biases')))}
            try:
                m = quantize_model(build_fresh(stack), quantization, resolve, nn); m.load_weights(list(dropped.items()), strict=True); outcomes['resident-scales-dropped'] = 'LOADED_UNEXPECTEDLY'
            except (ValueError, RuntimeError) as exc:
                outcomes['resident-scales-dropped'] = 'REJECTED:' + str(exc)[:100]
            # kv-b-split-transposed: the quantized branch without the swapaxes yields the wrong split
            text = dsv32_raw.decode(); before = 'v[:, : self.args.qk_nope_head_dim, :].swapaxes(-1, -2)'; self.assertEqual(text.count(before), 1)
            import ast
            model_node = sources['ffn']._node(ast.parse(text.replace(before, 'v[:, : self.args.qk_nope_head_dim, :]', 1)), 'Model')
            fn = next(n for n in model_node.body if isinstance(n, ast.FunctionDef) and n.name == 'sanitize')
            mns = {'__name__': 'test-only-dsv32', 'mx': mx}; exec(compile(ast.Module(body=[fn], type_ignores=[]), 'test-only:dsv32', 'exec'), mns)
            cfg = case['config']; H, dq, dv, kvr = cfg['num_attention_heads'], cfg['qk_nope_head_dim'], cfg['v_head_dim'], cfg['kv_lora_rank']
            mx.random.seed(case['init']['seed'] + 1); kv_b = mx.random.uniform(-0.25, 0.25, (H * (dq + dv), kvr)); w, s, b = mx.quantize(kv_b, group_size=case['kv_b']['group_size'], bits=8)
            p = 'model.layers.1.self_attn.'
            try:
                out = mns['sanitize'](build_fresh(stack), {p + 'kv_b_proj.weight': w, p + 'kv_b_proj.scales': s, p + 'kv_b_proj.biases': b})
                eq = mx.dequantize(out[p + 'embed_q.weight'], out[p + 'embed_q.scales'], out[p + 'embed_q.biases'], group_size=case['kv_b']['group_size'], bits=8); mx.eval(eq)
                deq = mx.dequantize(w, s, b, group_size=case['kv_b']['group_size'], bits=8).reshape(H, dq + dv, kvr); wk = deq[:, :dq, :].swapaxes(-1, -2)
                outcomes['kv-b-split-transposed'] = 'SHAPE_MISMATCH' if list(eq.shape) != [H, kvr, dq] else ('SPLIT_MISMATCH' if max_abs_diff(eq, wk, mx) > 1e-2 else 'MATCHED_UNEXPECTEDLY')
            except (ValueError, RuntimeError) as exc:
                outcomes['kv-b-split-transposed'] = 'REJECTED:' + str(exc)[:100]
            for label, expected_outcome in fixture['structural_controls'].items():
                row = {'label': label, 'outcome': outcomes[label], 'expected': expected_outcome, 'pass': not outcomes[label].endswith('UNEXPECTEDLY')}
                control_rows.append(row); emit('quantized_load_control', **row)
                self.assertTrue(row['pass'], json.dumps(row))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(QuantizedLoad)
    test_ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('quantized_load_summary', backend=backend, observations=[{k: v for k, v in o.items() if k not in ('contract', 'cache_binding')} for o in observations], controls=control_rows,
         scope='STRUCTURAL + EQUIVALENCE; nn.quantize per-path (8-bit resident, 4-bit experts, fp32 router) -> export -> strict reload bit-identical -> mixed layout via repack/patch_model; DSV32 quantized kv_b split; no real checkpoint')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=test_ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

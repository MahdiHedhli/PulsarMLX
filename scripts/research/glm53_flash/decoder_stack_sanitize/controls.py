"""LanguageModel.sanitize + strict load into the admitted stack, against the frozen sanitize reference, in the successor child.

The synthetic checkpoint is built as mx arrays with the tagged dtypes
(bfloat16 for A_log/dt_bias), passed through the admitted sanitize (the
capsule's own method delegating to the retained DeepSeek-V3.2 Model.sanitize
under a tripwire mx), compared key by key against the reference (keys, dtypes,
exact values, dropped keys), strictly loaded into a freshly constructed model,
compared parameter by parameter with the directly built model, and the forward
logits are checked against the frozen stack logits. Mutants are decided
against the matrix frozen from oracle variants.
"""
import ast
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-stack-sanitize-v1/fixtures.json'


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


def checkpoint_arrays(case, mx):
    dt = {'float32': mx.float32, 'bfloat16': mx.bfloat16}
    return {e['key']: mx.array(e['value'], dtype=dt[e['dtype']]) for e in case['checkpoint']}


def run(context, backend, mx, nn, refs, sources, stack_controls, sanitize_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    case = fixture['cases'][0]; expected = fixture['expected'][case['fixture_id']]
    matrix = fixture['expected_kill_matrix']; tol = fixture['tolerances']
    capsule_raw = context.read_verified(root / sources['stack'].CAPSULE)
    language_raw = context.read_verified(root / sources['ffn'].LANGUAGE)
    dsv32_raw = context.read_verified(context.roots['upstream'] / sources['stack'].DSV32_LANGUAGE)
    linear_fixture = json.loads(context.read_verified(root / stack_controls.LINEAR_FIXTURE))
    cache_fixture = json.loads(context.read_verified(root / stack_controls.CACHE_FIXTURE))
    cache_raw = context.read_verified(root / sources['stack'].CACHE)
    base_raw = context.read_verified(root / sources['sparse'].BASE)
    mla_raw = context.read_verified(root / sources['sparse'].MLA)
    switch_raw = context.read_verified(root / sources['moe'].SWITCH)
    moe_capsule = context.read_verified(root / sources['moe'].CAPSULE)
    sparse_capsule = context.read_verified(root / sources['sparse'].CAPSULE)
    stack_case = {**case, 'embedding': None}
    emit('sanitize_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), dsv32_sha256=digest(dsv32_raw), backend=backend,
         actual_default_device=str(mx.default_device()))

    def admitted(capsule=capsule_raw, dsv32=None):
        ffn = sources['ffn'].load(root, mx, nn)
        attention = sources['attention'].load(context, linear_fixture, None)
        cache_ns, _, cache_binding = sources['cache'].load(context, cache_fixture)
        gate = sources['rc'].Builder(context.phase, mx, nn, context.verify_environment(context.phase)).new()
        moe = sources['moe'].load(moe_capsule, language_raw, switch_raw, mx, nn, sources['ffn'], ffn.namespace, gate['caller'])
        sparse = sources['sparse'].load(sparse_capsule, language_raw, mla_raw, base_raw, mx, nn, sources['ffn'])
        dsv = dsv32 or sources['stack'].load_dsv32_sanitize(dsv32_raw, mx, sources['ffn'])
        stack = sources['stack'].load(capsule, language_raw, cache_raw, base_raw, mx, nn, sources['ffn'], sources['sparse'],
                                      {'ffn_namespace': ffn.namespace, 'attention_namespace': attention.namespace, 'cache_namespace': cache_ns,
                                       'moe_class': moe.namespace['source_moe'], 'sparse_class': sparse.namespace['source_sparse_attention'],
                                       'dsv32_model': types.SimpleNamespace(sanitize=dsv.sanitize)})
        return stack, dsv, cache_binding

    def config_of():
        return types.SimpleNamespace(**case['config'], index_kpool_compress=True)

    def sanitize_load_forward(ns, dsv_sanitize=None):
        """Returns (sanitized dict, fresh model, logits) using the namespace's source_language_model."""
        fresh = ns['source_language_model'](config_of())
        sanitized = fresh.sanitize(checkpoint_arrays(case, mx))
        fresh.load_weights(list(sanitized.items()), strict=True)
        out = fresh(mx.array([case['ids']], dtype=mx.int32)); mx.eval(out.logits)
        return sanitized, fresh, out.logits[0].tolist()

    def compare(sanitized, logits, reference_model=None):
        from_ref = expected['parameters']
        keys_ok = set(sanitized) == set(from_ref)
        row = {'keys_equal': keys_ok, 'missing': sorted(set(from_ref) - set(sanitized))[:8], 'extra': sorted(set(sanitized) - set(from_ref))[:8],
               'dropped_absent': all(k not in sanitized for k in expected['dropped_keys'])}
        if keys_ok:
            dtypes = {k: str(v.dtype).split('.')[-1] for k, v in sanitized.items()}
            row['dtype_mismatches'] = sorted(k for k in dtypes if dtypes[k] != from_ref[k]['dtype'])[:8]
            errs = {}
            for k, v in sanitized.items():
                # the reference holds JSON doubles; a float32 parameter is compared against their float32 rounding
                mx.eval(v); errs[k] = max_error(v.tolist(), _fp32(from_ref[k]['value']))
            row['max_parameter_error'] = max(errs.values()); row['parameter_mismatches'] = sorted(k for k, e in errs.items() if e > tol['parameters'])[:8]
        row['logits_error'] = max_error(logits, expected['logits'])
        return row

    observations, mutant_rows = [], []

    class Sanitize(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            got = sanitize_oracle.run(case['checkpoint'], case['config'])
            self.assertEqual(got['parameters'], expected['parameters']); self.assertEqual(got['dropped_keys'], expected['dropped_keys'])
            emit('frozen_reference', status='RECOMPUTED_EQUAL', parameters=len(got['parameters']))

        def test_sanitize_and_strict_load(self):
            bound, dsv, cache_binding = admitted()
            sanitized, fresh, logits = sanitize_load_forward(bound.namespace)
            row = compare(sanitized, logits)
            # loaded parameters equal the directly built model's, exactly
            from_build = {k: v for k, v in sanitized.items()}
            built = stack_controls.build(bound.namespace, json.loads(context.read_verified(root / stack_controls.FIXTURE))['cases'][0], mx)
            flat_built = dict(_tree_flatten(built.parameters())); flat_fresh = dict(_tree_flatten(fresh.parameters()))
            row['built_keys_equal'] = set(flat_built) == set(flat_fresh)
            row['built_max_error'] = max(max_error(flat_fresh[k].tolist(), flat_built[k].tolist()) for k in flat_built) if row['built_keys_equal'] else float('inf')
            row['tripwire_ops'] = list(sources['stack'].DSV32_UNEXECUTED_OPS); row['dsv32_sanitize_ast_sha256'] = dsv.ast_sha256; row['dsv32_mx_ops'] = dsv.mx_ops
            row['pass'] = (row['keys_equal'] and row['dropped_absent'] and not row['dtype_mismatches'] and row['max_parameter_error'] <= tol['parameters']
                           and row['logits_error'] <= tol['logits'] and row['built_keys_equal'] and row['built_max_error'] == 0.0)
            record = {'fixture_id': case['fixture_id'], **row, 'contract': bound.contract, 'cache_binding': cache_binding}
            observations.append(record); emit('sanitize_observation', **record)
            self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items()}))
            with self.assertRaisesRegex(RuntimeError, 'DSV32_FROM_FP8_NOT_ADMITTED'):
                dsv.sanitize(fresh, {'model.layers.0.mlp.gate_proj.weight_scale_inv': mx.zeros((1, 1)), 'model.layers.0.mlp.gate_proj.weight': mx.zeros((1, 1), dtype=mx.uint8)})
            emit('refusal', fp8_dequant='REFUSED')

        def test_semantic_mutants(self):
            recipes = [
                ('mtp-filter-removed', 'capsule', 'weights = {k: v for k, v in weights.items() if "mtp." not in k}', 'weights = dict(weights)'),
                ('hc-rename-collision', 'capsule', 'nk = k.replace(".hc_attn_", ".attn_hc.").replace(".hc_ffn_", ".ffn_hc.")', 'nk = k.replace(".hc_attn_", ".ffn_hc.").replace(".hc_ffn_", ".ffn_hc.")'),
                ('conv-fusion-order-reversed', 'capsule', '[parts["q"], parts["k"], parts["v"]]', '[parts["v"], parts["k"], parts["q"]]'),
                ('conv-axis-move-omitted', 'capsule', 'weights[k] = v.moveaxis(2, 1)', 'weights[k] = v'),
                ('fp32-cast-omitted', 'capsule', 'weights[k] = v.astype(mx.float32)', 'weights[k] = v'),
                ('forget-gate-move-omitted', 'capsule', 'nk = nk[: -len(p)] + "forget_gate." + p', 'nk = nk'),
                ('kv-b-split-not-transposed', 'dsv32', 'v[:, : self.args.qk_nope_head_dim, :].swapaxes(-1, -2)', 'v[:, : self.args.qk_nope_head_dim, :]'),
                ('experts-stack-order-reversed', 'dsv32', 'for e in range(self.args.n_routed_experts)', 'for e in reversed(range(self.args.n_routed_experts))'),
            ]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            capsule_text = capsule_raw.decode(); dsv32_text = dsv32_raw.decode()
            factor, allowance = matrix['kill_margin_factor'], tol['logits']
            bound, dsv, _ = admitted()
            for label, target, before, after in recipes:
                text = capsule_text if target == 'capsule' else dsv32_text
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                if target == 'capsule':
                    with self.assertRaisesRegex(ValueError, 'DECODER_STACK_(CALLER_TRANSFORM|CLOSURE)'):
                        sources['stack'].verify_capsule(mutated, language_raw, sources['ffn'])
                    ns = {k: v for k, v in bound.namespace.items() if k not in ('Glm5NextDecoderLayer', 'Glm5NextModel', 'source_language_model')}
                    for n in ast.parse(mutated).body:
                        exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
                else:
                    with self.assertRaisesRegex(ValueError, 'DECODER_STACK_DSV32_DIGEST'):
                        sources['stack'].load_dsv32_sanitize(mutated, mx, sources['ffn'])
                    model_node = sources['ffn']._node(ast.parse(mutated), 'Model')
                    fn = next(n for n in model_node.body if isinstance(n, ast.FunctionDef) and n.name == 'sanitize')
                    mns = {'__name__': 'test-only-dsv32', 'mx': mx}
                    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'test-only:dsv32-sanitize', 'exec'), mns)
                    ns = {k: v for k, v in bound.namespace.items() if k not in ('Glm5NextDecoderLayer', 'Glm5NextModel', 'source_language_model')}
                    ns['DSV32Model'] = types.SimpleNamespace(sanitize=mns['sanitize'])
                    for n in ast.parse(capsule_raw).body:
                        exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
                expected_cell = matrix['matrix'][label][0]
                try:
                    sanitized, fresh, logits = sanitize_load_forward(ns)
                    row = compare(sanitized, logits)
                    structural = not row['keys_equal'] or bool(row.get('dtype_mismatches')) or not row['dropped_absent']
                    err = float('inf') if structural else max(row['max_parameter_error'], row['logits_error'])
                    reason = 'structural:' + json.dumps({k: row[k] for k in ('missing', 'extra', 'dtype_mismatches') if row.get(k)}) if structural else 'value'
                except (RuntimeError, ValueError, TypeError, AttributeError, KeyError, IndexError) as exc:
                    err, reason = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)[:160]
                observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                result = {'fixture_id': case['fixture_id'], 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason,
                          'observed': observed, 'expected_cell': expected_cell, 'cell_pass': observed == expected_cell,
                          'predicted': matrix['predicted_oracle_variant_error'][label][0]}
                row = {'label': label, 'target': target, 'mutant_sha256': digest(mutated), 'results': [result], 'all_cells_pass': result['cell_pass']}
                mutant_rows.append(row); emit('sanitize_mutant', **row)
                self.assertEqual(observed, expected_cell, f"{label}: {result}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Sanitize)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('sanitize_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='SANITIZE_AND_STRICT_LOAD_SYNTHETIC_HF_NAMING_ONLY; unquantized (no fp8, no scales); two-layer stack; MTP layer and mtp. keys dropped')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1


def _fp32(v):
    import struct
    return [_fp32(x) for x in v] if isinstance(v, list) else struct.unpack('f', struct.pack('f', v))[0]


def _tree_flatten(tree, prefix=''):
    if isinstance(tree, dict):
        for k, v in tree.items():
            yield from _tree_flatten(v, prefix + k + '.')
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            yield from _tree_flatten(v, prefix + str(i) + '.')
    else:
        yield prefix[:-1], tree

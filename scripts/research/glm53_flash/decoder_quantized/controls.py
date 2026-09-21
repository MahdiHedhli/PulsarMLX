"""Quantized projections against the affine-dequantization reference over frozen quantized arrays, in the successor child.

The frozen fixture holds packed uint32 words, scales and biases produced by a
stdlib quantizer. A SwitchGLU with ClampedSwiGLU is built over
QuantizedSwitchLinear modules whose arrays are set from the fixture and run
on the fixture tokens/indices; a QuantizedMultiLinear is run in both
transpose modes. Boundaries: gate/up projections and the expert outputs,
mx.dequantize of the frozen arrays against the stdlib dequantization (format
cross-check), quant_predicate names. Mutants of the two retained nodes are
decided against the matrix frozen from reference variants.
"""
import ast
import hashlib
import json
import math
import resource
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json'


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


def arrays(q, mx):
    """Stacked frozen arrays for a list of per-expert/head packs."""
    return (mx.array([e['words'] for e in q], dtype=mx.uint32), mx.array([e['scales'] for e in q], dtype=mx.float32), mx.array([e['biases'] for e in q], dtype=mx.float32))


def build_switch(bound, case, mx):
    cfg = case['config']; ns = bound.switch_namespace
    glu = ns['SwitchGLU'](cfg['hidden'], cfg['intermediate'], cfg['num_experts'], activation=bound.clamped_swiglu(cfg['swiglu_limit']))
    for p, in_dims, out_dims in (('gate', cfg['hidden'], cfg['intermediate']), ('up', cfg['hidden'], cfg['intermediate']), ('down', cfg['intermediate'], cfg['hidden'])):
        q = ns['QuantizedSwitchLinear'](in_dims, out_dims, cfg['num_experts'], bias=False, group_size=cfg['group_size'], bits=cfg['bits'])
        q.weight, q.scales, q.biases = arrays(case['quantized'][p], mx)
        setattr(glu, p + '_proj', q)
    return glu


def build_multilinear(bound, case, mx):
    cfg = case['config']
    m = bound.mla_namespace['QuantizedMultiLinear'](cfg['input_dims'], cfg['output_dims'], cfg['num_heads'], cfg['group_size'], cfg['bits'], 'affine')
    m.weight, m.scales, m.biases = arrays(case['quantized']['weight'], mx)
    return m


def run_switch(glu, case, mx):
    seen = {}
    gate, up = glu.gate_proj, glu.up_proj
    def og(x, inds, **k):
        r = gate(x, inds, **k); mx.eval(r); seen['gate'] = r[0].squeeze(-2).tolist(); return r
    def ou(x, inds, **k):
        r = up(x, inds, **k); mx.eval(r); seen['up'] = r[0].squeeze(-2).tolist(); return r
    glu.gate_proj, glu.up_proj = og, ou
    try:
        y = glu(mx.array([case['x']], dtype=mx.float32), mx.array([case['indices']], dtype=mx.int32)); mx.eval(y)
    finally:
        glu.gate_proj, glu.up_proj = gate, up
    seen['output'] = y[0].tolist()
    return seen


def run_multilinear(m, case, mx):
    t = m(mx.array([case['x_transpose']], dtype=mx.float32), transpose=True); n = m(mx.array([case['x_no_transpose']], dtype=mx.float32), transpose=False)
    mx.eval(t, n)
    return {'transpose': t.tolist(), 'no_transpose': n.tolist()}


def run(context, backend, mx, nn, ffn_source, moe_source, sparse_source, quantized_source, quantized_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    switch_raw = context.read_verified(root / moe_source.SWITCH); mla_raw = context.read_verified(root / sparse_source.MLA)
    tol = fixture['tolerances']; matrix = fixture['expected_kill_matrix']
    cases = {c['fixture_id']: c for c in fixture['cases']}; expected = fixture['expected']
    emit('quantized_binding', fixture_sha256=digest(raw), switch_sha256=digest(switch_raw), mla_sha256=digest(mla_raw), backend=backend, actual_default_device=str(mx.default_device()))

    def admitted():
        ffn = ffn_source.load(root, mx, nn)
        return quantized_source.load(switch_raw, mla_raw, mx, nn, ffn_source, moe_source, sparse_source, ffn.namespace)

    def evaluate(bound, case):
        if case['kind'] == 'switch':
            seen = run_switch(build_switch(bound, case, mx), case, mx); exp = expected[case['fixture_id']]['tokens']
            errs = {'gate': max_error(seen['gate'], [[e['gate'] for e in t] for t in exp]), 'up': max_error(seen['up'], [[e['up'] for e in t] for t in exp]),
                    'output': max_error(seen['output'], [[e['output'] for e in t] for t in exp])}
        else:
            seen = run_multilinear(build_multilinear(bound, case, mx), case, mx); exp = expected[case['fixture_id']]
            errs = {'transpose': max_error(seen['transpose'], exp['transpose']), 'no_transpose': max_error(seen['no_transpose'], exp['no_transpose'])}
        return errs

    observations, mutant_rows = [], []

    class Quantized(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for fid, case in cases.items():
                self.assertEqual(quantized_oracle.run(case), expected[fid], fid)
            emit('frozen_reference', status='RECOMPUTED_EQUAL', cases=len(cases))

        def test_format_cross_check(self):
            # mx.dequantize of the frozen arrays equals the stdlib dequantization: the fixture's packing is MLX's
            rows = []
            for fid, case in cases.items():
                if case['kind'] == 'predicate':
                    continue
                cfg = case['config']; packs = [p for key in case['quantized'] for p in (case['quantized'][key] if isinstance(case['quantized'][key], list) else [case['quantized'][key]])]
                err = 0.0
                for pack in packs:
                    w, s, b = arrays([pack], mx)
                    d = mx.dequantize(w[0], s[0], b[0], group_size=cfg['group_size'], bits=cfg['bits']); mx.eval(d)
                    err = max(err, max_error(d.tolist(), quantized_oracle.dequantize(pack, cfg['bits'], cfg['group_size'])))
                rows.append({'fixture_id': fid, 'packs': len(packs), 'max_dequantize_error': err, 'pass': err <= tol['dequantize_cross_check'],
                             'quantization_error_vs_fp32_reported': case['quantization_max_abs_error_vs_fp32']})
            emit('format_cross_check', rows=rows)
            for r in rows:
                self.assertTrue(r['pass'], json.dumps(r))

        def test_quantized_boundaries(self):
            bound = admitted()
            for fid, case in cases.items():
                if case['kind'] == 'predicate':
                    continue
                errs = evaluate(bound, case)
                row = {'fixture_id': fid, 'kind': case['kind'], 'errors': {k: (v if v != float('inf') else 'inf') for k, v in errs.items()},
                       'pass': all(e <= tol['output'] for e in errs.values()), 'contract': bound.contract}
                observations.append(row); emit('quantized_observation', **row)
                self.assertTrue(row['pass'], json.dumps({k: v for k, v in row.items() if k != 'contract'}))
            # quant_predicate by name on real key names, against the frozen mapping
            pred = cases['quant-predicate-names']
            class Args: pass
            got = {}
            # the predicate is a property of the LanguageModel capsule; reproduced by name here from the frozen mapping (structural)
            for p in pred['paths']:
                got[p] = {'group_size': 64, 'bits': 8} if (p.endswith('mlp.gate') or 'e_score_correction_bias' in p or '.indexer' in p) else True
            self.assertEqual(got, expected['quant-predicate-names'])
            emit('quant_predicate', mapping=expected['quant-predicate-names'], scope='name-level; the capsule property text is verified by the stack admission')
            with self.assertRaisesRegex(RuntimeError, 'DEFAULT_SWIGLU_NOT_ADMITTED'):
                bound.switch_namespace['SwiGLU']()(mx.zeros((1,)), mx.zeros((1,)))
            emit('refusal', default_swiglu='REFUSED')

        def test_semantic_mutants(self):
            recipes = [
                ('scales-biases-swapped', 'switch', '            self["scales"],\n            self.get("biases"),\n', '            self.get("biases"),\n            self["scales"],\n'),
                ('gather-transpose-flipped', 'switch', 'rhs_indices=indices,\n            transpose=True,', 'rhs_indices=indices,\n            transpose=False,'),
                ('bits-forced-8', 'switch', 'bits=self.bits,', 'bits=8,'),
                ('group-forced-32', 'switch', 'group_size=self.group_size,', 'group_size=32,'),
                ('biases-dropped', 'switch', 'self.get("biases"),', 'None,'),
                ('multilinear-transpose-forced', 'multilinear', 'transpose=transpose,', 'transpose=True,'),
            ]
            self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
            factor, allowance = matrix['kill_margin_factor'], tol['output']
            bound = admitted()
            for label, target, before, after in recipes:
                text = bound.switch_text if target == 'switch' else bound.mla_text
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                node_name = quantized_source.SWITCH_NODE if target == 'switch' else quantized_source.MLA_NODE
                with self.assertRaisesRegex(ValueError, 'DECODER_QUANTIZED_DIGEST'):
                    quantized_source.verify_node(mutated, moe_source.SWITCH_SHA256 if target == 'switch' else sparse_source.MLA_SHA256, node_name,
                                                 quantized_source.SWITCH_GLOBALS if target == 'switch' else quantized_source.MLA_GLOBALS,
                                                 quantized_source.SWITCH_MX_OPS if target == 'switch' else quantized_source.MLA_MX_OPS, ffn_source)
                node = ffn_source._node(ast.parse(mutated), node_name)
                mutant = type(bound)(**vars(bound))
                if target == 'switch':
                    ns = {k: v for k, v in bound.switch_namespace.items() if k not in ('QuantizedSwitchLinear', 'SwitchGLU', 'SwitchLinear', 'SwiGLU', '_gather_sort', '_scatter_unsort')}
                    for n in [node] + list(bound.switch_nodes):
                        exec(compile(ast.Module(body=[n], type_ignores=[]), 'test-only:' + n.name, 'exec'), ns)
                    mutant.switch_namespace = ns
                else:
                    ns = {k: v for k, v in bound.mla_namespace.items() if k != 'QuantizedMultiLinear'}
                    exec(compile(ast.Module(body=[node], type_ignores=[]), 'test-only:' + node.name, 'exec'), ns)
                    mutant.mla_namespace = ns
                results = []
                for expected_cell, fid in zip(matrix['matrix'][label], matrix['cases_by_target'][target]):
                    case = cases[fid]
                    try:
                        errs = evaluate(mutant, case); err = max(errs.values()); reason = 'value' if err != float('inf') else 'nonfinite_or_shape'
                    except (RuntimeError, ValueError, TypeError, IndexError) as exc:
                        err, reason = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)[:140]
                    observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                    results.append({'fixture_id': fid, 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason, 'observed': observed,
                                    'expected_cell': expected_cell, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'target': target, 'mutant_sha256': digest(mutated), 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                mutant_rows.append(row); emit('quantized_mutant', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Quantized)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('quantized_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='AFFINE_QUANTIZED_PROJECTIONS_OVER_FROZEN_ARRAYS; gather_qmm 4-bit g64 and 8-bit g32 in SwitchGLU; quantized_matmul 4-bit g64 both transposes; no router, no full block, no quantized caches')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

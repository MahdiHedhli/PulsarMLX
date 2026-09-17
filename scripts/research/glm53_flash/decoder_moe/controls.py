"""Glm5NextMoE composition against the frozen MoE oracle, in the successor child.

Gate: the router track's Builder (unchanged upstream Glm5NextMoEGate over the
retained selector); experts: SwitchGLU over admitted switch-layer nodes with
ClampedSwiGLU; shared: ClampedMLP from the dense-FFN graph. Observed
boundaries: gate indices/scores, switch output per selected expert (via the
score-weighted combine), shared output and the block output. Mutants are
decided cell by cell against the frozen matrix.
"""
import ast
import hashlib
import json
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-decoder-moe-v1/fixtures.json'


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


def build(ns, case, mx):
    cfg = case['config']
    config = types.SimpleNamespace(**cfg, intermediate_size=cfg['moe_intermediate_size'])
    block = ns['source_moe'](config)
    block.gate.weight = mx.array(case['gate_weight'], dtype=mx.float32)
    block.gate.e_score_correction_bias = mx.array(case['gate_bias'], dtype=mx.float32)
    for p in ('gate', 'up', 'down'):
        getattr(block.switch_mlp, p + '_proj').weight = mx.array(case['experts'][p], dtype=mx.float32)
        getattr(block.shared_experts, p + '_proj').weight = mx.array(case['shared'][p], dtype=mx.float32)
    return block


def observe(block, x, mx):
    seen = {}
    gate, switch, shared = block.gate, block.switch_mlp, block.shared_experts
    def observed_gate(v):
        inds, scores = gate(v); mx.eval(inds, scores); seen['inds'] = inds.tolist(); seen['scores'] = scores.tolist(); return inds, scores
    def observed_switch(v, inds):
        r = switch(v, inds); mx.eval(r); seen['switch'] = r.tolist(); return r
    def observed_shared(v):
        r = shared(v); mx.eval(r); seen['shared'] = r.tolist(); return r
    block.gate, block.switch_mlp, block.shared_experts = observed_gate, observed_switch, observed_shared
    try:
        y = block(x); mx.eval(y)
    finally:
        block.gate, block.switch_mlp, block.shared_experts = gate, switch, shared
    seen['output'] = y.tolist()
    return seen


def run(context, backend, mx, nn, ffn_source, rc_source, rc_oracle, moe_source, moe_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE)
    fixture = json.loads(raw)
    capsule_raw = context.read_verified(root / moe_source.CAPSULE)
    language_raw = context.read_verified(root / ffn_source.LANGUAGE)
    switch_raw = context.read_verified(root / moe_source.SWITCH)
    tol = fixture['tolerances']
    matrix = fixture['expected_kill_matrix']
    emit('moe_binding', fixture_sha256=digest(raw), capsule_sha256=digest(capsule_raw), switch_sha256=digest(switch_raw),
         backend=backend, actual_default_device=str(mx.default_device()))

    def admitted(capsule=capsule_raw):
        ffn = ffn_source.load(root, mx, nn)
        # Builder binds mx/nn origins against the environment manifest (as rc_runtime does),
        # not the inputs manifest.
        gate = rc_source.Builder(context.phase, mx, nn, context.verify_environment(context.phase)).new()
        return moe_source.load(capsule, language_raw, switch_raw, mx, nn, ffn_source, ffn.namespace, gate['caller']), gate['record']

    observations, mutant_rows = [], []

    class MoE(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for case in fixture['cases']:
                r = moe_oracle.run(case, rc_oracle.reference)
                self.assertEqual(r, fixture['expected'][case['fixture_id']], case['fixture_id'])
            emit('frozen_reference', status='RECOMPUTED_EQUAL')

        def test_block_boundaries(self):
            bound, gate_record = admitted()
            for case in fixture['cases']:
                exp = fixture['expected'][case['fixture_id']]['tokens']
                block = build(bound.namespace, case, mx)
                x = mx.array(case['x'], dtype=mx.float32)
                seen = observe(block, x, mx)
                rows = []
                for t, tok in enumerate(exp):
                    inds = seen['inds'][t]; scores = seen['scores'][t]
                    # Selected set must match (order unspecified); scores are compared by expert id.
                    ids_ok = sorted(inds) == sorted(tok['selected_ids'])
                    score_err = max(abs(s - tok['scores_by_id'][str(i)]) for i, s in zip(inds, scores)) if ids_ok else float('inf')
                    # switch output rows follow the candidate's own index order.
                    switch_err = max(max_error(seen['switch'][t][j], tok['experts'][str(i)]) for j, i in enumerate(inds)) if ids_ok else float('inf')
                    row = {'time': t, 'selected_ids_ok': ids_ok, 'candidate_ids': inds, 'score_error': score_err,
                           'switch_error': switch_err, 'shared_error': max_error(seen['shared'][t], tok['shared']),
                           'output_error': max_error(seen['output'][t], tok['output'])}
                    row['pass'] = (ids_ok and score_err <= tol['scores'] and switch_err <= tol['experts']
                                   and row['shared_error'] <= tol['shared'] and row['output_error'] <= tol['output'])
                    rows.append(row)
                record = {'fixture_id': case['fixture_id'], 'rows': rows, 'contract': bound.contract, 'gate_source_record': gate_record}
                observations.append(record); emit('moe_observation', **record)
                for r in rows:
                    self.assertTrue(r['pass'], f"{case['fixture_id']} t={r['time']}: {r}")

        def test_semantic_mutants(self):
            recipes = [
                ('scores-unweighted-combine', 'y = (y * scores[..., None]).sum(axis=-2).astype(y.dtype)', 'y = y.sum(axis=-2).astype(y.dtype)'),
                ('shared-expert-omitted', 'y = y + self.shared_experts(x)', 'y = y'),
                ('expert-score-pairing-reversed', 'y = self.switch_mlp(x, inds)', 'y = self.switch_mlp(x, inds[..., ::-1])'),
                ('combine-axis-wrong', '.sum(axis=-2)', '.sum(axis=-1)'),
                # A limit far above every pre-activation removes the clamp while the
                # admitted (observable) activation path stays in place.
                ('routed-activation-unclamped', 'activation=ClampedSwiGLU(config.swiglu_limit)', 'activation=ClampedSwiGLU(1e30)'),
            ]
            self.assertEqual([r[0] for r in recipes], list(matrix['matrix']))
            text = capsule_raw.decode()
            factor, allowance = matrix['kill_margin_factor'], tol['output']
            for label, before, after in recipes:
                self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
                mutated = text.replace(before, after, 1).encode()
                with self.assertRaisesRegex(ValueError, 'DECODER_MOE_(CALLER_TRANSFORM|CLOSURE)'):
                    moe_source.verify_capsule(mutated, language_raw, ffn_source)
                bound, _ = admitted()
                ns = dict(bound.namespace)
                node = ast.parse(mutated).body[0]
                exec(compile(ast.Module(body=[node], type_ignores=[]), 'test-only:' + label, 'exec'), ns)
                results = []
                for expected_cell, case in zip(matrix['matrix'][label], fixture['cases']):
                    expected = [tok['output'] for tok in fixture['expected'][case['fixture_id']]['tokens']]
                    block = build(ns, case, mx)
                    try:
                        y = block(mx.array(case['x'], dtype=mx.float32)); mx.eval(y)
                        err = max_error(y.tolist(), expected); reason = 'value'
                    except (RuntimeError, ValueError) as exc:
                        # A refused stub (RuntimeError) or an MLX shape rejection (ValueError)
                        # raised by the mutated block is a kill by rule, never a survivor.
                        err, reason = float('inf'), 'rejected:' + type(exc).__name__ + ':' + str(exc)
                    observed = 'KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'
                    results.append({'fixture_id': case['fixture_id'], 'max_absolute_error': err if err != float('inf') else 'inf', 'reason': reason,
                                    'observed': observed, 'expected_cell': expected_cell, 'cell_pass': observed == expected_cell})
                row = {'label': label, 'mutant_sha256': digest(mutated), 'results': results, 'all_cells_pass': all(r['cell_pass'] for r in results)}
                mutant_rows.append(row); emit('moe_mutant', **row)
                for r in results:
                    self.assertEqual(r['observed'], r['expected_cell'], f"{label}: {r}")

        def test_refusals(self):
            bound, _ = admitted()
            with self.assertRaisesRegex(RuntimeError, 'DEFAULT_SWIGLU_NOT_ADMITTED'):
                bound.switch_namespace['SwiGLU']()(mx.zeros((1,)), mx.zeros((1,)))
            with self.assertRaisesRegex(RuntimeError, 'QUANTIZED_SWITCH_LINEAR_NOT_ADMITTED'):
                bound.switch_namespace['SwitchLinear'](4, 3, 4, bias=False).to_quantized()
            emit('refusal', default_swiglu='REFUSED', quantized_switch_linear='REFUSED')

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MoE)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('moe_summary', backend=backend, observations=observations, mutants=mutant_rows,
         scope='FINITE_FP32_GLM5NEXT_MOE_BLOCK_SYNTHETIC_ONLY; 4 experts top-2; no quantized experts')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

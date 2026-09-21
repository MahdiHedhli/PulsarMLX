"""Prospectively declared finite controls using admitted extracted router definitions.

The caller injects the unchanged source/runtime components and independent
stdlib oracle after the successor's OS fence and source-free admission.
"""
import hashlib
import json
from pathlib import Path
import resource
import unittest

FIXTURE_SHA256 = '1976c8f55f392b052b026d1999a4120f1cb169adae2d728bfa5ad162c86dae4f'
FIXTURE_PATH = 'successor-discrimination-v1/fixtures.json'


def fixtures(context):
    raw = context.read_verified(context.roots['fixtures'] / FIXTURE_PATH)
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError('DISCRIMINATION_WRONG_GENERATION_BYTES')
    value = context.parse(raw)
    if value['schema'] != 'flash-router-discrimination-fixtures-v1' or value['generation'] != 1:
        raise ValueError('DISCRIMINATION_WRONG_GENERATION')
    return value


def run(context, backend):
    context.verify()
    f = fixtures(context)
    r = runtime.Runtime(context.phase)
    mx = r.mx
    observations = {'cast': [], 'grouped': [], 'e288': []}
    claims = {}
    requests = []
    original_read = Path.read_bytes
    expected_reads = {row['path'].removeprefix('upstream/'): row for row in context.manifest['source_inputs']
                      if row['path'].startswith('upstream/')}

    def trace(path):
        if not path.is_relative_to(context.phase / 'source'):
            return original_read(path)
        name = path.relative_to(context.phase / 'source').as_posix()
        row = expected_reads[name]
        event = {'order': len(requests), 'path': 'source/' + name, 'operation': 'Path.read_bytes',
                 'requested_logical_bytes': row['bytes'], 'returned_bytes': None, 'status': 'ATTEMPTED'}
        requests.append(event)
        raw = context.read(path, row['bytes'])
        if context.sha(raw) != row['sha256']:
            raise ValueError('DISCRIMINATION_STAGED_SOURCE_DRIFT')
        event.update(returned_bytes=len(raw), sha256=context.sha(raw), status='RETURNED')
        return raw

    def invoke(case, variant=None, base=False):
        instance = r.make(case, variant)
        gate, x = instance['gate'], instance['x']
        if base:
            actual_base = instance['bundle']['base'](source.ResearchConfig(case['config']))
            actual_base.weight = gate.weight
            actual_base.e_score_correction_bias = gate.e_score_correction_bias
            gate = actual_base
        px = x if variant == 'omit-input-cast' or base else x.astype(mx.float32)
        pw = gate.weight if variant == 'omit-weight-cast' or base else gate.weight.astype(mx.float32)
        diagnostic = px @ pw.T
        ids, scores = gate(x)
        r.evaluate(diagnostic, ids, scores, caller=True)
        origin = instance['bundle']['record']
        row = {'case': case['name'], 'variant': variant or ('ACTUAL_BASE_CALLER' if base else 'UNCHANGED_UPSTREAM'),
               'raw_ids': ids.tolist(), 'raw_scores': scores.tolist(), 'output_dtype': str(scores.dtype),
               'input_dtype': str(x.dtype), 'weight_dtype': str(gate.weight.dtype),
               'separate_projection': diagnostic.tolist(), 'projection_dtype': str(diagnostic.dtype),
               'projection_scope': 'separate same-expression diagnostic, not captured caller locals',
               'bundle_sequence': origin['sequence'], 'caller_body_sha256': origin['caller_executed_body_sha256'],
               'actual_base_call': base}
        return row

    def checked(row, case, expected=None):
        reference = expected or oracle.selection(oracle.projection(case)[0], case['bias'], case['config'])
        return oracle.check_output(row['raw_ids'][0], row['raw_scores'][0], reference,
                                   case['config'], f['score_tolerance'])

    class Controls(unittest.TestCase):
        @classmethod
        def setUpClass(cls):
            if len(f['cast_cases']) != f['cast_expected_domain_size'] or len({c['name'] for c in f['cast_cases']}) != 162:
                raise ValueError('FINITE_DOMAIN_MEMBERSHIP')
            cls.cast_results = {'omit-input-cast': [], 'omit-weight-cast': []}
            for raw_case in f['cast_cases']:
                case = oracle.prepare(raw_case)
                reference_projection = oracle.projection(case)
                baseline = invoke(case)
                checked(baseline, case)
                if baseline['separate_projection'] != reference_projection or baseline['projection_dtype'] != 'mlx.core.float32':
                    raise AssertionError('INDEPENDENT_FIXED_DYADIC_PROJECTION')
                observations['cast'].append(baseline)
                original = oracle.canonical(baseline['raw_ids'][0], baseline['raw_scores'][0])
                for variant in cls.cast_results:
                    mutant = invoke(case, variant)
                    same_output = oracle.canonical(mutant['raw_ids'][0], mutant['raw_scores'][0]) == original
                    same_projection = (mutant['separate_projection'] == reference_projection and
                                       mutant['projection_dtype'] == baseline['projection_dtype'])
                    mutant.update(caller_output_exactly_equal=same_output,
                                  separate_projection_exactly_equal=same_projection)
                    observations['cast'].append(mutant)
                    cls.cast_results[variant].append({'case': case['name'], 'same_output': same_output,
                                                     'same_projection': same_projection})

        def cast_claim(self, name):
            rows = self.cast_results[name]
            witnesses = [r['case'] for r in rows if not r['same_output']]
            if witnesses:
                status = 'DISCRIMINATED'
            elif len(rows) == 162 and all(r['same_projection'] for r in rows):
                status = 'RETIRED_WITH_DOMAIN_PROOF'
            else:
                status = 'STILL_OPEN'
            claims[name] = {'status': status, 'exhaustive_domain_members': len(rows), 'witnesses': witnesses,
                            'domain': 'only the entire fixed 2-dtype by 9-input by 9-weight generation-1 Cartesian product',
                            'proof_kind': 'exhaustive finite enumeration with exact ID-associated output bits and separately exact FP32 projections',
                            'native_BF16_or_arbitrary_matrix_inference': 'NOT_QUALIFIED'}
            self.assertNotEqual(status, 'STILL_OPEN')

        def test_input_cast(self):
            self.cast_claim('omit-input-cast')

        def test_weight_cast(self):
            self.cast_claim('omit-weight-cast')

        def test_grouped_negative_mask(self):
            texts, _, _ = source.load_nodes(context.phase)
            before, after = f['mask_mutant']['replace_once']
            self.assertEqual(texts['group_expert_select'].count(before), 1)
            derivative = texts['group_expert_select'].replace(before, after)
            source.audit_node('group_expert_select', derivative)
            namespace = {'__builtins__': {}, 'mx': mx, '__name__': 'declared_mask_test_derivative'}
            exec(compile(derivative, 'declared-test-derivative:negative-mask', 'exec'), namespace)
            selector = namespace['group_expert_select']
            for raw_case in f['grouped_cases']:
                case = oracle.prepare(raw_case)
                projection = oracle.projection(case)[0]
                zero = oracle.selection(projection, case['bias'], case['config'], 'zero')
                excluded = oracle.selection(projection, case['bias'], case['config'], 'exclude')
                self.assertEqual(sorted(zero['selected_ids']), case['expected_zero_mask_ids'])
                self.assertEqual(sorted(excluded['selected_ids']), case['expected_exclusion_ids'])
                self.assertTrue(all(v < 0 for v in zero['group_scores']))
                self.assertTrue(set(zero['selected_ids']).isdisjoint(excluded['selected_ids']))
                for base in (False, True):
                    row = invoke(case, base=base)
                    row['independent_comparison'] = checked(row, case, zero)
                    row['retained_group_expectation'] = zero['retained_groups']
                    observations['grouped'].append(row)
                c = case['config']
                ids, scores = selector(mx.array([projection], dtype=mx.float32),
                                       mx.array(case['bias'], dtype=mx.float32), c['num_experts_per_tok'],
                                       c['n_group'], c['topk_group'], c['routed_scaling_factor'], c['norm_topk_prob'])
                r.evaluate(ids, scores)
                row = {'case': case['name'], 'variant': 'DECLARED_SELECTOR_MASK_MINUS_1E30',
                       'raw_ids': ids.tolist(), 'raw_scores': scores.tolist(), 'output_dtype': str(scores.dtype),
                       'executed_derivative_sha256': hashlib.sha256(derivative.encode()).hexdigest(),
                       'source_is_test_derivative': True}
                row['independent_comparison'] = checked(row, case, excluded)
                observations['grouped'].append(row)
            claims['grouped-negative-mask'] = {'status': 'DISCRIMINATED', 'cases': len(f['grouped_cases']),
                    'domain': 'FP32 zero logits/all-negative corrected scores; 2,3,4 groups; keep all but one; normalized and unnormalized',
                    'actual_source_semantics': 'zero-masked rejected experts outrank retained negative experts',
                    'excluded_group_semantics': 'different, explicitly named test derivative; not a production repair',
                    'representative_n_group_1': 'mask branch does not execute'}

        def test_e288_products(self):
            selected = []
            for raw_case in f['e288_cases']:
                case = oracle.prepare(raw_case)
                row = invoke(case)
                self.assertEqual(row['separate_projection'], oracle.projection(case))
                row['independent_comparison'] = checked(row, case)
                ids = sorted(row['raw_ids'][0])
                self.assertEqual(ids, case['expected_selected_ids'])
                self.assertLessEqual(max(abs(v) for v in case['bias']), 1/4096)
                selected.append(set(ids))
                observations['e288'].append(row)
            self.assertTrue(selected[0].isdisjoint(selected[1]))
            self.assertTrue(selected[0].isdisjoint(selected[2]))
            self.assertEqual(f['e288_cases'][0]['bias'], f['e288_cases'][1]['bias'])
            self.assertEqual(f['e288_cases'][0]['bias'], f['e288_cases'][2]['bias'])
            claims['e288-products'] = {'status': 'DISCRIMINATED', 'cases': 3,
                    'domain': 'synthetic E288/H2/top_k8/n_group1/topk_group1/normalization/scale2.5, fixed bias bounded by1/4096',
                    'input_and_weight_perturbations_change_selected_experts': True,
                    'checkpoint_bias_or_model_routing': 'NOT_QUALIFIED'}

    Path.read_bytes = trace
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    finally:
        Path.read_bytes = original_read
    context.verify()
    origins = [entry['record'] for entry in r.builder.retained]
    identity_counts = {key: len({row[key] for row in origins}) for key in
                       ('selector_object_id', 'base_class_object_id', 'caller_class_object_id')}
    if any(count != len(origins) for count in identity_counts.values()):
        raise ValueError('DISCRIMINATION_FRESH_OBJECT_IDENTITY')
    print(json.dumps({'event': 'discrimination_observations', 'fixture_sha256': FIXTURE_SHA256,
                      'fixture_generation': f['generation'], 'backend': backend, 'observations': observations,
                      'claims': claims, 'evaluations': r.evaluations, 'caller_evaluations': r.caller_evaluations,
                      'fresh_bundles': len(origins), 'unique_identity_counts': identity_counts,
                      'source_bindings': origins[0]['source_nodes'] if origins else [],
                      'actual_caller_body_hashes': sorted({row['caller_executed_body_sha256'] for row in origins})}), flush=True)
    print(json.dumps({'event': 'successor_source_requests', 'requests': requests,
                      'scope': 'Only captured Path.read_bytes while tracing phase/source; excludes read_text, guard checksums and runtime I/O. No syscall or physical-I/O measurement.'}), flush=True)
    print(json.dumps({'event': 'result', 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
                      'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
                      'skips': len(result.skipped), 'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped else 1

"""Finite default dispatch, outer-only barriers and real cache1 composition."""
import copy
import hashlib
import json
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-recurrent-dispatch-v1/fixtures.json'
FIXTURE_SHA256 = 'fdf13a02a098fb73818bc9aaf44f1926d88da9d43f5410a014c7b8f87f59ffd2'


class Mismatch(AssertionError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def compare(actual, expected, fixture):
    for name in ['output', 'state']:
        if not oracle.close(actual[name], expected[name], fixture['tolerances'][name + '_atol'],
                            fixture['tolerances'][name + '_rtol']):
            raise Mismatch(name.upper() + '_VALUES')


def expected_delta(case, backend, boundary, mutation=None):
    kernel = backend == 'metal' and case['Dk'] >= 32 and mutation != 'forced_fallback'
    return {'step_entries': 0 if kernel else case['T'], 'kernel_entries': int(kernel),
            'ops_entries': int(not kernel), 'update_entries': 1,
            'caller_entries': int(boundary == 'caller'), 'kernel_API_submissions': int(kernel),
            'inner_evaluation_barriers': (1 if kernel else case['T']) if mutation == 'illicit_inner_barrier' else 0,
            'outer_evaluation_barriers': 1,
            'cache_observation_barriers': 2 if boundary == 'caller' else 0}


def detection(error, message, delta, expected):
    return type(error) is Mismatch and str(error) == message and delta == expected


class Engine:
    def __init__(self, context, fixture, cache_fixture, backend, mutation=None):
        self.bound = source.load(context, fixture, mutation)
        self.classes, _, self.cache_binding = cache_source.load(context, cache_fixture)
        self.stats = self.bound.stats
        self.fixture, self.backend, self.mutation = fixture, backend, mutation
        self.last = None
        self.carried_state = None
        self.carried_state_values = None
        self.device = str(mx.default_device())
        if (mx.default_device() == mx.gpu) != (backend == 'metal'):
            raise Mismatch('ACTUAL_DEFAULT_DEVICE')
        if self.stats['factory_entries'] != 4 or self.stats['factory_API_calls'] != 4:
            raise Mismatch('SOURCE_FACTORY_CREATION')

    def new_cache(self, case):
        oracle.validate(case, case['state'])
        cache = self.classes.source_make_cache()
        slot0 = [[[.125 * (b + 1), -.25]] for b in range(case['B'])]
        cache.state = [mx.array(slot0, dtype=mx.float32),
                       None if case['state'] is None else mx.array(case['state'], dtype=mx.float32)]
        cache.prepare([case['T'] + 3 + b for b in range(case['B'])])
        cache.left_padding = mx.array([1 + b for b in range(case['B'])])
        return cache

    def cache_record(self, cache):
        if cache is None:
            return None, None
        slots = cache.state
        lengths, padding = cache.lengths, cache.left_padding
        mx.eval(*[x for x in (*slots, lengths, padding) if x is not None])
        self.stats['cache_observation_barriers'] += 1
        state = None if slots[1] is None else slots[1].tolist()
        record = {'slot0': slots[0].tolist(), 'slot1_sha256': digest(state),
                  'lengths': None if lengths is None else lengths.tolist(),
                  'left_padding': None if padding is None else padding.tolist(),
                  'lengths_advance': cache._lengths_advance,
                  'padding_advance': cache._left_padding_advance, 'class': type(cache).__name__}
        return record, state

    def invoke(self, case, state, boundary='update', cache=None, carry=False):
        self.last = None
        before, cache_state = self.cache_record(cache)
        input_state = cache_state if cache is not None else (self.carried_state_values if carry else state)
        if carry and (boundary != 'update' or self.carried_state is None):
            raise oracle.InputError('MISSING_ACTUAL_CARRIED_STATE')
        oracle.validate(case, input_state)
        if boundary == 'caller' and (case['gate'] != 'vector' or case.get('mask') is not None or cache is None):
            raise oracle.InputError('CALLER_INPUT_BOUNDARY')
        arrays = {name: mx.array(case[name], dtype=mx.float32)
                  for name in ['q', 'k', 'v', 'a', 'b', 'A_log', 'dt_bias']}
        original_slot0 = cache[0] if cache is not None else None
        kernel_before, ops_before = self.stats['kernel_entries'], self.stats['ops_entries']
        submission_start = len(self.bound.submissions)
        if boundary == 'caller':
            owner = types.SimpleNamespace(num_heads=case['Hv'], head_dim=case['Dk'])
            fg = types.SimpleNamespace(A_log=arrays['A_log'], dt_bias=arrays['dt_bias'],
                                       safe_gate_lower_bound=case['lower_bound'])
            y, updated = self.bound.namespace['source_recurrent_step'](
                owner, fg, arrays['q'], arrays['k'], arrays['v'], arrays['a'], arrays['b'], cache, case['T'])
        else:
            tensor_state = self.carried_state if carry else (None if state is None else mx.array(state, dtype=mx.float32))
            mask = None if case.get('mask') is None else mx.array(case['mask'], dtype=mx.bool_)
            # The original True default and the original device/shape selector run.
            y, updated = self.bound.namespace['gated_delta_update'](
                arrays['q'], arrays['k'], arrays['v'], arrays['a'], arrays['b'], arrays['A_log'], arrays['dt_bias'],
                state=tensor_state, mask=mask, lower_bound=case['lower_bound'])
        mx.eval(y, updated)
        self.stats['outer_evaluation_barriers'] += 1
        if y.dtype != mx.float32 or updated.dtype != mx.float32:
            raise Mismatch('RETURN_DTYPE')
        after, after_state = self.cache_record(cache)
        output, final_state = y.tolist(), updated.tolist()
        self.carried_state, self.carried_state_values = updated, final_state
        self.last = {'output': output, 'state': final_state, 'dtype': 'float32',
                     'actual_input_state_sha256': digest(input_state), 'carried_actual_tensor': carry,
                     'boundary': boundary, 'actual_default_device': str(mx.default_device()),
                     'default_device_is_gpu': mx.default_device() == mx.gpu,
                     'actual_kernel_entry_delta': self.stats['kernel_entries'] - kernel_before,
                     'actual_ops_entry_delta': self.stats['ops_entries'] - ops_before,
                     'kernel_submissions': copy.deepcopy(self.bound.submissions[submission_start:]),
                     'cache_before': before, 'cache_after': after,
                     'cache1_is_returned_state': cache is not None and cache[1] is updated,
                     'cache1_mismatch_body': after_state if cache is not None and after_state != final_state else None,
                     'cache1_body_binding': 'After-state body equals returned state when mismatch body is null; before-state resolves to initial fixture or previous outer state by SHA256.'}
        if cache is not None and (cache[0] is not original_slot0 or after['slot0'] != before['slot0']):
            raise Mismatch('CACHE0_CHANGED')
        return self.last


def run(context, backend):
    raw = context.read_verified(context.roots['code'] / FIXTURE)
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError('DISPATCH_FIXTURE_IDENTITY')
    fixture = json.loads(raw)
    cache_raw = context.read_verified(context.roots['code'] / 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json')
    oracle_raw = context.read_verified(context.roots['code'] / 'scripts/research/glm53_flash/recurrent_dispatch/oracle.py')
    if (hashlib.sha256(cache_raw).hexdigest() != fixture['accepted_cache_fixture_sha256']
            or hashlib.sha256(oracle_raw).hexdigest() != fixture['oracle_sha256']):
        raise ValueError('DISPATCH_DEPENDENCY_BINDING')
    cache_fixture = json.loads(cache_raw)
    cases = {c['name']: c for c in fixture['cases']}
    engines, observations, mutations, refusals = [], [], [], []
    function_ids, kernel_ids = set(), set()

    def engine(mutation=None):
        e = Engine(context, fixture, cache_fixture, backend, mutation)
        ids = {id(value) for value in e.bound.originals.values()}
        handles = {id(value) for value in e.bound.handles}
        if len(ids) != 8 or ids & function_ids or len(handles) != 8 or handles & kernel_ids:
            raise Mismatch('FUNCTION_OR_KERNEL_OBJECT_REUSE')
        function_ids.update(ids); kernel_ids.update(handles); engines.append(e)
        e.serial = len(engines)
        return e

    def check(e, c, actual, expected, delta, boundary):
        if delta['inner_evaluation_barriers'] != 0:
            raise Mismatch('INNER_EVALUATION_BARRIER')
        wanted = expected_delta(c, backend, boundary)
        if any(delta[key] != wanted[key] for key in ['kernel_entries', 'ops_entries', 'step_entries', 'kernel_API_submissions']):
            raise Mismatch('DEFAULT_DISPATCH')
        if delta != wanted:
            raise Mismatch('SOURCE_ENTRY_OR_OUTER_BARRIER')
        compare(actual, expected, fixture)
        if boundary == 'caller':
            if actual['cache_after']['slot1_sha256'] != digest(actual['state']):
                raise Mismatch('CACHE1_RETURNED_STATE')
            for name in ['lengths', 'left_padding']:
                if actual['cache_after'][name] != [n - c['T'] for n in actual['cache_before'][name]]:
                    raise Mismatch('CACHE_LENGTHS')

    def invoke_observe(e, c, state, label, boundary='update', cache=None, carry=False):
        expected = oracle.transition(c, state, kernel_mask=backend == 'metal' and c['Dk'] >= 32)
        before = dict(e.stats)
        actual = e.invoke(c, state, boundary, cache, carry)
        delta = {key: e.stats[key] - before[key] for key in expected_delta(c, backend, boundary)}
        check(e, c, actual, expected, delta, boundary)
        observations.append({'label': label, 'case': c['name'], 'input_sha256': digest(c),
                             'independent_initial_state_sha256': digest(state), 'source': e.bound.binding,
                             'closure_serial': e.serial, 'delta': delta, 'actual': actual, 'independent_reference': 'PASS'})
        return expected['state'], actual

    class Checks(unittest.TestCase):
        def test_bridge_outer_only(self):
            c = cases['vector-cache-batch']
            _, actual = invoke_observe(engine(), c, c['state'], 'lazy-ops-bridge')
            reference = fixture['bridge_eager_references'][backend]
            compare(actual, reference, fixture)
            self.assertEqual(reference['old_delta']['step_evaluation_barriers'], c['T'])
            self.assertEqual(observations[-1]['delta']['inner_evaluation_barriers'], 0)

        def test_default_dispatch_and_masks(self):
            for c in cases.values():
                for number, parts in enumerate(c['partitions']):
                    e = engine(); state = copy.deepcopy(c['state']); offset = 0; chunks = []
                    for length in parts:
                        state, actual = invoke_observe(e, oracle.chunk(c, offset, length), state,
                                                       'default-partition-' + str(number) + ':' + str(offset), carry=offset > 0)
                        chunks.append(actual); offset += length
                    whole = fixture['expected'][c['name']]['kernel' if backend == 'metal' and c['Dk'] >= 32 else 'ops']
                    joined = [[time for chunk in chunks for time in chunk['output'][b]] for b in range(c['B'])]
                    compare({'output': joined, 'state': chunks[-1]['state']}, whole, fixture)
                    self.assertEqual(offset, c['T'])
            c = cases['scalar64-all-false-mask']
            expected = fixture['expected'][c['name']]
            self.assertTrue(any(abs(v) > 2e-5 for v in oracle.flat(expected['ops']['output'])))
            self.assertTrue(all(v == 0 for v in oracle.flat(expected['kernel']['output'])))
            self.assertEqual(expected['kernel']['state'], c['state'])
            self.assertEqual(expected['ops']['state'], c['state'])

        def test_cache_composition(self):
            for name in fixture['cache_cases']:
                c = cases[name]
                for number, parts in enumerate(c['partitions']):
                    e = engine(); cache = e.new_cache(c); state = copy.deepcopy(c['state']); offset = 0
                    for length in parts:
                        state, _ = invoke_observe(e, oracle.chunk(c, offset, length), state,
                                                  'cache-partition-' + str(number) + ':' + str(offset), 'caller', cache)
                        offset += length
                    self.assertEqual(offset, c['T'])
            e = engine()
            plans = fixture['interleaved']
            caches = [e.new_cache(cases[p['case']]) for p in plans]
            self.assertIsNot(caches[0].state, caches[1].state)
            states = [copy.deepcopy(cases[p['case']]['state']) for p in plans]
            offsets = [0, 0]
            for step in range(max(len(p['parts']) for p in plans)):
                for i, p in enumerate(plans):
                    if step >= len(p['parts']):
                        continue
                    c = cases[p['case']]; length = p['parts'][step]
                    states[i], _ = invoke_observe(e, oracle.chunk(c, offsets[i], length), states[i],
                                                  'interleaved-' + str(i) + ':' + str(offsets[i]), 'caller', caches[i])
                    offsets[i] += length
            c = cases[plans[0]['case']]
            fresh = e.new_cache(c)
            self.assertIsNot(fresh.state, caches[0].state)
            invoke_observe(e, oracle.chunk(c, 0, 1), c['state'], 'fresh-cache-replacement', 'caller', fresh)

        def test_frozen_binary64_and_rational_anchors(self):
            for c in cases.values():
                for path in ['ops', 'kernel']:
                    value = oracle.transition(c, c['state'], kernel_mask=path == 'kernel')
                    for key in ['output', 'state', 'g', 'beta']:
                        self.assertTrue(oracle.close(value[key], fixture['expected'][c['name']][path][key], 1e-14, 1e-14))
            anchor = fixture['expected']['kernel32-rational-anchor']['ops']
            self.assertEqual(anchor['state'][0][0][0][0], 19 / 64)
            self.assertEqual(anchor['output'][0][0][0][0], 19 / 128)

        def test_mutations(self):
            for name, spec in fixture['mutants'].items():
                if backend not in spec['backends']:
                    mutations.append({'name': name, 'status': 'NOT_APPLICABLE_CPU_ALREADY_SELECTS_OPS',
                                      'detected': False, 'scope': 'No CPU fallback discrimination claim; declared Metal-only control.'})
                    continue
                c = oracle.chunk(cases[spec['case']], spec['start'], spec['length'])
                identities = []
                for mode in ['normal', 'mutant', 'restored']:
                    mutation = name if mode == 'mutant' else None
                    e = engine(mutation)
                    # Cache initialization reuses the declared full-case initial state.
                    cache = e.new_cache(cases[spec['case']]) if spec['boundary'] == 'caller' else None
                    kernel_expected = backend == 'metal' and c['Dk'] >= 32
                    if mutation == 'wrong_mask_output_expectation':
                        kernel_expected = not kernel_expected
                    expected = oracle.transition(c, c['state'], kernel_mask=kernel_expected)
                    before = dict(e.stats); error = None
                    try:
                        actual = e.invoke(c, c['state'], spec['boundary'], cache)
                        delta = {key: e.stats[key] - before[key] for key in expected_delta(c, backend, spec['boundary'])}
                        check(e, c, actual, expected, delta, spec['boundary'])
                    except Exception as caught:
                        error = caught
                    delta = {key: e.stats[key] - before[key] for key in expected_delta(c, backend, spec['boundary'])}
                    wanted = expected_delta(c, backend, spec['boundary'], mutation)
                    if mode == 'mutant':
                        self.assertTrue(detection(error, spec['message'], delta, wanted),
                                        (name, type(error).__name__, str(error), delta, wanted))
                    else:
                        if error is not None:
                            raise error
                        self.assertEqual(delta, wanted)
                    identity = {'input_sha256': digest(c), 'state_sha256': digest(c['state']),
                                'original_capsule': fixture['capsule_sha256'], 'oracle': fixture['oracle_sha256']}
                    identities.append(identity)
                    mutations.append({'name': name, 'mode': mode, 'detected': mode == 'mutant',
                                      'exception': type(error).__name__ if error is not None else None,
                                      'message': str(error) if error is not None else None, 'delta': delta,
                                      'identity': identity, 'closure_serial': e.serial, 'source': e.bound.binding,
                                      'actual': e.last, 'family': spec['family']})
                self.assertEqual(identities[0], identities[1]); self.assertEqual(identities[0], identities[2])

        def test_preentry_refusals(self):
            c = cases['vector32-grouped-safe']
            for kind, message in [('dimension', 'DOMAIN_SHAPE'), ('shape', 'INPUT_SHAPE:q'),
                                   ('nonfinite', 'INPUT_NONFINITE:q')]:
                e = engine(); bad = oracle.chunk(c, 0, 1)
                if kind == 'dimension': bad['Dk'] = 33
                if kind == 'shape': bad['q'] = []
                if kind == 'nonfinite': bad['q'][0][0][0][0] = float('nan')
                before = dict(e.stats)
                with self.assertRaises(oracle.InputError) as error:
                    e.invoke(bad, bad['state'])
                self.assertEqual(str(error.exception), message)
                delta = {key: e.stats[key] - before[key] for key in e.stats}
                self.assertTrue(all(value == 0 for value in delta.values()))
                refusals.append({'name': kind, 'exception': type(error.exception).__name__, 'message': message,
                                 'source_entry_and_submission_delta': delta,
                                 'scope': 'Research input refusal before source update/GPU submission, not an upstream guarantee.'})
            delta = expected_delta(oracle.chunk(c, 0, 1), backend, 'update')
            self.assertTrue(detection(Mismatch('OUTPUT_VALUES'), 'OUTPUT_VALUES', delta, delta))
            self.assertFalse(detection(RuntimeError('OUTPUT_VALUES'), 'OUTPUT_VALUES', delta, delta))
            self.assertFalse(detection(Mismatch('unrelated'), 'OUTPUT_VALUES', delta, delta))
            self.assertFalse(detection(Mismatch('OUTPUT_VALUES'), 'OUTPUT_VALUES', dict(delta, outer_evaluation_barriers=0), delta))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    names = sorted(test._testMethodName for test in suite)
    if names != fixture['test_ids']:
        raise ValueError('DISPATCH_TEST_INVENTORY')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    generated = {}
    for e in engines:
        for key, body in e.bound.generated_sources.items():
            if key in generated and generated[key] != body:
                raise ValueError('GENERATED_SOURCE_COLLISION')
            generated[key] = body
    print(json.dumps({'event': 'default_dispatch_observations', 'backend': backend,
                      'actual_default_device': str(mx.default_device()),
                      'observations': observations, 'mutations': mutations, 'refusals': refusals,
                      'source_instances': len(engines), 'fresh_original_function_objects': len(function_ids),
                      'fresh_kernel_API_objects': len(kernel_ids), 'generated_kernel_sources': generated,
                      'totals': {key: sum(e.stats[key] for e in engines) for key in engines[0].stats},
                      'factory_records': [{'closure_serial': e.serial, 'factories': e.bound.factories} for e in engines],
                      'fixture_sha256': FIXTURE_SHA256, 'oracle_sha256': fixture['oracle_sha256'],
                      'generation': context.manifest['generation'], 'physical_compiled_counts': 'NOT_MEASURABLE',
                      'scope': 'Seven finite source-bound default-dispatch/outer-only cases; separate masked semantics; synthetic vector/unmasked caller only.'}, allow_nan=False), flush=True)
    print(json.dumps({'event': 'result', 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
                      'tests_run': result.testsRun, 'test_ids': names, 'skips': len(result.skipped),
                      'failures': len(result.failures), 'errors': len(result.errors),
                      'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped else 1

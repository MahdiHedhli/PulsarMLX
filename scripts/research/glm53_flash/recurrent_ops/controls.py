"""Finite actual recurrent ops and cache1 seam; independent expected state."""
import copy
import hashlib
import json
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-recurrent-ops-v1/fixtures.json'
FIXTURE_SHA256 = 'db337dd490380fca5d3d98b473c1dca9f3059a142e4e9fed9001d2dbee09308f'


class Mismatch(AssertionError):
    pass


class InjectedFailure(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def detected(error, specification, delta):
    return (type(error) is Mismatch and str(error) == specification['message']
            and delta == specification['expected_delta'])


def compare(actual, expected, fixture, case):
    tol = fixture['tolerances']
    for name in ('output', 'state'):
        if not oracle.close(actual[name], expected[name], tol[name + '_atol'], tol[name + '_rtol']):
            raise Mismatch(name.upper() + '_VALUES')
    if len(actual['traces']) != case['T']:
        raise Mismatch('STEP_TRACE_COUNT')
    for observed, wanted in zip(actual['traces'], expected['traces']):
        for name, absolute in [('g', tol['g_atol']), ('beta', tol['beta_atol']),
                               ('output', tol['output_atol']), ('new_state', tol['state_atol']),
                               ('prior_state', tol['state_atol'])]:
            relative = 0.0 if name in ('g', 'beta') else 3e-6
            if not oracle.close(observed[name], wanted[name], absolute, relative):
                raise Mismatch('TRACE_' + name.upper())
        for name in ('q', 'k'):
            expanded = [[row[h // (case['Hv'] // case['Hk'])] for h in range(case['Hv'])] for row in wanted[name]]
            if observed[name + '_expanded'] != expanded:
                raise Mismatch('TRACE_HEAD_EXPANSION')
        if observed['v'] != wanted['v'] or observed['mask'] != wanted['mask']:
            raise Mismatch('TRACE_INPUT_OR_MASK')


class Engine:
    def __init__(self, context, fixture, accepted_cache, mutation=None):
        self.bound = source.load(context, fixture, mutation)
        self.classes, _, self.cache_binding = cache_source.load(context, accepted_cache)
        self.mutation = mutation
        self.fixture = fixture
        self.stats = self.bound.stats
        self.stats['cache_observation_barriers'] = 0
        self.last = None

    def new_cache(self, case, state):
        cache = self.classes.source_make_cache()
        slot0 = [[[.125 * (b + 1), -.25]] for b in range(case['B'])]
        cache.state = [mx.array(slot0, dtype=mx.float32), None if state is None else mx.array(state, dtype=mx.float32)]
        cache.prepare([case['T'] + 3 + b for b in range(case['B'])])
        cache.left_padding = mx.array([1 + b for b in range(case['B'])])
        return cache

    def cache_record(self, cache):
        if cache is None:
            return None
        slots = cache.state; lengths = cache.lengths; padding = cache.left_padding
        mx.eval(*[x for x in (*slots, lengths, padding) if x is not None])
        self.stats['cache_observation_barriers'] += 1
        return {'slots': [None if x is None else x.tolist() for x in slots],
                'lengths': None if lengths is None else lengths.tolist(),
                'left_padding': None if padding is None else padding.tolist(),
                'lengths_advance': cache._lengths_advance, 'padding_advance': cache._left_padding_advance,
                'class': type(cache).__name__}

    def invoke(self, case, state, *, boundary='update', cache=None, fault=None):
        self.last = None
        before_cache = self.cache_record(cache)
        source_state = before_cache['slots'][1] if cache is not None else state
        oracle.validate(case, source_state)
        if boundary == 'caller' and (case['gate'] != 'vector' or case.get('mask') is not None):
            raise oracle.InputError('CALLER_INPUT_BOUNDARY')
        arrays = {k: mx.array(case[k], dtype=mx.float32) for k in ('q', 'k', 'v', 'a', 'b', 'A_log', 'dt_bias')}
        start = len(self.bound.traces)
        original_slot0 = cache[0] if cache is not None else None
        namespace = self.bound.namespace
        if fault == 'callee':
            def fail(*args, **kwargs):
                raise InjectedFailure('CALLEE_BEFORE_CACHE_WRITE')
            namespace['gated_delta_update'] = fail
        if fault == 'advance':
            def fail_advance(length):
                self.advance_failure_state = self.cache_record(cache)
                raise InjectedFailure('ADVANCE_AFTER_CACHE_WRITE')
            cache.advance = fail_advance
        if boundary == 'caller':
            obj = types.SimpleNamespace(num_heads=case['Hv'], head_dim=case['Dk'])
            fg = types.SimpleNamespace(A_log=arrays['A_log'], dt_bias=arrays['dt_bias'], safe_gate_lower_bound=case['lower_bound'])
            y, updated = namespace['source_recurrent_step'](obj, fg, arrays['q'], arrays['k'], arrays['v'], arrays['a'], arrays['b'], cache, case['T'])
        else:
            mask = None if case.get('mask') is None else mx.array(case['mask'], dtype=mx.bool_)
            tensor_state = None if state is None else mx.array(state, dtype=mx.float32)
            # use_kernel is deliberately omitted: original True default/selector.
            y, updated = namespace['gated_delta_update'](arrays['q'], arrays['k'], arrays['v'], arrays['a'], arrays['b'], arrays['A_log'], arrays['dt_bias'], state=tensor_state, mask=mask, lower_bound=case['lower_bound'])
        mx.eval(y, updated)
        self.stats['outer_evaluation_barriers'] += 1
        if y.dtype != mx.float32 or updated.dtype != mx.float32:
            raise Mismatch('OUTPUT_DTYPE')
        self.last = {'output': y.tolist(), 'state': updated.tolist(), 'traces': copy.deepcopy(self.bound.traces[start:]),
                     'boundary': boundary, 'dtype': 'float32', 'cache_before': before_cache, 'cache_after': self.cache_record(cache)}
        if cache is not None and (cache[0] is not original_slot0 or self.last['cache_after']['slots'][0] != before_cache['slots'][0]):
            raise Mismatch('CACHE0_CHANGED')
        if self.stats['kernel_entries']:
            raise Mismatch('KERNEL_ARM_ENTERED')
        return self.last


def varied(case):
    value = copy.deepcopy(case)
    value['v'] = [[[[ -x for x in head] for head in time] for time in batch] for batch in case['v']]
    return value


def run(context, backend):
    raw = context.read_verified(context.roots['code'] / FIXTURE)
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError('RECURRENT_FIXTURE_GENERATION')
    fixture = json.loads(raw)
    cache_raw = context.read_verified(context.roots['code'] / 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json')
    oracle_raw = context.read_verified(context.roots['code'] / 'scripts/research/glm53_flash/recurrent_ops/oracle.py')
    if hashlib.sha256(cache_raw).hexdigest() != fixture['accepted_cache_fixture_sha256'] or hashlib.sha256(oracle_raw).hexdigest() != fixture['oracle_sha256']:
        raise ValueError('RECURRENT_DEPENDENCY_BINDING')
    accepted_cache = json.loads(cache_raw)
    cases = {c['name']: c for c in fixture['cases']}
    engines, observations, mutations, refusals, failures = [], [], [], [], []
    function_ids = set()

    def engine(mutation=None):
        e = Engine(context, fixture, accepted_cache, mutation)
        ids = {id(f) for f in e.bound.originals.values()}
        if len(ids) != 6 or ids & function_ids:
            raise Mismatch('COMPILED_FUNCTION_REUSE')
        function_ids.update(ids); engines.append(e)
        e.serial = len(engines)
        return e

    def observe(e, c, expected_state, label, *, boundary='update', cache=None):
        expected = oracle.transition(c, expected_state)
        before = dict(e.stats)
        actual = e.invoke(c, expected_state, boundary=boundary, cache=cache)
        compare(actual, expected, fixture, c)
        delta = {k: e.stats[k] - before[k] for k in e.stats}
        if (delta['step_entries'] != c['T'] or delta['step_evaluation_barriers'] != c['T']
                or delta['outer_evaluation_barriers'] != 1 or delta['update_entries'] != 1
                or delta['caller_entries'] != (1 if boundary == 'caller' else 0) or delta['kernel_entries'] != 0):
            raise Mismatch('ENTRY_OR_EVALUATION_DELTA')
        if cache is not None:
            for key in ('lengths', 'left_padding'):
                if actual['cache_after'][key] != [n - c['T'] for n in actual['cache_before'][key]]:
                    raise Mismatch('CACHE_LENGTHS')
            if not oracle.close(actual['cache_after']['slots'][1], expected['state'], fixture['tolerances']['state_atol'], fixture['tolerances']['state_rtol']):
                raise Mismatch('CACHE1_RETURNED_STATE')
        observations.append({'label': label, 'case': c['name'], 'input_sha256': digest(c),
                             'independent_initial_state_sha256': digest(expected_state), 'source': e.bound.binding,
                             'closure_serial': e.serial, 'delta': delta, 'actual': actual, 'oracle': 'PASS'})
        return expected['state'], actual

    class Checks(unittest.TestCase):
        def test_frozen_scalar_expectations(self):
            for c in cases.values():
                computed = oracle.transition(c, c['state'])
                for name in ('output', 'state', 'g', 'beta'):
                    self.assertTrue(oracle.close(computed[name], fixture['expected'][c['name']][name], 1e-14, 1e-14))
                self.assertEqual(len(computed['traces']), c['T'])
            self.assertEqual(fixture['expected']['scalar-d1-anchor']['output'], [[[[.1484375]]]])
            self.assertEqual(fixture['expected']['scalar-d1-anchor']['state'], [[[[.296875]]]])

        def test_ops_partitions_and_mask(self):
            for c in cases.values():
                whole = fixture['expected'][c['name']]
                for pnum, parts in enumerate(c['partitions']):
                    e = engine(); state = copy.deepcopy(c['state']); offset = 0; chunks = []
                    for length in parts:
                        piece = oracle.chunk(c, offset, length)
                        state, actual = observe(e, piece, state, 'ops-partition-' + str(pnum) + ':' + str(offset))
                        chunks.append(actual); offset += length
                    joined = [[time for item in chunks for time in item['output'][b]] for b in range(c['B'])]
                    self.assertEqual(offset, c['T'])
                    self.assertTrue(oracle.close(joined, whole['output'], fixture['tolerances']['output_atol'], fixture['tolerances']['output_rtol']))
            masked = fixture['expected']['vector-grouped-mask']
            self.assertEqual(masked['traces'][0]['new_state'][1], masked['traces'][0]['prior_state'][1])
            self.assertTrue(any(abs(x) > .001 for x in oracle.flat(masked['traces'][0]['output'][1])))

        def test_cache_partitions_and_streams(self):
            for name in fixture['cache_cases']:
                c = cases[name]
                for pnum, parts in enumerate(c['partitions']):
                    e = engine(); cache = e.new_cache(c, c['state']); state = copy.deepcopy(c['state']); offset = 0
                    for length in parts:
                        state, _ = observe(e, oracle.chunk(c, offset, length), state, 'cache-partition-' + str(pnum) + ':' + str(offset), boundary='caller', cache=cache)
                        offset += length
                    self.assertEqual(offset, c['T'])
            c = cases['vector-cache']; streams = [c, varied(c)]; e = engine()
            caches = [e.new_cache(c, c['state']), e.new_cache(c, None)]; states = [copy.deepcopy(c['state']), None]
            self.assertIsNot(caches[0].state, caches[1].state); offset = 0
            for length in [2, 1, 3, 1]:
                for stream in (0, 1):
                    states[stream], _ = observe(e, oracle.chunk(streams[stream], offset, length), states[stream], 'interleave-' + str(stream) + ':' + str(offset), boundary='caller', cache=caches[stream])
                offset += length
            fresh = e.new_cache(c, None)
            self.assertIsNot(fresh.state, caches[0].state)
            observe(e, oracle.chunk(c, 0, 2), None, 'replacement-fresh-cache', boundary='caller', cache=fresh)
            # Exact optional-cache branch; no claim of a cache mutation here.
            observe(engine(), oracle.chunk(c, 0, 1), None, 'caller-without-cache', boundary='caller')

        def test_mutations(self):
            for name, spec in fixture['mutants'].items():
                c = cases[spec['case']]; piece = oracle.chunk(c, spec['start'], spec['length']); identities = []
                for mode in ('normal', 'mutant', 'restored'):
                    e = engine(name if mode == 'mutant' else None)
                    cache = e.new_cache(c, c['state']) if spec['boundary'] == 'caller' else None
                    state = copy.deepcopy(c['state'])
                    if name in ('stale_cache1', 'cross_stream_cache1'):
                        prefix = oracle.chunk(c, 0, 2)
                        state, _ = observe(e, prefix, state, name + ':' + mode + ':warmup', boundary='caller', cache=cache)
                        if name == 'stale_cache1' and mode == 'mutant':
                            cache[1] = mx.array(c['state'], dtype=mx.float32)
                        if name == 'cross_stream_cache1':
                            other = e.new_cache(c, None)
                            observe(e, oracle.chunk(varied(c), 0, 2), None, name + ':' + mode + ':other-stream', boundary='caller', cache=other)
                            if mode == 'mutant':
                                cache[1] = other[1]
                    expected = oracle.transition(piece, state); before = dict(e.stats); error = None
                    try:
                        actual = e.invoke(piece, state, boundary=spec['boundary'], cache=cache)
                        compare(actual, expected, fixture, piece)
                        if cache is not None and actual['cache_after']['lengths'] != [n - piece['T'] for n in actual['cache_before']['lengths']]:
                            raise Mismatch('CACHE_LENGTHS')
                    except Exception as caught:
                        error = caught
                    delta = {k: e.stats[k] - before[k] for k in spec['expected_delta']}
                    if mode == 'mutant':
                        self.assertTrue(detected(error, spec, delta), (name, type(error).__name__, str(error), delta))
                    else:
                        if error is not None:
                            raise error
                        self.assertEqual(delta, spec['expected_delta'])
                    identity = {'input': digest(piece), 'expected_initial_state': digest(state), 'original_capsule': e.bound.binding['capsule_sha256'],
                                'oracle': fixture['oracle_sha256'], 'python': context.manifest['python_sha256']}
                    identities.append(identity)
                    mutations.append({'name': name, 'mode': mode, 'detected': mode == 'mutant', 'exception': None if error is None else type(error).__name__,
                                      'message': None if error is None else str(error), 'delta': delta, 'identity': identity,
                                      'closure_serial': e.serial, 'source': e.bound.binding, 'actual': e.last,
                                      'cache_after': e.cache_record(cache), 'stats_including_warmup': dict(e.stats)})
                self.assertEqual(identities[0], identities[1]); self.assertEqual(identities[0], identities[2])

        def test_exception_order(self):
            c = cases['vector-cache']; piece = oracle.chunk(c, 0, 1)
            for fault, message in [('callee', 'CALLEE_BEFORE_CACHE_WRITE'), ('advance', 'ADVANCE_AFTER_CACHE_WRITE')]:
                e = engine(); cache = e.new_cache(c, c['state']); before = e.cache_record(cache); slot0, slot1 = cache.state
                with self.assertRaises(InjectedFailure) as caught:
                    e.invoke(piece, c['state'], boundary='caller', cache=cache, fault=fault)
                self.assertEqual(str(caught.exception), message); self.assertIs(cache[0], slot0)
                after = e.cache_record(cache)
                if fault == 'callee':
                    self.assertIs(cache[1], slot1); self.assertEqual(after, before)
                    self.assertEqual(e.stats['step_entries'], 0); self.assertEqual(e.stats['step_evaluation_barriers'], 0)
                else:
                    self.assertIsNot(cache[1], slot1)
                    expected = oracle.transition(piece, c['state'])
                    self.assertTrue(oracle.close(after['slots'][1], expected['state'], fixture['tolerances']['state_atol'], fixture['tolerances']['state_rtol']))
                    self.assertEqual(after['lengths'], before['lengths']); self.assertEqual(e.stats['step_entries'], 1)
                    self.assertEqual(e.stats['step_evaluation_barriers'], 1)
                self.assertEqual(e.stats['caller_entries'], 1); self.assertEqual(e.stats['outer_evaluation_barriers'], 0)
                failures.append({'fault': fault, 'message': message, 'before': before, 'after': after, 'stats': dict(e.stats),
                                 'source': e.bound.binding, 'source_caller': 'ACTUAL_SOURCE_EXECUTED',
                                 'injected_callee': 'RESEARCH_WRAPPER; no numerical qualification for fake update or replaced advance method'})

        def test_refusal_and_classifier(self):
            c = cases['vector-cache']; piece = oracle.chunk(c, 0, 1)
            for kind, message in [('shape', 'INPUT_SHAPE:q'), ('nonfinite', 'INPUT_NONFINITE:q'), ('state', 'STATE_SHAPE'), ('domain', 'DOMAIN_SHAPE')]:
                e = engine(); cache = e.new_cache(c, c['state']); bad = copy.deepcopy(piece)
                if kind == 'shape': bad['q'] = []
                if kind == 'nonfinite': bad['q'][0][0][0][0] = float('nan')
                if kind == 'state': cache[1] = mx.zeros((1, 1, 1), dtype=mx.float32)
                if kind == 'domain': bad['Dk'] = 32
                before = e.cache_record(cache); original_slots = list(cache.state)
                with self.assertRaises(oracle.InputError) as caught:
                    e.invoke(bad, None, boundary='caller', cache=cache)
                self.assertEqual(str(caught.exception), message); self.assertEqual(e.cache_record(cache), before)
                self.assertTrue(all(a is b for a, b in zip(cache.state, original_slots)))
                self.assertTrue(all(e.stats[k] == 0 for k in ('step_entries', 'update_entries', 'caller_entries', 'step_evaluation_barriers', 'outer_evaluation_barriers', 'kernel_entries')))
                refusals.append({'name': kind, 'type': type(caught.exception).__name__, 'message': message,
                                 'operated_instance_unchanged': True, 'source_entries': 0, 'source_evaluation_barriers': 0,
                                 'scope': 'RESEARCH_PREENTRY_REFUSAL_NOT_UPSTREAM_GUARANTEE'})
            spec = fixture['mutants']['missing_decay']; good = spec['expected_delta']
            self.assertTrue(detected(Mismatch(spec['message']), spec, good))
            self.assertFalse(detected(RuntimeError(spec['message']), spec, good)); self.assertFalse(detected(Mismatch('unrelated'), spec, good))
            for step in (0, 2):
                bad = dict(good, step_entries=step)
                self.assertFalse(detected(Mismatch(spec['message']), spec, bad))
            self.assertFalse(detected(Mismatch(spec['message']), spec, dict(good, step_evaluation_barriers=0)))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    names = sorted(t._testMethodName for t in suite)
    if names != fixture['test_ids']:
        raise ValueError('RECURRENT_EDGE_TEST_INVENTORY')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    totals = {k: sum(e.stats[k] for e in engines) for k in engines[0].stats} if engines else {}
    print(json.dumps({'event': 'recurrent_ops_observations', 'backend': backend, 'observations': observations,
                      'mutations': mutations, 'refusals': refusals, 'controlled_failures': failures,
                      'source_instances': len(engines), 'fresh_original_function_objects': len(function_ids), 'totals': totals,
                      'compiled_trace_operator_kernel_counts': 'NOT_MEASURABLE', 'fixture_sha256': FIXTURE_SHA256,
                      'oracle_sha256': fixture['oracle_sha256'], 'generation': context.manifest['generation'],
                      'scope': 'finite actual ops/default tiny dispatcher and exact unmasked cache1 caller only; no custom Metal kernel/full KDA/model'}, allow_nan=False), flush=True)
    print(json.dumps({'event': 'result', 'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'tests_run': result.testsRun,
                      'test_ids': names, 'skips': len(result.skipped), 'failures': len(result.failures), 'errors': len(result.errors),
                      'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped else 1

"""Finite actual-cache composition; the unchanged scalar oracle is independent."""
import copy
import hashlib
import json
import resource
import unittest

FIXTURE = 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'
FIXTURE_SHA256 = 'b26a06902aae5786a99ec49cc1b69f6d6843b05c9a16a5a96fe7674fa142ec3f'
Mismatch = cc.Mismatch


class Engine(cc.Engine):
    def __init__(self, context, fixture, accepted, case, mutation=None):
        super().__init__(context, accepted, case)
        self.classes, self.bound, self.binding = cache_source.load(context, fixture, mutation)
        self.mutation = mutation
        self.steps = 0

    def new_cache(self, state=None):
        cache = self.classes.source_make_cache()
        # Source state setter intentionally retains this list; no adapter class.
        cache.state = [mx.array(state, dtype=mx.float32) if state is not None else None,
                       mx.full((self.case['B'], 1, 1), 0.5, dtype=mx.float32)]
        return cache

    def step(self, inputs, cache, *, admit=True):
        self.last = None
        state = cache[0].tolist() if cache[0] is not None else None
        if admit:
            cc.validate(inputs, self.case['weights'], self.case['K'], state)
        self.cache = cache
        self.expected_shape = [len(inputs), len(inputs[0]), self.case['C']]
        slot1 = cache[1]
        arr = mx.array(inputs, dtype=mx.float32)
        self.steps += 1
        activated, qkv = self.bound.source_step(self.self, arr, arr, cache)
        mx.eval(activated, *qkv)
        saved = cc.array_record(cache[0])
        self.last = {'raw': self.observer.raw, 'activated': cc.array_record(activated), 'state': saved,
                     'qkv': [cc.array_record(x) for x in qkv],
                     'state_seen_before_operator': self.observer.state_at_call,
                     'slot1_untouched': cache[1] is slot1,
                     'cache_class': type(cache).__name__, 'state_list_is_cache_storage': cache.state is cache.cache}
        if cache[1] is not slot1:
            raise Mismatch('SLOT1_CHANGED')
        if self.observer.state_at_call != saved:
            raise Mismatch('STATE_UPDATE_ORDER')
        return self.last


def detected(error, specification, delta):
    return (type(error) is Mismatch and str(error) == specification['message']
            and delta == (1 if specification['numeric_required'] else 0))


def run(context, backend):
    raw = context.read_verified(context.roots['code'] / FIXTURE)
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError('CACHE_FIXTURE_GENERATION')
    fixture = json.loads(raw)
    old = context.read_verified(context.roots['code'] / cc.FIXTURE)
    if hashlib.sha256(old).hexdigest() != fixture['accepted_fixture_sha256']:
        raise ValueError('ACCEPTED_CONVOLUTION_FIXTURE')
    accepted = json.loads(old)
    oracle_bytes = context.read_verified(context.roots['code'] / 'scripts/research/glm53_flash/convolution_state/oracle.py')
    if hashlib.sha256(oracle_bytes).hexdigest() != fixture['scalar_oracle_sha256']:
        raise ValueError('INDEPENDENT_ORACLE_BINDING')
    cases = {c['name']: c for c in fixture['cases']}
    observations, lifecycle, mutants, refusals, engines = [], [], [], [], []

    def engine(case, mutation=None):
        e = Engine(context, fixture, accepted, case, mutation)
        engines.append(e)
        return e

    def observe(e, chunk, cache, expected_state, label):
        expected = oracle.transition(chunk, e.case['weights'], expected_state, e.case['K'])
        before = e.numeric
        actual = e.step(chunk, cache)
        cc.compare(actual, expected, fixture)
        if e.numeric - before != 1:
            raise Mismatch('TARGET_EVALUATION_COUNT')
        observations.append({'label': label, 'case': e.case['name'], 'input_sha256': cc.digest(chunk),
                             'weights_sha256': e.weight_binding, 'source': e.binding,
                             'target_step_evaluation_delta': e.numeric - before,
                             'actual': actual, 'oracle': 'PASS'})
        return expected['state']['values']

    def cache_record(cache):
        return {'slots': [cc.array_record(x) if x is not None else None for x in cache.state],
                'left_padding': cc.array_record(cache.left_padding) if cache.left_padding is not None else None,
                'lengths': cc.array_record(cache.lengths) if cache.lengths is not None else None,
                'batch_size': cache.batch_size, 'empty': cache.empty(), 'nbytes': cache.nbytes}

    class Checks(unittest.TestCase):
        def test_partitions(self):
            for case in cases.values():
                whole = None
                for pnum, parts in enumerate(case['partitions']):
                    e = engine(case); cache = e.new_cache(case['state']); state = copy.deepcopy(case['state'])
                    offset = 0; chunks = []
                    for length in parts:
                        chunk = [row[offset:offset + length] for row in case['inputs']]
                        state = observe(e, chunk, cache, state, 'partition-' + str(pnum) + ':' + str(offset))
                        chunks.append(e.last); offset += length
                    self.assertEqual(offset, case['T'])
                    combined = {key: [[row for item in chunks for row in item[key]['values'][b]] for b in range(case['B'])]
                                for key in ('raw', 'activated')}
                    if whole is None:
                        whole = combined
                    for key, stem in [('raw', 'raw'), ('activated', 'silu')]:
                        self.assertTrue(oracle.bounded_equal(combined[key], whole[key],
                                                           fixture['tolerances'][stem + '_atol'], fixture['tolerances'][stem + '_rtol']))

        def test_interleaved_new_cache(self):
            case = cases['configured-k4-state']; e = engine(case)
            streams = [case['inputs'], [[[-x for x in row] for row in b] for b in case['inputs']]]
            caches = [e.new_cache(case['state']), e.new_cache()]
            self.assertIsNot(caches[0].state, caches[1].state)
            states = [copy.deepcopy(case['state']), None]; offset = 0
            for length in [2, 1, 3, 1]:
                for s in (0, 1):
                    states[s] = observe(e, [b[offset:offset + length] for b in streams[s]], caches[s], states[s],
                                        'interleave-' + str(s) + ':' + str(offset))
                offset += length
            fresh = e.new_cache(); self.assertIsNot(fresh.state, caches[0].state)
            observe(e, [b[:2] for b in streams[0]], fresh, None, 'fresh-cache-replacement')

        def test_cache_construction_alias_and_errors(self):
            case = cases['configured-k4-state']; e = engine(case); cls = e.classes.ArraysCache
            fresh = e.classes.source_make_cache(); other = e.classes.source_make_cache()
            self.assertEqual(fresh.state, [None, None]); self.assertIsNot(fresh.state, other.state)
            self.assertTrue(fresh.empty()); self.assertEqual(fresh.batch_size, 1); self.assertEqual(fresh.size(), 0)
            self.assertFalse(fresh.is_trimmable()); self.assertEqual(fresh.meta_state, '')
            self.assertEqual(fresh.prefix_cache_reserve(3), ()); self.assertIsNone(fresh.prefix_cache_merge([], []))
            cache = e.new_cache(case['state']); original_list = cache.state; original_slot = cache[0]
            snapshot = cache.prefix_cache_snapshot(); self.assertIs(snapshot['state'], original_list)
            restored = e.classes.source_make_cache(); restored.prefix_cache_restore(snapshot)
            from_state = cls.from_state(original_list, '')
            self.assertIs(restored.state, original_list); self.assertIs(from_state.state, original_list)
            self.assertIs(restored[0], original_slot)
            replacement = mx.array(case['state'], dtype=mx.float32)
            cache[0] = replacement; self.assertIs(restored[0], replacement); self.assertIs(from_state[0], replacement)
            observe(e, [b[:2] for b in case['inputs']], restored, case['state'], 'snapshot-reference-next-step')
            self.assertIs(cache[0], restored[0]); self.assertIs(from_state[0], restored[0])
            lifecycle.append({'name': 'fresh-factory-and-alias-contract', 'actual': cache_record(cache),
                              'factory_and_constructor': 'ACTUAL_CACHE_METHOD_EXECUTED',
                              'state_and_snapshot_share_references': True, 'independent_fresh_lists': True})
            specifications = fixture['cache_expectations']['errors']
            operations = [('getitem_2', lambda: cache[2]), ('setitem_2', lambda: cache.__setitem__(2, replacement)),
                          ('meta_state', lambda: setattr(cache, 'meta_state', 'invalid')),
                          ('extract_none', lambda: fresh.extract(0))]
            for name, call in operations:
                old_list = cache.state; values = cache_record(cache)
                try:
                    call()
                except Exception as error:
                    self.assertEqual([type(error).__name__, str(error)], specifications[name])
                else:
                    self.fail('Missing declared source error')
                self.assertIs(cache.state, old_list); self.assertEqual(cache_record(cache), values)
                refusals.append({'name': name, 'source_error': specifications[name], 'original_cache_unchanged': True})

        def test_cache_bookkeeping_composition(self):
            case = cases['configured-k4-zero']; e = engine(case); cache = e.new_cache()
            state = observe(e, [b[:2] for b in case['inputs']], cache, None, 'before-bookkeeping')
            spec = fixture['cache_expectations']['advance']
            # Constructor path with left-padding argument is separately real.
            padded = e.classes.ArraysCache(2, left_padding=spec['left_padding_initial'])
            self.assertEqual(padded.left_padding.tolist(), spec['left_padding_initial']); self.assertEqual(padded.batch_size, 2)
            cache.left_padding = mx.array(spec['left_padding_initial'])
            cache.prepare(spec['lengths_initial'])
            original_lengths, original_padding = cache._lengths, cache._left_padding
            slots = cache.state
            cache.advance(spec['advance'])
            self.assertIs(cache._lengths, original_lengths); self.assertIs(cache._left_padding, original_padding)
            self.assertEqual(cache.lengths.tolist(), spec['lengths_after'])
            self.assertEqual(cache.left_padding.tolist(), spec['left_padding_after'])
            self.assertEqual(cache.make_mask(4).tolist(), spec['left_padding_priority_mask_N4'])
            cache.left_padding = None
            self.assertEqual(cache.make_mask(4).tolist(), spec['lengths_only_mask_N4'])
            before = cache_record(cache); cache.finalize()
            self.assertIs(cache.state, slots); self.assertIsNone(cache.lengths); self.assertIsNone(cache.left_padding)
            self.assertEqual(cache._lengths_advance, 0); self.assertEqual(cache._left_padding_advance, 0)
            self.assertIsNone(cache.make_mask(4))
            state = observe(e, [b[2:3] for b in case['inputs']], cache, state, 'after-bookkeeping-next-step')
            self.assertEqual(cache.nbytes, case['B'] * (case['K'] - 1) * case['C'] * 4 + case['B'] * 4)
            lifecycle.append({'name': 'prepare-advance-mask-finalize-next-convolution', 'before_finalize': before,
                              'after_next_step': cache_record(cache), 'scope': 'auxiliary bookkeeping, NOT KDA'})

        def test_batch_lifecycle_composition(self):
            case = cases['configured-k4-zero']; e = engine(case); cache = e.new_cache()
            state = observe(e, [b[:2] for b in case['inputs']], cache, None, 'before-batch-filter')
            cache.left_padding = mx.array([1, 2]); cache.prepare([6, 7])
            cache.filter(mx.array([1, 0]))
            state = [state[1], state[0]]
            self.assertEqual(cache.left_padding.tolist(), [2, 1]); self.assertEqual(cache.lengths.tolist(), [7, 6])
            chunk = [case['inputs'][1][2:3], case['inputs'][0][2:3]]
            state = observe(e, chunk, cache, state, 'filtered-rows-next-step')
            extracted = cache.extract(1)
            self.assertIsNone(extracted.left_padding); self.assertIsNone(extracted.lengths)
            extracted_state = observe(e, [case['inputs'][0][3:4]], extracted, [state[1]], 'extracted-row-next-step')
            lifecycle.append({'name': 'filter-extract-next-step', 'filtered': cache_record(cache), 'extracted': cache_record(extracted)})
            small = cases['configured-k4-state']; e2 = engine(small)
            left = e2.new_cache(small['state']); right = e2.new_cache()
            lstate = observe(e2, [b[:2] for b in small['inputs']], left, small['state'], 'extend-left-prefix')
            rstate = observe(e2, [b[:2] for b in small['inputs']], right, None, 'extend-right-prefix')
            left.prepare([7]); right.prepare([5]); left.extend(right)
            self.assertEqual(left.lengths.tolist(), [7, 5])
            next_input = [small['inputs'][0][2:3], small['inputs'][0][2:3]]
            observe(e2, next_input, left, lstate + rstate, 'extended-batch-next-step')
            full = e2.new_cache(small['state']); empty = e2.classes.source_make_cache()
            full.extend(empty)
            zeros = [[[0.0] * small['C'] for _ in range(small['K'] - 1)]]
            observe(e2, next_input, full, small['state'] + zeros, 'extend-zero-fill-next-step')
            merged = e2.classes.ArraysCache.merge([e2.new_cache(small['state']), e2.classes.source_make_cache()])
            observe(e2, next_input, merged, small['state'] + zeros, 'merged-rows-next-step')
            all_empty = e2.classes.ArraysCache.merge([e2.classes.source_make_cache(), e2.classes.source_make_cache()])
            self.assertEqual(all_empty.left_padding.tolist(), [0, 0]); self.assertEqual(all_empty.state, [None, None])
            # The convolution slice leaves a None slot1 untouched as well.
            observe(e2, next_input, all_empty, None, 'merged-empty-next-step')
            lifecycle.append({'name': 'extend-merge-zero-fill-next-step', 'extended': cache_record(left),
                              'merged': cache_record(merged), 'all_empty_after_convolution': cache_record(all_empty)})

        def test_mutations(self):
            case = cases['configured-k4-state']; chunk = [b[2:3] for b in case['inputs']]
            for name, specification in fixture['mutants'].items():
                identities = []
                for mode in ('normal', 'mutant', 'restored'):
                    mutation = name if mode == 'mutant' else None
                    e = engine(case, mutation); cache = e.new_cache(case['state'])
                    expected_state = copy.deepcopy(case['state'])
                    if name in ('reset_omission', 'cross_stream_alias', 'stale_prefill_state'):
                        prefix = [b[:2] for b in case['inputs']]
                        warm = oracle.transition(prefix, case['weights'], case['state'], case['K'])
                        cc.compare(e.step(prefix, cache), warm, fixture)
                        if name == 'stale_prefill_state':
                            expected_state = warm['state']['values']
                            if mode == 'mutant':
                                cache[0] = mx.array(case['state'], dtype=mx.float32)
                        else:
                            expected_state = None
                            if mode != 'mutant':
                                cache = e.new_cache()
                    before = e.numeric; error = None
                    try:
                        if name == 'wrong_advance':
                            cache.prepare([7]); cache.advance(2)
                            if cache.lengths.tolist() != [5]:
                                raise Mismatch('BOOKKEEPING_ADVANCE')
                        else:
                            expected = oracle.transition(chunk, case['weights'], expected_state, case['K'])
                            cc.compare(e.step(chunk, cache), expected, fixture)
                    except Exception as caught:
                        error = caught
                    delta = e.numeric - before
                    if mode == 'mutant':
                        self.assertTrue(detected(error, specification, delta), (name, type(error).__name__, str(error), delta))
                    else:
                        if error is not None:
                            raise error
                        self.assertEqual(delta, 1 if specification['numeric_required'] else 0)
                    identity = {'input': cc.digest(chunk), 'weights': e.weight_binding,
                                'environment': context.manifest['python_sha256'],
                                'original_cache_capsule': e.binding['cache_capsule_sha256'],
                                'original_convolution_capsule': e.binding['convolution_capsule_sha256']}
                    identities.append(identity)
                    mutants.append({'name': name, 'mode': mode, 'detected': mode == 'mutant',
                                    'exception': type(error).__name__ if error else None,
                                    'message': str(error) if error else None,
                                    'target_step_evaluation_delta': delta, 'total_evaluations_including_warmup': e.numeric,
                                    'actual': e.last, 'cache_after': cache_record(cache), 'identity': identity,
                                    'source': e.binding})
                self.assertEqual(identities[0], identities[1]); self.assertEqual(identities[0], identities[2])

        def test_classifier(self):
            spec = fixture['mutants']['wrong_slot']
            self.assertTrue(detected(Mismatch('SLOT1_CHANGED'), spec, 1))
            self.assertFalse(detected(RuntimeError('SLOT1_CHANGED'), spec, 1))
            self.assertFalse(detected(Mismatch('unrelated'), spec, 1))
            self.assertFalse(detected(Mismatch('SLOT1_CHANGED'), spec, 0))
            self.assertFalse(detected(Mismatch('SLOT1_CHANGED'), spec, 2))
            self.assertFalse(detected(None, spec, 1))
            bookkeeping = fixture['mutants']['wrong_advance']
            self.assertTrue(detected(Mismatch('BOOKKEEPING_ADVANCE'), bookkeeping, 0))
            self.assertFalse(detected(Mismatch('BOOKKEEPING_ADVANCE'), bookkeeping, 1))

        def test_research_refusal_and_callee_failure(self):
            case = cases['configured-k4-state']; e = engine(case); cache = e.new_cache(case['state'])
            original = cache[0]; before = cache_record(cache)
            bad = copy.deepcopy(case['inputs']); bad[0][0][0] = float('nan')
            with self.assertRaises(cc.ResearchInputError) as caught:
                e.step(bad, cache)
            self.assertEqual(str(caught.exception), 'INPUT_NONFINITE'); self.assertEqual(e.steps, 0)
            self.assertEqual(e.numeric, 0); self.assertIs(cache[0], original); self.assertEqual(cache_record(cache), before)
            e.observer.fault = True; chunk = [b[:2] for b in case['inputs']]
            expected = oracle.transition(chunk, case['weights'], case['state'], case['K'])
            with self.assertRaises(cc.InjectedConvolutionFailure) as caught:
                e.step(chunk, cache)
            self.assertEqual(str(caught.exception), 'AFTER_STATE_WRITE'); self.assertEqual(e.numeric, 0)
            self.assertEqual(cc.array_record(cache[0]), expected['state']); self.assertIsNot(cache[0], original)
            refusals.append({'name': 'research-input-refusal', 'source_steps': 0, 'numeric_delta': 0,
                             'scope': 'strict research entry, not upstream refusal guarantee'})
            refusals.append({'name': 'controlled-callee-failure', 'source_steps': e.steps, 'numeric_delta': e.numeric,
                             'saved_state': cc.array_record(cache[0]), 'scope': 'actual slot0 write before operator, not KDA/error rollback guarantee'})

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    names = sorted(t._testMethodName for t in suite)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    print(json.dumps({'event': 'cache_lifecycle_observations', 'backend': backend,
                      'observations': observations, 'lifecycle': lifecycle, 'mutations': mutants, 'refusals': refusals,
                      'actual_convolution_evaluations': sum(e.numeric for e in engines),
                      'actual_source_step_calls': sum(e.steps for e in engines), 'source_instances': len(engines),
                      'fixture_sha256': FIXTURE_SHA256, 'scalar_oracle_sha256': fixture['scalar_oracle_sha256'],
                      'cache_scope': 'ACTUAL_CACHE_METHOD_EXECUTED for recorded finite operations',
                      'KDA_or_full_model': 'NOT_EXECUTED', 'generation': context.manifest['generation']}, allow_nan=False), flush=True)
    print(json.dumps({'event': 'result', 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
                      'tests_run': result.testsRun, 'test_ids': names, 'skips': len(result.skipped),
                      'failures': len(result.failures), 'errors': len(result.errors),
                      'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped else 1

"""Finite source-slice composition checks; injected dependencies enter after fences."""
import copy
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE_SHA256 = '3ef5266921478b31a247761111dddcc88ae2942e8420ad3d6f481b3c76fc891a'
FIXTURE = 'fixtures/research/glm53-flash-convolution-state-v1/fixtures.json'


class Mismatch(AssertionError):
    pass


class ResearchInputError(ValueError):
    pass


class InjectedConvolutionFailure(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def array_record(value):
    mx.eval(value)
    return {'shape': list(value.shape), 'values': value.tolist()}


def validate(inputs, weights, kernel, state):
    """Research-only, exact built-in finite data admission before MLX construction."""
    if type(kernel) is not int or kernel not in (1, 2, 3, 4):
        raise ResearchInputError('INPUT_KERNEL')
    def tensor(value, shape, magnitude):
        if shape:
            if type(value) is not list or len(value) != shape[0]:
                raise ResearchInputError('INPUT_SHAPE')
            for item in value:
                tensor(item, shape[1:], magnitude)
        elif type(value) not in (int, float):
            raise ResearchInputError('INPUT_TYPE')
        elif not math.isfinite(value):
            raise ResearchInputError('INPUT_NONFINITE')
        elif abs(value) > magnitude:
            raise ResearchInputError('INPUT_RANGE')
    if (type(inputs) is not list or not 1 <= len(inputs) <= 2 or type(inputs[0]) is not list
            or not 1 <= len(inputs[0]) <= 8 or type(inputs[0][0]) is not list
            or len(inputs[0][0]) not in (3, 6)):
        raise ResearchInputError('INPUT_SHAPE')
    B, T, C = len(inputs), len(inputs[0]), len(inputs[0][0])
    tensor(inputs, (B, T, C), 1.5)
    tensor(weights, (C, kernel, 1), 1)
    if state is not None:
        tensor(state, (B, kernel - 1, C), 1.5)
    return B, T, C


class InertCache:
    """RESEARCH_ADAPTER: direct indexed slots, no real ArraysCache/advance/reset claim."""
    def __init__(self, state=None):
        self.slot1_marker = object()
        self.slots = [state, self.slot1_marker]
        self.writes = 0

    def __getitem__(self, index):
        return self.slots[index]

    def __setitem__(self, index, value):
        self.slots[index] = value
        self.writes += 1


class ConvObserver:
    """Observe the real layer; shape failure is checked after actual evaluation."""
    def __init__(self, layer, owner):
        self.layer, self.owner = layer, owner
        self.raw = None
        self.state_at_call = None
        self.fault = False

    def __call__(self, inputs):
        engine = self.owner
        self.state_at_call = array_record(engine.cache[0]) if engine.cache is not None else None
        if self.fault:
            raise InjectedConvolutionFailure('AFTER_STATE_WRITE')
        raw = self.layer(inputs)
        mx.eval(raw)
        self.raw = array_record(raw)
        engine.numeric += 1
        if self.raw['shape'] != engine.expected_shape:
            raise Mismatch('RAW_SHAPE')
        return raw


class Engine:
    def __init__(self, context, fixture, case, mutation=None):
        self.case, self.mutation, self.numeric = case, mutation, 0
        self.last = None
        self.bound, self.binding = source.load(context, fixture, mutation)
        self.self = types.SimpleNamespace(qkv_dim=case['C'] // 3, num_heads=1,
                                          head_dim=case['C'] // 3, conv_kernel_size=case['K'])
        layer = self.bound.source_construct(self.self)
        weights = mx.array(case['weights'], dtype=mx.float32)
        if mutation == 'reverse_taps':
            weights = weights[:, ::-1, :]
        elif mutation == 'wrong_channel_axis':
            weights = weights.transpose(1, 0, 2)
        layer.weight = weights
        mx.eval(layer.weight)
        self.weight_binding = digest(array_record(layer.weight))
        self.observer = ConvObserver(layer, self)
        self.self.conv1d = self.observer
        self.cache = None

    def new_cache(self, state=None):
        return InertCache(mx.array(state, dtype=mx.float32) if state is not None else None)

    def step(self, inputs, cache, *, admit=True):
        state = cache[0].tolist() if cache is not None and cache[0] is not None else None
        if admit:
            validate(inputs, self.case['weights'], self.case['K'], state)
        self.cache = cache
        self.expected_shape = [len(inputs), len(inputs[0]), self.case['C']]
        before_writes = cache.writes if cache is not None else 0
        arr = mx.array(inputs, dtype=mx.float32)
        activated, qkv = self.bound.source_step(self.self, arr, arr, cache)
        mx.eval(activated, *qkv)
        saved = array_record(cache[0]) if cache is not None else None
        if cache is not None and (cache.writes != before_writes + 1 or cache[1] is not cache.slot1_marker):
            raise Mismatch('SOURCE_SLOT_EFFECT')
        if self.observer.state_at_call != saved:
            raise Mismatch('STATE_UPDATE_ORDER')
        self.last = {'raw': self.observer.raw, 'activated': array_record(activated), 'state': saved,
                'qkv': [array_record(x) for x in qkv], 'state_seen_before_operator': self.observer.state_at_call,
                'slot1_untouched': cache is None or cache[1] is cache.slot1_marker}
        return self.last


def compare(actual, expected, fixture, *, state=True):
    tolerance = fixture['tolerances']
    for key, stem in [('raw', 'raw'), ('activated', 'silu')]:
        if actual[key]['shape'] != expected[key]['shape']:
            raise Mismatch('RAW_SHAPE' if key == 'raw' else 'ACTIVATED_SHAPE')
        if not oracle.bounded_equal(actual[key]['values'], expected[key]['values'],
                                    tolerance[stem + '_atol'], tolerance[stem + '_rtol']):
            raise Mismatch('RAW_VALUES' if key == 'raw' else 'ACTIVATED_VALUES')
    if state:
        if actual['state'] is None or actual['state']['shape'] != expected['state']['shape']:
            raise Mismatch('STATE_SHAPE')
        if actual['state']['values'] != expected['state']['values']:
            raise Mismatch('STATE_VALUES')
    for a, b in zip(actual['qkv'], expected['qkv']):
        if a['shape'] != b['shape'] or not oracle.bounded_equal(a['values'], b['values'],
                                                              tolerance['silu_atol'], tolerance['silu_rtol']):
            raise Mismatch('QKV_LAYOUT')


def detected(error, specification, numerical_count):
    return (type(error) is Mismatch and str(error) == specification['message']
            and (numerical_count > 0 if specification['numeric_required'] else numerical_count == 0))


def run(context, backend):
    raw = context.read_verified(context.roots['code'] / FIXTURE)
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError('FIXTURE_GENERATION')
    fixture = json.loads(raw)
    cases = {c['name']: c for c in fixture['cases']}
    observations, mutants, refusals, engines = [], [], [], []
    def engine(case, mutation=None):
        e = Engine(context, fixture, case, mutation)
        engines.append(e)
        return e
    def observe(e, name, chunk, cache, expected_state, label, *, state=True, admit=True):
        expected = oracle.transition(chunk, e.case['weights'], expected_state, e.case['K'])
        actual = e.step(chunk, cache, admit=admit)
        compare(actual, expected, fixture, state=state)
        observations.append({'name': name, 'label': label, 'source': e.binding,
                             'input_sha256': digest(chunk), 'weight_sha256': e.weight_binding,
                             'actual': actual, 'oracle': 'PASS'})
        return expected['state']['values'], actual
    def sequence(case, parts, label, mutation=None):
        e = engine(case, mutation);cache = e.new_cache(case['state']);state = copy.deepcopy(case['state']);offset=0; joined=[]
        for length in parts:
            chunk = [b[offset:offset+length] for b in case['inputs']]
            state, actual = observe(e, case['name'], chunk, cache, state, label + ':' + str(offset))
            joined.append(actual);offset += length
        if offset != case['T']:
            raise Mismatch('PARTITION_COVERAGE')
        return e, joined

    class Checks(unittest.TestCase):
        def test_partition_composition(self):
            for case in cases.values():
                whole = None
                for index, parts in enumerate(case['partitions']):
                    _, chunks = sequence(case, parts, 'partition-' + str(index))
                    combined = {k: [[row for x in chunks for row in x[k]['values'][b]] for b in range(case['B'])]
                                for k in ['raw', 'activated']}
                    if whole is None:
                        whole = combined
                    for k, stem in [('raw', 'raw'), ('activated', 'silu')]:
                        self.assertTrue(oracle.bounded_equal(combined[k], whole[k],
                                                            fixture['tolerances'][stem+'_atol'], fixture['tolerances'][stem+'_rtol']))
                e=engine(case)
                observe(e, case['name'], case['inputs'], None, None, 'cache-none', state=False)

        def test_interleaved_and_new_cache(self):
            case=cases['configured-k4-state'];e=engine(case)
            streams=[case['inputs'], [[[-x for x in row] for row in b] for b in case['inputs']]]
            caches=[e.new_cache(case['state']),e.new_cache()];states=[copy.deepcopy(case['state']),None]
            self.assertIsNot(caches[0],caches[1]);self.assertIsNot(caches[0].slots,caches[1].slots)
            offset=0
            for length in [2,1,3,1]:
                for stream in [0,1]:
                    chunk=[b[offset:offset+length] for b in streams[stream]]
                    states[stream],_=observe(e,case['name'],chunk,caches[stream],states[stream],'interleaved-'+str(stream)+':'+str(offset))
                offset+=length
            fresh=e.new_cache();self.assertIsNot(fresh,caches[0])
            observe(e,case['name'],[b[:2] for b in streams[0]],fresh,None,'explicit-new-cache')

        def test_research_refusals_and_failure_order(self):
            case=cases['configured-k4-state'];e=engine(case);cache=e.new_cache(case['state'])
            original=array_record(cache[0]);slot=cache[0]
            variants=[]
            for value,code in [(float('nan'),'INPUT_NONFINITE'),(float('inf'),'INPUT_NONFINITE'),('x','INPUT_TYPE'),(True,'INPUT_TYPE'),(2.0,'INPUT_RANGE')]:
                bad=copy.deepcopy(case['inputs']);bad[0][0][0]=value;variants.append((bad,code))
            variants += [([], 'INPUT_SHAPE'),([[]], 'INPUT_SHAPE'),([[[0.0]]], 'INPUT_SHAPE'),(tuple(case['inputs']),'INPUT_SHAPE')]
            for bad,code in variants:
                before=e.numeric
                with self.assertRaises(ResearchInputError) as caught:e.step(bad,cache)
                self.assertEqual(str(caught.exception),code);self.assertEqual(e.numeric,before)
                self.assertIs(cache[0],slot);self.assertEqual(array_record(cache[0]),original)
                refusals.append({'code':code,'numerical_execution':False,'source_state_unchanged':True,'scope':'research entry validation only'})
            e.observer.fault=True;chunk=[b[:2] for b in case['inputs']];expected=oracle.transition(chunk,case['weights'],case['state'],case['K'])
            with self.assertRaises(InjectedConvolutionFailure) as caught:e.step(chunk,cache)
            self.assertEqual(str(caught.exception),'AFTER_STATE_WRITE');self.assertEqual(e.numeric,0)
            self.assertEqual(array_record(cache[0]),expected['state']);self.assertEqual(e.observer.state_at_call,expected['state'])
            refusals.append({'code':'AFTER_STATE_WRITE','numerical_execution':False,'source_slot0_updated_before_injected_callee_failure':True,'scope':'exact source ordering with controlled callee; not an upstream error guarantee'})

        def test_mutants_normal_mutant_restored(self):
            def trial(case,name,mutated):
                e=engine(case,name if mutated else None)
                cache=e.new_cache(case['state'])
                if name in ('reset_omission','cross_stream_alias','stale_prefill_state'):
                    prefix=[b[:3] for b in case['inputs']]
                    state,_=observe(e,case['name'],prefix,cache,case['state'],name+':warmup')
                    if name=='stale_prefill_state':
                        target=cache
                        if mutated:target.slots[0]=mx.array(case['state'],dtype=mx.float32)
                        chunk=[b[3:4] for b in case['inputs']];expected_state=state
                    else:
                        target=cache if mutated else e.new_cache();expected_state=None
                        chunk=[b[3:5] for b in case['inputs']]
                        if name=='cross_stream_alias':chunk=[[[-x for x in row] for row in b] for b in chunk]
                    observe(e,case['name'],chunk,target,expected_state,name+(':mutant' if mutated else ':normal'),admit=True)
                else:
                    observe(e,case['name'],case['inputs'],cache,case['state'],name+(':mutant' if mutated else ':normal'))
                return e
            for name,spec in fixture['mutants'].items():
                case=cases[spec['case']];identity=digest(case)
                baseline=trial(case,name,False);first=len(engines);caught=None
                try:trial(case,name,True)
                except BaseException as exc:caught=exc
                numeric=sum(e.numeric for e in engines[first:])
                mutant_evidence=[{'source':e.binding,'weight_sha256':e.weight_binding,'last_completed_step':e.last,
                                  'raw_at_last_operator':e.observer.raw,'state_at_last_operator':e.observer.state_at_call}
                                 for e in engines[first:]]
                self.assertIsNotNone(caught,name)
                self.assertTrue(detected(caught,spec,numeric),(name,type(caught).__name__,str(caught),numeric))
                restored=trial(case,name,False)
                self.assertEqual(digest(case),identity);self.assertEqual(baseline.weight_binding,restored.weight_binding)
                self.assertEqual(baseline.binding,restored.binding)
                mutants.append({'name':name,'status':'DETECTED_EXPECTED_MECHANISM','exception':type(caught).__name__,'message':str(caught),'numeric_evaluations':numeric,'raw_mutant_evidence':mutant_evidence,'normal_restored_input_sha256':identity,'normal_restored_weight_sha256':baseline.weight_binding,'restored_source_binding':restored.binding})

        def test_classifier_wrong_type_and_message(self):
            spec={'message':'RAW_VALUES','numeric_required':True}
            self.assertFalse(detected(ValueError('RAW_VALUES'),spec,1))
            self.assertFalse(detected(Mismatch('wrong'),spec,1))
            self.assertFalse(detected(Mismatch('RAW_VALUES'),spec,0))
            self.assertTrue(detected(Mismatch('RAW_VALUES'),spec,1))

        def test_k1_source_diagnostic(self):
            case=copy.deepcopy(cases['k2-signed']);case.update(name='k1-source-diagnostic',K=1,state=None)
            case['weights']=[w[:1] for w in case['weights']]
            e=engine(case);cache=e.new_cache();actual=e.step(case['inputs'],cache)
            expected=oracle.transition(case['inputs'],case['weights'],None,1)
            compare(actual,expected,fixture,state=False)
            self.assertEqual(actual['state'],{'shape':[case['B'],case['T'],case['C']],'values':case['inputs']})
            self.assertNotEqual(actual['state']['shape'],expected['state']['shape'])
            observations.append({'name':case['name'],'label':'SOURCE_DEFINED_MINUS_ZERO_RETENTION','actual':actual,'conceptual_empty_state':expected['state'],'scope':'one-call diagnostic; K1 empty-state composition NOT_QUALIFIED'})

    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    ids=[test._testMethodName for test in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    for row in observations:
        print(json.dumps({'event':'convolution_observation',**row},sort_keys=True,allow_nan=False),flush=True)
    print(json.dumps({'event':'convolution_summary','backend':backend,'generation':context.manifest['generation'],
                      'fixture_sha256':FIXTURE_SHA256,'observations':len(observations),
                      'actual_conv_evaluations':sum(e.numeric for e in engines),'source_engines':len(engines),
                      'mutants':mutants,'refusals':refusals,'source_slice':'EXECUTED','cache_interface':'RESEARCH_ADAPTER',
                      'real_cache':'NOT_EXECUTED','full_sanitation':'SOURCE_READ_ONLY_NOT_QUALIFIED',
                      'KDA_advance_slot1':'NOT_EXECUTED','physical_IO':'NOT_MEASURED','empty_chunks':'NOT_QUALIFIED'},sort_keys=True),flush=True)
    print(json.dumps({'event':'result','status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,
                      'test_ids':ids,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
                      'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}),flush=True)
    return 0 if result.wasSuccessful() and not result.skipped else 1

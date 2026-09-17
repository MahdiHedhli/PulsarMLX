"""Linear attention beyond the 5-token kernel domain, in the successor child.

Single-call prefills of S in {8, 16, 33, 64} through the admitted module (the
linear track's namespace with its counters and kernel admission, loaded with
max_sequence 64 for this operation only) against the chunked composition of
the accepted reference; the same inputs also run chunked (<= 5 tokens per
call, inside the existing domain) with the real ArraysCache. Both paths on the
CPU ops path and the Metal kernel path. Domain-gate control: the default load
(max_sequence 5) must refuse the single S = N call.
"""
import hashlib
import json
import math
import resource
import types
import unittest

FIXTURE = 'fixtures/research/glm53-flash-linear-long-v1/fixtures.json'
LINEAR_FIXTURE = 'fixtures/research/glm53-flash-linear-attention-v1/fixtures.json'
CACHE_FIXTURE = 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'
MAX_SEQUENCE = 64


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


def build(ns, case, mx):
    cfg = case['config']
    config = types.SimpleNamespace(**cfg)
    module = ns['Glm5NextLinearAttention'](config)
    for name, value in case['parameters'].items():
        owner = module; parts = name.split('.')
        for part in parts[:-1]:
            owner = getattr(owner, part)
        setattr(owner, parts[-1], mx.array(value, dtype=mx.float32))
    return module


def fresh_cache(cache_classes, mx):
    cache = cache_classes.source_make_cache()
    cache.state = [None, None]
    return cache


def run(context, backend, mx, nn, attention_source, attention_oracle, accepted_recurrence, cache_source, long_oracle):
    root = context.roots['code']
    raw = context.read_verified(root / FIXTURE); fixture = json.loads(raw)
    linear_fixture = json.loads(context.read_verified(root / LINEAR_FIXTURE)); cache_fixture = json.loads(context.read_verified(root / CACHE_FIXTURE))
    tol = fixture['tolerances']
    emit('linear_long_binding', fixture_sha256=digest(raw), backend=backend, actual_default_device=str(mx.default_device()), max_sequence=MAX_SEQUENCE)

    observations = []

    class LinearLong(unittest.TestCase):
        def test_frozen_reference_recomputes(self):
            for case in fixture['cases']:
                self.assertEqual(long_oracle.run(case), fixture['expected'][case['fixture_id']], case['fixture_id'])
            emit('frozen_reference', status='RECOMPUTED_EQUAL', cases=len(fixture['cases']))

        def test_long_prefill(self):
            attention = attention_source.load(context, linear_fixture, None, max_sequence=MAX_SEQUENCE)
            cache_classes, _, cache_binding = cache_source.load(context, cache_fixture)
            for case in fixture['cases']:
                exp = fixture['expected'][case['fixture_id']]; S = case['tokens']
                module = build(attention.namespace, case, mx)
                x = mx.array([case['inputs']], dtype=mx.float32)
                # single call
                cache = fresh_cache(cache_classes, mx)
                y = module(x, None, cache); c0, c1 = cache.state; mx.eval(y, c0, c1)
                single = {'output_error': max_error(y[0].tolist(), exp['output']),
                          'cache0_ok': attention_oracle.close(c0.tolist(), [exp['final_cache0'][0]], tol['cache0_atol'], tol['cache0_rtol']),
                          'cache1_ok': attention_oracle.close(c1.tolist(), [exp['final_cache1'][0]], tol['cache1_atol'], tol['cache1_rtol'])}
                single_y = y
                # chunked (inside the existing domain)
                cache = fresh_cache(cache_classes, mx); rows = []; chunk_ok = True
                for rec in exp['chunks']:
                    ts = rec['tokens']; yc = module(x[:, ts[0]:ts[-1] + 1], None, cache); cc0, cc1 = cache.state; mx.eval(yc, cc0, cc1)
                    ok0 = attention_oracle.close(cc0.tolist(), [rec['cache0_after'][0]], tol['cache0_atol'], tol['cache0_rtol'])
                    ok1 = attention_oracle.close(cc1.tolist(), [rec['cache1_after'][0]], tol['cache1_atol'], tol['cache1_rtol'])
                    err = max_error(yc[0].tolist(), [exp['output'][t] for t in ts]); rows.append(yc)
                    chunk_ok = chunk_ok and ok0 and ok1 and err <= tol['output']
                chunked_y = mx.concatenate(rows, axis=1); mx.eval(chunked_y)
                d = mx.abs(single_y - chunked_y).max().item()
                stats = attention.stats if hasattr(attention, 'stats') else None
                row = {'fixture_id': case['fixture_id'], 'tokens': S, 'single_call': single, 'chunked_ok': chunk_ok, 'chunks': len(exp['chunks']),
                       'single_vs_chunked_candidate': d if math.isfinite(d) else 'inf', 'reference_maximum_radii': exp['maximum_radii_over_chunks'],
                       'kernel_submissions': stats['kernel_API_submissions'] if stats else None}
                row['pass'] = single['output_error'] <= tol['output'] and single['cache0_ok'] and single['cache1_ok'] and chunk_ok
                observations.append(row); emit('linear_long_observation', **row)
                self.assertTrue(row['pass'], json.dumps(row))
            emit('cache_binding', **{k: v for k, v in cache_binding.items() if isinstance(v, str)})

        def test_domain_gate(self):
            default = attention_source.load(context, linear_fixture, None)   # max_sequence 5, as every earlier operation
            cache_classes, _, _ = cache_source.load(context, cache_fixture)
            case = fixture['cases'][0]
            module = build(default.namespace, case, mx)
            x = mx.array([case['inputs']], dtype=mx.float32)
            if backend == 'metal':
                with self.assertRaisesRegex(ValueError, 'MODULE_KERNEL_DOMAIN'):
                    y = module(x, None, fresh_cache(cache_classes, mx)); mx.eval(y)
                emit('domain_gate', outcome='REFUSED_AT_DEFAULT_MAX_SEQUENCE_5', tokens=case['tokens'])
            else:
                y = module(x, None, fresh_cache(cache_classes, mx)); mx.eval(y)
                emit('domain_gate', outcome='CPU_OPS_PATH_HAS_NO_KERNEL_GATE', tokens=case['tokens'])

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LinearLong)
    ids = [t._testMethodName for t in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('linear_long_summary', backend=backend, observations=observations,
         scope='SINGLE_CALL_PREFILL_S_UP_TO_64_VS_CHUNKED_ACCEPTED_REFERENCE; B=1 H=1 D=32 K=2 I=4; no padding; kernel admission raised to 64 for this operation only')
    emit('result', status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL', test_ids=ids,
         tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1

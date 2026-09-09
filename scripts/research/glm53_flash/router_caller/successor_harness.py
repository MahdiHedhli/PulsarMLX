"""Compose unchanged mathematical definitions with explicit successor context.

This is a new entrypoint, not an import or qualification of the historical
runner. Only the enumerated dependency imports are omitted. No historical
guard object is imported, modified, or installed in sys.modules.
"""
import ast
import copy
import json
import os
from pathlib import Path
import resource
import types
import unittest


def component(context, name, dependencies, omitted=(), folder='router_caller'):
    path = context.roots['code'] / 'scripts/research/glm53_flash' / folder / (name + '.py')
    raw = context.read_verified(path)
    tree = ast.parse(raw)
    seen = []
    body = []
    for node in tree.body:
        spelling = ast.unparse(node) if isinstance(node, (ast.Import, ast.ImportFrom)) else None
        if spelling in omitted:
            seen.append(spelling)
        else:
            body.append(node)
    if sorted(seen) != sorted(omitted):
        raise ValueError('SUCCESSOR_DEPENDENCY_IMPORT_SHAPE')
    # Logical exception namespaces retain the frozen control table's names.
    # They do not install modules or pretend the old guard was executed.
    namespace = {'__name__': name, **dependencies}
    exec(compile(ast.Module(body=body, type_ignores=[]), 'successor-component:' + name, 'exec'), namespace)
    return types.SimpleNamespace(**namespace)


def run(context, mode, backend):
    context.verify()
    context.verify_child_interpreter(context.phase)
    import mlx.core as mx
    mx.set_memory_limit(512 * 1024**2)
    mx.set_cache_limit(16 * 1024**2)
    mx.set_default_device(mx.cpu if backend == 'cpu' else mx.gpu)
    if mode == 'linear':
        import mlx.nn as nn
        accepted_recurrence = component(context, 'oracle', {}, folder='recurrent_dispatch')
        recurrent_verifier = component(context, 'source', {'mx': mx, 'nn': nn}, folder='recurrent_dispatch')
        independent = component(context, 'oracle', {}, folder='linear_attention')
        module_source = component(context, 'source', {'mx': mx, 'nn': nn,
                                  'recurrent_verifier': recurrent_verifier}, folder='linear_attention')
        actual_cache = component(context, 'source', {'mx': mx, 'nn': nn}, folder='cache_lifecycle')
        archive = component(context, 'rc_archive', {})
        controls = component(context, 'controls', {'mx': mx, 'nn': nn, 'oracle': independent,
                             'accepted_recurrence': accepted_recurrence, 'source': module_source,
                             'cache_source': actual_cache, 'archive': archive}, folder='linear_attention')
        return controls.run(context, backend)
    if mode == 'dispatch':
        import mlx.nn as nn
        independent = component(context, 'oracle', {}, folder='recurrent_dispatch')
        dispatch_source = component(context, 'source', {'mx': mx, 'nn': nn}, folder='recurrent_dispatch')
        actual_cache = component(context, 'source', {'mx': mx, 'nn': nn}, folder='cache_lifecycle')
        controls = component(context, 'controls', {'mx': mx, 'oracle': independent,
                             'source': dispatch_source, 'cache_source': actual_cache}, folder='recurrent_dispatch')
        return controls.run(context, backend)
    if mode == 'recurrent':
        import mlx.nn as nn
        independent = component(context, 'oracle', {}, folder='recurrent_ops')
        recurrent_source = component(context, 'source', {'mx': mx, 'nn': nn}, folder='recurrent_ops')
        actual_cache = component(context, 'source', {'mx': mx, 'nn': nn}, folder='cache_lifecycle')
        controls = component(context, 'controls', {'mx': mx, 'oracle': independent,
                             'source': recurrent_source, 'cache_source': actual_cache}, folder='recurrent_ops')
        return controls.run(context, backend)
    if mode in ('convolution', 'cache'):
        import mlx.nn as nn
        independent = component(context, 'oracle', {}, folder='convolution_state')
        source_slice = component(context, 'source', {'mx': mx, 'nn': nn}, folder='convolution_state')
        controls = component(context, 'controls', {'mx': mx, 'nn': nn, 'oracle': independent,
                                                 'source': source_slice}, folder='convolution_state')
        if mode == 'cache':
            actual_cache = component(context, 'source', {'mx': mx, 'nn': nn}, folder='cache_lifecycle')
            cache_controls = component(context, 'controls',
                                       {'mx': mx, 'nn': nn, 'cc': controls, 'oracle': independent,
                                        'cache_source': actual_cache}, folder='cache_lifecycle')
            return cache_controls.run(context, backend)
        return controls.run(context, backend)
    checks = component(context, 'rc_checks', {})
    oracle = component(context, 'rc_oracle', {})
    source = component(context, 'rc_source', {'guard': context}, ('import rc_guard as guard',))
    runtime = component(context, 'rc_runtime', {'guard': context, 'source': source, 'checks': checks},
                        ('import rc_guard as guard', 'import rc_source as source', 'import rc_checks as checks'))
    if mode == 'discrimination':
        independent = component(context, 'successor_discrimination_oracle', {})
        controls = component(context, 'successor_discrimination',
                             {'source': source, 'runtime': runtime, 'oracle': independent})
        return controls.run(context, backend)
    path = context.roots['code'] / 'scripts/research/tests/test_glm53_flash_router_caller_numeric.py'
    tree = ast.parse(context.read_verified(path))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if [n.name for n in classes] != ['EvidenceCase', 'SingleCase', 'Matrix']:
        raise ValueError('SUCCESSOR_FROZEN_TEST_CLASS_SHAPE')
    namespace = {'__name__': 'successor_frozen_numeric_classes', 'copy': copy, 'json': json,
                 'os': os, 'unittest': unittest, 'Path': Path, 'PHASE': context.phase,
                 'SOURCE': context.roots['code'], 'runtime': runtime, 'source': source,
                 'oracle': oracle, 'checks': checks}
    exec(compile(ast.Module(body=classes, type_ignores=[]), 'successor-frozen-numeric-classes', 'exec'), namespace)
    selected = namespace['SingleCase' if mode == 'case' else 'Matrix']

    # Only fixture allocation changes; every numerical test/classifier method
    # and tearDown observation producer is the exact frozen class definition.
    class ExplicitFixtureCase(selected):
        @classmethod
        def setUpClass(cls):
            root = context.roots['fixtures']
            cls.f = context.parse(context.read_verified(root / 'cases.json'))
            cls.table = context.parse(context.read_verified(root / 'controls.json'))
            cls.cases = {c['name']: c for c in cls.f['cases']}
            cls.r = runtime.Runtime(context.phase)
            cls.controls = []; cls.probes = []; cls.domains = []; cls.compositions = []

    os.environ['FLASH_ROUTER_CALLER_MODE'] = mode
    os.environ['FLASH_ADMITTED_BACKEND'] = backend
    requests = []
    original = Path.read_bytes
    expected = {r['path'].removeprefix('upstream/'): r for r in context.manifest['source_inputs']
                if r['path'].startswith('upstream/')}

    def traced_read(path):
        if not path.is_relative_to(context.phase / 'source'):
            return original(path)
        name = path.relative_to(context.phase / 'source').as_posix()
        row = expected[name]
        record = {'order': len(requests), 'path': 'source/' + name,
                  'operation': 'Path.read_bytes/read-entire-file', 'offset': 0,
                  'logical_requested_bytes': row['bytes'], 'numeric_syscall_request_size': 'NOT_OBSERVED',
                  'returned_bytes': None, 'status': 'ATTEMPTED'}
        requests.append(record)
        try:
            raw = context.read(path, row['bytes'])
            if context.sha(raw) != row['sha256']:
                raise ValueError('SUCCESSOR_STAGED_SOURCE_DRIFT')
        except BaseException as exc:
            record.update(status='RAISED', exception_type=type(exc).__name__)
            raise
        record.update(returned_bytes=len(raw), sha256=context.sha(raw), status='RETURNED')
        return raw

    Path.read_bytes = traced_read
    try:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExplicitFixtureCase))
    finally:
        Path.read_bytes = original
    context.verify()
    print(json.dumps({'event': 'successor_source_requests', 'requests': requests,
                      'scope': 'ordered logical source byte requests and returned bytes; no syscall or physical-I/O measurement'}), flush=True)
    print(json.dumps({'event': 'successor_composition', 'historical_guard_imported': False,
                      'historical_runner_executed': False, 'sys_modules_replacements': [],
                      'unchanged_definitions': ['rc_source', 'rc_runtime', 'rc_oracle', 'rc_checks'],
                      'explicit_dependencies': ['guard context', 'source component', 'checks component'],
                      'fixture_setup': 'new explicit-root setup; frozen numerical methods unchanged',
                      'generation': context.manifest['generation']}), flush=True)
    print(json.dumps({'event': 'result', 'status': 'PASS' if result.wasSuccessful() else 'FAIL',
                      'tests_run': result.testsRun, 'failures': len(result.failures),
                      'errors': len(result.errors), 'skips': len(result.skipped),
                      'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped else 1

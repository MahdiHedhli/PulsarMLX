"""Full exact source bodies/decorators; fresh compilation objects per variant."""
import ast
from functools import partial
import hashlib
import json
import textwrap
import types
from typing import Optional, Tuple

PREFIX = 'scripts/research/glm53_flash/recurrent_ops/'
NAMES = ('compute_g', 'compute_g_safe', '_gated_delta_step_ops', 'gated_delta_ops', 'gated_delta_update')
ORIGIN_SHA256 = 'e15cd83bfc0bfff3de7a9563aa6978f7e39e0e248cc8a55ca9482f1ce18f54d8'
CALLER_SHA256 = '6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196'


def verify(raw, original, language, provenance):
    digest = lambda b: hashlib.sha256(b).hexdigest()
    if digest(original) != ORIGIN_SHA256 or digest(language) != CALLER_SHA256 or digest(raw) != provenance['capsule_sha256']:
        raise ValueError('RECURRENT_SOURCE_BINDING')
    tree = ast.parse(raw); upstream = {n.name: n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef)}
    if [(type(n).__name__, getattr(n, 'name', None)) for n in tree.body] != [('FunctionDef', n) for n in (*NAMES, 'source_recurrent_step')]:
        raise ValueError('RECURRENT_CLOSURE')
    for node, span in zip(tree.body[:5], provenance['source_spans']):
        selected = original[span['byte_start']:span['byte_end']]
        if (node.name != span['name'] or digest(selected) != span['sha256']
                or ast.dump(ast.parse(selected).body[0], include_attributes=False) != ast.dump(node, include_attributes=False)
                or ast.dump(upstream[node.name], include_attributes=False) != ast.dump(node, include_attributes=False)):
            raise ValueError('RECURRENT_SOURCE_AST_OR_SPAN')
    span = provenance['caller']; selected = language[span['byte_start']:span['byte_end']]
    expected = ast.parse('def source_recurrent_step(self, fg, q, k, v, a, b_o, cache, S):\n' +
                         textwrap.indent(textwrap.dedent(selected.decode()), '    ') + '    return out, state\n').body[0]
    # Anchor the selected statements to actual statements in the original class.
    module = ast.parse(language)
    calls = [n for n in ast.walk(module) if isinstance(n, ast.FunctionDef) and n.name == '__call__'
             and any(isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == 'gated_delta_update' for v in ast.walk(n))]
    if len(calls) != 1:
        raise ValueError('RECURRENT_CALLER_UNIQUE')
    originals = [n for n in calls[0].body if 289 <= n.lineno <= 303]
    if (digest(selected) != span['selected_sha256']
            or ast.dump(expected, include_attributes=False) != ast.dump(tree.body[-1], include_attributes=False)
            or [ast.dump(n, include_attributes=False) for n in originals] != [ast.dump(n, include_attributes=False) for n in expected.body[:-1]]):
        raise ValueError('RECURRENT_CALLER_AST_OR_SPAN')
    return tree


def load(context, fixture, mutation=None):
    root = context.roots['code']; read = context.read_verified
    raw = read(root / PREFIX / 'capsule.py'); original = read(root / PREFIX / 'upstream-gated-delta.txt')
    pbytes = read(root / PREFIX / 'provenance.json'); provenance = json.loads(pbytes)
    language = read(root / PREFIX / 'upstream-language.txt')
    digest = lambda b: hashlib.sha256(b).hexdigest()
    if digest(raw) != fixture['capsule_sha256'] or digest(pbytes) != fixture['provenance_sha256']:
        raise ValueError('RECURRENT_FIXTURE_SOURCE_BINDING')
    verify(raw, original, language, provenance)
    changed = raw
    if mutation in provenance['mutations']:
        spec = provenance['mutations'][mutation]; before = spec['before'].encode()
        if raw.count(before) != 1:
            raise ValueError('RECURRENT_MUTANT_SITE')
        changed = raw.replace(before, spec['after'].encode())
        if digest(changed) != spec['sha256']:
            raise ValueError('RECURRENT_MUTANT_BINDING')
    elif mutation not in (None, 'stale_cache1', 'cross_stream_cache1'):
        raise ValueError('RECURRENT_MUTANT_UNKNOWN')
    stats = {'compute_g_entries': 0, 'compute_g_safe_entries': 0, 'step_entries': 0,
             'ops_entries': 0, 'update_entries': 0, 'caller_entries': 0, 'kernel_entries': 0,
             'step_evaluation_barriers': 0, 'outer_evaluation_barriers': 0}
    traces = []

    def kernel_excluded(*args, **kwargs):
        stats['kernel_entries'] += 1
        raise RuntimeError('KERNEL_ARM_EXCLUDED')

    namespace = {'__name__': 'exact_recurrent_ops', 'mx': mx, 'nn': nn, 'partial': partial,
                 'Optional': Optional, 'Tuple': Tuple, 'gated_delta_kernel': kernel_excluded}
    exec(compile(changed, 'verified-recurrent-capsule', 'exec'), namespace)
    originals = {n: namespace[n] for n in (*NAMES, 'source_recurrent_step')}
    entry_keys = dict(zip((*NAMES, 'source_recurrent_step'), ('compute_g_entries', 'compute_g_safe_entries',
                       'step_entries', 'ops_entries', 'update_entries', 'caller_entries')))

    def instrument(name):
        original_function = originals[name]
        def counted(*args, **kwargs):
            stats[entry_keys[name]] += 1
            if name != '_gated_delta_step_ops':
                return original_function(*args, **kwargs)
            q, k, v, g, beta, prior = args[:6]
            mask = args[6] if len(args) > 6 else kwargs.get('mask')
            y, state = original_function(*args, **kwargs)
            mx.eval(q, k, v, g, beta, prior, y, state)
            stats['step_evaluation_barriers'] += 1
            traces.append({'q_expanded': q.tolist(), 'k_expanded': k.tolist(), 'v': v.tolist(),
                           'g': g.tolist(), 'beta': beta.tolist(), 'prior_state': prior.tolist(),
                           'output': y.tolist(), 'new_state': state.tolist(),
                           'mask': None if mask is None else mask.tolist()})
            return y, state
        return counted

    for name in originals:
        namespace[name] = instrument(name)
    return types.SimpleNamespace(namespace=namespace, originals=originals, stats=stats, traces=traces,
                                 binding={'capsule_sha256': digest(raw), 'executed_capsule_sha256': digest(changed),
                                          'origin_sha256': digest(original), 'mutation': mutation,
                                          'source_AST_and_spans': 'PASS', 'fresh_function_objects': True,
                                          'source_decorators': 'UNCHANGED', 'kernel_arm': 'DECLARED_FAIL_CLOSED_SENTINEL',
                                          'compiled_trace_operator_kernel_counts': 'NOT_MEASURABLE'})

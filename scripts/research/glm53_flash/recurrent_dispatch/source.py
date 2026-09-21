"""Exact original nodes, bounded buffers, and counters without inner evaluation."""
import ast
from functools import partial
import hashlib
import json
import textwrap
import types
from typing import Optional, Tuple

PREFIX = 'scripts/research/glm53_flash/recurrent_dispatch/'
ORIGIN_SHA256 = 'e15cd83bfc0bfff3de7a9563aa6978f7e39e0e248cc8a55ca9482f1ce18f54d8'
CALLER_SHA256 = '6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196'
FUNCTIONS = ('compute_g', 'compute_g_safe', '_make_gated_delta_kernel',
             '_gated_delta_step_ops', 'gated_delta_kernel', 'gated_delta_ops', 'gated_delta_update')
INITIALIZERS = ('_gated_delta_kernel', '_gated_delta_kernel_masked',
                '_gated_delta_kernel_vec', '_gated_delta_kernel_vec_masked')
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def node_name(node):
    if isinstance(node, ast.FunctionDef):
        return node.name
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


def verify(raw, original, language, provenance):
    if sha(original) != ORIGIN_SHA256 or sha(language) != CALLER_SHA256 or sha(raw) != provenance['capsule_sha256']:
        raise ValueError('DISPATCH_SOURCE_BINDING')
    origins = [n for n in ast.parse(original).body if node_name(n) in FUNCTIONS + INITIALIZERS]
    actual = ast.parse(raw)
    if len(origins) != 11 or len(actual.body) != 12 or len(provenance['source_spans']) != 11:
        raise ValueError('DISPATCH_CLOSURE')
    for expected, observed, span in zip(origins, actual.body[:-1], provenance['source_spans']):
        selected = original[span['byte_start']:span['byte_end']]
        if (node_name(expected) != node_name(observed) or node_name(expected) != span['name']
                or sha(selected) != span['sha256']
                or ast.dump(expected, include_attributes=False) != ast.dump(observed, include_attributes=False)
                or ast.dump(ast.parse(selected).body[0], include_attributes=False) != ast.dump(expected, include_attributes=False)):
            raise ValueError('DISPATCH_ORIGINAL_NODE_OR_SPAN')
    span = provenance['caller']
    selected = language[span['byte_start']:span['byte_end']]
    wrapped = ast.parse('def source_recurrent_step(self, fg, q, k, v, a, b_o, cache, S):\n' +
                        textwrap.indent(textwrap.dedent(selected.decode()), '    ') + '    return out, state\n').body[0]
    callers = [n for n in ast.walk(ast.parse(language)) if isinstance(n, ast.FunctionDef) and n.name == '__call__'
               and any(isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == 'gated_delta_update' for v in ast.walk(n))]
    if len(callers) != 1:
        raise ValueError('DISPATCH_CALLER_UNIQUE')
    original_statements = [n for n in callers[0].body if 289 <= n.lineno <= 303]
    if (sha(selected) != span['selected_sha256']
            or ast.dump(wrapped, include_attributes=False) != ast.dump(actual.body[-1], include_attributes=False)
            or [ast.dump(n, include_attributes=False) for n in original_statements]
            != [ast.dump(n, include_attributes=False) for n in wrapped.body[:-1]]):
        raise ValueError('DISPATCH_CALLER_NODE_OR_SPAN')
    kernel = next(n for n in origins if node_name(n) == 'gated_delta_kernel')
    geometry = {k.arg: ast.unparse(k.value) for k in kernel.body[-1].value.keywords
                if k.arg in ('grid', 'threadgroup', 'output_shapes', 'output_dtypes')}
    update = next(n for n in origins if node_name(n) == 'gated_delta_update')
    if (geometry != provenance['geometry_expressions'] or geometry['grid'] != '(32, Dv, B * Hv)'
            or geometry['threadgroup'] != '(32, 4, 1)'
            or ast.unparse(update.body[-2].test) != provenance['selector_predicate']
            or b'constexpr int n_per_t = Dk / 32;' not in original
            or b'y[dv_idx] = static_cast<InT>(0);' not in original):
        raise ValueError('DISPATCH_SOURCE_ADMISSION_PREDICATES')
    return actual


def kernel_buffers(kwargs, input_names):
    """Metadata-only checks at API submission; never evaluate inner arrays."""
    inputs = kwargs['inputs']
    if len(inputs) != len(input_names) or len(inputs) not in (7, 8):
        raise ValueError('KERNEL_INPUT_COUNT')
    q, k, v, g, beta, state, T = inputs[:7]
    if len(q.shape) != 4 or q.shape != k.shape or len(v.shape) != 4:
        raise ValueError('KERNEL_RANK')
    B, times, Hk, Dk = q.shape
    Hv, Dv = v.shape[-2:]
    if (not (1 <= B <= 2 and 1 <= times <= 7 and 1 <= Hk <= 2 and 1 <= Hv <= 4)
            or Hv % Hk or Dk not in (32, 64) or Dv not in (4, 8) or type(T) is not int or T != times):
        raise ValueError('KERNEL_DIMENSION_DOMAIN')
    expected = [(B, T, Hk, Dk), (B, T, Hk, Dk), (B, T, Hv, Dv),
                (B, T, Hv, Dk) if len(g.shape) == 4 else (B, T, Hv),
                (B, T, Hv), (B, Hv, Dv, Dk)]
    for value, shape in zip(inputs[:6], expected):
        count = 1
        for dimension in shape:
            count *= dimension
        if value.shape != shape or value.dtype != mx.float32 or value.size != count or count > 4096:
            raise ValueError('KERNEL_BUFFER_METADATA')
    if len(inputs) == 8 and (inputs[7].shape != (B, T) or inputs[7].dtype != mx.bool_):
        raise ValueError('KERNEL_MASK_METADATA')
    if (kwargs['grid'] != (32, Dv, B * Hv) or kwargs['threadgroup'] != (32, 4, 1)
            or kwargs['output_shapes'] != [(B, T, Hv, Dv), state.shape]
            or kwargs['output_dtypes'] != [mx.float32, mx.float32]
            or dict(kwargs['template']) != {'InT': mx.float32, 'StT': mx.float32,
                                            'Dk': Dk, 'Dv': Dv, 'Hk': Hk, 'Hv': Hv}):
        raise ValueError('KERNEL_SOURCE_GEOMETRY')
    return {'B': B, 'T': T, 'Hk': Hk, 'Hv': Hv, 'Dk': Dk, 'Dv': Dv,
            'max_state_float32_elements': B * Hv * Dv * Dk,
            'canonical_inputs': 'Constructed from validated bounded Python lists; unchanged API default ensure_row_contiguous=True.',
            'finite_scope': 'All external scientific operands validated before tensor construction. Gates/beta are lazy source-derived values from the declared bounded stable domain, not host-read before submission.',
            'index_proof': 'n<B*Hv; hk=floor(hv/(Hv/Hk))<Hk; dv<Dv; s=(Dk/32)*dk+i spans0..Dk-1. Dv multiple4 tiles the exact threadgroup; all pointer strides stay within the verified shapes.'}


def load(context, fixture, mutation=None):
    root = context.roots['code'] / PREFIX
    raw = context.read_verified(root / 'capsule.py')
    original = context.read_verified(root / 'upstream-gated-delta.txt')
    language = context.read_verified(root / 'upstream-language.txt')
    pbytes = context.read_verified(root / 'provenance.json')
    provenance = json.loads(pbytes)
    if sha(raw) != fixture['capsule_sha256'] or sha(pbytes) != fixture['provenance_sha256']:
        raise ValueError('DISPATCH_FIXTURE_SOURCE_BINDING')
    verify(raw, original, language, provenance)
    changed = raw
    if mutation in provenance['mutations']:
        specification = provenance['mutations'][mutation]
        for replacement in specification['replacements']:
            before = replacement['before'].encode()
            if changed.count(before) != 1:
                raise ValueError('DISPATCH_MUTANT_SITE')
            changed = changed.replace(before, replacement['after'].encode())
        if sha(changed) != specification['sha256']:
            raise ValueError('DISPATCH_MUTANT_BINDING')
    elif mutation not in (None, *provenance['wrapper_controls']):
        raise ValueError('DISPATCH_UNKNOWN_MUTATION')
    stats = dict.fromkeys(['compute_g_entries', 'compute_g_safe_entries', 'factory_entries',
                           'step_entries', 'kernel_entries', 'ops_entries', 'update_entries',
                           'caller_entries', 'factory_API_calls', 'kernel_API_submissions',
                           'inner_evaluation_barriers', 'outer_evaluation_barriers',
                           'cache_observation_barriers'], 0)
    factories, submissions, handles = [], [], []
    generated_sources = {}

    def factory(**kwargs):
        stats['factory_API_calls'] += 1
        callable_source = kwargs['source'].encode()
        generated_sources[sha(callable_source)] = kwargs['source']
        original_kernel = mx.fast.metal_kernel(**kwargs)
        record = {'factory_ordinal': len(factories) + 1, 'name': kwargs['name'],
                  'source_sha256': sha(callable_source), 'input_names': kwargs['input_names'],
                  'ensure_row_contiguous': kwargs.get('ensure_row_contiguous', True),
                  'compile_options': kwargs.get('compile_options'),
                  'effective_compiler_math_mode': 'NOT_OBSERVED; admitted API documents omitted option default safe'}
        factories.append(record)

        def submitted(**arguments):
            proof = kernel_buffers(arguments, kwargs['input_names'])
            if mutation == 'wrong_head_mapping':
                proof['index_proof'] = 'Declared safe semantic mutant: hk=hv%Hk remains0..Hk-1; every other stride/index/geometry expression is unchanged. Original grouped mapping is intentionally wrong, not claimed.'
            stats['kernel_API_submissions'] += 1
            submissions.append({**record, 'admission': proof, 'grid': list(arguments['grid']),
                                'threadgroup': list(arguments['threadgroup'])})
            return original_kernel(**arguments)
        handles.extend([original_kernel, submitted])
        return submitted

    class CoreFacade:
        fast = types.SimpleNamespace(metal_kernel=factory)
        def __getattr__(self, key):
            return getattr(mx, key)

    namespace = {'__name__': 'exact_default_recurrent_dispatch', 'mx': CoreFacade(),
                 'nn': nn, 'partial': partial, 'Optional': Optional, 'Tuple': Tuple}
    originals = {}
    keys = dict(zip((*FUNCTIONS, 'source_recurrent_step'),
                    ('compute_g_entries', 'compute_g_safe_entries', 'factory_entries',
                     'step_entries', 'kernel_entries', 'ops_entries', 'update_entries', 'caller_entries')))

    def wrap(name, function):
        def counted(*args, **kwargs):
            stats[keys[name]] += 1
            result = function(*args, **kwargs)
            if mutation == 'illicit_inner_barrier' and name in ('_gated_delta_step_ops', 'gated_delta_kernel'):
                mx.eval(*result)
                stats['inner_evaluation_barriers'] += 1
            return result
        return counted

    # Executing exact nodes in source order lets the four original initializer
    # statements call the counted original factory without changing their ASTs.
    for node in ast.parse(changed).body:
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'verified-default-dispatch-capsule', 'exec'), namespace)
        if isinstance(node, ast.FunctionDef):
            originals[node.name] = namespace[node.name]
            namespace[node.name] = wrap(node.name, namespace[node.name])
    return types.SimpleNamespace(namespace=namespace, originals=originals, handles=handles,
                                 stats=stats, factories=factories, submissions=submissions,
                                 generated_sources=generated_sources,
                                 binding={'capsule_sha256': sha(raw), 'executed_capsule_sha256': sha(changed),
                                          'origin_sha256': sha(original), 'mutation': mutation,
                                          'original_full_nodes_and_spans': 'PASS', 'source_decorators': 'UNCHANGED',
                                          'original_nodes_executed_in_order': True,
                                          'compiled_physical_counts': 'NOT_MEASURABLE'})

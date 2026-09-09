"""Verify exact retained-source correspondence before compiling only the capsule.

mx and nn are injected by the existing fenced successor after environment checks.
"""
import ast
import hashlib
import json
import types

PREFIX = 'scripts/research/glm53_flash/convolution_state/'
ORIGIN = 'pipenetwork/glm53_flash_mlx/glm5_next/language.py'


def load(context, fixture, mutation=None):
    root = context.roots['code']
    provenance_bytes = context.read_verified(root / PREFIX / 'provenance.json')
    provenance = json.loads(provenance_bytes)
    raw = context.read_verified(root / PREFIX / 'capsule.py')
    original = context.read_verified(context.roots['upstream'] / ORIGIN)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    if (sha(raw) != fixture['source_capsule_sha256'] or sha(raw) != provenance['capsule_sha256']
            or sha(provenance_bytes) != fixture['provenance_sha256']
            or sha(original) != provenance['origin']['sha256']):
        raise ValueError('SOURCE_BINDING')
    original_tree = ast.parse(original)
    nodes = {(n.lineno, n.end_lineno): n for n in ast.walk(original_tree)
             if isinstance(n, ast.stmt)}
    actual = ast.parse(raw)
    if [n.name for n in actual.body if isinstance(n, ast.FunctionDef)] != ['source_construct', 'source_step'] or len(actual.body) != 2:
        raise ValueError('SOURCE_CLOSURE')
    expected = {name: [] for name in ('source_construct', 'source_step')}
    for row in provenance['statements']:
        body = original[row['source_byte_start']:row['source_byte_end_exclusive']]
        if sha(body) != row['original_sha256'] or body.decode() != row['source_text']:
            raise ValueError('SOURCE_SPAN')
        node = nodes[(row['source_line_start'], row['source_line_end'])]
        expected[row['function']].append(ast.dump(node, include_attributes=False))
    for function in actual.body:
        if [ast.dump(n, include_attributes=False) for n in function.body[:-1]] != expected[function.name]:
            raise ValueError('SOURCE_AST')
    executed = raw
    if mutation in provenance['mutations'] and 'before' in provenance['mutations'][mutation]:
        row = provenance['mutations'][mutation]
        before, after = row['before'].encode(), row['after'].encode()
        if raw.count(before) != 1:
            raise ValueError('MUTANT_SITE')
        executed = raw.replace(before, after)
        if sha(executed) != row['capsule_sha256']:
            raise ValueError('MUTANT_BINDING')
    elif mutation not in (None, 'reverse_taps', 'wrong_channel_axis', 'reset_omission',
                          'cross_stream_alias', 'stale_prefill_state'):
        raise ValueError('MUTANT_UNKNOWN')
    namespace = {'__name__': 'source_bound_convolution_slice', 'mx': mx, 'nn': nn}
    exec(compile(executed, 'verified-convolution-source-slice', 'exec'), namespace)
    return types.SimpleNamespace(**namespace), {
        'origin_sha256': sha(original), 'original_capsule_sha256': sha(raw),
        'executed_capsule_sha256': sha(executed), 'mutation': mutation,
        'scope': 'SOURCE_SLICE_EXECUTED with RESEARCH_ADAPTER; REAL_CACHE_NOT_EXECUTED',
        'source_ast_binding': 'PASS'}

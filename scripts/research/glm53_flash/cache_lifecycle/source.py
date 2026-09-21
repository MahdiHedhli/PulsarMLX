"""Verify exact cache classes and the caller seam; dependencies enter after fences."""
import ast
import hashlib
import json
import types
from typing import List, Optional

PREFIX = 'scripts/research/glm53_flash/cache_lifecycle/'
CONV = 'scripts/research/glm53_flash/convolution_state/'


def load(context, fixture, mutation=None):
    root = context.roots['code']
    digest = lambda b: hashlib.sha256(b).hexdigest()
    raw = context.read_verified(root / PREFIX / 'capsule.py')
    pbytes = context.read_verified(root / PREFIX / 'provenance.json')
    provenance = json.loads(pbytes)
    original = context.read_verified(root / PREFIX / 'upstream-cache.txt')
    if (digest(raw) != fixture['cache_capsule_sha256'] or digest(raw) != provenance['capsule_sha256']
            or digest(pbytes) != fixture['cache_provenance_sha256']
            or digest(original) != provenance['origin']['sha256']):
        raise ValueError('CACHE_SOURCE_BINDING')
    actual = ast.parse(raw)
    if [(type(n).__name__, getattr(n, 'name', None)) for n in actual.body] != [
            ('ClassDef', '_BaseCache'), ('ClassDef', 'ArraysCache'), ('FunctionDef', 'source_make_cache')]:
        raise ValueError('CACHE_CLOSURE')
    original_classes = {n.name: n for n in ast.parse(original).body if isinstance(n, ast.ClassDef)}
    for node, span in zip(actual.body[:2], provenance['class_spans']):
        selected = original[span['byte_start']:span['byte_end']]
        if (node.name != span['name'] or digest(selected) != span['sha256']
                or ast.dump(ast.parse(selected).body[0], include_attributes=False) != ast.dump(node, include_attributes=False)
                or ast.dump(original_classes[node.name], include_attributes=False) != ast.dump(node, include_attributes=False)):
            raise ValueError('CACHE_SOURCE_AST_OR_SPAN')
    factory = actual.body[2]
    language = context.read_verified(context.roots['upstream'] / 'pipenetwork/glm53_flash_mlx/glm5_next/language.py')
    calls = [n for n in ast.walk(ast.parse(language)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'ArraysCache']
    if (digest(language) != provenance['factory']['sha256'] or len(calls) != 1
            or len(factory.body) != 1 or not isinstance(factory.body[0], ast.Return)
            or factory.args.args or factory.decorator_list
            or ast.dump(factory.body[0].value, include_attributes=False) != ast.dump(calls[0], include_attributes=False)):
        raise ValueError('CACHE_FACTORY_SOURCE')
    conv = context.read_verified(root / CONV / 'capsule.py')
    if digest(conv) != provenance['convolution_capsule_sha256']:
        raise ValueError('CONVOLUTION_SOURCE_BINDING')
    changed_cache, changed_conv = raw, conv
    if mutation in provenance['mutations']:
        spec = provenance['mutations'][mutation]
        selected = raw if spec['target'] == 'cache' else conv
        before, after = spec['before'].encode(), spec['after'].encode()
        if selected.count(before) != 1:
            raise ValueError('CACHE_MUTANT_SITE')
        selected = selected.replace(before, after)
        if digest(selected) != spec['sha256']:
            raise ValueError('CACHE_MUTANT_BINDING')
        if spec['target'] == 'cache':
            changed_cache = selected
        else:
            changed_conv = selected
    elif mutation not in (None, 'reset_omission', 'cross_stream_alias', 'stale_prefill_state'):
        raise ValueError('CACHE_MUTANT_UNKNOWN')
    namespace = {'__name__': 'source_bound_actual_arrays_cache', 'mx': mx, 'Optional': Optional, 'List': List}
    exec(compile(changed_cache, 'verified-actual-cache-classes', 'exec'), namespace)
    conv_namespace = {'__name__': 'source_bound_convolution_for_actual_cache', 'mx': mx, 'nn': nn}
    exec(compile(changed_conv, 'verified-cache-convolution-slice', 'exec'), conv_namespace)
    return types.SimpleNamespace(**namespace), types.SimpleNamespace(**conv_namespace), {
        'cache_origin_sha256': digest(original), 'cache_capsule_sha256': digest(raw),
        'executed_cache_capsule_sha256': digest(changed_cache),
        'convolution_capsule_sha256': digest(conv), 'executed_convolution_capsule_sha256': digest(changed_conv),
        'mutation': mutation, 'cache_class_AST_and_factory_source': 'PASS',
        'scope': 'ACTUAL_CACHE_METHOD_EXECUTED for observed methods; SOURCE_SLICE_EXECUTED convolution; no KDA or full model'}

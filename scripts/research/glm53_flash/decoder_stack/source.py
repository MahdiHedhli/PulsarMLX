"""Admit the two-layer stack: Glm5NextDecoderLayer and Glm5NextModel (unchanged) and LanguageModel (renamed only).

Every constructor the capsule reaches is an already-admitted class: the linear
attention module (linear-attention track), the sparse attention (sparse
track), the MoE block (MoE track), ClampedMLP/HyperConnection/hc_expand
(dense-FFN track) and ArraysCache (cache track). KVCache, CacheList and
create_causal_mask are taken whole from the retained mlx-vlm cache.py;
create_attention_mask, create_ssm_mask and LanguageModelOutput from the
retained mlx-vlm base.py; all by canonical-AST identity with a global census.
The cache module's own create_attention_mask (N, offset, ...) is bound for
KVCache.make_mask; base.py's create_attention_mask (h, cache, ...) for the model.
DSV32Model (sanitize), the batch/quantized cache classes and the TurboQuant
paths are refused stubs.
"""
import ast
import copy
import dataclasses
import symtable
import types
import typing

CAPSULE = 'scripts/research/glm53_flash/decoder_stack/capsule.py'
CACHE = 'scripts/research/glm53_flash/cache_lifecycle/upstream-cache.txt'
CACHE_SHA256 = 'fde16e0558f8135fa88ae72484cdddc6adfd0c201a18be60bd041cb2d4f602d7'
CAPSULE_GLOBALS = ['Any', 'ArraysCache', 'CacheList', 'ClampedMLP', 'DSV32Model', 'Glm5NextDecoderLayer', 'Glm5NextLinearAttention',
                   'Glm5NextMoE', 'Glm5NextModel', 'Glm5NextSparseAttention', 'HyperConnection', 'KVCache', 'LanguageModelOutput',
                   'ModelConfig', 'Optional', 'TextConfig', 'all', 'create_attention_mask', 'create_ssm_mask', 'enumerate', 'hc_expand',
                   'int', 'len', 'list', 'mx', 'next', 'nn', 'property', 'range', 'super', 'zip']
DEPENDENCIES = {
    'KVCache': ('cache', ['BatchKVCache', 'IndexError', 'KVCache', 'QuantizedKVCache', '_BaseCache', 'classmethod', 'create_attention_mask',
                          'int', 'max', 'min', 'mx', 'property']),
    'CacheList': ('cache', ['CacheList', '_BaseCache', 'all', 'classmethod', 'globals', 'len', 'max', 'property', 'range', 'sum', 'tuple', 'type', 'zip']),
    'create_causal_mask': ('cache', ['Optional', 'int', 'mx']),
    'cache_create_attention_mask': ('cache', ['Optional', 'bool', 'create_causal_mask', 'int']),
    'create_attention_mask': ('base', ['Optional', 'bool', 'create_causal_mask', 'hasattr', 'int', 'isinstance', 'mx']),
    'create_ssm_mask': ('base', ['hasattr', 'isinstance', 'mx']),
    'LanguageModelOutput': ('base', ['Dict', 'List', 'Optional', 'dataclass', 'mx', 'str', 'tuple']),
}
QUANTIZED_OPS = ('gather_qmm', 'quantized_matmul', 'quantize', 'dequantize')


def _refused(name):
    def stub(*args, **kwargs):
        raise RuntimeError('DECODER_STACK_' + name + '_NOT_ADMITTED')
    return stub


class _RefusedSanitize:
    sanitize = staticmethod(_refused('DSV32_SANITIZE'))


DSV32_LANGUAGE = 'mlx-vlm/mlx_vlm/models/deepseek_v32/language.py'  # under the upstream root
DSV32_LANGUAGE_SHA256 = 'cd210c73ce3e569ab5270a47a92941cd5ec1450c6ff7b55b8be57c51263f4cb6'
DSV32_SANITIZE_GLOBALS = ['int', 'len', 'mx', 'range']
DSV32_UNEXECUTED_OPS = ('from_fp8', 'quantize', 'dequantize')


class _TripwireMx:
    """Forwards every attribute of the admitted mx except the fp8/quantized ops, which raise: the
    sanitize fixture is unquantized and those branches must not execute."""
    def __init__(self, mx):
        self._mx = mx

    def __getattr__(self, name):
        if name in DSV32_UNEXECUTED_OPS:
            raise RuntimeError('DECODER_STACK_DSV32_' + name.upper() + '_NOT_ADMITTED')
        return getattr(self._mx, name)


def load_dsv32_sanitize(dsv32_raw, mx, ffn_source):
    """The DeepSeek-V3.2 Model.sanitize method taken whole from the retained mlx-vlm text, as a plain function."""
    if ffn_source.sha(dsv32_raw) != DSV32_LANGUAGE_SHA256:
        raise ValueError('DECODER_STACK_DSV32_DIGEST')
    model = ffn_source._node(ast.parse(dsv32_raw), 'Model')
    node = next(n for n in model.body if isinstance(n, ast.FunctionDef) and n.name == 'sanitize')
    if _census(ast.unparse(node), 'dsv32-sanitize') != DSV32_SANITIZE_GLOBALS:
        raise ValueError('DECODER_STACK_DSV32_CLOSURE:' + repr(_census(ast.unparse(node), 'dsv32-sanitize')))
    ns = {'__name__': 'decoder_stack_dsv32_sanitize_verified', 'mx': _TripwireMx(mx)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'decoder-stack-dsv32-sanitize', 'exec'), ns)
    return types.SimpleNamespace(sanitize=ns['sanitize'], node=node, ast_sha256=ffn_source.ast_sha(node), mx_ops=_mx_ops(node))


def _census(text, name):
    table = symtable.symtable(text, name, 'exec')
    observed, pending = set(), [table]
    while pending:
        scope = pending.pop()
        observed.update(s.get_name() for s in scope.get_symbols() if s.is_global() and s.is_referenced())
        pending.extend(scope.get_children())
    return sorted(observed)


def _mx_ops(node):
    return sorted({a.attr for a in ast.walk(node) if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == 'mx'})


def verify_dependencies(cache_raw, base_raw, ffn_source, sparse_source):
    if ffn_source.sha(cache_raw) != CACHE_SHA256 or ffn_source.sha(base_raw) != sparse_source.BASE_SHA256:
        raise ValueError('DECODER_STACK_DEPENDENCY_DIGEST')
    trees = {'cache': ast.parse(cache_raw), 'base': ast.parse(base_raw)}
    nodes, digests = {}, {}
    for name, (origin, expected) in DEPENDENCIES.items():
        node = ffn_source._node(trees[origin], name.removeprefix('cache_'))
        if _census(ast.unparse(node), name) != expected:
            raise ValueError('DECODER_STACK_DEPENDENCY_CLOSURE:' + name + ':' + repr(_census(ast.unparse(node), name)))
        for fn in [n for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]:
            # quantize appears only in KVCache.to_quantized, whose target class is a refused stub
            allowed = ('quantize',) if (name, fn.name) == ('KVCache', 'to_quantized') else ()
            if [op for op in _mx_ops(fn) if op in QUANTIZED_OPS and op not in allowed]:
                raise ValueError('DECODER_STACK_DEPENDENCY_QUANTIZED_OP:' + name + '.' + fn.name)
        nodes[name] = node; digests[name] = ffn_source.ast_sha(node)
    return nodes, digests


def verify_capsule(capsule_raw, language_raw, ffn_source):
    if ffn_source.sha(language_raw) != ffn_source.LANGUAGE_SHA256:
        raise ValueError('DECODER_STACK_UPSTREAM_DIGEST')
    tree = ast.parse(language_raw)
    originals = [ffn_source._node(tree, n) for n in ('Glm5NextDecoderLayer', 'Glm5NextModel', 'LanguageModel')]
    transformed = copy.deepcopy(originals[2]); transformed.name = 'source_language_model'
    capsule = ast.parse(capsule_raw)
    if (len(capsule.body) != 3 or [ffn_source.ast_sha(n) for n in capsule.body]
            != [ffn_source.ast_sha(originals[0]), ffn_source.ast_sha(originals[1]), ffn_source.ast_sha(transformed)]):
        raise ValueError('DECODER_STACK_CALLER_TRANSFORM')
    if _census(capsule_raw.decode(), 'stack-capsule') != CAPSULE_GLOBALS:
        raise ValueError('DECODER_STACK_CLOSURE:' + repr(_census(capsule_raw.decode(), 'stack-capsule')))
    for n in capsule.body:
        if [op for op in _mx_ops(n) if op in QUANTIZED_OPS]:
            raise ValueError('DECODER_STACK_QUANTIZED_OP_IN_CAPSULE')
    return capsule.body, {'original_ast_sha256': [ffn_source.ast_sha(n) for n in originals],
                          'capsule_ast_sha256': [ffn_source.ast_sha(n) for n in capsule.body], 'digest_scheme': ffn_source.DIGEST_SCHEME}


def load_cache_classes(cache_raw, base_raw, mx, nn, ffn_source, sparse_source, base_cache_class):
    """KVCache and CacheList over the admitted _BaseCache, with the cache module's own mask helpers."""
    dep_nodes, dep_digests = verify_dependencies(cache_raw, base_raw, ffn_source, sparse_source)
    cache_ns = {'__name__': 'decoder_stack_cache_classes_verified', 'mx': mx, 'nn': nn, 'Optional': typing.Optional,
                '_BaseCache': base_cache_class, 'BatchKVCache': _refused('BATCH_KV_CACHE'), 'QuantizedKVCache': _refused('QUANTIZED_KV_CACHE')}
    for name in ('create_causal_mask', 'cache_create_attention_mask', 'KVCache', 'CacheList'):
        exec(compile(ast.Module(body=[dep_nodes[name]], type_ignores=[]), 'decoder-stack-cache-dependency:' + name, 'exec'), cache_ns)
    return types.SimpleNamespace(namespace=cache_ns, nodes=dep_nodes, digests=dep_digests)


def load(capsule_raw, language_raw, cache_raw, base_raw, mx, nn, ffn_source, sparse_source, bindings):
    """bindings: ffn_namespace, attention_namespace, cache_namespace, moe_class, sparse_class."""
    caches = load_cache_classes(cache_raw, base_raw, mx, nn, ffn_source, sparse_source, bindings['cache_namespace']._BaseCache)
    nodes, contract = verify_capsule(capsule_raw, language_raw, ffn_source)
    base_ns = {'__name__': 'decoder_stack_base_dependencies_verified', 'mx': mx, 'Optional': typing.Optional, 'List': typing.List,
               'Dict': typing.Dict, 'dataclass': dataclasses.dataclass}
    for name in ('create_causal_mask', 'create_attention_mask', 'create_ssm_mask', 'LanguageModelOutput'):
        exec(compile(ast.Module(body=[caches.nodes[name]], type_ignores=[]), 'decoder-stack-base-dependency:' + name, 'exec'), base_ns)
    ns = {'__name__': 'decoder_stack_verified', 'mx': mx, 'nn': nn, 'Optional': typing.Optional, 'Any': typing.Any,
          'TextConfig': object, 'ModelConfig': object, 'DSV32Model': bindings.get('dsv32_model', _RefusedSanitize),
          'Glm5NextLinearAttention': bindings['attention_namespace']['Glm5NextLinearAttention'],
          'Glm5NextSparseAttention': bindings['sparse_class'], 'Glm5NextMoE': bindings['moe_class'],
          'ClampedMLP': bindings['ffn_namespace']['ClampedMLP'], 'HyperConnection': bindings['ffn_namespace']['HyperConnection'],
          'hc_expand': bindings['ffn_namespace']['hc_expand'], 'ArraysCache': bindings['cache_namespace'].ArraysCache,
          'KVCache': caches.namespace['KVCache'], 'CacheList': caches.namespace['CacheList'], 'LanguageModelOutput': base_ns['LanguageModelOutput'],
          'create_attention_mask': base_ns['create_attention_mask'], 'create_ssm_mask': base_ns['create_ssm_mask']}
    for n in nodes:
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-stack-admitted:' + n.name, 'exec'), ns)
    contract['dependency_ast_sha256'] = caches.digests
    dependency_namespace = {**caches.namespace, **{k: v for k, v in base_ns.items() if k not in ('__name__', 'create_causal_mask')}}
    return types.SimpleNamespace(namespace=ns, dependency_namespace=dependency_namespace, cache_namespace=caches.namespace,
                                 base_namespace=base_ns, contract=contract)

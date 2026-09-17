"""Admit Glm5NextIndexer (unchanged) and Glm5NextSparseAttention (renamed only) with their upstream deps.

MultiLinear is taken whole from the retained mlx-vlm mla.py; scaled_dot_product_attention
from the retained mlx-vlm base.py. Both by canonical-AST identity with a global census.
Quantized and TurboQuant paths are refused stubs (QuantizedMultiLinear, the TurboQuant cache
classes, _turboquant_attention_applies, quantized_scaled_dot_product_attention); a cache is
not passed in slice 1, so the executed attention is mx.fast.scaled_dot_product_attention.
"""
import ast
import copy
import math
import symtable
import types
import typing

MLA = 'scripts/research/glm53_flash/decoder_sparse/upstream-mla.txt'
MLA_SHA256 = 'da01333e57a5ba76b778a779e8e98724f48de1fffd24f6353d58bc846ba19bbf'
BASE = 'scripts/research/glm53_flash/decoder_sparse/upstream-base.txt'
BASE_SHA256 = '9f1e42adfc9829a5e585a2d0107ea591537f6050882ddb32600c72a1cc527a9a'
CAPSULE = 'scripts/research/glm53_flash/decoder_sparse/capsule.py'
MULTILINEAR_GLOBALS = ['QuantizedMultiLinear', 'int', 'math', 'mx', 'nn', 'str', 'super']
SDPA_GLOBALS = ['BatchTurboQuantKVCache', 'Optional', 'TurboQuantKVCache', 'ValueError', '_turboquant_attention_applies',
                'float', 'hasattr', 'isinstance', 'mx', 'quantized_scaled_dot_product_attention']
CAPSULE_GLOBALS = ['Any', 'Glm5NextIndexer', 'MultiLinear', 'NotImplementedError', 'Optional', 'TextConfig', 'bool', 'getattr',
                   'len', 'list', 'min', 'mx', 'nn', 'range', 'scaled_dot_product_attention', 'super']
QUANTIZED_OPS = ('gather_qmm', 'quantized_matmul', 'quantize', 'dequantize')


def _refused(name):
    def stub(*args, **kwargs):
        raise RuntimeError('DECODER_SPARSE_' + name + '_NOT_ADMITTED')
    return stub


class _RefusedCacheType:
    """Never instantiated; exists so the upstream isinstance() check evaluates to False."""
    def __init__(self, *a, **k):
        raise RuntimeError('DECODER_SPARSE_TURBOQUANT_CACHE_NOT_ADMITTED')


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


def verify_dependency(raw, sha, name, expected_globals, ffn_source):
    if ffn_source.sha(raw) != sha:
        raise ValueError('DECODER_SPARSE_DEPENDENCY_DIGEST:' + name)
    node = ffn_source._node(ast.parse(raw), name)
    text = ast.unparse(node)
    if _census(text, name) != expected_globals:
        raise ValueError('DECODER_SPARSE_DEPENDENCY_CLOSURE:' + name + ':' + repr(_census(text, name)))
    return node, ffn_source.ast_sha(node)


def verify_capsule(capsule_raw, language_raw, ffn_source):
    if ffn_source.sha(language_raw) != ffn_source.LANGUAGE_SHA256:
        raise ValueError('DECODER_SPARSE_UPSTREAM_DIGEST')
    tree = ast.parse(language_raw)
    indexer = ffn_source._node(tree, 'Glm5NextIndexer')
    original = ffn_source._node(tree, 'Glm5NextSparseAttention')
    transformed = copy.deepcopy(original)
    transformed.name = 'source_sparse_attention'
    capsule = ast.parse(capsule_raw)
    if (len(capsule.body) != 2 or ffn_source.ast_sha(capsule.body[0]) != ffn_source.ast_sha(indexer)
            or ffn_source.ast_sha(capsule.body[1]) != ffn_source.ast_sha(transformed)):
        raise ValueError('DECODER_SPARSE_CALLER_TRANSFORM')
    if _census(capsule_raw.decode(), 'sparse-capsule') != CAPSULE_GLOBALS:
        raise ValueError('DECODER_SPARSE_CLOSURE:' + repr(_census(capsule_raw.decode(), 'sparse-capsule')))
    for n in capsule.body:
        reached = [op for op in _mx_ops(n) if op in QUANTIZED_OPS]
        if reached:
            raise ValueError('DECODER_SPARSE_QUANTIZED_OP_IN_CAPSULE:' + ','.join(reached))
    return capsule.body, {'indexer_ast_sha256': ffn_source.ast_sha(indexer), 'original_ast_sha256': ffn_source.ast_sha(original),
                          'capsule_ast_sha256': [ffn_source.ast_sha(n) for n in capsule.body], 'digest_scheme': ffn_source.DIGEST_SCHEME,
                          'capsule_mx_ops': {n.name: _mx_ops(n) for n in capsule.body}}


def load(capsule_raw, language_raw, mla_raw, base_raw, mx, nn, ffn_source, quantized_multilinear=None):
    """quantized_multilinear: the graph-15 admitted QuantizedMultiLinear class, for operations that quantize resident weights; default refused."""
    multilinear, ml_sha = verify_dependency(mla_raw, MLA_SHA256, 'MultiLinear', MULTILINEAR_GLOBALS, ffn_source)
    sdpa, sdpa_sha = verify_dependency(base_raw, BASE_SHA256, 'scaled_dot_product_attention', SDPA_GLOBALS, ffn_source)
    if [op for op in _mx_ops(multilinear) if op in QUANTIZED_OPS] != ['quantize']:
        raise ValueError('DECODER_SPARSE_MULTILINEAR_OPS')  # quantize appears only in to_quantized, whose target is refused
    if [op for op in _mx_ops(sdpa) if op in QUANTIZED_OPS]:
        raise ValueError('DECODER_SPARSE_SDPA_OPS')
    nodes, contract = verify_capsule(capsule_raw, language_raw, ffn_source)
    dep_ns = {'__name__': 'decoder_sparse_dependencies_verified', 'mx': mx, 'nn': nn, 'math': math, 'Optional': typing.Optional,
              'QuantizedMultiLinear': quantized_multilinear if quantized_multilinear is not None else _refused('QUANTIZED_MULTILINEAR'),
              'TurboQuantKVCache': _RefusedCacheType, 'BatchTurboQuantKVCache': _RefusedCacheType,
              '_turboquant_attention_applies': _refused('TURBOQUANT_ATTENTION'),
              'quantized_scaled_dot_product_attention': _refused('QUANTIZED_SDPA')}
    for n in (multilinear, sdpa):
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-sparse-dependency:' + n.name, 'exec'), dep_ns)
    ns = {'__name__': 'decoder_sparse_verified', 'mx': mx, 'nn': nn, 'Optional': typing.Optional, 'Any': typing.Any,
          'TextConfig': object, 'MultiLinear': dep_ns['MultiLinear'],
          'scaled_dot_product_attention': dep_ns['scaled_dot_product_attention']}
    for n in nodes:
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-sparse-admitted:' + n.name, 'exec'), ns)
    contract.update(multilinear_ast_sha256=ml_sha, sdpa_ast_sha256=sdpa_sha, mla_sha256=MLA_SHA256, base_sha256=BASE_SHA256)
    return types.SimpleNamespace(namespace=ns, dependency_namespace=dep_ns, contract=contract)

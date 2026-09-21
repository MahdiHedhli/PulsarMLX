"""Admit the retained QuantizedSwitchLinear (mlx-vlm switch_layers.py) and QuantizedMultiLinear (mlx-vlm mla.py).

Both are taken whole by canonical-AST identity with a global census from the
same retained texts the MoE and sparse tracks anchor by digest. The switch-layer
namespace here is the MoE track's admitted node set with QuantizedSwitchLinear
bound to the real node instead of the refused stub (SwiGLU's default swiglu
remains refused; SwitchGLU is built with ClampedSwiGLU). The quantized arrays
are supplied from the frozen fixture; the constructors' mx.quantize of random
weights runs only to allocate the modules and is overwritten.
"""
import ast
import math
import symtable
import types

SWITCH_NODE = 'QuantizedSwitchLinear'
SWITCH_GLOBALS = ['bool', 'int', 'math', 'mx', 'nn', 'property', 'str', 'super']
SWITCH_MX_OPS = ['expand_dims', 'gather_qmm', 'quantize', 'random', 'zeros']
MLA_NODE = 'QuantizedMultiLinear'
MLA_GLOBALS = ['int', 'math', 'mx', 'nn', 'str', 'super']
MLA_MX_OPS = ['quantize', 'quantized_matmul', 'random']


def _refused(name):
    def stub(*args, **kwargs):
        raise RuntimeError('DECODER_QUANTIZED_' + name + '_NOT_ADMITTED')
    return stub


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


def verify_node(raw, sha, name, expected_globals, expected_ops, ffn_source):
    if ffn_source.sha(raw) != sha:
        raise ValueError('DECODER_QUANTIZED_DIGEST:' + name)
    node = ffn_source._node(ast.parse(raw), name)
    if _census(ast.unparse(node), name) != expected_globals:
        raise ValueError('DECODER_QUANTIZED_CLOSURE:' + name + ':' + repr(_census(ast.unparse(node), name)))
    if _mx_ops(node) != expected_ops:
        raise ValueError('DECODER_QUANTIZED_OPS:' + name + ':' + repr(_mx_ops(node)))
    return node, ffn_source.ast_sha(node)


def load(switch_raw, mla_raw, mx, nn, ffn_source, moe_source, sparse_source, ffn_namespace):
    switch_nodes, switch_digests = moe_source.verify_switch(switch_raw, ffn_source)
    q_switch, q_switch_sha = verify_node(switch_raw, moe_source.SWITCH_SHA256, SWITCH_NODE, SWITCH_GLOBALS, SWITCH_MX_OPS, ffn_source)
    q_mla, q_mla_sha = verify_node(mla_raw, sparse_source.MLA_SHA256, MLA_NODE, MLA_GLOBALS, MLA_MX_OPS, ffn_source)
    switch_ns = {'__name__': 'decoder_quantized_switch_verified', 'mx': mx, 'nn': nn, 'math': math, 'swiglu': moe_source._refused('DEFAULT_SWIGLU')}
    for n in [q_switch] + list(switch_nodes):
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-quantized-switch:' + n.name, 'exec'), switch_ns)
    mla_ns = {'__name__': 'decoder_quantized_mla_verified', 'mx': mx, 'nn': nn, 'math': math}
    exec(compile(ast.Module(body=[q_mla], type_ignores=[]), 'decoder-quantized-mla:' + q_mla.name, 'exec'), mla_ns)
    contract = {'switch_node_ast_sha256': switch_digests, 'quantized_switch_linear_ast_sha256': q_switch_sha, 'quantized_multilinear_ast_sha256': q_mla_sha,
                'switch_sha256': moe_source.SWITCH_SHA256, 'mla_sha256': sparse_source.MLA_SHA256, 'digest_scheme': ffn_source.DIGEST_SCHEME}
    return types.SimpleNamespace(switch_namespace=switch_ns, mla_namespace=mla_ns, clamped_swiglu=ffn_namespace['ClampedSwiGLU'], contract=contract,
                                 switch_text=switch_raw.decode(), mla_text=mla_raw.decode(), switch_nodes=switch_nodes, q_switch=q_switch, q_mla=q_mla)

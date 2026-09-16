"""Admit Glm5NextMoE (renamed only) over the router, switch-layer and FFN graphs.

The switch-layer nodes (_gather_sort, _scatter_unsort, SwitchLinear, SwiGLU,
SwitchGLU) are taken whole from the retained upstream text by canonical-AST
identity with a global census. QuantizedSwitchLinear is not admitted: the
quantized path (to_quantized, gather_qmm) and the default swiglu activation
are refused stubs; SwitchGLU is always constructed with ClampedSwiGLU here.
The gate class comes from the router track's Builder (unchanged upstream
variant); ClampedSwiGLU/ClampedMLP from the dense-FFN admitted namespace.
"""
import ast
import copy
import math
import symtable
import types

SWITCH = 'scripts/research/glm53_flash/decoder_moe/upstream-switch-layers.txt'
SWITCH_SHA256 = '914b40c985d96ffc8e3025ea6e3bef1fafcd588fa4dd99cf27d5e5f09c26ab35'
SWITCH_NODES = ('_gather_sort', '_scatter_unsort', 'SwitchLinear', 'SwiGLU', 'SwitchGLU')
SWITCH_GLOBALS = ['QuantizedSwitchLinear', 'SwiGLU', 'SwitchLinear', '_gather_sort', '_scatter_unsort',
                  'bool', 'int', 'math', 'mx', 'nn', 'property', 'str', 'super', 'swiglu']
CAPSULE = 'scripts/research/glm53_flash/decoder_moe/capsule.py'
CAPSULE_GLOBALS = ['ClampedMLP', 'ClampedSwiGLU', 'Glm5NextMoEGate', 'SwitchGLU', 'nn', 'super']


def _refused(name):
    def stub(*args, **kwargs):
        raise RuntimeError('DECODER_MOE_' + name + '_NOT_ADMITTED')
    return stub


def _census(text, name):
    table = symtable.symtable(text, name, 'exec')
    observed, pending = set(), [table]
    while pending:
        scope = pending.pop()
        observed.update(s.get_name() for s in scope.get_symbols() if s.is_global() and s.is_referenced())
        pending.extend(scope.get_children())
    return sorted(observed)


def verify_switch(switch_raw, ffn_source):
    if ffn_source.sha(switch_raw) != SWITCH_SHA256:
        raise ValueError('DECODER_MOE_SWITCH_DIGEST')
    tree = ast.parse(switch_raw)
    nodes = [ffn_source._node(tree, n) for n in SWITCH_NODES]
    text = '\n\n'.join(ast.unparse(n) for n in nodes)
    if _census(text, 'switch-nodes') != SWITCH_GLOBALS:
        raise ValueError('DECODER_MOE_SWITCH_CLOSURE:' + repr(_census(text, 'switch-nodes')))
    for n in nodes:
        for call in ast.walk(n):
            if isinstance(call, ast.Attribute) and call.attr in ('eval', 'tolist', 'item'):
                raise ValueError('DECODER_MOE_SWITCH_INNER_BARRIER')
    return nodes, {n.name: ffn_source.ast_sha(n) for n in nodes}


def verify_capsule(capsule_raw, language_raw, ffn_source):
    if ffn_source.sha(language_raw) != ffn_source.LANGUAGE_SHA256:
        raise ValueError('DECODER_MOE_UPSTREAM_DIGEST')
    original = ffn_source._node(ast.parse(language_raw), 'Glm5NextMoE')
    transformed = copy.deepcopy(original)
    transformed.name = 'source_moe'
    capsule = ast.parse(capsule_raw)
    if len(capsule.body) != 1 or ffn_source.ast_sha(capsule.body[0]) != ffn_source.ast_sha(transformed):
        raise ValueError('DECODER_MOE_CALLER_TRANSFORM')
    if _census(capsule_raw.decode(), 'moe-capsule') != CAPSULE_GLOBALS:
        raise ValueError('DECODER_MOE_CLOSURE:' + repr(_census(capsule_raw.decode(), 'moe-capsule')))
    return capsule.body[0], {'original_ast_sha256': ffn_source.ast_sha(original), 'capsule_ast_sha256': ffn_source.ast_sha(capsule.body[0]),
                             'digest_scheme': ffn_source.DIGEST_SCHEME}


def load(capsule_raw, language_raw, switch_raw, mx, nn, ffn_source, ffn_namespace, gate_class):
    switch_nodes, switch_digests = verify_switch(switch_raw, ffn_source)
    node, contract = verify_capsule(capsule_raw, language_raw, ffn_source)
    switch_ns = {'__name__': 'decoder_moe_switch_verified', 'mx': mx, 'nn': nn, 'math': math,
                 'swiglu': _refused('DEFAULT_SWIGLU'), 'QuantizedSwitchLinear': _refused('QUANTIZED_SWITCH_LINEAR')}
    for n in switch_nodes:
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-moe-switch:' + n.name, 'exec'), switch_ns)
    ns = {'__name__': 'decoder_moe_verified', 'mx': mx, 'nn': nn, 'SwitchGLU': switch_ns['SwitchGLU'],
          'ClampedSwiGLU': ffn_namespace['ClampedSwiGLU'], 'ClampedMLP': ffn_namespace['ClampedMLP'],
          'Glm5NextMoEGate': gate_class}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'decoder-moe-admitted', 'exec'), ns)
    contract['switch_node_ast_sha256'] = switch_digests
    return types.SimpleNamespace(namespace=ns, switch_namespace=switch_ns, contract=contract)

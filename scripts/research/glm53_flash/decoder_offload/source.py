"""Admit the retained ExpertStore (mlx-vlm moe_offload.py) and OffloadedSwitchGLU (mlx-vlm switch_layers.py).

Both by canonical-AST identity with a global census from digest-anchored
retained texts. The store's auto-budget helpers (_default_expert_cache_bytes,
_resident_bytes_on_disk) are refused stubs: every store here receives an
explicit byte budget. _PROJ_KEYS is taken from the retained text. The module
imports mlx.core inside its methods (as upstream); numpy is the admitted
environment's numpy.
"""
import ast
import symtable
import types
import typing
from collections import OrderedDict

OFFLOAD = 'scripts/research/glm53_flash/decoder_offload/upstream-moe-offload.txt'
OFFLOAD_SHA256 = '1cfb0198949d2c0f955ac5fdba3b5a64a260f75121b0bd2919647fdf193fd7e1'
STORE_GLOBALS = ['Exception', 'Optional', 'OrderedDict', '_PROJ_KEYS', '_default_expert_cache_bytes', '_resident_bytes_on_disk', 'bool', 'dict',
                 'glob', 'int', 'json', 'len', 'open', 'os', 'str', 'sum']
MODULE_GLOBALS = ['Any', 'Optional', 'Tuple', 'int', 'len', 'mx', 'nn', 'np', 'str', 'super']


def _refused(name):
    def stub(*args, **kwargs):
        raise RuntimeError('DECODER_OFFLOAD_' + name + '_NOT_ADMITTED')
    return stub


def _census(text, name):
    table = symtable.symtable(text, name, 'exec')
    observed, pending = set(), [table]
    while pending:
        scope = pending.pop()
        observed.update(s.get_name() for s in scope.get_symbols() if s.is_global() and s.is_referenced())
        pending.extend(scope.get_children())
    return sorted(observed)


def verify(offload_raw, switch_raw, ffn_source, moe_source):
    if ffn_source.sha(offload_raw) != OFFLOAD_SHA256:
        raise ValueError('DECODER_OFFLOAD_DIGEST')
    if ffn_source.sha(switch_raw) != moe_source.SWITCH_SHA256:
        raise ValueError('DECODER_OFFLOAD_SWITCH_DIGEST')
    otree = ast.parse(offload_raw)
    store = ffn_source._node(otree, 'ExpertStore')
    keys = next(n for n in otree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', None) == '_PROJ_KEYS')
    module = ffn_source._node(ast.parse(switch_raw), 'OffloadedSwitchGLU')
    if _census(ast.unparse(store), 'store') != STORE_GLOBALS:
        raise ValueError('DECODER_OFFLOAD_STORE_CLOSURE:' + repr(_census(ast.unparse(store), 'store')))
    if _census(ast.unparse(module), 'module') != MODULE_GLOBALS:
        raise ValueError('DECODER_OFFLOAD_MODULE_CLOSURE:' + repr(_census(ast.unparse(module), 'module')))
    return store, keys, module, {'store_ast_sha256': ffn_source.ast_sha(store), 'module_ast_sha256': ffn_source.ast_sha(module),
                                 'offload_sha256': OFFLOAD_SHA256, 'switch_sha256': moe_source.SWITCH_SHA256, 'digest_scheme': ffn_source.DIGEST_SCHEME}


def load(offload_raw, switch_raw, mx, nn, np, ffn_source, moe_source):
    import glob, json, os
    store, keys, module, contract = verify(offload_raw, switch_raw, ffn_source, moe_source)
    store_ns = {'__name__': 'decoder_offload_store_verified', 'Optional': typing.Optional, 'OrderedDict': OrderedDict, 'glob': glob, 'json': json, 'os': os,
                '_default_expert_cache_bytes': _refused('AUTO_BUDGET'), '_resident_bytes_on_disk': _refused('RESIDENT_BYTES_ON_DISK')}
    for n in (keys, store):
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-offload-store', 'exec'), store_ns)
    module_ns = {'__name__': 'decoder_offload_module_verified', 'mx': mx, 'nn': nn, 'np': np, 'Any': typing.Any, 'Optional': typing.Optional, 'Tuple': typing.Tuple}
    exec(compile(ast.Module(body=[module], type_ignores=[]), 'decoder-offload-module', 'exec'), module_ns)
    return types.SimpleNamespace(store_namespace=store_ns, module_namespace=module_ns, contract=contract, store_node=store, keys_node=keys, module_node=module,
                                 offload_text=offload_raw.decode(), switch_text=switch_raw.decode())

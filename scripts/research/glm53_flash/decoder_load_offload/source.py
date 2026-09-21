"""Admit the retained mlx-vlm loading path: plan, repack, patch_model and helpers (moe_offload.py), _quantization_for_path (one_bit.py).

Nodes are taken whole by canonical-AST identity with global censuses from the
digest-anchored retained texts. patch_model's two relative function-body
imports (OffloadedSwitchGLU, _quantization_for_path) are omitted from the
executed body and bound explicitly - the omitted spellings are recorded in the
contract. _get_language_sanitizer (the fallback for non-conventional names)
and _estimate_kv_reserve_bytes (auto budget) are refused stubs: every
patch_model call here passes an explicit expert_cache_gb.
"""
import ast
import re
import symtable
import types
import typing

ONE_BIT = 'scripts/research/glm53_flash/decoder_load_offload/upstream-one-bit.txt'
ONE_BIT_SHA256 = '6771b9003e4529658c6f051f208265cceb8a25fe7f7ee27369d2bed4098e46c7'
NODES = {'plan': ['PEREXPERT_RE', 'STACKED_FUSED_RE', 'STACKED_RE', 'dict', 'int', 'sorted'],
         '_check_disk_headroom': ['ValueError', 'float', 'glob', 'os', 'shutil', 'str', 'sum'],
         '_group_raw_names_by_layer': ['_LAYER_IDX_RE', 'dict', 'int'],
         '_expand_expert_layer': ['STACKED_FUSED_RE', 'STACKED_RE', 'Tuple', 'dict', 'int', 'max', 'range'],
         'repack': ['Exception', 'ValueError', '_LAYER_IDX_RE', '_check_disk_headroom', '_expand_expert_layer', '_get_language_sanitizer',
                    '_group_raw_names_by_layer', 'dict', 'float', 'glob', 'int', 'json', 'len', 'list', 'max', 'open', 'os', 'plan', 'print', 'set', 'sorted', 'str'],
         'patch_model': ['ExpertStore', 'Optional', 'Tuple', 'ValueError', '_estimate_kv_reserve_bytes', '_layer_id', '_n_experts', 'all', 'dict', 'enumerate',
                         'float', 'getattr', 'hasattr', 'int', 'isinstance', 'json', 'len', 'list', 'open', 'os', 'sorted', 'str'],
         '_layer_id': ['Optional', 'int', 're', 'str'], '_n_experts': ['getattr', 'int']}
CONSTANTS = ('_PROJ', '_FUSED_PROJ', 'PEREXPERT_RE', 'STACKED_RE', 'STACKED_FUSED_RE', '_LAYER_IDX_RE')
OMITTED_IMPORTS = ('from .models.switch_layers import OffloadedSwitchGLU', 'from .quantization.one_bit import _quantization_for_path')


def _refused(name):
    def stub(*args, **kwargs):
        raise RuntimeError('DECODER_LOAD_OFFLOAD_' + name + '_NOT_ADMITTED')
    return stub


def _census(text, name):
    table = symtable.symtable(text, name, 'exec')
    observed, pending = set(), [table]
    while pending:
        scope = pending.pop()
        observed.update(s.get_name() for s in scope.get_symbols() if s.is_global() and s.is_referenced())
        pending.extend(scope.get_children())
    return sorted(observed)


def verify(offload_raw, one_bit_raw, ffn_source, offload_source):
    if ffn_source.sha(offload_raw) != offload_source.OFFLOAD_SHA256:
        raise ValueError('DECODER_LOAD_OFFLOAD_DIGEST')
    if ffn_source.sha(one_bit_raw) != ONE_BIT_SHA256:
        raise ValueError('DECODER_LOAD_OFFLOAD_ONE_BIT_DIGEST')
    tree = ast.parse(offload_raw)
    nodes, digests = {}, {}
    for name, expected in NODES.items():
        node = ffn_source._node(tree, name)
        if _census(ast.unparse(node), name) != expected:
            raise ValueError('DECODER_LOAD_OFFLOAD_CLOSURE:' + name + ':' + repr(_census(ast.unparse(node), name)))
        nodes[name] = node; digests[name] = ffn_source.ast_sha(node)
    constants = [n for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in CONSTANTS]
    if [n.targets[0].id for n in constants] != list(CONSTANTS):
        raise ValueError('DECODER_LOAD_OFFLOAD_CONSTANTS')
    q = ffn_source._node(ast.parse(one_bit_raw), '_quantization_for_path')
    if _census(ast.unparse(q), 'q') != ['dict', 'isinstance', 'len', 'str']:
        raise ValueError('DECODER_LOAD_OFFLOAD_QUANT_PATH_CLOSURE')
    # patch_model: omit exactly the two relative function-body imports
    pm = nodes['patch_model']; kept, seen = [], []
    for stmt in pm.body:
        spelling = ast.unparse(stmt) if isinstance(stmt, ast.ImportFrom) else None
        (seen if spelling in OMITTED_IMPORTS else kept).append(spelling if spelling in OMITTED_IMPORTS else stmt)
    if sorted(seen) != sorted(OMITTED_IMPORTS):
        raise ValueError('DECODER_LOAD_OFFLOAD_PATCH_IMPORT_SHAPE')
    patched = ast.FunctionDef(name=pm.name, args=pm.args, body=kept, decorator_list=pm.decorator_list, returns=pm.returns, type_params=getattr(pm, 'type_params', []))
    ast.copy_location(patched, pm); ast.fix_missing_locations(patched)
    return nodes, constants, q, patched, {'node_ast_sha256': digests, 'quantization_for_path_ast_sha256': ffn_source.ast_sha(q), 'omitted_function_body_imports': list(OMITTED_IMPORTS),
                                          'offload_sha256': offload_source.OFFLOAD_SHA256, 'one_bit_sha256': ONE_BIT_SHA256}


def load(offload_raw, one_bit_raw, mx, nn, np, ffn_source, moe_source, offload_source, offload_bound):
    import glob, json, os, shutil
    nodes, constants, q, patched, contract = verify(offload_raw, one_bit_raw, ffn_source, offload_source)
    ns = {'__name__': 'decoder_load_offload_verified', 'glob': glob, 'json': json, 'os': os, 're': re, 'shutil': shutil, 'Optional': typing.Optional, 'Tuple': typing.Tuple,
          'nn': nn, 'ExpertStore': offload_bound.store_namespace['ExpertStore'], 'OffloadedSwitchGLU': offload_bound.module_namespace['OffloadedSwitchGLU'],
          '_get_language_sanitizer': _refused('LANGUAGE_SANITIZER_FALLBACK'), '_estimate_kv_reserve_bytes': _refused('KV_RESERVE_AUTO_BUDGET')}
    for n in constants:
        exec(compile(ast.Module(body=[n], type_ignores=[]), 'decoder-load-offload-constant', 'exec'), ns)
    exec(compile(ast.Module(body=[q], type_ignores=[]), 'decoder-load-offload:_quantization_for_path', 'exec'), ns)
    for name, n in nodes.items():
        exec(compile(ast.Module(body=[patched if name == 'patch_model' else n], type_ignores=[]), 'decoder-load-offload:' + name, 'exec'), ns)
    return types.SimpleNamespace(namespace=ns, contract=contract, offload_text=offload_raw.decode(), one_bit_text=one_bit_raw.decode())

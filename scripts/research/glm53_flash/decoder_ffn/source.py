"""Admit the entire closed FFN graph before adapting any selected node.

The outer harness binds this loader before import. No runtime bypass exists.
"""
import ast
import copy
import hashlib
import json
import re
import symtable
import types

ROOT = 'scripts/research/glm53_flash/'
LANGUAGE = ROOT + 'recurrent_dispatch/upstream-language.txt'
HC = ROOT + 'decoder_ffn/upstream-hyper-connection.txt'
CAPSULE = ROOT + 'decoder_ffn/capsule.py'
PROVENANCE = ROOT + 'decoder_ffn/provenance.json'
LANGUAGE_SHA256 = '6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196'
HC_SHA256 = '141fbe47d99f8eda9ab9a4c78665e5eb439cbf73b53a604c4da2a77845167bb3'
PROVENANCE_SHA256 = '0969e1a4ddfa8a09035826420995bda61f00b69917e059e759fd2d28c5fcca57'
LANGUAGE_NAMES = ('ClampedSwiGLU', 'ClampedMLP')
HC_NAMES = ('_hc_split_sinkhorn_ops','_hc_ops','HyperConnection','_hc_expand_op','hc_expand')
GRAPH_FILES = (CAPSULE, ROOT+'decoder_ffn/oracle.py', ROOT+'decoder_ffn/controls.py',
               'fixtures/research/glm53-flash-decoder-ffn-v1/fixtures.json',
               'scripts/research/tests/test_glm53_flash_decoder_ffn.py',
               'docs/glm53-flash/decoder-ffn.md')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ast_sha(node):
    return sha(ast.dump(node, include_attributes=False).encode())


def _node(tree, name):
    nodes = [n for n in tree.body if getattr(n,'name',None) == name]
    if len(nodes) != 1:
        raise ValueError('DENSE_FFN_NODE_MISSING:'+name)
    return nodes[0]


def _exec(node, namespace, filename):
    exec(compile(ast.Module(body=[node],type_ignores=[]),filename,'exec'),namespace)


def _json(raw):
    def unique(pairs):
        result = {}
        for k,v in pairs:
            if k in result:
                raise ValueError('DENSE_FFN_DUPLICATE_KEY')
            result[k] = v
        return result
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('DENSE_FFN_NONFINITE_JSON')))


def _closure(nodes):
    allowed = set(LANGUAGE_NAMES+HC_NAMES+('source_ffn_block',)) | {
        'mx','nn','Tuple','super','int','float','range','max','_hc_kernel'}
    text = '\n\n'.join(ast.unparse(n) for n in nodes)
    table = symtable.symtable(text,'ffn-closed-graph','exec')
    pending, observed = [table], set()
    while pending:
        scope = pending.pop()
        observed.update(s.get_name() for s in scope.get_symbols()
                        if s.is_global() and s.is_referenced())
        pending.extend(scope.get_children())
    if observed - allowed:
        raise ValueError('DENSE_FFN_UNSUPPORTED_CLOSURE:'+repr(sorted(observed-allowed)))
    return sorted(observed)


def load(root, mx, nn):
    # Admit bytes first. Graph-owned altered files cannot shift trust anchors.
    raw_provenance = (root/PROVENANCE).read_bytes()
    if sha(raw_provenance) != PROVENANCE_SHA256:
        raise ValueError('DENSE_FFN_PROVENANCE_DIGEST')
    p = _json(raw_provenance)
    language, hc = (root/LANGUAGE).read_bytes(), (root/HC).read_bytes()
    if sha(language) != LANGUAGE_SHA256 or sha(hc) != HC_SHA256:
        raise ValueError('DENSE_FFN_UPSTREAM_DIGEST')
    loader = (root/(ROOT+'decoder_ffn/source.py')).read_bytes()
    normalized, count = re.subn(rb"PROVENANCE_SHA256 = '[0-9a-f]{64}'",
        b"PROVENANCE_SHA256 = '"+b'0'*64+b"'",loader)
    if count != 1 or sha(normalized) != p['loader_template_sha256']:
        raise ValueError('DENSE_FFN_LOADER_DIGEST')
    if set(p['graph_sha256']) != set(GRAPH_FILES):
        raise ValueError('DENSE_FFN_GRAPH_INVENTORY')
    bodies = {path:(root/path).read_bytes() for path in GRAPH_FILES}
    if any(sha(raw) != p['graph_sha256'][path] for path,raw in bodies.items()):
        raise ValueError('DENSE_FFN_GRAPH_DIGEST')
    # No parsing or adaptation precedes byte admission.
    lt, ht, ct = ast.parse(language), ast.parse(hc), ast.parse(bodies[CAPSULE])
    language_nodes = [_node(lt,name) for name in LANGUAGE_NAMES]
    hc_nodes = [_node(ht,name) for name in HC_NAMES]
    original = _node(_node(lt,'Glm5NextDecoderLayer'),'_ffn_block')
    transformed = copy.deepcopy(original)
    transformed.name = 'source_ffn_block'
    call = _node(ct,'source_ffn_block')
    if len(ct.body) != 1 or ast_sha(call) != ast_sha(transformed):
        raise ValueError('DENSE_FFN_CALLER_TRANSFORM')
    contract = {'original_ast_sha256':ast_sha(original),
                'transformed_ast_sha256':ast_sha(transformed),
                'transformations':['rename _ffn_block to source_ffn_block only']}
    if p['caller_contract'] != contract:
        raise ValueError('DENSE_FFN_CALLER_CONTRACT')
    all_nodes = language_nodes+hc_nodes+[call]
    if p['node_ast_sha256'] != {n.name:ast_sha(n) for n in all_nodes}:
        raise ValueError('DENSE_FFN_NODE_DIGEST')
    if p['closure_globals'] != _closure(all_nodes):
        raise ValueError('DENSE_FFN_CLOSURE_CONTRACT')
    # All later nodes and decorators are admitted before the first adaptation.
    def refused(*args,**kwargs):
        raise RuntimeError('DENSE_FFN_FUSED_HC_FORBIDDEN')
    ns = {'mx':mx,'nn':nn,'Tuple':tuple,'__name__':'dense_ffn_verified',
          '_hc_kernel':refused}
    for node in all_nodes:
        _exec(node,ns,'dense-ffn-admitted:'+node.name)
    return types.SimpleNamespace(namespace=ns,provenance=p)

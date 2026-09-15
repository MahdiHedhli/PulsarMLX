"""Closed, source-verified dense decoder FFN adaptation."""
import ast
import hashlib
import json
import types


ROOT = 'scripts/research/glm53_flash/'
LANGUAGE = ROOT + 'recurrent_dispatch/upstream-language.txt'
HC = ROOT + 'decoder_ffn/upstream-hyper-connection.txt'
CAPSULE = ROOT + 'decoder_ffn/capsule.py'
sha = lambda b: hashlib.sha256(b).hexdigest()


def _node(raw, name):
    nodes = [n for n in ast.parse(raw).body if getattr(n, 'name', None) == name]
    if len(nodes) != 1:
        raise ValueError('DENSE_FFN_NODE_MISSING:' + name)
    return nodes[0]


def _exec(node, namespace, filename):
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, 'exec'), namespace)


def load(root, mx, nn):
    language = (root / LANGUAGE).read_bytes()
    hc = (root / HC).read_bytes()
    capsule = (root / CAPSULE).read_bytes()
    provenance = json.loads((root / (ROOT + 'decoder_ffn/provenance.json')).read_text())
    if sha(language) != provenance['language_sha256'] or sha(hc) != provenance['hyperconnection_sha256']:
        raise ValueError('DENSE_FFN_UPSTREAM_DIGEST')
    names = ('ClampedSwiGLU', 'ClampedMLP')
    hc_names = ('_hc_split_sinkhorn_ops', '_hc_ops', 'HyperConnection', '_hc_expand_op', 'hc_expand')
    ns = {'mx': mx, 'nn': nn, 'Tuple': tuple, '__name__': 'dense_ffn_verified'}
    def refused(*args, **kwargs):
        raise RuntimeError('DENSE_FFN_FUSED_HC_FORBIDDEN')
    ns['_hc_kernel'] = refused
    for name in names:
        node = _node(language, name)
        if sha(ast.dump(node, include_attributes=False).encode()) != provenance['language_nodes'][name]['ast_sha256']:
            raise ValueError('DENSE_FFN_LANGUAGE_NODE')
        _exec(node, ns, 'retained-language')
    for name in hc_names:
        node = _node(hc, name)
        if sha(ast.dump(node, include_attributes=False).encode()) != provenance['hc_nodes'][name]['ast_sha256']:
            raise ValueError('DENSE_FFN_HC_NODE')
        _exec(node, ns, 'retained-hyper-connection')
    call = _node(capsule, 'source_ffn_block')
    if sha(capsule) != provenance['capsule_sha256']:
        raise ValueError('DENSE_FFN_CAPSULE_DIGEST')
    _exec(call, ns, 'dense-ffn-capsule')
    return types.SimpleNamespace(namespace=ns, provenance=provenance)

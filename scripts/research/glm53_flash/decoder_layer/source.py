"""Admit the renamed upstream decoder layer over two already-admitted graphs.

The capsule is Glm5NextDecoderLayer with only the class name changed
(canonical-AST equality against the retained upstream node is required). The
attention class comes from the linear-attention admitted namespace (with its
counters and kernel admission); ClampedMLP, HyperConnection and hc_expand from
the dense-FFN admitted namespace. The sparse-attention and MoE constructors are
refused: this graph qualifies the (linear_attention, dense) layer type only.
"""
import ast
import copy
import symtable
import types

LANGUAGE_SHA256 = '6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196'
CAPSULE = 'scripts/research/glm53_flash/decoder_layer/capsule.py'
ALLOWED_GLOBALS = ['Any', 'ClampedMLP', 'Glm5NextLinearAttention', 'Glm5NextMoE', 'Glm5NextSparseAttention',
                   'HyperConnection', 'Optional', 'TextConfig', 'hc_expand', 'int', 'mx', 'nn', 'super']


def _refused(name):
    def constructor(*args, **kwargs):
        raise RuntimeError('DECODER_LAYER_' + name + '_NOT_ADMITTED')
    return constructor


def verify(capsule_raw, language_raw, ffn_source):
    if ffn_source.sha(language_raw) != LANGUAGE_SHA256:
        raise ValueError('DECODER_LAYER_UPSTREAM_DIGEST')
    tree = ast.parse(language_raw)
    original = ffn_source._node(tree, 'Glm5NextDecoderLayer')
    transformed = copy.deepcopy(original)
    transformed.name = 'source_decoder_layer'
    capsule = ast.parse(capsule_raw)
    if len(capsule.body) != 1 or ffn_source.ast_sha(capsule.body[0]) != ffn_source.ast_sha(transformed):
        raise ValueError('DECODER_LAYER_CALLER_TRANSFORM')
    table = symtable.symtable(capsule_raw.decode(), 'decoder-layer-capsule', 'exec')
    observed, pending = set(), [table]
    while pending:
        scope = pending.pop()
        observed.update(s.get_name() for s in scope.get_symbols() if s.is_global() and s.is_referenced())
        pending.extend(scope.get_children())
    if sorted(observed) != ALLOWED_GLOBALS:
        raise ValueError('DECODER_LAYER_CLOSURE:' + repr(sorted(observed)))
    return capsule.body[0], {'original_ast_sha256': ffn_source.ast_sha(original),
                             'capsule_ast_sha256': ffn_source.ast_sha(capsule.body[0]),
                             'digest_scheme': ffn_source.DIGEST_SCHEME, 'closure_globals': sorted(observed)}


def load(capsule_raw, language_raw, mx, nn, ffn_source, ffn_namespace, attention_namespace):
    node, contract = verify(capsule_raw, language_raw, ffn_source)
    ns = {'__name__': 'decoder_layer_verified', 'mx': mx, 'nn': nn, 'Optional': None, 'Any': None,
          'TextConfig': types.SimpleNamespace,
          'Glm5NextLinearAttention': attention_namespace['Glm5NextLinearAttention'],
          'Glm5NextSparseAttention': _refused('SPARSE_ATTENTION'), 'Glm5NextMoE': _refused('MOE'),
          'ClampedMLP': ffn_namespace['ClampedMLP'], 'HyperConnection': ffn_namespace['HyperConnection'],
          'hc_expand': ffn_namespace['hc_expand']}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'decoder-layer-admitted', 'exec'), ns)
    return types.SimpleNamespace(namespace=ns, contract=contract)

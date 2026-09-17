#!/usr/bin/env python3
"""45-layer topology fixture: the retained GLM-5.3-Flash config's layer pattern at tiny width, with a parameter-init recipe.

There is no numeric reference for this graph. The fixture freezes the real
pattern (layer_types, mlp_layer_types, first_k_dense_replace, hc_mult,
hc_sinkhorn_iters, hc_eps, rms_norm_eps, swiglu_limit, router fields,
indexer fields) copied from the retained config, every width reduced, the
token schedule, the init recipe (seed and per-parameter magnitudes drawn by
the candidate's mx.random after mx.random.seed) and the structural
expectations."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
UPSTREAM = ROOT / 'scripts/research/glm53_flash/decoder_topology/upstream-config.json'
SEED = 0x20260917E5


def main(out_path):
    raw = UPSTREAM.read_bytes(); c = json.loads(raw); tc = c.get('text_config', c)
    pattern_keys = ('layer_types', 'mlp_layer_types', 'first_k_dense_replace', 'hc_mult', 'hc_sinkhorn_iters', 'hc_eps', 'rms_norm_eps', 'swiglu_limit',
                    'n_group', 'topk_group', 'norm_topk_prob', 'routed_scaling_factor', 'topk_method', 'num_experts_per_tok', 'index_kpool',
                    'index_kpool_always_select_tail', 'mla_use_nope', 'attention_bias', 'qk_rope_head_dim', 'tie_word_embeddings', 'model_type', 'num_hidden_layers')
    pattern = {k: tc[k] for k in pattern_keys}
    assert pattern['num_hidden_layers'] == 45 and len(pattern['layer_types']) == 45
    config = {**pattern,
              'vocab_size': 16, 'hidden_size': 8, 'intermediate_size': 8, 'moe_intermediate_size': 8, 'n_routed_experts': 4, 'num_experts_per_tok': 2, 'n_shared_experts': 1,
              'num_attention_heads': 2, 'q_lora_rank': 8, 'kv_lora_rank': 8, 'qk_nope_head_dim': 8, 'v_head_dim': 8, 'index_n_heads': 2, 'index_head_dim': 8, 'index_topk': 8,
              'linear_num_heads': 1, 'linear_head_dim': 32, 'linear_conv_kernel_dim': 2, 'linear_lower_bound': None}
    init = {'seed': SEED, 'rules': [
        ['.attn_hc.scale', 'const', [1.0, 1.0, 1.1]], ['.ffn_hc.scale', 'const', [1.0, 1.0, 1.1]],
        ['.attn_hc.base', 'uniform', 0.3], ['.ffn_hc.base', 'uniform', 0.3], ['.attn_hc.fn', 'uniform', 0.2], ['.ffn_hc.fn', 'uniform', 0.2],
        ['layernorm.weight', 'uniform_around_one', 0.1], ['norm.weight', 'uniform_around_one', 0.1], ['o_norm.weight', 'uniform_around_one', 0.1],
        ['k_norm.bias', 'uniform', 0.1], ['forget_gate.A_log', 'const', [0.03125]], ['forget_gate.dt_bias', 'uniform', 0.05],
        ['e_score_correction_bias', 'uniform', 0.1], ['index_kpool_compress_ape', 'uniform', 0.3], ['index_kpool_compress_gate', 'uniform', 0.3],
        ['conv1d.weight', 'uniform', 0.3], ['embed_tokens.weight', 'uniform', 0.5], ['lm_head.weight', 'uniform', 0.5], ['', 'uniform', 0.25]],
        'note': 'first matching rule by substring wins; uniform(-m, m); uniform_around_one is 1 + uniform(-m, m); drawn by mx.random after mx.random.seed(seed)'}
    # every prefill call stays inside the admitted linear-attention kernel domain (S <= 5); the sparse regime (T > index_topk) is reached through decode
    schedule = {'prefill_tokens': 5, 'decode_tokens': 5, 'ids': [3, 9, 1, 14, 7, 5, 11, 2, 8, 12], 'paths': ['prefill5+decode5', 'stepwise10']}
    linear_idx = [i for i, t in enumerate(pattern['layer_types']) if t == 'linear_attention']; sparse_idx = [i for i, t in enumerate(pattern['layer_types']) if t != 'linear_attention']
    expected = {'is_linear': [t == 'linear_attention' for t in pattern['layer_types']], 'linear_layers': linear_idx, 'sparse_layers': sparse_idx,
                'moe_layers': [i for i in range(45) if i >= pattern['first_k_dense_replace'] and pattern['mlp_layer_types'][i] == 'sparse'],
                'cache_types': ['ArraysCache' if t == 'linear_attention' else 'CacheList' for t in pattern['layer_types']],
                'indexer_regime_by_T': {str(T): ('bypass' if T <= config['index_topk'] else 'sparse') for T in range(1, 11)},
                'equivalence_tolerance': 1e-4}
    doc = {'schema': 'flash-topology-fixtures/1', 'upstream_config_sha256': hashlib.sha256(raw).hexdigest(), 'pattern_keys': list(pattern_keys),
           'cases': [{'fixture_id': 'topology-45-layers-tiny', 'config': config, 'init': init, 'schedule': schedule}], 'expected': {'topology-45-layers-tiny': expected},
           'structural_controls': {'mask-routing-swapped': 'must be rejected or break prefill/decode equivalence', 'layer-caches-dropped': 'must break prefill/decode equivalence'},
           'scope': 'STRUCTURAL AND SELF-CONSISTENT ONLY; no numeric reference; not an oracle qualification',
           'revision': 'v1 scheduled a 6-token prefill and a 10-token full prefill; the admitted linear-attention Metal kernel domain is S <= 5 per call (MODULE_KERNEL_DOMAIN at first Metal contact); v2 compares prefill 5 + decode 5 against 10 single steps'}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    print('sparse layers', sparse_idx, 'moe layers', len(expected['moe_layers']), 'regimes', expected['indexer_regime_by_T'])


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-topology-v1/fixtures.json')

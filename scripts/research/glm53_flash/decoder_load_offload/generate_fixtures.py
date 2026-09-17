#!/usr/bin/env python3
"""Loading-path fixture: a two-layer stack config at hidden 64 with the graph-15 4-bit/g64 routed experts, a seeded init
recipe for everything else, a prefill+decode schedule, and the structural expectations of repack()/patch_model()."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
QUANTIZED = ROOT / 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json'
SEED = 0x20260917A7


def main(out_path):
    q = json.loads(QUANTIZED.read_bytes()); base = next(c for c in q['cases'] if c['fixture_id'] == 'switch-4bit-g64')
    cfg = base['config']; E, D, I = cfg['num_experts'], cfg['hidden'], cfg['intermediate']
    config = {'model_type': 'glm5_next_text', 'vocab_size': 16, 'hidden_size': D, 'num_hidden_layers': 2, 'hc_mult': 2, 'hc_sinkhorn_iters': 3, 'hc_eps': 1e-6,
              'rms_norm_eps': 1e-5, 'tie_word_embeddings': False, 'layer_types': ['linear_attention', 'deepseek_sparse_attention'], 'mlp_layer_types': ['dense', 'sparse'],
              'first_k_dense_replace': 1, 'intermediate_size': I, 'moe_intermediate_size': I, 'swiglu_limit': cfg['swiglu_limit'],
              'n_routed_experts': E, 'num_experts_per_tok': 2, 'n_shared_experts': 1, 'norm_topk_prob': True, 'routed_scaling_factor': 2.5, 'n_group': 1, 'topk_group': 1, 'topk_method': 'noaux_tc',
              'num_attention_heads': 2, 'q_lora_rank': 64, 'kv_lora_rank': 64, 'qk_nope_head_dim': 32, 'v_head_dim': 32, 'qk_rope_head_dim': 0, 'mla_use_nope': True, 'attention_bias': False,
              'index_n_heads': 2, 'index_head_dim': 32, 'index_topk': 2, 'index_kpool': 1, 'index_kpool_always_select_tail': True,
              'linear_num_heads': 1, 'linear_head_dim': 32, 'linear_conv_kernel_dim': 2, 'linear_lower_bound': None,
              'quantization': {'group_size': cfg['group_size'], 'bits': cfg['bits'], 'mode': 'affine'}}
    init = {'seed': SEED, 'rules': [['.attn_hc.scale', 'const', [1.0, 1.0, 1.1]], ['.ffn_hc.scale', 'const', [1.0, 1.0, 1.1]],
                                    ['.attn_hc.base', 'uniform', 0.3], ['.ffn_hc.base', 'uniform', 0.3], ['.attn_hc.fn', 'uniform', 0.1], ['.ffn_hc.fn', 'uniform', 0.1],
                                    ['layernorm.weight', 'uniform_around_one', 0.1], ['norm.weight', 'uniform_around_one', 0.1], ['o_norm.weight', 'uniform_around_one', 0.1],
                                    ['k_norm.bias', 'uniform', 0.1], ['forget_gate.A_log', 'const', [0.03125]], ['forget_gate.dt_bias', 'uniform', 0.05],
                                    ['e_score_correction_bias', 'uniform', 0.1], ['index_kpool_compress_ape', 'uniform', 0.3], ['index_kpool_compress_gate', 'uniform', 0.1],
                                    ['conv1d.weight', 'uniform', 0.3], ['embed_tokens.weight', 'uniform', 0.5], ['lm_head.weight', 'uniform', 0.2], ['', 'uniform', 0.1]],
            'note': 'first matching rule by substring wins; drawn by mx.random after mx.random.seed; the routed experts (layers.1.mlp.switch_mlp.*) come from the frozen quantized arrays instead'}
    expert_key = 'model.layers.1.mlp.switch_mlp'
    expected = {'checkpoint_names': 'the admitted LanguageModel parameter names (container prefix already stripped); stacked routed experts as {expert_key}.{gate,up,down}_proj.{weight,scales,biases}',
                'repack_files': ['experts/layer_0001.safetensors', 'offload_index.json', 'resident-0001.safetensors', 'config.json', 'model.safetensors.index.json'],
                'expert_file_keys': sorted(f'e{j}.{p}_proj.{k}' for j in range(E) for p in ('gate', 'up', 'down') for k in ('weight', 'scales', 'biases')),
                'expert_shapes': {'gate_proj.weight': [I, D // 8], 'gate_proj.scales': [I, D // 64], 'up_proj.weight': [I, D // 8], 'down_proj.weight': [D, I // 8], 'down_proj.scales': [D, I // 64]},
                'offload_index': {'layers': [1], 'num_experts': E}, 'resident_excludes_prefix': expert_key, 'patched_modules': 1, 'resolved_quant': [cfg['group_size'], cfg['bits'], 'affine'],
                'equivalence_tolerance': 1e-4, 'schedule': {'prefill_tokens': 3, 'ids': [3, 9, 1, 14, 7]}}
    doc = {'schema': 'flash-load-offload-fixtures/1', 'derived_from': {'fixture': 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json', 'case': base['fixture_id']},
           'cases': [{'fixture_id': 'load-offload-2layer-h64', 'config': config, 'init': init, 'expert_key': expert_key, 'quantized_experts': base['quantized'], 'expert_config': cfg}],
           'expected': {'load-offload-2layer-h64': expected},
           'structural_controls': {'plan-shared-experts-not-resident': 'rejected or equivalence broken', 'patch-expert-count-check-inverted': 'rejected (swapped 0)',
                                   'quant-bits-resolved-as-8': 'equivalence broken or rejected', 'expand-expert-slices-rotated': 'equivalence broken'},
           'scope': 'STRUCTURAL + EQUIVALENCE; no numeric oracle at hidden 64; resident weights stay fp32'}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n'); print('written', len(base['quantized']['gate']), 'experts')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-load-offload-v1/fixtures.json')

#!/usr/bin/env python3
"""Quantized-load fixture: the graph-19 hidden-64 stack config with a config-style quantization block (4-bit g64 default for the
routed experts; 8-bit per-path entries for every resident linear, embedding, multilinear and the indexer; the router gate carries
no entry since it has no to_quantized), the seeded init, a schedule, and structural expectations."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOAD = ROOT / 'fixtures/research/glm53-flash-decoder-load-offload-v1/fixtures.json'

RESIDENT_8BIT = [
    'model.embed_tokens', 'lm_head',
    'model.layers.0.self_attn.q_proj', 'model.layers.0.self_attn.k_proj', 'model.layers.0.self_attn.v_proj', 'model.layers.0.self_attn.b_proj',
    'model.layers.0.self_attn.g_a_proj', 'model.layers.0.self_attn.g_b_proj', 'model.layers.0.self_attn.o_proj',
    'model.layers.0.self_attn.forget_gate.f_a_proj', 'model.layers.0.self_attn.forget_gate.f_b_proj',
    'model.layers.0.mlp.gate_proj', 'model.layers.0.mlp.up_proj', 'model.layers.0.mlp.down_proj',
    'model.layers.1.self_attn.q_a_proj', 'model.layers.1.self_attn.q_b_proj', 'model.layers.1.self_attn.kv_a_proj_with_mqa', 'model.layers.1.self_attn.o_proj',
    'model.layers.1.self_attn.embed_q', 'model.layers.1.self_attn.unembed_out',
    'model.layers.1.self_attn.indexer.wq_b', 'model.layers.1.self_attn.indexer.wk', 'model.layers.1.self_attn.indexer.weights_proj',
    'model.layers.1.mlp.shared_experts.gate_proj', 'model.layers.1.mlp.shared_experts.up_proj', 'model.layers.1.mlp.shared_experts.down_proj',
]
EXPERTS_4BIT = ['model.layers.1.mlp.switch_mlp.gate_proj', 'model.layers.1.mlp.switch_mlp.up_proj', 'model.layers.1.mlp.switch_mlp.down_proj']
UNQUANTIZED_MODULES = ['model.layers.1.mlp.gate (Glm5NextMoEGate: no to_quantized; fp32 router)', 'conv1d', 'norms', 'hyper-connections', 'k_norm']


def main(out_path):
    base = json.loads(LOAD.read_bytes())['cases'][0]
    quantization = {'group_size': 64, 'bits': 4, 'mode': 'affine', **{p: {'group_size': 64, 'bits': 8} for p in RESIDENT_8BIT}}
    config = {**base['config'], 'quantization': quantization}
    case = {'fixture_id': 'quantized-load-2layer-h64', 'config': config, 'init': base['init'], 'schedule': {'prefill_tokens': 3, 'ids': [3, 9, 1, 14, 7]},
            'kv_b': {'bits': 8, 'group_size': 64, 'note': 'an HF-style kv_b_proj [heads*(dq+dv), kvr] = [128, 64] quantized at 8-bit g64 for the DeepSeek-V3.2 quantized split branch'}}
    expected = {'quantized_modules_8bit': RESIDENT_8BIT, 'quantized_modules_4bit': EXPERTS_4BIT, 'unquantized': UNQUANTIZED_MODULES,
                'scales_present_for': sorted(RESIDENT_8BIT + EXPERTS_4BIT), 'bits_by_module': {**{p: 8 for p in RESIDENT_8BIT}, **{p: 4 for p in EXPERTS_4BIT}},
                'reload_bit_identical': True, 'mixed_layout_equivalence_tolerance': 1e-4,
                'kv_b_split_dequantized_tolerance': 'one quantization step: |dequant(split) - split(dequant(kv_b))| <= max scale of the re-quantized groups',
                'expert_file_keys': sorted(f'e{j}.{p}_proj.{k}' for j in range(4) for p in ('gate', 'up', 'down') for k in ('weight', 'scales', 'biases'))}
    doc = {'schema': 'flash-quantized-load-fixtures/1', 'derived_from': 'fixtures/research/glm53-flash-decoder-load-offload-v1/fixtures.json', 'cases': [case], 'expected': {case['fixture_id']: expected},
           'structural_controls': {'predicate-bits-swapped': 'strict load rejects (scales/biases shapes)', 'resident-scales-dropped': 'strict load rejects',
                                   'kv-b-split-transposed': 'dequantized split mismatch or shape rejection'},
           'scope': 'STRUCTURAL + EQUIVALENCE; no numeric oracle at hidden 64; mlx core nn.quantize/QuantizedLinear/QuantizedEmbedding are environment-bound, not upstream code'}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n'); print('written', len(RESIDENT_8BIT), '8-bit modules,', len(EXPERTS_4BIT), '4-bit')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-quantized-load-v1/fixtures.json')

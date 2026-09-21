#!/usr/bin/env python3
"""Deterministic two-layer stack fixture frozen by the composed oracle before observation.

Layer 0 is a (linear_attention, dense) layer whose parameters come from the
decoder-layer generator's family (accepted recurrence domain); layer 1 is a
(sparse attention, MoE) layer at the sparse track's geometry with kpool 1 /
topk 2 and the MoE track's 4-expert top-2 geometry. Embeddings are one-negative-
lane sign patterns so the first attention input sits in the accepted linear
reference's domain. Cases are regenerated until the linear reference admits the
inputs, every sparse selection margin is >= SPARSE_MARGIN and every router
margin is >= ROUTER_MARGIN.
"""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_stack import oracle as stack_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_layer import oracle as layer_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_layer import generate_fixtures as layer_generator  # noqa: E402
from scripts.research.glm53_flash.linear_attention import oracle as attention_oracle  # noqa: E402
from scripts.research.glm53_flash.recurrent_dispatch import oracle as recurrence_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_ffn import oracle as ffn_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import oracle as sparse_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_moe import oracle as moe_oracle  # noqa: E402
from scripts.research.glm53_flash.router_caller import rc_oracle  # noqa: E402

SEED = 0x20260917B2
SPARSE_MARGIN, ROUTER_MARGIN = 2e-2, 1e-2
V, D, H, S = 8, 4, 2, 4
SPARSE = {'hidden_size': D, 'num_attention_heads': 2, 'q_lora_rank': 4, 'kv_lora_rank': 4, 'qk_nope_head_dim': 4, 'v_head_dim': 4,
          'qk_rope_head_dim': 0, 'mla_use_nope': True, 'attention_bias': False, 'rms_norm_eps': 1e-6,
          'index_n_heads': 2, 'index_head_dim': 4, 'index_topk': 2, 'index_kpool': 1, 'index_kpool_always_select_tail': True}
MOE = {'n_routed_experts': 4, 'hidden_size': D, 'num_experts_per_tok': 2, 'norm_topk_prob': True, 'routed_scaling_factor': 2.5,
       'n_group': 1, 'topk_group': 1, 'topk_method': 'noaux_tc', 'moe_intermediate_size': 3, 'n_shared_experts': 1, 'swiglu_limit': 1.0}
REFS = {'layer_run': layer_oracle.run, 'attention_reference': attention_oracle.module_reference, 'accepted_recurrence': recurrence_oracle,
        'ffn_run': ffn_oracle.run, 'hc': layer_oracle, 'sparse_run': sparse_oracle.run, 'moe_run': moe_oracle.run,
        'router_reference': rc_oracle.reference}


def f32(v):
    return struct.unpack('f', struct.pack('f', v))[0]


def mat(rng, rows, cols, scale):
    return [[f32(rng.uniform(-scale, scale)) for _ in range(cols)] for _ in range(rows)]


def hc(rng):
    mix = (2 + H) * H
    return {'fn': [[round(rng.uniform(-0.7, 0.7), 4) for _ in range(H * D)] for _ in range(mix)],
            'base': [round(rng.uniform(-0.3, 0.3), 4) for _ in range(mix)], 'scale': [1.0, 1.0, 1.1]}


def sparse_weights(rng):
    c = SPARSE; heads, dq, dv, qr, kvr, nI, di, kp = (c[k] for k in ('num_attention_heads', 'qk_nope_head_dim', 'v_head_dim', 'q_lora_rank',
                                                                  'kv_lora_rank', 'index_n_heads', 'index_head_dim', 'index_kpool'))
    weights = {'q_a_proj': mat(rng, qr, D, .6), 'q_a_layernorm': [f32(rng.uniform(.7, 1.3)) for _ in range(qr)], 'q_b_proj': mat(rng, heads * dq, qr, .8),
               'kv_a_proj_with_mqa': mat(rng, kvr, D, .6), 'kv_a_layernorm': [f32(rng.uniform(.7, 1.3)) for _ in range(kvr)],
               'embed_q': [mat(rng, kvr, dq, .7) for _ in range(heads)], 'unembed_out': [mat(rng, dv, kvr, .7) for _ in range(heads)],
               'o_proj': mat(rng, D, heads * dv, .5)}
    indexer = {'wq_b': mat(rng, nI * di, qr, .8), 'wk': mat(rng, di, D, .6), 'k_norm_weight': [f32(rng.uniform(.7, 1.3)) for _ in range(di)],
               'k_norm_bias': [f32(rng.uniform(-.2, .2)) for _ in range(di)], 'weights_proj': mat(rng, nI, D, .8),
               'compress_ape': mat(rng, kp, di, .5), 'compress_gate': mat(rng, di, D, .5)}
    return {'config': dict(SPARSE), 'weights': weights, 'indexer': indexer}


def moe_weights(rng):
    E, I = MOE['n_routed_experts'], MOE['moe_intermediate_size']
    return {'config': dict(MOE), 'gate_weight': mat(rng, E, D, .8), 'gate_bias': [f32(rng.uniform(-.1, .1)) for _ in range(E)],
            'experts': {p: [mat(rng, I, D, 1.2) if p != 'down' else mat(rng, D, I, .8) for _ in range(E)] for p in ('gate', 'up', 'down')},
            'shared': {p: (mat(rng, I, D, 1.2) if p != 'down' else mat(rng, D, I, .8)) for p in ('gate', 'up', 'down')}}


def main(out_path):
    rng = random.Random(SEED)
    for attempt in range(1, 10001):
        l0 = layer_generator.case(H, random.Random(rng.getrandbits(64)))
        signs = [[-1.0 if d == rng.randrange(D) else 1.0 for d in range(D)] for _ in range(V)]
        magnitudes = [rng.randint(8, 64) / 64 for _ in range(V)]  # one magnitude per token: uniform |v| after the norm
        embedding = [[signs[v][d] * magnitudes[v] for d in range(D)] for v in range(V)]
        case = {'fixture_id': 'stack-linear-dense-sparse-moe-s4', 'ids': rng.sample(range(V), S),
                'config': {'model_type': 'glm5_next_text', 'vocab_size': V, 'hidden_size': D, 'num_hidden_layers': 2, 'hc_mult': H,
                           'hc_sinkhorn_iters': 3, 'hc_eps': 1e-6, 'rms_norm_eps': 1e-6, 'tie_word_embeddings': False,
                           'layer_types': ['linear_attention', 'deepseek_sparse_attention'], 'mlp_layer_types': ['dense', 'sparse'],
                           'first_k_dense_replace': 1, 'intermediate_size': 3, 'swiglu_limit': 1.0, **layer_generator.LINEAR, **SPARSE, **MOE},
                'embedding': embedding,
                'layer0': {'attn_hc': l0['attn_hc'], 'ffn_hc': l0['ffn_hc'], 'linear_config': l0['linear_config'],
                           'linear_parameters': l0['linear_parameters'], 'ffn': l0['ffn']},
                'layer1': {'attn_hc': hc(rng), 'ffn_hc': hc(rng), 'sparse': sparse_weights(rng), 'moe': moe_weights(rng)},
                'norm_weight': [f32(rng.uniform(.7, 1.3)) for _ in range(D)], 'lm_head': mat(rng, V, D, .8),
                'generator': {'seed': hex(SEED), 'attempt': attempt}}
        try:
            r = stack_oracle.run(case, REFS)
        except ValueError as exc:  # accepted references reject out-of-domain inputs
            continue
        sparse_margins = [m for m in (sparse_oracle.run({'config': {**SPARSE}, 'x': r['layer1_attn_norm'], **case['layer1']['sparse']})['selection_margins'] or []) if m is not None]
        moe_case = {'config': MOE, 'x': r['layer1_ffn_norm'], **{k: case['layer1']['moe'][k] for k in ('gate_weight', 'gate_bias', 'experts', 'shared')}}
        router_margins = [t['selection_margin'] for t in moe_oracle.run(moe_case, rc_oracle.reference)['tokens']]
        if r['layer1_topk'] is None or any(m < SPARSE_MARGIN for m in sparse_margins) or any(m < ROUTER_MARGIN for m in router_margins):
            continue
        break
    else:
        raise SystemExit('no admissible case')
    expected = r
    allowance, factor = 1e-4, 10
    variants = {
        'mean-replaced-by-stream0': ("pooled = [[math.fsum(out1[t][h][d] for h in range(H)) / H for d in range(D)] for t in range(S)]",
                                     "pooled = [[out1[t][0][d] for d in range(D)] for t in range(S)]"),
        'mean-replaced-by-sum': ("pooled = [[math.fsum(out1[t][h][d] for h in range(H)) / H for d in range(D)] for t in range(S)]",
                                 "pooled = [[math.fsum(out1[t][h][d] for h in range(H)) for d in range(D)] for t in range(S)]"),
        'final-norm-omitted': ("final = [rmsnorm(p, case['norm_weight'], eps) for p in pooled]", "final = [list(p) for p in pooled]"),
        'lm-head-tied-to-embedding': ("logits = [_proj(f, case['lm_head']) for f in final]", "logits = [_proj(f, case['embedding']) for f in final]"),
        'linear-layer-given-attention-mask': ("layer_masks = [ssm_mask if lt == 'linear_attention' else fa_mask for lt in cfg['layer_types']]",
                                              "layer_masks = [fa_mask for lt in cfg['layer_types']]"),
        'sparse-layer-mask-dropped': ("if allowed is not None and case.get('intersect_causal', True):", "if False:"),
    }
    text = Path(stack_oracle.__file__).read_text()
    predicted = {}
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant_' + label}; exec(compile(text.replace(before, after), 'oracle-variant:' + label, 'exec'), ns)
        try:
            out = ns['run'](case, REFS)['logits']
            err = max(abs(a - b) for ra, rb in zip(out, expected['logits']) for a, b in zip(ra, rb))
            predicted[label] = ('KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL', err)
        except ValueError as exc:
            predicted[label] = ('KILL', 'rejected:' + str(exc))
    matrix = {'schema': 'flash-stack-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': [case['fixture_id']], 'kill_margin_factor': factor,
              'matrix': {k: [v[0]] for k, v in predicted.items()}, 'predicted_oracle_variant_error': {k: [v[1]] for k, v in predicted.items()},
              'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants},
              'reasoning': {
                  'mean-replaced-by-stream0': 'the residual streams differ after two hyper-connected layers, so taking stream 0 instead of the mean changes the pooled state',
                  'mean-replaced-by-sum': 'sum = hc_mult * mean; the final RMSNorm removes a uniform scale, so this is expected to be inactive at the logits: a designed control',
                  'final-norm-omitted': 'the pooled state is not unit-RMS and the norm weight is not ones',
                  'lm-head-tied-to-embedding': 'lm_head and the embedding are independent matrices here (tie_word_embeddings False)',
                  'linear-layer-given-attention-mask': 'the linear layer receives a boolean [S,S] mask it cannot consume (the reference does not model it; the candidate is expected to reject or corrupt)',
                  'sparse-layer-mask-dropped': 'the indexer only selects causally visible pools, so intersecting the sparse mask with the causal mask is a no-op: a designed inactive control',
              }}
    doc = {'schema': 'flash-stack-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_stack/oracle.py',
           'tolerances': {'layer0_output': 1e-4, 'layer1_attn_norm': 1e-4, 'layer1_attention': 1e-4, 'layer1_x1': 1e-4, 'layer1_ffn_norm': 1e-4,
                          'layer1_mlp': 1e-4, 'layer1_output': 1e-4, 'pooled': 1e-4, 'final_norm': 1e-4, 'logits': 1e-4},
           'generator': {'seed': hex(SEED), 'sparse_margin': SPARSE_MARGIN, 'router_margin': ROUTER_MARGIN, 'attempt': case['generator']['attempt'],
                         'sparse_margins': sparse_margins, 'router_margins': router_margins},
           'cases': [case], 'expected': {case['fixture_id']: expected}, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    print('attempt', case['generator']['attempt'], 'ids', case['ids'], 'allowed', expected['layer1_allowed'], 'sparse margins', [round(m, 4) for m in sparse_margins],
          'router margins', [round(m, 4) for m in router_margins], 'clamp', expected['layer0_clamp_active_elements'], expected['moe_clamp_active_elements'])
    for k, v in predicted.items():
        print(f'  {k:36s} {v[0]:9s} {v[1] if isinstance(v[1], str) else round(v[1], 5)}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json')

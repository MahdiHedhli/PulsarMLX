#!/usr/bin/env python3
"""Deterministic layer fixtures with expected boundaries frozen by the oracle.

Input design constraint (structural, declared): the accepted linear-attention
reference admits inputs only with |v| <= 1, FP32-exact. An RMS-normalised vector
has some |element| >= 1, strictly > 1 unless all magnitudes are equal. Layer
inputs therefore use a rank-1 sign pattern x[h][d] = s[d] * c[h] (c dyadic in
(0,1]) so the collapsed xc has uniform magnitude and the normalised attention
input has uniform magnitude just below 1 (RMSNorm eps), inside the |v| <= 1 domain. The norm stage is thereby exercised only at a symmetric
point; recorded as a limitation, not hidden. No candidate arithmetic is used.
"""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_layer import oracle as layer_oracle  # noqa: E402
from scripts.research.glm53_flash.linear_attention import oracle as attention_oracle  # noqa: E402
from scripts.research.glm53_flash.recurrent_dispatch import oracle as recurrence_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_ffn import oracle as ffn_oracle  # noqa: E402

SEED = 0x20260916A8
I, S, B = 4, 2, 1
LINEAR = {'hidden_size': I, 'linear_num_heads': 1, 'linear_head_dim': 32, 'linear_conv_kernel_dim': 2,
          'linear_lower_bound': None, 'rms_norm_eps': 1e-6}


def dyadic(rng, scale=1.0, q=64):
    return struct.unpack('f', struct.pack('f', rng.randint(-q, q) / q * scale))[0]


def tensor(rng, dims, scale=1.0):
    if len(dims) == 1:
        return [dyadic(rng, scale) for _ in range(dims[0])]
    return [tensor(rng, dims[1:], scale) for _ in range(dims[0])]


def case(H, rng):
    # One negative lane per token: enough sign structure to vary the attention
    # input across tokens while keeping projections free of cancellation, which
    # the accepted recurrence's |k|<=.5 post-L2-norm bound requires.
    signs = [[-1.0 if d == rng.randrange(I) else 1.0 for d in range(I)] for _ in range(S)]
    magnitudes = [[rng.randint(8, 64) / 64 for _ in range(H)] for _ in range(S)]
    x = [[[[signs[t][d] * magnitudes[t][h] for d in range(I)] for h in range(H)] for t in range(S)]]
    mix = (2 + H) * H
    hc = lambda: {'fn': [[round(rng.uniform(-0.7, 0.7), 4) for _ in range(H * I)] for _ in range(mix)],
                  'base': [round(rng.uniform(-0.3, 0.3), 4) for _ in range(mix)], 'scale': [1.0, 1.0, 1.1]}
    # Dyadic parameter family mirroring glm53-flash-linear-attention-v1, scaled
    # down for +/-1 inputs so q,k,v,a,b stay inside the accepted recurrence
    # bounds (|q|,|k|,|a|,|b| <= .5, |v| <= .75). o_proj is kept larger than the
    # linear fixtures' 1/512 so attention-path mutants remain observable at the
    # layer output; this is an input-design choice, not a tolerance change.
    def family(dims, unit, lo, hi, signed=False):
        if len(dims) == 1:
            return [(rng.choice((-1, 1)) if signed else 1) * rng.randint(lo, hi) / unit for _ in range(dims[0])]
        return [family(dims[1:], unit, lo, hi, signed) for _ in range(dims[0])]
    spec = {'q_proj.weight': (256, 4, 8), 'k_proj.weight': (256, 4, 8), 'v_proj.weight': (256, 4, 8),
            'conv1d.weight': (64, 12, 20), 'forget_gate.f_a_proj.weight': (256, 0, 5), 'forget_gate.f_b_proj.weight': (256, 0, 5),
            'b_proj.weight': (256, 0, 4), 'g_a_proj.weight': (256, 0, 5), 'g_b_proj.weight': (256, 0, 5), 'o_proj.weight': (256, 4, 8)}
    # q/k/v/conv/o_proj positive (as in the linear fixtures); the gate/forget
    # projections carry signs so the recurrence gates are not one-sided.
    signed = {'forget_gate.f_a_proj.weight', 'forget_gate.f_b_proj.weight', 'b_proj.weight', 'g_a_proj.weight', 'g_b_proj.weight'}
    params = {k: family(list(v), *spec[k], signed=(k in signed)) for k, v in attention_oracle.parameter_shapes(LINEAR).items() if k in spec}
    params['forget_gate.A_log'] = [1 / 32]
    params['forget_gate.dt_bias'] = [rng.randint(0, 3) / 64 for _ in range(32)]
    params['o_norm.weight'] = [rng.randint(48, 58) / 64 for _ in range(32)]
    intermediate = 3
    ffn = {'gate': [[round(rng.uniform(-1.6, 1.6), 4) for _ in range(I)] for _ in range(intermediate)],
           'up': [[round(rng.uniform(-1.6, 1.6), 4) for _ in range(I)] for _ in range(intermediate)],
           'down': [[round(rng.uniform(-0.8, 0.8), 4) for _ in range(intermediate)] for _ in range(I)], 'limit': 1.0}
    return {'fixture_id': f'layer-h{H}-linear-dense', 'shape': [B, S, H, I], 'hc_sinkhorn_iters': 3, 'hc_eps': 1e-6,
            'rms_norm_eps': 1e-6, 'clamp_expected': 'active', 'x': x, 'attn_hc': hc(), 'ffn_hc': hc(),
            'linear_config': LINEAR, 'linear_parameters': params, 'ffn': ffn,
            'input_design': 'rank-1 sign pattern x[h][d]=s[d]*c[h]; normalised attention input is uniform-magnitude, |v|<=1 (accepted reference domain)'}


def main():
    rng = random.Random(SEED)
    cases, expected = [], {}
    for H in (2, 3):
        c = case(H, rng)
        r = layer_oracle.run(c, attention_oracle.module_reference, recurrence_oracle, ffn_oracle.run)
        norm = r['boundaries']['attn_norm']
        assert all(abs(v) <= 1.0 and abs(v) > 0.999 for b in norm for t in b for v in t), 'attention input must be within the accepted domain (|v|<=1) and uniform-magnitude'
        if c['clamp_expected'] == 'active':
            assert r['clamp_active_elements'] > 0, 'clamp inactive for an active-declared case'
        cases.append(c)
        expected[c['fixture_id']] = {'boundaries': r['boundaries'], 'clamp_active_elements': r['clamp_active_elements'],
                                     'attention_maximum_radii': r['attention_reference']['maximum_radii']}
    tolerances = {'attn_pre': 1e-4, 'attn_post': 1e-4, 'attn_comb': 1e-4, 'attn_xc': 1e-4, 'attn_norm': 1e-4,
                  'attention': 1e-4, 'x1': 1e-4, 'output': 1e-4}
    out = {'schema': 'glm53-flash-decoder-layer-v1', 'generator': {'seed': hex(SEED), 'module': 'decoder_layer/generate_fixtures.py'},
           'linear_config': LINEAR, 'tolerances': tolerances, 'cases': cases, 'expected': expected,
           'limits': ['norm stage exercised only at the symmetric +/-1 point (accepted linear reference domain)',
                      'cache=None; cache lifecycle across calls is slice 2', 'fixture scale; not real-model correctness']}
    target = ROOT / 'fixtures/research/glm53-flash-decoder-layer-v1/fixtures.json'
    target.write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({'cases': [c['fixture_id'] for c in cases], 'clamp_active': {k: v['clamp_active_elements'] for k, v in expected.items()},
                      'attention_radii': {k: v['attention_maximum_radii'] for k, v in expected.items()}}))


if __name__ == '__main__':
    main()

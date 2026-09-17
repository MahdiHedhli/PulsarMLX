"""Independent stdlib reference for the two-layer GLM-5.3-Flash stack (Glm5NextModel + lm_head), prefill.

    e_t   = embedding[ids[t]] ; streams_t = [e_t] * hc_mult           (broadcast to the residual streams)
    fa_mask = causal ; ssm_mask = None                                  (create_attention_mask / create_ssm_mask)
    layer 0 (linear_attention, dense):  accepted decoder-layer reference (mask None)
    layer 1 (sparse attention, MoE):    attn_hc -> input norm -> accepted sparse reference -> hc_expand
                                        -> ffn_hc -> post norm -> accepted MoE reference -> hc_expand
    h_t = mean over streams ; final = rmsnorm(h_t) * w ; logits = lm_head final

The HyperConnection arithmetic is the decoder-layer reference's. Layer norms
use weight ones (as constructed by the controls); the final norm carries an
explicit weight. binary64 with math.fsum; no candidate arithmetic.
"""
import math


def _dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def _proj(x, w):
    return [_dot(row, x) for row in w]


def rmsnorm(x, w, eps):
    r = 1.0 / math.sqrt(math.fsum(v * v for v in x) / len(x) + eps)
    return [v * r * g for v, g in zip(x, w)]


def run(case, refs):
    """refs: layer_run, attention_reference, accepted_recurrence, ffn_run, hc (decoder_layer.oracle), sparse_run, moe_run, router_reference."""
    cfg = case['config']; H, D = cfg['hc_mult'], cfg['hidden_size']; S = len(case['ids']); eps = cfg['rms_norm_eps']
    iters, hc_eps = cfg['hc_sinkhorn_iters'], cfg['hc_eps']
    hc = refs['hc']
    fa_mask, ssm_mask = 'causal', None
    layer_masks = [ssm_mask if lt == 'linear_attention' else fa_mask for lt in cfg['layer_types']]
    if layer_masks[0] is not None:
        raise ValueError('LINEAR_LAYER_MASK_NOT_MODELLED')
    embed = [case['embedding'][i] for i in case['ids']]
    streams0 = [[list(e) for _ in range(H)] for e in embed]
    l0 = case['layer0']
    layer_case = {'fixture_id': case['fixture_id'] + ':layer0', 'shape': [1, S, H, D], 'hc_sinkhorn_iters': iters, 'hc_eps': hc_eps,
                  'rms_norm_eps': eps, 'clamp_expected': 'unconstrained', 'x': [streams0], 'attn_hc': l0['attn_hc'], 'ffn_hc': l0['ffn_hc'],
                  'linear_config': l0['linear_config'], 'linear_parameters': l0['linear_parameters'], 'ffn': l0['ffn']}
    r0 = refs['layer_run'](layer_case, refs['attention_reference'], refs['accepted_recurrence'], refs['ffn_run'])
    out0 = r0['boundaries']['output'][0]                       # [S][H][D]
    l1 = case['layer1']
    pre_a, post_a, comb_a, attn_in = [], [], [], []
    for t in range(S):
        pre, post, comb = hc.hyper_connection(out0[t], l1['attn_hc']['fn'], l1['attn_hc']['base'], l1['attn_hc']['scale'], iters, hc_eps, eps)
        xc = hc.collapse(out0[t], pre)
        attn_in.append(hc.rms_norm(xc, eps)); pre_a.append(pre); post_a.append(post); comb_a.append(comb)
    sparse_case = {'fixture_id': case['fixture_id'] + ':sparse', 'config': {**l1['sparse']['config'], 'rms_norm_eps': eps}, 'tokens': S,
                   'x': attn_in, 'weights': l1['sparse']['weights'], 'indexer': l1['sparse']['indexer']}
    sr = refs['sparse_run'](sparse_case)
    allowed = sr['allowed']
    if allowed is not None and case.get('intersect_causal', True):
        allowed = [[j for j in row if j <= t] for t, row in enumerate(allowed)]   # sparse_mask & causal upstream: a no-op by construction
    x1 = [hc.expand(sr['output'][t], out0[t], post_a[t], comb_a[t]) for t in range(S)]
    ffn_in, post_f, comb_f = [], [], []
    for t in range(S):
        pre, post, comb = hc.hyper_connection(x1[t], l1['ffn_hc']['fn'], l1['ffn_hc']['base'], l1['ffn_hc']['scale'], iters, hc_eps, eps)
        ffn_in.append(hc.rms_norm(hc.collapse(x1[t], pre), eps)); post_f.append(post); comb_f.append(comb)
    moe_case = {'fixture_id': case['fixture_id'] + ':moe', 'config': l1['moe']['config'], 'tokens': S, 'x': ffn_in,
                'gate_weight': l1['moe']['gate_weight'], 'gate_bias': l1['moe']['gate_bias'], 'experts': l1['moe']['experts'], 'shared': l1['moe']['shared']}
    mr = refs['moe_run'](moe_case, refs['router_reference'])
    mlp_out = [mr['tokens'][t]['output'] for t in range(S)]
    out1 = [hc.expand(mlp_out[t], x1[t], post_f[t], comb_f[t]) for t in range(S)]
    pooled = [[math.fsum(out1[t][h][d] for h in range(H)) / H for d in range(D)] for t in range(S)]
    final = [rmsnorm(p, case['norm_weight'], eps) for p in pooled]
    logits = [_proj(f, case['lm_head']) for f in final]
    return {'layer0_output': out0, 'layer1_attn_norm': attn_in, 'layer1_topk': sr['topk'], 'layer1_allowed': allowed,
            'layer1_attention': sr['output'], 'layer1_x1': x1, 'layer1_ffn_norm': ffn_in, 'layer1_mlp': mlp_out, 'layer1_output': out1,
            'pooled': pooled, 'final_norm': final, 'logits': logits,
            'layer0_clamp_active_elements': r0['clamp_active_elements'], 'moe_clamp_active_elements': mr['clamp_active_elements']}

"""Independent stdlib reference for Glm5NextMoE at tiny geometry.

    inds, scores = gate(x)                       # accepted router reference (rc_oracle)
    y_e = down_e(clamped_swiglu(up_e x, gate_e x))   for each selected expert e
    y = sum_e score_e * y_e
    output = y + shared(x)                       # ClampedMLP, same clamped activation

binary64 arithmetic with math.fsum; the router stage delegates to the accepted
router reference on a float32-represented case. No candidate arithmetic.
"""
import math


def _sigmoid(v):
    return 1.0 / (1.0 + math.exp(-v)) if v >= 0 else math.exp(v) / (1.0 + math.exp(v))


def _dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def _proj(x, w):
    return [_dot(row, x) for row in w]


def clamped_swiglu(up, gate, limit):
    out, active = [], 0
    for u, g in zip(up, gate):
        active += int(g > limit or abs(u) > limit)
        g = min(g, limit)
        u = max(-limit, min(u, limit))
        out.append(g * _sigmoid(g) * u)
    return out, active


def mlp(x, gate_w, up_w, down_w, limit):
    act, active = clamped_swiglu(_proj(x, up_w), _proj(x, gate_w), limit)
    return _proj(act, down_w), active


def run(case, router_reference):
    cfg = case['config']
    router_case = {'config': {k: cfg[k] for k in ('n_routed_experts', 'hidden_size', 'num_experts_per_tok', 'norm_topk_prob',
                                                   'routed_scaling_factor', 'n_group', 'topk_group', 'topk_method')},
                   'represented_input': case['x'], 'represented_weight': case['gate_weight'], 'bias': case['gate_bias']}
    routed = router_reference(router_case)
    tokens = []
    clamp_active = 0
    for t, x in enumerate(case['x']):
        row = routed['rows'][t]
        experts = {}
        combine = [0.0] * len(x)
        for e in row['selected_ids']:
            y, active = mlp(x, case['experts']['gate'][e], case['experts']['up'][e], case['experts']['down'][e], cfg['swiglu_limit'])
            clamp_active += active
            experts[str(e)] = y
            s = row['scores_by_id'][str(e)]
            combine = [c + s * v for c, v in zip(combine, y)]
        shared, active = mlp(x, case['shared']['gate'], case['shared']['up'], case['shared']['down'], cfg['swiglu_limit'])
        clamp_active += active
        output = [a + b for a, b in zip(combine, shared)]
        tokens.append({'logits': row['logits'], 'selected_ids': row['selected_ids'], 'scores_by_id': row['scores_by_id'],
                       'selection_margin': row['selection_margin'], 'experts': experts, 'combine': combine,
                       'shared': shared, 'output': output})
    return {'tokens': tokens, 'clamp_active_elements': clamp_active}

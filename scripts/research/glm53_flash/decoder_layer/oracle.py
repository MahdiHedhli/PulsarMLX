"""Independent stdlib reference for one dense/linear GLM-5.3-Flash decoder layer.

Composition mirrors Glm5NextDecoderLayer.__call__ for layer_type
'linear_attention' and a dense ClampedMLP:

    residual = x
    xc, post, comb = attn_hc(x)
    r  = self_attn(input_layernorm(xc))          # accepted linear-attention reference
    x1 = hc_expand(r, residual, post, comb)
    output = _ffn_block(x1)                      # accepted dense-FFN reference

The HyperConnection arithmetic is reimplemented here in binary64 and is
cross-checked against the accepted dense-FFN reference on its own fixtures by
the qualification test. Declared cast point: the normalized attention input is
rounded to FP32 before it enters the accepted linear-attention reference, which
requires FP32-exact inputs; nothing else is rounded. No candidate arithmetic is
imported.
"""
import math
import struct


def fp32(v):
    return struct.unpack('f', struct.pack('f', v))[0]


def _sigmoid(v):
    return 1.0 / (1.0 + math.exp(-v)) if v >= 0 else math.exp(v) / (1.0 + math.exp(v))


def _dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def rms_norm(v, eps):
    inv = 1.0 / math.sqrt(math.fsum(x * x for x in v) / len(v) + eps)
    return [x * inv for x in v]  # weight is ones, as constructed by the controls


def hyper_connection(streams, fn, base, scale, iters, eps, hidden_eps):
    """pre [H], post [H], comb [H][H] for one token's H residual streams."""
    H = len(streams)
    flat = [d for s in streams for d in s]
    z = rms_norm(flat, hidden_eps)
    mixes = [_dot(w, z) for w in fn]
    pre = [_sigmoid(mixes[h] * scale[0] + base[h]) + eps for h in range(H)]
    post = [2 * _sigmoid(mixes[H + h] * scale[1] + base[H + h]) for h in range(H)]
    comb = []
    for i in range(H):
        logits = [mixes[2 * H + i * H + j] * scale[2] + base[2 * H + i * H + j] for j in range(H)]
        peak = max(logits)
        numer = [math.exp(q - peak) for q in logits]
        total = sum(numer)
        comb.append([q / total + eps for q in numer])
    for j in range(H):
        total = sum(comb[i][j] for i in range(H)) + eps
        for i in range(H):
            comb[i][j] /= total
    for _ in range(iters - 1):
        for i in range(H):
            total = sum(comb[i]) + eps
            comb[i] = [q / total for q in comb[i]]
        for j in range(H):
            total = sum(comb[i][j] for i in range(H)) + eps
            for i in range(H):
                comb[i][j] /= total
    return pre, post, comb


def collapse(streams, pre):
    D = len(streams[0])
    return [math.fsum(pre[h] * streams[h][d] for h in range(len(streams))) for d in range(D)]


def expand(branch, streams, post, comb):
    H, D = len(streams), len(streams[0])
    return [[post[j] * branch[d] + math.fsum(comb[i][j] * streams[i][d] for i in range(H))
             for d in range(D)] for j in range(H)]


def run(case, attention_reference, accepted_recurrence, ffn_reference):
    """Return every boundary and the layer output for one case.

    attention_reference: linear_attention.oracle.module_reference
    ffn_reference: decoder_ffn.oracle.run
    """
    B, S, H, D = case['shape']
    x = case['x']
    hc_a, hc_f = case['attn_hc'], case['ffn_hc']
    iters, eps, hidden_eps = case['hc_sinkhorn_iters'], case['hc_eps'], case['rms_norm_eps']
    boundaries = {k: [] for k in ('attn_pre', 'attn_post', 'attn_comb', 'attn_xc', 'attn_norm',
                                   'attention', 'x1', 'output')}
    attention_inputs = [[] for _ in range(B)]
    stage1 = []
    for b in range(B):
        rows = []
        for t in range(S):
            streams = x[b][t]
            pre, post, comb = hyper_connection(streams, hc_a['fn'], hc_a['base'], hc_a['scale'], iters, eps, hidden_eps)
            xc = collapse(streams, pre)
            norm = rms_norm(xc, hidden_eps)
            cast = [fp32(v) for v in norm]  # declared cast point
            attention_inputs[b].append(cast)
            rows.append({'pre': pre, 'post': post, 'comb': comb, 'xc': xc, 'norm': norm, 'cast': cast})
        stage1.append(rows)
    attention_case = {'B': B, 'S': S, 'config': case['linear_config'], 'parameters': case['linear_parameters'],
                      'inputs': attention_inputs, 'mask': None, 'cache0': None, 'cache1': None,
                      'initial_lengths': [S] * B, 'initial_padding': [0] * B, 'parts': [S]}
    attention = attention_reference(attention_case, accepted_recurrence)
    ffn_results = []
    for b in range(B):
        batch = {k: [] for k in boundaries}
        for t in range(S):
            r1 = stage1[b][t]
            r = attention['output'][b][t]
            x1 = expand(r, x[b][t], r1['post'], r1['comb'])
            ffn_case = {**case['ffn'], 'shape': [1, 1, H, D], 'x': [[x1]], 'sinkhorn_iters': iters,
                        'hc_eps': eps, 'rms_norm_eps': hidden_eps, 'fn': hc_f['fn'], 'base': hc_f['base'],
                        'scale': hc_f['scale'], 'clamp_expected': case['clamp_expected'], 'fixture_id': case['fixture_id']}
            f = ffn_reference(ffn_case)
            ffn_results.append(f)
            out = f['boundaries']['output'][0][0]
            for k, v in (('attn_pre', r1['pre']), ('attn_post', r1['post']), ('attn_comb', r1['comb']),
                         ('attn_xc', r1['xc']), ('attn_norm', r1['cast']), ('attention', r), ('x1', x1), ('output', out)):
                batch[k].append(v)
        for k in boundaries:
            boundaries[k].append(batch[k])
    # Per-time cache states from the accepted reference, for the split-run
    # (cache lifecycle) comparison: cache0 [B,K-1,3Q] and cache1 [B,H,D,D] after
    # each token, plus the final states. Comparison-only values, never inputs.
    cache_events = [{'time': e['time'], 'cache0': e['cache0'], 'cache1': e['cache1']} for e in attention['events']]
    return {'boundaries': boundaries, 'attention_reference': {'maximum_radii': attention['maximum_radii']},
            'attention_cache_events': cache_events, 'attention_final_cache': {'cache0': attention['cache0'], 'cache1': attention['cache1']},
            'clamp_active_elements': sum(f['clamp_active_elements'] for f in ffn_results),
            'ffn_boundaries': [f['boundaries'] for f in ffn_results]}

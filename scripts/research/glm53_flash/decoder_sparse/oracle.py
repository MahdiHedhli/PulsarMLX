"""Independent stdlib reference for Glm5NextSparseAttention (NoPE MLA + lightning indexer), prefill.

    qr      = rmsnorm(x Wqa^T) ; q_h = (qr Wqb^T) split per head
    latent  = rmsnorm(x Wkva^T)
    indexer = pooled-key scoring over kpool-token pools, relu(q.k * d^-1/2) weighted per head,
              causal pool visibility, top select_k pools -> token indices, always-select-tail
    keys_h  = latent W_embed[h] ; values_h = latent W_unembed[h]^T
    out     = concat_h softmax(q_h keys_h^T * dq^-1/2, allowed) values_h ; Wo^T

Bypass: when the sequence length is <= index_topk the indexer returns no
selection and attention uses the causal mask alone. binary64 with math.fsum;
no candidate arithmetic. Batch 1, no cache, no padding.
"""
import math


def _dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def _proj(x, w):
    return [_dot(row, x) for row in w]


def rmsnorm(x, w, eps):
    r = 1.0 / math.sqrt(math.fsum(v * v for v in x) / len(x) + eps)
    return [v * r * g for v, g in zip(x, w)]


def layernorm(x, w, b, eps):
    m = math.fsum(x) / len(x)
    var = math.fsum((v - m) ** 2 for v in x) / len(x)
    r = 1.0 / math.sqrt(var + eps)
    return [(v - m) * r * g + c for v, g, c in zip(x, w, b)]


def softmax(v):
    m = max(v)
    e = [math.exp(u - m) for u in v]
    z = math.fsum(e)
    return [u / z for u in e]


def indexer(case, x, qr):
    cfg, w = case['config'], case['indexer']
    S = len(x); kp = cfg['index_kpool']; nI = cfg['index_n_heads']; di = cfg['index_head_dim']
    q = [[_proj(qr[t], w['wq_b'])[h * di:(h + 1) * di] for h in range(nI)] for t in range(S)]
    k = [layernorm(_proj(x[t], w['wk']), w['k_norm_weight'], w['k_norm_bias'], 1e-6) for t in range(S)]
    gate = [_proj(x[t], w['compress_gate']) for t in range(S)]
    P = (S + kp - 1) // kp
    pools = []
    for p in range(P):
        idx = [p * kp + j for j in range(kp)]
        valid = [i < S for i in idx]
        logits = [[gate[i][d] + w['compress_ape'][j][d] if valid[j] else -1e30 for d in range(di)] for j, i in enumerate(idx)]
        probs = [softmax([logits[j][d] for j in range(kp)]) for d in range(di)]  # softmax over the pool axis, per feature
        # invalid slots gather the clipped index (S-1) upstream; their probability is exactly 0
        key = [math.fsum(probs[d][j] * k[min(idx[j], S - 1)][d] for j in range(kp)) for d in range(di)]
        pools.append({'indices': [i if valid[j] else -1 for j, i in enumerate(idx)], 'valid': all(valid), 'key': key,
                      'end': min(max(idx[-1] if valid[-1] else -1, 0), S - 1)})
    select_k = min(cfg['index_topk'] // kp, P)
    scale = di ** -0.5
    width = cfg['index_topk'] + (kp - 1 if cfg['index_kpool_always_select_tail'] and kp > 1 else 0)
    rows = []
    for t in range(S):
        weights = [v * nI ** -0.5 for v in _proj(x[t], w['weights_proj'])]
        scores = []
        for p in range(P):
            per_head = [max(_dot(q[t][h], pools[p]['key']) * scale, 0.0) for h in range(nI)]
            candidate = pools[p]['end'] <= t and pools[p]['valid']
            scores.append(math.fsum(wh * s for wh, s in zip(weights, per_head)) if candidate else -1e30)
        order = sorted(range(P), key=lambda p: -scores[p])
        selected = order[:select_k]
        cand = sorted((scores[p] for p in range(P) if scores[p] > -1e30), reverse=True)
        margin = (cand[select_k - 1] - cand[select_k]) if len(cand) > select_k else None
        topk = []
        for p in selected:
            topk.extend(pools[p]['indices'] if scores[p] > -1e30 else [-1] * kp)
        if cfg['index_kpool_always_select_tail'] and kp > 1:
            visible_count = t + 1
            tail_count = visible_count - (visible_count // kp) * kp
            tail_start = visible_count - tail_count
            topk.extend([tail_start + o if o < tail_count and tail_start + o < S else -1 for o in range(kp - 1)])
        topk = (topk + [-1] * width)[:width]
        rows.append({'topk': topk, 'index_scores': scores, 'selection_margin': margin,
                     'allowed': sorted({i for i in topk if i >= 0})})
    return rows


def run(case):
    cfg, w = case['config'], case['weights']
    x = case['x']; S = len(x); H = cfg['num_attention_heads']; dq = cfg['qk_nope_head_dim']; dv = cfg['v_head_dim']
    eps = cfg['rms_norm_eps']
    qr = [rmsnorm(_proj(xt, w['q_a_proj']), w['q_a_layernorm'], eps) for xt in x]
    q = [[_proj(qr[t], w['q_b_proj'])[h * dq:(h + 1) * dq] for h in range(H)] for t in range(S)]
    latent = [rmsnorm(_proj(xt, w['kv_a_proj_with_mqa']), w['kv_a_layernorm'], eps) for xt in x]
    bypass = S <= cfg['index_topk']
    index_rows = None if bypass else indexer(case, x, qr)
    keys = [[[_dot(latent[t], [w['embed_q'][h][r][d] for r in range(len(latent[t]))]) for d in range(dq)] for t in range(S)] for h in range(H)]
    values = [[_proj(latent[t], w['unembed_out'][h]) for t in range(S)] for h in range(H)]
    scale = dq ** -0.5
    attn = []
    for t in range(S):
        allowed = [j for j in range(t + 1)] if bypass else index_rows[t]['allowed']
        if not allowed:  # explicit, not an assert: the rejection must survive -O
            raise ValueError('EMPTY_ATTENTION_ROW')
        concat = []
        for h in range(H):
            logits = [_dot(q[t][h], keys[h][j]) * scale for j in allowed]
            p = softmax(logits)
            concat.extend(math.fsum(pj * values[h][j][d] for pj, j in zip(p, allowed)) for d in range(dv))
        attn.append(concat)
    output = [_proj(a, w['o_proj']) for a in attn]
    return {'qr': qr, 'kv_latent': latent, 'bypass': bypass,
            'topk': None if bypass else [r['topk'] for r in index_rows],
            'selection_margins': None if bypass else [r['selection_margin'] for r in index_rows],
            'allowed': None if bypass else [r['allowed'] for r in index_rows],
            'attention_concat': attn, 'output': output}

"""Independent stdlib reference for Glm5NextSparseAttention decode with caches (batch 1, no padding).

A prefill of S0 tokens followed by one-token decode steps, with explicit
cache state: the latent cache (all latents so far), the indexer cache (per-
token key/gate/valid packs) and the indexer's pool state
(stable complete pools kept, the suffix recomputed each step), i.e. the
incremental pooling rule:

    T = tokens so far; if T <= index_topk: bypass (dense over all cached positions)
    first non-bypass step or prefill: full pooling; later steps: pools[:t_prev // kp] kept,
    pools recomputed from s0 = (t_prev // kp) * kp with indices offset by s0
    select top select_k visible complete pools + tail; attend over the selected positions

The per-step row must equal the frozen prefill reference's row t
(decoder_sparse.oracle), which is asserted by the generator and the offline
test: the incremental rule is proven equivalent to full pooling on the fixture
independently of the candidate. The absorbed-query decode form
(q W_embed^T . latent, then unembed) equals the prefill key/value form; the
reference uses the key/value form. binary64 with math.fsum.
"""
import math

from scripts.research.glm53_flash.decoder_sparse import oracle as prefill


def _pools(cfg, ape, k, gate, start, T):
    """Pools over positions [start, T) in kpool groups (absolute indices)."""
    kp, di = cfg['index_kpool'], cfg['index_head_dim']
    n = T - start
    P = (n + kp - 1) // kp
    pools = []
    for p in range(P):
        idx = [start + p * kp + j for j in range(kp)]
        valid = [i < T for i in idx]
        logits = [[gate[i][d] + ape[j][d] if valid[j] else -1e30 for d in range(di)] for j, i in enumerate(idx)]
        probs = [prefill.softmax([logits[j][d] for j in range(kp)]) for d in range(di)]
        key = [math.fsum(probs[d][j] * k[min(idx[j], T - 1)][d] for j in range(kp)) for d in range(di)]
        pools.append({'indices': [i if valid[j] else -1 for j, i in enumerate(idx)], 'valid': all(valid), 'key': key})
    return pools


def run(case):
    cfg, w, ix = case['config'], case['weights'], case['indexer']
    x = case['x']; S = len(x); S0 = case['prefill_tokens']
    H, dq, dv, kp, nI, di = (cfg[k] for k in ('num_attention_heads', 'qk_nope_head_dim', 'v_head_dim', 'index_kpool', 'index_n_heads', 'index_head_dim'))
    eps = cfg['rms_norm_eps']
    qr = [prefill.rmsnorm(prefill._proj(xt, w['q_a_proj']), w['q_a_layernorm'], eps) for xt in x]
    q = [[prefill._proj(qr[t], w['q_b_proj'])[h * dq:(h + 1) * dq] for h in range(H)] for t in range(S)]
    latent = [prefill.rmsnorm(prefill._proj(xt, w['kv_a_proj_with_mqa']), w['kv_a_layernorm'], eps) for xt in x]
    qi = [[prefill._proj(qr[t], ix['wq_b'])[h * di:(h + 1) * di] for h in range(nI)] for t in range(S)]
    k = [prefill.layernorm(prefill._proj(x[t], ix['wk']), ix['k_norm_weight'], ix['k_norm_bias'], 1e-6) for t in range(S)]
    gate = [prefill._proj(x[t], ix['compress_gate']) for t in range(S)]
    keys = [[[prefill._dot(latent[t], [w['embed_q'][h][r][d] for r in range(len(latent[t]))]) for d in range(dq)] for t in range(S)] for h in range(H)]
    values = [[prefill._proj(latent[t], w['unembed_out'][h]) for t in range(S)] for h in range(H)]
    select_k_of = lambda P: min(cfg['index_topk'] // kp, P)
    scale_i, scale_a = di ** -0.5, dq ** -0.5
    width = cfg['index_topk'] + (kp - 1 if cfg['index_kpool_always_select_tail'] and kp > 1 else 0)
    pool_state = None  # (pools, T)
    steps = []

    def attend(t, allowed):
        if not allowed:
            raise ValueError('EMPTY_ATTENTION_ROW')
        concat = []
        for h in range(H):
            p = prefill.softmax([prefill._dot(q[t][h], keys[h][j]) * scale_a for j in allowed])
            concat.extend(math.fsum(pj * values[h][j][d] for pj, j in zip(p, allowed)) for d in range(dv))
        return concat, prefill._proj(concat, w['o_proj'])

    def select(t, pools, T):
        weights = [v * nI ** -0.5 for v in prefill._proj(x[t], ix['weights_proj'])]
        scores = []
        for pool in pools:
            end = min(max(pool['indices'][-1], 0), T - 1)
            candidate = end <= t and pool['valid']
            per_head = [max(prefill._dot(qi[t][h], pool['key']) * scale_i, 0.0) for h in range(nI)]
            scores.append(math.fsum(wh * s for wh, s in zip(weights, per_head)) if candidate else -1e30)
        P = len(pools); sk = select_k_of(P)
        order = sorted(range(P), key=lambda p: -scores[p])[:sk]
        cand = sorted((s for s in scores if s > -1e30), reverse=True)
        margin = (cand[sk - 1] - cand[sk]) if len(cand) > sk else None
        topk = []
        for p in order:
            topk.extend(pools[p]['indices'] if scores[p] > -1e30 else [-1] * kp)
        if cfg['index_kpool_always_select_tail'] and kp > 1:
            vc = t + 1; tc = vc - (vc // kp) * kp; ts = vc - tc
            topk.extend([ts + o if o < tc and ts + o < T else -1 for o in range(kp - 1)])
        topk = (topk + [-1] * width)[:width]
        return topk, margin

    def step(t_list, T, kind):
        nonlocal pool_state
        rows = []
        if T <= cfg['index_topk']:
            for t in t_list:
                concat, out = attend(t, list(range(t + 1)))
                rows.append({'time': t, 'regime': 'bypass', 'topk': None, 'allowed': list(range(t + 1)), 'attention_concat': concat, 'output': out, 'selection_margin': None})
            return rows
        if kind == 'decode' and pool_state is not None:
            old, t_prev = pool_state
            n_stable = t_prev // kp; s0 = n_stable * kp
            pools = old[:n_stable] + _pools(cfg, ix['compress_ape'], k, gate, s0, T)
            pooling = 'incremental'
        else:
            pools = _pools(cfg, ix['compress_ape'], k, gate, 0, T); pooling = 'full'
        pool_state = (pools, T)
        for t in t_list:
            topk, margin = select(t, pools, T)
            allowed = sorted({i for i in topk if i >= 0})
            concat, out = attend(t, allowed)
            rows.append({'time': t, 'regime': 'sparse', 'pooling': pooling, 'topk': topk, 'allowed': allowed, 'selection_margin': margin,
                         'attention_concat': concat, 'output': out,
                         'pool_state': {'indices': [p['indices'] for p in pools], 'valid': [p['valid'] for p in pools], 'keys': [p['key'] for p in pools]}})
        return rows

    steps.append({'kind': 'prefill', 'tokens': list(range(S0)), 'rows': step(list(range(S0)), S0, 'prefill')})
    for t in range(S0, S):
        steps.append({'kind': 'decode', 'tokens': [t], 'rows': step([t], t + 1, 'decode')})
    return {'steps': steps, 'qr': qr, 'kv_latent': latent}

"""Reference for two-layer stack decode with make_cache caches (batch 1, no padding).

Prefill S0 tokens, then one token per step. Because every stage is causal and
the caches carry exactly the per-position state, the logits at position t are
those of the frozen stack reference on the whole sequence
(decoder_stack.oracle); this module re-slices that reference into the step
schedule and adds, as comparison-only values, the accepted linear-attention
reference's per-time cache states (cache0 [K-1, 3Q] and cache1 [H, D, D] after
each token) for the linear layer's ArraysCache, and the cache routing the model
performs (ArraysCache for linear layers, CacheList(KVCache, KVCache) for
sparse layers; lengths unset, so the SSM mask is None and the attention mask
is the causal mask at prefill and None at decode). The reference has no
compile distinction: the compiled decode-step FFN is expected to equal the
eager block.
"""


def run(case, refs):
    """refs: stack_run (decoder_stack.oracle.run), layer_run, attention_reference, accepted_recurrence, ffn_run, hc, sparse_run, moe_run, router_reference."""
    cfg = case['config']
    S0 = case['prefill_tokens']; S = len(case['ids'])
    linear_slots = cfg['linear_cache_slots']
    if linear_slots != 2:
        raise ValueError('LINEAR_CACHE_SLOTS')
    routing = ['ArraysCache' if lt == 'linear_attention' else 'CacheList' for lt in cfg['layer_types']]
    if routing != case['cache_routing']:
        raise ValueError('CACHE_ROUTING')
    full = refs['stack_run'](case, refs)
    # linear-layer cache states after each token, from the accepted references (comparison only)
    H, D = cfg['hc_mult'], cfg['hidden_size']
    embed = [case['embedding'][i] for i in case['ids']]
    l0 = case['layer0']
    layer_case = {'fixture_id': case['fixture_id'] + ':layer0', 'shape': [1, S, H, D], 'hc_sinkhorn_iters': cfg['hc_sinkhorn_iters'],
                  'hc_eps': cfg['hc_eps'], 'rms_norm_eps': cfg['rms_norm_eps'], 'clamp_expected': 'unconstrained',
                  'x': [[[list(e) for _ in range(H)] for e in embed]], 'attn_hc': l0['attn_hc'], 'ffn_hc': l0['ffn_hc'],
                  'linear_config': l0['linear_config'], 'linear_parameters': l0['linear_parameters'], 'ffn': l0['ffn']}
    r0 = refs['layer_run'](layer_case, refs['attention_reference'], refs['accepted_recurrence'], refs['ffn_run'])
    events = r0['attention_cache_events']
    steps = [{'kind': 'prefill', 'tokens': list(range(S0)), 'mask': 'causal', 'ssm_mask': None,
              'logits': [full['logits'][t] for t in range(S0)], 'linear_cache_after': events[S0 - 1],
              'kv_offset_after': S0, 'compiled_ffn_used': False}]
    for t in range(S0, S):
        steps.append({'kind': 'decode', 'tokens': [t], 'mask': None, 'ssm_mask': None, 'logits': [full['logits'][t]],
                      'linear_cache_after': events[t], 'kv_offset_after': t + 1, 'compiled_ffn_used': True})
    final = [[r for r in row] for row in full['logits']]
    return {'steps': steps, 'logits': final, 'final_linear_cache': r0['attention_final_cache'], 'stream_mean': full['pooled'],
            'layer1_topk': full['layer1_topk']}

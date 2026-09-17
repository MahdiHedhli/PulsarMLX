"""Stdlib reference for LanguageModel.sanitize on nested lists: HF checkpoint naming -> model parameters.

Mirrors, at the level of names, shapes and pure data moves, what the pinned
pipenetwork LanguageModel.sanitize does after the container prefix is stripped
(glm5_next.py: model.language_model.X -> X, lm_head.X -> lm_head.X):

    drop keys containing 'mtp.'
    DeepSeek-V3.2 Model.sanitize: drop model.layers.N with N >= num_hidden_layers;
        (fp8 weight_scale_inv dequantisation: not modelled; the fixture has none)
        stack mlp.experts.E.{gate,down,up}_proj.{weight,scales,biases} -> mlp.switch_mlp.*
        split self_attn.kv_b_proj.weight [H*(dq+dv), kvr] -> embed_q [H, kvr, dq] (transposed) and unembed_out [H, dv, kvr]
    rename .hc_attn_ -> .attn_hc. and .hc_ffn_ -> .ffn_hc.
    fuse self_attn.{q,k,v}_conv1d.weight (axis 0, order q,k,v) -> self_attn.conv1d.weight
    move self_attn.{A_log,dt_bias,f_a_proj.weight,f_b_proj.weight} under self_attn.forget_gate.
    conv1d weights of rank 3 whose last axis is not 1: move axis 2 to 1  ((C,1,K) -> (C,K,1))
    parameters ending in FP32_SUFFIXES are float32

Values are nested lists tagged with a dtype; the fixture's bf16 inputs are
bf16-exact so the cast is a value identity.
"""

FP32_SUFFIXES = ('_hc.base', '_hc.scale', 'forget_gate.A_log', 'forget_gate.dt_bias', 'e_score_correction_bias')


def _moveaxis_2_to_1(v):  # (C, A, K) -> (C, K, A)
    return [[[v[c][a][k] for a in range(len(v[c]))] for k in range(len(v[c][0]))] for c in range(len(v))]


def run(checkpoint, cfg):
    w = {e['key']: {'value': e['value'], 'dtype': e['dtype']} for e in checkpoint}
    dropped = [k for k in w if 'mtp.' in k]
    w = {k: v for k, v in w.items() if 'mtp.' not in k}
    L = cfg['num_hidden_layers']
    for k in list(w):
        parts = k.split('.')
        if len(parts) >= 3 and parts[1] == 'layers' and int(parts[2]) >= L:
            dropped.append(k); del w[k]
    for l in range(L):
        prefix = f'model.layers.{l}'
        for m in ('gate_proj', 'down_proj', 'up_proj'):
            for kind in ('weight', 'scales', 'biases'):
                if f'{prefix}.mlp.experts.0.{m}.{kind}' in w:
                    joined = [w.pop(f'{prefix}.mlp.experts.{e}.{m}.{kind}') for e in range(cfg['n_routed_experts'])]
                    w[f'{prefix}.mlp.switch_mlp.{m}.{kind}'] = {'value': [j['value'] for j in joined], 'dtype': joined[0]['dtype']}
        p = f'{prefix}.self_attn'
        if f'{p}.kv_b_proj.weight' in w:
            v = w.pop(f'{p}.kv_b_proj.weight'); dq, dv, H = cfg['qk_nope_head_dim'], cfg['v_head_dim'], cfg['num_attention_heads']
            rows = v['value']; head_dim = dq + dv
            heads = [rows[h * head_dim:(h + 1) * head_dim] for h in range(H)]           # [H][dq+dv][kvr]
            wk = [[[heads[h][d][r] for d in range(dq)] for r in range(len(rows[0]))] for h in range(H)]   # swapaxes -> [H][kvr][dq]
            wv = [[heads[h][dq + d] for d in range(dv)] for h in range(H)]              # [H][dv][kvr]
            w[f'{p}.embed_q.weight'] = {'value': wk, 'dtype': v['dtype']}; w[f'{p}.unembed_out.weight'] = {'value': wv, 'dtype': v['dtype']}
    remapped, conv_parts = {}, {}
    fg_parts = ('A_log', 'dt_bias', 'f_a_proj.weight', 'f_b_proj.weight')
    for k, v in w.items():
        nk = k.replace('.hc_attn_', '.attn_hc.').replace('.hc_ffn_', '.ffn_hc.')
        fused = False
        for part in ('q_conv1d.weight', 'k_conv1d.weight', 'v_conv1d.weight'):
            suffix = '.self_attn.' + part
            if nk.endswith(suffix):
                conv_parts.setdefault(nk[:-len(part)], {})[part[0]] = v; fused = True; break
        if fused:
            continue
        for fp in fg_parts:
            suffix = '.self_attn.' + fp
            if nk.endswith(suffix):
                nk = nk[:-len(fp)] + 'forget_gate.' + fp; break
        remapped[nk] = v
    for prefix, parts in conv_parts.items():
        if all(c in parts for c in 'qkv'):
            remapped[prefix + 'conv1d.weight'] = {'value': parts['q']['value'] + parts['k']['value'] + parts['v']['value'], 'dtype': parts['q']['dtype']}
        else:
            for c, val in parts.items():
                remapped[prefix + c + '_conv1d.weight'] = val
    out = {}
    for k, v in remapped.items():
        value, dtype = v['value'], v['dtype']
        if 'conv1d.weight' in k and isinstance(value[0][0], list) and len(value[0][0]) != 1:
            value = _moveaxis_2_to_1(value)
        if k.endswith(FP32_SUFFIXES) and dtype != 'float32':
            dtype = 'float32'
        out[k] = {'value': value, 'dtype': dtype}
    return {'parameters': out, 'dropped_keys': sorted(dropped)}

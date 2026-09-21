"""Prospectively banked independent scalar dense FFN reference.

No candidate arithmetic or comparison helper imports. Python binary64 math
approximates the retained float32 contract only for this finite fixture matrix.
"""
import math


def _tensor(v, shape):
    if not shape:
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError('ORACLE_NONFINITE_OR_TYPE')
        return
    if type(v) is not list or len(v) != shape[0] or shape[0] <= 0:
        raise ValueError('ORACLE_SHAPE')
    for child in v:
        _tensor(child, shape[1:])


def _dot(a, b):
    if len(a) != len(b) or not a:
        raise ValueError('ORACLE_DOT_SHAPE')
    return sum(a[i] * b[i] for i in range(len(a)))


def _norm(v, eps):
    denom = math.sqrt(sum(y*y for y in v) / len(v) + eps)
    return [y / denom for y in v]


def _sigmoid(v):
    return 1.0 / (1.0 + math.exp(-v))


def run(f):
    B, L, H, D = f['shape']
    I = len(f['gate'])
    for name, shape in {'x':[B,L,H,D], 'fn':[(2+H)*H,H*D],
                        'base':[(2+H)*H], 'scale':[3], 'gate':[I,D],
                        'up':[I,D], 'down':[D,I]}.items():
        _tensor(f[name], shape)
    if type(f['sinkhorn_iters']) is not int or f['sinkhorn_iters'] < 1:
        raise ValueError('ORACLE_ITERATIONS')
    for k in ('hc_eps', 'rms_norm_eps', 'limit'):
        if type(f[k]) not in (int, float) or not math.isfinite(f[k]) or f[k] <= 0:
            raise ValueError('ORACLE_PARAMETER')
    names = ('xc','post','comb','norm','gate','up','activation','mlp','residual','output')
    boundaries = {name: [] for name in names}
    active_count = 0
    eps = f['hc_eps']
    for b in range(B):
        batch = {name: [] for name in names}
        for t in range(L):
            streams = f['x'][b][t]
            flat = [streams[h][d] for h in range(H) for d in range(D)]
            z = _norm(flat, f['rms_norm_eps'])
            mixes = [_dot(w, z) for w in f['fn']]
            pre = [_sigmoid(mixes[h]*f['scale'][0]+f['base'][h])+eps for h in range(H)]
            post = [2*_sigmoid(mixes[H+h]*f['scale'][1]+f['base'][H+h]) for h in range(H)]
            comb = []
            for i in range(H):
                logits = [mixes[2*H+i*H+j]*f['scale'][2]+f['base'][2*H+i*H+j] for j in range(H)]
                peak = max(logits)
                numer = [math.exp(q-peak) for q in logits]
                total = sum(numer)
                comb.append([q/total+eps for q in numer])
            for j in range(H):
                total = sum(comb[i][j] for i in range(H)) + eps
                for i in range(H):
                    comb[i][j] /= total
            for iteration in range(f['sinkhorn_iters']-1):
                for i in range(H):
                    total = sum(comb[i]) + eps
                    comb[i] = [q/total for q in comb[i]]
                for j in range(H):
                    total = sum(comb[i][j] for i in range(H)) + eps
                    for i in range(H):
                        comb[i][j] /= total
            xc = [sum(pre[h]*streams[h][d] for h in range(H)) for d in range(D)]
            norm = _norm(xc, f['rms_norm_eps'])
            gate = [_dot(w,norm) for w in f['gate']]
            up = [_dot(w,norm) for w in f['up']]
            activation = []
            for i in range(I):
                active_count += int(gate[i] > f['limit'] or abs(up[i]) > f['limit'])
                g = min(gate[i], f['limit'])
                u = max(-f['limit'], min(up[i],f['limit']))
                activation.append(g*_sigmoid(g)*u)
            mlp = [_dot(w,activation) for w in f['down']]
            output = [[post[j]*mlp[d]+sum(comb[i][j]*streams[i][d] for i in range(H))
                       for d in range(D)] for j in range(H)]
            values = dict(xc=xc,post=post,comb=comb,norm=norm,gate=gate,up=up,
                          activation=activation,mlp=mlp,residual=streams,output=output)
            for name in names:
                batch[name].append(values[name])
        for name in names:
            boundaries[name].append(batch[name])
    return {'output': boundaries['output'], 'boundaries':boundaries,
            'clamp_active_elements':active_count}

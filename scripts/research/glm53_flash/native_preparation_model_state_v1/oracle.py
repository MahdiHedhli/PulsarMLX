"""MIT. Independent binary64 expectations; only stdlib imports.

KDA uses value-major rows, rebuilding convolution windows from chronological
history. Sparse scores complete pools from raw history, not cached candidate
pool data. Does not import candidate, state, contract, fixtures or their helpers.
"""
import math


def kda(tokens, kernel, initial):
    initial_state, prefix = initial
    rows = [list(c) for c in zip(*initial_state)]  # independent [value,key]
    history = [list(x) for x in prefix]
    results = []
    for raw, a, b in tokens:
        history.append(raw)
        conv = []
        for c in range(7):
            z = math.fsum(history[-3+j][c]*kernel[c][j] for j in range(3))
            conv.append(z/(1+math.exp(-z)))
        q, k, v = conv[:2], conv[2:4], conv[4:]
        q = [x/math.sqrt(math.fsum(y*y for y in q)+1e-6)/math.sqrt(2) for x in q]
        k = [x/math.sqrt(math.fsum(y*y for y in k)+1e-6) for x in k]
        # A_log=.125; dt_bias=(.0625,-.125); lower_bound=-5.
        g = [math.exp(-5/(1+math.exp(-math.exp(.125)*(a[i]+(.0625,-.125)[i])))) for i in range(2)]
        beta = 1/(1+math.exp(-b))
        for j in range(3):
            prior = [rows[j][i]*g[i] for i in range(2)]
            correction = beta*(v[j]-math.fsum(k[i]*prior[i] for i in range(2)))
            rows[j] = [prior[i]+k[i]*correction for i in range(2)]
        results.append(tuple(math.fsum(q[i]*rows[j][i] for i in range(2)) for j in range(3)))
    return tuple(results), tuple(zip(*rows)), tuple(tuple(x) for x in history[-2:])


def sparse(tokens, origin):
    """Recompute each prefix; completed pools win by score, incomplete tail stays."""
    outputs, selections = [], []
    for t in range(len(tokens)):
        full = (t+1)//2
        pool_scores = []
        for p in range(full):
            compressed = []
            for d in range(2):
                exps = [math.exp(tokens[2*p+j][1][d]+((.125,-.25),(.375,.0625))[j][d]) for j in range(2)]
                compressed.append(math.fsum(exps[j]*tokens[2*p+j][0][d] for j in range(2))/sum(exps))
            score = max(0, math.fsum(tokens[t][2][d]*compressed[d] for d in range(2))/math.sqrt(2))*tokens[t][3]
            pool_scores.append(score)
        # Exact ties choose earlier pool only for this toy contract.
        winner = max(range(full), key=lambda p: (pool_scores[p], -p)) if full else None
        indices = ([] if winner is None else [2*winner, 2*winner+1])
        if (t+1) % 2:
            indices.append(t)
        indices.sort()
        logits = [math.fsum(tokens[t][4][d]*tokens[j][5][d] for d in range(3))/math.sqrt(3) for j in indices]
        exps = [math.exp(z-max(logits)) for z in logits]
        outputs.append(tuple(math.fsum(exps[n]*tokens[j][6][d] for n,j in enumerate(indices))/sum(exps) for d in range(3)))
        selections.append(tuple(origin+j for j in indices))
    return tuple(outputs), tuple(selections)


def mhc(case):
    x, fn, scale, base = (case[k] for k in ('streams','fn','scale','base'))
    flat = [v for row in x for v in row]
    denominator = math.sqrt(sum(v*v for v in flat)/12+1e-5)
    mix = [sum(w*v/denominator for w,v in zip(row,flat)) for row in fn]
    pre = [1/(1+math.exp(-(scale[0]*mix[i]+base[i])))+1e-6 for i in range(4)]
    post = [2/(1+math.exp(-(scale[1]*mix[4+i]+base[4+i]))) for i in range(4)]
    comb = []
    for i in range(4):
        z = [scale[2]*mix[8+4*i+j]+base[8+4*i+j] for j in range(4)]
        e = [math.exp(a-max(z)) for a in z]
        comb.append([a/sum(e)+1e-6 for a in e])
    for iteration in range(20):
        if iteration:
            for i in range(4):
                den = sum(comb[i])+1e-6
                comb[i] = [v/den for v in comb[i]]
        for j in range(4):
            den = sum(comb[i][j] for i in range(4))+1e-6
            for i in range(4):
                comb[i][j] /= den
    collapsed = tuple(sum(pre[i]*x[i][d] for i in range(4)) for d in range(3))
    # Scatter contributions from each input stream to each output stream.
    expanded = [[post[j]*case['branch'][d] for d in range(3)] for j in range(4)]
    for i in range(4):
        for j in range(4):
            for d in range(3):
                expanded[j][d] += comb[i][j]*x[i][d]
    return collapsed, tuple(post), tuple(map(tuple,comb)), tuple(map(tuple,expanded))


def route(scores, bias, k):
    remaining = set(range(len(scores)))
    selected = []
    for _ in range(k):
        best = max(remaining, key=lambda i: (scores[i]+bias[i], -i))
        selected.append(best)
        remaining.remove(best)
    den = sum(scores[i] for i in selected) if k > 1 else 1
    return tuple(selected), tuple(2.5*scores[i]/den for i in selected)


def mlp(x, weights):
    gate = [sum(a*b for a,b in zip(x,row)) for row in weights['gate']]
    up = [sum(a*b for a,b in zip(x,row)) for row in weights['up']]
    activation = []
    for g,u in zip(gate,up):
        g = min(10,g)
        activation.append(g/(1+math.exp(-g))*min(10,max(-10,u)))
    return tuple(sum(a*b for a,b in zip(activation,row)) for row in weights['down'])


def boundary(case, streams=None):
    e = tuple(case['embedding'][i] for i in case['ids'])
    residual = tuple(tuple(tuple(row) for _ in range(4)) for row in e) if streams is None else streams
    pooled = [tuple(sum(row[h][d] for h in range(4))/4 for d in range(3)) for row in residual]
    logits = []
    for row in pooled:
        inv = 1/math.sqrt(sum(x*x for x in row)/3+1e-5)
        logits.append(tuple(sum(row[d]*inv*case['norm'][d]*w[d] for d in range(3)) for w in case['head']))
    return e, residual, tuple(logits)

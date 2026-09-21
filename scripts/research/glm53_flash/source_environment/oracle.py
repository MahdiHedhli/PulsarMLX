"""Independent binary64 scalar equations for these bounded synthetic cases."""
import math

def sigmoid(x):
    if x >= 0:
        return 1 / (1 + math.exp(-x))
    z = math.exp(x)
    return z / (1 + z)

def selection(case):
    original = [sigmoid(x) for x in case['gates']]
    corrected = [x + b for x, b in zip(original, case['bias'])]
    groups, keep = case['n_group'], case['topk_group']
    suppressed, margin = [], None
    if groups > 1:
        width = len(corrected) // groups
        gs = [sum(sorted(corrected[g*width:(g+1)*width], reverse=True)[:2]) for g in range(groups)]
        ordered = sorted(range(groups), key=lambda g: gs[g], reverse=True)
        if keep < groups:
            margin = gs[ordered[keep-1]] - gs[ordered[keep]]
        suppressed = ordered[keep:]
        for g in suppressed:
            corrected[g*width:(g+1)*width] = [0.0] * width
    values = sorted(corrected, reverse=True)
    threshold = values[case['top_k']-1]
    required = {i for i, x in enumerate(corrected) if x > threshold}
    eligible = {i for i, x in enumerate(corrected) if x >= threshold}
    gap = values[case['top_k']-1] - values[case['top_k']] if case['top_k'] < len(values) else None
    return original, required, eligible, gap, margin, suppressed

def weights(case, ids):
    vals = [sigmoid(case['gates'][i]) for i in ids]
    denominator = sum(vals) if case['top_k'] > 1 and case['normalize'] else 1.0
    return [x / denominator * case['scale'] for x in vals]

def convolution(x, weights, state=None):
    batches, channels, kernel = len(x), len(weights), len(weights[0])
    if state is None:
        state = [[[0.0] * channels for _ in range(kernel-1)] for _ in range(batches)]
    joined = [s + row for s, row in zip(state, x)]
    raw = [[[sum(joined[b][t+j][c] * weights[c][j][0] for j in range(kernel))
             for c in range(channels)] for t in range(len(x[b]))] for b in range(batches)]
    activated = [[[v * sigmoid(v) for v in row] for row in batch] for batch in raw]
    suffix = [batch[-(kernel-1):] if kernel > 1 else [] for batch in joined]
    return raw, activated, suffix

def expert_values(fixture):
    x = fixture['x']
    outputs = []
    for expert in fixture['projections'][:4]:
        gate = [sum(a*b for a,b in zip(row, x)) for row in expert['gate']]
        up = [sum(a*b for a,b in zip(row, x)) for row in expert['up']]
        hidden = [g * sigmoid(g) * u for g,u in zip(gate, up)]
        outputs.append([sum(a*b for a,b in zip(row, hidden)) for row in expert['down']])
    return outputs

def aggregate(case, ids, experts):
    ws = weights(case, ids)
    result, limits = [], []
    for c in range(len(experts[0])):
        products = [w * experts[i][c] for i,w in zip(ids,ws)]
        result.append(sum(products))
        limits.append(4e-5 * sum(abs(experts[i][c]) for i in ids)
                      + 64 * 2**-24 * max(1, sum(abs(x) for x in products)))
    return result, limits

"""Independent scalar chronological-history reference. No MLX or candidate code."""
import math


def transition(inputs, weights, initial, kernel):
    batch, length, channels = len(inputs), len(inputs[0]), len(inputs[0][0])
    raw, activated, saved = [], [], []
    for b in range(batch):
        history = ([list(row) for row in initial[b]] if initial is not None
                   else [[0.0 for _ in range(channels)] for _ in range(kernel - 1)])
        rb, ab = [], []
        for token in inputs[b]:
            history.append(list(token))
            values = [math.fsum(history[len(history) - kernel + j][c] * weights[c][j][0]
                                for j in range(kernel)) for c in range(channels)]
            rb.append(values)
            ab.append([y / (1.0 + math.exp(-y)) for y in values])
        raw.append(rb)
        activated.append(ab)
        saved.append([list(row) for row in history[-(kernel - 1):]] if kernel > 1 else [])
    dim = channels // 3
    qkv = [[[[row[part * dim:(part + 1) * dim]] for row in stream]
            for stream in activated] for part in range(3)]
    return {'raw': {'shape': [batch, length, channels], 'values': raw},
            'activated': {'shape': [batch, length, channels], 'values': activated},
            'state': {'shape': [batch, kernel - 1, channels], 'values': saved},
            'qkv': [{'shape': [batch, length, 1, dim], 'values': part} for part in qkv]}


def flat(value):
    if isinstance(value, list):
        for item in value:
            yield from flat(item)
    else:
        yield value


def bounded_equal(actual, expected, atol, rtol):
    left, right = list(flat(actual)), list(flat(expected))
    return len(left) == len(right) and all(
        type(a) in (float, int) and math.isfinite(a) and math.isfinite(b)
        and abs(a - b) <= atol + rtol * abs(b) for a, b in zip(left, right))

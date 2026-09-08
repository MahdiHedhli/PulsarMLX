"""MIT. Independently authored tiny f64 candidate, not a model runtime.

Equations/provenance: docs/glm53-flash/tiny-reference-v1/oracle-equations.md.
No oracle import or shared numerical helper. One sequence/head at a time.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RouteResult:
    ids: tuple
    raw_scores: tuple
    corrected_scores: tuple
    weights: tuple


@dataclass(frozen=True)
class SparseResult:
    indices: tuple
    bypassed: bool
    requested: int
    returned: int


@dataclass(frozen=True)
class ConvResult:
    outputs: tuple
    suffix: tuple


@dataclass(frozen=True)
class KdaResult:
    outputs: tuple
    state: tuple
    position: int
    decays: tuple
    betas: tuple


@dataclass(frozen=True)
class MhcResult:
    collapsed: tuple
    pre: tuple
    post: tuple
    comb: tuple
    mixes: tuple


@dataclass(frozen=True)
class MlpWeights:
    gate: tuple
    up: tuple
    down: tuple


@dataclass(frozen=True)
class MlpTrace:
    gate: tuple
    up: tuple
    activated: tuple
    output: tuple


@dataclass(frozen=True)
class CompositionResult:
    output: tuple
    route: RouteResult
    selected_traces: tuple
    shared_trace: MlpTrace
    routed: tuple
    shared: tuple
    branch: tuple


def finite(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("numeric scalar required")
    try:
        y = float(x)
    except OverflowError as e:
        raise ValueError("numeric overflow") from e
    if not math.isfinite(y):
        raise ValueError("nonfinite scalar or intermediate")
    return y


def integer(x, lo, hi):
    if type(x) is not int or not lo <= x <= hi:
        raise ValueError("integer axis/parameter out of scope")
    return x


def vector(x, n=None, maximum=32):
    if not isinstance(x, (tuple, list)) or not 1 <= len(x) <= maximum:
        raise ValueError("invalid vector axis")
    if n is not None and len(x) != n:
        raise ValueError("vector axis mismatch")
    return tuple(map(finite, x))


def matrix(x, rows=None, cols=None, maximum=32):
    if not isinstance(x, (tuple, list)) or not 1 <= len(x) <= maximum:
        raise ValueError("invalid matrix axis")
    if rows is not None and len(x) != rows:
        raise ValueError("matrix row mismatch")
    first = vector(x[0], cols)
    return (first,) + tuple(vector(row, len(first)) for row in x[1:])


def add(*xs):
    try:
        return finite(math.fsum(finite(x) for x in xs))
    except OverflowError as e:
        raise ValueError("sum overflow") from e


def mul(a, b):
    return finite(finite(a) * finite(b))


def dot(a, b):
    if len(a) != len(b):
        raise ValueError("dot axis mismatch")
    return add(*(mul(x, y) for x, y in zip(a, b)))


def sigmoid(x):
    x = finite(x)
    z = math.exp(-abs(x))
    return 1 / (1 + z) if x >= 0 else z / (1 + z)


def exp(x):
    try:
        return finite(math.exp(finite(x)))
    except OverflowError as e:
        raise ValueError("exp overflow") from e


def softmax(xs):
    high = max(xs)
    ex = tuple(exp(add(x, -high)) for x in xs)
    den = add(*ex)
    return tuple(finite(x / den) for x in ex)


def route_scores(scores, correction_bias, top_k, scaling_factor, *, normalize=True):
    raw = vector(scores, maximum=8)
    bias = vector(correction_bias, len(raw), maximum=8)
    integer(top_k, 1, len(raw))
    if type(normalize) is not bool or any(not 0 <= x <= 1 for x in raw):
        raise ValueError("sigmoid score domain required")
    scale = finite(scaling_factor)
    if scale <= 0:
        raise ValueError("positive routing scale required")
    corrected = tuple(add(a, b) for a, b in zip(raw, bias))
    ids = tuple(sorted(range(len(raw)), key=lambda i: (-corrected[i], i))[:top_k])
    den = add(*(raw[i] for i in ids)) if normalize else 1.0
    if den == 0:
        raise ValueError("zero selected routing mass")
    weights = tuple(mul(raw[i] / den, scale) for i in ids)
    return RouteResult(ids, raw, corrected, weights)


def route_tokens(logits, correction_bias, top_k, scaling_factor, *, normalize=True):
    return route_scores(tuple(sigmoid(x) for x in vector(logits, maximum=8)),
                        correction_bias, top_k, scaling_factor, normalize=normalize)


def causal_conv_silu(inputs, kernels, suffix=None):
    xs = matrix(inputs, maximum=16)
    width = len(xs[0])
    coeff = matrix(kernels, rows=width)
    kernel = len(coeff[0])
    integer(kernel, 2, 4)
    history = matrix(suffix, rows=kernel - 1, cols=width) if suffix is not None else ((0.0,) * width,) * (kernel - 1)
    data = history + xs
    outputs = []
    for t in range(len(xs)):
        raw = tuple(dot(tuple(data[t + tap][c] for tap in range(kernel)), coeff[c]) for c in range(width))
        outputs.append(tuple(mul(y, sigmoid(y)) for y in raw))
    return ConvResult(tuple(outputs), data[-(kernel - 1):])


def kda_sequence(q, k, v, a, b, A_log, dt_bias, *, lower_bound=-5.0, state=None, position=0, l2_eps=1e-6):
    qs = matrix(q, maximum=16)
    count, dk = len(qs), len(qs[0])
    ks, vs = matrix(k, count, dk), matrix(v, count)
    aa, bb = matrix(a, count, dk), vector(b, count)
    db = vector(dt_bias, dk)
    integer(position, 0, 16)
    if position + count > 16 or l2_eps != 1e-6 or lower_bound != -5.0:
        raise ValueError("unsupported KDA parameter or sequence budget")
    dv = len(vs[0])
    initial = matrix(state, dk, dv) if state is not None else ((0.0,) * dv,) * dk
    # Candidate stores columns [Dv,Dk], exposing the reference contract [Dk,Dv].
    columns = [list(column) for column in zip(*initial)]
    decay_scale = exp(A_log)
    outs, decays, betas = [], [], []
    for qt, kt, vt, at, bt in zip(qs, ks, vs, aa, bb):
        qden = math.sqrt(add(dot(qt, qt), l2_eps)) * math.sqrt(dk)
        kden = math.sqrt(add(dot(kt, kt), l2_eps))
        nq, nk = tuple(finite(z / qden) for z in qt), tuple(finite(z / kden) for z in kt)
        decay = tuple(exp(mul(lower_bound, sigmoid(mul(decay_scale, add(x, bias))))) for x, bias in zip(at, db))
        beta = sigmoid(bt)
        out = []
        for j in range(dv):
            prior = [mul(columns[j][i], decay[i]) for i in range(dk)]
            delta = mul(add(vt[j], -dot(nk, prior)), beta)
            columns[j] = [add(prior[i], mul(nk[i], delta)) for i in range(dk)]
            out.append(dot(nq, columns[j]))
        outs.append(tuple(out)); decays.append(decay); betas.append(beta)
    return KdaResult(tuple(outs), tuple(tuple(column) for column in zip(*columns)),
                     position + count, tuple(decays), tuple(betas))


def mhc_collapse(streams, fn, scale, base, *, sinkhorn_iters=20, norm_eps=1e-5, hc_eps=1e-6):
    x = matrix(streams, rows=4)
    if sinkhorn_iters != 20 or norm_eps != 1e-5 or hc_eps != 1e-6:
        raise ValueError("unsupported mHC parameters")
    flat = tuple(z for row in x for z in row)
    if len(flat) > 32:
        raise ValueError("flattened feature budget exceeded")
    weights = matrix(fn, 24, len(flat))
    ss, bs = vector(scale, 3), vector(base, 24)
    norm = math.sqrt(add(dot(flat, flat) / len(flat), norm_eps))
    z = tuple(finite(t / norm) for t in flat)
    mixes = tuple(dot(row, z) for row in weights)
    pre = tuple(add(sigmoid(add(mul(mixes[i], ss[0]), bs[i])), hc_eps) for i in range(4))
    post = tuple(mul(2, sigmoid(add(mul(mixes[i+4], ss[1]), bs[i+4]))) for i in range(4))
    comb = [list(add(t, hc_eps) for t in softmax(tuple(add(mul(mixes[8+4*i+j], ss[2]), bs[8+4*i+j]) for j in range(4)))) for i in range(4)]
    for iteration in range(20):
        if iteration:
            comb = [[finite(t / add(*row, hc_eps)) for t in row] for row in comb]
        totals = [add(*(comb[i][j] for i in range(4)), hc_eps) for j in range(4)]
        comb = [[finite(comb[i][j] / totals[j]) for j in range(4)] for i in range(4)]
    collapsed = tuple(dot(pre, column) for column in zip(*x))
    return MhcResult(collapsed, pre, post, tuple(map(tuple, comb)), mixes)


def mhc_expand(branch, streams, post, comb):
    x = matrix(streams, rows=4)
    y, p, c = vector(branch, len(x[0])), vector(post, 4), matrix(comb, 4, 4)
    return tuple(tuple(add(mul(p[j], y[d]), dot(tuple(c[i][j] for i in range(4)), tuple(x[i][d] for i in range(4)))) for d in range(len(y))) for j in range(4))


def clamped_swiglu(gate, up, limit=10.0):
    gg, uu = vector(gate), vector(up, len(gate))
    if finite(limit) != 10.0:
        raise ValueError("unsupported clamp")
    return tuple(mul(mul(min(g, limit), sigmoid(min(g, limit))), max(-limit, min(u, limit))) for g, u in zip(gg, uu))


def clamped_mlp(x, gate_weight, up_weight, down_weight, limit=10.0):
    xx = vector(x)
    gw = matrix(gate_weight, cols=len(xx))
    uw = matrix(up_weight, len(gw), len(xx))
    dw = matrix(down_weight, len(xx), len(gw))
    gate, up = tuple(dot(row, xx) for row in gw), tuple(dot(row, xx) for row in uw)
    active = clamped_swiglu(gate, up, limit)
    return MlpTrace(gate, up, active, tuple(dot(row, active) for row in dw))


def compose_moe_residual(x, residual, logits, correction_bias, experts, shared_expert, top_k, scaling_factor, *, limit=10.0):
    xx, rr = vector(x), vector(residual, len(x))
    if not isinstance(experts, (list, tuple)) or not 1 <= len(experts) <= 8 or len(experts) != len(logits):
        raise ValueError("expert axis mismatch")
    # Validate all supplied expert metadata, including unselected entries.
    for w in (*experts, shared_expert):
        if not isinstance(w, MlpWeights):
            raise ValueError("MlpWeights metadata required")
        gw = matrix(w.gate, cols=len(xx))
        matrix(w.up, len(gw), len(xx)); matrix(w.down, len(xx), len(gw))
    route = route_tokens(logits, correction_bias, top_k, scaling_factor)
    selected = tuple((i, clamped_mlp(xx, experts[i].gate, experts[i].up, experts[i].down, limit)) for i in route.ids)
    routed = tuple(dot(tuple(trace.output[d] for _, trace in selected), route.weights) for d in range(len(xx)))
    shared_trace = clamped_mlp(xx, shared_expert.gate, shared_expert.up, shared_expert.down, limit)
    shared = shared_trace.output
    branch = tuple(add(r, s) for r, s in zip(routed, shared))
    return CompositionResult(tuple(add(r, z) for r, z in zip(rr, branch)), route, selected, shared_trace, routed, shared, branch)


def sparse_select(keys, gates, ape, queries, head_weights, valid, query_position, top_k, pool_size, *, always_tail=True, current_query_valid=True, bypass_short=True):
    kk = matrix(keys, maximum=16)
    length, width = len(kk), len(kk[0])
    gg, qq = matrix(gates, length, width), matrix(queries, cols=width, maximum=4)
    ww = vector(head_weights, len(qq), maximum=4)
    integer(top_k, 1, 16); integer(pool_size, 1, 4); integer(query_position, 0, length - 1)
    if top_k % pool_size or len(valid) != length or any(type(v) is not bool for v in valid):
        raise ValueError("unsupported sparse metadata")
    if any(type(v) is not bool for v in (always_tail, current_query_valid, bypass_short)):
        raise ValueError("boolean sparse policy required")
    aa = matrix(ape, pool_size, width)
    # Current query must agree with the retained token-valid channel.
    current_query_valid = current_query_valid and valid[query_position]
    requested = top_k + (pool_size - 1 if always_tail and pool_size > 1 else 0)
    if bypass_short and length <= top_k:
        return SparseResult(tuple(), True, top_k, 0)
    first = next((i for i, live in enumerate(valid) if live), length)
    if first == length:
        raise ValueError("at least one valid token required")
    # Interior holes are outside the declared contiguous-valid tiny convention.
    if any(not x for x in valid[first:]):
        raise ValueError("interior padding unsupported")
    pools = []
    count = (length + pool_size - 1) // pool_size
    for group in range(count):
        indices = tuple(first + group * pool_size + i for i in range(pool_size))
        available = tuple(i for i in indices if i < length and valid[i])
        full = len(available) == pool_size
        pooled = []
        for d in range(width):
            if not available:
                pooled.append(0.0)
            else:
                probs = softmax(tuple(add(gg[i][d], aa[j][d]) for j, i in enumerate(available)))
                pooled.append(dot(probs, tuple(kk[i][d] for i in available)))
        visible = full and indices[-1] <= query_position
        score = dot(ww, tuple(max(mul(dot(q, pooled), width ** -0.5), 0.0) for q in qq)) * len(qq) ** -0.5
        if visible and finite(score) <= -1e30:
            raise ValueError("visible score conflicts with source mask sentinel")
        pools.append((finite(score) if visible else -1e30, indices, visible))
    order = sorted(range(count), key=lambda i: (-pools[i][0], i))[:min(top_k // pool_size, count)]
    selected = [index if pools[i][2] else -1 for i in order for index in pools[i][1]]
    if always_tail and pool_size > 1:
        visible_count = sum(valid[i] for i in range(query_position + 1))
        tail_count = visible_count % pool_size
        start = first + visible_count - tail_count
        selected.extend(start + j if j < tail_count and start + j <= query_position else -1 for j in range(pool_size - 1))
    selected.extend([-1] * max(0, requested - len(selected)))
    indices = tuple(selected[:requested]) if current_query_valid else (-1,) * requested
    return SparseResult(indices, False, top_k, sum(i >= 0 for i in indices))

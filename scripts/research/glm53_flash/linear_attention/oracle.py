"""Stdlib binary64 module reference and prospective FP32 error propagation.

No MLX or candidate imports. Dense weights are [out,in], depthwise weights
[channel,kernel,1]; state is [B,H,value,key]. Inputs and weights are exact
FP32 dyadics. Values below are binary64 expectations, never candidate-rounded
answers. Error radii include FP32 working arithmetic and transcendentals.
"""
import copy
import math
import struct

U = 2.0**-24
ATOL, RTOL = 1e-4, 1e-5


class InputError(ValueError):
    pass


def shape(x):
    if not isinstance(x, list):
        return ()
    if not x:
        return (0,)
    child = shape(x[0])
    if any(shape(v) != child for v in x):
        raise InputError('RAGGED')
    return (len(x),) + child


def flat(x):
    if isinstance(x, list):
        for v in x:
            yield from flat(v)
    else:
        yield x


def zeros(dims):
    return [zeros(dims[1:]) for _ in range(dims[0])] if dims else 0.0


def mapping(x, fn):
    return [mapping(v, fn) for v in x] if isinstance(x, list) else fn(x)


def gamma(n):
    return n * U / (1 - n * U)


class Ball:
    """Absolute forward error; reduction order is bounded by gamma(n).

    Standard finite FP32 arithmetic is assumed. exp/rsqrt relative working
    error <=2e-6 and sigmoid/softplus absolute working error <=2e-6 on the
    recorded bounded domains are explicit assumptions, not driver attestation.
    Subnormal terms have a 1e-37 absolute floor; exact zero products stay zero.
    """
    def __init__(self, v, e=0.0):
        self.v, self.e = float(v), float(e)

    def __add__(self, other):
        other = as_ball(other)
        v = self.v + other.v
        e = self.e + other.e
        return Ball(v, e + gamma(1) * (abs(self.v) + abs(other.v) + e) + 1e-37)

    __radd__ = __add__

    def __neg__(self):
        return Ball(-self.v, self.e)

    def __sub__(self, other):
        return self + -as_ball(other)

    def __mul__(self, other):
        other = as_ball(other)
        if (self.v == 0 and self.e == 0) or (other.v == 0 and other.e == 0):
            return Ball(0)
        v = self.v * other.v
        e = abs(self.v) * other.e + abs(other.v) * self.e + self.e * other.e
        return Ball(v, e + gamma(1) * (abs(v) + e) + 1e-37)

    __rmul__ = __mul__


def as_ball(x):
    return x if isinstance(x, Ball) else Ball(x, abs(float(x)-struct.unpack('f',struct.pack('f',x))[0]))


def total(xs):
    xs = list(map(as_ball, xs))
    v = math.fsum(x.v for x in xs)
    e = math.fsum(x.e for x in xs)
    return Ball(v, e + gamma(len(xs)) * (math.fsum(abs(x.v) for x in xs) + e) + 1e-37)


def sigmoid(x):
    x = as_ball(x)
    return Ball(1 / (1 + math.exp(-x.v)), .25 * x.e + 2e-6)


def exponential(x):
    x = as_ball(x)
    return Ball(math.exp(x.v), math.exp(x.v) * math.expm1(x.e) + 2e-6 * math.exp(x.v + x.e))


def softplus(x):
    x = as_ball(x)
    return Ball(math.log1p(math.exp(x.v)), x.e + 2e-6)


def rsqrt(x):
    x = as_ball(x)
    if x.v - x.e <= 0:
        raise InputError('NORMALIZATION_INTERVAL_NOT_POSITIVE')
    v = x.v**-.5
    return Ball(v, max(abs((x.v - x.e)**-.5 - v), abs((x.v + x.e)**-.5 - v))
                + 2e-6 * (x.v - x.e)**-.5)


def dense(x, weight):
    return [total(a * w for a, w in zip(x, row)) for row in weight]


def parameter_shapes(config):
    I, H, D, K = (config[k] for k in ('hidden_size', 'linear_num_heads', 'linear_head_dim', 'linear_conv_kernel_dim'))
    Q = H * D
    return {'q_proj.weight': (Q, I), 'k_proj.weight': (Q, I), 'v_proj.weight': (Q, I),
            'conv1d.weight': (3 * Q, K, 1), 'forget_gate.f_a_proj.weight': (D, I),
            'forget_gate.f_b_proj.weight': (Q, D), 'forget_gate.dt_bias': (Q,),
            'forget_gate.A_log': (H,), 'b_proj.weight': (H, I),
            'g_a_proj.weight': (D, I), 'g_b_proj.weight': (Q, D),
            'o_norm.weight': (D,), 'o_proj.weight': (I, Q)}


def validate(case):
    cfg = case['config']
    expected_fields = {'hidden_size', 'linear_num_heads', 'linear_head_dim',
                       'linear_conv_kernel_dim', 'linear_lower_bound', 'rms_norm_eps'}
    if set(cfg) != expected_fields:
        raise InputError('CONFIG_FIELDS')
    B, S = case['B'], case['S']
    I, H, D, K = (cfg[k] for k in ('hidden_size', 'linear_num_heads', 'linear_head_dim', 'linear_conv_kernel_dim'))
    if (any(type(v) is not int for v in (B, S, I, H, D, K)) or B not in (1, 2)
            or not 1 <= S <= 5 or I not in (4, 8) or H not in (1, 2) or D != 32 or K not in (2, 3)
            or cfg['linear_lower_bound'] not in (None, -2.) or cfg['rms_norm_eps'] != 1e-6):
        raise InputError('FINITE_DOMAIN')
    shapes = parameter_shapes(cfg)
    if set(case['parameters']) != set(shapes):
        raise InputError('PARAMETER_CENSUS')
    for key, dims in shapes.items():
        value = case['parameters'][key]
        if shape(value) != dims:
            raise InputError('PARAMETER_SHAPE:' + key)
        for v in flat(value):
            if type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1 or struct.unpack('f', struct.pack('f', v))[0] != v:
                raise InputError('PARAMETER_FP32_DYADIC:' + key)
    if shape(case['inputs']) != (B, S, I) or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1 for v in flat(case['inputs'])):
        raise InputError('INPUT_SHAPE_OR_RANGE')
    for value in (case['inputs'],case['cache0'],case['cache1']):
        if value is not None and any(type(v) not in (int,float) or not math.isfinite(v) or struct.unpack('f',struct.pack('f',v))[0]!=v for v in flat(value)):
            raise InputError('EXTERNAL_FP32_DYADIC')
    for key, dims in [('cache0', (B, K - 1, 3 * H * D)), ('cache1', (B, H, D, D))]:
        value = case[key]
        if value is not None and (shape(value) != dims or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1 for v in flat(value))):
            raise InputError('CACHE_SHAPE_OR_RANGE')
    mask = case['mask']
    if mask is not None and (shape(mask) != (B, S) or any(type(v) is not bool for v in flat(mask))):
        raise InputError('MASK_SHAPE_OR_TYPE')
    if any(type(n) is not int or n < 1 for n in case['parts']) or sum(case['parts']) != S:
        raise InputError('PARTITION')
    return B, S, I, H, D, K


def module_reference(case, accepted_recurrence):
    """Compute all outputs and both caches before candidate observation.

    The reviewed Dv8 recurrence is called at its unchanged interface in four
    independent value-row blocks. Its equations have no cross-value-row edge.
    The parallel Ball recurrence propagates radii; its values must agree with
    that accepted reference, preventing a new silently substituted recurrence.
    """
    B, S, I, H, D, K = validate(case)
    Q = H * D
    p = {k: mapping(v, as_ball) for k, v in case['parameters'].items()}
    inputs = mapping(case['inputs'], as_ball)
    hist = mapping(case['cache0'] if case['cache0'] is not None else zeros((B, K-1, 3*Q)), as_ball)
    state = mapping(case['cache1'] if case['cache1'] is not None else zeros((B, H, D, D)), as_ball)
    output, events, conditioning = [[] for _ in range(B)], [], []
    normalizer_min, normalizer_max = math.inf, 0.
    for t in range(S):
        q_all, k_all, v_all, a_all, b_all, gate_all = [], [], [], [], [], []
        mixes, raw_conv = [], []
        for b in range(B):
            x = inputs[b][t]
            segments = [dense(x, p[key + '.weight']) for key in ('q_proj', 'k_proj', 'v_proj')]
            mixed = sum(segments, [])
            if case['mask'] is not None and not case['mask'][b][t]:
                mixed = [Ball(0) for _ in mixed]
            mixes.append(mixed)
            window = hist[b] + [mixed]
            z = [total(window[j][c] * p['conv1d.weight'][c][j][0] for j in range(K)) for c in range(3*Q)]
            raw_conv.append(z)
            conv = [v * sigmoid(v) for v in z]
            hist[b] = window[-(K-1):]
            q, k, v = [conv[j*Q:(j+1)*Q] for j in range(3)]
            qs, ks, vs = [], [], []
            for h in range(H):
                qq, kk, vv = q[h*D:(h+1)*D], k[h*D:(h+1)*D], v[h*D:(h+1)*D]
                qn, kn = total(x*x for x in qq) + 1e-6, total(x*x for x in kk) + 1e-6
                conditioning.extend([qn.v-qn.e, kn.v-kn.e])
                qs.append([x * rsqrt(qn) * D**-.5 for x in qq])
                ks.append([x * rsqrt(kn) for x in kk]); vs.append(vv)
            fa = dense(x, p['forget_gate.f_a_proj.weight'])
            av = dense(fa, p['forget_gate.f_b_proj.weight'])
            gv = dense(dense(x, p['g_a_proj.weight']), p['g_b_proj.weight'])
            q_all.append(qs); k_all.append(ks); v_all.append(vs)
            a_all.append([av[h*D:(h+1)*D] for h in range(H)])
            b_all.append(dense(x, p['b_proj.weight']))
            gate_all.append([gv[h*D:(h+1)*D] for h in range(H)])
        prior_values = mapping(state, lambda x: x.v)
        recur_y = zeros((B, H, D))
        for b in range(B):
            for h in range(H):
                beta = sigmoid(b_all[b][h])
                gs = []
                for j in range(D):
                    z = a_all[b][h][j] + p['forget_gate.dt_bias'][h*D+j]
                    scale = exponential(p['forget_gate.A_log'][h])
                    g = exponential(-scale * softplus(z)) if case['config']['linear_lower_bound'] is None else exponential(-2. * sigmoid(scale*z))
                    gs.append(g)
                for row in range(D):
                    decayed = [state[b][h][row][j] * gs[j] for j in range(D)]
                    residual = v_all[b][h][row] - total(decayed[j] * k_all[b][h][j] for j in range(D))
                    delta = beta * residual
                    state[b][h][row] = [decayed[j] + k_all[b][h][j]*delta for j in range(D)]
                    recur_y[b][h][row] = total(state[b][h][row][j]*q_all[b][h][j] for j in range(D))
        block_outputs, block_states = [], []
        for block in range(4):
            r = {'B': B, 'T': 1, 'Hk': H, 'Hv': H, 'Dk': D, 'Dv': 8, 'gate': 'vector',
                 'lower_bound': case['config']['linear_lower_bound'], 'mask': None,
                 'q': [[mapping(q_all[b], lambda x:x.v)] for b in range(B)],
                 'k': [[mapping(k_all[b], lambda x:x.v)] for b in range(B)],
                 'v': [[[mapping(v_all[b][h][block*8:(block+1)*8], lambda x:x.v) for h in range(H)]] for b in range(B)],
                 'a': [[mapping(a_all[b], lambda x:x.v)] for b in range(B)],
                 'b': [[mapping(b_all[b], lambda x:x.v)] for b in range(B)],
                 'A_log': [[v] for v in case['parameters']['forget_gate.A_log']],
                 'dt_bias': [case['parameters']['forget_gate.dt_bias'][h*D:(h+1)*D] for h in range(H)]}
            initial = [[prior_values[b][h][block*8:(block+1)*8] for h in range(H)] for b in range(B)]
            result = accepted_recurrence.ops_transition(r, initial)
            block_outputs.append(result['output']); block_states.append(result['state'])
        accepted_y = [[sum([block_outputs[z][b][0][h] for z in range(4)], []) for h in range(H)] for b in range(B)]
        accepted_state = [[sum([block_states[z][b][h] for z in range(4)], []) for h in range(H)] for b in range(B)]
        assert close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13)
        assert close(mapping(state, lambda x:x.v), accepted_state, 1e-14, 1e-13)
        for b in range(B):
            normed = []
            for h in range(H):
                denom = total(x*x for x in recur_y[b][h]) * (1/D) + case['config']['rms_norm_eps']
                normalizer_min = min(normalizer_min, denom.v-denom.e)
                normalizer_max = max(normalizer_max, denom.v+denom.e)
                conditioning.append(denom.v-denom.e)
                inv = rsqrt(denom)
                normed.extend([recur_y[b][h][j] * inv * p['o_norm.weight'][j] * sigmoid(gate_all[b][h][j]) for j in range(D)])
            output[b].append(dense(normed, p['o_proj.weight']))
        events.append({'time': t, 'cache0': mapping(hist, lambda x:x.v), 'cache1': mapping(state, lambda x:x.v),
                       'output': [[mapping(output[b][-1], lambda x:x.v)] for b in range(B)],
                       'radii': {'cache0': max(x.e for x in flat(hist)), 'cache1': max(x.e for x in flat(state)),
                                 'output': max(x.e for b in range(B) for x in output[b][-1])},
                       'anchor': {'mixed_b0_c0': mixes[0][0].v, 'convolution_b0_c0': raw_conv[0][0].v}})
    maxima = {key: max(e['radii'][key] for e in events) for key in ('output','cache0','cache1')}
    if min(conditioning) <= 0 or any(v > ATOL for v in maxima.values()):
        raise InputError('PROSPECTIVE_ERROR_CEILING:' + repr(maxima))
    return {'output': mapping(output, lambda x:x.v), 'cache0': mapping(hist, lambda x:x.v),
            'cache1': mapping(state, lambda x:x.v), 'events': events, 'maximum_radii': maxima,
            'conditioning': {'minimum_squared_norm_interval': min(conditioning),
                             'RMS_denominator_minimum': normalizer_min, 'RMS_denominator_maximum': normalizer_max},
            'accepted_recurrence_block_crosscheck': 'PASS; unchanged Dv8 interface, four independent value-row blocks'}


def close(a, e, atol=ATOL, rtol=RTOL):
    return shape(a) == shape(e) and all(type(x) in (int,float) and math.isfinite(x) and abs(x-y) <= atol+rtol*abs(y) for x,y in zip(flat(a),flat(e)))

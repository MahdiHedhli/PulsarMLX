"""Independent binary64 scalar/list recurrence; imports no candidate or MLX.

Inputs are exactly representable dyadic FP32 values. Transcendentals and
math.fsum use Python binary64; no simulated candidate rounding supplies the
expected answers. Each step retains its mathematical inputs and both states.
"""
import copy
import math


class InputError(ValueError):
    pass


def shape(x):
    if not isinstance(x, list):
        return ()
    if not x:
        return (0,)
    inner = shape(x[0])
    if any(shape(v) != inner for v in x):
        raise InputError('RAGGED_INPUT')
    return (len(x),) + inner


def flat(x):
    if isinstance(x, list):
        for v in x:
            yield from flat(v)
    else:
        yield x


def zeros(dims):
    return [zeros(dims[1:]) for _ in range(dims[0])] if dims else 0.0


def validate(case, state):
    B, T, Hk, Hv, Dk, Dv = (case[k] for k in ('B', 'T', 'Hk', 'Hv', 'Dk', 'Dv'))
    if (any(type(n) is not int for n in (B, T, Hk, Hv, Dk, Dv))
            or not (1 <= B <= 2 and 1 <= T <= 7 and 1 <= Hk <= 2
                    and 1 <= Hv <= 4 and Hv % Hk == 0 and 1 <= Dk <= 4 and 1 <= Dv <= 4)):
        raise InputError('DOMAIN_SHAPE')
    vector = case['gate'] == 'vector'
    expected = {'q': (B, T, Hk, Dk), 'k': (B, T, Hk, Dk), 'v': (B, T, Hv, Dv),
                'a': (B, T, Hv, Dk) if vector else (B, T, Hv), 'b': (B, T, Hv),
                'A_log': (Hv, 1) if vector else (Hv,), 'dt_bias': (Hv, Dk) if vector else (Hv,)}
    for key, dims in expected.items():
        value = case[key]
        if shape(value) != dims:
            raise InputError('INPUT_SHAPE:' + key)
        bound = {'q': .5, 'k': .5, 'v': .75, 'a': .5, 'b': .5, 'A_log': .25, 'dt_bias': .25}[key]
        for number in flat(value):
            if type(number) not in (int, float) or not math.isfinite(number):
                raise InputError('INPUT_NONFINITE:' + key)
            if abs(number) > bound:
                raise InputError('INPUT_RANGE:' + key)
    if state is not None:
        if shape(state) != (B, Hv, Dv, Dk):
            raise InputError('STATE_SHAPE')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in flat(state)):
            raise InputError('STATE_NONFINITE')
        if any(abs(v) > 8 for v in flat(state)):
            raise InputError('STATE_RANGE')
    mask = case.get('mask')
    if mask is not None and (shape(mask) != (B, T) or any(type(v) is not bool for v in flat(mask))):
        raise InputError('MASK_SHAPE_OR_TYPE')
    if case['lower_bound'] not in (None, -2.0):
        raise InputError('GATE_BOUND')
    return B, T, Hk, Hv, Dk, Dv


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def gate(log_scale, value, bias, lower_bound):
    z = value + bias
    scale = math.exp(log_scale)
    return (math.exp(-scale * math.log1p(math.exp(z))) if lower_bound is None
            else math.exp(lower_bound * sigmoid(scale * z)))


def transition(case, initial_state=None):
    B, T, Hk, Hv, Dk, Dv = validate(case, initial_state)
    state = zeros((B, Hv, Dv, Dk)) if initial_state is None else copy.deepcopy(initial_state)
    output = zeros((B, T, Hv, Dv)); traces = []
    all_g = zeros((B, T, Hv, Dk) if case['gate'] == 'vector' else (B, T, Hv))
    all_beta = zeros((B, T, Hv)); repeat = Hv // Hk
    for time in range(T):
        prior = copy.deepcopy(state); proposed = zeros((B, Hv, Dv, Dk))
        step_y = zeros((B, Hv, Dv)); step_g = zeros((B, Hv, Dk) if case['gate'] == 'vector' else (B, Hv))
        step_beta = zeros((B, Hv))
        for batch in range(B):
            for head in range(Hv):
                kh = head // repeat
                query = case['q'][batch][time][kh]; key = case['k'][batch][time][kh]
                value = case['v'][batch][time][head]; beta = sigmoid(case['b'][batch][time][head])
                if case['gate'] == 'vector':
                    gs = [gate(case['A_log'][head][0], case['a'][batch][time][head][j],
                               case['dt_bias'][head][j], case['lower_bound']) for j in range(Dk)]
                    step_g[batch][head] = list(gs); all_g[batch][time][head] = list(gs)
                else:
                    scalar = gate(case['A_log'][head], case['a'][batch][time][head],
                                  case['dt_bias'][head], case['lower_bound'])
                    gs = [scalar for _ in range(Dk)]
                    step_g[batch][head] = scalar; all_g[batch][time][head] = scalar
                step_beta[batch][head] = beta; all_beta[batch][time][head] = beta
                for row in range(Dv):
                    decayed = [prior[batch][head][row][j] * gs[j] for j in range(Dk)]
                    projection = math.fsum(decayed[j] * key[j] for j in range(Dk))
                    correction = beta * (value[row] - projection)
                    updated = [decayed[j] + key[j] * correction for j in range(Dk)]
                    proposed[batch][head][row] = updated
                    projected = math.fsum(updated[j] * query[j] for j in range(Dk))
                    output[batch][time][head][row] = projected; step_y[batch][head][row] = projected
        for batch in range(B):
            active = case.get('mask') is None or case['mask'][batch][time]
            state[batch] = copy.deepcopy(proposed[batch] if active else prior[batch])
        traces.append({'time': time, 'q': [case['q'][b][time] for b in range(B)],
                       'k': [case['k'][b][time] for b in range(B)], 'v': [case['v'][b][time] for b in range(B)],
                       'g': step_g, 'beta': step_beta, 'prior_state': prior, 'computed_state': proposed,
                       'output': step_y, 'new_state': copy.deepcopy(state),
                       'mask': None if case.get('mask') is None else [case['mask'][b][time] for b in range(B)]})
    return {'output': output, 'state': state, 'g': all_g, 'beta': all_beta, 'traces': traces}


def chunk(case, start, length):
    value = copy.deepcopy(case); value['T'] = length
    for key in ('q', 'k', 'v', 'a', 'b', 'mask'):
        if value.get(key) is not None:
            value[key] = [row[start:start + length] for row in value[key]]
    return value


def close(actual, expected, atol, rtol):
    return (shape(actual) == shape(expected)
            and all(type(a) in (int, float) and math.isfinite(a) and abs(a - e) <= atol + rtol * abs(e)
                    for a, e in zip(flat(actual), flat(expected))))


def fp32_budget(case, expected):
    """Prospective conservative error propagation, not an MLX accuracy proof.

    Working finite-domain absolute gate error 2e-6, beta error 1e-6;
    arithmetic unit roundoff 2^-24 and gamma(2*Dk+4) account for
    products/sums. Carry state error through decay, projection, residual,
    outer update and output projection; a false mask retains prior error.
    """
    B, T, Hk, Hv, Dk, Dv = validate(case, case['state'])
    errors = zeros((B, Hv, Dv, Dk)); bounds = []; eps = 2**-24
    gamma = ((2 * Dk + 4) * eps) / (1 - (2 * Dk + 4) * eps)
    for tr in expected['traces']:
        previous = copy.deepcopy(errors); new_errors = zeros((B, Hv, Dv, Dk)); yerr = []
        for b in range(B):
            for h in range(Hv):
                kh = h // (Hv // Hk); q = tr['q'][b][kh]; k = tr['k'][b][kh]
                gs = tr['g'][b][h] if case['gate'] == 'vector' else [tr['g'][b][h]] * Dk
                beta = tr['beta'][b][h]
                for row in range(Dv):
                    prior = tr['prior_state'][b][h][row]
                    de = [abs(gs[j]) * previous[b][h][row][j] + 2e-6 * (abs(prior[j]) + previous[b][h][row][j])
                          + gamma * (abs(prior[j]) + previous[b][h][row][j]) * (abs(gs[j]) + 2e-6) for j in range(Dk)]
                    dot_abs = math.fsum(abs(prior[j] * gs[j] * k[j]) for j in range(Dk))
                    dot_err = math.fsum(abs(k[j]) * de[j] for j in range(Dk)) + gamma * (dot_abs + math.fsum(de))
                    residual_abs = abs(tr['v'][b][h][row]) + dot_abs
                    re = (abs(beta) + 1e-6) * dot_err + 1e-6 * residual_abs + gamma * (residual_abs + dot_err)
                    se = [de[j] + abs(k[j]) * re + gamma * (abs(tr['computed_state'][b][h][row][j]) + de[j] + abs(k[j]) * re) for j in range(Dk)]
                    new_errors[b][h][row] = se
                    yerr.append(math.fsum(abs(q[j]) * se[j] for j in range(Dk)) + gamma * math.fsum(abs(q[j] * tr['computed_state'][b][h][row][j]) for j in range(Dk)))
        for b in range(B):
            errors[b] = new_errors[b] if tr['mask'] is None or tr['mask'][b] else previous[b]
        bounds.append({'time': tr['time'], 'state_absolute_budget': max(flat(errors)), 'output_absolute_budget': max(yerr)})
    return bounds

#!/usr/bin/env python3
"""Independent analytic synthetic proof. Does not import fixture/native code.

Closed form proof is host design evidence, not candidate qualification.
"""
from fractions import Fraction as F
import json

def exact_bf16(value):
    value = F(value)
    n = abs(value.numerator)
    while n and n % 2 == 0:
        n //= 2
    if n.bit_length() > 8 or value.denominator & value.denominator - 1:
        raise ValueError('synthetic metadata not exact BF16')
    if value and (not F(1, 2 ** 32) <= abs(value) <= 2 ** 32):
        raise ValueError('synthetic metadata outside domain')
from f020_expert_mlp_r1_v1 import activation

def input_exact():
    return [F(2 + (-1) ** bin(j).count('1'), 4096) for j in range(4096)]

def gamma(k):
    if k not in (2048, 4096):
        raise ValueError('scoped full geometry only')
    n = k // 16 + 17
    return F(n, 2 ** 24 - n)

def projection(t, sign):
    """Every code occurs four times/group; parity cancels across high bits.

    Row L1=2 and input is positive. sum x*q=15 for every rotation.
    """
    s, b = (F(sign, 16), F(t, 2) - F(sign * 15, 32))
    exact_bf16(s)
    exact_bf16(b)
    value = 15 * s + 2 * b
    phi = 15 * abs(s) + 2 * abs(b)
    if not value == t:
        raise ValueError('synthetic proof predicate: value == t')
    return (value, gamma(4096) * phi, b)

def prove():
    x = input_exact()
    if not sum(x) == 2:
        raise ValueError('synthetic proof predicate: sum(x) == 2')
    for start in range(0, 4096, 64):
        if not sum(x[start:start + 64]) == F(1, 32):
            raise ValueError('synthetic proof predicate: sum(x[start:start + 64]) == F(1, 32)')
    for offset in range(16):
        for start in range(0, 4096, 64):
            if not sum((v * ((j + offset) % 16) for j, v in enumerate(x[start:start + 64]))) == F(15, 64):
                raise ValueError('synthetic proof predicate: sum((v * ((j + offset) % 16) for j, v in enumerate(x[start:start + 64]))) == F(15, 64)')
        if not sum((v * ((j + offset) % 16) for j, v in enumerate(x))) == 15:
            raise ValueError('synthetic proof predicate: sum((v * ((j + offset) % 16) for j, v in enumerate(x))) == 15')
    cases = {'A': ((1, 2), (4, -3), (12, 12), (2, -12)), 'B': ((2, 1), (3, -4), (12, -12), (4, 12))}
    report = {}
    for name, targets in cases.items():
        sign = 1 if name == 'A' else -1
        hidden, budgets, witnesses = ([], [], [])
        for gt, ut in targets:
            g, bg, gb = projection(gt, sign)
            u, bu, ub = projection(ut, sign)
            if not -16 <= g - bg <= g + bg <= 16:
                raise ValueError('synthetic proof predicate: -16 <= g - bg <= g + bg <= 16')
            if not -16 <= u - bu <= u + bu <= 16:
                raise ValueError('synthetic proof predicate: -16 <= u - bu <= u + bu <= 16')
            lo, hi = activation(g, u)
            bh = 20 * bg + 10 * bu + F(1, 128)
            if not hi - lo <= F(1, 2 ** 160):
                raise ValueError('synthetic proof predicate: hi - lo <= F(1, 2 ** 160)')
            if not (lo - bh >= F(1, 2 ** 32) or hi + bh <= -F(1, 2 ** 32)):
                raise ValueError('synthetic proof predicate: lo - bh >= F(1, 2 ** 32) or hi + bh <= -F(1, 2 ** 32)')
            if not max(abs(lo - bh), abs(hi + bh)) <= 2 ** 32:
                raise ValueError('synthetic proof predicate: max(abs(lo - bh), abs(hi + bh)) <= 2 ** 32')
            omitted_bias_budget = gamma(4096) * F(15, 16)
            if not (abs(2 * gb) > bg + omitted_bias_budget and abs(2 * ub) > bu + omitted_bias_budget):
                raise ValueError('synthetic proof predicate: abs(2 * gb) > bg + omitted_bias_budget and abs(2 * ub) > bu + omitted_bias_budget')
            sl, sh = activation(u, g)
            swap_gap = max(F(0), lo - sh, sl - hi)
            mutant_bh = 20 * bu + 10 * bg + F(1, 128)
            witnesses.append(swap_gap > bh + mutant_bh)
            hidden.append((lo, hi))
            budgets.append(bh)
        if not any(witnesses):
            raise ValueError('synthetic proof predicate: any(witnesses)')
        if not 512 * sum((max(abs(lo - b), abs(hi + b)) for (lo, hi), b in zip(hidden, budgets))) <= 2 ** 40:
            raise ValueError('synthetic proof predicate: 512 * sum((max(abs(lo - b), abs(hi + b)) for (lo, hi), b in zip(hidden, budgets))) <= 2 ** 40')
        output_lower_abs = []
        for offset in range(16):
            yl = yh = propagated = F(0)
            for j in range(16):
                w = sign * (F((j + offset) % 16, 4096) + F(1, 8192))
                lo, hi = hidden[j % 4]
                yl += min(w * lo, w * hi) * 128
                yh += max(w * lo, w * hi) * 128
                propagated += abs(w) * budgets[j % 4] * 128
            if not (yl > 0 or yh < 0):
                raise ValueError('synthetic proof predicate: yl > 0 or yh < 0')
            output_lower_abs.append(min(abs(yl), abs(yh)))
        report[name] = {'hidden_patterns': 4, 'hidden_lanes': 2048, 'output_rows': 4096, 'gate_up_swap_witnesses': sum(witnesses), 'min_output_abs_lower_bound': str(min(output_lower_abs)), 'max_Bh': str(max(budgets))}
    word = 1985229328
    normal = [word >> 4 * j & 15 for j in range(8)]
    reversed_nibbles = [word >> 4 * (7 - j) & 15 for j in range(8)]
    basis = [1] + [0] * 7
    if not sum((a * b for a, b in zip(normal, basis))) == 0:
        raise ValueError('synthetic proof predicate: sum((a * b for a, b in zip(normal, basis))) == 0')
    if not sum((a * b for a, b in zip(reversed_nibbles, basis))) == 7:
        raise ValueError('synthetic proof predicate: sum((a * b for a, b in zip(reversed_nibbles, basis))) == 7')
    return {'status': 'PASS', 'scope': 'analytic synthetic design only', 'cases': report, 'real_payload_bytes_read': 0, 'native_calls': 0}
if __name__ == '__main__':
    print(json.dumps(prove(), indent=2))

"""Stdlib reference for MLX affine-quantized projections over frozen quantized arrays.

Format (mlx affine mode): along the last (input) axis, groups of `group_size`
elements share a float32 scale s and bias b; each element's code q (bits wide)
is packed little-endian into uint32 words, 32/bits codes per word, code i of a
row in bits [bits*(i mod per_word), bits*(i mod per_word + 1)) of word
i // per_word; the element value is q*s + b.

    dequantize(words, scales, biases) -> W [rows][in]
    switch experts: per token t and selected expert e: gate = x W_g^T, up = x W_u^T,
                    act = clamped_swiglu(up, gate, limit) (MoE reference), out = act W_d^T
    multilinear:    transpose True: x W_h^T ; False: x W_h

binary64 with math.fsum; no candidate arithmetic.
"""
import math

from scripts.research.glm53_flash.decoder_moe import oracle as moe


def unpack(words, bits):
    per_word, mask = 32 // bits, (1 << bits) - 1
    return [(w >> (bits * j)) & mask for w in words for j in range(per_word)]


def dequantize(q, bits, group_size):
    """q: {'words': [rows][in/per_word] ints, 'scales': [rows][in/group_size], 'biases': same}."""
    out = []
    for words, scales, biases in zip(q['words'], q['scales'], q['biases']):
        codes = unpack(words, bits)
        out.append([c * scales[i // group_size] + biases[i // group_size] for i, c in enumerate(codes)])
    return out


def _proj(x, w):
    return [math.fsum(a * b for a, b in zip(row, x)) for row in w]


def switch_experts(case):
    cfg = case['config']; bits, g = cfg['bits'], cfg['group_size']
    W = {p: [dequantize(e, bits, g) for e in case['quantized'][p]] for p in ('gate', 'up', 'down')}
    tokens = []
    for x, inds in zip(case['x'], case['indices']):
        experts = []
        for e in inds:
            gate, up = _proj(x, W['gate'][e]), _proj(x, W['up'][e])
            act, active = moe.clamped_swiglu(up, gate, cfg['swiglu_limit'])
            experts.append({'expert': e, 'gate': gate, 'up': up, 'clamp_active': active, 'output': _proj(act, W['down'][e])})
        tokens.append(experts)
    return {'tokens': tokens}


def multilinear(case):
    cfg = case['config']; bits, g = cfg['bits'], cfg['group_size']
    W = [dequantize(h, bits, g) for h in case['quantized']['weight']]          # [H][out][in]
    t = [[_proj(x, Wh) for x in case['x_transpose']] for Wh in W]             # x [S][in] -> [H][S][out]
    n = [[[math.fsum(x[o] * Wh[o][i] for o in range(len(Wh))) for i in range(len(Wh[0]))] for x in case['x_no_transpose']] for Wh in W]  # x [S][out] -> [H][S][in]
    return {'transpose': t, 'no_transpose': n}


def quant_predicate_reference(paths):
    """The upstream LanguageModel.quant_predicate, by name only."""
    return {p: ({'group_size': 64, 'bits': 8} if (p.endswith('mlp.gate') or 'e_score_correction_bias' in p or '.indexer' in p) else True) for p in paths}


def run(case):
    kind = case['kind']
    if kind == 'switch':
        return switch_experts(case)
    if kind == 'multilinear':
        return multilinear(case)
    if kind == 'predicate':
        return quant_predicate_reference(case['paths'])
    raise ValueError('UNKNOWN_CASE_KIND')

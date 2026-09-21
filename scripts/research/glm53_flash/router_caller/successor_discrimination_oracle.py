"""Independent finite-domain oracle. Standard library only; no MLX/candidate calls."""
import copy
import math
import struct


def f32(x):
    return struct.unpack('>f', struct.pack('>f', float(x)))[0]


def word(x):
    return struct.unpack('>I', struct.pack('>f', float(x)))[0]


def represented(value, dtype):
    if isinstance(value, list):
        return [represented(v, dtype) for v in value]
    bits = word(value)
    if dtype == 'bfloat16':
        bits = ((bits + 0x7fff + ((bits >> 16) & 1)) >> 16) << 16
    elif dtype != 'float32':
        raise ValueError('ORACLE_DTYPE')
    return struct.unpack('>f', struct.pack('>I', bits & 0xffffffff))[0]


def prepare(case):
    result = copy.deepcopy(case)
    result['represented_input'] = represented(case['input'], case['dtype'])
    result['represented_weight'] = represented(case['weight'], case['dtype'])
    if represented(case['bias'], 'float32') != case['bias']:
        raise ValueError('BIAS_MUST_BE_EXACT_FP32')
    return result


def projection(case):
    # Our fixed dyadic products/sums are exactly representable as float32.
    # fsum avoids importing the candidate's matmul or reduction algorithm.
    return [[f32(math.fsum(a*b for a, b in zip(x, w)))
             for w in case['represented_weight']] for x in case['represented_input']]


def sigmoid(x):
    return f32(1 / (1 + math.exp(-x))) if x >= 0 else f32(math.exp(x) / (1 + math.exp(x)))


def selection(logits, bias, config, mask='zero'):
    if mask not in ('zero', 'exclude'):
        raise ValueError('ORACLE_MASK')
    scores = [sigmoid(v) for v in logits]
    ranked = [f32(v+b) for v, b in zip(scores, bias)]
    groups, keep = config['n_group'], config['topk_group']
    group_scores = []
    retained = list(range(groups))
    if groups > 1:
        width = len(scores)//groups
        group_scores = [f32(math.fsum(sorted(ranked[i*width:(i+1)*width], reverse=True)[:2]))
                        for i in range(groups)]
        order = sorted(range(groups), key=lambda i: (-group_scores[i], i))
        if group_scores[order[keep-1]] == group_scores[order[keep]]:
            raise ValueError('GENERATION_DISALLOWS_GROUP_BOUNDARY_TIE')
        retained = order[:keep]
        ranked = [v if i//width in retained else (0.0 if mask == 'zero' else -1e30)
                  for i, v in enumerate(ranked)]
    k = config['num_experts_per_tok']
    order = sorted(range(len(ranked)), key=lambda i: (-ranked[i], i))
    boundary = ranked[order[k-1]]
    return {'selected_ids': order[:k], 'mandatory_ids': [i for i, v in enumerate(ranked) if v > boundary],
            'boundary_ids': [i for i, v in enumerate(ranked) if v == boundary],
            'scores': scores, 'ranked_scores': ranked, 'group_scores': group_scores,
            'retained_groups': retained, 'k': k}


def check_output(ids, scores, expected, config, tolerance):
    if len(ids) != expected['k'] or len(set(ids)) != len(ids) or len(scores) != len(ids):
        raise AssertionError('OUTPUT_CARDINALITY')
    chosen = set(ids)
    mandatory = set(expected['mandatory_ids'])
    if not mandatory <= chosen or not chosen <= mandatory | set(expected['boundary_ids']):
        raise AssertionError('INDEPENDENT_SELECTION_MISMATCH')
    denominator = math.fsum(expected['scores'][i] for i in ids)
    predicted = [expected['scores'][i] * config['routed_scaling_factor'] /
                 (denominator if len(ids) > 1 and config['norm_topk_prob'] else 1.0) for i in ids]
    for actual, reference in zip(scores, predicted):
        if not math.isfinite(actual) or abs(actual-reference) > tolerance['absolute'] + tolerance['relative']*abs(reference):
            raise AssertionError('INDEPENDENT_SCORE_MISMATCH')
    return {'selected_ids_sorted': sorted(ids), 'maximum_score_error': max(abs(a-b) for a, b in zip(scores, predicted))}


def canonical(ids, scores):
    return sorted((int(i), word(v)) for i, v in zip(ids, scores))

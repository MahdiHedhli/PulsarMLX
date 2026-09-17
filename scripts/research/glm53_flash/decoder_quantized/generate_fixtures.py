#!/usr/bin/env python3
"""Frozen quantized fixtures: fp32 weights are quantized by a stdlib affine quantizer (never mx.quantize),
packed little-endian, and the reference outputs are frozen before observation."""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_quantized import oracle  # noqa: E402

SEED = 0x20260917D4


def f32(v):
    return struct.unpack('f', struct.pack('f', v))[0]


def quantize_rows(rows, bits, group_size):
    """Affine: per group scale=(max-min)/(2^bits-1) (1 if zero), bias=min, code=round((w-bias)/scale) clipped; little-endian packing."""
    per_word, levels = 32 // bits, (1 << bits) - 1
    words, scales, biases, err = [], [], [], 0.0
    for row in rows:
        codes, s_row, b_row = [], [], []
        for g0 in range(0, len(row), group_size):
            grp = row[g0:g0 + group_size]; lo, hi = min(grp), max(grp)
            s = f32((hi - lo) / levels) or 1.0; b = f32(lo)
            s_row.append(s); b_row.append(b)
            for w in grp:
                c = min(levels, max(0, int(round((w - b) / s)))); codes.append(c)
                err = max(err, abs(c * s + b - w))
        words.append([sum(codes[i * per_word + j] << (bits * j) for j in range(per_word)) for i in range(len(codes) // per_word)])
        scales.append(s_row); biases.append(b_row)
    return {'words': words, 'scales': scales, 'biases': biases}, err


def mat(rng, rows, cols, scale):
    return [[f32(rng.uniform(-scale, scale)) for _ in range(cols)] for _ in range(rows)]


def switch_case(rng, fixture_id, bits, group_size):
    E, D, I, T, k = 4, 64, 48, 3, 2
    fp32 = {'gate': [mat(rng, I, D, .25) for _ in range(E)], 'up': [mat(rng, I, D, .25) for _ in range(E)], 'down': [mat(rng, D, I, .25) for _ in range(E)]}
    q, errs = {}, {}
    for p in fp32:
        packed = [quantize_rows(e, bits, group_size) for e in fp32[p]]
        q[p] = [pk for pk, _ in packed]; errs[p] = max(e for _, e in packed)
    return {'fixture_id': fixture_id, 'kind': 'switch', 'config': {'bits': bits, 'group_size': group_size, 'num_experts': E, 'hidden': D, 'intermediate': I, 'swiglu_limit': 1.0},
            'x': mat(rng, T, D, 1.0), 'indices': [rng.sample(range(E), k) for _ in range(T)], 'quantized': q,
            'quantization_max_abs_error_vs_fp32': errs, 'generator': {'seed': hex(SEED)}}


def multilinear_case(rng, fixture_id, bits, group_size):
    H, IN, OUT, S = 2, 64, 48, 3
    fp32 = [mat(rng, OUT, IN, .25) for _ in range(H)]
    packed = [quantize_rows(h, bits, group_size) for h in fp32]
    return {'fixture_id': fixture_id, 'kind': 'multilinear', 'config': {'bits': bits, 'group_size': group_size, 'num_heads': H, 'input_dims': IN, 'output_dims': OUT},
            'x_transpose': mat(rng, S, IN, 1.0), 'x_no_transpose': mat(rng, S, OUT, 1.0), 'quantized': {'weight': [pk for pk, _ in packed]},
            'quantization_max_abs_error_vs_fp32': max(e for _, e in packed), 'generator': {'seed': hex(SEED)}}


def main(out_path):
    rng = random.Random(SEED)
    cases = [switch_case(rng, 'switch-4bit-g64', 4, 64), switch_case(rng, 'switch-8bit-g32', 8, 32), multilinear_case(rng, 'multilinear-4bit-g64', 4, 64),
             {'fixture_id': 'quant-predicate-names', 'kind': 'predicate', 'paths': [
                 'model.layers.3.mlp.gate', 'model.layers.3.mlp.gate.e_score_correction_bias', 'model.layers.3.self_attn.indexer.wq_b',
                 'model.layers.3.self_attn.indexer.weights_proj', 'model.layers.3.mlp.switch_mlp.gate_proj', 'model.layers.3.self_attn.embed_q',
                 'model.layers.0.self_attn.q_proj', 'model.embed_tokens', 'lm_head', 'model.layers.3.mlp.shared_experts.up_proj']}]
    expected = {c['fixture_id']: oracle.run(c) for c in cases}
    # sanity: the switch activation clamp is active somewhere and both experts differ
    assert any(e['clamp_active'] > 0 for c in cases[:2] for t in expected[c['fixture_id']]['tokens'] for e in t)
    allowance, factor = 1e-4, 10
    variants = {
        'scales-biases-swapped': ("out.append([c * scales[i // group_size] + biases[i // group_size] for i, c in enumerate(codes)])",
                                  "out.append([c * biases[i // group_size] + scales[i // group_size] for i, c in enumerate(codes)])"),
        'gather-transpose-flipped': ("gate, up = _proj(x, W['gate'][e]), _proj(x, W['up'][e])",
                                     "gate, up = [math.fsum(x[o] * W['gate'][e][o][i] for o in range(len(W['gate'][e]))) for i in range(len(W['gate'][e][0]))], _proj(x, W['up'][e])"),
        'bits-forced-8': ("codes = unpack(words, bits)", "codes = unpack(words, 8)"),
        'group-forced-32': ("out.append([c * scales[i // group_size] + biases[i // group_size] for i, c in enumerate(codes)])",
                            "out.append([c * scales[i // 32] + biases[i // 32] for i, c in enumerate(codes)])"),
        'biases-dropped': ("out.append([c * scales[i // group_size] + biases[i // group_size] for i, c in enumerate(codes)])",
                           "out.append([c * scales[i // group_size] for i, c in enumerate(codes)])"),
        'multilinear-transpose-forced': ("n = [[[math.fsum(x[o] * Wh[o][i] for o in range(len(Wh))) for i in range(len(Wh[0]))] for x in case['x_no_transpose']] for Wh in W]",
                                         "n = [[_proj(x, Wh) for x in case['x_no_transpose']] for Wh in W]"),
    }
    text = Path(oracle.__file__).read_text()
    def flat(v):
        return [x for y in v for x in flat(y)] if isinstance(v, list) else ([x for y in v.values() for x in flat(y)] if isinstance(v, dict) and 'expert' not in v else [v] if not isinstance(v, dict) else [x for k2 in ('gate', 'up', 'output') for x in flat(v[k2])])
    targets = {'scales-biases-swapped': 'switch', 'gather-transpose-flipped': 'switch', 'bits-forced-8': 'switch', 'group-forced-32': 'switch',
               'biases-dropped': 'switch', 'multilinear-transpose-forced': 'multilinear'}
    predicted = {}
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant_' + label, 'moe': oracle.moe}
        exec(compile(text.replace(before, after).replace('from scripts.research.glm53_flash.decoder_moe import oracle as moe', ''), 'oracle-variant:' + label, 'exec'), ns)
        cells = []
        for c in [c for c in cases[:3] if c['kind'] == targets[label]]:  # a mutant of one class only reaches that class's cases
            try:
                v = ns['run'](c); a, b = flat(v), flat(expected[c['fixture_id']])
                if len(a) != len(b):
                    cells.append(('KILL', 'rejected:shape')); continue
                err = max(abs(p - q) for p, q in zip(a, b))
                cells.append(('KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL', err))
            except (ValueError, IndexError, TypeError) as exc:
                cells.append(('KILL', 'rejected:' + type(exc).__name__))
        predicted[label] = cells
    matrix = {'schema': 'flash-quantized-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': [c['fixture_id'] for c in cases[:3]], 'kill_margin_factor': factor,
              'matrix': {k: [c[0] for c in v] for k, v in predicted.items()}, 'predicted_oracle_variant_error': {k: [c[1] for c in v] for k, v in predicted.items()},
              'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants},
              'targets': targets, 'cases_by_target': {'switch': ['switch-4bit-g64', 'switch-8bit-g32'], 'multilinear': ['multilinear-4bit-g64']}}
    doc = {'schema': 'flash-quantized-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_quantized/oracle.py',
           'format': 'mlx affine: little-endian bit packing into uint32, per-group scale/bias along the input axis, value = code*scale + bias',
           'tolerances': {'output': 1e-4, 'dequantize_cross_check': 1e-6}, 'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases[:3]:
        print(' ', c['fixture_id'], 'quant err vs fp32', c['quantization_max_abs_error_vs_fp32'])
    for k, v in predicted.items():
        print(f'  {k:30s} ' + '  '.join(f"{c[0]:8s}({c[1] if isinstance(c[1], str) else round(c[1], 4)})" for c in v))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json')

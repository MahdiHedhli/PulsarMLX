#!/usr/bin/env python3
"""Deterministic MoE fixtures frozen by the oracle before observation.

Geometry mirrors the accepted router fixtures (4 routed experts, hidden 4,
top-k 2, one group, scaling 2.5, norm_topk_prob) so the router stage sits in
the accepted reference's domain. Cases are generated until every token's
selection margin is at least MARGIN so no tie-breaking is exercised; the seed
and the accepted attempt are recorded.
"""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_moe import oracle as moe_oracle  # noqa: E402
from scripts.research.glm53_flash.router_caller import rc_oracle  # noqa: E402

SEED = 0x20260916B9
MARGIN = 1e-2
CONFIG = {'n_routed_experts': 4, 'hidden_size': 4, 'num_experts_per_tok': 2, 'norm_topk_prob': True,
          'routed_scaling_factor': 2.5, 'n_group': 1, 'topk_group': 1, 'topk_method': 'noaux_tc',
          'moe_intermediate_size': 3, 'n_shared_experts': 1, 'swiglu_limit': 1.0}


def f32(v):
    return struct.unpack('f', struct.pack('f', v))[0]


def dyadic(rng, unit, lo, hi):
    return rng.choice((-1, 1)) * rng.randint(lo, hi) / unit


def mat(rng, r, c, unit, lo, hi):
    return [[dyadic(rng, unit, lo, hi) for _ in range(c)] for _ in range(r)]


def case(rng, attempt):
    E, H, I = CONFIG['n_routed_experts'], CONFIG['hidden_size'], CONFIG['moe_intermediate_size']
    T = 2
    c = {'fixture_id': f'moe-e4-k2-t{T}', 'config': CONFIG, 'tokens': T,
         'x': [[f32(dyadic(rng, 8, 1, 8)) for _ in range(H)] for _ in range(T)],
         'gate_weight': mat(rng, E, H, 16, 1, 8), 'gate_bias': [f32(dyadic(rng, 16, 0, 4)) for _ in range(E)],
         'experts': {'gate': [mat(rng, I, H, 8, 2, 12) for _ in range(E)], 'up': [mat(rng, I, H, 8, 2, 12) for _ in range(E)],
                     'down': [mat(rng, H, I, 8, 1, 6) for _ in range(E)]},
         'shared': {'gate': mat(rng, I, H, 8, 2, 12), 'up': mat(rng, I, H, 8, 2, 12), 'down': mat(rng, H, I, 8, 1, 6)},
         'generator': {'seed': hex(SEED), 'attempt': attempt, 'margin_floor': MARGIN}}
    return c


def main():
    rng = random.Random(SEED)
    for attempt in range(1, 200):
        c = case(rng, attempt)
        r = moe_oracle.run(c, rc_oracle.reference)
        margins = [t['selection_margin'] for t in r['tokens']]
        if min(margins) >= MARGIN and r['clamp_active_elements'] > 0:
            break
    else:
        raise SystemExit('NO_ADMISSIBLE_CASE')
    out = {'schema': 'glm53-flash-decoder-moe-v1', 'cases': [c], 'expected': {c['fixture_id']: r},
           'tolerances': {'logits': 1e-4, 'scores': 1e-4, 'experts': 1e-4, 'combine': 1e-4, 'shared': 1e-4, 'output': 1e-4},
           'limits': ['tiny geometry; float32 router; no quantized experts; E288 bias-dominated selection and nondiscriminating individual-cast controls remain historical router limits; not real-model correctness']}
    target = ROOT / 'fixtures/research/glm53-flash-decoder-moe-v1/fixtures.json'
    if target.exists():
        previous = json.loads(target.read_text())
        if 'expected_kill_matrix' in previous:
            out['expected_kill_matrix'] = previous['expected_kill_matrix']
    target.write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({'attempt': attempt, 'margins': margins, 'selected': [t['selected_ids'] for t in r['tokens']],
                      'clamp_active': r['clamp_active_elements'], 'output_absmax': max(abs(v) for t in r['tokens'] for v in t['output'])}))


if __name__ == '__main__':
    main()

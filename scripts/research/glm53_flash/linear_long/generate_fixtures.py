#!/usr/bin/env python3
"""Long-sequence linear attention fixtures: the decoder-layer generator's accepted parameter family, one-negative-lane
sign-pattern tokens, S in {8, 16, 33, 64}; expected outputs and caches from the chunked composition of the accepted
reference, frozen before observation."""
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_layer import generate_fixtures as layer_generator  # noqa: E402
from scripts.research.glm53_flash.linear_long import oracle  # noqa: E402

SEED = 0x20260917F6
LENGTHS = (8, 16, 33, 64)


def main(out_path):
    rng = random.Random(SEED)
    layer_case = layer_generator.case(2, random.Random(rng.getrandbits(64)))
    params, cfg = layer_case['linear_parameters'], layer_case['linear_config']
    I = cfg['hidden_size']
    cases, expected, timing = [], {}, {}
    for S in LENGTHS:
        inputs = []
        for _ in range(S):
            lane = rng.randrange(I); m = rng.randint(32, 63) / 64
            inputs.append([(-m if d == lane else m) for d in range(I)])
        case = {'fixture_id': f'linear-long-s{S}', 'config': cfg, 'parameters': params, 'inputs': inputs, 'tokens': S,
                'input_design': 'one negative lane per token, uniform magnitude in [1/2, 63/64] (dyadic, |v| <= 1)', 'generator': {'seed': hex(SEED)}}
        t0 = time.time(); expected[case['fixture_id']] = oracle.run(case); timing[case['fixture_id']] = round(time.time() - t0, 2)
        cases.append(case)
    doc = {'schema': 'flash-linear-long-fixtures/1', 'oracle': 'scripts/research/glm53_flash/linear_long/oracle.py',
           'accepted_reference': 'scripts/research/glm53_flash/linear_attention/oracle.py (unchanged; S <= 5 per call)', 'chunk': oracle.CHUNK,
           'tolerances': {'output': 1e-4, 'cache0_atol': 1e-4, 'cache0_rtol': 1e-5, 'cache1_atol': 1e-4, 'cache1_rtol': 1e-5},
           'controls': {'kernel-domain-gate': 'with max_sequence 5 the single S=N call must be refused with MODULE_KERNEL_DOMAIN',
                        'single-call-vs-chunked-candidate': 'observed and reported; both compared to the reference'},
           'cases': cases, 'expected': expected, 'reference_seconds': timing}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]
        print(f"  S={c['tokens']:3d} chunks={len(e['chunks'])} radii={ {k: '%.1e' % v for k, v in e['maximum_radii_over_chunks'].items()} } ref {timing[c['fixture_id']]}s")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-linear-long-v1/fixtures.json')

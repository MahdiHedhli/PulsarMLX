#!/usr/bin/env python3
"""LFU-with-decay fixtures over the graph-18 arrays with a schedule where LFU and LRU residency differ; warm-state expectation;
prospective controls from oracle variants."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_offload import oracle as lru_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_offload_pulsar import oracle  # noqa: E402

OFFLOAD = ROOT / 'fixtures/research/glm53-flash-decoder-offload-v1/fixtures.json'
CACHE_BOUND_BYTES = 1 << 30   # the bounded case: the tiny fixtures' freed buffers never reach it, so the true store must not clear
# Graph 22: the allocator-cache mutants have no stdlib model (the model has no allocator); their cells follow by construction
# from the threshold semantics and are recorded before any run. 'clear-always' clears after every evicting call regardless of
# the threshold (mismatch on the bounded case); 'never-clear' never clears (mismatch on the threshold-0 case).
CACHE_MUTANTS = {'clear-always': {'expected_reason': 'cache-clears-mismatch', 'kills_on': 'bounded'}, 'never-clear': {'expected_reason': 'cache-clears-mismatch', 'kills_on': 'threshold-0'}}


def predicted_cells(cases, expected, variants, text):
    predicted = {}
    for label, (before, after) in variants.items():
        ns = {'__name__': 'variant', 'base': oracle.base}
        exec(compile(text.replace(before, after).replace('from scripts.research.glm53_flash.decoder_offload import oracle as base', ''), 'variant:' + label, 'exec'), ns)
        cells = []
        for c in cases:
            v = ns['run'](c); e = expected[c['fixture_id']]
            stats_differ = any(vc['stats'] != ec['stats'] for vc, ec in zip(v['calls'], e['calls']))
            warm_differ = sorted(v['warm_state']['admitted_on_restart']) != sorted(e['warm_state']['admitted_on_restart'])
            cells.append('KILL' if (stats_differ or warm_differ) else 'INACTIVE')
        predicted[label] = cells
    return predicted


VARIANTS = {
    'decay-disabled': ("                        counts[k] *= decay", "                        counts[k] *= 1.0"),
    'tie-break-most-recent': ("victim = min(resident, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))", "victim = min(resident, key=lambda k: (counts.get(k, 0.0), -touch.get(k, 0)))"),
    'warm-state-ignored': ("    warm_order = sorted(resident, key=lambda j: -counts.get(j, 0.0))", "    warm_order = []"),
}


def main(out_path):
    import random
    base = json.loads(OFFLOAD.read_bytes())
    text = Path(oracle.__file__).read_text()
    for before, _ in VARIANTS.values():
        assert text.count(before) == 1
    rng = random.Random(0x20260917D8)
    # search a seeded family of schedules for one where LFU != LRU on both cases and every control kills on both
    for attempt in range(1, 5001):
        n = rng.randint(10, 16)
        schedule = [{'tokens': [rng.randrange(3)]} for _ in range(n)] + [{'tokens': [0, 1, 2]}, {'tokens': [rng.randrange(3)]}]
        policy = {'decay': 0.5, 'decay_every': rng.choice([3, 4, 5, 6])}
        cases, expected, ok = [], {}, True
        for b in base['cases']:
            case = {**b, 'fixture_id': b['fixture_id'].replace('offload', 'pulsar'), 'schedule': schedule, 'policy': policy}
            r = oracle.run(case); lru = lru_oracle.run({**b, 'schedule': schedule})
            differs = [i for i, (a, c) in enumerate(zip(r['calls'], lru['calls'])) if a['stats'] != c['stats']]
            if not differs or r['final_stats']['hits'] <= lru['final_stats']['hits']:
                ok = False; break
            r['lru_differs_at_calls'] = differs; r['lru_final_stats'] = lru['final_stats']
            cases.append(case); expected[case['fixture_id']] = r
        if not ok:
            continue
        predicted = predicted_cells(cases, expected, VARIANTS, text)
        if all(c == 'KILL' for v in predicted.values() for c in v) and all(expected[c['fixture_id']]['calls'][-1]['eviction_events'] > 0 for c in cases):
            break
    else:
        raise SystemExit('no discriminating schedule found')
    variants = VARIANTS
    for label in CACHE_MUTANTS:
        predicted[label] = ['KILL' for _ in cases]
    search = {'seed': hex(0x20260917D8), 'attempt': attempt, 'schedule_length': len(schedule), 'policy': policy}
    matrix = {'schema': 'flash-pulsar-store-expected-kill-matrix/2', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True, 'schedule_search': search,
              'fixtures': [c['fixture_id'] for c in cases], 'cell_scope': 'policy counts per call or the warm-state admitted SET (order is not part of the claim)',
              'matrix': predicted, 'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants},
              'cache_mutants': CACHE_MUTANTS, 'cache_bound_bytes': CACHE_BOUND_BYTES}
    doc = {'schema': 'flash-pulsar-store-fixtures/2', 'oracle': 'scripts/research/glm53_flash/decoder_offload_pulsar/oracle.py', 'store': 'scripts/research/glm53_flash/dogfood/pulsar_expert_store.py',
           'tolerances': {'output': 1e-4}, 'cache_bound_bytes': CACHE_BOUND_BYTES, 'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]; print(' ', c['fixture_id'], 'LFU final', e['final_stats'], 'LRU final', e['lru_final_stats'], 'differs at', e['lru_differs_at_calls'], 'warm', e['warm_state']['admitted_on_restart'])
    for k, v in predicted.items():
        print(f'  {k:24s} {v}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-offload-pulsar-v2/fixtures.json')

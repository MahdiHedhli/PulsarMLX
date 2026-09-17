#!/usr/bin/env python3
"""Slot-store fixtures over the graph-18 arrays: graph 21's schedule family (seeded search) re-run against the slot model
so that every policy control kills on both cases and every case needs at least one wave split and one eviction;
structural (value) mutants recorded by construction."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_slot_store import oracle  # noqa: E402

OFFLOAD = ROOT / 'fixtures/research/glm53-flash-decoder-offload-v1/fixtures.json'

VARIANTS = {
    'decay-disabled': ("                        counts[k] *= decay", "                        counts[k] *= 1.0"),
    'tie-break-most-recent': ("victim = min(candidates, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))", "victim = min(candidates, key=lambda k: (counts.get(k, 0.0), -touch.get(k, 0)))"),
    'warm-state-ignored': ("    warm_order = sorted(slot_of, key=lambda j: -counts.get(j, 0.0))[:capacity]", "    warm_order = []"),
    'pin-ignored': ("                        candidates = [k for k in slot_of if k not in pinned]", "                        candidates = list(slot_of)"),
}
# value-only structural mutants of the runtime file: the stdlib model has no slot tensors, so their cells follow by
# construction (a token computed from the wrong slot changes the output) and are recorded before any run
STRUCTURAL = {'stale-slot-map': {'expected_reason': 'value', 'kills_on': 'any eviction followed by a touch of the evicted expert'},
              'missing-check-removed': {'expected_reason': 'rejected-or-value', 'kills_on': 'the first miss'},
              'victim-slot-wrong': {'expected_reason': 'value', 'kills_on': 'the first eviction'}}


def predicted_cells(cases, expected, variants, text):
    predicted = {}
    for label, (before, after) in variants.items():
        ns = {'__name__': 'variant', 'base': oracle.base, '_VALUES': oracle._VALUES}
        exec(compile(text.replace(before, after).replace('from scripts.research.glm53_flash.decoder_offload import oracle as base', ''), 'variant:' + label, 'exec'), ns)
        cells = []
        for c in cases:
            v = ns['run'](c); e = expected[c['fixture_id']]
            differ = any((vc['stats'], vc['slot_of']) != (ec['stats'], ec['slot_of']) for vc, ec in zip(v['calls'], e['calls']))
            warm_differ = v['warm_state']['slot_on_restart'] != e['warm_state']['slot_on_restart']
            cells.append('KILL' if (differ or warm_differ) else 'INACTIVE')
        predicted[label] = cells
    return predicted


def main(out_path):
    import random
    base = json.loads(OFFLOAD.read_bytes())
    text = Path(oracle.__file__).read_text()
    for before, _ in VARIANTS.values():
        assert text.count(before) == 1, before
    rng = random.Random(0x20260917E1)
    for attempt in range(1, 5001):
        n = rng.randint(10, 16)
        schedule = [{'tokens': [rng.randrange(3)]} for _ in range(n)] + [{'tokens': [0, 1, 2]}, {'tokens': [rng.randrange(3)]}]
        policy = {'decay': 0.5, 'decay_every': rng.choice([3, 4, 5, 6])}
        cases, expected, ok = [], {}, True
        for b in base['cases']:
            case = {**b, 'fixture_id': b['fixture_id'].replace('offload', 'slot'), 'schedule': schedule, 'policy': policy}
            r = oracle.run(case)
            if r['final_stats']['evictions'] == 0 or not any(len(c['waves']) > 1 for c in r['calls']):
                ok = False; break
            cases.append(case); expected[case['fixture_id']] = r
        if not ok:
            continue
        predicted = predicted_cells(cases, expected, VARIANTS, text)
        if all(c == 'KILL' for v in predicted.values() for c in v):
            break
    else:
        raise SystemExit('no discriminating schedule found')
    for label in STRUCTURAL:
        predicted[label] = ['KILL' for _ in cases]
    search = {'seed': hex(0x20260917E1), 'attempt': attempt, 'schedule_length': len(schedule), 'policy': policy}
    matrix = {'schema': 'flash-slot-store-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True, 'schedule_search': search,
              'fixtures': [c['fixture_id'] for c in cases], 'cell_scope': 'per-call stats and slot map, or the warm-state slot assignment; structural mutants by value',
              'matrix': predicted, 'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in VARIANTS.items()}, 'needle_counts': {k: 1 for k in VARIANTS},
              'structural_mutants': STRUCTURAL}
    doc = {'schema': 'flash-slot-store-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_slot_store/oracle.py', 'store': 'scripts/research/glm53_flash/dogfood/pulsar_slot_store.py',
           'tolerances': {'output': 1e-4}, 'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]; print(' ', c['fixture_id'], 'capacity', e['capacity'], 'final', e['final_stats'], 'waves>1 at', [i for i, cc in enumerate(e['calls']) if len(cc['waves']) > 1], 'warm', e['warm_state']['slot_on_restart'])
    for k, v in predicted.items():
        print(f'  {k:24s} {v}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v1/fixtures.json')

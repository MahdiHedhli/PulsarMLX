#!/usr/bin/env python3
"""Slot-store fixtures over the graph-18 arrays: graph 21's schedule family (seeded search) re-run against the slot model
so that every policy control kills on both cases and every case needs at least one wave split and one eviction;
structural (value) mutants recorded by construction. Revision 4 (graph 31): read-phase fault expectations at the first miss and the
first eviction (retry reproduces the slot map; misses and accesses advance twice) and three residency-commit mutants."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_slot_store import oracle  # noqa: E402

OFFLOAD = ROOT / 'fixtures/research/glm53-flash-decoder-offload-v1/fixtures.json'

VARIANTS = {
    'decay-disabled': ("                    counts[k] *= decay", "                    counts[k] *= 1.0"),
    'tie-break-most-recent': ("victim = min(candidates, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))", "victim = min(candidates, key=lambda k: (counts.get(k, 0.0), -touch.get(k, 0)))"),
    'warm-state-ignored': ("    warm_order = sorted(slot_of, key=lambda j: -counts.get(j, 0.0))[:capacity]", "    warm_order = []"),
    'pin-ignored': ("                    candidates = [k for k in slot_of if k not in pinned]", "                    candidates = list(slot_of)"),
}
# value-only structural mutants of the runtime file: the stdlib model has no slot tensors, so their cells follow by
# construction (a token computed from the wrong slot changes the output) and are recorded before any run
STRUCTURAL = {'map-not-refreshed': {'expected_reason': 'rejected-or-value', 'kills_on': 'the first miss (the GPU slot map is not rebuilt after reads: the gather sees stale slots)'},
              'missing-check-removed': {'expected_reason': 'rejected-or-value', 'kills_on': 'the first miss'},
              'victim-slot-wrong': {'expected_reason': 'value', 'kills_on': 'the first eviction'},
              'coalesce-offset-wrong': {'expected_reason': 'value', 'kills_on': 'the first coalesced cold read (contiguous layout, forced cold): tensors sliced one byte off'},
              'layout-flag-ignored': {'expected_reason': 'rejected-or-value', 'kills_on': 'the hash-ordered layout read as contiguous (forced cold): expert ranges are not contiguous'},
              # graph 31: residency committed after materialization; these three are killed by the fault-injection test
              'publish-before-fill': {'expected_reason': 'policy-or-value', 'kills_on': 'a read-phase fault then retry: the failed wave is a false HIT (no read; stale or partial slot bytes) - the pre-graph-31 behaviour'},
              'poison-not-checked': {'expected_reason': 'rejection-expected-but-served', 'kills_on': 'a write-phase fault then retry: the store serves values from an unverified slot state instead of raising STORE_POISONED'},
              'release-slots-omitted': {'expected_reason': 'policy', 'kills_on': 'a read-phase fault then retry: the reserved slots never return to the free list, so the retry evicts other residents and the slot map diverges from the model'}}
FAULTS = {'model': 'oracle.run(case, fault={call, wave}) for the read phase (retry reproduces the fault-free slot map at the failing call; misses and accesses advance twice for that wave); write/eval-phase faults poison the store (STORE_POISONED on every later call, checked by rejection)',
          'points': 'oracle.fault_points: first-miss and first-eviction (fault-free run)', 'stages': ['read-done (before the first write)', 'projection-written (between projections)', 'before-eval', 'during-eval (mx.eval patched to raise)']}
REVISION = {'revision': 4, 'graph31': "revision 4 adds the residency-commit mutants (publish-before-fill, poison-not-checked, release-slots-omitted) and the fault-injection expectations (calls carry wave_evictions; test_fault_injection joins the operation)", 'graph29': "revision 3 adds the two layout mutants (graph 29: expert-contiguous repack + coalesced cold reads); every case now runs in both layouts and both residency modes and must agree bit for bit", 'first_contact': "revision 1 recorded 'stale-slot-map' (expert_to_slot[victim] not cleared on eviction) as KILL by construction; the "
                                            "supervised run observed INACTIVE on both cases: slot_of is the authority for hits, a stale map entry is only read for "
                                            "experts of the current call, which are always just-filled, so the clear is redundant and the mutant equivalent. "
                                            "Replaced before the re-run by 'map-not-refreshed' (L.map_array not invalidated after reads), which the gather depends on."}


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
    faults = {}
    for c in cases:
        e = expected[c['fixture_id']]; points = oracle.fault_points(e)
        runs = {}
        for name, pt in points.items():
            r = oracle.run(c, fault=pt)   # values are the fault-free values (same arithmetic): keep policy, slot maps and the post-fault state only
            runs[name] = {'fault': r['fault'], 'final_stats': r['final_stats'], 'warm_state': r['warm_state'],
                          'calls': [{k: v for k, v in call.items() if k in ('stats', 'slot_of', 'resident_set', 'after_fault', 'attempts', 'reads', 'wave_evictions')} for call in r['calls']]}
        faults[c['fixture_id']] = {'points': points, 'read_phase': runs}
    search = {'seed': hex(0x20260917E1), 'attempt': attempt, 'schedule_length': len(schedule), 'policy': policy}
    matrix = {'schema': 'flash-slot-store-expected-kill-matrix/4', 'faults': FAULTS, 'frozen_before_tests': True, 'prospective_from_oracle_variants': True, 'schedule_search': search,
              'fixtures': [c['fixture_id'] for c in cases], 'cell_scope': 'per-call stats and slot map, or the warm-state slot assignment; structural mutants by value',
              'matrix': predicted, 'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in VARIANTS.items()}, 'needle_counts': {k: 1 for k in VARIANTS},
              'structural_mutants': STRUCTURAL, **REVISION}
    doc = {'schema': 'flash-slot-store-fixtures/2', 'oracle': 'scripts/research/glm53_flash/decoder_slot_store/oracle.py', 'store': 'scripts/research/glm53_flash/dogfood/pulsar_slot_store.py',
           'tolerances': {'output': 1e-4}, 'cases': cases, 'expected': expected, 'expected_faults': faults, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]; print(' ', c['fixture_id'], 'capacity', e['capacity'], 'final', e['final_stats'], 'waves>1 at', [i for i, cc in enumerate(e['calls']) if len(cc['waves']) > 1], 'warm', e['warm_state']['slot_on_restart'])
    for k, v in predicted.items():
        print(f'  {k:24s} {v}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v1/fixtures.json')

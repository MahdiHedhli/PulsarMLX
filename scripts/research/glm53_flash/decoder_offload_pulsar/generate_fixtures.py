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
SCHEDULE = [{'tokens': [0]}, {'tokens': [0]}, {'tokens': [1]}, {'tokens': [0]}, {'tokens': [2]}, {'tokens': [1]}, {'tokens': [0]}, {'tokens': [2]}, {'tokens': [0, 1, 2]}, {'tokens': [0]}]
POLICY = {'decay': 0.5, 'decay_every': 6}


def main(out_path):
    base = json.loads(OFFLOAD.read_bytes())
    cases, expected = [], {}
    for b in base['cases']:
        case = {**b, 'fixture_id': b['fixture_id'].replace('offload', 'pulsar'), 'schedule': SCHEDULE, 'policy': POLICY}
        r = oracle.run(case); lru = lru_oracle.run({**b, 'schedule': SCHEDULE})
        differs = [i for i, (a, c) in enumerate(zip(r['calls'], lru['calls'])) if a['stats'] != c['stats']]
        assert differs, 'schedule does not discriminate LFU from LRU for ' + case['fixture_id']
        r['lru_differs_at_calls'] = differs; r['lru_final_stats'] = lru['final_stats']
        cases.append(case); expected[case['fixture_id']] = r
    variants = {
        'decay-disabled': ("                        counts[k] *= decay", "                        counts[k] *= 1.0"),
        'tie-break-most-recent': ("victim = min(resident, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))", "victim = min(resident, key=lambda k: (counts.get(k, 0.0), -touch.get(k, 0)))"),
        'warm-state-ignored': ("    warm_order = sorted(resident, key=lambda j: -counts.get(j, 0.0))", "    warm_order = []"),
    }
    text = Path(oracle.__file__).read_text()
    predicted = {}
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant', 'base': oracle.base}
        exec(compile(text.replace(before, after).replace('from scripts.research.glm53_flash.decoder_offload import oracle as base', ''), 'variant:' + label, 'exec'), ns)
        cells = []
        for c in cases:
            v = ns['run'](c); e = expected[c['fixture_id']]
            stats_differ = any(vc['stats'] != ec['stats'] for vc, ec in zip(v['calls'], e['calls']))
            warm_differ = v['warm_state']['admitted_on_restart'] != e['warm_state']['admitted_on_restart']
            cells.append('KILL' if (stats_differ or warm_differ) else 'INACTIVE')
        predicted[label] = cells
    matrix = {'schema': 'flash-pulsar-store-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': [c['fixture_id'] for c in cases], 'cell_scope': 'policy counts per call or the warm-state admission set',
              'matrix': predicted, 'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants}}
    doc = {'schema': 'flash-pulsar-store-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_offload_pulsar/oracle.py', 'store': 'scripts/research/glm53_flash/dogfood/pulsar_expert_store.py',
           'tolerances': {'output': 1e-4}, 'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]; print(' ', c['fixture_id'], 'LFU final', e['final_stats'], 'LRU final', e['lru_final_stats'], 'differs at', e['lru_differs_at_calls'], 'warm', e['warm_state']['admitted_on_restart'])
    for k, v in predicted.items():
        print(f'  {k:24s} {v}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-offload-pulsar-v1/fixtures.json')

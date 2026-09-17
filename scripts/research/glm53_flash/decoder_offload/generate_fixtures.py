#!/usr/bin/env python3
"""Offload fixtures: the graph-15 switch cases with a decode-like schedule and a two-expert byte budget, frozen with the
LRU-model expectations and a prospective matrix."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_offload import oracle  # noqa: E402

QUANTIZED = ROOT / 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json'
SCHEDULE = [{'tokens': [0]}, {'tokens': [1]}, {'tokens': [2]}, {'tokens': [0]}, {'tokens': [2]}, {'tokens': [1]}, {'tokens': [0, 1, 2]}, {'tokens': [1]}]


def main(out_path):
    q = json.loads(QUANTIZED.read_bytes())
    cases, expected = [], {}
    for base in q['cases'][:2]:
        cfg = base['config']
        case = {'fixture_id': base['fixture_id'].replace('switch', 'offload'), 'config': cfg, 'x': base['x'], 'indices': base['indices'], 'quantized': base['quantized'],
                'schedule': SCHEDULE, 'budget_bytes': 2 * oracle.expert_bytes(cfg), 'layer_id': 0,
                'derived_from': {'fixture': 'fixtures/research/glm53-flash-decoder-quantized-v1/fixtures.json', 'case': base['fixture_id']}}
        cases.append(case); expected[case['fixture_id']] = oracle.run(case)
    variants = {
        'lru-evicts-most-recent': ("lru.popitem(last=False); resident -= nbytes; evictions += 1", "lru.popitem(last=True); resident -= nbytes; evictions += 1"),
        'lru-no-touch-on-hit': ("lru.move_to_end(j); hits += 1", "hits += 1"),
        'refetch-after-evict-omitted': ("                    lru[j] = nbytes; resident += nbytes", "                    if evictions: raise KeyError('EXPERT_KEYS_DROPPED')\n                    lru[j] = nbytes; resident += nbytes"),
        'scatter-slot-ignored': ("rows = [[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))] for t in tokens]",
                                 "rows = [[[sum(v) for v in zip(*[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))])], [0.0] * cfg['hidden']] for t in tokens]"),
        'expert-rows-misgathered': ("rows = [[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))] for t in tokens]",
                                    "rows = [[values['tokens'][tokens[min(k, len(tokens) - 1)]][k]['output'] if k < len(tokens) else (_ for _ in ()).throw(IndexError('SLOT_AS_ROW')) for k in range(len(case['indices'][t]))] for t in tokens]"),
        'bulk-threshold-inverted': ("bulk = len(uniq) * 2 > E", "bulk = len(uniq) * 2 <= E"),
    }
    text = Path(oracle.__file__).read_text()
    predicted = {}
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant_' + label, 'quantized': oracle.quantized, 'OrderedDict': oracle.OrderedDict}
        src = text.replace(before, after).replace('from scripts.research.glm53_flash.decoder_quantized import oracle as quantized', '').replace('from collections import OrderedDict', '')
        exec(compile(src, 'oracle-variant:' + label, 'exec'), ns)
        cells = []
        for c in cases:
            exp = expected[c['fixture_id']]
            try:
                v = ns['run'](c)
                stats_differ = any(vc['stats'] != ec['stats'] or vc['bulk'] != ec['bulk'] for vc, ec in zip(v['calls'], exp['calls']))
                err = max(abs(a - b) for vc, ec in zip(v['calls'], exp['calls']) for vr, er in zip(vc['outputs'], ec['outputs']) for va, ea in zip(vr, er) for a, b in zip(va, ea))
                cells.append(('KILL', 'policy-mismatch') if stats_differ else ('KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', err))
            except (KeyError, IndexError, ValueError) as exc:
                cells.append(('KILL', 'rejected:' + type(exc).__name__))
        predicted[label] = cells
    matrix = {'schema': 'flash-offload-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': [c['fixture_id'] for c in cases], 'kill_margin_factor': 10,
              'cell_scope': 'per case: a store-policy mismatch (hits/misses/evictions/bulk), a rejection, or an output value error',
              'matrix': {k: [c[0] for c in v] for k, v in predicted.items()}, 'predicted_oracle_variant_error': {k: [c[1] for c in v] for k, v in predicted.items()},
              'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants},
              'targets': {'lru-evicts-most-recent': 'store', 'lru-no-touch-on-hit': 'store', 'refetch-after-evict-omitted': 'store',
                          'scatter-slot-ignored': 'module', 'expert-rows-misgathered': 'module', 'bulk-threshold-inverted': 'module'}}
    doc = {'schema': 'flash-offload-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_offload/oracle.py',
           'store_format': 'experts/layer_0000.safetensors with e{j}.{gate,up,down}_proj.{weight,scales,biases}; offload_index.json {layers, num_experts}',
           'tolerances': {'output': 1e-4}, 'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]; print(' ', c['fixture_id'], 'expert bytes', e['expert_bytes'], 'budget', c['budget_bytes'])
        for call in e['calls']: print('    ', call['tokens'], 'uniq', call['unique'], 'bulk' if call['bulk'] else 'get ', call['stats'], call['resident_order'])
    for k, v in predicted.items():
        print(f'  {k:30s} ' + '  '.join(f"{c[0]:8s}({c[1] if isinstance(c[1], str) else round(c[1], 4)})" for c in v))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-offload-v1/fixtures.json')

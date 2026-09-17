#!/usr/bin/env python3
"""Deterministic sparse-attention decode fixture frozen by the incremental oracle before observation.

kpool 2 / topk 2 / S=7 with a 2-token prefill: the prefill is a bypass (T=2),
the first decode step (T=3) performs full pooling, later steps use the
incremental rule with alternating partial/complete trailing pools; select_k is
1 so pool competition and -1 padding both appear in decode rows. Every decode
row must equal the frozen prefill reference's row (decoder_sparse.oracle on the
whole sequence), which proves the incremental rule equivalent to full pooling
on this fixture independently of the candidate. Cases are regenerated until
every selection margin is >= MARGIN.
"""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_sparse import oracle as prefill_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse import generate_fixtures as sparse_generator  # noqa: E402
from scripts.research.glm53_flash.decoder_sparse_decode import oracle as decode_oracle  # noqa: E402

SEED = 0x20260917C3
MARGIN = 2e-2
S, S0 = 7, 2
CONFIG = {**sparse_generator.CONFIG, 'index_topk': 2, 'index_kpool': 2}


def main(out_path):
    rng = random.Random(SEED)
    for attempt in range(1, 10001):
        case = {'fixture_id': 'sparse-decode-kpool2-topk2-s7-prefill2', 'config': dict(CONFIG), 'tokens': S, 'prefill_tokens': S0,
                'x': sparse_generator.mat(rng, S, CONFIG['hidden_size'], 1.0), 'weights': sparse_generator.weights(rng, CONFIG),
                'indexer': sparse_generator.indexer_weights(rng, CONFIG), 'generator': {'seed': hex(SEED), 'attempt': attempt}}
        r = decode_oracle.run(case)
        full = prefill_oracle.run({k: v for k, v in case.items() if k != 'prefill_tokens'})
        rows = [row for st in r['steps'] for row in st['rows']]
        margins = [row['selection_margin'] for row in rows if row['selection_margin'] is not None]
        if any(m < MARGIN for m in margins):
            continue
        # incremental == full pooling reference, row by row (topk, allowed, outputs)
        for t, row in enumerate(rows):
            assert row['time'] == t
            if row['regime'] == 'sparse':
                assert row['topk'] == full['topk'][t] and row['allowed'] == full['allowed'][t], ('selection', t)
            else:
                assert row['allowed'] == list(range(t + 1))
            assert max(abs(a - b) for a, b in zip(row['output'], full['output'][t])) <= 1e-12, ('output', t)
        break
    else:
        raise SystemExit('no admissible case')
    expected = r
    allowance, factor = 1e-4, 10
    variants = {
        'incremental-suffix-offset-omitted': ("pools = old[:n_stable] + _pools(cfg, ix['compress_ape'], k, gate, s0, T)",
                                              "pools = old[:n_stable] + [{**p, 'indices': [i - s0 if i >= 0 else -1 for i in p['indices']]} for p in _pools(cfg, ix['compress_ape'], k, gate, s0, T)]"),
        'stale-partial-pool-kept': ("n_stable = t_prev // kp; s0 = n_stable * kp", "n_stable = t_prev // kp + 1; s0 = n_stable * kp"),
        'stable-pools-recomputed': ("n_stable = t_prev // kp; s0 = n_stable * kp", "n_stable = max(t_prev // kp - 1, 0); s0 = n_stable * kp"),
        'incremental-path-disabled': ("if kind == 'decode' and pool_state is not None:", "if False:"),
        'decode-selection-mask-ignored': ("allowed = sorted({i for i in topk if i >= 0})", "allowed = [max(i, 0) for i in topk]"),
        'decode-unembed-omitted': ("concat.extend(math.fsum(pj * values[h][j][d] for pj, j in zip(p, allowed)) for d in range(dv))",
                                   "concat.extend(math.fsum(pj * latent[j][d] for pj, j in zip(p, allowed)) for d in range(dv))"),
        'latent-cache-not-fetched': ("concat, out = attend(t, allowed)\n            rows.append({'time': t, 'regime': 'sparse'",
                                     "concat, out = attend(t, [t] * len(allowed))\n            rows.append({'time': t, 'regime': 'sparse'"),
    }
    text = Path(decode_oracle.__file__).read_text()
    predicted = {}
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant_' + label}; exec(compile(text.replace(before, after), 'oracle-variant:' + label, 'exec'), ns)
        try:
            vrows = [row for st in ns['run'](case)['steps'] for row in st['rows']]
            err = max(abs(a - b) for vr, er in zip(vrows, rows) for a, b in zip(vr['output'], er['output']))
            steps_changed = [vr['time'] for vr, er in zip(vrows, rows) if max(abs(a - b) for a, b in zip(vr['output'], er['output'])) > allowance]
            predicted[label] = ('KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL', err, steps_changed)
        except (ValueError, IndexError) as exc:
            predicted[label] = ('KILL', 'rejected:' + type(exc).__name__ + ':' + str(exc), None)
    matrix = {'schema': 'flash-sparse-decode-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': [case['fixture_id']], 'kill_margin_factor': factor, 'cell_scope': 'maximum over all decode steps of the output error',
              'matrix': {k: [v[0]] for k, v in predicted.items()}, 'predicted_oracle_variant_error': {k: [v[1]] for k, v in predicted.items()},
              'predicted_steps_changed': {k: v[2] for k, v in predicted.items()},
              'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants},
              'reasoning': {
                  'incremental-suffix-offset-omitted': 'suffix pools carry indices relative to s0 instead of absolute: selecting a suffix pool attends to the wrong tokens',
                  'stale-partial-pool-kept': 'the trailing partial pool is treated as stable, so the token that completes it is never pooled and stays unreachable except through the tail',
                  'stable-pools-recomputed': 'recomputing one extra complete pool reproduces it exactly: a designed inactive control',
                  'incremental-path-disabled': 'full pooling at every step gives the same pools: a designed inactive control (the equivalence the fixture proves)',
                  'decode-selection-mask-ignored': 'the -1 padding slots are clipped to position 0 upstream; without the selection mask they attend to token 0',
                  'decode-unembed-omitted': 'the absorbed decode output is a latent mixture until unembed_out; kv_lora_rank == v_head_dim here so the shape is legal and the values are wrong',
                  'latent-cache-not-fetched': 'only the current latent is visible, every selected index clips onto it and the row attends to itself',
              }}
    doc = {'schema': 'flash-sparse-decode-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_sparse_decode/oracle.py',
           'prefill_reference': 'scripts/research/glm53_flash/decoder_sparse/oracle.py',
           'tolerances': {'qr': 1e-4, 'kv_latent': 1e-4, 'attention_concat': 1e-4, 'output': 1e-4, 'pool_keys': 1e-4},
           'generator': {'seed': hex(SEED), 'margin': MARGIN, 'attempt': attempt, 'selection_margins': margins},
           'cases': [case], 'expected': {case['fixture_id']: expected}, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    print('attempt', attempt, 'margins', [round(m, 4) for m in margins])
    for st in r['steps']:
        for row in st['rows']:
            print(f"  {st['kind']:8s} t={row['time']} {row['regime']:7s} {row.get('pooling', ''):12s} topk={row['topk']} allowed={row['allowed']}")
    for k, v in predicted.items():
        print(f'  {k:36s} {v[0]:9s} {v[1] if isinstance(v[1], str) else round(v[1], 5)} steps {v[2]}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-sparse-decode-v1/fixtures.json')

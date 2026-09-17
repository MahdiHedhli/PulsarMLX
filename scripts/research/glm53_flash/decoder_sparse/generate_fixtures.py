#!/usr/bin/env python3
"""Deterministic sparse-attention fixtures frozen by the oracle before observation.

Tiny NoPE-MLA geometry with the lightning indexer at kpool 2 / topk 4. Case A
(S=4) sits inside the bypass (S <= index_topk): dense causal MLA. Case B (S=7)
exercises pooling with a partial trailing pool, top-2-of-3 pool selection and
the always-select-tail path. Cases are generated until every query position
with more candidates than select_k has a selection margin >= MARGIN.
"""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_sparse import oracle  # noqa: E402

SEED = 0x20260917A1
MARGIN = 2e-2
CONFIG = {'hidden_size': 8, 'num_attention_heads': 2, 'q_lora_rank': 4, 'kv_lora_rank': 4, 'qk_nope_head_dim': 4,
          'v_head_dim': 4, 'qk_rope_head_dim': 0, 'mla_use_nope': True, 'attention_bias': False, 'rms_norm_eps': 1e-5,
          'index_n_heads': 2, 'index_head_dim': 4, 'index_topk': 4, 'index_kpool': 2, 'index_kpool_always_select_tail': True}


def f32(v):
    return struct.unpack('f', struct.pack('f', v))[0]


def mat(rng, rows, cols, scale):
    return [[f32(rng.uniform(-scale, scale)) for _ in range(cols)] for _ in range(rows)]


def weights(rng, c):
    H, dq, dv, qr, kvr, nI, di, kp = (c[k] for k in ('hidden_size', 'qk_nope_head_dim', 'v_head_dim', 'q_lora_rank', 'kv_lora_rank',
                                                    'index_n_heads', 'index_head_dim', 'index_kpool'))
    heads = c['num_attention_heads']
    return {'q_a_proj': mat(rng, qr, H, .6), 'q_a_layernorm': [f32(rng.uniform(.7, 1.3)) for _ in range(qr)],
            'q_b_proj': mat(rng, heads * dq, qr, .8), 'kv_a_proj_with_mqa': mat(rng, kvr, H, .6),
            'kv_a_layernorm': [f32(rng.uniform(.7, 1.3)) for _ in range(kvr)],
            'embed_q': [mat(rng, kvr, dq, .7) for _ in range(heads)], 'unembed_out': [mat(rng, dv, kvr, .7) for _ in range(heads)],
            'o_proj': mat(rng, H, heads * dv, .5)}


def indexer_weights(rng, c):
    H, qr, nI, di, kp = (c[k] for k in ('hidden_size', 'q_lora_rank', 'index_n_heads', 'index_head_dim', 'index_kpool'))
    return {'wq_b': mat(rng, nI * di, qr, .8), 'wk': mat(rng, di, H, .6), 'k_norm_weight': [f32(rng.uniform(.7, 1.3)) for _ in range(di)],
            'k_norm_bias': [f32(rng.uniform(-.2, .2)) for _ in range(di)], 'weights_proj': mat(rng, nI, H, .8),
            'compress_ape': mat(rng, kp, di, .5), 'compress_gate': mat(rng, di, H, .5)}


def main(out):
    rng = random.Random(SEED)
    cases, expected, attempts = [], {}, {}
    for fixture_id, S in (('sparse-bypass-s4', 4), ('sparse-kpool2-topk4-s7', 7)):
        for attempt in range(1, 10001):
            case = {'fixture_id': fixture_id, 'config': dict(CONFIG), 'tokens': S, 'x': mat(rng, S, CONFIG['hidden_size'], 1.0),
                    'weights': weights(rng, CONFIG), 'indexer': indexer_weights(rng, CONFIG), 'generator': {'seed': hex(SEED), 'attempt': attempt}}
            r = oracle.run(case)
            margins = [m for m in (r['selection_margins'] or []) if m is not None]
            if all(m >= MARGIN for m in margins):
                cases.append(case); expected[fixture_id] = r; attempts[fixture_id] = attempt
                break
        else:
            raise SystemExit('no admissible ' + fixture_id)
    # Every cell is filled prospectively from the frozen oracle: the equivalent mutation is
    # applied to the oracle text (never to the candidate), evaluated on the frozen cases and
    # classified with the controls' thresholds. A NaN/empty attention row counts as a kill.
    allowance, factor = 1e-4, 10
    variants = {
        'indexer-scale-omitted': ("max(_dot(q[t][h], pools[p]['key']) * scale, 0.0)", "max(_dot(q[t][h], pools[p]['key']), 0.0)"),
        'indexer-relu-omitted': ("max(_dot(q[t][h], pools[p]['key']) * scale, 0.0)", "_dot(q[t][h], pools[p]['key']) * scale"),
        'tail-selection-omitted': ("        if cfg['index_kpool_always_select_tail'] and kp > 1:\n            visible_count", "        if False:\n            visible_count"),
        'kv-latent-norm-omitted': ("latent = [rmsnorm(_proj(xt, w['kv_a_proj_with_mqa']), w['kv_a_layernorm'], eps) for xt in x]", "latent = [_proj(xt, w['kv_a_proj_with_mqa']) for xt in x]"),
        'sparse-mask-ignored': ("allowed = [j for j in range(t + 1)] if bypass else index_rows[t]['allowed']", "allowed = [j for j in range(t + 1)]"),
        'embed-transpose-wrong': ("[w['embed_q'][h][r][d] for r in range(len(latent[t]))]", "[w['embed_q'][h][d][r] for r in range(len(latent[t]))]"),
    }
    text = Path(oracle.__file__).read_text()
    def classify(label, case):
        before, after = variants[label]; assert text.count(before) == 1, label
        ns = {'__name__': 'oracle_variant_' + label}; exec(compile(text.replace(before, after), 'oracle-variant:' + label, 'exec'), ns)
        try:
            out = ns['run'](case)['output']
        except AssertionError as exc:  # empty attention row
            return 'KILL', 'rejected:' + str(exc)
        exp = expected[case['fixture_id']]['output']
        err = max(abs(a - b) for ra, rb in zip(out, exp) for a, b in zip(ra, rb))
        return ('KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL'), err
    predicted = {label: [classify(label, c) for c in cases] for label in variants}
    matrix = {
        'schema': 'flash-sparse-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
        'fixtures': [c['fixture_id'] for c in cases], 'kill_margin_factor': factor,
        'matrix': {label: [cell for cell, _ in cells] for label, cells in predicted.items()},
        'predicted_oracle_variant_error': {label: [e if isinstance(e, str) else e for _, e in cells] for label, cells in predicted.items()},
        'oracle_variants': {label: {'before': b, 'after': a} for label, (b, a) in variants.items()},
        'needle_counts': {label: 1 for label in variants},
        'reasoning': {
            'indexer-scale-omitted': 'relu(s*c) = c*relu(s) for c > 0, so a positive scale never changes pool ordering: designed INACTIVE control (bypass on A)',
            'indexer-relu-omitted': 'bypass on A; on B negative head scores can change the weighted pool ordering',
            'tail-selection-omitted': 'bypass on A; on B t=0 reaches itself only through the tail (empty row without it) and t=6 reaches token 6 only through the tail',
            'kv-latent-norm-omitted': 'the latent feeds keys and values on every path; skipping its RMSNorm changes them',
            'sparse-mask-ignored': 'bypass on A; on B a visible complete pool is not selected at t>=5 (top-2 of 3), so dense causal attention adds keys',
            'embed-transpose-wrong': 'kv_lora_rank == qk_nope_head_dim here, so the transposed multiply is shape-legal but uses W^T: wrong keys on every path',
        },
    }
    doc = {'schema': 'flash-sparse-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_sparse/oracle.py',
           'tolerances': {'qr': 1e-4, 'kv_latent': 1e-4, 'attention_concat': 1e-4, 'output': 1e-4},
           'generator': {'seed': hex(SEED), 'margin': MARGIN, 'attempts': attempts},
           'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]
        print(c['fixture_id'], 'bypass' if e['bypass'] else 'sparse', 'attempt', attempts[c['fixture_id']],
              'allowed' if e['bypass'] else e['allowed'], 'margins', None if e['bypass'] else [round(m, 4) if m else m for m in e['selection_margins']])
    for label, cells in matrix['matrix'].items():
        print(f"  {label:26s} {cells} {[round(e, 5) if not isinstance(e, str) else e for e in matrix['predicted_oracle_variant_error'][label]]}")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-sparse-v1/fixtures.json')

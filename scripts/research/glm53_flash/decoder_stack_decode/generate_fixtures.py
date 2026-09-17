#!/usr/bin/env python3
"""Stack decode fixture: the graph-11 stack case re-sliced into prefill [ids[:2]] + two decode steps, frozen before observation."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_stack import generate_fixtures as stack_generator  # noqa: E402
from scripts.research.glm53_flash.decoder_stack import oracle as stack_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_stack_decode import oracle as decode_oracle  # noqa: E402

STACK_FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json'
REFS = {**stack_generator.REFS, 'stack_run': stack_oracle.run}


def main(out_path):
    stack = json.loads(STACK_FIXTURE.read_bytes())
    base = stack['cases'][0]
    case = {**base, 'fixture_id': 'stack-decode-prefill2-decode2', 'prefill_tokens': 2,
            'config': {**base['config'], 'linear_cache_slots': 2}, 'cache_routing': ['ArraysCache', 'CacheList'],
            'derived_from': {'fixture': 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json', 'case': base['fixture_id']}}
    expected = decode_oracle.run(case, REFS)
    for t, row in enumerate(expected['logits']):
        assert row == stack['expected'][base['fixture_id']]['logits'][t]
    allowance, factor = 1e-4, 10
    variants = {
        'compile-gate-forced-eager': ("'compiled_ffn_used': True", "'compiled_ffn_used': False"),
        'compile-cache-not-reused': ("'kv_offset_after': t + 1, 'compiled_ffn_used'", "'kv_offset_after': t + 1, 'recompiled_each_step': True, 'compiled_ffn_used'"),
        'layer-cache-dropped': ("        steps.append({'kind': 'decode', 'tokens': [t], 'mask': None, 'ssm_mask': None, 'logits': [full['logits'][t]],",
                                "        alone = refs['stack_run']({**case, 'ids': [case['ids'][t]]}, refs)\n        steps.append({'kind': 'decode', 'tokens': [t], 'mask': None, 'ssm_mask': None, 'logits': [alone['logits'][0]],"),
        'norm-before-mean': ("    final = [[r for r in row] for row in full['logits']]",
                             "    import math\n    def rn(x, w, eps):\n        r = 1.0 / math.sqrt(math.fsum(v * v for v in x) / len(x) + eps)\n        return [v * r * g for v, g in zip(x, w)]\n"
                             "    per_stream = [[rn(s, case['norm_weight'], cfg['rms_norm_eps']) for s in streams] for streams in full['layer1_output']]\n"
                             "    mixed = [[math.fsum(ps[h][d] for h in range(H)) / H for d in range(D)] for ps in per_stream]\n"
                             "    final = [[math.fsum(w * v for w, v in zip(row, m)) for row in case['lm_head']] for m in mixed]\n"
                             "    for st in steps:\n        st['logits'] = [final[t] for t in st['tokens']]"),
        'cache-list-misrouted': ("    if routing != case['cache_routing']:", "    if list(reversed(routing)) != case['cache_routing']:"),
        'make-cache-linear-size-1': ("    if linear_slots != 2:", "    if linear_slots != 1:"),
    }
    text = Path(decode_oracle.__file__).read_text()
    predicted = {}
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant_' + label}; exec(compile(text.replace(before, after), 'oracle-variant:' + label, 'exec'), ns)
        try:
            v = ns['run'](case, REFS)
            rows = [(t, lg) for st in v['steps'] for t, lg in zip(st['tokens'], st['logits'])]
            per_step = {t: max(abs(a - b) for a, b in zip(lg, expected['logits'][t])) for t, lg in rows}
            err = max(per_step.values())
            predicted[label] = ('KILL' if err >= factor * allowance else 'INACTIVE' if err <= allowance else 'WEAK_STRUCTURAL', err,
                                [t for t, e in per_step.items() if e > allowance])
        except ValueError as exc:
            predicted[label] = ('KILL', 'rejected:' + str(exc), None)
    matrix = {'schema': 'flash-stack-decode-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': [case['fixture_id']], 'kill_margin_factor': factor, 'cell_scope': 'maximum logits error over the schedule',
              'matrix': {k: [v[0]] for k, v in predicted.items()}, 'predicted_oracle_variant_error': {k: [v[1]] for k, v in predicted.items()},
              'predicted_steps_changed': {k: v[2] for k, v in predicted.items()},
              'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants},
              'reasoning': {
                  'compile-gate-forced-eager': 'the reference has no compile distinction; eager and compiled FFN blocks must agree: designed inactive control',
                  'compile-cache-not-reused': 'recompiling every step changes nothing numerically: designed inactive control',
                  'layer-cache-dropped': 'without caches each decode token is processed as a fresh single-token sequence: the recurrent state and the attended positions are lost',
                  'norm-before-mean': 'normalising each residual stream before averaging differs from normalising the mean',
                  'cache-list-misrouted': 'the linear layer receives the CacheList and the sparse layer the ArraysCache: a type mismatch (the reference models routing explicitly)',
                  'make-cache-linear-size-1': 'the linear attention writes two slots; a one-slot ArraysCache cannot hold them (the reference models the slot count explicitly)',
              }}
    doc = {'schema': 'flash-stack-decode-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_stack_decode/oracle.py',
           'stack_reference': 'scripts/research/glm53_flash/decoder_stack/oracle.py',
           'tolerances': {'logits': 1e-4, 'cache0_atol': 1e-4, 'cache0_rtol': 1e-5, 'cache1_atol': 1e-4, 'cache1_rtol': 1e-5},
           'cases': [case], 'expected': {case['fixture_id']: expected}, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    for st in expected['steps']:
        print(f"  {st['kind']:8s} tokens={st['tokens']} mask={st['mask']} kv_offset_after={st['kv_offset_after']} compiled={st['compiled_ffn_used']}")
    for k, v in predicted.items():
        print(f'  {k:28s} {v[0]:9s} {v[1] if isinstance(v[1], str) else round(v[1], 5)} steps {v[2]}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-stack-decode-v1/fixtures.json')

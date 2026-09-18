#!/usr/bin/env python3
"""Slot-store fixture v2 (graph 33): the production paths the inherited cases never reach.

Twelve stdlib-quantized experts (hidden 32, intermediate 32, group 32; the reference is the graph-15 binary64
dequantization + the graph-9 activation), top-8 routing over 24 tokens, a shared seeded schedule with calls of 7 / 8 / 9
tokens (56 / 64 / 72 (token, k) indices: below / at / above the runtime's sort threshold of 64) and single-token calls,
capacity 6 (budget = 6 expert bytes, so a 9-token call needs two waves), three quantizations of the same weights:
4-bit with float32 scales, 8-bit with float32 scales, 4-bit with bfloat16 scales and bfloat16 activations (x rounded to
bf16-representable values; explicit tolerance 5e-2 vs 1e-4 for float32). The schedule search requires, for the shared
routing: at least one call of each index count, evictions, a two-wave call, a wave with >= 4 cold experts (hash-layout
bulk mx.load path) and one with 1-3 (preadv pool), a wave whose cold experts merge into >= 2 disjoint coalesced runs on
the contiguous layout, and a run spanning several read chunks (chunk 4096 bytes in the controls). Expected: the slot
model's values / policy / slot maps (oracle.run) and the cumulative read-path counters per call (oracle.predict_paths)
the runtime must report - matching outputs alone cannot show a branch ran. Mutants: the four policy variants predicted
from the oracle, seven structural mutants by construction (three of them - sort-threshold-raised, bulk-threshold-
ignored, coalesce-gap-ignored - change no value and are killed only by the counters).
"""
import json
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_slot_store import oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_slot_store.generate_fixtures import VARIANTS, predicted_cells  # noqa: E402
from scripts.research.glm53_flash.decoder_quantized.generate_fixtures import f32, mat, quantize_rows  # noqa: E402

SEED = 0x20260918A3
E, D, I, T, K, G = 12, 32, 32, 24, 8, 32
CAPACITY = 6
RUNTIME = {'read_chunk_bytes': 4096, 'bulk_min': 4, 'coalesce_gap_experts': 2, 'sort_threshold': 64}
TOL = {'float32': 1e-4, 'bfloat16': 5e-2}
STRUCTURAL = {
    'unsort-omitted': {'expected_reason': 'value', 'kills_on': 'every call with >= 64 indices: rows stay in sorted order'},
    'inverse-permutation-wrong': {'expected_reason': 'value', 'kills_on': 'every call with >= 64 indices: order used as its own inverse'},
    'sort-threshold-raised': {'expected_reason': 'counter', 'kills_on': 'sorted_gathers stays 0 on the >= 64-index calls (values unchanged: the sort is an optimization)'},
    'slot-map-off-by-one': {'expected_reason': 'value', 'kills_on': 'the first call: every token reads the next slot (in bounds; another expert or zeros)'},
    'chunk-boundary-off-by-one': {'expected_reason': 'value', 'kills_on': 'the contiguous forced-cold pass: one byte per chunk is skipped, tensors read garbage'},
    'bulk-threshold-ignored': {'expected_reason': 'counter', 'kills_on': 'the hash forced-cold pass: bulk_reads stays 0, pool_reads takes every cold expert (values unchanged)'},
    'coalesce-gap-ignored': {'expected_reason': 'counter', 'kills_on': 'the contiguous forced-cold pass: every wave becomes one run (coalesced_ranges, overread_bytes, chunks_read differ; values unchanged)'},
}


def bf16(v):
    """Round a float to the nearest bfloat16 (round-to-nearest-even on the f32 bit pattern); returns a float."""
    bits = struct.unpack('<I', struct.pack('<f', v))[0]
    lsb = (bits >> 16) & 1
    bits = (bits + 0x7FFF + lsb) & 0xFFFF0000
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def quantize_experts(fp32, bits, group, scales_dtype):
    q = {}
    for p in fp32:
        packed = [quantize_rows(e, bits, group) for e in fp32[p]]
        packs = []
        for pk, _ in packed:
            if scales_dtype == 'bfloat16':
                pk = {'words': pk['words'], 'scales': [[bf16(s) for s in row] for row in pk['scales']], 'biases': [[bf16(b) for b in row] for row in pk['biases']]}
            packs.append(pk)
        q[p] = packs
    return q


def reachability(exp, nbytes):
    """The schedule constraints, from the fault-free expectation."""
    idx_counts = {len(c['tokens']) * K for c in exp['calls']}
    ok = {'below_at_above_sort': {56, 64, 72} <= idx_counts, 'evictions': exp['final_stats']['evictions'] > 0,
          'two_waves': any(len(c['waves']) > 1 for c in exp['calls']), 'bulk_wave': False, 'pool_wave': False, 'two_runs_wave': False, 'multi_chunk_run': False}
    for c in exp['calls']:
        for wr in c['wave_reads']:
            if len(wr) >= RUNTIME['bulk_min']:
                ok['bulk_wave'] = True
            if 1 <= len(wr) < RUNTIME['bulk_min']:
                ok['pool_wave'] = True
            runs = oracle.merge_runs(wr, RUNTIME['coalesce_gap_experts'])
            if len(runs) >= 2:
                ok['two_runs_wave'] = True
            if any((b - a + 1) * nbytes > RUNTIME['read_chunk_bytes'] for a, b, _ in runs):
                ok['multi_chunk_run'] = True
    return ok


def main(out_path):
    rng = random.Random(SEED)
    fp32 = {'gate': [mat(rng, I, D, .25) for _ in range(E)], 'up': [mat(rng, I, D, .25) for _ in range(E)], 'down': [mat(rng, D, I, .25) for _ in range(E)]}
    x32 = mat(rng, T, D, 1.0)
    indices = [sorted(rng.sample(range(E), K)) for _ in range(T)]
    specs = [('slot2-4bit-g32-f32', 4, 'float32'), ('slot2-8bit-g32-f32', 8, 'float32'), ('slot2-4bit-g32-bf16', 4, 'bfloat16')]
    quantized = {fid: quantize_experts(fp32, bits, G, sd) for fid, bits, sd in specs}
    base_cfg = {'group_size': G, 'num_experts': E, 'hidden': D, 'intermediate': I, 'swiglu_limit': 1.0}

    def make_case(fid, bits, sd, schedule, policy):
        cfg = {**base_cfg, 'bits': bits, 'scales_dtype': sd, 'activation_dtype': sd}
        x = x32 if sd == 'float32' else [[bf16(v) for v in row] for row in x32]
        return {'fixture_id': fid, 'config': cfg, 'x': x, 'indices': indices, 'quantized': quantized[fid], 'schedule': schedule, 'policy': policy,
                'budget_bytes': CAPACITY * oracle.expert_bytes_v2(cfg), 'layer_id': 0, 'tolerance': TOL[sd], 'generator': {'seed': hex(SEED)}}

    sizes = [7, 8, 9, 1, 9, 1, 2, 8]
    for attempt in range(1, 20001):
        schedule = [{'tokens': sorted(rng.sample(range(T), n))} for n in sizes]
        policy = {'decay': 0.5, 'decay_every': rng.choice([5, 7, 9, 11])}
        probe = make_case(*specs[0], schedule, policy)
        exp = oracle.run(probe)
        ok = reachability(exp, oracle.expert_bytes_v2(probe['config']))
        if not all(ok.values()):
            continue
        cases = [make_case(fid, bits, sd, schedule, policy) for fid, bits, sd in specs]
        expected = {c['fixture_id']: oracle.run(c) for c in cases}
        predicted = predicted_cells(cases, expected, VARIANTS, Path(oracle.__file__).read_text())
        if all(cell == 'KILL' for v in predicted.values() for cell in v):
            break
    else:
        raise SystemExit('no schedule satisfies the reachability constraints and kills every policy variant')
    for c in cases:
        expected[c['fixture_id']]['paths'] = oracle.predict_paths(c, expected[c['fixture_id']], RUNTIME)
        expected[c['fixture_id']]['reachability'] = reachability(expected[c['fixture_id']], oracle.expert_bytes_v2(c['config']))
    for label in STRUCTURAL:
        predicted[label] = ['KILL' for _ in cases]
    matrix = {'schema': 'flash-slot-store-v2-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'schedule_search': {'seed': hex(SEED), 'attempt': attempt, 'sizes': sizes, 'policy': policy}, 'fixtures': [c['fixture_id'] for c in cases],
              'cell_scope': 'per call: values within the case tolerance, stats and slot map vs the model, cumulative counters vs predict_paths on every pass; structural mutants by construction (value or counter)',
              'matrix': predicted, 'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in VARIANTS.items()}, 'needle_counts': {k: 1 for k in VARIANTS},
              'structural_mutants': STRUCTURAL, 'revision': 1}
    doc = {'schema': 'flash-slot-store-fixtures-v2/1', 'oracle': 'scripts/research/glm53_flash/decoder_slot_store/oracle.py', 'store': 'scripts/research/glm53_flash/dogfood/pulsar_slot_store.py',
           'runtime': RUNTIME, 'tolerances': TOL, 'cases': cases, 'expected': expected, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, sort_keys=True, separators=(',', ':')) + '\n')
    for c in cases:
        e = expected[c['fixture_id']]
        print(' ', c['fixture_id'], 'expert bytes', e['paths']['expert_bytes'], 'capacity', e['capacity'], 'final', e['final_stats'], 'last', e['paths']['per_call'][-1])
    print('  reachability', expected[cases[0]['fixture_id']]['reachability'], 'attempt', attempt)
    for k, v in predicted.items():
        print(f'  {k:28s} {v}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-slot-store-v2/fixtures.json')

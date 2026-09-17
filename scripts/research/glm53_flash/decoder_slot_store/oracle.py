"""Stdlib policy + slot model for PulsarSlotStore / PulsarSwitchGLU (graph 24).

Per MoE layer the store holds C slots (C = budget_bytes // expert_bytes). A call touches the sorted unique experts of
its tokens; unlike graph 21 there is no bulk bypass (prefill goes through the same path) and every call must see all
of its experts resident at once for the gather over the slots, so a call is processed in WAVES of at most C experts
(sorted order): within a wave every expert is counted once (count += 1, touch = ordinal; every `decay_every` accesses
all counts are multiplied by `decay`), a hit keeps its slot, a miss takes a free slot or else the slot of the victim
with the smallest (count, touch) among residents NOT in the current wave (pinned). Reads = misses. Warm state: counts
and the resident set; a fresh store re-admits most-frequent first into slots 0.. in that order. Values are graph 18's
(the same expert arithmetic over the same frozen arrays; the wave split does not change them).
"""
from scripts.research.glm53_flash.decoder_offload import oracle as base

_VALUES = {}   # the expert arithmetic does not depend on the schedule or the policy: memoized per fixture arrays


def _values(case):
    key = (case['fixture_id'], id(case['quantized']))
    if key not in _VALUES:
        cfg = case['config']
        _VALUES[key] = base.quantized.switch_experts({'config': cfg, 'x': case['x'], 'indices': case['indices'], 'quantized': case['quantized']})
    return _VALUES[key]


def run(case):
    cfg = case['config']; nbytes = base.expert_bytes(cfg)
    values = _values(case)
    decay, decay_every, budget = case['policy']['decay'], case['policy']['decay_every'], case['budget_bytes']
    capacity = budget // nbytes
    if capacity < 1:
        raise ValueError('CAPACITY_ZERO')
    counts, touch, slot_of = {}, {}, {}
    free = list(range(capacity))
    accesses = hits = misses = evictions = 0
    calls = []
    for call in case['schedule']:
        tokens = call['tokens']
        uniq = sorted({j for t in tokens for j in case['indices'][t]})
        waves = [uniq[i:i + capacity] for i in range(0, len(uniq), capacity)]
        reads = []
        for wave in waves:
            pinned = set(wave)
            for j in wave:
                accesses += 1; counts[j] = counts.get(j, 0.0) + 1.0; touch[j] = accesses
                if accesses % decay_every == 0:
                    for k in list(counts):
                        counts[k] *= decay
                if j in slot_of:
                    hits += 1
                else:
                    misses += 1; reads.append(j)
                    if free:
                        s = free.pop(0)
                    else:
                        candidates = [k for k in slot_of if k not in pinned]
                        victim = min(candidates, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))
                        s = slot_of.pop(victim); evictions += 1
                    slot_of[j] = s
        rows = [[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))] for t in tokens]
        calls.append({'tokens': tokens, 'unique': uniq, 'waves': waves, 'reads': reads,
                      'stats': {'hits': hits, 'misses': misses, 'evictions': evictions, 'resident_experts': len(slot_of), 'resident_bytes': len(slot_of) * nbytes},
                      'resident_set': sorted(slot_of), 'slot_of': {str(k): v for k, v in sorted(slot_of.items())},
                      'counts': {str(k): round(v, 6) for k, v in sorted(counts.items())}, 'outputs': rows})
    warm_order = sorted(slot_of, key=lambda j: -counts.get(j, 0.0))[:capacity]
    return {'expert_bytes': nbytes, 'capacity': capacity, 'calls': calls, 'final_stats': calls[-1]['stats'],
            'warm_state': {'resident': sorted(slot_of), 'admitted_on_restart': warm_order, 'slot_on_restart': {str(j): i for i, j in enumerate(warm_order)}, 'accesses': accesses}}

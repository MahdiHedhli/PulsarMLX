"""Stdlib policy + slot model for PulsarSlotStore / PulsarSwitchGLU (graph 24).

Per MoE layer the store holds C slots (C = budget_bytes // expert_bytes). A call touches the sorted unique experts of
its tokens; unlike graph 21 there is no bulk bypass (prefill goes through the same path) and every call must see all
of its experts resident at once for the gather over the slots, so a call is processed in WAVES of at most C experts
(sorted order): within a wave every expert is counted once (count += 1, touch = ordinal; every `decay_every` accesses
all counts are multiplied by `decay`), a hit keeps its slot, a miss takes a free slot or else the slot of the victim
with the smallest (count, touch) among residents NOT in the current wave (pinned). Reads = misses. Warm state: counts
and the resident set; a fresh store re-admits most-frequent first into slots 0.. in that order. Values are graph 18's
(the same expert arithmetic over the same frozen arrays; the wave split does not change them).

Graph 31 (residency committed after materialization): a miss RESERVES its slot; the victim is evicted from the published
map at touch time (its bytes are about to be overwritten); the reservation becomes residency only after every part of
every reserved expert has been materialized. A fault in the READ phase (before the first write) drops the reservations,
returns the reserved slots to the FRONT of the free list in reservation order and raises; the call is retried whole:
waves already filled are hits, the failed wave is touched again (counts and accesses advance twice, so the decay clock
does too), its misses take the same slots back (no second eviction). A fault in the WRITE/EVAL phase poisons the store:
every later call is rejected (STORE_POISONED); nothing is compared after it. run_with_fault models the read-phase case.
"""
from scripts.research.glm53_flash.decoder_offload import oracle as base

_VALUES = {}   # the expert arithmetic does not depend on the schedule or the policy: memoized per fixture arrays


def _values(case):
    key = (case['fixture_id'], id(case['quantized']))
    if key not in _VALUES:
        cfg = case['config']
        _VALUES[key] = base.quantized.switch_experts({'config': cfg, 'x': case['x'], 'indices': case['indices'], 'quantized': case['quantized']})
    return _VALUES[key]


def run(case, fault=None):
    """fault = {'call': c, 'wave': w} models a read-phase fault on wave w of call c (the first attempt raises, the call
    is retried whole); the failing call's record carries 'after_fault' (stats and slot map observed after the raise)
    and 'attempts': 2. Without a fault this is the graph-24 model unchanged."""
    cfg = case['config']; nbytes = base.expert_bytes(cfg)
    values = _values(case)
    decay, decay_every, budget = case['policy']['decay'], case['policy']['decay_every'], case['budget_bytes']
    capacity = budget // nbytes
    if capacity < 1:
        raise ValueError('CAPACITY_ZERO')
    counts, touch, slot_of = {}, {}, {}
    free = list(range(capacity))
    accesses = hits = misses = evictions = 0
    fill_failures = 0
    calls = []

    def touch_wave(wave):
        """Policy for one wave: returns [(expert, slot)] reservations (victims already evicted from slot_of)."""
        nonlocal accesses, hits, misses, evictions
        pinned = set(wave); reserved = []
        for j in wave:
            accesses += 1; counts[j] = counts.get(j, 0.0) + 1.0; touch[j] = accesses
            if accesses % decay_every == 0:
                for k in list(counts):
                    counts[k] *= decay
            if j in slot_of:
                hits += 1
            else:
                misses += 1
                if free:
                    s = free.pop(0)
                else:
                    candidates = [k for k in slot_of if k not in pinned]
                    victim = min(candidates, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))
                    s = slot_of.pop(victim); evictions += 1
                reserved.append((j, s))
        return reserved

    def stats():
        return {'hits': hits, 'misses': misses, 'evictions': evictions, 'resident_experts': len(slot_of), 'resident_bytes': len(slot_of) * nbytes}

    for ci, call in enumerate(case['schedule']):
        tokens = call['tokens']
        uniq = sorted({j for t in tokens for j in case['indices'][t]})
        waves = [uniq[i:i + capacity] for i in range(0, len(uniq), capacity)]
        reads = []; after_fault = None; attempts = 1; wave_evictions = []
        for wi, wave in enumerate(waves):
            ev0 = evictions
            reserved = touch_wave(wave)
            wave_evictions.append(evictions - ev0)
            if fault is not None and fault['call'] == ci and fault['wave'] == wi:
                # read-phase fault: reservations dropped, slots back to the front of the free list, the call raises
                free[0:0] = [s for _, s in reserved]; fill_failures += 1
                after_fault = {'stats': stats(), 'slot_of': {str(k): v for k, v in sorted(slot_of.items())}, 'fill_failures': fill_failures}
                attempts = 2
                reserved = touch_wave(wave)          # the retry touches the failed wave again (earlier waves are hits)
            for j, s in reserved:
                slot_of[j] = s                       # commit after materialization
            reads.extend(j for j, _ in reserved)
        rows = [[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))] for t in tokens]
        record = {'tokens': tokens, 'unique': uniq, 'waves': waves, 'reads': reads, 'wave_evictions': wave_evictions, 'stats': stats(),
                  'resident_set': sorted(slot_of), 'slot_of': {str(k): v for k, v in sorted(slot_of.items())},
                  'counts': {str(k): round(v, 6) for k, v in sorted(counts.items())}, 'outputs': rows}
        if after_fault is not None:
            record['after_fault'] = after_fault; record['attempts'] = attempts
        calls.append(record)
    warm_order = sorted(slot_of, key=lambda j: -counts.get(j, 0.0))[:capacity]
    out = {'expert_bytes': nbytes, 'capacity': capacity, 'calls': calls, 'final_stats': calls[-1]['stats'],
           'warm_state': {'resident': sorted(slot_of), 'admitted_on_restart': warm_order, 'slot_on_restart': {str(j): i for i, j in enumerate(warm_order)}, 'accesses': accesses}}
    if fault is not None:
        out['fault'] = dict(fault, fill_failures=fill_failures)
    return out


def fault_points(expected):
    """Where the fault tests inject: the first wave with a miss and the first wave with an eviction (fault-free run)."""
    points = {}
    for ci, c in enumerate(expected['calls']):
        for wi, wave in enumerate(c['waves']):
            if 'first-miss' not in points and any(j in c['reads'] for j in wave):
                points['first-miss'] = {'call': ci, 'wave': wi}
            if 'first-eviction' not in points and c['wave_evictions'][wi] > 0:
                points['first-eviction'] = {'call': ci, 'wave': wi}
    if len(points) != 2:
        raise ValueError('FAULT_POINTS_MISSING')
    return points

"""Stdlib policy model for PulsarExpertStore (LFU with periodic multiplicative decay, LRU tie-break) and its warm state.

Per call the module requests the sorted unique experts; bulk (get_all) when unique*2 > num_experts, no accounting.
Every get() counts the expert (count += 1, touch = ordinal) and, every `decay_every` accesses, multiplies all counts
by `decay`. A hit keeps residency; a miss evicts the resident with the smallest (count, touch) until the expert fits.
Warm state: the resident set and counts after the schedule; a fresh store re-admits residents most-frequent first
within the budget. Values are graph 18's (the same OffloadedSwitchGLU over the same frozen arrays).
Graph 22: each call also records whether it evicted (`evicted`) and the running count of evicting gets (`eviction_events`:
a miss that evicted at least one resident is one event, however many it evicted). The store clears the allocator cache
after such a get only when the cache is at or above its threshold, so under threshold 0 its cache_clears must equal
eviction_events and under a bound the tiny fixtures never reach it must be 0.
"""
from scripts.research.glm53_flash.decoder_offload import oracle as base


def run(case):
    cfg = case['config']; E = cfg['num_experts']; nbytes = base.expert_bytes(cfg)
    values = base.quantized.switch_experts({'config': cfg, 'x': case['x'], 'indices': case['indices'], 'quantized': case['quantized']})
    decay, decay_every, budget = case['policy']['decay'], case['policy']['decay_every'], case['budget_bytes']
    counts, touch, resident = {}, {}, {}
    accesses = hits = misses = evictions = eviction_events = 0
    calls = []
    for call in case['schedule']:
        tokens = call['tokens']
        uniq = sorted({j for t in tokens for j in case['indices'][t]})
        bulk = len(uniq) * 2 > E
        evicted_before = evictions
        if not bulk:
            for j in uniq:
                accesses += 1; counts[j] = counts.get(j, 0.0) + 1.0; touch[j] = accesses
                if accesses % decay_every == 0:
                    for k in list(counts):
                        counts[k] *= decay
                if j in resident:
                    hits += 1
                else:
                    misses += 1
                    evicted_by_get = 0
                    while resident and sum(resident.values()) + nbytes > budget:
                        victim = min(resident, key=lambda k: (counts.get(k, 0.0), touch.get(k, 0)))
                        del resident[victim]; evictions += 1; evicted_by_get += 1
                    eviction_events += int(evicted_by_get > 0)
                    resident[j] = nbytes
        evicted = evictions > evicted_before
        rows = [[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))] for t in tokens]
        calls.append({'tokens': tokens, 'unique': uniq, 'bulk': bulk, 'evicted': evicted, 'eviction_events': eviction_events,
                      'stats': {'hits': hits, 'misses': misses, 'evictions': evictions, 'resident_experts': len(resident), 'resident_bytes': sum(resident.values())},
                      'resident_set': sorted(resident), 'counts': {str(k): round(v, 6) for k, v in sorted(counts.items())}, 'outputs': rows})
    warm_order = sorted(resident, key=lambda j: -counts.get(j, 0.0))
    warm_admitted, used = [], 0
    for j in warm_order:
        if used + nbytes > budget:
            break
        warm_admitted.append(j); used += nbytes
    return {'expert_bytes': nbytes, 'calls': calls, 'final_stats': calls[-1]['stats'], 'warm_state': {'resident': sorted(resident), 'admitted_on_restart': warm_admitted, 'accesses': accesses}}

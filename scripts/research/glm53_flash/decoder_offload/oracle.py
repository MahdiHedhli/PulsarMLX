"""Stdlib reference for the expert-offload path: values and cache policy.

Values: the graph-15 affine-dequantization reference over the same frozen
arrays (OffloadedSwitchGLU computes per selected expert exactly
down(activation(up(x), gate(x))) with quantized_matmul; the output row order
follows the indices). Cache policy: an explicit model of ExpertStore under a
byte budget - per call the module requests the sorted unique experts; when
unique*2 > num_experts it bulk-loads the layer (get_all: no LRU accounting),
otherwise get(layer, j) is a hit (moved to most-recent) or a miss (evict
least-recent until the expert fits, then insert). Expected after every call:
hits, misses, evictions, resident set, and the row outputs.
"""
from collections import OrderedDict

from scripts.research.glm53_flash.decoder_quantized import oracle as quantized


def expert_bytes(cfg):
    per_word = 32 // cfg['bits']; g = cfg['group_size']; D, I = cfg['hidden'], cfg['intermediate']
    def proj(out, inp):
        return out * (inp // per_word) * 4 + 2 * out * (inp // g) * 4
    return proj(I, D) + proj(I, D) + proj(D, I)


def run(case):
    cfg = case['config']; E = cfg['num_experts']; nbytes = expert_bytes(cfg)
    values = quantized.switch_experts({'config': cfg, 'x': case['x'], 'indices': case['indices'], 'quantized': case['quantized']})
    lru, resident = OrderedDict(), 0
    hits = misses = evictions = 0
    calls = []
    for call in case['schedule']:
        tokens = call['tokens']
        uniq = sorted({j for t in tokens for j in case['indices'][t]})
        bulk = len(uniq) * 2 > E
        if not bulk:
            for j in uniq:
                if j in lru:
                    lru.move_to_end(j); hits += 1
                else:
                    misses += 1
                    while lru and resident + nbytes > case['budget_bytes']:
                        lru.popitem(last=False); resident -= nbytes; evictions += 1
                    lru[j] = nbytes; resident += nbytes
        rows = [[values['tokens'][t][k]['output'] for k in range(len(case['indices'][t]))] for t in tokens]
        calls.append({'tokens': tokens, 'unique': uniq, 'bulk': bulk, 'stats': {'hits': hits, 'misses': misses, 'evictions': evictions,
                      'resident_experts': len(lru), 'resident_bytes': resident}, 'resident_order': list(lru), 'outputs': rows})
    return {'expert_bytes': nbytes, 'calls': calls, 'final_stats': calls[-1]['stats']}

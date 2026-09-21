"""Long-sequence reference for the linear attention module by chunked composition of the accepted reference.

The accepted reference (linear_attention.oracle.module_reference) has a finite
domain of at most 5 tokens per call and self-refuses when its error radii
exceed its tolerance. A sequence of S tokens is processed as consecutive
chunks of at most CHUNK tokens; the reference's cache0 (convolution history)
and cache1 (recurrent state) after each chunk are rounded to float32 (the
declared cast point: the reference requires fp32-dyadic external inputs, and
the candidate's cache is float32) and fed to the next chunk. Per-chunk
maximum radii and cache states are recorded. The reference's text and domain
are not touched.
"""
import struct

from scripts.research.glm53_flash.linear_attention import oracle as accepted
from scripts.research.glm53_flash.recurrent_dispatch import oracle as recurrence

CHUNK = 5


def fp32(v):
    return [fp32(x) for x in v] if isinstance(v, list) else struct.unpack('f', struct.pack('f', v))[0]


def run(case):
    S = len(case['inputs']); cfg = case['config']; params = case['parameters']
    chunks = [list(range(i, min(i + CHUNK, S))) for i in range(0, S, CHUNK)]
    c0 = c1 = None
    outputs, chunk_records, events = [], [], []
    for ci, chunk in enumerate(chunks):
        ref_case = {'B': 1, 'S': len(chunk), 'config': cfg, 'parameters': params, 'inputs': [[case['inputs'][t] for t in chunk]],
                    'mask': None, 'cache0': c0, 'cache1': c1, 'initial_lengths': [len(chunk)], 'initial_padding': [0], 'parts': [len(chunk)]}
        r = accepted.module_reference(ref_case, recurrence)
        outputs.extend(r['output'][0])
        c0, c1 = fp32(r['cache0']), fp32(r['cache1'])          # cast point at the carry
        chunk_records.append({'chunk': ci, 'tokens': chunk, 'maximum_radii': r['maximum_radii'], 'conditioning': r['conditioning'],
                              'cache0_after': c0, 'cache1_after': c1})
        for e in r['events']:
            events.append({'time': chunk[e['time']], 'cache0': e['cache0'], 'cache1': e['cache1'], 'radii': e['radii']})
    return {'output': outputs, 'final_cache0': c0, 'final_cache1': c1, 'chunks': chunk_records, 'events': events,
            'maximum_radii_over_chunks': {k: max(c['maximum_radii'][k] for c in chunk_records) for k in ('output', 'cache0', 'cache1')}}

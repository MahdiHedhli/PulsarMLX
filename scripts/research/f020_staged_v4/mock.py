"""Public independent CPU backend. No checker/source/owner module imports.

No native/model code, filesystem reading, real capability or attempt ledger.
This is a mock numerical producer, never a native qualification result.
"""
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import json
import struct

import f020_selected_fixtures_v2 as fixtures
from . import literals as O
from .protocol import Stage


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def packed(words):
    return b''.join(struct.pack('<I', v) for v in words)


def values(raw):
    return tuple(O.word_value(v[0]) for v in struct.iter_unpack('<I', raw))


def public_source(case='A', zero_row=None):
    """Original public synthetic generator, same full geometry/input as v3."""
    parts = []
    for role in ('gate', 'up', 'down'):
        n = 4096 if role == 'down' else 2048
        rows = [fixtures.row_bytes(case, role, row) for row in range(n)]
        if role == 'gate' and zero_row is not None:
            w, s, b = rows[zero_row]
            rows[zero_row] = (w, bytes(len(s)), bytes(len(b)))
        parts.extend(b''.join(row[i] for row in rows) for i in range(3))
    parts = tuple(parts)
    hashes = list(map(sha, parts))
    lengths = list(map(len, parts))
    prefix = 'language_model.model.layers.3.mlp.switch_mlp.'
    modules = [prefix+role+'_proj' for role in ('gate', 'up', 'down')]
    metadata = sha(('public-literal-'+case+'-'+str(zero_row)).encode())
    checkpoint = 'synthetic-staged-'+case+'-'+str(zero_row)
    planes = []
    for i, role in enumerate(('gate', 'up', 'down')):
        planes.append(dict(role=role, module=modules[i], expert=0, bits=4, group_size=64,
                           resolved_from='default', metadata_dtype='BF16',
                           logical_shape=[4096, 2048] if i == 2 else [2048, 4096],
                           ranges=[dict(tensor=modules[i]+'.'+suffix, shard='public.synthetic',
                                        begin=0, len=lengths[3*i+j])
                                   for j, suffix in enumerate(('weight', 'scales', 'biases'))]))
    plan = dict(schema='pulsarmlx.bounded-expert-plan/1', checkpoint=checkpoint,
                metadata_snapshot_sha256=metadata, metadata_bytes_read=790848,
                request=dict(modules=modules, expert=0, experts=288, d=4096, h=2048,
                             bits=[4, 4, 4], group_size=64), planes=planes,
                selected_bytes=sum(lengths),
                identity_scope='metadata snapshot and selected ranges only; no whole-checkpoint payload identity')
    owned = dict(schema='pulsarmlx.bounded-expert-owned/1', plan=plan,
                 selected_range_sha256=hashes, owned_bytes=sum(lengths),
                 packed_weights_unchanged=True, native_calls=0, whole_shard_reads=0,
                 whole_shard_hashes=0, scope='host owned range bytes only; no numerical or full-checkpoint qualification')
    header = json.dumps(dict(schema='pulsarmlx.selected-expert-snapshot/1', owned=owned,
                             payload_lengths=lengths,
                             scope='selected packed content only; no numerical qualification'),
                        sort_keys=True, separators=(',', ':')).encode()
    h = hashlib.sha256(b'PLSEX001'+struct.pack('<Q', len(header))+header)
    for part in parts:
        h.update(part)
    expected = dict(snapshot_sha256=h.hexdigest(), snapshot_bytes=16+len(header)+sum(lengths),
                    metadata_sha256=metadata, checkpoint=checkpoint, ranges_sha256=hashes)
    return header, parts, expected, fixtures.input_bytes()


class Backend:
    execution_scope = 'CPU_PUBLIC_SYNTHETIC'

    def __init__(self, perturb=False, mutate=None):
        self.calls = [0, 0, 0, 0]
        self.perturb = perturb
        self.mutate = mutate
        self.hidden_input = None
        self.cache_stats = {}

    def _finish(self, stage, report):
        return self.mutate(stage, report) if self.mutate else report

    def _affine(self, original, role, x):
        n, k = (4096, 2048) if role == 2 else (2048, 4096)
        weights, scales, biases = original.parts[role*3:role*3+3]
        cache = {}
        output = []
        hits = misses = 0
        for r in range(n):
            row = (weights[r*k//2:(r+1)*k//2],
                   scales[r*k//32:(r+1)*k//32], biases[r*k//32:(r+1)*k//32])
            if row not in cache:
                if len(cache) == 32:
                    cache.clear()
                cache[row] = O.rtne_word(O.affine_row(*row, x)[0])
                misses += 1
            else:
                hits += 1
            output.append(cache[row])
        self.cache_stats[str(role)] = dict(hits=hits, misses=misses)
        return output

    def gate_up(self, original):
        self.calls[0] += 1
        x = values(original.x)
        g = self._affine(original, 0, x)
        u = self._affine(original, 1, x)
        if self.perturb:
            for lane, (gw, uw) in O.PERTURBED.items():
                g[lane], u[lane] = gw, uw
        return self._finish('gu', Stage((packed(g), packed(u)), (sha(original.x),), (273, 273)))

    def activation(self, graw, uraw):
        self.calls[1] += 1
        g, u = values(graw), values(uraw)
        cache = {}
        h = []
        for pair in zip(g, u, strict=True):
            if pair not in cache:
                if len(cache) == 32:
                    cache.clear()
                cache[pair] = O.activation_word(*pair)
            h.append(cache[pair])
        gc = tuple(0x41200000 if v > 10 else w[0] for v, w in zip(g, struct.iter_unpack('<I', graw), strict=True))
        uc = tuple(0x41200000 if v > 10 else 0xc1200000 if v < -10 else w[0]
                   for v, w in zip(u, struct.iter_unpack('<I', uraw), strict=True))
        return self._finish('activation', Stage((packed(h),), (sha(graw), sha(uraw)), (2048,), gc, uc))

    def down(self, hraw, original):
        self.calls[2] += 1
        self.hidden_input = hraw
        y = self._affine(original, 2, values(hraw))
        return self._finish('down', Stage((packed(y),), (sha(hraw),), (145,)))

    def cleanup(self):
        self.calls[3] += 1
        return (0, 0, 0)

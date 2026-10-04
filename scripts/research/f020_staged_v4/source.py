"""Immutable in-memory packed source and original-only certificate construction.

No filesystem/model reader, capability issuer or native imports. Current public
constructor admits synthetic source descriptors only. A future real adapter is
not authorized or implemented by this API.
"""
from collections import OrderedDict
from dataclasses import dataclass, fields, is_dataclass
from fractions import Fraction as F
import hashlib
import json
import struct

import f020_selected_snapshot_v2 as framing
import f020_selected_r1_v2 as inherited
from . import numeric as N


def digest(value):
    """Streaming canonical typed hash, with explicit container boundaries."""
    h = hashlib.sha256()
    def put(v):
        if type(v) is bytes:
            h.update(b'b'+str(len(v)).encode()+b':'); h.update(v)
        elif type(v) in (str, int, bool, F) or v is None:
            raw = (type(v).__name__+':'+str(v)).encode()
            h.update(str(len(raw)).encode()+b':'+raw)
        elif type(v) in (tuple, list):
            h.update(b'['+str(len(v)).encode()+b':')
            for item in v:
                put(item)
            h.update(b']')
        elif type(v) is dict:
            h.update(b'{')
            for key in sorted(v):
                put(key); put(v[key])
            h.update(b'}')
        elif is_dataclass(v):
            put(type(v).__name__)
            for field in fields(v):
                put(field.name); put(getattr(v, field.name))
        else:
            raise N.Refusal('noncanonical digest type')
    put(value)
    return h.hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Original:
    header: bytes
    parts: tuple
    x: bytes
    descriptor: bytes
    source_digest: str

    @classmethod
    def synthetic(cls, header, parts, expected, x):
        N.require(type(header) is type(x) is bytes, 'owned immutable source')
        N.require(type(parts) is tuple and len(parts) == 9 and all(type(v) is bytes for v in parts),
                  'nine immutable source parts')
        N.require(tuple(map(len, parts)) == framing.LENGTHS, 'source byte lengths')
        framing.keys(expected, 'snapshot_sha256 snapshot_bytes metadata_sha256 checkpoint ranges_sha256')
        N.require(type(expected['checkpoint']) is str and expected['checkpoint'].startswith('synthetic-'),
                  'CPU public synthetic source only')
        N.require(type(expected['ranges_sha256']) is list and len(expected['ranges_sha256']) == 9,
                  'nine external hashes')
        for value in (expected['snapshot_sha256'], expected['metadata_sha256'], *expected['ranges_sha256']):
            N.require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                      'source digest syntax')
        N.require(expected['snapshot_sha256'] != '43e251a64d1d475900214d3c51b9b21ca988e7b6634d3891fbc6c3a0d5733305',
                  'real snapshot outside current API')
        framing.decode_header(header, expected)
        N.require(sha(x) == inherited.INPUT_SHA256 and len(x) == 16384, 'original input identity')
        inherited.original_input(x, 4096)
        h = hashlib.sha256(b'PLSEX001'+struct.pack('<Q', len(header))+header)
        for part, wanted in zip(parts, expected['ranges_sha256'], strict=True):
            N.require(sha(part) == wanted, 'original component hash')
            h.update(part)
        N.require(type(expected['snapshot_bytes']) is int and expected['snapshot_bytes'] == 16+len(header)+sum(map(len, parts)),
                  'snapshot framing size')
        N.require(h.hexdigest() == expected['snapshot_sha256'], 'original framing hash')
        descriptor = json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()
        return cls(header, parts, x, descriptor, digest((header, parts, x, descriptor)))

    def verify(self):
        N.require(type(self.descriptor) is bytes and len(self.descriptor) <= framing.MAX_HEADER,
                  'descriptor bound')
        expected = json.loads(self.descriptor, object_pairs_hook=framing.unique,
                              parse_constant=framing.reject_constant)
        checked = Original.synthetic(self.header, self.parts, expected, self.x)
        N.require(checked.source_digest == self.source_digest,
                  'original source changed')

    def row(self, role, row):
        N.require(type(role) is int and role in (0, 1, 2), 'source role')
        n, k = (4096, 2048) if role == 2 else (2048, 4096)
        N.require(type(row) is int and 0 <= row < n, 'source row')
        w, s, b = self.parts[3*role:3*role+3]
        return (w[row*k//2:(row+1)*k//2], s[row*k//32:(row+1)*k//32], b[row*k//32:(row+1)*k//32])


def groups(row):
    w, s, b = row
    for group in range(len(s)//2):
        su = inherited.units(struct.unpack_from('<H', s, 2*group)[0], True)
        bu = inherited.units(struct.unpack_from('<H', b, 2*group)[0], True)
        N.require(255*abs(su)+abs(bu) <= 1 << 75, 'metadata envelope')
        yield group, memoryview(w)[group*32:(group+1)*32], su, bu


def affine_row(row, x):
    total = phi = 0
    for group, packed, s, b in groups(row):
        for j in range(64):
            code = (packed[j//2] >> (4*(j % 2))) & 15
            v = x[group*64+j]
            total = N.integer(total+v*(s*code+b))
            phi = N.integer(phi+abs(v)*(abs(s)*code+abs(b)))
    return F(total, 1 << 94), inherited.gamma(len(x))*F(phi, 1 << 94)


def contract_row(row, hidden, budgets):
    yl = yh = pb = old = 0
    for group, packed, s, b in groups(row):
        for j in range(64):
            index = group*64+j
            w = s*((packed[j//2] >> (4*(j % 2))) & 15)+b
            lo, hi = hidden[index]
            a, c = w*lo, w*hi
            yl = N.integer(yl+min(a, c)); yh = N.integer(yh+max(a, c))
            pb = N.integer(pb+abs(w)*budgets[index][0])
            old = N.integer(old+abs(w)*budgets[index][1])
    divisor = 1 << 39
    y = (F(yl//divisor, N.LATTICE), F(-((-yh)//divisor), N.LATTICE))
    return y, F(pb, N.DEN_E*divisor), F(old, N.DEN_E*divisor)


class Rows:
    """Bounded exact-row memoization, metadata and operand identity in every key."""
    def __init__(self, original, checkpoint):
        self.original = original
        self.checkpoint = checkpoint
        self.stats = {}

    def apply(self, role, operand_digest, call, label):
        cache = OrderedDict()
        result = []
        hits = misses = 0
        for row in range(4096 if role == 2 else 2048):
            self.checkpoint()
            data = self.original.row(role, row)
            key = (role, data, operand_digest)
            if key in cache:
                hits += 1
                out = cache[key]
                cache.move_to_end(key)
            else:
                misses += 1
                out = call(data)
                cache[key] = out
                if len(cache) > 32:
                    cache.popitem(last=False)
            result.append(out)
        self.stats[label] = {'hits': hits, 'misses': misses}
        return tuple(result)


@dataclass(frozen=True)
class Certificate:
    identity: tuple
    original_digest: str
    lanes: tuple
    y: tuple
    propagation: tuple
    old_propagation: tuple
    e_digest: str


def references(original, identity, checkpoint):
    """Original-only signature: no candidate values or caller reference accepted."""
    original.verify()
    rows = Rows(original, checkpoint)
    x = tuple(inherited.original_input(original.x, 4096))
    operand = digest(x)
    g = rows.apply(0, operand, lambda row: affine_row(row, x), 'gate')
    u = rows.apply(1, operand, lambda row: affine_row(row, x), 'up')
    lane_cache = OrderedDict()
    lanes = []
    for (gv, gb), (uv, ub) in zip(g, u, strict=True):
        checkpoint()
        key = (gv, uv, gb, ub)
        if key not in lane_cache:
            lane_cache[key] = N.lane(*key)
            if len(lane_cache) > 32:
                lane_cache.popitem(last=False)
        lanes.append(lane_cache[key])
    lanes = tuple(lanes)
    N.require(len(lanes) == 2048 and sum(v.magnitude for v in lanes) <= 1 << 40,
              'prospective hidden row sum')
    hidden = tuple((int(v.h[0]*N.LATTICE), int(v.h[1]*N.LATTICE)) for v in lanes)
    budgets = []
    for v in lanes:
        scaled_old = v.old*N.DEN_E
        N.require(scaled_old.denominator == 1, 'old budget denominator')
        budgets.append((N.scale_e(v.e), N.integer(scaled_old.numerator)))
    budgets = tuple(budgets)
    down = rows.apply(2, digest((hidden, budgets)), lambda row: contract_row(row, hidden, budgets), 'ideal_down')
    y, propagation, old_propagation = zip(*down, strict=True)
    N.require(all(a <= b for a, b in zip(propagation, old_propagation, strict=True)), 'propagated old ceiling')
    cert = Certificate(identity, original.source_digest, lanes, tuple(y), tuple(propagation),
                       tuple(old_propagation), digest(tuple(v.e for v in lanes)))
    return cert, rows.stats


def local_down(original, hraw, checkpoint):
    original.verify()
    x = tuple(inherited.original_input(hraw, 2048))
    rows = Rows(original, checkpoint)
    values = rows.apply(2, sha(hraw), lambda row: affine_row(row, x), 'local_down')
    z, r = zip(*values, strict=True)
    return tuple(z), tuple(r), rows.stats

#!/usr/bin/env python3
"""F020 Slice 2B -- frozen fixture generator for native MLX primitive qualification.

Standard library only. Deterministic: the same generator bytes always produce
the same fixture bytes and the same manifest. Nothing here calls MLX or any
numerical library; the only arithmetic is exact (integers and
fractions.Fraction) and is used to *classify* generated inputs against the
contract's admitted domain, never to predict an MLX output.

Contract: specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json
(draft.4). Every constant below is quoted from that contract; changing one is a
contract revision, not a generator edit.

Usage:
    f020_native_primitives_fixtures_v1.py --out fixtures/native-primitives
    f020_native_primitives_fixtures_v1.py --out fixtures/native-primitives --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from fractions import Fraction
from pathlib import Path

SCHEMA = "pulsarmlx.f020.native-primitives-fixtures/1.0.0"
CONTRACT_SCHEMA = "pulsarmlx.f020.native-primitives-contract/1.0.0-draft.4"

# ---------------------------------------------------------------- constants --
# Admitted numeric domain (contract: domain.D-NUM).
E_LO = -32                      # every nonzero |x|, |s|, |b| >= 2^E_LO
E_HI = 32                       # every nonzero |x|, |s|, |b| <= 2^E_HI
ROWSUM_MAX = Fraction(2) ** 40  # per-row sum |x| (G-ROWSUM)
WMAX = Fraction(2) ** 36        # per-group |s|*255 + |b| (G-WMAX)
# Admitted geometry (contract: domain.D-GEOM).
K_MAX = 16384
N_MAX = 16384
M_MAX = 4096
N_ALIGN = 64
BITS = (4, 8)
GROUPS = (32, 64, 128)
META = ("F16", "BF16", "F32")
PY_EXACT_MAC_LIMIT = 1 << 21    # cases with M_eff*N*K <= this also get the exact Python R1
CHILD_TIMEOUT_SECONDS = 1800    # parent watchdog (contract: execution.watchdog)

REFUSAL_ORDER = [
    "R-DEVICE", "R-TRANSPOSE", "R-BITS", "R-GROUP", "R-WDTYPE", "R-EMPTY-DIM", "R-META",
    "R-XDTYPE", "R-XSHAPE", "R-GEOMETRY", "R-NONFINITE", "R-SUBNORMAL",
    "R-DOMAIN-X-RANGE", "R-DOMAIN-META-RANGE", "R-DOMAIN-ROWSUM",
    "R-DOMAIN-WMAX", "R-DQ-RANGE", "R-DQ-NORMAL",
]

# Floating formats: (total bits, significand precision p incl. hidden bit, emin, emax)
FMT = {
    "F32": (32, 24, -126, 127),
    "F16": (16, 11, -14, 15),
    "BF16": (16, 8, -126, 127),
}
MAX_FINITE = {k: (2 - Fraction(1, 2 ** (p - 1))) * Fraction(2) ** emax
              for k, (_, p, _, emax) in FMT.items()}
LAMBDA = {k: Fraction(1, 2 ** (-emin)) for k, (_, _, emin, _) in FMT.items()}

# ------------------------------------------------------------------- PRNG ----
MASK64 = (1 << 64) - 1


class SplitMix64:
    """splitmix64; every draw consumes exactly one next() call."""

    def __init__(self, seed: int) -> None:
        self.state = seed & MASK64

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def below(self, n: int) -> int:
        """Integer in [0, n): multiply-shift of one 64-bit draw (no rejection)."""
        return (self.next() * n) >> 64

    def top_bits(self, k: int) -> int:
        """The top k bits of one 64-bit draw (k >= 1)."""
        return self.next() >> (64 - k)


def case_seed(case_id: str) -> int:
    """Per-case seed: first 8 bytes (big-endian) of sha256(b'f020-2b:' + id)."""
    return int.from_bytes(hashlib.sha256(b"f020-2b:" + case_id.encode()).digest()[:8], "big")


# ------------------------------------------------------ float bit patterns ---
def encode_normal(fmt: str, sign: int, exp: int, frac: int) -> int:
    width, p, emin, emax = FMT[fmt]
    assert emin <= exp <= emax and 0 <= frac < (1 << (p - 1))
    ebits = width - p
    bias = (1 << (ebits - 1)) - 1
    return (sign << (width - 1)) | ((exp + bias) << (p - 1)) | frac


def decode(fmt: str, bits: int):
    """Exact value as Fraction, or the strings 'nan'/'inf'/'-inf'. Zero keeps no sign here."""
    width, p, _, _ = FMT[fmt]
    ebits = width - p
    bias = (1 << (ebits - 1)) - 1
    sign = -1 if bits >> (width - 1) else 1
    e = (bits >> (p - 1)) & ((1 << ebits) - 1)
    f = bits & ((1 << (p - 1)) - 1)
    if e == (1 << ebits) - 1:
        return "nan" if f else ("inf" if sign > 0 else "-inf")
    if e == 0:
        return sign * Fraction(f, 1 << (p - 1)) * Fraction(2) ** (1 - bias)
    return sign * (1 + Fraction(f, 1 << (p - 1))) * Fraction(2) ** (e - bias)


def is_subnormal(fmt: str, bits: int) -> bool:
    width, p, _, _ = FMT[fmt]
    ebits = width - p
    e = (bits >> (p - 1)) & ((1 << ebits) - 1)
    f = bits & ((1 << (p - 1)) - 1)
    return e == 0 and f != 0


def pow2_bits(fmt: str, exp: int, sign: int = 0) -> int:
    return encode_normal(fmt, sign, exp, 0)


def draw_float(rng: SplitMix64, fmt: str, e_lo: int, e_hi: int, zero_permille: int) -> int:
    """Draw order (frozen): below(1000) for zero; if nonzero: top_bits(1) sign,
    below(e_hi-e_lo+1) exponent offset, top_bits(p-1) fraction. A zero is +0."""
    if rng.below(1000) < zero_permille:
        return 0
    sign = rng.top_bits(1)
    exp = e_lo + rng.below(e_hi - e_lo + 1)
    _, p, _, _ = FMT[fmt]
    frac = rng.top_bits(p - 1)
    return encode_normal(fmt, sign, exp, frac)


def rn(value: Fraction, fmt: str):
    """Round-to-nearest-even of an exact value into fmt; returns Fraction or 'inf'."""
    _, p, emin, emax = FMT[fmt]
    if value == 0:
        return Fraction(0)
    sign = -1 if value < 0 else 1
    a = abs(value)
    e = a.numerator.bit_length() - a.denominator.bit_length()
    if Fraction(2) ** e > a:
        e -= 1
    e = max(e, emin)
    quantum = Fraction(2) ** (e - p + 1)
    q = a / quantum
    n = q.numerator // q.denominator
    rem = q - n
    if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and n % 2 == 1):
        n += 1
    r = n * quantum
    if r > MAX_FINITE[fmt]:
        return "inf"
    return sign * r


# ------------------------------------------------------------- packing -------
def pack_rows(codes, rows: int, k: int, bits: int):
    """LSB-first: element j of a row occupies bits [j*bits, (j+1)*bits) of the
    row's little-endian u32 stream."""
    per = 32 // bits
    words = []
    for r in range(rows):
        for w in range(k // per):
            v = 0
            for i in range(per):
                v |= codes[r * k + w * per + i] << (bits * i)
            words.append(v)
    return words


def to_bytes(dtype: str, values) -> bytes:
    fmt = {"U32": "<%dI", "F32": "<%dI", "F16": "<%dH", "BF16": "<%dH"}[dtype]
    return struct.pack(fmt % len(values), *values)


# --------------------------------------------------------- case builders -----
class Case:
    def __init__(self, cid: str, family: str, op: str):
        self.id = cid
        self.family = family
        self.op = op
        self.tensors = []          # (name, dtype, shape, values)
        self.params = {}
        self.expected = {}
        self.references = []

    def add(self, name, dtype, shape, values):
        n = 1
        for d in shape:
            n *= d
        assert n == len(values), (self.id, name, shape, len(values))
        self.tensors.append((name, dtype, list(shape), list(values)))


def draw_codes(rng, total: int, bits: int):
    """Codes: element t < 2^bits gets t (coverage sweep), later elements one below(2^bits) each."""
    top = 1 << bits
    return [t if t < top else rng.below(top) for t in range(total)]


def draw_meta(rng, fmt: str, count: int, kind: str):
    """Frozen per-dtype exponent windows (all inside [E_LO, E_HI] and normal in fmt).
    kind 'scale': F16 [-10,-4], BF16/F32 [-12,-3]; kind 'bias': F16 [-6,0], BF16/F32 [-8,1];
    zero_permille 0 for scales, 20 for biases."""
    if kind == "scale":
        lo, hi = (-10, -4) if fmt == "F16" else (-12, -3)
        zp = 0
    else:
        lo, hi = (-6, 0) if fmt == "F16" else (-8, 1)
        zp = 20
    return [draw_float(rng, fmt, lo, hi, zp) for _ in range(count)]


def draw_x(rng, count: int):
    """x (F32): exponent window [-8, 3], zero_permille 10."""
    return [draw_float(rng, "F32", -8, 3, 10) for _ in range(count)]


def dq_case(cid, bits, gs, meta, rows, k, override=None):
    c = Case(cid, "FX-DQ", "dequantize")
    rng = SplitMix64(case_seed(cid))
    codes = draw_codes(rng, rows * k, bits)
    groups = rows * (k // gs)
    scales = draw_meta(rng, meta, groups, "scale")
    biases = draw_meta(rng, meta, groups, "bias")
    if override:
        override(codes, scales, biases)
    c.add("w", "U32", (rows, k * bits // 32), pack_rows(codes, rows, k, bits))
    c.add("scales", meta, (rows, k // gs), scales)
    c.add("biases", meta, (rows, k // gs), biases)
    c.params = {"bits": bits, "group_size": gs, "metadata_dtype": meta, "rows": rows, "K": k}
    c._codes = codes
    return c


def qmm_case(cid, bits, gs, meta, x_lead, k, n, x_override=None, meta_override=None, xdtype="F32", transpose=True):
    c = Case(cid, "FX-QMM", "quantized_matmul")
    rng = SplitMix64(case_seed(cid))
    m_eff = 1
    for d in x_lead:
        m_eff *= d
    x = draw_x(rng, m_eff * k)
    codes = draw_codes(rng, n * k, bits)
    groups = n * (k // gs)
    scales = draw_meta(rng, meta, groups, "scale")
    biases = draw_meta(rng, meta, groups, "bias")
    if x_override:
        x_override(x, m_eff, k)
    if meta_override:
        meta_override(codes, scales, biases)
    if xdtype != "F32":
        # refusal probes only: reinterpret as 16-bit patterns of the requested dtype (value irrelevant)
        x = [v >> 16 for v in x]
    c.add("x", xdtype, tuple(x_lead) + (k,), x)
    c.add("w", "U32", (n, k * bits // 32), pack_rows(codes, n, k, bits))
    c.add("scales", meta, (n, k // gs), scales)
    c.add("biases", meta, (n, k // gs), biases)
    c.params = {"bits": bits, "group_size": gs, "metadata_dtype": meta, "x_shape": list(x_lead) + [k],
                "M_eff": m_eff, "K": k, "N": n, "transpose": transpose, "x_dtype": xdtype}
    c._codes = codes
    return c


# ---------------------------------------------------- domain classification --
def _tensor(c, name):
    for nm, dtype, shape, vals in c.tensors:
        if nm == name:
            return dtype, shape, vals
    return None


def _value_class(fmt, bits):
    v = decode(fmt, bits)
    if isinstance(v, str):
        return "nonfinite", None
    if is_subnormal(fmt, bits):
        return "subnormal", v
    return ("zero" if v == 0 else "normal"), v


def guard_results(c):
    """Evaluate EVERY guard independently (not just the first failing one).

    Returns a dict id -> True (violated), False (satisfied) or a string
    "n/a: <reason>" when the guard does not apply to the op or its
    precondition (a structurally valid tensor it reads) is not met.
    Value classes are disjoint: a non-finite value is judged only by
    R-NONFINITE, a subnormal value only by R-SUBNORMAL, and the range,
    row-sum, envelope and element guards read only zero or normal values.
    Guards never divide by a dimension; the lower-dimension conditions are
    owned by R-EMPTY-DIM.
    """
    p = c.params
    qmm = c.op == "quantized_matmul"
    G = {}
    G["R-DEVICE"] = p.get("context") == "cpu"
    G["R-TRANSPOSE"] = (not p.get("transpose", True)) if qmm else "n/a: op"
    bits, gs = p["bits"], p["group_size"]
    G["R-BITS"] = bits not in BITS
    G["R-GROUP"] = gs not in GROUPS
    wd, wshape, _ = _tensor(c, "w")
    G["R-WDTYPE"] = wd != "U32" or len(wshape) != 2
    G["R-EMPTY-DIM"] = any(d == 0 for _, _, shape, _ in c.tensors for d in shape)
    sd, sshape, sv = _tensor(c, "scales")
    bd, bshape, bv = _tensor(c, "biases")
    w_ok = G["R-WDTYPE"] is False
    k = None
    if w_ok:
        rows, packed = wshape
        G["R-META"] = (sd not in META or bd != sd or sshape != bshape or len(sshape) != 2
                       or sshape[0] != rows or packed * 32 != sshape[1] * gs * bits)
        if bits > 0 and (packed * 32) % bits == 0:
            k = packed * 32 // bits
    else:
        G["R-META"] = "n/a: weight not a rank-2 U32 tensor"
    meta_num = G["R-META"] is False
    x_num = False
    xv = []
    xshape = []
    if qmm:
        xd, xshape, xv = _tensor(c, "x")
        G["R-XDTYPE"] = xd != "F32"
        if k is None:
            G["R-XSHAPE"] = "n/a: K undefined"
            G["R-GEOMETRY"] = "n/a: K undefined"
        else:
            G["R-XSHAPE"] = not (1 <= len(xshape) <= 3) or xshape[-1] != k
            m_eff = 1
            for d in xshape[:-1]:
                m_eff *= d
            G["R-GEOMETRY"] = (k > K_MAX or rows > N_MAX or m_eff > M_MAX
                               or (rows >= 1 and rows % N_ALIGN != 0)
                               or (k >= 1 and k % gs != 0))
        x_num = G["R-XDTYPE"] is False and len(xshape) >= 1
    else:
        for rid in ("R-XDTYPE", "R-XSHAPE"):
            G[rid] = "n/a: op"
        G["R-GEOMETRY"] = ("n/a: K undefined" if k is None else
                           (k > K_MAX or rows > N_MAX or (k >= 1 and k % gs != 0)))
    classes = []
    if x_num:
        classes += [_value_class("F32", b)[0] for b in xv]
    if meta_num:
        classes += [_value_class(sd, b)[0] for b in sv] + [_value_class(bd, b)[0] for b in bv]
    if x_num or meta_num:
        G["R-NONFINITE"] = "nonfinite" in classes
        G["R-SUBNORMAL"] = "subnormal" in classes
    else:
        G["R-NONFINITE"] = G["R-SUBNORMAL"] = "n/a: no numerically readable tensor"
    lo, hi = Fraction(2) ** E_LO, Fraction(2) ** E_HI

    def out_of_range(fmt, vals):
        for b in vals:
            cls, v = _value_class(fmt, b)
            if cls == "normal" and not (lo <= abs(v) <= hi):
                return True
        return False
    if qmm:
        G["R-DOMAIN-X-RANGE"] = out_of_range("F32", xv) if x_num else "n/a: x not F32"
        if x_num and xshape[-1] >= 1:
            viol = False
            kk = xshape[-1]
            for r in range(len(xv) // kk):
                tot = Fraction(0)
                for b in xv[r * kk:(r + 1) * kk]:
                    cls, v = _value_class("F32", b)
                    if cls != "nonfinite":
                        tot += abs(v)
                if tot > ROWSUM_MAX:
                    viol = True
            G["R-DOMAIN-ROWSUM"] = viol
        else:
            G["R-DOMAIN-ROWSUM"] = False if x_num else "n/a: x not F32"
    else:
        G["R-DOMAIN-X-RANGE"] = G["R-DOMAIN-ROWSUM"] = "n/a: op"
    G["R-DOMAIN-META-RANGE"] = (out_of_range(sd, sv) or out_of_range(bd, bv)) if meta_num else "n/a: metadata inconsistent"

    def usable(i):
        cs, s = _value_class(sd, sv[i])
        cb, b = _value_class(bd, bv[i])
        if cs in ("normal", "zero") and cb in ("normal", "zero"):
            return s, b
        return None
    if qmm:
        if meta_num:
            viol = False
            for i in range(len(sv)):
                u = usable(i)
                if u and abs(u[0]) * 255 + abs(u[1]) > WMAX:
                    viol = True
            G["R-DOMAIN-WMAX"] = viol
        else:
            G["R-DOMAIN-WMAX"] = "n/a: metadata inconsistent"
        G["R-DQ-RANGE"] = G["R-DQ-NORMAL"] = "n/a: op"
    else:
        G["R-DOMAIN-WMAX"] = "n/a: op"
        if meta_num and k is not None and gs in GROUPS:
            codes = c._codes
            half_max = MAX_FINITE[sd] / 2
            lam = LAMBDA[sd]
            vr = vn = False
            for idx, q in enumerate(codes):
                u = usable(idx // gs)
                if not u:
                    continue
                s_, b_ = u
                if abs(s_) * q + abs(b_) > half_max:
                    vr = True
                pv = s_ * q
                for v in (pv + b_, rn(pv, sd) + b_):
                    if v != 0 and abs(v) < lam:
                        vn = True
            G["R-DQ-RANGE"], G["R-DQ-NORMAL"] = vr, vn
        else:
            G["R-DQ-RANGE"] = G["R-DQ-NORMAL"] = "n/a: metadata or K undefined"
    return G


def violations(G):
    return [rid for rid in REFUSAL_ORDER if G.get(rid) is True]


def not_evaluable(G):
    return sorted(rid for rid, v in G.items() if isinstance(v, str) and not v.startswith("n/a: op"))


# ------------------------------------------------ 0.31.2 family derivation ---
def split_k_0312(m, n, k, gs):
    """MLX312 quantized.cpp:793-803."""
    tiles = ((n + 31) // 32) * ((m + 31) // 32)
    sk = max(1, 512 // tiles)
    sk = min(sk, k // gs)
    while sk > 1 and k % (sk * gs) != 0:
        sk -= 1
    return sk


def vector_family(k, n, bits):
    if k in (64, 128):
        return "qmv_quad"
    if n % 8 == 0 and k % 512 == 0:
        return "qmv_fast"
    return "qmv"


def gamma_exponent(fam, k, bits, sk=1):
    """Contract N-QMM-BOUND exponents (T = float32)."""
    if fam == "qmv_quad":
        return k // 4 + 5
    if fam == "qmv_fast":
        return k // 16 + 17 if bits == 4 else k // 8 + 9
    if fam == "qmv":
        return k // 8 + 9 if bits == 4 else k // 4 + 5
    if fam == "qmm_t":
        return k + 3
    if fam == "qmm_t_splitk":
        return k // sk + sk + 3
    raise ValueError(fam)


def families(p):
    m, n, k, gs, bits = p["M_eff"], p["N"], p["K"], p["group_size"], p["bits"]
    out = []
    if m <= 31:
        f = vector_family(k, n, bits)
        out.append({"family": f, "gamma_n": gamma_exponent(f, k, bits)})
    if m >= 6:
        sk = split_k_0312(m, n, k, gs)
        if sk > 1:
            out.append({"family": "qmm_t_splitk", "split_k": sk, "gamma_n": gamma_exponent("qmm_t_splitk", k, bits, sk)})
        else:
            out.append({"family": "qmm_t", "gamma_n": gamma_exponent("qmm_t", k, bits)})
    return out


def r2_label(p):
    """0.32.0 labelling predicate (MLX320 quantized.cpp:1456-1484): quad branch first."""
    m, k = p["M_eff"], p["K"]
    if k in (64, 128):
        return "same_family_rule_as_0.31.2_when_vector"
    if 2 <= m <= 31:
        return "different_kernel_family_if(M_eff<L and generation>=15)"
    return "same_family_rule_as_0.31.2"


# ------------------------------------------------------------ population -----
def population():
    cases = []
    # FX-IMPORT-U32
    shapes = [(1, 1), (1, 4), (3, 8), (7, 48), (64, 512)]
    edge = [0x00000000, 0xFFFFFFFF, 0x80000000, 0x00000001, 0xAAAAAAAA, 0x55555555]
    for r, cshape in enumerate(shapes):
        cid = "imp-u32-%dx%d" % cshape
        c = Case(cid, "FX-IMPORT-U32", "import_u32")
        rng = SplitMix64(case_seed(cid))
        n = cshape[0] * cshape[1]
        vals = [edge[i] if i < len(edge) else (rng.next() & 0xFFFFFFFF) for i in range(n)]
        c.add("w", "U32", cshape, vals)
        c.expected = {"outcome": "accept", "checks": ["N-IMPORT-U32"]}
        c.references = ["byte_identity"]
        cases.append(c)
    # FX-IMPORT-META
    for fmt in ("F16", "BF16"):
        cid = "imp-%s-all" % fmt.lower()
        c = Case(cid, "FX-IMPORT-META", "import_meta")
        c.add("values", fmt, (256, 256), list(range(65536)))
        c.expected = {"outcome": "accept", "checks": ["N-IMPORT-META"]}
        c.references = ["byte_identity"]
        cases.append(c)
    cid = "imp-f32-special-random"
    c = Case(cid, "FX-IMPORT-META", "import_meta")
    rng = SplitMix64(case_seed(cid))
    special = [0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007FFFFF, 0x807FFFFF,
               0x00800000, 0x80800000, 0x7F7FFFFF, 0xFF7FFFFF, 0x7F800000, 0xFF800000,
               0x7FC00001, 0x7F800001, 0xFFFFFFFF, 0x3F800000]
    vals = special + [rng.next() & 0xFFFFFFFF for _ in range(65536)]
    c.add("values", "F32", (1, len(vals)), vals)
    c.expected = {"outcome": "accept", "checks": ["N-IMPORT-META"]}
    c.references = ["byte_identity"]
    cases.append(c)
    # FX-CAST: reuses the exhaustive F16/BF16 import tensors
    for fmt in ("F16", "BF16"):
        c = Case("cast-%s-to-f32" % fmt.lower(), "FX-CAST", "astype_f32")
        c.params = {"input_case": "imp-%s-all" % fmt.lower(), "source_dtype": fmt}
        c.expected = {"outcome": "accept", "checks": ["N-CAST-WIDEN"],
                      "domain": "zero or normal finite patterns gate; subnormal, inf and NaN patterns are recorded only"}
        c.references = ["exact_host_widening"]
        cases.append(c)
    # FX-DQ accepted
    for bits in BITS:
        for gs in GROUPS:
            for meta in META:
                for rows, k in ((1, gs), (3, 2 * gs), (17, 512)):
                    cid = "dq-b%d-g%d-%s-r%d-k%d" % (bits, gs, meta.lower(), rows, k)
                    c = dq_case(cid, bits, gs, meta, rows, k)
                    c.expected = {"outcome": "accept", "checks": ["N-DQ-SHAPE-DTYPE", "N-DQ-BOUND"], "recorded": ["H-DQ-SET"]}
                    c.references = ["rust_binary64_r1", "python_exact_r1"]
                    cases.append(c)
                cid = "dq-codes-b%d-g%d-%s" % (bits, gs, meta.lower())

                def unit(codes, scales, biases, meta=meta):
                    one = encode_normal(meta, 0, 0, 0)
                    for i in range(len(scales)):
                        scales[i] = one
                        biases[i] = 0
                c = dq_case(cid, bits, gs, meta, 8, 256 if bits == 8 else gs, unit)
                c.expected = {"outcome": "accept", "checks": ["N-DQ-SHAPE-DTYPE", "N-DQ-CODES"], "canary": "E4"}
                c.references = ["codes_exact"]
                cases.append(c)
    for bits in BITS:   # production-relevant: group 64, BF16 (census)
        cid = "dq-prod-b%d-g64-bf16-r64-k4096" % bits
        c = dq_case(cid, bits, 64, "BF16", 64, 4096)
        c.expected = {"outcome": "accept", "checks": ["N-DQ-SHAPE-DTYPE", "N-DQ-BOUND"], "recorded": ["H-DQ-SET"]}
        c.references = ["rust_binary64_r1", "python_exact_r1"]
        c.params["production_relevant"] = True
        cases.append(c)
    # edge magnitudes for dequantize
    for meta, sset, bset in (
        ("BF16", [(-32, 0), (-32, 1), (28, 0), (28, 1)], [(-32, 0), (32, 1), (27, 0)]),
        ("F32", [(-32, 0), (-32, 1), (28, 0), (28, 1)], [(-32, 1), (32, 0), (27, 1)]),
        ("F16", [(-14, 0), (-14, 1), (6, 0), (6, 1)], [(-14, 1), (14, 0), (14, 1)]),
    ):
        cid = "dq-edge-b8-g32-%s" % meta.lower()

        def edges(codes, scales, biases, meta=meta, sset=sset, bset=bset):
            for i in range(len(scales)):
                e, sg = sset[i % len(sset)]
                scales[i] = pow2_bits(meta, e, sg)
                e, sg = bset[i % len(bset)]
                biases[i] = pow2_bits(meta, e, sg) if i % 5 else (0x8000 if meta != "F32" else 0x80000000)
        c = dq_case(cid, 8, 32, meta, 12, 64, edges)
        c.expected = {"outcome": "accept", "checks": ["N-DQ-SHAPE-DTYPE", "N-DQ-BOUND"], "recorded": ["H-DQ-SET"]}
        c.references = ["rust_binary64_r1", "python_exact_r1"]
        cases.append(c)
    # FX-QMM accepted
    shape_set = [
        ("quad64", (1,), 64, 64),
        ("quad128", (1,), 128, 64),
        ("qmv384", (1,), 384, 64),
        ("fast512", (1,), 512, 64),
        ("vec-m2", (2,), 256, 64),
        ("vec-m5-fast", (5,), 512, 64),
        ("band-m8", (8,), 256, 128),
        ("band-m16", (16,), 256, 64),
        ("band-m31-quad", (31,), 128, 64),
        ("mat-m32", (32,), 128, 64),
        ("mat-m33", (33,), 256, 64),
        ("rank3-m34", (2, 17), 128, 64),
        ("rank1", (), 256, 64),
    ]
    for bits in BITS:
        for gs in GROUPS:
            for meta in META:
                for label, lead, k, n in shape_set:
                    if k % gs:
                        continue
                    cid = "qmm-b%d-g%d-%s-%s" % (bits, gs, meta.lower(), label)
                    cases.append(accepted_qmm(qmm_case(cid, bits, gs, meta, lead, k, n)))
    for bits, gs, meta in ((4, 64, "BF16"), (8, 64, "BF16")):
        cid = "qmm-b%d-g%d-%s-mat-m512-nosplit" % (bits, gs, meta.lower())
        cases.append(accepted_qmm(qmm_case(cid, bits, gs, meta, (512,), 64, 1024)))
    for bits in BITS:   # production-relevant: group 64, BF16 (census)
        for label, lead, k, n in (("prod-m1-fast", (1,), 4096, 64), ("prod-m4-fast", (4,), 2048, 64),
                                  ("prod-m32-splitk", (32,), 1024, 64)):
            cid = "qmm-b%d-g64-bf16-%s" % (bits, label)
            c = accepted_qmm(qmm_case(cid, bits, 64, "BF16", lead, k, n))
            c.params["production_relevant"] = True
            cases.append(c)
    # edge magnitudes and zero rows

    def x_edges(x, m, k):
        pats = [pow2_bits("F32", -32), pow2_bits("F32", 32), pow2_bits("F32", 32, 1), pow2_bits("F32", -32, 1), 0x80000000]
        for i in range(0, len(x), 7):
            x[i] = pats[(i // 7) % len(pats)]

    def meta_edges(codes, scales, biases):
        for i in range(len(scales)):
            scales[i] = pow2_bits("BF16", 28, i % 2) if i % 3 == 0 else scales[i]
            biases[i] = pow2_bits("BF16", 28, (i + 1) % 2) if i % 3 == 0 else biases[i]
    cases.append(accepted_qmm(qmm_case("qmm-b4-g64-bf16-edge-m3", 4, 64, "BF16", (3,), 256, 64, x_edges, meta_edges)))

    def x_edges32(x, m, k):
        x_edges(x, m, k)

    def meta_edges32(codes, scales, biases):
        for i in range(len(scales)):
            if i % 4 == 0:
                scales[i] = pow2_bits("F32", -32, i % 2)
                biases[i] = pow2_bits("F32", -32, (i + 1) % 2)
    cases.append(accepted_qmm(qmm_case("qmm-b8-g32-f32-edge-m40", 8, 32, "F32", (40,), 256, 64, x_edges32, meta_edges32)))

    def zero_rows(x, m, k):
        for i in range(k):
            x[i] = 0 if i % 2 else 0x80000000          # row 0: signed zeros
        for i in range(k, 2 * k):
            x[i] = pow2_bits("F32", 31)                # row 1: sum |x| = 2^31 * 512 = 2^40 (G-ROWSUM boundary, admitted)
    c = accepted_qmm(qmm_case("qmm-b4-g64-bf16-zero-rowsum-m3", 4, 64, "BF16", (3,), 512, 64, zero_rows))
    c.expected["checks"].append("N-QMM-ZERO(row 0)")
    cases.append(c)
    cases.extend(refusal_cases())
    return cases


def accepted_qmm(c):
    p = c.params
    c.expected = {"outcome": "accept", "checks": ["N-QMM-SHAPE-DTYPE", "N-QMM-BOUND"],
                  "families_0_31_2": families(p),
                  "architecture_dependent": 6 <= p["M_eff"] <= 31,
                  "r2_label_rule_0_32_0": r2_label(p)}
    macs = p["M_eff"] * p["N"] * p["K"]
    c.references = ["rust_binary64_r1"] + (["python_exact_r1"] if macs <= PY_EXACT_MAC_LIMIT else [])
    c.checks_extra = []
    return c


def refusal_cases():
    out = []

    def ref(c, rid, note):
        c.family = "FX-REFUSE"
        c.expected = {"outcome": "refuse", "refusal_id": rid, "note": note,
                      "requirement": "refused by the bridge before any MLX-C numerical call"}
        c.references = []
        out.append(c)

    # Astra F1 (vector): x[3] = 2^-120, s = 2^120 -- outside D-NUM, refused before MLX
    def f1x(x, m, k):
        for i in range(k):
            x[i] = 0
        x[3] = pow2_bits("F32", -120)
    def f1m(codes, scales, biases):
        for i in range(len(scales)):
            scales[i] = pow2_bits("F32", 0)
            biases[i] = 0
    ref(qmm_case("ref-astra-f1-vector-x-underflow", 4, 32, "F32", (1,), 64, 64, f1x, f1m),
        "R-DOMAIN-X-RANGE", "review F1: x/4096 = 2^-132 would flush; nonzero |x| < 2^-32")
    # Astra F1 (matrix): s = 2^-126 (BF16 normal), x = 2^126
    def f1mx(x, m, k):
        for i in range(len(x)):
            x[i] = 0
    def f1mm(codes, scales, biases):
        scales[0] = pow2_bits("BF16", -126)
    ref(qmm_case("ref-astra-f1-matrix-scale-underflow", 4, 32, "BF16", (32,), 32, 64, f1mx, f1mm),
        "R-DOMAIN-META-RANGE", "review F1: s/16 = 2^-130 would flush; nonzero |s| < 2^-32")
    # Astra F2 structure (Phi = 0: zero codes and biases, unit scales) with |x| kept IN range so that
    # only the row-sum guard is violated: 512 x 2^32 = 2^41 > 2^40. The review's literal values
    # (x = 2^126) necessarily violate two guards (X-RANGE and ROWSUM) and are therefore represented
    # by this probe plus the single-guard X-RANGE probes (ref-astra-f1-vector-x-underflow, ref-x-above-range).
    def f2x(x, m, k):
        for i in range(k):
            x[i] = pow2_bits("F32", 32)
    def f2m(codes, scales, biases):
        for i in range(len(codes)):
            codes[i] = 0
        for i in range(len(scales)):
            scales[i] = pow2_bits("F32", 0)
            biases[i] = 0
    ref(qmm_case("ref-astra-f2-rowsum-in-range", 4, 32, "F32", (1,), 512, 64, f2x, f2m),
        "R-DOMAIN-ROWSUM", "review F2 structure: unweighted sum x = 2^41 > 2^40 with every |x| = 2^32 in range")
    def above(x, m, k):
        for i in range(k):
            x[i] = 0
        x[0] = pow2_bits("F32", 33)
    ref(qmm_case("ref-x-above-range", 4, 32, "F32", (1,), 64, 64, above, f1m),
        "R-DOMAIN-X-RANGE", "nonzero |x| = 2^33 > 2^32 (row sum 2^33 stays within 2^40)")
    # G-ROWSUM probe: 1024 x 2^31 = 2^41 > 2^40
    def rowsum(x, m, k):
        for i in range(k):
            x[i] = pow2_bits("F32", 31)
    ref(qmm_case("ref-rowsum-2p41", 4, 64, "BF16", (1,), 1024, 64, rowsum), "R-DOMAIN-ROWSUM", "sum |x| = 2^41 > 2^40")
    # G-WMAX probe: s = 2^30 -> 255*2^30 > 2^36
    def wmax(codes, scales, biases):
        scales[0] = pow2_bits("BF16", 30)
    ref(qmm_case("ref-wmax-s2p30", 4, 64, "BF16", (1,), 256, 64, None, wmax), "R-DOMAIN-WMAX", "|s|*255 + |b| > 2^36")
    # Astra F3: F16 s=144, q=229, b=32544 (fused sum 65520 rounds to inf)
    def f3(codes, scales, biases):
        codes[0] = 229
        scales[0] = 0x5880   # 144.0 in F16
        biases[0] = 0x77F2   # 32544.0 in F16
    c = dq_case("ref-astra-f3-f16-fused-overflow", 8, 32, "F16", 1, 32, f3)
    assert decode("F16", 0x5880) == 144 and decode("F16", 0x77F2) == 32544
    ref(c, "R-DQ-RANGE", "review F3: |s|q + |b| = 65520 > 0.5*65504")
    # R-DQ-NORMAL probe: F16 s=2^-13, q=1, b=-(2^-13 - 2^-23) -> P + b = 2^-23 < 2^-14
    def dqn(codes, scales, biases):
        codes[0] = 1
        scales[0] = pow2_bits("F16", -13)
        biases[0] = encode_normal("F16", 1, -14, 0x3FE)   # -(1 + 1022/1024) * 2^-14 = -(2^-13 - 2^-23)
    c = dq_case("ref-dq-f16-subnormal-result", 4, 32, "F16", 1, 32, dqn)
    assert decode("F16", encode_normal("F16", 1, -14, 0x3FE)) == -(Fraction(2) ** -13 - Fraction(2) ** -23)
    ref(c, "R-DQ-NORMAL", "exact P + b = 2^-23 is nonzero and below lambda_F16")
    # subnormal operands
    def subx(x, m, k):
        x[0] = 0x00100000   # 2^-129 subnormal F32
    ref(qmm_case("ref-subnormal-x", 4, 64, "BF16", (1,), 256, 64, subx), "R-SUBNORMAL", "subnormal x")
    def subs(codes, scales, biases):
        scales[0] = 0x0010    # F16 subnormal 2^-20
    ref(dq_case("ref-subnormal-scale-dq-f16", 4, 32, "F16", 1, 64, subs), "R-SUBNORMAL", "subnormal F16 scale (dequantize)")
    # non-finite
    def nanx(x, m, k):
        x[5] = 0x7FC00000
    ref(qmm_case("ref-nonfinite-x-nan", 4, 64, "BF16", (1,), 256, 64, nanx), "R-NONFINITE", "NaN in x")
    def infs(codes, scales, biases):
        scales[1] = 0x7F80    # BF16 +inf
    ref(dq_case("ref-nonfinite-scale-inf", 4, 64, "BF16", 2, 128, infs), "R-NONFINITE", "inf scale")
    # structural
    ref(qmm_case("ref-transpose-false", 4, 64, "BF16", (1,), 256, 64, transpose=False), "R-TRANSPOSE", "test-only entry point")
    ref(qmm_case("ref-x-f16", 4, 64, "F16", (1,), 256, 64, xdtype="F16"), "R-XDTYPE", "x float16")
    ref(qmm_case("ref-x-bf16", 4, 64, "BF16", (1,), 256, 64, xdtype="BF16"), "R-XDTYPE", "x bfloat16")
    for b in (2, 3, 5, 6):
        c = Case("ref-bits-%d" % b, "FX-REFUSE", "quantized_matmul")
        rng = SplitMix64(case_seed(c.id))
        c.add("x", "F32", (1, 32), draw_x(rng, 32))
        c.add("w", "U32", (64, b), [rng.next() & 0xFFFFFFFF for _ in range(64 * b)])
        c.add("scales", "BF16", (64, 1), draw_meta(rng, "BF16", 64, "scale"))
        c.add("biases", "BF16", (64, 1), draw_meta(rng, "BF16", 64, "bias"))
        c.params = {"bits": b, "group_size": 32, "metadata_dtype": "BF16", "transpose": True}
        c._codes = []
        ref(c, "R-BITS", "bits %d" % b)
    for gs, k in ((16, 64), (256, 256)):
        c = qmm_case("ref-group-%d" % gs, 4, 32, "BF16", (1,), k, 64)
        c.params["group_size"] = gs
        c.tensors = [t for t in c.tensors if t[0] not in ("scales", "biases")]
        rng = SplitMix64(case_seed(c.id + "/meta"))
        c.add("scales", "BF16", (64, k // gs), draw_meta(rng, "BF16", 64 * (k // gs), "scale"))
        c.add("biases", "BF16", (64, k // gs), draw_meta(rng, "BF16", 64 * (k // gs), "bias"))
        ref(c, "R-GROUP", "group size %d" % gs)
    c = qmm_case("ref-n-not-64-aligned", 4, 32, "BF16", (1,), 64, 8)
    ref(c, "R-GEOMETRY", "N = 8 (N % 64 != 0; qmv_quad tail, review F5)")
    def zx(x, m, k):
        for i in range(len(x)):
            x[i] = 0
    def zc(codes, scales, biases):
        for i in range(len(codes)):
            codes[i] = 0
    c = qmm_case("ref-k-over-cap", 4, 32, "BF16", (1,), 16416, 64, zx, zc)
    ref(c, "R-GEOMETRY", "K = 16416 > 16384")
    c = qmm_case("ref-n-over-cap", 4, 32, "BF16", (1,), 32, 16448, zx, zc)
    ref(c, "R-GEOMETRY", "N = 16448 > 16384")
    c = qmm_case("ref-m-over-cap", 4, 32, "BF16", (4097,), 32, 64, zx, zc)
    ref(c, "R-GEOMETRY", "M_eff = 4097 > 4096")
    c = qmm_case("ref-x-rank4", 4, 32, "BF16", (1, 1, 2), 32, 64)
    ref(c, "R-XSHAPE", "x rank 4")
    c = qmm_case("ref-x-lastdim-mismatch", 4, 32, "BF16", (1,), 64, 64)
    c.tensors = [t if t[0] != "x" else ("x", "F32", [1, 32], t[3][:32]) for t in c.tensors]
    ref(c, "R-XSHAPE", "x.shape[-1] = 32 != K = 64")
    c = qmm_case("ref-meta-dtype-mismatch", 4, 32, "BF16", (1,), 64, 64)
    c.tensors = [t if t[0] != "biases" else ("biases", "F16", t[2], [v & 0x7BFF for v in t[3]]) for t in c.tensors]
    ref(c, "R-META", "scales BF16, biases F16")
    c = qmm_case("ref-meta-shape-mismatch", 4, 32, "BF16", (1,), 64, 64)
    c.tensors = [t if t[0] != "biases" else ("biases", "BF16", [64, 1], t[3][:64]) for t in c.tensors]
    ref(c, "R-META", "biases shape [64,1] != scales [64,2]")
    c = qmm_case("ref-weight-rank3", 4, 32, "BF16", (1,), 64, 64)
    c.tensors = [t if t[0] != "w" else ("w", "U32", [1, 64, 8], t[3]) for t in c.tensors]
    ref(c, "R-WDTYPE", "weight rank 3")
    c = qmm_case("ref-weight-f32", 4, 32, "BF16", (1,), 64, 64)
    c.tensors = [t if t[0] != "w" else ("w", "F32", t[2], [0x3F800000] * len(t[3])) for t in c.tensors]
    ref(c, "R-WDTYPE", "weight dtype F32")
    c = qmm_case("ref-cpu-context", 4, 64, "BF16", (1,), 256, 64)
    c.params["context"] = "cpu"
    ref(c, "R-DEVICE", "CPU-device context (negative control E6)")
    # empty dimensions (review R2-2); R-EMPTY-DIM precedes every division by a dimension
    def zeros_x(x, m, k):
        for i in range(len(x)):
            x[i] = 0
    ref(qmm_case("ref-astra-r2-2-n-zero", 4, 64, "BF16", (1,), 64, 0, zeros_x),
        "R-EMPTY-DIM", "review R2-2 exact example: x F32 [1,64] zero, w U32 [0,8], scales/biases BF16 [0,1]")
    ref(qmm_case("ref-empty-m-zero", 4, 64, "BF16", (0,), 64, 64), "R-EMPTY-DIM", "M = 0: x [0,64]")
    ref(qmm_case("ref-empty-k-zero", 4, 64, "BF16", (1,), 0, 64), "R-EMPTY-DIM", "K = 0: x [1,0], w [64,0], scales/biases [64,0]")
    ref(dq_case("ref-dq-empty-rows", 4, 64, "BF16", 0, 64), "R-EMPTY-DIM", "dequantize with empty metadata rows: w [0,8], scales/biases [0,1]")
    ref(dq_case("ref-dq-empty-k", 8, 64, "BF16", 4, 0), "R-EMPTY-DIM", "dequantize with K = 0: w [4,0], scales/biases [4,0]")
    return out


# ----------------------------------------------------------------- output ----
def build(out_dir: Path, check: bool) -> int:
    gen_bytes = Path(__file__).read_bytes()
    cases = population()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case id"
    manifest_cases = []
    files = {}
    for c in cases:
        if c.op in ("quantized_matmul", "dequantize"):
            G = guard_results(c)
            viol = violations(G)
            if c.expected["outcome"] == "accept":
                # admitted: every guard evaluated and satisfied
                assert viol == [] and not_evaluable(G) == [], (c.id, viol, not_evaluable(G))
            else:
                # refusal probe: EXACTLY ONE guard violated, and it is the expected one
                assert viol == [c.expected["refusal_id"]], (c.id, viol, c.expected["refusal_id"])
                c.expected["violated_guards"] = viol
                c.expected["not_evaluable_guards"] = not_evaluable(G)
        blob = bytearray()
        tensors = []
        for name, dtype, shape, vals in c.tensors:
            b = to_bytes(dtype, vals)
            tensors.append({"name": name, "dtype": dtype, "shape": shape, "offset": len(blob),
                            "nbytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
            blob += b
        entry = {"id": c.id, "family": c.family, "op": c.op, "params": c.params,
                 "expected": c.expected, "references": c.references}
        if tensors:
            fname = "cases/%s.bin" % c.id
            files[fname] = bytes(blob)
            entry["file"] = fname
            entry["file_sha256"] = hashlib.sha256(blob).hexdigest()
            entry["tensors"] = tensors
        manifest_cases.append(entry)
    manifest = {
        "schema": SCHEMA,
        "contract_schema": CONTRACT_SCHEMA,
        "generator": "scripts/research/f020_native_primitives_fixtures_v1.py",
        "generator_sha256": hashlib.sha256(gen_bytes).hexdigest(),
        "constants": {"E_LO": E_LO, "E_HI": E_HI, "ROWSUM_MAX": "2^40", "WMAX": "2^36",
                      "K_MAX": K_MAX, "N_MAX": N_MAX, "M_MAX": M_MAX, "N_ALIGN": N_ALIGN,
                      "PY_EXACT_MAC_LIMIT": PY_EXACT_MAC_LIMIT, "CHILD_TIMEOUT_SECONDS": CHILD_TIMEOUT_SECONDS,
                      "refusal_order": REFUSAL_ORDER},
        "encoding": "each case file is the concatenation of its tensors' little-endian bytes in manifest order; U32/F32 as 4-byte words, F16/BF16 as 2-byte words",
        "case_count": len(manifest_cases),
        "cases": manifest_cases,
    }
    files["manifest.json"] = (json.dumps(manifest, indent=1, sort_keys=False) + "\n").encode()
    if check:
        bad = 0
        for rel, data in files.items():
            p = out_dir / rel
            if not p.is_file() or p.read_bytes() != data:
                print("MISMATCH", rel)
                bad += 1
        present = {str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()}
        extra = present - set(files)
        for rel in sorted(extra):
            print("UNEXPECTED", rel)
        return 1 if bad or extra else 0
    (out_dir / "cases").mkdir(parents=True, exist_ok=True)
    for rel, data in files.items():
        (out_dir / rel).write_bytes(data)
    print("wrote %d cases, %d files, %d bytes" % (len(manifest_cases), len(files), sum(len(d) for d in files.values())))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    return build(a.out, a.check)


if __name__ == "__main__":
    sys.exit(main())

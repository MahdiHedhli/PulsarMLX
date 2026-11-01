#!/usr/bin/env python3
"""Independent row-streamed original-byte affine reference; no native imports.

No CLI reads real bytes. Caller must first validate exact-version capability
and selected snapshot custody. This module consumes immutable original buffers.
"""
from fractions import Fraction as F
import struct
import hashlib

INPUT_SHA256 = "746ed37cdd4a6a1792ec512ada02f9a2bd2cfa9c5a88d2eae2758ccbd9b2d799"
from f020_expert_mlp_r1_v1 import activation

X_EXP = 55
W_EXP = 39
E_ACT = F(1, 128)


def units(word, bf=False):
    """Exact units for admitted F32/BF16, with original-bit domain checks."""
    if bf:
        word <<= 16
    e, mant = (word >> 23) & 255, word & 0x7fffff
    if e == 255:
        raise ValueError('R-NONFINITE')
    if e == 0:
        if mant:
            raise ValueError('R-SUBNORMAL')
        return 0
    mant |= 1 << 23
    power = e - 150
    # Compare exactly before shifting; all admitted nonzero values [2^-32,2^32].
    value = F(mant) * (F(2)**power)
    if not F(1,2**32) <= value <= 2**32:
        raise ValueError('R-DOMAIN-META-RANGE' if bf else 'R-DOMAIN-X-RANGE')
    shift = power + (W_EXP if bf else X_EXP)
    if shift < 0:
        if mant % (1 << -shift):
            raise ValueError('nonintegral admitted units')
        result = mant >> -shift
    else:
        result = mant << shift
    return -result if word >> 31 else result


def original_input(raw, k):
    if type(raw) is not bytes or len(raw) != k*4:
        raise ValueError('original immutable F32 byte count')
    values = [units(t[0]) for t in struct.iter_unpack('<I', raw)]
    if sum(map(abs,values)) > 1 << (40+X_EXP):
        raise ValueError('R-DOMAIN-ROWSUM')
    return values


class Plane:
    """Immutable packed source, no dense decoded weight representation."""
    def __init__(self, role, parts):
        if role not in ('gate','up','down'):
            raise ValueError('R1 role')
        self.n, self.k = (4096,2048) if role=='down' else (2048,4096)
        if len(parts)!=3 or any(type(p) is not bytes for p in parts):
            raise ValueError('immutable original buffers required')
        expected = (self.n*self.k//2, self.n*self.k//32, self.n*self.k//32)
        if tuple(map(len,parts)) != expected:
            raise ValueError('R1 plane byte count')
        self.parts = tuple(memoryview(p) for p in parts)

    def groups(self, row):
        """At most 64 metadata pairs and a packed row are transient."""
        if not 0 <= row < self.n:
            raise ValueError('row')
        groups = self.k//64
        w,s,b = self.parts
        for group in range(groups):
            pos = (row*groups+group)*2
            su = units(struct.unpack_from('<H',s,pos)[0],True)
            bu = units(struct.unpack_from('<H',b,pos)[0],True)
            if 255*abs(su)+abs(bu) > 1 << (36+W_EXP):
                raise ValueError('R-DOMAIN-WMAX')
            offset = row*(self.k//2)+group*32
            yield group, w[offset:offset+32], su, bu


def code(packed, j):
    # Byte nibble interpretation, independent of native U32 decoder.
    return (packed[j//2] >> (4*(j%2))) & 15


def gamma(k):
    if k not in (2048,4096):
        raise ValueError('R1 geometry scope')
    n = k//16+17  # pinned M1/4-bit qmv_fast bound_exponent
    return F(n, 2**24-n)


def affine(plane, x):
    if len(x)!=plane.k:
        raise ValueError('R1 x geometry')
    exact, bounds = [], []
    denominator = 1 << (X_EXP+W_EXP)
    for row in range(plane.n):
        total = phi = 0
        for group, packed, s, b in plane.groups(row):
            base = group*64
            for j in range(64):
                q = code(packed,j)
                v = x[base+j]
                total += v*(s*q+b)
                phi += abs(v)*(abs(s)*q+abs(b))
        exact.append(F(total,denominator))
        bounds.append(gamma(plane.k)*F(phi,denominator))
    return exact, bounds


class AdmissionRefusal(ValueError):
    def __init__(self,reason,evidence):
        super().__init__(reason)
        self.evidence=evidence


def hidden_admission(g,u,bg,bu):
    hidden, bounds = [], []
    for lane,(gc,uc,gb,ub) in enumerate(zip(g,u,bg,bu,strict=True)):
        evidence={"lane":lane,"g":str(gc),"u":str(uc),"bg":str(gb),"bu":str(ub)}
        if not (-16 <= gc-gb <= gc+gb <= 16 and -16 <= uc-ub <= uc+ub <= 16):
            raise AdmissionRefusal('prospective activation margin',evidence)
        lo,hi = activation(gc,uc)
        bh = 20*gb+10*ub+E_ACT
        evidence.update(hidden_interval=[str(lo),str(hi)],bh=str(bh))
        if (gc==0 and gb==0) or (uc==0 and ub==0):
            lo=hi=bh=F(0)
        elif not (lo-bh>=F(1,2**32) or hi+bh<=-F(1,2**32)):
            raise AdmissionRefusal('prospective down nonzero floor margin',evidence)
        if max(abs(lo-bh),abs(hi+bh))>2**32:
            raise AdmissionRefusal('prospective down magnitude margin',evidence)
        hidden.append((lo,hi)); bounds.append(bh)
    if sum(max(abs(lo-b),abs(hi+b)) for (lo,hi),b in zip(hidden,bounds))>2**40:
        raise ValueError('prospective down row sum margin')
    return hidden,bounds


def ideal_down(plane, hidden, bh):
    """Integer interval contraction, outward rounding only at row end.

    Original h interval endpoints lie on 2^-256 lattice. Exact sums contain
    all ideal values; rounding only at the end is an enclosure, not a budget
    increase. No candidate values accepted by this function.
    """
    if plane.k!=len(hidden) or len(bh)!=plane.k:
        raise ValueError('hidden geometry')
    lattice = 1 << 256
    endpoints=[]
    for lo,hi in hidden:
        a,b=lo*lattice,hi*lattice
        if a.denominator!=1 or b.denominator!=1:
            raise ValueError('hidden lattice')
        endpoints.append((a.numerator,b.numerator))
    # Bh denominators share fixed gamma denominator: lcm gives bounded exact
    # integer accumulation rather than Fraction allocation per weight.
    from math import lcm
    bd=1
    for v in bh:
        bd=lcm(bd,v.denominator)
    bi=[int(v*bd) for v in bh]
    ys,propagated=[],[]
    for row in range(plane.n):
        yl=yh=pb=0
        for group,packed,s,b in plane.groups(row):
            for j in range(64):
                weight=s*code(packed,j)+b
                lo,hi=endpoints[group*64+j]
                a,c=weight*lo,weight*hi
                yl+=min(a,c); yh+=max(a,c)
                pb+=abs(weight)*bi[group*64+j]
        div=1 << W_EXP
        ys.append((F(yl//div,lattice),F(-((-yh)//div),lattice)))
        propagated.append(F(pb,bd*div))
    return ys,propagated


def references(parts, original_x):
    """Original plane mapping only; custody/review gate is caller's obligation."""
    if hashlib.sha256(original_x).hexdigest() != INPUT_SHA256:
        raise ValueError('R1 original input identity')
    if set(parts)!= {'gate','up','down'}:
        raise ValueError('R1 roles')
    x=original_input(original_x,4096)
    g,bg=affine(Plane('gate',parts['gate']),x)
    u,bu=affine(Plane('up',parts['up']),x)
    h,bh=hidden_admission(g,u,bg,bu)
    y,propagated=ideal_down(Plane('down',parts['down']),h,bh)
    return {'g':g,'u':u,'bg':bg,'bu':bu,'h':h,'bh':bh,'y':y,'propagated':propagated}

#!/usr/bin/env python3
"""Independent rational R1. No MLX, candidate, production decoder or generator imports."""
from fractions import Fraction as F
from functools import lru_cache
import json, math, struct

PRECISION = 256
E_ACT = F(1, 128)

def enclose(lo, hi):
    """Outward projection onto a fixed dyadic lattice, never host float rounding."""
    d = 1 << PRECISION
    return F((lo*d).__floor__(), d), F((hi*d).__ceil__(), d)

def mul(a, b):
    p = [x*y for x in a for y in b]
    return enclose(min(p), max(p))

@lru_cache(maxsize=8192)
def exp_interval(z):
    if abs(z) > 16:
        raise ValueError('R1 exp domain')
    a = abs(z)/32
    term = total = F(1)
    for n in range(1, 65):
        term *= a/n
        total += term
    tail = a**65 / math.factorial(65) / (1-a/66)
    lo, hi = enclose(total, total+tail)
    for _ in range(5):
        lo, hi = enclose(lo*lo, hi*hi)
    if z < 0:
        return enclose(1/hi, 1/lo)
    return lo, hi

@lru_cache(maxsize=8192)
def activation(g, u):
    if abs(g)>16 or abs(u)>16:
        raise ValueError('R1 activation domain')
    g = min(g, F(10)); u = min(max(u, F(-10)), F(10))
    lo, hi = exp_interval(-g)
    sig = enclose(1/(1+hi), 1/(1+lo))
    h = mul(mul((g,g), sig), (u,u))
    if h[1]-h[0] > F(1, 2**160):
        raise ValueError('R1 fixed width exceeded')
    return h

def f32(word):
    sign = -1 if word>>31 else 1
    e = (word>>23)&255; m = word&0x7fffff
    if e==255: raise ValueError('nonfinite F32')
    if e: m |= 1<<23
    exponent = e-150 if e else -149
    return sign * (F(m<<exponent) if exponent>=0 else F(m,1<<-exponent))

def bf16(word):
    return f32(word<<16)

def read_checkpoint(path):
    """Independent standard-library Safetensors parser; offsets relative to data."""
    raw = path.read_bytes()
    n = struct.unpack_from('<Q', raw)[0]
    header = json.loads(raw[8:8+n]); data = raw[8+n:]
    out = {}
    for name, t in header.items():
        if name=='__metadata__': continue
        lo, hi = t['data_offsets']
        fmt = {'U32':'I','BF16':'H'}[t['dtype']]
        size = struct.calcsize(fmt)
        if hi-lo != math.prod(t['shape'])*size:
            raise ValueError('independent tensor byte count')
        out[name] = (t['shape'], list(struct.unpack('<'+fmt*((hi-lo)//size), data[lo:hi])))
    return out

def plane(tensors, role, e, bits, n, k):
    prefix = 'synthetic.experts.'+role
    shape, words = tensors[prefix+'.weight']
    ps = k*bits//32; groups=k//64
    if shape != [3,n,ps]: raise ValueError('R1 packed shape')
    result=[]; envelopes=[]
    scales=tensors[prefix+'.scales']; biases=tensors[prefix+'.biases']
    if scales[0]!=[3,n,groups] or biases[0]!=[3,n,groups]:
        raise ValueError('R1 metadata shape')
    for row in range(n):
        w=[]; a=[]
        for col in range(k):
            word=words[(e*n+row)*ps+col//(32//bits)]
            q=(word >> ((col%(32//bits))*bits)) & ((1<<bits)-1)
            ix=(e*n+row)*groups+col//64
            s=bf16(scales[1][ix]); b=bf16(biases[1][ix])
            w.append(s*q+b); a.append(abs(s)*q+abs(b))
        result.append(w); envelopes.append(a)
    return result,envelopes

def gamma_n(m,n,k):
    if m==1: return k//4+5
    if m!=32: raise ValueError('population outside frozen M=1,32')
    tiles=((n+31)//32)*((m+31)//32)
    sk=min(max(512//tiles,1), k//64)
    while k%(sk*64): sk-=1
    return k//sk+sk+3 if sk>1 else k+3

def qmm(x, plane_data):
    w, envelopes=plane_data
    m=len(x); n=len(w); k=len(w[0]); ng=gamma_n(m,n,k)
    gamma=F(ng, (1<<24)-ng)
    exact=[]; bound=[]; cache={}
    for xr in x:
        key=tuple(xr)
        if key not in cache:
            cache[key]=([sum((a*b for a,b in zip(xr,wr)),F(0)) for wr in w],
                        [gamma*sum((abs(a)*b for a,b in zip(xr,ar)),F(0)) for ar in envelopes])
        er,br=cache[key];exact.append(er);bound.append(br)
    return exact,bound

def references(case, tensors, x):
    d,h=case['D'],case['H']; e=case['expert']; profile=case['profile']
    gate=plane(tensors,'gate',e,8 if profile=='mixed' else 4,h,d)
    up=plane(tensors,'up',e,4,h,d)
    down=plane(tensors,'down',e,8 if profile=='mixed' else 4,d,h)
    g,bg=qmm(x,gate); u,bu=qmm(x,up)
    hs=[]; bh=[]
    for row in range(len(x)):
        hi=[]; bi=[]
        for col in range(h):
            gc,uc=g[row][col],u[row][col]
            if gc-bg[row][col]<-16 or gc+bg[row][col]>16 or uc-bu[row][col]<-16 or uc+bu[row][col]>16:
                raise ValueError('prospective activation margin')
            ref=activation(gc,uc)
            b=20*bg[row][col]+10*bu[row][col]+E_ACT
            # Exact zero follows from the corresponding zero Phi, hence zero
            # local QMM budget, and multiplication of finite values by zero.
            zero=(gc==0 and bg[row][col]==0) or (uc==0 and bu[row][col]==0)
            if zero: b=F(0); ref=(F(0),F(0))
            elif not (ref[0]-b>=F(1,2**32) or ref[1]+b<=-F(1,2**32)):
                raise ValueError('prospective down nonzero floor margin')
            if max(abs(ref[0]-b),abs(ref[1]+b))>2**32:
                raise ValueError('prospective down magnitude margin')
            hi.append(ref); bi.append(b)
        if sum(max(abs(a-b),abs(c+b)) for (a,c),b in zip(hi,bi))>2**40:
            raise ValueError('prospective down row sum margin')
        hs.append(hi); bh.append(bi)
    ys=[]; propagated=[]; cache={}
    for hr,br in zip(hs,bh):
        key=(tuple(hr),tuple(br))
        if key in cache:
            yr,bp=cache[key];ys.append(yr);propagated.append(bp);continue
        yr=[]; bp=[]
        for wr in down[0]:
            terms=[mul(a,(b,b)) for a,b in zip(hr,wr)]
            yr.append(enclose(sum(a for a,b in terms),sum(b for a,b in terms)))
            bp.append(sum(abs(w)*b for w,b in zip(wr,br)))
        cache[key]=(yr,bp);ys.append(yr); propagated.append(bp)
    return {'g':g,'u':u,'bg':bg,'bu':bu,'h':hs,'bh':bh,'y':ys,'propagated':propagated,'down':down}

def distance_pass(observed, interval, budget):
    # Both endpoints bound distance; uncertainty stays on the distance side.
    return max(abs(observed-interval[0]),abs(observed-interval[1]))<=budget

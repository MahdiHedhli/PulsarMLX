"""Prospective scientific gates for stored BF16 outputs and FP32 router scores.

A precision target, NOT a proof that every 45-layer execution differs by at most
one BF16 neighbor. Failure/ambiguity preserves the original population and
input. Inspect only independently sealed originals in a separate grader.
"""
import numpy as np

from studio017_ref_store import finite, require


def interval_bf16(values):
    """Adjacent BF16 values; directed nonuniform intervals at powers of two."""
    a=np.asarray(values)
    require(a.dtype==np.dtype('<f4') and a.ndim>0,'BF16 F32-carrier array')
    finite(a)
    bits=a.view('<u4')
    require(not np.any(bits&0xffff),'value not represented in BF16')
    # Monotone rank with both signed zeros merged into the same numeric zero.
    mag=(bits>>16 & 0x7fff).astype(np.int32)
    rank=np.where(bits>>31!=0,-mag,mag)
    require(np.all(np.abs(rank)<0x7f7f),'outer finite BF16 neighbor unavailable')
    def invert(r):
        v=(np.abs(r).astype('<u4') | np.where(r<0,0x8000,0).astype('<u4'))<<16
        return v.view('<f4')
    return invert(rank-1),invert(rank+1)


def bf_stage(ref,actual):
    require(isinstance(ref,np.ndarray) and isinstance(actual,np.ndarray) and ref.shape==actual.shape,'stage shape')
    lo,hi=interval_bf16(ref)
    interval_bf16(actual)
    return dict(total=int(ref.size),outside=int(np.count_nonzero((actual<lo)|(actual>hi))),
                max_abs=float(np.max(np.abs(actual.astype('f8')-ref.astype('f8')))))


def golden_margin(ref):
    require(ref.ndim==1 and ref.size>=2,'vocabulary')
    lo,hi=interval_bf16(ref)
    order=np.lexsort((np.arange(len(ref)), -ref))
    win,runner=map(int,order[:2])
    competitors=np.arange(len(ref))!=win
    margin=float(ref[win])-float(ref[runner])
    worst=float(lo[win])-float(hi[competitors].max())
    return dict(winner=win,runner_up=runner,margin=margin,robust_lower_gap=worst,
                eligible=bool(worst>0))


def logits_result(ref,actual,returned_id):
    r=golden_margin(ref); m=bf_stage(ref,actual)
    peak=int(np.argmax(actual))
    # A tie or unstable winner cannot satisfy the strict scientific criterion.
    return dict(**m,**r,actual_id=peak,pass_all=bool(r['eligible'] and m['outside']==0 and
                type(returned_id) is int and peak==returned_id==r['winner']))


def route_eps(v):
    # Strict prospective target inherited at unchanged numeric units from the
    # qualified isolated FP32 selector (router-caller-v1/contract.md). It does
    # not assert upstream BF16 layers always preserve this target.
    return 4e-5+4e-6*np.abs(np.asarray(v,dtype=np.float64))


def route_margin(corrected,selected):
    x=np.asarray(corrected)
    require(x.ndim==1 and x.dtype==np.dtype('<f4'),'corrected score type')
    finite(x)
    require(isinstance(selected,(list,tuple)) and
            all(type(i) is int and 0<=i<len(x) for i in selected) and
            0<len(selected)<len(x) and len(set(selected))==len(selected),'selected expert ids')
    ranking=np.lexsort((np.arange(len(x)), -x))
    require(set(selected)==set(map(int,ranking[:len(selected)])),'corrected scores disagree with selected ids')
    mask=np.zeros(len(x),bool);mask[list(selected)]=True
    centers=x.astype('f8');eps=route_eps(x)
    gap=float(np.min((centers-eps)[mask])-np.max((centers+eps)[~mask]))
    return dict(robust_lower_gap=gap,eligible=bool(gap>0))


def route_result(ref,actual):
    """Each row: corrected F32[E], weights F32[K] aligned with selected IDs."""
    rs,cs=ref['selected'],actual['selected']
    rm=route_margin(ref['corrected'],rs)
    cm=route_margin(actual['corrected'],cs)
    a,r=actual['corrected'],ref['corrected']
    w,v=ref['weights'],actual['weights']
    require(a.shape==r.shape and w.shape==(len(rs),) and v.shape==(len(cs),) and
            w.dtype==v.dtype==np.dtype('<f4') and len(cs)==len(rs),'route fields')
    finite(w);finite(v)
    mapped=dict(zip(cs,v))
    matched=set(rs)==set(cs) and all(abs(float(mapped[id_])-float(expected))<=float(route_eps(expected))
                                     for id_,expected in zip(rs,w))
    return dict(membership_match=set(rs)==set(cs),weights_match=bool(matched),
                ref_robust_gap=rm['robust_lower_gap'],candidate_gap=cm['robust_lower_gap'],
                corrected_max_abs=float(np.max(np.abs(a.astype('f8')-r.astype('f8')))),
                pass_all=bool(rm['eligible'] and matched and np.all(np.abs(a.astype('f8')-r)<=route_eps(r))))

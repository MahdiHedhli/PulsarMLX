"""Host-only reference and acceptance checks; no candidate imports or MLX."""
from fractions import Fraction as F
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).parent))
import f020_expert_mlp_r1_v1 as R

def test_exp_enclosures_and_fixed_width():
    lo,hi=R.exp_interval(F(0));assert lo==hi==1
    lo,hi=R.exp_interval(F(16));assert 8_000_000<lo<hi<9_000_000
    lo,hi=R.exp_interval(F(-16));assert F(1,10_000_000)<lo<hi<F(2,10_000_000)
    for g in [-16,-15,-10,-3,0,10,16]:
        for u in [-16,-10,0,10,16]:
            lo,hi=R.activation(F(g),F(u));assert hi-lo<=F(1,2**160)

def test_upper_gate_and_symmetric_up_clamps_without_lower_gate_clamp():
    assert R.activation(F(16),F(16))==R.activation(F(10),F(10))
    assert R.activation(F(1),F(-16))==R.activation(F(1),F(-10))
    assert R.activation(F(-15),F(1))[0]>R.activation(F(-10),F(1))[1]
    assert R.activation(F(-3),F(0))==(0,0)

def test_reference_uncertainty_cannot_inflate_budget():
    interval=(F(1),F(3,2));budget=F(1,2)
    assert R.distance_pass(F(1),interval,budget)
    assert not R.distance_pass(F(3,4),interval,budget)
    assert not R.distance_pass(F(2),interval,F(1,4))

def test_qmm_budget_uses_pinned_union_rule_and_exact_affine_envelope():
    assert [R.gamma_n(m,n,k) for m,n,k in [(1,64,64),(1,128,128),(32,64,64),(32,128,128)]]==[21,37,67,69]
    data=([[F(2),F(3)]+[F(0)]*62]*64,[[F(4),F(5)]+[F(0)]*62]*64)
    exact,b=R.qmm([[F(1),F(-1)]+[F(0)]*62],data)
    assert exact==[[F(-1)]*64]
    assert b==[[F(21,2**24-21)*9]*64]
    exact,b=R.qmm([[F(0)]*64],data)
    assert exact==b==[[F(0)]*64]

def test_f32_decoder_handles_signed_zero_and_subnormal_exactly():
    assert R.f32(0)==R.f32(0x80000000)==0
    assert R.f32(1)==F(1,2**149)
    assert R.f32(0x3f800000)==1
    assert R.bf16(0x3f80)==1

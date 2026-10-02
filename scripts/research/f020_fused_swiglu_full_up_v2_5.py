"""Pure rational propagation and deterministic controls; no candidate execution."""
from fractions import Fraction as F
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "fixtures/f020-fused-swiglu/full-up-controls-v2-5.json"
BETA_SILU = F(1,8192) + 10*F(1,2**24) + F(1,2**20)
BETA_B = F(5201,4194304)
E_N = F(1,128)
DELTA_MAX = F(27567,4194304)
TAU = F(1,2**126)
NATIVE_PRODUCT_ROUND = F(1,2**17)
NATIVE_FLUSH = 22*TAU

def certify_full_up(delta: F) -> dict:
    if not isinstance(delta, F) or delta < 0 or delta > DELTA_MAX:
        raise ValueError("scalar delta outside inherited bound")
    scalar = delta+BETA_SILU
    if 10+scalar >= 11:
        raise ValueError("native SiLU magnitude envelope not proved")
    # RTNE or RTZ plus optional operand/output FTZ; no Metal RN assumption.
    bound = 10*scalar + NATIVE_PRODUCT_ROUND + NATIVE_FLUSH
    return {"beta_silu":str(BETA_SILU), "scalar_native_error":str(scalar),
            "native_silu_abs_envelope":"11", "product_rounding":str(NATIVE_PRODUCT_ROUND),
            "product_flush":str(NATIVE_FLUSH), "full_up_error_bound":str(bound),
            "E_N":str(E_N), "full_up_leq_E_N":bound <= E_N,
            "inherited_delta_plus_beta_leq_E_N":delta+BETA_B <= E_N}

def scalar_delta_limit() -> F:
    # Derived consequence of the unchanged E_N, not a replacement frozen budget.
    return (E_N-NATIVE_PRODUCT_ROUND-NATIVE_FLUSH)/10-BETA_SILU

def ordered_key(bits: int) -> int:
    return (~bits & 0xffffffff) if bits & 0x80000000 else bits ^ 0x80000000

def from_ordered(key: int) -> int:
    return (key ^ 0x80000000) if key & 0x80000000 else ~key & 0xffffffff

def extended_control_bits(worst: int) -> list[tuple[int,int]]:
    policy = json.loads(POLICY.read_text())
    lo, hi = ordered_key(0xc1800000), ordered_key(0x41800000)
    if type(worst) is not int or not 0 <= worst < 2**32:
        raise ValueError("worst gate bits outside full domain")
    key = ordered_key(worst)
    if not lo <= key <= hi:
        raise ValueError("worst gate bits outside full domain")
    if policy["worst_neighborhood_key_radius"] != 2:
        raise ValueError("neighborhood radius drift")
    gates = [int(x,16) for x in policy["fixed_gate_bits"]]
    for k in range(max(lo,key-2),min(hi,key+2)+1):
        b = from_ordered(k)
        if b not in gates: gates.append(b)
    return [(g,int(u,16)) for g in gates for u in policy["up_bits"]]

def certify_analytic_identities() -> dict:
    # p=s(1-s)=1/4-(s-1/2)^2; exp(t)-2t>=((t-1)^2+1)/2>0.
    # Therefore 2p+tp<=1/2+t*exp(-t)<1, with no sampling premise.
    assert F(2)*F(1,4) == F(1,2)
    assert F(1)-F(1)+F(1,2) == F(1,2)
    assert BETA_SILU == F(1037,8388608)
    assert 10*BETA_SILU+F(1,2**18) == BETA_B
    assert 10*(10+DELTA_MAX+BETA_SILU) < 128
    limit = scalar_delta_limit()
    assert 0 < limit < DELTA_MAX
    at = certify_full_up(limit)
    assert F(at["full_up_error_bound"]) == E_N
    assert not certify_full_up(DELTA_MAX)["full_up_leq_E_N"]
    return {"curvature":"2p+tp <= 1/2+t*exp(-t) < 1",
            "beta_silu":str(BETA_SILU), "full_up_formula":"10*(delta+beta_silu)+2^-17+22*2^-126",
            "derived_scalar_delta_limit":str(limit), "inherited_delta_max":str(DELTA_MAX)}

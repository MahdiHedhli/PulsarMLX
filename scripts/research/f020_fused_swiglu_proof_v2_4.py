#!/usr/bin/env python3
"""Exact static certificate checks; never calls Candidate N/B or MLX."""
from __future__ import annotations
import argparse
from fractions import Fraction as F
from functools import lru_cache
import importlib.util
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "fixtures/f020-fused-swiglu/candidate-b-silu-table-v1.json"
SWEEP = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-native-sweep-v2-3.json"
B_CONTRACT = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-candidate-b-v2.json"
DOWN = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-r1-v1.json"
U = F(1, 2**24)
ETA = F(1, 2**150)
H = F(1, 32)
NODE_ERROR = 10 * U

class ProofError(ValueError):
    pass

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProofError(message)

def pow2(e: int) -> F:
    return F(2**e) if e >= 0 else F(1, 2**-e)

def from_bits(bits: int) -> F:
    sign = -1 if bits & 0x80000000 else 1
    exp = (bits >> 23) & 255
    mantissa = bits & 0x7fffff
    require(exp != 255, "nonfinite table/probe bits")
    if exp == 0:
        return sign * mantissa * pow2(-149)
    return sign * (mantissa + 2**23) * pow2(exp - 150)

def exponent(q: F) -> int:
    e = q.numerator.bit_length() - q.denominator.bit_length()
    if q < pow2(e):
        e -= 1
    return e

def rn32_bits(q: F) -> int:
    """Pure rational IEEE RN-even model, gradual underflow, signed tiny results."""
    sign = 0x80000000 if q < 0 else 0
    q = abs(q)
    if q == 0:
        return sign
    e = exponent(q)
    step = pow2(max(e - 23, -149))
    ratio = q / step
    n, remainder = divmod(ratio.numerator, ratio.denominator)
    if 2 * remainder > ratio.denominator or (2 * remainder == ratio.denominator and n & 1):
        n += 1
    result = n * step
    if result == 0:
        return sign
    if result < pow2(-126):
        return sign | int(result / pow2(-149))
    e = exponent(result)
    require(e <= 127, "rational model overflow")
    mantissa = int(result / pow2(e - 23)) - 2**23
    return sign | ((e + 127) << 23) | mantissa

@lru_cache(maxsize=1)
def r1_module():
    name = "f020_v2_4_independent_r1"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts/research/f020_fused_swiglu_r1_v1.py")
    require(spec is not None and spec.loader is not None, "R1 source missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def certify_ln2() -> None:
    r1 = r1_module()
    # ln2 = 2 atanh(1/3). Each positive tail denominator is at least 2N+1.
    n = 128
    partial = sum((F(2, (2*k+1) * 3**(2*k+1)) for k in range(n)), F(0))
    tail = F(2, (2*n+1) * 3**(2*n+1)) / (1 - F(1, 9))
    require(r1.LN2.lo <= partial and partial + tail <= r1.LN2.hi,
            "R1 ln2 enclosure not independently certified")

@lru_cache(maxsize=833)
def reference_node(i: int):
    r1 = r1_module()
    x = F(i - 512, 32)
    s = r1.sigmoid(x)
    return r1.scale(s, x)

def upper_dyadic(value: F, places: int = 80) -> F:
    ratio = value * 2**places
    n = (ratio.numerator + ratio.denominator - 1) // ratio.denominator
    return F(n, 2**places)

def certify_table(data: dict) -> dict:
    require(data.get("schema") == "pulsarmlx.f020.candidate-b-silu-table/1.0.0",
            "table schema drift")
    nodes = data.get("nodes")
    require(data.get("node_count") == 833 and isinstance(nodes, list) and len(nodes) == 833,
            "833-node population required")
    certify_ln2()
    values = []
    max_error, max_width = F(0), F(0)
    for i, node in enumerate(nodes):
        require(node.get("i") == i and node.get("x_num") == i - 512, "table grid/index drift")
        raw = node.get("silu_f32_bits")
        require(isinstance(raw, str) and re.fullmatch(r"0x[0-9a-fA-F]{8}", raw) is not None,
                "malformed coefficient bits")
        bits = int(raw, 16)
        value = from_bits(bits)
        require(abs(value) <= 10, "coefficient magnitude exceeds10")
        interval = reference_node(i)
        require(interval.width <= pow2(-160), "R1 node enclosure too wide")
        require(rn32_bits(interval.lo) == bits == rn32_bits(interval.hi),
                "coefficient not certified correctly rounded by R1")
        error = max(abs(value - interval.lo), abs(value - interval.hi))
        require(error <= NODE_ERROR, "coefficient exceeds frozen absolute node error")
        max_error, max_width = max(max_error, error), max(max_width, interval.width)
        values.append(value)
    gaps = [abs(b-a) for a,b in zip(values, values[1:])]
    require(all(gap <= 5*H + 2*NODE_ERROR for gap in gaps), "adjacent coefficient gap bound violated")
    return {"nodes": 833, "gaps": 832, "node_error_upper": str(upper_dyadic(max_error)),
            "reference_width_upper": str(upper_dyadic(max_width, 200)),
            "maximum_gap": str(max(gaps)), "correct_rounding": "PASS"}

def certify_ledger() -> dict:
    # Mean-value bound5 and node error bound justify the rounded slope bound.
    difference_error = U*(5*H + 2*NODE_ERROR) + ETA
    slope_error = 32 * difference_error  # multiplication by32 is exact
    require(5 + 64*NODE_ERROR + slope_error < 6, "slope envelope violated")
    delta_error = U*H + ETA
    multiply_error = U*(6*(H+delta_error)) + ETA
    # Exact chord <=10; pre-add perturbations leave magnitude strictly below11.
    before_add_error = slope_error*H + 6*delta_error + multiply_error
    require(10 + before_add_error < 11, "addition magnitude envelope violated")
    addition_error = 11*U + ETA
    interpolation_error = before_add_error + addition_error
    require(interpolation_error < pow2(-20), "interpolation error exceeds frozen envelope")
    require(10*(10 + pow2(-20)) < 128, "product leaves half-ulp2^-18 envelope")
    beta = 10*(F(1,8192) + NODE_ERROR + pow2(-20)) + pow2(-18)
    require(beta == F(5201,4194304), "beta drift")
    return {"slope_error": str(slope_error), "delta_error": str(delta_error),
            "interpolation_error_upper": str(interpolation_error),
            "interpolation_envelope": "1/1048576", "product_envelope": "1/262144",
            "beta_B": str(beta)}

def certify_indices() -> dict:
    probes = {0, 0x80000000, 1, 0x80000001, 0x007fffff, 0x807fffff,
              0x00800000, 0x80800000, 0x00000020, 0x80000020}
    for n in range(-512, 321):
        bits = rn32_bits(F(n,32))
        for offset in (-1,0,1):
            candidate = bits + offset
            if 0 <= candidate <= 0xffffffff and ((candidate >> 23) & 255) != 255:
                if -16 <= from_bits(candidate) <= 16:
                    probes.add(candidate)
    for bits in sorted(probes):
        gate = from_bits(bits)
        g = min(gate, F(10))
        scaled = g*32
        require(from_bits(rn32_bits(scaled)) == scaled, "power-of-two scaling not exact")
        floor = scaled.numerator // scaled.denominator
        i = max(0,min(831,floor+512))
        x0 = F(i-512,32)
        require(from_bits(rn32_bits(x0)) == x0, "grid coordinate not exact")
        exact_delta = g-x0
        require(0 <= exact_delta <= H, "honest interval assignment violated")
        delta = from_bits(rn32_bits(exact_delta))
        require(0 <= delta <= H and abs(delta-exact_delta) <= U*H+ETA,
                "delta RN32 bound violated")
    require(rn32_bits(pow2(-149)*32) == 32, "least-subnormal scaling")
    require(rn32_bits(pow2(-126)/2) == 0x00400000, "normal-input underflow model")
    require((0x41800000+1) + (0xc1800000-0x80000000+1) == 2197815298,
            "full-domain count violated")
    return {"boundary_probes": len(probes), "full_domain_total": 2197815298,
            "all_intervals": 832, "coverage": "analytic theorem plus boundary probes; no sweep executed"}

def certify_contracts(sweep: dict, candidate: dict, down: dict) -> None:
    clarified = json.loads((ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-r1-v2.json").read_text())
    require(all(clarified[key] == down[key] for key in ("input", "admission", "operation", "composition_bound")),
            "R1 clarification changed target/domain/admission")
    require(all(clarified["reference"][key] == down["reference"][key]
                for key in ("name", "target", "independent_of_candidates", "arithmetic", "acceptance", "reference_width")),
            "R1 clarification changed numerical acceptance")
    e = sweep["enumeration"]
    require(e["positive_range"] == ["0x00000000","0x41800000"] and
            e["negative_range"] == ["0x80000000","0xc1800000"] and
            e["expected_positive_count"] == 1098907649 and
            e["expected_negative_count"] == 1098907649 and
            e["expected_total_evaluated"] == 2197815298 and e["batch_elements"] == 1048576,
            "full exhaustive domain/count/batch drift")
    require(sweep["budgets"] == {"beta_B":"5201/4194304","E_N":"1/128","delta_max":"27567/4194304"},
            "frozen numerical budgets drift")
    require(candidate["domain"] == {"gate_after_clamp":[-16,10],"up_after_clamp":[-10,10]},
            "Candidate B domain drift")
    require(candidate["approximation"]["rounding_model"] == "RN32_GRADUAL_UNDERFLOW" and
            candidate["certificate"]["beta_B"] == "5201/4194304",
            "gradual-underflow contract or certificate drift")
    require(down["admission"]["preserve_inherited_down_qmm_contract"] is True and
            down["admission"]["reject"] ==
            ["nonfinite","subnormal","zero","abs(h)<2^-32","abs(h)>2^32","row_abs_sum>2^40"] and
            down["admission"]["no_rescale_or_clip_after_activation"] is True,
            "inherited down admission weakened")

def certify() -> dict:
    certify_contracts(json.loads(SWEEP.read_text()),json.loads(B_CONTRACT.read_text()),json.loads(DOWN.read_text()))
    return {"status":"STATIC_PROOF_PASS", "candidate_observations":0,
            "table":certify_table(json.loads(TABLE.read_text())),
            "ledger":certify_ledger(), "index":certify_indices()}

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        result=certify()
    except (ProofError,KeyError,ValueError) as exc:
        raise SystemExit("F020_V2_4_PROOF_BLOCKER: "+str(exc))
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.output:
        a.output.write_text(text)
    print("F020_V2_4_STATIC_PROOF_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""F020 Slice 2B -- the exact-rational acceptance gates.

Standard library only. This file decides, with ``fractions.Fraction`` and
nothing else, the four gates the frozen contract words as exact rational
comparisons (specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json,
``acceptance_implementation``):

* G-QMM-EXACT   pass iff |y3 - y*| <= (n / (2^24 - n)) * Phi
* G-DQ-EXACT    pass iff |out - w| <= u*(1 + u*)|P| + u*|w|
* G-R1-SELF-QMM pass iff |y1 - y*| <= (K+1)*2^-53 / (1 - (K+1)*2^-53) * Phi
* G-R1-SELF-DQ  pass iff |w_hat - w| <= 2^-53 * |w|

and records the non-gating hypothesis H-DQ-SET per element. The binary64
gates (G-QMM-RUST, G-DQ-RUST) and the bit-exact gates are decided in Rust by
``crates/mlx-native-affine`` (``gates.rs``); the parent combines both, and a
case carrying both references passes only if both decisions pass.

Inputs, all produced upstream and never recomputed here:

* ``--r1-exact``  the exact Python R1 document
  (``scripts/research/mlx_affine_qmm_reference_v1.py``): y*, Phi, P and w as
  exact ``"num/den"`` rationals;
* ``--rust-r1``   the Rust binary64 R1 values (16-hex binary64 bit patterns);
* ``--r3-report`` and ``--r3-dir``  the qualification child's report and its
  raw output files (R3), each checked against the report's sha256;
* ``--manifest``  the frozen manifest, for references and the gamma exponent
  ``n`` (the largest candidate-family exponent it records).

The only arithmetic performed on inputs is exact decoding of stored bit
patterns into rationals and the comparisons above. ``b`` for H-DQ-SET is
``w - P`` from R1, not decoded from the fixture.

Exit status: 0 when the document was produced (the decisions are inside it),
2 when an input was refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from fractions import Fraction
from pathlib import Path

SCHEMA = "pulsarmlx.f020.slice2b-exact-gates/1.0.0"
R1_SCHEMA = "pulsarmlx.f020.r1-exact-native-primitives/1.0.0"
RUST_SCHEMA = "pulsarmlx.f020.r1-rust-binary64/1.0.0"
CHILD_SCHEMA = "pulsarmlx.f020.slice2b-child-report/1.0.0"
MANIFEST_SHA256 = "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04"

TWO24 = 1 << 24
TWO53 = 1 << 53
# (total bits, precision p incl. hidden bit, emin, emax)
FORMATS = {"F32": (32, 24, -126, 127), "F16": (16, 11, -14, 15), "BF16": (16, 8, -126, 127)}
U_STAR = {
    "F32": Fraction(1, 1 << 24),
    "F16": Fraction(1, 1 << 11) + Fraction(1, 1 << 24) + Fraction(1, 1 << 35),
    "BF16": Fraction(1, 1 << 8) + Fraction(1, 1 << 24) + Fraction(1, 1 << 32),
}


class InputError(ValueError):
    pass


def decode(fmt: str, bits: int):
    """Exact value of a stored pattern as a Fraction; None for inf/NaN."""
    width, p, _, _ = FORMATS[fmt]
    ebits = width - p
    bias = (1 << (ebits - 1)) - 1
    sign = -1 if (bits >> (width - 1)) & 1 else 1
    e = (bits >> (p - 1)) & ((1 << ebits) - 1)
    f = bits & ((1 << (p - 1)) - 1)
    if e == (1 << ebits) - 1:
        return None
    if e == 0:
        return sign * Fraction(f, 1 << (p - 1)) * Fraction(2) ** (1 - bias)
    return sign * (1 + Fraction(f, 1 << (p - 1))) * Fraction(2) ** (e - bias)


def binary64(hex_bits: str) -> Fraction:
    value = struct.unpack(">d", bytes.fromhex(hex_bits))[0]
    if not math.isfinite(value):
        raise InputError("non-finite Rust R1 value")
    return Fraction(value)


def rational(text: str) -> Fraction:
    num, den = text.split("/")
    return Fraction(int(num), int(den))


def rn(value: Fraction, fmt: str):
    """Round-to-nearest-even into fmt with gradual underflow; 'inf' on overflow."""
    _, p, emin, emax = FORMATS[fmt]
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
    max_finite = (2 - Fraction(1, 1 << (p - 1))) * Fraction(2) ** emax
    if r > max_finite:
        return "inf"
    return sign * r


def ratio(distance: Fraction, bound: Fraction):
    if bound == 0:
        return 0.0 if distance == 0 else None
    return float(distance / bound)


def read_output(record: dict, r3_dir: Path) -> tuple[str, list]:
    out = record.get("output")
    if not isinstance(out, dict):
        raise InputError("case %s has no output" % record.get("id"))
    data = (r3_dir / out["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != out["sha256"]:
        raise InputError("case %s: R3 output sha256 differs from the report" % record["id"])
    dtype = out["dtype"]
    width = FORMATS[dtype][0] // 8
    fmt = "<%d%s" % (len(data) // width, "I" if width == 4 else "H")
    return dtype, list(struct.unpack(fmt, data))


def gamma_n(case: dict) -> int:
    fams = case["expected"]["families_0_31_2"]
    return max(int(f["gamma_n"]) for f in fams)


def decide_qmm(case, exact, rust, record, r3_dir):
    k = exact["k"]
    n = gamma_n(case)
    dtype, bits = read_output(record, r3_dir)
    if dtype != "F32":
        raise InputError("case %s: R3 output dtype %s" % (case["id"], dtype))
    y_star = [rational(v) for v in exact["y_exact"]]
    phi = [rational(v) for v in exact["phi_exact"]]
    if not len(bits) == len(y_star) == len(phi):
        raise InputError("case %s: element count differs (R3 %d, R1 %d)" % (case["id"], len(bits), len(y_star)))
    gate = {"elements": len(bits), "failed_elements": 0, "worst_ratio": 0.0, "gamma_n": n}
    for b, ys, ph in zip(bits, y_star, phi):
        y3 = decode("F32", b)
        bound = Fraction(n, TWO24 - n) * ph
        if y3 is None:
            gate["failed_elements"] += 1
            gate["worst_ratio"] = None
            continue
        d = abs(y3 - ys)
        if not d <= bound:
            gate["failed_elements"] += 1
        r = ratio(d, bound)
        if r is None or gate["worst_ratio"] is None:
            gate["worst_ratio"] = None
        else:
            gate["worst_ratio"] = max(gate["worst_ratio"], r)
    gate["pass"] = gate["failed_elements"] == 0
    self_gate = None
    if rust is not None:
        y1 = [binary64(v) for v in rust["y"]]
        if len(y1) != len(y_star):
            raise InputError("case %s: Rust R1 length differs" % case["id"])
        self_gate = {"elements": len(y1), "failed_elements": 0, "worst_ratio": 0.0}
        g64 = Fraction(k + 1, TWO53 - (k + 1))
        for a, ys, ph in zip(y1, y_star, phi):
            d = abs(a - ys)
            bound = g64 * ph
            if not d <= bound:
                self_gate["failed_elements"] += 1
            r = ratio(d, bound)
            if r is None or self_gate["worst_ratio"] is None:
                self_gate["worst_ratio"] = None
            else:
                self_gate["worst_ratio"] = max(self_gate["worst_ratio"], r)
        self_gate["pass"] = self_gate["failed_elements"] == 0
    return {"G-QMM-EXACT": gate, "G-R1-SELF-QMM": self_gate}


def decide_dq(case, exact, rust, record, r3_dir):
    meta = exact["metadata_dtype"]
    dtype, bits = read_output(record, r3_dir)
    if dtype != meta:
        raise InputError("case %s: R3 output dtype %s != metadata %s" % (case["id"], dtype, meta))
    w = [rational(v) for v in exact["w_exact"]]
    p = [rational(v) for v in exact["p_exact"]]
    if not len(bits) == len(w) == len(p):
        raise InputError("case %s: element count differs" % case["id"])
    u = U_STAR[meta]
    c1 = u * (1 + u)
    gate = {"elements": len(bits), "failed_elements": 0, "worst_ratio": 0.0}
    hset = {"elements": len(bits), "in_set": 0, "separate": 0, "contracted": 0, "contracted_via_f32": 0}
    for ob, we, pe in zip(bits, w, p):
        out = decode(meta, ob)
        bound = c1 * abs(pe) + u * abs(we)
        if out is None:
            gate["failed_elements"] += 1
            gate["worst_ratio"] = None
            continue
        d = abs(out - we)
        if not d <= bound:
            gate["failed_elements"] += 1
        r = ratio(d, bound)
        if r is None or gate["worst_ratio"] is None:
            gate["worst_ratio"] = None
        else:
            gate["worst_ratio"] = max(gate["worst_ratio"], r)
        # H-DQ-SET (recorded only): which admissible evaluation matches.
        b = we - pe
        rp = rn(pe, meta)
        cands = {
            "separate": rn(rp + b, meta) if rp != "inf" else "inf",
            "contracted": rn(we, meta),
            "contracted_via_f32": (lambda t: rn(t, meta) if t != "inf" else "inf")(rn(we, "F32")),
        }
        hit = False
        for name, v in cands.items():
            if v != "inf" and v == out:
                hset[name] += 1
                hit = True
        hset["in_set"] += hit
    gate["pass"] = gate["failed_elements"] == 0
    self_gate = None
    if rust is not None:
        w_hat = [binary64(v) for v in rust["w"]]
        if len(w_hat) != len(w):
            raise InputError("case %s: Rust R1 length differs" % case["id"])
        self_gate = {"elements": len(w_hat), "failed_elements": 0, "worst_ratio": 0.0}
        for a, we in zip(w_hat, w):
            d = abs(a - we)
            bound = abs(we) / TWO53
            if not d <= bound:
                self_gate["failed_elements"] += 1
            r = ratio(d, bound)
            if r is None or self_gate["worst_ratio"] is None:
                self_gate["worst_ratio"] = None
            else:
                self_gate["worst_ratio"] = max(self_gate["worst_ratio"], r)
        self_gate["pass"] = self_gate["failed_elements"] == 0
    hset["all_in_set"] = hset["in_set"] == hset["elements"]
    return {"G-DQ-EXACT": gate, "G-R1-SELF-DQ": self_gate, "H-DQ-SET": hset}


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--r1-exact", required=True, type=Path)
    ap.add_argument("--rust-r1", required=True, type=Path)
    ap.add_argument("--r3-report", required=True, type=Path)
    ap.add_argument("--r3-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        raw = a.manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
            raise InputError("manifest sha256 differs from the frozen value")
        manifest = json.loads(raw)
        r1 = json.loads(a.r1_exact.read_bytes())
        if r1.get("schema") != R1_SCHEMA or r1.get("manifest_sha256") != MANIFEST_SHA256:
            raise InputError("exact R1 document schema or manifest binding differs")
        rust = json.loads(a.rust_r1.read_bytes())
        if rust.get("schema") != RUST_SCHEMA:
            raise InputError("Rust R1 document schema differs")
        report = json.loads(a.r3_report.read_bytes())
        if report.get("schema") != CHILD_SCHEMA or report.get("manifest_sha256") != MANIFEST_SHA256:
            raise InputError("child report schema or manifest binding differs")
        records = {}
        for rec in report["cases"]:
            if rec["id"] in records:
                raise InputError("duplicate case %s in the child report" % rec["id"])
            records[rec["id"]] = rec
        cases = {}
        for case in manifest["cases"]:
            if "python_exact_r1" not in case.get("references", []):
                continue
            cid = case["id"]
            exact = r1["cases"].get(cid)
            if exact is None:
                raise InputError("exact R1 lacks case %s" % cid)
            rec = records.get(cid)
            rust_rec = rust["cases"].get(cid) if "rust_binary64_r1" in case["references"] else None
            if rec is None or rec.get("outcome") != "executed":
                cases[cid] = {"op": case["op"], "executed": False,
                              "outcome": None if rec is None else rec.get("outcome")}
                continue
            if case["op"] == "quantized_matmul":
                d = decide_qmm(case, exact, rust_rec, rec, a.r3_dir)
            else:
                d = decide_dq(case, exact, rust_rec, rec, a.r3_dir)
            d["op"] = case["op"]
            d["executed"] = True
            cases[cid] = d
    except (InputError, OSError, KeyError, ValueError, TypeError) as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    summary = {}
    for gate in ("G-QMM-EXACT", "G-DQ-EXACT", "G-R1-SELF-QMM", "G-R1-SELF-DQ"):
        decided = [c[gate] for c in cases.values() if c.get(gate) is not None]
        summary[gate] = {"cases": len(decided), "passed_cases": sum(1 for g in decided if g["pass"]),
                         "elements": sum(g["elements"] for g in decided),
                         "failed_elements": sum(g["failed_elements"] for g in decided)}
    hs = [c["H-DQ-SET"] for c in cases.values() if "H-DQ-SET" in c]
    summary["H-DQ-SET"] = {"cases": len(hs), "elements": sum(h["elements"] for h in hs),
                           "in_set": sum(h["in_set"] for h in hs),
                           "separate": sum(h["separate"] for h in hs),
                           "contracted": sum(h["contracted"] for h in hs),
                           "contracted_via_f32": sum(h["contracted_via_f32"] for h in hs),
                           "gating": False}
    summary["not_executed"] = sorted(cid for cid, c in cases.items() if not c["executed"])
    document = {"schema": SCHEMA, "manifest_sha256": MANIFEST_SHA256, "cases": cases, "summary": summary}
    a.out.write_text(json.dumps(document, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())

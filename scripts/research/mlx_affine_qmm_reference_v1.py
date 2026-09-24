#!/usr/bin/env python3
"""R1 (exact) for F020 Slice 2B: exact rational references for OP-QMM and OP-DQ.

Standard library only (``fractions``, ``struct``, ``json``, ``hashlib``,
``operator``, ``argparse``). Nothing here imports MLX or any array library,
the PulsarMLX crates, the Slice 1 references or the frozen fixture generator:
the fixture bytes are parsed by this file's own reader from the manifest's
recorded tensor offsets, dtypes and shapes, and every value is widened from
its bit pattern by this file's own exact conversion. It was written after, and
separately from, the Rust binary64 R1 (``crates/mlx-affine/src/reference_qmm.rs``);
the two share no code and use different arithmetic (exact integers here,
binary64 there), which is what makes their agreement a check.

Contract: specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json
(1.0.0-draft.6), gates G-QMM-EXACT, G-DQ-EXACT, G-R1-SELF-QMM and G-R1-SELF-DQ.

What is computed (exactly, no rounding anywhere)
------------------------------------------------
*  OP-QMM, ``y = x . W^T`` with W stored ``[N, K*bits/32]``:
   ``y*[i, j] = sum_k (s*q + b) * x[i, k]`` and
   ``Phi[i, j] = sum_k (|s|*q + |b|) * |x[i, k]|``, for every x row ``i``
   (``M_eff`` = product of x's leading dimensions) and weight row ``j``.
*  OP-DQ: ``P = s*q`` and ``w = P + b`` for every element of ``[rows, K]``.

Every finite binary16, bfloat16 and binary32 value is an integer multiple of
``2^-24``, ``2^-133`` and ``2^-149`` respectively, so each value is held as an
exact Python integer at that fixed power-of-two scale and the sums are exact
integer arithmetic. That is exact rational arithmetic with a power-of-two
denominator, carried as integers for speed; the results are reported and all
decisions are taken in ``fractions.Fraction``.

Packing: code ``j`` of a weight row occupies bits ``[j*bits, j*bits + bits)``
of the row's little-endian ``uint32`` stream. The row's bytes, read as one
little-endian integer, are exactly that stream, so a code is
``(row_integer >> (j*bits)) & (2^bits - 1)``.

CLI
---
    mlx_affine_qmm_reference_v1.py --manifest fixtures/native-primitives/manifest.json \\
        --cases-dir fixtures/native-primitives (--all | --case ID [--case ID ...]) \\
        --out r1-exact.json [--rust-r1 rust-r1.json]

``--all`` selects exactly the manifest cases whose ``references`` list
``python_exact_r1`` (296 in the frozen population). ``--case`` accepts any
accepted ``dequantize`` or ``quantized_matmul`` case. Every case file's and
tensor's sha256 is checked against the manifest before it is read.

Output (UTF-8 JSON, ``sort_keys``, deterministic, no timing data)::

    {"schema": "pulsarmlx.f020.r1-exact-native-primitives/1.0.0",
     "manifest_sha256": "<hex>",
     "value_encoding": "...",
     "case_count": <int>,
     "cases": {
       "<qmm id>": {"op": "quantized_matmul", "m_eff": M, "n": N, "k": K,
                    "bits": b, "group_size": g, "metadata_dtype": "BF16",
                    "y_exact": ["num/den", ...],      # row-major [M_eff, N]
                    "phi_exact": ["num/den", ...]},   # row-major [M_eff, N]
       "<dq id>":  {"op": "dequantize", "rows": R, "k": K, "bits": b,
                    "group_size": g, "metadata_dtype": "F16",
                    "w_exact": ["num/den", ...],      # row-major [rows, K]
                    "p_exact": ["num/den", ...]}},    # row-major [rows, K]
     "r1_self_check": {...}}                          # only with --rust-r1

Every value is ``"num/den"``: the exact rational in lowest terms, ``den`` a
positive power of two (``"0/1"`` for zero; zero carries no sign).

``--rust-r1`` takes the Rust binary64 R1 values (written by
``crates/mlx-affine/tests/reference_qmm_frozen.rs``) as
``{"schema": "pulsarmlx.f020.r1-rust-binary64/1.0.0", "cases": {id:
{"op": "quantized_matmul", "y": [hex], "phi": [hex]} | {"op": "dequantize",
"w": [hex], "p": [hex]}}}`` where each ``hex`` is the 16-digit binary64 bit
pattern, and decides on every case carrying both references:

*  N-R1-SELF (G-R1-SELF-QMM): ``|y1 - y*| <= (K+1)*2^-53/(1-(K+1)*2^-53) * Phi``;
*  N-R1-SELF-DQ (G-R1-SELF-DQ): ``|w_hat - w| <= 2^-53 * |w|``;

plus two supporting checks of the reference-error statements G-QMM-RUST and
G-DQ-RUST rest on (``|Phi_hat - Phi| <= gamma64_{K+2} * Phi`` and
``P_hat == P``). The exit status is 1 when any decision fails.

Exit status: 0 success, 1 a self-check failed, 2 an input was refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import operator
import struct
import sys
from fractions import Fraction
from pathlib import Path

SCHEMA = "pulsarmlx.f020.r1-exact-native-primitives/1.0.0"
RUST_SCHEMA = "pulsarmlx.f020.r1-rust-binary64/1.0.0"
VALUE_ENCODING = ("each value is the exact rational \"num/den\" in lowest terms; den is a "
                  "positive power of two; zero is \"0/1\" and carries no sign")

# (exponent bits, fraction bits, exponent bias) of each stored float format.
FORMATS = {
    "F16": (5, 10, 15),
    "BF16": (8, 7, 127),
    "F32": (8, 23, 127),
}
# SCALE[d]: every finite value of dtype d times 2^SCALE[d] is an integer
# (the weight of the least significant subnormal bit is 2^(1 - bias - fraction_bits)).
SCALE = {name: bias + fraction - 1 for name, (_, fraction, bias) in FORMATS.items()}
WIDTH = {"U32": 4, "F32": 4, "F16": 2, "BF16": 2}
PACK = {"U32": "I", "F32": "I", "F16": "H", "BF16": "H"}


class InputError(ValueError):
    """An input the reference refuses (bad manifest, hash, shape or value)."""


# ------------------------------------------------------------ exact values --
def scaled_integer(dtype: str, pattern: int) -> int:
    """The exact value of a stored bit pattern times 2^SCALE[dtype], as an int.

    Signed zeros both map to 0. NaN and infinities are refused.
    """
    exponent_bits, fraction_bits, bias = FORMATS[dtype]
    width = 1 + exponent_bits + fraction_bits
    if not 0 <= pattern < (1 << width):
        raise InputError("%s bit pattern out of range: %r" % (dtype, pattern))
    negative = pattern >> (width - 1)
    biased = (pattern >> fraction_bits) & ((1 << exponent_bits) - 1)
    fraction = pattern & ((1 << fraction_bits) - 1)
    if biased == (1 << exponent_bits) - 1:
        raise InputError("%s pattern 0x%x is not finite" % (dtype, pattern))
    if biased == 0:
        magnitude = fraction                                   # fraction * 2^(1-bias-fb)
    else:
        magnitude = ((1 << fraction_bits) | fraction) << (biased - 1)
    return -magnitude if negative else magnitude


def exact(dtype: str, pattern: int) -> Fraction:
    """The exact value of a stored bit pattern as a Fraction."""
    return Fraction(scaled_integer(dtype, pattern), 1 << SCALE[dtype])


def dyadic_string(numerator: int, shift: int) -> str:
    """``numerator / 2^shift`` in lowest terms as "num/den"."""
    if numerator == 0:
        return "0/1"
    trailing = (numerator & -numerator).bit_length() - 1
    cut = min(trailing, shift)
    return "%d/%d" % (numerator >> cut, 1 << (shift - cut))


def parse_rational(text: str) -> Fraction:
    """Inverse of :func:`dyadic_string` (any "num/den" string)."""
    numerator, denominator = text.split("/")
    return Fraction(int(numerator), int(denominator))


def binary64_from_hex(text: str) -> Fraction:
    """The exact value of a 16-hex-digit binary64 bit pattern; refuses NaN and infinities."""
    if len(text) != 16:
        raise InputError("binary64 pattern must be 16 hex digits: %r" % text)
    (value,) = struct.unpack("<d", struct.pack("<Q", int(text, 16)))
    if value != value or value in (float("inf"), float("-inf")):
        raise InputError("binary64 pattern %s is not finite" % text)
    return Fraction(value)


# ------------------------------------------------------------ fixture I/O --
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(path: Path):
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise InputError("manifest has no case list")
    return manifest, sha256_hex(raw)


def read_tensors(case: dict, cases_dir: Path) -> dict:
    """Name -> (dtype, shape, raw bytes, patterns) for a case, hash-checked."""
    relative = case.get("file")
    if not relative:
        raise InputError("case %s has no data file" % case.get("id"))
    blob = (cases_dir / relative).read_bytes()
    if sha256_hex(blob) != case["file_sha256"]:
        raise InputError("case %s: file sha256 differs from the manifest" % case["id"])
    tensors = {}
    end = 0
    for spec in case["tensors"]:
        dtype, shape = spec["dtype"], list(spec["shape"])
        if dtype not in WIDTH:
            raise InputError("case %s: unknown dtype %s" % (case["id"], dtype))
        count = 1
        for dim in shape:
            count *= dim
        offset, nbytes = spec["offset"], spec["nbytes"]
        if nbytes != count * WIDTH[dtype] or offset != end:
            raise InputError("case %s: tensor %s layout is inconsistent" % (case["id"], spec["name"]))
        raw = blob[offset:offset + nbytes]
        if len(raw) != nbytes or sha256_hex(raw) != spec["sha256"]:
            raise InputError("case %s: tensor %s sha256 differs" % (case["id"], spec["name"]))
        patterns = struct.unpack("<%d%s" % (count, PACK[dtype]), raw)
        tensors[spec["name"]] = (dtype, shape, raw, patterns)
        end = offset + nbytes
    if end != len(blob):
        raise InputError("case %s: trailing bytes after the last tensor" % case["id"])
    return tensors


def row_codes(raw_row: bytes, bits: int, k: int):
    """The k codes of one packed row, least significant bit first."""
    stream = int.from_bytes(raw_row, "little")
    mask = (1 << bits) - 1
    return [(stream >> (j * bits)) & mask for j in range(k)]


def _geometry(case: dict, tensors: dict, rows_key: str):
    params = case["params"]
    bits, group = params["bits"], params["group_size"]
    wdtype, wshape, wraw, _ = tensors["w"]
    sdtype, sshape, _, spat = tensors["scales"]
    bdtype, bshape, _, bpat = tensors["biases"]
    if wdtype != "U32" or len(wshape) != 2:
        raise InputError("case %s: weight is not a rank-2 U32 tensor" % case["id"])
    if sdtype not in FORMATS or bdtype != sdtype or sshape != bshape:
        raise InputError("case %s: scales/biases dtype or shape mismatch" % case["id"])
    if bits not in range(1, 9) or group < 1:
        raise InputError("case %s: bits or group size out of range" % case["id"])
    rows, packed = wshape
    if (packed * 32) % bits:
        raise InputError("case %s: packed width is not a whole number of codes" % case["id"])
    k = packed * 32 // bits
    if rows < 1 or k < 1 or k % group or sshape != [rows, k // group]:
        raise InputError("case %s: geometry is inconsistent" % case["id"])
    if params.get("K") != k or params.get(rows_key) != rows or params.get("metadata_dtype") != sdtype:
        raise InputError("case %s: params disagree with the tensors" % case["id"])
    return bits, group, rows, k, packed, sdtype, wraw, spat, bpat


# ----------------------------------------------------------- the two ops --
def exact_dequantize(case: dict, tensors: dict) -> dict:
    bits, group, rows, k, packed, dtype, wraw, spat, bpat = _geometry(case, tensors, "rows")
    scale_shift = SCALE[dtype]
    scales = [scaled_integer(dtype, v) for v in spat]
    biases = [scaled_integer(dtype, v) for v in bpat]
    groups = k // group
    w_out, p_out = [], []
    for r in range(rows):
        codes = row_codes(wraw[r * packed * 4:(r + 1) * packed * 4], bits, k)
        for j, q in enumerate(codes):
            g = r * groups + j // group
            product = scales[g] * q
            p_out.append(dyadic_string(product, scale_shift))
            w_out.append(dyadic_string(product + biases[g], scale_shift))
    return {"op": "dequantize", "rows": rows, "k": k, "bits": bits, "group_size": group,
            "metadata_dtype": dtype, "w_exact": w_out, "p_exact": p_out}


def exact_quantized_matmul(case: dict, tensors: dict) -> dict:
    bits, group, n, k, packed, dtype, wraw, spat, bpat = _geometry(case, tensors, "N")
    xdtype, xshape, _, xpat = tensors["x"]
    if xdtype != "F32" or not 1 <= len(xshape) <= 3 or xshape[-1] != k:
        raise InputError("case %s: x is not an F32 [..., K] tensor of rank 1..3" % case["id"])
    m_eff = 1
    for dim in xshape[:-1]:
        m_eff *= dim
    if m_eff < 1 or case["params"].get("M_eff") != m_eff or case["params"].get("transpose") is not True:
        raise InputError("case %s: M_eff or transpose disagree with the tensors" % case["id"])
    scales = [scaled_integer(dtype, v) for v in spat]
    biases = [scaled_integer(dtype, v) for v in bpat]
    groups = k // group
    weight, envelope = [], []
    for j in range(n):
        codes = row_codes(wraw[j * packed * 4:(j + 1) * packed * 4], bits, k)
        w_row, a_row = [], []
        for t, q in enumerate(codes):
            g = j * groups + t // group
            s, b = scales[g], biases[g]
            w_row.append(s * q + b)
            a_row.append(abs(s) * q + abs(b))
        weight.append(w_row)
        envelope.append(a_row)
    x = [scaled_integer("F32", v) for v in xpat]
    shift = SCALE[dtype] + SCALE["F32"]
    y_out, phi_out = [], []
    for i in range(m_eff):
        x_row = x[i * k:(i + 1) * k]
        x_abs = [abs(v) for v in x_row]
        for j in range(n):
            y_out.append(dyadic_string(sum(map(operator.mul, weight[j], x_row)), shift))
            phi_out.append(dyadic_string(sum(map(operator.mul, envelope[j], x_abs)), shift))
    return {"op": "quantized_matmul", "m_eff": m_eff, "n": n, "k": k, "bits": bits,
            "group_size": group, "metadata_dtype": dtype, "y_exact": y_out, "phi_exact": phi_out}


def exact_case(case: dict, cases_dir: Path) -> dict:
    expected = case.get("expected", {})
    if expected.get("outcome") != "accept":
        raise InputError("case %s is not an accepted case" % case.get("id"))
    tensors = read_tensors(case, cases_dir)
    if case["op"] == "dequantize":
        return exact_dequantize(case, tensors)
    if case["op"] == "quantized_matmul":
        return exact_quantized_matmul(case, tensors)
    raise InputError("case %s: op %s has no R1" % (case["id"], case["op"]))


def select(manifest: dict, all_cases: bool, ids) -> list:
    by_id = {c["id"]: c for c in manifest["cases"]}
    if len(by_id) != len(manifest["cases"]):
        raise InputError("duplicate case id in the manifest")
    if all_cases:
        return [c for c in manifest["cases"] if "python_exact_r1" in c.get("references", [])]
    chosen = []
    for cid in ids:
        if cid not in by_id:
            raise InputError("unknown case id %s" % cid)
        chosen.append(by_id[cid])
    return chosen


# -------------------------------------------------------- R1 self-checks --
TWO53 = 1 << 53


def self_check(manifest: dict, results: dict, rust: dict) -> dict:
    """Decide N-R1-SELF and N-R1-SELF-DQ, exactly, on every dual-reference case."""
    if rust.get("schema") != RUST_SCHEMA or not isinstance(rust.get("cases"), dict):
        raise InputError("the Rust R1 file is not a %s document" % RUST_SCHEMA)
    report = {name: {"cases": 0, "passed_cases": 0, "failed_cases": [], "elements": 0,
                     "failed_elements": 0}
              for name in ("N-R1-SELF", "N-R1-SELF-DQ", "phi_hat_reference_error", "p_hat_exact")}
    dual = [c for c in manifest["cases"]
            if {"rust_binary64_r1", "python_exact_r1"} <= set(c.get("references", []))]
    missing = []

    def tally(name, cid, verdicts):
        entry = report[name]
        entry["cases"] += 1
        entry["elements"] += len(verdicts)
        bad = verdicts.count(False)
        entry["failed_elements"] += bad
        if bad:
            entry["failed_cases"].append(cid)
        else:
            entry["passed_cases"] += 1

    for case in dual:
        cid = case["id"]
        if cid not in results or cid not in rust["cases"]:
            missing.append(cid)
            continue
        exact_rec, rust_rec = results[cid], rust["cases"][cid]
        if rust_rec.get("op") != exact_rec["op"]:
            raise InputError("case %s: Rust R1 op differs" % cid)
        if exact_rec["op"] == "quantized_matmul":
            k = exact_rec["k"]
            y_star = [parse_rational(v) for v in exact_rec["y_exact"]]
            phi = [parse_rational(v) for v in exact_rec["phi_exact"]]
            y1 = [binary64_from_hex(v) for v in rust_rec["y"]]
            phi_hat = [binary64_from_hex(v) for v in rust_rec["phi"]]
            if not len(y_star) == len(phi) == len(y1) == len(phi_hat):
                raise InputError("case %s: Rust R1 length differs" % cid)
            # |y1 - y*| <= (K+1)2^-53 / (1 - (K+1)2^-53) * Phi, multiplied through by
            # the positive 2^53 - (K+1): an exact rational comparison.
            tally("N-R1-SELF", cid, [abs(a - e) * (TWO53 - (k + 1)) <= (k + 1) * f
                                     for a, e, f in zip(y1, y_star, phi)])
            tally("phi_hat_reference_error", cid, [abs(a - f) * (TWO53 - (k + 2)) <= (k + 2) * f
                                                   for a, f in zip(phi_hat, phi)])
        else:
            w = [parse_rational(v) for v in exact_rec["w_exact"]]
            p = [parse_rational(v) for v in exact_rec["p_exact"]]
            w_hat = [binary64_from_hex(v) for v in rust_rec["w"]]
            p_hat = [binary64_from_hex(v) for v in rust_rec["p"]]
            if not len(w) == len(p) == len(w_hat) == len(p_hat):
                raise InputError("case %s: Rust R1 length differs" % cid)
            # |w_hat - w| <= 2^-53 |w|, multiplied through by 2^53.
            tally("N-R1-SELF-DQ", cid, [abs(a - e) * TWO53 <= abs(e) for a, e in zip(w_hat, w)])
            tally("p_hat_exact", cid, [a == e for a, e in zip(p_hat, p)])
    for entry in report.values():
        entry["failed_cases"].sort()
    report["dual_reference_cases"] = len(dual)
    report["missing_cases"] = sorted(missing)
    report["result"] = "PASS" if not missing and all(
        report[n]["failed_elements"] == 0 and report[n]["cases"] > 0
        for n in ("N-R1-SELF", "N-R1-SELF-DQ", "phi_hat_reference_error", "p_hat_exact")) else "FAIL"
    return report


# --------------------------------------------------------------------- CLI --
def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cases-dir", required=True, type=Path)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true")
    which.add_argument("--case", action="append", default=[])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rust-r1", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest, manifest_sha = load_manifest(args.manifest)
        chosen = select(manifest, args.all, args.case)
        results = {c["id"]: exact_case(c, args.cases_dir) for c in chosen}
        document = {"schema": SCHEMA, "manifest_sha256": manifest_sha,
                    "value_encoding": VALUE_ENCODING, "case_count": len(results),
                    "cases": results}
        status = 0
        if args.rust_r1 is not None:
            rust = json.loads(args.rust_r1.read_bytes())
            document["r1_self_check"] = self_check(manifest, results, rust)
            status = 0 if document["r1_self_check"]["result"] == "PASS" else 1
    except (InputError, OSError, KeyError, ValueError, TypeError) as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
                        encoding="utf-8")
    if "r1_self_check" in document:
        check = document["r1_self_check"]
        summary = {n: {k: check[n][k] for k in ("cases", "passed_cases", "elements", "failed_elements")}
                   for n in ("N-R1-SELF", "N-R1-SELF-DQ", "phi_hat_reference_error", "p_hat_exact")}
        print(json.dumps({"result": check["result"], "missing_cases": check["missing_cases"],
                          **summary}, sort_keys=True))
    return status


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
"""R2 for F020 Slice 2B -- a CROSS-VERSION compatibility observation.

This is **not** a reference for the native candidate and it **gates nothing**.
R3 (the qualified candidate) is the source-built MLX 0.31.2 through MLX-C;
this script runs the pinned Python wheel, MLX 0.32.0, which is a different
version with a different build (contract ``version_relation``: "R2 (wheel
0.32.0) is NOT a same-version reference for R3 (native 0.31.2);
cross-version agreement is compatibility evidence only"). Correctness is
defined by R1 alone.

For every accepted OP-DQ and OP-QMM case of the frozen population
(``fixtures/native-primitives/manifest.json``) it runs the same operation the
bridge runs -- ``mx.dequantize`` on the stored metadata dtype, and
``mx.quantized_matmul`` with ``transpose=True``, float32 x, the stored packed
uint32 weight unchanged and the metadata widened with ``mx.astype`` on the
GPU -- and records:

* the label ``CROSS_VERSION_0.32.0_vs_0.31.2`` on every record;
* ``different_kernel_family``, the contract's r2_labelling_predicate
  (transpose and M_eff < L and K not in {64, 128} and M_eff >= 2 and
  generation >= 15; the 0.32.0 quad branch is tested first, so K in {64, 128}
  never routes to qmv_wide);
* optional compatibility margins against the exact R1 document
  (``--r1-exact``), using the contract's bound formulas as a yardstick only
  (``compatibility_observation``), and optional bit-identity counts against
  the R3 outputs (``--r3-report``/``--r3-dir``). Neither is a gate: no bit
  identity is claimed between R3 and R2.

Fail closed. With ``PULSAR_REQUIRE_NATIVE_MLX=1``, an MLX that cannot be
imported, an unavailable Metal, or a GPU selection that does not take is a
failure (exit 1), never a skip. Without it the script still writes a report
that says what happened. A completed observation exits 0 whatever it
observed: disagreements are recorded, not enforced.

Run it with the wheel's own libmlx: ``env -u DYLD_LIBRARY_PATH``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import struct
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "fixtures/native-primitives/manifest.json"
CASES_DIR = ROOT / "fixtures/native-primitives"
MANIFEST_SHA256 = "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04"
SCHEMA = "pulsarmlx.f020.slice2b-r2-cross-version/1.0.0"
LABEL = "CROSS_VERSION_0.32.0_vs_0.31.2"
REQUIRE = os.environ.get("PULSAR_REQUIRE_NATIVE_MLX") == "1"

FORMATS = {"F32": (32, 24, -126, 127), "F16": (16, 11, -14, 15), "BF16": (16, 8, -126, 127)}
U_STAR = {
    "F32": Fraction(1, 1 << 24),
    "F16": Fraction(1, 1 << 11) + Fraction(1, 1 << 24) + Fraction(1, 1 << 35),
    "BF16": Fraction(1, 1 << 8) + Fraction(1, 1 << 24) + Fraction(1, 1 << 32),
}


class Refusal(RuntimeError):
    pass


# --- labelling ---------------------------------------------------------------
def architecture_generation(arch: str) -> int:
    """device.cpp:485-497 (unchanged in 0.32.0): the two characters before the last."""
    def digit(c):
        return ord(c) - 48 if "0" <= c <= "9" else 0
    return digit(arch[-3]) * 10 + digit(arch[-2]) if len(arch) >= 3 else 0


def qmv_batch_limit(k: int, n: int, arch: str) -> int:
    """get_qmv_batch_limit(D=K, O=N), byte-identical in 0.31.2 and 0.32.0."""
    small = k <= 2048 and n <= 2048
    medium = k <= 4096 and n <= 4096

    def pick(a, b, c):
        return a if small else (b if medium else c)
    gen = architecture_generation(arch)
    size = arch[-1:] if arch else ""
    if size == "d":
        return pick(32, 18, 12)
    if gen in (13, 14):
        return pick(14, 10, 6)
    return pick(18, 12, 10)


def different_kernel_family(m_eff: int, k: int, batch_limit: int, generation: int, transpose: bool = True) -> bool:
    """Contract version_relation.r2_labelling_predicate, quad branch first."""
    if k in (64, 128):
        return False
    return bool(transpose and m_eff < batch_limit and m_eff >= 2 and generation >= 15)


# --- exact helpers (for the yardstick only) ----------------------------------
def decode(fmt: str, bits: int):
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


def rational(text: str) -> Fraction:
    a, b = text.split("/")
    return Fraction(int(a), int(b))


def ratio(distance, bound):
    if bound == 0:
        return 0.0 if distance == 0 else None
    return float(distance / bound)


# --- fixture reading (this arm's own plumbing) -------------------------------
def read_case(case: dict) -> dict:
    blob = (CASES_DIR / case["file"]).read_bytes()
    if hashlib.sha256(blob).hexdigest() != case["file_sha256"]:
        raise Refusal("case %s: file sha256 differs from the manifest" % case["id"])
    out = {}
    for t in case["tensors"]:
        raw = blob[t["offset"]:t["offset"] + t["nbytes"]]
        if hashlib.sha256(raw).hexdigest() != t["sha256"]:
            raise Refusal("case %s: tensor %s sha256" % (case["id"], t["name"]))
        out[t["name"]] = {"dtype": t["dtype"], "shape": t["shape"], "bytes": raw}
    return out


def to_mx(mx, np, t):
    shape = tuple(t["shape"])
    if t["dtype"] in ("U32", "F32"):
        a = np.frombuffer(t["bytes"], dtype=np.uint32).reshape(shape)
        arr = mx.array(a)
        return arr if t["dtype"] == "U32" else arr.view(mx.float32)
    a = np.frombuffer(t["bytes"], dtype=np.uint16).reshape(shape)
    return mx.array(a).view(mx.float16 if t["dtype"] == "F16" else mx.bfloat16)


def raw_bits(mx, np, arr):
    width = arr.dtype.size
    view = arr.view(mx.uint32 if width == 4 else mx.uint16)
    mx.eval(view)
    return [int(v) for v in np.array(view).reshape(-1)]


# --- the observation ----------------------------------------------------------
def observe(mx, np, manifest, arch, r1_exact, r3_records, r3_dir):
    gen = architecture_generation(arch)
    records = {}
    for case in manifest["cases"]:
        if case["op"] not in ("dequantize", "quantized_matmul") or case["expected"]["outcome"] != "accept":
            continue
        p = case["params"]
        t = read_case(case)
        rec = {"label": LABEL, "op": case["op"], "compatibility_observation": True, "gates": False}
        if case["op"] == "dequantize":
            out = mx.dequantize(to_mx(mx, np, t["w"]), to_mx(mx, np, t["scales"]), to_mx(mx, np, t["biases"]),
                                group_size=p["group_size"], bits=p["bits"], mode="affine", stream=mx.gpu)
            meta = p["metadata_dtype"]
            rec["different_kernel_family"] = False
            rec["output_dtype"] = str(out.dtype)
        else:
            x = to_mx(mx, np, t["x"])
            s32 = mx.astype(to_mx(mx, np, t["scales"]), mx.float32, stream=mx.gpu)
            b32 = mx.astype(to_mx(mx, np, t["biases"]), mx.float32, stream=mx.gpu)
            out = mx.quantized_matmul(x, to_mx(mx, np, t["w"]), s32, b32, transpose=True,
                                      group_size=p["group_size"], bits=p["bits"], mode="affine", stream=mx.gpu)
            meta = "F32"
            limit = qmv_batch_limit(p["K"], p["N"], arch)
            rec["batch_limit_L"] = limit
            rec["different_kernel_family"] = different_kernel_family(p["M_eff"], p["K"], limit, gen)
            rec["output_dtype"] = str(out.dtype)
        mx.eval(out)
        bits = raw_bits(mx, np, out)
        rec["elements"] = len(bits)
        rec["output_sha256"] = hashlib.sha256(
            struct.pack("<%d%s" % (len(bits), "I" if meta == "F32" else "H"), *bits)).hexdigest()
        exact = (r1_exact or {}).get("cases", {}).get(case["id"])
        if exact is not None:
            worst = 0.0
            over = 0
            if case["op"] == "dequantize":
                u = U_STAR[meta]
                for b, w, pe in zip(bits, exact["w_exact"], exact["p_exact"]):
                    v = decode(meta, b)
                    w, pe = rational(w), rational(pe)
                    bound = u * (1 + u) * abs(pe) + u * abs(w)
                    r = None if v is None else ratio(abs(v - w), bound)
                    over += r is None or r > 1
                    worst = None if (r is None or worst is None) else max(worst, r)
            else:
                n = max(f["gamma_n"] for f in case["expected"]["families_0_31_2"])
                for b, ys, ph in zip(bits, exact["y_exact"], exact["phi_exact"]):
                    v = decode("F32", b)
                    bound = Fraction(n, (1 << 24) - n) * rational(ph)
                    r = None if v is None else ratio(abs(v - rational(ys)), bound)
                    over += r is None or r > 1
                    worst = None if (r is None or worst is None) else max(worst, r)
            rec["margin_vs_exact_r1"] = {"yardstick": "contract bound formula for the 0.31.2 families",
                                         "worst_ratio": worst, "elements_over_yardstick": over}
        r3 = (r3_records or {}).get(case["id"])
        if r3 is not None and r3.get("outcome") == "executed" and r3_dir is not None:
            data = (r3_dir / r3["output"]["file"]).read_bytes()
            width = 4 if r3["output"]["dtype"] in ("F32", "U32") else 2
            r3_bits = list(struct.unpack("<%d%s" % (len(data) // width, "I" if width == 4 else "H"), data))
            same = sum(1 for a, b in zip(bits, r3_bits) if a == b) if len(r3_bits) == len(bits) else None
            rec["bit_identical_to_r3"] = {"elements": len(bits), "identical": same,
                                          "all": same == len(bits), "claimed": False}
        records[case["id"]] = rec
    return records


def acquire_runtime(loader=None):
    """Import the wheel, require Metal, select the GPU and assert it took."""
    mx, np, version, metal_version = (loader or default_loader)()
    if not mx.metal.is_available():
        raise Refusal("Metal is not available")
    mx.set_default_device(mx.gpu)
    if mx.default_device() != mx.gpu:
        raise Refusal("the default device is not the GPU after selecting the GPU")
    return mx, np, version, metal_version


def default_loader():
    from importlib.metadata import version

    import mlx.core as mx
    import numpy as np
    try:
        metal_version = version("mlx-metal")
    except Exception:
        metal_version = None
    return mx, np, version("mlx"), metal_version


def device_architecture(mx) -> str:
    for getter in (getattr(mx, "device_info", None), getattr(mx.metal, "device_info", None)):
        if getter is None:
            continue
        try:
            info = getter()
        except Exception:
            continue
        if isinstance(info, dict) and "architecture" in info:
            return str(info["architecture"])
    return ""


def write(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None, loader=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--r1-exact", type=Path)
    ap.add_argument("--r3-report", type=Path)
    ap.add_argument("--r3-dir", type=Path)
    args = ap.parse_args(argv)
    raw = MANIFEST.read_bytes()
    report = {
        "schema": SCHEMA,
        "arm": "R2",
        "label": LABEL,
        "is_reference_for_r3": False,
        "gates_anything": False,
        "statement": "Cross-version compatibility observation (wheel 0.32.0 vs native 0.31.2). "
                     "Correctness is defined by R1; this arm gates nothing and claims no bit identity.",
        "require_native_mlx": REQUIRE,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
    }
    if report["manifest_sha256"] != MANIFEST_SHA256:
        report["result"] = "REFUSED"
        report["detail"] = "manifest sha256 differs from the frozen value"
        write(args.output, report)
        return 3
    try:
        mx, np, version, metal_version = acquire_runtime(loader)
    except Exception as error:  # ImportError, Refusal and anything the import raises
        report["result"] = "FAILED_CLOSED" if REQUIRE else "NOT_RUN"
        report["detail"] = "MLX is unusable: %r" % (error,)
        write(args.output, report)
        stream = sys.stderr
        print("mlx_native_primitives_compat_v1: %s: %s" % (report["result"], report["detail"]), file=stream)
        return 1 if REQUIRE else 0
    arch = device_architecture(mx)
    report["environment"] = {
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "mlx_version": version,
        "mlx_metal_version": metal_version,
        "default_device": str(mx.default_device()),
        "architecture": arch,
        "architecture_generation": architecture_generation(arch),
        "dyld_library_path_set": "DYLD_LIBRARY_PATH" in os.environ,
    }
    manifest = json.loads(raw)
    r1_exact = json.loads(args.r1_exact.read_bytes()) if args.r1_exact and args.r1_exact.is_file() else None
    r3_records = None
    if args.r3_report and args.r3_report.is_file():
        r3_records = {r["id"]: r for r in json.loads(args.r3_report.read_bytes())["cases"]}
    try:
        records = observe(mx, np, manifest, arch, r1_exact, r3_records, args.r3_dir)
    except Refusal as refusal:
        report["result"] = "REFUSED"
        report["detail"] = str(refusal)
        write(args.output, report)
        return 3
    report["records"] = records
    over = [cid for cid, r in records.items() if r.get("margin_vs_exact_r1", {}).get("elements_over_yardstick")]
    report["summary"] = {
        "records": len(records),
        "every_record_labelled": all(r["label"] == LABEL for r in records.values()),
        "different_kernel_family_records": sum(1 for r in records.values() if r["different_kernel_family"]),
        "compared_to_exact_r1": sum(1 for r in records.values() if "margin_vs_exact_r1" in r),
        "records_over_yardstick": over,
        "compared_to_r3": sum(1 for r in records.values() if "bit_identical_to_r3" in r),
        "bit_identical_to_r3_records": sum(1 for r in records.values() if r.get("bit_identical_to_r3", {}).get("all")),
    }
    report["result"] = "OBSERVED"
    write(args.output, report)
    print(json.dumps({"result": report["result"], "summary": report["summary"], "environment": report["environment"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

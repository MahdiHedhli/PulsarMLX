#!/usr/bin/env python3
"""Checkpoint-free decoder differential driver (glm52-weekend W3).

Generates synthetic random blocks for every quantization format the GLM-5.2
UD-IQ2_XXS checkpoint uses (validated through the corrected oracle's
independent scalar decoders: non-finite scales are rejected and regenerated),
writes them as a case file for the Rust producer
(`f017-native-decoder-differential`, which runs the secure loader's exact
decode dispatch), then compares the producer's f32 values with the oracle's
binary64 values: exact-after-rounding count, max ULP distance, max absolute
and relative error, and a permutation check. A harness negative control
permutes two lanes of one oracle block and must be flagged.

Usage: f017_decoder_differential_v1.py generate CASES_JSON [--seed N]
       f017_decoder_differential_v1.py compare CASES_JSON PRODUCED_JSON REPORT_JSON
"""
from __future__ import annotations

import json
import math
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f017_oracle_primary_decoders as oracle  # noqa: E402

TYPE_IDS = {"F32": 0, "Q8_0": 8, "Q2_K": 10, "Q3_K": 11, "Q4_K": 12, "Q5_K": 13, "Q6_K": 14, "IQ2_XXS": 16, "IQ3_XXS": 18, "IQ2_S": 22, "IQ4_XS": 23}
# checkpoint census (docs/research/glm52/raw/f016-c01-catalog-0001.json)
FORMATS = ["F32", "Q8_0", "Q5_K", "IQ2_XXS", "Q6_K", "IQ3_XXS", "IQ4_XS", "Q4_K", "IQ2_S", "Q2_K", "Q3_K"]


def valid_block(fmt: str, rng: random.Random) -> bytes:
    values, nbytes = oracle.LAYOUT[fmt]
    while True:
        if fmt == "F32":
            block = struct.pack("<f", rng.uniform(-4.0, 4.0))
        else:
            block = bytes(rng.getrandbits(8) for _ in range(nbytes))
        try:
            out = oracle._decode_block(fmt, block)
        except (ValueError, IndexError):
            continue
        if len(out) == values and all(math.isfinite(v) and abs(v) < 1e4 for v in out):
            return block


def generate(path: str, seed: int) -> None:
    rng = random.Random(seed)
    cases = []
    for fmt in FORMATS:
        values, nbytes = oracle.LAYOUT[fmt]
        for k, (rows, columns) in enumerate([(1, values * 2), (3, values * 4), (4, values * 8)]):
            blocks = b"".join(valid_block(fmt, rng) for _ in range(rows * columns // values))
            cases.append({"id": f"{fmt}-r{rows}-c{columns}-{k}", "format": fmt, "type_id": TYPE_IDS[fmt], "rows": rows, "columns": columns, "bytes_hex": blocks.hex()})
    json.dump({"schema": "pulsarmlx.f017.decoder-differential-cases/1.0.0", "seed": seed, "formats": FORMATS, "cases": cases}, open(path, "w"), indent=1)
    print(f"generated {len(cases)} cases for {len(FORMATS)} formats (seed {seed})")


def ulp_distance(a: float, b32: float) -> int:
    """ULP distance between the oracle value rounded to f32 and the produced f32."""
    ra = struct.unpack("<f", struct.pack("<f", a))[0]
    ia = struct.unpack("<i", struct.pack("<f", ra))[0]
    ib = struct.unpack("<i", struct.pack("<f", b32))[0]
    return abs(ia - ib)


def compare(cases_path: str, produced_path: str, report_path: str) -> int:
    cases = {c["id"]: c for c in json.load(open(cases_path))["cases"]}
    produced = {d["id"]: d for d in json.load(open(produced_path))["decoded"]}
    rows_out = []
    worst = {}
    for cid, c in cases.items():
        p = produced.get(cid)
        fmt = c["format"]; n = c["rows"] * c["columns"]
        ref = oracle.decode(fmt, bytes.fromhex(c["bytes_hex"]), n)
        row = {"id": cid, "format": fmt, "n": n}
        if p is None or p["result"] != "OK":
            row.update(status="PRODUCER_ERROR", error=(p or {}).get("error")); rows_out.append(row); continue
        got = list(struct.unpack(f"<{n}f", bytes.fromhex(p["values_f32le_hex"])))
        ulps = [ulp_distance(a, b) for a, b in zip(ref, got)]
        abs_err = [abs(a - b) for a, b in zip(ref, got)]
        rel = [abs(a - b) / abs(a) for a, b in zip(ref, got) if abs(a) > 1e-30]
        exact = sum(1 for u in ulps if u == 0)
        # permutation check: same multiset (rounded to f32) but different order -> lane permutation signature
        same_multiset = sorted(struct.unpack("<f", struct.pack("<f", a))[0] for a in ref) == sorted(got)
        row.update(status="MATCH" if max(ulps) <= 1 else "DIVERGENT", exact_f32=exact, max_ulp=max(ulps), max_abs=max(abs_err), max_rel=max(rel) if rel else 0.0, permutation_signature=(max(ulps) > 1 and same_multiset))
        rows_out.append(row)
        w = worst.setdefault(fmt, {"max_ulp": 0, "cases": 0, "divergent": 0, "exact_f32": 0, "n": 0})
        w["max_ulp"] = max(w["max_ulp"], row["max_ulp"]); w["cases"] += 1; w["divergent"] += row["status"] == "DIVERGENT"; w["exact_f32"] += exact; w["n"] += n
    # harness negative control: permute two lanes of the oracle output of one IQ3_XXS case; the comparison must flag it
    ctrl_id = next(i for i in cases if cases[i]["format"] == "IQ3_XXS")
    c = cases[ctrl_id]; n = c["rows"] * c["columns"]
    ref = oracle.decode("IQ3_XXS", bytes.fromhex(c["bytes_hex"]), n)
    got = list(struct.unpack(f"<{n}f", bytes.fromhex(produced[ctrl_id]["values_f32le_hex"])))
    perm = got[:]
    i, j = next(((a, b) for a in range(n) for b in range(a + 1, n) if perm[a] != perm[b]))
    perm[i], perm[j] = perm[j], perm[i]
    ctrl_flagged = max(ulp_distance(a, b) for a, b in zip(ref, perm)) > 1
    verdict = "PASS" if all(r["status"] == "MATCH" for r in rows_out) and ctrl_flagged else "FAIL"
    report = {"schema": "pulsarmlx.f017.decoder-differential-report/1.0.0", "oracle": "scripts/research/f017_oracle_primary_decoders.py (corrected oracle independent scalar decoders, binary64)", "producer": "f017-native decode_packed_matrix_for_qualification (secure loader dispatch)", "rule": "MATCH = every value within 1 ULP of the oracle value rounded to f32; DIVERGENT otherwise; permutation_signature = divergent with identical multiset", "per_format": worst, "cases": rows_out, "negative_control": {"case": ctrl_id, "mutation": f"oracle lanes {i} and {j} swapped in the comparison", "flagged": ctrl_flagged}, "verdict": verdict}
    json.dump(report, open(report_path, "w"), indent=1)
    print(json.dumps({"verdict": verdict, "per_format": worst, "negative_control_flagged": ctrl_flagged}, indent=1))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    if sys.argv[1] == "generate":
        seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 20260920
        generate(sys.argv[2], seed)
    elif sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3], sys.argv[4]))
    else:
        raise SystemExit(__doc__)

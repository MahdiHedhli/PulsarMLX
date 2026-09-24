"""Boundary controls for exact_gates_v1.py (stdlib only).

Synthetic records exercise each exact gate on both sides of its bound, so a
gate that silently passed everything (or failed everything) is caught
independently of the frozen population. Run from the crate's host tests.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exact_gates_v1 as g  # noqa: E402

U = Fraction(1, 1 << 24)


def f32_bits(value: Fraction) -> int:
    # exact for the dyadic values used here
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


class Records:
    def __init__(self, directory: Path):
        self.dir = directory

    def record(self, cid: str, dtype: str, bits: list) -> dict:
        fmt = "<%d%s" % (len(bits), "I" if dtype == "F32" else "H")
        data = struct.pack(fmt, *bits)
        (self.dir / "outputs").mkdir(exist_ok=True)
        rel = "outputs/%s.bin" % cid
        (self.dir / rel).write_bytes(data)
        return {"id": cid, "outcome": "executed",
                "output": {"file": rel, "sha256": hashlib.sha256(data).hexdigest(), "dtype": dtype}}


def qmm_case(n=21):
    return {"id": "q", "op": "quantized_matmul",
            "expected": {"families_0_31_2": [{"family": "qmv_quad", "gamma_n": n}]}}


class QmmExact(unittest.TestCase):
    def decide(self, y3: Fraction, y1=None):
        with tempfile.TemporaryDirectory() as d:
            rec = Records(Path(d)).record("q", "F32", [f32_bits(y3)])
            exact = {"k": 64, "y_exact": ["1/1"], "phi_exact": ["1/1"]}
            rust = None if y1 is None else {"y": [struct.pack(">d", y1).hex()]}
            return g.decide_qmm(qmm_case(), exact, rust, rec, Path(d))

    def test_inside_and_outside_gamma_n(self):
        # gamma_21 = 21u/(1-21u): a distance of 20u passes, 22u fails.
        self.assertTrue(self.decide(1 + 20 * U)["G-QMM-EXACT"]["pass"])
        self.assertFalse(self.decide(1 + 22 * U)["G-QMM-EXACT"]["pass"])

    def test_r1_self_check(self):
        # gamma64_65 * Phi: 64*2^-53 passes; 2^-40 fails.
        ok = self.decide(Fraction(1), y1=1 + 64 * 2.0 ** -53)
        self.assertTrue(ok["G-R1-SELF-QMM"]["pass"])
        bad = self.decide(Fraction(1), y1=1 + 2.0 ** -40)
        self.assertFalse(bad["G-R1-SELF-QMM"]["pass"])

    def test_nan_fails(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Records(Path(d)).record("q", "F32", [0x7FC00000])
            r = g.decide_qmm(qmm_case(), {"k": 64, "y_exact": ["1/1"], "phi_exact": ["1/1"]}, None, rec, Path(d))
            self.assertFalse(r["G-QMM-EXACT"]["pass"])

    def test_zero_phi_admits_only_zero(self):
        with tempfile.TemporaryDirectory() as d:
            recs = Records(Path(d))
            exact = {"k": 64, "y_exact": ["0/1"], "phi_exact": ["0/1"]}
            self.assertTrue(g.decide_qmm(qmm_case(), exact, None, recs.record("q1", "F32", [0x80000000]), Path(d))["G-QMM-EXACT"]["pass"])
            self.assertFalse(g.decide_qmm(qmm_case(), exact, None, recs.record("q2", "F32", [1]), Path(d))["G-QMM-EXACT"]["pass"])

    def test_tampered_output_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            rec = Records(Path(d)).record("q", "F32", [f32_bits(Fraction(1))])
            (Path(d) / rec["output"]["file"]).write_bytes(b"\0\0\0\0")
            with self.assertRaises(g.InputError):
                g.decide_qmm(qmm_case(), {"k": 64, "y_exact": ["1/1"], "phi_exact": ["1/1"]}, None, rec, Path(d))


class DqExact(unittest.TestCase):
    def test_f32_bound(self):
        # P = 3, b = 1/2, w = 7/2: bound = u(1+u)*3 + u*7/2 ~ 6.5u; one ulp at
        # 3.5 is 2^-22 = 4u (pass), two ulps 8u (fail).
        with tempfile.TemporaryDirectory() as d:
            recs = Records(Path(d))
            exact = {"metadata_dtype": "F32", "w_exact": ["7/2"], "p_exact": ["3/1"]}
            one = recs.record("d1", "F32", [f32_bits(Fraction(7, 2)) + 1])
            two = recs.record("d2", "F32", [f32_bits(Fraction(7, 2)) + 2])
            self.assertTrue(g.decide_dq({"id": "d"}, exact, None, one, Path(d))["G-DQ-EXACT"]["pass"])
            self.assertFalse(g.decide_dq({"id": "d"}, exact, None, two, Path(d))["G-DQ-EXACT"]["pass"])

    def test_r1_self_dq(self):
        with tempfile.TemporaryDirectory() as d:
            recs = Records(Path(d))
            exact = {"metadata_dtype": "F32", "w_exact": ["7/2"], "p_exact": ["3/1"]}
            rec = recs.record("d", "F32", [f32_bits(Fraction(7, 2))])
            ok = g.decide_dq({"id": "d"}, exact, {"w": [struct.pack(">d", 3.5).hex()]}, rec, Path(d))
            self.assertTrue(ok["G-R1-SELF-DQ"]["pass"])
            self.assertTrue(ok["H-DQ-SET"]["all_in_set"])
            bad = g.decide_dq({"id": "d"}, exact, {"w": [struct.pack(">d", 3.5 + 2.0 ** -40).hex()]}, rec, Path(d))
            self.assertFalse(bad["G-R1-SELF-DQ"]["pass"])

    def test_rounding_helper(self):
        self.assertEqual(g.rn(Fraction(65520), "F16"), "inf")
        self.assertEqual(g.rn(1 + Fraction(1, 2048), "F16"), 1)
        self.assertEqual(g.rn(1 + Fraction(3, 2048), "F16"), 1 + Fraction(1, 512))


if __name__ == "__main__":
    unittest.main()

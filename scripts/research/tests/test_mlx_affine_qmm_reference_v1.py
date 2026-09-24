"""The exact Slice 2B R1 computes exact rationals from the fixture bytes and decides its self-checks."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import struct
import tempfile
from fractions import Fraction
from pathlib import Path
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "mlx_affine_qmm_reference_v1.py"
FIXTURES = REPOSITORY_ROOT / "fixtures" / "native-primitives"
MANIFEST = FIXTURES / "manifest.json"
MANIFEST_SHA256 = "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04"


def _load():
    spec = importlib.util.spec_from_file_location("mlx_affine_qmm_reference_v1", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("the exact R1 could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r1 = _load()

F16_ONE, F16_TWO, F16_HALF, F16_MINUS_ONE, F16_NEG_ZERO = 0x3C00, 0x4000, 0x3800, 0xBC00, 0x8000
BF16_ONE, BF16_QUARTER, BF16_MINUS_TWO, BF16_MINUS_HALF = 0x3F80, 0x3E80, 0xC000, 0xBF00
F32_ONE, F32_MINUS_ONE, F32_HALF, F32_MINUS_HALF = 0x3F800000, 0xBF800000, 0x3F000000, 0xBF000000
F32_MINUS_QUARTER, F32_NEG_ZERO = 0xBE800000, 0x80000000
F32_2P32, F32_2PM32, F32_M2P32 = 0x4F800000, 0x2F800000, 0xCF800000


def pack_row(codes, bits):
    """Set code j at bits [j*bits, j*bits + bits), bit by bit (test-side packer)."""
    total = len(codes) * bits
    assert total % 32 == 0
    words = [0] * (total // 32)
    for j, code in enumerate(codes):
        for bit in range(bits):
            if (code >> bit) & 1:
                position = j * bits + bit
                words[position // 32] |= 1 << (position % 32)
    return words


class Synthetic:
    """A throwaway manifest + case directory holding hand-built cases."""

    def __init__(self, directory: Path):
        self.directory = directory
        (directory / "cases").mkdir()
        self.cases = []

    def add(self, cid, op, params, tensors, references=("rust_binary64_r1", "python_exact_r1")):
        blob = bytearray()
        specs = []
        for name, dtype, shape, values in tensors:
            code = {"U32": "I", "F32": "I", "F16": "H", "BF16": "H"}[dtype]
            raw = struct.pack("<%d%s" % (len(values), code), *values)
            specs.append({"name": name, "dtype": dtype, "shape": list(shape), "offset": len(blob),
                          "nbytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            blob += raw
        relative = "cases/%s.bin" % cid
        (self.directory / relative).write_bytes(bytes(blob))
        self.cases.append({"id": cid, "op": op, "params": params,
                           "expected": {"outcome": "accept"}, "references": list(references),
                           "file": relative, "file_sha256": hashlib.sha256(blob).hexdigest(),
                           "tensors": specs})
        return self.cases[-1]

    def qmm(self, cid, bits, group, dtype, x, x_shape, rows_codes, scales, biases):
        k = x_shape[-1]
        m_eff = 1
        for d in x_shape[:-1]:
            m_eff *= d
        words = [w for row in rows_codes for w in pack_row(row, bits)]
        n = len(rows_codes)
        return self.add(cid, "quantized_matmul",
                        {"bits": bits, "group_size": group, "metadata_dtype": dtype, "x_shape": list(x_shape),
                         "M_eff": m_eff, "K": k, "N": n, "transpose": True, "x_dtype": "F32"},
                        [("x", "F32", x_shape, x), ("w", "U32", (n, k * bits // 32), words),
                         ("scales", dtype, (n, k // group), scales), ("biases", dtype, (n, k // group), biases)])

    def dq(self, cid, bits, group, dtype, rows_codes, scales, biases):
        k = len(rows_codes[0])
        rows = len(rows_codes)
        words = [w for row in rows_codes for w in pack_row(row, bits)]
        return self.add(cid, "dequantize",
                        {"bits": bits, "group_size": group, "metadata_dtype": dtype, "rows": rows, "K": k},
                        [("w", "U32", (rows, k * bits // 32), words),
                         ("scales", dtype, (rows, k // group), scales), ("biases", dtype, (rows, k // group), biases)])


def fr(text):
    return r1.parse_rational(text)


class ExactValueTests(unittest.TestCase):
    def test_every_finite_half_and_brain_half_pattern_is_widened_exactly(self):
        for pattern in range(1 << 16):
            (half,) = struct.unpack("<e", struct.pack("<H", pattern))
            if half != half or half in (float("inf"), float("-inf")):
                with self.assertRaises(r1.InputError):
                    r1.scaled_integer("F16", pattern)
            else:
                self.assertEqual(r1.exact("F16", pattern), Fraction(half), hex(pattern))
            (brain,) = struct.unpack("<f", struct.pack("<I", pattern << 16))
            if brain != brain or brain in (float("inf"), float("-inf")):
                with self.assertRaises(r1.InputError):
                    r1.scaled_integer("BF16", pattern)
            else:
                self.assertEqual(r1.exact("BF16", pattern), Fraction(brain), hex(pattern))

    def test_binary32_extremes_are_exact(self):
        for pattern in (0x00000000, 0x80000000, 0x00000001, 0x807FFFFF, 0x00800000, 0x7F7FFFFF,
                        0xFF7FFFFF, 0x3F800001, F32_2P32, F32_2PM32, 0x12345678, 0xDEADBEEF):
            (single,) = struct.unpack("<f", struct.pack("<I", pattern))
            self.assertEqual(r1.exact("F32", pattern), Fraction(single), hex(pattern))
        self.assertEqual(r1.exact("F32", 0x00000001), Fraction(1, 1 << 149))
        for pattern in (0x7F800000, 0xFF800000, 0x7FC00000, 0x7F800001):
            with self.assertRaises(r1.InputError):
                r1.scaled_integer("F32", pattern)

    def test_dyadic_strings_are_in_lowest_terms(self):
        self.assertEqual(r1.dyadic_string(0, 40), "0/1")
        self.assertEqual(r1.dyadic_string(3, 2), "3/4")
        self.assertEqual(r1.dyadic_string(-12, 4), "-3/4")
        self.assertEqual(r1.dyadic_string(8, 1), "4/1")
        self.assertEqual(r1.dyadic_string(1 << 60, 60), "1/1")
        self.assertEqual(fr(r1.dyadic_string(-5 << 7, 30)), Fraction(-5, 1 << 23))

    def test_binary64_hex_is_exact_and_refuses_non_finite(self):
        self.assertEqual(r1.binary64_from_hex("3ff0000000000000"), 1)
        self.assertEqual(r1.binary64_from_hex("8000000000000000"), 0)
        self.assertEqual(r1.binary64_from_hex("0000000000000001"), Fraction(1, 1 << 1074))
        for text in ("7ff0000000000000", "fff8000000000000", "3ff"):
            with self.assertRaises(r1.InputError):
                r1.binary64_from_hex(text)


class CodeTests(unittest.TestCase):
    def test_four_and_eight_bit_literal_words(self):
        raw = struct.pack("<2I", 0x76543210, 0xFEDCBA98)
        self.assertEqual(r1.row_codes(raw, 4, 16), list(range(16)))
        raw = struct.pack("<I", 0x03020100)
        self.assertEqual(r1.row_codes(raw, 8, 4), [0, 1, 2, 3])

    def test_three_bit_codes_straddle_words(self):
        codes = [j % 8 for j in range(32)]
        raw = struct.pack("<3I", *pack_row(codes, 3))
        self.assertEqual(r1.row_codes(raw, 3, 32), codes)


class HandComputedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.box = Synthetic(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_case(self, case):
        return r1.exact_case(case, self.tmp)

    def test_four_bit_group_32_f16(self):
        codes = [j % 16 for j in range(32)]
        case = self.box.qmm("a", 4, 32, "F16", [F32_ONE] * 32, (1, 32), [codes], [F16_HALF], [F16_MINUS_ONE])
        out = self.run_case(case)
        self.assertEqual((out["y_exact"], out["phi_exact"]), (["88/1"], ["152/1"]))
        case = self.box.dq("a-dq", 4, 32, "F16", [codes], [F16_HALF], [F16_MINUS_ONE])
        out = self.run_case(case)
        self.assertEqual([fr(v) for v in out["w_exact"]], [Fraction(q, 2) - 1 for q in codes])
        self.assertEqual([fr(v) for v in out["p_exact"]], [Fraction(q, 2) for q in codes])

    def test_two_groups_select_by_column(self):
        case = self.box.qmm("g", 4, 32, "F16", [F32_ONE] * 64, (64,), [[1] * 64],
                            [F16_ONE, F16_TWO], [0, F16_ONE])
        out = self.run_case(case)
        self.assertEqual(out["m_eff"], 1)
        self.assertEqual((out["y_exact"], out["phi_exact"]), (["128/1"], ["128/1"]))

    def test_eight_bit_group_64_bf16_two_by_two(self):
        x = [F32_ONE] * 64 + [F32_MINUS_HALF] * 64
        case = self.box.qmm("b", 8, 64, "BF16", x, (2, 64), [[255] * 64, list(range(64))],
                            [BF16_QUARTER, BF16_MINUS_HALF], [BF16_MINUS_TWO, BF16_ONE])
        out = self.run_case(case)
        self.assertEqual([fr(v) for v in out["y_exact"]], [3952, -944, -1976, 472])
        self.assertEqual([fr(v) for v in out["phi_exact"]], [4208, 1072, 2104, 536])

    def test_rank3_x_flattens_leading_dimensions(self):
        x = [F32_ONE] * 64 + [F32_MINUS_HALF] * 64
        case = self.box.qmm("r3", 8, 64, "BF16", x, (1, 2, 64), [[255] * 64],
                            [BF16_QUARTER], [BF16_MINUS_TWO])
        out = self.run_case(case)
        self.assertEqual((out["m_eff"], out["n"]), (2, 1))
        self.assertEqual([fr(v) for v in out["y_exact"]], [3952, -1976])

    def test_group_128_f32_cancels_to_exact_zero(self):
        x = [F32_ONE if t % 2 == 0 else F32_MINUS_ONE for t in range(128)]
        case = self.box.qmm("c", 4, 128, "F32", x, (1, 128), [[15] * 128], [F32_HALF], [F32_MINUS_QUARTER])
        out = self.run_case(case)
        self.assertEqual((out["y_exact"], out["phi_exact"]), (["0/1"], ["992/1"]))

    def test_exact_sum_keeps_what_sequential_binary64_loses(self):
        x = [F32_2P32, F32_2PM32, F32_M2P32] + [0] * 29
        case = self.box.qmm("o", 4, 32, "F32", x, (1, 32), [[1, 1, 1] + [0] * 29], [F32_ONE], [0])
        out = self.run_case(case)
        self.assertEqual(out["y_exact"], ["1/%d" % (1 << 32)])
        self.assertEqual(fr(out["phi_exact"][0]), Fraction(1 << 33) + Fraction(1, 1 << 32))

    def test_signed_zeros(self):
        case = self.box.qmm("z", 4, 32, "F16", [F32_ONE] * 32, (1, 32), [[1] * 32], [F16_NEG_ZERO], [F16_NEG_ZERO])
        out = self.run_case(case)
        self.assertEqual((out["y_exact"], out["phi_exact"]), (["0/1"], ["0/1"]))
        x = [0 if t % 2 == 0 else F32_NEG_ZERO for t in range(32)]
        case = self.box.qmm("z2", 4, 32, "F16", x, (1, 32), [[1] * 32], [F16_HALF], [F16_MINUS_ONE])
        out = self.run_case(case)
        self.assertEqual((out["y_exact"], out["phi_exact"]), (["0/1"], ["0/1"]))

    def test_dequantize_f32_exact_sum_is_not_rounded(self):
        case = self.box.dq("d", 8, 32, "F32", [[255] * 32], [0x3F800001], [0x53800000])
        out = self.run_case(case)
        p = 255 + Fraction(255, 1 << 23)
        self.assertTrue(all(fr(v) == p for v in out["p_exact"]))
        self.assertTrue(all(fr(v) == (1 << 40) + p for v in out["w_exact"]))

    def test_inconsistent_inputs_are_refused(self):
        case = self.box.qmm("bad", 4, 32, "F16", [F32_ONE] * 32, (1, 32), [[1] * 32], [F16_ONE], [0])
        tampered = dict(case, params=dict(case["params"], K=64))
        with self.assertRaises(r1.InputError):
            self.run_case(tampered)
        tampered = dict(case, file_sha256="0" * 64)
        with self.assertRaises(r1.InputError):
            self.run_case(tampered)
        nan = self.box.qmm("nan", 4, 32, "F16", [0x7FC00000] + [F32_ONE] * 31, (1, 32), [[1] * 32], [F16_ONE], [0])
        with self.assertRaises(r1.InputError):
            self.run_case(nan)
        refusal = dict(case, expected={"outcome": "refuse"})
        with self.assertRaises(r1.InputError):
            self.run_case(refusal)


class SelfCheckTests(unittest.TestCase):
    """The self-check decides exactly and fails closed; values are synthetic."""

    def setUp(self):
        self.manifest = {"cases": [
            {"id": "q", "op": "quantized_matmul", "references": ["rust_binary64_r1", "python_exact_r1"]},
            {"id": "d", "op": "dequantize", "references": ["rust_binary64_r1", "python_exact_r1"]},
            {"id": "rust-only", "op": "quantized_matmul", "references": ["rust_binary64_r1"]},
        ]}
        self.results = {
            # y* = 2^-32 and Phi = 2^33 + 2^-32: the Rust hand case sequential_order_is_k_ascending.
            "q": {"op": "quantized_matmul", "k": 32, "y_exact": ["1/4294967296"],
                  "phi_exact": ["%d/%d" % ((1 << 65) + 1, 1 << 32)]},
            "d": {"op": "dequantize", "w_exact": ["3/1"], "p_exact": ["2/1"]},
        }

    @staticmethod
    def h(value):
        return "%016x" % struct.unpack("<Q", struct.pack("<d", value))[0]

    def rust(self, y, phi, w, p):
        return {"schema": r1.RUST_SCHEMA, "cases": {
            "q": {"op": "quantized_matmul", "y": [self.h(y)], "phi": [self.h(phi)]},
            "d": {"op": "dequantize", "w": [self.h(w)], "p": [self.h(p)]}}}

    def test_the_sequential_binary64_result_passes(self):
        # y1 = 0 against y* = 2^-32 with Phi ~ 2^33 (the Rust hand case) is inside gamma64_{33}*Phi.
        report = r1.self_check(self.manifest, self.results, self.rust(0.0, 2.0 ** 33, 3.0, 2.0))
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["N-R1-SELF"]["passed_cases"], 1)
        self.assertEqual(report["N-R1-SELF-DQ"]["passed_cases"], 1)
        self.assertEqual(report["dual_reference_cases"], 2)

    def test_an_error_beyond_gamma64_fails(self):
        # (K+1) * 2^-53 * Phi ~ 33 * 2^-20; an error of 2^-10 is far outside.
        report = r1.self_check(self.manifest, self.results, self.rust(2.0 ** -10, 2.0 ** 33, 3.0, 2.0))
        self.assertEqual(report["result"], "FAIL")
        self.assertEqual(report["N-R1-SELF"]["failed_cases"], ["q"])

    def test_a_dequantize_error_beyond_one_rounding_fails(self):
        report = r1.self_check(self.manifest, self.results, self.rust(0.0, 2.0 ** 33, 3.0 + 2.0 ** -50, 2.0))
        self.assertEqual(report["result"], "FAIL")
        self.assertEqual(report["N-R1-SELF-DQ"]["failed_cases"], ["d"])
        report = r1.self_check(self.manifest, self.results, self.rust(0.0, 2.0 ** 33, 3.0, 2.0 + 2.0 ** -51))
        self.assertEqual(report["p_hat_exact"]["failed_cases"], ["d"])
        self.assertEqual(report["result"], "FAIL")

    def test_a_missing_case_fails(self):
        rust = self.rust(0.0, 2.0 ** 33, 3.0, 2.0)
        del rust["cases"]["d"]
        report = r1.self_check(self.manifest, self.results, rust)
        self.assertEqual(report["missing_cases"], ["d"])
        self.assertEqual(report["result"], "FAIL")

    def test_a_foreign_document_is_refused(self):
        with self.assertRaises(r1.InputError):
            r1.self_check(self.manifest, self.results, {"schema": "other", "cases": {}})


class FrozenPopulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_manifest_is_the_frozen_one_and_all_selects_the_296_exact_cases(self):
        manifest, digest = r1.load_manifest(MANIFEST)
        self.assertEqual(digest, MANIFEST_SHA256)
        chosen = r1.select(manifest, True, [])
        ops = [c["op"] for c in chosen]
        self.assertEqual((len(chosen), ops.count("quantized_matmul"), ops.count("dequantize")), (296, 237, 59))

    def test_one_frozen_case_matches_an_independent_fraction_computation(self):
        # Recompute y* and Phi for one case straight from the bytes with struct's own
        # half/single conversions and Fraction, a different path from the script's.
        manifest, _ = r1.load_manifest(MANIFEST)
        case = {c["id"]: c for c in manifest["cases"]}["qmm-b4-g32-f16-quad64"]
        out = r1.exact_case(case, FIXTURES)
        blob = (FIXTURES / case["file"]).read_bytes()
        spec = {t["name"]: t for t in case["tensors"]}

        def values(name, code):
            t = spec[name]
            count = t["nbytes"] // struct.calcsize("<" + code)
            return struct.unpack("<%d%s" % (count, code), blob[t["offset"]:t["offset"] + t["nbytes"]])

        x = [Fraction(v) for v in values("x", "f")]
        s = [Fraction(v) for v in values("scales", "e")]
        b = [Fraction(v) for v in values("biases", "e")]
        words = values("w", "I")
        k, n, group = 64, 64, 32
        for j in range(n):
            codes = [(words[j * 8 + t // 8] >> (4 * (t % 8))) & 15 for t in range(k)]
            g = [j * 2 + t // group for t in range(k)]
            y = sum((s[g[t]] * codes[t] + b[g[t]]) * x[t] for t in range(k))
            phi = sum((abs(s[g[t]]) * codes[t] + abs(b[g[t]])) * abs(x[t]) for t in range(k))
            self.assertEqual(fr(out["y_exact"][j]), y)
            self.assertEqual(fr(out["phi_exact"][j]), phi)

    def test_cli_is_deterministic_and_emits_power_of_two_denominators(self):
        outputs = []
        for name in ("one.json", "two.json"):
            path = self.tmp / name
            status = r1.run(["--manifest", str(MANIFEST), "--cases-dir", str(FIXTURES),
                             "--case", "qmm-b8-g64-bf16-rank1", "--case", "dq-b4-g32-f16-r1-k32",
                             "--out", str(path)])
            self.assertEqual(status, 0)
            outputs.append(path.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        document = json.loads(outputs[0])
        self.assertEqual(document["manifest_sha256"], MANIFEST_SHA256)
        self.assertEqual(document["case_count"], 2)
        qmm = document["cases"]["qmm-b8-g64-bf16-rank1"]
        self.assertEqual((qmm["m_eff"], qmm["n"], qmm["k"], len(qmm["y_exact"])), (1, 64, 256, 64))
        dq = document["cases"]["dq-b4-g32-f16-r1-k32"]
        self.assertEqual((dq["rows"], dq["k"], len(dq["w_exact"])), (1, 32, 32))
        for text in qmm["y_exact"] + qmm["phi_exact"] + dq["w_exact"] + dq["p_exact"]:
            numerator, denominator = (int(part) for part in text.split("/"))
            self.assertTrue(denominator > 0 and denominator & (denominator - 1) == 0, text)
            self.assertEqual(Fraction(numerator, denominator).denominator, denominator, text)
        self.assertTrue(all(fr(v) >= 0 for v in qmm["phi_exact"]))

    def test_cli_refuses_refusal_probes_unknown_ids_and_tampered_bytes(self):
        out = self.tmp / "out.json"
        base = ["--manifest", str(MANIFEST), "--out", str(out)]
        self.assertEqual(r1.run(base + ["--cases-dir", str(FIXTURES), "--case", "ref-rowsum-2p41"]), 2)
        self.assertEqual(r1.run(base + ["--cases-dir", str(FIXTURES), "--case", "no-such-case"]), 2)
        copy = self.tmp / "copy"
        (copy / "cases").mkdir(parents=True)
        source = FIXTURES / "cases" / "dq-b4-g32-f16-r1-k32.bin"
        data = bytearray(source.read_bytes())
        data[-1] ^= 1
        (copy / "cases" / source.name).write_bytes(bytes(data))
        self.assertEqual(r1.run(base + ["--cases-dir", str(copy), "--case", "dq-b4-g32-f16-r1-k32"]), 2)
        self.assertFalse(out.exists())


class PurityTests(unittest.TestCase):
    def test_the_script_imports_only_the_standard_library_modules_it_names(self):
        tree = ast.parse(MODULE_PATH.read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module)
        self.assertEqual(names, {"__future__", "argparse", "hashlib", "json", "operator", "struct",
                                 "sys", "fractions", "pathlib"})


if __name__ == "__main__":
    unittest.main()

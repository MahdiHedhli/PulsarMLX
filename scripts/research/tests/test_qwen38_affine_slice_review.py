"""Generated-only tests for the proposed real-row review candidate."""

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qwen38_affine_slice_review as candidate
from qwen38_affine_slice_review import (CASES, MAX_SELECTED_BYTES, MAX_VALUES_PER_CASE,
                                        bf16_values, compare_values, read_selected,
                                        scalar_dequantize, selected_spans)
from qwen38_page_catalog import TensorRef
from qwen38_verified_files import VerificationError, VerifiedFiles


def bf16(*values):
    return b"".join(struct.pack("<H", struct.unpack("<I", struct.pack("<f", v))[0] >> 16)
                    for v in values)


def generated_row(bits):
    width = 32 // bits
    words = [sum(((i * 3 + lane) % (1 << bits)) << (bits * lane)
                 for lane in range(width)) for i in range(MAX_VALUES_PER_CASE // width)]
    weight = b"".join(struct.pack("<I", value) for value in words)
    scales = bf16(*([0.5] * 40))
    biases = bf16(*([-1.0] * 40))
    return weight, scales, biases


def synthetic_refs():
    refs = {}
    for case in CASES:
        for suffix, dtype, shape in (("weight", "U32", case.weight_shape),
                                     ("scales", "BF16", case.affine_shape),
                                     ("biases", "BF16", case.affine_shape)):
            size = (4 if dtype == "U32" else 2)
            count = 1
            for dim in shape:
                count *= dim
            refs[f"{case.prefix}.{suffix}"] = TensorRef(
                case.filename, 8, dtype, shape, 0, count * size)
    return refs


class AffineSliceReviewTests(unittest.TestCase):
    def test_exact_pinned_span_geometry_and_bounds(self):
        spans = selected_spans(synthetic_refs())
        self.assertEqual(sum(length for triple in spans for _, _, length in triple),
                         MAX_SELECTED_BYTES)
        self.assertEqual(tuple(length for _, _, length in spans[0]), (1280, 80, 80))
        self.assertEqual(tuple(length for _, _, length in spans[1]), (2560, 80, 80))
        self.assertEqual(spans[0][0][0], "model-00006.safetensors")
        self.assertEqual(spans[1][0][0], "model-00001.safetensors")

    def test_changed_header_shape_or_filename_fails_closed(self):
        refs = synthetic_refs()
        name = CASES[0].prefix + ".weight"
        old = refs[name]
        refs[name] = TensorRef(old.filename, old.data_start, old.dtype,
                               (512, 640, 321), old.start, old.end)
        with self.assertRaises(ValueError):
            selected_spans(refs)
        refs[name] = TensorRef("wrong.safetensors", old.data_start, old.dtype,
                               old.shape, old.start, old.end)
        with self.assertRaises(ValueError):
            selected_spans(refs)

    def test_generated_four_and_eight_bit_known_boundaries(self):
        for bits in (4, 8):
            with self.subTest(bits=bits):
                weight, scales, biases = generated_row(bits)
                result = scalar_dequantize(weight, scales, biases,
                                           bits=bits, group_size=64)
                self.assertEqual(len(result), MAX_VALUES_PER_CASE)
                code = lambda index: ((index // (32 // bits)) * 3 +
                                      index % (32 // bits)) % (1 << bits)
                self.assertEqual(result[0], -1.0)
                self.assertEqual(result[1], 0.5 - 1.0)
                self.assertEqual(result[63], 0.5 * code(63) - 1.0)
                self.assertEqual(result[64], 0.5 * code(64) - 1.0)
                self.assertEqual(result[-1], 0.5 * code(MAX_VALUES_PER_CASE - 1) - 1.0)
                self.assertTrue(compare_values(result, result)["all_within_tolerance"])

    def test_nonfinite_and_tolerance_failure(self):
        weight, scales, biases = generated_row(4)
        with self.assertRaises(ValueError):
            scalar_dequantize(weight, bf16(*([float("nan")] * 40)), biases,
                              bits=4, group_size=64)
        expected = scalar_dequantize(weight, scales, biases, bits=4, group_size=64)
        changed = list(expected)
        changed[64] += 0.01
        with self.assertRaises(AssertionError):
            compare_values(tuple(changed), expected)

    def test_generated_verified_read_rejects_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "fixture.bin"
            payload = bytes(i % 251 for i in range(MAX_SELECTED_BYTES))
            path.write_bytes(payload)
            entry = {"path": path.name, "size_bytes": len(payload),
                     "sha256": hashlib.sha256(payload).hexdigest()}
            with VerifiedFiles(root, [entry]) as files:
                spans = (((path.name, 0, 1280), (path.name, 1280, 80),
                          (path.name, 1360, 80)),
                         ((path.name, 1440, 2560), (path.name, 4000, 80),
                          (path.name, 4080, 80)))
                self.assertEqual(b"".join(part for triple in read_selected(files, spans)
                                          for part in triple), payload)
                path.write_bytes(b"X" * len(payload))
                with self.assertRaises(VerificationError):
                    read_selected(files, spans)

    def test_bf16_rejects_misaligned_bytes(self):
        with self.assertRaises(ValueError):
            bf16_values(b"\0")

    def test_peak_rss_stop(self):
        with mock.patch.object(candidate, "peak_rss_bytes",
                               return_value=candidate.MAX_RSS_BYTES + 1):
            with self.assertRaises(RuntimeError):
                candidate.check_rss()


if __name__ == "__main__":
    unittest.main()

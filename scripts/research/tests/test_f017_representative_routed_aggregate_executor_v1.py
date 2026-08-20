from __future__ import annotations

import copy
import hashlib
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.research.f017_representative_routed_aggregate_executor_v1 import (
    AggregateError, IDS, OUTPUT_SHAS, WEIGHTS, OpenOnceInputs, aggregate_bytes, begin_attempt,
    write_terminal, validate_records,
)


def raw_for(ordinal: int) -> bytes:
    return struct.pack("<6144f", *[((ordinal + 1) * ((k % 257) - 128) + ((k * 17 + ordinal) % 31) - 15) / 2048.0 for k in range(6144)])


def records(root: Path) -> list[dict]:
    result = []
    for ordinal, (expert_id, weight) in enumerate(zip(IDS, WEIGHTS, strict=True)):
        name = f"{ordinal:02d}-expert-{expert_id}-down.f32le"
        raw = raw_for(ordinal)
        path = root / name
        path.write_bytes(raw)
        os.chmod(path, 0o400)
        result.append({"ordinal": ordinal, "expert_id": expert_id, "routing_weight": weight,
                       "private_relative_path": name, "output_sha256": hashlib.sha256(raw).hexdigest(),
                       "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576})
    return result


class ArithmeticTests(unittest.TestCase):
    def test_real_geometry_deterministic_and_f64(self) -> None:
        inputs = tuple(raw_for(i) for i in range(8))
        first = aggregate_bytes(inputs)
        second = aggregate_bytes(inputs)
        self.assertEqual(len(first), 49152)
        self.assertEqual(first, second)
        self.assertTrue(all(math.isfinite(x) for x in struct.unpack("<6144d", first)))

    def test_serial_f32_substitution_differs(self) -> None:
        inputs = tuple(raw_for(i) for i in range(8))
        canonical = struct.unpack("<6144d", aggregate_bytes(inputs))
        different = 0
        for k in range(6144):
            acc = 0.0
            for i in range(8):
                value = struct.unpack_from("<f", inputs[i], 4 * k)[0]
                product_f32 = struct.unpack("<f", struct.pack("<f", WEIGHTS[i] * value))[0]
                acc = struct.unpack("<f", struct.pack("<f", acc + product_f32))[0]
            different += canonical[k] != float(acc)
        self.assertGreater(different, 0)

    def test_order_changes_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = records(Path(directory))
            swapped = copy.deepcopy(base)
            swapped[3], swapped[4] = swapped[4], swapped[3]
            with self.assertRaises(AggregateError):
                validate_records(swapped, synthetic=True)

    def test_weight_reassignment_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = records(Path(directory))
            base[0]["routing_weight"] = base[1]["routing_weight"]
            with self.assertRaises(AggregateError):
                validate_records(base, synthetic=True)

    def test_historical_output_substitution_rejected_in_real_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = records(Path(directory))
            with self.assertRaises(AggregateError):
                validate_records(base, synthetic=False)

    def test_protected_real_output_identity_rejected_in_synthetic_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = records(Path(directory))
            base[0]["output_sha256"] = OUTPUT_SHAS[0]
            with self.assertRaises(AggregateError):
                validate_records(base, synthetic=True)


class RetainedInputTests(unittest.TestCase):
    def test_open_once_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = records(root)
            with OpenOnceInputs(root, base, manifest_sha=None) as inputs:
                self.assertEqual(tuple(hashlib.sha256(x).hexdigest() for x in inputs.raw_inputs),
                                 tuple(x["output_sha256"] for x in base))
                self.assertEqual(inputs.verify_after(), [x["output_sha256"] for x in base])

    def test_writable_alias_and_hash_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = records(root)
            path = root / base[0]["private_relative_path"]
            os.chmod(path, 0o600)
            with self.assertRaises(AggregateError):
                OpenOnceInputs(root, base, manifest_sha=None)
            os.chmod(path, 0o400)
            base[0]["output_sha256"] = "0" * 64
            with self.assertRaises(AggregateError):
                OpenOnceInputs(root, base, manifest_sha=None)

    def test_wrong_size_and_nonfinite_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = records(root)
            path = root / base[0]["private_relative_path"]
            os.chmod(path, 0o600)
            path.write_bytes(b"x")
            os.chmod(path, 0o400)
            with self.assertRaises(AggregateError):
                OpenOnceInputs(root, base, manifest_sha=None)
        inputs = list(raw_for(i) for i in range(8))
        inputs[0] = struct.pack("<f", float("nan")) + inputs[0][4:]
        with self.assertRaises(AggregateError):
            aggregate_bytes(tuple(inputs))

    def test_durable_attempt_start_is_exclusive_and_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authorization = root / "authorization.json"
            release = root / "release.json"
            authorization.write_text("{}\n")
            release.write_text("{}\n")
            state = root / "state"
            identity = begin_attempt(state, authorization, release)
            self.assertEqual(len(identity), 64)
            self.assertTrue((state / "attempt-start.json").is_file())
            with self.assertRaises(AggregateError):
                begin_attempt(state, authorization, release)
            write_terminal(state, "TERMINAL_FAILURE", output_sha256=None, error="TEST")
            terminal = (state / "terminal.json").read_text()
            self.assertIn('"retry":false', terminal)
            self.assertIn('"resume":false', terminal)
            with self.assertRaises(AggregateError):
                write_terminal(state, "COMPLETE", output_sha256="0" * 64, error=None)


if __name__ == "__main__":
    unittest.main()

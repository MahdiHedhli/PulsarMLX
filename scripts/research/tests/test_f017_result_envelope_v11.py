from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_binary_comparator_v11 import compare_logits
from f017_result_artifacts_v11 import (build_manifest, build_receipt, build_terminal,
    closure_root, require_primary_terminal, validate_manifest)
from f017_result_envelope_v11 import (HIDDEN_SIZE, VOCAB_SIZE, PAYLOAD_SPECS,
    ResultEnvelopeError, bank_payload, iter_payload, payload_spec, validate_payload)


class ResultEnvelopeV11Tests(unittest.TestCase):
    def test_geometry_is_derived(self) -> None:
        expected = {
            ("PRIMARY", "final_hidden"): 49_152,
            ("PRIMARY", "final_normalized"): 49_152,
            ("PRIMARY", "full_logits"): 1_239_040,
            ("SECONDARY", "final_hidden"): 24_576,
            ("SECONDARY", "final_normalized"): 24_576,
            ("SECONDARY", "full_logits"): 619_520,
        }
        self.assertEqual({key: spec.byte_count for key, spec in PAYLOAD_SPECS.items()}, expected)
        self.assertEqual(payload_spec("PRIMARY", "full_logits").element_count, VOCAB_SIZE)

    def test_chunking_is_byte_identical_and_signed_zero_preserved(self) -> None:
        values = [0.0, -0.0] + [float(index) / 17 for index in range(HIDDEN_SIZE - 2)]
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = bank_payload(Path(first), "hidden.bin", payload_spec("PRIMARY", "final_hidden"), values, chunk_elements=1)
            two = bank_payload(Path(second), "hidden.bin", payload_spec("PRIMARY", "final_hidden"), values, chunk_elements=997)
            self.assertEqual(one["sha256"], two["sha256"])
            self.assertEqual((Path(first) / "hidden.bin").read_bytes()[:16], struct.pack("<dd", 0.0, -0.0))
            self.assertEqual(validate_payload(Path(first), one)["result"], "PASS")

    def test_nonfinite_values_reject(self) -> None:
        spec = payload_spec("PRIMARY", "final_hidden")
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                values = [0.0] * HIDDEN_SIZE; values[12] = value
                with self.assertRaises(ResultEnvelopeError):
                    bank_payload(Path(directory), "payload.bin", spec, values)

    def test_short_extra_sha_and_record_mutations_reject(self) -> None:
        spec = payload_spec("SECONDARY", "final_hidden")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = bank_payload(root, "payload.bin", spec, [0.25] * HIDDEN_SIZE)
            original = (root / "payload.bin").read_bytes()
            for mutant in (original[:-1], original + b"\0"):
                (root / "payload.bin").write_bytes(mutant)
                with self.assertRaises(ResultEnvelopeError): validate_payload(root, record)
                (root / "payload.bin").write_bytes(original)
            changed = dict(record); changed["dtype"] = "f64le"
            with self.assertRaises(ResultEnvelopeError): validate_payload(root, changed, expected_spec=spec)
            changed = dict(record); changed["sha256"] = "0" * 64
            with self.assertRaises(ResultEnvelopeError): validate_payload(root, changed)

    def test_manifest_receipt_terminal_and_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); records = []
            for kind in ("final_hidden", "final_normalized", "full_logits"):
                spec = payload_spec("PRIMARY", kind)
                records.append(bank_payload(root, f"{kind}.bin", spec, (0.0 for _ in range(spec.element_count))))
            manifest = build_manifest("PRIMARY", "PKG", "PRIMARY-EVENT", records)
            self.assertEqual(validate_manifest(root, manifest)["result"], "PASS")
            digest = hashlib.sha256(b"x").hexdigest()
            receipt = build_receipt("PRIMARY", "AUTH", "PKG", "PRIMARY-EVENT", digest, digest,
                                    hashlib.sha256(__import__('json').dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n").hexdigest(),
                                    digest, digest, digest)
            terminal = build_terminal("PRIMARY", hashlib.sha256(__import__('json').dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n").hexdigest(),
                                      receipt["payload_manifest_sha256"])
            require_primary_terminal(terminal, terminal["result_receipt_sha256"], terminal["payload_manifest_sha256"])
            for key in ("payload_manifest_sha256", "result_receipt_sha256"):
                changed = dict(terminal); changed[key] = "0" * 64
                with self.assertRaises(ResultEnvelopeError):
                    require_primary_terminal(changed, terminal["result_receipt_sha256"], terminal["payload_manifest_sha256"])

    def test_streaming_full_vocabulary_comparison(self) -> None:
        primary_values = (float(index % 257) / 1000 for index in range(VOCAB_SIZE))
        secondary_values = (float(index % 257) / 1000 for index in range(VOCAB_SIZE))
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            p = bank_payload(Path(left), "logits.bin", payload_spec("PRIMARY", "full_logits"), primary_values)
            s = bank_payload(Path(right), "logits.bin", payload_spec("SECONDARY", "full_logits"), secondary_values)
            result = compare_logits(Path(left), p, Path(right), s, chunk_elements=977)
            self.assertEqual(result["element_count"], VOCAB_SIZE)
            self.assertLess(result["max_absolute_error"], 1.5e-8)
            self.assertTrue(result["top1_stable"])

    def test_primary_terminal_required_before_secondary(self) -> None:
        with self.assertRaises(ResultEnvelopeError):
            require_primary_terminal({"result": "COMPLETE"}, "0" * 64)


if __name__ == "__main__":
    unittest.main()

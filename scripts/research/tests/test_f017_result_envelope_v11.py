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

from f017_binary_comparator_v11 import compare_logits, validate_comparison_summary
from f017_result_artifacts_v11 import (build_consumer_terminal, build_manifest, build_receipt,
    build_result_terminal, build_top32, closure_root, require_primary_terminal,
    validate_manifest, validate_top32)
from f017_event04_diagnostic_converter_v11 import convert
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
            receipt_sha = hashlib.sha256(__import__('json').dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n").hexdigest()
            result_terminal = build_result_terminal("PRIMARY", receipt_sha, receipt["payload_manifest_sha256"])
            result_terminal_sha = hashlib.sha256(__import__('json').dumps(result_terminal, sort_keys=True, separators=(",", ":")).encode() + b"\n").hexdigest()
            terminal = build_consumer_terminal("PRIMARY", result_terminal_sha, receipt_sha, receipt["payload_manifest_sha256"])
            require_primary_terminal(terminal, result_terminal_sha, receipt_sha, receipt["payload_manifest_sha256"])
            for key in ("payload_manifest_sha256", "result_receipt_sha256", "result_terminal_sha256"):
                changed = dict(terminal); changed[key] = "0" * 64
                with self.assertRaises(ResultEnvelopeError):
                    require_primary_terminal(changed, result_terminal_sha, receipt_sha, receipt["payload_manifest_sha256"])

    def test_streaming_full_vocabulary_comparison(self) -> None:
        primary_values = (float(index % 257) / 1000 for index in range(VOCAB_SIZE))
        secondary_values = (float(index % 257) / 1000 for index in range(VOCAB_SIZE))
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            p = bank_payload(Path(left), "logits.bin", payload_spec("PRIMARY", "full_logits"), primary_values)
            s = bank_payload(Path(right), "logits.bin", payload_spec("SECONDARY", "full_logits"), secondary_values)
            result = compare_logits(Path(left), p, Path(right), s, route_structure_equal=True, chunk_elements=977)
            self.assertEqual(result["element_count"], VOCAB_SIZE)
            self.assertLess(result["max_absolute_error"], 1.5e-8)
            self.assertTrue(result["top1_stable"])

    def test_primary_terminal_required_before_secondary(self) -> None:
        with self.assertRaises(ResultEnvelopeError):
            require_primary_terminal({"result": "COMPLETE"}, "0" * 64, "0" * 64, "0" * 64)

    def test_stream_hash_is_revalidated(self) -> None:
        spec = payload_spec("PRIMARY", "final_hidden")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = bank_payload(root, "payload.bin", spec, [1.0] * HIDDEN_SIZE)
            raw = bytearray((root / "payload.bin").read_bytes()); raw[0] ^= 1
            (root / "payload.bin").write_bytes(raw)
            with self.assertRaises(ResultEnvelopeError):
                list(iter_payload(root, record))

    def test_top32_is_derived_from_payload(self) -> None:
        values = [float(index) for index in range(VOCAB_SIZE)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = bank_payload(root, "logits.bin", payload_spec("PRIMARY", "full_logits"), values)
            summary = build_top32(root, record, "EVENT")
            self.assertEqual(summary["selected_token"], VOCAB_SIZE - 1)
            self.assertEqual(validate_top32(root, record, summary)["result"], "PASS")
            mutant = dict(summary); mutant["selected_token"] = 0
            with self.assertRaises(ResultEnvelopeError): validate_top32(root, record, mutant)

    def test_comparison_frozen_classification_branches(self) -> None:
        cases = [
            (True, 1.0, "EXACT_EXPECTED_TOKEN_STABLE"),
            (True, 0.005, "NUMERICALLY_STABLE_TOP_K_ONLY"),
            (False, 1.0, "ORACLE_DISAGREEMENT"),
        ]
        for routes, margin, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
                values = [0.0] * VOCAB_SIZE; values[10] = 1.0; values[11] = 1.0 - margin
                p = bank_payload(Path(left), "logits.bin", payload_spec("PRIMARY", "full_logits"), values)
                s = bank_payload(Path(right), "logits.bin", payload_spec("SECONDARY", "full_logits"), values)
                result = compare_logits(Path(left), p, Path(right), s, route_structure_equal=routes)
                self.assertEqual(result["classification"], expected)
                self.assertEqual(result["primary_logits_payload_sha256"], p["sha256"])
                self.assertEqual(validate_comparison_summary(result, p, s)["result"], "PASS")

        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            primary = [1.0] * VOCAB_SIZE; secondary = [1.0] * VOCAB_SIZE
            primary[10] = 1.004; primary[11] = 1.003
            secondary[10] = 1.003; secondary[11] = 1.004
            p = bank_payload(Path(left), "logits.bin", payload_spec("PRIMARY", "full_logits"), primary)
            s = bank_payload(Path(right), "logits.bin", payload_spec("SECONDARY", "full_logits"), secondary)
            result = compare_logits(Path(left), p, Path(right), s, route_structure_equal=True)
            self.assertEqual(result["classification"], "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY")
            mutant = dict(result); mutant["primary_logits_payload_sha256"] = "0" * 64
            with self.assertRaises(ResultEnvelopeError): validate_comparison_summary(mutant, p, s)

    def test_event04_diagnostic_record_cannot_enter_manifest(self) -> None:
        raw = ROOT / "docs/architecture/reviews/evidence/f017-event04-v10-terminal-package-v1/package-evidence/primary-consumer-output.json"
        grant = __import__('json').loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event04-result-envelope-diagnostic-reuse-grant-v11.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            converted = convert(raw, Path(directory), grant)
            self.assertEqual(converted["event04_promotion"], "PROHIBITED")
            self.assertEqual(converted["payload"]["role"], "DIAGNOSTIC_EVENT04")
            with self.assertRaises(ResultEnvelopeError):
                build_manifest("PRIMARY", "EVENT05-PACKAGE", "EVENT05-PRIMARY", [converted["payload"]] * 3)


if __name__ == "__main__":
    unittest.main()

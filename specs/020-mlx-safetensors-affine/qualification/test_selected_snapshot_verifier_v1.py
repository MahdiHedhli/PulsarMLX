import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("snapshot_verifier", Path(__file__).with_name("selected-snapshot-verifier-v1.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class SnapshotCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pulsar-snapshot-verifier-")
        self.path = Path(self.tmp.name) / "synthetic.snapshot"
        ranges = [bytes([i + 1]) * (i + 3) for i in range(9)]
        lengths = [len(r) for r in ranges]
        owned = {
            "schema": "pulsarmlx.bounded-expert-owned/1",
            "selected_range_sha256": [hashlib.sha256(r).hexdigest() for r in ranges],
            "owned_bytes": sum(lengths),
            "plan": {"selected_bytes": sum(lengths), "metadata_snapshot_sha256": "1" * 64,
                     "planes": [{"ranges": [{"len": n} for n in lengths[i:i+3]]} for i in (0, 3, 6)]},
        }
        header = json.dumps({"schema": "pulsarmlx.selected-expert-snapshot/1", "owned": owned, "payload_lengths": lengths}).encode()
        raw = b"PLSEX001" + struct.pack("<Q", len(header)) + header + b"".join(ranges)
        self.path.write_bytes(raw)
        self.capture = {"schema": "pulsarmlx.selected-expert-freeze/1", "owned": owned,
                        "requested_payload_bytes": sum(lengths), "snapshot_payload_bytes_written": sum(lengths),
                        "payload_read_calls": 9, "native_calls": 0, "snapshot_bytes": len(raw),
                        "snapshot_sha256": hashlib.sha256(raw).hexdigest()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_original_synthetic_content(self):
        self.assertEqual(v.verify(self.path, self.capture)["status"], "PASS")

    def test_payload_mutation(self):
        raw = bytearray(self.path.read_bytes()); raw[-1] ^= 1; self.path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "range hash"):
            v.verify(self.path, self.capture)

    def test_capture_hash_substitution(self):
        self.capture["snapshot_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "snapshot hash"):
            v.verify(self.path, self.capture)

    def test_truncated_file(self):
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "framing"):
            v.verify(self.path, self.capture)

    def test_oversized_header_before_payload(self):
        self.path.write_bytes(b"PLSEX001" + struct.pack("<Q", v.MAX_HEADER + 1))
        with self.assertRaisesRegex(ValueError, "header budget"):
            v.verify(self.path, self.capture)

    def test_native_claim_refusal(self):
        self.capture["native_calls"] = 1
        with self.assertRaisesRegex(ValueError, "capture calls"):
            v.verify(self.path, self.capture)


if __name__ == "__main__":
    unittest.main()

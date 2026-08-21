import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from scripts.research import f017_bound_authority_resolver_v2 as resolver
from scripts.research import f017_real_payload_event_detector_v2 as detector
from scripts.research import f017_apple_serial_f32_capture_wrapper_v2 as wrapper
from scripts.research import f017_apple_serial_f32_capture_terminalizer_v2 as terminalizer


def write(path: Path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(path, 0o400)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StrictResolverTests(unittest.TestCase):
    def test_bool_is_not_int(self):
        self.assertFalse(resolver.exact_equal(True, 1))

    def test_int_is_not_float(self):
        self.assertFalse(resolver.exact_equal(1, 1.0))

    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.json"
            path.write_text('{"x":1,"x":1}')
            with self.assertRaises(resolver.ResolutionError):
                resolver.load(path)


class EventDetectorTests(unittest.TestCase):
    def event(self):
        return {"schema":"pulsarmlx.f017.real-payload-event-result","event_id":"E-1","access_accounting":{"ledger_before":175,"ledger_after":176,"consumed_reads":1},"receipts":[{"ordinal":0,"ledger_after":176,"receipt_sha256":"a" * 64}]}

    def test_schema_event_detected_without_filename(self):
        event = detector.detect(json.dumps(self.event()).encode())
        self.assertEqual((event.ledger_before, event.ledger_after), (175, 176))

    def test_bool_count_rejected(self):
        value = self.event(); value["access_accounting"]["consumed_reads"] = True
        with self.assertRaises(detector.EventDetectionError): detector.detect(json.dumps(value).encode())

    def test_duplicate_event_key_rejected(self):
        with self.assertRaises(detector.EventDetectionError): detector.detect(b'{"schema":"pulsarmlx.f017.real-payload-event-result","schema":"x"}')

    def test_unrecognized_advancing_schema_rejected(self):
        value = self.event(); value["schema"] = "unknown.advancing"
        with self.assertRaisesRegex(detector.EventDetectionError, "unrecognized"):
            detector.detect(json.dumps(value).encode())


class RN1Tests(unittest.TestCase):
    def make_started(self, root: Path, invocation="mine"):
        root.mkdir()
        owner_sha = write(root / "owner.json", {"schema":"pulsarmlx.f017.apple-production-serial-f32-owned-lock","attempt_id":"A-1","invocation_id":invocation})
        write(root / "attempt-start.json", {"attempt_id":"A-1","invocation_id":invocation,"owner_sha256":owner_sha})
        (root / "payload-receipts").mkdir()
        return owner_sha

    def test_exclusive_attempt_creation_one_winner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "attempt"
            outcomes = []
            def contender():
                try: os.mkdir(root); outcomes.append("won")
                except FileExistsError: outcomes.append("lost")
            a = threading.Thread(target=contender); b = threading.Thread(target=contender)
            a.start(); b.start(); a.join(); b.join()
            self.assertEqual(sorted(outcomes), ["lost", "won"])

    def test_exception_terminalization_requires_invocation_owner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "attempt"; owner_sha = self.make_started(root)
            with self.assertRaises(wrapper.GateError): wrapper.terminalize_owned_failure(root, "other", owner_sha, "X", 1)
            self.assertFalse((root / "terminal.json").exists())

    def test_receipt_count_disagrees_with_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "attempt"; owner_sha = self.make_started(root)
            write(root / "terminal.json", {"invocation_id":"mine","owner_sha256":owner_sha,"consumed_reads":1,"receipt_inventory":[],"ledger_after":176})
            with self.assertRaisesRegex(wrapper.GateError, "TERMINAL_RECEIPT_COUNT_MISMATCH"): terminalizer.reconcile(root)

    def test_orphan_inventory_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "attempt"; owner_sha = self.make_started(root)
            write(root / "terminal.json", {"invocation_id":"mine","owner_sha256":owner_sha,"consumed_reads":0,"receipt_inventory":[],"ledger_after":175})
            write(root / "orphan.bin", {"unexpected":True})
            rows=[]
            for name in ["owner.json","attempt-start.json","terminal.json"]:
                rows.append({"path":name,"sha256":wrapper.sha(root/name)})
            write(root / "artifact-inventory.json", {"artifacts":rows})
            with self.assertRaisesRegex(wrapper.GateError, "ORPHAN_OR_MISSING_ARTIFACT"): terminalizer.reconcile(root)

    def test_wrapper_v1_tombstone(self):
        script = Path(__file__).parents[1] / "f017_apple_serial_f32_capture_wrapper_v1.py"
        result = subprocess.run([str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 78)
        self.assertIn("TOMBSTONED", result.stderr)


if __name__ == "__main__":
    unittest.main()

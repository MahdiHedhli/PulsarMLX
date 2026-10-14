"""Tiny CPU-only analytic and frozen packet rejection tests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qwen38_studio_packet as p
from qwen38_studio_fixture import fixture as generated_fixture


class StudioPacketTests(unittest.TestCase):
    def test_literal_analytic_fixture_and_generated_identity(self):
        result = p.selfcheck()
        self.assertEqual(result["status"], "PASS_ANALYTIC_ONLY")
        self.assertEqual(result["probes"], 27)
        self.assertFalse(result["runtime_executed"])
        self.assertEqual(result["upstream_parity"], "BLOCKED")

    def test_no_second_shift_for_converted_or_gated_norm(self):
        raw = p.rms([3, 4], [.25, -.25], epsilon=1e-6, layout="raw-hf", family=p.CENTERED[0])
        converted = p.rms([3, 4], [1.25, .75], epsilon=1e-6, layout="converted", family=p.CENTERED[0])
        self.assertEqual(raw, converted)
        wrong = p.rms([3, 4], [1.25, .75], epsilon=1e-6, layout="raw-hf", family=p.CENTERED[0])
        with self.assertRaises(p.PacketError):
            p.compare(wrong, converted, atol=1e-6, rtol=1e-5)
        gated = p.rms([3, 4], [.25, -.25], epsilon=1e-6, layout="raw-hf", family="linear_attn.norm")
        self.assertLess(gated[1], 0)
        with self.assertRaises(p.PacketError):
            p.rms([3, 4], [1, 1], epsilon=1e-6, layout="guessed", family=p.CENTERED[0])

    def test_deltanet_rms_shortcut_is_detected(self):
        actual = p.l2([3, 4], epsilon=1e-12)
        self.assertEqual(actual, [.6, .8])
        with self.assertRaises(p.PacketError):
            p.compare([x * 2**.5 for x in actual], actual, atol=1e-6, rtol=1e-5)

    def test_zero_and_near_zero_l2_are_policy_only(self):
        self.assertEqual(p.l2([0, 0], epsilon=1e-12), [0, 0])
        self.assertEqual(p.l2([1e-14, 0], epsilon=1e-12), [.01, 0])

    def test_both_stops_and_repeated_resets(self):
        self.assertEqual(p.histories([7, 8, 248046, 9, 248044, 248044, 10]),
                         [[7], [7, 8], [], [9], [], [], [10]])
        for bad in ([True], [-1], [248320], [1.5]):
            with self.assertRaises(p.PacketError): p.histories(bad)

    def test_boundary_future_leak_and_current_partial_key(self):
        for query in (2046, 2047, 2048, 2049, 2079):
            keys = [0, query, 2079] if query != 2079 else [0, query]
            visible = p.causal_candidates(query, keys)
            self.assertIn(query, visible)
            self.assertTrue(all(k <= query for k in visible))
        with self.assertRaises(p.PacketError): p.causal_candidates(2048, [0, 0])
        with self.assertRaises(p.PacketError): p.boundary_attention(2047, [2048])

    def test_comparison_fails_on_shape_nonfinite_or_tolerance(self):
        for actual, expected in (([1], [1, 2]), ([float("nan")], [0]), ([0], [float("inf")]), ([True], [1])):
            with self.assertRaises(p.PacketError): p.compare(actual, expected, atol=0, rtol=0)
        for bad in (-1, float("nan"), True):
            with self.assertRaises(p.PacketError): p.compare([1], [1], atol=bad, rtol=0)
        p.compare([1.0001], [1], atol=.0001, rtol=0)
        with self.assertRaises(p.PacketError): p.compare([.001], [0], atol=.0001, rtol=.5)

    def test_bounded_reader_refuses_symlink_large_and_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            file = root / "small.json"; file.write_text("{}")
            link = root / "link.json"; link.symlink_to(file)
            with self.assertRaises(p.PacketError): p.bounded_bytes(link)
            with self.assertRaises(p.PacketError): p.bounded_bytes(root)
            with file.open("wb") as stream:
                stream.truncate(p.MAX_BYTES + 1)
            with self.assertRaises(p.PacketError): p.bounded_bytes(file)

    def test_duplicate_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "data.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(text)
                with self.assertRaises(p.PacketError): p.load_json(path)

    def test_fixed_fixture_seed_is_not_a_hash_oracle(self):
        fixture = p.load_json(p.PACKET / "analytic-fixtures.json")
        fixture["seed"] = 0
        with patch.object(p, "check_requirements"), patch.object(p, "load_json", return_value=fixture):
            with self.assertRaises(p.PacketError): p.selfcheck()

    def test_fixture_generator_matches_frozen_values(self):
        self.assertEqual(generated_fixture(), p.load_json(p.PACKET / "analytic-fixtures.json"))

    def test_resource_and_execution_gate_drift_rejected(self):
        environment = p.load_json(p.PACKET / "environment-requirements.json")
        request = p.load_json(p.PACKET / "runtime-requests.json")
        p.check_requirements()
        request["gates_bytes"]["process_tree"] += 1
        with patch.object(p, "load_json", side_effect=[environment, request]):
            with self.assertRaises(p.PacketError): p.check_requirements()
        environment["status"] = "AUTHORIZED"
        with patch.object(p, "load_json", side_effect=[environment, request]):
            with self.assertRaises(p.PacketError): p.check_requirements()

    def test_frozen_manifest_changed_source_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            artifact = root / "scripts/research/small.py"
            artifact.parent.mkdir(parents=True); artifact.write_bytes(b"pass\n")
            entry = {"path": "scripts/research/small.py", "size_bytes": 5,
                     "sha256": hashlib.sha256(b"pass\n").hexdigest()}
            manifest = {"schema": "pulsarmlx.qwen38.studio-packet-files/1", "files": [entry]}
            with patch.object(p, "ROOT", root), patch.object(p, "load_json", return_value=manifest):
                self.assertEqual(p.verify()["files"], 1)
                artifact.write_bytes(b"fail\n")
                with self.assertRaises(p.PacketError): p.verify()
                for name in ("/tmp/x.py", "scripts/research/../../x.py", "models/x.py", "scripts/research/x.bin"):
                    entry["path"] = name
                    with self.assertRaises(p.PacketError): p.verify()

    def test_frozen_manifest_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            file = root / "scripts/research/x.py"
            file.parent.mkdir(parents=True); file.write_bytes(b"pass\n")
            entry = {"path": "scripts/research/x.py", "size_bytes": 5, "sha256": hashlib.sha256(b"pass\n").hexdigest()}
            manifest = {"schema": "pulsarmlx.qwen38.studio-packet-files/1", "files": [entry, entry]}
            with patch.object(p, "ROOT", root), patch.object(p, "load_json", return_value=manifest):
                with self.assertRaises(p.PacketError): p.verify()


if __name__ == "__main__":
    unittest.main()

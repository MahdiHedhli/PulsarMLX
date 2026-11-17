"""Admission bridge controls using only in-memory capabilities; no numerical launch."""
import os
from pathlib import Path
import pwd
import sys
import unittest
from unittest.mock import patch

import studio019_py_gate as gate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = {"head": "1" * 40, "tree": "2" * 40}
STATE = Path(pwd.getpwuid(os.getuid()).pw_dir) / "LocalWorktrees/PulsarMLX-studio019-state"
OP = "a" * 32


class GateBinding(unittest.TestCase):
    def cap(self, fixture=False):
        return dict(schema="studio019-fixture-cap/1" if fixture else "studio019-child-cap/1",
                    stage="synthetic-ack" if fixture else "native", task=gate.TASK,
                    source=SOURCE, operation=OP,
                    python_gate=dict(policy="/policy", sha256="b" * 64,
                                     interpreter=str(Path(sys.executable).resolve())))

    def bind(self, cap, path=None, role="helper", operation=OP):
        path = path or STATE / "campaign-native/child-cap.json"
        args = [str(path)] + (["3"] if role in ("bootstrap", "fixture-bootstrap") else [])
        with patch.object(gate, "real", side_effect=Path), \
             patch.object(gate, "raw", return_value=gate.wire(cap)), \
             patch.object(sys, "pycache_prefix", str(path.parent / ("cache-" + role))):
            return gate.stage_binding(role, "/policy", "b" * 64,
                                      str(path.parent / ("python-" + role + ".json")), operation, args)

    def test_native_and_fixture_have_distinct_fresh_paths(self):
        self.assertEqual(self.bind(self.cap())["source"], SOURCE)
        path = STATE / ("synthetic-admission-" + OP) / "fixture-cap.json"
        self.assertEqual(self.bind(self.cap(True), path, "fixture-helper")["stage"], "synthetic-ack")
        for bad in (STATE / "campaign-reference/child-cap.json",
                    STATE.with_name("PulsarMLX-studio017-state") / "campaign-native/child-cap.json",
                    STATE / "other/campaign-native/child-cap.json"):
            with self.assertRaisesRegex(ValueError, "fresh native stage binding"):
                self.bind(self.cap(), bad)
        with self.assertRaisesRegex(ValueError, "fresh synthetic role binding"):
            self.bind(self.cap(True), STATE / "nested" / path.parent.name / path.name, "fixture-helper")
        with self.assertRaises(ValueError):
            self.bind(self.cap(True), path, "helper")

    def test_capability_task_role_operation_and_policy(self):
        for key, value in (("task", "studio017"), ("schema", "studio017-child-cap/1"),
                           ("stage", "reference"), ("operation", "c" * 32),
                           ("source", {"head": "g" * 40, "tree": "2" * 40}),
                           ("python_gate", dict(policy="/old-policy", sha256="b" * 64,
                                               interpreter=str(Path(sys.executable).resolve())))):
            cap = self.cap(); cap[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.bind(cap)
        for role in ("reference", "eligibility"):
            with self.assertRaises(ValueError):
                gate.gate([role, "/policy", "b" * 64, "/python-" + role + ".json", OP])
        with self.assertRaises(ValueError):
            gate.cap_cli("/nonexistent", "reference")

    def test_source_policy_mismatch_precedes_import_installation(self):
        cap = self.cap()
        policy = dict(task=gate.TASK, source=dict(SOURCE, head="3" * 40), roots=["/std", "/dyn", "/np", str(HERE)])
        with patch.object(gate, "stage_binding", return_value=cap), \
             patch.object(sys, "pycache_prefix", "/cache"), \
             patch.object(gate, "real", side_effect=Path), \
             patch.object(gate, "flags"), patch.object(gate, "binding", return_value=policy), \
             patch.object(gate, "validate"), patch.object(gate, "install") as install:
            with self.assertRaisesRegex(ValueError, "capability task/source policy mismatch"):
                gate.gate(["helper", "/policy", "b" * 64, "/python-helper.json", OP, "/cap"])
            install.assert_not_called()

    def test_policy_digest_and_module_bytes_are_pinned(self):
        with patch.object(gate, "raw", return_value=b"changed"):
            with self.assertRaisesRegex(ValueError, "policy digest"):
                gate.binding("/policy", "b" * 64)
            with self.assertRaisesRegex(ValueError, "unapproved module"):
                gate.source_bytes("/helper.py", {"modules": {"/helper.py": "b" * 64}})


class RustBridgeSource(unittest.TestCase):
    def test_explicit_leading_flag_selects_matching_embedded_sources(self):
        source = (ROOT / "crates/mlx-expert-mlp/src/full_flash/child.rs").read_text()
        # Source controls only: owner separately compiles and exercises the actual binary.
        self.assertIn('a.first().is_some_and(|arg| arg == "--studio019-route-b")', source)
        self.assertIn('if studio019 {\n        a.remove(0);\n    }', source)
        branch = source.split('if studio019 {', 2)[2].split('let verify =', 1)[0]
        selected, default = branch.split('} else {', 1)
        for version, section in (("019", selected), ("017", default)):
            for name in ("supervise", "py_gate"):
                filename = "studio" + version + "_" + name + ".py"
                self.assertIn('"' + filename + '"', section)
                self.assertIn('include_bytes!("../../../../scripts/research/' + filename + '")', section)
        self.assertIn('fs::read(&verify).map_err(err)? != supervisor_bytes', source)
        self.assertIn('fs::read(&gate).map_err(err)? != gate_bytes', source)
        self.assertLess(source.index('Python gate source changed'), source.index('ffi::verify_abi()?;'))


if __name__ == "__main__":
    unittest.main()

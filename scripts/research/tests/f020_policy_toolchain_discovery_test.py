"""Host-only tool discovery controls. Version and manager subprocesses are intercepted."""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f020_policy_native_custody as custody


class PinnedToolchainTests(unittest.TestCase):
    target = "aarch64-apple-darwin"
    versions = {
        "cargo": "cargo 1.95.0 (f2d3ce0bd 2026-03-21)",
        "rustc": "rustc 1.95.0 (59807616e 2026-04-14)",
    }

    def mocked(self, obj, name, **kwargs):
        context = patch.object(obj, name, **kwargs)
        self.addCleanup(context.stop)
        return context.start()

    @staticmethod
    def fixture_bytes(name, cpu=0x0100000C):
        # Synthetic file header and role label. The bytes are never executed.
        return struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0) + name.encode()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.bin = self.home / ".rustup" / "toolchains" / ("1.95.0-" + self.target) / "bin"
        self.bin.mkdir(parents=True)
        self.pins = {}
        for name, version in self.versions.items():
            raw = self.fixture_bytes(name)
            path = self.bin / name
            path.write_bytes(raw)
            path.chmod(0o700)
            self.pins[name] = (version, hashlib.sha256(raw).hexdigest())
        self.mocked(Path, "home", return_value=self.home)
        self.mocked(custody.os, "uname", return_value=SimpleNamespace(sysname="Darwin", machine="arm64"))
        p = patch.object(custody, "_RUSTUP_SYSTEM_DIRS", ())
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(custody, "_TOOLCHAIN_PINS", self.pins)
        p.start()
        self.addCleanup(p.stop)
        self.manager_path = self.home / "manager-observation"
        self.calls = []
        self.tool_output = self.mocked(custody.subprocess, "check_output", side_effect=self.output)
        self.effect_guards = [self.mocked(obj, name, side_effect=AssertionError("unexpected " + name))
                              for obj, name in ((custody.subprocess, "Popen"), (custody, "_run_build"),
                                                (custody, "_record"), (custody.prior, "installed"),
                                                (custody.prior, "wait_child"), (custody.prior, "exclusive"),
                                                (custody.prior, "fixture_identity"))]
        self.addCleanup(self.assert_no_effects)

    def assert_no_effects(self):
        for spy in self.effect_guards:
            spy.assert_not_called()

    def output(self, argv, **kwargs):
        args = [str(arg) for arg in argv]
        self.calls.append(args)
        self.assertEqual(kwargs["env"]["HOME"], str(self.home))
        self.assertNotIn(str(self.home / "decoy"), kwargs["env"]["PATH"].split(os.pathsep))
        self.assertLessEqual(kwargs["timeout"], 30)
        if args[0] == str(self.manager_path):
            name = args[-1]
            self.assertIn(name, self.versions)
            self.assertEqual(args[1:], ["which", "--toolchain", "1.95.0", name])
            return (str(self.bin / name) + "\n").encode()
        path = Path(args[0])
        self.assertEqual(path, self.bin / path.name)
        self.assertEqual(args[1:], ["-V"])
        return (self.versions[path.name] + "\n").encode()

    def test_absent_manager_uses_pinned_pair_and_preserves_build_command(self):
        with patch.dict(os.environ, {"PATH": str(self.home / "decoy"), "RUSTUP_HOME": str(self.home / "decoy")}):
            tools = custody._toolchain()
        self.assertEqual({tuple(args) for args in self.calls},
                         {(str(self.bin / name), "-V") for name in self.versions})
        for name, (version, digest) in self.pins.items():
            self.assertEqual(tools[name]["discovery"], "direct-installed")
            self.assertEqual(tools[name]["target"], self.target)
            self.assertEqual((tools[name]["path"], tools[name]["version"], tools[name]["sha256"]),
                             (str(self.bin / name), version, digest))
        paths = dict(binary=self.home / "target/release" / custody.BIN, prefix=self.home / "fixture-prefix")
        args, env = custody._command(paths, tools)
        self.assertEqual(args[0], str(self.bin / "cargo"))
        self.assertEqual(env["RUSTC"], str(self.bin / "rustc"))
        self.assertEqual(Path(env["PATH"].split(os.pathsep)[0]), self.bin)
        self.assertEqual(env["CARGO_NET_OFFLINE"], "true")
        self.assertIn("--offline", args)
        self.assertIn("--locked", args)
        self.assertEqual(args[args.index("-j") + 1], "2")

    def test_present_manager_takes_precedence_and_its_failures_are_final(self):
        self.mocked(custody, "_rustup_manager", return_value=self.manager_path)
        tools = custody._toolchain()
        self.assertEqual({v["discovery"] for v in tools.values()}, {"rustup"})
        self.assertEqual({args[-1] for args in self.calls if args[0] == str(self.manager_path)}, set(self.pins))
        self.calls.clear()
        self.tool_output.side_effect = subprocess.CalledProcessError(1, "manager")
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            custody._toolchain()
        self.assertEqual(str(self.tool_output.call_args.args[0][0]), str(self.manager_path))
        outside = self.home / "unrelated-cargo"
        outside.write_bytes(self.fixture_bytes("cargo"))
        outside.chmod(0o700)
        def crossed(argv, **kwargs):
            if str(argv[0]) == str(self.manager_path):
                return (str(outside) + "\n").encode()
            self.fail("resolved an out-of-root tool")
        self.tool_output.side_effect = crossed
        with self.assertRaises((ValueError, OSError)):
            custody._toolchain()

    def test_invalid_pairs_refuse_before_version_or_build(self):
        for name in ("cargo", "rustc"):
            p = self.bin / name
            original = p.read_bytes()
            for kind in ("absent", "nonexecutable", "spoof", "leaf-link"):
                with self.subTest(name=name, refusal=kind):
                    if kind == "absent":
                        p.unlink()
                    elif kind == "nonexecutable":
                        p.chmod(0o600)
                    elif kind == "spoof":
                        p.write_bytes(self.fixture_bytes("tool-with-plausible-version"))
                    else:
                        other = self.home / ("outside-" + name)
                        p.rename(other)
                        p.symlink_to(other)
                    try:
                        with self.assertRaises((ValueError, OSError)):
                            custody._toolchain()
                        self.tool_output.assert_not_called()
                    finally:
                        if p.is_symlink():
                            p.unlink()
                        p.write_bytes(original)
                        p.chmod(0o700)
        foreign = self.home / "foreign-bin"
        self.bin.rename(foreign)
        self.bin.symlink_to(foreign, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            custody._toolchain()
        self.tool_output.assert_not_called()

    def test_wrong_executable_architecture_even_with_matching_fixture_digest(self):
        raw = self.fixture_bytes("cargo", cpu=0x01000007)
        (self.bin / "cargo").write_bytes(raw)
        self.pins["cargo"] = self.versions["cargo"], hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "Darwin arm64"):
            custody._toolchain()
        self.tool_output.assert_not_called()

    def test_unusable_manager_does_not_enable_fallback(self):
        # An occupied directory marks a broken installation. No manager binary is created.
        (self.home / ".cargo/bin/rustup").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "unusable"):
            custody._toolchain()
        self.tool_output.assert_not_called()

    def test_wrong_machine_and_wrong_version(self):
        with patch.object(custody.os, "uname", return_value=SimpleNamespace(sysname="Darwin", machine="x86_64")):
            with self.assertRaises(ValueError):
                custody._toolchain()
        self.tool_output.assert_not_called()
        for name, bad in (("rustc", "rustc 1.97.1"), ("cargo", "cargo 1.95.0 (other-build)")):
            def wrong(argv, **kwargs):
                value = self.output(argv, **kwargs)
                return (bad + "\n").encode() if Path(argv[0]).name == name else value
            self.tool_output.side_effect = wrong
            with self.subTest(name=name), self.assertRaises(ValueError):
                custody._toolchain()

    def test_changed_bytes_during_version_check_refuse(self):
        def replace_tool(argv, **kwargs):
            value = self.output(argv, **kwargs)
            if len(self.calls) == 1:
                Path(argv[0]).write_bytes(self.fixture_bytes("changed"))
            return value
        self.tool_output.side_effect = replace_tool
        with self.assertRaises((ValueError, OSError)):
            custody._toolchain()

    def test_build_entry_refuses_missing_pair_and_input_drift_before_effects(self):
        (self.bin / "cargo").unlink()
        p = {"binary": self.home / "target/release" / custody.BIN}
        self.mocked(custody, "_host", return_value={})
        self.mocked(custody, "_paths", return_value=p)
        cfg = dict(commit="a"*40, tree="b"*40, input_sha256="c"*64)
        with patch.object(custody, "_admission", return_value={}):
            with self.assertRaises((ValueError, OSError)):
                custody.capture_build(cfg)
        self.tool_output.assert_not_called()
        self.assertFalse((self.home / "target").exists())

        self.mocked(custody.prior.old, "source", return_value=dict(commit=cfg["commit"], tree=cfg["tree"]))
        self.mocked(custody, "_git", side_effect=[custody.BASE.encode(), custody.BASE_TREE.encode()])
        self.mocked(custody, "closure", return_value=("d"*64, []))
        tool = self.mocked(custody, "_toolchain", side_effect=AssertionError("unexpected discovery"))
        with self.assertRaisesRegex(ValueError, "qualified inputs"):
            custody.capture_build(cfg)
        tool.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts/research"


def load_module(name: str, path: Path):
    import sys
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


WRAPPER = load_module("aggregate_release_wrapper", SCRIPTS / "f017_representative_routed_aggregate_release_wrapper_v1.py")
TERMINALIZER = load_module("aggregate_release_terminalizer", SCRIPTS / "f017_representative_routed_aggregate_release_terminalizer_v1.py")


class RoutedAggregateReleaseWrapperTests(unittest.TestCase):
    def make_roots(self, temporary: str):
        home = Path(temporary)
        paths = WRAPPER.fixed_paths(home)
        paths["release_root"].mkdir(parents=True, mode=0o700)
        paths["output_root"].mkdir(mode=0o700)
        os.chmod(paths["release_root"], 0o700)
        os.chmod(paths["output_root"], 0o700)
        return paths

    def test_fixed_paths_have_no_caller_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = WRAPPER.fixed_paths(Path(temporary))
            self.assertEqual(paths["state_root"], Path(temporary) / ".local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/attempt-state")
            self.assertEqual(paths["output"].name, "routed-aggregate.f64le")

    def test_no_replace_publication_is_durable_and_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            raw = bytes(WRAPPER.OUTPUT_BYTES)
            identity = WRAPPER.publish_no_replace(raw, paths["output_root"])
            self.assertEqual(identity, hashlib.sha256(raw).hexdigest())
            metadata = paths["output"].lstat()
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o400)
            self.assertEqual(metadata.st_nlink, 1)
            self.assertEqual(paths["output"].read_bytes(), raw)

    def test_preexisting_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            paths["output"].write_bytes(b"sentinel")
            os.chmod(paths["output"], 0o400)
            with self.assertRaises(WRAPPER.ReleaseError):
                WRAPPER.publish_no_replace(bytes(WRAPPER.OUTPUT_BYTES), paths["output_root"])
            self.assertEqual(paths["output"].read_bytes(), b"sentinel")

    def test_symlink_output_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            actual = base / "actual"
            actual.mkdir(mode=0o700)
            alias = base / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            with self.assertRaises(WRAPPER.ReleaseError):
                WRAPPER.publish_no_replace(bytes(WRAPPER.OUTPUT_BYTES), alias)

    def test_attempt_start_is_exclusive_and_durable(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            for path in (release, approval, token):
                path.write_text("{}\n")
            identity = WRAPPER.begin_attempt(paths, release, approval, token)
            self.assertEqual(identity, hashlib.sha256((paths["state_root"] / "attempt-start.json").read_bytes()).hexdigest())
            with self.assertRaises(WRAPPER.ReleaseError):
                WRAPPER.begin_attempt(paths, release, approval, token)

    def test_terminalizer_marks_started_no_output_consumed(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            release.write_text("{}\n")
            approval.write_text("{}\n")
            token.write_text("{}\n")
            WRAPPER.begin_attempt(paths, release, approval, token)
            packet = TERMINALIZER.reconcile(paths["state_root"], paths["output"], release)
            self.assertEqual(packet["disposition"], "INTERRUPTED_NO_OUTPUT")
            self.assertTrue(packet["release_consumed"])
            self.assertFalse(packet["retry"])

    def test_terminalizer_recovers_published_output_without_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            release.write_text("{}\n")
            approval.write_text("{}\n")
            token.write_text("{}\n")
            WRAPPER.begin_attempt(paths, release, approval, token)
            identity = WRAPPER.publish_no_replace(bytes(WRAPPER.OUTPUT_BYTES), paths["output_root"])
            packet = TERMINALIZER.reconcile(paths["state_root"], paths["output"], release)
            self.assertEqual(packet["disposition"], "INTERRUPTED_OUTPUT_PUBLISHED_REQUIRES_ADJUDICATION")
            self.assertEqual(packet["output_sha256"], identity)
            self.assertTrue(packet["release_consumed"])
            self.assertFalse(packet["output_authority"])
            self.assertTrue(packet["output_present_for_adjudication"])

    def test_terminalizer_reconstructs_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            release.write_text("{}\n")
            approval.write_text("{}\n")
            token.write_text("{}\n")
            WRAPPER.begin_attempt(paths, release, approval, token)
            identity = WRAPPER.publish_no_replace(bytes(WRAPPER.OUTPUT_BYTES), paths["output_root"])
            WRAPPER.write_terminal(paths, "COMPLETE", identity, None)
            packet = TERMINALIZER.reconcile(paths["state_root"], paths["output"], release)
            self.assertEqual(packet["disposition"], "COMPLETE_RECONSTRUCTED")
            self.assertEqual(packet["output_sha256"], identity)
            self.assertTrue(packet["output_authority"])

    def test_terminal_failure_never_confers_output_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self.make_roots(temporary)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            release.write_text("{}\n")
            approval.write_text("{}\n")
            token.write_text("{}\n")
            WRAPPER.begin_attempt(paths, release, approval, token)
            identity = WRAPPER.publish_no_replace(bytes(WRAPPER.OUTPUT_BYTES), paths["output_root"])
            WRAPPER.write_terminal(paths, "TERMINAL_FAILURE", identity, "synthetic-after-publish")
            packet = TERMINALIZER.reconcile(paths["state_root"], paths["output"], release)
            self.assertEqual(packet["disposition"], "TERMINAL_FAILURE_RECONSTRUCTED")
            self.assertEqual(packet["output_sha256"], identity)
            self.assertFalse(packet["output_authority"])
            self.assertTrue(packet["output_present_for_adjudication"])


if __name__ == "__main__":
    unittest.main()

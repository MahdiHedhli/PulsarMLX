"""Host-only controller controls. No native import, build or execution."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "packed_affine_m1a_v1.py"
spec = importlib.util.spec_from_file_location("m1a_controller", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REPOSITORY": m.REPOSITORY, "GITHUB_REF": "refs/heads/" + m.BRANCH,
                    "GITHUB_RUN_ATTEMPT": "1", "PULSAR_ADOPTION_PHASE": "m1a", "GITHUB_RUN_ID": "123"}
        self.event = {"inputs": {"mode": "full", "packed_affine_m1a": "true"}}
        self.run = {"id": 123, "head_sha": "controller", "event": "workflow_dispatch", "head_branch": m.BRANCH,
                    "run_attempt": 1, "path": ".github/workflows/macos.yml"}

    def test_exact_opt_in_route(self):
        m.require_route(self.env, self.event)
        for event in ("push", "pull_request"):
            with self.subTest(event=event), self.assertRaises(ValueError):
                m.require_route({**self.env, "GITHUB_EVENT_NAME": event}, self.event)
        for inputs in ({}, {"mode": "full", "packed_affine_m1a": "false"}, {"mode": "auto", "packed_affine_m1a": "true"}):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                m.require_route(self.env, {"inputs": inputs})

    def test_wrong_host_ref_or_m1b_cannot_enter(self):
        for key, value in (("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "fork/repo"),
                           ("GITHUB_REF", "refs/heads/main"), ("PULSAR_ADOPTION_PHASE", "m1b"),
                           ("PULSAR_ADOPTION_PHASE", ""), ("GITHUB_RUN_ATTEMPT", "2")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                m.require_route({**self.env, key: value}, self.event)

    def test_prior_run_or_new_id_does_not_reset_allowance(self):
        m.require_only_campaign([self.run], "123", "controller")
        for rows in ([], [self.run, {**self.run, "id": 124}], [{**self.run, "id": 124}], [{**self.run, "run_attempt": 2}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                m.require_only_campaign(rows, "123", "controller")
        with self.assertRaises(ValueError):
            m.require_only_campaign([self.run], "123", "wrong-controller")

    def test_run_refuses_before_any_command(self):
        event = self.root / "event.json"
        event.write_text(json.dumps(self.event))
        with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event)}, clear=True), patch.object(m.subprocess, "run") as command, patch.object(m.subprocess, "check_output") as read:
            with self.assertRaises(ValueError):
                m.run_native_ci(self.root / "campaign")
            command.assert_not_called()
            read.assert_not_called()

    def test_original_input_bytes_and_occupied_refusal(self):
        archive = SCRIPT.with_name(m.STEM + ".tar.gz")
        manifest = json.loads(SCRIPT.with_name(m.STEM + ".json").read_text())
        out = self.root / "inputs"
        m.extract_inputs(archive, manifest, out)
        self.assertEqual(len([p for p in out.rglob("*") if p.is_file()]), 46)
        self.assertEqual(m.digest(out / "fixtures/manifest.json"), "513b8c800be7f1f491d0bfa08748123066e6ef9369cc907e0a2d8475e733e597")
        with self.assertRaises(FileExistsError):
            m.extract_inputs(archive, manifest, out)
        with self.assertRaises(ValueError):
            m.extract_inputs(archive, {**manifest, "archive_sha256": "0" * 64}, self.root / "bad")

    def mutant_archive(self, name, kind="file", content=b"x", declared_hash=None, duplicate=False, size_delta=0):
        archive = self.root / "mutant.tar.gz"
        entries = [{"path": name, "bytes": len(content) + size_delta, "sha256": declared_hash or hashlib.sha256(content).hexdigest()}]
        entries += [{"path": "unused-" + str(i), "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()} for i in range(45)]
        with tarfile.open(archive, "w:gz") as tf:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            if kind == "link":
                info.type = tarfile.SYMTYPE
                info.linkname = "outside"
                info.size = 0
            tf.addfile(info, io.BytesIO(content))
            if duplicate:
                tf.addfile(info, io.BytesIO(content))
        sha = m.digest(archive)
        manifest = {"files": entries, "archive_sha256": sha, "archive_bytes": archive.stat().st_size, "unpacked_bytes": len(content)}
        with patch.object(m, "ARCHIVE_SHA", sha), self.assertRaises(ValueError):
            m.extract_inputs(archive, manifest, self.root / "out")

    def test_traversal_refused(self):
        self.mutant_archive("../escape")
        self.assertFalse((self.root / "escape").exists())

    def test_link_refused(self):
        self.mutant_archive("link", kind="link")

    def test_duplicate_refused(self):
        self.mutant_archive("a", duplicate=True)

    def test_file_tamper_refused(self):
        self.mutant_archive("a", declared_hash="0" * 64)

    def test_wrong_size_refused(self):
        self.mutant_archive("a", size_delta=1)

    def test_public_views_keep_original_and_view_identities_separate(self):
        source = self.root / "private"
        source.mkdir()
        m.write_new(source / "result.json", {"M1a_ran": True, "M1a_passed": False, "path": str(source / "child")})
        original = (source / "result.json").read_bytes()
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.root / "summary")}):
            m.export_public(source, self.root / "public")
        view = json.loads((self.root / "public/public-view-manifest.json").read_text())["files"][0]
        self.assertTrue(view["changed"])
        self.assertNotEqual(view["original_sha256"], view["public_sha256"])
        self.assertEqual((source / "result.json").read_bytes(), original)
        self.assertNotIn(str(source), (self.root / "public/result.json").read_text())

    def test_credential_like_content_refuses_export(self):
        with self.assertRaises(ValueError):
            m.public_text("Bearer " + "synthetic_test_sentinel", [])

    def test_ambiguous_build_artifacts_refused(self):
        p = self.root / "cargo.jsonl"
        p.write_text(json.dumps({"reason": "build-finished", "success": True}) + "\n")
        with self.assertRaises(ValueError):
            m.executable(p, "adoption_parent")


if __name__ == "__main__":
    unittest.main()

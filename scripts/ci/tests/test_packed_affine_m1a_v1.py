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
from contextlib import ExitStack
import urllib.error
import urllib.parse

SCRIPT = Path(__file__).resolve().parents[1] / "packed_affine_m1a_v1.py"
spec = importlib.util.spec_from_file_location("m1a_controller", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CheckoutBoundary(Exception):
    """Stop the successful path at its first permitted mutation; never execute."""


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REPOSITORY": m.REPOSITORY, "GITHUB_REF": "refs/heads/" + m.BRANCH,
                    "GITHUB_RUN_ATTEMPT": "1", "PULSAR_ADOPTION_PHASE": "m1a", "GITHUB_RUN_ID": "123"}
        self.event = {"inputs": {"mode": "full"}}
        self.authority = m.load_reconciliation()
        old = self.authority["predecessor"]
        self.run = {"id": 123, "head_sha": "controller", "event": "workflow_dispatch", "head_branch": m.BRANCH,
                    "run_attempt": 1, "path": ".github/workflows/macos.yml", "workflow_id": old["workflow_id"],
                    "status": "in_progress", "conclusion": None}
        self.predecessor = {**self.run, "id": old["run_id"], "head_sha": old["controller_commit"],
                            "status": "completed", "conclusion": "failure"}
        self.native = {"id": old["native_job_id"], "run_id": old["run_id"], "run_attempt": 1,
                       "head_sha": old["controller_commit"], "head_branch": m.BRANCH,
                       "name": "Apple MLX small-fixture validation", "status": "completed",
                       "conclusion": "cancelled", "runner_id": 0, "steps": []}
        self.api = {"runs": [self.predecessor, self.run], "run": self.predecessor.copy(),
                    "jobs": [self.native], "artifacts": [],
                    "commit": {"sha": old["controller_commit"], "tree": {"sha": old["controller_tree"]}}}
        self.api_override = None

    def api_response(self, request, timeout):
        url = urllib.parse.urlparse(request.full_url)
        path = url.path.split("/repos/" + m.REPOSITORY + "/", 1)[1]
        page = int(urllib.parse.parse_qs(url.query).get("page", ["1"])[0])
        if self.api_override:
            override = self.api_override(path, page)
            if override is not None:
                return io.BytesIO(json.dumps(override).encode())
        endpoint = "actions/runs/" + str(self.predecessor["id"])
        if path == "actions/workflows/macos.yml/runs":
            data = {"total_count": len(self.api["runs"]), "workflow_runs": self.api["runs"]}
        elif path == endpoint:
            data = self.api["run"]
        elif path == endpoint + "/attempts/1/jobs":
            data = {"total_count": len(self.api["jobs"]), "jobs": self.api["jobs"]}
        elif path == endpoint + "/artifacts":
            data = {"total_count": len(self.api["artifacts"]), "artifacts": self.api["artifacts"]}
        elif path.startswith("git/commits/"):
            data = self.api["commit"]
        else:
            raise AssertionError("unexpected API path: " + path)
        return io.BytesIO(json.dumps(data).encode())

    def run_admission(self, allowed=False, occupied=False):
        event = self.root / "event.json"
        event.write_text(json.dumps(self.event))
        root = self.root / "campaign"
        if occupied:
            root.mkdir()
            (root / "sentinel").write_text("retain")
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {**self.env, "GITHUB_EVENT_PATH": str(event), "GITHUB_SHA": "controller"}, clear=True))
            stack.enter_context(patch.object(m.platform, "system", return_value="Darwin"))
            stack.enter_context(patch.object(m.platform, "machine", return_value="arm64"))
            stack.enter_context(patch.object(m, "git", side_effect=lambda root, *args: "controller" if args == ("rev-parse", "HEAD") else ""))
            api = stack.enter_context(patch.object(m.urllib.request, "urlopen", side_effect=self.api_response))
            launch = stack.enter_context(patch.object(m.subprocess, "run", side_effect=CheckoutBoundary))
            read = stack.enter_context(patch.object(m.subprocess, "check_output", side_effect=AssertionError("unexpected subprocess read")))
            capture = stack.enter_context(patch.object(m, "capture", side_effect=AssertionError("unexpected build/child")))
            with self.assertRaises(CheckoutBoundary if allowed else (ValueError, FileNotFoundError, FileExistsError, OSError)):
                m.run_native_ci(root)
            if allowed:
                launch.assert_called_once_with(["git", "-C", str(m.CONTROLLER), "fetch", "--no-tags", "origin", m.CANDIDATE], check=True)
            else:
                launch.assert_not_called()
            capture.assert_not_called()
            read.assert_not_called()
            if occupied:
                api.assert_not_called()
                self.assertEqual((root / "sentinel").read_text(), "retain")
                self.assertFalse((root / "result.json").exists())
                return None
        self.assertFalse((root / "campaign/raw-probe.intent.json").exists())
        self.assertEqual((root / "campaign-claim.json").exists(), allowed)
        result = json.loads((root / "result.json").read_text())
        self.assertFalse(result["M1a_ran"])
        self.assertEqual(result["raw_probe_used"], 0)
        self.assertEqual(result["admission_evidence_sha256"], m.digest(root / "admission-evidence.json"))
        return result

    def test_exact_opt_in_route(self):
        m.require_route(self.env, self.event)
        for event in ("push", "pull_request"):
            with self.subTest(event=event), self.assertRaises(ValueError):
                m.require_route({**self.env, "GITHUB_EVENT_NAME": event}, self.event)
        for inputs in ({}, {"mode": "full", "packed_affine_m1a": "false"}, {"mode": "auto", "packed_affine_m1a": "true"}):
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                m.require_route(self.env, {"inputs": inputs})

    def test_only_exact_full_manual_selection(self):
        self.assertTrue(m.selected(self.env,self.event))
        for event in ('push','pull_request'):
            self.assertFalse(m.selected({**self.env,'GITHUB_EVENT_NAME':event},self.event))
        for mode in ('auto','evidence'):
            self.assertFalse(m.selected(self.env,{'inputs':{'mode':mode}}))
        for inputs in ({},{'mode':'full','packed_affine_m1a':'true'},{'mode':'unknown'}):
            with self.assertRaises(ValueError):m.selected(self.env,{'inputs':inputs})
        with self.assertRaises(ValueError):m.selected({**self.env,'GITHUB_REF':'refs/heads/main'},self.event)

    def test_original_authority_preserved_and_successor_bound(self):
        self.assertEqual(m.digest(m.CONTROLLER/m.ORIGINAL_RECONCILIATION),m.ORIGINAL_RECONCILIATION_SHA)
        self.assertEqual(self.authority['candidate_inventory_sha256'],m.INVENTORY_SHA)
        self.assertEqual(self.authority['additional_designated_dispatches_added'],0)
        self.assertEqual(self.authority['existing_held_opportunity_released_conditionally'],1)

    def test_actual_C_and_inventory_refused_before_build(self):
        source=self.root/'source';source.mkdir()
        for head,tree,dirty in [('wrong',m.TREE,''),(m.CANDIDATE,'wrong',''),(m.CANDIDATE,m.TREE,' M changed')]:
            def git(root,*args):
                return head if args==('rev-parse','HEAD') else tree if args==('rev-parse','HEAD^{tree}') else dirty
            with patch.object(m,'git',side_effect=git),patch.object(m,'capture') as build:
                with self.assertRaises(ValueError):m.verify_candidate(source)
                build.assert_not_called()

    def test_H_checkout_drift_refused_before_history_or_launch(self):
        event=self.root/'event.json';event.write_text(json.dumps(self.event))
        with patch.dict(os.environ,{**self.env,'GITHUB_EVENT_PATH':str(event),'GITHUB_SHA':'H'},clear=True),\
             patch.object(m.platform,'system',return_value='Darwin'),patch.object(m.platform,'machine',return_value='arm64'),\
             patch.object(m,'git',return_value='different'),patch.object(m,'reconcile_admission') as api,patch.object(m.subprocess,'run') as launch:
            with self.assertRaises(ValueError):m.run_native_ci(self.root/'out')
            api.assert_not_called();launch.assert_not_called()

    def test_wrong_host_ref_or_m1b_cannot_enter(self):
        for key, value in (("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "fork/repo"),
                           ("GITHUB_REF", "refs/heads/main"), ("PULSAR_ADOPTION_PHASE", "m1b"),
                           ("PULSAR_ADOPTION_PHASE", ""), ("GITHUB_RUN_ATTEMPT", "2")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                m.require_route({**self.env, key: value}, self.event)

    def test_prior_run_or_new_id_does_not_reset_allowance(self):
        m.require_only_campaign([self.predecessor, self.run], "123", "controller", self.authority)
        for rows in ([], [self.run], [self.run, {**self.run, "id": 124}], [{**self.run, "id": 124}], [self.predecessor, {**self.run, "run_attempt": 2}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                m.require_only_campaign(rows, "123", "controller", self.authority)
        with self.assertRaises(ValueError):
            m.require_only_campaign([self.predecessor, self.run], "123", "wrong-controller", self.authority)

    def test_exact_pair_live_admission_preserves_failure_accounting(self):
        self.api["run"]["actor"] = {"login": "nonessential-profile-sentinel"}
        result = self.run_admission(allowed=True)
        admission = result["admission"]
        self.assertEqual(admission["designated_dispatches_cumulative"], 2)
        self.assertEqual(admission["additional_raw_probe_allowances"], 0)
        self.assertEqual(admission["raw_probe_allowed"], 1)
        self.assertEqual(admission["predecessor_raw_probe_used"], 0)
        self.assertEqual(admission["reconciliation_sha256"], m.RECONCILIATION_SHA)
        self.assertEqual(admission["fetched_evidence"]["observations"]["predecessor_run"]["conclusion"], "failure")
        self.assertNotIn("nonessential-profile-sentinel", json.dumps(result))
        for receipt in admission["fetched_evidence"]["fetches"]:
            self.assertEqual(receipt["raw_sha256"], m.digest(self.root / "campaign/admission-api.private" / receipt["retained_private"]))

    def test_missing_authority_refuses_before_checkout(self):
        with patch.object(m, "RECONCILIATION", str(self.root / "absent.json")):
            self.run_admission()

    def test_changed_authority_refuses_before_checkout(self):
        p = self.root / "authority.json"
        p.write_text(json.dumps({**self.authority, "additional_designated_dispatches": 5}))
        with patch.object(m, "RECONCILIATION", str(p)):
            self.run_admission()

    def test_singleton_current_refuses_before_checkout(self):
        self.api["runs"] = [self.run]
        self.run_admission()

    def test_third_manual_run_refuses_before_checkout(self):
        self.api["runs"].append({**self.run, "id": 124})
        self.run_admission()

    def test_current_attempt_two_refuses_before_checkout(self):
        self.api["runs"][1]["run_attempt"] = 2
        self.run_admission()

    def test_current_wrong_controller_refuses_before_checkout(self):
        self.api["runs"][1]["head_sha"] = "wrong"
        self.run_admission()

    def test_predecessor_later_attempt_refuses_before_checkout(self):
        self.api["run"]["run_attempt"] = 2
        self.run_admission()

    def test_predecessor_wrong_controller_refuses_before_checkout(self):
        self.api["run"]["head_sha"] = "wrong"
        self.run_admission()

    def test_predecessor_success_refuses_before_checkout(self):
        self.api["run"]["conclusion"] = "success"
        self.run_admission()

    def test_predecessor_wrong_job_refuses_before_checkout(self):
        self.native["id"] += 1
        self.run_admission()

    def test_executed_step_refuses_before_checkout(self):
        self.native["steps"] = [{"name": "Set up job", "status": "completed"}]
        self.run_admission()

    def test_nonzero_runner_refuses_before_checkout(self):
        self.native["runner_id"] = 1
        self.run_admission()

    def test_boolean_runner_is_not_zero_identity(self):
        self.native["runner_id"] = False
        self.run_admission()

    def test_artifacts_refuse_before_checkout(self):
        self.api["artifacts"] = [{"id": 42}]
        self.run_admission()

    def test_wrong_predecessor_tree_refuses_before_checkout(self):
        self.api["commit"]["tree"]["sha"] = "wrong"
        self.run_admission()

    def test_incomplete_history_refuses_before_checkout(self):
        self.api_override = lambda path, page: {"total_count": 2, "workflow_runs": [self.predecessor] if page == 1 else []} if path.endswith("macos.yml/runs") else None
        self.run_admission()

    def test_complete_two_page_history_admitted(self):
        self.api_override = lambda path, page: {"total_count": 2, "workflow_runs": [self.api["runs"][page - 1]]} if path.endswith("macos.yml/runs") else None
        self.run_admission(allowed=True)

    def test_duplicate_api_page_refuses_before_checkout(self):
        self.api_override = lambda path, page: {"total_count": 2, "workflow_runs": [self.predecessor]} if path.endswith("macos.yml/runs") else None
        self.run_admission()

    def test_fetch_failure_preserved_and_refused(self):
        def fail(path, page):
            if path.endswith("/artifacts"):
                raise urllib.error.URLError("test unavailable API")
        self.api_override = fail
        self.run_admission()
        evidence = json.loads((self.root / "campaign/admission-evidence.json").read_text())
        self.assertFalse(evidence["admitted"])
        self.assertEqual(evidence["fetches"][-1]["status"], "fetch_failed")

    def test_occupied_campaign_refuses_without_api_or_overwrite(self):
        self.run_admission(occupied=True)

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

    def test_relative_source_paths_survive_publication(self):
        text=json.dumps({'path':'experiments/packed-affine-adoption/src/bin/adoption-probe/main.rs',
                         'source':'/Users/test-owner/source/experiments/packed-affine-adoption/src/bin/grade-rust.rs'})
        value=json.loads(m.public_text(text,[('/Users/test-owner/source','<SOURCE>')]))
        self.assertEqual(value['path'],'experiments/packed-affine-adoption/src/bin/adoption-probe/main.rs')
        self.assertEqual(value['source'],'<SOURCE>/experiments/packed-affine-adoption/src/bin/grade-rust.rs')

    def test_failed_export_does_not_relaunch_or_erase_claims(self):
        root=self.root/'failed';root.mkdir();m.write_new(root/'campaign-claim.json',{'spent':True})
        m.write_new(root/'result.json',{'M1a_ran':False,'M1a_passed':False,'failure':'Bearer '+'test_sentinel'})
        with patch.object(m,'run_native_ci') as run,patch.object(m,'capture') as launch:
            with self.assertRaises(ValueError):m.export_public(root,self.root/'public')
            run.assert_not_called();launch.assert_not_called()
        self.assertTrue((root/'campaign-claim.json').exists())

    def test_absent_campaign_exports_truthful_no_execution(self):
        with patch.dict(os.environ,{'GITHUB_STEP_SUMMARY':str(self.root/'summary')}):
            m.export_public(self.root/'not-started',self.root/'public')
        result=json.loads((self.root/'public/export-outcome.json').read_text())
        self.assertFalse(result['M1a_ran']);self.assertFalse(result['M1a_passed'])

    def test_ambiguous_build_artifacts_refused(self):
        p = self.root / "cargo.jsonl"
        p.write_text(json.dumps({"reason": "build-finished", "success": True}) + "\n")
        with self.assertRaises(ValueError):
            m.executable(p, "adoption_parent")


if __name__ == "__main__":
    unittest.main()

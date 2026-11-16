"""Nonnumerical controls for the amended stage and CI evidence formats."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio017_operator as op
from studio017_guard import digest, put, sha


class DirectRecords(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        rows = self.root / "synthetic"
        rows.mkdir(mode=0o700)
        self.config = dict(schema="studio017-operator-config/1", mode=op.MODE,
                           source={"head": "1" * 40, "tree": "2" * 40}, artifacts={}, run="3" * 64)
        constants = {"RUN": self.config["run"], "STATE": rows}
        for key, constant in [("amendment", "AMENDMENT"), ("input", "INPUT"),
                              ("criteria", "CRITERIA"), ("resource", "RESOURCES")]:
            data = ("isolated unit fixture for " + key).encode()
            file = rows / key
            file.write_bytes(data)
            constants[constant] = sha(data)
            if key == "amendment":
                self.config["artifacts"]["operator-amendment"] = {"path": str(file), "sha256": sha(data)}
            else:
                self.config[key] = str(file)
        self.config["artifacts"]["operator-lifecycle"] = {"sha256": "4" * 64}
        mock = patch.multiple(op, **constants)
        mock.start()
        self.addCleanup(mock.stop)
        self.facts = dict(stage="reference", run=op.RUN, attempt="initial", source=self.config["source"],
                          revision=op.MODEL, input_sha256=op.INPUT, criteria_sha256=op.CRITERIA,
                          resource_sha256=op.RESOURCES, children=1, one_cold_input=True)

    def test_explicit_mode_source_role_and_frozen_binding(self):
        c = self.config
        with self.assertRaisesRegex(ValueError, "explicit operator"):
            op.validate_config({**c, "mode": "strict"})
        with self.assertRaisesRegex(ValueError, "role, source"):
            op.manifest(c, "native", self.facts)
        with self.assertRaisesRegex(ValueError, "role, source"):
            op.manifest(c, "reference", {**self.facts, "source": dict(head="5" * 40)})
        manifest = op.manifest(c, "reference", self.facts)
        put(op.manifest_path("reference"), manifest)
        self.assertEqual(op.verified_manifest(c, "reference", manifest)["sha256"],
                         digest(op.manifest_path("reference")))
        with self.assertRaises(FileExistsError):
            put(op.manifest_path("reference"), manifest)
        with self.assertRaisesRegex(ValueError, "differs from current"):
            op.verified_manifest(c, "reference", {**manifest, "children": 2})
        Path(c["criteria"]).write_bytes(b"altered in fixture")
        with self.assertRaisesRegex(ValueError, "changed frozen"):
            op.manifest(c, "reference", self.facts)

    def test_native_requires_the_exact_eligible_reference_hashes(self):
        facts = {**self.facts, "stage": "native"}
        with self.assertRaisesRegex(ValueError, "native needs"):
            op.manifest(self.config, "native", facts)
        golden = {name: sha(name.encode()) for name in
                  ("seal_sha256", "eligibility_sha256", "claim_sha256", "full_logits_sha256")}
        candidate = op.manifest(self.config, "native", facts, golden)
        put(op.manifest_path("native"), candidate)
        other = op.manifest(self.config, "native", facts, {**golden, "full_logits_sha256": "6" * 64})
        with self.assertRaisesRegex(ValueError, "differs from current"):
            op.verified_manifest(self.config, "native", other)
        with self.assertRaisesRegex(ValueError, "no golden input"):
            op.manifest(self.config, "reference", self.facts, golden)


class OriginalCI(unittest.TestCase):
    def test_capacity_annotation_cannot_mask_an_executed_test_failure(self):
        head = "f" * 40
        run = dict(id=1, head_sha=head, event="push", head_branch=op.BRANCH, path=op.WORKFLOW,
                   status="completed", conclusion="failure", run_attempt=1)
        native = dict(id=2, run_id=1, head_sha=head, name=op.REQUIRED_JOBS[2], run_attempt=1,
                      status="completed", conclusion="cancelled", runner_id=0, steps=[])
        aggregate = {**native, "id": 3, "name": op.REQUIRED_JOBS[3], "runner_id": 1, "conclusion": "failure",
                     "steps": [dict(name="Enforce selected mode result", conclusion="failure")]}
        listing = dict(total_count=2, jobs=[native, aggregate])
        notes = {"2": [dict(message="The job was not acquired by Runner of type hosted even after multiple attempts")]}
        self.assertEqual(op.summarize_infra(head, run, listing, notes), [2])
        with self.assertRaisesRegex(ValueError, "wrong ordinary"):
            op.summarize_infra("d" * 40, run, listing, notes)
        bad = deepcopy(listing)
        bad["jobs"][0].update(runner_id=1, conclusion="failure",
                              steps=[dict(name="Unit tests", conclusion="failure")])
        with self.assertRaisesRegex(ValueError, "infrastructure diagnosis"):
            op.summarize_infra(head, run, bad, notes)

    def test_rerun_may_reuse_a_successful_job_from_attempt_one(self):
        head = "a" * 40
        base = dict(id=1, head_sha=head, event="push", head_branch=op.BRANCH,
                    path=op.WORKFLOW, status="completed")
        runs = [{**base, "conclusion": status, "run_attempt": i + 1}
                for i, status in enumerate(["failure", "success"])]
        def job(number, index, name):
            return dict(id=number * 10 + index, run_attempt=number, run_id=1, head_sha=head, name=name,
                        runner_id=1, steps=[dict(name="Run test", conclusion="success")],
                        conclusion="success", status="completed")

        first = [job(1, i, name) for i, name in enumerate(op.REQUIRED_JOBS)]
        first[2].update(runner_id=0, steps=[], conclusion="cancelled")
        first[3].update(steps=[dict(name="Enforce selected mode result", conclusion="failure")],
                        conclusion="failure")
        second = [job(2, i, op.REQUIRED_JOBS[i]) for i in (2, 3)]
        with tempfile.TemporaryDirectory() as t:
            directory = Path(t).resolve()
            def save(name, data):
                p = directory / name
                put(p, data)
                return dict(path=str(p), sha256=digest(p))
            rows = []
            for n, (run, jobs) in enumerate(zip(runs, (first, second))):
                rows.append(dict(run=save("run-" + str(n), run), jobs=save("jobs-" + str(n),
                                 dict(total_count=len(jobs), jobs=jobs)), annotations={}, retry_intent=None))
            rows[0]["annotations"] = {str(first[2]["id"]): save("annotations", [dict(message="Capacity constraints")])}
            intent = op.retry_intent(head, rows[0]["run"], rows[0]["jobs"], rows[0]["annotations"], "8" * 32)
            rows[0]["retry_intent"] = save("intent", intent)
            def config(key):
                return {"source": {"head": head}, "artifacts": {"ci-attempts": save(key, dict(
                        schema="studio017-operator-ci/1", attempts=rows))}}
            op.validate_ci(config("chain"), runs[1])
            rows[0]["retry_intent"] = save("changed-intent", {**intent, "run_id": 88})
            with self.assertRaisesRegex(ValueError, "retry authorization"):
                op.validate_ci(config("bad-chain"), runs[1])


if __name__ == "__main__":
    unittest.main()

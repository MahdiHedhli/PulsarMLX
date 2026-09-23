"""Mixed code+evidence ranges: routing, evidence-subset validation, aggregate.

Every range here is a real commit range in a temporary Git repository.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from scripts.ci.aggregate_status_v1 import KEYS, AggregateFailure, decide, main as aggregate_main
from scripts.ci.classify_ci_change import (
    DOCS_ONLY, EVIDENCE_ONLY, FULL_NATIVE, UNKNOWN_DEFAULT_FULL,
    classify_change, evidence_touched, main as classify_main,
)
from scripts.ci.validate_evidence_change import ValidationError, validate_change

EVIDENCE = "docs/architecture/reviews/evidence/"
HISTORICAL = EVIDENCE + "historical-result-v1.json"
CODE = "crates/demo/src/lib.rs"


class MixedRangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "CI Test")
        self.git("config", "user.email", "ci@example.invalid")
        self.put("README.md", "authority\n")
        self.put(CODE, "pub fn a() {}\n")
        self.put(HISTORICAL, '{"schema":"historical/1.0.0"}\n')
        self.base = self.commit("base")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True,
                                       stderr=subprocess.PIPE).strip()

    def put(self, path, body):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        self.git("add", "--", path)

    def commit(self, message="change"):
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def code_change(self, body="pub fn b() {}\n"):
        self.put(CODE, body)

    def route(self, head, base=None):
        base = base or self.base
        return (classify_change(self.root, base, head, branch="feat/test")[0],
                evidence_touched(self.root, base, head))

    def mixed(self, head, base=None, **kwargs):
        return validate_change(self.root, base=base or self.base, head=head,
                               branch="feat/test", run_attempt1=False, mixed_range=True, **kwargs)

    # 1. allowed code + allowed NEW evidence
    def test_code_plus_new_evidence_passes_every_leg(self):
        self.code_change()
        self.put(EVIDENCE + "new-result-v1.json", '{"schema":"new/1.0.0"}\n')
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, True))
        result = self.mixed(head)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["evidence_file_count"], 1)
        self.assertEqual(result["changed_file_count"], 1)
        self.assertEqual(result["range_scope"], "EVIDENCE_SUBSET_OF_MIXED_RANGE")
        self.assertEqual(result["ignored_non_evidence_row_count"], 1)
        # The strict evidence-only path still refuses a native-routed range.
        with self.assertRaises(ValidationError):
            validate_change(self.root, base=self.base, head=head, branch="feat/test",
                            run_attempt1=False)
        self.assertIn("selected_mode=FULL_NATIVE", decide(dict(
            MODE=FULL_NATIVE, EVIDENCE_TOUCHED="true", CLASSIFY_RESULT="success",
            EVIDENCE_RESULT="success", DOCS_RESULT="skipped", GUARD_RESULT="skipped",
            BASELINE_RESULT="success", NATIVE_RESULT="success")))

    def test_non_evidence_paths_are_not_refused_in_mixed_mode(self):
        # Trailing whitespace, a code rename and a documentation edit are native
        # CI's to judge; only the evidence subset is validated here.
        self.put(CODE, "pub fn b() {}   \n")
        self.git("mv", CODE, "crates/demo/src/other.rs")
        self.put("docs/guide.md", "guide\n")
        self.put(EVIDENCE + "new-result-v1.json", "{}\n")
        head = self.commit()
        self.assertEqual(self.mixed(head)["evidence_file_count"], 1)

    def test_mixed_new_evidence_still_gets_content_checks(self):
        for name, body in (("dup.json", '{"a":1,"a":2}\n'),
                           ("bind.json", json.dumps({"path": "missing.json", "sha256": "0" * 64}) + "\n"),
                           ("key.md", "-----BEGIN PRIVATE KEY-----\n"),
                           ("ws.md", "trailing   \n")):
            with self.subTest(name=name):
                self.git("reset", "-q", "--hard", self.base)
                self.code_change()
                self.put(EVIDENCE + name, body)
                head = self.commit()
                with self.assertRaises(ValidationError):
                    self.mixed(head)

    def test_mixed_new_evidence_must_be_regular_non_executable(self):
        self.code_change()
        self.put(EVIDENCE + "exec.json", "{}\n")
        (self.root / EVIDENCE / "exec.json").chmod(0o755)
        self.git("add", "--", EVIDENCE + "exec.json")
        head = self.commit()
        with self.assertRaises(ValidationError):
            self.mixed(head)

    # 2. code + unauthorized edit of historical evidence
    def test_code_plus_historical_edit_fails(self):
        self.code_change()
        self.put(HISTORICAL, '{"schema":"historical/2.0.0"}\n')
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, True))
        with self.assertRaises(ValidationError):
            self.mixed(head)

    def test_code_plus_historical_mode_change_fails(self):
        self.code_change()
        (self.root / HISTORICAL).chmod(0o755)
        self.git("add", "--", HISTORICAL)
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, True))
        with self.assertRaises(ValidationError):
            self.mixed(head)

    # 3. deletions and renames
    def test_code_plus_deletion_fails(self):
        self.code_change()
        self.git("rm", "-q", HISTORICAL)
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, True))
        with self.assertRaisesRegex(ValidationError, "append-only"):
            self.mixed(head)

    def test_code_plus_pure_rename_fails(self):
        self.code_change()
        self.git("mv", HISTORICAL, EVIDENCE + "renamed-v1.json")
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, True))
        with self.assertRaises(ValidationError):
            self.mixed(head)

    def test_code_plus_rename_and_edit_fails(self):
        self.code_change()
        self.git("mv", HISTORICAL, EVIDENCE + "renamed-v1.json")
        self.put(EVIDENCE + "renamed-v1.json", '{"schema":"historical/1.0.0","x":1}\n')
        head = self.commit()
        with self.assertRaises(ValidationError):
            self.mixed(head)

    def test_rename_out_of_and_into_evidence_root_fails(self):
        # Each alongside a legitimate new record, so the refusal is the rename's.
        self.git("mv", HISTORICAL, "crates/demo/historical-result-v1.json")
        self.put(EVIDENCE + "legit-a-v1.json", "{}\n")
        out = self.commit()
        self.assertEqual(self.route(out), (FULL_NATIVE, True))
        with self.assertRaisesRegex(ValidationError, "renames/copies prohibited"):
            self.mixed(out)
        self.git("mv", "crates/demo/historical-result-v1.json", EVIDENCE + "back-v1.json")
        self.put(EVIDENCE + "legit-b-v1.json", "{}\n")
        back = self.commit()
        self.assertEqual(self.route(back, base=out), (FULL_NATIVE, True))
        with self.assertRaisesRegex(ValidationError, "renames/copies prohibited"):
            self.mixed(back, base=out)

    def test_deletion_hidden_among_many_code_changes_fails(self):
        for index in range(80):
            self.put(f"crates/demo/src/m{index:02d}.rs", f"pub fn f{index}() {{}}\n")
        self.git("rm", "-q", HISTORICAL)
        self.put(EVIDENCE + "decoy-new-v1.json", "{}\n")
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, True))
        with self.assertRaisesRegex(ValidationError, "append-only"):
            self.mixed(head)

    def test_deletion_in_an_earlier_commit_of_the_range_fails(self):
        self.git("rm", "-q", HISTORICAL)
        self.commit("delete")
        self.code_change()
        self.put(EVIDENCE + "new-result-v1.json", "{}\n")
        head = self.commit("tip adds evidence")
        with self.assertRaises(ValidationError):
            self.mixed(head)

    def test_unpinned_binding_superseded_later_in_the_range_fails(self):
        # The existing rule, unchanged: a binding without a commit resolves at
        # the range head, so a record whose bound file changes later in the
        # same range no longer verifies. Pinning the commit is the compliant form.
        import hashlib
        manifest = "fixtures/demo/manifest.json"
        self.put(manifest, '{"v":1}\n')
        first = self.commit("manifest v1")
        digest = hashlib.sha256(b'{"v":1}\n').hexdigest()
        self.put(EVIDENCE + "unpinned-v1.json",
                 json.dumps({"manifest_path": manifest, "manifest_sha256": digest}) + "\n")
        self.put(EVIDENCE + "pinned-v1.json", json.dumps(
            {"manifest_path": manifest, "manifest_sha256": digest, "manifest_commit": first}) + "\n")
        recorded = self.commit("records")
        self.assertEqual(self.mixed(recorded)["resolved_binding_count"], 2)
        self.put(manifest, '{"v":2}\n')
        self.code_change()
        head = self.commit("manifest v2")
        with self.assertRaisesRegex(ValidationError, "bound SHA mismatch: " + head):
            self.mixed(head)
        self.git("rm", "-q", "--cached", EVIDENCE + "unpinned-v1.json")
        pinned_only = self.commit("drop the unpinned record from a fresh history")
        self.assertEqual(self.mixed(pinned_only)["resolved_binding_count"], 1)

    def test_mixed_mode_requires_evidence_and_a_valid_range(self):
        self.code_change()
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, False))
        with self.assertRaisesRegex(ValidationError, "requires changed evidence"):
            self.mixed(head)
        with self.assertRaises(subprocess.CalledProcessError):
            self.mixed(head, base="unavailable-ref")

    def test_mixed_flag_on_evidence_only_range_keeps_whole_strict_validation(self):
        # A manual `full` dispatch of an evidence+docs range is FULL_NATIVE to the
        # workflow but EVIDENCE_ONLY to auto classification: docs stay validated.
        self.put("README.md", "-----BEGIN PRIVATE KEY-----\n")
        self.put(EVIDENCE + "new-result-v1.json", "{}\n")
        head = self.commit()
        self.assertEqual(self.route(head), (EVIDENCE_ONLY, True))
        with self.assertRaises(ValidationError):
            self.mixed(head)
        self.put("README.md", "clean\n")
        clean = self.commit()
        result = self.mixed(clean)
        self.assertEqual(result["range_scope"], "WHOLE_EVIDENCE_ONLY_RANGE")
        self.assertEqual(result["documentation_file_count"], 1)

    def test_unknown_default_full_with_evidence_is_touched(self):
        self.put("mystery.bin", "x\n")
        self.put(EVIDENCE + "new-result-v1.json", "{}\n")
        head = self.commit()
        self.assertEqual(self.route(head), (UNKNOWN_DEFAULT_FULL, True))
        self.assertEqual(self.mixed(head)["mode"], UNKNOWN_DEFAULT_FULL)

    # 5/6. evidence-only and docs-only ranges keep their outputs
    def test_evidence_only_and_docs_only_unchanged(self):
        self.put(EVIDENCE + "new-result-v1.json", "{}\n")
        evidence_head = self.commit()
        self.assertEqual(self.route(evidence_head), (EVIDENCE_ONLY, True))
        strict = validate_change(self.root, base=self.base, head=evidence_head,
                                 branch="feat/test", run_attempt1=False)
        self.assertNotIn("range_scope", strict)
        self.assertEqual(strict["mode"], EVIDENCE_ONLY)
        self.put("docs/guide.md", "guide\n")
        docs_head = self.commit()
        self.assertEqual(self.route(docs_head, base=evidence_head), (DOCS_ONLY, False))
        docs = validate_change(self.root, base=evidence_head, head=docs_head,
                               branch="feat/test", run_attempt1=False)
        self.assertEqual((docs["mode"], docs["evidence_file_count"]), (DOCS_ONLY, 0))

    def test_classifier_cli_emits_evidence_touched(self):
        self.code_change()
        self.put(EVIDENCE + "new-result-v1.json", "{}\n")
        head = self.commit()
        output = self.root.parent / (self.root.name + "-github-output")
        self.addCleanup(lambda: output.unlink(missing_ok=True))
        record = self.root.parent / (self.root.name + "-classification.json")
        self.addCleanup(lambda: record.unlink(missing_ok=True))
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            classify_main(["--repository", str(self.root), "--base", self.base, "--head", head,
                           "--branch", "feat/test", "--github-output", str(output),
                           "--output-json", str(record)])
        lines = output.read_text().splitlines()
        self.assertIn("mode=FULL_NATIVE", lines)
        self.assertIn("evidence_touched=true", lines)
        self.assertIs(json.loads(record.read_text())["evidence_touched"], True)


# The aggregate's inline shell as it stood before it was factored out, verbatim.
LEGACY_AGGREGATE = r'''
          set -euo pipefail
          test "$CLASSIFY_RESULT" = success
          case "$MODE" in
            FULL_NATIVE)
              test "$BASELINE_RESULT" = success
              test "$NATIVE_RESULT" = success
              ;;
            EVIDENCE_ONLY)
              test "$EVIDENCE_RESULT" = success
              test "$BASELINE_RESULT" = skipped
              test "$NATIVE_RESULT" = skipped
              ;;
            DOCS_ONLY)
              test "$DOCS_RESULT" = success
              test "$BASELINE_RESULT" = skipped
              test "$NATIVE_RESULT" = skipped
              ;;
            NO_CHANGES)
              test "$BASELINE_RESULT" = skipped
              test "$NATIVE_RESULT" = skipped
              ;;
            CLOSED_BRANCH_GUARD)
              test "$GUARD_RESULT" = failure
              echo 'Closed-branch guard correctly refused automatic implementation qualification.'
              exit 1
              ;;
            UNKNOWN_DEFAULT_FULL)
              test "$BASELINE_RESULT" = success
              test "$NATIVE_RESULT" = success
              ;;
            *)
              echo "Unknown CI mode: $MODE" >&2
              exit 1
              ;;
          esac
          printf 'selected_mode=%s\n' "$MODE"
'''
MODES = ("FULL_NATIVE", "UNKNOWN_DEFAULT_FULL", "EVIDENCE_ONLY", "DOCS_ONLY", "NO_CHANGES",
         "CLOSED_BRANCH_GUARD", "BOGUS", "")
# The legacy shell distinguishes only success, skipped and failure; every other
# value behaves like a mismatch. The integrity result, which the new rule reads,
# also takes cancelled and absent.
RESULTS = ("success", "failure", "skipped")
JOB_KEYS = ("EVIDENCE_RESULT", "DOCS_RESULT", "GUARD_RESULT", "BASELINE_RESULT", "NATIVE_RESULT")
JOB_VALUES = (RESULTS + ("cancelled", ""),) + (RESULTS,) * (len(JOB_KEYS) - 1)


def _accepts(values):
    try:
        decide(values)
    except AggregateFailure:
        return False
    return True


class AggregateDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Evaluate the legacy shell once, over the whole result product, in one bash.
        cls.combos = [dict(zip(("MODE", "CLASSIFY_RESULT", *JOB_KEYS), row)) for row in
                      itertools.product(MODES, ("success", "failure"), *JOB_VALUES)]
        # The subshell must not sit in an && / || list: bash ignores `set -e` there.
        body = "legacy() {\n(\n" + LEGACY_AGGREGATE + "\n) >/dev/null 2>&1\necho $?\n}\n"
        script = [body, "while IFS=, read -r MODE CLASSIFY_RESULT " + " ".join(JOB_KEYS) + "; do",
                  "  export MODE CLASSIFY_RESULT " + " ".join(JOB_KEYS) + "; legacy", "done"]
        rows = "\n".join(",".join(c[k] for k in ("MODE", "CLASSIFY_RESULT", *JOB_KEYS))
                         for c in cls.combos) + "\n"
        out = subprocess.run(["bash", "-c", "\n".join(script)], input=rows, text=True,
                             capture_output=True, check=True).stdout.split()
        assert len(out) == len(cls.combos)
        assert set(out) <= {"0", "1"}, set(out)
        cls.legacy = [flag == "0" for flag in out]

    def test_untouched_evidence_is_identical_to_the_legacy_shell(self):
        self.assertGreater(sum(self.legacy), 0)
        for combo, legacy in zip(self.combos, self.legacy):
            self.assertEqual(_accepts(dict(combo, EVIDENCE_TOUCHED="false")), legacy, combo)

    def test_touched_evidence_is_legacy_plus_required_integrity_success(self):
        for combo, legacy in zip(self.combos, self.legacy):
            expected = legacy and combo["EVIDENCE_RESULT"] == "success"
            self.assertEqual(_accepts(dict(combo, EVIDENCE_TOUCHED="true")), expected, combo)

    def test_native_success_cannot_mask_unsuccessful_integrity(self):
        for mode in ("FULL_NATIVE", "UNKNOWN_DEFAULT_FULL"):
            for evidence in ("skipped", "cancelled", "failure", ""):
                with self.subTest(mode=mode, evidence=evidence):
                    with self.assertRaisesRegex(AggregateFailure, "EVIDENCE_RESULT"):
                        decide(dict(MODE=mode, EVIDENCE_TOUCHED="true", CLASSIFY_RESULT="success",
                                    EVIDENCE_RESULT=evidence, BASELINE_RESULT="success",
                                    NATIVE_RESULT="success"))
            absent = dict(MODE=mode, EVIDENCE_TOUCHED="true", CLASSIFY_RESULT="success",
                          BASELINE_RESULT="success", NATIVE_RESULT="success")
            with self.assertRaises(AggregateFailure):
                decide(absent)
            self.assertTrue(_accepts(dict(absent, EVIDENCE_TOUCHED="false",
                                          EVIDENCE_RESULT="skipped")))

    def test_missing_or_malformed_evidence_touched_fails_closed(self):
        good = dict(MODE="FULL_NATIVE", CLASSIFY_RESULT="success", EVIDENCE_RESULT="skipped",
                    BASELINE_RESULT="success", NATIVE_RESULT="success")
        for touched in ("", "True", "1", "yes", None):
            values = dict(good) if touched is None else dict(good, EVIDENCE_TOUCHED=touched)
            with self.subTest(touched=touched), self.assertRaises(AggregateFailure):
                decide(values)

    def test_entry_point_exit_codes(self):
        import contextlib, io
        env = dict(MODE="FULL_NATIVE", EVIDENCE_TOUCHED="true", CLASSIFY_RESULT="success",
                   EVIDENCE_RESULT="skipped", BASELINE_RESULT="success", NATIVE_RESULT="success")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(aggregate_main(env), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aggregate_main(dict(env, EVIDENCE_RESULT="success")), 0)


class WorkflowWiringTests(unittest.TestCase):
    def setUp(self):
        self.text = (Path(__file__).resolve().parents[3] / ".github/workflows/macos.yml").read_text()

    def job(self, name):
        return re.split(r"\n  (?=\S)", self.text.split("\n  " + name + ":", 1)[1], maxsplit=1)[0]

    def test_classifier_output_and_integrity_condition(self):
        self.assertIn("      evidence_touched: ${{ steps.route.outputs.evidence_touched }}\n",
                      self.job("classify"))
        integrity = self.job("evidence-integrity")
        self.assertIn("    if: needs.classify.outputs.mode == 'EVIDENCE_ONLY' || "
                      "needs.classify.outputs.evidence_touched == 'true'\n", integrity)
        self.assertIn("BASE_SHA: ${{ needs.classify.outputs.base }}", integrity)
        self.assertIn("HEAD_SHA: ${{ needs.classify.outputs.head }}", integrity)
        self.assertIn("MODE: ${{ needs.classify.outputs.mode }}", integrity)
        self.assertIn('if test "$MODE" != EVIDENCE_ONLY; then\n            RANGE_FLAG=--mixed-range',
                      integrity)
        self.assertIn("$ATTEMPT_FLAG $RANGE_FLAG", integrity)

    def test_aggregate_calls_the_tested_decision_with_every_input(self):
        aggregate = self.job("aggregate")
        self.assertIn("    if: always()\n", aggregate)
        self.assertIn("python3 -I -B scripts/ci/aggregate_status_v1.py", aggregate)
        self.assertNotIn("case \"$MODE\"", aggregate)
        for key in KEYS:
            self.assertEqual(len(re.findall(r"\n          " + key + r": \$\{\{ needs\.", aggregate)),
                             1, key)
        self.assertIn("EVIDENCE_TOUCHED: ${{ needs.classify.outputs.evidence_touched }}", aggregate)
        self.assertIn("EVIDENCE_RESULT: ${{ needs.evidence-integrity.result }}", aggregate)


if __name__ == "__main__":
    unittest.main()

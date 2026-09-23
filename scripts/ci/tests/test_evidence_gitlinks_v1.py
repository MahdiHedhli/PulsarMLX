"""Committed gitlinks cannot hide from, or pass through, evidence integrity.

Git honours submodule ignore settings in diffs, including a repository-controlled
`.gitmodules` `ignore = all`. Every range here commits real 160000 gitlinks in a
temporary repository and reads it through the production enumeration.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.ci.classify_ci_change import (
    DOCS_ONLY, EVIDENCE_ONLY, FULL_NATIVE, UNKNOWN_DEFAULT_FULL,
    changed_entries, classify_change, evidence_touched,
)
from scripts.ci.validate_evidence_change import ValidationError, validate_change

EVIDENCE = "docs/architecture/reviews/evidence/"
LINK = EVIDENCE + "linked"
OUTSIDE = "crates/vendor/linked"
CODE = "crates/demo/src/lib.rs"


class GitlinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        top = Path(self.temp.name)
        self.sub = top / "sub"
        self.root = top / "main"
        self.sub.mkdir()
        self.root.mkdir()
        for repo in (self.sub, self.root):
            self.run_git(repo, "init", "-q")
            self.run_git(repo, "config", "user.name", "CI Test")
            self.run_git(repo, "config", "user.email", "ci@example.invalid")
        self.sub_commits = []
        for index in range(2):
            self.run_git(self.sub, "commit", "-q", "--allow-empty", "-m", f"sub {index}")
            self.sub_commits.append(self.run_git(self.sub, "rev-parse", "HEAD"))
        self.put("README.md", "authority\n")
        self.put(CODE, "pub fn a() {}\n")
        self.put(EVIDENCE + "historical-v1.json", "{}\n")
        self.base = self.commit("base")

    @staticmethod
    def run_git(cwd, *args):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True,
                                       stderr=subprocess.PIPE).strip()

    def git(self, *args):
        return self.run_git(self.root, *args)

    def put(self, path, body):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        self.git("add", "--", path)

    def gitmodules(self, path, ignore):
        self.put(".gitmodules",
                 f'[submodule "linked"]\n\tpath = {path}\n\turl = ./sub\n\tignore = {ignore}\n')

    def gitlink(self, path, index=0):
        self.git("update-index", "--add", "--cacheinfo",
                 f"160000,{self.sub_commits[index]},{path}")

    def commit(self, message="change"):
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def route(self, head, base=None):
        base = base or self.base
        return (classify_change(self.root, base, head, branch="feat/test")[0],
                evidence_touched(self.root, base, head))

    def validate(self, head, base=None, mixed=True):
        return validate_change(self.root, base=base or self.base, head=head, branch="feat/test",
                               run_attempt1=False, mixed_range=mixed)

    def test_evidence_gitlink_with_code_is_touched_and_refused(self):
        for ignore in ("all", "dirty"):
            with self.subTest(ignore=ignore):
                self.git("reset", "-q", "--hard", self.base)
                self.gitmodules(LINK, ignore)
                self.put(CODE, "pub fn b() {}\n")
                self.gitlink(LINK)
                head = self.commit()
                modes = {row["new_mode"] for row in changed_entries(self.root, self.base, head)
                         if row["paths"] == [LINK]}
                self.assertEqual(modes, {"160000"})
                self.assertEqual(self.route(head), (FULL_NATIVE, True))
                with self.assertRaisesRegex(ValidationError, "gitlink prohibited"):
                    self.validate(head)

    def test_legitimate_evidence_cannot_carry_a_hidden_gitlink(self):
        # Integrity runs because of a real new record; the gitlink beside it
        # must still be enumerated and refused by the shared subset reader.
        self.gitmodules(LINK, "all")
        self.put(CODE, "pub fn b() {}\n")
        self.put(EVIDENCE + "new-v1.json", "{}\n")
        self.gitlink(LINK)
        head = self.commit()
        with self.assertRaisesRegex(ValidationError, "gitlink prohibited"):
            self.validate(head)

    def test_gitlink_only_evidence_range_is_not_no_changes(self):
        self.gitmodules(LINK, "all")
        configured = self.commit("configure the ignore first")
        self.gitlink(LINK)
        head = self.commit("add only the gitlink")
        self.assertEqual(self.route(head, base=configured), (EVIDENCE_ONLY, True))
        with self.assertRaisesRegex(ValidationError, "gitlink prohibited"):
            self.validate(head, base=configured, mixed=False)

    def test_evidence_gitlink_update_and_type_changes_are_refused(self):
        self.gitmodules(LINK, "all")
        self.gitlink(LINK)
        linked = self.commit("gitlink present")
        self.gitlink(LINK, index=1)
        moved = self.commit("gitlink moved")
        self.assertEqual(self.route(moved, base=linked), (EVIDENCE_ONLY, True))
        with self.assertRaisesRegex(ValidationError, "gitlink prohibited"):
            self.validate(moved, base=linked, mixed=False)
        record = EVIDENCE + "historical-v1.json"
        self.git("rm", "-q", "--cached", record)
        self.gitlink(record)
        swapped = self.commit("regular record replaced by a gitlink")
        self.assertEqual(self.route(swapped, base=moved)[1], True)
        with self.assertRaisesRegex(ValidationError, "gitlink prohibited"):
            self.validate(swapped, base=moved, mixed=False)

    def test_gitlink_outside_evidence_keeps_native_routing(self):
        # Not evidence: it neither triggers nor fails evidence integrity, and it
        # never gets a cheap route -- it is native CI's to qualify.
        self.gitmodules(OUTSIDE, "all")
        self.put(CODE, "pub fn b() {}\n")
        self.gitlink(OUTSIDE)
        head = self.commit()
        self.assertEqual(self.route(head), (FULL_NATIVE, False))
        self.put(EVIDENCE + "new-v1.json", "{}\n")
        with_record = self.commit()
        self.assertEqual(self.route(with_record), (FULL_NATIVE, True))
        self.assertEqual(self.validate(with_record)["evidence_file_count"], 1)

    def test_gitlink_only_outside_evidence_routes_native_not_no_changes(self):
        for path, expected in ((OUTSIDE, FULL_NATIVE), ("docs/linked.md", FULL_NATIVE),
                               ("vendor/linked", UNKNOWN_DEFAULT_FULL)):
            with self.subTest(path=path):
                self.git("reset", "-q", "--hard", self.base)
                self.gitmodules(path, "all")
                configured = self.commit("configure")
                self.gitlink(path)
                head = self.commit("gitlink only")
                self.assertEqual(self.route(head, base=configured), (expected, False))
                self.assertNotEqual(expected, DOCS_ONLY)


if __name__ == "__main__":
    unittest.main()

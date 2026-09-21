from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import tempfile
import re

from scripts.ci.classify_ci_change import (
    CLOSED_BRANCH,
    CLOSED_BRANCH_GUARD,
    DOCS_ONLY,
    EVIDENCE_ONLY,
    FULL_NATIVE,
    NO_CHANGES,
    UNKNOWN_DEFAULT_FULL,
    ClassificationError,
    classify_paths,
    classify_change,
    changed_paths,
)


NATIVE_BRANCH = "feat/017-rust-native-inference-runtime"


class ClassificationTests(unittest.TestCase):
    def classify(self, paths, branch=NATIVE_BRANCH, requested_mode="auto"):
        return classify_paths(paths, branch=branch, requested_mode=requested_mode)[0]

    def test_evidence_json_only(self):
        self.assertEqual(
            self.classify(["docs/architecture/reviews/evidence/new-result.json"]),
            EVIDENCE_ONLY,
        )

    def test_review_markdown_only(self):
        self.assertEqual(
            self.classify(["docs/architecture/reviews/evidence/cycle-request.md"]),
            EVIDENCE_ONLY,
        )

    def test_rust_source_only(self):
        self.assertEqual(self.classify(["crates/stream/src/lib.rs"]), FULL_NATIVE)

    def test_python_source_only(self):
        self.assertEqual(self.classify(["python/pulsar/runtime.py"]), FULL_NATIVE)

    def test_workflow_only(self):
        self.assertEqual(self.classify([".github/workflows/macos.yml"]), FULL_NATIVE)

    def test_contract_under_specs(self):
        self.assertEqual(
            self.classify(["specs/017-rust-native-inference-runtime/contracts/a.json"]),
            FULL_NATIVE,
        )

    def test_fixture_change(self):
        self.assertEqual(self.classify(["fixtures/mlx/manifest.json"]), FULL_NATIVE)

    def test_evidence_plus_source_is_full(self):
        self.assertEqual(
            self.classify(
                [
                    "docs/architecture/reviews/evidence/result.json",
                    "crates/stream/src/lib.rs",
                ]
            ),
            FULL_NATIVE,
        )

    def test_evidence_plus_docs_uses_integrity(self):
        self.assertEqual(
            self.classify(
                ["docs/architecture/reviews/evidence/result.json", "docs/guide.md"]
            ),
            EVIDENCE_ONLY,
        )

    def test_unknown_defaults_full(self):
        self.assertEqual(self.classify(["mystery.bin"]), UNKNOWN_DEFAULT_FULL)

    def test_no_changes(self):
        self.assertEqual(self.classify([]), NO_CHANGES)

    def test_docs_only(self):
        self.assertEqual(self.classify(["docs/guide.md"]), DOCS_ONLY)

    def test_closed_branch_evidence(self):
        self.assertEqual(
            self.classify(
                ["docs/architecture/reviews/evidence/result.json"], branch=CLOSED_BRANCH
            ),
            EVIDENCE_ONLY,
        )

    def test_closed_branch_source_mutation(self):
        self.assertEqual(
            self.classify(["crates/stream/src/lib.rs"], branch=CLOSED_BRANCH),
            CLOSED_BRANCH_GUARD,
        )

    def test_closed_branch_mixed_cheap_surface(self):
        self.assertEqual(self.classify(["docs/guide.md", "docs/architecture/reviews/evidence/a.json"],
                                       branch=CLOSED_BRANCH), EVIDENCE_ONLY)

    def test_dispatch_auto(self):
        self.assertEqual(
            self.classify(["docs/architecture/reviews/evidence/result.json"]),
            EVIDENCE_ONLY,
        )

    def test_dispatch_full(self):
        self.assertEqual(
            self.classify(
                ["docs/architecture/reviews/evidence/result.json"], requested_mode="full"
            ),
            FULL_NATIVE,
        )

    def test_dispatch_evidence(self):
        self.assertEqual(
            self.classify(
                ["docs/architecture/reviews/evidence/result.json"],
                requested_mode="evidence",
            ),
            EVIDENCE_ONLY,
        )

    def test_dispatch_evidence_cannot_mask_code(self):
        with self.assertRaises(ClassificationError):
            self.classify(["crates/stream/src/lib.rs"], requested_mode="evidence")

    def test_noncanonical_paths_fail_closed(self):
        for path in ("docs//x.md", "docs/./x.md", "../x", "/docs/x.md", "docs/x\ny.md", "docs/x\\y.md"):
            with self.subTest(path=path), self.assertRaises(ClassificationError):
                self.classify([path])


class CommittedDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "CI Test")
        self.git("config", "user.email", "ci@example.invalid")
        self.base = self.write("README.md", "base\n")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def commit(self, *paths):
        self.git("add", "--", *paths)
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def write(self, path, body):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        return self.commit(path)

    def mode(self, head, base=None, **kwargs):
        return classify_change(self.root, base or self.base, head,
                               branch=kwargs.pop("branch", "feat/test"), **kwargs)[0]

    def test_complete_multicommit_push_not_documentation_tip(self):
        source = self.write("scripts/research/x.py", "x = 1\n")
        head = self.write("docs/x.md", "guide\n")
        self.assertEqual(self.mode(head), FULL_NATIVE)
        self.assertEqual(self.mode(head, base=source), DOCS_ONLY)
        with self.assertRaises(ClassificationError):
            self.mode(head, requested_mode="evidence")
        self.assertEqual(self.mode(head, branch=CLOSED_BRANCH), CLOSED_BRANCH_GUARD)

    def test_new_branch_merge_base_covers_all_commits(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.write("python/source.py", "x = 1\n")
        head = self.write("docs/tip.md", "tip\n")
        base = self.git("merge-base", head, "origin/main")
        self.assertEqual(base, self.base)
        self.assertEqual(self.mode(head, base=base), FULL_NATIVE)
        with self.assertRaises(ClassificationError):
            self.mode(head, base="0" * 40)
        with self.assertRaises(subprocess.CalledProcessError):
            self.mode(head, base="unavailable-ref")

    def test_rename_both_source_sides(self):
        first = self.write("docs/example.md", "preserved exact content\n")
        (self.root / "python").mkdir()
        self.git("mv", "docs/example.md", "python/example.py")
        self.git("commit", "-qm", "rename into source")
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(changed_paths(self.root, first, head), ["docs/example.md", "python/example.py"])
        self.assertEqual(self.mode(head, base=first), FULL_NATIVE)
        self.git("mv", "python/example.py", "docs/example.md")
        self.git("commit", "-qm", "rename out of source")
        back = self.git("rev-parse", "HEAD")
        self.assertEqual(self.mode(back, base=head), FULL_NATIVE)

    def test_document_modes_do_not_get_cheap_pass(self):
        (self.root / "README.md").chmod(0o755)
        head = self.commit("README.md")
        self.assertEqual(self.mode(head), FULL_NATIVE)
        self.assertEqual(self.mode(head, branch=CLOSED_BRANCH), CLOSED_BRANCH_GUARD)
        (self.root / "docs").mkdir()
        (self.root / "docs/link.md").symlink_to("../README.md")
        link = self.commit("docs/link.md")
        self.assertEqual(self.mode(link, base=head), FULL_NATIVE)

    def test_unknown_and_evidence_modes(self):
        head = self.write("unknown.dat", "unknown\n")
        self.assertEqual(self.mode(head), UNKNOWN_DEFAULT_FULL)
        evidence = "docs/architecture/reviews/evidence/result.json"
        added = self.write(evidence, "{}\n")
        (self.root / evidence).chmod(0o755)
        changed = self.commit(evidence)
        self.assertEqual(self.mode(changed, base=added), EVIDENCE_ONLY)

    def test_workflow_routes_contract(self):
        text = (Path(__file__).resolve().parents[3] / ".github/workflows/macos.yml").read_text()
        self.assertIn('BASE_SHA="$(git merge-base HEAD "origin/${DEFAULT_BRANCH:-main}")"', text)
        self.assertNotIn("git rev-list --max-parents=0", text)
        self.assertIn('BASE_SHA="$EVENT_BEFORE"', text)
        self.assertIn('BASE_SHA="$PR_BASE_SHA"', text)
        self.assertEqual(text.count("python3 -m scripts.ci.validate_evidence_change"), 2)
        for job, mode in (("evidence-integrity", EVIDENCE_ONLY), ("documentation", DOCS_ONLY)):
            block = re.split(r"\n  (?=\S)", text.split("\n  " + job + ":", 1)[1], maxsplit=1)[0]
            self.assertIn("runs-on: ubuntu-latest", block)
            self.assertIn("if: needs.classify.outputs.mode == '" + mode + "'", block)
        for job in ("macos-15-arm64", "apple-mlx-small-fixtures"):
            block = re.split(r"\n  (?=\S)", text.split("\n  " + job + ":", 1)[1], maxsplit=1)[0]
            self.assertIn("if: needs.classify.outputs.mode == 'FULL_NATIVE' || needs.classify.outputs.mode == 'UNKNOWN_DEFAULT_FULL'", block)
        for mode in (EVIDENCE_ONLY, DOCS_ONLY):
            block = text.split("            " + mode + ")", 1)[1].split(";;", 1)[0]
            self.assertIn('test "$BASELINE_RESULT" = skipped', block)
            self.assertIn('test "$NATIVE_RESULT" = skipped', block)


if __name__ == "__main__":
    unittest.main()

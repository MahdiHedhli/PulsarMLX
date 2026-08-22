from __future__ import annotations

import unittest

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

    def test_evidence_plus_docs_is_full(self):
        self.assertEqual(
            self.classify(
                ["docs/architecture/reviews/evidence/result.json", "docs/guide.md"]
            ),
            FULL_NATIVE,
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


if __name__ == "__main__":
    unittest.main()

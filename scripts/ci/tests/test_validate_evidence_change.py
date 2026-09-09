from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.ci.validate_evidence_change import ValidationError, strict_json, validate_change


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValidationError):
            strict_json(b'{"a":1,"a":2}', "duplicate.json")

    def test_normal_json_passes(self):
        self.assertEqual(strict_json(b'{"a":1}', "ok.json"), {"a": 1})


class EvidenceIntegrationTests(unittest.TestCase):
    def test_document_rename_passes_and_both_sides_validated(self):
        (self.root / "docs").mkdir()
        self.git("mv", "README.md", "docs/guide.md")
        self.git("commit", "-qm", "rename documentation")
        result = self.validate(self.base, self.git("rev-parse", "HEAD"))
        self.assertEqual(result["mode"], "DOCS_ONLY")
        self.assertEqual(result["documentation_file_count"], 2)
        self.assertEqual(result["total_changed_bytes"], len(b"authority\n"))
        self.assertFalse(result["append_only"])

    def test_document_evidence_rename_cannot_change_semantics(self):
        path = "docs/architecture/reviews/evidence/doc.md"
        (self.root / path).parent.mkdir(parents=True)
        self.git("mv", "README.md", path)
        self.git("commit", "-qm", "rename docs to evidence")
        head = self.git("rev-parse", "HEAD")
        with self.assertRaises(ValidationError):
            self.validate(self.base, head)
        self.git("mv", path, "README.md")
        self.git("commit", "-qm", "rename evidence to docs")
        with self.assertRaises(ValidationError):
            self.validate(head, self.git("rev-parse", "HEAD"))

    def test_removing_historical_document_marker_passes(self):
        (self.root / "README.md").write_text("-----BEGIN PRIVATE KEY-----\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "synthetic historical marker")
        old = self.git("rev-parse", "HEAD")
        result = self.validate(old, self.modify_docs())
        self.assertEqual(result["total_changed_bytes"], len(b"updated documentation\n"))

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def validate(self, base, head):
        return validate_change(self.root, base=base, head=head, branch="feat/test", run_attempt1=False)

    def modify_docs(self):
        (self.root / "README.md").write_text("updated documentation\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "docs")
        return self.git("rev-parse", "HEAD")

    def test_docs_only_checks_without_evidence(self):
        result = self.validate(self.base, self.modify_docs())
        self.assertEqual(result["mode"], "DOCS_ONLY")
        self.assertEqual(result["documentation_file_count"], 1)
        self.assertEqual(result["evidence_file_count"], 0)

    def test_mixed_docs_and_valid_evidence(self):
        self.commit_evidence('{"schema":"test"}\n')
        result = self.validate(self.base, self.modify_docs())
        self.assertEqual(result["mode"], "EVIDENCE_ONLY")
        self.assertEqual(result["documentation_file_count"], 1)
        self.assertEqual(result["evidence_file_count"], 1)
        self.assertTrue(result["evidence_append_only"])

    def test_docs_cannot_hide_unresolved_binding(self):
        self.commit_evidence(json.dumps({"path": "missing.json", "sha256": "0" * 64}) + "\n")
        with self.assertRaises(ValidationError):
            self.validate(self.base, self.modify_docs())

    def test_docs_cannot_hide_duplicate_evidence_key(self):
        self.commit_evidence('{"a":1,"a":2}\n')
        with self.assertRaises(ValidationError):
            self.validate(self.base, self.modify_docs())

    def test_docs_do_not_exempt_evidence_edit_delete_or_rename(self):
        first = self.commit_evidence('{}\n')
        path = "docs/architecture/reviews/evidence/result.json"
        (self.root / path).write_text('{"changed":true}\n')
        self.git("add", path)
        self.git("commit", "-qm", "edit evidence")
        edited = self.modify_docs()
        with self.assertRaises(ValidationError):
            self.validate(first, edited)
        other = "docs/architecture/reviews/evidence/renamed.json"
        self.git("mv", path, other)
        self.git("commit", "-qm", "rename evidence")
        renamed = self.git("rev-parse", "HEAD")
        with self.assertRaises(ValidationError):
            self.validate(edited, renamed)
        self.git("rm", other)
        self.git("commit", "-qm", "delete evidence")
        with self.assertRaises(ValidationError):
            self.validate(renamed, self.git("rev-parse", "HEAD"))

    def test_executable_and_symlink_evidence_fail_cheaply(self):
        first = self.commit_evidence('{}\n')
        path = "docs/architecture/reviews/evidence/result.json"
        (self.root / path).chmod(0o755)
        self.git("add", path)
        self.git("commit", "-qm", "executable evidence")
        with self.assertRaises(ValidationError):
            self.validate(self.base, self.git("rev-parse", "HEAD"))
        link = self.root / "docs/architecture/reviews/evidence/link.json"
        link.symlink_to("result.json")
        self.git("add", str(link.relative_to(self.root)))
        self.git("commit", "-qm", "symlink evidence")
        with self.assertRaises(ValidationError):
            self.validate(first, self.git("rev-parse", "HEAD"))

    def test_document_credentials_are_checked_in_mixed_diff(self):
        self.commit_evidence('{}\n')
        (self.root / "README.md").write_text("-----BEGIN PRIVATE KEY-----\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "synthetic credential marker")
        with self.assertRaises(ValidationError):
            self.validate(self.base, self.git("rev-parse", "HEAD"))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "CI Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "ci@example.invalid"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("authority\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.root, check=True)
        self.base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()

    def tearDown(self):
        self.temporary.cleanup()

    def commit_evidence(self, content: str, name: str = "result.json") -> str:
        path = self.root / "docs/architecture/reviews/evidence" / name
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", str(path.relative_to(self.root))], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "evidence"], cwd=self.root, check=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()

    def test_append_only_evidence_passes(self):
        head = self.commit_evidence('{"schema":"test/1.0.0"}\n')
        result = validate_change(
            self.root,
            base=self.base,
            head=head,
            branch="feat/test",
            run_attempt1=False,
        )
        self.assertEqual(result["result"], "PASS")

    def test_unresolved_binding_rejected(self):
        head = self.commit_evidence(
            json.dumps({"authority": {"path": "missing.json", "sha256": "0" * 64}}) + "\n"
        )
        with self.assertRaises(ValidationError):
            validate_change(
                self.root,
                base=self.base,
                head=head,
                branch="feat/test",
                run_attempt1=False,
            )

    def test_numerical_node_receipt_rejects_unpaired_authority_shas(self):
        head = self.commit_evidence(
            json.dumps({
                "schema": "pulsarmlx.f017.numerical-output-interface-node-receipt/1.0.0",
                "input_authority_shas": {"numerical_requalification_v4": "0" * 64},
            }) + "\n",
            "f017-numerical-output-interface-node-r8-receipt-v2.json",
        )
        with self.assertRaises(ValidationError):
            validate_change(
                self.root, base=self.base, head=head, branch="feat/test", run_attempt1=False
            )

    def test_numerical_node_receipt_resolves_typed_authority_bindings(self):
        authority = self.root / "authority.json"
        authority.write_text('{"authority":true}\n', encoding="utf-8")
        subprocess.run(["git", "add", "authority.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "authority"], cwd=self.root, check=True)
        self.base = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        head = self.commit_evidence(
            json.dumps({
                "schema": "pulsarmlx.f017.numerical-output-interface-node-receipt/1.0.0",
                "input_authorities": {
                    "authority": {
                        "path": "authority.json",
                        "sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
                    }
                },
            }) + "\n",
            "f017-numerical-output-interface-node-r8-receipt-v2.json",
        )
        result = validate_change(
            self.root, base=self.base, head=head, branch="feat/test", run_attempt1=False
        )
        self.assertEqual(result["resolved_binding_count"], 1)

    def test_absolute_repository_binding_is_normalized_and_verified(self):
        authority = self.root / "authority.json"
        authority.write_text('{"authority":true}\n', encoding="utf-8")
        subprocess.run(["git", "add", "authority.json"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "authority"], cwd=self.root, check=True)
        self.base = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        head = self.commit_evidence(
            json.dumps({
                "authority_path": str(authority),
                "authority_sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
            }) + "\n"
        )
        result = validate_change(
            self.root, base=self.base, head=head, branch="feat/test", run_attempt1=False
        )
        self.assertEqual(result["resolved_binding_count"], 1)

    def test_external_runtime_path_is_not_misclassified_as_git_binding(self):
        head = self.commit_evidence(
            json.dumps({
                "installed_path": "/runtime/event04/authority.json",
                "installed_sha256": "0" * 64,
            }) + "\n"
        )
        result = validate_change(
            self.root, base=self.base, head=head, branch="feat/test", run_attempt1=False
        )
        self.assertEqual(result["resolved_binding_count"], 0)

    def test_explicitly_absent_optional_binding_is_ignored(self):
        head = self.commit_evidence(
            json.dumps({"synthetic_manifest_path": None, "synthetic_manifest_sha256": None}) + "\n"
        )
        result = validate_change(
            self.root, base=self.base, head=head, branch="feat/test", run_attempt1=False
        )
        self.assertEqual(result["resolved_binding_count"], 0)

    def test_modified_evidence_rejected(self):
        first = self.commit_evidence('{"schema":"test/1.0.0"}\n')
        path = self.root / "docs/architecture/reviews/evidence/result.json"
        path.write_text('{"schema":"test/2.0.0"}\n', encoding="utf-8")
        subprocess.run(["git", "add", str(path.relative_to(self.root))], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "mutate"], cwd=self.root, check=True)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root, text=True).strip()
        with self.assertRaises(ValidationError):
            validate_change(
                self.root,
                base=first,
                head=head,
                branch="feat/test",
                run_attempt1=False,
            )


if __name__ == "__main__":
    unittest.main()

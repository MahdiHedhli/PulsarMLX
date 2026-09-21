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

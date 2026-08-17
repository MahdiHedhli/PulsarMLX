from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "scripts/research/validate_f017_v2_antecedent_private_reuse.py"
SPEC = importlib.util.spec_from_file_location("validate_f017_v2_antecedent_private_reuse", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AntecedentPrivateReuseTests(unittest.TestCase):
    def document(self):
        return MODULE.load_json(MODULE.EVIDENCE)

    def test_committed_public_authorization_validates(self) -> None:
        document = self.document()
        MODULE.validate_authorization_document(document)
        self.assertEqual(document["consumer"]["allowed_purpose"], MODULE.ALLOWED_PURPOSE)
        self.assertEqual(document["isolation"]["checkpoint_reads"], 0)
        self.assertEqual(document["isolation"]["shard_opens"], 0)
        self.assertEqual(document["isolation"]["real_payload_ledger_after"], 139)

    def test_public_evidence_has_no_private_absolute_path(self) -> None:
        raw = MODULE.EVIDENCE.read_text()
        self.assertNotIn("/Users/", raw)
        self.assertNotIn("file://", raw)
        for item in self.document()["package"]["artifacts"]:
            self.assertFalse(Path(item["symbolic_name"]).is_absolute())
            self.assertNotIn("..", Path(item["symbolic_name"]).parts)

    def test_identity_and_authority_mutations_fail_closed(self) -> None:
        mutations = []
        document = self.document()
        mutated = copy.deepcopy(document)
        mutated["package"]["artifacts"][0]["after_sha256"] = "0" * 64
        mutations.append(mutated)
        mutated = copy.deepcopy(document)
        mutated["consumer"]["allowed_purpose"] = "ROUTE_SCORE_COMPUTATION"
        mutations.append(mutated)
        mutated = copy.deepcopy(document)
        mutated["isolation"]["checkpoint_reads"] = 1
        mutations.append(mutated)
        mutated = copy.deepcopy(document)
        mutated["isolation"]["real_payload_ledger_after"] = 140
        mutations.append(mutated)
        mutated = copy.deepcopy(document)
        mutated["package"]["artifacts"][0]["symbolic_name"] = "/private/leak.bin"
        mutations.append(mutated)
        for candidate in mutations:
            with self.assertRaises(MODULE.ReuseValidationError):
                MODULE.validate_authorization_document(candidate)

    def test_duplicate_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(MODULE.ReuseValidationError, "duplicate key"):
                MODULE.load_json(path)

    def test_private_verifier_rejects_mutation_writable_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            antecedents = root / "antecedents"
            antecedents.mkdir(parents=True)
            payload = antecedents / "sample.bin"
            payload.write_bytes(b"retained")
            payload.chmod(0o444)
            inventory = [{
                "symbolic_name": "antecedents/sample.bin",
                "byte_length": 8,
                "sha256": hashlib.sha256(b"retained").hexdigest(),
            }]
            MODULE.verify_private_artifacts(root, inventory)

            payload.chmod(0o644)
            with self.assertRaisesRegex(MODULE.ReuseValidationError, "writable"):
                MODULE.verify_private_artifacts(root, inventory)
            payload.write_bytes(b"mutated!")
            payload.chmod(0o444)
            with self.assertRaisesRegex(MODULE.ReuseValidationError, "SHA mismatch"):
                MODULE.verify_private_artifacts(root, inventory)

            payload.unlink()
            target = antecedents / "target.bin"
            target.write_bytes(b"retained")
            target.chmod(0o444)
            payload.symlink_to(target.name)
            with self.assertRaisesRegex(MODULE.ReuseValidationError, "symlink"):
                MODULE.verify_private_artifacts(root, inventory)

    def test_active_output_alias_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "package"
            antecedents = root / "antecedents"
            output = base / "active-output"
            antecedents.mkdir(parents=True)
            output.mkdir()
            payload = antecedents / "sample.bin"
            payload.write_bytes(b"retained")
            payload.chmod(0o444)
            alias = output / "sample.bin"
            os.link(payload, alias)
            inventory = [{
                "symbolic_name": "antecedents/sample.bin",
                "byte_length": 8,
                "sha256": hashlib.sha256(b"retained").hexdigest(),
            }]
            with self.assertRaisesRegex(MODULE.ReuseValidationError, "hard-link alias"):
                MODULE.verify_private_artifacts(root, inventory)


if __name__ == "__main__":
    unittest.main()

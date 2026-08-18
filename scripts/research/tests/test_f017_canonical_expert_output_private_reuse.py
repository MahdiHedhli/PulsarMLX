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
SOURCE = ROOT / "scripts/research/validate_f017_canonical_expert_output_private_reuse.py"
SPEC = importlib.util.spec_from_file_location("validate_f017_canonical_expert_output_private_reuse", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CanonicalExpertOutputPrivateReuseTests(unittest.TestCase):
    def document(self):
        return MODULE.load_json(MODULE.EVIDENCE)

    def test_committed_public_authorization_validates(self) -> None:
        document = self.document()
        MODULE.validate_authorization_document(document)
        self.assertEqual(document["consumer"]["consumer_id"], MODULE.CONSUMER_ID)
        self.assertEqual(document["package"]["artifact_count"], 8)
        self.assertEqual(document["isolation"]["real_payload_ledger_after"], 163)

    def test_public_evidence_has_no_private_path_or_aggregate_result(self) -> None:
        raw = MODULE.EVIDENCE.read_text()
        self.assertNotIn("/Users/", raw)
        self.assertNotIn("file://", raw)
        document = self.document()
        self.assertFalse(document["aggregate_theorem"]["evaluation_performed"])
        self.assertFalse(document["aggregate_theorem"]["weighted_products_computed"])
        self.assertEqual(document["isolation"]["aggregate_evaluations"], 0)
        for item in document["package"]["artifacts"]:
            self.assertFalse(Path(item["symbolic_name"]).is_absolute())
            self.assertNotIn("..", Path(item["symbolic_name"]).parts)

    def test_exact_id_keyed_inventory_and_provenance(self) -> None:
        document = self.document()
        artifacts = document["package"]["artifacts"]
        self.assertEqual([item["expert_id"] for item in artifacts], MODULE.SELECTED_IDS)
        self.assertEqual(len({item["expert_id"] for item in artifacts}), 8)
        for item in artifacts:
            self.assertEqual(item["shape"], [6144])
            self.assertEqual(item["dtype"], "f32")
            self.assertEqual(item["byte_length"], 24_576)
            self.assertEqual(set(item["source_weight_packed_sha256"]), {"gate", "up", "down"})
            self.assertEqual(item["expected_sha256"], item["before_sha256"])
            self.assertEqual(item["expected_sha256"], item["after_sha256"])

    def test_identity_authority_and_isolation_mutations_fail_closed(self) -> None:
        document = self.document()
        mutations = []
        for mutate in (
            lambda value: value["package"]["artifacts"][0].update(after_sha256="0" * 64),
            lambda value: value["package"]["artifacts"][1].update(expert_id=250),
            lambda value: value["package"]["artifacts"][0]["source_weight_packed_sha256"].update(gate="0" * 64),
            lambda value: value["consumer"].update(allowed_purpose="MODEL_EXECUTION"),
            lambda value: value["aggregate_theorem"].update(sha256="0" * 64),
            lambda value: value["aggregate_theorem"].update(evaluation_performed=True),
            lambda value: value["isolation"].update(checkpoint_reads=1),
            lambda value: value["isolation"].update(shard_opens=1),
            lambda value: value["isolation"].update(real_payload_ledger_after=164),
            lambda value: value["source"].update(private_package_manifest_sha256="0" * 64),
            lambda value: value["package"]["artifacts"][0].update(symbolic_name="/private/leak.bin"),
        ):
            candidate = copy.deepcopy(document)
            mutate(candidate)
            mutations.append(candidate)
        for candidate in mutations:
            with self.assertRaises(MODULE.ExpertOutputReuseValidationError):
                MODULE.validate_authorization_document(candidate)

    def test_duplicate_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(MODULE.ExpertOutputReuseValidationError, "duplicate key"):
                MODULE.load_json(path)

    def test_private_verifier_rejects_writable_mutated_symlink_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "package"
            outputs = root / "expert_outputs"
            outputs.mkdir(parents=True)
            payload = outputs / "expert_250_down_output.bin"
            payload.write_bytes(b"retained")
            payload.chmod(0o400)
            inventory = [{
                "expert_id": 250,
                "symbolic_name": "expert_outputs/expert_250_down_output.bin",
                "byte_length": 8,
                "sha256": hashlib.sha256(b"retained").hexdigest(),
            }]
            MODULE.verify_private_artifacts(root, inventory)

            payload.chmod(0o600)
            with self.assertRaisesRegex(MODULE.ExpertOutputReuseValidationError, "writable"):
                MODULE.verify_private_artifacts(root, inventory)
            payload.write_bytes(b"mutated!")
            payload.chmod(0o400)
            with self.assertRaisesRegex(MODULE.ExpertOutputReuseValidationError, "SHA"):
                MODULE.verify_private_artifacts(root, inventory)

            payload.unlink()
            target = outputs / "target.bin"
            target.write_bytes(b"retained")
            target.chmod(0o400)
            payload.symlink_to(target.name)
            with self.assertRaisesRegex(MODULE.ExpertOutputReuseValidationError, "symlink"):
                MODULE.verify_private_artifacts(root, inventory)

            payload.unlink()
            payload.write_bytes(b"retained")
            payload.chmod(0o400)
            alias = outputs / "alias.bin"
            os.link(payload, alias)
            with self.assertRaisesRegex(MODULE.ExpertOutputReuseValidationError, "hard-link alias"):
                MODULE.verify_private_artifacts(root, inventory)

    def test_active_output_alias_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "package"
            outputs = root / "expert_outputs"
            active = base / "active"
            outputs.mkdir(parents=True)
            active.mkdir()
            payload = outputs / "expert_250_down_output.bin"
            payload.write_bytes(b"retained")
            payload.chmod(0o400)
            os.link(payload, active / payload.name)
            inventory = [{
                "expert_id": 250,
                "symbolic_name": "expert_outputs/expert_250_down_output.bin",
                "byte_length": 8,
                "sha256": hashlib.sha256(b"retained").hexdigest(),
            }]
            with self.assertRaisesRegex(MODULE.ExpertOutputReuseValidationError, "hard-link alias"):
                MODULE.verify_private_artifacts(root, inventory)

    def test_historical_dispositions_remain_fail_closed(self) -> None:
        history = self.document()["historical_immutability"]
        self.assertEqual(history["REAL_1"], "REJECTED_UNCHANGED")
        self.assertEqual(history["REAL_2"], "REJECTED_UNCHANGED")
        self.assertEqual(history["REAL_3"], "REJECTED_UNCHANGED")
        self.assertEqual(history["DPREFIX_EXACT_1"], "CANONICAL_UNCHANGED")
        self.assertEqual(history["membership"], "1984_OF_1984_PASS_UNCHANGED")
        self.assertEqual(history["coefficient_qualification"], "0_OF_8_FAIL_UNCHANGED")
        self.assertEqual(history["route_disposition"], "ROUTE NOT PROVEN INVARIANT")


if __name__ == "__main__":
    unittest.main()

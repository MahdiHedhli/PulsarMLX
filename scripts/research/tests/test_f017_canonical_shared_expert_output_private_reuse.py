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
SOURCE = ROOT / "scripts/research/validate_f017_canonical_shared_expert_output_private_reuse.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_f017_canonical_shared_expert_output_private_reuse", SOURCE
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CanonicalSharedExpertOutputPrivateReuseTests(unittest.TestCase):
    def document(self):
        return MODULE.load_json(MODULE.EVIDENCE)

    def test_committed_public_authorization_validates(self) -> None:
        document = self.document()
        MODULE.validate_authorization_document(document)
        self.assertEqual(document["consumer"]["consumer_id"], MODULE.CONSUMER_ID)
        self.assertEqual(document["artifact"]["expected_sha256"], MODULE.OUTPUT_SHA)
        self.assertEqual(document["isolation"]["real_payload_ledger_after"], 166)

    def test_public_evidence_has_no_private_path_or_evaluation(self) -> None:
        raw = MODULE.EVIDENCE.read_text()
        self.assertNotIn("/Users/", raw)
        self.assertNotIn("file://", raw)
        document = self.document()
        self.assertFalse(document["complete_layer_v2"]["evaluation_performed"])
        self.assertFalse(document["complete_layer_v2"]["metrics_computed"])
        self.assertEqual(document["isolation"]["aggregate_evaluations"], 0)
        self.assertEqual(document["isolation"]["complete_layer_metrics_computed"], 0)

    def test_persisted_exact_class_authority_is_scoped(self) -> None:
        authority = self.document()["authority_classification"]
        self.assertEqual(authority["reproducibility_class"], "PERSISTED_AUTHORITY")
        self.assertTrue(authority["production_mechanism"].startswith("EXACT_CLASS_"))
        self.assertEqual(authority["delta_s_rule"], "delta_S=0")
        self.assertFalse(authority["generalization_permitted"])
        self.assertIn("ROUTING_WEIGHT_ONLY", authority["delta_s_scope"])

    def test_complete_layer_and_routed_dependencies_are_identity_bound(self) -> None:
        document = self.document()
        complete = document["complete_layer_v2"]
        self.assertEqual(complete["sha256"], MODULE.COMPLETE_LAYER_V2_SHA)
        self.assertEqual(complete["thresholds"], {
            "max_absolute": 0.0625, "rmse": 0.03125, "cosine_minimum": 0.999,
        })
        routed = document["routed_dependencies"]
        self.assertEqual(routed["routed_nominal_aggregate_sha256"], MODULE.ROUTED_NOMINAL_SHA)
        self.assertEqual(routed["routed_sound_intersection_sha256"], MODULE.ROUTED_INTERSECTION_SHA)
        self.assertFalse(routed["recomputed"])
        self.assertEqual(len(routed["canonical_expert_output_sha256_by_id"]), 8)

    def test_identity_authority_and_isolation_mutations_fail_closed(self) -> None:
        document = self.document()
        mutations = (
            lambda value: value["artifact"].update(after_sha256="0" * 64),
            lambda value: value["artifact"].update(byte_length=1),
            lambda value: value["artifact"].update(symbolic_name="/private/leak.bin"),
            lambda value: value["authority_classification"].update(generalization_permitted=True),
            lambda value: value["consumer"].update(allowed_purpose="MODEL_EXECUTION"),
            lambda value: value["consumer"].update(payload_decoding_permitted=True),
            lambda value: value["complete_layer_v2"].update(metrics_computed=True),
            lambda value: value["complete_layer_v2"]["thresholds"].update(cosine_minimum=0.9),
            lambda value: value["routed_dependencies"].update(recomputed=True),
            lambda value: value["routed_dependencies"].update(routed_sound_intersection_sha256="0" * 64),
            lambda value: value["isolation"].update(checkpoint_reads=1),
            lambda value: value["isolation"].update(shard_opens=1),
            lambda value: value["isolation"].update(real_payload_ledger_after=167),
            lambda value: value["historical_immutability"].update(route_disposition="PASS"),
        )
        for mutate in mutations:
            candidate = copy.deepcopy(document)
            mutate(candidate)
            with self.assertRaises(MODULE.SharedOutputReuseValidationError):
                MODULE.validate_authorization_document(candidate)

    def test_duplicate_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(MODULE.SharedOutputReuseValidationError, "duplicate key"):
                MODULE.load_json(path)

    def test_private_verifier_rejects_writable_mutated_symlink_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "package"
            outputs = package / "outputs"
            outputs.mkdir(parents=True)
            payload = outputs / "canonical_shared_expert_output.bin"
            expected_sha = hashlib.sha256(b"retained").hexdigest()
            payload.write_bytes(b"retained")
            payload.chmod(0o400)
            MODULE.verify_private_artifact(package, expected_sha256=expected_sha, expected_size=8)

            payload.chmod(0o600)
            with self.assertRaisesRegex(MODULE.SharedOutputReuseValidationError, "writable"):
                MODULE.verify_private_artifact(package, expected_sha256=expected_sha, expected_size=8)

            payload.write_bytes(b"mutated!")
            payload.chmod(0o400)
            with self.assertRaisesRegex(MODULE.SharedOutputReuseValidationError, "SHA"):
                MODULE.verify_private_artifact(package, expected_sha256=expected_sha, expected_size=8)

            payload.unlink()
            target = outputs / "target.bin"
            target.write_bytes(b"retained")
            target.chmod(0o400)
            payload.symlink_to(target.name)
            with self.assertRaisesRegex(MODULE.SharedOutputReuseValidationError, "symlink"):
                MODULE.verify_private_artifact(package, expected_sha256=expected_sha, expected_size=8)

            payload.unlink()
            payload.write_bytes(b"retained")
            payload.chmod(0o400)
            os.link(payload, outputs / "alias.bin")
            with self.assertRaisesRegex(MODULE.SharedOutputReuseValidationError, "hard-link alias"):
                MODULE.verify_private_artifact(package, expected_sha256=expected_sha, expected_size=8)

    def test_historical_dispositions_remain_fail_closed(self) -> None:
        history = self.document()["historical_immutability"]
        self.assertEqual(history["REAL_1"], "REJECTED_UNCHANGED")
        self.assertEqual(history["REAL_2"], "REJECTED_UNCHANGED")
        self.assertEqual(history["REAL_3"], "REJECTED_UNCHANGED")
        self.assertEqual(history["membership"], "1984_OF_1984_PASS_UNCHANGED")
        self.assertEqual(history["coefficient_qualification"], "0_OF_8_FAIL_UNCHANGED")
        self.assertEqual(history["routed_aggregate_v1"], "FAIL_UNCHANGED")
        self.assertEqual(history["complete_layer_v2"], "FROZEN_NOT_EVALUATED")
        self.assertEqual(history["route_disposition"], "ROUTE NOT PROVEN INVARIANT")


if __name__ == "__main__":
    unittest.main()

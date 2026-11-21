"""Temporary-file admission controls. Never access real claims, models or reference payloads."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import studio020_operator as op
import studio020_supervise as sup

SOURCE = dict(head="1" * 40, tree="2" * 40)
RUN = sup.RUN


class OperatorAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.binary = self.root / "synthetic-binary"
        self.binary.write_bytes(b"not an executable; synthetic identity only")
        self.cap = self.root / "campaign-native/child-cap.json"
        self.cap.parent.mkdir()
        self.cap.write_bytes(b"synthetic-capability")
        self.claim = self.root / "synthetic-native.claim"
        self.config = dict(schema="studio020-operator-config/1", mode=op.MODE, run=RUN,
                           source=SOURCE, operations=dict(sup.OPERATIONS), stages={"native": {"program": str(self.binary)}},
                           artifacts={"operator-lifecycle": {"sha256": "4" * 64},
                                      "numerical-invariance": {"sha256": "5" * 64}})
        comparison = self.root / "comparison.json"
        sup.put(comparison, sup.COMPARISON_LIMITS)
        self.config["artifacts"]["comparison-resource"] = dict(path=str(comparison), sha256=sup.digest(comparison))
        self.facts = dict(stage="native", run=RUN, attempt="initial", source=SOURCE,
                          revision=sup.MODEL, children=1, one_cold_input=True,
                          input_sha256=op.INPUT, criteria_sha256=op.CRITERIA,
                          resource_sha256=op.RESOURCES)

    def manifest(self, config=None, role="native", facts=None, reference=None):
        # Signed-review and fixed historical artifact acquisition are external boundaries.
        # Only this in-memory config is accepted by the substituted evidence validator.
        with patch.object(op, "validate_config", side_effect=lambda c: self.assertEqual(c, self.config)):
            return op.manifest(config or self.config, role, facts or self.facts,
                               op.original_reference_identity() if reference is None else reference)

    def test_ineligible_reference_identity_and_manifest_not_relabelled(self):
        result = self.manifest()
        identity = op.original_reference_identity()
        self.assertEqual(result["reference"], identity)
        self.assertFalse(result["qualifying"])
        self.assertFalse(identity["eligible"])
        self.assertEqual(identity["failed_route_layers"], [23, 33, 34])
        for key in identity:
            changed = copy.deepcopy(identity)
            changed[key] = True if key == "eligible" else ([] if key == "failed_route_layers" else "0" * 64)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "exact ineligible comparison reference"):
                self.manifest(reference=changed)
        for key, value in (("stage", "reference"), ("source", dict(SOURCE, head="0" * 40)),
                           ("run", "0" * 64), ("criteria_sha256", "0" * 64)):
            facts = dict(self.facts); facts[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.manifest(facts=facts)
        with self.assertRaises(ValueError): self.manifest(role="reference")

    def test_frozen_manifest_and_exclusive_claim_reject_replay(self):
        expected = self.manifest()
        with patch.object(op, "STATE", self.root), patch.object(sup, "ANCHORS", {"native": self.claim}):
            sup.put(op.manifest_path("native"), expected)
            identity = op.verified_manifest(self.config, "native", expected)
            wrong = dict(expected, source=dict(SOURCE, head="0" * 40))
            with self.assertRaises(ValueError): op.verified_manifest(self.config, "native", wrong)
            with self.assertRaises(ValueError): op.verified_manifest(self.config, "reference", expected)
            self.cap.write_bytes(b"synthetic-capability")
            sup.spend_operator(self.config, "native", expected, identity, sup.OPERATIONS["native"], self.cap)
            before = self.claim.read_bytes()
            with self.assertRaises(FileExistsError):
                sup.spend_operator(self.config, "native", expected, identity, sup.OPERATIONS["native"], self.cap)
            with self.assertRaisesRegex(ValueError, "spent claim"):
                sup.envelope(self.config, "native")
            self.assertEqual(before, self.claim.read_bytes())
            self.assertEqual(sup.doc(self.claim)["binary_sha256"], sup.digest(self.binary))
            self.binary.write_bytes(b"altered synthetic executable")
            with self.assertRaises(ValueError):
                op.verified_manifest(self.config, "native", self.manifest())

    def test_child_rejects_wrong_task_role_source_binary_and_claim_before_ack(self):
        payload = dict(schema="studio020-child-cap/1", task=sup.TASK, stage="native",
                       source=SOURCE, native_image_source=SOURCE, run=RUN, operation=sup.OPERATIONS["native"],
                       expected_image=str(self.binary), native_image_policy={"program": str(self.binary)},
                       **{key: "fixture" for key in ("model_root", "checkpoint_receipt", "inventory",
                          "witnesses", "input", "pins", "output", "prefix", "libs")})
        claim = dict(schema="studio020-operator-local-claim/1", stage="native", cap_sha256=sup.digest(self.cap),
                     source=SOURCE["head"], run=RUN, operation=sup.OPERATIONS["native"],
                     binary_sha256=sup.digest(self.binary))
        def read_fixture(path):
            if Path(path) == self.cap: return payload
            if Path(path) == self.claim: return claim
            raise AssertionError("unexpected fixture read " + str(path))
        with patch.object(sup, "STATE", self.root), patch.object(sup, "ANCHORS", {"native": self.claim}), \
             patch.object(sup, "doc", side_effect=read_fixture), patch.object(sup, "acknowledge_child") as ack:
            self.assertEqual(sup.child(self.cap)["stage"], "native")
            ack.assert_called_once(); ack.reset_mock()
            mutants = ((payload, "task", "Studio017"), (payload, "operation", "0"*32), (payload, "stage", "reference"),
                       (payload, "source", dict(SOURCE, head="0" * 40)),
                       (payload, "native_image_source", dict(SOURCE, tree="0" * 40)),
                       (claim, "schema", "studio017-operator-local-claim/1"),
                       (claim, "run", "0" * 64), (claim, "stage", "reference"),
                       (claim, "cap_sha256", "0" * 64), (claim, "binary_sha256", "0" * 64))
            for target, key, value in mutants:
                old = target[key]; target[key] = value
                try:
                    with self.subTest(key=key), self.assertRaises(ValueError): sup.child(self.cap)
                    ack.assert_not_called()
                finally: target[key] = old

    def test_default_off_and_reference_entry_rejected_before_configuration_read(self):
        with patch.object(sup, "load_cfg") as load:
            for args in (["launch", "/unused", "native"],
                         ["--studio020-stream-reuse", "launch", "/unused", "reference"],
                         ["launch", "/unused", "native", "--studio020-stream-reuse"]):
                with self.assertRaises(ValueError): sup.main(args)
            load.assert_not_called()
        with self.assertRaises(ValueError): sup.run_numeric("/unused", "native")
        with self.assertRaises(ValueError): sup.run_numeric("/unused", "reference", True)


if __name__ == "__main__": unittest.main()

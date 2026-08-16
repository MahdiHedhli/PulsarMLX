from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import hashlib
import struct
from pathlib import Path
from unittest import mock

from scripts.research import f017_dprefix_real_event_orchestrator as O
from scripts.research.ggml_kquants import dequantize_row_q4_k, dequantize_row_q5_k, dequantize_row_q6_k


class RealEventOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = O.load(O.INVENTORY_PATH)
        self.entries = O.validate_inventory(self.inventory)

    def test_blocker_is_real_and_same_attempt_continues(self) -> None:
        stop = O.load(O.STOP_EVIDENCE_PATH)
        self.assertEqual(stop["terminal_class"], "EXECUTION_SURFACE_DRIFT")
        self.assertEqual(stop["reason_code"], "REAL_EVENT_ORCHESTRATOR_UNBOUND")
        self.assertFalse(stop["state"]["consumed"])
        attempt = O.load(O.ATTEMPT_V5_PATH)["current_state"]
        self.assertTrue(attempt["authorized"])
        self.assertFalse(attempt["consumed"])
        self.assertFalse(attempt["checkpoint_accessed"])
        self.assertEqual(attempt["ledger"], 59)

    def test_inventory_is_exact_and_attacks_fail(self) -> None:
        self.assertEqual(len(self.entries), 40)
        self.assertEqual(sum(item["packed_length"] for item in self.entries), O.PACKED_BYTES)
        for mutation, message in [
            (lambda value: value["entries"].pop(), "40"),
            (lambda value: value["entries"].append(copy.deepcopy(value["entries"][-1])), "40"),
            (lambda value: value["entries"].__setitem__(1, copy.deepcopy(value["entries"][0])), "order|duplicate"),
            (lambda value: value["entries"][3].__setitem__("layer", 3), "layer-3"),
            (lambda value: value.__setitem__("packed_bytes", O.PACKED_BYTES + 1), "packed byte"),
        ]:
            changed = copy.deepcopy(self.inventory)
            mutation(changed)
            with self.assertRaisesRegex(O.OrchestratorError, message):
                O.validate_inventory(changed)

    def test_reader_uses_one_exact_pread_and_rejects_substitution_and_41st(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            shard = root / "fixture.gguf"
            shard.write_bytes(bytes(range(128)))
            entries = [
                {"ordinal": index, "name": f"tensor.{index}", "shard_basename": shard.name, "offset": index * 2, "packed_length": 2}
                for index in range(40)
            ]
            journal = O.DurableReadJournal(root / "journal.json")
            journal.start({"attempt_id": O.ATTEMPT})
            reader = O.BoundedCheckpointReader(shard, entries, journal)
            try:
                self.assertEqual(reader.read(entries[0]), b"\x00\x01")
                changed = dict(entries[1], offset=entries[1]["offset"] + 1)
                with self.assertRaisesRegex(O.OrchestratorError, "substitution"):
                    reader.read(changed)
                for item in entries[1:]:
                    reader.read(item)
                with self.assertRaisesRegex(O.OrchestratorError, "41st"):
                    reader.read(entries[-1])
            finally:
                reader.close()
            self.assertEqual(journal.issued_count, 40)
            self.assertEqual(journal.completed_count, 40)
            self.assertEqual(journal.reconstructed_ledger_after, 99)

    def test_reader_rejects_symlink_short_read_and_alternate_shard(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "target.gguf"
            target.write_bytes(b"abcd")
            link = root / "link.gguf"
            link.symlink_to(target)
            entry = {"ordinal": 0, "name": "x", "shard_basename": link.name, "offset": 0, "packed_length": 4}
            journal = O.DurableReadJournal(root / "j1.json")
            with self.assertRaisesRegex(O.OrchestratorError, "symlink"):
                O.BoundedCheckpointReader(link, [entry], journal)
            entry["shard_basename"] = target.name
            entry["packed_length"] = 8
            journal = O.DurableReadJournal(root / "j2.json")
            journal.start({"attempt_id": O.ATTEMPT})
            reader = O.BoundedCheckpointReader(target, [entry], journal)
            try:
                with self.assertRaisesRegex(O.OrchestratorError, "short"):
                    reader.read(entry)
            finally:
                reader.close()
            self.assertEqual(journal.reconstructed_ledger_after, 60)

    def test_partial_failure_campaign_reconstructs_every_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            campaign = O.partial_failure_campaign(self.entries, Path(raw))
        self.assertEqual(campaign["result"], "PASS")
        numeric = [item for item in campaign["cases"] if "phase" not in item]
        self.assertEqual([item["ledger_after"] for item in numeric], [59, 60, 61, 76, 98, 99])
        self.assertTrue(all(not item.get("false_pass", False) for item in campaign["cases"]))

    def test_dry_run_has_exact_topology_but_no_real_ledger_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            evidence = O.run_checkpoint_free_rehearsal(Path(raw))
        self.assertEqual(evidence["result"], "FULL_REAL_EVENT_ORCHESTRATION_INSTANTIABLE_CHECKPOINT_FREE")
        self.assertEqual(evidence["checkpoint_access"], 0)
        self.assertEqual(evidence["real_payload_ledger"], 59)
        self.assertEqual(evidence["logical_inventory"]["payloads"], 40)
        self.assertEqual(evidence["logical_inventory"]["packed_bytes"], O.PACKED_BYTES)
        self.assertEqual(evidence["journal"], {"issued": 40, "completed": 40, "ledger_mutation": 0})
        self.assertTrue(evidence["metrics"]["overall_pass"])
        self.assertEqual(evidence["candidate"]["repeats"], 10)
        self.assertTrue(evidence["candidate"]["deterministic"])
        self.assertEqual(evidence["oracle"]["identity_before"], evidence["oracle"]["identity_after"])
        self.assertTrue(evidence["retention"]["layer_2_output"]["read_only"])
        self.assertTrue(evidence["retention"]["layer_3_entry"]["read_only"])
        self.assertEqual(evidence["terminal_banker"]["derivation"], "CHECKPOINT_FREE_REHEARSAL_ACCEPTED")

    def test_terminal_banker_rejects_invented_or_inconsistent_truth(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            evidence = O.run_checkpoint_free_rehearsal(Path(raw))["terminal_banker"]["terminal_evidence"]
        O.validate_terminal_evidence(evidence, dry_run=True)
        mutations = [
            lambda value: value["numerical_surfaces"].pop(),
            lambda value: value["numerical_surfaces"][2].__setitem__("pass", False),
            lambda value: value["execution_surfaces"].__setitem__("candidate_binary_sha256", "0" * 64),
            lambda value: value["state"].__setitem__("ledger_after", 99),
            lambda value: value["retention"].pop("layer_3_entry"),
            lambda value: value["oracle"].__setitem__("identity_after", "0" * 64),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(evidence)
            mutate(changed)
            with self.assertRaises(O.OrchestratorError):
                O.validate_terminal_evidence(changed, dry_run=True)

    def test_cli_has_no_target_prompt_or_downstream_override(self) -> None:
        module = "scripts.research.f017_dprefix_real_event_orchestrator"
        for argument in ("--target", "--prompt", "--token", "--layer-3", "--m1f0", "--attempt"):
            process = subprocess.run(
                [sys.executable, "-m", module, argument], cwd=O.ROOT, text=True, capture_output=True
            )
            self.assertNotEqual(process.returncode, 0, argument)

    def test_q4_q6_mismatch_campaign_is_terminal_at_actual_positions(self) -> None:
        result = O.q4_q6_mismatch_campaign(self.entries)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual({item["terminal"] for item in result["cases"]}, {"Q4_IDENTITY_CONFIRMATION", "Q6_IDENTITY_CONFIRMATION"})
        q4 = [item for item in result["cases"] if item["terminal"].startswith("Q4")]
        q6 = [item for item in result["cases"] if item["terminal"].startswith("Q6")]
        self.assertEqual({item["payloads"] for item in q4}, {1})
        self.assertEqual(len({item["payloads"] for item in q6}), 1)
        self.assertGreater(q6[0]["payloads"], 1)

    def test_material_builder_enforces_identity_gates_and_no_cross_event_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            q4 = copy.deepcopy(self.entries[0])
            with mock.patch.object(O, "Q4_PACKED", O.digest_bytes(b"q4")), mock.patch.object(O, "Q4_DECODED", O.digest_bytes(b"decoded")):
                builder = O.MaterialPackageBuilder(Path(raw) / "material", lambda _entry, _payload: b"decoded")
                descriptor = builder.add(q4, b"q4")
                self.assertEqual(descriptor.packed_sha256, O.digest_bytes(b"q4"))
            with self.assertRaisesRegex(O.OrchestratorError, "Q4_IDENTITY_CONFIRMATION"):
                O.MaterialPackageBuilder(Path(raw) / "bad", lambda _entry, _payload: b"wrong").add(q4, b"q4")
            q6 = copy.deepcopy(next(item for item in self.entries if item["name"] == "blk.0.ffn_down.weight"))
            q6["ordinal"] = 0
            with mock.patch.object(O, "Q6_PACKED", O.digest_bytes(b"q6")), mock.patch.object(O, "Q6_DECODED", O.digest_bytes(b"decoded6")):
                O.MaterialPackageBuilder(Path(raw) / "q6", lambda _entry, _payload: b"decoded6").add(q6, b"q6")
            with self.assertRaisesRegex(O.OrchestratorError, "Q6_IDENTITY_CONFIRMATION"):
                O.MaterialPackageBuilder(Path(raw) / "bad-q6", lambda _entry, _payload: b"wrong").add(q6, b"q6")

    def test_fixed_decoder_dispatch_matches_independent_scalar_lineage(self) -> None:
        for family, size, decoder in [
            ("Q4_K", 144, dequantize_row_q4_k),
            ("Q5_K", 176, dequantize_row_q5_k),
            ("Q6_K", 210, dequantize_row_q6_k),
        ]:
            payload = hashlib.shake_256(family.encode()).digest(size)
            # Force finite half scales while retaining varied lanes and groups.
            data = bytearray(payload)
            if family in {"Q4_K", "Q5_K"}:
                data[:4] = struct.pack("<ee", 0.5, 0.25)
            else:
                data[208:210] = struct.pack("<e", 0.5)
            payload = bytes(data)
            entry = {"quantization": family, "element_count": 256}
            actual = O.decode_canonical_f32(entry, payload)
            expected = b"".join(struct.pack("<f", value) for value in decoder(payload, 256))
            self.assertEqual(actual, expected, family)
        q8 = struct.pack("<e", 0.5) + bytes(range(32))
        actual = O.decode_canonical_f32({"quantization": "Q8_0", "element_count": 32}, q8)
        expected = b"".join(struct.pack("<f", value * 0.5) for value in range(32))
        self.assertEqual(actual, expected)

    def test_source_and_package_substitution_fail_bindings(self) -> None:
        values = O.generate_artifacts()
        O.validate_artifacts(values)
        config = next(value for path, value in values.items() if path.name.endswith("execution-config-v5.json"))
        authorization = next(value for path, value in values.items() if path.name.endswith("authorization-binding-v4.json"))
        self.assertEqual(config["orchestrator"]["package_sha256"], O.digest_path(Path(O.__file__)))
        self.assertEqual(authorization["orchestrator_package_sha256"], config["orchestrator"]["package_sha256"])
        changed = copy.deepcopy(config)
        changed["orchestrator"]["package_sha256"] = "0" * 64
        self.assertNotEqual(O.artifact_sha(changed), authorization["execution_config_sha256"])

    def test_banked_artifacts_regenerate_and_preserve_history(self) -> None:
        values = O.generate_artifacts()
        O.validate_artifacts(values)
        for path, expected in values.items():
            self.assertEqual(json.loads(path.read_text()), expected, path.name)
        attempt = json.loads((O.EVIDENCE / "f017-dense-prefix-attempt-ledger-v6.json").read_text())
        self.assertEqual(attempt["append_only_predecessor"]["sha256"], O.digest_path(O.ATTEMPT_V5_PATH))
        self.assertEqual(attempt["history"][-2]["event"], "THIRD_RELEASE_EXECUTION_SURFACE_DRIFT_STOP")
        self.assertEqual(attempt["history"][-1]["event"], "REAL_EVENT_ORCHESTRATOR_CLOSURE_SUCCESSOR_AUTHORIZATION")
        self.assertFalse(attempt["current_state"]["consumed"])

    def test_public_artifacts_have_no_machine_local_path_and_ledger_stays_59(self) -> None:
        for path in O.generate_artifacts():
            text = path.read_text()
            self.assertNotIn("/Users/", text, path.name)
        self.assertEqual(O.load(O.PAYLOAD_LEDGER_PATH)["cumulative_tensor_payloads"], 59)


if __name__ == "__main__":
    unittest.main()

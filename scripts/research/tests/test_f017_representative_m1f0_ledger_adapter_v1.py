#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ADAPTER_PATH = ROOT / "scripts/research/f017_representative_m1f0_ledger_adapter_v1.py"
SPEC = importlib.util.spec_from_file_location("ledger_adapter_v1", ADAPTER_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def encoded(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


class CanonicalLedgerAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(MODULE.DEFAULT_CONTRACT.read_text())
        cls.documents = {
            source["role"]: json.loads((ROOT / source["path"]).read_text())
            for source in cls.contract["sources"]
        }

    def fixture(self, mutate=None, preserve_stale_hash: bool = False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        contract = copy.deepcopy(self.contract)
        documents = copy.deepcopy(self.documents)
        if mutate is not None:
            mutate(contract, documents)
        for source in contract["sources"]:
            path = root / source["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = encoded(documents[source["role"]])
            path.write_bytes(payload)
            if not preserve_stale_hash:
                source["sha256"] = hashlib.sha256(payload).hexdigest()
        contract_path = root / "contract.json"
        contract_path.write_bytes(encoded(contract))
        adapter = MODULE.CanonicalLedgerAdapter(root, contract_path, expected_contract_sha256=None)
        return temporary, adapter, contract, documents

    def assert_code(self, expected: str, mutate=None, preserve_stale_hash: bool = False) -> None:
        temporary, adapter, _, _ = self.fixture(mutate, preserve_stale_hash)
        with temporary:
            with self.assertRaises(MODULE.EventError) as caught:
                adapter.read()
        self.assertEqual(expected, caught.exception.code)

    def test_actual_committed_recovery_shape_resolves_ledger_166(self) -> None:
        recovery = self.documents["canonical_shared_expert_terminal_recovery"]
        self.assertEqual(166, recovery["ledger_after"])
        self.assertNotIn("ledger", recovery)
        value, observations = MODULE.CanonicalLedgerAdapter().read()
        self.assertEqual(166, value)
        self.assertEqual(
            ["cumulative_tensor_payloads", "ledger_after"],
            [observation["field"] for observation in observations],
        )

    def test_exact_former_nested_path_raises_keyerror_but_adapter_passes(self) -> None:
        recovery = self.documents["canonical_shared_expert_terminal_recovery"]
        with self.assertRaises(KeyError):
            value = recovery
            for key in ("ledger", "after"):
                value = value[key]
        self.assertEqual(166, MODULE.CanonicalLedgerAdapter().read()[0])

    def test_missing_ledger_after_rejected(self) -> None:
        self.assert_code(
            "LEDGER_SOURCE_FIELD",
            lambda _, docs: docs["canonical_shared_expert_terminal_recovery"].pop("ledger_after"),
        )

    def test_malformed_ledger_after_rejected(self) -> None:
        self.assert_code(
            "LEDGER_SOURCE_VALUE_TYPE",
            lambda _, docs: docs["canonical_shared_expert_terminal_recovery"].__setitem__("ledger_after", "166"),
        )

    def test_wrong_consistent_ledger_rejected(self) -> None:
        def mutate(_, docs):
            docs["cumulative_real_payload_ledger"]["cumulative_tensor_payloads"] = 165
            docs["canonical_shared_expert_terminal_recovery"]["ledger_after"] = 165
        self.assert_code("LEDGER_UNEXPECTED_VALUE", mutate)

    def test_unexpected_recovery_schema_rejected(self) -> None:
        self.assert_code(
            "LEDGER_SOURCE_SCHEMA",
            lambda _, docs: docs["canonical_shared_expert_terminal_recovery"].__setitem__("schema_version", "2.0.0"),
        )

    def test_nested_legacy_substitution_rejected(self) -> None:
        def mutate(_, docs):
            recovery = docs["canonical_shared_expert_terminal_recovery"]
            recovery.pop("ledger_after")
            recovery["ledger"] = {"after": 166}
        self.assert_code("LEDGER_SOURCE_FIELD", mutate)

    def test_two_authorities_disagree_rejected(self) -> None:
        self.assert_code(
            "LEDGER_SOURCE_DISAGREEMENT",
            lambda _, docs: docs["canonical_shared_expert_terminal_recovery"].__setitem__("ledger_after", 165),
        )

    def test_stale_recovery_artifact_rejected_by_identity(self) -> None:
        self.assert_code(
            "LEDGER_SOURCE_IDENTITY",
            lambda _, docs: docs["canonical_shared_expert_terminal_recovery"].__setitem__("output", {}),
            preserve_stale_hash=True,
        )

    def test_contract_schema_drift_rejected(self) -> None:
        self.assert_code(
            "LEDGER_CONTRACT_SCHEMA",
            lambda contract, _: contract.__setitem__("schema_version", "2.0.0"),
        )


if __name__ == "__main__":
    unittest.main()

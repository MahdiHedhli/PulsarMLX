"""Synthetic-only failure matrix for the canonical expert-output executor."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.research import validate_f017_canonical_expert_output_authorization as auth
from scripts.research.f017_canonical_expert_output_recovery_executor import (
    ATTEMPT_ID,
    EVENT_ID,
    DecoderPair,
    ExecutorBinding,
    FaultInjector,
    InventoryCursor,
    MockOutputStage,
    OneShardOpenGuard,
    RecoveryExecutionError,
    RecoveryExecutor,
    SyntheticPayload,
    SyntheticShardProvider,
)


ROOT = Path(__file__).resolve().parents[3]


class ExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "event"
        self.contract = auth.load_json(ROOT / auth.CONTRACT_PATH)
        self.inventory = copy.deepcopy(self.contract["payload_inventory"])

    def binding(self) -> ExecutorBinding:
        return ExecutorBinding(
            authoritative_commit="88c93fa80c85dcd8edd4d850ea4f5f81d3af8990",
            authorization_contract_sha256="58ad56f008a27ea4b69215c39404edbccf4008ef0620a3f46bb4ff7adb2a95ae",
            review_authorization="GO — EXECUTE F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1",
            shard_sha256=auth.SHARD_SHA,
            decoder_lineage_sha256=auth.DECODER_CONTRACT_SHA,
            inventory=self.inventory,
        )

    @staticmethod
    def decoders(*, fail_a: int | None = None, fail_b: int | None = None,
                 disagree: int | None = None) -> DecoderPair:
        calls = {"n": 0}

        def decoder_a(payload: bytes, entry: dict) -> bytes:
            calls["n"] += 1
            if fail_a == entry["ordinal"]:
                raise ValueError("decoder A synthetic failure")
            return (entry["checkpoint_key"] + ":decoded").encode()

        def decoder_b(payload: bytes, entry: dict) -> bytes:
            if fail_b == entry["ordinal"]:
                raise ValueError("decoder B synthetic failure")
            suffix = ":different" if disagree == entry["ordinal"] else ":decoded"
            return (entry["checkpoint_key"] + suffix).encode()

        return DecoderPair(
            decoder_a=decoder_a,
            decoder_b=decoder_b,
            decoder_a_identity="synthetic-independent-a",
            decoder_b_identity="synthetic-independent-b",
            lineage_sha256=auth.DECODER_CONTRACT_SHA,
        )

    def provider(self, *, short_at: int | None = None,
                 fail_open: bool = False) -> SyntheticShardProvider:
        payloads = {
            item["ordinal"]: SyntheticPayload(
                data=(f"payload-{item['ordinal']}").encode(),
                logical_count=item["packed_length"] - (1 if short_at == item["ordinal"] else 0),
            )
            for item in self.inventory
        }
        return SyntheticShardProvider(payloads, fail_open=fail_open)

    def executor(self, *, provider: SyntheticShardProvider | None = None,
                 decoders: DecoderPair | None = None,
                 faults: FaultInjector | None = None) -> RecoveryExecutor:
        return RecoveryExecutor(
            state_root=self.state,
            binding=self.binding(),
            shard_provider=provider or self.provider(),
            decoders=decoders or self.decoders(),
            output_stage=MockOutputStage(self.contract["selected_expert_ids"]),
            faults=faults,
            mock_only=True,
        )

    def terminal(self) -> dict:
        return json.loads((self.state / "terminal.json").read_text())

    def ledger(self) -> int:
        return json.loads((self.state / "ledger.json").read_text())["value"]

    def test_successful_24_reads(self) -> None:
        terminal = self.executor().execute()
        self.assertEqual(terminal["classification"], "COMPLETE")
        self.assertEqual(terminal["consumed_read_count"], 24)
        self.assertEqual(terminal["packed_bytes"], 90_439_680)
        self.assertEqual(terminal["ledger_after"], 163)
        self.assertEqual(terminal["decoder_agreement_count"], 24)
        self.assertEqual(terminal["output_generation_status"], "SYNTHETIC_COMPLETE")
        self.assertEqual(len(list((self.state / "journal").glob("*.json"))), 24)

    def test_failure_before_execution_start_durability_opens_nothing(self) -> None:
        provider = self.provider()
        faults = FaultInjector({"before:execution_start": 1})
        with self.assertRaises(RecoveryExecutionError):
            self.executor(provider=provider, faults=faults).execute()
        self.assertEqual(provider.open_count, 0)
        self.assertFalse((self.state / "execution-start.json").exists())

    def test_failure_opening_shard_consumes_nothing(self) -> None:
        with self.assertRaises(RecoveryExecutionError):
            self.executor(provider=self.provider(fail_open=True)).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 0)
        self.assertEqual(self.ledger(), 139)

    def test_short_read_on_payload_one_consumes_nothing(self) -> None:
        with self.assertRaises(RecoveryExecutionError):
            self.executor(provider=self.provider(short_at=0)).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 0)

    def test_short_read_on_payload_n_preserves_prior_count(self) -> None:
        with self.assertRaises(RecoveryExecutionError):
            self.executor(provider=self.provider(short_at=7)).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 7)
        self.assertEqual(self.ledger(), 146)

    def test_failure_retaining_bytes_counts_consumed_read(self) -> None:
        faults = FaultInjector({"before:retention:4": 1})
        with self.assertRaises(RecoveryExecutionError):
            self.executor(faults=faults).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 5)
        self.assertEqual(self.ledger(), 144)

    def test_journal_failure_counts_consumed_and_retained(self) -> None:
        faults = FaultInjector({"before:journal:5": 1})
        with self.assertRaises(RecoveryExecutionError):
            self.executor(faults=faults).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 6)
        self.assertEqual(self.terminal()["retained_artifact_count"], 6)

    def test_ledger_write_failure_is_recoverable_from_receipts(self) -> None:
        faults = FaultInjector({"before:ledger:3": 1})
        with self.assertRaises(RecoveryExecutionError):
            self.executor(faults=faults).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 4)
        self.assertEqual(self.terminal()["ledger_after"], 143)

    def test_decoder_a_failure_stops_after_actual_read(self) -> None:
        with self.assertRaises(RecoveryExecutionError):
            self.executor(decoders=self.decoders(fail_a=2)).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 3)

    def test_decoder_b_failure_stops_after_actual_read(self) -> None:
        with self.assertRaises(RecoveryExecutionError):
            self.executor(decoders=self.decoders(fail_b=2)).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 3)

    def test_decoder_disagreement_is_terminal_and_stops_reads(self) -> None:
        provider = self.provider()
        with self.assertRaisesRegex(RecoveryExecutionError, "DUAL_DECODER_DISAGREEMENT"):
            self.executor(provider=provider, decoders=self.decoders(disagree=4)).execute()
        self.assertEqual(provider.read_count, 5)
        self.assertEqual(self.terminal()["decoder_agreement_count"], 4)

    def test_failure_after_23_successful_reads(self) -> None:
        with self.assertRaises(RecoveryExecutionError):
            self.executor(provider=self.provider(short_at=23)).execute()
        self.assertEqual(self.terminal()["consumed_read_count"], 23)
        self.assertEqual(self.ledger(), 162)

    def test_attempted_25th_read_is_rejected(self) -> None:
        cursor = InventoryCursor(self.inventory)
        for item in self.inventory:
            cursor.claim(item)
        with self.assertRaisesRegex(RecoveryExecutionError, "READ_BUDGET_EXHAUSTED"):
            cursor.claim(self.inventory[0])

    def test_second_shard_open_is_rejected(self) -> None:
        guard = OneShardOpenGuard(maximum=1)
        guard.claim(auth.SHARD_SHA)
        with self.assertRaisesRegex(RecoveryExecutionError, "SHARD_OPEN_BUDGET"):
            guard.claim(auth.SHARD_SHA)

    def test_duplicate_inventory_item_fails_before_open(self) -> None:
        provider = self.provider()
        inventory = copy.deepcopy(self.inventory)
        inventory[-1] = copy.deepcopy(inventory[0])
        binding = self.binding()
        object.__setattr__(binding, "inventory", inventory)
        with self.assertRaises(RecoveryExecutionError):
            RecoveryExecutor(self.state, binding, provider, self.decoders(),
                             MockOutputStage(self.contract["selected_expert_ids"]), mock_only=True).execute()
        self.assertEqual(provider.open_count, 0)

    def test_missing_inventory_item_fails_before_open(self) -> None:
        provider = self.provider()
        binding = self.binding()
        object.__setattr__(binding, "inventory", self.inventory[:-1])
        with self.assertRaises(RecoveryExecutionError):
            RecoveryExecutor(self.state, binding, provider, self.decoders(),
                             MockOutputStage(self.contract["selected_expert_ids"]), mock_only=True).execute()
        self.assertEqual(provider.open_count, 0)

    def test_wrong_byte_total_fails_before_open(self) -> None:
        provider = self.provider()
        binding = self.binding()
        changed = copy.deepcopy(self.inventory)
        changed[0]["packed_length"] += 1
        object.__setattr__(binding, "inventory", changed)
        with self.assertRaises(RecoveryExecutionError):
            RecoveryExecutor(self.state, binding, provider, self.decoders(),
                             MockOutputStage(self.contract["selected_expert_ids"]), mock_only=True).execute()
        self.assertEqual(provider.open_count, 0)

    def test_wrong_shard_identity_fails_before_open(self) -> None:
        provider = self.provider()
        binding = self.binding()
        object.__setattr__(binding, "shard_sha256", "0" * 64)
        with self.assertRaises(RecoveryExecutionError):
            RecoveryExecutor(self.state, binding, provider, self.decoders(),
                             MockOutputStage(self.contract["selected_expert_ids"]), mock_only=True).execute()
        self.assertEqual(provider.open_count, 0)

    def test_process_restart_terminalizes_and_never_resumes(self) -> None:
        faults = FaultInjector({"crash:after_journal:6": 1}, crash=True)
        with self.assertRaises(BaseException):
            self.executor(faults=faults).execute()
        recovered = self.executor(faults=FaultInjector()).recover_interrupted()
        self.assertEqual(recovered["classification"], "TERMINAL_FAILURE")
        self.assertEqual(recovered["consumed_read_count"], 7)
        with self.assertRaisesRegex(RecoveryExecutionError, "ATTEMPT_EXISTS"):
            self.executor().execute()

    def test_attempted_retry_of_terminal_event_fails(self) -> None:
        self.executor().execute()
        with self.assertRaisesRegex(RecoveryExecutionError, "ATTEMPT_EXISTS"):
            self.executor().execute()

    def test_retained_artifact_hash_mutation_is_detected(self) -> None:
        executor = self.executor()
        executor.execute()
        artifact = sorted((self.state / "retained-packed").glob("*.bin"))[0]
        artifact.chmod(0o600)
        artifact.write_bytes(b"mutated")
        artifact.chmod(0o400)
        with self.assertRaisesRegex(RecoveryExecutionError, "RETAINED_HASH_MISMATCH"):
            executor.reconcile(require_complete=True)

    def test_ledger_journal_mismatch_is_detected(self) -> None:
        executor = self.executor()
        executor.execute()
        ledger = json.loads((self.state / "ledger.json").read_text())
        ledger["value"] = 162
        (self.state / "ledger.json").write_text(json.dumps(ledger))
        with self.assertRaisesRegex(RecoveryExecutionError, "LEDGER_MISMATCH"):
            executor.reconcile(require_complete=True)

    def test_retained_count_journal_mismatch_is_detected(self) -> None:
        executor = self.executor()
        executor.execute()
        artifact = sorted((self.state / "retained-packed").glob("*.bin"))[0]
        artifact.chmod(0o600)
        artifact.unlink()
        with self.assertRaisesRegex(RecoveryExecutionError, "RETAINED_COUNT_MISMATCH"):
            executor.reconcile(require_complete=True)

    def test_terminal_banker_failure_can_only_be_terminalized(self) -> None:
        faults = FaultInjector({"before:terminal": 1})
        with self.assertRaises(RecoveryExecutionError):
            self.executor(faults=faults).execute()
        terminal = self.executor(faults=FaultInjector()).recover_interrupted()
        self.assertEqual(terminal["classification"], "TERMINAL_FAILURE")
        self.assertEqual(terminal["consumed_read_count"], 24)

    def test_real_path_firewall_rejects_non_synthetic_provider_in_tests(self) -> None:
        provider = self.provider()
        provider.synthetic_only = False
        with self.assertRaisesRegex(RecoveryExecutionError, "TEST_REAL_PATH_FIREWALL"):
            self.executor(provider=provider).execute()
        self.assertEqual(provider.open_count, 0)

    def test_retained_artifacts_are_read_only_and_not_symlinks(self) -> None:
        self.executor().execute()
        for path in (self.state / "retained-packed").glob("*.bin"):
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o222, 0)

    def test_same_retained_bytes_object_reaches_both_decoders(self) -> None:
        identities: list[tuple[int, int]] = []

        def a(payload: bytes, entry: dict) -> bytes:
            identities.append((entry["ordinal"], id(payload)))
            return b"same"

        def b(payload: bytes, entry: dict) -> bytes:
            identities.append((entry["ordinal"], id(payload)))
            return b"same"

        decoders = DecoderPair(a, b, "a", "b", auth.DECODER_CONTRACT_SHA)
        self.executor(decoders=decoders).execute()
        for ordinal in range(24):
            pair = [identity for item, identity in identities if item == ordinal]
            self.assertEqual(len(pair), 2)
            self.assertEqual(pair[0], pair[1])


if __name__ == "__main__":
    unittest.main()

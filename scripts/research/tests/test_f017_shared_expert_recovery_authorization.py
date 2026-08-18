from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.research import f017_shared_expert_recovery as M
from scripts.research.f017_canonical_expert_output_recovery_executor import RecoveryExecutionError
from scripts.research.validate_f017_shared_expert_recovery_authorization import load_json_strict, validate


class SharedRecoveryAuthorizationTests(unittest.TestCase):
    def test_inventory_exact(self) -> None:
        M.validate_inventory(list(M.INVENTORY))
        self.assertEqual(sum(row["packed_length"] for row in M.INVENTORY), 27_623_424)
        self.assertEqual([row["quantization"] for row in M.INVENTORY], ["Q5_K", "Q5_K", "Q6_K"])

    def test_inventory_mutations_fail(self) -> None:
        for mutation in ("extra", "missing", "duplicate", "wrong_shard", "wrong_total"):
            rows = [dict(row) for row in M.INVENTORY]
            if mutation == "extra": rows.append(dict(rows[-1], ordinal=3))
            elif mutation == "missing": rows.pop()
            elif mutation == "duplicate": rows[1] = dict(rows[0])
            elif mutation == "wrong_shard": rows[0]["shard_ordinal"] = 3
            else: rows[0]["packed_length"] += 1
            with self.assertRaises(RecoveryExecutionError):
                M.validate_inventory(rows)

    def test_q5_decoders_exact_and_independent(self) -> None:
        packed = bytearray(176)
        packed[0:2] = np.float16(1.0).tobytes()
        packed[2:4] = np.float16(0.5).tobytes()
        packed[4:16] = bytes(range(12))
        packed[16:48] = bytes((i * 7) & 255 for i in range(32))
        packed[48:] = bytes((i * 11) & 255 for i in range(128))
        self.assertEqual(M.q5_decoder_a(bytes(packed)), M.q5_decoder_b(bytes(packed)))
        self.assertNotEqual(M.Q5_A_IDENTITY, M.Q5_B_IDENTITY)

    def test_q6_decoders_exact_and_independent(self) -> None:
        packed = bytearray(210)
        packed[:192] = bytes((i * 13) & 255 for i in range(192))
        packed[192:208] = bytes(range(16))
        packed[208:210] = np.float16(0.25).tobytes()
        self.assertEqual(M.q6_decoder_a(bytes(packed)), M.q6_decoder_b(bytes(packed)))
        self.assertNotEqual(M.Q6_A_IDENTITY, M.Q6_B_IDENTITY)

    def test_synthetic_integration_matrix(self) -> None:
        result = M.run_synthetic_rehearsal()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["case_count"], 11)
        self.assertEqual(result["checkpoint_reads"], 0)
        self.assertEqual(result["real_payload_ledger"], 163)

    def test_decoder_disagreement_stops_before_next_read(self) -> None:
        q5 = M.run_synthetic_case(disagree="Q5_K")
        q6 = M.run_synthetic_case(disagree="Q6_K")
        self.assertEqual(q5["consumed_read_count"], 1)
        self.assertEqual(q5["ledger_after"], 164)
        self.assertEqual(q6["consumed_read_count"], 3)
        self.assertEqual(q6["ledger_after"], 166)

    def test_partial_failure_accounting(self) -> None:
        after_one = M.run_synthetic_case(fail_read_at=1)
        after_two = M.run_synthetic_case(fail_read_at=2)
        self.assertEqual((after_one["consumed_read_count"], after_one["ledger_after"]), (1, 164))
        self.assertEqual((after_two["consumed_read_count"], after_two["ledger_after"]), (2, 165))

    def test_one_open_guard(self) -> None:
        provider = M.SyntheticProvider(M._synthetic_blocks())
        handle = provider.open_shard(M.SHARD_SHA256)
        with self.assertRaisesRegex(RecoveryExecutionError, "SHARD_OPEN_BUDGET"):
            provider.open_shard(M.SHARD_SHA256)
        handle.close()

    def test_preflight_creates_no_state(self) -> None:
        before = M.LEDGER_BEFORE
        result = M.production_preflight()
        self.assertEqual(result["status"], "PRODUCTION_BINDINGS_RESOLVED")
        self.assertEqual(result["surfaces_resolved"], 14)
        self.assertFalse(result["attempt_record_created"])
        self.assertEqual(M.LEDGER_BEFORE, before)

    def test_execution_requires_external_release(self) -> None:
        source = (M.ROOT / "scripts/research/run_f017_shared_expert_recovery.py").read_text()
        self.assertIn("INDEPENDENT_EXECUTION_RELEASE_REQUIRED", source)
        self.assertFalse(json.loads(M.CONTRACT_PATH.read_text())["event"]["execution_authority"])

    def test_static_checkpoint_boundary(self) -> None:
        result = M.static_checkpoint_capability_audit()
        self.assertEqual(result["capability_boundary_count"], 1)
        self.assertEqual(result["sole_boundary"], "ProductionShardProvider")

    def test_validator(self) -> None:
        self.assertEqual(validate()["status"], "SHARED EXPERT RECOVERY AUTHORIZATION READY")

    def test_duplicate_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(RecoveryExecutionError, "DUPLICATE_KEY"):
                load_json_strict(path)


if __name__ == "__main__":
    unittest.main()

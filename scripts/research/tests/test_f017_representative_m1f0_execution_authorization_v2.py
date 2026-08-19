from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v2.json"
sys.path.insert(0, str(ROOT / "scripts/research"))


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


V = module(ROOT / "scripts/research/validate_f017_representative_m1f0_execution_authorization_v2.py", "m1f0_v2_validator")
E = module(ROOT / "scripts/research/f017_representative_m1f0_validation_executor.py", "m1f0_v2_executor")


class AuthorizationV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(AUTH.read_text())

    def reject(self, code: str, mutation) -> None:
        value = copy.deepcopy(self.document)
        mutation(value)
        self.assertIn(code, V.validate(value, ROOT))

    def test_baseline(self) -> None:
        self.assertEqual([], V.validate(self.document, ROOT))

    def test_schema_is_executable(self) -> None:
        self.reject("SCHEMA_REQUIRED:$.output_contract", lambda d: d.pop("output_contract"))

    def test_packed_hash(self) -> None:
        self.reject("INVENTORY_EXACT", lambda d: d["attention_payload_inventory"][0].update(packed_sha256="0" * 64))

    def test_decoded_hash(self) -> None:
        self.reject("INVENTORY_EXACT", lambda d: d["attention_payload_inventory"][1].update(decoded_sha256="0" * 64))

    def test_f32_hash_identity(self) -> None:
        def mutate(d):
            d["attention_payload_inventory"][0]["packed_sha256"] = "1" * 64
            d["attention_payload_inventory"][0]["decoded_sha256"] = "2" * 64
        self.reject("F32_PACKED_DECODED", mutate)

    def test_read_safety(self) -> None:
        self.reject("READ_CONTRACT", lambda d: d["read_contract"].update(retain_before_receipt=False))
        self.reject("READ_CONTRACT", lambda d: d["read_contract"].update(durable_receipt_before_next_read=False))
        self.reject("READ_CONTRACT", lambda d: d["read_contract"].update(additional_reads=True))

    def test_scope_safety(self) -> None:
        for field in ("real_event_authorized","checkpoint_access_authorized","expert_execution_authorized","shared_expert_execution_authorized","candidate_or_model_dispatch_authorized","M1_F_authorized","M1_G_authorized","P1_authorized"):
            self.reject("AUTHORIZATION_SCOPE", lambda d, field=field: d["authorization"].update({field: True}))

    def test_numerical_semantics(self) -> None:
        self.reject("RMSNORM", lambda d: d["execution_semantics"]["rmsnorm"].update(epsilon_source="f32(1e-6)"))
        self.reject("ATTENTION", lambda d: d["execution_semantics"]["attention"].update(residual="ADD_TWICE"))
        self.reject("ROUTER", lambda d: d["execution_semantics"]["router"].update(weights="2.5*P/D"))

    def test_output_and_surface(self) -> None:
        self.reject("OUTPUT_CONTRACT", lambda d: d["output_contract"].update(retained_only_reproduction_runs=2))
        self.reject("SURFACE_SEPARATION", lambda d: d["surface_separation"].update(direct_dprefix_inputs=True))
        self.reject("STOP_BOUNDARY", lambda d: d.update(stop_boundary="AFTER_EXPERT"))


class ExecutorV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.authorization = json.loads(AUTH.read_text())

    def execute(self, root: Path, *, short=None, disagreement=None, retained_fail=False, wrong_vocab=False):
        provider = E.SyntheticShardProvider(self.authorization["attention_payload_inventory"], short_read=short)
        executor = E.RepresentativeExecutor(
            self.authorization, provider, E.SyntheticDecoderPair(disagreement),
            E.SyntheticRetainedInputs(retained_fail), E.SyntheticComputationStage(wrong_vocab), root,
            synthetic=True,
        )
        return executor, provider, executor.execute()

    def test_exact_geometry_success_and_durability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "attempt"
            executor, provider, result = self.execute(root)
            self.assertEqual((result.terminal, result.consumed_reads, result.packed_bytes, result.ledger_after, result.shard_opens), ("COMPLETE", 9, 132900864, 175, 1))
            self.assertEqual(set(result.required_stage_sha256), set(E.CANONICAL_STAGES))
            for ordinal in range(9):
                receipt = root / "receipts" / f"{ordinal + 1:02d}.json"
                retained = root / "retained-packed" / f"{ordinal:02d}.bin"
                self.assertTrue(receipt.is_file() and retained.is_file())
                value = json.loads(receipt.read_text())
                self.assertEqual(value["packed_sha256"], E.sha_file(retained))
            with self.assertRaises(E.ExecutionError) as context:
                executor.execute()
            self.assertEqual(context.exception.code, "ATTEMPT_ALREADY_EXISTS")

    def test_short_read_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, provider, result = self.execute(Path(directory) / "attempt", short=4)
            self.assertEqual((result.terminal, result.reason, result.consumed_reads, result.ledger_after, provider.read_count), ("TERMINAL_FAILURE", "SHORT_READ", 4, 170, 5))

    def test_decoder_disagreement_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, result = self.execute(Path(directory) / "attempt", disagreement=1)
            self.assertEqual((result.reason, result.consumed_reads, result.ledger_after), ("DECODER_DISAGREEMENT", 2, 168))

    def test_retained_failure_is_preopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = E.SyntheticShardProvider(self.authorization["attention_payload_inventory"])
            executor = E.RepresentativeExecutor(self.authorization, provider, E.SyntheticDecoderPair(), E.SyntheticRetainedInputs(True), E.SyntheticComputationStage(), Path(directory) / "attempt", synthetic=True)
            with self.assertRaises(E.ExecutionError) as context:
                executor.execute()
            self.assertEqual(context.exception.code, "RETAINED_PREFLIGHT")
            self.assertEqual((provider.open_count, provider.read_count), (0, 0))

    def test_wrong_vocabulary_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _, _, result = self.execute(Path(directory) / "attempt", wrong_vocab=True)
            self.assertEqual((result.reason, result.consumed_reads, result.ledger_after), ("STAGE_VOCABULARY", 9, 175))

    def test_inventory_reorder_rejected_preopen(self) -> None:
        value = copy.deepcopy(self.authorization)
        value["attention_payload_inventory"][0], value["attention_payload_inventory"][1] = value["attention_payload_inventory"][1], value["attention_payload_inventory"][0]
        provider = E.SyntheticShardProvider(value["attention_payload_inventory"])
        with tempfile.TemporaryDirectory() as directory:
            executor = E.RepresentativeExecutor(value, provider, E.SyntheticDecoderPair(), E.SyntheticRetainedInputs(), E.SyntheticComputationStage(), Path(directory) / "attempt", synthetic=True)
            with self.assertRaises(E.ExecutionError) as context:
                executor.execute()
            self.assertEqual(context.exception.code, "INVENTORY_ORDER")
            self.assertEqual(provider.open_count, 0)

    def test_production_vocabulary_adapter(self) -> None:
        oracle = module(ROOT / "scripts/research/prepare_f017_m1f0_real_reference.py", "m1f0_oracle")
        import numpy as np
        hidden = np.asarray([((index * 17) % 257 - 128) / 128.0 for index in range(6144)], dtype=np.float32)
        result = oracle.synthetic_real_shaped_oracle(hidden)
        self.assertEqual(set(E.canonicalize_oracle_output(result)), set(E.CANONICAL_STAGES))

    def test_production_decoder_pair_small_blocks(self) -> None:
        pair = E.ProductionDecoderPair()
        fixtures = [
            ({"quantization":"F32","logical_shape":[8]}, bytes(32)),
            ({"quantization":"Q8_0","logical_shape":[32]}, bytes(34)),
            ({"quantization":"Q5_K","logical_shape":[256]}, bytes(176)),
        ]
        for entry, packed in fixtures:
            left, right = pair.decode_pair(entry, packed)
            self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()

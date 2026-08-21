from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts/research/f017_p1_admission.py"
SPEC = importlib.util.spec_from_file_location("f017_p1_admission", MODULE_PATH)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def fixture_contract() -> dict:
    manifest_path = ROOT / "docs/validation/glm52-checkpoint.json"
    manifest = json.loads(manifest_path.read_text())
    return {
        "schema": gate.SCHEMA,
        "status": "PREPARED_HUMAN_GATE_REQUIRED",
        "repository": {
            "branch": "feat/017-rust-native-inference-runtime",
            "execution_code_head": "1" * 40,
            "clean_worktree_required": True,
            "local_remote_parity_required": True,
        },
        "checkpoint": {
            "manifest_path": "docs/validation/glm52-checkpoint.json",
            "manifest_sha256": gate.sha256_path(manifest_path),
            "set_sha256": manifest["checkpoint_set_sha256"],
            "revision": "abc55e72527792c6e77069c99b4cb7de16fa9f23",
            "path_environment": "PULSARMLX_GLM_GGUF",
            "fallback": "PROHIBITED",
            "shards": [
                {"filename": row["filename"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
                for row in manifest["files"]
            ],
        },
        "runtime": {
            "mlx_version": "0.31.2",
            "mlx_c_version": "0.6.0",
            "require_native_env": "PULSAR_REQUIRE_NATIVE_MLX=1",
            "device_identity": "APPLE_M1_ULTRA",
            "stream_mode": "owned_device",
            "bound_files": [],
            "machine_files": [],
        },
        "memory": {
            "minimum_free_bytes": gate.MIN_FREE_BYTES,
            "source": "mach_vm_statistics64",
            "maximum_sample_age_seconds": gate.MAX_MEMORY_SAMPLE_AGE_SECONDS,
            "caller_supplied_values_authoritative": False,
        },
        "p1": {
            "prompt_token": gate.PROMPT_TOKEN,
            "expected_token": gate.EXPECTED_TOKEN,
            "scope": "ONE_BOUNDED_M1_ULTRA_P1",
            "attempts": 1,
            "retries": 0,
            "resume": False,
            "mandatory_stop": "AFTER_FIRST_GENERATED_TOKEN_AND_TERMINALIZATION",
            "argv": ["/bound/p1-runner", "--checkpoint", "{checkpoint_root}", "--receipt", "{receipt_path}"],
            "receipt_schema": "pulsarmlx.f017.p1-execution-receipt/1.0.0",
        },
        "accounting": {
            "required_counters": sorted(gate.REQUIRED_COUNTERS),
            "observation": "MECHANICAL_PRE_POST_FROM_BOUND_EXECUTOR",
            "stream_authority_fields": [
                "semantic_stream_origin",
                "native_handle_owned",
                "deallocation_responsibility",
            ],
        },
        "authorization": {
            "schema": gate.AUTH_SCHEMA,
            "approval_statement": gate.APPROVAL_STATEMENT,
            "normal_validation_can_authorize": False,
            "live_authorization_present": False,
        },
        "state": {
            "lifecycle": ["PREPARED", "AUTHORIZED", "CONSUMING", "CONSUMED_TERMINAL"],
            "exclusive_attempt_claim": True,
            "durable_ownership": True,
            "immutable_prior_state": True,
            "automatic_retry": False,
        },
        "prohibitions": {
            "full_model_inference": True,
            "second_p1": True,
            "p2_or_broader": True,
            "automatic_retry": True,
            "checkpoint_fallback": True,
        },
    }


class ContractTests(unittest.TestCase):
    def test_control_contract_passes_without_checkpoint_payload(self) -> None:
        gate.validate_contract(fixture_contract(), ROOT)

    def assert_mutation_rejected(self, mutate) -> None:
        value = fixture_contract()
        mutate(value)
        with self.assertRaises(gate.AdmissionError):
            gate.validate_contract(value, ROOT)

    def test_authority_and_scope_mutations_fail_closed(self) -> None:
        mutations = [
            lambda x: x["repository"].__setitem__("execution_code_head", "2" * 39),
            lambda x: x["repository"].__setitem__("branch", "main"),
            lambda x: x["checkpoint"].__setitem__("set_sha256", "0" * 64),
            lambda x: x["checkpoint"].__setitem__("fallback", "ALLOWED"),
            lambda x: x["runtime"].__setitem__("mlx_version", "0.32.0"),
            lambda x: x["runtime"].__setitem__("mlx_c_version", "0.5.0"),
            lambda x: x["runtime"].__setitem__("require_native_env", ""),
            lambda x: x["memory"].__setitem__("minimum_free_bytes", gate.MIN_FREE_BYTES - 1),
            lambda x: x["memory"].__setitem__("caller_supplied_values_authoritative", True),
            lambda x: x["p1"].__setitem__("prompt_token", 1),
            lambda x: x["p1"].__setitem__("expected_token", 2),
            lambda x: x["p1"].__setitem__("attempts", 2),
            lambda x: x["p1"].__setitem__("retries", 1),
            lambda x: x["p1"].__setitem__("resume", True),
            lambda x: x["p1"].__setitem__("mandatory_stop", "REMOVED"),
            lambda x: x["accounting"]["required_counters"].remove("callback_count"),
            lambda x: x["accounting"].__setitem__("observation", "CALLER_SUPPLIED"),
            lambda x: x["accounting"]["stream_authority_fields"].remove("native_handle_owned"),
            lambda x: x["authorization"].__setitem__("live_authorization_present", True),
            lambda x: x["authorization"].__setitem__("normal_validation_can_authorize", True),
            lambda x: x["state"].__setitem__("automatic_retry", True),
            lambda x: x["prohibitions"].__setitem__("full_model_inference", False),
            lambda x: x["prohibitions"].__setitem__("second_p1", False),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_mutation_rejected(mutation)

    def test_duplicate_json_keys_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}\n')
            with self.assertRaises(gate.AdmissionError):
                gate.load_json(path)


class MemoryTests(unittest.TestCase):
    @mock.patch.object(gate.platform, "system", return_value="Darwin")
    def test_memory_is_mechanically_sampled(self, _system) -> None:
        output = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 1048576.\nPages inactive: 1.\nPages speculative: 1.\n"
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, output, ""))
        sample = gate.sample_free_memory_macos(runner=runner, now=lambda: 100.0)
        self.assertGreaterEqual(sample["free_bytes"], gate.MIN_FREE_BYTES)
        gate.require_fresh_memory_sample(sample, 104.0)
        runner.assert_called_once()

    @mock.patch.object(gate.platform, "system", return_value="Darwin")
    def test_low_and_stale_memory_fail(self, _system) -> None:
        output = "Mach Virtual Memory Statistics: (page size of 4096 bytes)\nPages free: 1.\nPages inactive: 1.\nPages speculative: 1.\n"
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, output, ""))
        with self.assertRaises(gate.AdmissionError):
            gate.sample_free_memory_macos(runner=runner)
        sample = {
            "source": "mach_vm_statistics64",
            "free_bytes": gate.MIN_FREE_BYTES,
            "observed_at_unix": 1.0,
        }
        with self.assertRaises(gate.AdmissionError):
            gate.require_fresh_memory_sample(sample, 7.0)


class OneShotTests(unittest.TestCase):
    def authorization(self) -> dict:
        return {
            "schema": gate.AUTH_SCHEMA,
            "authorization_id": "auth-1",
            "contract_sha256": "a" * 64,
            "reviewed_head": "1" * 40,
            "attempt_id": "attempt-1",
            "approval_statement": gate.APPROVAL_STATEMENT,
            "operator_identity": "human-operator",
            "real_event_authorized": True,
            "attempts": 1,
            "retries": 0,
            "resume": False,
            "disposition": "EXECUTE_P1_ONCE_THEN_MANDATORY_STOP",
        }

    def test_authorization_replay_and_concurrent_claim_fail(self) -> None:
        authorization = self.authorization()
        gate.validate_authorization(authorization, "a" * 64, "1" * 40)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = gate.claim_attempt(root, authorization)
            self.assertTrue((attempt / "attempt-start.json").is_file())
            with self.assertRaises(gate.AdmissionError):
                gate.claim_attempt(root, authorization)
            terminal = gate.terminalize(attempt, authorization, "SYNTHETIC_SUCCESS")
            self.assertEqual(gate.load_json(terminal)["retry_permitted"], False)
            with self.assertRaises(gate.AdmissionError):
                gate.claim_attempt(root, authorization)

    def test_inert_stale_and_forged_authorizations_rejected(self) -> None:
        mutations = [
            lambda x: x.__setitem__("real_event_authorized", False),
            lambda x: x.__setitem__("contract_sha256", "b" * 64),
            lambda x: x.__setitem__("reviewed_head", "2" * 40),
            lambda x: x.__setitem__("attempts", 2),
            lambda x: x.__setitem__("retries", 1),
            lambda x: x.__setitem__("resume", True),
            lambda x: x.__setitem__("approval_statement", "forged"),
            lambda x: x.__setitem__("disposition", "CONTINUE_FULL_INFERENCE"),
        ]
        for mutation in mutations:
            value = self.authorization()
            mutation(value)
            with self.assertRaises(gate.AdmissionError):
                gate.validate_authorization(value, "a" * 64, "1" * 40)

    def test_execution_receipt_requires_all_mechanical_counters(self) -> None:
        before = {name: 0 for name in gate.REQUIRED_COUNTERS}
        after = copy.deepcopy(before)
        receipt = {
            "schema": "pulsarmlx.f017.p1-execution-receipt/1.0.0",
            "prompt_token": gate.PROMPT_TOKEN,
            "generated_tokens": [gate.EXPECTED_TOKEN],
            "mandatory_stop_observed": True,
            "accounting_before": before,
            "accounting_after": after,
        }
        gate.validate_execution_receipt(receipt, fixture_contract())
        broken = copy.deepcopy(receipt)
        del broken["accounting_after"]["native_owned_stream_freed"]
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract())
        broken = copy.deepcopy(receipt)
        broken["accounting_after"]["owned_stream_freed"] = 1
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract())
        broken = copy.deepcopy(receipt)
        broken["generated_tokens"] = [gate.EXPECTED_TOKEN, 1]
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract())


if __name__ == "__main__":
    unittest.main()

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
            "executor_path": "scripts/research/f017_p1_admission.py",
            "executor_sha256": gate.sha256_path(MODULE_PATH),
            "argv": [str(MODULE_PATH), "--checkpoint", "{checkpoint_root}", "--receipt", "{receipt_path}"],
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
            "root": "/Users/mhedhli/.local/share/pulsarmlx/f017/m1-ultra-p1-admission-v1",
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
            lambda x: x["p1"].__setitem__("executor_sha256", "0" * 64),
            lambda x: x["p1"]["argv"].__setitem__(0, "/tmp/unbound-executor"),
            lambda x: x["accounting"]["required_counters"].remove("callback_count"),
            lambda x: x["accounting"].__setitem__("observation", "CALLER_SUPPLIED"),
            lambda x: x["accounting"]["stream_authority_fields"].remove("native_handle_owned"),
            lambda x: x["authorization"].__setitem__("live_authorization_present", True),
            lambda x: x["authorization"].__setitem__("normal_validation_can_authorize", True),
            lambda x: x["state"].__setitem__("root", "/tmp/caller-selected-p1-state"),
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


class RuntimeIdentityTests(unittest.TestCase):
    def _runner(self, stdout: str = "Apple M1 Ultra\n", returncode: int = 0):
        def run(argv, **kwargs):
            self.assertEqual(argv, ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"])
            if kwargs.get("check") and returncode:
                raise subprocess.CalledProcessError(returncode, argv)
            return subprocess.CompletedProcess(argv, returncode, stdout, "")
        return run

    @mock.patch.dict(os.environ, {"PULSAR_REQUIRE_NATIVE_MLX": "1"})
    def test_exact_m1_ultra_and_arm64_accept(self) -> None:
        gate.verify_runtime_machine(fixture_contract(), runner=self._runner(), machine=lambda: "arm64")

    @mock.patch.dict(os.environ, {"PULSAR_REQUIRE_NATIVE_MLX": "1"})
    def test_other_brands_and_architectures_reject(self) -> None:
        for brand in ["Apple M1 Max\n", "Apple M2 Ultra\n", "arm\n", "\n", "Apple M1 Ultra spoof\n"]:
            with self.subTest(brand=brand), self.assertRaises(gate.AdmissionError):
                gate.verify_runtime_machine(fixture_contract(), runner=self._runner(brand), machine=lambda: "arm64")
        with self.assertRaises(gate.AdmissionError):
            gate.verify_runtime_machine(fixture_contract(), runner=self._runner(), machine=lambda: "x86_64")
        with self.assertRaises(gate.AdmissionError):
            gate.verify_runtime_machine(fixture_contract(), runner=self._runner(returncode=1), machine=lambda: "arm64")


class StateRootTests(unittest.TestCase):
    def contract_for(self, root: Path) -> dict:
        contract = fixture_contract()
        contract["state"]["root"] = str(root)
        return contract

    def test_clean_absent_or_private_existing_root_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            absent = parent / "state"
            gate.verify_state_root(self.contract_for(absent), absent)
            absent.mkdir(mode=0o700)
            gate.verify_state_root(self.contract_for(absent), absent)

    def test_alternate_and_symlinked_roots_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            expected = parent / "state"
            with self.assertRaises(gate.AdmissionError):
                gate.verify_state_root(self.contract_for(expected), parent / "alternate")
            target = parent / "target"
            target.mkdir(mode=0o700)
            leaf = parent / "leaf"
            leaf.symlink_to(target, target_is_directory=True)
            with self.assertRaises(gate.AdmissionError):
                gate.verify_state_root(self.contract_for(leaf), leaf)
            real_parent = parent / "real-parent"
            real_parent.mkdir(mode=0o700)
            alias_parent = parent / "alias-parent"
            alias_parent.symlink_to(real_parent, target_is_directory=True)
            aliased = alias_parent / "state"
            with self.assertRaises(gate.AdmissionError):
                gate.verify_state_root(self.contract_for(aliased), aliased)


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

    def test_fresh_authorization_cannot_launch_second_p1(self) -> None:
        first = self.authorization()
        second = self.authorization()
        second["authorization_id"] = "auth-2"
        second["attempt_id"] = "attempt-2"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate.claim_attempt(root, first)
            with self.assertRaisesRegex(gate.AdmissionError, "already been consumed"):
                gate.claim_attempt(root, second)

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
            "authorization_id": "auth-1",
            "attempt_id": "attempt-1",
            "contract_sha256": "a" * 64,
            "executor_sha256": fixture_contract()["p1"]["executor_sha256"],
            "git_head": "1" * 40,
            "checkpoint_identity": {
                "manifest_sha256": fixture_contract()["checkpoint"]["manifest_sha256"],
                "set_sha256": fixture_contract()["checkpoint"]["set_sha256"],
            },
            "runtime_identity": {
                "mlx_version": "0.31.2",
                "mlx_c_version": "0.6.0",
                "machine_file_sha256": {},
            },
            "machine_identity": {"architecture": "arm64", "brand": "Apple M1 Ultra"},
            "prompt_token": gate.PROMPT_TOKEN,
            "generated_tokens": [gate.EXPECTED_TOKEN],
            "expected_token": gate.EXPECTED_TOKEN,
            "mandatory_stop_observed": True,
            "execution_result": "EXPECTED_TOKEN_MATCH",
            "terminal_state": "COMPLETE_MANDATORY_STOP",
            "started_at_unix": 1.0,
            "completed_at_unix": 2.0,
            "accounting_before": before,
            "accounting_after": after,
        }
        gate.validate_execution_receipt(receipt, fixture_contract(), self.authorization(), "a" * 64)
        broken = copy.deepcopy(receipt)
        del broken["accounting_after"]["native_owned_stream_freed"]
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract(), self.authorization(), "a" * 64)
        broken = copy.deepcopy(receipt)
        broken["accounting_after"]["owned_stream_freed"] = 1
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract(), self.authorization(), "a" * 64)
        broken = copy.deepcopy(receipt)
        broken["generated_tokens"] = [gate.EXPECTED_TOKEN, 1]
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract(), self.authorization(), "a" * 64)
        broken = copy.deepcopy(receipt)
        broken["unknown"] = 1
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract(), self.authorization(), "a" * 64)
        broken = copy.deepcopy(receipt)
        broken["accounting_after"]["callback_count"] = True
        with self.assertRaises(gate.AdmissionError):
            gate.validate_execution_receipt(broken, fixture_contract(), self.authorization(), "a" * 64)


if __name__ == "__main__":
    unittest.main()

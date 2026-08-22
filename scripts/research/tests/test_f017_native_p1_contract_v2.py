#!/usr/bin/env python3
"""Mutation gates for the exact native bounded-P1 contract and human boundary."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json"
EXECUTOR = ROOT / "specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1"
AUTHORIZER = ROOT / "scripts/research/f017_native_p1_authorization.py"
INERT = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-native-bounded-p1-human-approval-inert-v1.json"


def load_authorizer():
    spec = importlib.util.spec_from_file_location("f017_native_p1_authorization", AUTHORIZER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExactContract(unittest.TestCase):
    def validate(self, document: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            portable = copy.deepcopy(document)
            exact_state_root = json.loads(CONTRACT.read_text())["state_root"]
            if portable["state_root"] == exact_state_root:
                portable["state_root"] = str(Path(directory).resolve() / "state")
            candidate = Path(directory) / "contract.json"
            candidate.write_text(json.dumps(portable) + "\n")
            return subprocess.run(
                [str(EXECUTOR), "validate-contract", str(candidate), str(ROOT)],
                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

    def validate_machine(self, document: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", suffix=".json") as candidate:
            json.dump(document, candidate)
            candidate.flush()
            environment = os.environ.copy()
            environment.update(document["runtime"]["environment"])
            return subprocess.run(
                [str(EXECUTOR), "machine-preflight", candidate.name, str(ROOT)],
                cwd=ROOT, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

    def test_exact_contract_is_instantiable_without_checkpoint_access(self) -> None:
        self.assertEqual(
            hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
            "91248295cac2f078e47576e5f22b4f7d0457bf9b3b11645c8e46406b8b1a2e03",
        )
        result = self.validate(json.loads(CONTRACT.read_text()))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_load_bearing_mutations_fail_closed(self) -> None:
        base = json.loads(CONTRACT.read_text())

        def mutate(path: tuple[object, ...], value: object) -> None:
            candidate = copy.deepcopy(base)
            cursor: object = candidate
            for part in path[:-1]:
                cursor = cursor[part]  # type: ignore[index]
            cursor[path[-1]] = value  # type: ignore[index]
            self.assertNotEqual(self.validate(candidate).returncode, 0, path)

        mutations = [
            (("execution_code_head",), "bad"),
            (("executor", "sha256"), "0" * 64),
            (("authorities", "d0", "sha256"), "0" * 64),
            (("authorities", "d3_5_result", "sha256"), "0" * 64),
            (("authorities", "historical_master_terminal_value"), 176),
            (("checkpoint", "checkpoint_set_sha256"), "0" * 64),
            (("checkpoint", "fallback"), "ALLOWED"),
            (("checkpoint", "shards", 0, "sha256"), "0" * 64),
            (("runtime", "mlx_version"), "0.32.1"),
            (("runtime", "minimum_available_memory_bytes"), 1),
            (("one_shot", "prompt_token"), 1),
            (("one_shot", "attempt_id"), "../../ESCAPED"),
            (("one_shot", "expected_token"), 1),
            (("one_shot", "attempts"), 2),
            (("one_shot", "retries"), 1),
            (("one_shot", "resume"), True),
            (("one_shot", "mandatory_stop"), False),
            (("one_shot", "receipt_schema"), "stale"),
            (("live_authorization_present",), True),
            (("normal_validation_can_authorize",), True),
            (("state_root",), "relative/state"),
        ]
        for path, value in mutations:
            with self.subTest(path=path):
                mutate(path, value)

        missing = copy.deepcopy(base)
        missing["code_manifest"].pop()
        self.assertNotEqual(self.validate(missing).returncode, 0)
        duplicate = copy.deepcopy(base)
        duplicate["code_manifest"].append(duplicate["code_manifest"][0])
        self.assertNotEqual(self.validate(duplicate).returncode, 0)
        runtime_drift = copy.deepcopy(base)
        runtime_drift["runtime"]["dylibs"][0]["sha256"] = "0" * 64
        self.assertNotEqual(self.validate_machine(runtime_drift).returncode, 0)

    def test_inert_human_template_cannot_authorize_or_create_state(self) -> None:
        state = Path(json.loads(CONTRACT.read_text())["state_root"])
        self.assertFalse(state.exists())
        result = subprocess.run(
            ["/usr/bin/python3", str(AUTHORIZER), "authorize", str(INERT), str(CONTRACT)],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(state.exists())

    def test_operator_authorized_final_reviewer_vocabulary_is_exact(self) -> None:
        authorizer = load_authorizer()
        accepted = {
            "path": "review.json",
            "sha256": "a" * 64,
            "reviewer_model": "claude-opus-5",
            "verdict": "ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1",
            "blocking_count": 0,
            "non_blocking_required_count": 0,
        }
        self.assertEqual(authorizer.validate_final_review(accepted), accepted)
        for key, value in [
            ("reviewer_model", "claude-fable-5"),
            ("verdict", "ACCEPT"),
            ("blocking_count", 1),
            ("non_blocking_required_count", 1),
            ("blocking_count", False),
        ]:
            candidate = copy.deepcopy(accepted)
            candidate[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                authorizer.validate_final_review(candidate)


if __name__ == "__main__":
    unittest.main()

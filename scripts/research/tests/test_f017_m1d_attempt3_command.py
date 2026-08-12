import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

import f017_m1d_execution_config as contract


def artifact(role: str, path: str) -> dict:
    return {
        "path_kind": "repository_relative",
        "symbolic_path": path,
        "content_sha256": contract.sha256((ROOT / path).read_bytes()),
        "logical_role": role,
    }


class Attempt3CommandAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.temp = Path(self.temporary.name)
        self.package = self.temp / "private-package"
        self.package.mkdir()
        self.environment = self.temp / "environment.json"
        self.environment.write_text('{"fixture":true}\n')
        self.checkpoint = self.temp / "checkpoint.json"
        self.checkpoint.write_text('{"checkpoint":"fake"}\n')
        self.shard = self.temp / "fake-shard-2.bin"
        self.shard.write_bytes(b"checkpoint-free")

    def tearDown(self):
        self.temporary.cleanup()

    def binding(self) -> dict:
        artifacts = {
            role: artifact(role, path)
            for role, (path, _) in contract.EXPECTED_REPOSITORY_ARTIFACTS.items()
        }
        preparer_sha = artifacts["real_reference_preparer"]["content_sha256"]
        return {
            "schema": "pulsarmlx.f017.m1d-attempt-3-authorization-binding",
            "schema_version": "1.0.0",
            "status": "authorized_exactly_one_attempt_3_not_executed",
            "attempt": 3,
            "attempt_consumed": False,
            "runtime_sha": contract.repository_identity(ROOT),
            "tooling_sha": contract.repository_identity(ROOT),
            "activation_fixture": artifact("activation_fixture", contract.ACTIVATION_PATH),
            "activation_payload_sha256": contract.ACTIVATION_PAYLOAD_SHA256,
            "provenance": {
                "activation_generation_source_sha256": "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984",
                "fixture_finalization_source_sha256": "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92",
                "real_reference_preparer_sha256": preparer_sha,
            },
            "repository_artifacts": artifacts,
            "prior_evidence": contract.PRIOR,
            "checkpoint_bindings": contract.CHECKPOINT,
            "runner": {
                "mode": "fixture_projection",
                "validation_mode": "golden_strict",
                "stream_mode": "owned_device",
                "numerical_mode": "production_mlx_tier_b",
                "memory_floor_bytes": 1,
            },
            "execution": {
                "conceptual_projection_count": 1,
                "production_repeat_count": 10,
                "native_dispatch_count": 10,
                "all_repeat_hashes_equal_required": True,
                "oracle_finalized_before_candidate_required": True,
                "preflight_consumes_attempt": False,
            },
        }

    def local(self) -> dict:
        return {
            "repository_root": str(ROOT),
            "package_root": str(self.package),
            "environment_manifest": {
                "path_kind": "absolute_private_local",
                "path": str(self.environment),
                "content_sha256": contract.sha256(self.environment.read_bytes()),
            },
            "checkpoint_manifest": {
                "path_kind": "absolute_private_local",
                "path": str(self.checkpoint),
                "content_sha256": contract.sha256(self.checkpoint.read_bytes()),
            },
            "target_shard": {
                "path_kind": "absolute_private_local",
                "path": str(self.shard),
                "basename": self.shard.name,
                "ordinal": 2,
                "byte_size": self.shard.stat().st_size,
                "sha256": contract.sha256(self.shard.read_bytes()),
            },
            "oracle_output": str(self.package / "oracle.json"),
            "package_output": str(self.package / "package.json"),
            "evidence_output": str(self.temp / "evidence.json"),
        }

    def render(self, binding=None, local=None, *, expect=True):
        binding_path = self.temp / "binding.json"
        local_path = self.temp / "local.json"
        output = self.temp / "execution.json"
        rendered = self.temp / "render.json"
        binding_path.write_text(json.dumps(binding or self.binding(), indent=2) + "\n")
        local_path.write_text(json.dumps(local or self.local(), indent=2) + "\n")
        result = subprocess.run(
            [
                sys.executable,
                str(RESEARCH / "prepare_f017_m1d_attempt3_execution.py"),
                "--authorization-binding", str(binding_path),
                "--local-inputs", str(local_path),
                "--output-config", str(output),
                "--output-render", str(rendered),
            ],
            cwd=self.temp,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode == 0, expect, result.stderr)
        return result, output, rendered

    def test_preflight_renders_exact_config_without_consuming_attempt(self):
        _, output, rendered = self.render()
        digest = contract.sha256(output.read_bytes())
        document = contract.validate_config_file(output, digest, check_outputs_absent=True)
        self.assertEqual(document["activation_fixture"]["symbolic_path"], contract.ACTIVATION_PATH)
        result = json.loads(rendered.read_text())
        self.assertEqual(result["status"], contract.READY)
        self.assertFalse(result["attempt_consumed"])
        self.assertFalse(result["checkpoint_accessed"])

    def test_historical_wrong_path_and_same_bytes_elsewhere_fail(self):
        binding = self.binding()
        binding["activation_fixture"]["symbolic_path"] = contract.WRONG_HISTORICAL_ACTIVATION_PATH
        self.render(binding=binding, expect=False)

        copied = self.temp / "copied-oracle.json"
        copied.write_bytes((ROOT / contract.ACTIVATION_PATH).read_bytes())
        binding = self.binding()
        binding["activation_fixture"]["symbolic_path"] = "copied-oracle.json"
        self.render(binding=binding, expect=False)

    def test_one_character_hash_path_attempt_and_provenance_mutations_fail(self):
        mutations = []
        wrong = self.binding()
        wrong["activation_fixture"]["symbolic_path"] += "x"
        mutations.append(wrong)
        wrong = self.binding()
        wrong["activation_fixture"]["content_sha256"] = "0" * 64
        mutations.append(wrong)
        wrong = self.binding()
        wrong["attempt"] = 2
        mutations.append(wrong)
        wrong = self.binding()
        wrong["provenance"]["real_reference_preparer_sha256"] = "0" * 64
        mutations.append(wrong)
        wrong = self.binding()
        wrong["repository_artifacts"].pop("tier_b_contract")
        mutations.append(wrong)
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                sub = self.temp / f"case-{index}"
                sub.mkdir()
                original = self.temp
                self.temp = sub
                try:
                    self.render(binding=mutation, local=self.local(), expect=False)
                finally:
                    self.temp = original

    def test_duplicate_keys_and_config_mutation_fail(self):
        path = self.temp / "duplicate.json"
        path.write_text('{"schema":"a","schema":"b"}\n')
        with self.assertRaises(ValueError):
            contract.load_json_no_duplicates(path)
        _, output, _ = self.render()
        digest = contract.sha256(output.read_bytes())
        output.chmod(0o600)
        output.write_bytes(output.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            contract.validate_config_file(output, digest)

    def test_local_input_cannot_add_cli_or_environment_override(self):
        local = self.local()
        local["activation_fixture"] = contract.WRONG_HISTORICAL_ACTIVATION_PATH
        self.render(local=local, expect=False)


if __name__ == "__main__":
    unittest.main()

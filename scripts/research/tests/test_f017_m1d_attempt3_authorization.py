import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))
import validate_f017_m1d_attempt3_authorization as validator
import f017_m1d_execution_config as execution


class Attempt3AuthorizationValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "docs/architecture/reviews").mkdir(parents=True)
        handoff = self.root / validator.HANDOFF_PATH
        handoff.write_text("attempt 3 handoff\n")
        for role, (path, _) in execution.EXPECTED_REPOSITORY_ARTIFACTS.items():
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / path).read_bytes())
        preparer = self.root / "scripts/research/prepare_f017_m1d_real_reference.py"
        self.runtime = "1" * 40
        self.tooling = "2" * 40

    def tearDown(self):
        self.temp.cleanup()

    def valid(self):
        artifacts = {}
        for role, (path, _) in execution.EXPECTED_REPOSITORY_ARTIFACTS.items():
            artifacts[role] = {
                "path_kind": "repository_relative",
                "symbolic_path": path,
                "content_sha256": validator.sha(self.root / path),
                "logical_role": role,
            }
        return {
            "schema": "pulsarmlx.f017.m1d-attempt-3-authorization-binding",
            "schema_version": "1.0.0",
            "status": "authorized_exactly_one_attempt_3_not_executed",
            "attempt": 3,
            "attempt_consumed": False,
            "runtime_sha": self.runtime,
            "tooling_sha": self.tooling,
            "handoff": {"path": validator.HANDOFF_PATH, "sha256": validator.sha(self.root / validator.HANDOFF_PATH)},
            "execution_config_sha256": "3" * 64,
            "activation_fixture": {
                "path_kind": "repository_relative",
                "symbolic_path": execution.ACTIVATION_PATH,
                "content_sha256": execution.ACTIVATION_ARTIFACT_SHA256,
                "logical_role": "activation_fixture",
            },
            "activation_payload_sha256": execution.ACTIVATION_PAYLOAD_SHA256,
            "provenance": {
                "activation_generation_source_sha256": "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984",
                "fixture_finalization_source_sha256": "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92",
                "real_reference_preparer_sha256": validator.sha(self.root / "scripts/research/prepare_f017_m1d_real_reference.py"),
            },
            "repository_artifacts": artifacts,
            "prior_evidence": copy.deepcopy(execution.PRIOR),
            "checkpoint_bindings": copy.deepcopy(execution.CHECKPOINT),
            "path_contract": {"version":"f017-m1d-artifact-path-resolution-v1", "sha256":"40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d"},
            "package_schema": {"version":"2.0.0", "sha256":"eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a"},
            "runner": {"mode":"real_projection", "validation_mode":"golden_strict", "stream_mode":"owned_device", "numerical_mode":"production_mlx_tier_b", "memory_floor_bytes":17179869184},
            "execution": {"conceptual_projection_count":1, "production_repeat_count":10, "native_dispatch_count":10, "all_repeat_hashes_equal_required":True, "oracle_finalized_before_candidate_required":True, "preflight_consumes_attempt":False},
            "stop_policy": {"no_auto_retry":True, "mandatory_stop_before_m1_e":True},
        }

    def test_complete_binding_is_eligible(self):
        validator.validate(self.valid(), self.root, self.runtime, self.tooling, validate_packet=False)

    def test_every_command_controlling_field_fails_closed(self):
        mutations = []
        for field in ("runtime_sha", "tooling_sha", "execution_config_sha256", "activation_payload_sha256"):
            value = self.valid(); value[field] = "0" * len(value[field]); mutations.append(value)
        value = self.valid(); value["activation_fixture"]["symbolic_path"] = execution.WRONG_HISTORICAL_ACTIVATION_PATH; mutations.append(value)
        value = self.valid(); value["attempt"] = 2; mutations.append(value)
        value = self.valid(); value["attempt_consumed"] = True; mutations.append(value)
        value = self.valid(); value["prior_evidence"]["attempt_2"] = "0" * 64; mutations.append(value)
        value = self.valid(); value["repository_artifacts"]["tier_b_contract"]["content_sha256"] = "0" * 64; mutations.append(value)
        value = self.valid(); value["runner"]["mode"] = "fixture_projection"; mutations.append(value)
        value = self.valid(); value["provenance"] = {"generator_sha256": "0" * 64}; mutations.append(value)
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(validator.ValidationError):
                validator.validate(mutation, self.root, self.runtime, self.tooling, validate_packet=False)


if __name__ == "__main__":
    unittest.main()

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))
SPEC = importlib.util.spec_from_file_location(
    "m1e_preparer_v3", RESEARCH / "prepare_f017_m1e_real_reference.py"
)
PREPARER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PREPARER)

SHA = "0" * 64
GIT = "1" * 40
CONTRACT_PATH = PREPARER.PREPARER_INPUT_CONTRACT


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repository_artifact(role: str, path: str = CONTRACT_PATH) -> dict[str, str]:
    return {
        "path_kind": "repository_relative",
        "symbolic_path": path,
        "content_sha256": digest(ROOT / path),
        "logical_role": role,
    }


def tensor(role: str) -> dict[str, object]:
    values = {
        "gate": ("blk.3.ffn_gate_exps.weight", "IQ2_XXS", [6144, 2048, 256], [2048, 6144], 3423197024, 3244032, 1584, "42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354"),
        "up": ("blk.3.ffn_up_exps.weight", "IQ2_XXS", [6144, 2048, 256], [2048, 6144], 4268636000, 3244032, 1584, "011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119"),
        "down": ("blk.3.ffn_down_exps.weight", "IQ3_XXS", [2048, 6144, 256], [6144, 2048], 2203342688, 4816896, 784, "1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1"),
    }[role]
    return {
        "role": role,
        "name": values[0],
        "layer": 3,
        "expert": 15,
        "quantization": values[1],
        "gguf_shape": values[2],
        "logical_matrix_shape": values[3],
        "shard_ordinal": 2,
        "offset": values[4],
        "packed_length": values[5],
        "packed_row_width": values[6],
        "catalog_entry_sha256": values[7],
        "decoder_contract_sha256": PREPARER.DECODER_CONTRACT_SHA256,
        "path_kind": "bounded_checkpoint_range",
        "allowed_read_count": 1,
    }


def valid() -> dict[str, object]:
    artifacts = {
        role: repository_artifact(role, path)
        for role, path in PREPARER.REPOSITORY_ARTIFACT_PATHS.items()
    }
    return {
        "schema": PREPARER.EXECUTION_CONFIG_SCHEMA,
        "schema_version": "3.0.0",
        "status": PREPARER.EXECUTION_READY,
        "attempt": 3,
        "attempt_consumed": False,
        "compiled_runtime_sha": GIT,
        "tooling_sha": GIT,
        "authorization_head_sha": GIT,
        "trusted_repository_identity": {
            "contract_version": "f017-trusted-repository-identity-v2",
            "contract_sha256": SHA,
            "compiled_runtime_sha": GIT,
            "tooling_sha": GIT,
            "authorization_head_sha": GIT,
            "runtime_drift_classification_sha256": SHA,
        },
        "executable_identity": {
            "sha256": SHA,
            "build_profile": "release",
            "architecture": "aarch64",
            "feature_flags": ["pulsar_native_mlx"],
        },
        "repository_root": {"path_kind": "absolute_private_local", "path": str(ROOT), "identity": GIT},
        "package_root": {"path_kind": "absolute_private_local", "path": "/private/tmp/m1e-v3", "identity": "m1e_attempt_3_private_package_root"},
        "activation_fixture": repository_artifact("activation_fixture", PREPARER.ACTIVATION_PATH),
        "activation_payload_sha256": PREPARER.ACTIVATION_PAYLOAD_SHA256,
        "repository_artifacts": artifacts,
        "local_artifacts": {
            "environment_manifest": {"path_kind": "absolute_private_local", "path": "/private/tmp/environment", "content_sha256": SHA},
            "checkpoint_manifest": {"path_kind": "absolute_private_local", "path": "/private/tmp/checkpoint", "content_sha256": SHA},
            "runner_binary": {"path_kind": "absolute_private_local", "path": "/private/tmp/runner", "content_sha256": SHA},
            "oracle_launcher": {"path_kind": "absolute_private_local", "path": "/private/tmp/uv", "content_sha256": SHA},
            "target_shard": {"path_kind": "absolute_private_local", "path": "/private/tmp/shard", "ordinal": 2, "basename": "fixture.gguf", "byte_size": 1, "content_sha256": SHA},
            "oracle_output": "/private/tmp/m1e-v3/oracle.json",
            "package_output": "/private/tmp/m1e-v3/package.json",
            "attempt_state_output": "/private/tmp/m1e-v3/state.json",
            "preflight_evidence_output": "/private/tmp/m1e-v3/preflight.json",
            "evidence_output": "/private/tmp/m1e-v3/evidence.json",
        },
        "prior_evidence": copy.deepcopy(PREPARER.PRIOR_EVIDENCE),
        "checkpoint_bindings": copy.deepcopy(PREPARER.CHECKPOINT_BINDINGS),
        "expert": {"layer": 3, "expert": 15, "symbolic_id": "blk.3.expert.15"},
        "tensors": [tensor("gate"), tensor("up"), tensor("down")],
        "runner": {"mode": "fixture_expert", "memory_floor_bytes": 1},
        "execution": {"conceptual_expert_count": 1, "repeat_count": 10, "native_dispatch_count": 30, "maximum_payload_count": 3, "maximum_positional_reads": 3, "maximum_shard_opens": 1, "compressed_byte_budget": 11304960, "auto_retry": False, "stop_before_m1_f": True},
    }


class PreparerV3Tests(unittest.TestCase):
    def assert_rejected(self, document: dict[str, object]):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            PREPARER.validate_execution_config_v3(document)

    def test_valid_v3_is_accepted(self):
        PREPARER.validate_execution_config_v3(valid())

    def test_schema_downgrade_future_missing_malformed_and_mixed_are_rejected(self):
        for version in ("2.0.0", "4.0.0", "3.1.0", None, "three"):
            document = valid()
            if version is None:
                del document["schema_version"]
            else:
                document["schema_version"] = version
            self.assert_rejected(document)
        document = valid()
        document["runtime_sha"] = document.pop("compiled_runtime_sha")
        self.assert_rejected(document)
        document = valid()
        document["schema_version"] = "2.0.0"
        self.assert_rejected(document)

    def test_duplicate_schema_key_is_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"schema_version":"3.0.0","schema_version":"2.0.0"}', object_pairs_hook=PREPARER.no_duplicates)

    def test_v2_rejection_occurs_before_any_payload_open(self):
        document = valid()
        document["schema_version"] = "2.0.0"
        document["attempt"] = 2
        raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_bytes(raw)
            with mock.patch.object(PREPARER.os, "open", side_effect=AssertionError("payload open")):
                with self.assertRaisesRegex(ValueError, "execution config identity mismatch"):
                    PREPARER.prepare_from_config(path, hashlib.sha256(raw).hexdigest())

    def test_identity_attempt_unknown_and_stale_evidence_are_rejected(self):
        mutations = []
        for field in ("compiled_runtime_sha", "tooling_sha", "authorization_head_sha"):
            document = valid(); document[field] = "2" * 40; mutations.append(document)
        document = valid(); document["trusted_repository_identity"]["authorization_head_sha"] = "2" * 40; mutations.append(document)
        document = valid(); document["executable_identity"]["sha256"] = "2" * 64; document["local_artifacts"]["runner_binary"]["content_sha256"] = "3" * 64; mutations.append(document)
        document = valid(); document["attempt"] = 2; mutations.append(document)
        document = valid(); document["prior_evidence"]["m1_e_attempt_2"] = "2" * 64; mutations.append(document)
        document = valid(); document["unreviewed_field"] = True; mutations.append(document)
        for document in mutations:
            self.assert_rejected(document)

    def test_config_hash_decoder_activation_scaffold_and_tier_b_substitutions_are_rejected(self):
        document = valid(); document["tensors"][2]["decoder_contract_sha256"] = "2" * 64; self.assert_rejected(document)
        document = valid(); document["activation_payload_sha256"] = "2" * 64; self.assert_rejected(document)
        for role in ("decoder_contract", "scaffold_contract", "tier_b_contract"):
            document = valid(); document["repository_artifacts"][role]["unexpected"] = True; self.assert_rejected(document)
        raw = json.dumps(valid(), sort_keys=True, separators=(",", ":")).encode()
        self.assertNotEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw + b" ").hexdigest())

    def test_stale_preparer_and_bound_contract_content_fail_against_repository(self):
        document = valid()
        document["repository_artifacts"]["real_reference_preparer"] = repository_artifact(
            "real_reference_preparer", "scripts/research/prepare_f017_m1e_real_reference.py"
        )
        PREPARER.validate_execution_config_v3(document, ROOT)
        document["repository_artifacts"]["real_reference_preparer"]["content_sha256"] = "2" * 64
        self.assert_rejected_with_root(document)

    def assert_rejected_with_root(self, document):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            PREPARER.validate_execution_config_v3(document, ROOT)

    def test_identity_metadata_is_numerically_inert(self):
        original = valid()
        changed = copy.deepcopy(original)
        changed["compiled_runtime_sha"] = "2" * 40
        changed["tooling_sha"] = "3" * 40
        changed["authorization_head_sha"] = "4" * 40
        changed["attempt"] = 99
        self.assertEqual(
            PREPARER.oracle_semantic_projection(original),
            PREPARER.oracle_semantic_projection(changed),
        )

    def test_preparer_independence_surface_has_no_candidate_dependency(self):
        source = (RESEARCH / "prepare_f017_m1e_real_reference.py").read_text().lower()
        for forbidden in ("import ctypes", "import cffi", "import mlx", "from mlx", "subprocess"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

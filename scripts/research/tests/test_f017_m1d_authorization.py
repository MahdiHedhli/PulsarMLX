from __future__ import annotations

import copy
import hashlib
import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/validate_f017_m1d_authorization.py"
SPEC = importlib.util.spec_from_file_location("m1d_authorization", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def file_sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def valid_document() -> dict:
    binding = validator.load_json_no_duplicates(
        ROOT / "docs/architecture/reviews/evidence/f017-m1-d-authorization-binding-v1.json"
    )
    return {
        "schema": "pulsarmlx.f017.m1d-authorization-binding",
        "schema_version": "1.0.0",
        "status": "authorized_exactly_one_not_executed",
        "runtime_sha": validator.RUNTIME_SHA,
        "previous_tooling_sha": validator.PREVIOUS_TOOLING_SHA,
        "tooling_sha": binding["tooling_sha"],
        "handoff": {
            "path": "docs/architecture/reviews/f017-m1-d-real-projection-handoff.md",
            "sha256": file_sha("docs/architecture/reviews/f017-m1-d-real-projection-handoff.md"),
        },
        "direct_bindings": {
            **validator.EXPECTED_HASHES,
            "repeat_integrity": file_sha(validator.CONTRACT_PATHS["repeat_integrity"]),
            "oracle_ordering": file_sha(validator.CONTRACT_PATHS["oracle_ordering"]),
        },
        "contract_versions": copy.deepcopy(validator.CONTRACT_VERSIONS),
        "provenance": copy.deepcopy(validator.PROVENANCE),
        "activation": {
            "payload_sha256": validator.ACTIVATION_SHA,
            "element_count": 6144,
            "dtype": "little_endian_f32",
            "seed": 17017004,
            "prng": "PCG64",
            "python": "3.13.13",
            "numpy": "2.4.5",
            "bytes_changed_by_finalization_remediation": False,
        },
        "execution": {
            "conceptual_projection_count": 1,
            "production_repeat_count": 10,
            "all_repeat_hashes_equal_required": True,
            "oracle_finalized_before_candidate_required": True,
            "mandatory_stop_before_m1_e": True,
        },
    }


class AuthorizationValidatorTests(unittest.TestCase):
    def test_complete_binding_is_eligible(self) -> None:
        validator.validate_document(valid_document(), ROOT, validate_git=False)

    def test_every_execution_binding_fails_closed(self) -> None:
        base = valid_document()
        mutations = []
        for field in ("runtime_sha", "previous_tooling_sha", "tooling_sha"):
            value = copy.deepcopy(base)
            value[field] = "0" * 40
            mutations.append(value)
        value = copy.deepcopy(base)
        value["handoff"]["sha256"] = "0" * 64
        mutations.append(value)
        value = copy.deepcopy(base)
        del value["handoff"]["sha256"]
        mutations.append(value)
        for field in base["direct_bindings"]:
            value = copy.deepcopy(base)
            value["direct_bindings"][field] = "0" * 64
            mutations.append(value)
        for role in base["provenance"]:
            value = copy.deepcopy(base)
            value["provenance"][role]["sha256"] = "0" * 64
            mutations.append(value)
        for contract in base["contract_versions"]:
            value = copy.deepcopy(base)
            value["contract_versions"][contract] = "stale"
            mutations.append(value)
        value = copy.deepcopy(base)
        value["activation"]["payload_sha256"] = "0" * 64
        mutations.append(value)
        for document in mutations:
            with self.assertRaises(validator.ValidationError):
                validator.validate_document(document, ROOT, validate_git=False)

    def test_generic_generator_field_is_rejected_as_ambiguous(self) -> None:
        value = valid_document()
        value["provenance"] = {"generator_sha256": "29c5c51a" + "0" * 56}
        with self.assertRaisesRegex(validator.ValidationError, "ambiguous"):
            validator.validate_document(value, ROOT, validate_git=False)

    def test_stale_real_tooling_ancestor_is_rejected(self) -> None:
        value = valid_document()
        value["tooling_sha"] = validator.PREVIOUS_TOOLING_SHA
        with self.assertRaises(validator.ValidationError):
            validator.validate_document(value, ROOT, validate_git=True)

    def test_duplicate_keys_are_rejected(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema":"a","schema":"b"}')
            with self.assertRaisesRegex(validator.ValidationError, "duplicate key"):
                validator.load_json_no_duplicates(path)

    def test_activation_bytes_are_identical_before_and_after_finalization_change(self) -> None:
        old = subprocess.run(
            ["git", "show", "bfca0b3f836039173e5c8d98745be99811e2d244:specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json"],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        import json

        historical = json.loads(old)
        current = json.loads((ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json").read_text())
        self.assertEqual(historical["activation"]["bytes_hex"], current["activation"]["bytes_hex"])
        self.assertEqual(current["activation"]["sha256"], validator.ACTIVATION_SHA)


if __name__ == "__main__":
    unittest.main()

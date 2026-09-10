#!/usr/bin/env python3
"""Whole-inventory tests for the active CI input manifest.

The extracted loop below is the production consumer's actual digest check. The
schema, path, role, cardinality, and historical-substitution checks are test-side
guards that make the manifest contract explicit; they are not attributed to the
production consumer.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
CONSUMER = ROOT / "scripts/research/tests/f017_primary_confined_ci_v1.py"
MANIFEST = ROOT / "scripts/ci/f017_primary_ci_inputs_v1.json"
MEASUREMENT = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json"
VALIDATOR = "scripts/research/validate_f017_v11_execution_authority_v1.py"
SECONDARY_WRAPPER = "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py"
SCHEMA = "f017.current-primary-ci-inputs/1"
ACTIVE_ROLE = "PROTECTED_RUNTIME_AND_ORIGINAL_FIXTURE_CONTENT_PINS_CARRIED_FORWARD_UNCHANGED"
CONTROLLER_ROLE = "ACTUAL_COMMITTED_HEAD_AND_CONTENTS_BOUND_IN_EXTERNAL_QUALIFICATION_RECEIPT"
HISTORICAL_ROLE = "MEASUREMENT_V8_REMAINS_BOUND_TO_F35D_NOT_CURRENT_CONTROLLERS"
SOURCE_BASE = "6f59d9db93e92afed142b543a0e2fc19e0362bb4"
HISTORICAL = "f35d341110c67377200ad353ab56a3cf38615a73"
MEASUREMENT_SHA256 = "c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414"
STALE_VALIDATOR_SHA256 = "5a123ec88b805df77d00be1f42a6e6f13dcb7c6c69b06f09deb102761872628c"
CURRENT_VALIDATOR_SHA256 = "dec34ba2157f04dcea6e64347bb96dc4288bfc8d676fdb1b10801c5146602253"
FROZEN_WRAPPER_SHA256 = "2dad5b54bdc875d981dd5d5f7cf6eb8c78c83f751925a063e5423f04b11a0d22"


_consumer = runpy.run_path(str(CONSUMER))
need = _consumer["need"]
sha = _consumer["sha"]


def compile_real_active_loop():
    """Extract the exact active-input loop from the production consumer."""
    tree = ast.parse(CONSUMER.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    loop = next(
        node
        for node in main.body
        if isinstance(node, ast.For)
        and any(
            isinstance(item, ast.Constant) and item.value == "CURRENT_ACTIVE_SOURCE_DRIFT:"
            for item in ast.walk(node)
        )
    )
    function = ast.FunctionDef(
        name="real_active_loop",
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=name) for name in ("policy", "SOURCE", "need", "sha")],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[
            ast.Assign(
                targets=[ast.Name(id="current", ctx=ast.Store())],
                value=ast.Dict(keys=[], values=[]),
            ),
            loop,
            ast.Return(value=ast.Name(id="current", ctx=ast.Load())),
        ],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace: dict = {}
    exec(compile(module, str(CONSUMER), "exec"), namespace)
    return namespace["real_active_loop"]


real_active_loop = compile_real_active_loop()


def validate_whole_active_manifest(policy: dict, source: Path) -> dict[str, bytes]:
    """Apply test-side guards, then run the real consumer loop over all rows."""
    need(
        set(policy)
        == {"schema", "source_base", "input_role", "controller_identity", "historical_identity", "inputs"},
        "INPUT_POLICY_SCHEMA",
    )
    need(policy["schema"] == SCHEMA, "INPUT_POLICY_SCHEMA")
    need(policy["source_base"] == SOURCE_BASE, "INPUT_POLICY_BASE")
    need(policy["input_role"] == ACTIVE_ROLE, "INPUT_POLICY_ROLE")
    need(policy["controller_identity"] == CONTROLLER_ROLE, "CONTROLLER_ROLE")
    need(policy["historical_identity"] == HISTORICAL_ROLE, "HISTORICAL_ROLE_SEPARATION")
    rows = policy["inputs"]
    need(type(rows) is list and len(rows) == 38, "ACTIVE_INVENTORY_38")
    need(
        all(
            type(row) is dict
            and set(row) == {"repository_path", "sha256", "view_path"}
            and all(type(row[key]) is str for key in row)
            for row in rows
        ),
        "INPUT_ROW_SCHEMA",
    )
    repository_paths = [row["repository_path"] for row in rows]
    view_paths = [row["view_path"] for row in rows]
    need(len(repository_paths) == len(set(repository_paths)), "DUPLICATE_REPOSITORY_PATH")
    need(len(view_paths) == len(set(view_paths)), "DUPLICATE_VIEW_PATH")
    need(repository_paths.count(VALIDATOR) == 1, "VALIDATOR_CARDINALITY")
    for row in rows:
        relative = Path(row["repository_path"])
        view = Path(row["view_path"])
        need(not relative.is_absolute() and ".." not in relative.parts, "ACTIVE_ENTRY_PATH")
        need(not view.is_absolute() and ".." not in view.parts, "ACTIVE_VIEW_PATH")
        target = (source / relative).resolve()
        need(target.is_relative_to(source.resolve()), "ACTIVE_ENTRY_PATH")
        if row["repository_path"] == SECONDARY_WRAPPER:
            need(row["sha256"] != FROZEN_WRAPPER_SHA256, "HISTORICAL_SUBSTITUTION")
    return real_active_loop(policy, source, need, sha)


class ActiveInputProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(MANIFEST.read_text())

    def mutated(self) -> dict:
        return copy.deepcopy(self.policy)

    @staticmethod
    def row(policy: dict, path: str) -> dict:
        return next(row for row in policy["inputs"] if row["repository_path"] == path)

    def test_real_consumer_rule_is_still_the_rule_under_test(self) -> None:
        tree = ast.parse(CONSUMER.read_text())
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("CURRENT_ACTIVE_SOURCE_DRIFT:", literals)
        self.assertEqual(_consumer["SOURCE_BASE"], SOURCE_BASE)

    def test_all_38_corrected_active_rows_pass_together(self) -> None:
        current = validate_whole_active_manifest(self.policy, ROOT)
        self.assertEqual(len(current), 38)
        self.assertEqual(sha(current[VALIDATOR]), CURRENT_VALIDATOR_SHA256)

    def test_stale_validator_binding_reproduces_known_failure(self) -> None:
        policy = self.mutated()
        self.row(policy, VALIDATOR)["sha256"] = STALE_VALIDATOR_SHA256
        with self.assertRaisesRegex(ValueError, "CURRENT_ACTIVE_SOURCE_DRIFT:" + VALIDATOR):
            validate_whole_active_manifest(policy, ROOT)

    def test_wrong_digest_fails_real_loop(self) -> None:
        policy = self.mutated()
        self.row(policy, VALIDATOR)["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "CURRENT_ACTIVE_SOURCE_DRIFT:" + VALIDATOR):
            validate_whole_active_manifest(policy, ROOT)

    def test_wrong_path_fails_test_side_guard(self) -> None:
        policy = self.mutated()
        self.row(policy, VALIDATOR)["repository_path"] = "../outside.py"
        with self.assertRaisesRegex(ValueError, "VALIDATOR_CARDINALITY"):
            validate_whole_active_manifest(policy, ROOT)

    def test_wrong_role_fails_test_side_guard(self) -> None:
        policy = self.mutated()
        policy["input_role"] = HISTORICAL_ROLE
        with self.assertRaisesRegex(ValueError, "INPUT_POLICY_ROLE"):
            validate_whole_active_manifest(policy, ROOT)

    def test_historical_substitution_fails_test_side_guard(self) -> None:
        policy = self.mutated()
        self.row(policy, SECONDARY_WRAPPER)["sha256"] = FROZEN_WRAPPER_SHA256
        with self.assertRaisesRegex(ValueError, "HISTORICAL_SUBSTITUTION"):
            validate_whole_active_manifest(policy, ROOT)

    def test_changed_source_bytes_fail_real_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            for row in self.policy["inputs"]:
                target = source / row["repository_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / row["repository_path"]).read_bytes())
            validator = source / VALIDATOR
            validator.write_bytes(validator.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "CURRENT_ACTIVE_SOURCE_DRIFT:" + VALIDATOR):
                validate_whole_active_manifest(self.policy, source)

    def test_missing_entry_fails_test_side_guard(self) -> None:
        policy = self.mutated()
        policy["inputs"] = [row for row in policy["inputs"] if row["repository_path"] != VALIDATOR]
        with self.assertRaisesRegex(ValueError, "ACTIVE_INVENTORY_38"):
            validate_whole_active_manifest(policy, ROOT)

    def test_duplicate_entry_fails_test_side_guard(self) -> None:
        policy = self.mutated()
        policy["inputs"][-1] = copy.deepcopy(policy["inputs"][0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_REPOSITORY_PATH"):
            validate_whole_active_manifest(policy, ROOT)

    def test_frozen_measurement_remains_exact_git_only_evidence(self) -> None:
        body = MEASUREMENT.read_bytes()
        self.assertEqual(hashlib.sha256(body).hexdigest(), MEASUREMENT_SHA256)
        measurement = json.loads(body)
        self.assertEqual(measurement["implementation_head"], HISTORICAL)
        self.assertEqual(len(measurement["measured_paths"]), 36)
        for row in measurement["measured_paths"]:
            historical = subprocess.run(
                ["git", "show", f"{HISTORICAL}:{row['path']}"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
            ).stdout
            self.assertEqual(hashlib.sha256(historical).hexdigest(), row["sha256"])


if __name__ == "__main__":
    unittest.main()

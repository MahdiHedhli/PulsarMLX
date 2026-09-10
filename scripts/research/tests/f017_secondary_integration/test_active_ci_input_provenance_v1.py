#!/usr/bin/env python3
"""Focused mutation tests for the secondary wrapper's active CI input pin."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
CONSUMER = ROOT / "scripts/research/tests/f017_primary_confined_ci_v1.py"
MANIFEST = ROOT / "scripts/ci/f017_primary_ci_inputs_v1.json"
TARGET = "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py"
ACTIVE_ROLE = "PROTECTED_RUNTIME_AND_ORIGINAL_FIXTURE_CONTENT_PINS_CARRIED_FORWARD_UNCHANGED"
HISTORICAL_ROLE = "MEASUREMENT_V8_REMAINS_BOUND_TO_F35D_NOT_CURRENT_CONTROLLERS"
SOURCE_BASE = "6f59d9db93e92afed142b543a0e2fc19e0362bb4"
OLD_SHA256 = "97e640e1e0fa4da36e7aed407c612ea991681422316f527a585e7c70eb6c8c55"
CURRENT_SHA256 = "77b3b473f3744c88f37ab18175df6ace4f6e44d6b15aeefa1832aa3913834586"
HISTORICAL_SHA256 = "2dad5b54bdc875d981dd5d5f7cf6eb8c78c83f751925a063e5423f04b11a0d22"


_consumer = runpy.run_path(str(CONSUMER))
need = _consumer["need"]
sha = _consumer["sha"]


def compile_real_active_loop():
    """Extract and compile the consumer's exact active-input loop."""
    tree = ast.parse(CONSUMER.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    loop = next(
        node for node in main.body
        if isinstance(node, ast.For)
        and any(isinstance(item, ast.Constant) and item.value == "CURRENT_ACTIVE_SOURCE_DRIFT:" for item in ast.walk(node))
    )
    function = ast.FunctionDef(
        name="real_active_loop",
        args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=name) for name in ("policy", "SOURCE", "need", "sha")], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=[ast.Assign(targets=[ast.Name(id="current", ctx=ast.Store())], value=ast.Dict(keys=[], values=[])), loop, ast.Return(value=ast.Name(id="current", ctx=ast.Load()))],
        decorator_list=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace: dict = {}
    exec(compile(module, str(CONSUMER), "exec"), namespace)
    return namespace["real_active_loop"]


real_active_loop = compile_real_active_loop()


def validate_scoped_active_entry(policy: dict, source: Path) -> bytes:
    """Apply the real consumer's current-byte hash rule to one admitted row."""
    need(policy.get("schema") == "f017.current-primary-ci-inputs/1", "INPUT_POLICY_SCHEMA")
    need(policy.get("source_base") == SOURCE_BASE, "INPUT_POLICY_BASE")
    need(policy.get("input_role") == ACTIVE_ROLE, "INPUT_POLICY_ROLE")
    need(policy.get("historical_identity") == HISTORICAL_ROLE, "HISTORICAL_ROLE_SEPARATION")
    rows = policy.get("inputs")
    need(type(rows) is list, "INPUT_ROWS")
    need(all(type(row) is dict and set(row) == {"repository_path", "sha256", "view_path"} for row in rows), "INPUT_ROW_SCHEMA")
    repository_paths = [row["repository_path"] for row in rows]
    view_paths = [row["view_path"] for row in rows]
    need(len(repository_paths) == len(set(repository_paths)), "DUPLICATE_REPOSITORY_PATH")
    need(len(view_paths) == len(set(view_paths)), "DUPLICATE_VIEW_PATH")
    matches = [row for row in rows if row["repository_path"] == TARGET]
    need(len(matches) == 1, "ACTIVE_ENTRY_CARDINALITY")
    row = matches[0]
    need(row["view_path"] == TARGET, "ACTIVE_ENTRY_ROLE")
    need(row["sha256"] != HISTORICAL_SHA256, "HISTORICAL_SUBSTITUTION")
    relative = Path(row["repository_path"])
    need(not relative.is_absolute() and ".." not in relative.parts, "ACTIVE_ENTRY_PATH")
    target = (source / relative).resolve()
    need(target.is_relative_to(source.resolve()), "ACTIVE_ENTRY_PATH")
    scoped = {"inputs": [row]}
    current = real_active_loop(scoped, source, need, sha)
    body = current[TARGET]
    return body


class ActiveInputProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(MANIFEST.read_text())
        cls.body = (ROOT / TARGET).read_bytes()

    def mutated(self) -> dict:
        return copy.deepcopy(self.policy)

    def target(self, policy: dict) -> dict:
        return next(row for row in policy["inputs"] if row["repository_path"] == TARGET)

    def test_real_consumer_rule_is_still_the_rule_under_test(self) -> None:
        tree = ast.parse(CONSUMER.read_text())
        literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertIn("CURRENT_ACTIVE_SOURCE_DRIFT:", literals)
        self.assertEqual(_consumer["SOURCE_BASE"], SOURCE_BASE)
        self.assertEqual(sha(self.body), CURRENT_SHA256)

    def test_corrected_active_binding_passes(self) -> None:
        self.assertEqual(validate_scoped_active_entry(self.policy, ROOT), self.body)

    def test_old_binding_reproduces_known_failure(self) -> None:
        policy = self.mutated()
        self.target(policy)["sha256"] = OLD_SHA256
        with self.assertRaisesRegex(ValueError, "CURRENT_ACTIVE_SOURCE_DRIFT"):
            validate_scoped_active_entry(policy, ROOT)

    def test_wrong_digest_fails(self) -> None:
        policy = self.mutated()
        self.target(policy)["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "CURRENT_ACTIVE_SOURCE_DRIFT"):
            validate_scoped_active_entry(policy, ROOT)

    def test_wrong_path_fails(self) -> None:
        policy = self.mutated()
        self.target(policy)["repository_path"] = "../outside.py"
        with self.assertRaisesRegex(ValueError, "ACTIVE_ENTRY_CARDINALITY"):
            validate_scoped_active_entry(policy, ROOT)

    def test_wrong_role_fails(self) -> None:
        policy = self.mutated()
        policy["input_role"] = policy["historical_identity"]
        with self.assertRaisesRegex(ValueError, "INPUT_POLICY_ROLE"):
            validate_scoped_active_entry(policy, ROOT)

    def test_historical_substitution_fails(self) -> None:
        policy = self.mutated()
        self.target(policy)["sha256"] = HISTORICAL_SHA256
        with self.assertRaisesRegex(ValueError, "HISTORICAL_SUBSTITUTION"):
            validate_scoped_active_entry(policy, ROOT)

    def test_changed_source_bytes_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            target = source / TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(self.body + b"\n")
            with self.assertRaisesRegex(ValueError, "CURRENT_ACTIVE_SOURCE_DRIFT"):
                validate_scoped_active_entry(self.policy, source)

    def test_missing_entry_fails(self) -> None:
        policy = self.mutated()
        policy["inputs"] = [row for row in policy["inputs"] if row["repository_path"] != TARGET]
        with self.assertRaisesRegex(ValueError, "ACTIVE_ENTRY_CARDINALITY"):
            validate_scoped_active_entry(policy, ROOT)

    def test_duplicate_entry_fails(self) -> None:
        policy = self.mutated()
        policy["inputs"].append(copy.deepcopy(self.target(policy)))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_REPOSITORY_PATH"):
            validate_scoped_active_entry(policy, ROOT)


if __name__ == "__main__":
    unittest.main()

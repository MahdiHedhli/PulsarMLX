from __future__ import annotations

import ast
import copy
import inspect
import json
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from f017_event06_durable_installation_transaction_v1 import (
    RACE_FAMILIES,
    DurableTransactionResult,
)
from f017_event06_production_installation_v1 import ProductionInstallationError
from f017_event06_production_installation_v2 import (
    FutureGoCapabilityV2,
    commit_production_installation_v2,
    produce_future_go_capability,
    validate_future_go_capability,
)
from f017_event06_readiness_authority_v3 import ValidatedEvent06ReadinessV3
from qualify_f017_event06_sequence09_no_access_v1 import qualify

ROOT = Path(__file__).resolve().parents[3]


def test_sequence09_no_access_qualification() -> None:
    result = qualify()
    assert result["result"] == "PASS"
    assert result["readiness_reconstructions"] == 20
    assert result["readiness_unique_digest_count"] == 1
    assert result["installation_reconstructions"] == 20
    assert result["installation_unique_identity_set_count"] == 1
    assert result["mutation_rejections"] >= 324
    assert result["unexpected_passes"] == 0
    assert result["installation_failure_outcomes"] == 16
    assert result["race_families"] == 10
    assert result["transaction_successes_synthetic_non_authority"] == 10
    assert result["transaction_failures"] == 10
    assert result["production_capability_instances"] == 0
    assert result["production_commit_success_calls"] == 0
    assert result["terminal"] == "PACKAGE_START_ELIGIBLE_DRY_STOP"
    assert result["checkpoint_root_resolved"] is False
    assert result["checkpoint_access"] == 0
    assert result["numerical_operations"] == 0


def test_successor_seals_are_repository_only() -> None:
    for cls in (
        ValidatedEvent06ReadinessV3,
        FutureGoCapabilityV2,
        DurableTransactionResult,
    ):
        with pytest.raises(TypeError):
            cls()


def test_future_go_and_production_commit_surface_is_explicit() -> None:
    assert tuple(inspect.signature(produce_future_go_capability).parameters) == (
        "raw",
        "prepared",
        "readiness",
    )
    assert tuple(inspect.signature(commit_production_installation_v2).parameters) == (
        "prepared",
        "capability",
    )
    assert len(RACE_FAMILIES) == 10


def test_successor_modules_preserve_historical_sources() -> None:
    expected = {
        "scripts/research/f017_event06_readiness_authority_v2.py": "86796c3f1f9fa4d85c3618340b88b4dd8fb316b251913a6cbf026a1186b38eb3",
        "scripts/research/f017_event06_production_installation_v1.py": "13579b0d5b8d27e84b2eb8c5e91e85eac648798b24847169458370da670a6d6d",
    }
    import hashlib

    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_successor_modules_have_no_dynamic_import_or_checkpoint_literal() -> None:
    paths = (
        ROOT / "scripts/research/f017_event06_readiness_authority_v3.py",
        ROOT / "scripts/research/f017_event06_production_installation_v2.py",
        ROOT / "scripts/research/f017_event06_durable_installation_transaction_v1.py",
        ROOT / "scripts/research/f017_corrected_oracle_authorization_v12_v3.py",
    )
    forbidden_imports = {"mmap", "socket", "ctypes", "importlib", "multiprocessing"}
    forbidden_calls = {
        "eval",
        "exec",
        "compile",
        "globals",
        "locals",
        "vars",
        "__import__",
    }
    findings: list[str] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "GLM-5.2" not in source
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                findings.extend(
                    alias.name
                    for alias in node.names
                    if alias.name.split(".")[0] in forbidden_imports
                )
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] in forbidden_imports:
                    findings.append(node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in forbidden_calls:
                    findings.append(node.func.id)
    assert findings == []


def test_execution_facing_imports_are_interposed_before_load() -> None:
    code = r"""
import builtins
import mmap
import os
from pathlib import Path
census = {"open": 0, "stat": 0, "resolve": 0, "mmap": 0}
real_open = os.open
real_builtin_open = builtins.open
real_stat = Path.stat
real_resolve = Path.resolve
def forbidden(value):
    text = str(value)
    return "GLM-5.2" in text or "original-checkpoint" in text.lower()
def guarded_open(path, *args, **kwargs):
    if forbidden(path):
        census["open"] += 1
        raise AssertionError("checkpoint open")
    return real_open(path, *args, **kwargs)
def guarded_builtin(path, *args, **kwargs):
    if forbidden(path):
        census["open"] += 1
        raise AssertionError("checkpoint open")
    return real_builtin_open(path, *args, **kwargs)
def guarded_stat(self, *args, **kwargs):
    if forbidden(self):
        census["stat"] += 1
        raise AssertionError("checkpoint stat")
    return real_stat(self, *args, **kwargs)
def guarded_resolve(self, *args, **kwargs):
    if forbidden(self):
        census["resolve"] += 1
        raise AssertionError("checkpoint resolve")
    return real_resolve(self, *args, **kwargs)
def guarded_mmap(*args, **kwargs):
    census["mmap"] += 1
    raise AssertionError("mmap")
os.open = guarded_open
builtins.open = guarded_builtin
Path.stat = guarded_stat
Path.resolve = guarded_resolve
mmap.mmap = guarded_mmap
import f017_event06_production_installation_v2
import qualify_f017_event06_sequence09_no_access_v1
assert census == {"open": 0, "stat": 0, "resolve": 0, "mmap": 0}
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "scripts/research")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_committed_interposed_qualification_harness() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "scripts/research")
    completed = subprocess.run(
        [
            sys.executable,
            str(
                ROOT
                / "scripts/research/run_f017_event06_sequence09_interposed_qualification_v1.py"
            ),
        ],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["result"] == "PASS"
    assert result["interposition_installed_before_execution_facing_imports"] is True
    assert set(result["interposition_census"].values()) == {0}


def test_committed_harness_interposes_every_reported_execution_counter() -> None:
    path = (
        ROOT
        / "scripts/research/run_f017_event06_sequence09_interposed_qualification_v1.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    counter_literals = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "forbid"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert {"numerical_execute", "package_start", "tensor_source"} <= counter_literals
    for target in (
        "primary_numerics.execute_outputs",
        "secondary_numerics.execute_outputs",
        "coordinator.bank_package_start",
        "coordinator.execute_event06_bridge",
        "primary_source.source_from_inherited_descriptors",
        "secondary_source.source_from_inherited_descriptors",
    ):
        assert target in source


def test_caller_copy_pickle_and_constructor_attacks_fail() -> None:
    for cls in (FutureGoCapabilityV2, DurableTransactionResult):
        with pytest.raises(TypeError):
            cls()

    forged = object.__new__(FutureGoCapabilityV2)
    for name, value in {
        "authorization_id": "F017-FORGED-AUTHORIZATION",
        "package_attempt_id": "F017-FORGED-PACKAGE",
        "prepared_installation_sha256": "1" * 64,
        "readiness_sha256": "2" * 64,
        "target_parent": Path("/tmp"),
        "target_leaf": "forged-installation",
        "nonce_sha256": "3" * 64,
        "expires_at_unix_ns": 2**63 - 1,
        "source_sha256": "4" * 64,
        "_locked": True,
    }.items():
        object.__setattr__(forged, name, value)
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError):
            operation(forged)

    from qualify_f017_event06_sequence09_no_access_v1 import _package

    with tempfile.TemporaryDirectory(prefix="f017-forge-test-") as root:
        package = _package(Path(root) / "fixture")
        with pytest.raises(ProductionInstallationError, match="producer-issued"):
            validate_future_go_capability(forged, prepared=package["prepared"])

from __future__ import annotations

import ast
import copy
import inspect
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from f017_event06_production_installation_v1 import (
    DOCUMENT_RULES,
    FAILURE_OUTCOMES,
    PackageStartEligibleDryStop,
    PreparedProductionInstallation,
    ProductionInstallationError,
    _FutureGoCapability,
    commit_production_installation,
    prepare_production_installation,
)
from f017_event06_readiness_authority_v2 import ValidatedEvent06ReadinessV2
from qualify_f017_event06_sequence08_implementation_v1 import qualify

ROOT = Path(__file__).resolve().parents[3]


def test_local_implementation_qualification() -> None:
    result = qualify()
    assert result["result"] == "PASS_PENDING_QUALIFICATION_GRAPH"
    assert result["readiness_reconstructions"] == 20
    assert result["readiness_unique_digest_count"] == 1
    assert result["installation_reconstructions"] == 20
    assert result["installation_unique_identity_set_count"] == 1
    assert result["mutation_rejections"] == 324
    assert result["unexpected_passes"] == 0
    assert result["installation_failure_outcomes"] == 16
    assert result["race_families"] == 10
    assert result["terminal"] == "PACKAGE_START_ELIGIBLE_DRY_STOP"
    assert result["checkpoint_root_resolved"] is False
    assert result["checkpoint_access"] == 0
    assert result["numerical_operations"] == 0
    assert result["production_commit_success_calls"] == 0
    assert result["live_installations"] == 0
    assert result["package_starts"] == 0
    assert result["identities_consumed"] == 0


def test_new_readiness_and_installation_types_have_no_public_constructor() -> None:
    with pytest.raises(TypeError):
        ValidatedEvent06ReadinessV2()
    with pytest.raises(TypeError):
        PreparedProductionInstallation()
    with pytest.raises(TypeError):
        PackageStartEligibleDryStop()
    with pytest.raises(TypeError):
        _FutureGoCapability()


def test_production_commit_cannot_succeed_without_future_capability() -> None:
    with pytest.raises(ProductionInstallationError) as raised:
        commit_production_installation(object(), object(), Path("/never"))
    assert raised.value.outcome_id == FAILURE_OUTCOMES["posture"]


def test_prepare_surface_has_no_callbacks_mappings_or_paths() -> None:
    parameters = inspect.signature(prepare_production_installation).parameters
    assert tuple(parameters) == (
        "readiness",
        "human_go",
        "execution_plan",
        "approval",
        "event_identity",
        "candidate",
        "checkpoint_census",
        "integration",
    )
    assert all(
        "callback" not in name and not name.startswith("on_") for name in parameters
    )
    assert all(
        parameter.kind not in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}
        for parameter in parameters.values()
    )


def test_closed_input_rules_are_exact() -> None:
    assert set(DOCUMENT_RULES) == {
        "GO",
        "APPROVAL",
        "EVENT_IDENTITY",
        "CHECKPOINT_CENSUS",
        "INTEGRATION",
    }
    assert all(
        type(rule["keys"]) is set and "schema" in rule["keys"]
        for rule in DOCUMENT_RULES.values()
    )


@pytest.mark.parametrize("category", sorted(FAILURE_OUTCOMES))
def test_all_installation_outcomes_are_distinct(category: str) -> None:
    assert FAILURE_OUTCOMES[category].startswith("F017_V12_PRODUCTION_INSTALL_")
    assert len(set(FAILURE_OUTCOMES.values())) == 16


def test_execution_facing_import_is_interposed_before_load() -> None:
    code = r"""
import mmap
import os
from pathlib import Path

census = {"open": 0, "stat": 0, "resolve": 0, "mmap": 0}
real_open = os.open
real_stat = Path.stat
real_resolve = Path.resolve
real_mmap = mmap.mmap

def forbidden(value):
    text = str(value)
    return "GLM-5.2" in text or "/NONEXISTENT/F017/EVENT06/SEQUENCE08" in text

def guarded_open(path, *args, **kwargs):
    if forbidden(path):
        census["open"] += 1
        raise AssertionError("checkpoint open")
    return real_open(path, *args, **kwargs)

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
Path.stat = guarded_stat
Path.resolve = guarded_resolve
mmap.mmap = guarded_mmap
import f017_event06_production_installation_v1
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


def test_new_modules_have_no_dynamic_or_reflection_capability() -> None:
    paths = (
        ROOT / "scripts/research/f017_event06_readiness_authority_v2.py",
        ROOT / "scripts/research/f017_event06_production_installation_v1.py",
        ROOT / "scripts/research/f017_corrected_oracle_authorization_v12_v2.py",
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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                findings.extend(
                    alias.name
                    for alias in node.names
                    if alias.name.split(".")[0] in forbidden_imports
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] in forbidden_imports
            ):
                findings.append(node.module or "")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in forbidden_calls
            ):
                findings.append(node.func.id)
    assert findings == []


def test_historical_v1_modules_remain_present_and_separate() -> None:
    assert (ROOT / "scripts/research/f017_event06_readiness_authority_v1.py").is_file()
    assert (
        ROOT / "scripts/research/validate_f017_corrected_oracle_access_v12.py"
    ).is_file()
    assert (ROOT / "scripts/research/f017_event06_readiness_authority_v2.py").is_file()
    assert (
        ROOT / "scripts/research/f017_event06_production_installation_v1.py"
    ).is_file()


def test_sealed_classes_reject_copy_and_pickle_without_instance_forgery() -> None:
    for cls in (ValidatedEvent06ReadinessV2, PreparedProductionInstallation):
        with pytest.raises(TypeError):
            copy.copy(cls())
        with pytest.raises(TypeError):
            pickle.dumps(cls())

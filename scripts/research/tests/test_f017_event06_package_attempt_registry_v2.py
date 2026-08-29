from __future__ import annotations

import copy
import inspect
import os
import pickle
from pathlib import Path
from unittest.mock import patch

import pytest

import f017_event06_package_attempt_registry_v1 as historical
import f017_event06_package_attempt_registry_v2 as registry
from execute_f017_corrected_oracle_event_v12_bridge import (
    bank_live_package_start,
    bank_qualification_package_start,
    execute_event06_bridge,
)
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values
from f017_event06_dag_derived_control_path_v1 import run_full_call_path
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
from qualify_f017_event06_package_uniqueness_v1 import qualify as qualify_uniqueness
from validate_f017_event06_authority_dag_v2 import validate as validate_dag_v2


def _production_and_qualification(tmp_path: Path):
    package = build_sequence14_qualification(
        tmp_path / "authority", now_unix_ns=4_000_000_000_000_000_000
    )
    return package["installed"].authority, package["installed"]


def test_public_production_signature_has_no_storage_or_generic_input():
    signature = inspect.signature(registry.reserve_live_package_attempt)
    assert tuple(signature.parameters) == ("installed",)
    assert all(
        parameter.kind not in {parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL}
        for parameter in signature.parameters.values()
    )
    coordinator = inspect.signature(execute_event06_bridge)
    prohibited = {"root", "registry", "configuration", "provider", "callback"}
    assert not any(
        any(word in name for word in prohibited)
        for name in coordinator.parameters
    )


def test_cross_mode_authority_and_root_intersections_fail_before_observation(tmp_path):
    production, qualification = _production_and_qualification(tmp_path)
    observed = 0

    def observer(_root):
        nonlocal observed
        observed += 1
        raise AssertionError("qualification root observed")

    with patch.object(registry, "_prepare_qualification_registry", observer):
        with pytest.raises(ValueError, match="synthetic authority"):
            registry.reserve_qualification_package_attempt(
                production, tmp_path / "must-not-be-observed"
            )
    assert observed == 0
    with pytest.raises(TypeError):
        registry.reserve_live_package_attempt(qualification)

    synthetic = fixture_values()[1]
    for root in (
        registry.LIVE_REGISTRY_ROOT,
        registry.LIVE_REGISTRY_ROOT / "child",
        registry.LIVE_REGISTRY_ROOT.parent,
    ):
        with pytest.raises(ValueError, match="intersects live registry"):
            registry.reserve_qualification_package_attempt(synthetic, root)


def test_production_fixed_root_is_internal_and_intercepted_before_creation(tmp_path):
    production, _qualification = _production_and_qualification(tmp_path)
    observed = []

    def abort(path):
        observed.append(path)
        raise RuntimeError("INTERPOSED_BEFORE_CREATE")

    with patch.object(registry, "_secure_directory", abort):
        with pytest.raises(RuntimeError, match="INTERPOSED_BEFORE_CREATE"):
            registry.reserve_live_package_attempt(production)
    assert observed == [registry.LIVE_REGISTRY_ROOT]


def test_qualification_types_are_sealed_and_not_live_substitutes(tmp_path):
    synthetic = fixture_values()[1]
    reservation = registry.reserve_qualification_package_attempt(
        synthetic, tmp_path / "registry"
    )
    assert type(reservation) is registry.ValidatedQualificationPackageAttemptReservation
    assert type(reservation) is not registry.ValidatedLivePackageAttemptReservation
    for operation in (
        lambda: copy.copy(reservation),
        lambda: copy.deepcopy(reservation),
        lambda: pickle.dumps(reservation),
        lambda: setattr(reservation, "sha256", "0" * 64),
    ):
        with pytest.raises(TypeError):
            operation()
    with pytest.raises(TypeError):
        registry.ValidatedLivePackageAttemptReservation()
    with pytest.raises((TypeError, ValueError)):
        bank_live_package_start(synthetic)


def test_reservation_restart_and_second_start_are_one_shot(tmp_path):
    package = build_sequence14_qualification(
        tmp_path / "authority", now_unix_ns=4_000_000_000_000_000_000
    )
    root = tmp_path / "registry"
    start = bank_qualification_package_start(package["installed"], root)
    reconstructed = registry.load_qualification_package_attempt(
        package["installed"], root
    )
    assert reconstructed.sha256 == start.reservation.sha256
    assert reconstructed.root == start.reservation.root
    with pytest.raises(FileExistsError):
        bank_qualification_package_start(package["installed"], root)


def test_legacy_shared_writers_are_tombstoned():
    for call in (
        lambda: historical.reserve_package_attempt(None),
        lambda: historical.claim_terminal_sinks(None, None, None, None, [], None),
        lambda: historical.claim_qualification_terminal_sinks(None, None, None),
        lambda: historical.bank_terminal(None, {}),
    ):
        with pytest.raises(RuntimeError, match="superseded"):
            call()


def test_twenty_fresh_qualification_paths_are_deterministic_and_no_access(tmp_path):
    digests = set()
    for index in range(20):
        result = run_full_call_path(tmp_path / f"run-{index:02d}")
        assert result["result"] == "PASS"
        assert not any(result["live_counters"].values())
        assert result["original_checkpoint_root_resolved"] is False
        assert result["full_model_inference"] == "NONE"
        digests.add(result["aggregate_sha256"])
    assert len(digests) == 1


def test_environment_and_cwd_cannot_select_production_registry(tmp_path, monkeypatch):
    production, _qualification = _production_and_qualification(tmp_path)
    monkeypatch.setenv("F017_EVENT06_REGISTRY_ROOT", os.fspath(tmp_path / "environment"))
    monkeypatch.chdir(tmp_path)
    observed = []
    with patch.object(
        registry, "_secure_directory",
        lambda path: observed.append(path) or (_ for _ in ()).throw(RuntimeError("STOP")),
    ):
        with pytest.raises(RuntimeError, match="STOP"):
            registry.reserve_live_package_attempt(production)
    assert observed == [registry.LIVE_REGISTRY_ROOT]


def test_twenty_process_reservation_and_terminal_claim_races_have_one_winner():
    result = qualify_uniqueness(20)
    assert result["package_reservation_winners_per_identity"] == 1
    assert result["package_terminal_claim_winners_per_identity"] == 1
    assert result["competing_terminal_outcomes_accepted"] == 0
    assert result["ambiguous_accounting_outcomes"] == 0


def test_source_derived_dag_covers_split_and_live_terminal_boundaries():
    result = validate_dag_v2()
    assert result["result"] == "PASS"
    assert result["uncovered_typed_boundaries"] == 0
    assert result["extraneous_dag_edges"] == 0
    assert result["live_terminal_boundaries_with_composition_tests"] == result[
        "live_terminal_boundaries_total"
    ]

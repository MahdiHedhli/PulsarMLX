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
import f017_event06_numerical_bridge_v1 as numerical_bridge
import execute_f017_corrected_oracle_event_v12_bridge as coordinator_v1
import execute_f017_corrected_oracle_event_v12_bridge_v2 as coordinator_v2
from execute_f017_corrected_oracle_event_v12_bridge import (
    _qualification_bank_live_package_start as qualification_bank_live_package_start,
    bank_live_package_start,
    bank_qualification_package_start,
    execute_event06_bridge,
)
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values
from f017_event06_dag_derived_control_path_v1 import (
    _qualification_run_full_call_path as run_full_call_path,
)
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
from f017_event06_storage_authority_v1 import fixed_live_registry_root
from f017_event06_sequence18_storage_census_v1 import census as storage_census
from f017_event06_sequence18_vfs_v1 import InMemorySafetyFilesystem
from generate_f017_event06_authority_dag_v2 import build as build_dag_v2
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
    successor = inspect.signature(coordinator_v2.execute_event06_bridge)
    assert tuple(successor.parameters) == ("installed", "execution_plan", "bridge_input")


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
        registry._qualification_reserve_live_package_attempt(qualification)
    with pytest.raises(RuntimeError, match="superseded by F017 Sequence 39"):
        registry.reserve_live_package_attempt(production)

    synthetic = fixture_values()[1]
    for root in (
        fixed_live_registry_root(),
        Path("/var/tmp/pulsarmlx-f017-event06-v12-package-registry"),
        fixed_live_registry_root() / "child",
        fixed_live_registry_root().parent,
    ):
        with pytest.raises(ValueError, match="intersects live registry"):
            registry.reserve_qualification_package_attempt(synthetic, root)


def test_darwin_alias_and_symlink_alias_reject_before_registry_creation(tmp_path):
    synthetic = fixture_values()[1]
    observed = []
    alias = Path("/var/tmp/pulsarmlx-f017-event06-v12-package-registry")
    with patch.object(registry, "_secure_directory", lambda path: observed.append(path)):
        with pytest.raises(ValueError, match="intersects live registry"):
            registry.reserve_qualification_package_attempt(synthetic, alias)
    assert observed == []

    stand_in = tmp_path / "stand-in-live"
    link = tmp_path / "qualification-alias"
    stand_in.mkdir()
    link.symlink_to(stand_in, target_is_directory=True)
    with patch.object(registry, "_LIVE_REGISTRY_ROOT", stand_in):
        with pytest.raises(ValueError, match="resolves into live registry"):
            registry.reserve_qualification_package_attempt(synthetic, link)


def test_registry_key_is_one_package_identity_across_reinstallations(tmp_path):
    production, qualification = _production_and_qualification(tmp_path)
    live = registry._reservation_value(production, "LIVE_CANONICAL")
    dry = registry._reservation_value(qualification.authority, "QUALIFICATION_ONLY")
    assert live["registry_key_sha256"] == dry["registry_key_sha256"]
    changed = production.as_dict()
    changed["installed_authority_sha256"] = "f" * 64
    assert registry._sha({
        "authorization_id": changed["authorization_id"],
        "package_attempt_id": changed["package_attempt_id"],
        "checkpoint_set_sha256": changed["checkpoint_set_sha256"],
    }) == live["registry_key_sha256"]


def test_execution_result_freeze_is_injective_for_empty_and_pair_lists():
    from execute_f017_corrected_oracle_event_v12_bridge import _freeze, _thaw

    values = ({}, [], [["a", 1], ["b", 2]], {"nested": [{}, [], ["x", 3]]})
    frozen = [_freeze(value) for value in values]
    assert len(set(frozen)) == len(values)
    assert [_thaw(value) for value in frozen] == list(values)


def test_production_fixed_root_is_internal_and_intercepted_before_creation(tmp_path):
    production, _qualification = _production_and_qualification(tmp_path)
    observed = []

    def abort(path):
        observed.append(path)
        raise RuntimeError("INTERPOSED_BEFORE_CREATE")

    with patch.object(registry, "_secure_directory", abort):
        with pytest.raises(RuntimeError, match="INTERPOSED_BEFORE_CREATE"):
            registry._qualification_reserve_live_package_attempt(production)
    assert observed == [fixed_live_registry_root()]


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
        qualification_bank_live_package_start(synthetic)


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


def test_sequence39_superseded_live_registry_apis_remain_tombstoned():
    for call in (
        lambda: registry.reserve_live_package_attempt(None),
        lambda: registry.load_live_package_attempt(None),
        lambda: registry.claim_live_terminal_sinks(
            None, None, None, None, [], None
        ),
        lambda: registry.bank_live_terminal(None, {}),
        lambda: bank_live_package_start(None),
        lambda: execute_event06_bridge(None, None, None),
    ):
        with pytest.raises(RuntimeError, match="superseded by F017 Sequence 39"):
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
            registry._qualification_reserve_live_package_attempt(production)
    assert observed == [fixed_live_registry_root()]


def test_twenty_process_reservation_and_terminal_claim_races_have_one_winner():
    result = qualify_uniqueness(20)
    assert result["package_reservation_winners_per_identity"] == 1
    assert result["package_terminal_claim_winners_per_identity"] == 1
    assert result["competing_terminal_outcomes_accepted"] == 0
    assert result["ambiguous_accounting_outcomes"] == 0
    assert result["losing_contenders_with_pre_package_start_abort_proof"] == 19
    assert len(result["loser_records"]) == 19


def test_whole_closure_storage_and_legacy_writer_census_passes():
    result = storage_census()
    assert result["result"] == "PASS"
    assert result["production_public_storage_location_inputs"] == 0
    assert result["production_indirect_storage_location_inputs"] == 0
    assert result["legacy_production_writers_total"] == (
        result["legacy_production_writers_removed"]
        + result["legacy_production_writers_fail_closed_proven"]
    )
    assert result["legacy_production_writers_reachable_to_safety_state"] == 0
    assert result["reservation_reclaim_expire_unlock_or_override_symbols_reachable"] == 0


def test_live_package_key_and_start_are_exclusive_in_process_vfs(tmp_path):
    production, _qualification = _production_and_qualification(tmp_path)
    filesystem = InMemorySafetyFilesystem()
    with filesystem.installed():
        start = qualification_bank_live_package_start(production)
        with pytest.raises(FileExistsError):
            qualification_bank_live_package_start(production)
    assert start.get("authority_mode") == "LIVE_CANONICAL"
    assert filesystem.snapshot()["file_count"] == 2


def test_source_derived_dag_covers_split_and_live_terminal_boundaries():
    result = validate_dag_v2()
    assert result["result"] == "PASS"
    assert result["uncovered_typed_boundaries"] == 0
    assert result["extraneous_dag_edges"] == 0
    assert result["live_terminal_boundaries_with_composition_tests"] == result[
        "live_terminal_boundaries_total"
    ]


def test_live_terminal_claim_inputs_are_source_derived():
    inputs = [
        edge for edge in build_dag_v2()["edges"]
        if edge.get("boundary_direction") == "CONSUMER_INPUT"
        and edge["consumer_symbol"] == "claim_live_terminal_sinks"
    ]
    assert {edge["consumer_parameter"] for edge in inputs} == {
        "reservation", "package_start", "bridge", "execution_result",
        "transition_records", "package_terminal_view",
    }
    assert all(
        edge["composition_evidence"]["test_symbol"]
        == "test_live_terminal_claim_inputs_are_source_derived"
        for edge in inputs
    )


def test_qualification_coordinators_have_no_live_package_start_call():
    for function in (
        coordinator_v1.execute_event06_bridge_qualification,
        coordinator_v2.execute_event06_bridge_qualification,
    ):
        source = inspect.getsource(function)
        assert "bank_live_package_start(" not in source
        assert "reserve_qualification_package_attempt(" in source


def test_terminal_view_rejects_same_package_from_different_authorization(tmp_path):
    result = run_full_call_path(tmp_path / "composition", retain_authorities=True)
    authorities = result["_authorities"]
    filesystem = InMemorySafetyFilesystem()
    with filesystem.installed():
        reservation = registry._qualification_reserve_live_package_attempt(
            authorities["installed_authority"]
        )
    bridge_value = authorities["historical_bridge"].as_dict()
    bridge_value["authorization_id"] = "F017-CORRECTED-ORACLE-AUTHORIZATION-DIFFERENT"
    forged_bridge = numerical_bridge.ValidatedNumericalBridge(
        numerical_bridge._SEAL, bridge_value
    )
    forged_view = numerical_bridge._validated_consumer_view_from_producer(
        "PACKAGE_TERMINAL",
        {
            "schema": numerical_bridge.VIEW_SCHEMA,
            "bridge_sha256": forged_bridge.sha256,
            "package_attempt_id": reservation.get("package_attempt_id"),
            "binding_chain_head_sha256": "1" * 64,
            "v11_closure_root_sha256": "2" * 64,
            "accounting_binding_sha256": "3" * 64,
        },
    )
    with pytest.raises(TypeError, match="exact package closure authorities required"):
        registry._validate_view(reservation, forged_bridge, forged_view)

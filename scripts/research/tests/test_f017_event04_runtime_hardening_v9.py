from __future__ import annotations

import copy
import ast
import json
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

from check_f017_descriptor_type_safety_v9 import _validate_descriptors as independent_validate
from f017_corrected_oracle_event_accounting_v9 import validate_snapshot
from f017_descriptor_lease_manager_v9 import LeaseRecord, LeaseSet, validate_descriptors
from f017_descriptor_lease_manager_v9 import acquire_synthetic_leases
from f017_event04_tensor_plan_v9 import build_plan, validate_plan
from f017_runtime_outcome_realizer_v9 import realize
from f017_canonical_serialization_v8 import bank_exclusive
from f017_synthetic_checkpoint_v9 import prepare
from execute_f017_corrected_oracle_event_v9 import execute_event04
import validate_f017_corrected_oracle_access_v9 as authorizer
from f017_memory_gate_v9 import THRESHOLD_BYTES
from f017_corrected_oracle_authorization_v9 import parse_candidate_bytes, production_shards
from f017_canonical_serialization_v8 import canonical_bytes


def descriptors() -> list[dict]:
    return [{"device": 1, "inode": 1000 + ordinal, "mode": 0o100600, "size": 10 + ordinal,
             "mtime_ns": 1, "ctime_ns": 1, "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
             "lease_id": f"LEASE-F017-V9-UNIT-{ordinal}"} for ordinal in range(2, 7)]


@pytest.mark.parametrize("value", [None, [], (), set(), 1, True, "", b""])
def test_non_dictionary_descriptors_fail_controlled(value: object) -> None:
    sample = descriptors(); sample[0] = value
    for validator in (validate_descriptors, independent_validate):
        with pytest.raises(ValueError): validator(copy.deepcopy(sample))


@pytest.mark.parametrize("value", [[], {}, set(), (), True, 1, 1.0, b"x", None])
def test_unhashable_or_non_string_lease_ids_fail_controlled(value: object) -> None:
    sample = descriptors(); sample[0]["lease_id"] = value
    for validator in (validate_descriptors, independent_validate):
        with pytest.raises(ValueError): validator(copy.deepcopy(sample))


def test_release_is_idempotent_and_continues_after_failure() -> None:
    handles = [os.open(__file__, os.O_RDONLY) for _ in range(5)]
    leases = LeaseSet([LeaseRecord(identity, descriptor) for identity, descriptor in zip(descriptors(), handles, strict=True)], "0" * 64, ["0" * 64] * 5)
    failed = set()
    def close(descriptor: int, lease_id: str) -> None:
        if lease_id.endswith("-4") and lease_id not in failed:
            failed.add(lease_id); raise OSError(5, "injected")
        os.close(descriptor)
    first = leases.release(close_function=close); second = leases.release(close_function=close, retry_failed=True); third = leases.release()
    assert first["attempted_closures"] == 5 and first["successful_closures"] == 4 and first["live_leases_after_release"] == 1
    assert second["attempted_closures"] == 1 and second["live_leases_after_release"] == 0
    assert third["attempted_closures"] == 0 and third["idempotent_noop"] is True


def test_release_continues_when_close_event_banking_fails_after_close() -> None:
    handles = [os.open(__file__, os.O_RDONLY) for _ in range(5)]
    leases = LeaseSet([LeaseRecord(identity, descriptor) for identity, descriptor in zip(descriptors(), handles, strict=True)], "0" * 64, ["0" * 64] * 5)
    failed = False
    def bank(event: dict) -> str:
        nonlocal failed
        if not failed:
            failed = True
            raise OSError(5, "injected close-event banking failure")
        return "1" * 64
    first = leases.release(event_function=bank)
    assert first["attempted_closures"] == 5 and first["successful_closures"] == 5
    assert first["live_leases_after_release"] == 0 and first["evidence_banking_failures"] == 1
    recovered = leases.release(event_function=bank)
    assert recovered["attempted_closures"] == 0 and recovered["evidence_banking_failures"] == 0
    assert recovered["result"] == "PASS" and all(record.close_attempt_count == 1 for record in leases.records)


def test_production_tensor_plan_exact_census() -> None:
    plan = validate_plan(build_plan())
    assert plan["graph_tensor_count"] == 1410 and plan["non_access_tensor_count"] == 399
    assert plan["graph_shards"] == [2, 3, 4, 5, 6]


def test_accounting_snapshot_fails_closed() -> None:
    expected = {"authorization": 0, "package": 1, "primary": 1, "secondary": 0, "historical_before": 175, "historical_after": 175}
    validate_snapshot(expected, expected)
    with pytest.raises(ValueError): validate_snapshot({**expected, "primary": 0}, expected)


def test_production_preparse_failure_is_terminalized_in_bound_fallback(tmp_path: Path) -> None:
    installed = tmp_path / "installed.json"; installed.write_bytes(b"not-json\n")
    receipt = tmp_path / "receipt.json"; receipt.write_bytes(b"not-json\n")
    fallback = tmp_path / "emergency"; fallback.mkdir(mode=0o700)
    result = execute_event04(installed, receipt, tmp_path / "state", fallback)
    assert result["result"] == "CONTROLLED_FAILURE" and result["generic_fallback"] is True
    assert (fallback / "failure-terminal-capsule.json").is_file()


def test_modeled_failure_requires_independent_transition_observation() -> None:
    with tempfile.TemporaryDirectory() as raw:
        result = realize("PRIMARY_POST_START_FAILURE__AFTER_RANK_030", Path(raw) / "positive")
    assert result["failed_transition_id"] == "FAIL_PRIMARY_POST_START_FAILURE__AFTER_RANK_030"
    assert result["capsule_source"] == "COORDINATOR_CAUSAL_BANK_INJECTION"


def test_runtime_failure_realizer_is_not_generic() -> None:
    with tempfile.TemporaryDirectory() as raw:
        result = realize("PRIMARY_POST_START_FAILURE__AFTER_RANK_030", Path(raw) / "case")
    assert result["result"] == "PASS" and result["generic_fallback"] is False
    assert result["accounting"] == {"package": 1, "primary": 1, "secondary": 0}


def test_target_sources_have_no_graph_path_open_primitive() -> None:
    for name in ("f017_corrected_oracle_primary_target_source_v9.py", "f017_corrected_oracle_secondary_target_source_v9.py"):
        tree = ast.parse((RESEARCH / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert not (isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "open")
                assert node.func.attr != "open"


def test_future_live_candidate_is_renderable_but_not_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = __import__("time").time_ns()
    observation = {"parser_version": "UNIT", "page_size_bytes": 16384, "pages_free": 0, "pages_inactive": 0,
                   "pages_speculative": 0, "pages_purgeable": 0, "available_bytes": THRESHOLD_BYTES,
                   "canonical_observation": "UNIT", "stdout_sha256": "0" * 64, "observed_at_unix_ns": now}
    monkeypatch.setattr(authorizer, "observe", lambda *, enforce: {"result": "PASS", "enforced": enforce,
                        "threshold_bytes": THRESHOLD_BYTES, "sample_age_ns": 0, "observation": observation})
    plan = Path("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json").resolve()
    readiness = tmp_path / "readiness.json"
    bank_exclusive(readiness, {"schema": "pulsarmlx.f017.event04-execution-readiness-declaration/9.0.0",
                               "F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS": "ACCEPTED",
                               "READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO": "YES",
                               "ACTIVE_CORRECTED_ORACLE_GENERATION": "V9", "accepted_implementation_head": "f" * 40,
                               "accepted_authority_manifest_sha256": "b" * 64, "accepted_at_unix_ns": now})
    approval = tmp_path / "approval.json"; shards = production_shards(); readiness_sha = hashlib.sha256(readiness.read_bytes()).hexdigest()
    bank_exclusive(approval, {"schema": "pulsarmlx.f017.corrected-oracle-event04-operator-approval/9.0.0",
        "result": "APPROVED_FOR_ONE_EVENT_04", "active_generation": "V9",
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "checkpoint_root": "/future/operator/approved/checkpoint", "shards": shards,
        "canonical_authorization_path": str(tmp_path / "canonical" / "authorization.json"),
        "installation_receipt_path": str(tmp_path / "canonical" / "receipt.json"),
        "emergency_evidence_root": str(tmp_path / "emergency"), "authority_manifest_sha256": "a" * 64,
        "readiness_declaration_sha256": readiness_sha, "approved_at_unix_ns": now,
        "approval_expires_at_unix_ns": now + 60_000_000_000})
    output = tmp_path / "candidate.json"
    result = authorizer.render_operator_go_candidate(approval, readiness, plan, output)
    assert result["result"] == "PASS" and result["authority_created"] is False
    assert result["candidate"]["state"] == "OPERATOR_APPROVED_CANDIDATE" and result["candidate"]["live"] is False
    assert not Path(result["candidate"]["canonical_authorization_path"]).exists()
    delayed = copy.deepcopy(result["candidate"])
    delayed["mint_memory_gate"]["observation"]["observed_at_unix_ns"] -= 120_000_000_000
    assert parse_candidate_bytes(canonical_bytes(delayed))["scope"] == "PRODUCTION_EVENT_04"


def test_live_candidate_rejects_non_authoritative_shard_census(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Reuse the accepted renderer test as the positive control, then prove the
    # live parser rejects one changed size before any checkpoint access.
    gate = {"parser_version": "UNIT", "page_size_bytes": 16384, "pages_free": 0, "pages_inactive": 0,
            "pages_speculative": 0, "pages_purgeable": 0, "available_bytes": THRESHOLD_BYTES,
            "canonical_observation": "UNIT", "stdout_sha256": "0" * 64, "observed_at_unix_ns": __import__("time").time_ns()}
    value = {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0",
        "state": "OPERATOR_APPROVED_CANDIDATE", "live": False, "scope": "PRODUCTION_EVENT_04", "authority_generation": 9,
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "causal_dag_sha256": "0"*64, "numerical_contract_sha256": "1"*64, "primary_numerical_sha256": "2"*64,
        "secondary_numerical_sha256": "3"*64, "checkpoint_root": "/future/checkpoint", "shards": production_shards(),
        "attempts": 1, "retries": 0, "resume": False, "active_generation": "V9", "synthetic_root_manifest_path": None,
        "synthetic_root_manifest_sha256": None, "tensor_catalog_path": "/future/plan", "tensor_catalog_sha256": "4"*64,
        "mint_memory_gate": {"result":"PASS","enforced":True,"threshold_bytes":THRESHOLD_BYTES,"sample_age_ns":0,"observation":gate},
        "operator_approval_path": "/future/approval", "operator_approval_sha256":"5"*64,
        "canonical_authorization_path":"/future/authorization", "installation_receipt_path":"/future/receipt",
        "emergency_evidence_root":"/future/emergency", "authority_manifest_sha256":"6"*64,
        "execution_readiness_declaration_path":"/future/readiness", "execution_readiness_declaration_sha256":"7"*64}
    value["shards"][1]["size_bytes"] += 1
    with pytest.raises(ValueError, match="live checkpoint shard authority"):
        parse_candidate_bytes(canonical_bytes(value))


@pytest.mark.parametrize("gate", [None, [], {}, True, 1])
def test_live_candidate_malformed_memory_gate_fails_controlled(gate: object) -> None:
    value = {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0",
        "state": "OPERATOR_APPROVED_CANDIDATE", "live": False, "scope": "PRODUCTION_EVENT_04", "authority_generation": 9,
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "causal_dag_sha256": "0"*64, "numerical_contract_sha256": "1"*64, "primary_numerical_sha256": "2"*64,
        "secondary_numerical_sha256": "3"*64, "checkpoint_root": "/future/checkpoint", "shards": production_shards(),
        "attempts": 1, "retries": 0, "resume": False, "active_generation": "V9", "synthetic_root_manifest_path": None,
        "synthetic_root_manifest_sha256": None, "tensor_catalog_path": "/future/plan", "tensor_catalog_sha256": "4"*64,
        "mint_memory_gate": gate, "operator_approval_path": "/future/approval", "operator_approval_sha256":"5"*64,
        "canonical_authorization_path":"/future/authorization", "installation_receipt_path":"/future/receipt",
        "emergency_evidence_root":"/future/emergency", "authority_manifest_sha256":"6"*64,
        "execution_readiness_declaration_path":"/future/readiness", "execution_readiness_declaration_sha256":"7"*64}
    with pytest.raises(ValueError):
        parse_candidate_bytes(canonical_bytes(value))


def test_synthetic_manifest_catalog_binding_and_hardlinks_fail_closed(tmp_path: Path) -> None:
    package_root = tmp_path / "package"; package_root.mkdir()
    checkpoint, shards, catalog, manifest = prepare(package_root, 18101, "ISOLATION", True)
    candidate_path = tmp_path / "candidate.json"
    rendered = authorizer.render_rehearsal_candidate(checkpoint, shards, catalog, candidate_path, "ISOLATION",
                                                      scope="SYNTHETIC_QUALIFICATION", manifest_path=manifest)
    candidate = rendered["candidate"]
    manifest_value = json.loads(manifest.read_bytes()); manifest_value["catalog_sha256"] = "f" * 64
    manifest.write_bytes(canonical_bytes(manifest_value))
    candidate["synthetic_root_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="synthetic catalog binding"):
        acquire_synthetic_leases(candidate)

    # Restore the valid manifest binding and prove a second hardlink to any
    # shard makes the file-backed synthetic authority fail closed.
    manifest_value["catalog_sha256"] = candidate["tensor_catalog_sha256"]
    manifest.write_bytes(canonical_bytes(manifest_value))
    candidate["synthetic_root_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    os.link(checkpoint / shards[1]["filename"], tmp_path / "hardlink-to-shard-2")
    with pytest.raises(ValueError, match="synthetic shard hardlink prohibited"):
        acquire_synthetic_leases(candidate)

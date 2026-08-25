from __future__ import annotations

import copy
import ast
import json
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
from f017_event04_tensor_plan_v9 import build_plan, validate_plan
from f017_runtime_outcome_realizer_v9 import realize
from f017_canonical_serialization_v8 import bank_exclusive
import validate_f017_corrected_oracle_access_v9 as authorizer
from f017_memory_gate_v9 import THRESHOLD_BYTES


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
    bank_exclusive(readiness, {"F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS": "ACCEPTED",
                               "READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO": "YES",
                               "ACTIVE_CORRECTED_ORACLE_GENERATION": "V9"})
    approval = tmp_path / "approval.json"; shards = []
    for ordinal in range(1, 7):
        shards.append({"filename": f"GLM-5.2-UD-IQ2_XXS-{ordinal:05d}-of-00006.gguf", "size_bytes": ordinal,
                       "sha256": f"{ordinal}" * 64, "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"})
    bank_exclusive(approval, {"schema": "pulsarmlx.f017.corrected-oracle-event04-operator-approval/9.0.0",
        "result": "APPROVED_FOR_ONE_EVENT_04", "active_generation": "V9",
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "checkpoint_root": "/future/operator/approved/checkpoint", "shards": shards,
        "canonical_authorization_path": str(tmp_path / "canonical" / "authorization.json"),
        "installation_receipt_path": str(tmp_path / "canonical" / "receipt.json"),
        "emergency_evidence_root": str(tmp_path / "emergency"), "authority_manifest_sha256": "a" * 64})
    output = tmp_path / "candidate.json"
    result = authorizer.render_operator_go_candidate(approval, readiness, plan, output)
    assert result["result"] == "PASS" and result["authority_created"] is False
    assert result["candidate"]["state"] == "OPERATOR_APPROVED_CANDIDATE" and result["candidate"]["live"] is False
    assert not Path(result["candidate"]["canonical_authorization_path"]).exists()

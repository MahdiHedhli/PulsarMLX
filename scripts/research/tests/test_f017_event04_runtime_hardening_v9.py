from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

import pytest

from check_f017_descriptor_type_safety_v8 import _validate_descriptors as independent_validate
from f017_corrected_oracle_event_accounting_v9 import validate_snapshot
from f017_descriptor_lease_manager_v9 import LeaseRecord, LeaseSet, validate_descriptors
from f017_event04_tensor_plan_v9 import build_plan, validate_plan
from f017_runtime_outcome_realizer_v9 import realize


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

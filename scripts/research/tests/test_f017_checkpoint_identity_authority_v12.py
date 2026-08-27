from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import validate_candidate_bytes
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError
from f017_corrected_oracle_authorization_v12 import build_identity_candidate
from qualify_f017_checkpoint_identity_authority_v12 import qualify

CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-checkpoint-identity-v12.json"
PLAN_SHA = hashlib.sha256(b"F017-V12-TEST-PLAN").hexdigest()


def candidate(tmp_path: Path) -> dict:
    root = tmp_path / "root"
    root.mkdir()
    for ordinal in range(1, 7):
        (root / f"synthetic-v12-shard-{ordinal}.bin").touch()
    return build_identity_candidate(
        authority_scope="SYNTHETIC", authorization_id="F017-V12-TEST-AUTH-01",
        package_attempt_id="F017-V12-TEST-PACKAGE-01", checkpoint_root=root,
        checkpoint_identity_contract_path=CONTRACT, event_identity_plan_sha256=PLAN_SHA,
    )


def test_candidate_is_strict_and_immutable(tmp_path: Path) -> None:
    authority = validate_candidate_bytes(canonical_bytes(candidate(tmp_path)))
    assert authority.posture == "CANDIDATE"
    assert authority.get("generation") == "V12"
    with pytest.raises(Exception):
        authority.items[0] = ("schema", "bad")  # type: ignore[index]


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(authority_scope="PRODUCTION_EVENT_06"),
    lambda value: value.update(resume=True),
    lambda value: value.update(retries=1),
    lambda value: value.update(attempts=True),
    lambda value: value.update(generation="V11"),
    lambda value: value.update(unknown_alias=False),
])
def test_candidate_mutations_fail_closed(tmp_path: Path, mutation) -> None:
    value = candidate(tmp_path)
    mutation(value)
    with pytest.raises(IdentityAuthorityError):
        validate_candidate_bytes(canonical_bytes(value))


def test_overnight_qualification_census() -> None:
    result = qualify()
    assert result["result"] == "PASS"
    assert result["successful_identity_stages"] >= 30
    assert result["identity_terminals_complete"] >= 90
    assert result["minimal_six_shard_packages"] >= 20
    assert result["mixed_format_six_shard_packages"] >= 20
    assert result["identity_stage_fresh_process_repetitions"] >= 20
    assert result["total_failure_executions"] >= 300
    assert result["runtime_failure_executions"] >= 300
    assert result["runtime_failure_fresh_processes"] >= 60
    assert result["modeled_outcomes_realized"] == result["modeled_outcomes"]
    assert result["filesystem_faults_realized"] >= 50
    assert result["evidence_and_close_faults_realized"] >= 17
    assert result["scope_separation"]["result"] == "PASS"
    assert result["unexpected_passes"] == 0
    assert result["original_checkpoint_shard_opens"] == 0

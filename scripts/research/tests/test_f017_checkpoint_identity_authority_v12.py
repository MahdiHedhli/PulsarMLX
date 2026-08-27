from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import validate_candidate_bytes
from f017_checkpoint_identity_capability_v12 import validate_capability
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError
from f017_corrected_oracle_authorization_v12 import build_identity_candidate
from f017_event06_readiness_authority_v1 import validate_event06_readiness_value
from execute_f017_corrected_oracle_event_v12 import validate_package_start
from qualify_f017_checkpoint_identity_authority_v12 import qualify
from validate_f017_corrected_oracle_access_v12 import (
    bank_candidate, install_noncanonical_candidate, validate_installed_triple,
)

CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-checkpoint-identity-v12.json"
PLAN_SHA = hashlib.sha256(b"F017-V12-TEST-PLAN").hexdigest()
READINESS_CONTRACT = Path("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-readiness-consumer-interface-v1.json")


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


def readiness_value() -> dict:
    contract = json.loads(READINESS_CONTRACT.read_text())
    value: dict = {}
    defaults = {
        "boolean":False, "nonnegative_integer":0, "git_object":"a" * 40,
        "repository_path":"docs/architecture/reviews/evidence/bound.json",
        "sha256":"b" * 64, "string":"BOUND",
    }
    for category, names in contract["exact_types"].items():
        for name in names:
            value[name] = defaults[category]
    value.update(contract["exact_predicates"])
    value.update({
        "schema":"pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.0.0",
        "gemini_verdict":"NO_UNRESOLVED_MATERIAL_CHALLENGE",
        "opus_verdict":"ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_AUTHORIZATION_PREPARATION",
        "exact_next_safe_action":"REQUEST_FRESH_HUMAN_EVENT06_GO",
    })
    return value


def test_candidate_is_strict_and_immutable(tmp_path: Path) -> None:
    authority = validate_candidate_bytes(canonical_bytes(candidate(tmp_path)))
    assert authority.posture == "CANDIDATE"
    assert authority.get("generation") == "V12"
    with pytest.raises(Exception):
        authority.items[0] = ("schema", "bad")  # type: ignore[index]


def test_event06_readiness_value_is_exact_and_typed() -> None:
    value = readiness_value()
    assert validate_event06_readiness_value(value) == value


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(event_06_executed=True),
    lambda value: value.update(ready_for_corrected_full_checkpoint_oracle_event_06_execution_go="YES"),
    lambda value: value.update(required_native_skips=True),
    lambda value: value.update(active_corrected_oracle_generation="v12"),
    lambda value: value.update(READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_EXECUTION_GO=True),
    lambda value: value.pop("historical_master_ledger"),
])
def test_event06_readiness_mutations_fail_closed(mutation) -> None:
    value = readiness_value(); mutation(value)
    with pytest.raises(ValueError):
        validate_event06_readiness_value(value)


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
    assert result["install_boundary_substitutions_rejected"] == 20
    assert result["live_drift_faults_realized"] == 2
    assert result["filesystem_faults_realized"] >= 50
    assert result["evidence_and_close_faults_realized"] >= 17
    assert result["scope_separation"]["result"] == "PASS"
    assert result["unexpected_passes"] == 0
    assert result["original_checkpoint_shard_opens"] == 0


def test_installed_field_substitution_is_rejected(tmp_path: Path) -> None:
    path_a = tmp_path / "a"; path_a.mkdir()
    path_b = tmp_path / "b"; path_b.mkdir()
    candidate_a = candidate(path_a)
    candidate_b = candidate(path_b)
    candidate_b["authorization_id"] = "F017-V12-TEST-AUTH-02"
    candidate_b["package_attempt_id"] = "F017-V12-TEST-PACKAGE-02"
    candidate_a_path = tmp_path / "candidate-a.json"
    candidate_b_path = tmp_path / "candidate-b.json"
    installed_b_path = tmp_path / "installed-b.json"
    receipt_b_path = tmp_path / "receipt-b.json"
    candidate_a_sha = bank_candidate(candidate_a_path, candidate_a)
    bank_candidate(candidate_b_path, candidate_b)
    install_noncanonical_candidate(candidate_b_path, installed_b_path, receipt_b_path)
    receipt = json.loads(receipt_b_path.read_text())
    receipt["candidate_sha256"] = candidate_a_sha
    receipt_b_path.write_bytes(canonical_bytes(receipt))
    installed = json.loads(installed_b_path.read_text())
    installed["installed_authorization_sha256"] = candidate_a_sha
    installed["installation_receipt_sha256"] = hashlib.sha256(receipt_b_path.read_bytes()).hexdigest()
    installed_b_path.write_bytes(canonical_bytes(installed))
    with pytest.raises(IdentityAuthorityError) as raised:
        validate_package_start(candidate_a_path, installed_b_path, receipt_b_path)
    assert raised.value.outcome_id == "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH"


def test_capability_drift_has_live_modeled_raise_site(tmp_path: Path) -> None:
    drift = tmp_path / "producer.py"
    drift.write_text("import subprocess\n", encoding="utf-8")
    with mock.patch("f017_checkpoint_identity_capability_v12.PRODUCER", drift):
        with pytest.raises(IdentityAuthorityError) as raised:
            validate_capability()
    assert raised.value.outcome_id == "F017_V12_IDENTITY_CAPABILITY_DRIFT"


def test_producer_measurement_drift_has_live_modeled_raise_site(tmp_path: Path) -> None:
    candidate_path = tmp_path / "candidate.json"
    installed_path = tmp_path / "installed.json"
    receipt_path = tmp_path / "receipt.json"
    value = candidate(tmp_path)
    bank_candidate(candidate_path, value)
    install_noncanonical_candidate(candidate_path, installed_path, receipt_path)
    candidate_authority = validate_candidate_bytes(candidate_path.read_bytes())
    import f017_checkpoint_identity_authority_v12 as authority_module
    original_sha = authority_module._sha
    measured = (authority_module.ROOT / value["measured_producer_path"]).resolve()
    def drift_sha(path: Path) -> str:
        return "0" * 64 if path.resolve() == measured else original_sha(path)
    with mock.patch("f017_checkpoint_identity_authority_v12._sha", side_effect=drift_sha):
        with pytest.raises(IdentityAuthorityError) as raised:
            validate_installed_triple(
                installed_path, receipt_path, candidate_authority,
            )
    assert raised.value.outcome_id == "F017_V12_IDENTITY_PRODUCER_MEASUREMENT_DRIFT"

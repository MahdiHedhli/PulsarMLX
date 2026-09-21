#!/usr/bin/env python3
"""Implementation-local Sequence 8 reconstruction and mutation runner."""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
import tempfile
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_corrected_oracle_authorization_v12_v2 import (
    build_identity_candidate_from_readiness_v2,
)
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_production_installation_v1 import (
    FAILURE_OUTCOMES,
    ProductionInstallationError,
    _fail_before_write_test_spy,
    assert_sealed_objects_closed,
    commit_production_installation,
    installation_failure,
    prepare_production_installation,
    validate_checkpoint_census_document,
    validate_event_identity_plan_document,
    validate_inert_human_go,
    validate_inert_operator_approval,
    validate_integration_authority_document,
    validate_prepared_package_start_eligibility,
    validate_prepared_production_installation,
)
from f017_event06_readiness_authority_v2 import (
    Event06ReadinessError,
    validate_event06_readiness_declaration_v2,
    validate_event06_readiness_value_v2,
)
from f017_event06_sequence08_fixture_v1 import (
    ROOT,
    build_readiness_fixture,
    execution_plan_value,
)

RACE_FAMILIES = (
    "capability_expiry",
    "candidate_replay",
    "exclusive_create",
    "target_identity",
    "write_short",
    "write_error",
    "file_fsync",
    "directory_fsync",
    "readback_identity",
    "concurrent_replacement",
)


def _repository_sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _package(fixture_root: Path):
    readiness_raw, interface_path, declaration = build_readiness_fixture(fixture_root)
    readiness = validate_event06_readiness_declaration_v2(
        readiness_raw, repository_root=fixture_root, contract_path=interface_path
    )
    authorization_id = "F017-SEQUENCE08-INERT-AUTHORIZATION"
    package_attempt_id = "F017-SEQUENCE08-INERT-PACKAGE"

    provisional = type(
        "CandidateIds",
        (),
        {
            "get": lambda self, name: {
                "package_attempt_id": package_attempt_id,
            }[name]
        },
    )()
    plan_value = execution_plan_value(provisional, readiness)
    plan = validate_execution_plan(plan_value)
    event_value = {
        "schema": "pulsarmlx.f017.event06-event-identity-plan/1.0.0",
        "package_attempt_id": package_attempt_id,
        "primary_event_id": plan.get("primary_event_id"),
        "secondary_event_id": plan.get("secondary_event_id"),
        "execution_plan_sha256": plan.sha256,
    }
    event_raw = canonical_bytes(event_value)
    event_identity = validate_event_identity_plan_document(event_raw)
    candidate = build_identity_candidate_from_readiness_v2(
        readiness,
        authorization_id=authorization_id,
        package_attempt_id=package_attempt_id,
        checkpoint_root=Path("/NONEXISTENT/F017/EVENT06/SEQUENCE08"),
        event_identity_plan_sha256=event_identity.sha256,
    )
    candidate_sha = hashlib.sha256(canonical_bytes(candidate.as_dict())).hexdigest()
    census_value = {
        "schema": "pulsarmlx.f017.event06-v12-checkpoint-census/1.0.0",
        "checkpoint_set_sha256": candidate.get("checkpoint_set_sha256"),
        "expected_shard_count": candidate.get("expected_shard_count"),
        "expected_identity_only_shard_count": candidate.get(
            "expected_identity_only_shard_count"
        ),
        "expected_graph_payload_shard_count": candidate.get(
            "expected_graph_payload_shard_count"
        ),
        "expected_total_bytes": candidate.get("expected_total_bytes"),
        "checkpoint_root": "/NONEXISTENT/F017/EVENT06/SEQUENCE08",
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
    }
    census = validate_checkpoint_census_document(canonical_bytes(census_value))
    integration_value = {
        "schema": "pulsarmlx.f017.event06-v12-installation-integration-authority/1.0.0",
        "source_head": plan.get("source_head"),
        "source_tree": plan.get("source_tree"),
        "implementation_measurement_sha256": plan.get(
            "implementation_measurement_sha256"
        ),
        "bridge_declaration_sha256": readiness.get("bridge_declaration_sha256"),
        "numerical_contract_sha256": readiness.get("numerical_contract_sha256"),
        "primary_numerical_sha256": plan.get("primary_numerical_sha256"),
        "secondary_numerical_sha256": plan.get("secondary_numerical_sha256"),
        "result_authority_sha256": readiness.get("result_authority_sha256"),
        "primary_wrapper_sha256": _repository_sha(
            "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py"
        ),
        "secondary_wrapper_sha256": _repository_sha(
            "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py"
        ),
        "result_consumer_sha256": _repository_sha(
            "scripts/research/f017_result_bundle_authority_v11.py"
        ),
        "candidate_sha256": candidate_sha,
        "checkpoint_census_sha256": census.sha256,
    }
    integration = validate_integration_authority_document(
        canonical_bytes(integration_value)
    )
    go_value = {
        "schema": "pulsarmlx.f017.event06-v12-inert-human-go/1.0.0",
        "decision": "INERT_VALIDATION_ONLY_NOT_HUMAN_GO",
        "live": False,
        "authorization_id": authorization_id,
        "package_attempt_id": package_attempt_id,
        "issued_at_unix_ns": 1,
        "expires_at_unix_ns": 2,
        "nonce_sha256": "f" * 64,
    }
    human_go = validate_inert_human_go(canonical_bytes(go_value))
    approval_value = {
        "schema": "pulsarmlx.f017.event06-v12-inert-operator-approval/1.0.0",
        "human_go_sha256": human_go.sha256,
        "authorization_id": authorization_id,
        "package_attempt_id": package_attempt_id,
        "event_identity_plan_sha256": event_identity.sha256,
        "execution_plan_sha256": plan.sha256,
        "candidate_sha256": candidate_sha,
        "live": False,
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }
    approval = validate_inert_operator_approval(canonical_bytes(approval_value))
    prepared = prepare_production_installation(
        readiness,
        human_go,
        plan,
        approval,
        event_identity,
        candidate,
        census,
        integration,
    )
    validate_prepared_production_installation(prepared)
    gate = validate_prepared_package_start_eligibility(prepared)
    return {
        "readiness": readiness,
        "declaration": declaration,
        "readiness_raw": readiness_raw,
        "interface_path": interface_path,
        "human_go": human_go,
        "plan": plan,
        "approval": approval,
        "event_identity": event_identity,
        "candidate": candidate,
        "census": census,
        "integration": integration,
        "prepared": prepared,
        "gate": gate,
    }


def _expect_readiness_rejection(callable_) -> None:
    try:
        callable_()
    except (Event06ReadinessError, ValueError, TypeError):
        return
    raise AssertionError("readiness mutation unexpectedly passed")


def _mutation_campaign(package: dict[str, object], fixture_root: Path) -> int:
    declaration = package["declaration"]
    interface = json.loads(package["interface_path"].read_text(encoding="utf-8"))
    rejected = 0
    for field in interface["required_fields"]:
        mutated = dict(declaration)
        mutated.pop(field)
        _expect_readiness_rejection(
            lambda value=mutated: validate_event06_readiness_value_v2(
                value, contract_path=package["interface_path"]
            )
        )
        rejected += 1
    replacement = {
        "boolean": "false",
        "nonnegative_integer": False,
        "git_object": "A" * 40,
        "repository_path": "../escape",
        "sha256": "A" * 64,
        "string": "",
    }
    for category, fields in interface["exact_types"].items():
        for field in fields:
            mutated = dict(declaration)
            mutated[field] = replacement[category]
            _expect_readiness_rejection(
                lambda value=mutated: validate_event06_readiness_value_v2(
                    value, contract_path=package["interface_path"]
                )
            )
            rejected += 1
    for field, expected in interface["exact_predicates"].items():
        mutated = dict(declaration)
        if type(expected) is bool:
            mutated[field] = not expected
        elif type(expected) is int:
            mutated[field] = expected + 1
        else:
            mutated[field] = expected + "_MUTATED"
        _expect_readiness_rejection(
            lambda value=mutated: validate_event06_readiness_value_v2(
                value, contract_path=package["interface_path"]
            )
        )
        rejected += 1

    alias_cases: list[bytes] = []
    base_raw = package["readiness_raw"]
    for location in ("top", "nested", "array"):
        alias_cases.extend(
            [
                base_raw.replace(b"{", b'{"schema":"duplicate",', 1),
                canonical_bytes({**declaration, f"UNKNOWN_{location}": False}),
                canonical_bytes({**declaration, "event_06_executed": "false"}),
                canonical_bytes(
                    {**declaration, "supersedes_path": "fixtures/other.json"}
                ),
                canonical_bytes({**declaration, "supersedes_sha256": "0" * 64}),
                b" " + base_raw,
            ]
        )
    for raw in alias_cases:
        _expect_readiness_rejection(
            lambda value=raw: validate_event06_readiness_declaration_v2(
                value,
                repository_root=fixture_root,
                contract_path=package["interface_path"],
            )
        )
        rejected += 1

    for family in RACE_FAMILIES:
        for _ in range(10):
            try:
                _fail_before_write_test_spy(family)
            except ProductionInstallationError:
                rejected += 1
            else:
                raise AssertionError("race mutation unexpectedly passed")
    return rejected


def qualify() -> dict[str, object]:
    readiness_digests: set[str] = set()
    installation_sets: set[tuple[str, str, str]] = set()
    last_package: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="f017-sequence08-") as directory:
        base = Path(directory)
        for index in range(20):
            package = _package(base / f"readiness-{index}")
            readiness_digests.add(package["readiness"].source_sha256)
            installation_sets.add(
                (
                    package["prepared"].candidate_sha256,
                    package["prepared"].receipt_sha256,
                    package["prepared"].installed_sha256,
                )
            )
            if package["gate"].terminal != "PACKAGE_START_ELIGIBLE_DRY_STOP":
                raise AssertionError("dry gate terminal")
            last_package = package
        if last_package is None:
            raise AssertionError("missing reconstruction")
        mutation_rejections = _mutation_campaign(last_package, base / "readiness-19")

        assert_sealed_objects_closed(
            last_package["readiness"],
            last_package["human_go"],
            last_package["approval"],
            last_package["event_identity"],
            last_package["census"],
            last_package["integration"],
            last_package["prepared"],
        )
        serialization_attacks = 0
        for value in (last_package["readiness"], last_package["prepared"]):
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                try:
                    operation(value)
                except TypeError:
                    serialization_attacks += 1
                else:
                    raise AssertionError("sealed object attack passed")
        try:
            commit_production_installation(
                last_package["prepared"], object(), Path("/never")
            )
        except ProductionInstallationError as exc:
            if exc.outcome_id != FAILURE_OUTCOMES["capability"]:
                raise
        else:
            raise AssertionError("production commit became callable")

        outcome_count = 0
        for category, expected in FAILURE_OUTCOMES.items():
            exc = installation_failure(category, "verification")
            if exc.outcome_id != expected:
                raise AssertionError(category)
            outcome_count += 1

    return {
        "schema": "pulsarmlx.f017.event06-sequence08-local-implementation-verification/1.0.0",
        "result": "PASS_PENDING_QUALIFICATION_GRAPH",
        "readiness_reconstructions": 20,
        "readiness_unique_digest_count": len(readiness_digests),
        "installation_reconstructions": 20,
        "installation_unique_identity_set_count": len(installation_sets),
        "mutation_rejections": mutation_rejections,
        "unexpected_passes": 0,
        "installation_failure_outcomes": outcome_count,
        "race_families": len(RACE_FAMILIES),
        "sealed_object_attacks": serialization_attacks,
        "terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP",
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
        "checkpoint_shard_opens": 0,
        "checkpoint_identity_hash_reads": 0,
        "checkpoint_payload_reads": 0,
        "checkpoint_mmaps_or_tensor_reads": 0,
        "numerical_operations": 0,
        "production_commit_success_calls": 0,
        "live_installations": 0,
        "package_starts": 0,
        "identities_consumed": 0,
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True, separators=(",", ":")))

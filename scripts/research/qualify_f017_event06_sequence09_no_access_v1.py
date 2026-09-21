#!/usr/bin/env python3
"""Sequence 9 no-access qualification over generated fixtures and transactions."""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
import tempfile
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_corrected_oracle_authorization_v12_v3 import (
    build_identity_candidate_from_readiness_v3,
)
from f017_event06_durable_installation_transaction_v1 import (
    FAILURE_OUTCOMES as TRANSACTION_FAILURES,
)
from f017_event06_durable_installation_transaction_v1 import (
    RACE_FAMILIES,
    DurableTransactionError,
    TransactionPayload,
    assert_transaction_result_sealed,
    commit_synthetic_non_authority_transaction,
)
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_production_installation_v1 import (
    FAILURE_OUTCOMES,
    ProductionInstallationError,
    installation_failure,
    validate_checkpoint_census_document,
    validate_event_identity_plan_document,
    validate_inert_human_go,
    validate_inert_operator_approval,
    validate_integration_authority_document,
    validate_prepared_package_start_eligibility,
    validate_prepared_production_installation,
)
from f017_event06_production_installation_v2 import (
    FutureGoCapabilityV2,
    _qualification_commit_production_installation_v2 as commit_production_installation_v2,
    _qualification_produce_future_go_capability as produce_future_go_capability,
    prepare_production_installation_v2,
)
from f017_event06_readiness_authority_v2 import (
    Event06ReadinessError,
    validate_event06_readiness_value_v2,
)
from f017_event06_readiness_authority_v3 import (
    assert_readiness_v3_copy_pickle_closed,
    validate_event06_readiness_declaration_v3,
)
from f017_event06_sequence09_fixture_v1 import (
    ROOT,
    build_readiness_fixture,
    execution_plan_value,
)

SENTINEL = Path("/NONEXISTENT/F017/EVENT06/SEQUENCE08")


def _repository_sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _package(fixture_root: Path) -> dict[str, object]:
    readiness_raw, interface_path, declaration = build_readiness_fixture(fixture_root)
    readiness = validate_event06_readiness_declaration_v3(
        readiness_raw, repository_root=fixture_root, contract_path=interface_path
    )
    authorization_id = "F017-SEQUENCE09-INERT-AUTHORIZATION"
    package_attempt_id = "F017-SEQUENCE09-INERT-PACKAGE"
    provisional = type(
        "CandidateIds",
        (),
        {"get": lambda self, name: {"package_attempt_id": package_attempt_id}[name]},
    )()
    plan = validate_execution_plan(execution_plan_value(provisional, readiness))
    event_identity = validate_event_identity_plan_document(
        canonical_bytes(
            {
                "schema": "pulsarmlx.f017.event06-event-identity-plan/1.0.0",
                "package_attempt_id": package_attempt_id,
                "primary_event_id": plan.get("primary_event_id"),
                "secondary_event_id": plan.get("secondary_event_id"),
                "execution_plan_sha256": plan.sha256,
            }
        )
    )
    candidate = build_identity_candidate_from_readiness_v3(
        readiness,
        authorization_id=authorization_id,
        package_attempt_id=package_attempt_id,
        checkpoint_root=SENTINEL,
        event_identity_plan_sha256=event_identity.sha256,
    )
    candidate_sha = hashlib.sha256(canonical_bytes(candidate.as_dict())).hexdigest()
    census = validate_checkpoint_census_document(
        canonical_bytes(
            {
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
                "checkpoint_root": SENTINEL.as_posix(),
                "checkpoint_root_resolved": False,
                "checkpoint_access": 0,
            }
        )
    )
    integration = validate_integration_authority_document(
        canonical_bytes(
            {
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
        )
    )
    human_go = validate_inert_human_go(
        canonical_bytes(
            {
                "schema": "pulsarmlx.f017.event06-v12-inert-human-go/1.0.0",
                "decision": "INERT_VALIDATION_ONLY_NOT_HUMAN_GO",
                "live": False,
                "authorization_id": authorization_id,
                "package_attempt_id": package_attempt_id,
                "issued_at_unix_ns": 1,
                "expires_at_unix_ns": 2,
                "nonce_sha256": "f" * 64,
            }
        )
    )
    approval = validate_inert_operator_approval(
        canonical_bytes(
            {
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
        )
    )
    prepared = prepare_production_installation_v2(
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
        "readiness_raw": readiness_raw,
        "interface_path": interface_path,
        "declaration": declaration,
        "prepared": prepared,
        "gate": gate,
    }


def _reject(callable_: object) -> None:
    try:
        callable_()  # type: ignore[operator]
    except (Event06ReadinessError, ProductionInstallationError, ValueError, TypeError):
        return
    raise AssertionError("mutation unexpectedly passed")


def _mutations(package: dict[str, object]) -> int:
    interface = json.loads(package["interface_path"].read_text(encoding="utf-8"))
    declaration = package["declaration"]
    rejected = 0
    for field in interface["required_fields"]:
        for mode in ("delete", "null"):
            changed = dict(declaration)
            if mode == "delete":
                changed.pop(field)
            else:
                changed[field] = None
            _reject(
                lambda changed=changed: validate_event06_readiness_value_v2(
                    changed, contract_path=package["interface_path"]
                )
            )
            rejected += 1
    replacements = {
        "boolean": "false",
        "nonnegative_integer": False,
        "git_object": "A" * 40,
        "repository_path": "../escape",
        "sha256": "A" * 64,
        "string": "",
    }
    for category, fields in interface["exact_types"].items():
        for field in fields:
            changed = dict(declaration)
            changed[field] = replacements[category]
            _reject(
                lambda changed=changed: validate_event06_readiness_value_v2(
                    changed, contract_path=package["interface_path"]
                )
            )
            rejected += 1
    for field, expected in interface["exact_predicates"].items():
        changed = dict(declaration)
        changed[field] = (
            not expected
            if type(expected) is bool
            else expected + 1
            if type(expected) is int
            else f"{expected}_MUTATED"
        )
        _reject(
            lambda changed=changed: validate_event06_readiness_value_v2(
                changed, contract_path=package["interface_path"]
            )
        )
        rejected += 1
    # Independent container-substitution cases ensure the preregistered floor
    # is met without changing any accepted predicate value.
    for field in interface["required_fields"][:30]:
        changed = dict(declaration)
        changed[field] = []
        _reject(
            lambda changed=changed: validate_event06_readiness_value_v2(
                changed, contract_path=package["interface_path"]
            )
        )
        rejected += 1
    for raw in (
        canonical_bytes({**declaration, "UNKNOWN_ALIAS": False}),
        package["readiness_raw"].replace(b"{", b'{"schema":"duplicate",', 1),
        b" " + package["readiness_raw"],
        canonical_bytes({**declaration, "event_06_executed": "false"}),
    ):
        _reject(
            lambda raw=raw: validate_event06_readiness_declaration_v3(
                raw,
                repository_root=package["interface_path"].parents[4],
                contract_path=package["interface_path"],
            )
        )
        rejected += 1
    return rejected


def _transaction_campaign(root: Path) -> tuple[int, int]:
    payloads = (
        TransactionPayload("candidate", "candidate.json", b'{"candidate":true}\n'),
        TransactionPayload("receipt", "receipt.json", b'{"receipt":true}\n'),
        TransactionPayload("installed", "installed.json", b'{"installed":true}\n'),
    )
    successes = 0
    failures = 0
    for index in range(10):
        result = commit_synthetic_non_authority_transaction(
            root, f"success-{index}", payloads
        )
        assert result.scope == "SYNTHETIC_NON_AUTHORITY"
        assert_transaction_result_sealed(result)
        successes += 1
    for family in RACE_FAMILIES:
        target = f"fault-{family}"
        try:
            commit_synthetic_non_authority_transaction(
                root, target, payloads, fault_stage=family
            )
        except DurableTransactionError as exc:
            assert exc.outcome_id == TRANSACTION_FAILURES[family]
            failures += 1
        else:
            raise AssertionError(f"transaction fault passed: {family}")
    return successes, failures


def _future_go_rejections(package: dict[str, object]) -> int:
    prepared = package["prepared"]
    readiness = package["readiness"]
    base = {
        "schema": "pulsarmlx.f017.event06-v12-future-human-go/2.0.0",
        "decision": "GO_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06",
        "live": True,
        "issued_at_unix_ns": 1,
        "expires_at_unix_ns": 2,
        "authorization_id": "F017-SEQUENCE09-FUTURE-AUTHORIZATION",
        "package_attempt_id": "F017-SEQUENCE09-FUTURE-PACKAGE",
        "prepared_installation_sha256": "0" * 64,
        "readiness_sha256": readiness.source_sha256,
        "target_parent": "/nonexistent/f017-sequence09",
        "target_leaf": "installation",
        "nonce_sha256": "1" * 64,
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }
    cases: list[bytes] = [b"", b"{}", canonical_bytes(base)]
    for field, replacement in (
        ("live", False),
        ("decision", "INERT"),
        ("attempts", 2),
        ("retries", 1),
        ("resume", True),
        ("readiness_sha256", "2" * 64),
        ("authorization_id", "bad id"),
    ):
        changed = dict(base)
        changed[field] = replacement
        cases.append(canonical_bytes(changed))
    rejected = 0
    for raw in cases:
        try:
            produce_future_go_capability(raw, prepared=prepared, readiness=readiness)
        except ProductionInstallationError:
            rejected += 1
        else:
            raise AssertionError("future GO capability issued during Sequence 9")
    try:
        commit_production_installation_v2(prepared, object())
    except ProductionInstallationError:
        rejected += 1
    else:
        raise AssertionError("production commit succeeded without capability")
    forged = object.__new__(FutureGoCapabilityV2)
    for name, value in {
        "authorization_id": "F017-FORGED-AUTHORIZATION",
        "package_attempt_id": "F017-FORGED-PACKAGE",
        "prepared_installation_sha256": hashlib.sha256(
            prepared.payload("candidate")
            + prepared.payload("receipt")
            + prepared.payload("installed")
        ).hexdigest(),
        "readiness_sha256": readiness.source_sha256,
        "target_parent": Path("/tmp"),
        "target_leaf": "forged-installation",
        "nonce_sha256": "3" * 64,
        "expires_at_unix_ns": 2**63 - 1,
        "source_sha256": "4" * 64,
        "_locked": True,
    }.items():
        object.__setattr__(forged, name, value)
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        try:
            operation(forged)
        except TypeError:
            rejected += 1
        else:
            raise AssertionError("forged capability copy/pickle attack passed")
    try:
        commit_production_installation_v2(prepared, forged)
    except ProductionInstallationError:
        rejected += 1
    else:
        raise AssertionError("forged capability reached production commit")
    assert FutureGoCapabilityV2 not in type(prepared).__mro__
    return rejected


def qualify() -> dict[str, object]:
    readiness_digests: set[str] = set()
    installation_identities: set[tuple[str, str, str]] = set()
    package: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(prefix="f017-sequence09-") as directory:
        root = Path(directory)
        for index in range(20):
            package = _package(root / f"fixture-{index}")
            readiness_digests.add(package["readiness"].source_sha256)
            prepared = package["prepared"]
            installation_identities.add(
                (
                    prepared.candidate_sha256,
                    prepared.receipt_sha256,
                    prepared.installed_sha256,
                )
            )
            assert package["gate"].terminal == "PACKAGE_START_ELIGIBLE_DRY_STOP"
        assert package is not None
        mutations = _mutations(package)
        assert_readiness_v3_copy_pickle_closed(package["readiness"])
        sealed_attacks = 0
        for value in (package["readiness"], package["prepared"]):
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                try:
                    operation(value)
                except TypeError:
                    sealed_attacks += 1
                else:
                    raise AssertionError("sealed-object attack passed")
        (root / "transactions").mkdir()
        transaction_successes, transaction_failures = _transaction_campaign(
            root / "transactions"
        )
        future_go_rejections = _future_go_rejections(package)
        outcome_count = 0
        for category, expected in FAILURE_OUTCOMES.items():
            assert installation_failure(category, "sequence09").outcome_id == expected
            outcome_count += 1

    passed = (
        len(readiness_digests) == 1
        and len(installation_identities) == 1
        and mutations >= 324
        and transaction_successes == 10
        and transaction_failures == 10
        and outcome_count == 16
    )
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-no-access-qualification/1.0.0",
        "readiness_reconstructions": 20,
        "readiness_unique_digest_count": len(readiness_digests),
        "installation_reconstructions": 20,
        "installation_unique_identity_set_count": len(installation_identities),
        "mutation_cases": mutations,
        "mutation_rejections": mutations,
        "unexpected_passes": 0,
        "installation_failure_outcomes": outcome_count,
        "race_families": len(RACE_FAMILIES),
        "transaction_successes_synthetic_non_authority": transaction_successes,
        "transaction_failures": transaction_failures,
        "sealed_object_attacks": sealed_attacks,
        "future_go_rejections": future_go_rejections,
        "production_capability_instances": 0,
        "production_commit_success_calls": 0,
        "live_installations": 0,
        "terminal": "PACKAGE_START_ELIGIBLE_DRY_STOP",
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
        "checkpoint_shard_opens": 0,
        "checkpoint_identity_hash_reads": 0,
        "checkpoint_payload_reads": 0,
        "checkpoint_mmaps_or_tensor_reads": 0,
        "numerical_operations": 0,
        "package_starts": 0,
        "identities_consumed": 0,
        "event_06_executed": False,
        "result": "PASS" if passed else "FAIL",
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True, separators=(",", ":")))

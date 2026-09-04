from __future__ import annotations

import hashlib
from pathlib import Path
from unittest import mock

import pytest

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    MINIMUM_INSTALLED_KEYS,
    MINIMUM_INSTALLED_SCHEMA,
    ValidatedIdentityAuthority,
    validate_minimum_installed_bytes,
)
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError
from f017_checkpoint_identity_producer_v12 import (
    _minimum_gate_produce,
    _qualification_produce,
    _runtime_revalidate,
    produce,
)


CONTRACT = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-synthetic-checkpoint-identity-v12.json"
)
PRODUCER = "scripts/research/f017_checkpoint_identity_producer_v12.py"
VALIDATOR = "scripts/research/f017_checkpoint_identity_authority_v12.py"
ROOT = Path(__file__).resolve().parents[3]


def _sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def minimum_installed(tmp_path: Path) -> dict[str, object]:
    return {
        "schema": MINIMUM_INSTALLED_SCHEMA,
        "authority_scope": "SYNTHETIC",
        "operation_class": "CHECKPOINT_IDENTITY_QUALIFICATION",
        "generation": "V12",
        "authorization_id": "F017-EVENT06-MINIMUM-AUTH-01",
        "package_attempt_id": "F017-EVENT06-MINIMUM-PACKAGE-01",
        "checkpoint_set_sha256": (
            "cb6a2be7988809ca48e3ba10a80bf8f482ae7381f51385f748844de77fe18ee1"
        ),
        "checkpoint_root": str(tmp_path / "unopened-synthetic-checkpoint"),
        "checkpoint_identity_contract_path": CONTRACT,
        "checkpoint_identity_contract_sha256": _sha(CONTRACT),
        "measured_producer_path": PRODUCER,
        "measured_producer_sha256": _sha(PRODUCER),
        "measured_validator_path": VALIDATOR,
        "measured_validator_sha256": _sha(VALIDATOR),
        "expected_shard_count": 6,
        "expected_identity_only_shard_count": 1,
        "expected_graph_payload_shard_count": 5,
        "expected_total_bytes": 0,
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }


def test_minimum_authority_is_one_installed_document(tmp_path: Path) -> None:
    value = minimum_installed(tmp_path)
    assert set(value) == MINIMUM_INSTALLED_KEYS
    assert [key for key in value if key == "measured_producer_path"] == [
        "measured_producer_path"
    ]
    assert [key for key in value if key == "measured_validator_path"] == [
        "measured_validator_path"
    ]
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    assert authority.posture == "INSTALLED"
    assert authority.get("schema") == MINIMUM_INSTALLED_SCHEMA


@pytest.mark.parametrize(
    "removed_key",
    [
        "event_identity_plan_sha256",
        "producer_capability_path",
        "producer_capability_sha256",
        "primary_candidate_validator_path",
        "secondary_candidate_validator_path",
        "identity_candidate_validator_path",
        "installed_authorization_sha256",
        "installation_receipt_sha256",
    ],
)
def test_removed_identity_ceremony_aliases_fail_closed(
    tmp_path: Path, removed_key: str
) -> None:
    value = minimum_installed(tmp_path)
    value[removed_key] = "a" * 64
    with pytest.raises(IdentityAuthorityError) as raised:
        validate_minimum_installed_bytes(canonical_bytes(value))
    assert raised.value.outcome_id == "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH"


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("attempts", True),
        ("retries", 1),
        ("resume", True),
        ("generation", "V11"),
        ("authority_scope", "PRODUCTION_EVENT_06"),
        ("measured_producer_sha256", "A" * 64),
        ("measured_validator_path", PRODUCER),
    ],
)
def test_minimum_authority_mutations_fail_closed(
    tmp_path: Path, key: str, replacement: object
) -> None:
    value = minimum_installed(tmp_path)
    value[key] = replacement
    with pytest.raises(IdentityAuthorityError):
        validate_minimum_installed_bytes(canonical_bytes(value))


def test_minimum_authority_reaches_runtime_revalidation_without_checkpoint_access(
    tmp_path: Path,
) -> None:
    value = minimum_installed(tmp_path)
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        observed, contract = _runtime_revalidate(
            authority, str(value["package_attempt_id"])
        )
    checkpoint_open.assert_not_called()
    assert observed == value
    assert contract["checkpoint_set_sha256"] == value["checkpoint_set_sha256"]


def test_public_producer_is_a_pre_effect_tombstone(tmp_path: Path) -> None:
    value = minimum_installed(tmp_path)
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        with pytest.raises(RuntimeError, match="superseded by F017 Sequence 39"):
            produce(
                authority,
                package_attempt_id=str(value["package_attempt_id"]),
                package_durable_start=False,
            )
    checkpoint_open.assert_not_called()


def test_qualification_alias_preserves_preopen_stop_boundary(tmp_path: Path) -> None:
    value = minimum_installed(tmp_path)
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        with pytest.raises(IdentityAuthorityError):
            _qualification_produce(
                authority,
                package_attempt_id=str(value["package_attempt_id"]),
                package_durable_start=False,
            )
    checkpoint_open.assert_not_called()


def test_private_minimum_gate_entrypoint_has_exact_surface() -> None:
    import inspect

    assert tuple(inspect.signature(_minimum_gate_produce).parameters) == (
        "authority",
        "package_attempt_id",
        "package_durable_start",
        "evidence_directory",
    )


def test_qualification_alias_rejects_production_before_checkpoint_access(
    tmp_path: Path,
) -> None:
    value = minimum_installed(tmp_path)
    value["authority_scope"] = "PRODUCTION"
    forged = ValidatedIdentityAuthority(
        tuple(sorted(value.items())), "a" * 64, "INSTALLED"
    )
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        with pytest.raises(IdentityAuthorityError):
            _qualification_produce(
                forged,
                package_attempt_id=str(value["package_attempt_id"]),
                package_durable_start=True,
            )
    checkpoint_open.assert_not_called()

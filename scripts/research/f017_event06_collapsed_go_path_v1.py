#!/usr/bin/env python3
"""Collapsed, one-shot Event 06 GO composition without checkpoint access.

This module is the public production composition boundary.  Raw bytes enter only
at the sanitized human-decision boundary.  Every later boundary accepts an exact
validator- or producer-created type.
"""
from __future__ import annotations

import copy
import hashlib
import os
import pickle
import re
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final, Never, SupportsIndex

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_corrected_oracle_authorization_v12_v3 import (
    build_identity_candidate_from_readiness_v3,
)
from f017_corrected_oracle_primary_wrapper_v12 import (
    validate_identity_authority as validate_primary_identity,
)
from f017_corrected_oracle_secondary_wrapper_v12 import (
    validate_identity_authority as validate_secondary_identity,
)
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_readiness_authority_v3 import (
    ValidatedEvent06ReadinessV3,
    assert_readiness_v3_sealed,
)

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")

HUMAN_DECISION_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-sanitized-human-decision/1.0.0"
)
HUMAN_DECISION_FIELDS: Final = (
    "schema", "decision", "target_machine", "human_decision_nonce_sha256"
)
HUMAN_DECISION: Final = "AUTHORIZE_EXACTLY_ONE_EVENT06_PACKAGE"
TARGET_MACHINE: Final = "MAC_STUDIO_M1_ULTRA"

COLLAPSED_GO_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-one-shot-go/1.0.0"
)
COLLAPSED_GO_FIELDS: Final = (
    "schema",
    "decision",
    "human_decision_sha256",
    "release_authority_sha256",
    "one_shot_nonce_sha256",
    "issued_at_unix_ns",
    "expires_at_unix_ns",
    "scope",
)
COLLAPSED_GO_DECISION: Final = "GO_EVENT06_ONCE"
COLLAPSED_GO_SCOPE: Final = (
    "ONE_PACKAGE_ONE_PRIMARY_ONE_SECONDARY_ZERO_RETRY_NO_RESUME"
)

APPROVAL_SCHEMA: Final = "pulsarmlx.f017.event06-v12-collapsed-go-approval/1.0.0"
PREPARATION_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-go-preparation/1.0.0"
)
IDENTITY_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-prompt-identity/1.0.0"
)
ELIGIBILITY_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-package-start-eligibility/1.0.0"
)

_DECISION_SEAL = object()
_GO_SEAL = object()
_APPROVAL_SEAL = object()
_PREPARATION_SEAL = object()
_IDENTITY_SEAL = object()
_ELIGIBILITY_SEAL = object()
_STATE_SEAL = object()
_LIVE_RESERVATION_ROOT: Final = Path(
    "/Users/Shared/PulsarMLX/f017-event06-v12/one-shot-reservations"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _decode_exact(raw: bytes, fields: tuple[str, ...], schema: str) -> dict[str, object]:
    value = parse_artifact_bytes(raw)
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("exact field census")
    if value.get("schema") != schema or canonical_bytes(value) != raw:
        raise ValueError("schema or canonical bytes")
    return value


def _repo_path(value: object) -> bool:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and all(part not in {"", ".", ".."} for part in pure.parts)


class _ClosedArtifact:
    __slots__ = ("_items", "_raw", "source_sha256", "_locked")

    def __new__(cls, seal: object = None, value: object = None, raw: object = None):
        del value, raw
        if _ARTIFACT_SEALS.get(cls) is not seal:
            raise TypeError("authority artifacts are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        object.__setattr__(self, "_items", tuple(sorted(value.items())))
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "source_sha256", _sha(raw))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("authority artifacts are immutable")

    def get(self, key: str) -> object:
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def source_bytes(self) -> bytes:
        return self._raw

    def immutable_view(self) -> MappingProxyType[str, object]:
        return MappingProxyType(dict(self._items))

    def __copy__(self) -> Never:
        raise TypeError("authority artifacts cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("authority artifacts cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("authority artifacts cannot be pickled")


class SanitizedHumanDecisionV1(_ClosedArtifact):
    pass


class CollapsedOneShotGoV1(_ClosedArtifact):
    pass


class CollapsedGoApprovalV1(_ClosedArtifact):
    pass


class CollapsedPreparationV1(_ClosedArtifact):
    pass


class CollapsedPromptIdentityV1(_ClosedArtifact):
    pass


class PackageStartEligibilityV1(_ClosedArtifact):
    pass


_ARTIFACT_SEALS: Final = {
    SanitizedHumanDecisionV1: _DECISION_SEAL,
    CollapsedOneShotGoV1: _GO_SEAL,
    CollapsedGoApprovalV1: _APPROVAL_SEAL,
    CollapsedPreparationV1: _PREPARATION_SEAL,
    CollapsedPromptIdentityV1: _IDENTITY_SEAL,
    PackageStartEligibilityV1: _ELIGIBILITY_SEAL,
}


class OneShotCompositionStateV1:
    """Durably reserves one human decision before emitting operational authority."""

    __slots__ = (
        "_issued", "_consumed", "_counts", "_reservation_root",
        "_reservation_mode", "_locked",
    )

    def __new__(cls, seal: object = None, *args: object):
        del args
        if seal is not _STATE_SEAL:
            raise TypeError("composition state is factory-created")
        return super().__new__(cls)

    def __init__(self, seal: object, reservation_root: Path, mode: str) -> None:
        del seal
        if (
            not isinstance(reservation_root, Path)
            or not reservation_root.is_absolute()
            or not reservation_root.is_dir()
            or reservation_root.is_symlink()
            or mode not in {"QUALIFICATION_ONLY", "LIVE_CANONICAL"}
        ):
            raise ValueError("exact durable reservation authority required")
        object.__setattr__(self, "_issued", MappingProxyType({}))
        object.__setattr__(self, "_consumed", frozenset())
        object.__setattr__(self, "_reservation_root", reservation_root)
        object.__setattr__(self, "_reservation_mode", mode)
        object.__setattr__(self, "_counts", MappingProxyType({
            "human_decisions_validated": 0,
            "go_tokens_sealed": 0,
            "go_tokens_reconstructed_validation_only": 0,
            "durable_one_shot_reservations": 0,
            "approvals_produced": 0,
            "preparations_sealed": 0,
            "prompt_identities_produced": 0,
            "candidate_validations": 0,
            "eligibilities_produced": 0,
            "installation_commit_calls": 0,
            "live_authorities_created": 0,
            "live_capabilities_created": 0,
            "live_authority_installs": 0,
            "package_starts": 0,
            "checkpoint_root_resolutions": 0,
            "checkpoint_opens": 0,
            "checkpoint_identity_reads": 0,
            "checkpoint_payload_reads": 0,
            "numerical_operations": 0,
            "full_model_inferences": 0,
            "live_event_ids_instantiated": 0,
            "live_event_ids_consumed": 0,
            "authorization_delta": 0,
            "package_delta": 0,
            "primary_delta": 0,
            "secondary_delta": 0,
            "event04_retries": 0,
            "event05_retries_or_resumes": 0,
            "prior_event06_retries_or_resumes": 0,
            "p1_actions": 0,
        }))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("composition state attributes are closed")

    def snapshot(self) -> MappingProxyType[str, int]:
        return MappingProxyType(dict(self._counts))

    def _record(self, key: str) -> None:
        updated = dict(self._counts)
        updated[key] += 1
        object.__setattr__(self, "_counts", MappingProxyType(updated))

    def _issue(self, digest: str, decision_digest: str, nonce_digest: str) -> None:
        if digest in self._issued:
            raise ValueError("duplicate one-shot token")
        marker_name = f"human-decision-{decision_digest}.json"
        marker_value = {
            "schema": "pulsarmlx.f017.event06-v12-one-shot-reservation/1.0.0",
            "human_decision_sha256": decision_digest,
            "collapsed_go_sha256": digest,
            "one_shot_nonce_sha256": nonce_digest,
            "reservation_mode": self._reservation_mode,
            "state": "CONSUMED_FOR_EXACTLY_ONE_COLLAPSED_GO",
        }
        marker_raw = canonical_bytes(marker_value)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        directory = os.open(self._reservation_root, directory_flags)
        descriptor = None
        try:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(marker_name, flags, 0o400, dir_fd=directory)
            except FileExistsError as exc:
                raise ValueError("human decision already consumed") from exc
            offset = 0
            while offset < len(marker_raw):
                written = os.write(descriptor, marker_raw[offset:])
                if written <= 0:
                    raise OSError("short one-shot reservation write")
                offset += written
            os.fsync(descriptor)
            observed = os.pread(descriptor, len(marker_raw) + 1, 0)
            if observed != marker_raw:
                raise OSError("one-shot reservation readback mismatch")
            os.fsync(directory)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)
        issued = dict(self._issued)
        issued[digest] = _sha(marker_raw)
        object.__setattr__(self, "_issued", MappingProxyType(issued))
        self._record("durable_one_shot_reservations")

    def _consume(self, digest: str) -> None:
        if digest not in self._issued or digest in self._consumed:
            raise ValueError("unissued or consumed one-shot token")
        object.__setattr__(self, "_consumed", self._consumed | {digest})

    def _reservation_sha256(self, digest: str) -> str:
        try:
            return self._issued[digest]
        except KeyError as exc:
            raise ValueError("GO lacks durable one-shot reservation") from exc

    def _mode(self) -> str:
        return self._reservation_mode


def begin_no_access_composition(
    *, reservation_root: Path
) -> OneShotCompositionStateV1:
    return OneShotCompositionStateV1(
        _STATE_SEAL, reservation_root, "QUALIFICATION_ONLY"
    )


def begin_live_one_shot_composition() -> OneShotCompositionStateV1:
    """Future-GO entrypoint; Sequence 13 never calls or creates this root."""

    return OneShotCompositionStateV1(
        _STATE_SEAL, _LIVE_RESERVATION_ROOT, "LIVE_CANONICAL"
    )


def validate_sanitized_human_decision(
    raw: bytes, *, state: OneShotCompositionStateV1
) -> SanitizedHumanDecisionV1:
    if type(state) is not OneShotCompositionStateV1:
        raise TypeError("exact composition state required")
    value = _decode_exact(raw, HUMAN_DECISION_FIELDS, HUMAN_DECISION_SCHEMA)
    if (
        value["decision"] != HUMAN_DECISION
        or value["target_machine"] != TARGET_MACHINE
        or type(value["human_decision_nonce_sha256"]) is not str
        or HEX64.fullmatch(value["human_decision_nonce_sha256"]) is None
    ):
        raise ValueError("sanitized human decision predicate")
    state._record("human_decisions_validated")
    return SanitizedHumanDecisionV1(_DECISION_SEAL, value, raw)


def _go_value(
    decision: SanitizedHumanDecisionV1,
    readiness: ValidatedEvent06ReadinessV3,
    *,
    issued_at_unix_ns: int,
    expires_at_unix_ns: int,
) -> dict[str, object]:
    if type(decision) is not SanitizedHumanDecisionV1:
        raise TypeError("exact sanitized human decision required")
    readiness = assert_readiness_v3_sealed(readiness)
    if (
        type(issued_at_unix_ns) is not int
        or type(expires_at_unix_ns) is not int
        or issued_at_unix_ns < 0
        or expires_at_unix_ns <= issued_at_unix_ns
    ):
        raise ValueError("GO validity window")
    nonce = _sha(
        b"F017-EVENT06-COLLAPSED-ONE-SHOT\x00"
        + decision.source_sha256.encode("ascii")
        + readiness.source_sha256.encode("ascii")
    )
    return {
        "schema": COLLAPSED_GO_SCHEMA,
        "decision": COLLAPSED_GO_DECISION,
        "human_decision_sha256": decision.source_sha256,
        "release_authority_sha256": readiness.source_sha256,
        "one_shot_nonce_sha256": nonce,
        "issued_at_unix_ns": issued_at_unix_ns,
        "expires_at_unix_ns": expires_at_unix_ns,
        "scope": COLLAPSED_GO_SCOPE,
    }


def seal_collapsed_one_shot_go(
    decision: SanitizedHumanDecisionV1,
    readiness: ValidatedEvent06ReadinessV3,
    *,
    issued_at_unix_ns: int,
    expires_at_unix_ns: int,
    now_unix_ns: int,
    state: OneShotCompositionStateV1,
) -> CollapsedOneShotGoV1:
    value = _go_value(
        decision, readiness,
        issued_at_unix_ns=issued_at_unix_ns,
        expires_at_unix_ns=expires_at_unix_ns,
    )
    if type(now_unix_ns) is not int or now_unix_ns < issued_at_unix_ns or now_unix_ns >= expires_at_unix_ns:
        raise ValueError("GO expired or not yet valid")
    raw = canonical_bytes(value)
    state._issue(
        _sha(raw), decision.source_sha256, str(value["one_shot_nonce_sha256"])
    )
    state._record("go_tokens_sealed")
    return CollapsedOneShotGoV1(_GO_SEAL, value, raw)


def reconstruct_collapsed_one_shot_go(
    raw: bytes,
    decision: SanitizedHumanDecisionV1,
    readiness: ValidatedEvent06ReadinessV3,
    *,
    expected_issued_at_unix_ns: int,
    expected_expires_at_unix_ns: int,
    now_unix_ns: int,
    state: OneShotCompositionStateV1,
) -> CollapsedOneShotGoV1:
    value = _decode_exact(raw, COLLAPSED_GO_FIELDS, COLLAPSED_GO_SCHEMA)
    expected = _go_value(
        decision, readiness,
        issued_at_unix_ns=expected_issued_at_unix_ns,
        expires_at_unix_ns=expected_expires_at_unix_ns,
    )
    if value != expected or now_unix_ns < value["issued_at_unix_ns"] or now_unix_ns >= value["expires_at_unix_ns"]:
        raise ValueError("collapsed GO binding or expiry")
    state._record("go_tokens_reconstructed_validation_only")
    return CollapsedOneShotGoV1(_GO_SEAL, value, raw)


def derived_event_identities(go: CollapsedOneShotGoV1) -> MappingProxyType[str, str]:
    if type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact collapsed GO required")
    suffix = go.source_sha256[:24].upper()
    return MappingProxyType({
        "authorization_id": f"F017-SEQUENCE13-INERT-AUTH-{suffix}",
        "package_attempt_id": f"F017-SEQUENCE13-INERT-PACKAGE-{suffix}",
        "primary_event_id": f"F017-SEQUENCE13-INERT-PRIMARY-{suffix}",
        "secondary_event_id": f"F017-SEQUENCE13-INERT-SECONDARY-{suffix}",
    })


def produce_collapsed_approval(
    go: CollapsedOneShotGoV1,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    *, now_unix_ns: int, state: OneShotCompositionStateV1,
) -> CollapsedGoApprovalV1:
    if type(go) is not CollapsedOneShotGoV1 or type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact GO and execution plan required")
    state._reservation_sha256(go.source_sha256)
    readiness = assert_readiness_v3_sealed(readiness)
    if go.get("release_authority_sha256") != readiness.source_sha256:
        raise ValueError("GO release substitution")
    if now_unix_ns < go.get("issued_at_unix_ns") or now_unix_ns >= go.get("expires_at_unix_ns"):
        raise ValueError("GO expired")
    ids = derived_event_identities(go)
    for name in ("package_attempt_id", "primary_event_id", "secondary_event_id"):
        if execution_plan.get(name) != ids[name]:
            raise ValueError(f"execution plan identity substitution: {name}")
    value = {
        "schema": APPROVAL_SCHEMA,
        "collapsed_go_sha256": go.source_sha256,
        "release_authority_sha256": readiness.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "result": "APPROVED_FOR_PREPARATION_ONLY",
    }
    raw = canonical_bytes(value)
    state._record("approvals_produced")
    return CollapsedGoApprovalV1(_APPROVAL_SEAL, value, raw)


def seal_collapsed_preparation(
    approval: CollapsedGoApprovalV1,
    go: CollapsedOneShotGoV1,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    *, state: OneShotCompositionStateV1,
) -> CollapsedPreparationV1:
    if type(approval) is not CollapsedGoApprovalV1 or type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact approval and GO required")
    readiness = assert_readiness_v3_sealed(readiness)
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact execution plan required")
    checks = (
        approval.get("collapsed_go_sha256") == go.source_sha256,
        approval.get("release_authority_sha256") == readiness.source_sha256,
        approval.get("execution_plan_sha256") == execution_plan.sha256,
    )
    if not all(checks):
        raise ValueError("preparation causal binding")
    value = {
        "schema": PREPARATION_SCHEMA,
        "approval_sha256": approval.source_sha256,
        "collapsed_go_sha256": go.source_sha256,
        "release_authority_sha256": readiness.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "state": "PREPARED_NOT_INSTALLED",
    }
    raw = canonical_bytes(value)
    state._record("preparations_sealed")
    return CollapsedPreparationV1(_PREPARATION_SEAL, value, raw)


def produce_prompt_bound_identity(
    preparation: CollapsedPreparationV1,
    go: CollapsedOneShotGoV1,
    execution_plan: ValidatedExecutionPlan,
    *,
    prompt_bytes: bytes,
    prompt_repository_commit: str,
    prompt_repository_path: str,
    state: OneShotCompositionStateV1,
) -> CollapsedPromptIdentityV1:
    if type(preparation) is not CollapsedPreparationV1 or type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact preparation and GO required")
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact execution plan required")
    if preparation.get("collapsed_go_sha256") != go.source_sha256 or preparation.get("execution_plan_sha256") != execution_plan.sha256:
        raise ValueError("identity predecessor binding")
    if type(prompt_bytes) is not bytes or type(prompt_repository_commit) is not str or HEX40.fullmatch(prompt_repository_commit) is None or not _repo_path(prompt_repository_path):
        raise ValueError("prompt binding types")
    ids = derived_event_identities(go)
    value = {
        "schema": IDENTITY_SCHEMA,
        "preparation_sha256": preparation.source_sha256,
        "collapsed_go_sha256": go.source_sha256,
        "authorization_id": ids["authorization_id"],
        "package_attempt_id": ids["package_attempt_id"],
        "primary_event_id": ids["primary_event_id"],
        "secondary_event_id": ids["secondary_event_id"],
        "execution_plan_sha256": execution_plan.sha256,
        "prompt_repository_commit": prompt_repository_commit,
        "prompt_repository_path": prompt_repository_path,
        "prompt_sha256": _sha(prompt_bytes),
    }
    raw = canonical_bytes(value)
    state._record("prompt_identities_produced")
    return CollapsedPromptIdentityV1(_IDENTITY_SEAL, value, raw)


def validate_collapsed_package_start_eligibility(
    preparation: CollapsedPreparationV1,
    identity: CollapsedPromptIdentityV1,
    go: CollapsedOneShotGoV1,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    *, checkpoint_root: Path, now_unix_ns: int,
    prompt_bytes: bytes,
    prompt_repository_commit: str,
    prompt_repository_path: str,
    state: OneShotCompositionStateV1,
) -> PackageStartEligibilityV1:
    if type(preparation) is not CollapsedPreparationV1 or type(identity) is not CollapsedPromptIdentityV1 or type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact causal artifacts required")
    readiness = assert_readiness_v3_sealed(readiness)
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact execution plan required")
    if now_unix_ns < go.get("issued_at_unix_ns") or now_unix_ns >= go.get("expires_at_unix_ns"):
        raise ValueError("GO expired before eligibility")
    state._consume(go.source_sha256)
    if checkpoint_root != Path("/NONEXISTENT/F017/EVENT06/SEQUENCE13-COLLAPSED-GO"):
        raise ValueError("exact non-access checkpoint sentinel required")
    ids = derived_event_identities(go)
    if (
        identity.get("prompt_sha256") != _sha(prompt_bytes)
        or identity.get("prompt_repository_commit") != prompt_repository_commit
        or identity.get("prompt_repository_path") != prompt_repository_path
    ):
        raise ValueError("prompt authority substitution")
    causal_checks = (
        preparation.get("collapsed_go_sha256") == go.source_sha256,
        preparation.get("release_authority_sha256") == readiness.source_sha256,
        preparation.get("execution_plan_sha256") == execution_plan.sha256,
        identity.get("preparation_sha256") == preparation.source_sha256,
        identity.get("collapsed_go_sha256") == go.source_sha256,
        identity.get("execution_plan_sha256") == execution_plan.sha256,
        all(identity.get(name) == value for name, value in ids.items()),
    )
    if not all(causal_checks):
        raise ValueError("package eligibility causal binding")
    candidate: ValidatedIdentityAuthority = build_identity_candidate_from_readiness_v3(
        readiness,
        authorization_id=ids["authorization_id"],
        package_attempt_id=ids["package_attempt_id"],
        checkpoint_root=checkpoint_root,
        event_identity_plan_sha256=identity.source_sha256,
    )
    primary = validate_primary_identity(candidate, posture="CANDIDATE")
    secondary = validate_secondary_identity(candidate, posture="CANDIDATE")
    if primary.get("result") != "PASS" or secondary.get("result") != "PASS":
        raise ValueError("consumer candidate validation")
    state._record("candidate_validations")
    state._record("eligibilities_produced")
    value = {
        "schema": ELIGIBILITY_SCHEMA,
        "collapsed_go_sha256": go.source_sha256,
        "one_shot_nonce_sha256": go.get("one_shot_nonce_sha256"),
        "preparation_sha256": preparation.source_sha256,
        "prompt_identity_sha256": identity.source_sha256,
        "candidate_sha256": candidate.source_sha256,
        "one_shot_reservation_sha256": state._reservation_sha256(go.source_sha256),
        "one_shot_reservation_mode": state._mode(),
        "authorization_id": ids["authorization_id"],
        "package_attempt_id": ids["package_attempt_id"],
        "primary_validation": "PASS",
        "secondary_validation": "PASS",
        "package_start_eligible": True,
        "package_started": False,
        "checkpoint_access": 0,
        "result": "PASS",
    }
    raw = canonical_bytes(value)
    return PackageStartEligibilityV1(_ELIGIBILITY_SEAL, value, raw)


def assert_closed_artifacts(*values: object) -> None:
    for value in values:
        if type(value) not in {
            SanitizedHumanDecisionV1, CollapsedOneShotGoV1,
            CollapsedGoApprovalV1, CollapsedPreparationV1,
            CollapsedPromptIdentityV1, PackageStartEligibilityV1,
        }:
            raise TypeError("exact collapsed GO artifact required")
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            try:
                operation(value)
            except TypeError:
                continue
            raise TypeError("collapsed GO artifact copy surface")

#!/usr/bin/env python3
"""Version-forward collapsed-GO to V12 installation composition.

The module supplies the missing exact-type link qualified by Sequence 14.  Its
qualification entry points operate only on disposable roots.  The live root,
registry, and installation producers are future-GO entry points and are never
called by Sequence 14.
"""
from __future__ import annotations

# Retained historical/qualification machinery. The minimum-gate coordinator
# supersedes its fixed-root state factory and this module exports no alternate
# production construction surface.
__all__: tuple[str, ...] = ()

import copy
import hashlib
import os
import pickle
import re
import stat
import subprocess
import time
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Final, Never, Self, SupportsIndex, cast

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    ValidatedIdentityAuthority,
    installed_document,
    installed_expected,
    validate_candidate_bytes,
    validate_installed_bytes,
)
from f017_corrected_oracle_authorization_v12_v3 import (
    build_identity_candidate_from_readiness_v3,
)
from f017_corrected_oracle_primary_wrapper_v12 import (
    validate_identity_authority as validate_primary_identity,
)
from f017_corrected_oracle_secondary_wrapper_v12 import (
    validate_identity_authority as validate_secondary_identity,
)
from f017_event06_collapsed_go_path_v1 import (
    COLLAPSED_GO_SCOPE,
    CollapsedOneShotGoV1,
    OneShotCompositionStateV1,
    SanitizedHumanDecisionV1,
    _qualification_begin_live_one_shot_composition,
    begin_no_access_composition,
    seal_collapsed_one_shot_go,
    validate_sanitized_human_decision,
)
from f017_event06_durable_installation_transaction_v1 import (
    DurableTransactionResult,
    TransactionPayload,
    _commit_bound_production_transaction,
    commit_synthetic_non_authority_transaction,
)
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_readiness_authority_v3 import (
    ValidatedEvent06ReadinessV3,
    assert_readiness_v3_sealed,
)

HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")

TARGET_MACHINE: Final = "MAC_STUDIO_M1_ULTRA"
HUMAN_GO_SCOPE: Final = COLLAPSED_GO_SCOPE
HUMAN_GO_RECORD_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-sanitized-human-go-record/2.0.0"
)
HUMAN_GO_RECORD_FIELDS: Final = (
    "schema", "decision", "target_machine", "nonce_sha256",
    "issued_at_unix_ns", "expires_at_unix_ns", "scope",
)
HUMAN_GO_RECORD_DECISION: Final = "AUTHORIZE_EXACTLY_ONE_EVENT06_PACKAGE"
PLANNER_ACCEPTANCE_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-planner-human-go-acceptance/2.0.0"
)
PLANNER_ACCEPTANCE_FIELDS: Final = (
    "schema", "human_go_record_sha256", "execution_prompt_commit",
    "execution_prompt_path", "execution_prompt_sha256", "accepted", "scope",
)
HUMAN_AUTHORITY_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-human-go-authenticity-authority/2.0.0"
)
HUMAN_AUTHORITY_FIELDS: Final = (
    "schema", "prompt_control_commit", "human_go_record_path",
    "human_go_record_sha256", "human_go_sidecar_sha256",
    "planner_acceptance_path", "planner_acceptance_sha256",
    "execution_prompt_commit", "execution_prompt_path",
    "execution_prompt_sha256", "release_authority_sha256", "target_machine",
    "one_shot_scope", "issued_at_unix_ns", "expires_at_unix_ns",
    "go_disposition",
)

APPROVAL_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-live-approval/2.0.0"
)
PREPARATION_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-live-preparation/2.0.0"
)
PROMPT_IDENTITY_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-live-prompt-identity/2.0.0"
)
ELIGIBILITY_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-installation-eligibility/2.0.0"
)
INSTALLATION_RECEIPT_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-installation-receipt/2.0.0"
)
PACKAGE_GATE_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-package-start-gate/2.0.0"
)

_HUMAN_AUTHORITY_SEAL = object()
_APPROVAL_SEAL = object()
_PREPARATION_SEAL = object()
_PROMPT_IDENTITY_SEAL = object()
_ELIGIBILITY_SEAL = object()
_BUNDLE_SEAL = object()
_ROOT_SEAL = object()
_TARGET_SEAL = object()
_PREPARED_SEAL = object()
_QUALIFICATION_CAPABILITY_SEAL = object()
_LIVE_CAPABILITY_SEAL = object()
_INSTALLED_SEAL = object()
_PACKAGE_GATE_SEAL = object()
_STATE_SEAL = object()
_PROMPT_CONTROL_SEAL = object()

_LIVE_CHECKPOINT_ALIAS: Final = "F017_EVENT06_CANONICAL_CHECKPOINT"
_LIVE_CHECKPOINT_ROOT: Final = (
    Path.home() / "Models" / "PulsarMLX" / "GLM-5.2-UD-IQ2_XXS"
)
_LIVE_INSTALLATION_ROOT: Final = Path(
    "/Users/Shared/PulsarMLX/f017-event06-v12/installations"
)
_LIVE_PROMPT_CONTROL_REPOSITORY: Final = (
    Path.home() / "Documents" / "Coding" / "PulsarMLX-Prompts"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _repo_path(value: object) -> bool:
    if type(value) is not str or not value or value.startswith("/") or "\\" in value:
        return False
    pure = PurePosixPath(value)
    return not pure.is_absolute() and all(
        part not in {"", ".", ".."} for part in pure.parts
    )


def _exact_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _decode_exact(raw: bytes, fields: tuple[str, ...], schema: str) -> dict[str, object]:
    value = parse_artifact_bytes(raw)
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("exact field census")
    if value.get("schema") != schema or canonical_bytes(value) != raw:
        raise ValueError("schema or canonical bytes")
    return value


class _ClosedArtifact:
    __slots__ = ("_items", "_raw", "source_sha256", "_locked")

    def _initialize(self, value: dict[str, object], raw: bytes) -> None:
        object.__setattr__(self, "_items", tuple(sorted(value.items())))
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "source_sha256", _sha(raw))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("collapsed installation authority is immutable")

    def __delattr__(self, name: str) -> Never:
        del name
        raise TypeError("collapsed installation authority is immutable")

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
        raise TypeError("collapsed installation authority cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("collapsed installation authority cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("collapsed installation authority cannot be pickled")


class BoundSanitizedHumanDecisionV2(_ClosedArtifact):
    __slots__ = ("_collapsed_decision", "mode")

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _HUMAN_AUTHORITY_SEAL:
            raise TypeError("sanitized human decisions are producer-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        value: dict[str, object],
        raw: bytes,
        collapsed_decision: SanitizedHumanDecisionV1,
        mode: str,
    ) -> None:
        del seal
        if mode not in {"QUALIFICATION_ONLY", "LIVE_CANONICAL"}:
            raise TypeError("exact decision authority mode")
        self._initialize(value, raw)
        object.__setattr__(self, "_collapsed_decision", collapsed_decision)
        object.__setattr__(self, "mode", mode)

    def _decision(self) -> SanitizedHumanDecisionV1:
        return self._collapsed_decision


class CollapsedLiveApprovalV2(_ClosedArtifact):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _APPROVAL_SEAL:
            raise TypeError("collapsed live approvals are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw)


class CollapsedLivePreparationV2(_ClosedArtifact):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PREPARATION_SEAL:
            raise TypeError("collapsed preparations are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw)


class CollapsedLivePromptIdentityV2(_ClosedArtifact):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PROMPT_IDENTITY_SEAL:
            raise TypeError("collapsed prompt identities are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw)


class CollapsedInstallationEligibilityV2(_ClosedArtifact):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _ELIGIBILITY_SEAL:
            raise TypeError("installation eligibility is producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw)


class CollapsedLiveIntegrationStateV2:
    __slots__ = ("_one_shot", "_mode", "_counts", "_locked")

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _STATE_SEAL:
            raise TypeError("integration state is factory-created")
        return super().__new__(cls)

    def __init__(
        self, seal: object, one_shot: OneShotCompositionStateV1, mode: str
    ) -> None:
        del seal
        if type(one_shot) is not OneShotCompositionStateV1 or mode not in {
            "QUALIFICATION_ONLY", "LIVE_CANONICAL"
        }:
            raise TypeError("exact integration state authority")
        object.__setattr__(self, "_one_shot", one_shot)
        object.__setattr__(self, "_mode", mode)
        object.__setattr__(self, "_counts", MappingProxyType({
            "sanitized_human_decisions_from_live_go": 0,
            "collapsed_live_go_tokens": 0,
            "canonical_live_reservations": 0,
            "live_checkpoint_root_resolutions": 0,
            "live_installation_commit_calls": 0,
            "live_authorities_or_capabilities": 0,
            "package_starts": 0,
            "original_checkpoint_shard_opens": 0,
            "original_checkpoint_identity_hash_reads": 0,
            "original_checkpoint_payload_reads": 0,
            "original_checkpoint_mmaps_or_tensor_reads": 0,
            "numerical_operations": 0,
            "event06_identities_instantiated": 0,
            "event06_identities_consumed": 0,
            "authorization_delta": 0,
            "package_delta": 0,
            "primary_delta": 0,
            "secondary_delta": 0,
            "p1_actions": 0,
            "qualification_decisions": 0,
            "qualification_tokens": 0,
            "qualification_candidates": 0,
            "qualification_installation_commits": 0,
            "qualification_package_gates": 0,
        }))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("integration state attributes are closed")

    def __copy__(self) -> Never:
        raise TypeError("integration state cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("integration state cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("integration state cannot be pickled")

    def _record(self, key: str) -> None:
        updated = dict(self._counts)
        updated[key] += 1
        object.__setattr__(self, "_counts", MappingProxyType(updated))

    def snapshot(self) -> MappingProxyType[str, int]:
        return MappingProxyType(dict(self._counts))

    def one_shot_snapshot(self) -> MappingProxyType[str, int]:
        return self._one_shot.snapshot()


def begin_qualification_live_installation(
    *, reservation_root: Path
) -> CollapsedLiveIntegrationStateV2:
    return CollapsedLiveIntegrationStateV2(
        _STATE_SEAL,
        begin_no_access_composition(reservation_root=reservation_root),
        "QUALIFICATION_ONLY",
    )


def _qualification_begin_live_collapsed_installation() -> CollapsedLiveIntegrationStateV2:
    """Historical live-shape constructor retained for isolated qualification."""

    return CollapsedLiveIntegrationStateV2(
        _STATE_SEAL,
        _qualification_begin_live_one_shot_composition(),
        "LIVE_CANONICAL",
    )


def begin_live_collapsed_installation() -> Never:
    """Fail closed: the former live integration root is superseded."""
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


class _PromptControlRepositoryAuthority:
    __slots__ = ("_root", "mode", "source_sha256", "_locked")

    def _initialize(self, root: Path, mode: str) -> None:
        root = root.resolve(strict=True)
        if not (root / ".git").exists():
            raise ValueError("prompt-control Git repository required")
        observed = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            text=True,
        ).strip()
        if observed != "true":
            raise ValueError("prompt-control worktree authority")
        identity = root.lstat()
        safe = canonical_bytes({
            "schema": "pulsarmlx.f017.event06-v12-prompt-control-repository-authority/2.0.0",
            "mode": mode,
            "device": identity.st_dev,
            "inode": identity.st_ino,
            "owner_uid": identity.st_uid,
        })
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "source_sha256", _sha(safe))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("prompt-control authorities are immutable")

    def __copy__(self) -> Never:
        raise TypeError("prompt-control authorities cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("prompt-control authorities cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("prompt-control authorities cannot be pickled")


class QualificationPromptControlAuthorityV2(_PromptControlRepositoryAuthority):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PROMPT_CONTROL_SEAL:
            raise TypeError("qualification prompt-control authorities are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, root: Path) -> None:
        del seal
        self._initialize(root, "QUALIFICATION_ONLY")


class LivePromptControlAuthorityV2(_PromptControlRepositoryAuthority):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PROMPT_CONTROL_SEAL:
            raise TypeError("live prompt-control authorities are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, root: Path) -> None:
        del seal
        self._initialize(root, "LIVE_CANONICAL")


def produce_qualification_prompt_control_authority(
    repository_root: Path,
) -> QualificationPromptControlAuthorityV2:
    return QualificationPromptControlAuthorityV2(
        _PROMPT_CONTROL_SEAL, repository_root
    )


def resolve_live_prompt_control_authority(
    *, state: CollapsedLiveIntegrationStateV2
) -> LivePromptControlAuthorityV2:
    """Future-only resolver for the configured prompt-control repository."""

    if type(state) is not CollapsedLiveIntegrationStateV2 or state._mode != "LIVE_CANONICAL":
        raise TypeError("live integration state required")
    return LivePromptControlAuthorityV2(
        _PROMPT_CONTROL_SEAL, _LIVE_PROMPT_CONTROL_REPOSITORY
    )


def _git_blob(
    authority: _PromptControlRepositoryAuthority,
    commit: str,
    path: str,
) -> bytes:
    if HEX40.fullmatch(commit) is None or not _repo_path(path):
        raise ValueError("commit-pinned prompt-control coordinate")
    try:
        return subprocess.check_output(
            ["git", "-C", str(authority._root), "show", f"{commit}:{path}"],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError("prompt-control blob unavailable") from exc


def produce_bound_sanitized_human_decision(
    *,
    prompt_control_authority: QualificationPromptControlAuthorityV2 | LivePromptControlAuthorityV2,
    authority_commit: str,
    authority_path: str,
    readiness: ValidatedEvent06ReadinessV3,
    now_unix_ns: int,
    state: CollapsedLiveIntegrationStateV2,
) -> BoundSanitizedHumanDecisionV2:
    if type(state) is not CollapsedLiveIntegrationStateV2:
        raise TypeError("exact integration state required")
    expected_prompt_type = (
        QualificationPromptControlAuthorityV2
        if state._mode == "QUALIFICATION_ONLY"
        else LivePromptControlAuthorityV2
    )
    if type(prompt_control_authority) is not expected_prompt_type:
        raise TypeError("prompt-control mode/type substitution")
    readiness = assert_readiness_v3_sealed(readiness)
    authority_raw = _git_blob(
        prompt_control_authority, authority_commit, authority_path
    )
    authority = _decode_exact(
        authority_raw, HUMAN_AUTHORITY_FIELDS, HUMAN_AUTHORITY_SCHEMA
    )
    for name in (
        "prompt_control_commit", "execution_prompt_commit",
    ):
        if type(authority[name]) is not str or HEX40.fullmatch(
            cast(str, authority[name])
        ) is None:
            raise ValueError(f"human authority git binding: {name}")
    for name in (
        "human_go_record_sha256", "human_go_sidecar_sha256",
        "planner_acceptance_sha256", "execution_prompt_sha256",
        "release_authority_sha256",
    ):
        if type(authority[name]) is not str or HEX64.fullmatch(
            cast(str, authority[name])
        ) is None:
            raise ValueError(f"human authority digest: {name}")
    for name in (
        "human_go_record_path", "planner_acceptance_path", "execution_prompt_path",
    ):
        if not _repo_path(authority[name]):
            raise ValueError(f"human authority path: {name}")
    if (
        authority["target_machine"] != TARGET_MACHINE
        or authority["one_shot_scope"] != HUMAN_GO_SCOPE
        or authority["release_authority_sha256"] != readiness.source_sha256
        or authority["go_disposition"] != "FRESH_UNCONSUMED"
        or not _exact_int(authority["issued_at_unix_ns"])
        or not _exact_int(authority["expires_at_unix_ns"])
        or cast(int, authority["issued_at_unix_ns"]) > now_unix_ns
        or cast(int, authority["expires_at_unix_ns"]) <= now_unix_ns
    ):
        raise ValueError("human authority posture")
    human_go_record_bytes = _git_blob(
        prompt_control_authority,
        cast(str, authority["prompt_control_commit"]),
        cast(str, authority["human_go_record_path"]),
    )
    human_go_sidecar_bytes = _git_blob(
        prompt_control_authority,
        cast(str, authority["prompt_control_commit"]),
        cast(str, authority["human_go_record_path"]) + ".sha256",
    )
    planner_acceptance_bytes = _git_blob(
        prompt_control_authority,
        cast(str, authority["prompt_control_commit"]),
        cast(str, authority["planner_acceptance_path"]),
    )
    execution_prompt_bytes = _git_blob(
        prompt_control_authority,
        cast(str, authority["execution_prompt_commit"]),
        cast(str, authority["execution_prompt_path"]),
    )
    bindings = (
        (authority["human_go_record_sha256"], _sha(human_go_record_bytes)),
        (authority["human_go_sidecar_sha256"], _sha(human_go_sidecar_bytes)),
        (authority["planner_acceptance_sha256"], _sha(planner_acceptance_bytes)),
        (authority["execution_prompt_sha256"], _sha(execution_prompt_bytes)),
    )
    if any(observed != expected for observed, expected in bindings):
        raise ValueError("human authority byte binding")
    record = _decode_exact(
        human_go_record_bytes, HUMAN_GO_RECORD_FIELDS, HUMAN_GO_RECORD_SCHEMA
    )
    if (
        record["decision"] != HUMAN_GO_RECORD_DECISION
        or record["target_machine"] != TARGET_MACHINE
        or record["scope"] != HUMAN_GO_SCOPE
        or type(record["nonce_sha256"]) is not str
        or HEX64.fullmatch(cast(str, record["nonce_sha256"])) is None
        or record["issued_at_unix_ns"] != authority["issued_at_unix_ns"]
        or record["expires_at_unix_ns"] != authority["expires_at_unix_ns"]
    ):
        raise ValueError("human GO record predicate")
    sidecar = human_go_sidecar_bytes.decode("utf-8")
    expected_sidecar = (
        f"{_sha(human_go_record_bytes)}  "
        f"{PurePosixPath(cast(str, authority['human_go_record_path'])).name}\n"
    )
    if sidecar != expected_sidecar:
        raise ValueError("human GO adjacent sidecar")
    acceptance = _decode_exact(
        planner_acceptance_bytes,
        PLANNER_ACCEPTANCE_FIELDS,
        PLANNER_ACCEPTANCE_SCHEMA,
    )
    if (
        acceptance["human_go_record_sha256"] != _sha(human_go_record_bytes)
        or acceptance["execution_prompt_commit"]
        != authority["execution_prompt_commit"]
        or acceptance["execution_prompt_path"] != authority["execution_prompt_path"]
        or acceptance["execution_prompt_sha256"] != _sha(execution_prompt_bytes)
        or acceptance["accepted"] is not True
        or acceptance["scope"] != HUMAN_GO_SCOPE
    ):
        raise ValueError("planner acceptance binding")
    collapsed_raw = canonical_bytes({
        "schema": "pulsarmlx.f017.event06-v12-sanitized-human-decision/1.0.0",
        "decision": "AUTHORIZE_EXACTLY_ONE_EVENT06_PACKAGE",
        "target_machine": TARGET_MACHINE,
        # The human record itself is the uniqueness unit.  Readiness and
        # release-authority revisions remain transitively bound by the outer
        # authority, but cannot turn one human decision into another attempt.
        "human_decision_nonce_sha256": _sha(human_go_record_bytes),
    })
    collapsed = validate_sanitized_human_decision(
        collapsed_raw, state=state._one_shot
    )
    state._record(
        "sanitized_human_decisions_from_live_go"
        if state._mode == "LIVE_CANONICAL"
        else "qualification_decisions"
    )
    safe_value = dict(authority)
    safe_value["human_go_record_sha256"] = _sha(human_go_record_bytes)
    return BoundSanitizedHumanDecisionV2(
        _HUMAN_AUTHORITY_SEAL, safe_value, authority_raw, collapsed, state._mode
    )


def seal_bound_collapsed_one_shot_go(
    decision: BoundSanitizedHumanDecisionV2,
    readiness: ValidatedEvent06ReadinessV3,
    *,
    issued_at_unix_ns: int,
    expires_at_unix_ns: int,
    now_unix_ns: int,
    state: CollapsedLiveIntegrationStateV2,
) -> CollapsedOneShotGoV1:
    if (
        type(decision) is not BoundSanitizedHumanDecisionV2
        or type(state) is not CollapsedLiveIntegrationStateV2
        or decision.mode != state._mode
    ):
        raise TypeError("exact bound sanitized decision required")
    go = seal_collapsed_one_shot_go(
        decision._decision(),
        readiness,
        issued_at_unix_ns=issued_at_unix_ns,
        expires_at_unix_ns=expires_at_unix_ns,
        now_unix_ns=now_unix_ns,
        state=state._one_shot,
    )
    state._record(
        "collapsed_live_go_tokens"
        if state._mode == "LIVE_CANONICAL"
        else "qualification_tokens"
    )
    if state._mode == "LIVE_CANONICAL":
        state._record("canonical_live_reservations")
    return go


def derive_production_event_identities(
    go: CollapsedOneShotGoV1,
    *,
    repository_identity_census: frozenset[str] = frozenset(),
    machine_identity_census: frozenset[str] = frozenset(),
) -> MappingProxyType[str, str]:
    if type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact collapsed GO required")
    suffix = go.source_sha256[:24].upper()
    identities = {
        "authorization_id": f"F017-EVENT06-V12-AUTH-{suffix}",
        "package_attempt_id": f"F017-EVENT06-V12-PACKAGE-{suffix}",
        "primary_event_id": f"F017-EVENT06-V12-PRIMARY-{suffix}",
        "secondary_event_id": f"F017-EVENT06-V12-SECONDARY-{suffix}",
    }
    if len(set(identities.values())) != 4 or any(
        TYPED_ID.fullmatch(value) is None for value in identities.values()
    ):
        raise ValueError("production identity grammar or uniqueness")
    if set(identities.values()) & (
        set(repository_identity_census) | set(machine_identity_census)
    ):
        raise ValueError("Event 06 identity already used")
    return MappingProxyType(identities)


def produce_collapsed_live_approval(
    decision: BoundSanitizedHumanDecisionV2,
    go: CollapsedOneShotGoV1,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    *,
    now_unix_ns: int,
    state: CollapsedLiveIntegrationStateV2,
) -> CollapsedLiveApprovalV2:
    if (
        type(decision) is not BoundSanitizedHumanDecisionV2
        or type(go) is not CollapsedOneShotGoV1
        or type(state) is not CollapsedLiveIntegrationStateV2
        or decision.mode != state._mode
    ):
        raise TypeError("exact decision and collapsed GO required")
    readiness = assert_readiness_v3_sealed(readiness)
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact execution plan required")
    if now_unix_ns < go.get("issued_at_unix_ns") or now_unix_ns >= go.get("expires_at_unix_ns"):
        raise ValueError("collapsed GO expired")
    if go.get("human_decision_sha256") != decision._decision().source_sha256:
        raise ValueError("collapsed GO decision authority substitution")
    ids = derive_production_event_identities(go)
    for name in ("package_attempt_id", "primary_event_id", "secondary_event_id"):
        if execution_plan.get(name) != ids[name]:
            raise ValueError(f"execution plan identity substitution: {name}")
    value = {
        "schema": APPROVAL_SCHEMA,
        "human_authority_sha256": decision.source_sha256,
        "collapsed_go_sha256": go.source_sha256,
        "readiness_sha256": readiness.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "authority_mode": state._mode,
        "authorization_id": ids["authorization_id"],
        "package_attempt_id": ids["package_attempt_id"],
        "state": "APPROVED_FOR_COLLAPSED_PREPARATION_ONLY",
    }
    raw = canonical_bytes(value)
    return CollapsedLiveApprovalV2(_APPROVAL_SEAL, value, raw)


def seal_collapsed_live_preparation(
    approval: CollapsedLiveApprovalV2,
    decision: BoundSanitizedHumanDecisionV2,
    go: CollapsedOneShotGoV1,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> CollapsedLivePreparationV2:
    if type(approval) is not CollapsedLiveApprovalV2 or type(decision) is not BoundSanitizedHumanDecisionV2:
        raise TypeError("exact approval and decision required")
    readiness = assert_readiness_v3_sealed(readiness)
    if (
        type(go) is not CollapsedOneShotGoV1
        or type(execution_plan) is not ValidatedExecutionPlan
        or type(state) is not CollapsedLiveIntegrationStateV2
        or decision.mode != state._mode
        or approval.get("authority_mode") != state._mode
    ):
        raise TypeError("exact GO and plan required")
    checks = (
        approval.get("human_authority_sha256") == decision.source_sha256,
        approval.get("collapsed_go_sha256") == go.source_sha256,
        approval.get("readiness_sha256") == readiness.source_sha256,
        approval.get("execution_plan_sha256") == execution_plan.sha256,
    )
    if not all(checks):
        raise ValueError("collapsed preparation causal binding")
    value = {
        "schema": PREPARATION_SCHEMA,
        "approval_sha256": approval.source_sha256,
        "human_authority_sha256": decision.source_sha256,
        "collapsed_go_sha256": go.source_sha256,
        "readiness_sha256": readiness.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "authority_mode": state._mode,
        "state": "PREPARED_NOT_INSTALLED",
    }
    raw = canonical_bytes(value)
    return CollapsedLivePreparationV2(_PREPARATION_SEAL, value, raw)


def produce_collapsed_live_prompt_identity(
    preparation: CollapsedLivePreparationV2,
    go: CollapsedOneShotGoV1,
    execution_plan: ValidatedExecutionPlan,
    *,
    prompt_bytes: bytes,
    prompt_repository_commit: str,
    prompt_repository_path: str,
    state: CollapsedLiveIntegrationStateV2,
) -> CollapsedLivePromptIdentityV2:
    if type(preparation) is not CollapsedLivePreparationV2 or type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact preparation and GO required")
    if (
        type(execution_plan) is not ValidatedExecutionPlan
        or type(state) is not CollapsedLiveIntegrationStateV2
        or preparation.get("authority_mode") != state._mode
    ):
        raise TypeError("exact execution plan required")
    if (
        type(prompt_bytes) is not bytes
        or type(prompt_repository_commit) is not str
        or HEX40.fullmatch(prompt_repository_commit) is None
        or not _repo_path(prompt_repository_path)
    ):
        raise ValueError("prompt authority types")
    if preparation.get("collapsed_go_sha256") != go.source_sha256 or preparation.get("execution_plan_sha256") != execution_plan.sha256:
        raise ValueError("prompt identity predecessor binding")
    ids = derive_production_event_identities(go)
    value = {
        "schema": PROMPT_IDENTITY_SCHEMA,
        "preparation_sha256": preparation.source_sha256,
        "collapsed_go_sha256": go.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "authority_mode": state._mode,
        **dict(ids),
        "prompt_repository_commit": prompt_repository_commit,
        "prompt_repository_path": prompt_repository_path,
        "prompt_sha256": _sha(prompt_bytes),
    }
    raw = canonical_bytes(value)
    return CollapsedLivePromptIdentityV2(_PROMPT_IDENTITY_SEAL, value, raw)


def _validate_directory_authority(path: Path) -> tuple[int, int, int, int]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise TypeError("exact absolute Path authority required")
    identity = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(identity.st_mode):
        raise ValueError("directory authority must be a nonsymlink directory")
    if identity.st_uid != os.getuid() or stat.S_IMODE(identity.st_mode) & 0o022:
        raise ValueError("directory authority ownership or permissions")
    cursor = path
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError("symlink ancestry is prohibited")
        cursor = cursor.parent
    return identity.st_dev, identity.st_ino, identity.st_uid, stat.S_IMODE(identity.st_mode)


class _CheckpointRootAuthority:
    __slots__ = ("_path", "alias", "mode", "source_sha256", "_locked")

    def _initialize(self, path: Path, alias: str, mode: str) -> None:
        device, inode, owner, permissions = _validate_directory_authority(path)
        safe = canonical_bytes({
            "schema": "pulsarmlx.f017.event06-v12-checkpoint-root-authority/2.0.0",
            "alias": alias,
            "mode": mode,
            "device": device,
            "inode": inode,
            "owner_uid": owner,
            "permissions": permissions,
        })
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "alias", alias)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "source_sha256", _sha(safe))
        object.__setattr__(self, "_locked", True)

    def _validated_path(self) -> Path:
        _validate_directory_authority(self._path)
        return self._path

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("checkpoint root authorities are immutable")

    def __copy__(self) -> Never:
        raise TypeError("checkpoint root authorities cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("checkpoint root authorities cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("checkpoint root authorities cannot be pickled")


class QualificationCheckpointRootAuthorityV2(_CheckpointRootAuthority):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _ROOT_SEAL:
            raise TypeError("qualification root authorities are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, path: Path, alias: str) -> None:
        del seal
        self._initialize(path, alias, "QUALIFICATION_ONLY")


class LiveCheckpointRootAuthorityV2(_CheckpointRootAuthority):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _ROOT_SEAL:
            raise TypeError("live root authorities are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, path: Path, alias: str) -> None:
        del seal
        self._initialize(path, alias, "LIVE_CANONICAL")


def produce_qualification_checkpoint_root_authority(
    disposable_root: Path,
) -> QualificationCheckpointRootAuthorityV2:
    return QualificationCheckpointRootAuthorityV2(
        _ROOT_SEAL, disposable_root, "QUALIFICATION_SYNTHETIC_ROOT"
    )


def resolve_live_checkpoint_root_authority(
    decision: BoundSanitizedHumanDecisionV2,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> LiveCheckpointRootAuthorityV2:
    """Resolve the configured alias only after a future fresh live GO."""

    if (
        type(decision) is not BoundSanitizedHumanDecisionV2
        or type(state) is not CollapsedLiveIntegrationStateV2
        or decision.mode != "LIVE_CANONICAL"
        or state._mode != "LIVE_CANONICAL"
    ):
        raise TypeError("fresh live decision and live state required")
    resolved = _LIVE_CHECKPOINT_ROOT.resolve(strict=True)
    state._record("live_checkpoint_root_resolutions")
    return LiveCheckpointRootAuthorityV2(
        _ROOT_SEAL, resolved, _LIVE_CHECKPOINT_ALIAS
    )


class CheckpointBoundCandidateBundleV2:
    __slots__ = (
        "candidate", "eligibility", "prompt_identity", "root_authority_sha256",
        "source_sha256", "_locked",
    )

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _BUNDLE_SEAL:
            raise TypeError("checkpoint-bound bundles are producer-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        candidate: ValidatedIdentityAuthority,
        eligibility: CollapsedInstallationEligibilityV2,
        prompt_identity: CollapsedLivePromptIdentityV2,
        root_authority_sha256: str,
    ) -> None:
        del seal
        object.__setattr__(self, "candidate", candidate)
        object.__setattr__(self, "eligibility", eligibility)
        object.__setattr__(self, "prompt_identity", prompt_identity)
        object.__setattr__(self, "root_authority_sha256", root_authority_sha256)
        object.__setattr__(self, "source_sha256", _sha(
            canonical_bytes({
                "candidate_sha256": candidate.source_sha256,
                "eligibility_sha256": eligibility.source_sha256,
                "prompt_identity_sha256": prompt_identity.source_sha256,
                "root_authority_sha256": root_authority_sha256,
            })
        ))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("checkpoint-bound bundles are immutable")

    def __copy__(self) -> Never:
        raise TypeError("checkpoint-bound bundles cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("checkpoint-bound bundles cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("checkpoint-bound bundles cannot be pickled")


def produce_checkpoint_bound_candidate_bundle(
    preparation: CollapsedLivePreparationV2,
    identity: CollapsedLivePromptIdentityV2,
    go: CollapsedOneShotGoV1,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    root_authority: QualificationCheckpointRootAuthorityV2 | LiveCheckpointRootAuthorityV2,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> CheckpointBoundCandidateBundleV2:
    if type(preparation) is not CollapsedLivePreparationV2 or type(identity) is not CollapsedLivePromptIdentityV2:
        raise TypeError("exact preparation and prompt identity required")
    if (
        type(go) is not CollapsedOneShotGoV1
        or type(execution_plan) is not ValidatedExecutionPlan
        or type(state) is not CollapsedLiveIntegrationStateV2
    ):
        raise TypeError("exact GO and execution plan required")
    readiness = assert_readiness_v3_sealed(readiness)
    expected_root_type = (
        QualificationCheckpointRootAuthorityV2
        if state._mode == "QUALIFICATION_ONLY"
        else LiveCheckpointRootAuthorityV2
    )
    if type(root_authority) is not expected_root_type:
        raise TypeError("checkpoint root mode/type substitution")
    if (
        preparation.get("collapsed_go_sha256") != go.source_sha256
        or identity.get("preparation_sha256") != preparation.source_sha256
        or preparation.get("authority_mode") != state._mode
        or identity.get("authority_mode") != state._mode
    ):
        raise ValueError("candidate predecessor splice")
    ids = derive_production_event_identities(go)
    candidate = build_identity_candidate_from_readiness_v3(
        readiness,
        authorization_id=ids["authorization_id"],
        package_attempt_id=ids["package_attempt_id"],
        checkpoint_root=root_authority._validated_path(),
        event_identity_plan_sha256=identity.source_sha256,
    )
    if any(
        report.get("result") != "PASS"
        for report in (
            validate_primary_identity(candidate, posture="CANDIDATE"),
            validate_secondary_identity(candidate, posture="CANDIDATE"),
        )
    ):
        raise ValueError("candidate consumer validation")
    state._one_shot._consume(go.source_sha256)
    value = {
        "schema": ELIGIBILITY_SCHEMA,
        "collapsed_go_sha256": go.source_sha256,
        "preparation_sha256": preparation.source_sha256,
        "prompt_identity_sha256": identity.source_sha256,
        "readiness_sha256": readiness.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "root_authority_sha256": root_authority.source_sha256,
        "root_authority_mode": root_authority.mode,
        "authority_mode": state._mode,
        "candidate_sha256": candidate.source_sha256,
        "authorization_id": ids["authorization_id"],
        "package_attempt_id": ids["package_attempt_id"],
        "primary_event_id": ids["primary_event_id"],
        "secondary_event_id": ids["secondary_event_id"],
        "primary_validation": "PASS",
        "secondary_validation": "PASS",
        "package_start_eligible": True,
        "package_started": False,
        "checkpoint_access": 0,
        "result": "PASS",
    }
    raw = canonical_bytes(value)
    eligibility = CollapsedInstallationEligibilityV2(
        _ELIGIBILITY_SEAL, value, raw
    )
    state._record(
        "qualification_candidates"
        if state._mode == "QUALIFICATION_ONLY"
        else "event06_identities_instantiated"
    )
    return CheckpointBoundCandidateBundleV2(
        _BUNDLE_SEAL,
        candidate,
        eligibility,
        identity,
        root_authority.source_sha256,
    )


class PreparedCollapsedInstallationV2:
    __slots__ = (
        "_candidate", "_receipt", "_installed", "candidate_sha256",
        "receipt_sha256", "installed_sha256", "prepared_sha256",
        "eligibility_sha256", "mode", "_locked",
    )

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PREPARED_SEAL:
            raise TypeError("prepared collapsed installations are producer-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        candidate: bytes,
        receipt: bytes,
        installed: bytes,
        eligibility_sha256: str,
        mode: str,
    ) -> None:
        del seal
        object.__setattr__(self, "_candidate", candidate)
        object.__setattr__(self, "_receipt", receipt)
        object.__setattr__(self, "_installed", installed)
        object.__setattr__(self, "candidate_sha256", _sha(candidate))
        object.__setattr__(self, "receipt_sha256", _sha(receipt))
        object.__setattr__(self, "installed_sha256", _sha(installed))
        object.__setattr__(self, "prepared_sha256", _sha(candidate + receipt + installed))
        object.__setattr__(self, "eligibility_sha256", eligibility_sha256)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "_locked", True)

    def payload(self, role: str) -> bytes:
        return {
            "candidate": self._candidate,
            "receipt": self._receipt,
            "installed": self._installed,
        }[role]

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("prepared collapsed installations are immutable")

    def __copy__(self) -> Never:
        raise TypeError("prepared collapsed installations cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("prepared collapsed installations cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("prepared collapsed installations cannot be pickled")


def prepare_collapsed_production_installation(
    decision: BoundSanitizedHumanDecisionV2,
    go: CollapsedOneShotGoV1,
    approval: CollapsedLiveApprovalV2,
    preparation: CollapsedLivePreparationV2,
    bundle: CheckpointBoundCandidateBundleV2,
    readiness: ValidatedEvent06ReadinessV3,
    execution_plan: ValidatedExecutionPlan,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> PreparedCollapsedInstallationV2:
    if type(decision) is not BoundSanitizedHumanDecisionV2 or type(go) is not CollapsedOneShotGoV1:
        raise TypeError("exact decision and GO required")
    if type(approval) is not CollapsedLiveApprovalV2 or type(preparation) is not CollapsedLivePreparationV2:
        raise TypeError("exact approval and preparation required")
    if type(bundle) is not CheckpointBoundCandidateBundleV2 or type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact bundle and plan required")
    if type(state) is not CollapsedLiveIntegrationStateV2:
        raise TypeError("exact integration state required")
    readiness = assert_readiness_v3_sealed(readiness)
    candidate = bundle.candidate
    candidate_raw = canonical_bytes(candidate.as_dict())
    validate_candidate_bytes(candidate_raw)
    checks = (
        approval.get("collapsed_go_sha256") == go.source_sha256,
        preparation.get("approval_sha256") == approval.source_sha256,
        bundle.eligibility.get("preparation_sha256") == preparation.source_sha256,
        bundle.eligibility.get("candidate_sha256") == candidate.source_sha256,
        bundle.eligibility.get("readiness_sha256") == readiness.source_sha256,
        bundle.eligibility.get("execution_plan_sha256") == execution_plan.sha256,
        decision.mode == state._mode,
        approval.get("authority_mode") == state._mode,
        preparation.get("authority_mode") == state._mode,
        bundle.prompt_identity.get("authority_mode") == state._mode,
        bundle.eligibility.get("authority_mode") == state._mode,
        bundle.eligibility.get("root_authority_mode") == state._mode,
    )
    if not all(checks):
        raise ValueError("prepared installation causal binding")
    ids = derive_production_event_identities(go)
    receipt_value = {
        "schema": INSTALLATION_RECEIPT_SCHEMA,
        "human_authority_sha256": decision.source_sha256,
        "collapsed_go_sha256": go.source_sha256,
        "approval_sha256": approval.source_sha256,
        "preparation_sha256": preparation.source_sha256,
        "eligibility_sha256": bundle.eligibility.source_sha256,
        "candidate_sha256": candidate.source_sha256,
        "readiness_sha256": readiness.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "authorization_id": ids["authorization_id"],
        "package_attempt_id": ids["package_attempt_id"],
        "installation_kind": "COLLAPSED_GO_DERIVED_PRODUCTION",
        "live_authority": state._mode == "LIVE_CANONICAL",
        "result": "PASS",
    }
    receipt_raw = canonical_bytes(receipt_value)
    installed_raw = canonical_bytes(installed_document(candidate, _sha(receipt_raw)))
    validate_installed_bytes(installed_raw, installed_expected(candidate))
    return PreparedCollapsedInstallationV2(
        _PREPARED_SEAL,
        candidate_raw,
        receipt_raw,
        installed_raw,
        bundle.eligibility.source_sha256,
        state._mode,
    )


class _InstallationTargetAuthority:
    __slots__ = ("_path", "mode", "source_sha256", "_locked")

    def _initialize(self, path: Path, mode: str) -> None:
        device, inode, owner, permissions = _validate_directory_authority(path)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "source_sha256", _sha(canonical_bytes({
            "schema": "pulsarmlx.f017.event06-v12-installation-target-authority/2.0.0",
            "mode": mode,
            "device": device,
            "inode": inode,
            "owner_uid": owner,
            "permissions": permissions,
        })))
        object.__setattr__(self, "_locked", True)

    def _validated_path(self) -> Path:
        _validate_directory_authority(self._path)
        return self._path

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("installation target authorities are immutable")

    def __copy__(self) -> Never:
        raise TypeError("installation target authorities cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("installation target authorities cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("installation target authorities cannot be pickled")


class QualificationInstallationTargetV2(_InstallationTargetAuthority):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _TARGET_SEAL:
            raise TypeError("qualification targets are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, path: Path) -> None:
        del seal
        self._initialize(path, "QUALIFICATION_ONLY")


class LiveInstallationTargetV2(_InstallationTargetAuthority):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _TARGET_SEAL:
            raise TypeError("live targets are producer-created")
        return super().__new__(cls)

    def __init__(self, seal: object, path: Path) -> None:
        del seal
        self._initialize(path, "LIVE_CANONICAL")


def produce_qualification_installation_target(
    disposable_root: Path,
) -> QualificationInstallationTargetV2:
    return QualificationInstallationTargetV2(_TARGET_SEAL, disposable_root)


def resolve_live_installation_target(
    decision: BoundSanitizedHumanDecisionV2,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> LiveInstallationTargetV2:
    if (
        type(decision) is not BoundSanitizedHumanDecisionV2
        or type(state) is not CollapsedLiveIntegrationStateV2
        or decision.mode != "LIVE_CANONICAL"
        or state._mode != "LIVE_CANONICAL"
    ):
        raise TypeError("fresh live decision and live state required")
    return LiveInstallationTargetV2(
        _TARGET_SEAL, _LIVE_INSTALLATION_ROOT.resolve(strict=True)
    )


class _InstallationCapability:
    __slots__ = (
        "prepared_sha256", "eligibility_sha256", "target_sha256", "target_leaf",
        "expires_at_unix_ns", "mode", "source_sha256", "_target", "_locked",
    )

    def _initialize(
        self,
        prepared: PreparedCollapsedInstallationV2,
        bundle: CheckpointBoundCandidateBundleV2,
        target: _InstallationTargetAuthority,
        target_leaf: str,
        expires_at_unix_ns: int,
        mode: str,
    ) -> None:
        if (
            type(target_leaf) is not str or not target_leaf
            or target_leaf in {".", ".."} or target_leaf.startswith(".")
            or "/" in target_leaf or "\\" in target_leaf
        ):
            raise ValueError("installation target leaf")
        value = {
            "schema": "pulsarmlx.f017.event06-v12-collapsed-installation-capability/2.0.0",
            "prepared_sha256": prepared.prepared_sha256,
            "eligibility_sha256": bundle.eligibility.source_sha256,
            "target_sha256": target.source_sha256,
            "target_leaf": target_leaf,
            "expires_at_unix_ns": expires_at_unix_ns,
            "mode": mode,
        }
        object.__setattr__(self, "prepared_sha256", prepared.prepared_sha256)
        object.__setattr__(self, "eligibility_sha256", bundle.eligibility.source_sha256)
        object.__setattr__(self, "target_sha256", target.source_sha256)
        object.__setattr__(self, "target_leaf", target_leaf)
        object.__setattr__(self, "expires_at_unix_ns", expires_at_unix_ns)
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "source_sha256", _sha(canonical_bytes(value)))
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("installation capabilities are immutable")

    def __copy__(self) -> Never:
        raise TypeError("installation capabilities cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("installation capabilities cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("installation capabilities cannot be pickled")


class QualificationInstallationCapabilityV2(_InstallationCapability):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _QUALIFICATION_CAPABILITY_SEAL:
            raise TypeError("qualification capabilities are producer-created")
        return super().__new__(cls)


class CollapsedLiveInstallationCapabilityV2(_InstallationCapability):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _LIVE_CAPABILITY_SEAL:
            raise TypeError("live capabilities are producer-created")
        return super().__new__(cls)


_ISSUED_QUALIFICATION_CAPABILITIES: dict[int, QualificationInstallationCapabilityV2] = {}
_ISSUED_LIVE_CAPABILITIES: dict[int, CollapsedLiveInstallationCapabilityV2] = {}
_QUALIFICATION_PREPARED_CAPABILITIES: set[str] = set()
_LIVE_PREPARED_CAPABILITIES: set[str] = set()


def _capability_inputs(
    prepared: PreparedCollapsedInstallationV2,
    bundle: CheckpointBoundCandidateBundleV2,
    expires_at_unix_ns: int,
) -> None:
    if type(prepared) is not PreparedCollapsedInstallationV2 or type(bundle) is not CheckpointBoundCandidateBundleV2:
        raise TypeError("exact prepared installation and bundle required")
    if prepared.eligibility_sha256 != bundle.eligibility.source_sha256:
        raise ValueError("capability eligibility splice")
    if type(expires_at_unix_ns) is not int or expires_at_unix_ns <= time.time_ns():
        raise ValueError("capability expiry")


def produce_qualification_installation_capability(
    prepared: PreparedCollapsedInstallationV2,
    bundle: CheckpointBoundCandidateBundleV2,
    target: QualificationInstallationTargetV2,
    *,
    target_leaf: str,
    expires_at_unix_ns: int,
) -> QualificationInstallationCapabilityV2:
    _capability_inputs(prepared, bundle, expires_at_unix_ns)
    if type(target) is not QualificationInstallationTargetV2 or prepared.mode != "QUALIFICATION_ONLY":
        raise TypeError("qualification target/capability mode")
    if prepared.prepared_sha256 in _QUALIFICATION_PREPARED_CAPABILITIES:
        raise ValueError("prepared installation capability already issued")
    _QUALIFICATION_PREPARED_CAPABILITIES.add(prepared.prepared_sha256)
    capability = QualificationInstallationCapabilityV2(_QUALIFICATION_CAPABILITY_SEAL)
    capability._initialize(
        prepared, bundle, target, target_leaf, expires_at_unix_ns, "QUALIFICATION_ONLY"
    )
    _ISSUED_QUALIFICATION_CAPABILITIES[id(capability)] = capability
    return capability


def produce_collapsed_live_installation_capability(
    prepared: PreparedCollapsedInstallationV2,
    bundle: CheckpointBoundCandidateBundleV2,
    target: LiveInstallationTargetV2,
    *,
    target_leaf: str,
    expires_at_unix_ns: int,
    state: CollapsedLiveIntegrationStateV2,
) -> CollapsedLiveInstallationCapabilityV2:
    _capability_inputs(prepared, bundle, expires_at_unix_ns)
    if type(target) is not LiveInstallationTargetV2 or prepared.mode != "LIVE_CANONICAL" or state._mode != "LIVE_CANONICAL":
        raise TypeError("live target/capability mode")
    if prepared.prepared_sha256 in _LIVE_PREPARED_CAPABILITIES:
        raise ValueError("prepared installation capability already issued")
    _LIVE_PREPARED_CAPABILITIES.add(prepared.prepared_sha256)
    capability = CollapsedLiveInstallationCapabilityV2(_LIVE_CAPABILITY_SEAL)
    capability._initialize(
        prepared, bundle, target, target_leaf, expires_at_unix_ns, "LIVE_CANONICAL"
    )
    _ISSUED_LIVE_CAPABILITIES[id(capability)] = capability
    state._record("live_authorities_or_capabilities")
    return capability


def _payloads(prepared: PreparedCollapsedInstallationV2) -> tuple[TransactionPayload, ...]:
    return (
        TransactionPayload("candidate", "candidate.json", prepared.payload("candidate")),
        TransactionPayload("receipt", "installation-receipt.json", prepared.payload("receipt")),
        TransactionPayload("installed", "installed-authorization.json", prepared.payload("installed")),
    )


def commit_qualification_collapsed_installation(
    prepared: PreparedCollapsedInstallationV2,
    capability: QualificationInstallationCapabilityV2,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> DurableTransactionResult:
    if type(capability) is not QualificationInstallationCapabilityV2 or _ISSUED_QUALIFICATION_CAPABILITIES.pop(id(capability), None) is not capability:
        raise TypeError("issued single-use qualification capability required")
    if state._mode != "QUALIFICATION_ONLY" or capability.prepared_sha256 != prepared.prepared_sha256 or capability.expires_at_unix_ns <= time.time_ns():
        raise ValueError("qualification capability binding or expiry")
    state._record("qualification_installation_commits")
    return commit_synthetic_non_authority_transaction(
        capability._target._validated_path(),
        capability.target_leaf,
        _payloads(prepared),
    )


def _qualification_commit_collapsed_live_installation(
    prepared: PreparedCollapsedInstallationV2,
    capability: CollapsedLiveInstallationCapabilityV2,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> DurableTransactionResult:
    if type(capability) is not CollapsedLiveInstallationCapabilityV2 or _ISSUED_LIVE_CAPABILITIES.pop(id(capability), None) is not capability:
        raise TypeError("issued single-use live capability required")
    if state._mode != "LIVE_CANONICAL" or capability.prepared_sha256 != prepared.prepared_sha256 or capability.expires_at_unix_ns <= time.time_ns():
        raise ValueError("live capability binding or expiry")
    state._record("live_installation_commit_calls")
    # The durable marker is preparation-bound, not capability-bound.  Even if
    # a process crashes after minting a capability, reconstructing a capability
    # with another leaf or expiry cannot turn one prepared package into a
    # second installation attempt.
    marker = f"F017-COLLAPSED-GO-CONSUMED-{prepared.prepared_sha256}"
    return _commit_bound_production_transaction(
        capability._target._validated_path(),
        capability.target_leaf,
        _payloads(prepared),
        consumption_marker=marker,
    )


def commit_collapsed_live_installation(
    prepared: PreparedCollapsedInstallationV2,
    capability: CollapsedLiveInstallationCapabilityV2,
    *,
    state: CollapsedLiveIntegrationStateV2,
) -> DurableTransactionResult:
    """Fail closed: superseded V2 installation cannot mint live authority."""
    del prepared, capability, state
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


class CollapsedInstalledTripleV2:
    __slots__ = (
        "authority", "candidate_sha256", "receipt_sha256", "installed_sha256",
        "eligibility_sha256", "transaction_sha256", "source_sha256", "mode", "_locked",
    )

    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _INSTALLED_SEAL:
            raise TypeError("installed triples are validator-created")
        return super().__new__(cls)

    def __init__(
        self,
        seal: object,
        authority: ValidatedIdentityAuthority,
        prepared: PreparedCollapsedInstallationV2,
        transaction: DurableTransactionResult,
    ) -> None:
        del seal
        object.__setattr__(self, "authority", authority)
        object.__setattr__(self, "candidate_sha256", prepared.candidate_sha256)
        object.__setattr__(self, "receipt_sha256", prepared.receipt_sha256)
        object.__setattr__(self, "installed_sha256", prepared.installed_sha256)
        object.__setattr__(self, "eligibility_sha256", prepared.eligibility_sha256)
        object.__setattr__(self, "transaction_sha256", transaction.transaction_sha256)
        object.__setattr__(self, "mode", prepared.mode)
        object.__setattr__(self, "source_sha256", _sha(canonical_bytes({
            "candidate_sha256": prepared.candidate_sha256,
            "receipt_sha256": prepared.receipt_sha256,
            "installed_sha256": prepared.installed_sha256,
            "eligibility_sha256": prepared.eligibility_sha256,
            "transaction_sha256": transaction.transaction_sha256,
        })))
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("installed triples are immutable")

    def __copy__(self) -> Never:
        raise TypeError("installed triples cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("installed triples cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("installed triples cannot be pickled")


def _read_leaf(directory: Path, leaf: str, bound: int = 262_145) -> bytes:
    directory_fd = os.open(
        directory, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(
            leaf, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd
        )
        identity = os.fstat(descriptor)
        if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
            raise ValueError("installed triple leaf identity")
        raw = os.read(descriptor, bound)
        if os.read(descriptor, 1):
            raise ValueError("installed triple leaf exceeds bound")
        return raw
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)


def validate_collapsed_installed_triple(
    target: QualificationInstallationTargetV2 | LiveInstallationTargetV2,
    target_leaf: str,
    prepared: PreparedCollapsedInstallationV2,
    transaction: DurableTransactionResult,
) -> CollapsedInstalledTripleV2:
    if type(prepared) is not PreparedCollapsedInstallationV2 or type(transaction) is not DurableTransactionResult:
        raise TypeError("exact prepared installation and transaction required")
    expected_target = (
        QualificationInstallationTargetV2
        if prepared.mode == "QUALIFICATION_ONLY"
        else LiveInstallationTargetV2
    )
    if type(target) is not expected_target or transaction.target_leaf != target_leaf:
        raise TypeError("installed triple target mode or leaf")
    directory = target._validated_path() / target_leaf
    candidate_raw = _read_leaf(directory, "candidate.json")
    receipt_raw = _read_leaf(directory, "installation-receipt.json")
    installed_raw = _read_leaf(directory, "installed-authorization.json")
    if (
        candidate_raw != prepared.payload("candidate")
        or receipt_raw != prepared.payload("receipt")
        or installed_raw != prepared.payload("installed")
    ):
        raise ValueError("installed triple prepared-byte mismatch")
    candidate = validate_candidate_bytes(candidate_raw)
    receipt = _decode_exact(
        receipt_raw,
        (
            "schema", "human_authority_sha256", "collapsed_go_sha256",
            "approval_sha256", "preparation_sha256", "eligibility_sha256",
            "candidate_sha256", "readiness_sha256", "execution_plan_sha256",
            "authorization_id", "package_attempt_id", "installation_kind",
            "live_authority", "result",
        ),
        INSTALLATION_RECEIPT_SCHEMA,
    )
    if (
        receipt["candidate_sha256"] != candidate.source_sha256
        or receipt["eligibility_sha256"] != prepared.eligibility_sha256
        or receipt["live_authority"] is not (prepared.mode == "LIVE_CANONICAL")
    ):
        raise ValueError("installation receipt authority binding")
    installed = validate_installed_bytes(installed_raw, installed_expected(candidate))
    if installed.get("installation_receipt_sha256") != _sha(receipt_raw):
        raise ValueError("installed authority receipt binding")
    for posture, authority in (("CANDIDATE", candidate), ("INSTALLED", installed)):
        if any(
            report.get("result") != "PASS"
            for report in (
                validate_primary_identity(authority, posture=posture),
                validate_secondary_identity(authority, posture=posture),
            )
        ):
            raise ValueError("installed triple consumer validation")
    return CollapsedInstalledTripleV2(
        _INSTALLED_SEAL, installed, prepared, transaction
    )


class CollapsedPackageStartGateV2(_ClosedArtifact):
    def __new__(cls, seal: object = None, *args: object) -> Self:
        del args
        if seal is not _PACKAGE_GATE_SEAL:
            raise TypeError("package-start gates are coordinator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: dict[str, object], raw: bytes) -> None:
        del seal
        self._initialize(value, raw)


def _produce_package_start_gate(
    installed: CollapsedInstalledTripleV2,
    bundle: CheckpointBoundCandidateBundleV2,
    execution_plan: ValidatedExecutionPlan,
    *,
    identity_capability_result: str,
    state: CollapsedLiveIntegrationStateV2,
) -> CollapsedPackageStartGateV2:
    if type(installed) is not CollapsedInstalledTripleV2 or type(bundle) is not CheckpointBoundCandidateBundleV2:
        raise TypeError("exact installed triple and candidate bundle required")
    if type(execution_plan) is not ValidatedExecutionPlan or identity_capability_result != "PASS":
        raise TypeError("exact plan and checkpoint identity capability required")
    if (
        installed.candidate_sha256 != bundle.candidate.source_sha256
        or installed.eligibility_sha256 != bundle.eligibility.source_sha256
        or installed.authority.get("package_attempt_id") != execution_plan.get("package_attempt_id")
        or bundle.eligibility.get("primary_event_id") != execution_plan.get("primary_event_id")
        or bundle.eligibility.get("secondary_event_id") != execution_plan.get("secondary_event_id")
    ):
        raise ValueError("package-start gate causal binding")
    value = {
        "schema": PACKAGE_GATE_SCHEMA,
        "installed_triple_sha256": installed.source_sha256,
        "candidate_bundle_sha256": bundle.source_sha256,
        "execution_plan_sha256": execution_plan.sha256,
        "authorization_id": installed.authority.get("authorization_id"),
        "package_attempt_id": installed.authority.get("package_attempt_id"),
        "primary_event_id": execution_plan.get("primary_event_id"),
        "secondary_event_id": execution_plan.get("secondary_event_id"),
        "identity_capability": "PASS",
        "package_claim_eligible": True,
        "package_started": False,
        "checkpoint_opens": 0,
        "checkpoint_reads": 0,
        "numerical_operations": 0,
        "result": "PASS",
    }
    raw = canonical_bytes(value)
    state._record("qualification_package_gates")
    return CollapsedPackageStartGateV2(_PACKAGE_GATE_SEAL, value, raw)


def assert_collapsed_live_security_surface(*values: object) -> None:
    for value in values:
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            try:
                operation(value)
            except TypeError:
                continue
            raise TypeError("collapsed live authority copy surface")

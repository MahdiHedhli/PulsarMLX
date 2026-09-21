#!/usr/bin/env python3
"""Package-scoped Event 06 reservation and terminal transaction authority.

The live API has no caller-controlled registry root.  Qualification accepts a
sealed qualification installation and a disposable root, and cannot be
substituted for the live API.  Both modes use the same exclusive-create
mechanism while retaining exact, non-substitutable authority types.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_event06_collapsed_live_installation_v2 import CollapsedInstalledTripleV2
from f017_event06_storage_authority_v1 import fixed_live_registry_root
import f017_event06_storage_primitives_v1 as storage

if TYPE_CHECKING:
    from f017_event06_numerical_bridge_v1 import ValidatedConsumerView

_LIVE_REGISTRY_ROOT = fixed_live_registry_root()
_RESERVATION_SEALS = {"LIVE_CANONICAL": object(), "QUALIFICATION_ONLY": object()}
_SINK_SEALS = {"LIVE_CANONICAL": object(), "QUALIFICATION_ONLY": object()}


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _lexical(path: Path) -> Path:
    return storage.canonical_identity(path)


def _canonical_lexical(path: Path) -> Path:
    return storage.canonical_identity(path)


def _intersects(first: Path, second: Path) -> bool:
    first = _canonical_lexical(first)
    second = _canonical_lexical(second)
    return first == second or first in second.parents or second in first.parents


def _secure_directory(path: Path) -> Path:
    return storage.secure_directory(path)


def _prepare_live_registry() -> Path:
    """The sole production root selector; callers cannot supply a pathname."""
    if _LIVE_REGISTRY_ROOT != fixed_live_registry_root():
        raise ValueError("live registry fixed authority")
    return _secure_directory(_LIVE_REGISTRY_ROOT)


def _prepare_qualification_registry(root: Path) -> Path:
    if not isinstance(root, Path):
        raise TypeError("qualification registry root")
    # Reject equality, child, and parent intersections before resolving or
    # creating either path.  No live-root filesystem observation occurs here.
    if _intersects(root, _LIVE_REGISTRY_ROOT):
        raise ValueError("qualification registry intersects live registry")
    # A symlinked qualification root or ancestor can be a second spelling of
    # the fixed namespace even when its lexical spelling is unrelated.
    resolved = storage.resolved_identity(root)
    if _intersects(resolved, _LIVE_REGISTRY_ROOT):
        raise ValueError("qualification registry resolves into live registry")
    return _secure_directory(root)


class _ImmutableRecord:
    __slots__ = ("_items", "sha256")

    def _initialize(self, value: dict) -> None:
        object.__setattr__(self, "_items", MappingProxyType(copy.deepcopy(value)))
        object.__setattr__(self, "sha256", _sha(value))

    def __setattr__(self, name, value):
        del name, value
        raise TypeError("package registry authorities are immutable")

    def __delattr__(self, name):
        del name
        raise TypeError("package registry authorities are immutable")

    def __copy__(self):
        raise TypeError("package registry authorities cannot be copied")

    def __deepcopy__(self, memo):
        del memo
        raise TypeError("package registry authorities cannot be copied")

    def __reduce_ex__(self, protocol):
        del protocol
        raise TypeError("package registry authorities cannot be pickled")

    def get(self, key, default=None):
        return self._items.get(key, default)

    def as_dict(self) -> dict:
        return copy.deepcopy(dict(self._items))


class _Reservation(_ImmutableRecord):
    __slots__ = ("_root",)
    _MODE = ""

    def __new__(cls, seal=None, *args):
        del args
        expected = _RESERVATION_SEALS.get(cls._MODE)
        if expected is None or seal is not expected:
            raise TypeError("package reservations are registry-created")
        return super().__new__(cls)

    def __init__(self, seal, value, root):
        del seal
        self._initialize(value)
        object.__setattr__(self, "_root", root)

    @property
    def root(self) -> Path:
        return self._root


class ValidatedLivePackageAttemptReservation(_Reservation):
    __slots__ = ()
    _MODE = "LIVE_CANONICAL"


class ValidatedQualificationPackageAttemptReservation(_Reservation):
    __slots__ = ()
    _MODE = "QUALIFICATION_ONLY"


class _TerminalSink(_ImmutableRecord):
    __slots__ = ("_path", "_root")
    _MODE = ""

    def __new__(cls, seal=None, *args):
        del args
        expected = _SINK_SEALS.get(cls._MODE)
        if expected is None or seal is not expected:
            raise TypeError("terminal sinks are registry-created")
        return super().__new__(cls)

    def __init__(self, seal, value, path, root):
        del seal
        self._initialize(value)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_root", root)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def root(self) -> Path:
        return self._root


class ValidatedLivePackageTerminalSink(_TerminalSink):
    __slots__ = ()
    _MODE = "LIVE_CANONICAL"


class ValidatedQualificationPackageTerminalSink(_TerminalSink):
    __slots__ = ()
    _MODE = "QUALIFICATION_ONLY"


def _reservation_value(installed: ValidatedIdentityAuthority, mode: str) -> dict:
    authority = installed.as_dict()
    key = _sha({
        "authorization_id": authority["authorization_id"],
        "package_attempt_id": authority["package_attempt_id"],
        "checkpoint_set_sha256": authority["checkpoint_set_sha256"],
    })
    return {
        "schema": "pulsarmlx.f017.event06-v12-package-attempt-reservation/1.1.0",
        "authority_mode": mode,
        "authorization_id": authority["authorization_id"],
        "package_attempt_id": authority["package_attempt_id"],
        "installed_authority_sha256": installed.source_sha256,
        "checkpoint_set_sha256": authority["checkpoint_set_sha256"],
        "registry_key_sha256": key,
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "state": "PACKAGE_ATTEMPT_RESERVED",
    }


def _bank_reservation(installed: ValidatedIdentityAuthority, mode: str,
                      registry: Path, reservation_type: type[_Reservation]) -> _Reservation:
    value = _reservation_value(installed, mode)
    root = _secure_directory(registry / value["registry_key_sha256"])
    reservation = reservation_type(_RESERVATION_SEALS[mode], value, root)
    if storage.bank_exclusive(root / "package-attempt-reservation.json", value) != reservation.sha256:
        raise ValueError("package attempt reservation banking")
    return reservation


def _load_reservation(installed: ValidatedIdentityAuthority, mode: str,
                      registry: Path, reservation_type: type[_Reservation]) -> _Reservation:
    value = _reservation_value(installed, mode)
    root = registry / value["registry_key_sha256"]
    observed = storage.read_artifact(root / "package-attempt-reservation.json")
    if observed != value:
        raise ValueError("package attempt reservation reconstruction")
    return reservation_type(_RESERVATION_SEALS[mode], value, root)


def _qualification_reserve_live_package_attempt(
    installed: ValidatedIdentityAuthority,
) -> ValidatedLivePackageAttemptReservation:
    """Historical fixed-root reservation retained for qualification evidence."""
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("exact installed production authority required")
    if installed.as_dict().get("authority_scope") != "PRODUCTION":
        raise ValueError("live package reservation requires production authority")
    registry = _prepare_live_registry()
    return _bank_reservation(
        installed, "LIVE_CANONICAL", registry, ValidatedLivePackageAttemptReservation
    )


def _qualification_load_live_package_attempt(
    installed: ValidatedIdentityAuthority,
) -> ValidatedLivePackageAttemptReservation:
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("exact installed production authority required")
    if installed.as_dict().get("authority_scope") != "PRODUCTION":
        raise ValueError("live package reconstruction requires production authority")
    registry = _prepare_live_registry()
    return _load_reservation(
        installed, "LIVE_CANONICAL", registry, ValidatedLivePackageAttemptReservation
    )


def reserve_qualification_package_attempt(
    installed: CollapsedInstalledTripleV2 | ValidatedIdentityAuthority,
    qualification_root: Path,
) -> ValidatedQualificationPackageAttemptReservation:
    """Reserve a disposable qualification namespace; production is rejected first."""
    if type(installed) is CollapsedInstalledTripleV2:
        if installed.mode != "QUALIFICATION_ONLY":
            raise ValueError("qualification reservation requires qualification installation")
        authority = installed.authority
    elif type(installed) is ValidatedIdentityAuthority:
        authority = installed
        if authority.as_dict().get("authority_scope") not in {
            "SYNTHETIC", "SYNTHETIC_NON_AUTHORITY",
        }:
            raise ValueError("qualification reservation requires synthetic authority")
    else:
        raise TypeError("exact qualification installed authority required")
    if type(authority) is not ValidatedIdentityAuthority or authority.posture != "INSTALLED":
        raise TypeError("exact installed qualification authority required")
    registry = _prepare_qualification_registry(qualification_root)
    return _bank_reservation(
        authority, "QUALIFICATION_ONLY", registry,
        ValidatedQualificationPackageAttemptReservation,
    )


def load_qualification_package_attempt(
    installed: CollapsedInstalledTripleV2 | ValidatedIdentityAuthority,
    qualification_root: Path,
) -> ValidatedQualificationPackageAttemptReservation:
    if type(installed) is CollapsedInstalledTripleV2:
        if installed.mode != "QUALIFICATION_ONLY":
            raise ValueError("qualification reconstruction requires qualification installation")
        authority = installed.authority
    elif type(installed) is ValidatedIdentityAuthority:
        authority = installed
        if authority.as_dict().get("authority_scope") not in {
            "SYNTHETIC", "SYNTHETIC_NON_AUTHORITY",
        }:
            raise ValueError("qualification reconstruction requires synthetic authority")
    else:
        raise TypeError("exact qualification installed authority required")
    registry = _prepare_qualification_registry(qualification_root)
    return _load_reservation(
        authority, "QUALIFICATION_ONLY", registry,
        ValidatedQualificationPackageAttemptReservation,
    )


def _validate_view(reservation: _Reservation, bridge, package_terminal_view) -> None:
    from f017_event06_numerical_bridge_v1 import (
        ValidatedConsumerView, ValidatedNumericalBridge,
    )
    if (type(bridge) is not ValidatedNumericalBridge
            or type(package_terminal_view) is not ValidatedConsumerView
            or package_terminal_view.producer_kind != "PACKAGE_TERMINAL"
            or reservation.get("authorization_id") != bridge.get("authorization_id")
            or reservation.get("package_attempt_id") != bridge.get("package_attempt_id")
            or package_terminal_view.get("bridge_sha256") != bridge.sha256
            or package_terminal_view.get("package_attempt_id")
            != reservation.get("package_attempt_id")):
        raise TypeError("exact package closure authorities required")


def _claim(reservation: _Reservation, package_start_sha256: str | None,
           bridge_sha256: str, package_terminal_view,
           sink_type: type[_TerminalSink]) -> tuple[_TerminalSink, _TerminalSink]:
    claim = {
        "schema": "pulsarmlx.f017.event06-v12-package-terminal-claim/1.1.0",
        "authority_mode": reservation.get("authority_mode"),
        "authorization_id": reservation.get("authorization_id"),
        "package_attempt_id": reservation.get("package_attempt_id"),
        "package_attempt_reservation_sha256": reservation.sha256,
        "package_durable_start_sha256": package_start_sha256,
        "bridge_sha256": bridge_sha256,
        "binding_chain_head_sha256": package_terminal_view.get("binding_chain_head_sha256"),
        "v11_closure_root_sha256": package_terminal_view.get("v11_closure_root_sha256"),
        "accounting_binding_sha256": package_terminal_view.get("accounting_binding_sha256"),
        "terminal_layers": ["LEGACY_V11_CLOSURE", "PROMPT_BOUND_V12_CLOSURE"],
        "state": "TERMINALIZATION_CLAIMED",
    }
    claim_sha = _sha(claim)
    if storage.bank_exclusive(reservation.root / "package-terminal-claim.json", claim) != claim_sha:
        raise ValueError("package terminal claim banking")
    base = {
        "schema": "pulsarmlx.f017.event06-v12-package-terminal-sink/1.1.0",
        "authority_mode": reservation.get("authority_mode"),
        "package_attempt_id": reservation.get("package_attempt_id"),
        "package_attempt_reservation_sha256": reservation.sha256,
        "terminal_claim_sha256": claim_sha,
        "binding_chain_head_sha256": claim["binding_chain_head_sha256"],
        "v11_closure_root_sha256": claim["v11_closure_root_sha256"],
        "accounting_binding_sha256": claim["accounting_binding_sha256"],
    }
    seal = _SINK_SEALS[reservation.get("authority_mode")]
    legacy = sink_type(
        seal, base | {"terminal_layer": "LEGACY_V11_CLOSURE"},
        reservation.root / "legacy-package-terminal.json", reservation.root,
    )
    successor = sink_type(
        seal,
        base | {
            "terminal_layer": "PROMPT_BOUND_V12_CLOSURE",
            "legacy_terminal_sink_sha256": legacy.sha256,
        },
        reservation.root / "prompt-bound-package-terminal.json", reservation.root,
    )
    return legacy, successor


def _qualification_claim_live_terminal_sinks(
    reservation: ValidatedLivePackageAttemptReservation,
    package_start,
    bridge,
    execution_result,
    transition_records: list[dict],
    package_terminal_view: "ValidatedConsumerView",
) -> tuple[ValidatedLivePackageTerminalSink, ValidatedLivePackageTerminalSink]:
    """Consume the sole live terminal claim from exact coordinator outputs."""
    from execute_f017_corrected_oracle_event_v12_bridge import (
        ValidatedBridgeExecutionResult, ValidatedDurableStart,
    )
    from f017_event06_numerical_bridge_v1 import (
        PHASES, package_terminal_view as derive_package_terminal_view,
        validate_transition_chain,
    )
    if (type(reservation) is not ValidatedLivePackageAttemptReservation
            or type(package_start) is not ValidatedDurableStart
            or package_start.reservation is not reservation
            or type(execution_result) is not ValidatedBridgeExecutionResult
            or execution_result.get("result") != "PASS"):
        raise TypeError("exact live package closure authorities required")
    _validate_view(reservation, bridge, package_terminal_view)
    primary = execution_result["primary"]
    secondary = execution_result["secondary"]
    expected_subjects = [
        ("PACKAGE_DURABLE_START", package_start.sha256),
        ("IDENTITY_TERMINAL", bridge.get("identity_terminal_sha256")),
        ("PRIMARY_DURABLE_START", execution_result["primary_start_sha256"]),
        ("PRIMARY_RESULT_TERMINAL", primary["index"]["result_terminal_sha256"]),
        ("SECONDARY_DURABLE_START", execution_result["secondary_start_sha256"]),
        ("SECONDARY_RESULT_TERMINAL", secondary["index"]["result_terminal_sha256"]),
        ("COMPARISON_TERMINAL", _sha(execution_result["comparison_terminal"])),
        ("RELEASE_TERMINAL", _sha(execution_result["release_terminal"])),
        ("ACCOUNTING_BINDING", execution_result["accounting_binding_sha256"]),
        ("V11_PACKAGE_CLOSURE", execution_result["v11_closure_sha256"]),
    ]
    if (type(transition_records) is not list or len(transition_records) != len(PHASES)
            or [(item.get("subject_artifact_kind"), item.get("subject_sha256"))
                for item in transition_records] != expected_subjects):
        raise ValueError("live terminal subjects do not derive from execution result")
    chain = validate_transition_chain(bridge, transition_records)
    expected_view = derive_package_terminal_view(
        bridge, chain, execution_result["v11_closure_binding"],
        execution_result["accounting_binding"],
    )
    if expected_view.sha256 != package_terminal_view.sha256:
        raise ValueError("live terminal view does not derive from execution result")
    return _claim(
        reservation, package_start.sha256, bridge.sha256, package_terminal_view,
        ValidatedLivePackageTerminalSink,
    )


def claim_qualification_terminal_sinks(
    reservation: ValidatedQualificationPackageAttemptReservation,
    bridge,
    package_terminal_view: "ValidatedConsumerView",
) -> tuple[ValidatedQualificationPackageTerminalSink,
           ValidatedQualificationPackageTerminalSink]:
    if type(reservation) is not ValidatedQualificationPackageAttemptReservation:
        raise TypeError("exact qualification reservation required")
    _validate_view(reservation, bridge, package_terminal_view)
    return _claim(
        reservation, None, bridge.sha256, package_terminal_view,
        ValidatedQualificationPackageTerminalSink,
    )


def _validate_claim(sink: _TerminalSink) -> dict:
    claim = storage.read_artifact(sink.root / "package-terminal-claim.json")
    if (_sha(claim) != sink.get("terminal_claim_sha256")
            or claim.get("package_attempt_id") != sink.get("package_attempt_id")
            or claim.get("package_attempt_reservation_sha256")
            != sink.get("package_attempt_reservation_sha256")
            or claim.get("authority_mode") != sink.get("authority_mode")
            or claim.get("state") != "TERMINALIZATION_CLAIMED"):
        raise ValueError("terminal sink claim continuity")
    for key in ("binding_chain_head_sha256", "v11_closure_root_sha256",
                "accounting_binding_sha256"):
        if claim.get(key) != sink.get(key):
            raise ValueError("terminal sink closure continuity")
    return claim


def _bank_terminal(sink: _TerminalSink, value: dict) -> str:
    if type(value) is not dict or value.get("result") != "COMPLETE":
        raise TypeError("exact complete package terminal required")
    _validate_claim(sink)
    if (value.get("package_attempt_id") != sink.get("package_attempt_id")
            or value.get("authority_mode") != sink.get("authority_mode")):
        raise ValueError("package terminal package scope")
    layer = sink.get("terminal_layer")
    if layer == "LEGACY_V11_CLOSURE":
        if (value.get("package_attempt_reservation_sha256")
                != sink.get("package_attempt_reservation_sha256")
                or value.get("terminal_claim_sha256") != sink.get("terminal_claim_sha256")
                or value.get("terminal_sink_sha256") != sink.sha256):
            raise ValueError("legacy package terminal sink continuity")
        for key in ("binding_chain_head_sha256", "v11_closure_root_sha256",
                    "accounting_binding_sha256"):
            if value.get(key) != sink.get(key):
                raise ValueError("legacy package terminal closure continuity")
    elif layer == "PROMPT_BOUND_V12_CLOSURE":
        legacy = storage.read_artifact(sink.root / "legacy-package-terminal.json")
        if (legacy.get("terminal_sink_sha256")
                != sink.get("legacy_terminal_sink_sha256")
                or value.get("legacy_package_terminal_sha256") != _sha(legacy)):
            raise ValueError("successor package terminal legacy continuity")
    else:
        raise ValueError("package terminal layer")
    digest = _sha(value)
    if storage.bank_exclusive(sink.path, value) != digest:
        raise ValueError("package terminal banking")
    return digest


def _qualification_bank_live_terminal(
    sink: ValidatedLivePackageTerminalSink, value: dict
) -> str:
    if type(sink) is not ValidatedLivePackageTerminalSink:
        raise TypeError("exact live package terminal sink required")
    return _bank_terminal(sink, value)


def reserve_live_package_attempt(
    installed: ValidatedIdentityAuthority,
) -> ValidatedLivePackageAttemptReservation:
    """Fail closed: Sequence 39 owns the sole production one-shot claim."""
    del installed
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def load_live_package_attempt(
    installed: ValidatedIdentityAuthority,
) -> ValidatedLivePackageAttemptReservation:
    """Fail closed: historical live reservations are not production authority."""
    del installed
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def claim_live_terminal_sinks(
    reservation: ValidatedLivePackageAttemptReservation,
    package_start,
    bridge,
    execution_result,
    transition_records: list[dict],
    package_terminal_view: "ValidatedConsumerView",
) -> tuple[ValidatedLivePackageTerminalSink, ValidatedLivePackageTerminalSink]:
    """Fail closed: Sequence 39 has one package-scoped terminal writer."""
    del (
        reservation,
        package_start,
        bridge,
        execution_result,
        transition_records,
        package_terminal_view,
    )
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def bank_live_terminal(sink: ValidatedLivePackageTerminalSink, value: dict) -> str:
    """Fail closed: superseded terminal sinks cannot bank Event 06 state."""
    del sink, value
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def bank_qualification_terminal(
    sink: ValidatedQualificationPackageTerminalSink, value: dict,
) -> str:
    if type(sink) is not ValidatedQualificationPackageTerminalSink:
        raise TypeError("exact qualification package terminal sink required")
    return _bank_terminal(sink, value)


__all__ = [
    "ValidatedQualificationPackageAttemptReservation",
    "ValidatedQualificationPackageTerminalSink",
    "bank_qualification_terminal",
    "claim_qualification_terminal_sinks",
    "load_qualification_package_attempt",
    "reserve_qualification_package_attempt",
]

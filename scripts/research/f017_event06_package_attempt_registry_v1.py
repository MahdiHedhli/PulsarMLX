#!/usr/bin/env python3
"""Identity-derived one-shot package and terminal registry for Event 06.

Production registry paths are derived only from validated authority bytes and
the package identity. Qualification roots are explicit and their sinks carry a
non-live posture that terminal validators preserve.
"""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority

if TYPE_CHECKING:
    from f017_event06_numerical_bridge_v1 import ValidatedConsumerView

LIVE_REGISTRY_ROOT = Path("/private/var/tmp/pulsarmlx-f017-event06-v12-package-registry")
_RESERVATION_SEAL = object()
_SINK_SEAL = object()


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _secure_directory(path: Path) -> Path:
    path = path.resolve(strict=False)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    observed = path.resolve(strict=True)
    metadata = os.lstat(observed)
    if (observed != path.absolute() or stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077):
        raise ValueError("package registry directory identity")
    return observed


class ValidatedPackageAttemptReservation:
    __slots__ = ("_items", "_root", "sha256")

    def __new__(cls, seal=None, value=None, root=None):
        if seal is not _RESERVATION_SEAL:
            raise TypeError("package reservations are registry-created")
        return super().__new__(cls)

    def __init__(self, seal, value, root):
        object.__setattr__(self, "_items", MappingProxyType(dict(value)))
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "sha256", _sha(value))

    def __setattr__(self, name, value):
        del name, value
        raise TypeError("package reservations are immutable")

    def get(self, key, default=None):
        return self._items.get(key, default)

    @property
    def root(self) -> Path:
        return self._root


class ValidatedPackageTerminalSink:
    __slots__ = ("_items", "_path", "sha256")

    def __new__(cls, seal=None, value=None, path=None):
        if seal is not _SINK_SEAL:
            raise TypeError("terminal sinks are registry-created")
        return super().__new__(cls)

    def __init__(self, seal, value, path):
        object.__setattr__(self, "_items", MappingProxyType(dict(value)))
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "sha256", _sha(value))

    def __setattr__(self, name, value):
        del name, value
        raise TypeError("terminal sinks are immutable")

    def get(self, key, default=None):
        return self._items.get(key, default)

    @property
    def path(self) -> Path:
        return self._path


def reserve_package_attempt(
    installed: ValidatedIdentityAuthority,
    *,
    qualification_root: Path | None = None,
) -> ValidatedPackageAttemptReservation:
    raise RuntimeError(
        "superseded shared package reservation API; use exact live or qualification V2 API"
    )
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("exact installed authority required")
    authority = installed.as_dict()
    scope = authority.get("authority_scope")
    if qualification_root is not None:
        if not isinstance(qualification_root, Path):
            raise TypeError("qualification registry root")
        qualification_root = qualification_root.resolve(strict=False)
        live_root = LIVE_REGISTRY_ROOT.resolve(strict=False)
        if qualification_root == live_root or live_root in qualification_root.parents:
            raise ValueError("qualification registry cannot overlap live registry")
        authority_mode = "QUALIFICATION_ONLY"
        registry = qualification_root
    elif scope == "PRODUCTION":
        authority_mode = "LIVE_CANONICAL"
        registry = LIVE_REGISTRY_ROOT
    else:
        raise ValueError("live package reservation requires production authority")
    key = _sha({
        "authorization_id": authority["authorization_id"],
        "package_attempt_id": authority["package_attempt_id"],
        "installed_authority_sha256": installed.source_sha256,
        "checkpoint_set_sha256": authority["checkpoint_set_sha256"],
    })
    registry = _secure_directory(registry)
    root = _secure_directory(registry / key)
    value = {
        "schema": "pulsarmlx.f017.event06-v12-package-attempt-reservation/1.0.0",
        "authority_mode": authority_mode,
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
    reservation = ValidatedPackageAttemptReservation(_RESERVATION_SEAL, value, root)
    if bank_exclusive(root / "package-attempt-reservation.json", value) != reservation.sha256:
        raise ValueError("package attempt reservation banking")
    return reservation


def claim_terminal_sinks(
    reservation: ValidatedPackageAttemptReservation,
    package_start,
    bridge,
    execution_result,
    transition_records: list[dict],
    package_terminal_view: "ValidatedConsumerView",
) -> tuple[ValidatedPackageTerminalSink, ValidatedPackageTerminalSink]:
    """Consume the sole live terminal claim from exact coordinator outputs."""
    raise RuntimeError("superseded terminal claim API; use package-scoped V2 live claim")
    from execute_f017_corrected_oracle_event_v12_bridge import (
        ValidatedBridgeExecutionResult,
        ValidatedDurableStart,
    )
    from f017_event06_numerical_bridge_v1 import (
        PHASES,
        ValidatedConsumerView,
        ValidatedNumericalBridge,
        package_terminal_view as derive_package_terminal_view,
        validate_transition_chain,
    )

    if (type(reservation) is not ValidatedPackageAttemptReservation
            or reservation.get("authority_mode") != "LIVE_CANONICAL"
            or type(package_start) is not ValidatedDurableStart
            or package_start.reservation is not reservation
            or type(bridge) is not ValidatedNumericalBridge
            or type(execution_result) is not ValidatedBridgeExecutionResult
            or execution_result.get("result") != "PASS"
            or type(package_terminal_view) is not ValidatedConsumerView
            or package_terminal_view.producer_kind != "PACKAGE_TERMINAL"):
        raise TypeError("exact live package closure authorities required")
    if (reservation.get("package_attempt_id") != bridge.get("package_attempt_id")
            or package_start.get("package_attempt_id") != bridge.get("package_attempt_id")
            or execution_result.get("bridge_sha256") != bridge.sha256):
        raise ValueError("live terminal claim continuity")
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
            or [(record.get("subject_artifact_kind"), record.get("subject_sha256"))
                for record in transition_records] != expected_subjects):
        raise ValueError("live terminal subjects do not derive from execution result")
    chain = validate_transition_chain(bridge, transition_records)
    expected_view = derive_package_terminal_view(
        bridge, chain, execution_result["v11_closure_binding"],
        execution_result["accounting_binding"],
    )
    if expected_view.sha256 != package_terminal_view.sha256:
        raise ValueError("live terminal view does not derive from execution result")
    return _bank_terminal_claim(
        reservation, package_start.sha256, bridge.sha256, package_terminal_view
    )


def claim_qualification_terminal_sinks(
    reservation: ValidatedPackageAttemptReservation,
    bridge,
    package_terminal_view: "ValidatedConsumerView",
) -> tuple[ValidatedPackageTerminalSink, ValidatedPackageTerminalSink]:
    """Produce explicitly non-live sinks for the no-access composition path."""
    raise RuntimeError(
        "superseded terminal claim API; use package-scoped V2 qualification claim"
    )
    from f017_event06_numerical_bridge_v1 import (
        ValidatedConsumerView,
        ValidatedNumericalBridge,
    )

    if (type(reservation) is not ValidatedPackageAttemptReservation
            or reservation.get("authority_mode") != "QUALIFICATION_ONLY"
            or type(bridge) is not ValidatedNumericalBridge
            or reservation.get("package_attempt_id") != bridge.get("package_attempt_id")
            or type(package_terminal_view) is not ValidatedConsumerView
            or package_terminal_view.producer_kind != "PACKAGE_TERMINAL"):
        raise TypeError("exact qualification package closure authorities required")
    return _bank_terminal_claim(reservation, None, bridge.sha256, package_terminal_view)


def _bank_terminal_claim(reservation, package_start_sha256, bridge_sha256,
                         package_terminal_view):
    if (package_terminal_view.get("bridge_sha256") != bridge_sha256
            or package_terminal_view.get("package_attempt_id")
            != reservation.get("package_attempt_id")):
        raise ValueError("terminal claim consumer-view continuity")
    claim = {
        "schema": "pulsarmlx.f017.event06-v12-package-terminal-claim/1.0.0",
        "authority_mode": reservation.get("authority_mode"),
        "authorization_id": reservation.get("authorization_id"),
        "package_attempt_id": reservation.get("package_attempt_id"),
        "package_attempt_reservation_sha256": reservation.sha256,
        "package_durable_start_sha256": package_start_sha256,
        "bridge_sha256": bridge_sha256,
        "binding_chain_head_sha256": package_terminal_view.get(
            "binding_chain_head_sha256"
        ),
        "v11_closure_root_sha256": package_terminal_view.get(
            "v11_closure_root_sha256"
        ),
        "accounting_binding_sha256": package_terminal_view.get(
            "accounting_binding_sha256"
        ),
        "terminal_layers": ["LEGACY_V11_CLOSURE", "PROMPT_BOUND_V12_CLOSURE"],
        "state": "TERMINALIZATION_CLAIMED",
    }
    claim_sha = _sha(claim)
    if bank_exclusive(reservation.root / "package-terminal-claim.json", claim) != claim_sha:
        raise ValueError("package terminal claim banking")
    base = {
        "schema": "pulsarmlx.f017.event06-v12-package-terminal-sink/1.0.0",
        "authority_mode": reservation.get("authority_mode"),
        "package_attempt_id": reservation.get("package_attempt_id"),
        "package_attempt_reservation_sha256": reservation.sha256,
        "terminal_claim_sha256": claim_sha,
        "binding_chain_head_sha256": claim["binding_chain_head_sha256"],
        "v11_closure_root_sha256": claim["v11_closure_root_sha256"],
        "accounting_binding_sha256": claim["accounting_binding_sha256"],
    }
    legacy = ValidatedPackageTerminalSink(
        _SINK_SEAL, base | {"terminal_layer": "LEGACY_V11_CLOSURE"},
        reservation.root / "legacy-package-terminal.json",
    )
    successor = ValidatedPackageTerminalSink(
        _SINK_SEAL,
        base | {
            "terminal_layer": "PROMPT_BOUND_V12_CLOSURE",
            "legacy_terminal_sink_sha256": legacy.sha256,
        },
        reservation.root / "prompt-bound-package-terminal.json",
    )
    return legacy, successor


def bank_terminal(sink: ValidatedPackageTerminalSink, value: dict) -> str:
    raise RuntimeError("superseded generic terminal writer; use exact V2 mode writer")
    if type(sink) is not ValidatedPackageTerminalSink:
        raise TypeError("exact package terminal sink required")
    digest = _sha(value)
    if bank_exclusive(sink.path, value) != digest:
        raise ValueError("package terminal banking")
    return digest


__all__ = [
    "ValidatedPackageAttemptReservation",
    "ValidatedPackageTerminalSink",
    "bank_terminal",
    "claim_qualification_terminal_sinks",
    "claim_terminal_sinks",
    "reserve_package_attempt",
]

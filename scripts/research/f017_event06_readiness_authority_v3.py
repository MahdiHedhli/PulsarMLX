#!/usr/bin/env python3
"""Version-forward Event 06 readiness consumer for Sequence 9 authority."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Final, Never, Self, SupportsIndex

from f017_event06_readiness_authority_v2 import (
    ValidatedEvent06ReadinessV2,
    assert_readiness_sealed,
    validate_event06_readiness_declaration_v2,
)


ROOT: Final = Path(__file__).resolve().parents[2]
INTERFACE: Final = ROOT / (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-event06-readiness-consumer-interface-v11.json"
)
_SEAL = object()


class ValidatedEvent06ReadinessV3:
    """Opaque successor authority wrapping the independently validated value."""

    __slots__ = ("_delegate", "source_sha256", "_locked")
    _delegate: ValidatedEvent06ReadinessV2
    source_sha256: str
    _locked: bool

    def __new__(cls, seal: object = None, delegate: object = None) -> Self:
        del delegate
        if seal is not _SEAL:
            raise TypeError("Event 06 readiness V3 is validator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, delegate: ValidatedEvent06ReadinessV2) -> None:
        del seal
        assert_readiness_sealed(delegate)
        object.__setattr__(self, "_delegate", delegate)
        object.__setattr__(self, "source_sha256", delegate.source_sha256)
        object.__setattr__(self, "_locked", True)

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("Event 06 readiness V3 is immutable")

    def get(self, key: str) -> object:
        return self._delegate.get(key)

    def __copy__(self) -> Never:
        raise TypeError("Event 06 readiness V3 cannot be copied")

    def __deepcopy__(self, memo: object) -> Never:
        del memo
        raise TypeError("Event 06 readiness V3 cannot be copied")

    def __reduce_ex__(self, protocol: SupportsIndex) -> Never:
        del protocol
        raise TypeError("Event 06 readiness V3 cannot be pickled")


def validate_event06_readiness_declaration_v3(
    raw: bytes,
    *,
    repository_root: Path = ROOT,
    contract_path: Path = INTERFACE,
) -> ValidatedEvent06ReadinessV3:
    delegate = validate_event06_readiness_declaration_v2(
        raw,
        repository_root=repository_root,
        contract_path=contract_path,
    )
    return ValidatedEvent06ReadinessV3(_SEAL, delegate)


def assert_readiness_v3_sealed(
    value: object,
) -> ValidatedEvent06ReadinessV3:
    if type(value) is not ValidatedEvent06ReadinessV3:
        raise TypeError("sealed Event 06 readiness V3 required")
    return value


def _repository_delegate(
    value: ValidatedEvent06ReadinessV3,
) -> ValidatedEvent06ReadinessV2:
    """Narrow repository-internal adapter; not an authority serialization."""

    return assert_readiness_v3_sealed(value)._delegate


def assert_readiness_v3_copy_pickle_closed(
    value: ValidatedEvent06ReadinessV3,
) -> None:
    for operation in (copy.copy, copy.deepcopy):
        try:
            operation(value)
        except TypeError:
            continue
        raise TypeError("Event 06 readiness V3 copy surface")

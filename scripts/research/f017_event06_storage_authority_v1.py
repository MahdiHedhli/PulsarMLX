#!/usr/bin/env python3
"""Single sealed source for Event 06 production safety-state storage.

No public runtime input, environment lookup, current-directory lookup, home
directory expansion, or configuration value participates in this authority.
The path is deliberately exposed only to measured production modules; public
evidence binds its UTF-8 digest and length, not its plaintext.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


_FIXED_LIVE_REGISTRY_ROOT = Path(
    "/private/var/tmp/pulsarmlx-f017-event06-v12-package-registry"
)
FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256 = (
    "e9628d51208d2340d67885b471bf87a5cfa0a372a759e095378f5609c1843e83"
)
FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_LENGTH = 60


def fixed_live_registry_root() -> Path:
    """Return the one measured production storage authority."""
    raw = str(_FIXED_LIVE_REGISTRY_ROOT).encode("utf-8")
    if (len(raw) != FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_LENGTH
            or hashlib.sha256(raw).hexdigest()
            != FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256):
        raise RuntimeError("fixed Event 06 live registry authority drift")
    return _FIXED_LIVE_REGISTRY_ROOT


def package_storage_layout(package_root: Path) -> dict[str, Path]:
    """Derive all live package storage from an already sealed reservation root."""
    if not isinstance(package_root, Path):
        raise TypeError("sealed package root required")
    return {
        "identity": package_root / "identity",
        "primary": package_root / "primary",
        "secondary": package_root / "secondary",
        "package": package_root / "package",
    }


__all__ = [
    "FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_LENGTH",
    "FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256",
    "fixed_live_registry_root",
    "package_storage_layout",
]

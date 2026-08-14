#!/usr/bin/env python3
"""Validate phase-declared analytical retention without hard-coded fields."""

from __future__ import annotations

import re

SHA = re.compile(r"^[0-9a-f]{64}$")


def resolve(document: object, pointer: str) -> object:
    value = document
    if not pointer.startswith("/"):
        raise ValueError(f"invalid JSON pointer: {pointer}")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            raise KeyError(pointer)
        value = value[token]
    return value


def validate_declared_retention(config: dict[str, object], evidence: dict[str, object]) -> None:
    requirements = config.get("required_analytical_retention")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("required_analytical_retention must be non-empty")
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise ValueError("invalid retention declaration")
        name = str(requirement.get("name", "unnamed"))
        try:
            value = resolve(evidence, str(requirement["value_path"]))
            bound_hash = resolve(evidence, str(requirement["hash_path"]))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"missing declared analytical retention: {name}") from exc
        if value is None or not isinstance(bound_hash, str) or not SHA.fullmatch(bound_hash):
            raise ValueError(f"invalid declared analytical retention: {name}")

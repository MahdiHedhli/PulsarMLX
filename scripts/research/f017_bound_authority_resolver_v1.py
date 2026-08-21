#!/usr/bin/env python3
"""Generic fail-closed resolver for F017 bound JSON fields and source constants."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any, Iterator


class BoundAuthorityError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise BoundAuthorityError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundAuthorityError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BoundAuthorityError(f"object required: {path}")
    return value


def safe_path(root: pathlib.Path, raw: Any) -> pathlib.Path:
    if not isinstance(raw, str) or not raw:
        raise BoundAuthorityError("bound path missing")
    relative = pathlib.Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise BoundAuthorityError(f"unsafe bound path: {raw}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise BoundAuthorityError(f"bound path escapes root: {raw}") from exc
    return path


def resolve_json_path(value: Any, components: list[Any]) -> Any:
    current = value
    for component in components:
        if isinstance(current, dict) and isinstance(component, str) and component in current:
            current = current[component]
        elif isinstance(current, list) and isinstance(component, int) and 0 <= component < len(current):
            current = current[component]
        else:
            raise BoundAuthorityError(f"unresolved json_path component: {component!r}")
    return current


def declaration_nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if "path" in value and "sha256" in value and ("field" in value or "json_path" in value):
            yield value
        for child in value.values():
            yield from declaration_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from declaration_nodes(child)


def validate_bound_fields(root: pathlib.Path, contract: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for node in declaration_nodes(contract):
        path = safe_path(root, node["path"])
        if not path.is_file() or sha256(path) != node["sha256"]:
            raise BoundAuthorityError(f"bound identity mismatch: {node['path']}")
        document = load_json(path)
        if "field" in node:
            field = node["field"]
            if not isinstance(field, str) or not field or "." in field:
                raise BoundAuthorityError("field must be one exact top-level key")
            components: list[Any] = [field]
        else:
            components = node["json_path"]
            if not isinstance(components, list) or not components:
                raise BoundAuthorityError("json_path must be a non-empty array")
        if "expected" not in node:
            raise BoundAuthorityError(f"bound field lacks expected value: {node['path']}")
        resolved = resolve_json_path(document, components)
        if resolved != node["expected"]:
            raise BoundAuthorityError(f"bound value mismatch: {node['path']} {components}")
        observations.append({"path":node["path"],"sha256":node["sha256"],"json_path":components,"resolved":resolved})
    return observations


def validate_executable_numeric_bindings(root: pathlib.Path, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for binding in bindings:
        if set(binding) != {"id", "path", "sha256", "extractor", "pattern", "expected", "limitation"}:
            raise BoundAuthorityError("numeric binding schema")
        path = safe_path(root, binding["path"])
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise BoundAuthorityError(f"numeric source identity: {binding['id']}")
        if binding["extractor"] == "REGEX_FLOAT_LITERAL":
            matches = re.findall(binding["pattern"], path.read_text())
            if len(matches) != 1:
                raise BoundAuthorityError(f"numeric extractor cardinality: {binding['id']}")
            token = matches[0] if isinstance(matches[0], str) else matches[0][0]
            token = token.rstrip("fF")
            try:
                resolved: Any = float(token)
            except ValueError as exc:
                raise BoundAuthorityError(f"numeric parse: {binding['id']}") from exc
        elif binding["extractor"] == "REGEX_SOURCE_TOKEN":
            matches = re.findall(binding["pattern"], path.read_text())
            if len(matches) != 1:
                raise BoundAuthorityError(f"source token cardinality: {binding['id']}")
            resolved = matches[0] if isinstance(matches[0], str) else matches[0][0]
        else:
            raise BoundAuthorityError(f"unknown numeric extractor: {binding['extractor']}")
        if resolved != binding["expected"]:
            raise BoundAuthorityError(f"numeric executable mismatch: {binding['id']}")
        observations.append({"id":binding["id"],"path":binding["path"],"resolved":resolved,"limitation":binding["limitation"]})
    return observations

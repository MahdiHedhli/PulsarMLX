#!/usr/bin/env python3
"""Strict typed resolver for F017 path/SHA/JSON-field and numeric bindings."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re


class ResolutionError(RuntimeError):
    pass


def unique(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ResolutionError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load(path: Path):
    try:
        return json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError(f"cannot load {path}: {exc}") from exc


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_equal(actual, expected) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(exact_equal(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(exact_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def safe(root: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ResolutionError("path")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise ResolutionError("unsafe path")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ResolutionError("path escape") from exc
    return resolved


def nodes(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value and ("field" in value or "json_path" in value):
            yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def resolve(document, path):
    value = document
    for component in path:
        if isinstance(value, dict) and type(component) is str and component in value:
            value = value[component]
        elif isinstance(value, list) and type(component) is int and 0 <= component < len(value):
            value = value[component]
        else:
            raise ResolutionError(f"unresolved field: {component!r}")
    return value


def validate_bound_fields(root: Path, contract) -> list[dict]:
    observations = []
    for node in nodes(contract):
        path = safe(root, node.get("path"))
        if not path.is_file() or sha(path) != node.get("sha256"):
            raise ResolutionError(f"hash: {node.get('path')}")
        components = [node["field"]] if "field" in node else node.get("json_path")
        if not isinstance(components, list) or not components or "expected" not in node:
            raise ResolutionError("binding schema")
        actual = resolve(load(path), components)
        if not exact_equal(actual, node["expected"]):
            raise ResolutionError(f"strict typed mismatch: {node.get('path')} {components}")
        observations.append({"path": node["path"], "sha256": node["sha256"], "json_path": components, "resolved_type": type(actual).__name__, "resolved": actual})
    return observations


def validate_numeric_bindings(root: Path, bindings) -> list[dict]:
    observations = []
    for binding in bindings:
        path = safe(root, binding["path"])
        if not path.is_file() or sha(path) != binding["sha256"]:
            raise ResolutionError(f"numeric hash: {binding['id']}")
        matches = re.findall(binding["pattern"], path.read_text())
        if len(matches) != 1:
            raise ResolutionError(f"numeric cardinality: {binding['id']}")
        token = matches[0] if isinstance(matches[0], str) else matches[0][0]
        kind = binding["extractor"]
        if kind == "REGEX_F32_LITERAL":
            actual = float(token.rstrip("fF").replace("_", ""))
        elif kind == "REGEX_USIZE_LITERAL":
            actual = int(token.replace("_", ""))
        elif kind == "REGEX_SOURCE_TOKEN":
            actual = token
        else:
            raise ResolutionError(f"numeric extractor: {kind}")
        if not exact_equal(actual, binding["expected"]):
            raise ResolutionError(f"numeric mismatch: {binding['id']}")
        observations.append({"id": binding["id"], "resolved": actual, "resolved_type": type(actual).__name__, "limitation": binding.get("limitation")})
    return observations

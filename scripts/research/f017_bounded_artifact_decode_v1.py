#!/usr/bin/env python3
"""Bounded, canonical JSON decoding for active F017 runtime authority bytes."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
from typing import Final


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"


class ArtifactDecodeError(ValueError):
    """Stable fail-closed boundary for malformed runtime authority bytes."""


@dataclass(frozen=True)
class ArtifactLimits:
    max_bytes: int
    max_depth: int
    max_object_keys: int
    max_array_elements: int
    max_string_chars: int
    max_integer_digits: int
    max_number_chars: int
    require_canonical_bytes: bool = True

    def __post_init__(self) -> None:
        for name, value in (
            ("max_bytes", self.max_bytes),
            ("max_depth", self.max_depth),
            ("max_object_keys", self.max_object_keys),
            ("max_array_elements", self.max_array_elements),
            ("max_string_chars", self.max_string_chars),
            ("max_integer_digits", self.max_integer_digits),
            ("max_number_chars", self.max_number_chars),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"invalid artifact limit: {name}")
        if type(self.require_canonical_bytes) is not bool:
            raise ValueError("invalid canonical-byte policy")


DEFAULT_LIMITS: Final = ArtifactLimits(
    max_bytes=1_048_576,
    max_depth=64,
    max_object_keys=4_096,
    max_array_elements=16_384,
    max_string_chars=524_288,
    max_integer_digits=128,
    max_number_chars=256,
)
NONCANONICAL_LIMITS: Final = ArtifactLimits(
    max_bytes=DEFAULT_LIMITS.max_bytes,
    max_depth=DEFAULT_LIMITS.max_depth,
    max_object_keys=DEFAULT_LIMITS.max_object_keys,
    max_array_elements=DEFAULT_LIMITS.max_array_elements,
    max_string_chars=DEFAULT_LIMITS.max_string_chars,
    max_integer_digits=DEFAULT_LIMITS.max_integer_digits,
    max_number_chars=DEFAULT_LIMITS.max_number_chars,
    require_canonical_bytes=False,
)


def _scan_structure(raw: bytes, limits: ArtifactLimits) -> None:
    """Reject excessive nesting before Python's recursive JSON decoder runs."""
    depth = 0
    in_string = False
    escaped = False
    string_bytes = 0
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
                string_bytes += 1
                continue
            if byte == 0x5C:  # backslash
                escaped = True
                string_bytes += 1
                continue
            if byte == 0x22:  # quote
                in_string = False
                string_bytes = 0
                continue
            if byte < 0x20:
                raise ArtifactDecodeError("unescaped control byte in JSON string")
            string_bytes += 1
            if string_bytes > limits.max_string_chars * 6:
                # Six raw ASCII bytes is the maximum canonical JSON expansion
                # of one Unicode code point (\\uXXXX).
                raise ArtifactDecodeError("artifact string exceeds bound")
            continue
        if byte == 0x22:
            in_string = True
            string_bytes = 0
        elif byte in (0x7B, 0x5B):  # { [
            depth += 1
            if depth > limits.max_depth:
                raise ArtifactDecodeError("artifact nesting exceeds bound")
        elif byte in (0x7D, 0x5D):  # } ]
            depth -= 1
            if depth < 0:
                raise ArtifactDecodeError("unbalanced JSON structure")
    if in_string or escaped or depth != 0:
        raise ArtifactDecodeError("truncated JSON structure")


def _bounded_integer(token: str, maximum_digits: int) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > maximum_digits:
        raise ArtifactDecodeError("artifact integer exceeds bound")
    return int(token)


def _bounded_float(token: str, maximum_chars: int) -> float:
    if len(token) > maximum_chars:
        raise ArtifactDecodeError("artifact float exceeds lexical bound")
    value = float(token)
    if not math.isfinite(value):
        raise ArtifactDecodeError("artifact float is nonfinite")
    return value


def _decode(raw: bytes, limits: ArtifactLimits) -> object:
    if type(raw) is not bytes:
        raise ArtifactDecodeError("artifact input must be bytes")
    if len(raw) > limits.max_bytes:
        raise ArtifactDecodeError("artifact bytes exceed bound")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ArtifactDecodeError("artifact is not valid UTF-8") from exc
    # UTF-8 validation is deliberately first: the frozen decode contract
    # permits the structural scanner to reason only about a valid byte-to-text
    # mapping.  The scanner still runs before recursive JSON decoding.
    _scan_structure(raw, limits)

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in items:
            if key in value:
                raise ArtifactDecodeError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ArtifactDecodeError(f"nonfinite JSON number: {item}")
            ),
            parse_int=lambda item: _bounded_integer(item, limits.max_integer_digits),
            parse_float=lambda item: _bounded_float(item, limits.max_number_chars),
        )
    except ArtifactDecodeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError, TypeError, OverflowError) as exc:
        raise ArtifactDecodeError("invalid bounded JSON artifact") from exc

    # Container depth is counted by opening ``{``/``[`` tokens.  The root
    # scalar therefore has depth zero and a root container depth one.
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > limits.max_depth:
            raise ArtifactDecodeError("decoded artifact nesting exceeds bound")
        if type(item) is dict:
            container_depth = depth + 1
            if container_depth > limits.max_depth:
                raise ArtifactDecodeError("decoded artifact nesting exceeds bound")
            if len(item) > limits.max_object_keys:
                raise ArtifactDecodeError("artifact object key census exceeds bound")
            for key, child in item.items():
                if type(key) is not str or len(key) > limits.max_string_chars:
                    raise ArtifactDecodeError("artifact key exceeds bound")
                stack.append((child, container_depth))
        elif type(item) is list:
            container_depth = depth + 1
            if container_depth > limits.max_depth:
                raise ArtifactDecodeError("decoded artifact nesting exceeds bound")
            if len(item) > limits.max_array_elements:
                raise ArtifactDecodeError("artifact array census exceeds bound")
            stack.extend((child, container_depth) for child in item)
        elif type(item) is str and len(item) > limits.max_string_chars:
            raise ArtifactDecodeError("decoded artifact string exceeds bound")
        elif type(item) is int and len(str(abs(item))) > limits.max_integer_digits:
            raise ArtifactDecodeError("decoded artifact integer exceeds bound")

    if limits.require_canonical_bytes:
        try:
            expected = _canonical_bytes(value)
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            raise ArtifactDecodeError("artifact cannot be canonically serialized") from exc
        if raw != expected:
            raise ArtifactDecodeError("noncanonical JSON artifact bytes")
    return value


def parse_artifact_bytes(raw: bytes, *, limits: ArtifactLimits = DEFAULT_LIMITS,
                         expected_top_level: type | None = dict) -> object:
    try:
        value = _decode(raw, limits)
    except ArtifactDecodeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError, TypeError, OverflowError) as exc:
        raise ArtifactDecodeError("artifact decode failed") from exc
    if expected_top_level is not None and type(value) is not expected_top_level:
        raise ArtifactDecodeError("artifact top-level type")
    return value


def read_artifact(path: Path, *, limits: ArtifactLimits = DEFAULT_LIMITS,
                  expected_top_level: type | None = dict) -> object:
    if not isinstance(path, Path):
        raise ArtifactDecodeError("artifact path type")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise
    try:
        return read_artifact_fd(descriptor, limits=limits, expected_top_level=expected_top_level)
    finally:
        os.close(descriptor)


def read_artifact_at(directory_fd: int, leaf: str, *, limits: ArtifactLimits = DEFAULT_LIMITS,
                     expected_top_level: type | None = dict) -> object:
    if type(directory_fd) is not int or type(leaf) is not str or not leaf or "/" in leaf or leaf in {".", ".."}:
        raise ArtifactDecodeError("descriptor-relative artifact identity")
    descriptor = os.open(leaf, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
    try:
        return read_artifact_fd(descriptor, limits=limits, expected_top_level=expected_top_level)
    finally:
        os.close(descriptor)


def read_artifact_fd(descriptor: int, *, limits: ArtifactLimits = DEFAULT_LIMITS,
                     expected_top_level: type | None = dict) -> object:
    if type(descriptor) is not int or descriptor < 0:
        raise ArtifactDecodeError("artifact descriptor")
    chunks: list[bytes] = []
    remaining = limits.max_bytes + 1
    offset = 0
    while remaining:
        chunk = os.pread(descriptor, min(65_536, remaining), offset)
        if not chunk:
            break
        chunks.append(chunk)
        offset += len(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > limits.max_bytes:
        raise ArtifactDecodeError("artifact bytes exceed bound")
    return parse_artifact_bytes(raw, limits=limits, expected_top_level=expected_top_level)

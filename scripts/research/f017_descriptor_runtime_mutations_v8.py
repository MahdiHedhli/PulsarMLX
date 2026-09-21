#!/usr/bin/env python3
"""Permanent malformed-descriptor campaign for the production V8 validator."""
from __future__ import annotations

import copy

from f017_descriptor_lease_manager_v8 import validate_descriptors


def valid_descriptors() -> list[dict]:
    return [{
        "device": 1, "inode": 1000 + ordinal, "mode": 0o100600,
        "size": 4096 * ordinal, "mtime_ns": 1, "ctime_ns": 1,
        "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
        "lease_id": f"LEASE-F017-V8-RUNTIME-{ordinal}",
    } for ordinal in range(2, 7)]


class MappingSubclass(dict):
    pass


def mutations() -> list[tuple[str, object]]:
    cases: list[tuple[str, object]] = []
    for name, value in (
        ("NEGATIVE", -1), ("BOUND", 65536), ("PROBE-1100644", 0o1100644),
        ("LARGE", 2**31), ("TRUE", True), ("FALSE", False), ("FLOAT", 1.0),
        ("STRING", "33152"), ("BYTES", b"33152"), ("NONE", None),
        ("LIST", []), ("DICT", {}),
    ):
        item = valid_descriptors(); item[0]["mode"] = value
        cases.append((f"V8-RT-MODE-{name}", item))
    for name, value in (
        ("NONE", None), ("ZERO", 0), ("TRUE", True), ("STRING", ""),
        ("BYTES", b""), ("LIST", []), ("TUPLE", ()), ("SET", set()),
        ("MAPPING-SUBCLASS", MappingSubclass(valid_descriptors()[0])),
    ):
        item = valid_descriptors(); item[0] = value
        cases.append((f"V8-RT-ENTRY-{name}", item))
    missing = valid_descriptors(); del missing[0]["ctime_ns"]
    extra = valid_descriptors(); extra[0]["unexpected"] = 1
    nested = valid_descriptors(); nested[0]["device"] = {"nested": 1}
    cases.extend([
        ("V8-RT-ENTRY-MISSING-KEY", missing),
        ("V8-RT-ENTRY-EXTRA-KEY", extra),
        ("V8-RT-ENTRY-NESTED-MALFORMED", nested),
    ])
    for name, value in (
        ("LIST", []), ("DICT", {}), ("SET", set()), ("TUPLE", ()),
        ("TRUE", True), ("INTEGER", 7), ("FLOAT", 1.0), ("BYTES", b"LEASE"),
        ("NONE", None), ("EMPTY", ""), ("INVALID-CHARS", "LEASE/INVALID"),
        ("OVERLENGTH", "L" * 129), ("INERT", "LEASE-INERT-2"),
        ("FIXTURE", "LEASE-FIXTURE-2"),
    ):
        item = valid_descriptors(); item[0]["lease_id"] = value
        cases.append((f"V8-RT-LEASE-{name}", item))
    duplicate = valid_descriptors(); duplicate[1]["lease_id"] = duplicate[0]["lease_id"]
    cases.append(("V8-RT-LEASE-DUPLICATE", duplicate))
    for field, value in (
        ("device", True), ("inode", "1002"), ("size", -1),
        ("mtime_ns", 1.0), ("ctime_ns", None), ("shard_ordinal", False),
        ("role", b"GRAPH_PAYLOAD"),
    ):
        item = valid_descriptors(); item[0][field] = value
        cases.append((f"V8-RT-FIELD-{field.upper()}", item))
    wrong_ordinal = valid_descriptors(); wrong_ordinal[0]["shard_ordinal"] = 3
    duplicate_inode = valid_descriptors(); duplicate_inode[1]["inode"] = duplicate_inode[0]["inode"]
    cases.extend([
        ("V8-RT-ORDINAL-CENSUS", wrong_ordinal),
        ("V8-RT-DESCRIPTOR-IDENTITY-DUPLICATE", duplicate_inode),
    ])
    return cases


def qualify() -> dict:
    failures = []
    for mutation_id, value in mutations():
        try:
            validate_descriptors(copy.deepcopy(value))
        except ValueError:
            failures.append({"mutation_id": mutation_id, "failure_class": "ValueError"})
        except Exception as exc:  # pragma: no cover - this is the property under test
            raise AssertionError(f"uncontrolled exception: {mutation_id}:{type(exc).__name__}") from exc
        else:
            raise AssertionError(f"unexpected mutation pass: {mutation_id}")
    return {"result": "PASS", "mutation_count": len(failures), "unexpected_passes": 0, "uncontrolled_exception_classes": 0, "results": failures}

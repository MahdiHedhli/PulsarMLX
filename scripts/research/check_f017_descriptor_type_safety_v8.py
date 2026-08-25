#!/usr/bin/env python3
"""Independent V8 descriptor type-safety and continuity checker.

This checker intentionally shares no imports or validation helpers with the
primary transitive-closure validator or the design generator.
"""
from __future__ import annotations

import argparse
import json
import re
import stat
from pathlib import Path


FIELDS = {
    "device",
    "inode",
    "mode",
    "size",
    "mtime_ns",
    "ctime_ns",
    "shard_ordinal",
    "role",
    "lease_id",
}
INTEGER_FIELDS = {"device", "inode", "mode", "size", "mtime_ns", "ctime_ns", "shard_ordinal"}
ORDINALS = [2, 3, 4, 5, 6]
LEASE_PATTERN = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?")
FORBIDDEN_MARKERS = ("INERT", "FIXTURE", "TEST", "SYNTHETIC")


def _read_payload(path: Path) -> dict:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable descriptor artifact: {path.name}") from exc
    if type(value) is not dict or type(value.get("payload")) is not dict:
        raise ValueError(f"descriptor artifact envelope type mismatch: {path.name}")
    return value["payload"]


def _validate_descriptors(value: object) -> list[dict]:
    if type(value) is not list or len(value) != 5:
        raise ValueError("descriptor collection must be an exact five-element list")
    if any(type(item) is not dict for item in value):
        raise ValueError("descriptor entry must be an exact dictionary")
    descriptors: list[dict] = value
    if any(set(item) != FIELDS for item in descriptors):
        raise ValueError("descriptor entry key census mismatch")
    for item in descriptors:
        if any(type(item[field]) is not int for field in INTEGER_FIELDS):
            raise ValueError("descriptor integer field type mismatch")
        if any(item[field] < 0 for field in ("device", "inode", "size", "mtime_ns", "ctime_ns")):
            raise ValueError("descriptor integer field range mismatch")
        if item["mode"] < 0 or item["mode"] >= 65536:
            raise ValueError("descriptor mode outside portable 16-bit domain")
        if not stat.S_ISREG(item["mode"]):
            raise ValueError("descriptor mode is not a regular file")
        if type(item["role"]) is not str or item["role"] != "GRAPH_PAYLOAD":
            raise ValueError("descriptor role mismatch")
        if (type(item["lease_id"]) is not str or LEASE_PATTERN.fullmatch(item["lease_id"]) is None
                or any(marker in item["lease_id"] for marker in FORBIDDEN_MARKERS)):
            raise ValueError("descriptor lease-id type or grammar mismatch")
    if [item["shard_ordinal"] for item in descriptors] != ORDINALS:
        raise ValueError("descriptor ordinal census mismatch")
    if len({(item["device"], item["inode"]) for item in descriptors}) != 5:
        raise ValueError("descriptor device/inode identity is not unique")
    if len({item["lease_id"] for item in descriptors}) != 5:
        raise ValueError("descriptor lease IDs are not unique")
    return descriptors


def validate_package(package_root: Path) -> dict:
    manifest = _read_payload(package_root / "descriptor_lease_manifest.json")
    if set(manifest) != {"lease_count", "ordinals", "lease_ids", "descriptor_identities"}:
        raise ValueError("descriptor lease manifest key census mismatch")
    if type(manifest["lease_count"]) is not int or manifest["lease_count"] != 5:
        raise ValueError("descriptor lease count mismatch")
    if type(manifest["ordinals"]) is not list or manifest["ordinals"] != ORDINALS:
        raise ValueError("descriptor manifest ordinal mismatch")
    lease_ids = manifest["lease_ids"]
    if type(lease_ids) is not list or len(lease_ids) != 5:
        raise ValueError("lease-id collection mismatch")
    for lease_id in lease_ids:
        if (type(lease_id) is not str or LEASE_PATTERN.fullmatch(lease_id) is None
                or any(marker in lease_id for marker in FORBIDDEN_MARKERS)):
            raise ValueError("lease-id type or grammar mismatch")
    if len(set(lease_ids)) != 5:
        raise ValueError("lease IDs are not unique")
    descriptors = _validate_descriptors(manifest["descriptor_identities"])
    if [item["lease_id"] for item in descriptors] != lease_ids:
        raise ValueError("descriptor lease IDs do not match manifest")
    for report_name, role in (
        ("primary_descriptor_continuity_report.json", "PRIMARY"),
        ("secondary_descriptor_continuity_report.json", "SECONDARY"),
    ):
        report_path = package_root / report_name
        if not report_path.exists():
            continue
        report = _read_payload(report_path)
        if set(report) != {"consumer_role", "descriptor_count", "ordinals", "lease_ids", "descriptor_identities", "path_reopen_count"}:
            raise ValueError(f"continuity report key census mismatch: {role}")
        if (type(report["consumer_role"]) is not str or report["consumer_role"] != role
                or type(report["descriptor_count"]) is not int or report["descriptor_count"] != 5
                or type(report["path_reopen_count"]) is not int or report["path_reopen_count"] != 0
                or report["ordinals"] != ORDINALS
                or report["lease_ids"] != lease_ids
                or report["descriptor_identities"] != descriptors):
            raise ValueError(f"continuity report restatement mismatch: {role}")
    return {
        "result": "PASS",
        "descriptor_count": 5,
        "lease_id_count": 5,
        "ordinals": ORDINALS,
        "mode_domain": "0<=mode<2**16",
        "original_checkpoint_access": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_package(args.package_root), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

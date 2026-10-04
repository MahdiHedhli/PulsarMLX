#!/usr/bin/env python3
"""Independent bounded snapshot byte/hash custody check; no numerical decoding."""
import argparse
import hashlib
import json
import os
import stat
import struct
from pathlib import Path

MAX_HEADER = 128 * 1024
MAX_PAYLOAD = 32 * 1024 * 1024
MAX_RECEIPT = 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw):
    def bad_constant(_):
        raise ValueError("non-finite JSON constant")
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=bad_constant)


def bounded_receipt(path):
    with open(path, "rb") as file:
        raw = file.read(MAX_RECEIPT + 1)
    if len(raw) > MAX_RECEIPT:
        raise ValueError("receipt budget")
    return strict_json(raw)


def integer(value, label, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(label)
    return value


def verify(snapshot, capture):
    if capture.get("schema") != "pulsarmlx.selected-expert-freeze/1":
        raise ValueError("capture schema")
    total_payload = integer(capture.get("requested_payload_bytes"), "payload budget", MAX_PAYLOAD)
    if capture.get("payload_read_calls") != 9 or capture.get("native_calls") != 0:
        raise ValueError("capture calls")
    if capture.get("snapshot_payload_bytes_written") != total_payload:
        raise ValueError("capture payload count")
    fd = os.open(snapshot, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or not 16 <= before.st_size <= 16 + MAX_HEADER + MAX_PAYLOAD:
            raise ValueError("snapshot size/type")
        prefix = file.read(16)
        if len(prefix) != 16 or prefix[:8] != b"PLSEX001":
            raise ValueError("snapshot magic/prefix")
        header_length = struct.unpack("<Q", prefix[8:])[0]
        if not 0 < header_length <= MAX_HEADER:
            raise ValueError("header budget")
        raw_header = file.read(header_length)
        if len(raw_header) != header_length:
            raise ValueError("truncated header")
        header = strict_json(raw_header)
        if header.get("schema") != "pulsarmlx.selected-expert-snapshot/1":
            raise ValueError("snapshot schema")
        if header.get("owned") != capture.get("owned"):
            raise ValueError("owned receipt binding")
        lengths = header.get("payload_lengths")
        if type(lengths) is not list or len(lengths) != 9:
            raise ValueError("nine ranges required")
        lengths = [integer(n, "range budget", MAX_PAYLOAD) for n in lengths]
        if sum(lengths) != total_payload or before.st_size != 16 + header_length + total_payload:
            raise ValueError("snapshot framing")
        owned = header["owned"]
        if owned.get("schema") != "pulsarmlx.bounded-expert-owned/1":
            raise ValueError("owned schema")
        plan = owned["plan"]
        declared = [r["len"] for plane in plan["planes"] for r in plane["ranges"]]
        if declared != lengths or plan["selected_bytes"] != total_payload or owned["owned_bytes"] != total_payload:
            raise ValueError("plan length binding")
        hashes = owned["selected_range_sha256"]
        if type(hashes) is not list or len(hashes) != 9:
            raise ValueError("nine hashes required")
        whole = hashlib.sha256(prefix + raw_header)
        actual_hashes = []
        for n, expected in zip(lengths, hashes):
            digest = hashlib.sha256()
            remaining = n
            while remaining:
                chunk = file.read(min(256 * 1024, remaining))
                if not chunk:
                    raise ValueError("truncated payload")
                whole.update(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            actual = digest.hexdigest()
            if actual != expected:
                raise ValueError("selected range hash")
            actual_hashes.append(actual)
        if file.read(1):
            raise ValueError("trailing content")
        after = os.fstat(file.fileno())
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, f) != getattr(after, f) for f in fields):
            raise ValueError("snapshot descriptor changed")
        if whole.hexdigest() != capture.get("snapshot_sha256") or before.st_size != capture.get("snapshot_bytes"):
            raise ValueError("snapshot hash/size")
    return {
        "schema": "pulsarmlx.selected-snapshot-byte-verification/1",
        "status": "PASS",
        "snapshot_sha256": whole.hexdigest(),
        "snapshot_bytes_read": before.st_size,
        "selected_payload_bytes_verified": total_payload,
        "selected_range_sha256": actual_hashes,
        "metadata_snapshot_sha256": plan["metadata_snapshot_sha256"],
        "original_checkpoint_bytes_read": 0,
        "native_calls": 0,
        "scope": "selected snapshot framing and byte/hash custody only; no R1 or numerical admission",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--capture-receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.snapshot, bounded_receipt(args.capture_receipt)), indent=2))


if __name__ == "__main__":
    main()

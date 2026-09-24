#!/usr/bin/env python3
"""Copy the *headers* of a Safetensors checkpoint, and provably nothing else.

A header-only metadata census needs, per shard, the 8-byte length prefix and
the ``N`` header bytes it declares -- never a payload byte. This tool reads
exactly that, and proves it read exactly that:

* every shard is opened ``O_RDONLY | O_NOFOLLOW`` and must be a regular file;
* every read goes through :class:`BoundedReader`, which reads by absolute
  offset (``os.pread``: no seek, no shared file position) under a ceiling. The
  ceiling starts at 8, is raised to ``8 + N`` only after ``N`` has been parsed
  and checked against the bound (``N <= 100 MiB``, ``8 + N <= file size``),
  and a read that would end past it raises :class:`BoundViolation` *before*
  any system call is made;
* every read is logged, and after each shard the log must show a maximum read
  end of exactly ``8 + N``, ``8 + N`` bytes read in total, and a file position
  still at 0 (no ``read()`` ever advanced it). Anything else aborts the run.

It also copies a fixed list of small JSON files (bounded, parsed as JSON),
records every top-level directory entry's type and ``lstat`` size, and names --
without opening -- the entries of any subdirectory. Nothing is imported or
executed from the checkpoint directory, and no output names the directory's
own path.

Output (the directory must not exist yet)::

    <out>/headers/<shard>.header        8 + N bytes, verbatim
    <out>/headers/<shard>.header.json   sidecar: file size, N, sha256 of the header bytes
    <out>/shards.json                   the shard list in the census input format
    <out>/extract-log.json              the per-shard read log and max offsets
    <out>/listing.json                  directory entries, types, sizes
    <out>/<name>.json                   each small JSON file that exists

The sha256 recorded is of the **header bytes only**. It identifies a header; it
says nothing about the payload.

Standard library only. Runs under Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys

SCHEMA = "pulsarmlx.f020.safetensors-header-extract/1.0.0"
PREFIX_BYTES = 8
MAX_HEADER_BYTES = 100 * 1024 * 1024
MAX_SMALL_JSON_BYTES = 64 * 1024 * 1024
SHARD_SUFFIX = ".safetensors"
SMALL_JSON_NAMES = (
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json",
    "download-record.json",
    "tokenizer_config.json",
)
LABEL = (
    "header bytes only; no payload byte read; header sha256 identifies the "
    "header, not the payload; not Q0"
)


class BoundViolation(RuntimeError):
    """A read would have gone past the bytes this tool is allowed to read."""


class ExtractionError(RuntimeError):
    """The checkpoint is not something this tool will extract from."""


class BoundedReader:
    """Absolute-offset reads under a ceiling, with a complete read log.

    The ceiling only ever rises, and only to a value the caller has checked.
    A request is refused before any system call if it would end past the
    ceiling, so a refused read reads nothing.
    """

    def __init__(self, fd: int, ceiling: int) -> None:
        self._fd = fd
        self.ceiling = ceiling
        self.max_end = 0
        self.bytes_read = 0
        self.reads: list[list[int]] = []

    def raise_ceiling(self, ceiling: int) -> None:
        if ceiling < self.ceiling:
            raise BoundViolation("the read ceiling may only rise")
        if ceiling > PREFIX_BYTES + MAX_HEADER_BYTES:
            raise BoundViolation(
                f"ceiling {ceiling} exceeds the prefix plus the header bound"
            )
        self.ceiling = ceiling

    def pread_exact(self, length: int, offset: int) -> bytes:
        if length < 0 or offset < 0:
            raise BoundViolation(f"negative read request ({length} at {offset})")
        end = offset + length
        if end > self.ceiling:
            raise BoundViolation(
                f"read [{offset}, {end}) would pass the ceiling {self.ceiling}"
            )
        chunks = []
        at = offset
        while at < end:
            chunk = os.pread(self._fd, end - at, at)
            if not chunk:
                raise ExtractionError(f"premature end of file at {at}, wanted {end}")
            chunks.append(chunk)
            at += len(chunk)
        data = b"".join(chunks)
        if len(data) != length:
            raise BoundViolation(f"read returned {len(data)} bytes, wanted {length}")
        self.reads.append([offset, length])
        self.bytes_read += length
        self.max_end = max(self.max_end, end)
        return data


def _open_regular(path: str) -> tuple[int, int]:
    """Open without following a symlink; return (fd, size) of a regular file."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise ExtractionError(f"cannot open {os.path.basename(path)}: {error}") from error
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ExtractionError(f"{os.path.basename(path)} is not a regular file")
    return fd, info.st_size


def extract_shard_header(path: str) -> tuple[bytes, dict]:
    """Read one shard's prefix and header; return (bytes, read record)."""
    name = os.path.basename(path)
    fd, file_len = _open_regular(path)
    try:
        if file_len < PREFIX_BYTES:
            raise ExtractionError(f"{name}: {file_len} bytes cannot hold the prefix")
        reader = BoundedReader(fd, PREFIX_BYTES)
        prefix = reader.pread_exact(PREFIX_BYTES, 0)
        header_len = int.from_bytes(prefix, "little")
        if header_len > MAX_HEADER_BYTES:
            raise ExtractionError(
                f"{name}: declared header length {header_len} exceeds "
                f"{MAX_HEADER_BYTES}; refused before reading it"
            )
        limit = PREFIX_BYTES + header_len
        if limit > file_len:
            raise ExtractionError(
                f"{name}: prefix and header need {limit} bytes, the file holds {file_len}"
            )
        reader.raise_ceiling(limit)
        header = reader.pread_exact(header_len, PREFIX_BYTES)
        position = os.lseek(fd, 0, os.SEEK_CUR)
    finally:
        os.close(fd)

    data = prefix + header
    # The proof, checked rather than asserted: the furthest byte touched is the
    # last header byte, exactly 8 + N bytes were read, and the file position
    # never moved, so no read() outside the reader happened on this descriptor.
    if reader.max_end != limit or reader.bytes_read != limit or len(data) != limit:
        raise BoundViolation(
            f"{name}: read log max end {reader.max_end}, bytes {reader.bytes_read}, "
            f"expected exactly {limit}"
        )
    if position != 0:
        raise BoundViolation(f"{name}: file position moved to {position}")
    record = {
        "file": name,
        "file_len": file_len,
        "header_len": header_len,
        "header_bytes": limit,
        "read_ceiling": reader.ceiling,
        "max_read_offset_exclusive": reader.max_end,
        "bytes_read": reader.bytes_read,
        "reads": reader.reads,
        "file_position_after": position,
        "payload_bytes_read": max(0, reader.max_end - limit),
        "within_bound": reader.max_end <= limit,
    }
    return data, record


def _read_small_json(path: str) -> bytes:
    fd, size = _open_regular(path)
    try:
        if size > MAX_SMALL_JSON_BYTES:
            raise ExtractionError(
                f"{os.path.basename(path)} is {size} bytes, above {MAX_SMALL_JSON_BYTES}"
            )
        reader = BoundedReader(fd, size)
        data = reader.pread_exact(size, 0)
    finally:
        os.close(fd)
    json.loads(data.decode("utf-8"))
    return data


def _entry_type(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def list_directory(root: str) -> list[dict]:
    """Every top-level entry with its lstat size; subdirectories by name only."""
    entries = []
    for name in sorted(os.listdir(root)):
        info = os.lstat(os.path.join(root, name))
        entry = {"name": name, "type": _entry_type(info.st_mode), "size": info.st_size}
        if stat.S_ISDIR(info.st_mode):
            children = []
            for child in sorted(os.listdir(os.path.join(root, name))):
                child_info = os.lstat(os.path.join(root, name, child))
                children.append({
                    "name": child,
                    "type": _entry_type(child_info.st_mode),
                    "size": child_info.st_size,
                })
            entry["children"] = children
        entries.append(entry)
    return entries


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: str, value: object) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def extract(checkpoint: str, output: str) -> dict:
    if not os.path.isdir(checkpoint):
        raise ExtractionError("the checkpoint is not a directory")
    if os.path.lexists(output):
        raise ExtractionError("the output directory already exists")
    listing = list_directory(checkpoint)
    shard_names = [
        entry["name"] for entry in listing
        if entry["name"].endswith(SHARD_SUFFIX) and entry["type"] == "file"
    ]
    refused = [
        entry["name"] for entry in listing
        if entry["name"].endswith(SHARD_SUFFIX) and entry["type"] != "file"
    ]
    if refused:
        raise ExtractionError(f"shard names that are not regular files: {refused}")
    if not shard_names:
        raise ExtractionError("no *.safetensors files")

    os.makedirs(os.path.join(output, "headers"))
    shards = []
    log = []
    for name in shard_names:
        data, record = extract_shard_header(os.path.join(checkpoint, name))
        digest = _sha256(data)
        record["header_sha256"] = digest
        header_file = f"headers/{name}.header"
        with open(os.path.join(output, header_file), "wb") as handle:
            handle.write(data)
        _write_json(os.path.join(output, header_file + ".json"), {
            "schema": SCHEMA,
            "label": LABEL,
            "file": name,
            "file_len": record["file_len"],
            "header_len": record["header_len"],
            "header_bytes": record["header_bytes"],
            "header_sha256": digest,
            "max_read_offset_exclusive": record["max_read_offset_exclusive"],
        })
        shards.append({
            "file": name,
            "file_len": record["file_len"],
            "header_file": header_file,
            "header_len": record["header_len"],
            "header_sha256": digest,
        })
        log.append(record)

    small = {}
    for name in SMALL_JSON_NAMES:
        path = os.path.join(checkpoint, name)
        if not os.path.lexists(path):
            small[name] = {"present": False}
            continue
        data = _read_small_json(path)
        with open(os.path.join(output, name), "wb") as handle:
            handle.write(data)
        small[name] = {"present": True, "size": len(data), "sha256": _sha256(data)}

    _write_json(os.path.join(output, "shards.json"), {"schema": SCHEMA, "shards": shards})
    _write_json(os.path.join(output, "listing.json"), {"schema": SCHEMA, "entries": listing})
    summary = {
        "schema": SCHEMA,
        "label": LABEL,
        "bound": {
            "prefix_bytes": PREFIX_BYTES,
            "max_header_bytes": MAX_HEADER_BYTES,
            "rule": "per shard, no read ends past 8 + N",
        },
        "shard_count": len(log),
        "shards": log,
        "small_json": small,
        "totals": {
            "header_bytes_read": sum(record["bytes_read"] for record in log),
            "payload_bytes_read": sum(record["payload_bytes_read"] for record in log),
            "shards_within_bound": sum(1 for record in log if record["within_bound"]),
            "full_shard_hashes": 0,
            "downloads": 0,
        },
    }
    _write_json(os.path.join(output, "extract-log.json"), summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--checkpoint", required=True, help="checkpoint directory")
    parser.add_argument("--output", required=True, help="new output directory")
    arguments = parser.parse_args(argv)
    try:
        summary = extract(arguments.checkpoint, arguments.output)
    except (ExtractionError, BoundViolation) as error:
        print(f"extract_safetensors_headers_v1: refused: {error}", file=sys.stderr)
        return 1
    totals = summary["totals"]
    print(
        f"extract_safetensors_headers_v1: {summary['shard_count']} shards, "
        f"{totals['header_bytes_read']} header bytes, "
        f"{totals['payload_bytes_read']} payload bytes, "
        f"{totals['shards_within_bound']} within bound"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

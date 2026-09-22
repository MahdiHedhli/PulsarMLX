#!/usr/bin/env python3
"""Read a GGUF file's header metadata without loading any tensor payload.

A split GGUF keeps its whole key/value block in the first shard, so this reads
the architecture, geometry and tokenizer of a multi-hundred-gigabyte
checkpoint from a few megabytes. It is a gate to run before acquiring the
rest: a wrong architecture or an unexpected geometry should be found here,
not after a download.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

UINT8, INT8, UINT16, INT16, UINT32, INT32, FLOAT32, BOOL, STRING, ARRAY, UINT64, INT64, FLOAT64 = range(13)
_FIXED = {
    UINT8: ("<B", 1), INT8: ("<b", 1), UINT16: ("<H", 2), INT16: ("<h", 2),
    UINT32: ("<I", 4), INT32: ("<i", 4), FLOAT32: ("<f", 4), BOOL: ("<B", 1),
    UINT64: ("<Q", 8), INT64: ("<q", 8), FLOAT64: ("<d", 8),
}


class Reader:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.offset = 0

    def take(self, count: int) -> bytes:
        if self.offset + count > len(self.raw):
            raise ValueError("truncated GGUF header")
        chunk = self.raw[self.offset:self.offset + count]
        self.offset += count
        return chunk

    def scalar(self, kind: int):
        if kind == STRING:
            length = struct.unpack("<Q", self.take(8))[0]
            return self.take(length).decode("utf-8", "replace")
        fmt, size = _FIXED[kind]
        value = struct.unpack(fmt, self.take(size))[0]
        return bool(value) if kind == BOOL else value

    def value(self, kind: int, array_cap: int):
        if kind != ARRAY:
            return self.scalar(kind)
        element, count = struct.unpack("<IQ", self.take(12))
        if element == STRING:
            out = []
            for index in range(count):
                length = struct.unpack("<Q", self.take(8))[0]
                text = self.take(length)
                if index < array_cap:
                    out.append(text.decode("utf-8", "replace"))
            return {"array_of": "string", "count": count, "first": out}
        fmt, size = _FIXED[element]
        out = []
        for index in range(count):
            chunk = self.take(size)
            if index < array_cap:
                out.append(struct.unpack(fmt, chunk)[0])
        return {"array_of": element, "count": count, "first": out}


def read(path: Path, array_cap: int = 8) -> dict:
    raw = path.read_bytes()
    if raw[:4] != b"GGUF":
        raise ValueError("not a GGUF file")
    version, tensor_count, kv_count = struct.unpack("<IQQ", raw[4:24])
    reader = Reader(raw)
    reader.offset = 24
    metadata = {}
    for _ in range(kv_count):
        key_length = struct.unpack("<Q", reader.take(8))[0]
        key = reader.take(key_length).decode("utf-8", "replace")
        kind = struct.unpack("<I", reader.take(4))[0]
        metadata[key] = reader.value(kind, array_cap)
    return {
        "file": str(path),
        "gguf_version": version,
        "tensor_count_in_this_shard": tensor_count,
        "metadata_key_count": kv_count,
        "metadata": metadata,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--array-cap", type=int, default=8,
                        help="how many elements of an array value to show")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    document = read(arguments.file, arguments.array_cap)
    raw = json.dumps(document, indent=1, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(raw)
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

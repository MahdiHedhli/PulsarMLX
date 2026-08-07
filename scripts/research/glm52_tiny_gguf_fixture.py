#!/usr/bin/env python3
"""Build tiny multi-shard GGUF fixtures for CI (not real model weights)."""

from __future__ import annotations

import struct
from pathlib import Path


def _write_string(buf: bytearray, s: str) -> None:
    b = s.encode("utf-8")
    buf += struct.pack("<Q", len(b))
    buf += b


def _write_kv_u32(buf: bytearray, key: str, val: int) -> None:
    _write_string(buf, key)
    buf += struct.pack("<I", 4)  # uint32 type
    buf += struct.pack("<I", val)


def _write_kv_string(buf: bytearray, key: str, val: str) -> None:
    _write_string(buf, key)
    buf += struct.pack("<I", 8)  # string
    _write_string(buf, val)


def write_minimal_gguf(
    path: Path,
    *,
    arch: str = "glm-dsa",
    n_tensors: int = 0,
    tensor_specs: list[tuple[str, list[int], int, bytes]] | None = None,
) -> None:
    """Write a minimal GGUF v3 file.

    tensor_specs: list of (name, dims, type_id, payload_bytes)
    """
    tensor_specs = tensor_specs or []
    assert n_tensors == len(tensor_specs) or n_tensors == 0
    n_tensors = len(tensor_specs)

    # KV: architecture + block_count
    kv = bytearray()
    _write_kv_string(kv, "general.architecture", arch)
    _write_kv_u32(kv, f"{arch}.block_count", 2)
    _write_kv_u32(kv, f"{arch}.embedding_length", 64)
    n_kv = 3

    # Tensor infos
    infos = bytearray()
    # We'll assign relative offsets after alignment
    payloads = []
    rel = 0
    for name, dims, ttype, payload in tensor_specs:
        _write_string(infos, name)
        infos += struct.pack("<I", len(dims))
        for d in dims:
            infos += struct.pack("<Q", d)
        infos += struct.pack("<I", ttype)
        infos += struct.pack("<Q", rel)
        payloads.append(payload)
        # align payload to 32
        rel += len(payload)
        pad = (32 - (rel % 32)) % 32
        rel += pad

    header = bytearray()
    header += b"GGUF"
    header += struct.pack("<I", 3)  # version
    header += struct.pack("<Q", n_tensors)
    header += struct.pack("<Q", n_kv)
    header += kv
    header += infos

    # align data section to 32
    pos = len(header)
    pad0 = (32 - (pos % 32)) % 32
    header += b"\x00" * pad0

    data = bytearray()
    for payload in payloads:
        data += payload
        pad = (32 - (len(payload) % 32)) % 32
        data += b"\x00" * pad

    path.write_bytes(bytes(header + data))


def build_two_shard_fixture(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    # shard A: metadata-only style + one F32 vector
    p1 = root / "toy-00001-of-00002.gguf"
    vec = struct.pack("<4f", 1.0, 2.0, 3.0, 4.0)
    write_minimal_gguf(
        p1,
        tensor_specs=[("toy.weight", [4], 0, vec)],
    )
    # shard B: second tensor
    p2 = root / "toy-00002-of-00002.gguf"
    vec2 = struct.pack("<4f", 5.0, 6.0, 7.0, 8.0)
    write_minimal_gguf(
        p2,
        tensor_specs=[("toy.bias", [4], 0, vec2)],
    )
    return [p1, p2]

#!/usr/bin/env python3
"""Multi-shard GGUF tensor store for GLM-5.2 (mmap / positional reads).

Builds a name→(file, abs_offset, nbytes, type, dims) index from all shards.
Supports bounded reads without loading the full model.
"""

from __future__ import annotations

import json
import mmap
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from glm52_gguf_catalog import discover_ggufs, parse_header, TENSOR_TYPE

# nbytes helpers for common types (row-agnostic element sizes / block layouts)
QK_K = 256


def nbytes_for_tensor(ttype: int, n_elem: int) -> int:
    """Encoded byte length for n_elem elements of ggml type ttype."""
    # mirror ggml_row_size / type traits for types we expect
    if ttype == 0:  # F32
        return n_elem * 4
    if ttype == 1:  # F16
        return n_elem * 2
    if ttype == 8:  # Q8_0
        # 32 elems → 34 bytes
        assert n_elem % 32 == 0
        return (n_elem // 32) * 34
    if ttype == 16:  # IQ2_XXS
        assert n_elem % QK_K == 0
        return (n_elem // QK_K) * 66
    if ttype == 10:  # Q2_K
        assert n_elem % QK_K == 0
        return (n_elem // QK_K) * 84
    if ttype == 12:  # Q4_K
        assert n_elem % QK_K == 0
        return (n_elem // QK_K) * 144
    if ttype == 14:  # Q6_K
        assert n_elem % QK_K == 0
        return (n_elem // QK_K) * 210
    if ttype == 17:  # IQ2_XS
        assert n_elem % QK_K == 0
        return (n_elem // QK_K) * 66  # verify if needed
    # fallback: refuse unknown
    raise ValueError(f"unsupported tensor type {ttype} for nbytes")


@dataclass
class TensorLoc:
    name: str
    file: Path
    offset: int
    n_bytes: int
    type_id: int
    type_name: str
    dims: list[int]

    @property
    def n_elem(self) -> int:
        n = 1
        for d in self.dims:
            n *= d
        return n


class Glm52TensorStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tensors: dict[str, TensorLoc] = {}
        self.kv: dict[str, Any] = {}
        self.shards: list[dict[str, Any]] = []
        self._mmaps: dict[Path, mmap.mmap] = {}
        self._files: dict[Path, Any] = {}
        self._build_index()

    def _build_index(self) -> None:
        paths = discover_ggufs(self.root)
        if not paths:
            raise FileNotFoundError(f"no gguf under {self.root}")
        for path in paths:
            h = parse_header(path)
            self.shards.append(
                {
                    "file": path.name,
                    "size": h["file_size_bytes"],
                    "n_tensors": h["n_tensors"],
                }
            )
            for k, v in h["kv"].items():
                if k not in self.kv:
                    self.kv[k] = v
            for t in h["tensors"]:
                dims = [int(x) for x in t["dims"]]
                n_elem = 1
                for d in dims:
                    n_elem *= d
                try:
                    nb = nbytes_for_tensor(t["type_id"], n_elem)
                except ValueError:
                    # still index with unknown nbytes = 0 marker
                    nb = 0
                loc = TensorLoc(
                    name=t["name"],
                    file=path,
                    offset=int(t["data_offset_abs"]),
                    n_bytes=nb,
                    type_id=t["type_id"],
                    type_name=t["type"],
                    dims=dims,
                )
                if t["name"] in self.tensors:
                    raise ValueError(f"duplicate tensor {t['name']}")
                self.tensors[t["name"]] = loc

    def close(self) -> None:
        for m in self._mmaps.values():
            m.close()
        for f in self._files.values():
            f.close()
        self._mmaps.clear()
        self._files.clear()

    def _mmap(self, path: Path) -> mmap.mmap:
        if path not in self._mmaps:
            f = path.open("rb")
            self._files[path] = f
            self._mmaps[path] = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        return self._mmaps[path]

    def read_bytes(self, name: str) -> bytes:
        loc = self.tensors[name]
        if loc.n_bytes <= 0:
            raise ValueError(f"unknown encoded size for {name} type={loc.type_name}")
        mm = self._mmap(loc.file)
        return bytes(mm[loc.offset : loc.offset + loc.n_bytes])

    def pread(self, name: str, rel: int, n: int) -> bytes:
        loc = self.tensors[name]
        mm = self._mmap(loc.file)
        start = loc.offset + rel
        return bytes(mm[start : start + n])

    def arch(self) -> str | None:
        return self.kv.get("general.architecture")

    def meta(self, suffix: str) -> Any:
        a = self.arch()
        if not a:
            return None
        return self.kv.get(f"{a}.{suffix}")

    def summary(self) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        for t in self.tensors.values():
            type_counts[t.type_name] = type_counts.get(t.type_name, 0) + 1
        return {
            "architecture": self.arch(),
            "shard_count": len(self.shards),
            "tensor_count": len(self.tensors),
            "type_counts": type_counts,
            "block_count": self.meta("block_count"),
            "expert_count": self.meta("expert_count"),
            "embedding_length": self.meta("embedding_length"),
        }


def main() -> None:
    import argparse
    import os

    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, default=os.environ.get("PULSARMLX_GLM_GGUF"))
    args = p.parse_args()
    if not args.model:
        raise SystemExit("set --model or PULSARMLX_GLM_GGUF")
    store = Glm52TensorStore(Path(args.model))
    print(json.dumps(store.summary(), indent=2, sort_keys=True))
    store.close()


if __name__ == "__main__":
    main()

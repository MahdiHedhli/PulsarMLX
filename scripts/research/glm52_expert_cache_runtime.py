#!/usr/bin/env python3
"""Bounded expert dequant cache for GLM inference path.

Caches full expert slabs (gate/up/down rows as f32) under a byte budget.
Deterministic LRU by expert key. Used by inference mode; research path
may remain uncached.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from glm52_expert import expert_matvec
from glm52_tensor_store import Glm52TensorStore


@dataclass
class ExpertCacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    bytes_resident: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "bytes_resident": self.bytes_resident,
            "hit_rate": self.hits / max(1, self.hits + self.misses),
        }


@dataclass
class ExpertSlabCache:
    """LRU cache of decoded expert matrix rows for matvec reuse."""

    max_bytes: int = 2 * 1024**3  # 2 GiB default decoded
    stats: ExpertCacheStats = field(default_factory=ExpertCacheStats)
    _lru: OrderedDict[str, list[list[float]]] = field(default_factory=OrderedDict)
    _sizes: dict[str, int] = field(default_factory=dict)

    def _key(self, name: str, expert: int) -> str:
        return f"{name}#{expert}"

    def clear(self) -> None:
        self._lru.clear()
        self._sizes.clear()
        self.stats = ExpertCacheStats()

    def get_or_load_rows(
        self,
        store: Glm52TensorStore,
        name: str,
        expert: int,
    ) -> list[list[float]]:
        """Return list of dequantized rows for y = W @ x matvec."""
        from glm52_tensor_store import nbytes_for_tensor
        from glm52_dense_primitives import dequant_row
        from glm52_expert import _dequant_row_bytes

        k = self._key(name, expert)
        if k in self._lru:
            self._lru.move_to_end(k)
            self.stats.hits += 1
            return self._lru[k]

        self.stats.misses += 1
        loc = store.tensors[name]
        if len(loc.dims) == 2:
            cols, rows = int(loc.dims[0]), int(loc.dims[1])
            mat = [dequant_row(store, loc, r) for r in range(rows)]
        elif len(loc.dims) == 3:
            cols, rows, n_exp = int(loc.dims[0]), int(loc.dims[1]), int(loc.dims[2])
            if expert < 0 or expert >= n_exp:
                raise IndexError(expert)
            rb = nbytes_for_tensor(loc.type_id, cols)
            expert_bytes = rb * rows
            base = expert * expert_bytes
            mat = []
            for r in range(rows):
                raw = store.pread(name, base + r * rb, rb)
                mat.append(_dequant_row_bytes(loc.type_id, raw, cols))
        else:
            raise ValueError(name)

        nbytes = sum(len(r) for r in mat) * 4
        while self.stats.bytes_resident + nbytes > self.max_bytes and self._lru:
            old_k, _ = self._lru.popitem(last=False)
            old_n = self._sizes.pop(old_k, 0)
            self.stats.bytes_resident -= old_n
            self.stats.evictions += 1
        if nbytes <= self.max_bytes:
            self._lru[k] = mat
            self._sizes[k] = nbytes
            self.stats.bytes_resident += nbytes
        return mat


def matvec_cached_rows(rows: list[list[float]], x: list[float]) -> list[float]:
    return [sum(a * b for a, b in zip(row, x, strict=True)) for row in rows]


def expert_matvec_cached(
    store: Glm52TensorStore,
    cache: ExpertSlabCache,
    name: str,
    expert: int,
    x: list[float],
) -> list[float]:
    rows = cache.get_or_load_rows(store, name, expert)
    if len(rows[0]) != len(x):
        # fall back
        return expert_matvec(store, name, expert, x)
    try:
        import mlx.core as mx

        # rows as matrix
        flat = [v for row in rows for v in row]
        w = mx.array(flat, dtype=mx.float32).reshape((len(rows), len(x)))
        y = w @ mx.array(x, dtype=mx.float32)
        mx.eval(y)
        return y.tolist()
    except Exception:
        return matvec_cached_rows(rows, x)

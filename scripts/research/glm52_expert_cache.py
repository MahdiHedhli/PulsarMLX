#!/usr/bin/env python3
"""Bounded expert cache skeleton (checkpoint-independent).

Deterministic LRU-with-admission budget for compressed expert slabs.
Uses a FakeExpertStore for CI; real store plugs in GGUF positional reads later.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ExpertKey:
    layer: int
    expert: int
    kind: str  # gate | up | down | shexp_gate | ...

    def __str__(self) -> str:
        return f"L{self.layer}:{self.kind}:e{self.expert}"


@dataclass
class ExpertSlab:
    key: ExpertKey
    offset: int
    length: int
    payload: bytes
    compressed_bytes: int


class ExpertStore(Protocol):
    def read_slab(self, key: ExpertKey, offset: int, length: int) -> bytes: ...


class FakeExpertStore:
    """Synthetic store: payload = deterministic bytes from key+offset."""

    def __init__(self) -> None:
        self.reads: list[tuple[ExpertKey, int, int]] = []
        self.fail_keys: set[ExpertKey] = set()

    def read_slab(self, key: ExpertKey, offset: int, length: int) -> bytes:
        if key in self.fail_keys:
            raise OSError(f"fake read fail {key}")
        if offset < 0 or length < 0:
            raise ValueError("negative offset/length")
        self.reads.append((key, offset, length))
        # deterministic payload
        seed = f"{key}|{offset}|{length}".encode()
        return (seed * ((length // len(seed)) + 1))[:length]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    bytes_read: int = 0
    read_duration_s: float = 0.0
    duplicate_suppressed: int = 0
    admission_rejections: int = 0

    def as_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "bytes_read": self.bytes_read,
            "read_duration_s": self.read_duration_s,
            "duplicate_suppressed": self.duplicate_suppressed,
            "admission_rejections": self.admission_rejections,
            "resident_entries": None,  # filled by cache
            "resident_compressed_bytes": None,
        }


class ExpertCache:
    """Thread-safe deterministic LRU expert slab cache."""

    def __init__(
        self,
        store: ExpertStore,
        budget_compressed_bytes: int,
        max_in_flight: int = 8,
    ) -> None:
        if budget_compressed_bytes < 0:
            raise ValueError("budget must be non-negative")
        self.store = store
        self.budget = budget_compressed_bytes
        self.max_in_flight = max_in_flight
        self._lru: OrderedDict[ExpertKey, ExpertSlab] = OrderedDict()
        self._resident_bytes = 0
        self.stats = CacheStats()
        self._lock = threading.RLock()
        self._in_flight: dict[ExpertKey, threading.Event] = {}
        self._in_flight_results: dict[ExpertKey, ExpertSlab | BaseException] = {}

    def resident_bytes(self) -> int:
        with self._lock:
            return self._resident_bytes

    def entries(self) -> int:
        with self._lock:
            return len(self._lru)

    def stats_dict(self) -> dict:
        d = self.stats.as_dict()
        d["resident_entries"] = self.entries()
        d["resident_compressed_bytes"] = self.resident_bytes()
        return d

    def get(self, key: ExpertKey, offset: int, length: int) -> ExpertSlab:
        if length < 0 or offset < 0:
            raise ValueError("offset/length")
        if length > self.budget and self.budget > 0:
            # single slab larger than budget: fail closed
            self.stats.admission_rejections += 1
            raise MemoryError(f"slab {length} exceeds budget {self.budget}")

        with self._lock:
            if key in self._lru:
                slab = self._lru.pop(key)
                if slab.offset != offset or slab.length != length:
                    # key reuse with different range — treat as miss after drop
                    self._resident_bytes -= slab.compressed_bytes
                else:
                    self._lru[key] = slab
                    self.stats.hits += 1
                    return slab
            # wait if another thread is fetching same key
            if key in self._in_flight:
                ev = self._in_flight[key]
                self.stats.duplicate_suppressed += 1
            else:
                if len(self._in_flight) >= self.max_in_flight:
                    raise RuntimeError("max in-flight expert reads exceeded")
                ev = threading.Event()
                self._in_flight[key] = ev
                ev = None  # we are the fetcher

        if ev is not None:
            ev.wait(timeout=60)
            with self._lock:
                res = self._in_flight_results.pop(key, None)
            if isinstance(res, BaseException):
                raise res
            if res is None:
                raise RuntimeError("in-flight result missing")
            return res

        # fetch
        t0 = time.perf_counter()
        try:
            payload = self.store.read_slab(key, offset, length)
            dt = time.perf_counter() - t0
            slab = ExpertSlab(
                key=key,
                offset=offset,
                length=length,
                payload=payload,
                compressed_bytes=len(payload),
            )
            with self._lock:
                self.stats.misses += 1
                self.stats.bytes_read += len(payload)
                self.stats.read_duration_s += dt
                self._admit(slab)
                self._in_flight_results[key] = slab
                fin = self._in_flight.pop(key, None)
                if fin:
                    fin.set()
            return slab
        except BaseException as e:
            with self._lock:
                self._in_flight_results[key] = e
                fin = self._in_flight.pop(key, None)
                if fin:
                    fin.set()
            raise

    def _admit(self, slab: ExpertSlab) -> None:
        # caller holds lock
        need = slab.compressed_bytes
        while self._resident_bytes + need > self.budget and self._lru:
            _, old = self._lru.popitem(last=False)
            self._resident_bytes -= old.compressed_bytes
            self.stats.evictions += 1
        if self._resident_bytes + need > self.budget:
            self.stats.admission_rejections += 1
            raise MemoryError("cannot admit slab within budget")
        if slab.key in self._lru:
            prev = self._lru.pop(slab.key)
            self._resident_bytes -= prev.compressed_bytes
        self._lru[slab.key] = slab
        self._resident_bytes += need

    def prefetch(self, key: ExpertKey, offset: int, length: int) -> None:
        """Best-effort prefetch; ignores if already resident."""
        with self._lock:
            if key in self._lru:
                return
        try:
            self.get(key, offset, length)
        except Exception:
            pass  # prefetch is best-effort unless fail-closed caller wants raise

    def cancel_inflight(self) -> int:
        """Mark in-flight as cancelled (tests); returns count cancelled."""
        with self._lock:
            n = len(self._in_flight)
            for k, ev in list(self._in_flight.items()):
                self._in_flight_results[k] = RuntimeError("prefetch cancelled")
                ev.set()
            self._in_flight.clear()
            return n


# Default profile (configurable, not a benchmark conclusion)
DEFAULT_EXPERT_CACHE_BYTES = 48 * 1024**3
DEFAULT_MIN_HEADROOM_BYTES = 24 * 1024**3
DEFAULT_STREAMED_LAYERS = 16

#!/usr/bin/env python3
"""Public-safe runtime telemetry for GLM research path."""

from __future__ import annotations

import os
import re
import resource
import time
from dataclasses import asdict, dataclass, field
from typing import Any


_PRIVATE_PATTERNS = [
    re.compile(r"(?i)username\s*[:=]"),
    re.compile(r"(?i)hostname\s*[:=]"),
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"(?i)serial[_\s-]?number"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"(?i)(api[_-]?key|token|bearer)\s*[:=]\s*\S+"),
    re.compile(r"https://huggingface\.co/[^?\s]+\?[^?\s]*X-Amz"),
]


def contains_private_leak(text: str) -> list[str]:
    hits = []
    for pat in _PRIVATE_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def assert_public_safe(obj: Any, path: str = "$") -> None:
    """Raise ValueError if serialized observation leaks private fields."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in {"username", "hostname", "home", "serial", "uuid", "ip", "password"}:
                raise ValueError(f"private key forbidden at {path}.{k}")
            # Model token IDs are public numerical evidence. Credential-like
            # strings under a generic `token` key remain forbidden.
            if kl == "token" and not isinstance(v, (int, float)):
                raise ValueError(f"private key forbidden at {path}.{k}")
            assert_public_safe(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            assert_public_safe(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        leaks = contains_private_leak(obj)
        if leaks:
            raise ValueError(f"private pattern in string at {path}: {leaks[0]}")


@dataclass
class RuntimeObservation:
    schema: str = "pulsarmlx.telemetry.runtime_observation"
    schema_version: str = "1.0.0"
    # public-safe roles only
    host_class: str = "apple_silicon_m1_ultra"
    storage_class: str = "internal_ssd"
    monotonic_s: float = 0.0
    process_rss_bytes: int | None = None
    process_peak_rss_bytes: int | None = None
    bytes_read: int = 0
    read_duration_s: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_evictions: int = 0
    resident_compressed_bytes: int = 0
    decoded_bytes: int = 0
    mapped_bytes: int = 0
    swap_bytes: int | None = None
    memory_pressure: str = "unknown"  # normal|warn|critical|unknown
    thermal_state: str = "unknown"  # nominal|fair|serious|critical|unknown
    extras: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        assert_public_safe(d)
        return d


def sample_process_rss_bytes() -> int | None:
    try:
        # ru_maxrss on macOS is bytes
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return None


def sample_swap_bytes() -> int | None:
    # best-effort; may be unavailable — leave None rather than private sysctl dump
    return None


def memory_pressure_category() -> str:
    # avoid shelling private host info; leave unknown unless env override for tests
    return os.environ.get("PULSARMLX_MEMORY_PRESSURE_FAKE", "unknown")


def thermal_category() -> str:
    return os.environ.get("PULSARMLX_THERMAL_FAKE", "unknown")


class TelemetryCollector:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.bytes_read = 0
        self.read_duration_s = 0.0
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_evictions = 0
        self.resident_compressed_bytes = 0
        self.decoded_bytes = 0
        self.mapped_bytes = 0

    def record_read(self, n: int, duration_s: float) -> None:
        self.bytes_read += n
        self.read_duration_s += duration_s

    def record_cache(self, stats: dict[str, Any]) -> None:
        self.cache_hits = int(stats.get("hits", 0))
        self.cache_misses = int(stats.get("misses", 0))
        self.cache_evictions = int(stats.get("evictions", 0))
        self.resident_compressed_bytes = int(stats.get("resident_compressed_bytes") or 0)

    def snapshot(self) -> RuntimeObservation:
        rss = sample_process_rss_bytes()
        obs = RuntimeObservation(
            monotonic_s=time.monotonic() - self.t0,
            process_rss_bytes=rss,
            process_peak_rss_bytes=rss,
            bytes_read=self.bytes_read,
            read_duration_s=self.read_duration_s,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            cache_evictions=self.cache_evictions,
            resident_compressed_bytes=self.resident_compressed_bytes,
            decoded_bytes=self.decoded_bytes,
            mapped_bytes=self.mapped_bytes,
            swap_bytes=sample_swap_bytes(),
            memory_pressure=memory_pressure_category(),
            thermal_state=thermal_category(),
        )
        return obs

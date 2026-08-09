#!/usr/bin/env python3
"""Public-safe memory pressure sampling (macOS-oriented).

Design adapted from ssd-llm memory_pressure concepts (MIT, Nicola Spieser);
reimplemented without vendoring that tree. No hostname/username.
"""

from __future__ import annotations

import os
import platform
import re
import resource
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class PressureSample:
    level: str  # normal|warning|critical|urgent|unknown
    budget_fraction: float
    allow_prefetch: bool
    rss_bytes: int | None
    peak_rss_bytes: int | None
    free_pages_approx: int | None
    system_free_percent: int | None
    process_cpu_user_seconds: float | None
    process_cpu_system_seconds: float | None
    notes: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "budget_fraction": self.budget_fraction,
            "allow_prefetch": self.allow_prefetch,
            "rss_bytes": self.rss_bytes,
            "peak_rss_bytes": self.peak_rss_bytes,
            "free_pages_approx": self.free_pages_approx,
            "system_free_percent": self.system_free_percent,
            "process_cpu_user_seconds": self.process_cpu_user_seconds,
            "process_cpu_system_seconds": self.process_cpu_system_seconds,
            "notes": self.notes,
            "platform": platform.system(),
        }


def sample_pressure() -> PressureSample:
    rss = None
    peak_rss = None
    cpu_user = None
    cpu_system = None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is bytes on macOS.
        peak_rss = int(usage.ru_maxrss)
        cpu_user = float(usage.ru_utime)
        cpu_system = float(usage.ru_stime)
    except Exception:
        pass
    try:
        # ps reports current resident size in KiB on macOS.
        rss_kib = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(os.getpid())],
            text=True,
            timeout=2,
        ).strip()
        rss = int(rss_kib) * 1024
        if peak_rss is not None:
            peak_rss = max(peak_rss, rss)
    except Exception:
        pass
    level = "unknown"
    free_pages = None
    free_percent = None
    notes = ""
    if platform.system() == "Darwin":
        try:
            pressure = subprocess.check_output(
                ["memory_pressure", "-Q"], text=True, timeout=2
            )
            match = re.search(
                r"System-wide memory free percentage:\s*(\d+)%", pressure
            )
            if match is not None:
                free_percent = int(match.group(1))
                if free_percent > 20:
                    level = "normal"
                elif free_percent > 10:
                    level = "warning"
                elif free_percent > 5:
                    level = "critical"
                else:
                    level = "urgent"
                notes = "memory_pressure_query"
        except Exception as exc:
            notes = f"memory_pressure_failed:{type(exc).__name__}"
        try:
            out = subprocess.check_output(["vm_stat"], text=True, timeout=2)
            for line in out.splitlines():
                if "Pages free" in line:
                    free_pages = int(line.split(":")[1].strip().rstrip("."))
        except Exception as exc:
            suffix = f"vm_stat_failed:{type(exc).__name__}"
            notes = f"{notes};{suffix}" if notes else suffix
    frac = {"normal": 1.0, "warning": 0.75, "critical": 0.5, "urgent": 0.25}.get(level, 1.0)
    allow = level in ("normal", "warning", "unknown")
    return PressureSample(
        level=level,
        budget_fraction=frac,
        allow_prefetch=allow,
        rss_bytes=rss,
        peak_rss_bytes=peak_rss,
        free_pages_approx=free_pages,
        system_free_percent=free_percent,
        process_cpu_user_seconds=cpu_user,
        process_cpu_system_seconds=cpu_system,
        notes=notes,
    )

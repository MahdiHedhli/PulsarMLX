#!/usr/bin/env python3
"""Public-safe memory pressure sampling (macOS-oriented).

Design adapted from ssd-llm memory_pressure concepts (MIT, Nicola Spieser);
reimplemented without vendoring that tree. No hostname/username.
"""

from __future__ import annotations

import platform
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
    free_pages_approx: int | None
    notes: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "budget_fraction": self.budget_fraction,
            "allow_prefetch": self.allow_prefetch,
            "rss_bytes": self.rss_bytes,
            "free_pages_approx": self.free_pages_approx,
            "notes": self.notes,
            "platform": platform.system(),
        }


def sample_pressure() -> PressureSample:
    rss = None
    try:
        # ru_maxrss on macOS is bytes
        rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        pass
    level = "unknown"
    free_pages = None
    notes = ""
    if platform.system() == "Darwin":
        try:
            out = subprocess.check_output(["vm_stat"], text=True, timeout=2)
            # pages free
            for line in out.splitlines():
                if "Pages free" in line:
                    free_pages = int(line.split(":")[1].strip().rstrip("."))
            # heuristic only — not Mach host_statistics64 full port
            if free_pages is not None:
                # 16k pages on Apple Silicon often
                free_mib = free_pages * 16 / 1024
                if free_mib > 8192:
                    level = "normal"
                elif free_mib > 4096:
                    level = "warning"
                elif free_mib > 1024:
                    level = "critical"
                else:
                    level = "urgent"
                notes = "vm_stat_heuristic"
        except Exception as exc:
            notes = f"vm_stat_failed:{type(exc).__name__}"
    frac = {"normal": 1.0, "warning": 0.75, "critical": 0.5, "urgent": 0.25}.get(level, 1.0)
    allow = level in ("normal", "warning", "unknown")
    return PressureSample(level, frac, allow, rss, free_pages, notes)

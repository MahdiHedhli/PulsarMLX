#!/usr/bin/env python3
"""Fail-closed memory gates for F017 V9 mint and package start."""
from __future__ import annotations

import time

from f017_macos_memory_observation_v1 import MemoryObservation, observe_vm_stat


THRESHOLD_BYTES = 17_179_869_184
MAX_AGE_NS = 60_000_000_000


def validate_observation(value: dict, *, now_ns: int | None = None, enforce: bool) -> dict:
    required = {"parser_version", "page_size_bytes", "pages_free", "pages_inactive", "pages_speculative",
                "pages_purgeable", "available_bytes", "canonical_observation", "stdout_sha256", "observed_at_unix_ns"}
    if type(value) is not dict or set(value) != required:
        raise ValueError("memory observation census")
    for key in ("page_size_bytes", "pages_free", "pages_inactive", "pages_speculative", "pages_purgeable", "available_bytes", "observed_at_unix_ns"):
        if type(value[key]) is not int or value[key] < 0:
            raise ValueError("memory observation type")
    now_ns = now_ns or time.time_ns(); age = now_ns - value["observed_at_unix_ns"]
    passed = 0 <= age <= MAX_AGE_NS and value["available_bytes"] >= THRESHOLD_BYTES
    if enforce and not passed:
        raise ValueError("required memory gate failed")
    return {"result": "PASS" if passed else "OBSERVED_BELOW_PRODUCTION_GATE", "enforced": enforce,
            "threshold_bytes": THRESHOLD_BYTES, "sample_age_ns": age, "observation": value}


def observe(*, enforce: bool) -> dict:
    observation: MemoryObservation = observe_vm_stat()
    return validate_observation(observation.as_dict(), enforce=enforce)

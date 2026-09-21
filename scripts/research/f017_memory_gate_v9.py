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


def prove_enforced_policy() -> dict:
    """Mechanically prove that production PASS, low-memory, and stale cases close correctly."""
    now = time.time_ns()
    base = {
        "parser_version": "F017_MEMORY_GATE_POLICY_PROBE_V1", "page_size_bytes": 16_384,
        "pages_free": 0, "pages_inactive": 0, "pages_speculative": 0, "pages_purgeable": 0,
        "available_bytes": THRESHOLD_BYTES, "canonical_observation": "POLICY_PROBE",
        "stdout_sha256": "0" * 64, "observed_at_unix_ns": now,
    }
    passed = validate_observation(base, now_ns=now, enforce=True)
    rejected = []
    for case, value, probe_now in (
        ("BELOW_THRESHOLD", {**base, "available_bytes": THRESHOLD_BYTES - 1}, now),
        ("STALE", {**base, "observed_at_unix_ns": now - MAX_AGE_NS - 1}, now),
    ):
        try:
            validate_observation(value, now_ns=probe_now, enforce=True)
        except ValueError:
            rejected.append(case)
        else:
            raise ValueError(f"memory gate policy mutation accepted: {case}")
    return {"result": "PASS", "production_pass_enforced": passed["enforced"],
            "rejected": rejected, "threshold_bytes": THRESHOLD_BYTES, "max_age_ns": MAX_AGE_NS}

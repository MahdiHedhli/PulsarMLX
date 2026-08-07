#!/usr/bin/env python3
"""Fail-closed execution mode for GLM research / performance path."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class FailClosedError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class ExecutionPolicy:
    require_mlx: bool = True
    allow_cpu_fallback: bool = False
    min_headroom_bytes: int = 24 * 1024**3
    max_materialized_bytes: int = 96 * 1024**3  # hard cap; not full 754B
    performance_mode: bool = False

    @classmethod
    def from_env(cls) -> "ExecutionPolicy":
        perf = os.environ.get("PULSARMLX_GLM_PERF_MODE", "0") == "1"
        return cls(
            require_mlx=True,
            allow_cpu_fallback=False if perf else os.environ.get("PULSARMLX_ALLOW_CPU", "0") == "1",
            performance_mode=perf,
        )


class ExecutionGuard:
    def __init__(self, policy: ExecutionPolicy | None = None) -> None:
        self.policy = policy or ExecutionPolicy.from_env()
        self.materialized_bytes = 0
        self.cpu_ops = 0
        self.mlx_ops = 0

    def check_mlx_available(self, mlx_ok: bool) -> None:
        if self.policy.require_mlx and not mlx_ok:
            raise FailClosedError("mlx_unavailable", "MLX device required; refusing run")

    def record_mlx(self) -> None:
        self.mlx_ops += 1

    def record_cpu(self, reason: str = "") -> None:
        self.cpu_ops += 1
        if self.policy.performance_mode or not self.policy.allow_cpu_fallback:
            raise FailClosedError(
                "silent_cpu_fallback_forbidden",
                f"CPU path used while fail-closed (reason={reason!r})",
            )

    def admit_materialization(self, n_bytes: int) -> None:
        if n_bytes < 0:
            raise FailClosedError("invalid_materialization", "negative bytes")
        if self.materialized_bytes + n_bytes > self.policy.max_materialized_bytes:
            raise FailClosedError(
                "full_model_materialization_blocked",
                f"would exceed max_materialized_bytes={self.policy.max_materialized_bytes}",
            )
        self.materialized_bytes += n_bytes

    def check_headroom(self, free_bytes: int) -> None:
        if free_bytes < self.policy.min_headroom_bytes:
            raise FailClosedError(
                "memory_headroom_exhausted",
                f"free_bytes={free_bytes} < min_headroom={self.policy.min_headroom_bytes}",
            )

    def check_tensor_type_supported(self, type_name: str, supported: set[str]) -> None:
        if type_name not in supported:
            raise FailClosedError(
                "unsupported_tensor_type",
                f"type {type_name} not in supported set",
            )

    def check_expert_range(self, offset: int, length: int, tensor_nbytes: int) -> None:
        if offset < 0 or length < 0 or offset + length > tensor_nbytes:
            raise FailClosedError(
                "expert_read_out_of_range",
                f"offset={offset} length={length} tensor_nbytes={tensor_nbytes}",
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "performance_mode": self.policy.performance_mode,
            "allow_cpu_fallback": self.policy.allow_cpu_fallback,
            "materialized_bytes": self.materialized_bytes,
            "mlx_ops": self.mlx_ops,
            "cpu_ops": self.cpu_ops,
            "min_headroom_bytes": self.policy.min_headroom_bytes,
            "max_materialized_bytes": self.policy.max_materialized_bytes,
        }

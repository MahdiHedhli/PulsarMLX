#!/usr/bin/env python3
"""Compact, bounded decoded expert residency for GLM inference mode.

The policy protects only shared-expert matrices because their cross-token reuse
is architecture-guaranteed. Routed experts bypass this tier until measured
routing history justifies another policy. The production backend is MLX-only
and propagates every backend failure; no CPU fallback exists here.
"""

from __future__ import annotations

import gc
import time
from array import array
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Protocol

from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor


@dataclass(frozen=True)
class LoadMetrics:
    storage_bytes_read: int
    storage_read_count: int
    storage_read_seconds: float
    dequant_seconds: float
    contiguous_buffer_seconds: float
    matrix_build_seconds: float
    matrix_construct_seconds: float = 0.0
    matrix_eval_seconds: float = 0.0


@dataclass(frozen=True)
class DecodedMatrix:
    value: Any
    rows: int
    cols: int
    decoded_bytes: int
    compressed_bytes: int
    quantization: str
    decoder_mode: str


class MatrixBackend(Protocol):
    def load(
        self, store: Glm52TensorStore, name: str, expert: int
    ) -> tuple[DecodedMatrix, LoadMetrics]: ...

    def matvec(
        self, matrix: DecodedMatrix, x: list[float]
    ) -> tuple[list[float], float]: ...

    def identity(self) -> dict[str, str]: ...

    def release_transient(self) -> None: ...


class MlxMatrixBackend:
    """Decode into compact f32 storage and retain an evaluated MLX matrix."""

    DECODER_MODES = ("scalar_reference", "numpy_vectorized")

    def __init__(self, decoder_mode: str = "scalar_reference") -> None:
        if decoder_mode not in self.DECODER_MODES:
            raise ValueError(f"unsupported decoder mode {decoder_mode}")
        import mlx.core as mx

        self.mx = mx
        self.decoder_mode = decoder_mode

    def identity(self) -> dict[str, str]:
        try:
            from importlib.metadata import version

            mlx_version = version("mlx")
        except Exception:
            mlx_version = "unknown"
        return {
            "backend": "mlx",
            "device": str(self.mx.default_device()),
            "mlx_version": mlx_version,
            "decoder_mode": self.decoder_mode,
        }

    def load(
        self, store: Glm52TensorStore, name: str, expert: int
    ) -> tuple[DecodedMatrix, LoadMetrics]:
        from glm52_expert import _dequant_row_bytes

        loc = store.tensors[name]
        if len(loc.dims) not in (2, 3):
            raise ValueError(f"{name}: expected 2D or 3D expert tensor")
        cols, rows = int(loc.dims[0]), int(loc.dims[1])
        if len(loc.dims) == 3:
            n_expert = int(loc.dims[2])
            if not 0 <= expert < n_expert:
                raise IndexError(expert)
        elif expert != 0:
            raise IndexError(f"{name}: shared expert index must be zero")

        row_bytes = nbytes_for_tensor(loc.type_id, cols)
        compressed_bytes = row_bytes * rows
        base = expert * compressed_bytes if len(loc.dims) == 3 else 0
        read_seconds = 0.0
        dequant_seconds = 0.0
        contiguous_buffer_seconds = 0.0
        vector_decoder = None
        if self.decoder_mode == "numpy_vectorized" and loc.type_id == 16:
            from iq2_xxs_dequant import dequantize_matrix_iq2_xxs_numpy

            vector_decoder = dequantize_matrix_iq2_xxs_numpy
        elif self.decoder_mode == "numpy_vectorized" and loc.type_id == 18:
            from iq3_xxs_dequant import dequantize_matrix_iq3_xxs_numpy

            vector_decoder = dequantize_matrix_iq3_xxs_numpy
        elif self.decoder_mode == "numpy_vectorized" and loc.type_id == 10:
            from ggml_kquants import dequantize_matrix_q2_k_numpy

            vector_decoder = dequantize_matrix_q2_k_numpy

        if vector_decoder is not None:

            read_start = time.perf_counter()
            raw = store.pread(name, base, compressed_bytes)
            read_seconds = time.perf_counter() - read_start
            if len(raw) != compressed_bytes:
                raise OSError(f"{name}: truncated complete expert matrix")
            decode_start = time.perf_counter()
            decoded = vector_decoder(raw, rows, cols)
            dequant_seconds = time.perf_counter() - decode_start
            buffer_start = time.perf_counter()
            flat = decoded.reshape(-1)
            if flat.dtype.name != "float32" or not flat.flags.c_contiguous:
                raise ValueError(f"{name}: vector decoder returned a non-contiguous f32 matrix")
            contiguous_buffer_seconds = time.perf_counter() - buffer_start
        else:
            flat = array("f")
            for row in range(rows):
                read_start = time.perf_counter()
                raw = store.pread(name, base + row * row_bytes, row_bytes)
                read_seconds += time.perf_counter() - read_start
                if len(raw) != row_bytes:
                    raise OSError(f"{name}: truncated row {row}")
                decode_start = time.perf_counter()
                decoded = _dequant_row_bytes(loc.type_id, raw, cols)
                dequant_seconds += time.perf_counter() - decode_start
                if len(decoded) != cols:
                    raise ValueError(f"{name}: decoded row {row} has wrong length")
                buffer_start = time.perf_counter()
                flat.extend(decoded)
                contiguous_buffer_seconds += time.perf_counter() - buffer_start

        construct_start = time.perf_counter()
        value = self.mx.array(flat, dtype=self.mx.float32).reshape((rows, cols))
        matrix_construct_seconds = time.perf_counter() - construct_start
        eval_start = time.perf_counter()
        self.mx.eval(value)
        matrix_eval_seconds = time.perf_counter() - eval_start
        matrix_build_seconds = matrix_construct_seconds + matrix_eval_seconds
        matrix = DecodedMatrix(
            value=value,
            rows=rows,
            cols=cols,
            decoded_bytes=cols * rows * 4,
            compressed_bytes=compressed_bytes,
            quantization=loc.type_name,
            decoder_mode=(
                "numpy_vectorized"
                if vector_decoder is not None
                else "scalar_reference"
            ),
        )
        metrics = LoadMetrics(
            storage_bytes_read=compressed_bytes,
            storage_read_count=(
                1
                if vector_decoder is not None
                else rows
            ),
            storage_read_seconds=read_seconds,
            dequant_seconds=dequant_seconds,
            contiguous_buffer_seconds=contiguous_buffer_seconds,
            matrix_build_seconds=matrix_build_seconds,
            matrix_construct_seconds=matrix_construct_seconds,
            matrix_eval_seconds=matrix_eval_seconds,
        )
        return matrix, metrics

    def matvec(
        self, matrix: DecodedMatrix, x: list[float]
    ) -> tuple[list[float], float]:
        if len(x) != matrix.cols:
            raise ValueError(f"activation length {len(x)} != {matrix.cols}")
        start = time.perf_counter()
        xv = self.mx.array(x, dtype=self.mx.float32)
        y = matrix.value @ xv
        self.mx.eval(y)
        result = y.tolist()
        return result, time.perf_counter() - start

    def release_transient(self) -> None:
        """Release unretained Python and MLX objects after synchronized use."""

        gc.collect()
        clear_cache = getattr(self.mx, "clear_cache", None)
        if clear_cache is not None:
            clear_cache()


@dataclass
class ExpertCacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    admissions: int = 0
    admission_rejections: int = 0
    policy_bypasses: int = 0
    bytes_resident: int = 0
    peak_bytes_resident: int = 0
    storage_cache_hits: int = 0
    storage_cache_misses: int = 0
    decoded_cache_hits: int = 0
    decoded_cache_misses: int = 0
    storage_bytes_read: int = 0
    storage_read_count: int = 0
    storage_bytes_avoided: int = 0
    decoded_bytes_materialized: int = 0
    decoded_bytes_avoided: int = 0
    expert_redecode_count: int = 0
    storage_read_seconds: float = 0.0
    dequant_seconds: float = 0.0
    contiguous_buffer_seconds: float = 0.0
    mlx_matrix_build_seconds: float = 0.0
    mlx_matvec_count: int = 0
    mlx_matvec_seconds: float = 0.0
    transient_releases: int = 0
    cpu_fallbacks: int = 0
    backend: str = "unknown"
    device: str = "unknown"
    mlx_version: str = "unknown"
    decoder_mode: str = "unknown"
    resident_entries: int = 0
    quantization_metrics: dict[str, dict[str, int | float]] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "admissions": self.admissions,
            "admission_rejections": self.admission_rejections,
            "policy_bypasses": self.policy_bypasses,
            "bytes_resident": self.bytes_resident,
            "peak_bytes_resident": self.peak_bytes_resident,
            "resident_entries": self.resident_entries,
            "hit_rate": self.hits / max(1, self.hits + self.misses),
            "storage_cache_hits": self.storage_cache_hits,
            "storage_cache_misses": self.storage_cache_misses,
            "decoded_cache_hits": self.decoded_cache_hits,
            "decoded_cache_misses": self.decoded_cache_misses,
            "storage_bytes_read": self.storage_bytes_read,
            "storage_read_count": self.storage_read_count,
            "storage_bytes_avoided": self.storage_bytes_avoided,
            "decoded_bytes_materialized": self.decoded_bytes_materialized,
            "decoded_bytes_avoided": self.decoded_bytes_avoided,
            "expert_redecode_count": self.expert_redecode_count,
            "storage_read_seconds": self.storage_read_seconds,
            "dequant_seconds": self.dequant_seconds,
            "contiguous_buffer_seconds": self.contiguous_buffer_seconds,
            "mlx_matrix_build_seconds": self.mlx_matrix_build_seconds,
            "mlx_matvec_count": self.mlx_matvec_count,
            "mlx_matvec_seconds": self.mlx_matvec_seconds,
            "transient_releases": self.transient_releases,
            "cpu_fallbacks": self.cpu_fallbacks,
            "backend": self.backend,
            "device": self.device,
            "mlx_version": self.mlx_version,
            "decoder_mode": self.decoder_mode,
            "quantization_metrics": {
                quantization: dict(metrics)
                for quantization, metrics in sorted(self.quantization_metrics.items())
            },
        }


@dataclass
class ExpertSlabCache:
    """Protected shared-expert decoded cache under an exact logical cap."""

    max_bytes: int = 16 * 1024**3
    backend: MatrixBackend | None = None
    policy: str = "decoded_shared_only"
    decoder_mode: str = "scalar_reference"
    capture_events: bool = False
    stats: ExpertCacheStats = field(init=False)
    _resident: OrderedDict[str, DecodedMatrix] = field(default_factory=OrderedDict)
    _events: list[dict[str, Any]] = field(default_factory=list, init=False)
    _active_event: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        if self.policy != "decoded_shared_only":
            raise ValueError(f"unsupported cache policy {self.policy}")
        if self.decoder_mode not in MlxMatrixBackend.DECODER_MODES:
            raise ValueError(f"unsupported decoder mode {self.decoder_mode}")
        if self.backend is None:
            self.backend = MlxMatrixBackend(self.decoder_mode)
        self.stats = self._new_stats()

    def _new_stats(self) -> ExpertCacheStats:
        assert self.backend is not None
        identity = self.backend.identity()
        return ExpertCacheStats(
            backend=identity.get("backend", "unknown"),
            device=identity.get("device", "unknown"),
            mlx_version=identity.get("mlx_version", "unknown"),
            decoder_mode=identity.get("decoder_mode", self.decoder_mode),
        )

    def _quantization_metrics(self, quantization: str) -> dict[str, int | float]:
        return self.stats.quantization_metrics.setdefault(
            quantization,
            {
                "matrix_load_count": 0,
                "storage_bytes_read": 0,
                "storage_read_count": 0,
                "storage_read_seconds": 0.0,
                "dequant_seconds": 0.0,
                "contiguous_buffer_seconds": 0.0,
                "mlx_matrix_build_seconds": 0.0,
                "mlx_matvec_count": 0,
                "mlx_matvec_seconds": 0.0,
            },
        )

    @staticmethod
    def _key(name: str, expert: int) -> str:
        return f"{name}#{expert}"

    @staticmethod
    def _is_shared(name: str) -> bool:
        return "_shexp.weight" in name

    def clear(self) -> None:
        self._resident.clear()
        self.stats = self._new_stats()
        self._events.clear()
        self._active_event = None

    def event_snapshot(self) -> list[dict[str, Any]]:
        """Return independent bounded event dictionaries when capture is enabled."""

        return [dict(event) for event in self._events]

    def _record_load_event(
        self,
        *,
        name: str,
        expert: int,
        matrix: DecodedMatrix,
        hit: bool,
        metrics: LoadMetrics | None,
    ) -> None:
        if not self.capture_events:
            return
        self._events.append(
            {
                "tensor_name": name,
                "projection": next(
                    projection
                    for projection in ("gate", "up", "down")
                    if f"ffn_{projection}_" in name
                ),
                "expert_id": expert,
                "shared": self._is_shared(name),
                "cache_hit": hit,
                "quantization": matrix.quantization,
                "decoder_mode": matrix.decoder_mode,
                "rows": matrix.rows,
                "cols": matrix.cols,
                "compressed_bytes": matrix.compressed_bytes,
                "decoded_f32_bytes": matrix.decoded_bytes,
                "storage_read_count": 0 if metrics is None else metrics.storage_read_count,
                "storage_read_seconds": 0.0 if metrics is None else metrics.storage_read_seconds,
                "dequant_seconds": 0.0 if metrics is None else metrics.dequant_seconds,
                "contiguous_buffer_seconds": 0.0 if metrics is None else metrics.contiguous_buffer_seconds,
                "mlx_matrix_construct_seconds": 0.0 if metrics is None else metrics.matrix_construct_seconds,
                "mlx_matrix_eval_seconds": 0.0 if metrics is None else metrics.matrix_eval_seconds,
                "mlx_matrix_build_seconds": 0.0 if metrics is None else metrics.matrix_build_seconds,
                "mlx_matvec_seconds": 0.0,
                "cleanup_seconds": 0.0,
            }
        )
        self._active_event = len(self._events) - 1

    def get_or_load_matrix(
        self, store: Glm52TensorStore, name: str, expert: int
    ) -> DecodedMatrix:
        key = self._key(name, expert)
        matrix = self._resident.get(key)
        if matrix is not None:
            self.stats.hits += 1
            self.stats.storage_cache_hits += 1
            self.stats.decoded_cache_hits += 1
            self.stats.storage_bytes_avoided += matrix.compressed_bytes
            self.stats.decoded_bytes_avoided += matrix.decoded_bytes
            self._record_load_event(
                name=name,
                expert=expert,
                matrix=matrix,
                hit=True,
                metrics=None,
            )
            return matrix

        self.stats.misses += 1
        self.stats.storage_cache_misses += 1
        self.stats.decoded_cache_misses += 1
        assert self.backend is not None
        matrix, metrics = self.backend.load(store, name, expert)
        self.stats.storage_bytes_read += metrics.storage_bytes_read
        self.stats.storage_read_count += metrics.storage_read_count
        self.stats.storage_read_seconds += metrics.storage_read_seconds
        self.stats.dequant_seconds += metrics.dequant_seconds
        self.stats.contiguous_buffer_seconds += metrics.contiguous_buffer_seconds
        self.stats.mlx_matrix_build_seconds += metrics.matrix_build_seconds
        self.stats.decoded_bytes_materialized += matrix.decoded_bytes
        self.stats.expert_redecode_count += 1
        quantization = self._quantization_metrics(matrix.quantization)
        quantization["matrix_load_count"] += 1
        quantization["storage_bytes_read"] += metrics.storage_bytes_read
        quantization["storage_read_count"] += metrics.storage_read_count
        quantization["storage_read_seconds"] += metrics.storage_read_seconds
        quantization["dequant_seconds"] += metrics.dequant_seconds
        quantization["contiguous_buffer_seconds"] += metrics.contiguous_buffer_seconds
        quantization["mlx_matrix_build_seconds"] += metrics.matrix_build_seconds
        self._record_load_event(
            name=name,
            expert=expert,
            matrix=matrix,
            hit=False,
            metrics=metrics,
        )

        if not self._is_shared(name):
            self.stats.policy_bypasses += 1
            return matrix
        if self.stats.bytes_resident + matrix.decoded_bytes > self.max_bytes:
            self.stats.admission_rejections += 1
            return matrix

        self._resident[key] = matrix
        self.stats.admissions += 1
        self.stats.bytes_resident += matrix.decoded_bytes
        self.stats.peak_bytes_resident = max(
            self.stats.peak_bytes_resident, self.stats.bytes_resident
        )
        self.stats.resident_entries = len(self._resident)
        return matrix

    def matvec(self, matrix: DecodedMatrix, x: list[float]) -> list[float]:
        assert self.backend is not None
        result, seconds = self.backend.matvec(matrix, x)
        self.stats.mlx_matvec_count += 1
        self.stats.mlx_matvec_seconds += seconds
        quantization = self._quantization_metrics(matrix.quantization)
        quantization["mlx_matvec_count"] += 1
        quantization["mlx_matvec_seconds"] += seconds
        if self.capture_events:
            if self._active_event is None:
                raise RuntimeError("matvec event has no matching matrix load")
            self._events[self._active_event]["mlx_matvec_seconds"] += seconds
        return result

    def is_resident(self, name: str, expert: int) -> bool:
        return self._key(name, expert) in self._resident

    def release_transient(self) -> None:
        assert self.backend is not None
        cleanup_start = time.perf_counter() if self.capture_events else 0.0
        self.backend.release_transient()
        if self.capture_events:
            if self._active_event is None:
                raise RuntimeError("cleanup event has no matching matrix load")
            self._events[self._active_event]["cleanup_seconds"] += (
                time.perf_counter() - cleanup_start
            )
        self.stats.transient_releases += 1


def matvec_cached_rows(rows: list[list[float]], x: list[float]) -> list[float]:
    return [sum(a * b for a, b in zip(row, x, strict=True)) for row in rows]


def expert_matvec_cached(
    store: Glm52TensorStore,
    cache: ExpertSlabCache,
    name: str,
    expert: int,
    x: list[float],
) -> list[float]:
    matrix = cache.get_or_load_matrix(store, name, expert)
    resident = cache.is_resident(name, expert)
    if matrix.cols != len(x):
        raise ValueError(f"{name}: activation length {len(x)} != {matrix.cols}")
    result = cache.matvec(matrix, x)
    if not resident:
        del matrix
        cache.release_transient()
    return result

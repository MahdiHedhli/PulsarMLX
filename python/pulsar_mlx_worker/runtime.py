"""Sanitized MLX runtime discovery and the bounded GPU tensor probe.

This module never writes to stdout.  The protocol loop owns serialization and
stdout; callers receive immutable values or stable, bounded errors here.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import math
import os
import platform
import subprocess
from typing import Any, Mapping, Sequence


PINNED_MLX_VERSION = "0.32.0"
REQUIRED_SYSTEM = "Darwin"
REQUIRED_ARCHITECTURE = "arm64"
BACKEND_ID = "apple-mlx"
GPU_DEVICE_ID = "gpu"
PROBE_FIXTURE_ID = "nonsymmetric-f32-matmul-v1"
PROBE_OPERATION_ID = "nonsymmetric-f32-matmul"
PROBE_ABSOLUTE_TOLERANCE = 1.0e-5
PROBE_RELATIVE_TOLERANCE = 1.0e-5

_MAX_DIAGNOSTIC_CHARS = 512
_MAX_IDENTITY_CHARS = 256
_U64_MAX = (1 << 64) - 1

# The expected values are an independent, predeclared scalar result for:
# [[1, 2, 3], [4, 5, 6]] @ [[7, 8], [9, 10], [11, 12]].
_PROBE_LEFT = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
_PROBE_RIGHT = ((7.0, 8.0), (9.0, 10.0), (11.0, 12.0))
_PROBE_EXPECTED = (58.0, 64.0, 139.0, 154.0)


class RuntimeContractError(RuntimeError):
    """A stable worker error without implementation objects or private paths."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
        retryable: bool = False,
    ) -> None:
        self.code = (
            code
            if code
            and len(code) <= 64
            and all(
                character in "abcdefghijklmnopqrstuvwxyz0123456789_"
                for character in code
            )
            else "internal_worker_error"
        )
        self.message = _sanitize_diagnostic(message)
        self.details = dict(details or {})
        self.retryable = retryable
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class GpuDescriptor:
    """Whitelisted, bounded fields returned for the selected MLX GPU."""

    device_id: str
    device_name: str
    architecture: str
    memory_size_bytes: int | None
    max_recommended_working_set_bytes: int | None
    max_buffer_length_bytes: int | None

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "architecture": self.architecture,
            "memory_size_bytes": self.memory_size_bytes,
            "max_recommended_working_set_bytes": self.max_recommended_working_set_bytes,
            "max_buffer_length_bytes": self.max_buffer_length_bytes,
        }


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Sanitized identity established before any capability claim."""

    python_version: str
    python_arch: str
    mlx_version: str
    macos_version: str
    metal_available: bool
    gpu_count: int
    devices: tuple[GpuDescriptor, ...]
    capabilities: tuple[str, ...]
    supported_dtypes: tuple[str, ...]

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "python_version": self.python_version,
            "python_arch": self.python_arch,
            "mlx_version": self.mlx_version,
            "macos_version": self.macos_version,
            "metal_available": self.metal_available,
            "gpu_count": self.gpu_count,
            "devices": [device.to_protocol_result() for device in self.devices],
            "capabilities": list(self.capabilities),
            "supported_dtypes": list(self.supported_dtypes),
        }


@dataclass(frozen=True, slots=True)
class MemoryGauges:
    """Independent gauges; these values must never be added into one total."""

    mlx_active_bytes: int | None
    mlx_cache_bytes: int | None
    mlx_peak_bytes: int | None
    process_footprint_bytes: int | None
    process_footprint_source: str | None
    system_pressure: str | None

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "mlx_active_bytes": self.mlx_active_bytes,
            "mlx_cache_bytes": self.mlx_cache_bytes,
            "mlx_peak_bytes": self.mlx_peak_bytes,
            "process_footprint_bytes": self.process_footprint_bytes,
            "process_footprint_source": self.process_footprint_source,
            "system_pressure": self.system_pressure,
            "reported_summed_total_bytes": None,
        }


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    compared_count: int
    max_absolute_error: float
    max_relative_error: float
    first_mismatch_index: int | None
    passed: bool

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "oracle_id": "hard-coded-scalar:nonsymmetric-f32-matmul-v1",
            "absolute_tolerance": PROBE_ABSOLUTE_TOLERANCE,
            "relative_tolerance": PROBE_RELATIVE_TOLERANCE,
            "non_finite_policy": "reject",
            "compared_count": self.compared_count,
            "max_absolute_error": self.max_absolute_error,
            "max_relative_error": self.max_relative_error,
            "first_mismatch_index": self.first_mismatch_index,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class TensorProbeResult:
    fixture_id: str
    backend_id: str
    requested_device: str
    selected_device: str
    fallback_used: bool
    operation_id: str
    input_shapes: tuple[tuple[int, ...], ...]
    output_shape: tuple[int, ...]
    input_dtype: str
    accumulation_dtype: str
    output_dtype: str
    evaluated: bool
    synchronized: bool
    expected: tuple[float, ...]
    actual: tuple[float, ...]
    comparison: ComparisonResult
    memory_gauges: MemoryGauges

    @property
    def passed(self) -> bool:
        return (
            self.evaluated
            and self.synchronized
            and not self.fallback_used
            and self.selected_device == GPU_DEVICE_ID
            and self.comparison.passed
        )

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "backend_id": self.backend_id,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "operation_id": self.operation_id,
            "input_shapes": [list(shape) for shape in self.input_shapes],
            "output_shape": list(self.output_shape),
            "input_dtype": self.input_dtype,
            "accumulation_dtype": self.accumulation_dtype,
            "output_dtype": self.output_dtype,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "expected": list(self.expected),
            "actual": list(self.actual),
            "comparison": self.comparison.to_protocol_result(),
            "comparison_passed": self.comparison.passed,
            "memory_gauges": self.memory_gauges.to_protocol_result(),
            "passed": self.passed,
        }


def discover_runtime() -> RuntimeIdentity:
    """Discover and validate the one supported native Apple MLX runtime."""

    system = platform.system()
    architecture = platform.machine()
    if system != REQUIRED_SYSTEM or architecture != REQUIRED_ARCHITECTURE:
        raise RuntimeContractError(
            "unsupported_host",
            "apple-mlx requires a native arm64 Python process on macOS",
            details={"required_system": "macos", "required_arch": REQUIRED_ARCHITECTURE},
        )

    try:
        mlx_version = _bounded_identity(metadata.version("mlx"), "MLX version")
    except metadata.PackageNotFoundError as error:
        raise RuntimeContractError(
            "device_unavailable",
            "the pinned MLX runtime is not installed",
        ) from error
    if mlx_version != PINNED_MLX_VERSION:
        raise RuntimeContractError(
            "runtime_version_mismatch",
            "the installed MLX version does not match the project pin",
            details={"expected": PINNED_MLX_VERSION, "actual": mlx_version},
        )

    mx = _import_mlx()
    try:
        metal_available = bool(mx.metal.is_available())
    except Exception as error:
        raise RuntimeContractError(
            "metal_unavailable",
            "MLX could not establish Metal availability",
        ) from error
    if not metal_available:
        raise RuntimeContractError(
            "metal_unavailable",
            "the MLX Metal backend is unavailable",
        )

    try:
        raw_device_info = mx.device_info(mx.gpu)
    except Exception as error:
        raise RuntimeContractError(
            "device_unavailable",
            "MLX could not describe the explicitly selected GPU",
        ) from error
    gpu = sanitize_gpu_descriptor(raw_device_info)

    macos_version = _bounded_identity(platform.mac_ver()[0], "macOS version")
    python_version = _bounded_identity(platform.python_version(), "Python version")
    return RuntimeIdentity(
        python_version=python_version,
        python_arch=architecture,
        mlx_version=mlx_version,
        macos_version=macos_version,
        metal_available=True,
        gpu_count=1,
        devices=(gpu,),
        capabilities=(
            "health",
            "tensor_probe",
            "run_fixture",
            "run_synthetic_moe",
            "shutdown",
        ),
        supported_dtypes=("float32", "q8_0"),
    )


def run_tensor_probe(
    identity: RuntimeIdentity | None = None,
    *,
    requested_device: str = GPU_DEVICE_ID,
) -> TensorProbeResult:
    """Run one explicit, evaluated, synchronized MLX GPU matmul proof.

    The function never falls back.  Any request other than ``gpu`` or any
    inability to complete and compare the GPU result raises a stable error.
    """

    if requested_device != GPU_DEVICE_ID:
        raise RuntimeContractError(
            "device_unavailable",
            "the Apple MLX validation probe accepts only the explicit GPU device",
            details={"required_device": GPU_DEVICE_ID},
        )

    runtime_identity = identity if identity is not None else discover_runtime()
    _validate_probe_identity(runtime_identity)
    mx = _import_mlx()

    try:
        with mx.stream(mx.gpu):
            left = mx.array(_PROBE_LEFT, dtype=mx.float32)
            right = mx.array(_PROBE_RIGHT, dtype=mx.float32)
            result = mx.matmul(left, right, stream=mx.gpu)

        # Scheduling or allocation is not evidence.  Both calls must return.
        mx.eval(result)
        mx.synchronize(mx.gpu)
        actual = _flatten_numeric_result(result.tolist())
    except RuntimeContractError:
        raise
    except Exception as error:
        raise RuntimeContractError(
            "evaluation_failed",
            "the explicit MLX GPU tensor probe did not complete",
        ) from error

    comparison = compare_outputs(
        _PROBE_EXPECTED,
        actual,
        absolute_tolerance=PROBE_ABSOLUTE_TOLERANCE,
        relative_tolerance=PROBE_RELATIVE_TOLERANCE,
    )
    if not comparison.passed:
        raise RuntimeContractError(
            "comparison_failed",
            "the evaluated MLX GPU result did not match the independent scalar oracle",
            details={
                "compared_count": comparison.compared_count,
                "first_mismatch_index": comparison.first_mismatch_index,
                "max_absolute_error": comparison.max_absolute_error,
                "max_relative_error": comparison.max_relative_error,
            },
        )

    gauges = collect_memory_gauges(mx)
    return TensorProbeResult(
        fixture_id=PROBE_FIXTURE_ID,
        backend_id=BACKEND_ID,
        requested_device=GPU_DEVICE_ID,
        selected_device=GPU_DEVICE_ID,
        fallback_used=False,
        operation_id=PROBE_OPERATION_ID,
        input_shapes=((2, 3), (3, 2)),
        output_shape=(2, 2),
        input_dtype="float32",
        accumulation_dtype="float32",
        output_dtype="float32",
        evaluated=True,
        synchronized=True,
        expected=_PROBE_EXPECTED,
        actual=actual,
        comparison=comparison,
        memory_gauges=gauges,
    )


def sanitize_gpu_descriptor(raw: Mapping[str, object]) -> GpuDescriptor:
    """Whitelist and bound the device fields admitted to the protocol."""

    if not isinstance(raw, Mapping):
        raise RuntimeContractError(
            "device_unavailable",
            "MLX returned an invalid GPU descriptor",
        )
    return GpuDescriptor(
        device_id=GPU_DEVICE_ID,
        device_name=_bounded_identity(raw.get("device_name"), "GPU device name"),
        architecture=_bounded_identity(raw.get("architecture"), "GPU architecture"),
        memory_size_bytes=_optional_u64(raw.get("memory_size"), "GPU memory size"),
        max_recommended_working_set_bytes=_optional_u64(
            raw.get("max_recommended_working_set_size"),
            "GPU recommended working set",
        ),
        max_buffer_length_bytes=_optional_u64(
            raw.get("max_buffer_length"),
            "GPU maximum buffer length",
        ),
    )


def compare_outputs(
    expected: Sequence[float],
    actual: Sequence[float],
    *,
    absolute_tolerance: float,
    relative_tolerance: float,
) -> ComparisonResult:
    """Compare bounded numeric outputs using a predeclared abs/rel policy."""

    if not expected or len(expected) != len(actual) or len(expected) > 4_096:
        raise RuntimeContractError(
            "comparison_failed",
            "the comparison operands have invalid cardinality",
        )
    for tolerance in (absolute_tolerance, relative_tolerance):
        if not math.isfinite(tolerance) or tolerance < 0.0:
            raise RuntimeContractError(
                "comparison_failed",
                "comparison tolerances must be finite and nonnegative",
            )

    max_absolute_error = 0.0
    max_relative_error = 0.0
    first_mismatch_index: int | None = None

    for index, (expected_value, actual_value) in enumerate(zip(expected, actual)):
        if isinstance(expected_value, bool) or isinstance(actual_value, bool):
            raise RuntimeContractError(
                "comparison_failed",
                "boolean values are forbidden in the tensor probe comparison",
                details={"index": index},
            )
        try:
            expected_number = float(expected_value)
            actual_number = float(actual_value)
        except (TypeError, ValueError, OverflowError) as error:
            raise RuntimeContractError(
                "comparison_failed",
                "nonnumeric values are forbidden in the tensor probe comparison",
                details={"index": index},
            ) from error
        if not math.isfinite(expected_number) or not math.isfinite(actual_number):
            raise RuntimeContractError(
                "comparison_failed",
                "non-finite values are forbidden in the tensor probe comparison",
                details={"index": index},
            )

        absolute_error = abs(actual_number - expected_number)
        relative_error = (
            absolute_error / abs(expected_number)
            if expected_number != 0.0
            else (0.0 if absolute_error == 0.0 else math.inf)
        )
        max_absolute_error = max(max_absolute_error, absolute_error)
        max_relative_error = max(max_relative_error, relative_error)
        admitted_error = absolute_tolerance + relative_tolerance * abs(expected_number)
        if absolute_error > admitted_error and first_mismatch_index is None:
            first_mismatch_index = index

    return ComparisonResult(
        compared_count=len(expected),
        max_absolute_error=max_absolute_error,
        max_relative_error=max_relative_error,
        first_mismatch_index=first_mismatch_index,
        passed=first_mismatch_index is None,
    )


def collect_memory_gauges(mx: Any) -> MemoryGauges:
    """Capture independent allocator and optional host gauges without summing."""

    active = _optional_mlx_gauge(mx, "get_active_memory")
    cache = _optional_mlx_gauge(mx, "get_cache_memory")
    peak = _optional_mlx_gauge(mx, "get_peak_memory")
    if active is not None and peak is not None and peak < active:
        raise RuntimeContractError(
            "internal_worker_error",
            "MLX reported a peak memory gauge below active memory",
        )

    process_footprint = _optional_process_resident_bytes()
    return MemoryGauges(
        mlx_active_bytes=active,
        mlx_cache_bytes=cache,
        mlx_peak_bytes=peak,
        process_footprint_bytes=process_footprint,
        process_footprint_source="ps-rss" if process_footprint is not None else None,
        system_pressure=_optional_system_pressure(),
    )


def _validate_probe_identity(identity: RuntimeIdentity) -> None:
    if (
        identity.python_arch != REQUIRED_ARCHITECTURE
        or identity.mlx_version != PINNED_MLX_VERSION
        or not identity.macos_version
        or not identity.metal_available
        or identity.gpu_count != 1
        or len(identity.devices) != 1
        or identity.devices[0].device_id != GPU_DEVICE_ID
    ):
        raise RuntimeContractError(
            "device_unavailable",
            "the runtime identity no longer admits the explicit GPU probe",
        )


def _import_mlx() -> Any:
    try:
        import mlx.core as mx
    except Exception as error:
        raise RuntimeContractError(
            "device_unavailable",
            "the pinned MLX runtime could not be imported",
        ) from error
    return mx


def _flatten_numeric_result(value: object) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise RuntimeContractError(
            "evaluation_failed",
            "the tensor probe returned an unexpected output shape",
        )
    flattened: list[float] = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise RuntimeContractError(
                "evaluation_failed",
                "the tensor probe returned an unexpected output shape",
            )
        for element in row:
            if isinstance(element, bool) or not isinstance(element, (int, float)):
                raise RuntimeContractError(
                    "evaluation_failed",
                    "the tensor probe returned a nonnumeric value",
                )
            flattened.append(float(element))
    return tuple(flattened)


def _optional_mlx_gauge(mx: Any, function_name: str) -> int | None:
    function = getattr(mx, function_name, None)
    if not callable(function):
        metal = getattr(mx, "metal", None)
        function = getattr(metal, function_name, None)
    if not callable(function):
        return None
    try:
        value = function()
    except Exception:
        return None
    return _optional_u64(value, f"MLX {function_name}")


def _optional_process_resident_bytes() -> int | None:
    """Return current RSS as the closest portable process-footprint proxy."""

    try:
        completed = subprocess.run(
            ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
        if completed.returncode != 0:
            return None
        kibibytes = int(completed.stdout.strip())
        if kibibytes < 0 or kibibytes > _U64_MAX // 1_024:
            return None
        return kibibytes * 1_024
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _optional_system_pressure() -> str | None:
    """Read Darwin's pressure-level bit without emitting command output."""

    try:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.0,
        )
        if completed.returncode != 0:
            return None
        level = int(completed.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None

    return {1: "normal", 2: "warning", 4: "critical"}.get(level, f"unknown:{level}")


def _optional_u64(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _U64_MAX:
        raise RuntimeContractError(
            "internal_worker_error",
            f"{label} is not a valid unsigned byte count",
        )
    return value


def _bounded_identity(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise RuntimeContractError(
            "internal_worker_error",
            f"{label} is missing or invalid",
        )
    bounded = " ".join(value.split())
    if not bounded or len(bounded) > _MAX_IDENTITY_CHARS or _looks_like_private_path(bounded):
        raise RuntimeContractError(
            "internal_worker_error",
            f"{label} is missing, unbounded, or contains private path data",
        )
    return bounded


def _sanitize_diagnostic(message: str) -> str:
    bounded = " ".join(str(message).split())
    if not bounded or _looks_like_private_path(bounded):
        bounded = "runtime contract validation failed"
    return bounded[:_MAX_DIAGNOSTIC_CHARS]


def _looks_like_private_path(value: str) -> bool:
    return (
        value.startswith(("/", "~/"))
        or "/Users/" in value
        or "/home/" in value
        or "\\Users\\" in value
    )

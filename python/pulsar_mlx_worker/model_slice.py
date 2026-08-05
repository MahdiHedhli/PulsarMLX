"""One bounded, explicitly admitted Qwen3MoE Q8_0 projection slice.

This module is intentionally not a general GGUF loader.  Its public boundary
accepts only the frozen layer-0, expert-0, sixteen-row gate-projection slice.
All request, layout, byte-count, prompt, device, and Q8_0 scale checks finish
before MLX is imported or accessed.  Successful work is observable only after
explicit evaluation followed by synchronization on ``mx.gpu``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import ctypes
from dataclasses import dataclass
import hashlib
import math
import os
import platform
import struct
from typing import Any

from .runtime import (
    GPU_DEVICE_ID,
    RuntimeContractError,
    collect_memory_gauges,
)


SLICE_ID = "qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1"
OPERATION_ID = "q8_0_expert_projection_matvec"
TENSOR_NAME = "blk.0.ffn_gate_exps.weight"
OUTPUT_NAME = "blk0_ffn_gate_expert0_rows0_16_matvec"
PROMPT = (
    "PulsarMLX real-model oracle v1: Qwen3-30B-A3B Q8_0, "
    "blk.0.ffn_gate_exps.weight, expert 0, rows 0:16."
)
PROMPT_ADAPTER = "sha256-indexed-f32-v1"
ORIENTATION = "expert_output_row_input_column_no_transpose"

INPUT_COLUMNS = 2_048
EXPERT_ROWS = 768
EXPERT_COUNT = 128
OUTPUT_ROWS = 16
Q8_BLOCK_ELEMENTS = 32
Q8_BLOCK_BYTES = 34
Q8_SCALE_BYTES = 2
BLOCKS_PER_ROW = INPUT_COLUMNS // Q8_BLOCK_ELEMENTS
ENCODED_ROW_BYTES = BLOCKS_PER_ROW * Q8_BLOCK_BYTES
ENCODED_SLICE_BYTES = OUTPUT_ROWS * ENCODED_ROW_BYTES
DECODED_SLICE_BYTES = OUTPUT_ROWS * INPUT_COLUMNS * 4
ACTIVATION_BYTES = INPUT_COLUMNS * 4
OUTPUT_BYTES = OUTPUT_ROWS * 4

_GGUF_DIMS = (INPUT_COLUMNS, EXPERT_ROWS, EXPERT_COUNT)
_READER_ENCODED_SHAPE = (EXPERT_COUNT, EXPERT_ROWS, ENCODED_ROW_BYTES)
_READER_DEQUANTIZED_SHAPE = (EXPERT_COUNT, EXPERT_ROWS, INPUT_COLUMNS)
_ENCODED_SLICE_SHAPE = (OUTPUT_ROWS, ENCODED_ROW_BYTES)
_DECODED_SLICE_SHAPE = (OUTPUT_ROWS, INPUT_COLUMNS)
_OUTPUT_SHAPE = (OUTPUT_ROWS,)
_QUANT_TEMPORARY_BYTES = OUTPUT_ROWS * BLOCKS_PER_ROW * Q8_BLOCK_ELEMENTS * 4
_SCALE_TEMPORARY_BYTES = OUTPUT_ROWS * BLOCKS_PER_ROW * 4
_TEMPORARY_ARRAY_BYTES = _QUANT_TEMPORARY_BYTES + _SCALE_TEMPORARY_BYTES

_REQUEST_KEYS = frozenset(
    {
        "slice_id",
        "operation",
        "tensor_name",
        "gguf_dimensions_fastest_axis_first",
        "reader_encoded_shape",
        "reader_dequantized_shape",
        "orientation",
        "quantization",
        "expert_index",
        "output_row_start",
        "output_row_end",
        "input_column_start",
        "input_column_end",
        "prompt",
        "prompt_adapter",
        "output_name",
    }
)
_QUANTIZATION_KEYS = frozenset(
    {"id", "block_elements", "block_bytes", "scale_dtype"}
)


class ModelSliceError(RuntimeContractError):
    """Stable, bounded failure at the admitted model-slice boundary."""


@dataclass(frozen=True, slots=True)
class ModelSliceDescriptor:
    """Validated semantics for the single worker operation."""

    slice_id: str
    operation: str
    tensor_name: str
    gguf_dimensions_fastest_axis_first: tuple[int, int, int]
    reader_encoded_shape: tuple[int, int, int]
    reader_dequantized_shape: tuple[int, int, int]
    encoded_slice_shape: tuple[int, int]
    decoded_slice_shape: tuple[int, int]
    output_shape: tuple[int]
    orientation: str
    quantization: str
    quantization_block_elements: int
    quantization_block_bytes: int
    quantization_scale_dtype: str
    expert_index: int
    output_row_start: int
    output_row_end: int
    input_column_start: int
    input_column_end: int
    prompt: str
    prompt_adapter: str
    output_name: str
    encoded_byte_count: int
    decoded_byte_count: int
    transpose: bool


@dataclass(frozen=True, slots=True)
class ModelSliceMemoryGauges:
    """Separate allocation gauges that must never be added as one total."""

    model_file_bytes: int | None
    mapped_virtual_bytes: int
    mapped_resident_bytes: int
    owned_compressed_bytes: int
    decoded_array_bytes: int
    activation_array_bytes: int
    output_bytes: int
    temporary_current_bytes: int
    temporary_peak_bytes: int
    mlx_active_bytes: int | None
    mlx_cache_bytes: int | None
    mlx_peak_bytes: int | None
    process_footprint_bytes: int | None
    process_footprint_source: str | None
    process_physical_footprint_bytes: int | None
    process_physical_footprint_peak_bytes: int | None
    process_physical_footprint_source: str | None
    system_pressure: str | None

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "model_file_bytes": self.model_file_bytes,
            "mapped_virtual_bytes": self.mapped_virtual_bytes,
            "mapped_resident_bytes": self.mapped_resident_bytes,
            "owned_compressed_bytes": self.owned_compressed_bytes,
            "decoded_array_bytes": self.decoded_array_bytes,
            "activation_array_bytes": self.activation_array_bytes,
            "output_bytes": self.output_bytes,
            "temporary_current_bytes": self.temporary_current_bytes,
            "temporary_peak_bytes": self.temporary_peak_bytes,
            "mlx_active_bytes": self.mlx_active_bytes,
            "mlx_cache_bytes": self.mlx_cache_bytes,
            "mlx_peak_bytes": self.mlx_peak_bytes,
            "process_footprint_bytes": self.process_footprint_bytes,
            "process_footprint_source": self.process_footprint_source,
            "process_physical_footprint_bytes": (
                self.process_physical_footprint_bytes
            ),
            "process_physical_footprint_peak_bytes": (
                self.process_physical_footprint_peak_bytes
            ),
            "process_physical_footprint_source": (
                self.process_physical_footprint_source
            ),
            "system_pressure": self.system_pressure,
            # Inclusive MLX/process gauges overlap the named arrays above.
            "reported_summed_total_bytes": None,
        }


@dataclass(frozen=True, slots=True)
class ModelSliceResult:
    slice_id: str
    operation: str
    tensor_name: str
    output_name: str
    requested_device: str
    selected_device: str
    fallback_used: bool
    output_shape: tuple[int]
    output_dtype: str
    evaluated: bool
    synchronized: bool
    actual: tuple[float, ...]
    encoded_slice_sha256: str
    decoded_slice_sha256: str
    activation_sha256: str
    output_sha256: str
    memory_gauges: ModelSliceMemoryGauges

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "slice_id": self.slice_id,
            "operation": self.operation,
            "tensor_name": self.tensor_name,
            "output_name": self.output_name,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "output_shape": list(self.output_shape),
            "output_dtype": self.output_dtype,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "actual": list(self.actual),
            "encoded_slice_sha256": self.encoded_slice_sha256,
            "decoded_slice_sha256": self.decoded_slice_sha256,
            "activation_sha256": self.activation_sha256,
            "output_sha256": self.output_sha256,
            "memory_gauges": self.memory_gauges.to_protocol_result(),
        }


def build_prompt_activation(prompt: object) -> tuple[float, ...]:
    """Apply the frozen transparent prompt-digest adapter."""

    if not isinstance(prompt, str) or prompt != PROMPT:
        raise ModelSliceError(
            "malformed_request",
            "the model slice requires the exact frozen prompt",
        )
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return tuple(
        (((digest[index % len(digest)] + 73 * index + 19) % 257) - 128)
        / 128.0
        for index in range(INPUT_COLUMNS)
    )


def validate_model_slice_request(
    request: object,
    encoded_bytes: object,
) -> ModelSliceDescriptor:
    """Validate the entire operation and Q8_0 payload without touching MLX."""

    if not isinstance(request, Mapping):
        raise ModelSliceError(
            "malformed_request",
            "the model-slice request must be an object",
        )
    _require_exact_keys(request, _REQUEST_KEYS, "model-slice request")

    if request["slice_id"] != SLICE_ID:
        raise ModelSliceError(
            "unsupported_operation",
            "the requested model-slice identity is not supported",
        )
    if request["operation"] != OPERATION_ID:
        raise ModelSliceError(
            "unsupported_operation",
            "only the admitted Q8_0 expert projection is supported",
        )
    if request["tensor_name"] != TENSOR_NAME:
        raise ModelSliceError(
            "unsupported_operation",
            "the requested tensor is outside the admitted model slice",
        )

    gguf_dimensions = _exact_shape(
        request["gguf_dimensions_fastest_axis_first"],
        _GGUF_DIMS,
        "GGUF tensor dimensions",
    )
    reader_encoded_shape = _exact_shape(
        request["reader_encoded_shape"],
        _READER_ENCODED_SHAPE,
        "GGUF reader encoded shape",
    )
    reader_dequantized_shape = _exact_shape(
        request["reader_dequantized_shape"],
        _READER_DEQUANTIZED_SHAPE,
        "GGUF reader dequantized shape",
    )
    if request["orientation"] != ORIENTATION:
        raise ModelSliceError(
            "invalid_layout",
            "the model slice requires expert-row-column order without transpose",
        )

    quantization = request["quantization"]
    if not isinstance(quantization, Mapping):
        raise ModelSliceError(
            "malformed_request",
            "the Q8_0 descriptor must be an object",
        )
    _require_exact_keys(quantization, _QUANTIZATION_KEYS, "Q8_0 descriptor")
    if quantization["id"] != "Q8_0":
        raise ModelSliceError(
            "invalid_dtype",
            "the admitted tensor slice requires Q8_0",
        )
    if not _is_exact_int(quantization["block_elements"], Q8_BLOCK_ELEMENTS):
        raise ModelSliceError(
            "invalid_byte_count",
            "the Q8_0 element block width is invalid",
        )
    if not _is_exact_int(quantization["block_bytes"], Q8_BLOCK_BYTES):
        raise ModelSliceError(
            "invalid_byte_count",
            "the Q8_0 encoded block width is invalid",
        )
    if quantization["scale_dtype"] != "float16_little_endian":
        raise ModelSliceError(
            "invalid_dtype",
            "the Q8_0 scale must be little-endian float16",
        )

    bounded_fields = (
        ("expert_index", 0),
        ("output_row_start", 0),
        ("output_row_end", OUTPUT_ROWS),
        ("input_column_start", 0),
        ("input_column_end", INPUT_COLUMNS),
    )
    if any(
        not _is_exact_int(request[field], expected)
        for field, expected in bounded_fields
    ):
        raise ModelSliceError(
            "unsupported_operation",
            "the requested expert or range exceeds the admitted model slice",
        )
    if request["prompt"] != PROMPT or request["prompt_adapter"] != PROMPT_ADAPTER:
        raise ModelSliceError(
            "malformed_request",
            "the model slice requires the exact frozen prompt adapter",
        )
    if request["output_name"] != OUTPUT_NAME:
        raise ModelSliceError(
            "unsupported_operation",
            "the requested output is outside the admitted model slice",
        )

    if not isinstance(encoded_bytes, bytes):
        raise ModelSliceError(
            "invalid_byte_count",
            "the Q8_0 slice must be supplied as owned immutable bytes",
        )
    if len(encoded_bytes) != ENCODED_SLICE_BYTES:
        raise ModelSliceError(
            "invalid_byte_count",
            "the Q8_0 slice byte count does not match sixteen complete rows",
        )
    _validate_q8_0_scales(encoded_bytes)

    return ModelSliceDescriptor(
        slice_id=SLICE_ID,
        operation=OPERATION_ID,
        tensor_name=TENSOR_NAME,
        gguf_dimensions_fastest_axis_first=gguf_dimensions,
        reader_encoded_shape=reader_encoded_shape,
        reader_dequantized_shape=reader_dequantized_shape,
        encoded_slice_shape=_ENCODED_SLICE_SHAPE,
        decoded_slice_shape=_DECODED_SLICE_SHAPE,
        output_shape=_OUTPUT_SHAPE,
        orientation=ORIENTATION,
        quantization="Q8_0",
        quantization_block_elements=Q8_BLOCK_ELEMENTS,
        quantization_block_bytes=Q8_BLOCK_BYTES,
        quantization_scale_dtype="float16_little_endian",
        expert_index=0,
        output_row_start=0,
        output_row_end=OUTPUT_ROWS,
        input_column_start=0,
        input_column_end=INPUT_COLUMNS,
        prompt=PROMPT,
        prompt_adapter=PROMPT_ADAPTER,
        output_name=OUTPUT_NAME,
        encoded_byte_count=ENCODED_SLICE_BYTES,
        decoded_byte_count=DECODED_SLICE_BYTES,
        transpose=False,
    )


def validate_model_slice_output(values: object) -> tuple[float, ...]:
    """Return exactly sixteen finite numeric float values."""

    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or len(values) != OUTPUT_ROWS
    ):
        raise ModelSliceError(
            "invalid_shape",
            "the model-slice output must contain exactly sixteen values",
        )
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ModelSliceError(
                "evaluation_failed",
                "the model-slice output contains a nonnumeric value",
            )
        number = float(value)
        if not math.isfinite(number):
            raise ModelSliceError(
                "evaluation_failed",
                "the model-slice output contains a non-finite value",
            )
        result.append(number)
    return tuple(result)


def run_model_slice(
    request: object,
    encoded_bytes: object,
    *,
    requested_device: object,
    allow_fallback: object,
    mx_module: Any | None = None,
) -> ModelSliceResult:
    """Validate, decode, evaluate, synchronize, and read one bounded output."""

    if requested_device != GPU_DEVICE_ID or allow_fallback is not False:
        raise ModelSliceError(
            "device_unavailable",
            "the model slice accepts only an explicit GPU with fallback disabled",
        )

    # Every operation input, including every scale, is checked before the MLX
    # module is imported, dereferenced, or used for scheduling.
    descriptor = validate_model_slice_request(request, encoded_bytes)
    assert isinstance(encoded_bytes, bytes)  # Established by the validator.
    activation_values = build_prompt_activation(descriptor.prompt)
    scale_values, quant_values, decoded_bytes = _decode_q8_0(encoded_bytes)
    activation_identity = struct.pack(f"<{INPUT_COLUMNS}f", *activation_values)

    mx = mx_module if mx_module is not None else _import_mlx()
    try:
        with mx.stream(mx.gpu):
            scales = mx.reshape(
                mx.array(scale_values, dtype=mx.float32),
                (OUTPUT_ROWS, BLOCKS_PER_ROW, 1),
                stream=mx.gpu,
            )
            quants = mx.reshape(
                mx.array(quant_values, dtype=mx.float32),
                (OUTPUT_ROWS, BLOCKS_PER_ROW, Q8_BLOCK_ELEMENTS),
                stream=mx.gpu,
            )
            decoded = mx.reshape(
                quants * scales,
                _DECODED_SLICE_SHAPE,
                stream=mx.gpu,
            )
            activation = mx.array(activation_values, dtype=mx.float32)
            output = mx.matmul(decoded, activation, stream=mx.gpu)

        # Scheduling is not completion evidence.  Evaluate the decode and the
        # output, then cross the explicit GPU synchronization boundary.
        mx.eval(decoded, output)
        evaluated = True
        mx.synchronize(mx.gpu)
        synchronized = True

        _validate_mlx_output_metadata(mx, output)
        actual = validate_model_slice_output(output.tolist())
        base_gauges = collect_memory_gauges(mx)
    except ModelSliceError:
        raise
    except RuntimeContractError as error:
        raise ModelSliceError(error.code, error.message) from error
    except Exception as error:
        raise ModelSliceError(
            "evaluation_failed",
            "the admitted MLX model slice did not complete",
        ) from error

    physical_footprint, peak_physical_footprint = _optional_physical_footprint()
    memory_gauges = ModelSliceMemoryGauges(
        model_file_bytes=None,
        mapped_virtual_bytes=0,
        mapped_resident_bytes=0,
        owned_compressed_bytes=ENCODED_SLICE_BYTES,
        decoded_array_bytes=DECODED_SLICE_BYTES,
        activation_array_bytes=ACTIVATION_BYTES,
        output_bytes=OUTPUT_BYTES,
        temporary_current_bytes=_TEMPORARY_ARRAY_BYTES,
        temporary_peak_bytes=_TEMPORARY_ARRAY_BYTES,
        mlx_active_bytes=base_gauges.mlx_active_bytes,
        mlx_cache_bytes=base_gauges.mlx_cache_bytes,
        mlx_peak_bytes=base_gauges.mlx_peak_bytes,
        process_footprint_bytes=base_gauges.process_footprint_bytes,
        process_footprint_source=base_gauges.process_footprint_source,
        process_physical_footprint_bytes=physical_footprint,
        process_physical_footprint_peak_bytes=peak_physical_footprint,
        process_physical_footprint_source=(
            "proc_pid_rusage:RUSAGE_INFO_V4"
            if physical_footprint is not None
            else None
        ),
        system_pressure=base_gauges.system_pressure,
    )
    output_bytes = struct.pack(f"<{OUTPUT_ROWS}f", *actual)
    return ModelSliceResult(
        slice_id=descriptor.slice_id,
        operation=descriptor.operation,
        tensor_name=descriptor.tensor_name,
        output_name=descriptor.output_name,
        requested_device=GPU_DEVICE_ID,
        selected_device=GPU_DEVICE_ID,
        fallback_used=False,
        output_shape=_OUTPUT_SHAPE,
        output_dtype="float32",
        evaluated=evaluated,
        synchronized=synchronized,
        actual=actual,
        encoded_slice_sha256=hashlib.sha256(encoded_bytes).hexdigest(),
        decoded_slice_sha256=hashlib.sha256(decoded_bytes).hexdigest(),
        activation_sha256=hashlib.sha256(activation_identity).hexdigest(),
        output_sha256=hashlib.sha256(output_bytes).hexdigest(),
        memory_gauges=memory_gauges,
    )


def _validate_q8_0_scales(encoded_bytes: bytes) -> None:
    for offset in range(0, len(encoded_bytes), Q8_BLOCK_BYTES):
        scale = struct.unpack_from("<e", encoded_bytes, offset)[0]
        if not math.isfinite(scale):
            raise ModelSliceError(
                "invalid_dtype",
                "the Q8_0 slice contains a non-finite float16 scale",
            )


def _decode_q8_0(
    encoded_bytes: bytes,
) -> tuple[tuple[float, ...], tuple[float, ...], bytes]:
    """Decode row-major Q8_0 blocks with no tensor transpose."""

    scales: list[float] = []
    quants: list[float] = []
    decoded = bytearray(DECODED_SLICE_BYTES)
    decoded_offset = 0
    for row_index in range(OUTPUT_ROWS):
        row_offset = row_index * ENCODED_ROW_BYTES
        for block_index in range(BLOCKS_PER_ROW):
            block_offset = row_offset + block_index * Q8_BLOCK_BYTES
            scale = struct.unpack_from("<e", encoded_bytes, block_offset)[0]
            quantized = struct.unpack_from(
                f"<{Q8_BLOCK_ELEMENTS}b",
                encoded_bytes,
                block_offset + Q8_SCALE_BYTES,
            )
            scales.append(scale)
            for quant in quantized:
                quant_as_float = float(quant)
                quants.append(quant_as_float)
                struct.pack_into(
                    "<f",
                    decoded,
                    decoded_offset,
                    scale * quant_as_float,
                )
                decoded_offset += 4
    if decoded_offset != DECODED_SLICE_BYTES:
        raise ModelSliceError(
            "internal_worker_error",
            "the bounded Q8_0 decoder produced an invalid byte count",
        )
    return tuple(scales), tuple(quants), bytes(decoded)


def _validate_mlx_output_metadata(mx: Any, output: Any) -> None:
    try:
        actual_shape = tuple(output.shape)
        actual_dtype = output.dtype
    except Exception as error:
        raise ModelSliceError(
            "evaluation_failed",
            "the MLX model-slice output has no bounded shape or dtype",
        ) from error
    if actual_shape != _OUTPUT_SHAPE:
        raise ModelSliceError(
            "invalid_shape",
            "the MLX model-slice output shape is invalid",
        )
    if actual_dtype != mx.float32:
        raise ModelSliceError(
            "invalid_dtype",
            "the MLX model-slice output dtype is not float32",
        )


def _exact_shape(
    value: object,
    expected: tuple[int, int, int],
    label: str,
) -> tuple[int, int, int]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or len(value) != len(expected)
        or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in value
        )
        or tuple(value) != expected
    ):
        raise ModelSliceError(
            "invalid_shape",
            f"{label} does not match the admitted tensor",
        )
    return expected


def _require_exact_keys(
    value: Mapping[object, object],
    expected: frozenset[str],
    label: str,
) -> None:
    try:
        actual = frozenset(value.keys())
    except (TypeError, ValueError) as error:
        raise ModelSliceError(
            "malformed_request",
            f"{label} contains invalid field names",
        ) from error
    if actual != expected:
        raise ModelSliceError(
            "malformed_request",
            f"{label} fields do not match the versioned contract",
        )


def _is_exact_int(value: object, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _import_mlx() -> Any:
    try:
        import mlx.core as mx
    except Exception as error:
        raise ModelSliceError(
            "device_unavailable",
            "the pinned MLX runtime could not be imported",
        ) from error
    return mx


def _optional_physical_footprint() -> tuple[int | None, int | None]:
    """Read Darwin physical-footprint gauges without treating RSS as equal."""

    if platform.system() != "Darwin":
        return None, None
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        function = libproc.proc_pid_rusage
        function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        function.restype = ctypes.c_int
        usage = _RusageInfoV4()
        if function(os.getpid(), 4, ctypes.byref(usage)) != 0:
            return None, None
        current = int(usage.ri_phys_footprint)
        peak = int(usage.ri_lifetime_max_phys_footprint)
        if current < 0 or peak < current:
            return None, None
        return current, peak
    except (AttributeError, OSError, TypeError, ValueError):
        return None, None


class _RusageInfoV4(ctypes.Structure):
    """Darwin ``rusage_info_v4`` through its bounded physical gauges."""

    _fields_ = [
        ("ri_uuid", ctypes.c_uint8 * 16),
        ("ri_user_time", ctypes.c_uint64),
        ("ri_system_time", ctypes.c_uint64),
        ("ri_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_interrupt_wkups", ctypes.c_uint64),
        ("ri_pageins", ctypes.c_uint64),
        ("ri_wired_size", ctypes.c_uint64),
        ("ri_resident_size", ctypes.c_uint64),
        ("ri_phys_footprint", ctypes.c_uint64),
        ("ri_proc_start_abstime", ctypes.c_uint64),
        ("ri_proc_exit_abstime", ctypes.c_uint64),
        ("ri_child_user_time", ctypes.c_uint64),
        ("ri_child_system_time", ctypes.c_uint64),
        ("ri_child_pkg_idle_wkups", ctypes.c_uint64),
        ("ri_child_interrupt_wkups", ctypes.c_uint64),
        ("ri_child_pageins", ctypes.c_uint64),
        ("ri_child_elapsed_abstime", ctypes.c_uint64),
        ("ri_diskio_bytesread", ctypes.c_uint64),
        ("ri_diskio_byteswritten", ctypes.c_uint64),
        ("ri_cpu_time_qos_default", ctypes.c_uint64),
        ("ri_cpu_time_qos_maintenance", ctypes.c_uint64),
        ("ri_cpu_time_qos_background", ctypes.c_uint64),
        ("ri_cpu_time_qos_utility", ctypes.c_uint64),
        ("ri_cpu_time_qos_legacy", ctypes.c_uint64),
        ("ri_cpu_time_qos_user_initiated", ctypes.c_uint64),
        ("ri_cpu_time_qos_user_interactive", ctypes.c_uint64),
        ("ri_billed_system_time", ctypes.c_uint64),
        ("ri_serviced_system_time", ctypes.c_uint64),
        ("ri_logical_writes", ctypes.c_uint64),
        ("ri_lifetime_max_phys_footprint", ctypes.c_uint64),
        ("ri_instructions", ctypes.c_uint64),
        ("ri_cycles", ctypes.c_uint64),
        ("ri_billed_energy", ctypes.c_uint64),
        ("ri_serviced_energy", ctypes.c_uint64),
        ("ri_interval_max_phys_footprint", ctypes.c_uint64),
        ("ri_runnable_time", ctypes.c_uint64),
    ]

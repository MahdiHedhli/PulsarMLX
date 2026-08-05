"""Worker/file-boundary tests for the one admitted real-model slice.

The sparse files in this suite have the exact admitted byte length but contain
only generated zero Q8_0 blocks at the bounded range.  They are temporary test
fixtures, not model artifacts, and the injected runner never schedules MLX.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
import platform
import struct
import tempfile
from types import SimpleNamespace
import unittest

from pulsar_mlx_worker.__main__ import _dispatch
from pulsar_mlx_worker.model_slice import (
    ACTIVATION_BYTES,
    DECODED_SLICE_BYTES,
    ENCODED_SLICE_BYTES,
    MLX_ACTIVE_BYTES_CAP,
    MLX_CACHE_BYTES_CAP,
    MLX_PEAK_BYTES_CAP,
    MODEL_FILE_BYTES,
    MODEL_SLICE_OFFSET,
    OPERATION_ID,
    OUTPUT_BYTES,
    OUTPUT_NAME,
    PROCESS_PHYSICAL_FOOTPRINT_BYTES_CAP,
    SLICE_ID,
    TEMPORARY_CURRENT_BYTES_CAP,
    TEMPORARY_PEAK_BYTES_CAP,
    TENSOR_NAME,
    ModelSliceError,
    ModelSliceMemoryGauges,
    ModelSliceResult,
    admitted_model_slice_request,
    run_inherited_model_slice,
)
from pulsar_mlx_worker.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    RequestDecoder,
    RequestEnvelope,
)


ACTIVATION_SHA256 = (
    "3821796e8415d1214890e0e2fc97cddbb9ec773f2e941203dac41c1c7b36a92e"
)
GENERATED_SLICE = bytes(ENCODED_SLICE_BYTES)


def valid_gauges() -> ModelSliceMemoryGauges:
    return ModelSliceMemoryGauges(
        model_file_bytes=None,
        mapped_virtual_bytes=0,
        mapped_resident_bytes=0,
        owned_compressed_bytes=ENCODED_SLICE_BYTES,
        decoded_array_bytes=DECODED_SLICE_BYTES,
        activation_array_bytes=ACTIVATION_BYTES,
        output_bytes=OUTPUT_BYTES,
        temporary_current_bytes=135_168,
        temporary_peak_bytes=135_168,
        mlx_active_bytes=262_144,
        mlx_cache_bytes=65_536,
        mlx_peak_bytes=524_288,
        process_footprint_bytes=16_777_216,
        process_footprint_source="ps-rss",
        process_physical_footprint_bytes=33_554_432,
        process_physical_footprint_peak_bytes=67_108_864,
        process_physical_footprint_source="proc_pid_rusage:RUSAGE_INFO_V4",
        system_pressure="normal",
    )


def valid_result(
    gauges: ModelSliceMemoryGauges | None = None,
) -> ModelSliceResult:
    actual = tuple(float(index) for index in range(16))
    return ModelSliceResult(
        slice_id=SLICE_ID,
        operation=OPERATION_ID,
        tensor_name=TENSOR_NAME,
        output_name=OUTPUT_NAME,
        requested_device="gpu",
        selected_device="gpu",
        fallback_used=False,
        output_shape=(16,),
        output_dtype="float32",
        evaluated=True,
        synchronized=True,
        actual=actual,
        encoded_slice_sha256=hashlib.sha256(GENERATED_SLICE).hexdigest(),
        decoded_slice_sha256="2" * 64,
        activation_sha256=ACTIVATION_SHA256,
        output_sha256=hashlib.sha256(struct.pack("<16f", *actual)).hexdigest(),
        memory_gauges=valid_gauges() if gauges is None else gauges,
    )


class SparseAdmittedFile:
    def __init__(self, *, size: int = MODEL_FILE_BYTES) -> None:
        self.file = tempfile.TemporaryFile()
        self.file.truncate(size)
        if size >= MODEL_SLICE_OFFSET + ENCODED_SLICE_BYTES:
            written = os.pwrite(
                self.file.fileno(),
                GENERATED_SLICE,
                MODEL_SLICE_OFFSET,
            )
            if written != ENCODED_SLICE_BYTES:
                raise AssertionError("temporary positional write was short")

    def __enter__(self) -> "SparseAdmittedFile":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.file.close()

    def fileno(self) -> int:
        return self.file.fileno()


class RunnerSpy:
    def __init__(self, result: ModelSliceResult | None = None) -> None:
        self.calls = 0
        self.request: dict[str, object] | None = None
        self.encoded: bytes | None = None
        self.result = valid_result() if result is None else result

    def __call__(
        self,
        request: dict[str, object],
        encoded: bytes,
        *,
        requested_device: str,
        allow_fallback: bool,
    ) -> ModelSliceResult:
        self.calls += 1
        self.request = request
        self.encoded = encoded
        if requested_device != "gpu" or allow_fallback:
            raise AssertionError("runner received an unadmitted device request")
        return self.result


class ModelSliceWorkerTests(unittest.TestCase):
    def assert_slice_error(self, code: str, callable_, /, *args, **kwargs) -> None:
        with self.assertRaises(ModelSliceError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertLessEqual(len(caught.exception.message), 512)

    def dispatch(self, params: dict[str, object], runner) -> dict[str, object]:
        request = RequestEnvelope(
            protocol=PROTOCOL_VERSION,
            request_id=7,
            op="run_model_slice",
            params=params,
        )
        result, should_shutdown = _dispatch(
            request,
            object(),
            probe_runner=lambda *_args, **_kwargs: None,
            model_slice_runner=runner,
        )
        self.assertFalse(should_shutdown)
        return result

    def test_control_request_is_registered_bounded_and_contains_no_file_selector(
        self,
    ) -> None:
        params = {
            "slice_id": SLICE_ID,
            "device": "gpu",
            "allow_fallback": False,
        }
        encoded = json.dumps(
            {
                "protocol": PROTOCOL_VERSION,
                "request_id": 7,
                "op": "run_model_slice",
                "params": params,
            },
            separators=(",", ":"),
        ).encode() + b"\n"
        request = RequestDecoder().feed(encoded)[0]

        self.assertEqual(request.params, params)
        self.assertNotIn(b"model_path", encoded)
        self.assertNotIn(b"weights", encoded)
        self.assertNotIn(b"base64", encoded)
        self.assertNotIn(b"sha256", encoded)
        self.assertNotIn(b"token", encoded)

    def test_forbidden_file_weight_token_depth_and_extra_params_precede_runner(
        self,
    ) -> None:
        base = {
            "slice_id": SLICE_ID,
            "device": "gpu",
            "allow_fallback": False,
        }
        forbidden = {
            "model_path": "/private/model.gguf",
            "weights": [1, 2, 3],
            "base64": "AA==",
            "sha256": "0" * 64,
            "token": "secret",
            "depth": "full_layer",
            "output_dump": True,
            "extra": None,
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                runner = RunnerSpy()
                with self.assertRaises(ProtocolError) as caught:
                    self.dispatch({**base, field: value}, runner)
                self.assertEqual(caught.exception.code, "malformed_request")
                self.assertEqual(runner.calls, 0)

    def test_invalid_identity_device_and_fallback_precede_runner(self) -> None:
        cases = (
            (
                {
                    "slice_id": "different-slice",
                    "device": "gpu",
                    "allow_fallback": False,
                },
                "unsupported_operation",
            ),
            (
                {
                    "slice_id": SLICE_ID,
                    "device": "cpu",
                    "allow_fallback": False,
                },
                "device_unavailable",
            ),
            (
                {
                    "slice_id": SLICE_ID,
                    "device": "gpu",
                    "allow_fallback": True,
                },
                "device_unavailable",
            ),
            (
                {
                    "slice_id": SLICE_ID,
                    "device": "gpu",
                    "allow_fallback": 0,
                },
                "malformed_request",
            ),
        )
        for params, code in cases:
            with self.subTest(params=params):
                runner = RunnerSpy()
                with self.assertRaises(ProtocolError) as caught:
                    self.dispatch(params, runner)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(runner.calls, 0)

    def test_sparse_file_reads_exact_range_with_interrupted_partial_retries(
        self,
    ) -> None:
        with SparseAdmittedFile() as model:
            calls = 0

            def partial_pread(fd: int, count: int, offset: int) -> bytes:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise InterruptedError()
                return os.pread(fd, min(count, 97), offset)

            runner = RunnerSpy()
            result = run_inherited_model_slice(
                slice_id=SLICE_ID,
                requested_device="gpu",
                allow_fallback=False,
                model_fd=model.fileno(),
                model_runner=runner,
                pread_func=partial_pread,
                pressure_func=lambda: "normal",
            )

        self.assertGreater(calls, 2)
        self.assertEqual(runner.calls, 1)
        self.assertEqual(runner.request, admitted_model_slice_request())
        self.assertEqual(runner.encoded, GENERATED_SLICE)
        self.assertEqual(result.memory_gauges.model_file_bytes, MODEL_FILE_BYTES)
        self.assertEqual(result.memory_gauges.system_pressure, "normal")

    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "inherited model-slice execution requires native Apple Silicon",
    )
    def test_sparse_file_executes_t059_and_emits_real_bounded_gauges(self) -> None:
        with SparseAdmittedFile() as model:
            result = run_inherited_model_slice(
                slice_id=SLICE_ID,
                requested_device="gpu",
                allow_fallback=False,
                model_fd=model.fileno(),
            )

        self.assertTrue(result.evaluated and result.synchronized)
        self.assertEqual(result.actual, (0.0,) * 16)
        self.assertEqual(
            result.encoded_slice_sha256,
            hashlib.sha256(GENERATED_SLICE).hexdigest(),
        )
        gauges = result.memory_gauges.to_protocol_result()
        self.assertEqual(gauges["model_file_bytes"], MODEL_FILE_BYTES)
        self.assertEqual(gauges["owned_compressed_bytes"], ENCODED_SLICE_BYTES)
        self.assertEqual(gauges["decoded_array_bytes"], DECODED_SLICE_BYTES)
        self.assertEqual(gauges["system_pressure"], "normal")
        self.assertIsNotNone(gauges["process_physical_footprint_bytes"])
        self.assertIsNotNone(gauges["process_physical_footprint_peak_bytes"])
        self.assertIsNone(gauges["reported_summed_total_bytes"])

    def test_wrong_size_short_read_and_changed_stat_precede_runner(self) -> None:
        runner = RunnerSpy()
        with SparseAdmittedFile(size=MODEL_FILE_BYTES - 1) as model:
            self.assert_slice_error(
                "invalid_byte_count",
                run_inherited_model_slice,
                slice_id=SLICE_ID,
                requested_device="gpu",
                allow_fallback=False,
                model_fd=model.fileno(),
                model_runner=runner,
                pressure_func=lambda: "normal",
            )
        self.assertEqual(runner.calls, 0)

        with SparseAdmittedFile() as model:
            self.assert_slice_error(
                "invalid_byte_count",
                run_inherited_model_slice,
                slice_id=SLICE_ID,
                requested_device="gpu",
                allow_fallback=False,
                model_fd=model.fileno(),
                model_runner=runner,
                pread_func=lambda _fd, _count, _offset: b"",
                pressure_func=lambda: "normal",
            )
        self.assertEqual(runner.calls, 0)

        with SparseAdmittedFile() as model:
            observed = os.fstat(model.fileno())
            fstat_calls = 0

            def changing_fstat(_fd: int):
                nonlocal fstat_calls
                fstat_calls += 1
                modified_ns = observed.st_mtime_ns + (1 if fstat_calls > 1 else 0)
                return SimpleNamespace(
                    st_dev=observed.st_dev,
                    st_ino=observed.st_ino,
                    st_mode=observed.st_mode,
                    st_size=observed.st_size,
                    st_mtime_ns=modified_ns,
                    st_ctime_ns=observed.st_ctime_ns,
                )

            self.assert_slice_error(
                "invalid_byte_count",
                run_inherited_model_slice,
                slice_id=SLICE_ID,
                requested_device="gpu",
                allow_fallback=False,
                model_fd=model.fileno(),
                model_runner=runner,
                fstat_func=changing_fstat,
                pressure_func=lambda: "normal",
            )
        self.assertEqual(runner.calls, 0)

    def test_non_normal_pre_execution_pressure_precedes_file_and_runner(self) -> None:
        runner = RunnerSpy()
        self.assert_slice_error(
            "resource_limit",
            run_inherited_model_slice,
            slice_id=SLICE_ID,
            requested_device="gpu",
            allow_fallback=False,
            model_fd=999_999,
            model_runner=runner,
            pressure_func=lambda: "warning",
        )
        self.assertEqual(runner.calls, 0)

    def test_real_execution_requires_normal_pressure_physical_gauges_and_caps(
        self,
    ) -> None:
        base = valid_gauges()
        cases = (
            (replace(base, system_pressure="warning"), "pressure"),
            (
                replace(
                    base,
                    process_physical_footprint_bytes=None,
                    process_physical_footprint_peak_bytes=None,
                    process_physical_footprint_source=None,
                ),
                "missing physical footprint",
            ),
            (
                replace(
                    base,
                    process_physical_footprint_bytes=(
                        PROCESS_PHYSICAL_FOOTPRINT_BYTES_CAP + 1
                    ),
                    process_physical_footprint_peak_bytes=(
                        PROCESS_PHYSICAL_FOOTPRINT_BYTES_CAP + 1
                    ),
                ),
                "physical cap",
            ),
            (replace(base, mlx_active_bytes=MLX_ACTIVE_BYTES_CAP + 1), "active"),
            (replace(base, mlx_active_bytes=None), "missing active"),
            (replace(base, mlx_cache_bytes=MLX_CACHE_BYTES_CAP + 1), "cache"),
            (replace(base, mlx_peak_bytes=MLX_PEAK_BYTES_CAP + 1), "peak"),
            (
                replace(
                    base,
                    process_footprint_bytes=(
                        PROCESS_PHYSICAL_FOOTPRINT_BYTES_CAP + 1
                    ),
                ),
                "RSS envelope",
            ),
            (
                replace(
                    base,
                    temporary_current_bytes=TEMPORARY_CURRENT_BYTES_CAP + 1,
                ),
                "temporary current",
            ),
            (
                replace(base, temporary_peak_bytes=TEMPORARY_PEAK_BYTES_CAP + 1),
                "temporary peak",
            ),
            (replace(base, mapped_virtual_bytes=1), "mapping"),
        )

        with SparseAdmittedFile() as model:
            for gauges, label in cases:
                with self.subTest(label=label):
                    runner = RunnerSpy(valid_result(gauges))
                    self.assert_slice_error(
                        "resource_limit",
                        run_inherited_model_slice,
                        slice_id=SLICE_ID,
                        requested_device="gpu",
                        allow_fallback=False,
                        model_fd=model.fileno(),
                        model_runner=runner,
                        pressure_func=lambda: "normal",
                    )
                    self.assertEqual(runner.calls, 1)


if __name__ == "__main__":
    unittest.main()

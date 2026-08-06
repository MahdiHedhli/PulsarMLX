"""Model-free contracts for the inherited real-router worker boundary."""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from pathlib import Path
import platform
import stat
import struct
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pulsar_mlx_worker.router as router
from pulsar_mlx_worker.__main__ import _dispatch, _runtime_protocol_error
from pulsar_mlx_worker.protocol import PROTOCOL_VERSION, ProtocolError, RequestEnvelope
from pulsar_mlx_worker.runtime import MemoryGauges


def _mlx_core_available() -> bool:
    try:
        return importlib.util.find_spec("mlx.core") is not None
    except ModuleNotFoundError:
        return False


def _model_stat(*, size: int = router._MODEL_FILE_BYTES, modified: int = 10):
    return SimpleNamespace(
        st_dev=1,
        st_ino=2,
        st_mode=stat.S_IFREG | 0o400,
        st_size=size,
        st_mtime_ns=modified,
        st_ctime_ns=modified,
    )


class _RunnerSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = object()

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class _ProtocolResult:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id

    def to_protocol_result(self) -> dict[str, object]:
        return {"router_case_id": self.case_id, "passed": True}


class _DispatchRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return _ProtocolResult(kwargs["router_case_id"])


class RealRouterInputIsolationTests(unittest.TestCase):
    def test_real_cases_select_only_the_frozen_public_input_fragment(self) -> None:
        calls: list[tuple[int, int]] = []

        def logged_pread(descriptor: int, count: int, offset: int) -> bytes:
            calls.append((offset, count))
            return os.pread(descriptor, count, offset)

        single = router._load_real_hidden_case(
            router.REAL_SINGLE_ROW_CASE_ID,
            1,
            pread_func=logged_pread,
        )
        batch = router._load_real_hidden_case(
            router.REAL_BATCH_CASE_ID,
            2,
            pread_func=logged_pread,
        )

        self.assertEqual(single, batch[:1])
        self.assertNotEqual(batch[0], batch[1])
        self.assertEqual(len(batch), 2)
        self.assertTrue(all(len(row) == router.HIDDEN_WIDTH for row in batch))
        self.assertEqual(router._canonical_f32le_sha256(batch), router._REAL_INPUT_SHA256)
        self.assertEqual(
            tuple(router._canonical_f32le_sha256((row,)) for row in batch),
            router._REAL_INPUT_ROW_SHA256,
        )
        self.assertTrue(all(math.isfinite(value) for row in batch for value in row))
        self.assertTrue(calls)
        for offset, count in calls:
            self.assertGreaterEqual(offset, router._REAL_INPUT_FRAGMENT_OFFSET)
            self.assertLessEqual(offset + count, router._REAL_INPUT_FRAGMENT_END)

        with router._REAL_FIXTURE_PATH.open("rb") as fixture:
            fixture.seek(router._REAL_INPUT_FRAGMENT_OFFSET)
            fragment = fixture.read(router._REAL_INPUT_FRAGMENT_BYTES)
            suffix = fixture.read(32)
        self.assertNotIn(b'"result"', fragment)
        self.assertNotIn(b'"oracle"', fragment)
        self.assertTrue(suffix.startswith(b',\n  "model"'))

    def test_input_fragment_mutation_and_wrong_case_fail_closed(self) -> None:
        with self.assertRaises(RouterError) as unknown:
            router._load_real_hidden_case("generated-qwen3moe-router-single-row-v1", 1)
        self.assertEqual(unknown.exception.code, "unsupported_operation")

        def changed_pread(descriptor: int, count: int, offset: int) -> bytes:
            payload = bytearray(os.pread(descriptor, count, offset))
            if payload:
                payload[-1] ^= 1
            return bytes(payload)

        with self.assertRaises(RouterError) as changed:
            router._load_real_hidden_case(
                router.REAL_SINGLE_ROW_CASE_ID,
                1,
                pread_func=changed_pread,
            )
        self.assertEqual(changed.exception.code, "invalid_byte_count")


RouterError = router.RouterError


class InheritedRouterTensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = b"\x00\x00\x00\x00" * router._WEIGHT_ELEMENT_COUNT
        cls.payload_sha256 = hashlib.sha256(cls.payload).hexdigest()

    def setUp(self) -> None:
        with router._REAL_ROUTER_CACHE_LOCK:
            router._REAL_ROUTER_CACHE = None

    def tearDown(self) -> None:
        with router._REAL_ROUTER_CACHE_LOCK:
            router._REAL_ROUTER_CACHE = None

    def reader(self, calls: list[tuple[int, int]], *, chunk_size: int | None = None):
        def pread(_descriptor: int, count: int, offset: int) -> bytes:
            calls.append((offset, count))
            start = offset - router._ROUTER_TENSOR_OFFSET
            admitted = count if chunk_size is None else min(count, chunk_size)
            return self.payload[start : start + admitted]

        return pread

    def resolve(
        self,
        *,
        force_read: bool,
        timing_profile: str,
        recorder=None,
        pread_func=None,
        fstat_func=lambda _fd: _model_stat(),
        getfl_func=lambda _fd, _command: os.O_RDONLY,
    ):
        with patch.object(router, "_ROUTER_TENSOR_SHA256", self.payload_sha256):
            return router._resolve_real_router_weights(
                model_fd=198,
                force_read=force_read,
                timing_profile=timing_profile,
                recorder=recorder,
                fstat_func=fstat_func,
                pread_func=pread_func or self.reader([]),
                getfl_func=getfl_func,
            )

    def test_exact_positional_read_retries_partials_and_decodes_f32(self) -> None:
        calls: list[tuple[int, int]] = []
        partial = self.reader(calls, chunk_size=4_093)
        interrupted = True

        def pread(descriptor: int, count: int, offset: int) -> bytes:
            nonlocal interrupted
            if interrupted:
                interrupted = False
                raise InterruptedError()
            return partial(descriptor, count, offset)

        snapshot, weights, bytes_read, cache_status = self.resolve(
            force_read=False,
            timing_profile="minimal",
            pread_func=pread,
        )
        self.assertEqual(snapshot.size, router._MODEL_FILE_BYTES)
        self.assertEqual(bytes_read, router._ROUTER_TENSOR_BYTES)
        self.assertEqual(cache_status, router._ROUTER_TENSOR_READ_AND_CACHED)
        self.assertEqual(len(weights), router.EXPERT_COUNT)
        self.assertTrue(all(len(row) == router.HIDDEN_WIDTH for row in weights))
        self.assertTrue(all(value == 0.0 for row in weights for value in row))
        self.assertGreater(len(calls), 1)
        self.assertEqual(calls[0][0], router._ROUTER_TENSOR_OFFSET)
        final_offset, final_count = calls[-1]
        final_length = min(final_count, 4_093)
        self.assertEqual(final_offset + final_length, router._ROUTER_TENSOR_END)

    def test_warm_cache_avoids_reads_and_costly_profile_forces_read(self) -> None:
        calls: list[tuple[int, int]] = []
        pread = self.reader(calls)
        first_snapshot, first_weights, first_bytes, first_cache_status = self.resolve(
            force_read=False,
            timing_profile="minimal",
            pread_func=pread,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(first_bytes, router._ROUTER_TENSOR_BYTES)
        self.assertEqual(
            first_cache_status,
            router._ROUTER_TENSOR_READ_AND_CACHED,
        )
        (
            second_snapshot,
            second_weights,
            second_bytes,
            second_cache_status,
        ) = self.resolve(
            force_read=False,
            timing_profile="minimal",
            pread_func=pread,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(second_bytes, 0)
        self.assertEqual(second_cache_status, router._ROUTER_TENSOR_CACHE_HIT)
        self.assertIs(first_weights, second_weights)
        self.assertEqual(first_snapshot, second_snapshot)

        clock_values = iter((10, 20, 30, 40))
        recorder = router.RouterTimingRecorder(clock_ns=lambda: next(clock_values))
        _, forced_weights, forced_bytes, forced_cache_status = self.resolve(
            force_read=True,
            timing_profile="costly",
            recorder=recorder,
            pread_func=pread,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(forced_bytes, router._ROUTER_TENSOR_BYTES)
        self.assertEqual(
            forced_cache_status,
            router._ROUTER_TENSOR_READ_AND_CACHED,
        )
        self.assertIsNot(first_weights, forced_weights)
        self.assertEqual(recorder._stages["file_io"].status, "observed")
        self.assertEqual(
            recorder._stages["storage_validation_f32_decode"].status,
            "observed",
        )

        stage = router.RouterTimingRecorder()
        _, _, stage_bytes, stage_cache_status = self.resolve(
            force_read=False,
            timing_profile="stage",
            recorder=stage,
            pread_func=pread,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(stage_bytes, 0)
        self.assertEqual(stage_cache_status, router._ROUTER_TENSOR_CACHE_HIT)
        self.assertEqual(stage._stages["file_io"].status, "unavailable")
        self.assertEqual(stage._stages["file_io"].reason, router._CACHE_FILE_IO_REASON)

    def test_descriptor_and_file_mutation_fail_before_execution(self) -> None:
        calls: list[tuple[int, int]] = []
        for label, fstat_func, getfl_func, code in (
            (
                "wrong size",
                lambda _fd: _model_stat(size=router._MODEL_FILE_BYTES - 1),
                lambda _fd, _command: os.O_RDONLY,
                "invalid_byte_count",
            ),
            (
                "writable descriptor",
                lambda _fd: _model_stat(),
                lambda _fd, _command: os.O_RDWR,
                "invalid_byte_count",
            ),
        ):
            with self.subTest(label=label):
                with self.assertRaises(RouterError) as caught:
                    self.resolve(
                        force_read=True,
                        timing_profile="minimal",
                        pread_func=self.reader(calls),
                        fstat_func=fstat_func,
                        getfl_func=getfl_func,
                    )
                self.assertEqual(caught.exception.code, code)
        self.assertEqual(calls, [])

        snapshots = iter((_model_stat(modified=10), _model_stat(modified=11)))
        with self.assertRaises(RouterError) as changed:
            self.resolve(
                force_read=True,
                timing_profile="minimal",
                pread_func=self.reader([]),
                fstat_func=lambda _fd: next(snapshots),
            )
        self.assertEqual(changed.exception.code, "invalid_byte_count")

        runner = _RunnerSpy()
        with self.assertRaises(RouterError) as wrapper_failure:
            router.run_committed_router(
                router_case_id=router.REAL_SINGLE_ROW_CASE_ID,
                requested_device="gpu",
                allow_fallback=False,
                router_runner=runner,
                fstat_func=lambda _fd: _model_stat(
                    size=router._MODEL_FILE_BYTES - 1
                ),
                getfl_func=lambda _fd, _command: os.O_RDONLY,
                environ={},
            )
        self.assertEqual(wrapper_failure.exception.code, "invalid_byte_count")
        self.assertEqual(runner.calls, [])

    def test_short_overlong_hash_and_nonfinite_payloads_are_rejected(self) -> None:
        with self.assertRaises(RouterError) as short:
            router._pread_exact_router_tensor(198, lambda *_args: b"")
        self.assertEqual(short.exception.code, "invalid_byte_count")

        with self.assertRaises(RouterError) as overlong:
            router._pread_exact_router_tensor(
                198,
                lambda _fd, count, _offset: b"x" * (count + 1),
            )
        self.assertEqual(overlong.exception.code, "invalid_byte_count")

        with self.assertRaises(RouterError) as wrong_hash:
            router._decode_real_router_tensor(self.payload)
        self.assertEqual(wrong_hash.exception.code, "invalid_byte_count")

        nonfinite = struct.pack("<f", float("nan")) + self.payload[4:]
        with patch.object(
            router,
            "_ROUTER_TENSOR_SHA256",
            hashlib.sha256(nonfinite).hexdigest(),
        ):
            with self.assertRaises(RouterError) as invalid_f32:
                router._decode_real_router_tensor(nonfinite)
        self.assertEqual(invalid_f32.exception.code, "invalid_dtype")


class RealRouterControlAndTimingTests(unittest.TestCase):
    def test_real_scope_rejects_synthetic_not_applicable_tensor_access(self) -> None:
        with self.assertRaises(RouterError) as caught:
            router._run_router_with_profile(
                router_case_id=router.REAL_SINGLE_ROW_CASE_ID,
                hidden_states=(),
                router_weights=(),
                requested_device="gpu",
                allow_fallback=False,
                case_scope=router.RouterCaseScope.REAL_CHECKPOINT,
                timing_profile="minimal",
            )
        self.assertEqual(caught.exception.code, "internal_worker_error")

    def test_dispatch_admits_real_ids_without_widening_three_field_request(self) -> None:
        for case_id in (router.REAL_SINGLE_ROW_CASE_ID, router.REAL_BATCH_CASE_ID):
            runner = _DispatchRunner()
            params = {
                "router_case_id": case_id,
                "device": "gpu",
                "allow_fallback": False,
            }
            result, shutdown = _dispatch(
                RequestEnvelope(PROTOCOL_VERSION, 9, "run_router", params),
                object(),
                probe_runner=lambda *_args, **_kwargs: None,
                router_runner=runner,
            )
            self.assertFalse(shutdown)
            self.assertEqual(result["router_case_id"], case_id)
            self.assertEqual(
                runner.calls,
                [{
                    "router_case_id": case_id,
                    "requested_device": "gpu",
                    "allow_fallback": False,
                }],
            )

        runner = _DispatchRunner()
        with self.assertRaises(ProtocolError):
            _dispatch(
                RequestEnvelope(
                    PROTOCOL_VERSION,
                    10,
                    "run_router",
                    {
                        "router_case_id": router.REAL_SINGLE_ROW_CASE_ID,
                        "device": "gpu",
                        "allow_fallback": False,
                        "timing_profile": "costly",
                    },
                ),
                object(),
                probe_runner=lambda *_args, **_kwargs: None,
                router_runner=runner,
            )
        self.assertEqual(runner.calls, [])

    def test_real_profile_is_process_configuration_not_request_data(self) -> None:
        snapshot = router._ModelFileSnapshot(
            1,
            2,
            stat.S_IFREG,
            router._MODEL_FILE_BYTES,
            3,
            4,
        )
        weights = ((0.0,) * router.HIDDEN_WIDTH,) * router.EXPERT_COUNT
        hidden = ((0.0,) * router.HIDDEN_WIDTH,)
        for profile in ("minimal", "costly", "stage"):
            with self.subTest(profile=profile):
                runner = _RunnerSpy()
                with (
                    patch.object(
                        router,
                        "_resolve_real_router_weights",
                        return_value=(
                            snapshot,
                            weights,
                            router._ROUTER_TENSOR_BYTES,
                            router._ROUTER_TENSOR_READ_AND_CACHED,
                        ),
                    ),
                    patch.object(router, "_load_real_hidden_case", return_value=hidden),
                    patch.object(router, "_snapshot_model_file", return_value=snapshot),
                ):
                    result = router.run_committed_router(
                        router_case_id=router.REAL_SINGLE_ROW_CASE_ID,
                        requested_device="gpu",
                        allow_fallback=False,
                        router_runner=runner,
                        environ={router._TIMING_PROFILE_ENV: profile},
                        clock_ns=lambda: 1,
                    )
                self.assertIs(result, runner.result)
                self.assertEqual(runner.calls[0]["timing_profile"], profile)
                self.assertIs(
                    runner.calls[0]["case_scope"],
                    router.RouterCaseScope.REAL_CHECKPOINT,
                )
                self.assertEqual(
                    runner.calls[0]["router_tensor_bytes_read"],
                    router._ROUTER_TENSOR_BYTES,
                )
                self.assertEqual(
                    runner.calls[0]["router_tensor_cache_status"],
                    router._ROUTER_TENSOR_READ_AND_CACHED,
                )

        with self.assertRaises(RouterError) as invalid:
            router.run_committed_router(
                router_case_id=router.REAL_SINGLE_ROW_CASE_ID,
                requested_device="gpu",
                allow_fallback=False,
                environ={router._TIMING_PROFILE_ENV: "/private/invalid"},
            )
        self.assertEqual(invalid.exception.code, "malformed_request")
        self.assertNotIn("private", invalid.exception.message)

    def test_exact_minimal_costly_and_stage_timing_schemas(self) -> None:
        observed = lambda value=1: router.RouterTimingStage("observed", duration_ns=value)
        unavailable = lambda reason="bounded_unavailable": router.RouterTimingStage(
            "unavailable", reason=reason
        )
        not_applicable = router.RouterTimingStage(
            "not_applicable", reason=router._F32_DEQUANTIZATION_REASON
        )

        minimal = router.RouterExecutionTiming(
            "minimally_instrumented",
            True,
            True,
            {
                "dequantization": not_applicable,
                "total_evaluated_router": observed(),
            },
        )
        self.assertEqual(frozenset(minimal.stages), router._MINIMAL_TIMING_STAGES)

        costly_stages = {
            "file_io": observed(2),
            "storage_validation_f32_decode": observed(3),
            "dequantization": not_applicable,
            "host_to_device": unavailable(router._INSEPARABLE_TRANSFER_REASON),
            "total_evaluated_router": observed(4),
            "end_to_end_router_command": observed(5),
        }
        costly = router.RouterExecutionTiming(
            "minimally_instrumented", True, True, costly_stages
        )
        self.assertEqual(frozenset(costly.stages), router._COSTLY_TIMING_STAGES)

        stage_stages = {
            "setup_admission": unavailable(router._SETUP_REASON),
            "file_io": unavailable(router._CACHE_FILE_IO_REASON),
            "storage_validation_f32_decode": unavailable(
                router._CACHE_DECODE_REASON
            ),
            "dequantization": not_applicable,
            "host_to_device": observed(5),
            "graph_construction": unavailable(router._LAZY_GRAPH_REASON),
            "compilation": unavailable(router._COMPILATION_REASON),
            "router_projection": observed(6),
            "top_k": observed(7),
            "normalization": observed(8),
            "total_evaluated_router": observed(9),
            "synchronized_readback": observed(10),
            "end_to_end_router_command": observed(11),
        }
        stage = router.RouterExecutionTiming(
            "stage_instrumented", True, True, stage_stages
        )
        self.assertEqual(frozenset(stage.stages), router._STAGE_TIMING_STAGES)

        incomplete = dict(stage_stages)
        del incomplete["synchronized_readback"]
        with self.assertRaises(RouterError):
            router.RouterExecutionTiming(
                "stage_instrumented", True, True, incomplete
            )

    def test_real_success_payload_retains_complete_output_and_execution_evidence(
        self,
    ) -> None:
        logits = (tuple(float(index) for index in range(router.EXPERT_COUNT)),)
        probabilities = (
            tuple(1.0 / router.EXPERT_COUNT for _ in range(router.EXPERT_COUNT)),
        )
        selected_ids = (tuple(range(router.TOP_K)),)
        selected_probabilities = (
            tuple(probabilities[0][index] for index in selected_ids[0]),
        )
        normalized_weights = (
            tuple(1.0 / router.TOP_K for _ in range(router.TOP_K)),
        )
        timing = router.RouterExecutionTiming(
            "minimally_instrumented",
            True,
            True,
            {
                "dequantization": router.RouterTimingStage(
                    "not_applicable",
                    reason=router._F32_DEQUANTIZATION_REASON,
                ),
                "total_evaluated_router": router.RouterTimingStage(
                    "observed",
                    duration_ns=17,
                ),
            },
        )
        result = router.RouterResult(
            router_case_id=router.REAL_SINGLE_ROW_CASE_ID,
            operation=router.ROUTER_OPERATION_ID,
            requested_device="gpu",
            selected_device="gpu",
            fallback_used=False,
            evaluated=True,
            synchronized=True,
            batch_size=1,
            hidden_width=router.HIDDEN_WIDTH,
            expert_count=router.EXPERT_COUNT,
            top_k=router.TOP_K,
            output_dtype=router.OUTPUT_DTYPE,
            logits=logits,
            full_probabilities=probabilities,
            selected_expert_ids=selected_ids,
            selected_probabilities=selected_probabilities,
            normalized_weights=normalized_weights,
            logits_f32le_sha256=router._canonical_f32le_sha256(logits),
            full_probabilities_f32le_sha256=router._canonical_f32le_sha256(
                probabilities
            ),
            selected_probabilities_f32le_sha256=router._canonical_f32le_sha256(
                selected_probabilities
            ),
            normalized_weights_f32le_sha256=router._canonical_f32le_sha256(
                normalized_weights
            ),
            router_tensor_bytes_read=router._ROUTER_TENSOR_BYTES,
            router_tensor_cache_status=router._ROUTER_TENSOR_READ_AND_CACHED,
            memory_gauges=MemoryGauges(1, 2, 3, 4, "task_info", "nominal"),
            timing=timing,
        )

        payload = result.to_protocol_result()

        self.assertEqual(payload["router_case_id"], router.REAL_SINGLE_ROW_CASE_ID)
        self.assertEqual(payload["operation"], router.ROUTER_OPERATION_ID)
        self.assertEqual(payload["requested_device"], "gpu")
        self.assertEqual(payload["selected_device"], "gpu")
        self.assertFalse(payload["fallback_used"])
        self.assertTrue(payload["evaluated"])
        self.assertTrue(payload["synchronized"])
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["logits"], [list(logits[0])])
        self.assertEqual(
            payload["full_probabilities"],
            [list(probabilities[0])],
        )
        self.assertEqual(payload["selected_expert_ids"], [list(selected_ids[0])])
        self.assertEqual(
            payload["selected_probabilities"],
            [list(selected_probabilities[0])],
        )
        self.assertEqual(
            payload["normalized_weights"],
            [list(normalized_weights[0])],
        )
        self.assertEqual(
            payload["router_tensor_bytes_read"],
            router._ROUTER_TENSOR_BYTES,
        )
        self.assertEqual(
            payload["router_tensor_cache_status"],
            router._ROUTER_TENSOR_READ_AND_CACHED,
        )
        for field in (
            "logits_f32le_sha256",
            "full_probabilities_f32le_sha256",
            "selected_probabilities_f32le_sha256",
            "normalized_weights_f32le_sha256",
        ):
            self.assertRegex(payload[field], r"^[0-9a-f]{64}$")
        self.assertEqual(
            payload["timing"],
            {
                "monotonic_clock": "perf_counter_ns",
                "instrumentation_mode": "minimally_instrumented",
                "evaluated": True,
                "synchronized": True,
                "stages": {
                    "dequantization": {
                        "status": "not_applicable",
                        "reason": router._F32_DEQUANTIZATION_REASON,
                    },
                    "total_evaluated_router": {
                        "status": "observed",
                        "duration_ns": 17,
                    },
                },
            },
        )
        self.assertEqual(
            payload["memory_gauges"],
            {
                "mlx_active_bytes": 1,
                "mlx_cache_bytes": 2,
                "mlx_peak_bytes": 3,
                "process_footprint_bytes": 4,
                "process_footprint_source": "task_info",
                "system_pressure": "nominal",
                "reported_summed_total_bytes": None,
            },
        )

    def test_real_worker_failure_is_stable_bounded_and_private_path_free(
        self,
    ) -> None:
        private_path = "/" + "Users/private/checkpoint.gguf"
        error = _runtime_protocol_error(
            RouterError(
                "evaluation_failed",
                f"MLX evaluation failed at {private_path}",
            )
        )

        self.assertEqual(error.code, "evaluation_failed")
        self.assertEqual(error.message, "runtime contract validation failed")
        self.assertLessEqual(len(error.message), 512)
        self.assertNotIn("/Users/", error.message)
        self.assertFalse(error.retryable)
        self.assertEqual(error.details, {})


@unittest.skipUnless(
    platform.system() == "Darwin"
    and platform.machine() == "arm64"
    and _mlx_core_available(),
    "evaluated real-router profile fixtures require pinned MLX on Apple Silicon",
)
class NativeRealRouterProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hidden = router._load_real_hidden_case(
            router.REAL_SINGLE_ROW_CASE_ID,
            1,
        )
        tail = (0.0,) * (router.HIDDEN_WIDTH - 1)
        cls.weights = tuple(
            (float(expert_id) * 0.25, *tail)
            for expert_id in range(router.EXPERT_COUNT)
        )

    def execute(self, profile: str):
        recorder = None
        started = None
        if profile != "minimal":
            recorder = router.RouterTimingRecorder()
            started = time.perf_counter_ns()
            if profile == "stage":
                recorder.record_unavailable(
                    stage="setup_admission",
                    reason=router._SETUP_REASON,
                )
                recorder.record_unavailable(
                    stage="file_io",
                    reason=router._CACHE_FILE_IO_REASON,
                )
                recorder.record_unavailable(
                    stage="storage_validation_f32_decode",
                    reason=router._CACHE_DECODE_REASON,
                )
            else:
                recorder.record_observed(stage="file_io", duration_ns=1)
                recorder.record_observed(
                    stage="storage_validation_f32_decode", duration_ns=1
                )
            recorder.record_not_applicable(
                stage="dequantization",
                reason=router._F32_DEQUANTIZATION_REASON,
            )
            if profile == "costly":
                recorder.record_unavailable(
                    stage="host_to_device",
                    reason=router._INSEPARABLE_TRANSFER_REASON,
                )
        return router._run_router_with_profile(
            router_case_id=router.REAL_SINGLE_ROW_CASE_ID,
            hidden_states=self.hidden,
            router_weights=self.weights,
            requested_device="gpu",
            allow_fallback=False,
            case_scope=router.RouterCaseScope.REAL_CHECKPOINT,
            timing_profile=profile,
            router_tensor_bytes_read=(
                router._ROUTER_TENSOR_BYTES if profile == "costly" else 0
            ),
            router_tensor_cache_status=(
                router._ROUTER_TENSOR_READ_AND_CACHED
                if profile == "costly"
                else router._ROUTER_TENSOR_CACHE_HIT
            ),
            timing_recorder=recorder,
            end_to_end_started_ns=started,
        )

    def test_all_profiles_evaluate_the_same_gpu_router_result(self) -> None:
        results = {profile: self.execute(profile) for profile in ("minimal", "costly", "stage")}
        expected_ids = tuple(range(127, 119, -1))
        for profile, result in results.items():
            with self.subTest(profile=profile):
                self.assertTrue(result.passed)
                self.assertEqual(result.selected_expert_ids, (expected_ids,))
                self.assertEqual(
                    frozenset(result.timing.stages),
                    {
                        "minimal": router._MINIMAL_TIMING_STAGES,
                        "costly": router._COSTLY_TIMING_STAGES,
                        "stage": router._STAGE_TIMING_STAGES,
                    }[profile],
                )
        self.assertEqual(results["minimal"].logits, results["costly"].logits)
        self.assertEqual(results["minimal"].logits, results["stage"].logits)
        self.assertEqual(
            results["minimal"].normalized_weights,
            results["stage"].normalized_weights,
        )


if __name__ == "__main__":
    unittest.main()

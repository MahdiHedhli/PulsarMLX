"""Contract tests for the bounded complete-router MLX operation.

The inputs below are generated, model-free float32 values with the exact
Feature 002 router dimensions.  Their one-hot hidden rows make every expected
logit independently reviewable from the corresponding weight coefficient;
the scalar softmax oracle in this module does not call MLX or worker code.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import struct
import unittest

from pulsar_mlx_worker.__main__ import _dispatch
from pulsar_mlx_worker.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    RequestDecoder,
    RequestEnvelope,
)
from pulsar_mlx_worker.router import (
    RouterError,
    run_committed_router,
    run_router,
)
from pulsar_mlx_worker.runtime import discover_runtime


SINGLE_ROW_CASE_ID = "generated-qwen3moe-router-single-row-v1"
BOUNDED_BATCH_CASE_ID = "generated-qwen3moe-router-two-row-v1"
HIDDEN_WIDTH = 2_048
EXPERT_COUNT = 128
TOP_K = 8
LOGIT_ABSOLUTE_TOLERANCE = 5e-4
LOGIT_RELATIVE_TOLERANCE = 5e-4
PROBABILITY_ABSOLUTE_TOLERANCE = 1e-6
PROBABILITY_RELATIVE_TOLERANCE = 1e-6

EXPECTED_TOP8_IDS = (
    (83, 38, 121, 76, 31, 114, 69, 24),
    (24, 123, 94, 65, 36, 7, 106, 77),
)


def _row_zero_logit(expert_id: int) -> float:
    return (((expert_id * 37) % EXPERT_COUNT) - 64) / 16.0


def _row_one_logit(expert_id: int) -> float:
    return (((expert_id * 53 + 7) % EXPERT_COUNT) - 64) / 16.0


def _generated_router_weights() -> tuple[tuple[float, ...], ...]:
    """Build expert-major ``[128, 2048]`` F32-compatible test weights."""

    zero_tail = (0.0,) * (HIDDEN_WIDTH - 2)
    return tuple(
        (
            _row_zero_logit(expert_id),
            _row_one_logit(expert_id),
            *zero_tail,
        )
        for expert_id in range(EXPERT_COUNT)
    )


def _one_hot_hidden(column: int) -> tuple[float, ...]:
    values = [0.0] * HIDDEN_WIDTH
    values[column] = 1.0
    return tuple(values)


def _scalar_softmax(logits: tuple[float, ...]) -> tuple[float, ...]:
    maximum = max(logits)
    exponentials = tuple(math.exp(value - maximum) for value in logits)
    denominator = sum(exponentials)
    return tuple(value / denominator for value in exponentials)


ROUTER_WEIGHTS = _generated_router_weights()
SINGLE_ROW_HIDDEN = (_one_hot_hidden(0),)
BOUNDED_BATCH_HIDDEN = (_one_hot_hidden(0), _one_hot_hidden(1))
EXPECTED_LOGITS = (
    tuple(_row_zero_logit(expert_id) for expert_id in range(EXPERT_COUNT)),
    tuple(_row_one_logit(expert_id) for expert_id in range(EXPERT_COUNT)),
)
EXPECTED_PROBABILITIES = tuple(_scalar_softmax(row) for row in EXPECTED_LOGITS)
EXPECTED_SELECTED_PROBABILITIES = tuple(
    tuple(probabilities[expert_id] for expert_id in selected_ids)
    for probabilities, selected_ids in zip(
        EXPECTED_PROBABILITIES,
        EXPECTED_TOP8_IDS,
    )
)
EXPECTED_NORMALIZED_WEIGHTS = tuple(
    tuple(value / sum(selected) for value in selected)
    for selected in EXPECTED_SELECTED_PROBABILITIES
)


def _canonical_f32le_sha256(rows) -> str:
    digest = hashlib.sha256()
    for row in rows:
        for value in row:
            digest.update(struct.pack("<f", value))
    return digest.hexdigest()


class MlxEventSpy:
    """Delegate to native MLX while recording the explicit GPU boundary."""

    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.events: list[tuple[str, object]] = []

    def stream(self, device):
        self.events.append(("stream", device))
        return self.delegate.stream(device)

    def eval(self, *arrays):
        self.events.append(("eval", len(arrays)))
        return self.delegate.eval(*arrays)

    def synchronize(self, device):
        self.events.append(("synchronize", device))
        return self.delegate.synchronize(device)

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)


class SchedulingTrap:
    """Fail if a rejected device or fallback request touches MLX."""

    def __init__(self) -> None:
        self.access_count = 0

    def __getattr__(self, name: str):
        self.access_count += 1
        raise AssertionError(f"MLX was accessed before validation: {name}")


class _DeviceTargetStub:
    def __init__(self, name: str) -> None:
        self.name = name


class _MetalAvailabilityStub:
    def __init__(self, available: bool) -> None:
        self.available = available

    def is_available(self) -> bool:
        return self.available


class RuntimeEvidenceTrap:
    """Expose runtime device evidence but reject any tensor scheduling."""

    def __init__(self, *, target_name: str, metal_available: bool) -> None:
        self.gpu = _DeviceTargetStub(target_name)
        self.metal = _MetalAvailabilityStub(metal_available)
        self.device_info_calls = 0
        self.stream_calls = 0

    def device_info(self, device) -> dict[str, object]:
        self.device_info_calls += 1
        if device is not self.gpu:
            raise AssertionError("router described a device other than its target")
        return {
            "device_name": "Generated test GPU",
            "architecture": "generated-test-architecture",
            "memory_size": 1,
        }

    def stream(self, _device):
        self.stream_calls += 1
        raise AssertionError("invalid runtime evidence reached tensor scheduling")


class CoreRunnerSpy:
    """Capture the internally resolved committed arrays without MLX."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = object()

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class ProtocolResultStub:
    def __init__(self, router_case_id: str) -> None:
        self.router_case_id = router_case_id

    def to_protocol_result(self) -> dict[str, object]:
        return {"router_case_id": self.router_case_id, "passed": True}


class DispatchRunnerSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return ProtocolResultStub(kwargs["router_case_id"])


class RouterControlContractTests(unittest.TestCase):
    def dispatch(self, params: dict[str, object], runner):
        request = RequestEnvelope(
            protocol=PROTOCOL_VERSION,
            request_id=11,
            op="run_router",
            params=params,
        )
        result, should_shutdown = _dispatch(
            request,
            object(),
            probe_runner=lambda *_args, **_kwargs: None,
            router_runner=runner,
        )
        self.assertFalse(should_shutdown)
        return result

    def test_control_request_is_registered_exact_and_contains_no_values(self) -> None:
        params = {
            "router_case_id": SINGLE_ROW_CASE_ID,
            "device": "gpu",
            "allow_fallback": False,
        }
        encoded = json.dumps(
            {
                "protocol": PROTOCOL_VERSION,
                "request_id": 11,
                "op": "run_router",
                "params": params,
            },
            separators=(",", ":"),
        ).encode() + b"\n"
        request = RequestDecoder().feed(encoded)[0]

        self.assertEqual(request.params, params)
        for forbidden in (
            b"model_path",
            b"hidden_states",
            b"weights",
            b"oracle",
            b"sha256",
            b"warmup",
            b"measurement",
        ):
            self.assertNotIn(forbidden, encoded)

        runner = DispatchRunnerSpy()
        result = self.dispatch(params, runner)
        self.assertEqual(result, {"router_case_id": SINGLE_ROW_CASE_ID, "passed": True})
        self.assertEqual(
            runner.calls,
            [
                {
                    "router_case_id": SINGLE_ROW_CASE_ID,
                    "requested_device": "gpu",
                    "allow_fallback": False,
                }
            ],
        )

    def test_invalid_control_fields_precede_router_resolution(self) -> None:
        base = {
            "router_case_id": SINGLE_ROW_CASE_ID,
            "device": "gpu",
            "allow_fallback": False,
        }
        cases = (
            ({**base, "model_path": "/private/model.gguf"}, "malformed_request"),
            ({**base, "hidden_states": [[1.0]]}, "malformed_request"),
            ({**base, "router_case_id": "different-router"}, "unsupported_operation"),
            ({**base, "router_case_id": 7}, "malformed_request"),
            ({**base, "device": "cpu"}, "device_unavailable"),
            ({**base, "allow_fallback": True}, "device_unavailable"),
            ({**base, "allow_fallback": 0}, "malformed_request"),
        )
        for params, expected_code in cases:
            with self.subTest(params=params):
                runner = DispatchRunnerSpy()
                with self.assertRaises(ProtocolError) as caught:
                    self.dispatch(params, runner)
                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(runner.calls, [])

    def test_committed_cases_reconstruct_only_bounded_generated_inputs(self) -> None:
        for case_id, expected_rows in (
            (SINGLE_ROW_CASE_ID, 1),
            (BOUNDED_BATCH_CASE_ID, 2),
        ):
            with self.subTest(case_id=case_id):
                runner = CoreRunnerSpy()
                result = run_committed_router(
                    router_case_id=case_id,
                    requested_device="gpu",
                    allow_fallback=False,
                    router_runner=runner,
                )
                self.assertIs(result, runner.result)
                self.assertEqual(len(runner.calls), 1)
                call = runner.calls[0]
                self.assertEqual(call["router_case_id"], case_id)
                self.assertEqual(call["requested_device"], "gpu")
                self.assertFalse(call["allow_fallback"])
                hidden_states = call["hidden_states"]
                router_weights = call["router_weights"]
                self.assertEqual(len(hidden_states), expected_rows)
                self.assertTrue(
                    all(len(row) == HIDDEN_WIDTH for row in hidden_states)
                )
                self.assertEqual(len(router_weights), EXPERT_COUNT)
                self.assertTrue(
                    all(len(row) == HIDDEN_WIDTH for row in router_weights)
                )
                self.assertEqual(hidden_states[0][0], 1.0)
                self.assertEqual(sum(hidden_states[0]), 1.0)
                if expected_rows == 2:
                    self.assertEqual(hidden_states[1][1], 1.0)
                    self.assertEqual(sum(hidden_states[1]), 1.0)
                for expert_id in range(EXPERT_COUNT):
                    self.assertEqual(
                        router_weights[expert_id][0],
                        _row_zero_logit(expert_id),
                    )
                    self.assertEqual(
                        router_weights[expert_id][1],
                        _row_one_logit(expert_id),
                    )
                    self.assertTrue(
                        all(value == 0.0 for value in router_weights[expert_id][2:])
                    )


class RouterAdmissionContractTests(unittest.TestCase):
    def test_explicit_gpu_without_fallback_is_required_before_mlx(self) -> None:
        for label, requested_device, allow_fallback in (
            ("CPU request", "cpu", False),
            ("fallback request", "gpu", True),
        ):
            with self.subTest(label=label):
                trap = SchedulingTrap()
                with self.assertRaises(RouterError) as caught:
                    run_router(
                        router_case_id=SINGLE_ROW_CASE_ID,
                        hidden_states=SINGLE_ROW_HIDDEN,
                        router_weights=ROUTER_WEIGHTS,
                        requested_device=requested_device,
                        allow_fallback=allow_fallback,
                        mx_module=trap,
                    )
                self.assertEqual(caught.exception.code, "device_unavailable")
                self.assertLessEqual(len(caught.exception.message), 512)
                self.assertEqual(trap.access_count, 0)

    def test_runtime_gpu_evidence_precedes_tensor_scheduling(self) -> None:
        for label, target_name, metal_available in (
            ("non-GPU target", "cpu", True),
            ("Metal unavailable", "gpu", False),
        ):
            with self.subTest(label=label):
                trap = RuntimeEvidenceTrap(
                    target_name=target_name,
                    metal_available=metal_available,
                )
                with self.assertRaises(RouterError) as caught:
                    run_router(
                        router_case_id=SINGLE_ROW_CASE_ID,
                        hidden_states=SINGLE_ROW_HIDDEN,
                        router_weights=ROUTER_WEIGHTS,
                        requested_device="gpu",
                        allow_fallback=False,
                        mx_module=trap,
                    )
                self.assertEqual(caught.exception.code, "device_unavailable")
                self.assertEqual(trap.device_info_calls, 1)
                self.assertEqual(trap.stream_calls, 0)


@unittest.skipUnless(
    platform.system() == "Darwin" and platform.machine() == "arm64",
    "evaluated Feature 002 router tests require native Apple Silicon",
)
class RouterExecutionContractTests(unittest.TestCase):
    def test_runtime_advertises_additive_router_operation(self) -> None:
        identity = discover_runtime()
        self.assertIn("run_router", identity.capabilities)
        for inherited_operation in (
            "health",
            "tensor_probe",
            "run_fixture",
            "run_synthetic_moe",
            "shutdown",
        ):
            self.assertIn(inherited_operation, identity.capabilities)

    def assert_numeric_matrix(
        self,
        actual,
        expected: tuple[tuple[float, ...], ...],
        *,
        absolute_tolerance: float,
        relative_tolerance: float,
    ) -> None:
        self.assertEqual(len(actual), len(expected))
        for row_index, (actual_row, expected_row) in enumerate(
            zip(actual, expected)
        ):
            self.assertEqual(len(actual_row), len(expected_row))
            for column_index, (actual_value, expected_value) in enumerate(
                zip(actual_row, expected_row)
            ):
                self.assertTrue(math.isfinite(actual_value))
                admitted_error = absolute_tolerance + (
                    relative_tolerance * abs(expected_value)
                )
                self.assertLessEqual(
                    abs(actual_value - expected_value),
                    admitted_error,
                    f"numeric mismatch at [{row_index}][{column_index}]",
                )

    def assert_evaluated_gpu_boundary(self, result, mx: MlxEventSpy) -> None:
        self.assertEqual(result.requested_device, "gpu")
        self.assertEqual(result.selected_device, "gpu")
        self.assertFalse(result.fallback_used)
        self.assertTrue(result.evaluated)
        self.assertTrue(result.synchronized)

        event_names = [name for name, _ in mx.events]
        self.assertIn("stream", event_names)
        self.assertIn("eval", event_names)
        self.assertIn("synchronize", event_names)
        self.assertLess(event_names.index("stream"), event_names.index("eval"))
        self.assertLess(
            event_names.index("eval"),
            event_names.index("synchronize"),
        )
        evaluated_count = next(
            value for name, value in mx.events if name == "eval"
        )
        self.assertGreaterEqual(
            evaluated_count,
            5,
            "all router outputs must be evaluated before synchronization",
        )

    def assert_complete_router_result(
        self,
        result,
        *,
        case_id: str,
        expected_rows: int,
    ) -> None:
        self.assertEqual(result.router_case_id, case_id)
        self.assertEqual(result.operation, "complete_router_projection_topk")
        self.assertEqual(result.batch_size, expected_rows)
        self.assertEqual(result.hidden_width, HIDDEN_WIDTH)
        self.assertEqual(result.expert_count, EXPERT_COUNT)
        self.assertEqual(result.top_k, TOP_K)
        self.assertEqual(result.output_dtype, "float32")

        self.assertEqual(len(result.logits), expected_rows)
        self.assertEqual(len(result.full_probabilities), expected_rows)
        self.assertEqual(len(result.selected_expert_ids), expected_rows)
        self.assertEqual(len(result.selected_probabilities), expected_rows)
        self.assertEqual(len(result.normalized_weights), expected_rows)

        for row in result.logits:
            self.assertEqual(len(row), EXPERT_COUNT)
        for row in result.full_probabilities:
            self.assertEqual(len(row), EXPERT_COUNT)
            self.assertAlmostEqual(
                sum(row),
                1.0,
                delta=PROBABILITY_ABSOLUTE_TOLERANCE,
            )
        for row in result.selected_expert_ids:
            self.assertEqual(len(row), TOP_K)
            self.assertEqual(len(set(row)), TOP_K)
            self.assertTrue(all(0 <= expert_id < EXPERT_COUNT for expert_id in row))
        for row in result.selected_probabilities:
            self.assertEqual(len(row), TOP_K)
            self.assertLess(
                sum(row),
                1.0,
                "selected probabilities must remain pre-renormalization values",
            )
        for row in result.normalized_weights:
            self.assertEqual(len(row), TOP_K)
            self.assertTrue(all(weight >= 0.0 for weight in row))
            self.assertAlmostEqual(
                sum(row),
                1.0,
                delta=PROBABILITY_ABSOLUTE_TOLERANCE,
            )

        for probabilities, selected_ids, selected, normalized in zip(
            result.full_probabilities,
            result.selected_expert_ids,
            result.selected_probabilities,
            result.normalized_weights,
        ):
            selected_sum = sum(selected)
            for rank, expert_id in enumerate(selected_ids):
                self.assertAlmostEqual(
                    selected[rank],
                    probabilities[expert_id],
                    delta=PROBABILITY_ABSOLUTE_TOLERANCE,
                )
                self.assertAlmostEqual(
                    normalized[rank],
                    selected[rank] / selected_sum,
                    delta=PROBABILITY_ABSOLUTE_TOLERANCE,
                )

        self.assertEqual(
            result.logits_f32le_sha256,
            _canonical_f32le_sha256(result.logits),
        )
        self.assertEqual(
            result.full_probabilities_f32le_sha256,
            _canonical_f32le_sha256(result.full_probabilities),
        )
        self.assertEqual(
            result.selected_probabilities_f32le_sha256,
            _canonical_f32le_sha256(result.selected_probabilities),
        )
        self.assertEqual(
            result.normalized_weights_f32le_sha256,
            _canonical_f32le_sha256(result.normalized_weights),
        )
        gauges = result.memory_gauges.to_protocol_result()
        self.assertEqual(
            set(gauges),
            {
                "mlx_active_bytes",
                "mlx_cache_bytes",
                "mlx_peak_bytes",
                "process_footprint_bytes",
                "process_footprint_source",
                "system_pressure",
                "reported_summed_total_bytes",
            },
        )
        self.assertIsNone(gauges["reported_summed_total_bytes"])
        if (
            gauges["mlx_active_bytes"] is not None
            and gauges["mlx_peak_bytes"] is not None
        ):
            self.assertGreaterEqual(
                gauges["mlx_peak_bytes"],
                gauges["mlx_active_bytes"],
            )

    def run_generated_case(self, case_id: str, hidden_states):
        import mlx.core as native_mx

        mx = MlxEventSpy(native_mx)
        result = run_router(
            router_case_id=case_id,
            hidden_states=hidden_states,
            router_weights=ROUTER_WEIGHTS,
            requested_device="gpu",
            allow_fallback=False,
            mx_module=mx,
        )
        return result, mx

    def test_single_row_evaluates_complete_router_on_explicit_gpu(self) -> None:
        result, mx = self.run_generated_case(
            SINGLE_ROW_CASE_ID,
            SINGLE_ROW_HIDDEN,
        )

        self.assert_evaluated_gpu_boundary(result, mx)
        self.assert_complete_router_result(
            result,
            case_id=SINGLE_ROW_CASE_ID,
            expected_rows=1,
        )
        self.assertEqual(
            tuple(tuple(row) for row in result.selected_expert_ids),
            EXPECTED_TOP8_IDS[:1],
        )
        self.assert_numeric_matrix(
            result.logits,
            EXPECTED_LOGITS[:1],
            absolute_tolerance=LOGIT_ABSOLUTE_TOLERANCE,
            relative_tolerance=LOGIT_RELATIVE_TOLERANCE,
        )
        self.assert_numeric_matrix(
            result.full_probabilities,
            EXPECTED_PROBABILITIES[:1],
            absolute_tolerance=PROBABILITY_ABSOLUTE_TOLERANCE,
            relative_tolerance=PROBABILITY_RELATIVE_TOLERANCE,
        )
        self.assert_numeric_matrix(
            result.selected_probabilities,
            EXPECTED_SELECTED_PROBABILITIES[:1],
            absolute_tolerance=PROBABILITY_ABSOLUTE_TOLERANCE,
            relative_tolerance=PROBABILITY_RELATIVE_TOLERANCE,
        )
        self.assert_numeric_matrix(
            result.normalized_weights,
            EXPECTED_NORMALIZED_WEIGHTS[:1],
            absolute_tolerance=PROBABILITY_ABSOLUTE_TOLERANCE,
            relative_tolerance=PROBABILITY_RELATIVE_TOLERANCE,
        )

    def test_equal_probabilities_use_ascending_expert_ids(self) -> None:
        tied_hidden = ((0.0,) * HIDDEN_WIDTH,)
        result, mx = self.run_generated_case(
            SINGLE_ROW_CASE_ID,
            tied_hidden,
        )

        self.assert_evaluated_gpu_boundary(result, mx)
        self.assert_complete_router_result(
            result,
            case_id=SINGLE_ROW_CASE_ID,
            expected_rows=1,
        )
        self.assertEqual(result.selected_expert_ids, (tuple(range(TOP_K)),))
        self.assertTrue(
            all(
                probability == result.selected_probabilities[0][0]
                for probability in result.selected_probabilities[0]
            )
        )

    def test_two_row_batch_is_complete_and_deterministic(self) -> None:
        first, first_mx = self.run_generated_case(
            BOUNDED_BATCH_CASE_ID,
            BOUNDED_BATCH_HIDDEN,
        )
        second, second_mx = self.run_generated_case(
            BOUNDED_BATCH_CASE_ID,
            BOUNDED_BATCH_HIDDEN,
        )

        for result, mx in ((first, first_mx), (second, second_mx)):
            self.assert_evaluated_gpu_boundary(result, mx)
            self.assert_complete_router_result(
                result,
                case_id=BOUNDED_BATCH_CASE_ID,
                expected_rows=2,
            )
            self.assertEqual(
                tuple(tuple(row) for row in result.selected_expert_ids),
                EXPECTED_TOP8_IDS,
            )
            self.assert_numeric_matrix(
                result.logits,
                EXPECTED_LOGITS,
                absolute_tolerance=LOGIT_ABSOLUTE_TOLERANCE,
                relative_tolerance=LOGIT_RELATIVE_TOLERANCE,
            )
            self.assert_numeric_matrix(
                result.full_probabilities,
                EXPECTED_PROBABILITIES,
                absolute_tolerance=PROBABILITY_ABSOLUTE_TOLERANCE,
                relative_tolerance=PROBABILITY_RELATIVE_TOLERANCE,
            )
            self.assert_numeric_matrix(
                result.selected_probabilities,
                EXPECTED_SELECTED_PROBABILITIES,
                absolute_tolerance=PROBABILITY_ABSOLUTE_TOLERANCE,
                relative_tolerance=PROBABILITY_RELATIVE_TOLERANCE,
            )
            self.assert_numeric_matrix(
                result.normalized_weights,
                EXPECTED_NORMALIZED_WEIGHTS,
                absolute_tolerance=PROBABILITY_ABSOLUTE_TOLERANCE,
                relative_tolerance=PROBABILITY_RELATIVE_TOLERANCE,
            )

        self.assertEqual(first.logits, second.logits)
        self.assertEqual(first.full_probabilities, second.full_probabilities)
        self.assertEqual(first.selected_expert_ids, second.selected_expert_ids)
        self.assertEqual(first.selected_probabilities, second.selected_probabilities)
        self.assertEqual(first.normalized_weights, second.normalized_weights)


if __name__ == "__main__":
    unittest.main()

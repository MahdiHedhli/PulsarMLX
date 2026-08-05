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
from pathlib import Path
import platform
import struct
import tempfile
import unittest
from unittest.mock import patch

import pulsar_mlx_worker.router as router_module
from pulsar_mlx_worker.__main__ import _dispatch
from pulsar_mlx_worker.protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    RequestDecoder,
    RequestEnvelope,
)
from pulsar_mlx_worker.router import (
    RouterCaseScope,
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
SYNTHETIC_TIE_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "research"
    / "router-v1"
    / "synthetic-tie.json"
)


def _synthetic_tie_case(kind: str) -> dict[str, object]:
    document = json.loads(SYNTHETIC_TIE_FIXTURE_PATH.read_bytes())
    if (
        document.get("schema") != "pulsarmlx.fixture.router-synthetic-tie"
        or document.get("provenance")
        != {
            "evidence_level": "synthetic_tie_fixture_only",
            "external_checkpoint_access_required": False,
            "kind": "synthetic_generated",
            "model_free": True,
            "proves_real_checkpoint_routing": False,
        }
    ):
        raise AssertionError("synthetic tie fixture provenance is invalid")
    matches = [case for case in document.get("cases", []) if case.get("kind") == kind]
    if len(matches) != 1:
        raise AssertionError(f"synthetic tie fixture must contain one {kind} case")
    case = matches[0]
    if case.get("provenance") != "synthetic_generated_model_free":
        raise AssertionError("synthetic tie case provenance is invalid")
    return case


def _fixture_matrix(case: dict[str, object], field: str) -> tuple[tuple, ...]:
    return tuple(tuple(row) for row in case[field])


def _weights_for_fixture_logits(case: dict[str, object]) -> tuple[tuple[float, ...], ...]:
    logits = _fixture_matrix(case, "logits")
    if len(logits) != 1 or len(logits[0]) != EXPERT_COUNT:
        raise AssertionError("synthetic tie fixture logits have an invalid shape")
    zero_tail = (0.0,) * (HIDDEN_WIDTH - 1)
    return tuple((float(value), *zero_tail) for value in logits[0])


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


def _replace_matrix_value(matrix, row_index: int, column_index: int, value):
    """Return a bounded matrix copy with one deliberately malformed value."""

    rows = list(matrix)
    row = list(rows[row_index])
    row[column_index] = value
    rows[row_index] = tuple(row)
    return tuple(rows)


def _json_bytes(document: object) -> bytes:
    """Encode a temporary mutated fixture deterministically for admission tests."""

    return (
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


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
    """Fail if any rejected router input touches an MLX surface."""

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

    def test_every_malformed_control_field_precedes_router_runner(self) -> None:
        base = {
            "router_case_id": SINGLE_ROW_CASE_ID,
            "device": "gpu",
            "allow_fallback": False,
        }
        malformed_cases = (
            ("missing case ID", {"device": "gpu", "allow_fallback": False}),
            (
                "missing device",
                {
                    "router_case_id": SINGLE_ROW_CASE_ID,
                    "allow_fallback": False,
                },
            ),
            (
                "missing fallback",
                {"router_case_id": SINGLE_ROW_CASE_ID, "device": "gpu"},
            ),
            ("extra field", {**base, "top_k": TOP_K}),
            ("null case ID", {**base, "router_case_id": None}),
            ("boolean case ID", {**base, "router_case_id": False}),
            ("list case ID", {**base, "router_case_id": []}),
            ("empty case ID", {**base, "router_case_id": ""}),
            ("spaced case ID", {**base, "router_case_id": " bad-id"}),
            ("path-like case ID", {**base, "router_case_id": "bad/id"}),
            ("overlong case ID", {**base, "router_case_id": "x" * 129}),
            ("null device", {**base, "device": None}),
            ("boolean device", {**base, "device": True}),
            ("integer device", {**base, "device": 1}),
            ("null fallback", {**base, "allow_fallback": None}),
            ("integer fallback", {**base, "allow_fallback": 0}),
            ("string fallback", {**base, "allow_fallback": "false"}),
        )
        for label, params in malformed_cases:
            with self.subTest(label=label):
                runner = DispatchRunnerSpy()
                with self.assertRaises(ProtocolError) as caught:
                    self.dispatch(params, runner)
                self.assertEqual(caught.exception.code, "malformed_request")
                self.assertLessEqual(len(caught.exception.message), 512)
                self.assertEqual(runner.calls, [])

    def test_invalid_identity_and_fallback_precede_router_runner(self) -> None:
        base = {
            "router_case_id": SINGLE_ROW_CASE_ID,
            "device": "gpu",
            "allow_fallback": False,
        }
        cases = (
            (
                "uncommitted stable case",
                {**base, "router_case_id": "generated-router-unknown-v1"},
                "unsupported_operation",
            ),
            (
                "CPU device",
                {**base, "device": "cpu"},
                "device_unavailable",
            ),
            (
                "fallback enabled",
                {**base, "allow_fallback": True},
                "device_unavailable",
            ),
        )
        for label, params, expected_code in cases:
            with self.subTest(label=label):
                runner = DispatchRunnerSpy()
                with self.assertRaises(ProtocolError) as caught:
                    self.dispatch(params, runner)
                self.assertEqual(caught.exception.code, expected_code)
                self.assertLessEqual(len(caught.exception.message), 512)
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
                self.assertIs(
                    call["case_scope"],
                    RouterCaseScope.SYNTHETIC_FIXTURE,
                )
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
    def assert_rejected_before_mlx(
        self,
        expected_code: str,
        *,
        router_case_id: object = SINGLE_ROW_CASE_ID,
        hidden_states: object = SINGLE_ROW_HIDDEN,
        router_weights: object = ROUTER_WEIGHTS,
        requested_device: object = "gpu",
        allow_fallback: object = False,
        case_scope: object = RouterCaseScope.SYNTHETIC_FIXTURE,
    ) -> None:
        trap = SchedulingTrap()
        with self.assertRaises(RouterError) as caught:
            run_router(
                router_case_id=router_case_id,
                hidden_states=hidden_states,
                router_weights=router_weights,
                requested_device=requested_device,
                allow_fallback=allow_fallback,
                case_scope=case_scope,
                mx_module=trap,
            )
        self.assertEqual(caught.exception.code, expected_code)
        self.assertLessEqual(len(caught.exception.message), 512)
        self.assertEqual(
            trap.access_count,
            0,
            "rejected router input reached MLX array construction or scheduling",
        )

    def assert_committed_fixture_rejected_before_runner(
        self,
        expected_code: str,
        *,
        manifest_payload: bytes,
        hidden_payload: bytes,
        recipe_payload: bytes,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            manifest_path = fixture_root / "manifest.json"
            hidden_path = fixture_root / "hidden_states.json"
            recipe_path = fixture_root / "weight_recipe.json"
            manifest_path.write_bytes(manifest_payload)
            hidden_path.write_bytes(hidden_payload)
            recipe_path.write_bytes(recipe_payload)

            runner = CoreRunnerSpy()
            with (
                patch.object(router_module, "_MANIFEST_PATH", manifest_path),
                patch.object(router_module, "_HIDDEN_PATH", hidden_path),
                patch.object(router_module, "_WEIGHT_RECIPE_PATH", recipe_path),
            ):
                with self.assertRaises(RouterError) as caught:
                    run_committed_router(
                        router_case_id=SINGLE_ROW_CASE_ID,
                        requested_device="gpu",
                        allow_fallback=False,
                        router_runner=runner,
                    )
            self.assertEqual(caught.exception.code, expected_code)
            self.assertLessEqual(len(caught.exception.message), 512)
            self.assertEqual(
                runner.calls,
                [],
                "invalid committed bytes reached the router runner",
            )

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
                        case_scope=RouterCaseScope.SYNTHETIC_FIXTURE,
                        mx_module=trap,
                    )
                self.assertEqual(caught.exception.code, "device_unavailable")
                self.assertLessEqual(len(caught.exception.message), 512)
                self.assertEqual(trap.access_count, 0)

    def test_invalid_device_scalar_types_precede_mlx(self) -> None:
        for label, requested_device, allow_fallback in (
            ("null device", None, False),
            ("boolean device", True, False),
            ("integer device", 1, False),
            ("null fallback", "gpu", None),
            ("integer fallback", "gpu", 0),
            ("string fallback", "gpu", "false"),
        ):
            with self.subTest(label=label):
                self.assert_rejected_before_mlx(
                    "malformed_request",
                    requested_device=requested_device,
                    allow_fallback=allow_fallback,
                )

    def test_internal_case_scope_must_be_explicit_before_mlx(self) -> None:
        for case_scope in (None, "synthetic_fixture", "real_checkpoint"):
            with self.subTest(case_scope=case_scope):
                self.assert_rejected_before_mlx(
                    "internal_worker_error",
                    case_scope=case_scope,
                )

    def test_invalid_case_ids_precede_mlx(self) -> None:
        cases = (
            ("null", None, "malformed_request"),
            ("boolean", False, "malformed_request"),
            ("integer", 7, "malformed_request"),
            ("empty", "", "malformed_request"),
            ("leading whitespace", " bad-id", "malformed_request"),
            ("path-like", "bad/id", "malformed_request"),
            ("overlong", "x" * 129, "malformed_request"),
            (
                "stable but uncommitted",
                "generated-router-unknown-v1",
                "unsupported_operation",
            ),
        )
        for label, router_case_id, expected_code in cases:
            with self.subTest(label=label):
                self.assert_rejected_before_mlx(
                    expected_code,
                    router_case_id=router_case_id,
                )

    def test_hidden_state_shape_failures_precede_mlx(self) -> None:
        malformed = (
            ("null matrix", None),
            ("mapping matrix", {"row": SINGLE_ROW_HIDDEN[0]}),
            ("byte matrix", b"\x00" * (HIDDEN_WIDTH * 4)),
            ("no rows", ()),
            ("too many rows", BOUNDED_BATCH_HIDDEN),
            ("scalar row", (1.0,)),
            ("short row", (SINGLE_ROW_HIDDEN[0][:-1],)),
            ("overlong row", (SINGLE_ROW_HIDDEN[0] + (0.0,),)),
        )
        for label, hidden_states in malformed:
            with self.subTest(label=label):
                self.assert_rejected_before_mlx(
                    "invalid_shape",
                    hidden_states=hidden_states,
                )

    def test_weight_shape_failures_precede_mlx(self) -> None:
        malformed = (
            ("null matrix", None),
            ("mapping matrix", {"row": ROUTER_WEIGHTS[0]}),
            ("byte matrix", b"\x00" * 16),
            ("no rows", ()),
            ("too few rows", ROUTER_WEIGHTS[:-1]),
            ("too many rows", ROUTER_WEIGHTS + (ROUTER_WEIGHTS[0],)),
            (
                "short row",
                (ROUTER_WEIGHTS[0][:-1],) + ROUTER_WEIGHTS[1:],
            ),
            (
                "overlong row",
                (ROUTER_WEIGHTS[0] + (0.0,),) + ROUTER_WEIGHTS[1:],
            ),
        )
        for label, router_weights in malformed:
            with self.subTest(label=label):
                self.assert_rejected_before_mlx(
                    "invalid_shape",
                    router_weights=router_weights,
                )

    def test_invalid_decoded_dtypes_precede_mlx(self) -> None:
        cases = (
            (
                "boolean hidden value",
                _replace_matrix_value(SINGLE_ROW_HIDDEN, 0, 0, True),
                ROUTER_WEIGHTS,
            ),
            (
                "string hidden value",
                _replace_matrix_value(SINGLE_ROW_HIDDEN, 0, 0, "1.0"),
                ROUTER_WEIGHTS,
            ),
            (
                "complex hidden value",
                _replace_matrix_value(SINGLE_ROW_HIDDEN, 0, 0, 1.0 + 0.0j),
                ROUTER_WEIGHTS,
            ),
            (
                "boolean weight value",
                SINGLE_ROW_HIDDEN,
                _replace_matrix_value(ROUTER_WEIGHTS, 0, 0, False),
            ),
            (
                "string weight value",
                SINGLE_ROW_HIDDEN,
                _replace_matrix_value(ROUTER_WEIGHTS, 0, 0, "0.0"),
            ),
            (
                "complex weight value",
                SINGLE_ROW_HIDDEN,
                _replace_matrix_value(ROUTER_WEIGHTS, 0, 0, 0.0 + 0.0j),
            ),
        )
        for label, hidden_states, router_weights in cases:
            with self.subTest(label=label):
                self.assert_rejected_before_mlx(
                    "invalid_dtype",
                    hidden_states=hidden_states,
                    router_weights=router_weights,
                )

    def test_nonfinite_and_non_f32_values_precede_mlx(self) -> None:
        for label, value in (
            ("NaN", math.nan),
            ("positive infinity", math.inf),
            ("negative infinity", -math.inf),
            ("positive float32 overflow", 3.5e38),
            ("negative float32 overflow", -3.5e38),
        ):
            with self.subTest(location="hidden", label=label):
                self.assert_rejected_before_mlx(
                    "invalid_dtype",
                    hidden_states=_replace_matrix_value(
                        SINGLE_ROW_HIDDEN,
                        0,
                        0,
                        value,
                    ),
                )
            with self.subTest(location="weight", label=label):
                self.assert_rejected_before_mlx(
                    "invalid_dtype",
                    router_weights=_replace_matrix_value(
                        ROUTER_WEIGHTS,
                        0,
                        0,
                        value,
                    ),
                )

    def test_encoded_file_byte_count_failures_precede_router_runner(self) -> None:
        manifest_payload = router_module._MANIFEST_PATH.read_bytes()
        hidden_payload = router_module._HIDDEN_PATH.read_bytes()
        recipe_payload = router_module._WEIGHT_RECIPE_PATH.read_bytes()

        self.assertTrue(hidden_payload.endswith(b"\n"))
        cases = (
            ("truncated hidden document", hidden_payload[:-1]),
            ("overlong hidden document", hidden_payload + b" "),
        )
        for label, mutated_hidden in cases:
            with self.subTest(label=label):
                self.assert_committed_fixture_rejected_before_runner(
                    "invalid_byte_count",
                    manifest_payload=manifest_payload,
                    hidden_payload=mutated_hidden,
                    recipe_payload=recipe_payload,
                )

        changed_manifest = json.loads(manifest_payload)
        hidden_entry = next(
            entry
            for entry in changed_manifest["files"]
            if entry["path"] == "golden/hidden_states.json"
        )
        hidden_entry["byte_length"] += 4
        with self.subTest(label="changed manifest byte count"):
            self.assert_committed_fixture_rejected_before_runner(
                "invalid_byte_count",
                manifest_payload=_json_bytes(changed_manifest),
                hidden_payload=hidden_payload,
                recipe_payload=recipe_payload,
            )

    def test_canonical_tensor_byte_count_failures_precede_router_runner(self) -> None:
        original_manifest = json.loads(router_module._MANIFEST_PATH.read_bytes())
        original_hidden = json.loads(router_module._HIDDEN_PATH.read_bytes())
        original_recipe = json.loads(router_module._WEIGHT_RECIPE_PATH.read_bytes())

        cases = []
        changed_hidden = dict(original_hidden)
        changed_hidden["canonical_byte_length"] -= 4
        changed_hidden_payload = _json_bytes(changed_hidden)
        hidden_manifest = json.loads(json.dumps(original_manifest))
        hidden_entry = next(
            entry
            for entry in hidden_manifest["files"]
            if entry["path"] == "golden/hidden_states.json"
        )
        hidden_entry["byte_length"] = len(changed_hidden_payload)
        hidden_entry["sha256"] = hashlib.sha256(changed_hidden_payload).hexdigest()
        cases.append(
            (
                "hidden tensor canonical byte count",
                _json_bytes(hidden_manifest),
                changed_hidden_payload,
                router_module._WEIGHT_RECIPE_PATH.read_bytes(),
            )
        )

        changed_recipe = dict(original_recipe)
        changed_recipe["canonical_byte_length"] += 4
        changed_recipe_payload = _json_bytes(changed_recipe)
        recipe_manifest = json.loads(json.dumps(original_manifest))
        recipe_entry = next(
            entry
            for entry in recipe_manifest["files"]
            if entry["path"] == "golden/weight_recipe.json"
        )
        recipe_entry["byte_length"] = len(changed_recipe_payload)
        recipe_entry["sha256"] = hashlib.sha256(changed_recipe_payload).hexdigest()
        cases.append(
            (
                "weight tensor canonical byte count",
                _json_bytes(recipe_manifest),
                router_module._HIDDEN_PATH.read_bytes(),
                changed_recipe_payload,
            )
        )

        for label, manifest_payload, hidden_payload, recipe_payload in cases:
            with self.subTest(label=label):
                self.assert_committed_fixture_rejected_before_runner(
                    "invalid_byte_count",
                    manifest_payload=manifest_payload,
                    hidden_payload=hidden_payload,
                    recipe_payload=recipe_payload,
                )

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
                        case_scope=RouterCaseScope.SYNTHETIC_FIXTURE,
                        mx_module=trap,
                    )
                self.assertEqual(caught.exception.code, "device_unavailable")
                self.assertEqual(trap.device_info_calls, 1)
                self.assertEqual(trap.stream_calls, 0)


class RouterTiePolicyTests(unittest.TestCase):
    def validate_fixture_case(
        self,
        case: dict[str, object],
        case_scope: RouterCaseScope,
    ) -> None:
        router_module._validate_complete_result(
            _fixture_matrix(case, "logits"),
            _fixture_matrix(case, "full_softmax_probabilities"),
            _fixture_matrix(case, "selected_expert_ids"),
            _fixture_matrix(case, "selected_probabilities"),
            _fixture_matrix(case, "normalized_weights"),
            case_scope=case_scope,
        )

    def test_synthetic_exact_and_near_cutoff_fixtures_are_admitted(self) -> None:
        for kind in ("exact_tie", "near_tie"):
            with self.subTest(kind=kind):
                self.validate_fixture_case(
                    _synthetic_tie_case(kind),
                    RouterCaseScope.SYNTHETIC_FIXTURE,
                )

    def test_real_cutoff_policy_stops_exact_tie_and_allows_near_tie(self) -> None:
        with self.assertRaises(RouterError) as caught:
            self.validate_fixture_case(
                _synthetic_tie_case("exact_tie"),
                RouterCaseScope.REAL_CHECKPOINT,
            )
        self.assertEqual(caught.exception.code, "comparison_failed")
        self.assertLessEqual(len(caught.exception.message), 512)

        self.validate_fixture_case(
            _synthetic_tie_case("near_tie"),
            RouterCaseScope.REAL_CHECKPOINT,
        )


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

    def run_generated_case(
        self,
        case_id: str,
        hidden_states,
        *,
        router_weights=ROUTER_WEIGHTS,
    ):
        import mlx.core as native_mx

        mx = MlxEventSpy(native_mx)
        result = run_router(
            router_case_id=case_id,
            hidden_states=hidden_states,
            router_weights=router_weights,
            requested_device="gpu",
            allow_fallback=False,
            case_scope=RouterCaseScope.SYNTHETIC_FIXTURE,
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

    def test_committed_synthetic_cutoff_fixtures_execute_normative_order(self) -> None:
        expected = {
            "exact_tie": (0, 1, 2, 3, 4, 5, 6, 7),
            "near_tie": (0, 1, 2, 3, 4, 5, 6, 8),
        }
        for kind, expected_ids in expected.items():
            with self.subTest(kind=kind):
                case = _synthetic_tie_case(kind)
                result, mx = self.run_generated_case(
                    SINGLE_ROW_CASE_ID,
                    SINGLE_ROW_HIDDEN,
                    router_weights=_weights_for_fixture_logits(case),
                )
                self.assert_evaluated_gpu_boundary(result, mx)
                self.assertEqual(result.selected_expert_ids, (expected_ids,))
                self.assertEqual(
                    result.selected_expert_ids,
                    _fixture_matrix(case, "selected_expert_ids"),
                )
                probabilities = result.full_probabilities[0]
                if kind == "exact_tie":
                    self.assertEqual(probabilities[7], probabilities[8])
                else:
                    self.assertGreater(probabilities[8], probabilities[7])

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

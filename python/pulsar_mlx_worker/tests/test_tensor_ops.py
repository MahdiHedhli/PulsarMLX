"""Contract tests for deterministic MLX fixture operations.

The expected values in this module are deliberately hard-coded.  They are an
independent test oracle and are not calculated with the MLX operations under
test or copied from a result produced by the Apple backend.
"""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import platform
import unittest

from pulsar_mlx_worker.tensor_ops import (
    TensorOperationError,
    load_fixture_manifest,
    run_fixture_operation,
    validate_fixture_descriptor,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "fixtures" / "mlx" / "manifest.json"
FIXTURE_SET_ID = "mlx-tensor-fixtures-v1"
SYNCHRONIZATION_RULE = "explicit_eval_then_gpu_synchronize"
MAXIMUM_FIXTURE_ELEMENTS = 4_096

INDEPENDENT_EXPECTED: dict[str, tuple[float, ...]] = {
    "elementwise-fma-nonsymmetric-f32-v1": (
        0.75,
        -5.75,
        -5.0,
        8.25,
        -0.75,
        -5.75,
    ),
    "matmul-nonsymmetric-f32-v1": (58.0, 64.0, 139.0, 154.0),
    "embedding-gather-order-f32-v1": (
        -3.0,
        8.0,
        6.0,
        1.0,
        -1.0,
        2.0,
        7.0,
        0.5,
        4.0,
    ),
    "rms-norm-weighted-f32-v1": (
        0.6324542671264065,
        0.6324542671264065,
        -1.264908534252813,
        1.264908534252813,
        1.5894365976914109,
        -0.26490609961523515,
        0.5298121992304703,
        -1.0596243984609406,
    ),
    "residual-add-nonsymmetric-f32-v1": (9.0, 1.0, 3.0, 5.0, -6.0, -3.0),
    "router-topk-tie-f32-v1": (
        0.5,
        0.5,
        0.8807970779778824,
        0.11920292202211756,
    ),
    "q8-0-two-block-row-v1": (-8.0,),
}

INDEPENDENT_OUTPUT_SHAPES: dict[str, tuple[int, ...]] = {
    "elementwise-fma-nonsymmetric-f32-v1": (2, 3),
    "matmul-nonsymmetric-f32-v1": (2, 2),
    "embedding-gather-order-f32-v1": (3, 3),
    "rms-norm-weighted-f32-v1": (2, 4),
    "residual-add-nonsymmetric-f32-v1": (2, 3),
    "router-topk-tie-f32-v1": (2, 2),
    "q8-0-two-block-row-v1": (1,),
}

INDEPENDENT_ROUTER_IDS = (1, 2, 3, 0)
INDEPENDENT_Q8_DECODED = (
    -8.0,
    -7.5,
    -7.0,
    -6.5,
    -6.0,
    -5.5,
    -5.0,
    -4.5,
    -4.0,
    -3.5,
    -3.0,
    -2.5,
    -2.0,
    -1.5,
    -1.0,
    -0.5,
    0.0,
    0.5,
    1.0,
    1.5,
    2.0,
    2.5,
    3.0,
    3.5,
    4.0,
    4.5,
    5.0,
    5.5,
    6.0,
    6.5,
    7.0,
    7.5,
    2.0,
    -2.0,
    4.0,
    -4.0,
    6.0,
    -6.0,
    8.0,
    -8.0,
    10.0,
    -10.0,
    12.0,
    -12.0,
    14.0,
    -14.0,
    16.0,
    -16.0,
    18.0,
    -18.0,
    20.0,
    -20.0,
    22.0,
    -22.0,
    24.0,
    -24.0,
    26.0,
    -26.0,
    28.0,
    -28.0,
    30.0,
    -30.0,
    32.0,
    -32.0,
)


class SchedulingTrap:
    """Fail if malformed input touches any MLX scheduling surface."""

    def __init__(self) -> None:
        self.access_count = 0

    def __getattr__(self, name: str):
        self.access_count += 1
        raise AssertionError(f"MLX was accessed before validation: {name}")


class TensorOperationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_fixture_manifest(
            MANIFEST_PATH,
            expected_fixture_set_id=FIXTURE_SET_ID,
        )
        cls.cases = {
            case["case_id"]: case for case in cls.manifest.operations
        }

    def assert_tensor_error(
        self,
        expected_code: str,
        callable_,
        /,
        *args,
        **kwargs,
    ) -> TensorOperationError:
        with self.assertRaises(TensorOperationError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)
        self.assertLessEqual(len(caught.exception.message), 512)
        return caught.exception

    def run_case(self, case: dict[str, object], *, mx_module=None):
        return run_fixture_operation(
            case,
            fixture_set_id=self.manifest.fixture_set_id,
            synchronization_rule=self.manifest.synchronization_rule,
            maximum_fixture_elements=self.manifest.maximum_fixture_elements,
            requested_device="gpu",
            allow_fallback=False,
            mx_module=mx_module,
        )

    def assert_rejected_before_scheduling(
        self,
        expected_code: str,
        case: dict[str, object],
        **overrides,
    ) -> None:
        trap = SchedulingTrap()
        arguments = {
            "fixture_set_id": FIXTURE_SET_ID,
            "synchronization_rule": SYNCHRONIZATION_RULE,
            "maximum_fixture_elements": MAXIMUM_FIXTURE_ELEMENTS,
            "requested_device": "gpu",
            "allow_fallback": False,
            "mx_module": trap,
            **overrides,
        }
        self.assert_tensor_error(
            expected_code,
            run_fixture_operation,
            case,
            **arguments,
        )
        self.assertEqual(
            trap.access_count,
            0,
            "malformed fixture reached the MLX module before rejection",
        )

    def test_manifest_identity_and_frozen_independent_oracles(self) -> None:
        self.assertEqual(self.manifest.fixture_set_id, FIXTURE_SET_ID)
        self.assertEqual(
            self.manifest.synchronization_rule,
            SYNCHRONIZATION_RULE,
        )
        self.assertEqual(
            self.manifest.maximum_fixture_elements,
            MAXIMUM_FIXTURE_ELEMENTS,
        )
        self.assertFalse(self.manifest.allow_fallback)
        self.assertEqual(set(self.cases), set(INDEPENDENT_EXPECTED))

        for case_id, independent_expected in INDEPENDENT_EXPECTED.items():
            with self.subTest(case_id=case_id):
                self.assertEqual(
                    tuple(self.cases[case_id]["expected"]),
                    independent_expected,
                )
        self.assertEqual(
            tuple(self.cases["router-topk-tie-f32-v1"]["expected_expert_ids"]),
            INDEPENDENT_ROUTER_IDS,
        )
        self.assertEqual(
            tuple(self.cases["q8-0-two-block-row-v1"]["expected_decoded"]),
            INDEPENDENT_Q8_DECODED,
        )

    def test_every_descriptor_has_an_explicit_checked_contract(self) -> None:
        for case_id, case in self.cases.items():
            with self.subTest(case_id=case_id):
                descriptor = validate_fixture_descriptor(
                    case,
                    maximum_fixture_elements=MAXIMUM_FIXTURE_ELEMENTS,
                )
                self.assertEqual(descriptor.case_id, case_id)
                self.assertEqual(descriptor.layout, case["layout"])
                self.assertEqual(descriptor.input_dtype, case["input_dtype"])
                self.assertEqual(
                    descriptor.accumulation_dtype,
                    case["accumulation_dtype"],
                )
                self.assertEqual(descriptor.output_dtype, case["output_dtype"])
                self.assertGreater(descriptor.element_count, 0)
                self.assertLessEqual(
                    descriptor.element_count,
                    MAXIMUM_FIXTURE_ELEMENTS,
                )

    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "evaluated MLX fixture operations require native Apple Silicon",
    )
    def test_all_operations_match_independent_values_after_eval_and_sync(self) -> None:
        for case_id, independent_expected in INDEPENDENT_EXPECTED.items():
            with self.subTest(case_id=case_id):
                result = self.run_case(self.cases[case_id])

                self.assertEqual(result.fixture_set_id, FIXTURE_SET_ID)
                self.assertEqual(result.case_id, case_id)
                self.assertEqual(result.requested_device, "gpu")
                self.assertEqual(result.selected_device, "gpu")
                self.assertFalse(result.fallback_used)
                self.assertEqual(
                    tuple(result.output_shape),
                    INDEPENDENT_OUTPUT_SHAPES[case_id],
                )
                self.assertEqual(result.output_dtype, "float32")
                self.assertTrue(result.evaluated)
                self.assertTrue(result.synchronized)
                self.assertTrue(result.comparison.passed)
                self.assertEqual(
                    result.comparison.compared_count,
                    len(independent_expected),
                )
                self.assertIsNone(result.comparison.first_mismatch_index)
                self.assertTrue(result.passed)

                absolute_tolerance = self.cases[case_id]["comparison"][
                    "absolute_tolerance"
                ]
                relative_tolerance = self.cases[case_id]["comparison"][
                    "relative_tolerance"
                ]
                for index, (actual, expected) in enumerate(
                    zip(result.actual, independent_expected)
                ):
                    admitted = absolute_tolerance + relative_tolerance * abs(expected)
                    self.assertLessEqual(
                        abs(actual - expected),
                        admitted,
                        f"{case_id} mismatch at flattened index {index}",
                    )

                gauges = result.memory_gauges.to_protocol_result()
                self.assertIsNone(gauges["reported_summed_total_bytes"])

    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "evaluated MLX fixture operations require native Apple Silicon",
    )
    def test_router_ids_and_q8_decode_match_separate_exact_oracles(self) -> None:
        router = self.run_case(self.cases["router-topk-tie-f32-v1"])
        self.assertEqual(tuple(router.selected_expert_ids), INDEPENDENT_ROUTER_IDS)

        q8 = self.run_case(self.cases["q8-0-two-block-row-v1"])
        self.assertEqual(tuple(q8.decoded), INDEPENDENT_Q8_DECODED)

    def test_shape_layout_and_dtype_errors_precede_scheduling(self) -> None:
        base = self.cases["elementwise-fma-nonsymmetric-f32-v1"]
        malformed_cases: list[tuple[str, str, dict[str, object]]] = []

        zero_dimension = deepcopy(base)
        zero_dimension["logical_shape"] = [2, 0]
        malformed_cases.append(("zero dimension", "invalid_shape", zero_dimension))

        rank_too_large = deepcopy(base)
        rank_too_large["logical_shape"] = [1] * 17
        rank_too_large["storage_shape"] = [1] * 17
        malformed_cases.append(("rank too large", "invalid_shape", rank_too_large))

        wrong_storage_shape = deepcopy(base)
        wrong_storage_shape["storage_shape"] = [3, 2]
        malformed_cases.append(
            ("orientation mismatch", "invalid_shape", wrong_storage_shape)
        )

        unknown_layout = deepcopy(base)
        unknown_layout["layout"] = "implicit_backend_layout"
        malformed_cases.append(("unknown layout", "invalid_layout", unknown_layout))

        for field in ("input_dtype", "accumulation_dtype", "output_dtype"):
            invalid_dtype = deepcopy(base)
            invalid_dtype[field] = "float64"
            malformed_cases.append((field, "invalid_dtype", invalid_dtype))

        unknown_operation = deepcopy(base)
        unknown_operation["operation"] = "backend_defined_magic"
        malformed_cases.append(
            ("unknown operation", "unsupported_operation", unknown_operation)
        )

        for label, code, case in malformed_cases:
            with self.subTest(label=label):
                self.assert_rejected_before_scheduling(code, case)

        self.assert_rejected_before_scheduling(
            "resource_limit",
            deepcopy(base),
            maximum_fixture_elements=5,
        )

    def test_explicit_device_sync_and_no_fallback_are_validated_first(self) -> None:
        base = deepcopy(self.cases["matmul-nonsymmetric-f32-v1"])
        self.assert_rejected_before_scheduling(
            "device_unavailable",
            base,
            requested_device="cpu",
        )
        self.assert_rejected_before_scheduling(
            "device_unavailable",
            base,
            allow_fallback=True,
        )
        self.assert_rejected_before_scheduling(
            "malformed_request",
            base,
            synchronization_rule="queued_only",
        )

    def test_operation_specific_malformed_inputs_precede_scheduling(self) -> None:
        malformed: list[tuple[str, str, dict[str, object]]] = []

        elementwise = deepcopy(
            self.cases["elementwise-fma-nonsymmetric-f32-v1"]
        )
        elementwise["inputs"]["left"] = elementwise["inputs"]["left"][:-1]
        malformed.append(("elementwise cardinality", "invalid_shape", elementwise))

        non_finite = deepcopy(
            self.cases["elementwise-fma-nonsymmetric-f32-v1"]
        )
        non_finite["inputs"]["left"][0] = math.inf
        malformed.append(("non-finite input", "malformed_request", non_finite))

        matmul = deepcopy(self.cases["matmul-nonsymmetric-f32-v1"])
        matmul["inputs"]["right_shape"] = [2, 3]
        malformed.append(("matmul inner dimension", "invalid_shape", matmul))

        embedding = deepcopy(self.cases["embedding-gather-order-f32-v1"])
        embedding["inputs"]["token_ids"] = [3, -1, 2]
        malformed.append(("negative token", "malformed_request", embedding))

        embedding_high = deepcopy(self.cases["embedding-gather-order-f32-v1"])
        embedding_high["inputs"]["token_ids"] = [3, 4, 2]
        malformed.append(("high token", "malformed_request", embedding_high))

        rms_norm = deepcopy(self.cases["rms-norm-weighted-f32-v1"])
        rms_norm["inputs"]["epsilon"] = -0.00001
        malformed.append(("negative epsilon", "malformed_request", rms_norm))

        residual = deepcopy(
            self.cases["residual-add-nonsymmetric-f32-v1"]
        )
        residual["inputs"]["update"] = residual["inputs"]["update"][:-1]
        malformed.append(("residual cardinality", "invalid_shape", residual))

        router = deepcopy(self.cases["router-topk-tie-f32-v1"])
        router["inputs"]["top_k"] = 0
        malformed.append(("zero top-k", "invalid_shape", router))

        router_nonfinite = deepcopy(self.cases["router-topk-tie-f32-v1"])
        router_nonfinite["inputs"]["scores"][0] = math.nan
        malformed.append(
            ("non-finite router score", "malformed_request", router_nonfinite)
        )

        router_tie_rule = deepcopy(self.cases["router-topk-tie-f32-v1"])
        router_tie_rule["inputs"]["tie_rule"] = "implementation_defined"
        malformed.append(("unknown tie rule", "malformed_request", router_tie_rule))

        for label, code, case in malformed:
            with self.subTest(label=label):
                self.assert_rejected_before_scheduling(code, case)

    def test_q8_descriptor_and_encoded_bytes_are_rejected_before_scheduling(self) -> None:
        base = self.cases["q8-0-two-block-row-v1"]
        malformed: list[tuple[str, str, dict[str, object]]] = []

        short_bytes = deepcopy(base)
        short_bytes["inputs"]["encoded_hex"] = short_bytes["inputs"][
            "encoded_hex"
        ][:-2]
        malformed.append(("short encoded row", "invalid_byte_count", short_bytes))

        extra_bytes = deepcopy(base)
        extra_bytes["inputs"]["encoded_hex"] += "00"
        malformed.append(("extra encoded byte", "invalid_byte_count", extra_bytes))

        invalid_hex = deepcopy(base)
        invalid_hex["inputs"]["encoded_hex"] = "zz" + invalid_hex["inputs"][
            "encoded_hex"
        ][2:]
        malformed.append(("invalid hex", "invalid_byte_count", invalid_hex))

        wrong_declared_bytes = deepcopy(base)
        wrong_declared_bytes["encoded_byte_count"] = 67
        malformed.append(
            ("wrong declared byte count", "invalid_byte_count", wrong_declared_bytes)
        )

        wrong_block = deepcopy(base)
        wrong_block["quantization"]["block_elements"] = 16
        malformed.append(("wrong block elements", "invalid_byte_count", wrong_block))

        wrong_scale = deepcopy(base)
        wrong_scale["quantization"]["scale_dtype"] = "float16_native_endian"
        malformed.append(("wrong scale format", "invalid_dtype", wrong_scale))

        wrong_activation = deepcopy(base)
        wrong_activation["inputs"]["activation"] = wrong_activation["inputs"][
            "activation"
        ][:-1]
        malformed.append(("activation cardinality", "invalid_shape", wrong_activation))

        for label, code, case in malformed:
            with self.subTest(label=label):
                self.assert_rejected_before_scheduling(code, case)


if __name__ == "__main__":
    unittest.main()

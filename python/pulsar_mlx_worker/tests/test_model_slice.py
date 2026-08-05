"""Contract tests for the one admitted Qwen3MoE expert projection slice.

The encoded stand-in below has the exact byte shape of the planned real-model
slice but contains generated, reviewable Q8_0 blocks rather than model weights.
Its identities and scalar outputs were frozen independently of MLX.  The tests
therefore exercise the real shape and orientation boundary without requiring a
checkpoint or allowing Apple output to define its own oracle.
"""

from __future__ import annotations

import hashlib
import math
import platform
import struct
import unittest

from pulsar_mlx_worker.model_slice import (
    ModelSliceError,
    build_prompt_activation,
    run_model_slice,
    validate_model_slice_output,
    validate_model_slice_request,
)


SLICE_ID = "qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1"
OPERATION = "q8_0_expert_projection_matvec"
TENSOR_NAME = "blk.0.ffn_gate_exps.weight"
OUTPUT_NAME = "blk0_ffn_gate_expert0_rows0_16_matvec"
PROMPT = (
    "PulsarMLX real-model oracle v1: Qwen3-30B-A3B Q8_0, "
    "blk.0.ffn_gate_exps.weight, expert 0, rows 0:16."
)
PROMPT_SHA256 = "e5516410f283666d437d3cb5cbde9c121d8b12791cacbc2a0a81f2b9de2140bd"
ACTIVATION_SHA256 = (
    "3821796e8415d1214890e0e2fc97cddbb9ec773f2e941203dac41c1c7b36a92e"
)
ENCODED_SHA256 = "557122d9c5de58b714357fbedd83bae223d254e1a25469f0b1938c02138c5c97"
DECODED_SHA256 = "d474869e79a19ff5a01ba920c3f6e61f3db91f4b7784e46e71e2542a21cc69f6"
SCALAR_OUTPUT_SHA256 = (
    "2b44d0a66f8c4d2be5e6bd28cd2f1df9d99acbbfdc99cab82accaa40489e6c18"
)

INPUT_COLUMNS = 2_048
OUTPUT_ROWS = 16
EXPERT_ROWS = 768
EXPERT_COUNT = 128
Q8_BLOCK_ELEMENTS = 32
Q8_BLOCK_BYTES = 34
BLOCKS_PER_ROW = INPUT_COLUMNS // Q8_BLOCK_ELEMENTS
ENCODED_ROW_BYTES = BLOCKS_PER_ROW * Q8_BLOCK_BYTES
ENCODED_SLICE_BYTES = OUTPUT_ROWS * ENCODED_ROW_BYTES
DECODED_SLICE_BYTES = OUTPUT_ROWS * INPUT_COLUMNS * 4
ACTIVATION_BYTES = INPUT_COLUMNS * 4
OUTPUT_BYTES = OUTPUT_ROWS * 4
ABSOLUTE_TOLERANCE = 0.0005
RELATIVE_TOLERANCE = 0.0005

INDEPENDENT_SCALAR_OUTPUT = (
    11.9091796875,
    12.6513671875,
    -46.83984375,
    -120.2998046875,
    -107.7255859375,
    132.603515625,
    77.9033203125,
    -33.2587890625,
    81.2958984375,
    -77.865234375,
    -148.0947265625,
    -33.7080078125,
    117.400390625,
    57.9580078125,
    -28.0166015625,
    34.05859375,
)


def build_encoded_standin() -> bytes:
    """Generate asymmetric exact-shape bytes without implementing the oracle."""

    encoded = bytearray()
    for row_index in range(OUTPUT_ROWS):
        for block_index in range(BLOCKS_PER_ROW):
            scale = 2.0 ** (((row_index + block_index) % 4) - 3)
            encoded.extend(struct.pack("<e", scale))
            for quant_index in range(Q8_BLOCK_ELEMENTS):
                quant = (
                    (row_index * 11 + block_index * 7 + quant_index * 3) % 17
                ) - 8
                encoded.extend(struct.pack("<b", quant))
    return bytes(encoded)


ENCODED_STANDIN = build_encoded_standin()


def admitted_request() -> dict[str, object]:
    """Return the one exact slice contract rather than a generic matmul."""

    return {
        "slice_id": SLICE_ID,
        "operation": OPERATION,
        "tensor_name": TENSOR_NAME,
        "gguf_dimensions_fastest_axis_first": [
            INPUT_COLUMNS,
            EXPERT_ROWS,
            EXPERT_COUNT,
        ],
        "reader_encoded_shape": [EXPERT_COUNT, EXPERT_ROWS, ENCODED_ROW_BYTES],
        "reader_dequantized_shape": [EXPERT_COUNT, EXPERT_ROWS, INPUT_COLUMNS],
        "orientation": "expert_output_row_input_column_no_transpose",
        "quantization": {
            "id": "Q8_0",
            "block_elements": Q8_BLOCK_ELEMENTS,
            "block_bytes": Q8_BLOCK_BYTES,
            "scale_dtype": "float16_little_endian",
        },
        "expert_index": 0,
        "output_row_start": 0,
        "output_row_end": OUTPUT_ROWS,
        "input_column_start": 0,
        "input_column_end": INPUT_COLUMNS,
        "prompt": PROMPT,
        "prompt_adapter": "sha256-indexed-f32-v1",
        "output_name": OUTPUT_NAME,
    }


class SchedulingTrap:
    """Fail if malformed slice input reaches any MLX scheduling surface."""

    def __init__(self) -> None:
        self.access_count = 0

    def __getattr__(self, name: str):
        self.access_count += 1
        raise AssertionError(f"MLX was accessed before validation: {name}")


class MlxEventSpy:
    """Delegate to native MLX while recording completion-boundary calls."""

    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.events: list[str] = []

    def eval(self, *arrays):
        self.events.append("eval")
        return self.delegate.eval(*arrays)

    def synchronize(self, *args, **kwargs):
        self.events.append("synchronize")
        return self.delegate.synchronize(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)


class ModelSliceContractTests(unittest.TestCase):
    def assert_slice_error(
        self,
        expected_code: str,
        callable_,
        /,
        *args,
        **kwargs,
    ) -> ModelSliceError:
        with self.assertRaises(ModelSliceError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)
        self.assertLessEqual(len(caught.exception.message), 512)
        return caught.exception

    def assert_rejected_before_scheduling(
        self,
        expected_code: str,
        request: dict[str, object],
        encoded: bytes = ENCODED_STANDIN,
        **overrides,
    ) -> None:
        trap = SchedulingTrap()
        arguments = {
            "requested_device": "gpu",
            "allow_fallback": False,
            "mx_module": trap,
            **overrides,
        }
        self.assert_slice_error(
            expected_code,
            run_model_slice,
            request,
            encoded,
            **arguments,
        )
        self.assertEqual(
            trap.access_count,
            0,
            "malformed model slice reached MLX before rejection",
        )

    def test_standin_freezes_independent_exact_shape_identities_and_oracle(
        self,
    ) -> None:
        self.assertEqual(len(ENCODED_STANDIN), ENCODED_SLICE_BYTES)
        self.assertEqual(
            hashlib.sha256(ENCODED_STANDIN).hexdigest(),
            ENCODED_SHA256,
        )
        self.assertEqual(len(INDEPENDENT_SCALAR_OUTPUT), OUTPUT_ROWS)
        scalar_bytes = struct.pack("<16f", *INDEPENDENT_SCALAR_OUTPUT)
        self.assertEqual(
            hashlib.sha256(scalar_bytes).hexdigest(),
            SCALAR_OUTPUT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
            PROMPT_SHA256,
        )

    def test_exact_tensor_name_dimensions_orientation_and_q8_slice_are_admitted(
        self,
    ) -> None:
        descriptor = validate_model_slice_request(
            admitted_request(),
            ENCODED_STANDIN,
        )

        self.assertEqual(descriptor.slice_id, SLICE_ID)
        self.assertEqual(descriptor.operation, OPERATION)
        self.assertEqual(descriptor.tensor_name, TENSOR_NAME)
        self.assertEqual(
            descriptor.gguf_dimensions_fastest_axis_first,
            (INPUT_COLUMNS, EXPERT_ROWS, EXPERT_COUNT),
        )
        self.assertEqual(
            descriptor.reader_encoded_shape,
            (EXPERT_COUNT, EXPERT_ROWS, ENCODED_ROW_BYTES),
        )
        self.assertEqual(
            descriptor.reader_dequantized_shape,
            (EXPERT_COUNT, EXPERT_ROWS, INPUT_COLUMNS),
        )
        self.assertEqual(
            descriptor.encoded_slice_shape,
            (OUTPUT_ROWS, ENCODED_ROW_BYTES),
        )
        self.assertEqual(
            descriptor.decoded_slice_shape,
            (OUTPUT_ROWS, INPUT_COLUMNS),
        )
        self.assertEqual(descriptor.output_shape, (OUTPUT_ROWS,))
        self.assertEqual(descriptor.encoded_byte_count, ENCODED_SLICE_BYTES)
        self.assertEqual(descriptor.decoded_byte_count, DECODED_SLICE_BYTES)
        self.assertEqual(descriptor.quantization, "Q8_0")
        self.assertFalse(descriptor.transpose)

    def test_prompt_adapter_constructs_the_frozen_activation(self) -> None:
        activation = tuple(build_prompt_activation(PROMPT))

        self.assertEqual(len(activation), INPUT_COLUMNS)
        self.assertTrue(all(math.isfinite(value) for value in activation))
        activation_bytes = struct.pack("<2048f", *activation)
        self.assertEqual(len(activation_bytes), ACTIVATION_BYTES)
        self.assertEqual(
            hashlib.sha256(activation_bytes).hexdigest(),
            ACTIVATION_SHA256,
        )

    def test_wrong_tensor_dimensions_orientation_and_quantization_precede_mlx(
        self,
    ) -> None:
        cases: list[tuple[str, str, dict[str, object]]] = []

        wrong_name = admitted_request()
        wrong_name["tensor_name"] = "blk.0.ffn_up_exps.weight"
        cases.append(("tensor name", "unsupported_operation", wrong_name))

        reversed_gguf_dimensions = admitted_request()
        reversed_gguf_dimensions["gguf_dimensions_fastest_axis_first"] = [
            EXPERT_COUNT,
            EXPERT_ROWS,
            INPUT_COLUMNS,
        ]
        cases.append(("GGUF dimensions", "invalid_shape", reversed_gguf_dimensions))

        transposed_reader_shape = admitted_request()
        transposed_reader_shape["reader_dequantized_shape"] = [
            INPUT_COLUMNS,
            EXPERT_ROWS,
            EXPERT_COUNT,
        ]
        cases.append(("reader shape", "invalid_shape", transposed_reader_shape))

        transposed_orientation = admitted_request()
        transposed_orientation["orientation"] = "input_column_output_row_transposed"
        cases.append(("orientation", "invalid_layout", transposed_orientation))

        wrong_quantization = admitted_request()
        wrong_quantization["quantization"]["id"] = "Q4_K_M"
        cases.append(("quantization", "invalid_dtype", wrong_quantization))

        wrong_block_layout = admitted_request()
        wrong_block_layout["quantization"]["block_bytes"] = 35
        cases.append(("Q8_0 block layout", "invalid_byte_count", wrong_block_layout))

        for label, code, request in cases:
            with self.subTest(label=label):
                self.assert_rejected_before_scheduling(code, request)

    def test_promoted_depth_ranges_and_device_fallback_precede_mlx(self) -> None:
        cases: list[tuple[str, str, dict[str, object]]] = []

        full_layer = admitted_request()
        full_layer["operation"] = "full_layer"
        cases.append(("full layer", "unsupported_operation", full_layer))

        different_expert = admitted_request()
        different_expert["expert_index"] = 1
        cases.append(("different expert", "unsupported_operation", different_expert))

        more_rows = admitted_request()
        more_rows["output_row_end"] = OUTPUT_ROWS + 1
        cases.append(("more rows", "unsupported_operation", more_rows))

        shifted_columns = admitted_request()
        shifted_columns["input_column_start"] = 1
        cases.append(("shifted columns", "unsupported_operation", shifted_columns))

        mutated_prompt = admitted_request()
        mutated_prompt["prompt"] = f"{PROMPT} changed"
        cases.append(("mutated prompt", "malformed_request", mutated_prompt))

        for label, code, request in cases:
            with self.subTest(label=label):
                self.assert_rejected_before_scheduling(code, request)

        self.assert_rejected_before_scheduling(
            "device_unavailable",
            admitted_request(),
            requested_device="cpu",
        )
        self.assert_rejected_before_scheduling(
            "device_unavailable",
            admitted_request(),
            allow_fallback=True,
        )

    def test_bad_encoded_lengths_and_nonfinite_scales_precede_mlx(self) -> None:
        self.assert_rejected_before_scheduling(
            "invalid_byte_count",
            admitted_request(),
            ENCODED_STANDIN[:-1],
        )
        self.assert_rejected_before_scheduling(
            "invalid_byte_count",
            admitted_request(),
            ENCODED_STANDIN + b"\x00",
        )

        for label, scale in (("infinity", math.inf), ("NaN", math.nan)):
            with self.subTest(label=label):
                malformed = bytearray(ENCODED_STANDIN)
                malformed[:2] = struct.pack("<e", scale)
                self.assert_rejected_before_scheduling(
                    "invalid_dtype",
                    admitted_request(),
                    bytes(malformed),
                )

    def test_output_contract_accepts_only_sixteen_finite_values(self) -> None:
        actual = validate_model_slice_output(list(INDEPENDENT_SCALAR_OUTPUT))
        self.assertEqual(actual, INDEPENDENT_SCALAR_OUTPUT)

        self.assert_slice_error(
            "invalid_shape",
            validate_model_slice_output,
            list(INDEPENDENT_SCALAR_OUTPUT[:-1]),
        )
        self.assert_slice_error(
            "invalid_shape",
            validate_model_slice_output,
            [*INDEPENDENT_SCALAR_OUTPUT, 0.0],
        )
        for value in (math.nan, math.inf, -math.inf):
            malformed = list(INDEPENDENT_SCALAR_OUTPUT)
            malformed[3] = value
            self.assert_slice_error(
                "evaluation_failed",
                validate_model_slice_output,
                malformed,
            )

    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() == "arm64",
        "evaluated model-slice stand-in requires native Apple Silicon",
    )
    def test_evaluated_slice_matches_oracle_shape_after_eval_then_sync(self) -> None:
        import mlx.core as native_mx

        mx = MlxEventSpy(native_mx)
        result = run_model_slice(
            admitted_request(),
            ENCODED_STANDIN,
            requested_device="gpu",
            allow_fallback=False,
            mx_module=mx,
        )

        self.assertTrue(result.evaluated)
        self.assertTrue(result.synchronized)
        self.assertEqual(result.requested_device, "gpu")
        self.assertEqual(result.selected_device, "gpu")
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.tensor_name, TENSOR_NAME)
        self.assertEqual(result.output_name, OUTPUT_NAME)
        self.assertEqual(result.output_shape, (OUTPUT_ROWS,))
        self.assertEqual(result.output_dtype, "float32")
        self.assertEqual(len(result.actual), OUTPUT_ROWS)
        self.assertTrue(all(math.isfinite(value) for value in result.actual))

        self.assertIn("eval", mx.events)
        self.assertIn("synchronize", mx.events)
        self.assertLess(mx.events.index("eval"), mx.events.index("synchronize"))

        for index, (actual, expected) in enumerate(
            zip(result.actual, INDEPENDENT_SCALAR_OUTPUT)
        ):
            admitted_error = ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * abs(expected)
            self.assertLessEqual(
                abs(actual - expected),
                admitted_error,
                f"stand-in output mismatch at index {index}",
            )

        self.assertEqual(result.encoded_slice_sha256, ENCODED_SHA256)
        self.assertEqual(result.decoded_slice_sha256, DECODED_SHA256)
        self.assertEqual(result.activation_sha256, ACTIVATION_SHA256)
        candidate_output_bytes = struct.pack("<16f", *result.actual)
        self.assertEqual(
            result.output_sha256,
            hashlib.sha256(candidate_output_bytes).hexdigest(),
        )

        gauges = result.memory_gauges.to_protocol_result()
        self.assertIsNone(gauges["model_file_bytes"])
        self.assertEqual(gauges["mapped_virtual_bytes"], 0)
        self.assertEqual(gauges["mapped_resident_bytes"], 0)
        self.assertEqual(gauges["owned_compressed_bytes"], ENCODED_SLICE_BYTES)
        self.assertEqual(gauges["decoded_array_bytes"], DECODED_SLICE_BYTES)
        self.assertEqual(gauges["activation_array_bytes"], ACTIVATION_BYTES)
        self.assertEqual(gauges["output_bytes"], OUTPUT_BYTES)
        self.assertIn("temporary_current_bytes", gauges)
        self.assertIn("temporary_peak_bytes", gauges)
        self.assertIn("mlx_active_bytes", gauges)
        self.assertIn("mlx_cache_bytes", gauges)
        self.assertIn("mlx_peak_bytes", gauges)
        self.assertIn("process_footprint_bytes", gauges)
        self.assertIn("process_footprint_source", gauges)
        self.assertIn("process_physical_footprint_bytes", gauges)
        self.assertIn("process_physical_footprint_peak_bytes", gauges)
        self.assertIn("process_physical_footprint_source", gauges)
        self.assertIn("system_pressure", gauges)
        self.assertIsNone(gauges["reported_summed_total_bytes"])


if __name__ == "__main__":
    unittest.main()

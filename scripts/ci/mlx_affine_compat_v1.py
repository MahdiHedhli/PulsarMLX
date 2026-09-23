#!/usr/bin/env python3
"""R2 -- the pinned upstream MLX compatibility observation.

This is **not** the numerical correctness oracle for the affine
representation, and nothing it reports may be used as one. Correctness is
defined by R1, the independent binary64 reference; a defect shared by MLX and
by a native path that calls MLX would be invisible to an R3-vs-R2 comparison.
What this script establishes is narrower and still worth having: whether the
representation PulsarMLX committed to agrees with the upstream execution that
the pinned MLX wheel provides. See
`specs/020-mlx-safetensors-affine/contracts/numerics-v1.json`, check
`C-R2-COMPAT`.

For every positive fixture under `fixtures/safetensors/`, every quantized
module is handed to `mx.dequantize` exactly as the shards store it -- packed
`uint32` weights and `bfloat16` scales and biases, with the bit width and
group size the configuration resolves to -- and the result is compared against
the fixture's `expected.json`, which the R1 reference produced. Two checks:

*  codes: `mx.dequantize` with unit scales and zero biases must return exactly
   the codes R1 unpacks, as integers;
*  values: `mx.dequantize`'s output, against R1 rounded to `mx.dequantize`'s
   own output dtype, within one ulp of that dtype.

Fail closed. If MLX cannot be imported, or Metal is unavailable, and
`PULSAR_REQUIRE_NATIVE_MLX=1`, this exits non-zero with a clear message. There
is no silent skip and no fallback path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/safetensors"
POSITIVES = (
    "uniform-affine-v1",
    "mixed-4-8-v1",
    "mixed-4-8-index-total-size-v1",
    "metadata-variants-v1",
)
# 2.0.0 changed the report shape: codes are compared as finite floats rather
# than truncated integers, bit identity is a bit-pattern comparison, the GPU is
# selected explicitly and recorded, and the corpus covers every admitted
# metadata width and group size. Round 1 reports remain valid 1.0.0 documents
# and are not edited.
SCHEMA = "pulsarmlx.f020.mlx-affine-compatibility/2.0.0"
REQUIRE = os.environ.get("PULSAR_REQUIRE_NATIVE_MLX") == "1"

WEIGHT_SUFFIX = ".weight"
SCALES_SUFFIX = ".scales"
BIASES_SUFFIX = ".biases"


class Refusal(RuntimeError):
    pass


# --- a small, self-contained shard reader ---------------------------------
# Deliberately not the crate under test: this is the R2 arm's own plumbing.


def read_shard(path: Path):
    body = path.read_bytes()
    (length,) = struct.unpack("<Q", body[:8])
    header = json.loads(body[8:8 + length])
    data = body[8 + length:]
    tensors = {}
    for name, entry in header.items():
        if name == "__metadata__":
            continue
        begin, end = entry["data_offsets"]
        tensors[name] = {
            "dtype": entry["dtype"],
            "shape": entry["shape"],
            "bytes": data[begin:end],
        }
    return tensors


def read_checkpoint(directory: Path):
    index_path = directory / "model.safetensors.index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text())
        shards = sorted(set(index["weight_map"].values()))
    else:
        shards = sorted(p.name for p in directory.glob("*.safetensors"))
        if len(shards) != 1:
            raise Refusal(f"{directory.name}: no index and {len(shards)} shards")
    tensors = {}
    for shard in shards:
        for name, tensor in read_shard(directory / shard).items():
            if name in tensors:
                raise Refusal(f"{directory.name}: {name} appears twice")
            tensors[name] = tensor
    return tensors


def resolve_spec(config, module, has_scales):
    quantization = config.get("quantization")
    if quantization is None:
        return None
    explicit = quantization.get(module)
    if isinstance(explicit, dict):
        return int(explicit["bits"]), int(explicit["group_size"])
    if has_scales:
        return int(quantization["bits"]), int(quantization["group_size"])
    return None


# --- the observation -------------------------------------------------------


def ulp_of(dtype, mx, value_array):
    """One unit in the last place of `dtype`, elementwise, as float32."""
    import mlx.core as _mx  # noqa: F401  (kept explicit for the reader)

    magnitude = mx.abs(value_array.astype(mx.float32))
    significand_bits = {"float32": 24, "float16": 11, "bfloat16": 8}[str(dtype).split(".")[-1]]
    smallest = {"float32": 2.0 ** -149, "float16": 2.0 ** -24, "bfloat16": 2.0 ** -133}[
        str(dtype).split(".")[-1]
    ]
    exponent = mx.floor(mx.log2(mx.maximum(magnitude, mx.array(smallest, dtype=mx.float32))))
    return mx.maximum(
        mx.power(mx.array(2.0, dtype=mx.float32), exponent - (significand_bits - 1)),
        mx.array(smallest, dtype=mx.float32),
    )


def observe(mx, np, directory: Path):
    tensors = read_checkpoint(directory)
    config = json.loads((directory / "config.json").read_text())
    expected = json.loads((directory / "expected.json").read_text())["modules"]

    modules = sorted(
        {
            name[: -len(WEIGHT_SUFFIX)]
            for name in tensors
            if name.endswith(WEIGHT_SUFFIX)
        }
    )
    results = []
    for module in modules:
        scales_name = module + SCALES_SUFFIX
        spec = resolve_spec(config, module, scales_name in tensors)
        if spec is None or scales_name not in tensors:
            results.append({"module": module, "kind": "unquantized", "result": "SKIPPED_UNQUANTIZED"})
            continue
        bits, group_size = spec
        weight = tensors[module + WEIGHT_SUFFIX]
        scales = tensors[scales_name]
        biases = tensors[module + BIASES_SUFFIX]
        if weight["dtype"] != "U32":
            raise Refusal(f"{module}: quantized weight is {weight['dtype']}, not U32")
        if scales["dtype"] != biases["dtype"]:
            raise Refusal(f"{module}: scales {scales['dtype']} and biases {biases['dtype']}")

        packed = mx.array(
            np.frombuffer(weight["bytes"], dtype=np.uint32).copy().reshape(weight["shape"])
        )
        metadata_dtype = {"BF16": mx.bfloat16, "F16": mx.float16, "F32": mx.float32}[
            scales["dtype"]
        ]
        if scales["dtype"] == "F32":
            scale_array = mx.array(
                np.frombuffer(scales["bytes"], dtype=np.float32).copy().reshape(scales["shape"])
            )
            bias_array = mx.array(
                np.frombuffer(biases["bytes"], dtype=np.float32).copy().reshape(biases["shape"])
            )
        else:
            scale_array = mx.array(
                np.frombuffer(scales["bytes"], dtype=np.uint16).copy().reshape(scales["shape"])
            ).view(metadata_dtype)
            bias_array = mx.array(
                np.frombuffer(biases["bytes"], dtype=np.uint16).copy().reshape(biases["shape"])
            ).view(metadata_dtype)

        produced = mx.dequantize(
            packed, scale_array, bias_array, group_size=group_size, bits=bits, mode="affine"
        )
        mx.eval(produced)

        unit = mx.ones(scale_array.shape, dtype=mx.float32)
        zero = mx.zeros(scale_array.shape, dtype=mx.float32)
        codes = mx.dequantize(
            packed, unit, zero, group_size=group_size, bits=bits, mode="affine"
        )
        mx.eval(codes)

        case = expected[module]
        reference_f32 = np.array(case["dequant"], dtype=np.uint32).view(np.float32)
        reference = reference_f32.astype(np.float64).reshape(produced.shape)

        # Codes, compared as the finite floats they are returned as. Casting
        # to int64 first TRUNCATES: a returned 1.5 becomes 1 and passes a
        # comparison it should fail. The reference codes are widened to float
        # instead, so a fractional value cannot survive.
        observed_codes = np.array(codes, copy=False)
        if not np.all(np.isfinite(observed_codes)):
            raise Refusal(f"{module}: mx.dequantize returned a non-finite code")
        reference_codes = unpack_reference_codes(
            np.frombuffer(weight["bytes"], dtype=np.uint32),
            bits,
            case["rows"],
            case["columns"],
        )
        flat_codes = observed_codes.reshape(-1)
        codes_are_integral = bool(np.array_equal(flat_codes, np.rint(flat_codes)))
        codes_equal = codes_are_integral and bool(
            np.array_equal(flat_codes, reference_codes.astype(flat_codes.dtype))
        )
        if flat_codes.size and (
            flat_codes.min() < 0 or flat_codes.max() > (1 << bits) - 1
        ):
            raise Refusal(f"{module}: mx.dequantize returned a code outside 0..{(1 << bits) - 1}")

        # Values: R1 rounded to the output dtype, within one ulp of it.
        output_dtype = produced.dtype
        rounded = mx.array(reference.astype(np.float32)).astype(output_dtype)
        mx.eval(rounded)
        difference = mx.abs(produced.astype(mx.float32) - rounded.astype(mx.float32))
        bound = ulp_of(output_dtype, mx, rounded)
        mx.eval(difference, bound)
        within = bool(np.all(np.array(difference, copy=False) <= np.array(bound, copy=False)))
        max_difference = float(np.max(np.array(difference, copy=False)))
        # Bit identity means identical bit patterns. A numeric array_equal
        # says +0.0 == -0.0, which is exactly the distinction "bit-identical"
        # is supposed to make, so the two arrays are viewed as unsigned
        # integers of their own width and compared there.
        viewed = mx.uint16 if output_dtype in (mx.bfloat16, mx.float16) else mx.uint32
        produced_bits = np.array(produced.view(viewed), copy=False)
        rounded_bits = np.array(rounded.view(viewed), copy=False)
        exact = bool(np.array_equal(produced_bits, rounded_bits))

        results.append({
            "module": module,
            "kind": "quantized",
            "bits": bits,
            "group_size": group_size,
            "metadata_dtype": scales["dtype"],
            "output_dtype": str(output_dtype),
            "elements": int(produced.size),
            "codes_exactly_equal": codes_equal,
            "codes_are_integral": codes_are_integral,
            "values_within_one_ulp": within,
            "values_exactly_equal_after_rounding": exact,
            "max_abs_difference": max_difference,
            "result": "PASS" if (codes_equal and within) else "FAIL",
        })
    return results


def unpack_reference_codes(words, bits, rows, columns):
    """Codes from the packed stream, bit-serial, integers only."""
    import numpy as np

    per_word = 32 // bits
    if columns % per_word:
        raise Refusal("a row is not a whole number of packed words")
    packed_columns = columns // per_word
    grid = words.reshape(rows, packed_columns)
    out = np.empty((rows, columns), dtype=np.int64)
    mask = (1 << bits) - 1
    for index in range(columns):
        word = grid[:, index // per_word].astype(np.uint64)
        shift = np.uint64((index % per_word) * bits)
        out[:, index] = ((word >> shift) & np.uint64(mask)).astype(np.int64)
    return out.reshape(-1)


def environment(mx, mlx_version, metal_version):
    return {
        "interpreter": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "mlx_version": mlx_version,
        "mlx_metal_version": metal_version,
        "default_device": str(mx.default_device()),
        "metal_available": bool(mx.metal.is_available()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = FIXTURES / "manifest.json"
    report = {
        "schema": SCHEMA,
        "arm": "R2",
        "is_correctness_oracle": False,
        "statement": (
            "A compatibility observation against the pinned upstream MLX. Correctness is "
            "defined by R1; this arm never establishes it."
        ),
        "require_native_mlx": REQUIRE,
        "fixture_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()
        if manifest.is_file()
        else None,
    }

    try:
        mx, np, mlx_version, metal_version = acquire_runtime()
    except Refusal as refusal:
        return unavailable(args.output, report, str(refusal))
    except Exception as error:  # ImportError and anything the import raises
        return unavailable(args.output, report, f"MLX is unusable: {error!r}")

    report["environment"] = environment(mx, mlx_version, metal_version)
    report["environment"]["gpu_explicitly_selected"] = True

    cases = {}
    failures = 0
    quantized = 0
    try:
        for name in POSITIVES:
            directory = FIXTURES / name
            if not directory.is_dir():
                raise Refusal(f"{name} is absent")
            results = observe(mx, np, directory)
            cases[name] = results
            for entry in results:
                if entry["result"] == "FAIL":
                    failures += 1
                if entry.get("kind") == "quantized":
                    quantized += 1
    except Refusal as refusal:
        report["result"] = "REFUSED"
        report["detail"] = str(refusal)
        write(args.output, report)
        print(f"mlx_affine_compat_v1: REFUSED: {refusal}", file=sys.stderr)
        return 3

    report["cases"] = cases
    report["quantized_modules_observed"] = quantized
    report["failures"] = failures
    report["result"] = "PASS" if failures == 0 and quantized > 0 else "FAIL"
    write(args.output, report)
    print(json.dumps({k: report[k] for k in
                      ("result", "quantized_modules_observed", "failures", "environment")},
                     sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


def default_loader():
    """Import the pinned runtime. Replaced by a stub in tests."""
    from importlib.metadata import version

    import mlx.core as mx
    import numpy as np

    try:
        metal_version = version("mlx-metal")
    except Exception:
        metal_version = None
    return mx, np, version("mlx"), metal_version


def acquire_runtime(loader=default_loader):
    """Load MLX, require Metal, and put the work on the GPU explicitly.

    Factored out so that both refusal branches -- MLX unusable and Metal
    unavailable -- can be exercised deterministically by injecting a stub,
    rather than by relying on the test interpreter happening not to have MLX
    installed. An accident is not a test.
    """
    mx, np, mlx_version, metal_version = loader()
    if not mx.metal.is_available():
        raise Refusal("Metal is not available to this MLX build")
    # Metal being *available* is not the same as the work running on it.
    # Select the GPU explicitly and assert the selection took, so the
    # observation is about the device the brief names rather than whatever the
    # default happened to be.
    mx.set_default_device(mx.gpu)
    if mx.default_device() != mx.gpu:
        raise Refusal(f"the default device is {mx.default_device()} after selecting the GPU")
    return mx, np, mlx_version, metal_version


def unavailable(output: Path, report, detail: str) -> int:
    report["result"] = "UNAVAILABLE"
    report["detail"] = detail
    write(output, report)
    message = f"mlx_affine_compat_v1: {detail}"
    if REQUIRE:
        print(
            message
            + " -- PULSAR_REQUIRE_NATIVE_MLX=1, so this is a failure, not a skip.",
            file=sys.stderr,
        )
        return 2
    print(message + " -- PULSAR_REQUIRE_NATIVE_MLX is not 1, so this run is not required.")
    return 0


def write(output: Path, report) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=1) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

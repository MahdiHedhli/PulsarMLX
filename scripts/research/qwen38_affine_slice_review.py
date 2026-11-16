"""Review candidate: two bounded real-checkpoint affine rows, CPU only.

The real entry point is deliberately explicit and unqualified until its exact
source and execution packet pass independent review. Unit tests use generated
files only. No checkpoint Python or model graph is imported.
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from qwen38_page_catalog import TensorRef, admit_checkpoint_bound
from qwen38_verified_files import CHUNK_BYTES, VerifiedFiles


MAX_SELECTED_BYTES = 4_160
MAX_VALUES_PER_CASE = 2_560
MAX_AUTHENTICATED_CHUNK_READS = 12
MAX_RSS_BYTES = 512 * 2**20
ATOL = 1e-5
RTOL = 1e-5


@dataclass(frozen=True)
class Case:
    label: str
    prefix: str
    filename: str
    bits: int
    group_size: int
    weight_shape: tuple[int, ...]
    affine_shape: tuple[int, ...]


CASES = (
    Case("expert-4bit", "language_model.model.layers.2.mlp.switch_mlp.gate_proj",
         "model-00006.safetensors", 4, 64, (512, 640, 320), (512, 640, 40)),
    Case("text-8bit", "language_model.model.layers.0.linear_attn.in_proj_qkv",
         "model-00001.safetensors", 8, 64, (10240, 640), (10240, 40)),
)


def peak_rss_bytes() -> int:
    if sys.platform != "darwin":
        raise RuntimeError("RSS units have only been frozen for macOS")
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def check_rss() -> None:
    if peak_rss_bytes() > MAX_RSS_BYTES:
        raise RuntimeError("process peak RSS exceeded the 512 MiB stop value")


def selected_spans(tensors: dict[str, TensorRef], cases: tuple[Case, ...] = CASES):
    """Return only the first inner row, with exact pinned shapes and files."""
    spans = []
    for case in cases:
        refs = []
        for suffix, expected_dtype, expected_shape in (
            ("weight", "U32", case.weight_shape),
            ("scales", "BF16", case.affine_shape),
            ("biases", "BF16", case.affine_shape),
        ):
            ref = tensors[f"{case.prefix}.{suffix}"]
            if (ref.filename != case.filename or ref.dtype != expected_dtype or
                    ref.shape != expected_shape):
                raise ValueError(f"pinned affine tensor differs: {case.label}.{suffix}")
            item_bytes = 4 if expected_dtype == "U32" else 2
            length = ref.shape[-1] * item_bytes
            if ref.end - ref.start != math.prod(ref.shape) * item_bytes:
                raise ValueError("tensor span and shape differ")
            offset = ref.data_start + ref.start  # expert 0, inner row 0; or text row 0
            if length <= 0 or offset < ref.data_start or offset + length > ref.data_start + ref.end:
                raise ValueError("selected row is outside the admitted tensor")
            refs.append((ref.filename, offset, length))
        words = case.weight_shape[-1] * (32 // case.bits)
        if (words != MAX_VALUES_PER_CASE or
                words != case.affine_shape[-1] * case.group_size):
            raise ValueError("selected affine group geometry differs")
        spans.append(tuple(refs))
    selected_bytes = sum(length for triple in spans for _, _, length in triple)
    chunk_reads = sum((offset + length - 1) // CHUNK_BYTES - offset // CHUNK_BYTES + 1
                      for triple in spans for _, offset, length in triple)
    if selected_bytes != MAX_SELECTED_BYTES or chunk_reads > MAX_AUTHENTICATED_CHUNK_READS:
        raise ValueError("selected payload or authenticated read bound differs")
    return tuple(spans)


def read_selected(files: VerifiedFiles, spans) -> tuple[tuple[bytes, bytes, bytes], ...]:
    """Use only live descriptor-bound, identity-checked reads."""
    if (len(spans) != len(CASES) or any(len(triple) != 3 for triple in spans) or
            any(type(filename) is not str or type(offset) is not int or offset < 0 or
                type(length) is not int or not 0 < length <= 2_560
                for triple in spans for filename, offset, length in triple) or
            sum(length for triple in spans for _, _, length in triple) != MAX_SELECTED_BYTES):
        raise ValueError("selected read plan differs")
    result = []
    for triple in spans:
        parts = []
        for filename, offset, length in triple:
            target = bytearray(length)
            files.readinto(filename, memoryview(target), offset)
            parts.append(bytes(target))
        result.append(tuple(parts))
    return tuple(result)


def bf16_values(raw: bytes) -> tuple[float, ...]:
    if len(raw) % 2:
        raise ValueError("misaligned BF16 values")
    values = tuple(struct.unpack("<f", struct.pack("<I", word << 16))[0]
                   for (word,) in struct.iter_unpack("<H", raw))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite affine partner")
    return values


def scalar_dequantize(weight: bytes, scales: bytes, biases: bytes, *,
                      bits: int, group_size: int) -> tuple[float, ...]:
    """Independent integer extraction; no MLX, checkpoint code or tensor API."""
    if bits not in (4, 8) or group_size != 64 or len(weight) % 4:
        raise ValueError("unsupported packed row")
    words = tuple(word for (word,) in struct.iter_unpack("<I", weight))
    scale_values, bias_values = bf16_values(scales), bf16_values(biases)
    count = len(words) * (32 // bits)
    if (count != MAX_VALUES_PER_CASE or len(scale_values) != count // group_size or
            len(bias_values) != len(scale_values)):
        raise ValueError("affine partner geometry differs")
    mask = (1 << bits) - 1
    values = tuple(scale_values[i // group_size] *
                   ((words[i // (32 // bits)] >> (bits * (i % (32 // bits)))) & mask) +
                   bias_values[i // group_size] for i in range(count))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("nonfinite scalar output")
    return values


def compare_values(actual: tuple[float, ...], expected: tuple[float, ...]) -> dict:
    if len(actual) != MAX_VALUES_PER_CASE or len(expected) != MAX_VALUES_PER_CASE:
        raise ValueError("wrong affine output length")
    if not all(math.isfinite(value) for value in actual):
        raise ValueError("nonfinite backend output")
    errors = [abs(a - e) for a, e in zip(actual, expected)]
    failures = [i for i, (error, reference) in enumerate(zip(errors, expected))
                if error > ATOL + RTOL * abs(reference)]
    if failures:
        raise AssertionError(f"affine mismatch at {failures[0]}; failures={len(failures)}")
    return {"values": len(actual), "max_abs_error": max(errors),
            "atol": ATOL, "rtol": RTOL, "all_within_tolerance": True}


def run_real(root: Path) -> dict:
    check_rss()
    with admit_checkpoint_bound(root) as bound:
        check_rss()
        spans = selected_spans(bound.catalog.tensors)
        raw_cases = read_selected(bound.files, spans)
        check_rss()
        import mlx.core as mx  # Deliberately absent from static/synthetic tests.

        mx.set_default_device(mx.cpu)
        results = []
        for case, (weight, scales, biases) in zip(CASES, raw_cases):
            expected = scalar_dequantize(weight, scales, biases,
                                         bits=case.bits, group_size=case.group_size)
            w = mx.array([word for (word,) in struct.iter_unpack("<I", weight)],
                         dtype=mx.uint32).reshape(1, -1)
            s = mx.array(bf16_values(scales), dtype=mx.bfloat16).reshape(1, -1)
            b = mx.array(bf16_values(biases), dtype=mx.bfloat16).reshape(1, -1)
            actual_array = mx.dequantize(w, s, b, bits=case.bits,
                                         group_size=case.group_size, mode="affine",
                                         dtype=mx.float32)
            mx.eval(actual_array)
            actual = tuple(float(value) for value in actual_array.reshape(-1).tolist())
            result = compare_values(actual, expected)
            results.append({"case": case.label, "bits": case.bits,
                            "group_size": case.group_size, "filename": case.filename,
                            **result})
            check_rss()
    check_rss()
    return {"scope": "two real tensor rows; not model correctness",
            "device": "cpu", "selected_payload_bytes": MAX_SELECTED_BYTES,
            "maximum_authenticated_chunk_reads": MAX_AUTHENTICATED_CHUNK_READS,
            "maximum_peak_rss_bytes": MAX_RSS_BYTES, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_real(args.checkpoint), sort_keys=True))


if __name__ == "__main__":
    main()

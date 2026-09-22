#!/usr/bin/env python3
"""Generate the synthetic Safetensors fixtures under `fixtures/safetensors/`.

Stdlib only, seeded, deterministic bytes: running this twice produces the same
files byte for byte, and `--check` proves it without writing anything.

Three positive checkpoints and a directory of negative cases. The positives are
deliberately model-neutral: the module paths are `block.N....`, which belongs to
no model, because the crates under test must not be able to recognise a name.

*  `uniform-affine-v1` -- one shard, every module 4-bit group 64, a
   `config.json` carrying only the default.
*  `mixed-4-8-v1` -- three shards and an index; default 4-bit group 64, some
   modules overridden to 8-bit group 64, one to 8-bit group 32, one
   unquantized BF16 weight, one F32 vector, one stacked three-expert tensor at
   4 bits and `__metadata__` present. Gap-free: coverage is strict, so a
   positive checkpoint must tile its data buffer.
*  `mixed-4-8-index-total-size-v1` -- the same checkpoint with
   `metadata.total_size` declared in the index.
*  `metadata-variants-v1` -- one shard whose metadata is F16 and F32, at group
   128 as well as 64, so the R2 compatibility observation covers every metadata
   width and group size the representation admits rather than only the BF16
   groups 32 and 64 the first fixtures happened to use.

Each positive carries `expected.json`: the R1 dequantization of every quantized
module, as binary32 bit patterns, produced by
`scripts/research/mlx_affine_reference_v1.py`. MLX is not run here.

Each negative case is a directory with a one-line `README` naming the error
variant the crate must return.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mlx_affine_reference_v1 as r1  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures/safetensors"
MANIFEST = FIXTURES / "manifest.json"
SCHEMA = "pulsarmlx.f020.safetensors-fixtures/1.0.0"

DTYPE_SIZE = {
    "BOOL": 1, "U8": 1, "I8": 1, "F8_E5M2": 1, "F8_E4M3": 1,
    "I16": 2, "U16": 2, "F16": 2, "BF16": 2,
    "I32": 4, "U32": 4, "F32": 4,
    "F64": 8, "I64": 8, "U64": 8,
}


class Lcg:
    """A deterministic 64-bit LCG; the fixtures must not depend on `random`."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next_unit(self) -> float:
        self.state = (self.state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return ((self.state >> 11) & ((1 << 53) - 1)) / float(1 << 53)


# --- shard assembly --------------------------------------------------------


class ShardBuilder:
    """Lay tensors out back to back.

    `gap_before` exists only so a NEGATIVE fixture can be built: coverage is
    strict, so a positive checkpoint may not use it.
    """

    def __init__(self) -> None:
        self.entries: list[tuple[str, str, list[int], bytes, int]] = []

    def add(self, name, dtype, shape, payload, gap_before=0):
        expected = DTYPE_SIZE[dtype]
        for dimension in shape:
            expected *= dimension
        if len(payload) != expected:
            raise ValueError(f"{name}: {len(payload)} bytes, shape and dtype need {expected}")
        self.entries.append((name, dtype, list(shape), payload, gap_before))
        return self

    def build(self, metadata=None):
        header = {}
        if metadata is not None:
            header["__metadata__"] = metadata
        data = bytearray()
        for name, dtype, shape, payload, gap_before in self.entries:
            data.extend(b"\0" * gap_before)
            begin = len(data)
            data.extend(payload)
            header[name] = {"dtype": dtype, "shape": shape,
                            "data_offsets": [begin, len(data)]}
        text = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
        return struct.pack("<Q", len(text)) + text + bytes(data)


def raw_header(header_object, data=b""):
    text = json.dumps(header_object, sort_keys=True, separators=(",", ":")).encode()
    return struct.pack("<Q", len(text)) + text + data


def words_to_bytes(words):
    return b"".join(struct.pack("<I", word) for word in words)


def metadata_to_bytes(bit_patterns, dtype):
    if dtype == "F32":
        return b"".join(struct.pack("<I", bits) for bits in bit_patterns)
    return b"".join(struct.pack("<H", bits) for bits in bit_patterns)


# --- quantized module construction ----------------------------------------


def quantized_module(rng, *, leading, out_features, in_features, bits, group,
                     metadata_dtype):
    """Return (weight_bytes, scales_bytes, biases_bytes, shapes, expected)."""
    planes = 1
    for extent in leading:
        planes *= extent
    rows = planes * out_features
    values = [(rng.next_unit() - 0.5) * 4.0 for _ in range(rows * in_features)]
    words, scales, biases = r1.quantize_rows(
        values, bits=bits, group_size=group, rows=rows, columns=in_features,
        metadata_dtype=metadata_dtype,
    )
    convert = r1.CONVERTERS[metadata_dtype]
    decoded = r1.dequantize_rows(
        words,
        [r1.float_to_f32_bits(convert(b)) for b in scales],
        [r1.float_to_f32_bits(convert(b)) for b in biases],
        bits=bits, group_size=group, rows=rows, columns=in_features,
        metadata_dtype="F32",
    )
    packed_cols = in_features * bits // 32
    groups = in_features // group
    shapes = {
        "weight": list(leading) + [out_features, packed_cols],
        "metadata": list(leading) + [out_features, groups],
    }
    expected = {
        "rows": rows,
        "columns": in_features,
        "bits": bits,
        "group_size": group,
        "metadata_dtype": metadata_dtype,
        "dequant": [r1.float_to_f32_bits(value) for value in decoded],
    }
    return (
        words_to_bytes(words),
        metadata_to_bytes(scales, metadata_dtype),
        metadata_to_bytes(biases, metadata_dtype),
        shapes,
        expected,
    )


def bf16_vector(rng, count):
    return b"".join(
        struct.pack("<H", r1.float_to_bf16_bits(rng.next_unit() * 2.0 - 1.0))
        for _ in range(count)
    )


def f32_vector(rng, count):
    return b"".join(
        struct.pack("<f", rng.next_unit() * 2.0 - 1.0) for _ in range(count)
    )


# --- the positive checkpoints ---------------------------------------------


def metadata_variants_checkpoint():
    """A positive checkpoint whose metadata is F16 and F32, at group 128.

    The Round 1 corpus stored BF16 metadata at groups 32 and 64 only, so the
    R2 observation only ever saw `mx.dequantize` return bfloat16 and never
    exercised group 128 through MLX at all. These modules close that: the
    compatibility claim should cover every width the representation admits,
    not only the one the first fixtures happened to use.
    """
    rng = Lcg(0x0020_0004)
    expected = {}
    builder = ShardBuilder()
    plan = [
        ("block.0.half", "F16", 4, 128, 4, 128),
        ("block.1.single", "F32", 4, 128, 4, 128),
        ("block.2.half_eight", "F16", 2, 128, 8, 64),
        ("block.3.single_group128", "F32", 2, 256, 8, 128),
    ]
    for module, metadata_dtype, out_features, in_features, bits, group in plan:
        weight, scales, biases, shapes, values = quantized_module(
            rng, leading=[], out_features=out_features, in_features=in_features,
            bits=bits, group=group, metadata_dtype=metadata_dtype,
        )
        builder.add(f"{module}.weight", "U32", shapes["weight"], weight)
        builder.add(f"{module}.scales", metadata_dtype, shapes["metadata"], scales)
        builder.add(f"{module}.biases", metadata_dtype, shapes["metadata"], biases)
        expected[module] = values
    files = {"model.safetensors": builder.build(metadata={"format": "mlx"})}
    quantization = {"group_size": 128, "bits": 4}
    for module, _md, _o, _i, bits, group in plan:
        if (bits, group) != (4, 128):
            quantization[module] = {"group_size": group, "bits": bits}
    files["config.json"] = (
        json.dumps({"model_type": "synthetic-metadata-variants",
                    "quantization": quantization}, sort_keys=True, indent=1) + "\n"
    ).encode()
    files["expected.json"] = (
        json.dumps({"schema": SCHEMA, "modules": expected}, sort_keys=True, indent=1) + "\n"
    ).encode()
    return files


def uniform_checkpoint():
    rng = Lcg(0x0020_0001)
    files = {}
    expected = {}
    builder = ShardBuilder()
    for index in range(3):
        module = f"block.{index}.proj"
        weight, scales, biases, shapes, values = quantized_module(
            rng, leading=[], out_features=4, in_features=128, bits=4, group=64,
            metadata_dtype="BF16",
        )
        builder.add(f"{module}.weight", "U32", shapes["weight"], weight)
        builder.add(f"{module}.scales", "BF16", shapes["metadata"], scales)
        builder.add(f"{module}.biases", "BF16", shapes["metadata"], biases)
        expected[module] = values
    files["model.safetensors"] = builder.build(metadata={"format": "mlx"})
    files["config.json"] = (
        json.dumps({"model_type": "synthetic-uniform",
                    "quantization": {"group_size": 64, "bits": 4}},
                   sort_keys=True, indent=1) + "\n"
    ).encode()
    files["expected.json"] = (
        json.dumps({"schema": SCHEMA, "modules": expected}, sort_keys=True, indent=1) + "\n"
    ).encode()
    return files


def mixed_checkpoint(total_size: bool):
    rng = Lcg(0x0020_0002)
    expected = {}
    overrides = {}
    weight_map = {}

    first = ShardBuilder()
    second = ShardBuilder()
    third = ShardBuilder()

    def place(builder, shard, module, leading, out_features, in_features, bits,
              group, metadata_dtype, gap=0):
        weight, scales, biases, shapes, values = quantized_module(
            rng, leading=leading, out_features=out_features,
            in_features=in_features, bits=bits, group=group,
            metadata_dtype=metadata_dtype,
        )
        builder.add(f"{module}.weight", "U32", shapes["weight"], weight, gap_before=gap)
        builder.add(f"{module}.scales", metadata_dtype, shapes["metadata"], scales)
        builder.add(f"{module}.biases", metadata_dtype, shapes["metadata"], biases)
        for suffix in ("weight", "scales", "biases"):
            weight_map[f"{module}.{suffix}"] = shard
        expected[module] = values
        return values

    # Shard 1: two modules at the default 4-bit group 64, and one overridden
    # to 8-bit group 64. A gap is left in front of the third module's weight.
    place(first, "model-00001.safetensors", "block.0.gate", [], 4, 128, 4, 64, "BF16")
    place(first, "model-00001.safetensors", "block.0.up", [], 4, 128, 4, 64, "BF16")
    place(first, "model-00001.safetensors", "block.0.down", [], 4, 128, 8, 64, "BF16")
    overrides["block.0.down"] = {"group_size": 64, "bits": 8}

    # Shard 2: the module overridden to 8-bit group 32, the unquantized BF16
    # weight and the F32 vector.
    place(second, "model-00002.safetensors", "block.1.attn", [], 8, 128, 8, 32, "BF16")
    overrides["block.1.attn"] = {"group_size": 32, "bits": 8}
    second.add("block.1.router.weight", "BF16", [6, 32], bf16_vector(rng, 6 * 32))
    weight_map["block.1.router.weight"] = "model-00002.safetensors"
    second.add("block.1.router.correction", "F32", [6], f32_vector(rng, 6))
    weight_map["block.1.router.correction"] = "model-00002.safetensors"

    # Shard 3: a stacked three-expert tensor at the default 4 bits.
    place(third, "model-00003.safetensors", "block.2.experts", [3], 4, 128, 4, 64, "BF16")

    files = {
        "model-00001.safetensors": first.build(metadata={"format": "mlx", "shard": "1"}),
        "model-00002.safetensors": second.build(metadata={"format": "mlx", "shard": "2"}),
        "model-00003.safetensors": third.build(metadata={"format": "mlx", "shard": "3"}),
    }
    index = {"weight_map": dict(sorted(weight_map.items()))}
    if total_size:
        index["metadata"] = {
            "total_size": sum(
                sum(
                    DTYPE_SIZE[entry[1]] * _product(entry[2])
                    for entry in builder.entries
                )
                for builder in (first, second, third)
            )
        }
    files["model.safetensors.index.json"] = (
        json.dumps(index, sort_keys=True, indent=1) + "\n"
    ).encode()
    quantization = {"group_size": 64, "bits": 4}
    quantization.update(dict(sorted(overrides.items())))
    files["config.json"] = (
        json.dumps({"model_type": "synthetic-mixed", "quantization": quantization},
                   sort_keys=True, indent=1) + "\n"
    ).encode()
    files["expected.json"] = (
        json.dumps({"schema": SCHEMA, "modules": expected}, sort_keys=True, indent=1) + "\n"
    ).encode()
    return files


def _product(shape):
    total = 1
    for extent in shape:
        total *= extent
    return total


# --- the negative cases ----------------------------------------------------


def tiny_quantized(bits=4, group=64, out_features=2, in_features=64,
                   metadata_dtype="BF16", leading=()):
    rng = Lcg(0x0020_0003)
    return quantized_module(
        rng, leading=list(leading), out_features=out_features,
        in_features=in_features, bits=bits, group=group,
        metadata_dtype=metadata_dtype,
    )


def one_shard_case(tensors, metadata=None):
    builder = ShardBuilder()
    for entry in tensors:
        builder.add(*entry)
    return builder.build(metadata=metadata)


DEFAULT_CONFIG = (
    json.dumps({"quantization": {"group_size": 64, "bits": 4}}, sort_keys=True, indent=1) + "\n"
).encode()


def special_cases():
    """Negative cases that need a non-regular file, which bytes cannot express.

    Returns name -> (variant, note, {leaf: ("symlink", target) | ("dir",)}).
    These exist because containment has to be decided about the object a
    descriptor holds, not about a string, and a string cannot be a symlink.
    """
    return {
        "path-symlink-shard-escape": (
            "CatalogError::PathEscape",
            "The only shard is a symbolic link pointing outside the checkpoint root.",
            {"model.safetensors": ("symlink", "../../../../etc/hosts")},
        ),
        "path-symlink-shard-inside": (
            "CatalogError::PathEscape",
            "The only shard is a symbolic link, even though its target is inside the root.",
            {"real.bin": ("file", b"\x00" * 8),
             "model.safetensors": ("symlink", "real.bin")},
        ),
        "index-symlink": (
            "CatalogError::InvalidIndex",
            "model.safetensors.index.json is a symbolic link, so it is refused rather than ignored.",
            {"model.safetensors.index.json": ("symlink", "elsewhere.json")},
        ),
        "index-is-a-directory": (
            "CatalogError::InvalidIndex",
            "model.safetensors.index.json exists as a directory; absence and invalidity are different.",
            {"model.safetensors.index.json/.keep": ("file", b"")},
        ),
    }


def negative_cases():
    """name -> (error variant, one-line README, {file: bytes})."""
    cases = {}
    weight, scales, biases, shapes, _ = tiny_quantized()

    def simple_shard():
        return one_shard_case([
            ("m.weight", "U32", shapes["weight"], weight),
            ("m.scales", "BF16", shapes["metadata"], scales),
            ("m.biases", "BF16", shapes["metadata"], biases),
        ])

    # --- header bytes ---
    cases["header-truncated-length-prefix"] = (
        "CatalogError::MalformedHeader",
        "The file holds four bytes, which cannot carry the eight-byte length prefix.",
        {"model.safetensors": b"\x10\x00\x00\x00"},
    )
    cases["header-length-beyond-file"] = (
        "CatalogError::MalformedHeader",
        "The length prefix declares more header bytes than the file contains.",
        {"model.safetensors": struct.pack("<Q", 4096) + b"{}"},
    )
    cases["header-not-an-object"] = (
        "CatalogError::MalformedHeader",
        "The header is an array; the format says the object begins immediately after the prefix.",
        {"model.safetensors": raw_header([1, 2, 3])},
    )
    cases["header-metadata-non-string"] = (
        "CatalogError::InvalidMetadata",
        "__metadata__ carries a non-string value.",
        {"model.safetensors": raw_header(
            {"__metadata__": {"format": 7},
             "a": {"dtype": "U8", "shape": [1], "data_offsets": [0, 1]}},
            b"\0")},
    )
    cases["header-duplicate-tensor-name"] = (
        "CatalogError::DuplicateKey",
        "One header declares the same tensor name twice, which is a repeated JSON member.",
        {"model.safetensors": struct.pack("<Q", 108) + (
            b'{"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]},'
            b'"a":{"dtype":"U8","shape":[1],"data_offsets":[1,2]}}'
        ).ljust(108, b" ") + b"\0\0"},
    )
    cases["header-overlapping-ranges"] = (
        "CatalogError::OverlappingRanges",
        "Two tensors in one shard claim overlapping byte ranges.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]},
             "b": {"dtype": "U8", "shape": [4], "data_offsets": [2, 6]}},
            b"\0" * 6)},
    )
    cases["header-range-beyond-data"] = (
        "CatalogError::InvalidRange",
        "A tensor range extends past the end of the data section.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "U8", "shape": [8], "data_offsets": [0, 8]}}, b"\0" * 4)},
    )
    cases["header-length-mismatch"] = (
        "CatalogError::LengthMismatch",
        "The declared range is not shape product times dtype size.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "F32", "shape": [2, 3], "data_offsets": [0, 20]}}, b"\0" * 20)},
    )
    cases["header-unsupported-dtype"] = (
        "CatalogError::UnsupportedDtype",
        "The dtype string is not a standard Safetensors dtype.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "MXFP4", "shape": [4], "data_offsets": [0, 4]}}, b"\0" * 4)},
    )
    cases["header-shape-overflow"] = (
        "CatalogError::Overflow",
        "Three dimensions of u32::MAX each: every dimension is admissible and only the product overflows.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "F32", "shape": [4294967295, 4294967295, 4294967295],
                   "data_offsets": [0, 4]}}, b"\0" * 4)},
    )

    cases["header-uncovered-gap"] = (
        "CatalogError::Gap",
        "A shard leaves eight bytes between two tensors; upstream requires the buffer to be tiled.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]},
             "b": {"dtype": "U8", "shape": [4], "data_offsets": [12, 16]}},
            b"\0" * 16)},
    )
    cases["header-trailing-uncovered-bytes"] = (
        "CatalogError::Gap",
        "A shard declares a data section longer than its tensors cover.",
        {"model.safetensors": raw_header(
            {"a": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]}}, b"\0" * 8)},
    )
    cases["header-leading-whitespace"] = (
        "CatalogError::MalformedHeader",
        "The header begins with a space before '{'; the format says the object begins immediately.",
        {"model.safetensors": struct.pack("<Q", 55) + (
            b' {"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}'
        ).ljust(55, b" ") + b"\0"},
    )

    # --- duplicate JSON members, at every depth (Astra finding 2) ---
    # Each of these has two readings. In every one the LAST occurrence is
    # perfectly valid, which is exactly why accepting it would be wrong.
    cases["json-duplicate-tensor-dtype"] = (
        "CatalogError::DuplicateKey",
        'A tensor entry declares "dtype" twice; the geometry matches the second.',
        {"model.safetensors": struct.pack("<Q", 86) + (
            b'{"a":{"dtype":"U8","dtype":"U16","shape":[2],"data_offsets":[0,4]}}'
        ).ljust(86, b" ") + b"\0\0\0\0"},
    )
    cases["json-duplicate-metadata-member"] = (
        "CatalogError::DuplicateKey",
        '__metadata__ declares "format" twice, first as a number and then as a string.',
        {"model.safetensors": struct.pack("<Q", 100) + (
            b'{"__metadata__":{"format":7,"format":"mlx"},'
            b'"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}'
        ).ljust(100, b" ") + b"\0"},
    )
    cases["json-duplicate-weight-map-entry"] = (
        "CatalogError::DuplicateKey",
        "The index maps one tensor name twice; the first value names a missing shard.",
        {"model.safetensors": simple_shard(),
         "model.safetensors.index.json":
             b'{"weight_map":{"m.weight":"absent.safetensors","m.weight":"model.safetensors",'
             b'"m.scales":"model.safetensors","m.biases":"model.safetensors"}}\n'},
    )
    cases["json-duplicate-quantization-bits"] = (
        "AffineError::DuplicateConfigKey",
        'The quantization object declares "bits" twice, 3 and then the admitted 4.',
        {"model.safetensors": one_shard_case([
            ("m.weight", "U32", shapes["weight"], weight),
            ("m.scales", "BF16", shapes["metadata"], scales),
            ("m.biases", "BF16", shapes["metadata"], biases),
         ]),
         "config.json": b'{"quantization":{"group_size":64,"bits":3,"bits":4}}\n'},
    )

    # --- one name, two spellings (Astra round-2 finding 2) ---
    # The duplicate cases above all repeat a member byte for byte, so they are
    # caught by any comparison at all. These three are caught only by a
    # comparison that decodes \uXXXX escapes first, which is what the guard
    # claims to do and what nothing previously exercised.

    def framed(header: bytes, payload: bytes = b"") -> bytes:
        return struct.pack("<Q", len(header)) + header + payload

    cases["json-escaped-duplicate-tensor-name"] = (
        "CatalogError::DuplicateKey",
        'Two tensor entries whose names are "\\u006d" and "m": one member, spelled twice.',
        {"model.safetensors": framed(
            b'{"\\u006d":{"dtype":"U8","shape":[2],"data_offsets":[0,2]},'
            b'"m":{"dtype":"U8","shape":[2],"data_offsets":[2,4]}}',
            b"\0\0\0\0",
        )},
    )
    cases["json-surrogate-pair-duplicate-metadata"] = (
        "CatalogError::DuplicateKey",
        "__metadata__ names one emoji twice, once as a surrogate pair and once literally.",
        {"model.safetensors": framed(
            b'{"__metadata__":{"\\ud83d\\ude00":"first","\xf0\x9f\x98\x80":"second"},'
            b'"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}',
            b"\0",
        )},
    )
    cases["json-lone-surrogate-tensor-name"] = (
        "CatalogError::InvalidJson",
        "A tensor name is a lone high surrogate, which is not a Unicode scalar value.",
        {"model.safetensors": framed(
            b'{"\\ud83d":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}',
            b"\0",
        )},
    )

    # --- layout and index ---
    cases["layout-missing-shard"] = (
        "CatalogError::MissingShard",
        "The index names a shard file that does not exist under the root.",
        {"model.safetensors": simple_shard(),
         "model.safetensors.index.json": json.dumps(
             {"weight_map": {"m.weight": "model.safetensors",
                             "m.scales": "model.safetensors",
                             "m.biases": "model.safetensors",
                             "gone": "model-00002.safetensors"}},
             sort_keys=True, indent=1).encode() + b"\n"},
    )
    cases["layout-unindexed-tensor"] = (
        "CatalogError::UnindexedTensor",
        "A shard holds a tensor the index does not map: no silent extras.",
        {"model.safetensors": simple_shard(),
         "model.safetensors.index.json": json.dumps(
             {"weight_map": {"m.weight": "model.safetensors"}},
             sort_keys=True, indent=1).encode() + b"\n"},
    )
    cases["layout-indexed-tensor-absent"] = (
        "CatalogError::MissingTensorInShard",
        "The index maps a tensor to a shard whose header does not contain it.",
        {"model.safetensors": simple_shard(),
         "model.safetensors.index.json": json.dumps(
             {"weight_map": {"m.weight": "model.safetensors",
                             "m.scales": "model.safetensors",
                             "m.biases": "model.safetensors",
                             "m.absent": "model.safetensors"}},
             sort_keys=True, indent=1).encode() + b"\n"},
    )
    cross_a = one_shard_case([("x.weight", "U8", [4], b"\0\1\2\3")])
    cross_b = one_shard_case([("y.weight", "U8", [4], b"\4\5\6\7")])
    cases["layout-cross-shard-mismatch"] = (
        "CatalogError::MissingTensorInShard",
        "The index says x lives in shard A; it lives in shard B.",
        {"model-00001.safetensors": cross_a,
         "model-00002.safetensors": cross_b,
         "model.safetensors.index.json": json.dumps(
             {"weight_map": {"x.weight": "model-00002.safetensors",
                             "y.weight": "model-00001.safetensors"}},
             sort_keys=True, indent=1).encode() + b"\n"},
    )
    cases["layout-ambiguous-two-shards"] = (
        "CatalogError::AmbiguousLayout",
        "No index and two candidate shards, so the layout is not decidable.",
        {"a.safetensors": cross_a, "b.safetensors": cross_b},
    )
    for label, path in (
        ("parent", "../escape.safetensors"),
        ("absolute", "/tmp/escape.safetensors"),
        ("subdirectory", "sub/escape.safetensors"),
    ):
        cases[f"path-traversal-{label}"] = (
            "CatalogError::InvalidShardPath",
            f"The weight_map names {path!r}, which is not a plain file name inside the root.",
            {"model.safetensors": simple_shard(),
             "model.safetensors.index.json": json.dumps(
                 {"weight_map": {"m.weight": path}}, sort_keys=True, indent=1).encode() + b"\n"},
        )

    # --- affine triples and configuration ---
    def triple_case(name, variant, note, tensors, config=DEFAULT_CONFIG):
        cases[name] = (variant, note,
                       {"model.safetensors": one_shard_case(tensors),
                        "config.json": config})

    triple_case(
        "triple-weight-without-scales", "AffineError::IncompleteTriple",
        "A packed U32 weight with neither .scales nor .biases.",
        [("m.weight", "U32", shapes["weight"], weight)],
    )
    triple_case(
        "triple-scales-without-biases", "AffineError::IncompleteTriple",
        "A weight and .scales, but no .biases.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales)],
    )
    triple_case(
        "triple-biases-only", "AffineError::IncompleteTriple",
        "Only .biases is present; there is no .weight to anchor the module.",
        [("m.biases", "BF16", shapes["metadata"], biases)],
    )
    triple_case(
        "triple-dtype-mismatch", "AffineError::ScalesBiasesMismatch",
        "Scales are BF16 and biases are F16.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "F16", shapes["metadata"], b"\0" * len(biases))],
    )
    triple_case(
        "triple-shape-mismatch", "AffineError::ScalesBiasesMismatch",
        "Scales and biases have different shapes.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "BF16", [shapes["metadata"][0], shapes["metadata"][1] * 2],
          biases + biases)],
    )
    triple_case(
        "config-inconsistent-override", "AffineError::InconsistentOverride",
        "The override claims 8 bits; the stored shapes imply 4.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "BF16", shapes["metadata"], biases)],
        config=(json.dumps({"quantization": {"group_size": 64, "bits": 4,
                                             "m": {"group_size": 64, "bits": 8}}},
                           sort_keys=True, indent=1) + "\n").encode(),
    )
    triple_case(
        "config-override-without-scales", "AffineError::OverrideWithoutScales",
        "A module carries an explicit override but has no .scales tensor.",
        [("m.weight", "BF16", [4, 8], b"\0" * 64)],
        config=(json.dumps({"quantization": {"group_size": 64, "bits": 4,
                                             "m": {"group_size": 64, "bits": 8}}},
                           sort_keys=True, indent=1) + "\n").encode(),
    )
    triple_case(
        "config-scales-without-quantization", "AffineError::AmbiguousQuantization",
        "The shards say quantized and config.json declares no quantization object.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "BF16", shapes["metadata"], biases)],
        config=(json.dumps({"model_type": "synthetic"}, sort_keys=True, indent=1) + "\n").encode(),
    )
    for bits in (3, 6):
        triple_case(
            f"config-unsupported-bits-{bits}", "AffineError::UnsupportedQuantization",
            f"The configuration asks for {bits} bits, which this crate does not implement.",
            [("m.weight", "U32", shapes["weight"], weight),
             ("m.scales", "BF16", shapes["metadata"], scales),
             ("m.biases", "BF16", shapes["metadata"], biases)],
            config=(json.dumps({"quantization": {"group_size": 64, "bits": bits}},
                               sort_keys=True, indent=1) + "\n").encode(),
        )
    for group in (16, 256):
        triple_case(
            f"config-unsupported-group-{group}", "AffineError::UnsupportedQuantization",
            f"The configuration asks for group_size {group}, which MLX affine does not define.",
            [("m.weight", "U32", shapes["weight"], weight),
             ("m.scales", "BF16", shapes["metadata"], scales),
             ("m.biases", "BF16", shapes["metadata"], biases)],
            config=(json.dumps({"quantization": {"group_size": group, "bits": 4}},
                               sort_keys=True, indent=1) + "\n").encode(),
        )
    triple_case(
        "config-unsupported-mode", "AffineError::UnsupportedQuantization",
        "The configuration declares mode mxfp4; only affine is implemented.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "BF16", shapes["metadata"], biases)],
        config=(json.dumps({"quantization": {"group_size": 64, "bits": 4, "mode": "mxfp4"}},
                           sort_keys=True, indent=1) + "\n").encode(),
    )
    triple_case(
        "config-dicts-differ", "AffineError::InconsistentConfig",
        "quantization and quantization_config are both present and differ.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "BF16", shapes["metadata"], biases)],
        config=(json.dumps({"quantization": {"group_size": 64, "bits": 4},
                            "quantization_config": {"group_size": 64, "bits": 8}},
                           sort_keys=True, indent=1) + "\n").encode(),
    )
    triple_case(
        "config-non-object-override", "AffineError::UnsupportedOverrideValue",
        "An override is the boolean false; the upstream loader's False semantics are not admitted.",
        [("m.weight", "U32", shapes["weight"], weight),
         ("m.scales", "BF16", shapes["metadata"], scales),
         ("m.biases", "BF16", shapes["metadata"], biases)],
        config=(json.dumps({"quantization": {"group_size": 64, "bits": 4, "m": False}},
                           sort_keys=True, indent=1) + "\n").encode(),
    )
    return cases


# --- driver ---------------------------------------------------------------


def all_files():
    files: dict[str, bytes] = {}
    for name, produced in (
        ("uniform-affine-v1", uniform_checkpoint()),
        ("mixed-4-8-v1", mixed_checkpoint(total_size=False)),
        ("mixed-4-8-index-total-size-v1", mixed_checkpoint(total_size=True)),
        ("metadata-variants-v1", metadata_variants_checkpoint()),
    ):
        for leaf, body in produced.items():
            files[f"{name}/{leaf}"] = body
    for case, (variant, note, produced) in negative_cases().items():
        files[f"negative/{case}/README"] = (
            f"{variant}\n{note}\n"
        ).encode()
        for leaf, body in produced.items():
            files[f"negative/{case}/{leaf}"] = body
    for case, (variant, note, produced) in special_cases().items():
        files[f"negative/{case}/README"] = (
            f"{variant}\n{note}\n"
        ).encode()
        for leaf, entry in produced.items():
            if entry[0] == "file":
                files[f"negative/{case}/{leaf}"] = entry[1]
    return files


def all_specials():
    """path -> ("symlink", target) for entries that are not regular files."""
    specials = {}
    for case, (_variant, _note, produced) in special_cases().items():
        for leaf, entry in produced.items():
            if entry[0] == "symlink":
                specials[f"negative/{case}/{leaf}"] = entry[1]
    return specials


def build_manifest(files):
    return {
        "schema": SCHEMA,
        "generator": "scripts/research/generate_safetensors_fixtures_v1.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reference": "scripts/research/mlx_affine_reference_v1.py",
        "reference_sha256": hashlib.sha256(
            (ROOT / "scripts/research/mlx_affine_reference_v1.py").read_bytes()
        ).hexdigest(),
        "mlx_was_not_run": True,
        "positive": [
            "uniform-affine-v1",
            "mixed-4-8-v1",
            "mixed-4-8-index-total-size-v1",
            "metadata-variants-v1",
        ],
        "negative": sorted(list(negative_cases()) + list(special_cases())),
        "symlinks": dict(sorted(all_specials().items())),
        "files": {path: {"bytes": len(body),
                         "sha256": hashlib.sha256(body).hexdigest()}
                  for path, body in sorted(files.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("pass exactly one of --write and --check")

    files = all_files()
    specials = all_specials()
    manifest = build_manifest(files)
    encoded = (json.dumps(manifest, sort_keys=True, indent=1) + "\n").encode()

    if args.write:
        for path, body in files.items():
            target = FIXTURES / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        for path, destination in specials.items():
            target = FIXTURES / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(destination)
        MANIFEST.write_bytes(encoded)
        print(json.dumps({"result": "WROTE", "files": len(files),
                          "bytes": sum(len(b) for b in files.values())}, sort_keys=True))
        return 0

    problems = []
    if not MANIFEST.is_file():
        problems.append("manifest.json is absent")
    elif MANIFEST.read_bytes() != encoded:
        problems.append("manifest.json does not match what this generator produces")
    for path, body in files.items():
        target = FIXTURES / path
        if not target.is_file():
            problems.append(f"{path} is absent")
        elif target.read_bytes() != body:
            problems.append(f"{path} does not match what this generator produces")
    for path, destination in specials.items():
        target = FIXTURES / path
        if not target.is_symlink():
            problems.append(f"{path} is not a symbolic link")
        elif os.readlink(target) != destination:
            problems.append(f"{path} does not point at {destination}")
    # `golden-affine-dequant-v1/` has its own generator and its own
    # provenance, and the corpus README is prose, so neither is this
    # generator's output; everything else under fixtures/safetensors must be.
    existing = {
        str(path.relative_to(FIXTURES))
        for path in FIXTURES.rglob("*")
        if (path.is_file() or path.is_symlink())
        and not str(path.relative_to(FIXTURES)).startswith("golden-")
        and str(path.relative_to(FIXTURES)) not in ("manifest.json", "README.md")
    }
    for extra in sorted(existing - set(files) - set(specials)):
        problems.append(f"{extra} is not produced by this generator")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    print(json.dumps({"result": "PASS", "files": len(files),
                      "bytes": sum(len(b) for b in files.values())}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and check the golden MLX affine dequantization fixture.

The fixture has two blocks.

`adopted` is the nine-case fixture that arrived untracked in the shared
checkout as `crates/mlx-safetensors/tests/data/golden_mlx_dequant.json`
(20,460 bytes, mtime 2026-09-21 18:13, sha256 recorded in the fixture's
`provenance`). Phase 0 worker W1 re-derived all nine cases independently and
reported them self-consistent; this script re-derives them again, from the
stored `words`/`scales`/`biases` through the R1 reference, and refuses to write
a fixture whose `dequant` it cannot reproduce. Its authority is exactly that:
self-consistency plus two independent re-derivations. It was not produced by a
committed generator and carries no MLX version, so it is a regression baseline,
not an upstream oracle.

`extended` closes the gaps W1 recorded. Every adopted case has `cols == group`,
so none of them pins the layout of `scales`/`biases` when a row spans several
groups -- the one ambiguity a real checkpoint actually presents. The extended
cases add multi-group rows (`in == 4 * group`), `group_size` 128, 8 bits,
BF16 and F16 metadata, an F32-metadata case, and groups the MLX encoder's
signed, edge-snapped rule drives to a negative scale or to a zero bias. They
are generated here by the R1 encoder described in
`scripts/research/mlx_affine_reference_v1.py`, from the written specification
of MLX's implemented encoder -- not by running MLX. Whether the pinned MLX
agrees with them is a separate, labelled observation made by
`scripts/ci/mlx_affine_compat_v1.py`; it is not assumed here.

Encoding: every floating-point quantity in the fixture is stored as the
IEEE-754 binary32 bit pattern of its value, as a JSON integer. `metadata_dtype`
says what a checkpoint would store the scales and biases in; when it is BF16 or
F16 the stored binary32 pattern is exactly representable in that format, which
the checker asserts.

Usage:
    generate_golden_affine_dequant_v1.py --write   # regenerate the extended block
    generate_golden_affine_dequant_v1.py --check   # verify the committed file
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mlx_affine_reference_v1 as r1  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/safetensors/golden-affine-dequant-v1/golden.json"
SCHEMA = "pulsarmlx.f020.golden-affine-dequant/1.0.0"
ADOPTED_SOURCE_SHA256 = "88acea83f0ca4826e5cfae71abadb3cb17ad1b21db43433c2ea38e8b6a1c0a17"


class Lcg:
    """A tiny deterministic generator; the fixture must not depend on `random`."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next_unit(self) -> float:
        # Numerical Recipes' 64-bit LCG constants.
        self.state = (self.state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return ((self.state >> 11) & ((1 << 53) - 1)) / float(1 << 53)


def make_case(name, *, rows, cols, group, bits, metadata_dtype, seed, shaper):
    rng = Lcg(seed)
    values = [shaper(rng.next_unit(), index) for index in range(rows * cols)]
    words, scales, biases = r1.quantize_rows(
        values, bits=bits, group_size=group, rows=rows, columns=cols,
        metadata_dtype=metadata_dtype,
    )
    convert = r1.CONVERTERS[metadata_dtype]
    scale_f32 = [r1.float_to_f32_bits(convert(bits_)) for bits_ in scales]
    bias_f32 = [r1.float_to_f32_bits(convert(bits_)) for bits_ in biases]
    decoded = r1.dequantize_rows(
        words, scale_f32, bias_f32, bits=bits, group_size=group, rows=rows,
        columns=cols, metadata_dtype="F32",
    )
    return name, {
        "rows": rows,
        "cols": cols,
        "group": group,
        "bits": bits,
        "metadata_dtype": metadata_dtype,
        "words": words,
        "scales": scale_f32,
        "biases": bias_f32,
        "dequant": [r1.float_to_f32_bits(value) for value in decoded],
    }


def extended_cases():
    cases = {}

    def add(pair):
        cases[pair[0]] = pair[1]

    # A row spanning four groups: the layout the adopted cases cannot pin.
    add(make_case("multigroup_4bit_g64", rows=3, cols=256, group=64, bits=4,
                  metadata_dtype="BF16", seed=1,
                  shaper=lambda unit, index: (unit - 0.5) * (1.0 + index % 7)))
    # group_size 128, the common MLX 4-bit default.
    add(make_case("multigroup_4bit_g128", rows=2, cols=256, group=128, bits=4,
                  metadata_dtype="BF16", seed=2,
                  shaper=lambda unit, index: unit * 3.0 - 1.5))
    # Eight bits over two groups.
    add(make_case("multigroup_8bit_g64", rows=2, cols=128, group=64, bits=8,
                  metadata_dtype="BF16", seed=3,
                  shaper=lambda unit, index: (unit - 0.25) * 8.0))
    # Eight bits at group 32.
    add(make_case("multigroup_8bit_g32", rows=2, cols=128, group=32, bits=8,
                  metadata_dtype="F16", seed=4,
                  shaper=lambda unit, index: unit - 0.5))
    # Binary32 metadata: the case whose invariant is a bound, not an equality.
    add(make_case("multigroup_4bit_g64_f32_scales", rows=2, cols=128, group=64,
                  bits=4, metadata_dtype="F32", seed=5,
                  shaper=lambda unit, index: (unit - 0.5) * 1.7320508075688772))
    # Groups whose larger-magnitude edge is the minimum, so the encoder's
    # signed rule produces a POSITIVE scale, and groups where it is the
    # maximum, so the scale is negative. Alternating by group index forces both.
    add(make_case("edge_snapped_signs_4bit_g64", rows=4, cols=128, group=64,
                  bits=4, metadata_dtype="BF16", seed=6,
                  shaper=lambda unit, index: (unit * 4.0 - 3.5)
                  if (index // 64) % 2 == 0 else (unit * 4.0 - 0.5)))
    # A group that is entirely zero: the encoder's q0 == 0 branch, where the
    # bias is exactly 0.0 and the scale keeps the 1e-7 floor.
    add(make_case("zero_group_4bit_g64", rows=2, cols=128, group=64, bits=4,
                  metadata_dtype="BF16", seed=7,
                  shaper=lambda unit, index: 0.0 if index < 64 else unit - 0.5))
    # A stacked three-expert tensor, flattened to rows, so the fixture also
    # pins what one expert's rows look like.
    add(make_case("stacked_experts_4bit_g64", rows=6, cols=128, group=64,
                  bits=4, metadata_dtype="BF16", seed=8,
                  shaper=lambda unit, index: (unit - 0.5) * (1 + index // 128)))
    return cases


def reproduce(case):
    decoded = r1.dequantize_rows(
        case["words"], case["scales"], case["biases"], bits=case["bits"],
        group_size=case["group"], rows=case["rows"], columns=case["cols"],
        metadata_dtype="F32",
    )
    return [r1.float_to_f32_bits(value) for value in decoded]


def check_case(name, case, problems):
    if reproduce(case) != case["dequant"]:
        problems.append(f"{name}: R1 does not reproduce the stored dequant")
    if len(case["words"]) != case["rows"] * case["cols"] * case["bits"] // 32:
        problems.append(f"{name}: packed word count does not match the geometry")
    groups = case["rows"] * case["cols"] // case["group"]
    if len(case["scales"]) != groups or len(case["biases"]) != groups:
        problems.append(f"{name}: metadata count does not match the geometry")
    dtype = case.get("metadata_dtype", "F32")
    if dtype in ("BF16", "F16"):
        narrow = r1.float_to_bf16_bits if dtype == "BF16" else r1.float_to_f16_bits
        widen = r1.bf16_to_float if dtype == "BF16" else r1.f16_to_float
        for kind in ("scales", "biases"):
            for stored in case[kind]:
                value = r1.f32_to_float(stored)
                if r1.float_to_f32_bits(widen(narrow(value))) != stored:
                    problems.append(f"{name}: a {kind} value is not exact in {dtype}")
                    break


def build(adopted, conversion_vectors):
    return {
        "schema": SCHEMA,
        "encoding": "every floating-point quantity is the IEEE-754 binary32 bit pattern of its value, as a JSON integer",
        "provenance": {
            "adopted": {
                "origin": "untracked file crates/mlx-safetensors/tests/data/golden_mlx_dequant.json in the shared checkout /Users/mhedhli/Documents/Coding/PulsarMLX",
                "observed_bytes": 20460,
                "observed_mtime": "2026-09-21T18:13:00",
                "sha256": ADOPTED_SOURCE_SHA256,
                "re_derivation": "Phase 0 worker W1 reconstructed all nine cases independently in Python on 2026-09-22 and reported them self-consistent; this generator re-derives them again through the R1 reference on every run",
                "authority": "self-consistency and two independent re-derivations. No committed generator, no recorded MLX version, no schema field in the original. A regression baseline, not an upstream oracle.",
                "gaps_it_does_not_close": [
                    "cols == group in every case, so it pins no multi-group metadata layout",
                    "no group_size 128",
                    "no quantized_matmul or gather_qmm case"
                ]
            },
            "extended": {
                "origin": "generated by scripts/research/generate_golden_affine_dequant_v1.py from the R1 encoder in scripts/research/mlx_affine_reference_v1.py",
                "derived_from": "the written specification of MLX's implemented affine encoder (mlx/ops.cpp:4688-4712 packing, 4764-4778 encoding), as quoted in the F020 Phase 0 inventory W2 section 4",
                "mlx_was_not_run": True,
                "agreement_with_mlx": "not assumed here; observed separately and labelled by scripts/ci/mlx_affine_compat_v1.py"
            }
        },
        "adopted": adopted,
        "extended": extended_cases(),
        "conversion_vectors": conversion_vectors,
    }


def normalise_adopted(raw):
    """Turn the original file's nine cases into the fixture's case shape."""
    adopted = {}
    for name, case in raw.items():
        if name in ("f16", "bf16"):
            continue
        rows = case["rows"] * case.get("experts", 1)
        adopted[name] = {
            "rows": rows,
            "cols": case["cols"],
            "group": case["group"],
            "bits": case["bits"],
            "metadata_dtype": "F32",
            "experts": case.get("experts"),
            "words": case["words"],
            "scales": case["scales"],
            "biases": case["biases"],
            "dequant": case["dequant"],
        }
        if adopted[name]["experts"] is None:
            del adopted[name]["experts"]
    return adopted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--adopted-source", type=Path,
                        help="the original untracked fixture, needed only for a first --write")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("pass exactly one of --write and --check")

    if args.write:
        if args.adopted_source is not None:
            raw = json.loads(args.adopted_source.read_bytes())
            digest = hashlib.sha256(args.adopted_source.read_bytes()).hexdigest()
            if digest != ADOPTED_SOURCE_SHA256:
                print(f"adopted source sha256 {digest} is not the recorded one", file=sys.stderr)
                return 2
            adopted = normalise_adopted(raw)
            vectors = {key: raw[key] for key in ("f16", "bf16") if key in raw}
        else:
            existing = json.loads(FIXTURE.read_bytes())
            adopted = existing["adopted"]
            vectors = existing["conversion_vectors"]
        fixture = build(adopted, vectors)
        problems: list[str] = []
        for block in ("adopted", "extended"):
            for name, case in fixture[block].items():
                check_case(f"{block}/{name}", case, problems)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 2
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(fixture, sort_keys=True, indent=1) + "\n")
        print(f"wrote {FIXTURE} ({FIXTURE.stat().st_size} bytes)")
        return 0

    fixture = json.loads(FIXTURE.read_bytes())
    problems = []
    if fixture.get("schema") != SCHEMA:
        problems.append("schema mismatch")
    for block in ("adopted", "extended"):
        for name, case in fixture[block].items():
            check_case(f"{block}/{name}", case, problems)
    expected = extended_cases()
    if {k: v for k, v in fixture["extended"].items()} != expected:
        problems.append("the extended block is not what this generator produces")
    for key, vector in fixture["conversion_vectors"].items():
        narrow = r1.float_to_bf16_bits if key == "bf16" else r1.float_to_f16_bits
        widen = r1.bf16_to_float if key == "bf16" else r1.f16_to_float
        for stored in vector["vals"]:
            if r1.float_to_f32_bits(widen(narrow(r1.f32_to_float(stored)))) != stored:
                problems.append(f"conversion_vectors/{key}: a value is not exact in {key}")
                break
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    total = len(fixture["adopted"]) + len(fixture["extended"])
    print(json.dumps({"result": "PASS", "cases": total,
                      "adopted": len(fixture["adopted"]),
                      "extended": len(fixture["extended"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

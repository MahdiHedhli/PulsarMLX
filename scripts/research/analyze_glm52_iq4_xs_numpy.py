#!/usr/bin/env python3
"""Generate the bounded IQ4_XS qualification table."""

from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; SOURCE=ROOT/"docs/research/glm52/raw/post-f016-iq4-xs-numpy-qualification-0001.json"; TABLE=ROOT/"docs/research/glm52/tables/post-f016-iq4-xs-numpy-qualification-0001.md"


def render(record):
    scalar=record["benchmark"]["scalar_reference"]["summary"]; vector=record["benchmark"]["numpy_vectorized"]["summary"]
    lines=["# Post-Feature-016 NumPy IQ4_XS qualification","","> Decoder boundary only; complete real matrices cover all four IQ4_XS layers.","",f"- Evidence source: `{record['source_commit']}` (clean: `{str(not record['source_dirty']).lower()}`)",f"- Checkpoint set SHA-256: `{record['checkpoint']['checkpoint_set_sha256']}`","","| Tensor | Expert | Shard | Shape | Scalar first decode (s) | Vector first decode (s) | Exact f32 bits |","| --- | ---: | --- | ---: | ---: | ---: | --- |"]
    for case in record["cases"]:
        rows,cols=case["shape_rows_cols"]; lines.append(f"| `{case['tensor']}` | {case['expert_id']} | `{case['shard']}` | {rows}x{cols} | {case['scalar_decode_seconds']:.6f} | {case['vector_decode_seconds']:.6f} | {str(case['exact_f32_bits']).lower()} |")
    lines.extend(["","## Bounded decode population","","| Mode | Samples | Median (s) | Mean (s) | Stddev (s) |","| --- | ---: | ---: | ---: | ---: |",f"| scalar reference | {scalar['sample_count']} | {scalar['median_seconds']:.6f} | {scalar['mean_seconds']:.6f} | {scalar['standard_deviation_seconds']:.6f} |",f"| NumPy vectorized | {vector['sample_count']} | {vector['median_seconds']:.6f} | {vector['mean_seconds']:.6f} | {vector['standard_deviation_seconds']:.6f} |","",f"Layer-8 expert-216 down median decode-only ratio: **{record['benchmark']['median_decode_speedup']:.2f}x**.","","This is not complete expert, MoE, layer, stack, token, Rust, or Metal evidence.",""])
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args(); rendered=render(json.loads(SOURCE.read_text()))
    if args.check:
        if not TABLE.exists() or TABLE.read_text()!=rendered: raise SystemExit("generated IQ4_XS table is stale")
    else: TABLE.parent.mkdir(parents=True,exist_ok=True); TABLE.write_text(rendered)
    return 0


if __name__=="__main__": raise SystemExit(main())

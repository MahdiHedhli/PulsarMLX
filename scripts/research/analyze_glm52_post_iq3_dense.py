#!/usr/bin/env python3
"""Generate the post-IQ3 multi-layer dense profile table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("docs/research/glm52/raw/post-f018-dense-multilayer-profile-0001.json")
DEFAULT_OUTPUT = Path("docs/research/glm52/tables/post-f018-dense-multilayer-profile-0001.md")


def render(record: dict[str, Any]) -> str:
    if record.get("actual_status") != "passed" or record.get("classification") != "golden_identical":
        raise ValueError("post-IQ3 dense profile is not admitted")
    layer_lines = []
    tensor_rows = []
    for layer in record["layers"]:
        summary = layer["candidate_summaries"]
        layer_lines.append(
            f"| {layer['layer']} | {summary['wall_seconds']['median_seconds']:.6f} | "
            f"{summary['wall_seconds']['standard_deviation_seconds']:.6f} | "
            f"{summary['dense_attributed_seconds']['median_seconds']:.6f} | "
            f"{summary['orchestration_other_seconds']['median_seconds']:.6f} |"
        )
        for tensor in layer["tensor_summaries"]:
            stages = tensor["summaries"]
            tensor_rows.append(
                {
                    "layer": layer["layer"],
                    "tensor": tensor["tensor"],
                    "quantization": tensor["quantization"],
                    "shape": tensor["shape_rows_cols_per_slice"],
                    "slices": tensor["slice_count"],
                    "bytes": tensor["encoded_bytes_per_use"],
                    "storage": stages["storage_read_seconds"]["median_seconds"],
                    "decode": stages["dequant_seconds"]["median_seconds"],
                    "buffer": stages["contiguous_buffer_seconds"]["median_seconds"],
                    "build": stages["mlx_matrix_build_seconds"]["median_seconds"],
                    "matvec": stages["mlx_matvec_seconds"]["median_seconds"],
                    "total": stages["total_seconds"]["median_seconds"],
                }
            )
    tensor_rows.sort(key=lambda row: (-row["total"], row["tensor"]))
    tensor_lines = [
        f"| {rank} | {row['layer']} | `{row['tensor']}` | {row['quantization']} | "
        f"{row['shape'][0]}x{row['shape'][1]} x {row['slices']} | {row['bytes']} | "
        f"{row['storage']:.6f} | {row['decode']:.6f} | {row['buffer']:.6f} | "
        f"{row['build']:.6f} | {row['matvec']:.6f} | {row['total']:.6f} |"
        for rank, row in enumerate(tensor_rows, 1)
    ]
    return "\n".join(
        [
            "# Post-IQ3 dense/MLA multi-layer profile",
            "",
            "> Independent position-0 layer boundaries on one M1 Ultra; not sequential stack or token timing.",
            "",
            f"- Source: `{record['source']['commit']}` (clean)",
            f"- Layers: `{record['protocol']['layers']}`; samples/layer: `{record['protocol']['measured_samples_per_layer']}`",
            f"- Candidate mode: `{record['protocol']['candidate_mode']}`",
            "- Exact scalar-oracle output hashes: `true` for every layer",
            "",
            "| Layer | Wall median (s) | Wall stddev (s) | Dense attributed median (s) | Orchestration/other median (s) |",
            "| ---: | ---: | ---: | ---: | ---: |",
            *layer_lines,
            "",
            "## Per-tensor ranking",
            "",
            "| Rank | Layer | Tensor | Quant | Shape/slices | Encoded bytes | Storage (s) | Decode (s) | Buffer (s) | Build (s) | Matvec (s) | Total (s) |",
            "| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            *tensor_lines,
            "",
            "Q8_0 3D rows are grouped across all 64 head slices while retaining the slice count. Times are measured boundaries, not predicted speedups.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = render(json.loads(args.input.read_text()))
    if args.check:
        if args.output.read_text() != rendered:
            raise SystemExit(f"generated table differs: {args.output}")
        print(f"post-IQ3 dense table matches: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

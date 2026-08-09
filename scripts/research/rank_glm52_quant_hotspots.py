#!/usr/bin/env python3
"""Derive the Feature 016 mixed-quant hotspot ranking from committed P1 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path("docs/research/glm52/raw/f016-inference-p1-vectorized-0001.json")
DEFAULT_JSON = Path("docs/research/glm52/raw/f016-p1-quant-hotspot-ranking-0001.json")
DEFAULT_TABLE = Path("docs/research/glm52/tables/f016-p1-quant-hotspots.md")
EXPECTED_SCHEMA = "pulsarmlx.research.glm52-inference"
COMPONENTS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
)


def _repo_path(value: Path) -> Path:
    return value if value.is_absolute() else REPOSITORY_ROOT / value


def _relative(path: Path) -> str:
    return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()


def _load_source(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("P1 source must be a JSON object")
    if value.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("unexpected P1 evidence schema")
    if value.get("actual_status") != "passed" or value.get("source_dirty") is not False:
        raise ValueError("P1 source must be passed and clean")
    if value.get("matches_golden_prefix") is not True:
        raise ValueError("P1 source did not pass the frozen golden-prefix gate")
    return raw, value


def build_record(source_path: Path) -> dict[str, Any]:
    raw, source = _load_source(source_path)
    metrics = source.get("expert_cache", {}).get("quantization_metrics")
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("P1 source has no quantization metrics")

    rows: list[dict[str, Any]] = []
    for quantization, observed in metrics.items():
        if not isinstance(quantization, str) or not isinstance(observed, dict):
            raise ValueError("invalid quantization metric entry")
        row: dict[str, Any] = {"quantization": quantization}
        for field in COMPONENTS:
            value = observed.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{quantization}.{field} is not numeric")
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{quantization}.{field} is invalid")
            row[field] = value
        for field in ("matrix_load_count", "storage_read_count", "mlx_matvec_count", "storage_bytes_read"):
            value = observed.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{quantization}.{field} is invalid")
            row[field] = value
        row["measured_component_seconds"] = sum(row[field] for field in COMPONENTS)
        rows.append(row)

    rows.sort(key=lambda item: (-item["measured_component_seconds"], item["quantization"]))
    total = sum(row["measured_component_seconds"] for row in rows)
    if total <= 0:
        raise ValueError("P1 quantified component total is not positive")
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["fraction_of_quantified_component_time"] = row["measured_component_seconds"] / total

    return {
        "schema": "pulsarmlx.research.glm52-quant-hotspot-ranking",
        "schema_version": "1.0.0",
        "feature_id": "016-glm52-full-execution",
        "actual_status": "passed",
        "source": {
            "record": _relative(source_path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "source_commit": source["source_commit"],
            "source_dirty": source["source_dirty"],
            "decoder_mode": source["decoder_mode"],
            "requested_new_tokens": source["requested_new_tokens"],
            "matches_golden_prefix": source["matches_golden_prefix"],
            "p1_wall_seconds": source["seconds"],
        },
        "scope": {
            "operation": "P1 prompt stack plus one generated-token stack",
            "population": "expert-cache matrix operations actually exercised by the frozen P1 trace",
            "ranking_metric": "sum of recorded storage-read, dequant, contiguous-buffer, MLX-matrix-build, and MLX-matvec seconds",
            "global_tensor_count_used_for_ranking": False,
        },
        "quantified_component_seconds": total,
        "formats_exercised": [row["quantization"] for row in rows],
        "ranking": rows,
        "next_decoder_candidate": rows[0]["quantization"],
        "limitations": [
            "One clean-process P1 trace on one M1 Ultra; no benchmark population is inferred.",
            "Instrumented component sums are a hotspot attribution, not an independently timed wall-clock total.",
            "Shared-cache hits change load counts between the cold prompt and warm generated-token stacks.",
            "This ranking does not establish a speedup for any decoder that has not passed exact-bit qualification.",
        ],
    }


def render_json(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def render_table(record: dict[str, Any]) -> bytes:
    source = record["source"]
    lines = [
        "# Feature 016 P1 mixed-quant hotspot ranking",
        "",
        f"Derived from [`{Path(source['record']).name}`](../raw/{Path(source['record']).name}) at source commit `{source['source_commit']}`.",
        "The rank uses measured time in the exercised P1 trace, not global tensor count.",
        "",
        "| Rank | Format | Measured components (s) | Share | Loads | Reads | Matvecs | Bytes read |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in record["ranking"]:
        lines.append(
            "| {rank} | {quantization} | {measured_component_seconds:.6f} | {share:.2%} | "
            "{matrix_load_count} | {storage_read_count} | {mlx_matvec_count} | {storage_bytes_read} |".format(
                share=row["fraction_of_quantified_component_time"], **row
            )
        )
    lines.extend(
        [
            "",
            "Measured components are storage read, dequantization, contiguous-buffer construction, MLX matrix build, and MLX matvec. Their sum is an instrumented attribution and must not be substituted for independently timed P1 wall time.",
            "",
            f"**Next exact-bit decoder candidate:** `{record['next_decoder_candidate']}`.",
        ]
    )
    return ("\n".join(lines) + "\n").encode()


def _install_or_check(path: Path, content: bytes, check: bool) -> None:
    if check:
        if not path.exists() or path.read_bytes() != content:
            raise ValueError(f"generated artifact is stale: {_relative(path)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--table-out", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        source = _repo_path(args.source)
        json_out = _repo_path(args.json_out)
        table_out = _repo_path(args.table_out)
        record = build_record(source)
        _install_or_check(json_out, render_json(record), args.check)
        _install_or_check(table_out, render_table(record), args.check)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"quant hotspot ranking failed: {error}")
        return 1
    print("quant hotspot ranking: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

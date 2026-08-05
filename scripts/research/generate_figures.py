#!/usr/bin/env python3
"""Generate deterministic bounded static SVGs from Feature 002 evidence."""

from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sys
from typing import Any


SCHEMA_ID = "pulsarmlx.research.generated-sources"
SCHEMA_VERSION = "1.0.0"
GENERATOR_ID = "scripts/research/generate_figures.py"
OUTPUT_NAME = "002-router-parity-median.svg"
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 1_024
MAX_PLOTTED_ROWS = 256
MAX_SVG_BYTES = 128 * 1024


class GenerationError(ValueError):
    """A bounded deterministic-generation failure."""


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_constant(value: str) -> None:
    raise GenerationError(f"non-finite JSON number is forbidden: {value}")


def _load_records(raw_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise GenerationError("raw input must be a real directory")
    paths = sorted(raw_dir.glob("*.json"), key=lambda path: path.name)
    if not paths:
        raise GenerationError("raw input contains no JSON records")
    if len(paths) > MAX_RECORDS:
        raise GenerationError("raw input contains too many records")

    records: list[tuple[str, dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise GenerationError("raw input contains an unsafe entry")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise GenerationError("raw input record exceeds the size limit")
        try:
            record = json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=_reject_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GenerationError("raw input contains invalid JSON") from error
        if not isinstance(record, dict):
            raise GenerationError("raw evidence root must be an object")
        experiment_id = record.get("experiment_id")
        if not isinstance(experiment_id, str) or not experiment_id:
            raise GenerationError("raw evidence has no experiment identity")
        if experiment_id in seen_ids:
            raise GenerationError("raw evidence repeats an experiment identity")
        seen_ids.add(experiment_id)
        records.append((path.name, record))
    return sorted(records, key=lambda item: (item[1]["experiment_id"], item[0]))


def _finite_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationError(f"{field} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise GenerationError(f"{field} must be finite")
    return value


def _plot_rows(records: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, record in records:
        summaries = record.get("summaries")
        if not isinstance(summaries, list) or not summaries:
            raise GenerationError("statistical summaries must be a nonempty list")
        for summary in summaries:
            if not isinstance(summary, dict):
                raise GenerationError("statistical summary must be an object")
            group = summary.get("group", summary)
            statistics = summary.get("unfiltered_summary", summary)
            if not isinstance(group, dict) or not isinstance(statistics, dict):
                raise GenerationError("statistical summary shape is invalid")
            case_id = group.get("case_id", record.get("case_id"))
            phase = group.get("stage", summary.get("phase"))
            condition = group.get("condition")
            instrumentation = group.get("instrumentation_mode")
            if any(
                not isinstance(value, str)
                for value in (case_id, phase, condition, instrumentation)
            ):
                raise GenerationError("summary identity is invalid")
            median = _finite_number(statistics.get("median_ns"), "median_ns")
            if median < 0:
                raise GenerationError("median_ns must be nonnegative")
            rows.append(
                {
                    "experiment_id": record["experiment_id"],
                    "case_id": case_id,
                    "phase": phase,
                    "condition": condition,
                    "instrumentation_mode": instrumentation,
                    "median_ns": median,
                }
            )

    rows.sort(
        key=lambda row: (
            str(row["experiment_id"]),
            str(row["case_id"]),
            str(row["phase"]),
            str(row["condition"]),
            str(row["instrumentation_mode"]),
        )
    )
    if len(rows) > MAX_PLOTTED_ROWS:
        raise GenerationError("too many summaries for the bounded SVG")
    return rows


def _label(row: dict[str, Any]) -> str:
    value = (
        f"{row['experiment_id']} / {row['case_id']} / {row['phase']} / "
        f"{row['condition']} / {row['instrumentation_mode']}"
    )
    return value if len(value) <= 100 else value[:97] + "..."


def _svg_bytes(rows: list[dict[str, Any]]) -> bytes:
    width = 1_000
    left = 350
    right = 90
    top = 72
    row_height = 34
    bottom = 54
    height = top + max(1, len(rows)) * row_height + bottom
    chart_width = width - left - right
    maximum = max(float(row["median_ns"]) for row in rows)
    scale = maximum if maximum > 0 else 1.0

    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
            'aria-labelledby="title description">'
        ),
        '<title id="title">Feature 002 router median durations</title>',
        (
            '<desc id="description">Deterministically generated horizontal bars; '
            'durations are nanoseconds.</desc>'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,monospace;fill:#17202a}'
        '.label{font-size:11px}.value{font-size:11px;font-weight:600}'
        '.bar{fill:#4c78a8}.axis{stroke:#566573;stroke-width:1}</style>',
        '<text x="24" y="34" font-size="18" font-weight="700">Router median duration (ns)</text>',
        f'<line class="axis" x1="{left}" y1="{top - 12}" x2="{left}" y2="{height - bottom + 6}"/>',
    ]
    for index, row in enumerate(rows):
        y = top + index * row_height
        median = float(row["median_ns"])
        bar_width = (median / scale) * chart_width
        value_text = str(row["median_ns"])
        lines.extend(
            (
                f'<text class="label" x="12" y="{y + 16}">{escape(_label(row))}</text>',
                (
                    f'<rect class="bar" x="{left}" y="{y}" width="{bar_width:.3f}" '
                    'height="20" rx="2"/>'
                ),
                (
                    f'<text class="value" x="{left + bar_width + 6:.3f}" '
                    f'y="{y + 15}">{escape(value_text)}</text>'
                ),
            )
        )
    lines.append("</svg>")
    content = ("\n".join(lines) + "\n").encode("utf-8")
    if len(content) >= MAX_SVG_BYTES:
        raise GenerationError("generated SVG exceeds the size limit")
    return content


def _sidecar_bytes(
    *,
    output_content: bytes,
    sources: dict[str, str],
    source_commits: list[str],
) -> bytes:
    sidecar = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR_ID,
        "generator_sha256": _sha256_file(Path(__file__)),
        "generation_command": (
            "python3 scripts/research/generate_figures.py "
            "--raw-dir <raw-dir> --output-dir <output-dir>"
        ),
        "output": OUTPUT_NAME,
        "output_sha256": _sha256_bytes(output_content),
        "source_commits": source_commits,
        "sources": sources,
    }
    return (json.dumps(sidecar, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as error:
        raise GenerationError("generated output already exists") from error


def generate_figures(raw_dir: Path, output_dir: Path) -> list[Path]:
    """Generate a bounded deterministic SVG and its provenance sidecar."""

    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    records = _load_records(raw_dir)
    rows = _plot_rows(records)
    svg = _svg_bytes(rows)
    sources = {
        name: _sha256_file(raw_dir / name)
        for name, _ in sorted(records, key=lambda item: item[0])
    }
    source_commits = sorted(
        {
            str(record["source_commit"])
            for _, record in records
            if isinstance(record.get("source_commit"), str)
        }
    )
    contents = {
        OUTPUT_NAME: svg,
        f"{OUTPUT_NAME}.sources.json": _sidecar_bytes(
            output_content=svg,
            sources=sources,
            source_commits=source_commits,
        ),
    }

    if output_dir.is_symlink():
        raise GenerationError("output directory cannot be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [output_dir / name for name in sorted(contents)]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise GenerationError("generated output already exists")
    for path in paths:
        _write_exclusive(path, contents[path.name])
    return paths


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        paths = generate_figures(args.raw_dir, args.output_dir)
    except (GenerationError, OSError) as error:
        print(f"figure generation failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"output_count": len(paths), "status": "passed"},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

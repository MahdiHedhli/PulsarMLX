#!/usr/bin/env python3
"""Generate deterministic bounded static SVGs from Feature 002 evidence."""

from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any

from validate_evidence import EvidenceValidationError, validate_record


SCHEMA_ID = "pulsarmlx.research.generated-sources"
SCHEMA_VERSION = "1.0.0"
GENERATOR_ID = "scripts/research/generate_figures.py"
GENERATION_COMMAND = (
    "python3 scripts/research/generate_figures.py "
    "--raw-dir <raw-dir> --output-dir <output-dir>"
)
OUTPUT_NAME = "002-router-parity-median.svg"
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 1_024
MAX_PLOTTED_ROWS = 1_024
MAX_SVG_BYTES = 128 * 1024
MAX_SIDECAR_BYTES = 4 * 1024 * 1024


class GenerationError(ValueError):
    """A bounded deterministic-generation failure."""


def _reject_symlink_components(path: Path) -> None:
    current = path.absolute()
    while True:
        is_macos_root_alias = (
            current.parent == Path("/") and current.name in {"var", "tmp", "etc"}
        )
        if current.is_symlink() and not is_macos_root_alias:
            raise GenerationError("generation path contains a symbolic link")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_label(path: Path) -> str:
    """Return a stable public path for repository inputs and a safe temp fallback."""

    try:
        return path.resolve(strict=True).relative_to(
            Path.cwd().resolve(strict=True)
        ).as_posix()
    except (OSError, RuntimeError, ValueError):
        return path.name


def _reject_constant(value: str) -> None:
    raise GenerationError(f"non-finite JSON number is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GenerationError("raw input contains a duplicate JSON field")
        result[key] = value
    return result


def _read_record(path: Path) -> tuple[dict[str, Any], str, int]:
    _reject_symlink_components(path)
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise GenerationError("raw input contains an unsafe entry")
        if before.st_size <= 0 or before.st_size > MAX_INPUT_BYTES:
            raise GenerationError("raw input record exceeds the size limit")

        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, 64 * 1024):
            size += len(chunk)
            if size > MAX_INPUT_BYTES:
                raise GenerationError("raw input record exceeds the size limit")
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(raw) != before.st_size:
            raise GenerationError("raw input changed while it was read")
        record = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except GenerationError:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise GenerationError("raw input contains invalid JSON") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if not isinstance(record, dict):
        raise GenerationError("raw evidence root must be an object")
    if "evidence_schema" in record:
        try:
            validate_record(record)
        except EvidenceValidationError as error:
            raise GenerationError(
                f"raw evidence semantic validation failed: {error.code}"
            ) from error
    return record, _sha256_bytes(raw), len(raw)


def _load_records(raw_dir: Path) -> list[tuple[str, dict[str, Any], str, int]]:
    _reject_symlink_components(raw_dir)
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise GenerationError("raw input must be a real directory")
    paths = sorted(raw_dir.glob("*.json"), key=lambda path: path.name)
    if not paths:
        raise GenerationError("raw input contains no JSON records")
    if len(paths) > MAX_RECORDS:
        raise GenerationError("raw input contains too many records")

    records: list[tuple[str, dict[str, Any], str, int]] = []
    seen_ids: set[str] = set()
    total_input_bytes = 0
    for path in paths:
        record, digest, input_bytes = _read_record(path)
        total_input_bytes += input_bytes
        if total_input_bytes > MAX_TOTAL_INPUT_BYTES:
            raise GenerationError("raw input exceeds the aggregate size limit")
        experiment_id = record.get("experiment_id")
        if not isinstance(experiment_id, str) or not experiment_id:
            raise GenerationError("raw evidence has no experiment identity")
        if path.stem != experiment_id:
            raise GenerationError("raw filename and experiment identity differ")
        if experiment_id in seen_ids:
            raise GenerationError("raw evidence repeats an experiment identity")
        seen_ids.add(experiment_id)
        records.append((path.name, record, digest, input_bytes))
    return sorted(records, key=lambda item: (item[1]["experiment_id"], item[0]))


def _finite_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GenerationError(f"{field} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise GenerationError(f"{field} must be finite")
    return value


def _raw_observation_processes(record: dict[str, Any]) -> dict[str, str]:
    observations = record.get("raw_observations")
    if observations is None:
        return {}
    if not isinstance(observations, list):
        raise GenerationError("raw observations must be a list")
    processes: dict[str, str] = {}
    for observation in observations:
        if not isinstance(observation, dict):
            raise GenerationError("raw observation must be an object")
        observation_id = observation.get("observation_id")
        process_id = observation.get("process_replication_id")
        if not isinstance(observation_id, str) or not isinstance(process_id, str):
            raise GenerationError("raw observation process identity is invalid")
        if observation_id in processes:
            raise GenerationError("raw observation identity is duplicated")
        processes[observation_id] = process_id
    return processes


def _summary_process_replication_id(
    summary: dict[str, Any],
    observation_processes: dict[str, str],
) -> str | None:
    included_ids = summary.get("included_observation_ids")
    if included_ids is None:
        return None
    if (
        not isinstance(included_ids, list)
        or not included_ids
        or any(not isinstance(observation_id, str) for observation_id in included_ids)
    ):
        raise GenerationError("summary observation identities are invalid")
    try:
        processes = {
            observation_processes[observation_id]
            for observation_id in included_ids
        }
    except KeyError as error:
        raise GenerationError("summary references an unknown raw observation") from error
    if len(processes) != 1:
        raise GenerationError("summary pools multiple process replications")
    return next(iter(processes))


def _plot_rows(
    records: list[tuple[str, dict[str, Any], str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, record, _, _ in records:
        correctness = record.get("correctness")
        if not isinstance(correctness, dict) or type(correctness.get("passed")) is not bool:
            raise GenerationError("correctness status is invalid")
        status = record.get("actual_status", record.get("status"))
        scope = record.get("scope")
        if scope is None and isinstance(record.get("claim_boundary"), dict):
            scope = record["claim_boundary"].get("operation")
        if not isinstance(status, str) or not isinstance(scope, str):
            raise GenerationError("experiment status or scope is invalid")
        summaries = record.get("summaries")
        observation_processes = _raw_observation_processes(record)
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
                    "status": status,
                    "scope": scope,
                    "correctness_passed": correctness["passed"],
                    "case_id": case_id,
                    "process_replication_id": _summary_process_replication_id(
                        summary,
                        observation_processes,
                    ),
                    "phase": phase,
                    "condition": condition,
                    "instrumentation_mode": instrumentation,
                    "median_ns": median,
                }
            )

    rows.sort(
        key=lambda row: (
            str(row["experiment_id"]),
            str(row["status"]),
            str(row["scope"]),
            str(row["case_id"]),
            str(row["process_replication_id"]),
            str(row["phase"]),
            str(row["condition"]),
            str(row["instrumentation_mode"]),
        )
    )
    if len(rows) > MAX_PLOTTED_ROWS:
        raise GenerationError("too many summaries for the bounded SVG")
    return rows


def _label(row: dict[str, Any]) -> str:
    process = row["process_replication_id"] or "unavailable"
    value = (
        f"status={row['status']} / correctness={str(row['correctness_passed']).lower()} / "
        f"process={process} / scope={row['scope']} / {row['experiment_id']} / "
        f"{row['case_id']} / {row['phase']} / "
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
            'durations are nanoseconds and every label includes status, correctness, and scope.</desc>'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,monospace;fill:#17202a}'
        '.label{font-size:11px}.value{font-size:11px;font-weight:600}'
        '.bar-pass{fill:#4c78a8}.bar-nonpass{fill:#c44e52}'
        '.axis{stroke:#566573;stroke-width:1}</style>',
        '<text x="24" y="34" font-size="18" font-weight="700">Router median duration (ns)</text>',
        f'<line class="axis" x1="{left}" y1="{top - 12}" x2="{left}" y2="{height - bottom + 6}"/>',
    ]
    for index, row in enumerate(rows):
        y = top + index * row_height
        median = float(row["median_ns"])
        bar_width = (median / scale) * chart_width
        value_text = str(row["median_ns"])
        bar_class = (
            "bar-pass"
            if row["status"] == "passed" and row["correctness_passed"] is True
            else "bar-nonpass"
        )
        lines.extend(
            (
                f'<text class="label" x="12" y="{y + 16}">{escape(_label(row))}</text>',
                (
                    f'<rect class="{bar_class}" x="{left}" y="{y}" width="{bar_width:.3f}" '
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
        "generation_command": GENERATION_COMMAND,
        "output": OUTPUT_NAME,
        "output_sha256": _sha256_bytes(output_content),
        "source_commits": source_commits,
        "sources": sources,
    }
    content = (json.dumps(sidecar, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(content) > MAX_SIDECAR_BYTES:
        raise GenerationError("generated source sidecar exceeds the size limit")
    return content


def _write_exclusive(path: Path, content: bytes) -> None:
    created = False
    try:
        handle = path.open("xb")
        created = True
        with handle:
            if handle.write(content) != len(content):
                raise OSError("generated output write was incomplete")
    except FileExistsError as error:
        raise GenerationError("generated output already exists") from error
    except OSError as error:
        if created:
            try:
                path.unlink()
            except OSError:
                pass
        raise GenerationError("generated output could not be written") from error


def _write_all_exclusive(paths: list[Path], contents: dict[str, bytes]) -> None:
    created: list[Path] = []
    try:
        for path in paths:
            _write_exclusive(path, contents[path.name])
            created.append(path)
    except GenerationError:
        cleanup_failed = False
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            raise GenerationError("generated output cleanup failed") from None
        raise


def generate_figures(raw_dir: Path, output_dir: Path) -> list[Path]:
    """Generate a bounded deterministic SVG and its provenance sidecar."""

    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    records = _load_records(raw_dir)
    rows = _plot_rows(records)
    svg = _svg_bytes(rows)
    sources = {
        _source_label(raw_dir / name): digest
        for name, _, digest, _ in sorted(records, key=lambda item: item[0])
    }
    source_commits = sorted(
        {
            str(record["source_commit"])
            for _, record, _, _ in records
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

    _reject_symlink_components(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(output_dir)
    paths = [output_dir / name for name in sorted(contents)]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise GenerationError("generated output already exists")
    _write_all_exclusive(paths, contents)
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

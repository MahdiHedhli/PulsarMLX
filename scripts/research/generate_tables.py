#!/usr/bin/env python3
"""Generate deterministic Feature 002 Markdown and CSV research tables."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable


SCHEMA_ID = "pulsarmlx.research.generated-sources"
SCHEMA_VERSION = "1.0.0"
GENERATOR_ID = "scripts/research/generate_tables.py"
OUTPUT_BASENAME = "002-router-parity-summary"
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 1_024
MAX_SUMMARIES_PER_RECORD = 128

TABLE_FIELDS = (
    "experiment_id",
    "status",
    "scope",
    "case_id",
    "phase",
    "condition",
    "instrumentation_mode",
    "sample_count",
    "median_ns",
    "mean_ns",
    "minimum_ns",
    "maximum_ns",
    "correctness_passed",
    "compared_count",
    "mismatch_count",
    "maximum_absolute_error",
    "unsupported_interpretations",
)


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


def _plain_integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise GenerationError(f"{field} must be a plain integer")
    return value


def _mismatch_count(correctness: dict[str, Any]) -> int:
    if "mismatch_count" in correctness:
        return _plain_integer(correctness["mismatch_count"], "mismatch_count")
    fields = (
        "id_mismatch_count",
        "order_mismatch_count",
        "numeric_mismatch_count",
        "non_finite_count",
    )
    return sum(
        _plain_integer(correctness.get(field, 0), field)
        for field in fields
    )


def _unsupported_interpretations(record: dict[str, Any]) -> list[str]:
    values = record.get("unsupported_interpretations")
    if values is None and isinstance(record.get("claim_boundary"), dict):
        values = record["claim_boundary"].get("unsupported_interpretations")
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise GenerationError("unsupported interpretations must be a string list")
    return sorted(values)


def _table_rows(records: Iterable[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, record in records:
        correctness = record.get("correctness")
        summaries = record.get("summaries")
        if not isinstance(correctness, dict):
            raise GenerationError("correctness summary must be an object")
        if not isinstance(summaries, list) or not summaries:
            raise GenerationError("statistical summaries must be a nonempty list")
        if len(summaries) > MAX_SUMMARIES_PER_RECORD:
            raise GenerationError("raw evidence contains too many summaries")

        unsupported = _unsupported_interpretations(record)
        for summary in summaries:
            if not isinstance(summary, dict):
                raise GenerationError("statistical summary must be an object")
            group = summary.get("group", summary)
            statistics = summary.get("unfiltered_summary", summary)
            if not isinstance(group, dict) or not isinstance(statistics, dict):
                raise GenerationError("statistical summary shape is invalid")

            case_id = group.get("case_id", record.get("case_id"))
            phase = group.get("stage", summary.get("phase"))
            if not isinstance(case_id, str) or not isinstance(phase, str):
                raise GenerationError("summary case or phase identity is invalid")
            condition = group.get("condition")
            instrumentation = group.get("instrumentation_mode")
            if not isinstance(condition, str) or not isinstance(instrumentation, str):
                raise GenerationError("summary compatibility fields are invalid")

            status = record.get("actual_status", record.get("status"))
            if not isinstance(status, str):
                raise GenerationError("experiment status is invalid")
            scope = record.get("scope")
            if scope is None and isinstance(record.get("claim_boundary"), dict):
                scope = record["claim_boundary"].get("operation")
            if not isinstance(scope, str):
                raise GenerationError("experiment scope is invalid")

            correctness_passed = correctness.get("passed")
            if type(correctness_passed) is not bool:
                raise GenerationError("correctness pass state is invalid")

            row = {
                "experiment_id": record["experiment_id"],
                "status": status,
                "scope": scope,
                "case_id": case_id,
                "phase": phase,
                "condition": condition,
                "instrumentation_mode": instrumentation,
                "sample_count": _plain_integer(
                    statistics.get("sample_count"), "sample_count"
                ),
                "median_ns": _finite_number(statistics.get("median_ns"), "median_ns"),
                "mean_ns": _finite_number(statistics.get("mean_ns"), "mean_ns"),
                "minimum_ns": _plain_integer(
                    statistics.get("minimum_ns"), "minimum_ns"
                ),
                "maximum_ns": _plain_integer(
                    statistics.get("maximum_ns"), "maximum_ns"
                ),
                "correctness_passed": correctness_passed,
                "compared_count": _plain_integer(
                    correctness.get("compared_count"), "compared_count"
                ),
                "mismatch_count": _mismatch_count(correctness),
                "maximum_absolute_error": _finite_number(
                    correctness.get("maximum_absolute_error"),
                    "maximum_absolute_error",
                ),
                "unsupported_interpretations": unsupported,
            }
            rows.append(row)

    return sorted(
        rows,
        key=lambda row: (
            str(row["experiment_id"]),
            str(row["case_id"]),
            str(row["phase"]),
            str(row["condition"]),
            str(row["instrumentation_mode"]),
        ),
    )


def _display(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GenerationError("table value must be finite")
        return format(Decimal(str(value)), "f")
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value)


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TABLE_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _display(row[field]) for field in TABLE_FIELDS})
    return output.getvalue().encode("utf-8")


def _markdown_cell(value: Any) -> str:
    return _display(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _markdown_bytes(rows: list[dict[str, Any]]) -> bytes:
    lines = [
        "# Feature 002 Router-Parity Summary",
        "",
        "Generated deterministically from validated raw evidence. Times are nanoseconds.",
        "",
        "| " + " | ".join(TABLE_FIELDS) + " |",
        "| " + " | ".join("---" for _ in TABLE_FIELDS) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_markdown_cell(row[field]) for field in TABLE_FIELDS) + " |"
        for row in rows
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _sidecar_bytes(
    *,
    output_name: str,
    output_content: bytes,
    sources: dict[str, str],
    source_commits: list[str],
) -> bytes:
    generator_path = Path(__file__)
    sidecar = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "generator": GENERATOR_ID,
        "generator_sha256": _sha256_file(generator_path),
        "generation_command": (
            "python3 scripts/research/generate_tables.py "
            "--raw-dir <raw-dir> --output-dir <output-dir>"
        ),
        "output": output_name,
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


def generate_tables(raw_dir: Path, output_dir: Path) -> list[Path]:
    """Generate deterministic CSV/Markdown tables and provenance sidecars."""

    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    records = _load_records(raw_dir)
    rows = _table_rows(records)
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

    csv_name = f"{OUTPUT_BASENAME}.csv"
    markdown_name = f"{OUTPUT_BASENAME}.md"
    contents = {
        csv_name: _csv_bytes(rows),
        markdown_name: _markdown_bytes(rows),
    }
    for name, content in tuple(contents.items()):
        contents[f"{name}.sources.json"] = _sidecar_bytes(
            output_name=name,
            output_content=content,
            sources=sources,
            source_commits=source_commits,
        )

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
        paths = generate_tables(args.raw_dir, args.output_dir)
    except (GenerationError, OSError) as error:
        print(f"table generation failed: {error}", file=sys.stderr)
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

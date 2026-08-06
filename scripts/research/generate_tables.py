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
import os
from pathlib import Path
import stat
import sys
from typing import Any, Iterable

from validate_evidence import EvidenceValidationError, validate_record


SCHEMA_ID = "pulsarmlx.research.generated-sources"
SCHEMA_VERSION = "1.0.0"
GENERATOR_ID = "scripts/research/generate_tables.py"
GENERATION_COMMAND = (
    "python3 scripts/research/generate_tables.py "
    "--raw-dir <raw-dir> --output-dir <output-dir>"
)
OUTPUT_BASENAME = "002-router-parity-summary"
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 64 * 1024 * 1024
MAX_RECORDS = 1_024
MAX_SUMMARIES_PER_RECORD = 512
MAX_TABLE_ROWS = MAX_RECORDS * MAX_SUMMARIES_PER_RECORD
MAX_TABLE_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_SIDECAR_BYTES = 4 * 1024 * 1024

TABLE_FIELDS = (
    "experiment_id",
    "record_kind",
    "status",
    "scope",
    "case_id",
    "batch_id",
    "process_replication_id",
    "observation_kind",
    "phase",
    "condition",
    "instrumentation_mode",
    "statistics_algorithm",
    "sample_count",
    "mean_ns",
    "sample_standard_deviation_ns",
    "sample_standard_deviation_reason",
    "minimum_ns",
    "p5_ns",
    "p25_ns",
    "median_ns",
    "p75_ns",
    "p95_ns",
    "maximum_ns",
    "coefficient_of_variation",
    "coefficient_of_variation_reason",
    "correctness_passed",
    "compared_count",
    "mismatch_count",
    "id_mismatch_count",
    "order_mismatch_count",
    "numeric_mismatch_count",
    "non_finite_count",
    "deterministic_repeat_count",
    "mean_absolute_error",
    "rmse",
    "maximum_absolute_error",
    "maximum_relative_error",
    "unsupported_interpretations",
)


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


def _optional_finite_number(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    return _finite_number(value, field)


def _optional_plain_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _plain_integer(value, field)


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GenerationError(f"{field} must be a string or null")
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


def _table_rows(
    records: Iterable[tuple[str, dict[str, Any], str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, record, _, _ in records:
        correctness = record.get("correctness")
        summaries = record.get("summaries")
        observation_processes = _raw_observation_processes(record)
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
                "record_kind": _optional_string(
                    record.get("record_kind"), "record_kind"
                ),
                "status": status,
                "scope": scope,
                "case_id": case_id,
                "batch_id": _optional_string(
                    group.get("batch_id", record.get("batch_id")), "batch_id"
                ),
                "process_replication_id": _summary_process_replication_id(
                    summary,
                    observation_processes,
                ),
                "observation_kind": _optional_string(
                    group.get("observation_kind"), "observation_kind"
                ),
                "phase": phase,
                "condition": condition,
                "instrumentation_mode": instrumentation,
                "statistics_algorithm": _optional_string(
                    summary.get("statistics_algorithm"), "statistics_algorithm"
                ),
                "sample_count": _plain_integer(
                    statistics.get("sample_count"), "sample_count"
                ),
                "mean_ns": _finite_number(statistics.get("mean_ns"), "mean_ns"),
                "sample_standard_deviation_ns": _optional_finite_number(
                    statistics.get("sample_standard_deviation_ns"),
                    "sample_standard_deviation_ns",
                ),
                "sample_standard_deviation_reason": _optional_string(
                    statistics.get("sample_standard_deviation_reason"),
                    "sample_standard_deviation_reason",
                ),
                "minimum_ns": _plain_integer(
                    statistics.get("minimum_ns"), "minimum_ns"
                ),
                "p5_ns": _optional_finite_number(
                    statistics.get("p5_ns"), "p5_ns"
                ),
                "p25_ns": _optional_finite_number(
                    statistics.get("p25_ns"), "p25_ns"
                ),
                "median_ns": _finite_number(
                    statistics.get("median_ns"), "median_ns"
                ),
                "p75_ns": _optional_finite_number(
                    statistics.get("p75_ns"), "p75_ns"
                ),
                "p95_ns": _optional_finite_number(
                    statistics.get("p95_ns"), "p95_ns"
                ),
                "maximum_ns": _plain_integer(
                    statistics.get("maximum_ns"), "maximum_ns"
                ),
                "coefficient_of_variation": _optional_finite_number(
                    statistics.get("coefficient_of_variation"),
                    "coefficient_of_variation",
                ),
                "coefficient_of_variation_reason": _optional_string(
                    statistics.get("coefficient_of_variation_reason"),
                    "coefficient_of_variation_reason",
                ),
                "correctness_passed": correctness_passed,
                "compared_count": _plain_integer(
                    correctness.get("compared_count"), "compared_count"
                ),
                "mismatch_count": _mismatch_count(correctness),
                "id_mismatch_count": _optional_plain_integer(
                    correctness.get("id_mismatch_count"), "id_mismatch_count"
                ),
                "order_mismatch_count": _optional_plain_integer(
                    correctness.get("order_mismatch_count"),
                    "order_mismatch_count",
                ),
                "numeric_mismatch_count": _optional_plain_integer(
                    correctness.get("numeric_mismatch_count"),
                    "numeric_mismatch_count",
                ),
                "non_finite_count": _optional_plain_integer(
                    correctness.get("non_finite_count"), "non_finite_count"
                ),
                "deterministic_repeat_count": _optional_plain_integer(
                    correctness.get("deterministic_repeat_count"),
                    "deterministic_repeat_count",
                ),
                "mean_absolute_error": _optional_finite_number(
                    correctness.get("mean_absolute_error"),
                    "mean_absolute_error",
                ),
                "rmse": _optional_finite_number(correctness.get("rmse"), "rmse"),
                "maximum_absolute_error": _finite_number(
                    correctness.get("maximum_absolute_error"),
                    "maximum_absolute_error",
                ),
                "maximum_relative_error": _optional_finite_number(
                    correctness.get("maximum_relative_error"),
                    "maximum_relative_error",
                ),
                "unsupported_interpretations": unsupported,
            }
            rows.append(row)
            if len(rows) > MAX_TABLE_ROWS:
                raise GenerationError("raw evidence contains too many table rows")

    return sorted(
        rows,
        key=lambda row: (
            str(row["experiment_id"]),
            str(row["case_id"]),
            str(row["batch_id"]),
            str(row["process_replication_id"]),
            str(row["observation_kind"]),
            str(row["phase"]),
            str(row["condition"]),
            str(row["instrumentation_mode"]),
        ),
    )


def _display(value: Any) -> str:
    if value is None:
        return ""
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
    content = output.getvalue().encode("utf-8")
    if len(content) > MAX_TABLE_OUTPUT_BYTES:
        raise GenerationError("generated CSV exceeds the size limit")
    return content


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
    content = ("\n".join(lines) + "\n").encode("utf-8")
    if len(content) > MAX_TABLE_OUTPUT_BYTES:
        raise GenerationError("generated Markdown exceeds the size limit")
    return content


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
        "generation_command": GENERATION_COMMAND,
        "output": output_name,
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


def generate_tables(raw_dir: Path, output_dir: Path) -> list[Path]:
    """Generate deterministic CSV/Markdown tables and provenance sidecars."""

    raw_dir = Path(raw_dir)
    output_dir = Path(output_dir)
    records = _load_records(raw_dir)
    rows = _table_rows(records)
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

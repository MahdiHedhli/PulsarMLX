#!/usr/bin/env python3
"""Read-only verification boundary for Feature 002 evidence candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import tempfile
from typing import Any

import generate_figures
import generate_tables
from publish_evidence import (
    PublicationError,
    _read_candidate,
    _reject_non_public_values,
    sanitize_candidate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_RAW_DIRECTORY = (
    REPOSITORY_ROOT / "fixtures" / "research" / "router-v1" / "evidence"
)
CLAIMS_LEDGER = REPOSITORY_ROOT / "docs" / "research" / "CLAIMS_LEDGER.md"
REVIEWER_INDEX = REPOSITORY_ROOT / "docs" / "research" / "REVIEWER_INDEX.md"

MAX_DOCUMENT_BYTES = 512 * 1024
MAX_SIDECAR_BYTES = 128 * 1024
MAX_GENERATED_BYTES = 4 * 1024 * 1024
MAX_RAW_BYTES = 16 * 1024 * 1024
MAX_PUBLICATION_RAW_FILES = 512
MAX_PACKAGE_BYTES = 96 * 1024 * 1024
MAX_PACKAGE_FILES = 4_096
MAX_MARKDOWN_LINKS = 8_192
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CLAIM_ID_RE = re.compile(r"^(F002-C[0-9]{2})\s+\S.*$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\n]+)\)")
URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

SIDECAR_FIELDS = {
    "schema_id",
    "schema_version",
    "generator",
    "generator_sha256",
    "generation_command",
    "output",
    "output_sha256",
    "source_commits",
    "sources",
}
REVIEWER_SECTIONS = (
    "## Raw evidence",
    "## Generated tables",
    "## Generated figures",
    "## Claims and reproduction links",
)


class VerificationError(ValueError):
    """A bounded package-verification failure."""


def _reject_symlink_components(path: Path) -> None:
    """Reject caller-controlled symlinks without rejecting macOS root aliases."""

    current = path.absolute()
    while True:
        is_macos_root_alias = (
            current.parent == Path("/") and current.name in {"var", "tmp", "etc"}
        )
        if current.is_symlink() and not is_macos_root_alias:
            raise VerificationError("publication package contains a symbolic link")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _read_regular_bytes(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> bytes:
    """Read one bounded regular file through a no-follow descriptor."""

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
            raise VerificationError(f"{subject} must be a regular file")
        if before.st_size <= 0 or before.st_size > maximum_bytes:
            raise VerificationError(f"{subject} exceeds its size bound")

        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, min(64 * 1024, maximum_bytes + 1)):
            size += len(chunk)
            if size > maximum_bytes:
                raise VerificationError(f"{subject} exceeds its size bound")
            chunks.append(chunk)
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
        ) or size != before.st_size:
            raise VerificationError(f"{subject} changed while it was read")
        return b"".join(chunks)
    except VerificationError:
        raise
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_bounded_text(path: Path, *, subject: str) -> str:
    raw = _read_regular_bytes(
        path,
        maximum_bytes=MAX_DOCUMENT_BYTES,
        subject=subject,
    )
    try:
        return raw.decode("utf-8")
    except UnicodeError as error:
        raise VerificationError(f"{subject} is not valid UTF-8") from error


def _verify_public_document(text: str, *, subject: str) -> None:
    try:
        _reject_non_public_values({"public_document": text})
    except PublicationError as error:
        raise VerificationError(
            f"{subject} contains forbidden private or secret content"
        ) from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("publication JSON contains a duplicate field")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise VerificationError("publication JSON contains a non-finite number")


def _read_json_object(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> tuple[dict[str, Any], bytes]:
    raw = _read_regular_bytes(path, maximum_bytes=maximum_bytes, subject=subject)
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except VerificationError:
        raise
    except (RecursionError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise VerificationError(f"{subject} contains invalid JSON") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{subject} root must be an object")
    return value, raw


def _resolved_repository_root() -> Path:
    try:
        root = REPOSITORY_ROOT.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("repository root is unavailable") from error
    if not root.is_dir():
        raise VerificationError("repository root is unavailable")
    return root


def _relative_to_root(path: Path, root: Path, *, subject: str) -> str:
    try:
        return path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as error:
        raise VerificationError(f"{subject} escapes the repository") from error


def _resolve_repository_relative_file(value: str, *, subject: str) -> Path:
    """Resolve a strict repository-relative POSIX file path."""

    if (
        not value
        or "\x00" in value
        or "\\" in value
        or "?" in value
        or "#" in value
        or "%" in value
        or URI_SCHEME_RE.match(value)
    ):
        raise VerificationError(f"{subject} is not a package-relative path")
    lexical_parts = value.split("/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(
        part in {"", ".", ".."} for part in lexical_parts
    ):
        raise VerificationError(f"{subject} is not a package-relative path")

    root = _resolved_repository_root()
    candidate = REPOSITORY_ROOT.joinpath(*pure.parts)
    _reject_symlink_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise VerificationError(f"{subject} is unavailable or escapes the repository") from error
    try:
        mode = resolved.stat().st_mode
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    if not stat.S_ISREG(mode):
        raise VerificationError(f"{subject} must identify a regular file")
    return resolved


def _markdown_target(target: str) -> str:
    """Return an unambiguous Markdown link target without an optional title."""

    value = target.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if not value or any(character.isspace() for character in value):
        raise VerificationError("publication documentation has an ambiguous link")
    return value


def _resolve_markdown_file(
    target: str,
    *,
    document: Path,
    package_only: bool,
    subject: str,
) -> Path | None:
    """Resolve a local Markdown link with lexical and resolved containment."""

    value = _markdown_target(target)
    if URI_SCHEME_RE.match(value):
        if value.startswith(("https:", "http:")):
            return None
        raise VerificationError(f"{subject} uses an unsupported link scheme")
    if value.startswith("#"):
        return None
    if (
        "\x00" in value
        or "\\" in value
        or "?" in value
        or "#" in value
        or "%" in value
    ):
        raise VerificationError(f"{subject} is not a safe local link")
    lexical_parts = value.split("/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts:
        raise VerificationError(f"{subject} is not a safe local link")
    if any(part in {"", "."} for part in lexical_parts):
        raise VerificationError(f"{subject} is not a safe local link")
    if package_only and ".." in lexical_parts:
        raise VerificationError(f"{subject} is not package-relative")

    root = _resolved_repository_root()
    try:
        package_root = CLAIMS_LEDGER.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError("publication package root is unavailable") from error
    candidate = document.parent.joinpath(*pure.parts)
    _reject_symlink_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(package_root if package_only else root)
    except (OSError, RuntimeError, ValueError) as error:
        raise VerificationError(f"{subject} is unavailable or escapes its package") from error
    try:
        mode = resolved.stat().st_mode
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    if not stat.S_ISREG(mode):
        raise VerificationError(f"{subject} must identify a regular file")
    return resolved


def _markdown_links(text: str) -> list[str]:
    links = MARKDOWN_LINK_RE.findall(text)
    if len(links) > MAX_MARKDOWN_LINKS:
        raise VerificationError("publication documentation contains too many links")
    return links


def _flat_files(directory: Path, *, subject: str) -> list[Path]:
    """Inventory a bounded flat publication directory without following links."""

    if directory.is_symlink():
        raise VerificationError(f"{subject} cannot be a symbolic link")
    if not directory.exists():
        return []
    _reject_symlink_components(directory)
    try:
        if not directory.is_dir():
            raise VerificationError(f"{subject} must be a directory")
        entries = sorted(directory.iterdir(), key=lambda item: item.name)
    except OSError as error:
        raise VerificationError(f"{subject} is unavailable") from error
    if len(entries) > MAX_PACKAGE_FILES:
        raise VerificationError(f"{subject} contains too many entries")
    files: list[Path] = []
    for entry in entries:
        _reject_symlink_components(entry)
        try:
            mode = entry.stat().st_mode
        except OSError as error:
            raise VerificationError(f"{subject} contains an unavailable entry") from error
        if not stat.S_ISREG(mode):
            raise VerificationError(f"{subject} must contain only regular files")
        files.append(entry)
    return files


def verify_candidate(
    candidate_path: Path | str,
    *,
    expected_feature: str,
) -> dict[str, Any]:
    """Verify one candidate without modifying it or creating sidecar state."""

    path = Path(candidate_path)
    try:
        record, raw = _read_candidate(path)
        sanitized = sanitize_candidate(record)
    except PublicationError as error:
        raise VerificationError(str(error)) from error
    if sanitized["feature_id"] != expected_feature:
        raise VerificationError("candidate feature identity does not match")

    sanitized_bytes = (
        json.dumps(sanitized, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return {
        "passed": True,
        "experiment_id": sanitized["experiment_id"],
        "feature_id": sanitized["feature_id"],
        "candidate_sha256": hashlib.sha256(raw).hexdigest(),
        "sanitized_sha256": hashlib.sha256(sanitized_bytes).hexdigest(),
        "full_schema": "evidence_schema" in sanitized,
    }


def verify_candidate_collection(
    candidate: Path | str,
    *,
    expected_feature: str,
) -> list[dict[str, Any]]:
    """Verify a candidate file or a flat append-only candidate directory."""

    path = Path(candidate)
    if path.is_symlink():
        raise VerificationError("candidate collection cannot be a symbolic link")
    if path.is_file():
        return [verify_candidate(path, expected_feature=expected_feature)]
    if not path.is_dir():
        raise VerificationError("candidate collection is unavailable")
    files = sorted(path.glob("*.json"))
    if not files:
        raise VerificationError("candidate collection contains no JSON records")

    results = [
        verify_candidate(item, expected_feature=expected_feature)
        for item in files
    ]
    identities = [result["experiment_id"] for result in results]
    if len(identities) != len(set(identities)):
        raise VerificationError("candidate collection repeats an experiment identity")
    for item, identity in zip(files, identities, strict=True):
        if item.stem != identity:
            raise VerificationError("candidate filename and experiment identity differ")
    return results


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify_deterministic_regeneration(raw_directory: Path | str) -> dict[str, Any]:
    """Regenerate tables and figures twice and compare every output byte."""

    raw_path = Path(raw_directory)
    with tempfile.TemporaryDirectory(prefix="pulsarmlx-verify-a-") as first_temp:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-verify-b-") as second_temp:
            first = Path(first_temp)
            second = Path(second_temp)
            try:
                generate_tables.generate_tables(raw_path, first / "tables")
                generate_figures.generate_figures(raw_path, first / "figures")
                generate_tables.generate_tables(raw_path, second / "tables")
                generate_figures.generate_figures(raw_path, second / "figures")
            except (generate_tables.GenerationError, generate_figures.GenerationError) as error:
                raise VerificationError("deterministic regeneration failed") from error
            first_files = _tree_bytes(first)
            second_files = _tree_bytes(second)
            if not first_files or first_files != second_files:
                raise VerificationError("generated package is not byte-for-byte deterministic")
            return {
                "artifact_count": len(first_files),
                "artifact_sha256": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in sorted(first_files.items())
                },
            }


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_publication_raw_records(
    raw_files: list[Path],
) -> tuple[dict[Path, dict[str, Any]], dict[str, str], list[str]]:
    """Validate committed raw records and derive their exact provenance sets."""

    root = _resolved_repository_root()
    records: dict[Path, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    commits: set[str] = set()
    experiment_ids: set[str] = set()
    for path in raw_files:
        if path.suffix != ".json":
            raise VerificationError("raw evidence directory contains a non-JSON file")
        record, raw = _read_json_object(
            path,
            maximum_bytes=MAX_RAW_BYTES,
            subject="raw evidence",
        )
        try:
            sanitized = sanitize_candidate(record)
        except PublicationError as error:
            raise VerificationError("published raw evidence is invalid") from error
        if sanitized.get("feature_id") != "002-qwen-router-parity":
            raise VerificationError("published raw evidence has the wrong feature identity")
        if "evidence_schema" not in sanitized:
            raise VerificationError("published raw evidence must use the full schema")
        experiment_id = record.get("experiment_id")
        if not isinstance(experiment_id, str) or path.name != f"{experiment_id}.json":
            raise VerificationError("raw filename and experiment identity differ")
        if experiment_id in experiment_ids:
            raise VerificationError("raw package repeats an experiment identity")
        experiment_ids.add(experiment_id)
        commit = record.get("source_commit")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise VerificationError("raw evidence has an invalid source commit")
        resolved = path.resolve(strict=True)
        relative = _relative_to_root(resolved, root, subject="raw evidence")
        records[resolved] = sanitized
        sources[relative] = _sha256(raw)
        commits.add(commit)
    return records, dict(sorted(sources.items())), sorted(commits)


def _generator_contract(directory_name: str) -> tuple[Any, str, str]:
    if directory_name == "tables":
        module = generate_tables
    elif directory_name == "figures":
        module = generate_figures
    else:  # Defensive: callers pass only the two fixed publication directories.
        raise VerificationError("generated artifact directory is unsupported")
    generator = getattr(module, "GENERATOR_ID", None)
    command = getattr(module, "GENERATION_COMMAND", None)
    if not isinstance(generator, str) or not generator:
        raise VerificationError("generator identity is unavailable")
    if not isinstance(command, str) or not command:
        raise VerificationError("generator command identity is unavailable")
    return module, generator, command


def _verify_generated_directory(
    directory: Path,
    files: list[Path],
    *,
    expected_sources: dict[str, str],
    expected_commits: list[str],
) -> list[Path]:
    """Verify every output/sidecar pair against current source and generator bytes."""

    if directory.name == "tables":
        allowed_outputs = {".csv", ".md"}
        basename = getattr(generate_tables, "OUTPUT_BASENAME", None)
        expected_output_names = (
            {f"{basename}.csv", f"{basename}.md"}
            if isinstance(basename, str) and basename
            else set()
        )
    elif directory.name == "figures":
        allowed_outputs = {".svg"}
        output_name = getattr(generate_figures, "OUTPUT_NAME", None)
        expected_output_names = (
            {output_name} if isinstance(output_name, str) and output_name else set()
        )
    else:
        raise VerificationError("generated artifact directory is unsupported")

    outputs = [path for path in files if not path.name.endswith(".sources.json")]
    sidecars = [path for path in files if path.name.endswith(".sources.json")]
    if any(path.suffix not in allowed_outputs for path in outputs):
        raise VerificationError("generated artifact has an unsupported file type")
    if outputs and {path.name for path in outputs} != expected_output_names:
        raise VerificationError("generated artifact set does not match the current generator")
    expected_sidecars = {directory / f"{path.name}.sources.json" for path in outputs}
    if set(sidecars) != expected_sidecars:
        raise VerificationError("generated outputs and provenance sidecars are incomplete")

    module, generator_id, generation_command = _generator_contract(directory.name)
    generator_file_value = getattr(module, "__file__", None)
    if not isinstance(generator_file_value, str) or not generator_file_value:
        raise VerificationError("generator source file is unavailable")
    generator_bytes = _read_regular_bytes(
        Path(generator_file_value),
        maximum_bytes=MAX_GENERATED_BYTES,
        subject="generator source",
    )
    generator_sha256 = _sha256(generator_bytes)

    for output in outputs:
        output_bytes = _read_regular_bytes(
            output,
            maximum_bytes=MAX_GENERATED_BYTES,
            subject="generated output",
        )
        if directory.name == "figures":
            svg_bound = getattr(generate_figures, "MAX_SVG_BYTES", None)
            if not isinstance(svg_bound, int) or len(output_bytes) >= svg_bound:
                raise VerificationError("generated SVG exceeds the frozen size bound")
        sidecar_path = directory / f"{output.name}.sources.json"
        sidecar, sidecar_bytes = _read_json_object(
            sidecar_path,
            maximum_bytes=MAX_SIDECAR_BYTES,
            subject="generated provenance sidecar",
        )
        canonical = (
            json.dumps(sidecar, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if sidecar_bytes != canonical:
            raise VerificationError("generated provenance sidecar is not canonical JSON")
        if set(sidecar) != SIDECAR_FIELDS:
            raise VerificationError("generated provenance sidecar has an invalid shape")
        if (
            sidecar.get("schema_id") != "pulsarmlx.research.generated-sources"
            or sidecar.get("schema_version") != "1.0.0"
            or sidecar.get("generator") != generator_id
            or sidecar.get("generator_sha256") != generator_sha256
            or sidecar.get("generation_command") != generation_command
            or sidecar.get("output") != output.name
            or sidecar.get("output_sha256") != _sha256(output_bytes)
        ):
            raise VerificationError("generated provenance identity or hash is invalid")

        source_values = sidecar.get("sources")
        if not isinstance(source_values, dict) or any(
            not isinstance(path_value, str)
            or not isinstance(hash_value, str)
            or not SHA256_RE.fullmatch(hash_value)
            for path_value, hash_value in source_values.items()
        ):
            raise VerificationError("generated provenance sources are invalid")
        for source_path, source_hash in source_values.items():
            resolved = _resolve_repository_relative_file(
                source_path,
                subject="generated provenance source",
            )
            raw = _read_regular_bytes(
                resolved,
                maximum_bytes=MAX_RAW_BYTES,
                subject="generated provenance source",
            )
            if _sha256(raw) != source_hash:
                raise VerificationError("generated provenance source hash is stale")
        if source_values != expected_sources:
            raise VerificationError("generated provenance source set is incomplete")

        source_commits = sidecar.get("source_commits")
        if (
            not isinstance(source_commits, list)
            or any(
                not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit)
                for commit in source_commits
            )
            or source_commits != sorted(set(source_commits))
            or source_commits != expected_commits
        ):
            raise VerificationError("generated provenance commit set is invalid")
    return outputs


def _reviewer_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    positions: list[int] = []
    for heading in REVIEWER_SECTIONS:
        matches = [index for index, line in enumerate(lines) if line == heading]
        if len(matches) != 1:
            raise VerificationError("reviewer index is missing or repeats a required section")
        positions.append(matches[0])
    if positions != sorted(positions):
        raise VerificationError("reviewer index sections are out of order")
    sections: dict[str, str] = {}
    for index, heading in enumerate(REVIEWER_SECTIONS):
        end = positions[index + 1] if index + 1 < len(positions) else len(lines)
        sections[heading] = "\n".join(lines[positions[index] + 1 : end])
    return sections


def _resolved_section_links(section: str) -> list[Path]:
    links: list[Path] = []
    for target in _markdown_links(section):
        resolved = _resolve_markdown_file(
            target,
            document=REVIEWER_INDEX,
            package_only=False,
            subject="reviewer-index link",
        )
        if resolved is not None:
            links.append(resolved)
    return links


def _require_exact_reviewer_coverage(
    links: list[Path],
    expected: list[Path],
    *,
    subject: str,
) -> None:
    normalized = [path.resolve(strict=True) for path in links]
    for path in expected:
        count = normalized.count(path.resolve(strict=True))
        if count != 1:
            raise VerificationError(f"reviewer index does not uniquely name every {subject}")


def _split_markdown_row(line: str) -> list[str]:
    if not line.startswith("|") or not line.endswith("|"):
        raise VerificationError("claims ledger row is malformed")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    cells.append("".join(current).strip())
    return cells


def _record_scopes(record: dict[str, Any]) -> set[str]:
    try:
        repository = record["model"]["repository"]
        revision = record["model"]["revision"]
        tensor = record["tensor"]["name"]
        depth = record["claim_boundary"]["operation"]
        summaries = record["summaries"]
    except (KeyError, TypeError) as error:
        raise VerificationError("linked evidence cannot establish exact claim scope") from error
    if any(not isinstance(value, str) or not value for value in (repository, revision, tensor, depth)):
        raise VerificationError("linked evidence has an invalid claim scope")
    case_ids: set[str] = set()
    if isinstance(summaries, list):
        for summary in summaries:
            if isinstance(summary, dict) and isinstance(summary.get("group"), dict):
                case_id = summary["group"].get("case_id")
                if isinstance(case_id, str) and case_id:
                    case_ids.add(case_id)
    if not case_ids:
        raise VerificationError("linked evidence has no exact case scope")
    return {
        ";".join(
            (
                f"checkpoint={repository}@{revision}",
                f"tensor={tensor}",
                f"case={case_id}",
                f"depth={depth}",
            )
        )
        for case_id in case_ids
    }


def _promotion_identity(record: dict[str, Any]) -> str:
    """Return the immutable identity that an independent reproduction must match."""

    try:
        identity = {
            "model": {
                key: record["model"][key]
                for key in ("repository", "revision", "filename", "sha256")
            },
            "tensor": {
                key: record["tensor"][key]
                for key in ("name", "encoded_sha256")
            },
            "input": {
                key: record["input"][key]
                for key in ("fixture_id", "canonical_sha256")
            },
            "oracle": {
                key: record["oracle"][key]
                for key in ("oracle_id", "input_fixture_sha256", "tensor_sha256", "output_sha256")
            },
            "output_sha256": record["correctness"]["repeat_output_hashes"][0],
        }
    except (IndexError, KeyError, TypeError) as error:
        raise VerificationError("linked evidence lacks promotion identity") from error
    return json.dumps(identity, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _verify_claim_promotion(records: list[dict[str, Any]]) -> None:
    """Require two clean, matching raw attempts before package-level promotion."""

    if len(records) < 2:
        raise VerificationError("verified claim lacks clean-checkout reproduction evidence")
    identities = {_promotion_identity(record) for record in records}
    experiment_ids = {record.get("experiment_id") for record in records}
    process_ids = {record.get("process_replication_id") for record in records}
    if len(identities) != 1 or len(experiment_ids) != len(records) or len(process_ids) < 2:
        raise VerificationError("verified claim reproduction identity is incomplete")
    for record in records:
        boundary = record.get("claim_boundary")
        correctness = record.get("correctness")
        unsupported = boundary.get("unsupported_interpretations") if isinstance(boundary, dict) else None
        if (
            record.get("actual_status") != "passed"
            or record.get("source_worktree_before") != "clean"
            or not isinstance(correctness, dict)
            or correctness.get("passed") is not True
            or not isinstance(boundary, dict)
            or boundary.get("status") != "provisional"
            or not isinstance(unsupported, list)
            or "real_checkpoint_routing" in unsupported
        ):
            raise VerificationError("verified claim is not supported by promotable evidence")


def _validate_claim_rows(
    claims_text: str,
    raw_records: dict[Path, dict[str, Any]],
) -> int:
    header = "| Claim | Evidence files | Commit | Scope | Status | Caveat |"
    lines = claims_text.splitlines()
    header_positions = [index for index, line in enumerate(lines) if line == header]
    if len(header_positions) != 1:
        raise VerificationError("claims ledger has an invalid table header")
    header_index = header_positions[0]
    if header_index + 1 >= len(lines):
        raise VerificationError("claims ledger has no table separator")
    separator = _split_markdown_row(lines[header_index + 1])
    if len(separator) != 6 or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        raise VerificationError("claims ledger has an invalid table separator")

    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            continue
        cells = _split_markdown_row(line)
        if len(cells) != 6:
            raise VerificationError("claims ledger row has the wrong field count")
        rows.append(cells)
    if len(rows) > MAX_PACKAGE_FILES:
        raise VerificationError("claims ledger contains too many rows")

    claim_ids: set[str] = set()
    raw_root = (CLAIMS_LEDGER.parent / "raw" / "002-router-parity").resolve()
    for claim, evidence, commit, scope, status, caveat in rows:
        match = CLAIM_ID_RE.fullmatch(claim)
        if (
            match is None
            or not evidence
            or not COMMIT_RE.fullmatch(commit)
            or not scope
            or status not in {"verified", "provisional", "rejected", "unsupported"}
            or not caveat
        ):
            raise VerificationError("claims ledger row is incomplete or invalid")
        claim_id = match.group(1)
        if claim_id in claim_ids:
            raise VerificationError("claims ledger repeats a claim identity")
        claim_ids.add(claim_id)

        evidence_paths: list[Path] = []
        for target in _markdown_links(evidence):
            resolved = _resolve_markdown_file(
                target,
                document=CLAIMS_LEDGER,
                package_only=True,
                subject="claim evidence link",
            )
            if resolved is None:  # External links are not package evidence.
                raise VerificationError("claim evidence must be package-relative")
            evidence_paths.append(resolved)
        if not evidence_paths or len(evidence_paths) != len(set(evidence_paths)):
            raise VerificationError("claim evidence links are missing or duplicated")

        linked_records: list[dict[str, Any]] = []
        for path in evidence_paths:
            try:
                path.relative_to(raw_root)
            except ValueError:
                continue
            record = raw_records.get(path)
            if record is None:
                raise VerificationError("claim links unindexed raw evidence")
            linked_records.append(record)
        if not linked_records:
            raise VerificationError("claim has no linked machine-readable raw evidence")
        if any(record.get("source_commit") != commit for record in linked_records):
            raise VerificationError("claim commit does not match linked evidence")
        if any(scope not in _record_scopes(record) for record in linked_records):
            raise VerificationError("claim scope does not exactly match linked evidence")

        if status == "verified":
            _verify_claim_promotion(linked_records)
        elif status == "provisional":
            if any(
                record.get("actual_status") != "passed"
                or not isinstance(record.get("claim_boundary"), dict)
                or record["claim_boundary"].get("status") != "provisional"
                for record in linked_records
            ):
                raise VerificationError("provisional claim is not supported by passing evidence")
        elif status == "rejected" and all(
            record.get("actual_status") == "passed" for record in linked_records
        ):
            raise VerificationError("rejected claim does not link a failed outcome")
    return len(rows)


def verify_publication_index() -> dict[str, int]:
    """Verify bounded provenance, claim promotion, and reviewer completeness."""

    claims_text = _read_bounded_text(CLAIMS_LEDGER, subject="claims ledger")
    reviewer_text = _read_bounded_text(REVIEWER_INDEX, subject="reviewer index")
    _verify_public_document(claims_text, subject="claims ledger")
    _verify_public_document(reviewer_text, subject="reviewer index")
    research_root = CLAIMS_LEDGER.parent
    if REVIEWER_INDEX.parent.resolve(strict=True) != research_root.resolve(strict=True):
        raise VerificationError("publication index documents do not share a package root")

    raw_files = _flat_files(
        research_root / "raw" / "002-router-parity",
        subject="raw evidence directory",
    )
    table_files = _flat_files(research_root / "tables", subject="generated tables")
    figure_files = _flat_files(research_root / "figures", subject="generated figures")
    if len(raw_files) + len(table_files) + len(figure_files) > MAX_PACKAGE_FILES:
        raise VerificationError("publication package contains too many files")
    if len(raw_files) > MAX_PUBLICATION_RAW_FILES:
        raise VerificationError("publication package contains too many raw records")
    try:
        package_bytes = sum(
            path.stat().st_size
            for path in (*raw_files, *table_files, *figure_files)
        )
    except OSError as error:
        raise VerificationError("publication package size cannot be inspected") from error
    if package_bytes > MAX_PACKAGE_BYTES:
        raise VerificationError("publication package exceeds the aggregate size bound")

    raw_records, expected_sources, expected_commits = _load_publication_raw_records(
        raw_files
    )
    table_outputs = _verify_generated_directory(
        research_root / "tables",
        table_files,
        expected_sources=expected_sources,
        expected_commits=expected_commits,
    )
    figure_outputs = _verify_generated_directory(
        research_root / "figures",
        figure_files,
        expected_sources=expected_sources,
        expected_commits=expected_commits,
    )
    if raw_files and (not table_outputs or not figure_outputs):
        raise VerificationError("published raw evidence lacks generated tables or figures")
    if (table_outputs or figure_outputs) and not raw_files:
        raise VerificationError("generated package has no raw evidence")

    sections = _reviewer_sections(reviewer_text)
    raw_links = _resolved_section_links(sections["## Raw evidence"])
    table_links = _resolved_section_links(sections["## Generated tables"])
    figure_links = _resolved_section_links(sections["## Generated figures"])
    claim_links = _resolved_section_links(sections["## Claims and reproduction links"])
    _require_exact_reviewer_coverage(raw_links, raw_files, subject="raw artifact")
    _require_exact_reviewer_coverage(table_links, table_files, subject="table artifact")
    _require_exact_reviewer_coverage(figure_links, figure_files, subject="figure artifact")
    _require_exact_reviewer_coverage(
        claim_links,
        [CLAIMS_LEDGER, research_root / "REPRODUCIBILITY.md"],
        subject="claim/reproduction document",
    )

    claim_count = _validate_claim_rows(claims_text, raw_records)
    return {"claim_count": claim_count}


def verify_committed_regeneration(raw_directory: Path | str) -> dict[str, Any]:
    """Require fresh deterministic outputs to equal every committed package byte."""

    regeneration = verify_deterministic_regeneration(raw_directory)
    research_root = CLAIMS_LEDGER.parent
    files = _flat_files(research_root / "tables", subject="generated tables")
    files.extend(
        _flat_files(research_root / "figures", subject="generated figures")
    )
    committed_hashes: dict[str, str] = {}
    for path in files:
        relative = path.relative_to(research_root).as_posix()
        content = _read_regular_bytes(
            path,
            maximum_bytes=MAX_GENERATED_BYTES,
            subject="committed generated artifact",
        )
        committed_hashes[relative] = _sha256(content)
    if regeneration["artifact_sha256"] != dict(sorted(committed_hashes.items())):
        raise VerificationError(
            "committed generated artifacts differ from fresh regeneration"
        )
    return regeneration


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only verification of a bounded Feature 002 evidence package."
    )
    parser.add_argument("--feature", required=True)
    parser.add_argument(
        "--candidate",
        type=Path,
        help=(
            "Candidate JSON file or directory. If omitted, verify the committed "
            "raw directory for the requested feature."
        ),
    )
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help=(
            "Verify the committed model-free evidence fixture, regenerate its "
            "artifacts twice, and check publication index scaffolding."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.fixture_only and arguments.candidate is not None:
        print(
            "verification_error: --fixture-only and --candidate are mutually exclusive",
            file=os.sys.stderr,
        )
        return 2
    candidate = arguments.candidate
    complete_package = not arguments.fixture_only and candidate is None
    if arguments.fixture_only:
        candidate = FIXTURE_RAW_DIRECTORY
    elif candidate is None:
        candidate = Path("docs/research/raw") / arguments.feature.removeprefix("002-")
        if arguments.feature == "002-qwen-router-parity":
            candidate = Path("docs/research/raw/002-router-parity")
    try:
        results = verify_candidate_collection(
            candidate,
            expected_feature=arguments.feature,
        )
        regeneration: dict[str, Any] | None = None
        publication_index: dict[str, int] | None = None
        if arguments.fixture_only:
            if not results or any(not result["full_schema"] for result in results):
                raise VerificationError("fixture-only input is not full-schema evidence")
            regeneration = verify_deterministic_regeneration(candidate)
            publication_index = verify_publication_index()
        elif complete_package:
            publication_index = verify_publication_index()
            regeneration = verify_committed_regeneration(candidate)
    except VerificationError as error:
        print(f"verification_error: {error}", file=os.sys.stderr)
        return 1
    output: dict[str, Any] = {
        "fixture_only": arguments.fixture_only,
        "passed": True,
        "record_count": len(results),
        "records": results,
    }
    if regeneration is not None:
        output["regeneration"] = regeneration
    if publication_index is not None:
        output["publication_index"] = publication_index
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

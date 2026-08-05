#!/usr/bin/env python3
"""Sanitize and append-only publish bounded research-evidence candidates."""

from __future__ import annotations

import argparse
from copy import deepcopy
import errno
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable

from validate_evidence import EvidenceValidationError, validate_record


MAX_CANDIDATE_BYTES = 16 * 1024 * 1024
SCHEMA_ID = "pulsarmlx.research.experiment"
SCHEMA_VERSION = "1.0.0"
EXPERIMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s='\"])(?:/Users/|/home/|/private/|/tmp/|/var/folders/|"
    r"/Volumes/|[A-Za-z]:\\Users\\)"
)
SECRET_VALUE_RE = re.compile(
    r"(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|"
    r"(?:--|\b)(?:token|password|secret|authorization|cookie|api-key)\b)",
    re.IGNORECASE,
)
SECRET_KEYS = {
    "api_key",
    "auth",
    "authorization",
    "cookie",
    "github_token",
    "hf_token",
    "password",
    "private_key",
    "secret",
    "token",
}


class PublicationError(ValueError):
    """A bounded publication failure safe to report without private values."""


def _walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk(child)


def _reject_non_public_values(record: dict[str, Any]) -> None:
    for key, value in _walk(record):
        if key is not None and key.lower() in SECRET_KEYS:
            raise PublicationError("candidate contains a forbidden secret field")
        if isinstance(value, float) and not math.isfinite(value):
            raise PublicationError("candidate contains a non-finite number")
        if isinstance(value, str):
            if "\x00" in value:
                raise PublicationError("candidate contains an invalid string")
            if PRIVATE_PATH_RE.search(value):
                raise PublicationError("candidate contains a forbidden private path")
            if SECRET_VALUE_RE.search(value):
                raise PublicationError("candidate contains a forbidden secret value")


def _require_candidate_shape(record: dict[str, Any]) -> None:
    if "evidence_schema" in record:
        if (
            record.get("evidence_schema") != SCHEMA_ID
            or record.get("evidence_schema_version") != SCHEMA_VERSION
        ):
            raise PublicationError("candidate schema identity is unsupported")
        try:
            validate_record(record)
        except EvidenceValidationError as error:
            raise PublicationError(
                f"candidate evidence validation failed: {error.code}"
            ) from error
        return

    # The compact publication-boundary record is retained for atomic writer
    # tests. Public Feature 002 evidence uses the full evidence_schema form
    # above and must pass its semantic validator before installation.
    required = {
        "schema_id",
        "schema_version",
        "experiment_id",
        "feature_id",
        "status",
        "scope",
        "source",
        "command",
        "raw_observations",
        "unsupported_interpretations",
    }
    if required - record.keys():
        raise PublicationError("candidate is missing required publication fields")
    if record["schema_id"] != SCHEMA_ID or record["schema_version"] != SCHEMA_VERSION:
        raise PublicationError("candidate schema identity is unsupported")

    experiment_id = record["experiment_id"]
    if not isinstance(experiment_id, str) or not EXPERIMENT_ID_RE.fullmatch(experiment_id):
        raise PublicationError("candidate experiment identity is invalid")
    feature_id = record["feature_id"]
    if not isinstance(feature_id, str) or not EXPERIMENT_ID_RE.fullmatch(feature_id):
        raise PublicationError("candidate feature identity is invalid")
    if record["status"] not in {"passed", "failed", "blocked", "aborted", "excluded"}:
        raise PublicationError("candidate status is unsupported")
    if not isinstance(record["scope"], str) or not record["scope"]:
        raise PublicationError("candidate scope is invalid")

    source = record["source"]
    if not isinstance(source, dict) or set(source) != {"commit", "clean"}:
        raise PublicationError("candidate source identity is invalid")
    if not isinstance(source["commit"], str) or not COMMIT_RE.fullmatch(source["commit"]):
        raise PublicationError("candidate source commit is invalid")
    if type(source["clean"]) is not bool:
        raise PublicationError("candidate source cleanliness is invalid")

    command = record["command"]
    if not isinstance(command, dict) or set(command) != {"display", "exit_code"}:
        raise PublicationError("candidate command identity is invalid")
    if not isinstance(command["display"], str) or not command["display"]:
        raise PublicationError("candidate command is invalid")
    if type(command["exit_code"]) is not int:
        raise PublicationError("candidate command result is invalid")

    observations = record["raw_observations"]
    if not isinstance(observations, list) or not observations:
        raise PublicationError("candidate observations are unavailable")
    observation_ids: set[str] = set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise PublicationError("candidate observation is invalid")
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str) or not EXPERIMENT_ID_RE.fullmatch(observation_id):
            raise PublicationError("candidate observation identity is invalid")
        if observation_id in observation_ids:
            raise PublicationError("candidate observation identity is duplicated")
        observation_ids.add(observation_id)

    unsupported = record["unsupported_interpretations"]
    if (
        not isinstance(unsupported, list)
        or not unsupported
        or any(not isinstance(item, str) or not item for item in unsupported)
    ):
        raise PublicationError("candidate claim boundary is invalid")


def sanitize_candidate(record: dict[str, Any]) -> dict[str, Any]:
    """Return a public deep copy after removing only declared local metadata."""

    if not isinstance(record, dict):
        raise PublicationError("candidate root must be an object")
    sanitized = deepcopy(record)
    local = sanitized.pop("_local", None)
    if local is not None and not isinstance(local, dict):
        raise PublicationError("candidate local metadata is invalid")
    if any(isinstance(key, str) and key.startswith("_") for key in sanitized):
        raise PublicationError("candidate contains undeclared local metadata")

    _require_candidate_shape(sanitized)
    _reject_non_public_values(sanitized)
    try:
        # A JSON round trip both proves serializability and removes object aliases.
        return json.loads(json.dumps(sanitized, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError) as error:
        raise PublicationError("candidate is not bounded JSON") from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError("candidate contains a duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise PublicationError("candidate contains a non-finite JSON number")


def _read_candidate(path: Path) -> tuple[dict[str, Any], bytes]:
    _reject_symlink_components(path)
    if path.is_symlink() or not path.is_file():
        raise PublicationError("candidate must be a regular file")
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_CANDIDATE_BYTES:
            raise PublicationError("candidate size is outside the publication bound")
        raw = path.read_bytes()
        record = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except PublicationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError("candidate JSON is unreadable or invalid") from error
    if not isinstance(record, dict):
        raise PublicationError("candidate root must be an object")
    return record, raw


def _reject_symlink_components(path: Path) -> None:
    current = path.absolute()
    while True:
        # macOS intentionally exposes /var, /tmp, and /etc as root-level
        # compatibility symlinks into /private.  They are not caller-selected
        # publication aliases; every lower component remains checked.
        is_macos_root_alias = (
            current.parent == Path("/") and current.name in {"var", "tmp", "etc"}
        )
        if current.is_symlink() and not is_macos_root_alias:
            raise PublicationError("publication path contains a symbolic link")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _canonical_bytes(record: dict[str, Any]) -> bytes:
    return (json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_candidate(candidate_path: Path | str, raw_directory: Path | str) -> Path:
    """Sanitize and atomically install one candidate without replacing history."""

    candidate = Path(candidate_path)
    destination_directory = Path(raw_directory)
    record, _ = _read_candidate(candidate)
    sanitized = sanitize_candidate(record)
    payload = _canonical_bytes(sanitized)

    _reject_symlink_components(destination_directory)
    if destination_directory.exists() and not destination_directory.is_dir():
        raise PublicationError("publication destination is not a directory")
    try:
        destination_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise PublicationError("publication destination cannot be created") from error
    _reject_symlink_components(destination_directory)

    destination = destination_directory / f"{sanitized['experiment_id']}.json"
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{sanitized['experiment_id']}.",
            suffix=".tmp",
            dir=destination_directory,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, destination, follow_symlinks=False)
        except OSError as error:
            if error.errno == errno.EEXIST:
                raise FileExistsError(destination.name) from None
            raise PublicationError("candidate could not be installed atomically") from error
        _sync_directory(destination_directory)
        temporary_path.unlink()
        temporary_path = None
        _sync_directory(destination_directory)
        return destination
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sanitize and append-only publish one bounded evidence candidate."
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        installed = publish_candidate(arguments.candidate, arguments.output_dir)
    except FileExistsError:
        print("publication_error: experiment identity already exists", file=os.sys.stderr)
        return 1
    except PublicationError as error:
        print(f"publication_error: {error}", file=os.sys.stderr)
        return 1
    print(f"published: {installed.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

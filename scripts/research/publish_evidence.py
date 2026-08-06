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
import stat
import tempfile
from typing import Any, Iterable

from validate_evidence import EvidenceValidationError, validate_record


MAX_CANDIDATE_BYTES = 16 * 1024 * 1024
MAX_HISTORY_FILES = 512
MAX_HISTORY_BYTES = 64 * 1024 * 1024
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64
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
    r"Bearer\s+[^\s'\"]+)",
    re.IGNORECASE,
)
CREDENTIAL_OPTION_RE = re.compile(
    r"--(?P<name>[A-Za-z][A-Za-z0-9_-]*)(?=[\s=]|$)"
)
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*[:=]"
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
PRIVATE_IDENTIFIER_KEYS = {
    "account",
    "account_id",
    "account_identifier",
    "email",
    "email_address",
    "hardware_uuid",
    "host",
    "host_name",
    "hostname",
    "machine_id",
    "machine_identifier",
    "process_command_line",
    "serial",
    "serial_number",
    "shell_history",
    "user",
    "user_name",
    "username",
    "uuid",
}
ENVIRONMENT_KEY_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "AUTH", "COOKIE", "KEY")
PUBLIC_TOKEN_IDENTIFIER_KEYS = {"direct_token_ids", "token_ids"}
SECRET_KEY_PARTS = {
    "auth",
    "authentication",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}


class PublicationError(ValueError):
    """A bounded publication failure safe to report without private values."""


def _walk(value: Any) -> Iterable[tuple[tuple[str, ...], str | None, Any]]:
    pending: list[tuple[str, Any, tuple[str, ...], int]] = [
        ("visit", value, (), 0)
    ]
    visited = 0
    while pending:
        action, current, path, depth = pending.pop()
        if action == "yield":
            yield current
            continue
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise PublicationError("candidate exceeds the structural bound")
        if isinstance(current, dict):
            for key, child in reversed(tuple(current.items())):
                if not isinstance(key, str):
                    raise PublicationError("candidate contains an invalid JSON field")
                child_path = (*path, key)
                pending.append(("visit", child, child_path, depth + 1))
                pending.append(
                    ("yield", (child_path, key, child), path, depth + 1)
                )
        elif isinstance(current, list):
            for child in reversed(current):
                pending.append(("visit", child, path, depth + 1))
                pending.append(("yield", (path, None, child), path, depth + 1))


def _normalized_key(key: str) -> str:
    words = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", key)
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", words)
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_")


def _is_environment_key(path: tuple[str, ...]) -> bool:
    return any(
        _normalized_key(component) in {"environment", "safe_environment"}
        for component in path[:-1]
    )


def _is_secret_key(normalized: str, key_parts: set[str]) -> bool:
    if normalized in PUBLIC_TOKEN_IDENTIFIER_KEYS:
        return False
    return (
        normalized in SECRET_KEYS
        or bool(key_parts & SECRET_KEY_PARTS)
        or {"api", "key"} <= key_parts
        or {"private", "key"} <= key_parts
    )


def _contains_secret_value(value: str) -> bool:
    if SECRET_VALUE_RE.search(value):
        return True
    for pattern in (CREDENTIAL_OPTION_RE, CREDENTIAL_ASSIGNMENT_RE):
        for match in pattern.finditer(value):
            normalized = _normalized_key(match.group("name"))
            key_parts = {part for part in normalized.split("_") if part}
            if _is_secret_key(normalized, key_parts):
                return True
    return False


def _reject_non_public_values(record: dict[str, Any]) -> None:
    for path, key, value in _walk(record):
        if key is not None:
            normalized = _normalized_key(key)
            key_parts = {part for part in normalized.split("_") if part}
            if normalized in PRIVATE_IDENTIFIER_KEYS or key_parts & PRIVATE_IDENTIFIER_KEYS:
                raise PublicationError(
                    "candidate contains a forbidden private identifier field"
                )
            if _is_secret_key(normalized, key_parts):
                raise PublicationError("candidate contains a forbidden secret field")
            if _is_environment_key(path):
                environment_key = key.upper()
                if any(marker in environment_key for marker in ENVIRONMENT_KEY_MARKERS):
                    raise PublicationError(
                        "candidate contains a forbidden secret environment field"
                    )
        if isinstance(value, float) and not math.isfinite(value):
            raise PublicationError("candidate contains a non-finite number")
        if isinstance(value, str):
            if "\x00" in value:
                raise PublicationError("candidate contains an invalid string")
            if PRIVATE_PATH_RE.search(value):
                raise PublicationError("candidate contains a forbidden private path")
            if _contains_secret_value(value):
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
    if not isinstance(record["status"], str) or record["status"] not in {
        "passed",
        "failed",
        "blocked",
        "aborted",
        "excluded",
    }:
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
    local = record.get("_local")
    if local is not None and not isinstance(local, dict):
        raise PublicationError("candidate local metadata is invalid")
    try:
        sanitized = deepcopy({key: value for key, value in record.items() if key != "_local"})
    except (RecursionError, TypeError, ValueError) as error:
        raise PublicationError("candidate exceeds the structural bound") from error
    if any(isinstance(key, str) and key.startswith("_") for key in sanitized):
        raise PublicationError("candidate contains undeclared local metadata")

    _require_candidate_shape(sanitized)
    _reject_non_public_values(sanitized)
    try:
        # A JSON round trip both proves serializability and removes object aliases.
        return json.loads(json.dumps(sanitized, allow_nan=False, sort_keys=True))
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
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


def _read_bounded_json(
    path: Path,
    *,
    subject: str,
) -> tuple[dict[str, Any], bytes]:
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
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PublicationError(f"{subject} must be a regular file")
        if metadata.st_size <= 0 or metadata.st_size > MAX_CANDIDATE_BYTES:
            raise PublicationError(f"{subject} size is outside the publication bound")

        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(descriptor, 64 * 1024):
            size += len(chunk)
            if size > MAX_CANDIDATE_BYTES:
                raise PublicationError(
                    f"{subject} size is outside the publication bound"
                )
            chunks.append(chunk)
        raw = b"".join(chunks)
        record = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except PublicationError:
        raise
    except (
        OSError,
        RecursionError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        raise PublicationError(f"{subject} JSON is unreadable or invalid") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(record, dict):
        raise PublicationError(f"{subject} root must be an object")
    return record, raw


def _read_candidate(path: Path) -> tuple[dict[str, Any], bytes]:
    return _read_bounded_json(path, subject="candidate")


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
    try:
        payload = (
            json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise PublicationError("canonical candidate is not bounded JSON") from error
    if len(payload) > MAX_CANDIDATE_BYTES:
        raise PublicationError("canonical candidate exceeds the publication bound")
    return payload


def _validate_publication_history(
    directory: Path,
    *,
    candidate_experiment_id: str,
) -> None:
    """Fail closed on unsafe history and any reused logical experiment ID."""

    try:
        entries: list[Path] = []
        for entry in directory.iterdir():
            if not entry.name.endswith(".json"):
                continue
            entries.append(entry)
            if len(entries) > MAX_HISTORY_FILES:
                raise PublicationError("publication history exceeds the file-count bound")
        entries.sort(key=lambda entry: entry.name)
    except PublicationError:
        raise
    except OSError as error:
        raise PublicationError("publication history cannot be inspected") from error

    seen: set[str] = set()
    total_bytes = 0
    for entry in entries:
        record, raw = _read_bounded_json(entry, subject="publication history")
        total_bytes += len(raw)
        if total_bytes > MAX_HISTORY_BYTES:
            raise PublicationError("publication history exceeds the aggregate bound")
        if "_local" in record or any(
            isinstance(key, str) and key.startswith("_") for key in record
        ):
            raise PublicationError("publication history contains local metadata")
        try:
            _require_candidate_shape(record)
            _reject_non_public_values(record)
        except PublicationError as error:
            raise PublicationError("publication history contains invalid evidence") from error
        experiment_id = record.get("experiment_id")
        if (
            not isinstance(experiment_id, str)
            or not EXPERIMENT_ID_RE.fullmatch(experiment_id)
        ):
            raise PublicationError(
                "publication history contains an invalid experiment identity"
            )
        if experiment_id == candidate_experiment_id:
            raise FileExistsError(f"{candidate_experiment_id}.json")
        if experiment_id in seen:
            raise PublicationError(
                "publication history contains a duplicate experiment identity"
            )
        seen.add(experiment_id)
        if entry.name != f"{experiment_id}.json":
            raise PublicationError(
                "publication history contains a noncanonical experiment filename"
            )


def _rollback_destination(destination: Path, directory: Path) -> bool:
    """Return true only when a linked destination is absent after rollback."""

    try:
        destination.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return not destination.exists()
    try:
        _sync_directory(directory)
    except OSError:
        # The current namespace is still unambiguous: the destination is gone.
        pass
    return not destination.exists()


def _sync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(directory, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("publication destination is not a directory")
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
    _validate_publication_history(
        destination_directory,
        candidate_experiment_id=sanitized["experiment_id"],
    )

    destination = destination_directory / f"{sanitized['experiment_id']}.json"
    temporary_path: Path | None = None
    destination_linked = False
    try:
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{sanitized['experiment_id']}.",
                suffix=".tmp",
                dir=destination_directory,
            )
        except OSError as error:
            raise PublicationError("publication temporary file cannot be created") from error
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary_path, destination, follow_symlinks=False)
            destination_linked = True
        except OSError as error:
            if error.errno == errno.EEXIST:
                raise FileExistsError(destination.name) from None
            raise PublicationError("candidate could not be installed atomically") from error
        _sync_directory(destination_directory)
        temporary_path.unlink()
        temporary_path = None
        _sync_directory(destination_directory)
        return destination
    except FileExistsError:
        raise
    except PublicationError:
        if destination_linked and not _rollback_destination(
            destination, destination_directory
        ):
            # The exclusive link is the publication commit point. Never report
            # failure while that exact destination remains installed.
            return destination
        raise
    except OSError as error:
        if destination_linked and not _rollback_destination(
            destination, destination_directory
        ):
            return destination
        raise PublicationError("candidate could not be installed atomically") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
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

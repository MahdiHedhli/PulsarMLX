#!/usr/bin/env python3
"""Strict, side-effect-free macOS memory observation for F017 admission."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
import subprocess
import time

PARSER_VERSION = "F017_MACOS_VM_STAT_V1"
VM_STAT_COMMAND = ("/usr/bin/vm_stat",)
COMMAND_TIMEOUT_SECONDS = 5.0
MAX_STDOUT_BYTES = 65_536
REQUIRED_ROWS = (
    "Pages free",
    "Pages inactive",
    "Pages speculative",
    "Pages purgeable",
)
_HEADER = re.compile(
    r"\AMach Virtual Memory Statistics:[ \t]+\(page size of ([1-9][0-9]*) bytes\)[ \t]*\Z",
    re.ASCII,
)
_ROW = re.compile(
    r'\A((?:[A-Za-z][A-Za-z0-9 _()/-]{0,127}|"[A-Za-z][A-Za-z0-9 _()/-]{0,126}")):'
    r"[ \t]+([0-9]+)\.?[ \t]*\Z",
    re.ASCII,
)


class MemoryObservationError(ValueError):
    """The native observation cannot safely establish memory authority."""


@dataclass(frozen=True)
class MemoryObservation:
    parser_version: str
    page_size_bytes: int
    pages_free: int
    pages_inactive: int
    pages_speculative: int
    pages_purgeable: int
    available_bytes: int
    canonical_observation: str
    stdout_sha256: str
    observed_at_unix_ns: int

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)


def parse_vm_stat(text: str, *, observed_at_unix_ns: int | None = None) -> MemoryObservation:
    """Parse one bounded ``vm_stat`` observation with an anchored grammar."""
    if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_STDOUT_BYTES:
        raise MemoryObservationError("vm_stat stdout absent or oversized")
    lines = text.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        raise MemoryObservationError("vm_stat output empty")
    header = _HEADER.fullmatch(lines[first])
    if header is None:
        raise MemoryObservationError("vm_stat header grammar")
    page_size = int(header.group(1), 10)
    if page_size <= 0:
        raise MemoryObservationError("page size must be positive")

    required: dict[str, int] = {}
    normalized_rows: list[str] = []
    for line in lines[first + 1 :]:
        if not line.strip():
            continue
        match = _ROW.fullmatch(line)
        if match is None:
            raise MemoryObservationError("vm_stat row grammar")
        name, digits = match.groups()
        count = int(digits, 10)
        normalized_rows.append(f"{name}:{count}")
        if name in REQUIRED_ROWS:
            if name in required:
                raise MemoryObservationError(f"duplicate required row: {name}")
            required[name] = count
    missing = [name for name in REQUIRED_ROWS if name not in required]
    if missing:
        raise MemoryObservationError(f"missing required rows: {','.join(missing)}")

    available = page_size * sum(required[name] for name in REQUIRED_ROWS)
    canonical = "\n".join(
        [f"page_size_bytes:{page_size}"]
        + [f"{name}:{required[name]}" for name in REQUIRED_ROWS]
    )
    return MemoryObservation(
        parser_version=PARSER_VERSION,
        page_size_bytes=page_size,
        pages_free=required["Pages free"],
        pages_inactive=required["Pages inactive"],
        pages_speculative=required["Pages speculative"],
        pages_purgeable=required["Pages purgeable"],
        available_bytes=available,
        canonical_observation=canonical,
        stdout_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        observed_at_unix_ns=observed_at_unix_ns or time.time_ns(),
    )


def observe_vm_stat() -> MemoryObservation:
    """Execute the one fixed command; callers cannot supply an override."""
    try:
        completed = subprocess.run(
            list(VM_STAT_COMMAND),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=COMMAND_TIMEOUT_SECONDS,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MemoryObservationError("vm_stat timeout") from exc
    if completed.returncode != 0:
        raise MemoryObservationError("vm_stat nonzero exit")
    if completed.stderr:
        raise MemoryObservationError("vm_stat stderr is nonempty")
    if len(completed.stdout) > MAX_STDOUT_BYTES:
        raise MemoryObservationError("vm_stat stdout oversized")
    try:
        text = completed.stdout.decode("ascii", errors="strict")
    except UnicodeDecodeError as exc:
        raise MemoryObservationError("vm_stat stdout is not ASCII") from exc
    return parse_vm_stat(text)

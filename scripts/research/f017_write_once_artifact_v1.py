#!/usr/bin/env python3
"""Internal Darwin write-once artifact primitives for F017 authority leaves."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import stat
import sys

from f017_canonical_serialization_v10 import canonical_bytes, sha256_bytes

__all__: tuple[str, ...] = ()


def _set_user_immutable(descriptor: int, enabled: bool) -> None:
    """Set Darwin's owner-controlled immutable flag through the held FD."""
    if sys.platform != "darwin" or type(descriptor) is not int:
        raise RuntimeError("Darwin immutable-file authority required")
    if type(enabled) is not bool:
        raise TypeError("immutable-file policy")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        function = libc.fchflags
    except AttributeError as exc:
        raise RuntimeError("fchflags unavailable") from exc
    function.argtypes = [ctypes.c_int, ctypes.c_uint]
    function.restype = ctypes.c_int
    current = int(os.fstat(descriptor).st_flags)
    target = (
        current | stat.UF_IMMUTABLE
        if enabled
        else current & ~stat.UF_IMMUTABLE
    )
    if function(descriptor, target) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if bool(os.fstat(descriptor).st_flags & stat.UF_IMMUTABLE) is not enabled:
        raise RuntimeError("immutable-file transition did not hold")


def _bank_exclusive_write_once(path: Path, value: object) -> str:
    """Bank, read back, and seal authority on its exclusive writer FD."""
    raw = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(raw)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short artifact write")
            written += count
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or observed.st_uid != os.getuid()
            or observed.st_size != len(raw)
        ):
            raise ValueError("artifact write identity")
        _set_user_immutable(descriptor, True)
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = len(raw)
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("short artifact readback")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1) or b"".join(chunks) != raw:
            raise ValueError("artifact readback mismatch")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return sha256_bytes(raw)

"""Sequence 42 all-process fail-closed live-authority access barrier.

The prohibited roots are extracted lexically from the pinned Event 06 source.
This module is loaded by Python's site initialization before target imports.
"""
from __future__ import annotations

import ast
import builtins
import hashlib as _hashlib_module
import io
import json
import mmap as _mmap_module
import os
from pathlib import Path
import shlex
import stat as _stat
import subprocess
import sys
import threading
import time
import unicodedata


_SOURCE_FILE = os.environ.get("F017_SEQUENCE42_SOURCE_FILE")
_LOG = os.environ.get("F017_SEQUENCE42_BARRIER_LOG")
_BARRIER_DIR = os.path.dirname(__file__)
_LOCK = threading.Lock()
_MAXIMUM_SOURCE_BYTES = 2_000_000
_MAXIMUM_LOG_BYTES = 16_777_216
_HEX64 = frozenset("0123456789abcdef")
_BYPASS_FLAGS = frozenset({"S", "I", "E"})
_TRUSTED_NATIVE_PARENTS = frozenset({"/bin", "/sbin", "/usr/bin", "/usr/sbin"})
_PROHIBITED_NATIVE_EXECUTABLES = frozenset(
    {
        "bash",
        "csh",
        "dash",
        "env",
        "fish",
        "ksh",
        "node",
        "osascript",
        "perl",
        "python",
        "python3",
        "ruby",
        "sh",
        "xargs",
        "zsh",
    }
)
_PROHIBITED_NATIVE_ARGUMENTS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_BARRIER_ENV_KEYS = (
    "F017_SEQUENCE42_SOURCE_FILE",
    "F017_SEQUENCE42_SOURCE_SHA256",
    "F017_SEQUENCE42_SOURCE_DEVICE",
    "F017_SEQUENCE42_SOURCE_INODE",
    "F017_SEQUENCE42_SOURCE_SIZE",
    "F017_SEQUENCE42_SOURCE_MTIME_NS",
    "F017_SEQUENCE42_SOURCE_CTIME_NS",
    "F017_SEQUENCE42_BARRIER_LOG",
    "F017_SEQUENCE42_BARRIER_LOG_DEVICE",
    "F017_SEQUENCE42_BARRIER_LOG_INODE",
)
_TARGET_MODULE_PREFIXES = (
    "f017_event06_",
    "f017_checkpoint_identity_producer_v12",
    "qualify_f017_event06_",
    "test_f017_event06_",
)

_ORIGINAL_OS_OPEN = os.open
_ORIGINAL_OS_CLOSE = os.close
_ORIGINAL_OS_EXIT = os._exit
_ORIGINAL_OS_STAT = os.stat
_ORIGINAL_OS_LSTAT = os.lstat
_ORIGINAL_OS_FSTAT = os.fstat
_ORIGINAL_OS_FDOPEN = os.fdopen
_ORIGINAL_OS_LISTDIR = os.listdir
_ORIGINAL_OS_SCANDIR = os.scandir
_ORIGINAL_OS_READLINK = os.readlink
_ORIGINAL_OS_CHDIR = os.chdir
_ORIGINAL_OS_ACCESS = os.access
_ORIGINAL_OS_CHMOD = os.chmod
_ORIGINAL_OS_CHOWN = os.chown
_ORIGINAL_OS_REMOVE = os.remove
_ORIGINAL_OS_UNLINK = os.unlink
_ORIGINAL_OS_RENAME = os.rename
_ORIGINAL_OS_REPLACE = os.replace
_ORIGINAL_OS_MKDIR = os.mkdir
_ORIGINAL_OS_RMDIR = os.rmdir
_ORIGINAL_OS_READ = os.read
_ORIGINAL_OS_WRITE = os.write
_ORIGINAL_OS_PREAD = getattr(os, "pread", None)
_ORIGINAL_OS_PWRITE = getattr(os, "pwrite", None)
_ORIGINAL_OS_FSYNC = os.fsync
_ORIGINAL_OS_FTRUNCATE = os.ftruncate
_ORIGINAL_OS_FCHMOD = os.fchmod
_ORIGINAL_OS_LSEEK = os.lseek
_ORIGINAL_OS_READV = getattr(os, "readv", None)
_ORIGINAL_OS_WRITEV = getattr(os, "writev", None)
_ORIGINAL_OS_LINK = os.link
_ORIGINAL_OS_SYMLINK = os.symlink
_ORIGINAL_OS_TRUNCATE = os.truncate
_ORIGINAL_OS_UTIME = os.utime
_ORIGINAL_OS_STATVFS = os.statvfs
_ORIGINAL_OS_PUTENV = os.putenv
_ORIGINAL_OS_UNSETENV = os.unsetenv
_ORIGINAL_OS_SYSTEM = os.system
_ORIGINAL_OS_EXECV = os.execv
_ORIGINAL_OS_EXECVE = os.execve
_ORIGINAL_OS_EXECL = os.execl
_ORIGINAL_OS_EXECLP = os.execlp
_ORIGINAL_OS_EXECLPE = os.execlpe
_ORIGINAL_OS_EXECVP = os.execvp
_ORIGINAL_OS_EXECVPE = os.execvpe
_ORIGINAL_OS_POSIX_SPAWN = getattr(os, "posix_spawn", None)
_ORIGINAL_OS_POSIX_SPAWNP = getattr(os, "posix_spawnp", None)
_ORIGINAL_OS_SPAWNV = getattr(os, "spawnv", None)
_ORIGINAL_OS_SPAWNVE = getattr(os, "spawnve", None)
_ORIGINAL_OS_SPAWNVP = getattr(os, "spawnvp", None)
_ORIGINAL_OS_SPAWNVPE = getattr(os, "spawnvpe", None)
_ORIGINAL_OS_SPAWNL = getattr(os, "spawnl", None)
_ORIGINAL_OS_SPAWNLE = getattr(os, "spawnle", None)
_ORIGINAL_OS_SPAWNLP = getattr(os, "spawnlp", None)
_ORIGINAL_OS_SPAWNLPE = getattr(os, "spawnlpe", None)
_ORIGINAL_OS_FORK = getattr(os, "fork", None)
_ORIGINAL_OS_FORKPTY = getattr(os, "forkpty", None)
_ORIGINAL_REALPATH = os.path.realpath
_ORIGINAL_BUILTIN_OPEN = builtins.open
_ORIGINAL_IO_OPEN = io.open
_ORIGINAL_PATH_RESOLVE = Path.resolve
_ORIGINAL_PATH_STAT = Path.stat
_ORIGINAL_PATH_LSTAT = Path.lstat
_ORIGINAL_PATH_OPEN = Path.open
_ORIGINAL_PATH_READ_BYTES = Path.read_bytes
_ORIGINAL_PATH_READ_TEXT = Path.read_text
_ORIGINAL_PATH_WRITE_BYTES = Path.write_bytes
_ORIGINAL_PATH_WRITE_TEXT = Path.write_text
_ORIGINAL_PATH_ITERDIR = Path.iterdir
_ORIGINAL_PATH_GLOB = Path.glob
_ORIGINAL_PATH_RGLOB = Path.rglob
_ORIGINAL_MMAP = _mmap_module.mmap
_ORIGINAL_FILE_DIGEST = getattr(_hashlib_module, "file_digest", None)
_ORIGINAL_POPEN = subprocess.Popen
_ORIGINAL_GETENV = os.getenv
_ENVIRON_CLASS = type(os.environ)
_ORIGINAL_ENV_GETITEM = _ENVIRON_CLASS.__getitem__
_ORIGINAL_ENV_GET = _ENVIRON_CLASS.get
_ORIGINAL_ENV_SETITEM = _ENVIRON_CLASS.__setitem__
_ORIGINAL_ENV_SETDEFAULT = _ENVIRON_CLASS.setdefault
_ORIGINAL_ENV_UPDATE = _ENVIRON_CLASS.update
_ORIGINAL_ENV_DELITEM = _ENVIRON_CLASS.__delitem__
_ORIGINAL_ENV_POP = _ENVIRON_CLASS.pop
_ORIGINAL_ENV_POPITEM = _ENVIRON_CLASS.popitem
_ORIGINAL_ENV_CLEAR = _ENVIRON_CLASS.clear


def _fatal(detail: str) -> "None":
    """Terminate instead of relying on sitecustomize's non-fatal import errors."""

    try:
        raw = f"F017_SEQUENCE42_BARRIER_BOOTSTRAP_FAILURE:{detail}\n".encode(
            "ascii", "backslashreplace"
        )
        _ORIGINAL_OS_WRITE(2, raw)
    finally:
        _ORIGINAL_OS_EXIT(96)


def _literal_path_value(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or len(node.args) != 1 or node.keywords:
        return None
    if not isinstance(node.func, ast.Name) or node.func.id != "Path":
        return None
    value = node.args[0]
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _required_decimal_environment(name: str) -> int:
    value = _ORIGINAL_ENV_GETITEM(os.environ, name)
    if not value or not value.isascii() or not value.isdecimal():
        raise RuntimeError(f"F017_SEQUENCE42_BARRIER_ENVIRONMENT:{name}")
    return int(value)


def _required_environment(name: str) -> str:
    value = _ORIGINAL_ENV_GETITEM(os.environ, name)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"F017_SEQUENCE42_BARRIER_ENVIRONMENT:{name}")
    return value


def _load_roots() -> tuple[str, str]:
    if not _SOURCE_FILE:
        raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_REQUIRED")
    source_path = Path(_SOURCE_FILE)
    if (
        not source_path.is_absolute()
        or Path(os.path.normpath(_SOURCE_FILE)) != source_path
        or _SOURCE_FILE.startswith("//")
    ):
        raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_PATH")
    expected_sha = _required_environment("F017_SEQUENCE42_SOURCE_SHA256")
    if len(expected_sha) != 64 or any(item not in _HEX64 for item in expected_sha):
        raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_SHA256")
    expected_identity = (
        _required_decimal_environment("F017_SEQUENCE42_SOURCE_DEVICE"),
        _required_decimal_environment("F017_SEQUENCE42_SOURCE_INODE"),
        _required_decimal_environment("F017_SEQUENCE42_SOURCE_SIZE"),
        _required_decimal_environment("F017_SEQUENCE42_SOURCE_MTIME_NS"),
        _required_decimal_environment("F017_SEQUENCE42_SOURCE_CTIME_NS"),
    )
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = _ORIGINAL_OS_OPEN(_SOURCE_FILE, flags)
    try:
        before = _ORIGINAL_OS_FSTAT(descriptor)
        observed_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if (
            observed_identity != expected_identity
            or not _stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAXIMUM_SOURCE_BYTES
        ):
            raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_IDENTITY")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = _ORIGINAL_OS_READ(descriptor, min(65_536, remaining))
            if not chunk:
                raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_SHORT_READ")
            chunks.append(chunk)
            remaining -= len(chunk)
        if _ORIGINAL_OS_READ(descriptor, 1):
            raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_EXCESS_BYTES")
        after = _ORIGINAL_OS_FSTAT(descriptor)
        canonical = _ORIGINAL_OS_STAT(_SOURCE_FILE, follow_symlinks=False)
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            after_identity != expected_identity
            or (canonical.st_dev, canonical.st_ino) != expected_identity[:2]
        ):
            raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_CHANGED")
        raw = b"".join(chunks)
    finally:
        _ORIGINAL_OS_CLOSE(descriptor)
    if _hashlib_module.sha256(raw).hexdigest() != expected_sha:
        raise RuntimeError("F017_SEQUENCE42_BARRIER_SOURCE_DIGEST")
    tree = ast.parse(raw, filename=_SOURCE_FILE)
    found: dict[str, str] = {}
    for node in tree.body:
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        if isinstance(target, ast.Name) and target.id in {
            "_LIVE_PACKAGE_PARENT",
            "_LIVE_CHECKPOINT_ROOT",
        }:
            if target.id in found:
                raise RuntimeError(f"F017_SEQUENCE42_BARRIER_DUPLICATE:{target.id}")
            literal = _literal_path_value(value) if value is not None else None
            if literal is None:
                raise RuntimeError(f"F017_SEQUENCE42_BARRIER_NONLITERAL:{target.id}")
            found[target.id] = literal
    required = ("_LIVE_PACKAGE_PARENT", "_LIVE_CHECKPOINT_ROOT")
    if tuple(name for name in required if name in found) != required:
        raise RuntimeError("F017_SEQUENCE42_BARRIER_ROOT_CENSUS")
    roots = tuple(found[name] for name in required)
    if len(set(roots)) != 2 or any(not os.path.isabs(item) for item in roots):
        raise RuntimeError("F017_SEQUENCE42_BARRIER_ROOT_GEOMETRY")
    return roots  # type: ignore[return-value]


try:
    _LIVE_ROOTS = _load_roots()
except BaseException as _bootstrap_error:
    _fatal(f"source:{type(_bootstrap_error).__name__}:{_bootstrap_error}")
_LIVE_ROOT_KEYS = tuple(
    unicodedata.normalize("NFC", os.path.normpath(root)).casefold()
    for root in _LIVE_ROOTS
)


def _open_log_descriptor() -> int | None:
    if not _LOG:
        raise RuntimeError("F017_SEQUENCE42_BARRIER_LOG_REQUIRED")
    log_path = Path(_LOG)
    if (
        not log_path.is_absolute()
        or Path(os.path.normpath(_LOG)) != log_path
        or _LOG.startswith("//")
    ):
        raise RuntimeError("F017_SEQUENCE42_BARRIER_LOG_PATH")
    expected_identity = (
        _required_decimal_environment("F017_SEQUENCE42_BARRIER_LOG_DEVICE"),
        _required_decimal_environment("F017_SEQUENCE42_BARRIER_LOG_INODE"),
    )
    flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = _ORIGINAL_OS_OPEN(_LOG, flags)
    observed = _ORIGINAL_OS_FSTAT(fd)
    try:
        canonical = _ORIGINAL_OS_STAT(_LOG, follow_symlinks=False)
        if (
            not _stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or observed.st_uid != os.getuid()
            or _stat.S_IMODE(observed.st_mode) != 0o600
            or observed.st_size > _MAXIMUM_LOG_BYTES
            or (observed.st_dev, observed.st_ino) != expected_identity
            or (canonical.st_dev, canonical.st_ino) != expected_identity
        ):
            raise RuntimeError("F017_SEQUENCE42_BARRIER_LOG_IDENTITY")
    except BaseException:
        _ORIGINAL_OS_CLOSE(fd)
        raise
    return fd


try:
    _LOG_FD = _open_log_descriptor()
except BaseException as _bootstrap_error:
    _fatal(f"log:{type(_bootstrap_error).__name__}:{_bootstrap_error}")

try:
    _BARRIER_ENV_VALUES = {
        name: _required_environment(name) for name in _BARRIER_ENV_KEYS
    }
    _ROOT_TOKEN = _required_environment("F017_SEQUENCE42_BARRIER_TOKEN")
    _pythonpath_entries = tuple(
        item
        for item in _required_environment("PYTHONPATH").split(os.pathsep)
        if item
    )
    if not _pythonpath_entries or _pythonpath_entries[0] != _BARRIER_DIR:
        raise RuntimeError("F017_SEQUENCE42_BARRIER_PYTHONPATH")
except BaseException as _bootstrap_error:
    _fatal(f"environment:{type(_bootstrap_error).__name__}:{_bootstrap_error}")

_PROTECTED_ENV_KEYS = frozenset(
    (*_BARRIER_ENV_KEYS, "F017_SEQUENCE42_BARRIER_TOKEN")
)
_SPAWN_LOCK = threading.Lock()
_SPAWN_COUNTER = 0
_ISSUED_CHILD_TOKENS: set[str] = set()


def _append(event: dict[str, object]) -> None:
    if _LOG_FD is None:
        raise RuntimeError("F017_SEQUENCE42_BARRIER_LOG_UNAVAILABLE")
    raw = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with _LOCK:
        if _ORIGINAL_OS_WRITE(_LOG_FD, raw) != len(raw):
            raise OSError("F017_SEQUENCE42_BARRIER_LOG_SHORT_WRITE")
        _ORIGINAL_OS_FSYNC(_LOG_FD)


def _fd_path(fd: int) -> str | None:
    try:
        return _ORIGINAL_OS_READLINK(f"/dev/fd/{fd}")
    except OSError:
        return None


def _raw_candidate(value: object, dir_fd: int | None = None) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return _fd_path(value)
    try:
        raw = os.fspath(value)
    except TypeError:
        return None
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if not isinstance(raw, str):
        return None
    if dir_fd is not None and not os.path.isabs(raw):
        parent = _fd_path(dir_fd)
        if parent is not None:
            raw = os.path.join(parent, raw)
    expanded = os.path.expanduser(raw)
    if expanded.startswith(os.sep):
        return os.sep + expanded.lstrip(os.sep)
    return os.path.join(os.getcwd(), expanded)


def _names_live(candidate: str | None) -> bool:
    if candidate is None:
        return False
    key = unicodedata.normalize("NFC", os.path.normpath(candidate)).casefold()
    return any(key == root or key.startswith(root + os.sep) for root in _LIVE_ROOT_KEYS)


def _is_live(value: object, dir_fd: int | None = None) -> bool:
    raw_candidate = _raw_candidate(value, dir_fd)
    candidate = None if raw_candidate is None else os.path.normpath(raw_candidate)
    if _names_live(candidate):
        return True
    if candidate is None or raw_candidate is None:
        return False
    pending = raw_candidate.split(os.sep)[1:]
    resolved_parts: list[str] = []
    symlink_hops = 0
    while pending:
        component = pending.pop(0)
        if component in {"", "."}:
            continue
        if component == "..":
            if resolved_parts:
                resolved_parts.pop()
            if _names_live(os.sep + os.sep.join(resolved_parts)):
                return True
            continue
        current = os.sep + os.sep.join([*resolved_parts, component])
        if _names_live(current):
            return True
        try:
            observed = _ORIGINAL_OS_LSTAT(current)
        except OSError:
            return False
        if not _stat.S_ISLNK(observed.st_mode):
            resolved_parts.append(component)
            continue
        symlink_hops += 1
        if symlink_hops > 40:
            return False
        try:
            target = _ORIGINAL_OS_READLINK(current)
        except OSError:
            return False
        if os.path.isabs(target):
            resolved_parts = []
            target_parts = target.split(os.sep)[1:]
        else:
            target_parts = target.split(os.sep)
        pending = [*target_parts, *pending]
    return _names_live(os.sep + os.sep.join(resolved_parts))


def _blocked(operation: str) -> RuntimeError:
    _append(
        {
            "event": "BLOCKED_ACCESS",
            "operation": operation,
            "path_class": "LIVE_EVENT06_AUTHORITY_ROOT_OR_DESCENDANT",
            "pid": os.getpid(),
        }
    )
    return RuntimeError(f"F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:{operation}")


def _guard(operation: str, value: object, dir_fd: int | None = None) -> None:
    if _is_live(value, dir_fd):
        raise _blocked(operation)


def _guard_fd(operation: str, fd: int) -> None:
    if _is_live(fd):
        raise _blocked(operation)


def _os_open(path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
    _guard("os.open", path, dir_fd)
    return _ORIGINAL_OS_OPEN(path, flags, mode, dir_fd=dir_fd)


def _os_stat(path: object, *, dir_fd: int | None = None, follow_symlinks: bool = True):
    _guard("os.stat", path, dir_fd)
    return _ORIGINAL_OS_STAT(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)


def _os_lstat(path: object, *, dir_fd: int | None = None):
    _guard("os.lstat", path, dir_fd)
    return _ORIGINAL_OS_LSTAT(path, dir_fd=dir_fd)


def _os_fstat(fd: int):
    _guard_fd("os.fstat", fd)
    return _ORIGINAL_OS_FSTAT(fd)


def _os_fdopen(fd: int, *args: object, **kwargs: object):
    _guard_fd("os.fdopen", fd)
    return _ORIGINAL_OS_FDOPEN(fd, *args, **kwargs)


def _os_listdir(path: object = "."):
    _guard("os.listdir", path)
    return _ORIGINAL_OS_LISTDIR(path)


def _os_scandir(path: object = "."):
    _guard("os.scandir", path)
    return _ORIGINAL_OS_SCANDIR(path)


def _os_readlink(path: object, *, dir_fd: int | None = None):
    _guard("os.readlink", path, dir_fd)
    return _ORIGINAL_OS_READLINK(path, dir_fd=dir_fd)


def _os_chdir(path: object) -> None:
    _guard("os.chdir", path)
    return _ORIGINAL_OS_CHDIR(path)


def _os_access(path: object, mode: int, *, dir_fd: int | None = None, effective_ids: bool = False, follow_symlinks: bool = True):
    _guard("os.access", path, dir_fd)
    return _ORIGINAL_OS_ACCESS(path, mode, dir_fd=dir_fd, effective_ids=effective_ids, follow_symlinks=follow_symlinks)


def _os_chmod(path: object, mode: int, *, dir_fd: int | None = None, follow_symlinks: bool = True):
    _guard("os.chmod", path, dir_fd)
    return _ORIGINAL_OS_CHMOD(path, mode, dir_fd=dir_fd, follow_symlinks=follow_symlinks)


def _os_chown(path: object, uid: int, gid: int, *, dir_fd: int | None = None, follow_symlinks: bool = True):
    _guard("os.chown", path, dir_fd)
    return _ORIGINAL_OS_CHOWN(path, uid, gid, dir_fd=dir_fd, follow_symlinks=follow_symlinks)


def _os_remove(path: object, *, dir_fd: int | None = None):
    _guard("os.remove", path, dir_fd)
    return _ORIGINAL_OS_REMOVE(path, dir_fd=dir_fd)


def _os_unlink(path: object, *, dir_fd: int | None = None):
    _guard("os.unlink", path, dir_fd)
    return _ORIGINAL_OS_UNLINK(path, dir_fd=dir_fd)


def _os_rename(src: object, dst: object, *, src_dir_fd: int | None = None, dst_dir_fd: int | None = None):
    _guard("os.rename.src", src, src_dir_fd)
    _guard("os.rename.dst", dst, dst_dir_fd)
    return _ORIGINAL_OS_RENAME(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)


def _os_replace(src: object, dst: object, *, src_dir_fd: int | None = None, dst_dir_fd: int | None = None):
    _guard("os.replace.src", src, src_dir_fd)
    _guard("os.replace.dst", dst, dst_dir_fd)
    return _ORIGINAL_OS_REPLACE(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)


def _os_mkdir(path: object, mode: int = 0o777, *, dir_fd: int | None = None):
    _guard("os.mkdir", path, dir_fd)
    return _ORIGINAL_OS_MKDIR(path, mode, dir_fd=dir_fd)


def _os_rmdir(path: object, *, dir_fd: int | None = None):
    _guard("os.rmdir", path, dir_fd)
    return _ORIGINAL_OS_RMDIR(path, dir_fd=dir_fd)


def _os_read(fd: int, length: int) -> bytes:
    _guard_fd("os.read", fd)
    return _ORIGINAL_OS_READ(fd, length)


def _os_write(fd: int, data: object) -> int:
    _guard_fd("os.write", fd)
    return _ORIGINAL_OS_WRITE(fd, data)


def _os_pread(fd: int, length: int, offset: int) -> bytes:
    _guard_fd("os.pread", fd)
    assert _ORIGINAL_OS_PREAD is not None
    return _ORIGINAL_OS_PREAD(fd, length, offset)


def _os_pwrite(fd: int, data: object, offset: int) -> int:
    _guard_fd("os.pwrite", fd)
    assert _ORIGINAL_OS_PWRITE is not None
    return _ORIGINAL_OS_PWRITE(fd, data, offset)


def _os_fsync(fd: int) -> None:
    _guard_fd("os.fsync", fd)
    return _ORIGINAL_OS_FSYNC(fd)


def _os_ftruncate(fd: int, length: int) -> None:
    _guard_fd("os.ftruncate", fd)
    return _ORIGINAL_OS_FTRUNCATE(fd, length)


def _os_fchmod(fd: int, mode: int) -> None:
    _guard_fd("os.fchmod", fd)
    return _ORIGINAL_OS_FCHMOD(fd, mode)


def _os_lseek(fd: int, position: int, how: int) -> int:
    _guard_fd("os.lseek", fd)
    return _ORIGINAL_OS_LSEEK(fd, position, how)


def _os_readv(fd: int, buffers: object) -> int:
    _guard_fd("os.readv", fd)
    assert _ORIGINAL_OS_READV is not None
    return _ORIGINAL_OS_READV(fd, buffers)


def _os_writev(fd: int, buffers: object) -> int:
    _guard_fd("os.writev", fd)
    assert _ORIGINAL_OS_WRITEV is not None
    return _ORIGINAL_OS_WRITEV(fd, buffers)


def _os_link(src: object, dst: object, *, src_dir_fd: int | None = None, dst_dir_fd: int | None = None, follow_symlinks: bool = True):
    _guard("os.link.src", src, src_dir_fd)
    _guard("os.link.dst", dst, dst_dir_fd)
    return _ORIGINAL_OS_LINK(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd, follow_symlinks=follow_symlinks)


def _os_symlink(src: object, dst: object, target_is_directory: bool = False, *, dir_fd: int | None = None):
    _guard("os.symlink.src", src)
    _guard("os.symlink.dst", dst, dir_fd)
    return _ORIGINAL_OS_SYMLINK(src, dst, target_is_directory, dir_fd=dir_fd)


def _os_truncate(path: object, length: int) -> None:
    if isinstance(path, int) and not isinstance(path, bool):
        _guard_fd("os.truncate", path)
    else:
        _guard("os.truncate", path)
    return _ORIGINAL_OS_TRUNCATE(path, length)


def _os_utime(path: object, *args: object, dir_fd: int | None = None, follow_symlinks: bool = True, **kwargs: object):
    _guard("os.utime", path, dir_fd)
    return _ORIGINAL_OS_UTIME(path, *args, dir_fd=dir_fd, follow_symlinks=follow_symlinks, **kwargs)


def _os_statvfs(path: object):
    _guard("os.statvfs", path)
    return _ORIGINAL_OS_STATVFS(path)


def _environment_key(value: object) -> str | None:
    try:
        raw = os.fspath(value)
    except TypeError:
        return None
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    return raw if isinstance(raw, str) else None


def _policy_violation(operation: str, detail: str) -> RuntimeError:
    _append(
        {
            "detail": detail,
            "event": "BARRIER_POLICY_VIOLATION",
            "operation": operation,
            "pid": os.getpid(),
            "token": _ROOT_TOKEN,
        }
    )
    return RuntimeError(f"F017_SEQUENCE42_PROCESS_POLICY_BLOCKED:{operation}:{detail}")


def _os_putenv(key: object, value: object) -> None:
    name = _environment_key(key)
    if name in _PROTECTED_ENV_KEYS:
        expected = (
            _ROOT_TOKEN
            if name == "F017_SEQUENCE42_BARRIER_TOKEN"
            else _BARRIER_ENV_VALUES[name]
        )
        supplied = _environment_key(value)
        if supplied != expected:
            raise _policy_violation("os.putenv", "barrier-environment-mutation")
    if _contains_live(key) or _contains_live(value):
        raise _blocked("os.putenv")
    return _ORIGINAL_OS_PUTENV(key, value)


def _os_unsetenv(key: object) -> None:
    if _environment_key(key) in _PROTECTED_ENV_KEYS:
        raise _policy_violation("os.unsetenv", "barrier-environment-removal")
    if _contains_live(key):
        raise _blocked("os.unsetenv")
    return _ORIGINAL_OS_UNSETENV(key)


def _os_system(command: object) -> int:
    del command
    raise _policy_violation("os.system", "shell-child-prohibited")


def _os_fork() -> int:
    raise _policy_violation("os.fork", "untracked-fork-prohibited")


def _os_forkpty() -> tuple[int, int]:
    raise _policy_violation("os.forkpty", "untracked-fork-prohibited")


def _argument_text(value: object) -> str:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise _policy_violation("process.argv", "non-path-argument") from exc
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if not isinstance(raw, str) or "\x00" in raw:
        raise _policy_violation("process.argv", "invalid-argument")
    return raw


def _argv_tuple(argv: object) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes, os.PathLike)):
        raise _policy_violation("process.argv", "sequence-required")
    try:
        values = tuple(_argument_text(item) for item in argv)  # type: ignore[union-attr]
    except TypeError as exc:
        raise _policy_violation("process.argv", "sequence-required") from exc
    if not values:
        raise _policy_violation("process.argv", "empty")
    return values


def _validate_python_child(
    operation: str,
    executable: object,
    argv: object,
    *,
    shell: bool = False,
) -> tuple[str, tuple[str, ...]]:
    if shell:
        raise _policy_violation(operation, "shell-child-prohibited")
    executable_text = _argument_text(executable)
    if (
        not os.path.isabs(executable_text)
        or os.path.normpath(executable_text) != os.path.normpath(sys.executable)
    ):
        raise _policy_violation(operation, "native-or-unpinned-child-prohibited")
    values = _argv_tuple(argv)
    for value in values[1:]:
        if value in {"-c", "-m", "--"} or not value.startswith("-"):
            break
        if value.startswith("--"):
            continue
        flags = value[1:]
        if any(flag in _BYPASS_FLAGS for flag in flags):
            raise _policy_violation(operation, "site-startup-bypass-flag")
    return executable_text, values


def _is_pinned_python_executable(executable: object) -> bool:
    """Return whether an executable names this exact supervised interpreter."""

    try:
        executable_text = _argument_text(executable)
    except RuntimeError:
        return False
    return (
        os.path.isabs(executable_text)
        and os.path.normpath(executable_text) == os.path.normpath(sys.executable)
    )


def _validate_source_free_native_child(
    operation: str,
    executable: object,
    argv: object,
    *,
    shell: bool,
    explicit_executable: bool,
    explicit_environment: bool,
    pass_fds: object,
) -> tuple[str, tuple[str, ...]]:
    """Admit a bounded system utility without claiming Python startup coverage.

    Native utilities cannot import this startup hook. They are therefore
    admitted only as observed system children: the executable is an absolute
    root-owned platform binary, command chaining is rejected, and the caller
    cannot substitute an environment, executable, or inherited descriptor set.
    The common live-root guard has already checked every argument and cwd.
    """

    if shell:
        raise _policy_violation(operation, "shell-child-prohibited")
    if explicit_executable:
        raise _policy_violation(operation, "native-executable-override-prohibited")
    if explicit_environment:
        raise _policy_violation(operation, "native-environment-override-prohibited")
    try:
        inherited_descriptors = tuple(pass_fds)  # type: ignore[arg-type]
    except TypeError as exc:
        raise _policy_violation(operation, "invalid-pass-fds") from exc
    if inherited_descriptors:
        raise _policy_violation(operation, "native-pass-fds-prohibited")

    executable_text = _argument_text(executable)
    values = _argv_tuple(argv)
    if (
        not os.path.isabs(executable_text)
        or os.path.normpath(executable_text) != executable_text
        or values[0] != executable_text
        or os.path.dirname(executable_text) not in _TRUSTED_NATIVE_PARENTS
        or os.path.basename(executable_text) in _PROHIBITED_NATIVE_EXECUTABLES
        or any(value in _PROHIBITED_NATIVE_ARGUMENTS for value in values[1:])
    ):
        raise _policy_violation(operation, "unsafe-native-child-prohibited")
    observed = _ORIGINAL_OS_LSTAT(executable_text)
    if (
        not _stat.S_ISREG(observed.st_mode)
        or observed.st_uid != 0
        or observed.st_mode & (_stat.S_IWGRP | _stat.S_IWOTH)
    ):
        raise _policy_violation(operation, "untrusted-native-executable")
    return executable_text, values


def _record_native_subprocess(
    operation: str,
    executable: str,
    argv: tuple[str, ...],
    child_pid: int,
) -> None:
    _append(
        {
            "argument_count": len(argv),
            "child_pid": child_pid,
            "event": "NATIVE_SUBPROCESS_OBSERVED",
            "executable": executable,
            "operation": operation,
            "pid": os.getpid(),
            "source_free_from_live_roots": True,
            "token": _ROOT_TOKEN,
        }
    )


def _next_spawn_token(operation: str) -> str:
    global _SPAWN_COUNTER
    with _SPAWN_LOCK:
        _SPAWN_COUNTER += 1
        counter = _SPAWN_COUNTER
    material = (
        f"{_ROOT_TOKEN}:{os.getpid()}:{threading.get_ident()}:"
        f"{time.monotonic_ns()}:{counter}:{operation}"
    ).encode()
    return f"child-{_hashlib_module.sha256(material).hexdigest()}"


def _child_environment(
    operation: str,
    environment: object,
    *,
    existing_token: str | None = None,
) -> tuple[dict[str, str], str]:
    try:
        supplied = dict(os.environ if environment is None else environment)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise _policy_violation(operation, "invalid-environment") from exc
    if _contains_live(supplied):
        raise _blocked(operation)
    child: dict[str, str] = {}
    for key, value in supplied.items():
        key_text = _argument_text(key)
        value_text = _argument_text(value)
        child[key_text] = value_text
    child.update(_BARRIER_ENV_VALUES)
    entries = [item for item in child.get("PYTHONPATH", "").split(os.pathsep) if item]
    entries = [item for item in entries if item != _BARRIER_DIR]
    child["PYTHONPATH"] = os.pathsep.join([_BARRIER_DIR, *entries])
    child["PYTHONDONTWRITEBYTECODE"] = "1"
    token = existing_token or _next_spawn_token(operation)
    child["F017_SEQUENCE42_BARRIER_TOKEN"] = token
    return child, token


def _record_spawn_intent(operation: str, token: str) -> None:
    with _SPAWN_LOCK:
        if token in _ISSUED_CHILD_TOKENS:
            return
        _ISSUED_CHILD_TOKENS.add(token)
    _append(
        {
            "event": "SPAWN_INTENT",
            "operation": operation,
            "pid": os.getpid(),
            "token": token,
        }
    )


def _guard_exec(operation: str, path: object, argv: object, env: object = None) -> tuple[tuple[str, ...], dict[str, str]]:
    if _contains_live(path) or _contains_live(argv) or _contains_live(env):
        raise _blocked(operation)
    _executable, values = _validate_python_child(operation, path, argv)
    existing_token = None
    if isinstance(env, dict):
        candidate = env.get("F017_SEQUENCE42_BARRIER_TOKEN")
        if isinstance(candidate, str) and candidate in _ISSUED_CHILD_TOKENS:
            existing_token = candidate
    child, token = _child_environment(
        operation, env, existing_token=existing_token
    )
    _record_spawn_intent(operation, token)
    return values, child


def _os_execv(path: object, argv: object):
    values, child = _guard_exec("os.execv", path, argv, os.environ)
    return _ORIGINAL_OS_EXECVE(path, values, child)


def _os_execve(path: object, argv: object, env: object):
    values, child = _guard_exec("os.execve", path, argv, env)
    return _ORIGINAL_OS_EXECVE(path, values, child)


def _os_execl(path: object, *args: object):
    values, child = _guard_exec("os.execl", path, args, os.environ)
    return _ORIGINAL_OS_EXECVE(path, values, child)


def _os_execlp(file: object, *args: object):
    values, child = _guard_exec("os.execlp", file, args, os.environ)
    return _ORIGINAL_OS_EXECVE(file, values, child)


def _os_execlpe(file: object, *args: object):
    if len(args) < 1:
        raise _policy_violation("os.execlpe", "missing-environment")
    values, child = _guard_exec("os.execlpe", file, args[:-1], args[-1])
    return _ORIGINAL_OS_EXECVE(file, values, child)


def _os_execvp(file: object, args: object):
    values, child = _guard_exec("os.execvp", file, args, os.environ)
    return _ORIGINAL_OS_EXECVE(file, values, child)


def _os_execvpe(file: object, args: object, env: object):
    values, child = _guard_exec("os.execvpe", file, args, env)
    return _ORIGINAL_OS_EXECVE(file, values, child)


def _spawn_environment(operation: str, path: object, argv: object, env: object) -> tuple[tuple[str, ...], dict[str, str]]:
    if _contains_live(path) or _contains_live(argv) or _contains_live(env):
        raise _blocked(operation)
    _executable, values = _validate_python_child(operation, path, argv)
    existing_token = None
    if isinstance(env, dict):
        candidate = env.get("F017_SEQUENCE42_BARRIER_TOKEN")
        if isinstance(candidate, str) and candidate in _ISSUED_CHILD_TOKENS:
            existing_token = candidate
    child, token = _child_environment(operation, env, existing_token=existing_token)
    _record_spawn_intent(operation, token)
    return values, child


def _os_posix_spawn(path: object, argv: object, env: object, **kwargs: object):
    if _contains_live(kwargs):
        raise _blocked("os.posix_spawn")
    values, child = _spawn_environment("os.posix_spawn", path, argv, env)
    assert _ORIGINAL_OS_POSIX_SPAWN is not None
    return _ORIGINAL_OS_POSIX_SPAWN(path, values, child, **kwargs)


def _os_posix_spawnp(path: object, argv: object, env: object, **kwargs: object):
    if _contains_live(kwargs):
        raise _blocked("os.posix_spawnp")
    values, child = _spawn_environment("os.posix_spawnp", path, argv, env)
    assert _ORIGINAL_OS_POSIX_SPAWNP is not None
    return _ORIGINAL_OS_POSIX_SPAWNP(path, values, child, **kwargs)


def _spawn_python_process(
    operation: str,
    mode: int,
    path: object,
    argv: tuple[str, ...],
    environment: dict[str, str],
) -> int:
    if _ORIGINAL_OS_POSIX_SPAWN is None:
        raise _policy_violation(operation, "tracked-posix-spawn-unavailable")
    if type(mode) is not int or mode not in {os.P_WAIT, os.P_NOWAIT}:
        raise _policy_violation(operation, "unsupported-spawn-mode")
    pid = _ORIGINAL_OS_POSIX_SPAWN(path, argv, environment)
    if mode == os.P_NOWAIT:
        return pid
    _waited_pid, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


def _os_spawnv(mode: int, path: object, argv: object):
    values, child = _spawn_environment("os.spawnv", path, argv, os.environ)
    return _spawn_python_process("os.spawnv", mode, path, values, child)


def _os_spawnve(mode: int, path: object, argv: object, env: object):
    values, child = _spawn_environment("os.spawnve", path, argv, env)
    return _spawn_python_process("os.spawnve", mode, path, values, child)


def _os_spawnvp(mode: int, file: object, argv: object):
    values, child = _spawn_environment("os.spawnvp", file, argv, os.environ)
    return _spawn_python_process("os.spawnvp", mode, file, values, child)


def _os_spawnvpe(mode: int, file: object, argv: object, env: object):
    values, child = _spawn_environment("os.spawnvpe", file, argv, env)
    return _spawn_python_process("os.spawnvpe", mode, file, values, child)


def _os_spawnl(mode: int, path: object, *args: object):
    return _os_spawnv(mode, path, args)


def _os_spawnle(mode: int, path: object, *args: object):
    if not args:
        raise _policy_violation("os.spawnle", "missing-environment")
    return _os_spawnve(mode, path, args[:-1], args[-1])


def _os_spawnlp(mode: int, file: object, *args: object):
    return _os_spawnvp(mode, file, args)


def _os_spawnlpe(mode: int, file: object, *args: object):
    if not args:
        raise _policy_violation("os.spawnlpe", "missing-environment")
    return _os_spawnvpe(mode, file, args[:-1], args[-1])


def _realpath(path: object, *, strict: bool = False):
    _guard("os.path.realpath", path)
    try:
        result = _ORIGINAL_REALPATH(path, strict=strict)
    except TypeError:
        result = _ORIGINAL_REALPATH(path)
    _guard("os.path.realpath.result", result)
    return result


def _builtin_open(file: object, *args: object, **kwargs: object):
    _guard("builtins.open", file)
    return _ORIGINAL_BUILTIN_OPEN(file, *args, **kwargs)


def _io_open(file: object, *args: object, **kwargs: object):
    _guard("io.open", file)
    return _ORIGINAL_IO_OPEN(file, *args, **kwargs)


def _path_resolve(self: Path, strict: bool = False) -> Path:
    _guard("Path.resolve", self)
    result = _ORIGINAL_PATH_RESOLVE(self, strict=strict)
    _guard("Path.resolve.result", result)
    return result


def _path_stat(self: Path, *, follow_symlinks: bool = True):
    _guard("Path.stat", self)
    return _ORIGINAL_PATH_STAT(self, follow_symlinks=follow_symlinks)


def _path_lstat(self: Path):
    _guard("Path.lstat", self)
    return _ORIGINAL_PATH_LSTAT(self)


def _path_open(self: Path, *args: object, **kwargs: object):
    _guard("Path.open", self)
    return _ORIGINAL_PATH_OPEN(self, *args, **kwargs)


def _path_read_bytes(self: Path) -> bytes:
    _guard("Path.read_bytes", self)
    return _ORIGINAL_PATH_READ_BYTES(self)


def _path_read_text(self: Path, *args: object, **kwargs: object) -> str:
    _guard("Path.read_text", self)
    return _ORIGINAL_PATH_READ_TEXT(self, *args, **kwargs)


def _path_write_bytes(self: Path, data: bytes) -> int:
    _guard("Path.write_bytes", self)
    return _ORIGINAL_PATH_WRITE_BYTES(self, data)


def _path_write_text(self: Path, data: str, *args: object, **kwargs: object) -> int:
    _guard("Path.write_text", self)
    return _ORIGINAL_PATH_WRITE_TEXT(self, data, *args, **kwargs)


def _path_iterdir(self: Path):
    _guard("Path.iterdir", self)
    return _ORIGINAL_PATH_ITERDIR(self)


def _path_glob(self: Path, pattern: str, *args: object, **kwargs: object):
    _guard("Path.glob", self / pattern)
    return _ORIGINAL_PATH_GLOB(self, pattern, *args, **kwargs)


def _path_rglob(self: Path, pattern: str, *args: object, **kwargs: object):
    _guard("Path.rglob", self / pattern)
    return _ORIGINAL_PATH_RGLOB(self, pattern, *args, **kwargs)


def _mmap(fileno: int, *args: object, **kwargs: object):
    if fileno >= 0:
        _guard_fd("mmap.mmap", fileno)
    return _ORIGINAL_MMAP(fileno, *args, **kwargs)


def _file_digest(fileobj: object, digest: object, /, *, _bufsize: int = 2**18):
    try:
        fd = fileobj.fileno()  # type: ignore[attr-defined]
    except (AttributeError, OSError, ValueError):
        fd = None
    if isinstance(fd, int):
        _guard_fd("hashlib.file_digest", fd)
    assert _ORIGINAL_FILE_DIGEST is not None
    return _ORIGINAL_FILE_DIGEST(fileobj, digest, _bufsize=_bufsize)


def _contains_live(value: object) -> bool:
    if isinstance(value, (str, bytes, os.PathLike)):
        if _is_live(value):
            return True
        try:
            text = os.fsdecode(os.fspath(value))
        except (TypeError, ValueError):
            return False
        normalized = unicodedata.normalize("NFC", text).casefold()
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        if any(root in normalized for root in _LIVE_ROOT_KEYS):
            return True
        try:
            tokens = shlex.split(text)
        except ValueError:
            tokens = []
        return len(tokens) > 1 and any(_is_live(token) for token in tokens)
    if isinstance(value, dict):
        return any(_contains_live(key) or _contains_live(item) for key, item in value.items())
    if isinstance(value, (tuple, list)):
        return any(_contains_live(item) for item in value)
    return False


class _GuardedPopen(_ORIGINAL_POPEN):
    def __init__(self, args: object, *popen_args: object, **popen_kwargs: object) -> None:
        if (
            _contains_live(args)
            or _contains_live(popen_kwargs.get("cwd"))
            or _contains_live(popen_kwargs.get("env"))
            or _contains_live(popen_kwargs.get("executable"))
        ):
            raise _blocked("subprocess.Popen")
        if popen_kwargs.get("preexec_fn") is not None:
            raise _policy_violation(
                "subprocess.Popen", "preexec-callback-prohibited"
            )
        for name in ("stdin", "stdout", "stderr"):
            candidate_fd = popen_kwargs.get(name)
            if isinstance(candidate_fd, int) and candidate_fd >= 0:
                _guard_fd(f"subprocess.Popen.{name}", candidate_fd)
        for candidate_fd in popen_kwargs.get("pass_fds", ()):
            if isinstance(candidate_fd, int) and candidate_fd >= 0:
                _guard_fd("subprocess.Popen.pass_fds", candidate_fd)
        executable = popen_kwargs.get("executable")
        values = _argv_tuple(args)
        actual_executable: object = values[0] if executable is None else executable
        if _is_pinned_python_executable(actual_executable):
            _validate_python_child(
                "subprocess.Popen",
                actual_executable,
                values,
                shell=bool(popen_kwargs.get("shell", False)),
            )
            child_environment, token = _child_environment(
                "subprocess.Popen", popen_kwargs.get("env")
            )
            _record_spawn_intent("subprocess.Popen", token)
            popen_kwargs["env"] = child_environment
            super().__init__(values, *popen_args, **popen_kwargs)
            return

        native_executable, values = _validate_source_free_native_child(
            "subprocess.Popen",
            actual_executable,
            values,
            shell=bool(popen_kwargs.get("shell", False)),
            explicit_executable=executable is not None,
            explicit_environment=popen_kwargs.get("env") is not None,
            pass_fds=popen_kwargs.get("pass_fds", ()),
        )
        super().__init__(values, *popen_args, **popen_kwargs)
        _record_native_subprocess(
            "subprocess.Popen", native_executable, values, self.pid
        )


def _getenv(key: str, default: object = None):
    value = _ORIGINAL_GETENV(key, default)
    if _contains_live(value):
        raise _blocked("os.getenv")
    return value


def _environ_getitem(self: object, key: object):
    value = _ORIGINAL_ENV_GETITEM(self, key)
    if _contains_live(value):
        raise _blocked("os.environ.__getitem__")
    return value


def _environ_get(self: object, key: object, default: object = None):
    value = _ORIGINAL_ENV_GET(self, key, default)
    if _contains_live(value):
        raise _blocked("os.environ.get")
    return value


def _environ_setitem(self: object, key: object, value: object) -> None:
    name = _environment_key(key)
    if name in _PROTECTED_ENV_KEYS:
        expected = (
            _ROOT_TOKEN
            if name == "F017_SEQUENCE42_BARRIER_TOKEN"
            else _BARRIER_ENV_VALUES[name]
        )
        if _environment_key(value) != expected:
            raise _policy_violation(
                "os.environ.__setitem__", "barrier-environment-mutation"
            )
    if _contains_live(key) or _contains_live(value):
        raise _blocked("os.environ.__setitem__")
    return _ORIGINAL_ENV_SETITEM(self, key, value)


def _environ_setdefault(self: object, key: object, default: object = None):
    name = _environment_key(key)
    if name in _PROTECTED_ENV_KEYS:
        expected = (
            _ROOT_TOKEN
            if name == "F017_SEQUENCE42_BARRIER_TOKEN"
            else _BARRIER_ENV_VALUES[name]
        )
        if _environment_key(default) != expected:
            raise _policy_violation(
                "os.environ.setdefault", "barrier-environment-mutation"
            )
    if _contains_live(key) or _contains_live(default):
        raise _blocked("os.environ.setdefault")
    return _ORIGINAL_ENV_SETDEFAULT(self, key, default)


def _environ_update(self: object, *args: object, **kwargs: object) -> None:
    try:
        updates = dict(*args, **kwargs)
    except (TypeError, ValueError) as exc:
        raise _policy_violation("os.environ.update", "invalid-update") from exc
    for key, value in updates.items():
        name = _environment_key(key)
        if name in _PROTECTED_ENV_KEYS:
            expected = (
                _ROOT_TOKEN
                if name == "F017_SEQUENCE42_BARRIER_TOKEN"
                else _BARRIER_ENV_VALUES[name]
            )
            if _environment_key(value) != expected:
                raise _policy_violation(
                    "os.environ.update", "barrier-environment-mutation"
                )
    if _contains_live(updates):
        raise _blocked("os.environ.update")
    return _ORIGINAL_ENV_UPDATE(self, updates)


def _environ_delitem(self: object, key: object) -> None:
    if _environment_key(key) in _PROTECTED_ENV_KEYS:
        raise _policy_violation(
            "os.environ.__delitem__", "barrier-environment-removal"
        )
    return _ORIGINAL_ENV_DELITEM(self, key)


def _environ_pop(self: object, key: object, *args: object):
    if _environment_key(key) in _PROTECTED_ENV_KEYS:
        raise _policy_violation("os.environ.pop", "barrier-environment-removal")
    return _ORIGINAL_ENV_POP(self, key, *args)


def _environ_popitem(self: object):
    # popitem cannot promise which key it removes, so it is incompatible with
    # the inherited all-process barrier environment.
    raise _policy_violation("os.environ.popitem", "barrier-environment-removal")


def _environ_clear(self: object) -> None:
    raise _policy_violation("os.environ.clear", "barrier-environment-removal")


def _audit(event: str, args: tuple[object, ...]) -> None:
    if event == "import" and args and isinstance(args[0], str):
        module = args[0]
        if module.startswith(_TARGET_MODULE_PREFIXES):
            _append(
                {
                    "event": "EVENT06_TARGET_IMPORT",
                    "module": module,
                    "pid": os.getpid(),
                    "token": _ROOT_TOKEN,
                }
            )
    if event == "mmap.__new__" and args and isinstance(args[0], int):
        _guard_fd("audit.mmap", args[0])
        return
    if event == "subprocess.Popen" and _contains_live(args):
        raise _blocked("audit.subprocess.Popen")
    indexes = {
        "open": (0,),
        "os.listdir": (0,),
        "os.scandir": (0,),
        "os.chdir": (0,),
        "os.remove": (0,),
        "os.rmdir": (0,),
        "os.mkdir": (0,),
        "os.rename": (0, 1),
    }.get(event, ())
    for index in indexes:
        if index < len(args):
            _guard(f"audit.{event}", args[index])


def _validate_initial_process() -> None:
    if _LOG and _contains_live(_LOG):
        raise RuntimeError("F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:barrier.log")
    if _contains_live(dict(os.environ)):
        raise RuntimeError(
            "F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:process.environment"
        )
    if _contains_live(sys.argv):
        raise RuntimeError("F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:process.argv")
    if _contains_live(sys.path):
        raise RuntimeError(
            "F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:process.sys_path"
        )
    if _is_live(os.getcwd()):
        raise RuntimeError("F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:process.cwd")
    try:
        inherited_fds = tuple(
            int(item) for item in _ORIGINAL_OS_LISTDIR("/dev/fd")
        )
    except (OSError, ValueError):
        inherited_fds = ()
    for inherited_fd in inherited_fds:
        if inherited_fd != _LOG_FD and _is_live(inherited_fd):
            raise RuntimeError(
                "F017_SEQUENCE42_LIVE_AUTHORITY_ACCESS_BLOCKED:inherited.fd"
            )


try:
    _validate_initial_process()
except BaseException as _bootstrap_error:
    _fatal(f"initial:{type(_bootstrap_error).__name__}:{_bootstrap_error}")

os.open = _os_open
os.stat = _os_stat
os.lstat = _os_lstat
os.fstat = _os_fstat
os.fdopen = _os_fdopen
os.listdir = _os_listdir
os.scandir = _os_scandir
os.readlink = _os_readlink
os.chdir = _os_chdir
os.access = _os_access
os.chmod = _os_chmod
os.chown = _os_chown
os.remove = _os_remove
os.unlink = _os_unlink
os.rename = _os_rename
os.replace = _os_replace
os.mkdir = _os_mkdir
os.rmdir = _os_rmdir
os.read = _os_read
os.write = _os_write
if _ORIGINAL_OS_PREAD is not None:
    os.pread = _os_pread
if _ORIGINAL_OS_PWRITE is not None:
    os.pwrite = _os_pwrite
os.fsync = _os_fsync
os.ftruncate = _os_ftruncate
os.fchmod = _os_fchmod
os.lseek = _os_lseek
if _ORIGINAL_OS_READV is not None:
    os.readv = _os_readv
if _ORIGINAL_OS_WRITEV is not None:
    os.writev = _os_writev
os.link = _os_link
os.symlink = _os_symlink
os.truncate = _os_truncate
os.utime = _os_utime
os.statvfs = _os_statvfs
os.putenv = _os_putenv
os.unsetenv = _os_unsetenv
os.system = _os_system
if _ORIGINAL_OS_FORK is not None:
    os.fork = _os_fork
if _ORIGINAL_OS_FORKPTY is not None:
    os.forkpty = _os_forkpty
os.execv = _os_execv
os.execve = _os_execve
os.execl = _os_execl
os.execlp = _os_execlp
os.execlpe = _os_execlpe
os.execvp = _os_execvp
os.execvpe = _os_execvpe
if _ORIGINAL_OS_POSIX_SPAWN is not None:
    os.posix_spawn = _os_posix_spawn
if _ORIGINAL_OS_POSIX_SPAWNP is not None:
    os.posix_spawnp = _os_posix_spawnp
if _ORIGINAL_OS_SPAWNV is not None:
    os.spawnv = _os_spawnv
if _ORIGINAL_OS_SPAWNVE is not None:
    os.spawnve = _os_spawnve
if _ORIGINAL_OS_SPAWNVP is not None:
    os.spawnvp = _os_spawnvp
if _ORIGINAL_OS_SPAWNVPE is not None:
    os.spawnvpe = _os_spawnvpe
if _ORIGINAL_OS_SPAWNL is not None:
    os.spawnl = _os_spawnl
if _ORIGINAL_OS_SPAWNLE is not None:
    os.spawnle = _os_spawnle
if _ORIGINAL_OS_SPAWNLP is not None:
    os.spawnlp = _os_spawnlp
if _ORIGINAL_OS_SPAWNLPE is not None:
    os.spawnlpe = _os_spawnlpe
os.path.realpath = _realpath
builtins.open = _builtin_open
io.open = _io_open
Path.resolve = _path_resolve
Path.stat = _path_stat
Path.lstat = _path_lstat
Path.open = _path_open
Path.read_bytes = _path_read_bytes
Path.read_text = _path_read_text
Path.write_bytes = _path_write_bytes
Path.write_text = _path_write_text
Path.iterdir = _path_iterdir
Path.glob = _path_glob
Path.rglob = _path_rglob
_mmap_module.mmap = _mmap
if _ORIGINAL_FILE_DIGEST is not None:
    _hashlib_module.file_digest = _file_digest
subprocess.Popen = _GuardedPopen
os.getenv = _getenv
_ENVIRON_CLASS.__getitem__ = _environ_getitem
_ENVIRON_CLASS.get = _environ_get
_ENVIRON_CLASS.__setitem__ = _environ_setitem
_ENVIRON_CLASS.setdefault = _environ_setdefault
_ENVIRON_CLASS.update = _environ_update
_ENVIRON_CLASS.__delitem__ = _environ_delitem
_ENVIRON_CLASS.pop = _environ_pop
_ENVIRON_CLASS.popitem = _environ_popitem
_ENVIRON_CLASS.clear = _environ_clear
sys.addaudithook(_audit)

try:
    _append(
        {
            "event": "BARRIER_ACTIVE",
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "root_count": len(_LIVE_ROOTS),
            "scope": "LIVE_EVENT06_ROOTS_DESCENDANTS_RESOLVERS_AND_SUBPROCESSES",
            "source_sha256": _BARRIER_ENV_VALUES[
                "F017_SEQUENCE42_SOURCE_SHA256"
            ],
            "token": _ROOT_TOKEN,
        }
    )
except BaseException as _bootstrap_error:
    _fatal(f"activation:{type(_bootstrap_error).__name__}:{_bootstrap_error}")

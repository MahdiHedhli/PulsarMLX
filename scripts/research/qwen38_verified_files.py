"""Bounded, descriptor-bound verification for a trusted checkpoint manifest.

Construction repeats every manifest digest through open file descriptors and
retains SHA-256 chunk hashes. Later reads use those same descriptors and verify
each returned chunk before copying bytes to a caller. No model code is loaded.
The caller must close the set; this module does not make files immutable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from admit_qwen38_static import MANIFEST


CHUNK_BYTES = 1024 * 1024
MAX_METADATA_BYTES = 32 * 1024 * 1024 + 8
PINNED_REPO = "pipenetwork/Qwen3.8-Flash-Next-MLX-mixed-4_8bit"
PINNED_REVISION = "b2c422f3c643e36f04227a64d61796b44a4b1029"
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_HEX_SHA1 = re.compile(r"[0-9a-f]{40}\Z")


class VerificationError(ValueError):
    """A manifest, file identity, or verified read did not match."""


@dataclass(frozen=True)
class _File:
    fd: int
    size: int
    identity: tuple[int, ...]
    algorithm: str
    expected_digest: str
    chunk_bytes: int
    chunk_hashes: bytes


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _entries(entries: list[dict]):
    if type(entries) is not list or not entries:
        raise VerificationError("nonempty trusted manifest entries required")
    result = {}
    for entry in entries:
        if type(entry) is not dict:
            raise VerificationError("invalid manifest entry")
        name, size = entry.get("path"), entry.get("size_bytes")
        if (type(name) is not str or not name or name in (".", "..") or
                Path(name).name != name or type(size) is not int or size < 0 or
                name in result):
            raise VerificationError("unsafe or duplicate manifest file")
        has_sha256, has_blob = "sha256" in entry, "git_blob_sha1" in entry
        if has_sha256 == has_blob:
            raise VerificationError("manifest entry needs exactly one digest")
        digest = entry["sha256"] if has_sha256 else entry["git_blob_sha1"]
        pattern = _HEX_SHA256 if has_sha256 else _HEX_SHA1
        if type(digest) is not str or pattern.fullmatch(digest) is None:
            raise VerificationError("invalid manifest digest")
        result[name] = MappingProxyType(dict(entry))
    return MappingProxyType(result)


class VerifiedFiles:
    """Open-only source of authenticated bytes for a trusted manifest."""

    def __init__(self, root: Path, entries: list[dict]):
        self.entries = _entries(entries)
        root = Path(root)
        if root.is_symlink():
            raise VerificationError("symlinked root refused")
        self.root = root.resolve(strict=True)
        self.root_fd = -1
        self._files: dict[str, _File] = {}
        self.closed = False
        self.poisoned = False
        chunk_bytes = CHUNK_BYTES
        if type(chunk_bytes) is not int or chunk_bytes <= 0:
            raise VerificationError("invalid verification chunk size")
        try:
            self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY |
                                   os.O_NOFOLLOW | os.O_CLOEXEC)
            self.root_identity = _identity(os.fstat(self.root_fd))
            for name, entry in self.entries.items():
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                             os.O_CLOEXEC, dir_fd=self.root_fd)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size != entry["size_bytes"]:
                        raise VerificationError(f"file type or size mismatch: {name}")
                    identity = _identity(info)
                    digest = (hashlib.sha256() if "sha256" in entry else hashlib.sha1())
                    if "git_blob_sha1" in entry:
                        digest.update(f"blob {info.st_size}\0".encode())
                    chunks = bytearray()
                    for offset in range(0, info.st_size, chunk_bytes):
                        length = min(chunk_bytes, info.st_size - offset)
                        data = os.pread(fd, length, offset)
                        if len(data) != length:
                            raise VerificationError(f"short digest read: {name}")
                        digest.update(data)
                        chunks.extend(hashlib.sha256(data).digest())
                    expected = entry.get("sha256", entry.get("git_blob_sha1"))
                    if not hmac.compare_digest(digest.hexdigest(), expected):
                        raise VerificationError(f"pinned digest mismatch: {name}")
                    self._files[name] = _File(fd, info.st_size, identity,
                                              "sha256" if "sha256" in entry else "git_blob_sha1",
                                              expected, chunk_bytes, bytes(chunks))
                    self.check(name)
                except BaseException:
                    if name not in self._files:
                        os.close(fd)
                    raise
        except BaseException as exc:
            try:
                self.close()
            except OSError as cleanup_error:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"verified file cleanup also failed: {cleanup_error}")
            raise

    @property
    def files(self):
        return MappingProxyType(self._files)

    @property
    def file_sizes(self) -> dict[str, int]:
        return {name: file.size for name, file in self._files.items()}

    def check(self, name: str) -> None:
        if self.closed or self.poisoned:
            raise VerificationError("verified file set is closed or failed")
        if name not in self._files:
            raise VerificationError("file is not admitted")
        file = self._files[name]
        try:
            root = os.stat(self.root, follow_symlinks=False)
            opened_root = os.fstat(self.root_fd)
            path = os.stat(name, dir_fd=self.root_fd, follow_symlinks=False)
            opened = os.fstat(file.fd)
        except OSError as exc:
            self.poisoned = True
            raise VerificationError(f"file identity unavailable: {name}") from exc
        if (_identity(root) != self.root_identity or
                _identity(opened_root) != self.root_identity or
                _identity(path) != file.identity or _identity(opened) != file.identity):
            self.poisoned = True
            raise VerificationError(f"file identity changed: {name}")

    def readinto(self, name: str, target: memoryview, offset: int) -> None:
        """Copy only digest-checked bytes; discard target if this raises."""
        self.check(name)
        file = self._files[name]
        if (type(offset) is not int or offset < 0 or target.readonly or
                target.ndim != 1 or target.itemsize != 1 or
                offset + target.nbytes > file.size or not target.c_contiguous):
            raise VerificationError("verified read outside admitted file")
        end = offset + target.nbytes
        for chunk_index in range(offset // file.chunk_bytes,
                                 (end + file.chunk_bytes - 1) // file.chunk_bytes):
            chunk_start = chunk_index * file.chunk_bytes
            chunk_length = min(file.chunk_bytes, file.size - chunk_start)
            try:
                data = os.pread(file.fd, chunk_length, chunk_start)
            except OSError as exc:
                self.poisoned = True
                raise VerificationError(f"verified read failed: {name}") from exc
            expected = file.chunk_hashes[32 * chunk_index:32 * (chunk_index + 1)]
            if len(data) != chunk_length or not hmac.compare_digest(hashlib.sha256(data).digest(), expected):
                self.poisoned = True
                raise VerificationError(f"verified chunk changed: {name}")
            self.check(name)
            start = max(offset, chunk_start)
            stop = min(end, chunk_start + chunk_length)
            target[start - offset:stop - offset] = data[start - chunk_start:stop - chunk_start]

    def read_metadata(self, name: str, offset: int = 0, length: int | None = None) -> bytes:
        self.check(name)
        if length is None:
            length = self._files[name].size - offset
        if type(length) is not int or length < 0 or length > MAX_METADATA_BYTES:
            raise VerificationError("metadata read exceeds cap")
        result = bytearray(length)
        self.readinto(name, memoryview(result), offset)
        return bytes(result)

    def close(self) -> None:
        if self.closed:
            return
        first_error = None
        for file in self._files.values():
            try:
                os.close(file.fd)
            except OSError as exc:
                first_error = first_error or exc
        self._files.clear()
        if self.root_fd >= 0:
            try:
                os.close(self.root_fd)
            except OSError as exc:
                first_error = first_error or exc
            self.root_fd = -1
        self.closed = True
        if first_error is not None:
            raise first_error

    def __enter__(self) -> VerifiedFiles:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def open_pinned_files(root: Path, *, manifest_path: Path = MANIFEST) -> VerifiedFiles:
    """Repeat all pinned digests before any runtime binding; no receipt is trusted."""
    manifest = json.loads(manifest_path.read_text())
    entries = manifest.get("files")
    checked = _entries(entries)
    if (manifest.get("schema") != "pulsarmlx.qwen38.pinned-checkpoint/1" or
            manifest.get("repo") != PINNED_REPO or
            manifest.get("revision") != PINNED_REVISION or
            type(manifest.get("total_size_bytes")) is not int or
            manifest["total_size_bytes"] != sum(e["size_bytes"] for e in checked.values())):
        raise VerificationError("unexpected pinned manifest identity")
    return VerifiedFiles(root, entries)

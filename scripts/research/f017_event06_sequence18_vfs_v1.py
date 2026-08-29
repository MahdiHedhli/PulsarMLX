#!/usr/bin/env python3
"""Graph-owned process-level in-memory filesystem for Sequence 18 only.

This module is never imported by the production registry or coordinators.  A
qualification child installs it by replacing the measured OS storage boundary
functions before importing or invoking a producer.  The backing mapping and
lock may be multiprocessing-manager proxies so all Darwin contenders observe
one exclusive-create namespace.
"""
from __future__ import annotations

import hashlib
import threading
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes


class InMemorySafetyFilesystem:
    def __init__(self, files=None, directories=None, operations=None, lock=None):
        self.files = {} if files is None else files
        self.directories = {} if directories is None else directories
        self.operations = [] if operations is None else operations
        self.lock = threading.RLock() if lock is None else lock

    @staticmethod
    def _key(path: Path) -> str:
        return Path(path).as_posix()

    def canonical_identity(self, path: Path) -> Path:
        value = Path(path)
        if len(value.parts) > 1 and value.parts[1] in {"var", "tmp"}:
            value = Path("/private", *value.parts[1:])
        return value

    def resolved_identity(self, path: Path) -> Path:
        return self.canonical_identity(path)

    def secure_directory(self, path: Path) -> Path:
        key = self._key(self.canonical_identity(path))
        with self.lock:
            self.directories[key] = True
            self.operations.append({"primitive": "CREATE_DIRECTORY", "path_sha256": hashlib.sha256(key.encode()).hexdigest()})
        return Path(key)

    def bank_exclusive(self, path: Path, value: object) -> str:
        raw = canonical_bytes(value)
        key = self._key(self.canonical_identity(path))
        self.secure_directory(Path(key).parent)
        with self.lock:
            self.operations.append({"primitive": "OPEN_O_CREAT_O_EXCL", "path_sha256": hashlib.sha256(key.encode()).hexdigest()})
            if key in self.files:
                raise FileExistsError(key)
            self.files[key] = raw
            for primitive in ("WRITE_EXACT", "FSYNC_FILE", "FSYNC_PARENT_DIRECTORY", "READBACK"):
                self.operations.append({"primitive": primitive, "path_sha256": hashlib.sha256(key.encode()).hexdigest()})
        if self.files[key] != raw:
            raise ValueError("virtual safety-state readback")
        return hashlib.sha256(raw).hexdigest()

    def read_artifact(self, path: Path) -> object:
        key = self._key(self.canonical_identity(path))
        with self.lock:
            raw = self.files[key]
            self.operations.append({"primitive": "OPEN_READ", "path_sha256": hashlib.sha256(key.encode()).hexdigest()})
        return parse_artifact_bytes(bytes(raw))

    def snapshot(self) -> dict[str, object]:
        return {
            "file_count": len(self.files),
            "directory_count": len(self.directories),
            "operation_count": len(self.operations),
            "primitive_census": {
                name: sum(item["primitive"] == name for item in self.operations)
                for name in sorted({item["primitive"] for item in self.operations})
            },
        }

    @contextmanager
    def installed(self):
        import f017_event06_storage_primitives_v1 as storage
        with ExitStack() as stack:
            for name in (
                "canonical_identity", "resolved_identity", "secure_directory",
                "bank_exclusive", "read_artifact",
            ):
                stack.enter_context(patch.object(storage, name, getattr(self, name)))
            yield self


__all__ = ["InMemorySafetyFilesystem"]

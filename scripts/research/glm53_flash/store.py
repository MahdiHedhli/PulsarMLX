"""Bounded synthetic affine bundle/store research harness.

This module is deliberately checkpoint-free and standard-library-only.  It is
not an MLX loader and makes no claim about uninspected model payload bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePath
import stat
import struct
from typing import Mapping, Sequence


SCHEMA = "pulsarmlx.glm53-flash.synthetic-store.v1"
ENCODING = "mlx-affine-u32-low-bit-first-last-axis-v1"
PHYSICAL_IO = "NOT_MEASURABLE"
NATIVE_MAP_UNMAP = "NOT_EXERCISED"
ROLES = ("gate", "up", "down")
PLANES = ("packed", "scales", "biases")
U64_MAX = (1 << 64) - 1
MAX_FIXTURE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_BUNDLES = 64
SEMANTIC_DOMAIN = b"PULSARMLX-GLM53-FLASH-SYNTHETIC-SEMANTIC-V1\x00"
BUNDLE_DOMAIN = b"PULSARMLX-GLM53-FLASH-SYNTHETIC-BUNDLE-V1\x00"


class StoreError(Exception):
    """Base class for bounded store failures."""


class ManifestError(StoreError):
    pass


class PathSafetyError(StoreError):
    pass


class ShortReadError(StoreError):
    pass


class ReadFailure(StoreError):
    pass


class LoadCancelled(ReadFailure):
    pass


class MissingBundle(StoreError):
    pass


class StateError(StoreError):
    pass


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ManifestError("metadata is not canonicalizable") from exc


def _exact_keys(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ManifestError(f"{label} fields mismatch")
    return value


def _uint(value: object, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{label} must be an integer")
    if value < (1 if positive else 0) or value > U64_MAX:
        raise ManifestError(f"{label} outside admitted range")
    return value


def _product(values: Sequence[int], label: str) -> int:
    result = 1
    for value in values:
        if result > U64_MAX // value:
            raise ManifestError(f"{label} overflow")
        result *= value
    return result


def _checked_end(offset: int, length: int, label: str) -> int:
    if offset > U64_MAX - length:
        raise ManifestError(f"{label} overflow")
    return offset + length


def _align(value: int, alignment: int) -> int:
    if value > U64_MAX - (alignment - 1):
        raise ManifestError("alignment overflow")
    return (value + alignment - 1) & ~(alignment - 1)


def _safe_parts(name: object) -> tuple[str, ...]:
    if not isinstance(name, str) or not name:
        raise ManifestError("shard name must be non-empty text")
    raw_parts = name.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise PathSafetyError("unsafe shard path component")
    try:
        encoded_name = name.encode("utf-8")
        encoded_parts = [part.encode("utf-8") for part in raw_parts]
    except UnicodeEncodeError as exc:
        raise PathSafetyError("shard path is not valid UTF-8") from exc
    if len(encoded_name) > 1024 or any(len(part) > 255 for part in encoded_parts):
        raise PathSafetyError("shard path is too long")
    path = PurePath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise PathSafetyError("unsafe shard path")
    return path.parts


def _admit_root(root: os.PathLike[str] | str) -> Path:
    path = Path(root).absolute()
    try:
        chain = (path, *path.parents)
        infos = [candidate.lstat() for candidate in chain]
    except OSError as exc:
        raise PathSafetyError("fixture root unavailable") from exc
    if any(stat.S_ISLNK(info.st_mode) for info in infos):
        raise PathSafetyError("fixture root has a symlink ancestor")
    if not stat.S_ISDIR(infos[0].st_mode):
        raise PathSafetyError("fixture root must be a non-symlink directory")
    return path


def _open_shard(
    root: Path, name: str, expected_root: tuple[int, int, int] | None = None
) -> int:
    parts = _safe_parts(name)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    opened: list[int] = []
    try:
        fd = os.open(root, os.O_RDONLY | directory | nofollow)
        opened.append(fd)
        root_info = os.fstat(fd)
        observed_root = (root_info.st_dev, root_info.st_ino, root_info.st_uid)
        if expected_root is not None and observed_root != expected_root:
            raise PathSafetyError("fixture root identity changed")
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=fd)
            opened.append(fd)
        result = os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=opened[-1])
        if not stat.S_ISREG(os.fstat(result).st_mode):
            os.close(result)
            raise PathSafetyError("shard is not a regular file")
        return result
    except PathSafetyError:
        raise
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise PathSafetyError("symlink or non-directory shard path rejected") from exc
        raise ReadFailure("shard open failed") from exc
    finally:
        for fd in reversed(opened):
            os.close(fd)


def pack_lowbit(values: Sequence[int], bits: int) -> bytes:
    bits = _uint(bits, "bits")
    if bits not in (4, 8):
        raise ManifestError("bits must be 4 or 8")
    factor = 32 // bits
    if len(values) % factor:
        raise ManifestError("value count must fill uint32 words")
    limit = (1 << bits) - 1
    words: list[int] = []
    for base in range(0, len(values), factor):
        word = 0
        for field, value in enumerate(values[base : base + factor]):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
                raise ManifestError("quantized value outside bit width")
            word |= value << (bits * field)
        words.append(word)
    return struct.pack(f"<{len(words)}I", *words)


@dataclass(frozen=True)
class ProjectionInput:
    shape: tuple[int, ...]
    bits: int
    group_size: int
    qvalues: tuple[int, ...]
    scales: tuple[float, ...]
    biases: tuple[float, ...]


def _projection_bytes(source: ProjectionInput) -> tuple[dict, dict[str, bytes]]:
    if not source.shape or len(source.shape) > 8:
        raise ManifestError("shape must be non-empty")
    shape = tuple(_uint(value, "shape dimension", positive=True) for value in source.shape)
    bits = _uint(source.bits, "bits")
    if bits not in (4, 8):
        raise ManifestError("bits must be 4 or 8")
    factor = 32 // bits
    group = _uint(source.group_size, "group size", positive=True)
    if group > 64 or group % factor or shape[-1] % group:
        raise ManifestError("group/last-axis geometry mismatch")
    elements = _product(shape, "tensor elements")
    if elements > 65_536 or len(source.qvalues) != elements:
        raise ManifestError("tensor element count mismatch")
    packed = pack_lowbit(source.qvalues, bits)
    groups = elements // group
    if len(source.scales) != groups or len(source.biases) != groups:
        raise ManifestError("affine metadata count mismatch")
    floats = tuple(source.scales) + tuple(source.biases)
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in floats):
        raise ManifestError("affine metadata must be finite")
    for index, quantized in enumerate(source.qvalues):
        group_index = index // group
        decoded = quantized * source.scales[group_index] + source.biases[group_index]
        if not math.isfinite(decoded):
            raise ManifestError("decoded synthetic value must be finite")
    precision = {
        "mode": "affine",
        "bits": bits,
        "group_size": group,
        "packed_dtype": "uint32-le",
        "scale_dtype": "float64-le",
        "bias_dtype": "float64-le",
    }
    planes = {
        "packed": packed,
        "scales": struct.pack(f"<{groups}d", *source.scales),
        "biases": struct.pack(f"<{groups}d", *source.biases),
    }
    return {"shape": list(shape), "encoding": ENCODING, "precision": precision}, planes


def _semantic_descriptor(projection: Mapping[str, object]) -> dict:
    return {key: projection[key] for key in ("role", "shape", "encoding", "precision")}


def _semantic_hash(projections: Mapping[str, dict], payloads: Mapping[tuple[str, str], bytes]) -> str:
    digest = hashlib.sha256()
    digest.update(SEMANTIC_DOMAIN)
    for role in ROLES:
        descriptor = _canonical(_semantic_descriptor(projections[role]))
        if len(descriptor) > 0xFFFF:
            raise ManifestError("semantic descriptor too large")
        digest.update(struct.pack("<H", len(descriptor)))
        digest.update(descriptor)
        for plane in PLANES:
            data = payloads[(role, plane)]
            digest.update(struct.pack("<Q", len(data)))
            digest.update(data)
    return digest.hexdigest()


def _bundle_id(manifest_without_id: Mapping[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(BUNDLE_DOMAIN)
    digest.update(_canonical(manifest_without_id))
    return digest.hexdigest()


def _create_shard(root: Path, name: str, data: bytes) -> None:
    parts = _safe_parts(name)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    opened: list[int] = []
    result: int | None = None
    try:
        fd = os.open(root, os.O_RDONLY | directory | nofollow)
        opened.append(fd)
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=fd)
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=fd)
            opened.append(child)
            fd = child
        result = os.open(
            parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o600,
            dir_fd=fd,
        )
        view = memoryview(data)
        while view:
            wrote = os.write(result, view)
            if wrote <= 0:
                raise StoreError("short fixture write")
            view = view[wrote:]
        os.fsync(result)
    except StoreError:
        raise
    except OSError as exc:
        raise PathSafetyError("safe shard creation failed") from exc
    finally:
        if result is not None:
            os.close(result)
        for fd in reversed(opened):
            os.close(fd)


def write_synthetic_bundle(
    root: os.PathLike[str] | str,
    *,
    layer: int,
    expert: int,
    projection_order: Sequence[str],
    projections: Mapping[str, ProjectionInput],
    shard_for_role: Mapping[str, str],
    alignment: int = 16,
    layout_offsets: Mapping[str, int] | None = None,
) -> dict:
    admitted = _admit_root(root)
    layer = _uint(layer, "layer")
    expert = _uint(expert, "expert")
    if tuple(sorted(projection_order)) != tuple(sorted(ROLES)) or len(projection_order) != 3:
        raise ManifestError("projection order must contain each role once")
    if set(projections) != set(ROLES) or set(shard_for_role) != set(ROLES):
        raise ManifestError("projection inputs must map exactly gate/up/down")
    if isinstance(alignment, bool) or not isinstance(alignment, int) or alignment <= 0 or alignment > 4096 or alignment & (alignment - 1):
        raise ManifestError("alignment must be a bounded power of two")
    offsets = dict(layout_offsets or {})
    if not set(offsets) <= set(ROLES):
        raise ManifestError("unknown layout offset role")
    raw: dict[str, tuple[dict, dict[str, bytes]]] = {
        role: _projection_bytes(projections[role]) for role in ROLES
    }
    shard_buffers: dict[str, bytearray] = {}
    shard_cursor: dict[str, int] = {}
    descriptors: list[dict] = []
    payloads: dict[tuple[str, str], bytes] = {}
    for role in projection_order:
        shard = shard_for_role[role]
        _safe_parts(shard)
        base = offsets.get(role, _align(shard_cursor.get(shard, 0), alignment))
        base = _uint(base, "layout offset")
        if base % alignment or base < shard_cursor.get(shard, 0):
            raise ManifestError("layout offset overlaps or is unaligned")
        common, planes = raw[role]
        descriptor = {"role": role, **common, "shard": shard}
        cursor = base
        buffer = shard_buffers.setdefault(shard, bytearray())
        for plane in PLANES:
            cursor = _align(cursor, alignment)
            data = planes[plane]
            end = _checked_end(cursor, len(data), "synthetic segment")
            other_bytes = sum(
                len(existing)
                for existing_name, existing in shard_buffers.items()
                if existing_name != shard
            )
            if end > MAX_FIXTURE_BYTES or other_bytes + end > MAX_FIXTURE_BYTES:
                raise ManifestError("synthetic fixture byte ceiling exceeded")
            if len(buffer) < end:
                buffer.extend(b"\x00" * (end - len(buffer)))
            buffer[cursor:end] = data
            descriptor[plane] = {"offset": cursor, "length": len(data)}
            payloads[(role, plane)] = data
            cursor = end
        shard_cursor[shard] = cursor
        descriptors.append(descriptor)
    shard_rows = [{"name": name, "size": len(data)} for name, data in sorted(shard_buffers.items())]
    by_role = {row["role"]: row for row in descriptors}
    semantic = _semantic_hash(by_role, payloads)
    manifest: dict = {
        "schema": SCHEMA,
        "bundle": {"layer": layer, "expert": expert},
        "alignment": alignment,
        "projection_order": list(projection_order),
        "projections": descriptors,
        "shards": shard_rows,
        "semantic_sha256": semantic,
    }
    manifest["bundle_id"] = _bundle_id(manifest)
    validate_manifest(admitted, manifest)
    for name, data in shard_buffers.items():
        _create_shard(admitted, name, bytes(data))
    return manifest


def _validate_projection(row: object, alignment: int, shard_sizes: Mapping[str, int]) -> tuple[str, list[tuple[str, int, int]]]:
    projection = _exact_keys(
        row,
        {"role", "shape", "encoding", "precision", "shard", *PLANES},
        "projection",
    )
    role = projection["role"]
    if role not in ROLES:
        raise ManifestError("unknown projection role")
    if projection["encoding"] != ENCODING:
        raise ManifestError("unsupported encoding")
    shape_value = projection["shape"]
    if not isinstance(shape_value, list) or not shape_value or len(shape_value) > 8:
        raise ManifestError("shape must be a non-empty list")
    shape = [_uint(value, "shape dimension", positive=True) for value in shape_value]
    elements = _product(shape, "tensor elements")
    if elements > 65_536:
        raise ManifestError("tensor exceeds synthetic element ceiling")
    precision = _exact_keys(
        projection["precision"],
        {"mode", "bits", "group_size", "packed_dtype", "scale_dtype", "bias_dtype"},
        "precision",
    )
    bits = _uint(precision["bits"], "bits")
    if precision != {
        "mode": "affine",
        "bits": bits,
        "group_size": precision["group_size"],
        "packed_dtype": "uint32-le",
        "scale_dtype": "float64-le",
        "bias_dtype": "float64-le",
    } or bits not in (4, 8):
        raise ManifestError("unsupported precision descriptor")
    group = _uint(precision["group_size"], "group size", positive=True)
    factor = 32 // bits
    if group > 64 or group % factor or shape[-1] % group:
        raise ManifestError("group/last-axis geometry mismatch")
    shard = projection["shard"]
    if shard not in shard_sizes:
        raise ManifestError("projection references unknown shard")
    expected = {
        "packed": elements // factor * 4,
        "scales": elements // group * 8,
        "biases": elements // group * 8,
    }
    ranges = []
    for plane in PLANES:
        segment = _exact_keys(projection[plane], {"offset", "length"}, f"{plane} segment")
        offset = _uint(segment["offset"], f"{plane} offset")
        length = _uint(segment["length"], f"{plane} length")
        if length != expected[plane] or offset % alignment:
            raise ManifestError(f"{plane} length/alignment mismatch")
        end = _checked_end(offset, length, plane)
        if end > shard_sizes[shard]:
            raise ManifestError(f"{plane} outside shard")
        ranges.append((shard, offset, end))
    return role, ranges


def validate_manifest(root: os.PathLike[str] | str, manifest: object) -> dict:
    _admit_root(root)
    value = _exact_keys(
        manifest,
        {"schema", "bundle", "alignment", "projection_order", "projections", "shards", "semantic_sha256", "bundle_id"},
        "manifest",
    )
    if value["schema"] != SCHEMA:
        raise ManifestError("unsupported manifest schema")
    bundle = _exact_keys(value["bundle"], {"layer", "expert"}, "bundle")
    _uint(bundle["layer"], "layer")
    _uint(bundle["expert"], "expert")
    alignment = value["alignment"]
    if isinstance(alignment, bool) or not isinstance(alignment, int) or alignment <= 0 or alignment > 4096 or alignment & (alignment - 1):
        raise ManifestError("invalid alignment")
    order = value["projection_order"]
    if (
        not isinstance(order, list)
        or len(order) != 3
        or any(not isinstance(role, str) for role in order)
        or set(order) != set(ROLES)
    ):
        raise ManifestError("invalid projection order")
    shard_rows = value["shards"]
    if not isinstance(shard_rows, list) or not 1 <= len(shard_rows) <= 3:
        raise ManifestError("shards must contain one to three entries")
    shard_sizes: dict[str, int] = {}
    total_shard_bytes = 0
    for row in shard_rows:
        shard = _exact_keys(row, {"name", "size"}, "shard")
        name = shard["name"]
        _safe_parts(name)
        if name in shard_sizes:
            raise ManifestError("duplicate shard")
        size = _uint(shard["size"], "shard size")
        if size > MAX_FIXTURE_BYTES or total_shard_bytes > MAX_FIXTURE_BYTES - size:
            raise ManifestError("synthetic fixture byte ceiling exceeded")
        total_shard_bytes += size
        shard_sizes[name] = size
    projection_rows = value["projections"]
    if not isinstance(projection_rows, list) or len(projection_rows) != 3:
        raise ManifestError("projections must contain exactly three entries")
    roles: list[str] = []
    occupied: dict[str, list[tuple[int, int]]] = {name: [] for name in shard_sizes}
    for row in projection_rows:
        role, ranges = _validate_projection(row, alignment, shard_sizes)
        roles.append(role)
        for shard, start, end in ranges:
            occupied[shard].append((start, end))
    if len(set(roles)) != 3 or set(roles) != set(ROLES) or roles != order:
        raise ManifestError("duplicate, missing, or misordered projection")
    for shard, ranges in occupied.items():
        if not ranges:
            raise ManifestError("unmapped shard metadata")
        ranges.sort()
        if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
            raise ManifestError("overlapping shard segments")
    for label in ("semantic_sha256", "bundle_id"):
        digest = value[label]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ManifestError(f"invalid {label}")
    projection = {key: value[key] for key in value if key != "bundle_id"}
    if len(_canonical(projection)) > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest metadata byte ceiling exceeded")
    if _bundle_id(projection) != value["bundle_id"]:
        raise ManifestError("bundle identity mismatch")
    return value


def decode_projection(descriptor: Mapping[str, object], packed: bytes, scales: bytes, biases: bytes) -> tuple[float, ...]:
    if not isinstance(descriptor, Mapping):
        raise ManifestError("decode descriptor must be a mapping")
    shape_value = descriptor.get("shape")
    precision = descriptor.get("precision")
    if not isinstance(shape_value, (list, tuple)) or not shape_value or len(shape_value) > 8:
        raise ManifestError("decode shape must be non-empty")
    if not isinstance(precision, Mapping):
        raise ManifestError("decode precision must be a mapping")
    shape = tuple(_uint(value, "shape dimension", positive=True) for value in shape_value)
    bits = _uint(precision.get("bits"), "bits")
    if bits not in (4, 8):
        raise ManifestError("bits must be 4 or 8")
    group = _uint(precision.get("group_size"), "group size", positive=True)
    factor = 32 // bits
    if group > 64 or group % factor or shape[-1] % group:
        raise ManifestError("decode group/last-axis geometry mismatch")
    elements = _product(shape, "decode tensor elements")
    if elements > 65_536:
        raise ManifestError("decode tensor exceeds synthetic element ceiling")
    groups = elements // group
    if len(packed) != elements // factor * 4 or len(scales) != groups * 8 or len(biases) != groups * 8:
        raise ManifestError("decode plane length mismatch")
    words = struct.unpack(f"<{elements // factor}I", packed)
    scale_values = struct.unpack(f"<{groups}d", scales)
    bias_values = struct.unpack(f"<{groups}d", biases)
    if any(not math.isfinite(value) for value in scale_values + bias_values):
        raise ManifestError("nonfinite affine metadata")
    last = shape[-1]
    words_per_row = last // factor
    groups_per_row = last // group
    mask = (1 << bits) - 1
    result: list[float] = []
    for index in range(elements):
        row, column = divmod(index, last)
        word = words[row * words_per_row + column // factor]
        quantized = (word >> (bits * (column % factor))) & mask
        group_index = row * groups_per_row + column // group
        value = quantized * scale_values[group_index] + bias_values[group_index]
        if not math.isfinite(value):
            raise ManifestError("nonfinite decoded value")
        result.append(value)
    return tuple(result)


@dataclass
class ReadTelemetry:
    attempted_reads: int = 0
    completed_reads: int = 0
    short_reads: int = 0
    failed_reads: int = 0
    requested_bytes: int = 0
    returned_bytes: int = 0

    def as_dict(self) -> dict:
        return {
            "attempted_reads": self.attempted_reads,
            "completed_reads": self.completed_reads,
            "short_reads": self.short_reads,
            "failed_reads": self.failed_reads,
            "requested_bytes": self.requested_bytes,
            "returned_bytes": self.returned_bytes,
            "physical_io": PHYSICAL_IO,
            "native_map_unmap": NATIVE_MAP_UNMAP,
        }


@dataclass
class FixtureReader:
    root: os.PathLike[str] | str
    injections: Mapping[int, object] | None = None
    counters: ReadTelemetry = field(default_factory=ReadTelemetry, init=False)
    _calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.root = _admit_root(self.root)
        root_info = self.root.stat()
        self._root_identity = (root_info.st_dev, root_info.st_ino, root_info.st_uid)
        self.injections = dict(self.injections or {})

    def read(self, shard: str, offset: int, length: int) -> bytes:
        self._calls += 1
        self.counters.attempted_reads += 1
        try:
            offset = _uint(offset, "read offset")
            length = _uint(length, "read length")
            self.counters.requested_bytes += length
            if self.counters.requested_bytes > U64_MAX:
                raise ManifestError("requested byte telemetry overflow")
            if length > MAX_FIXTURE_BYTES:
                raise ReadFailure("read exceeds bounded fixture ceiling")
            end = _checked_end(offset, length, "read range")
            injection = self.injections.get(self._calls)
            if injection in ("fail", "disconnect"):
                raise ReadFailure(f"injected {injection}")
            if injection == "cancel":
                raise LoadCancelled("injected cancellation")
            fd = _open_shard(self.root, shard, self._root_identity)
            try:
                if end > os.fstat(fd).st_size:
                    raise ReadFailure("read range outside shard")
                wanted = length
                if isinstance(injection, tuple) and len(injection) == 2 and injection[0] == "short":
                    wanted = min(length, _uint(injection[1], "short injection length"))
                data = os.pread(fd, wanted, offset)
            finally:
                os.close(fd)
            self.counters.returned_bytes += len(data)
            if len(data) != length:
                self.counters.short_reads += 1
                raise ShortReadError("short positional read")
            self.counters.completed_reads += 1
            return data
        except ShortReadError:
            raise
        except (ManifestError, PathSafetyError, ReadFailure, OSError) as exc:
            self.counters.failed_reads += 1
            if isinstance(exc, (PathSafetyError, ReadFailure, LoadCancelled)):
                raise
            raise ReadFailure("fixture read failed") from exc

    def size(self, shard: str) -> int:
        """Return regular-file size through the same symlink-safe opener."""
        fd = _open_shard(self.root, shard, self._root_identity)
        try:
            return os.fstat(fd).st_size
        finally:
            os.close(fd)

    def telemetry(self) -> dict:
        return self.counters.as_dict()


@dataclass(frozen=True)
class BundleView:
    layer: int
    expert: int
    bundle_id: str
    semantic_sha256: str
    raw_planes: Mapping[tuple[str, str], bytes]
    decoded: Mapping[str, tuple[float, ...]]


@dataclass
class _Entry:
    value: BundleView
    leases: int = 0
    pending_eviction: bool = False


class Lease:
    def __init__(self, store: "DemandStore", key: tuple[int, int], entry: _Entry):
        self._store = store
        self._key = key
        self._entry = entry
        self._closed = False

    @property
    def bundle(self) -> BundleView:
        if self._closed:
            raise StoreError("lease is closed")
        return self._entry.value

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._store._release(self._key, self._entry)

    def __enter__(self) -> BundleView:
        return self.bundle

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


class DemandStore:
    def __init__(
        self,
        root: os.PathLike[str] | str,
        manifests: Sequence[dict],
        *,
        reader: FixtureReader | None = None,
        preserved_state: dict[tuple[str, str, str], bytes] | None = None,
    ):
        self.root = _admit_root(root)
        self.reader = reader or FixtureReader(self.root)
        if Path(self.reader.root) != self.root:
            raise PathSafetyError("reader root differs from store root")
        self.manifests: dict[tuple[int, int], dict] = {}
        self._by_identity: dict[str, dict] = {}
        if len(manifests) > MAX_BUNDLES:
            raise ManifestError("bundle count ceiling exceeded")
        for manifest in manifests:
            validated = validate_manifest(self.root, manifest)
            key = (validated["bundle"]["layer"], validated["bundle"]["expert"])
            if key in self.manifests or validated["bundle_id"] in self._by_identity:
                raise ManifestError("duplicate bundle metadata")
            self.manifests[key] = validated
            self._by_identity[validated["bundle_id"]] = validated
        self.preserved_state = preserved_state if preserved_state is not None else {}
        self._validate_state()
        self._cache: dict[tuple[int, int], _Entry] = {}

    def _valid_state_lengths(self) -> dict[tuple[str, str, str], int]:
        expected = {}
        for identity, manifest in self._by_identity.items():
            for projection in manifest["projections"]:
                for plane in PLANES:
                    expected[(identity, projection["role"], plane)] = projection[plane]["length"]
        return expected

    def _validate_state(self) -> None:
        expected = self._valid_state_lengths()
        for key, data in self.preserved_state.items():
            if key not in expected or not isinstance(data, bytes) or len(data) != expected[key]:
                raise StateError("preserved load state is contaminated")

    @staticmethod
    def _projection_map(manifest: dict) -> dict[str, dict]:
        return {row["role"]: row for row in manifest["projections"]}

    def _padding_ranges(self, manifest: dict) -> list[tuple[str, int, int]]:
        ranges: dict[str, list[tuple[int, int]]] = {row["name"]: [] for row in manifest["shards"]}
        sizes = {row["name"]: row["size"] for row in manifest["shards"]}
        for projection in manifest["projections"]:
            for plane in PLANES:
                segment = projection[plane]
                ranges[projection["shard"]].append((segment["offset"], segment["offset"] + segment["length"]))
        gaps = []
        for shard in sorted(ranges):
            cursor = 0
            for start, end in sorted(ranges[shard]):
                if start > cursor:
                    gaps.append((shard, cursor, start - cursor))
                cursor = end
            if cursor < sizes[shard]:
                gaps.append((shard, cursor, sizes[shard] - cursor))
        return gaps

    def _load(self, manifest: dict) -> BundleView:
        validate_manifest(self.root, manifest)
        self._validate_state()
        projections = self._projection_map(manifest)
        identity = manifest["bundle_id"]
        payloads: dict[tuple[str, str], bytes] = {}
        for role in manifest["projection_order"]:
            projection = projections[role]
            for plane in PLANES:
                state_key = (identity, role, plane)
                data = self.preserved_state.get(state_key)
                if data is None:
                    segment = projection[plane]
                    data = self.reader.read(projection["shard"], segment["offset"], segment["length"])
                    self.preserved_state[state_key] = data
                payloads[(role, plane)] = data
        for shard, offset, length in self._padding_ranges(manifest):
            if any(self.reader.read(shard, offset, length)):
                raise ManifestError("nonzero shard padding")
        for shard in manifest["shards"]:
            if self.reader.size(shard["name"]) != shard["size"]:
                raise ManifestError("actual shard size mismatch")
        semantic = _semantic_hash(projections, payloads)
        if semantic != manifest["semantic_sha256"]:
            raise ManifestError("semantic hash mismatch")
        decoded = {
            role: decode_projection(
                projections[role],
                payloads[(role, "packed")],
                payloads[(role, "scales")],
                payloads[(role, "biases")],
            )
            for role in ROLES
        }
        return BundleView(
            layer=manifest["bundle"]["layer"],
            expert=manifest["bundle"]["expert"],
            bundle_id=identity,
            semantic_sha256=semantic,
            raw_planes=payloads,
            decoded=decoded,
        )

    def acquire(self, key: tuple[int, int]) -> Lease:
        if key not in self.manifests:
            raise MissingBundle("bundle demand miss")
        entry = self._cache.get(key)
        if entry is None:
            entry = _Entry(self._load(self.manifests[key]))
            self._cache[key] = entry
        entry.leases += 1
        return Lease(self, key, entry)

    def _release(self, key: tuple[int, int], entry: _Entry) -> None:
        if entry.leases <= 0:
            raise StoreError("lease accounting underflow")
        entry.leases -= 1
        if entry.leases == 0 and entry.pending_eviction and self._cache.get(key) is entry:
            del self._cache[key]

    def evict(self, key: tuple[int, int]) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        if entry.leases:
            entry.pending_eviction = True
        else:
            del self._cache[key]
        return True

    def contains(self, key: tuple[int, int]) -> bool:
        return key in self._cache

    def telemetry(self) -> dict:
        return self.reader.telemetry()

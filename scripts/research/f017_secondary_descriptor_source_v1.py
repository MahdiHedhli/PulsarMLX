#!/usr/bin/env python3
"""Active secondary descriptor source; NumPy is required only for decoding.

The frozen V10 module is untouched. read_encoded is the real positional-read
boundary shared by descriptor-only qualification and the numerical adapter.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path


from f017_bounded_artifact_decode_v1 import NONCANONICAL_LIMITS, parse_artifact_bytes, read_artifact
from f017_descriptor_lease_manager_v10 import validate_descriptors
from f017_oracle_primary_decoders import LAYOUT
from f017_secondary_read_observation_v1 import (
    _bind_secondary_observation, _read_intent, _read_enter, _read_return, _read_error_while_raising,
    _secondary_observation_attachment,
)

ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json"


def _catalog(candidate: dict) -> tuple[dict, list[dict]]:
    path = Path(candidate["tensor_catalog_path"]); raw = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(raw).hexdigest() != candidate["tensor_catalog_sha256"]:
        raise ValueError("secondary catalog authority")
    document = parse_artifact_bytes(raw); schema = document.get("schema") if type(document) is dict else None
    if schema == "pulsarmlx.f017.synthetic-descriptor-catalog/9.0.0":
        return document, document.get("records")
    if schema == "pulsarmlx.f017.corrected-oracle-production-tensor-plan/9.0.0":
        geometry = read_artifact(GEOMETRY, limits=NONCANONICAL_LIMITS)
        return {"geometry": geometry, "token": 9703, "position": 0}, document.get("graph_tensors")
    raise ValueError("secondary catalog schema")


def _normalized(record: dict) -> dict:
    if type(record) is not dict:
        raise ValueError("secondary tensor record type")
    dims = record.get("dims", record.get("shape")); fmt = record.get("format")
    result = {"name": record.get("name"), "format": fmt, "dims": dims,
              "shard_ordinal": record.get("shard_ordinal"), "byte_offset": record.get("byte_offset"),
              "byte_length": record.get("byte_length"), "purpose": record.get("purpose", record.get("semantic_role"))}
    if (type(result["name"]) is not str or type(dims) is not list or not dims or any(type(v) is not int or v <= 0 for v in dims)
            or fmt not in LAYOUT or result["shard_ordinal"] not in range(2, 7)
            or type(result["byte_offset"]) is not int or result["byte_offset"] < 0
            or type(result["byte_length"]) is not int or result["byte_length"] <= 0):
        raise ValueError("secondary tensor record")
    return result


class SecondaryDescriptorStore:
    def __init__(self, candidate: dict, identities: list[dict], descriptors: list[int], *, _observation_owner=None):
        validate_descriptors(identities, [item["size_bytes"] for item in candidate["shards"][1:]])
        if type(descriptors) is not list or len(descriptors) != 5 or any(type(fd) is not int or fd < 0 for fd in descriptors):
            raise ValueError("secondary inherited descriptor census")
        document, source_records = _catalog(candidate)
        if type(source_records) is not list:
            raise ValueError("secondary tensor-record census")
        self.document = document; self.records: dict[str, dict] = {}
        for source_record in source_records:
            record = _normalized(source_record)
            if record["purpose"] in {"GRAPH", "FORMAT_PROBE"}:
                if record["name"] in self.records:
                    raise ValueError("duplicate secondary tensor")
                self.records[record["name"]] = record
        self.handles = {identity["shard_ordinal"]: (identity, fd) for identity, fd in zip(identities, descriptors, strict=True)}
        self.consumed: set[int] = set(); self.formats: set[str] = set(); self.tensor_reads = 0
        self.path_reopen_count = 0
        self._observation_owner = _bind_secondary_observation(_observation_owner, self, candidate, identities)

    @property
    def secondary_read_observation(self):
        return _secondary_observation_attachment(getattr(self, "_observation_owner", None))

    def _record(self, name: str, rows: int, columns: int) -> dict:
        record = self.records.get(name)
        if record is None:
            raise ValueError(f"secondary tensor missing: {name}")
        expected = [columns] if rows == 1 and len(record["dims"]) == 1 else [columns, rows]
        if record["dims"][:len(expected)] != expected:
            raise ValueError(f"secondary tensor geometry: {name}")
        return record

    def read_encoded(self, record: dict, expert: int | None, rows: int, columns: int, row_start: int = 0) -> bytes:
        block_values, block_bytes = LAYOUT[record["format"]]
        if columns % block_values:
            raise ValueError("secondary partial encoded row")
        row_bytes = columns // block_values * block_bytes
        full_rows = record["dims"][1] if len(record["dims"]) > 1 else 1
        offset = record["byte_offset"] + (0 if expert is None else expert * full_rows * row_bytes) + row_start * row_bytes
        size = rows * row_bytes
        identity, descriptor = self.handles[record["shard_ordinal"]]; observed = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_size, observed.st_mtime_ns, observed.st_ctime_ns) != (
                identity["device"], identity["inode"], identity["mode"], identity["size"], identity["mtime_ns"], identity["ctime_ns"]):
            raise ValueError("secondary inherited descriptor identity")
        if offset + size > identity["size"] or offset + size > record["byte_offset"] + record["byte_length"]:
            raise ValueError("secondary tensor bounds")
        owner = getattr(self, "_observation_owner", None)
        ticket = _read_intent(owner, self, record, identity, size)
        _read_enter(owner, ticket)
        try:
            raw = os.pread(descriptor, size, offset)
        except BaseException:
            _read_error_while_raising(owner, ticket)
            raise
        _read_return(owner, ticket, len(raw))
        if len(raw) != size:
            raise ValueError("secondary descriptor short read")
        return raw

    def _get(self, record: dict, expert: int | None, rows: int, columns: int, row_start: int = 0):
        raw = self.read_encoded(record, expert, rows, columns, row_start)
        import numpy as np
        from qualify_f017_quantization_matrix_v1 import independent_decode
        values = independent_decode(record["format"], raw, rows * columns)
        self.consumed.add(record["shard_ordinal"]); self.formats.add(record["format"]); self.tensor_reads += 1
        return np.asarray(values, dtype=np.float32).reshape((rows, columns))

    def vector(self, name: str, length: int) -> np.ndarray:
        return self._get(self._record(name, 1, length), None, 1, length).reshape(length)

    def matrix(self, name: str, rows: int, columns: int):
        return SecondaryRowMatrix(self, name, None, rows, columns)

    def expert(self, name: str, expert: int, rows: int, columns: int):
        if type(expert) is not int or expert < 0:
            raise ValueError("secondary expert ordinal")
        return SecondaryRowMatrix(self, name, expert, rows, columns)

    def exercise_format_probes(self) -> None:
        for name, record in sorted(self.records.items()):
            if record["purpose"] == "FORMAT_PROBE":
                count = math.prod(record["dims"])
                self._get(record, None, 1, count)


class SecondaryRowMatrix:
    def __init__(self, source: SecondaryDescriptorStore, name: str, expert: int | None, rows: int, columns: int):
        self.source, self.name, self.expert, self.rows, self.cols = source, name, expert, rows, columns
        source._record(name, rows, columns)

    def row(self, index: int) -> np.ndarray:
        if type(index) is not int or not 0 <= index < self.rows:
            raise IndexError(index)
        return self.source._get(self.source.records[self.name], self.expert, 1, self.cols, index).reshape(self.cols)

    def __getitem__(self, index):
        if type(index) is not int:
            raise ValueError("secondary streaming matrix exact row")
        return self.row(index)

    def copy(self):
        if self.rows != 1:
            raise ValueError("secondary streaming matrix copy only for single row")
        return self.row(0).copy()


def source_from_inherited_descriptors(candidate: dict, descriptors: list[dict], file_descriptors: list[int], *, _observation_owner=None):
    store = SecondaryDescriptorStore(candidate, descriptors, file_descriptors, _observation_owner=_observation_owner); store.exercise_format_probes()
    return store, store.document

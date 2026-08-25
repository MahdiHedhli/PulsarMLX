#!/usr/bin/env python3
"""Primary inherited-descriptor multi-shard source; no graph arithmetic."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import f017_corrected_oracle_primary_numerics_v2 as numerical
from f017_descriptor_lease_manager_v9 import validate_descriptors
from f017_oracle_primary_decoders import decode


def _load(candidate: dict, descriptors: list[dict], file_descriptors: list[int]) -> tuple[dict, list[int], list[str]]:
    validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
    if type(file_descriptors) is not list or len(file_descriptors) != 5 or any(type(item) is not int for item in file_descriptors):
        raise ValueError("primary inherited descriptor census")
    catalog_path = Path(candidate["tensor_catalog_path"])
    if catalog_path.is_symlink() or hashlib.sha256(catalog_path.read_bytes()).hexdigest() != candidate["tensor_catalog_sha256"]:
        raise ValueError("primary synthetic catalog authority")
    catalog = json.loads(catalog_path.read_bytes())
    if type(catalog) is not dict or catalog.get("schema") != "pulsarmlx.f017.synthetic-descriptor-catalog/9.0.0":
        raise ValueError("primary synthetic catalog schema")
    by_ordinal = {identity["shard_ordinal"]: (identity, descriptor) for identity, descriptor in zip(descriptors, file_descriptors, strict=True)}
    tensors: dict[str, list[float]] = {}; consumed: set[int] = set(); formats: set[str] = set()
    for record in catalog["records"]:
        ordinal = record["shard_ordinal"]; identity, descriptor = by_ordinal[ordinal]
        observed = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino, observed.st_size) != (identity["device"], identity["inode"], identity["size"]):
            raise ValueError("primary inherited descriptor identity")
        raw = os.pread(descriptor, record["byte_length"], record["byte_offset"])
        if len(raw) != record["byte_length"]:
            raise ValueError("primary descriptor short read")
        count = 1
        for dimension in record["dims"]: count *= dimension
        values = decode(record["format"], raw, count); consumed.add(ordinal); formats.add(record["format"])
        if record["purpose"] == "GRAPH":
            experts = record["dims"][2] if len(record["dims"]) > 2 else None
            if experts is None: tensors[record["name"]] = values
            else:
                width = count // experts
                for expert in range(experts): tensors[f"{record['name']}#{expert}"] = values[expert * width:(expert + 1) * width]
    if consumed != {2, 3, 4, 5, 6}:
        raise ValueError("primary five-shard consumption")
    return {**catalog, "tensors": tensors}, sorted(consumed), sorted(formats)


def source_from_inherited_descriptors(candidate: dict, descriptors: list[dict], file_descriptors: list[int]) -> tuple[numerical.JsonSource, numerical.Geometry, int, int, list[str], list[int]]:
    document, consumed, formats = _load(candidate, descriptors, file_descriptors)
    return numerical.JsonSource(document["tensors"]), numerical.Geometry.from_json(document["geometry"]), document["token"], document["position"], formats, consumed

#!/usr/bin/env python3
"""Secondary V8 inherited-descriptor synthetic target source."""
from __future__ import annotations

import json
import os

import f017_corrected_oracle_secondary_numerics_v2 as numerical


def source_from_inherited_descriptor(file_descriptors: list[int]) -> tuple[numerical.Store, dict, list[str]]:
    if type(file_descriptors) is not list or len(file_descriptors) != 5 or any(type(item) is not int for item in file_descriptors):
        raise ValueError("secondary inherited descriptor census")
    size = os.fstat(file_descriptors[0]).st_size
    raw = os.pread(file_descriptors[0], size, 0)
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("secondary synthetic checkpoint payload") from exc
    if type(document) is not dict or not {"geometry", "position", "tensors", "token"}.issubset(document):
        raise ValueError("secondary synthetic checkpoint schema")
    formats = document.get("v8_format_coverage", ["F32"])
    if type(formats) is not list or not formats or any(type(item) is not str for item in formats):
        raise ValueError("secondary synthetic format coverage")
    return numerical.Store(document["tensors"]), {"geometry": document["geometry"], "token": document["token"], "position": document["position"]}, formats

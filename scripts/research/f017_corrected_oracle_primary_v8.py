#!/usr/bin/env python3
"""V8 primary consumer wrapper over the unchanged binary64 pure core."""
from __future__ import annotations

import hashlib
from pathlib import Path

import f017_corrected_oracle_primary_numerics_v2 as numerical
from f017_corrected_oracle_authorization_v8 import parse_candidate
from f017_corrected_oracle_primary_target_source_v8 import source_from_inherited_descriptor
from f017_descriptor_lease_manager_v8 import validate_descriptors


ROOT = Path(__file__).resolve().parents[2]
NUMERICAL = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"
ROLE = "PRIMARY"


def capability() -> dict:
    return {"schema": "pulsarmlx.f017.corrected-oracle-consumer-capability/8.0.0", "role": ROLE, "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/8.0.0", "producer_path": Path(__file__).resolve().relative_to(ROOT).as_posix(), "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "numerical_path": NUMERICAL.relative_to(ROOT).as_posix(), "numerical_sha256": hashlib.sha256(NUMERICAL.read_bytes()).hexdigest(), "descriptor_transport": "INHERITED_FILE_DESCRIPTORS", "path_reopen_count": 0}


def validate_candidate(path: Path) -> dict:
    candidate, candidate_sha = parse_candidate(path)
    if candidate["primary_numerical_sha256"] != hashlib.sha256(NUMERICAL.read_bytes()).hexdigest():
        raise ValueError("primary numerical authority")
    return {"result": "PASS", "candidate_sha256": candidate_sha, "consumer_role": ROLE, "event_id": candidate["primary_event_id"], "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False, "numerical_operations": 0}


def execute(candidate: dict, descriptors: list[dict], file_descriptors: list[int]) -> dict:
    validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
    source, geometry, token, position, formats = source_from_inherited_descriptor(file_descriptors)
    result = numerical.execute(source, geometry, token, position)
    result.pop("result_sha256", None)
    return {"role": ROLE, "layers_completed": len(result["layers"]), "result": result, "path_reopen_count": 0, "descriptor_count": 5, "format_coverage": formats}

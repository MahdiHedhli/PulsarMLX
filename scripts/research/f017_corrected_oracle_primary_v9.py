#!/usr/bin/env python3
"""V9 primary wrapper over the unchanged binary64 pure core."""
from __future__ import annotations

import hashlib
from pathlib import Path

import f017_corrected_oracle_primary_numerics_v2 as numerical
from f017_corrected_oracle_authorization_v9 import parse_candidate
from f017_corrected_oracle_primary_target_source_v9 import source_from_inherited_descriptors
from f017_descriptor_lease_manager_v9 import validate_descriptors

ROOT = Path(__file__).resolve().parents[2]; NUMERICAL = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"


def validate_candidate(path: Path) -> dict:
    candidate, digest = parse_candidate(path)
    if candidate["primary_numerical_sha256"] != hashlib.sha256(NUMERICAL.read_bytes()).hexdigest(): raise ValueError("primary numerical authority")
    return {"result": "PASS", "candidate_sha256": digest, "consumer_role": "PRIMARY", "event_id": candidate["primary_event_id"],
            "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False, "numerical_operations": 0}


def execute(candidate: dict, descriptors: list[dict], file_descriptors: list[int]) -> dict:
    validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
    source, geometry, token, position, formats, shards = source_from_inherited_descriptors(candidate, descriptors, file_descriptors)
    result = numerical.execute(source, geometry, token, position); result.pop("result_sha256", None)
    return {"role": "PRIMARY", "layers_completed": len(result["layers"]), "result": result, "path_reopen_count": 0,
            "descriptor_count": 5, "format_coverage": formats, "consumed_graph_shards": shards}

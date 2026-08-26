#!/usr/bin/env python3
"""V11 primary wrapper: one pure-core execution, then exact-byte banking."""
from __future__ import annotations

from pathlib import Path
import hashlib

import f017_corrected_oracle_primary_numerics_v3 as primary_core
from f017_corrected_oracle_primary_target_source_v10 import source_from_inherited_descriptors
from f017_descriptor_lease_manager_v10 import validate_descriptors
from f017_result_bundle_builder_v11 import bank_output_bundle

ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v3.py"


def validate_candidate_document(candidate: dict) -> dict:
    if (type(candidate) is not dict
            or candidate.get("active_generation") != "V11"
            or candidate.get("primary_numerical_sha256") != hashlib.sha256(CORE_PATH.read_bytes()).hexdigest()):
        raise ValueError("primary V11 candidate authority")
    return {"result":"PASS","consumer_role":"PRIMARY","event_id":candidate.get("primary_event_id"),
            "checkpoint_opens":0,"checkpoint_reads":0,"state_created":False,"numerical_operations":0}


def execute_and_bank(source, geometry, token: int, directory: Path, *, position: int = 0,
                     authorization_id: str, package_attempt_id: str,
                     consumer_event_id: str, producer_measurement_sha256: str,
                     durable_start_sha256: str, access_census_sha256: str) -> dict:
    outputs = primary_core.execute_outputs(source, geometry, token, position)
    return bank_output_bundle(
        outputs, directory, authorization_id=authorization_id,
        package_attempt_id=package_attempt_id, consumer_event_id=consumer_event_id,
        producer_measurement_sha256=producer_measurement_sha256,
        durable_start_sha256=durable_start_sha256,
        access_census_sha256=access_census_sha256,
    )


def execute_target_and_bank(candidate: dict, descriptors: list[dict], file_descriptors: list[int],
                            directory: Path, **authority: str) -> dict:
    validate_candidate_document(candidate)
    validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
    source, geometry, token, position = source_from_inherited_descriptors(
        candidate, descriptors, file_descriptors
    )
    bundle = execute_and_bank(source, geometry, token, directory, position=position, **authority)
    return {**bundle, "role":"PRIMARY",
            "layers_completed":bundle["artifacts"]["routing"]["layer_count"],
            "path_reopen_count":source.path_reopen_count,
            "descriptor_count":len(descriptors),
            "format_coverage":sorted(source.formats),
            "consumed_graph_shards":sorted(source.consumed),
            "tensor_read_operations":source.tensor_reads}

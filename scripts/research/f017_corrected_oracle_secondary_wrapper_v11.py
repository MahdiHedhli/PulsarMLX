#!/usr/bin/env python3
"""V11 secondary wrapper with a complete-primary-terminal prerequisite."""
from __future__ import annotations

from pathlib import Path
import hashlib

import f017_corrected_oracle_secondary_numerics_v3 as secondary_core
from f017_corrected_oracle_secondary_target_source_v11 import source_from_inherited_descriptors
from f017_descriptor_lease_manager_v10 import validate_descriptors
from f017_result_artifacts_v11 import require_primary_terminal
from f017_result_bundle_builder_v11 import _minimum_gate_bank_output_bundle

__all__ = ("validate_candidate_document",)

ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py"


def validate_candidate_document(candidate: dict) -> dict:
    if (type(candidate) is not dict
            or candidate.get("active_generation") != "V11"
            or candidate.get("secondary_numerical_sha256") != hashlib.sha256(CORE_PATH.read_bytes()).hexdigest()):
        raise ValueError("secondary V11 candidate authority")
    return {"result":"PASS","consumer_role":"SECONDARY","event_id":candidate.get("secondary_event_id"),
            "checkpoint_opens":0,"checkpoint_reads":0,"state_created":False,"numerical_operations":0}


def _minimum_gate_execute_and_bank(
    document: dict,
    directory: Path,
    *,
    authorization_id: str,
    package_attempt_id: str,
    consumer_event_id: str,
    producer_measurement_sha256: str,
    durable_start_sha256: str,
    access_census_sha256: str,
    primary_terminal: dict,
    primary_result_terminal_sha256: str,
    primary_receipt_sha256: str,
    primary_manifest_sha256: str,
    use_mlx: bool = False,
    store=None,
    _write_once: bool = False,
) -> dict:
    require_primary_terminal(
        primary_terminal, primary_result_terminal_sha256,
        primary_receipt_sha256, primary_manifest_sha256,
    )
    outputs = secondary_core.execute_outputs(document, use_mlx=use_mlx, store=store)
    return _minimum_gate_bank_output_bundle(
        outputs, directory, authorization_id=authorization_id,
        package_attempt_id=package_attempt_id, consumer_event_id=consumer_event_id,
        producer_measurement_sha256=producer_measurement_sha256,
        durable_start_sha256=durable_start_sha256,
        access_census_sha256=access_census_sha256,
        _write_once=_write_once,
    )


def _minimum_gate_execute_target_and_bank(
    candidate: dict,
    descriptors: list[dict],
    file_descriptors: list[int],
    directory: Path,
    *,
    primary_terminal: dict,
    primary_result_terminal_sha256: str,
    primary_receipt_sha256: str,
    primary_manifest_sha256: str,
    use_mlx: bool = False,
    **authority: str,
) -> dict:
    validate_candidate_document(candidate)
    validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
    store, document = source_from_inherited_descriptors(candidate, descriptors, file_descriptors)
    bundle = _minimum_gate_execute_and_bank(document, directory, primary_terminal=primary_terminal,
        primary_result_terminal_sha256=primary_result_terminal_sha256,
        primary_receipt_sha256=primary_receipt_sha256,
        primary_manifest_sha256=primary_manifest_sha256, use_mlx=use_mlx,
        store=store, _write_once=True, **authority)
    return {**bundle, "role":"SECONDARY",
            "layers_completed":bundle["artifacts"]["routing"]["layer_count"],
            "path_reopen_count":store.path_reopen_count,
            "descriptor_count":len(descriptors),
            "format_coverage":sorted(store.formats),
            "consumed_graph_shards":sorted(store.consumed),
            "tensor_read_operations":store.tensor_reads}


_qualification_execute_and_bank = _minimum_gate_execute_and_bank
_qualification_execute_target_and_bank = _minimum_gate_execute_target_and_bank


def execute_and_bank(document: dict, directory: Path, *, authorization_id: str,
                     package_attempt_id: str, consumer_event_id: str,
                     producer_measurement_sha256: str, durable_start_sha256: str,
                     access_census_sha256: str, primary_terminal: dict,
                     primary_result_terminal_sha256: str,
                     primary_receipt_sha256: str, primary_manifest_sha256: str,
                     use_mlx: bool = False, store=None) -> dict:
    """Fail closed before the primary gate, numerical execution, or banking."""
    del (document, directory, authorization_id, package_attempt_id,
         consumer_event_id, producer_measurement_sha256, durable_start_sha256,
         access_census_sha256, primary_terminal,
         primary_result_terminal_sha256, primary_receipt_sha256,
         primary_manifest_sha256, use_mlx, store)
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")


def execute_target_and_bank(candidate: dict, descriptors: list[dict], file_descriptors: list[int],
                            directory: Path, *, primary_terminal: dict,
                            primary_result_terminal_sha256: str, primary_receipt_sha256: str,
                            primary_manifest_sha256: str, use_mlx: bool = False, **authority: str) -> dict:
    """Fail closed before descriptor validation, source reads, or banking."""
    del (candidate, descriptors, file_descriptors, directory, primary_terminal,
         primary_result_terminal_sha256, primary_receipt_sha256,
         primary_manifest_sha256, use_mlx, authority)
    raise RuntimeError("superseded by F017 Sequence 39 minimum-gate path")

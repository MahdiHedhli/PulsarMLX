#!/usr/bin/env python3
"""V12 secondary identity-authority validation leg; numerical path remains V11."""
from __future__ import annotations

from pathlib import Path

from f017_canonical_serialization_v10 import bank_exclusive
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_checkpoint_identity_lifecycle_v12 import failure
from f017_corrected_oracle_secondary_target_source_v11 import source_from_inherited_descriptors
from f017_corrected_oracle_secondary_wrapper_v11 import execute_and_bank as execute_and_bank_v11
from f017_corrected_oracle_secondary_wrapper_v11 import execute_target_and_bank
from f017_event06_numerical_bridge_v1 import (
    ValidatedConsumerView, build_bundle_binding, bundle_kwargs, source_projection,
)


def validate_identity_authority(authority: ValidatedIdentityAuthority, *, posture: str) -> dict:
    if type(authority) is not ValidatedIdentityAuthority or authority.posture != posture:
        outcome = ("F017_V12_IDENTITY_CANDIDATE_AUTHORITY_MISMATCH" if posture == "CANDIDATE"
                   else "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH")
        raise failure(outcome, "secondary authority posture")
    return {"member":"SECONDARY_CONSUMER","posture":posture,"result":"PASS","checkpoint_opens":0,"checkpoint_reads":0,"state_created":False}


def execute_bridge_and_bank(numerical_view: ValidatedConsumerView,
                            result_view: ValidatedConsumerView,
                            file_descriptors: list[int], directory: Path) -> dict:
    """Run one unchanged V11 secondary core from a sealed V12 bridge view."""
    if (type(numerical_view) is not ValidatedConsumerView or numerical_view.get("role") != "SECONDARY"
            or type(result_view) is not ValidatedConsumerView or result_view.get("role") != "SECONDARY"):
        raise TypeError("secondary bridge views")
    if numerical_view.get("bridge_sha256") != result_view.get("bridge_sha256"):
        raise ValueError("secondary bridge view identity")
    source_authority, descriptors = source_projection(numerical_view)
    store, document = source_from_inherited_descriptors(source_authority, descriptors, file_descriptors)
    primary = {key:numerical_view.get(key) for key in (
        "primary_terminal","primary_result_terminal_sha256","primary_receipt_sha256","primary_manifest_sha256"
    )}
    bundle = execute_and_bank_v11(
        document, directory, store=store, use_mlx=False, **primary, **bundle_kwargs(result_view)
    )
    binding, binding_sha = build_bundle_binding(numerical_view, result_view, bundle["index"])
    observed_sha = bank_exclusive(directory / "secondary-bridge-bundle-binding.json", binding)
    if observed_sha != binding_sha:
        raise ValueError("secondary bridge bundle binding")
    return {**bundle, "bridge_bundle_binding":binding,
            "bridge_bundle_binding_sha256":binding_sha,"role":"SECONDARY",
            "layers_completed":bundle["artifacts"]["routing"]["layer_count"],
            "path_reopen_count":store.path_reopen_count,"descriptor_count":len(descriptors),
            "format_coverage":sorted(store.formats),"consumed_graph_shards":sorted(store.consumed),
            "tensor_read_operations":store.tensor_reads}

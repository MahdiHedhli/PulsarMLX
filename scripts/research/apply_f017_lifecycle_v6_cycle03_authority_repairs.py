#!/usr/bin/env python3
"""Apply Opus lifecycle-V6 cycle-03 authority-binding repairs."""
from __future__ import annotations

from f017_lifecycle_semantics_v6 import MODEL_PATH, canonical_json_bytes, load_json


PATH_SHA_PAIRS = {
    "implementation_measurement_manifest_path": "implementation_measurement_manifest_sha256",
    "authorization_interface_path": "authorization_interface_sha256",
    "scientific_access_contract_path": "scientific_access_contract_sha256",
    "event_accounting_contract_path": "event_accounting_contract_sha256",
    "path_timing_contract_path": "path_timing_contract_sha256",
    "canonical_serialization_contract_path": "canonical_serialization_contract_sha256",
    "lifecycle_semantic_model_path": "lifecycle_semantic_model_sha256",
    "numerical_contract_path": "numerical_contract_sha256",
    "numerical_capability_policy_path": "numerical_capability_policy_sha256",
    "numerical_requalification_path": "numerical_requalification_sha256",
    "numerical_methodology_path": "numerical_methodology_sha256",
    "checkpoint_manifest_path": "checkpoint_manifest_sha256",
    "checkpoint_catalog_path": "checkpoint_catalog_sha256",
}


def main() -> int:
    model = load_json(MODEL_PATH)
    document = model["authorization_document"]
    document["authority_path_sha_pairs"] = PATH_SHA_PAIRS
    keys = document["top_level_keys"]
    for path_field in PATH_SHA_PAIRS:
        if path_field not in keys:
            keys.insert(keys.index("geometry_path"), path_field)
    model["measurement_authority"]["required_entries"] = sorted(set(
        model["measurement_authority"]["required_entries"]
    ) | {
        ".github/workflows/macos.yml",
        "scripts/research/apply_f017_lifecycle_v6_cycle03_authority_repairs.py",
        "scripts/research/generate_f017_lifecycle_v6_measurement_manifest.py",
        "scripts/research/check_f017_lifecycle_v6_independent.py",
    })
    model["serialization"]["finite_float_scope"] = "ALL_AUTHORITY_AND_NUMERICAL_RESULT_BYTES"
    model["serialization"]["serializer_applies_float_encoding_recursively"] = True
    for transition in model["transitions"]:
        if transition["id"] in {"T03_RENDER_CANDIDATE", "T04_PRIMARY_VALIDATE_CANDIDATE", "T05_SECONDARY_VALIDATE_CANDIDATE", "T06_INSTALL_AUTHORIZATION"}:
            transition["preconditions"] = sorted(set(transition["preconditions"]) | {
                "ALL_AUTHORITY_PATH_SHA_PAIRS_MATCH_EXACT_READBACK_BYTES",
            })
    MODEL_PATH.write_bytes(canonical_json_bytes(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

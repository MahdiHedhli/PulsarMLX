#!/usr/bin/env python3
"""Validate the complete F017 numerical authority V4 bundle."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACT = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json"
PRIMARY_V2 = RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py"
SECONDARY_V2 = RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py"
PRIMARY_V3 = RESEARCH / "f017_corrected_oracle_primary_numerics_v3.py"
SECONDARY_V3 = RESEARCH / "f017_corrected_oracle_secondary_numerics_v3.py"
PRIMARY_V2_SHA = "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767"
SECONDARY_V2_SHA = "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact_binding(binding: dict) -> None:
    require(type(binding) is dict and set(binding) == {"path", "sha256"}, "binding census")
    path = ROOT / binding["path"]
    require(path.is_file() and not path.is_symlink(), f"bound file: {binding['path']}")
    require(sha(path) == binding["sha256"], f"binding drift: {binding['path']}")


def main() -> int:
    subprocess.run([sys.executable, str(RESEARCH / "validate_f017_corrected_oracle_numerical_authority_v3.py")], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(RESEARCH / "validate_f017_numerical_output_interface_implementation_v1.py")], cwd=ROOT, check=True)
    contract = json.loads(CONTRACT.read_text())
    require(contract["schema"] == "pulsarmlx.f017.corrected-full-checkpoint-oracle-numerical-contract/4.0.0", "schema")
    require(contract["supersedes"] == {
        "path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json",
        "sha256": "84ff9ba061952e4aa9fe4fe2c76ac6cafa3f03eb74a37ac1056c2a44b5003cf9",
    }, "V3 supersession")
    for field in ("numerical_formulas_changed", "numerical_operation_order_changed", "numerical_methodology_changed", "numerical_thresholds_changed"):
        require(contract[field] is False, field)
    require(contract["pure_core_bytes_changed"] is True, "successor core declaration")
    require(contract["output_interface_changed"] is True, "output interface declaration")
    require(contract["legacy_result_compatibility"] == "EXACT", "legacy compatibility")
    require(contract["one_execution_three_outputs"] is True, "one execution")
    require(sha(PRIMARY_V2) == PRIMARY_V2_SHA and sha(SECONDARY_V2) == SECONDARY_V2_SHA, "historical V2 bytes")
    roles = contract["oracle_roles"]
    require(roles["primary"]["implementation_sha256"] == sha(PRIMARY_V3), "primary V3 binding")
    require(roles["secondary"]["implementation_sha256"] == sha(SECONDARY_V3), "secondary V3 binding")
    require(roles["primary"]["historical_implementation_sha256"] == PRIMARY_V2_SHA, "primary V2 role binding")
    require(roles["secondary"]["historical_implementation_sha256"] == SECONDARY_V2_SHA, "secondary V2 role binding")
    for binding in contract["authority_bindings"].values():
        exact_binding(binding)
    requalification = json.loads((EVIDENCE / "f017-corrected-oracle-numerical-requalification-v4.json").read_text())
    require(requalification["result"] == "PASS", "requalification")
    require(requalification["historical_equivalence_cases"] == 36, "equivalence census")
    require(requalification["fresh_process_total"] == 120, "fresh process census")
    require(requalification["ownership_mutations"] == {"mutations": 60, "rejected": 60, "unexpected_passes": 0}, "ownership mutations")
    require(requalification["packed_decoder_case_count"] == 44 and requalification["format_count"] == 11, "decoder corpus")
    require(requalification["capability_mutation_count"] >= 187 and requalification["capability_unexpected_pass_count"] == 0, "capability mutations")
    for field in (
        "primary_formula_equivalence", "secondary_formula_equivalence",
        "primary_legacy_equivalence", "secondary_legacy_equivalence",
        "primary_output_interface", "secondary_output_interface",
        "one_execution_all_outputs", "output_buffer_hash_binding", "source_read_equivalence",
    ):
        require(requalification[field] == "PASS", field)
    access_fields = (
        "original_checkpoint_shard_opens", "original_checkpoint_identity_hash_reads",
        "original_checkpoint_mmaps", "original_checkpoint_tensor_reads",
        "original_checkpoint_payload_reads",
    )
    require(all(requalification[field] == 0 for field in access_fields), "original checkpoint access")
    require(requalification["historical_master_ledger"] == 175, "historical ledger")
    require(contract["target_observation_quarantine"]["quarantined_values"] == [21615, 17351, 154820], "observation quarantine")
    for path in (PRIMARY_V3, SECONDARY_V3):
        constants = {node.value for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.Constant) and type(node.value) is int}
        require(not constants.intersection({21615, 17351, 154820}), f"observation literal: {path.name}")
    print(json.dumps({
        "schema": contract["schema"],
        "historical_v2_unchanged": True,
        "successor_core_count": 2,
        "equivalence_cases": requalification["historical_equivalence_cases"],
        "fresh_processes": requalification["fresh_process_total"],
        "capability_mutations": requalification["capability_mutation_count"],
        "original_checkpoint_access": 0,
        "result": "PASS",
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

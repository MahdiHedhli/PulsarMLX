#!/usr/bin/env python3
"""Validate numerical authority v3 and semantic capability closure."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def exact_binding(binding: dict, path: Path) -> None:
    expected = {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}
    if binding != expected:
        raise ValueError(f"authority binding drift: {expected['path']}")


def main() -> int:
    subprocess.run([sys.executable, str(RESEARCH / "validate_f017_corrected_oracle_numerical_authority_v2.py")], cwd=ROOT, check=True)
    policy_path = CONTRACTS / "f017-corrected-oracle-numerical-capability-policy-v1.json"
    analyzer = load("f017_capability_validator_v3", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    checker = load("f017_capability_checker_v3", RESEARCH / "check_f017_numerical_capabilities_independent_v1.py")
    policy = json.loads(policy_path.read_text())
    cores = {
        "primary": RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py",
        "secondary": RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py",
    }
    for role, path in cores.items():
        analyzer.analyze_path(path, policy_path, role)
        checker.check(path, policy)
    contract_path = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"
    contract = json.loads(contract_path.read_text())
    if contract["schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-numerical-contract/3.0.0":
        raise ValueError("numerical v3 schema")
    for field in ("numerical_formulas_changed", "numerical_methodology_changed", "numerical_thresholds_changed", "pure_core_bytes_changed"):
        if contract[field] is not False:
            raise ValueError(field)
    if contract["numerical_capability_policy_changed"] is not True:
        raise ValueError("capability policy status")
    expected = {
        "capability_policy": policy_path,
        "receiver_provenance": CONTRACTS / "f017-corrected-oracle-receiver-provenance-v1.json",
        "capability_use_manifest": CONTRACTS / "f017-corrected-oracle-numerical-capability-use-manifest-v1.json",
        "capability_analyzer": RESEARCH / "f017_numerical_capability_analysis_v1.py",
        "independent_capability_checker": RESEARCH / "check_f017_numerical_capabilities_independent_v1.py",
        "capability_qualifier": RESEARCH / "qualify_f017_numerical_capability_policy_v1.py",
        "capability_qualification": EVIDENCE / "f017-corrected-oracle-numerical-capability-qualification-v1.json",
        "bytecode_audit": EVIDENCE / "f017-corrected-oracle-numerical-capability-bytecode-audit-v1.json",
        "historical_authority_manifest": CONTRACTS / "f017-corrected-oracle-historical-numerical-authority-manifest-v1.json",
        "numerical_qualifier": RESEARCH / "qualify_f017_corrected_oracle_numerical_authority_v3.py",
        "numerical_requalification": EVIDENCE / "f017-corrected-oracle-numerical-requalification-v3.json",
        "numerical_validator": RESEARCH / "validate_f017_corrected_oracle_numerical_authority_v3.py",
        "separation_architecture": CONTRACTS / "f017-corrected-oracle-numerical-separation-architecture-v1.json",
    }
    if set(contract["authority_bindings"]) != set(expected):
        raise ValueError("v3 authority binding census")
    for name, path in expected.items():
        exact_binding(contract["authority_bindings"][name], path)
    qualification = json.loads((EVIDENCE / "f017-corrected-oracle-numerical-requalification-v3.json").read_text())
    if qualification["result"] != "PASS" or qualification["capability_mutation_count"] < 120 or qualification["capability_unexpected_pass_count"] != 0:
        raise ValueError("v3 requalification")
    if any(qualification[field] != 0 for field in (
        "original_checkpoint_shard_opens", "original_checkpoint_identity_hash_reads", "original_checkpoint_mmaps",
        "original_checkpoint_tensor_reads", "original_checkpoint_payload_reads",
    )):
        raise ValueError("original checkpoint access")
    print(json.dumps({"result": "PASS", "schema": contract["schema"], "capability_mutations": qualification["capability_mutation_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate numerical contract v3 with semantic capability authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path)}


def main() -> int:
    v2_path = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v2.json"
    document = json.loads(v2_path.read_text())
    document["schema"] = "pulsarmlx.f017.corrected-full-checkpoint-oracle-numerical-contract/3.0.0"
    document["supersedes"] = binding(v2_path)
    document["numerical_formulas_changed"] = False
    document["numerical_methodology_changed"] = False
    document["numerical_thresholds_changed"] = False
    document["pure_core_bytes_changed"] = False
    document["numerical_capability_policy_changed"] = True
    authorities = {
        "capability_policy": CONTRACTS / "f017-corrected-oracle-numerical-capability-policy-v1.json",
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
    document["authority_bindings"] = {name: binding(path) for name, path in authorities.items()}
    output = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"
    output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"result": "PASS", "path": str(output.relative_to(ROOT)), "sha256": sha(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

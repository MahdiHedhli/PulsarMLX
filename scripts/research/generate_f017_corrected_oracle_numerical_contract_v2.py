#!/usr/bin/env python3
"""Generate numerical contract v2 without changing v1 methodology."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
SOURCE = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json"
OUTPUT = CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v2.json"


def sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def main() -> int:
    value = json.loads(SOURCE.read_text())
    value["schema"] = "pulsarmlx.f017.corrected-full-checkpoint-oracle-numerical-contract/2.0.0"
    value["supersedes"] = {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha(str(SOURCE.relative_to(ROOT)))}
    value["numerical_methodology_changed"] = False
    value["numerical_thresholds_changed"] = False
    value["numerical_authority_paths_changed"] = True
    value["direct_checkpoint_target_surfaces_inside_numerical_authority"] = False
    value["oracle_roles"]["primary"]["implementation"] = "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"
    value["oracle_roles"]["primary"]["implementation_sha256"] = sha("scripts/research/f017_corrected_oracle_primary_numerics_v2.py")
    value["oracle_roles"]["primary"]["target_source"] = "scripts/research/f017_corrected_oracle_primary_target_source_v6.py"
    value["oracle_roles"]["primary"]["target_source_sha256"] = sha("scripts/research/f017_corrected_oracle_primary_target_source_v6.py")
    value["oracle_roles"]["primary"]["decoder"] = "scripts/research/f017_oracle_primary_decoders.py"
    value["oracle_roles"]["primary"]["decoder_sha256"] = sha("scripts/research/f017_oracle_primary_decoders.py")
    value["oracle_roles"]["secondary"]["implementation"] = "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"
    value["oracle_roles"]["secondary"]["implementation_sha256"] = sha("scripts/research/f017_corrected_oracle_secondary_numerics_v2.py")
    value["oracle_roles"]["secondary"]["target_source"] = "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py"
    value["oracle_roles"]["secondary"]["target_source_sha256"] = sha("scripts/research/f017_corrected_oracle_secondary_target_source_v6.py")
    value["oracle_roles"]["secondary"]["decoder"] = "scripts/research/qualify_f017_quantization_matrix_v1.py"
    value["oracle_roles"]["secondary"]["decoder_sha256"] = sha("scripts/research/qualify_f017_quantization_matrix_v1.py")
    value["frozen_thresholds"] = {
        "max_absolute_error": 0.0065169706285814755,
        "rmse": 0.003463567697419031,
        "cosine_minimum": 0.9999999985448085,
        "top_n": 32,
    }
    value["authority_bindings"] = {
        "separation_architecture": {"path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-separation-architecture-v1.json", "sha256": sha("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-separation-architecture-v1.json")},
        "historical_authority_manifest": {"path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-historical-numerical-authority-manifest-v1.json", "sha256": sha("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-historical-numerical-authority-manifest-v1.json")},
        "numerical_requalification": {"path": "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v2.json", "sha256": sha("docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v2.json")},
        "numerical_qualifier": {"path": "scripts/research/qualify_f017_corrected_oracle_numerical_authority_v2.py", "sha256": sha("scripts/research/qualify_f017_corrected_oracle_numerical_authority_v2.py")},
        "numerical_validator": {"path": "scripts/research/validate_f017_corrected_oracle_numerical_authority_v2.py", "sha256": sha("scripts/research/validate_f017_corrected_oracle_numerical_authority_v2.py")},
    }
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"
    temporary = OUTPUT.with_name(OUTPUT.name + ".generating")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data); output.flush(); os.fsync(output.fileno())
    os.replace(temporary, OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

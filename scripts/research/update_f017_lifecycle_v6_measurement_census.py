#!/usr/bin/env python3
"""Apply the reviewed cycle-02 measurement-census correction to model V6."""
from __future__ import annotations

from f017_lifecycle_semantics_v6 import MODEL_PATH, canonical_json_bytes, load_json

REMOVE = {"scripts/research/f017_numerical_capability_structural_check_v1.py"}
ADD = {
    "scripts/research/f017_corrected_oracle_compare_v6.py",
    "scripts/research/generate_f017_corrected_oracle_inert_v6.py",
    "scripts/research/generate_f017_corrected_oracle_scientific_access_v6.py",
    "scripts/research/qualify_f017_corrected_oracle_target_adapters_v6.py",
    "scripts/research/qualify_f017_lifecycle_v6.py",
    "scripts/research/rehearse_f017_corrected_oracle_event04_v6.py",
    "scripts/research/generate_f017_numerical_capability_authorities_v1.py",
    "scripts/research/qualify_f017_numerical_capability_policy_v1.py",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v1.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-primary-capability-v6.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v6.json",
    "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v6.json",
    "specs/017-rust-native-inference-runtime/templates/f017-corrected-oracle-event-04-operator-go-template-v1.json",
}


def main() -> int:
    model = load_json(MODEL_PATH)
    entries = set(model["measurement_authority"]["required_entries"])
    entries.difference_update(REMOVE)
    entries.update(ADD)
    model["measurement_authority"]["required_entries"] = sorted(entries)
    MODEL_PATH.write_bytes(canonical_json_bytes(model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

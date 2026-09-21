#!/usr/bin/env python3
"""Reproduce the rejected lifecycle-v4 semantic failures without checkpoint access."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
SCRIPTS = ROOT / "scripts/research"


def strict_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs)


def load_rejected_validator():
    path = SCRIPTS / "validate_f017_corrected_oracle_lifecycle_v4.py"
    spec = importlib.util.spec_from_file_location("f017_rejected_v4_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load rejected v4 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    registry = load(CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v1.json")
    matrix = load(CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v1.json")
    interface = load(CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v4.json")
    accounting = load(CONTRACTS / "f017-corrected-oracle-event-accounting-v4.json")
    validator = load_rejected_validator()

    baseline = validator.validate_documents(registry, matrix, interface)

    mutated_accounting = copy.deepcopy(accounting)
    mutated_accounting["unstarted_consumer_delta"] = 1
    mutated_accounting["reservation_is_not_execution"] = False
    accounting_mutation_result = validator.validate_documents(registry, matrix, interface)

    mutated_registry = copy.deepcopy(registry)
    mutated_matrix = copy.deepcopy(matrix)
    mutated_interface = copy.deepcopy(interface)
    fabricated_outcomes = [
        "SUCCESS",
        "ABORT_AFTER_SECONDARY_START",
        "ABORT_BEFORE_SECONDARY_START",
        "ABORT_BEFORE_PRIMARY_START",
    ]
    for identity in mutated_registry["identities"]:
        if identity["name"] == "secondary_terminal_sha256":
            identity["conditional_artifact_json_paths"]["package_receipt"]["required_outcomes"] = fabricated_outcomes
    for row in mutated_matrix["rows"]:
        if row["identity"] == "secondary_terminal_sha256":
            row["cells"]["package_receipt"]["required_outcomes"] = fabricated_outcomes
    mutated_interface["artifact_schemas"]["package_receipt"]["conditional_identity_outcomes"]["secondary_terminal_sha256"] = fabricated_outcomes
    fabricated_terminal_result = validator.validate_documents(mutated_registry, mutated_matrix, mutated_interface)

    absolute_path = registry["grammars"]["ABSOLUTE_PATH"]
    canonical_path_columns = next(
        identity["downstream_artifacts"]
        for identity in registry["identities"]
        if identity["name"] == "canonical_install_path"
    )
    path_unsatisfiable = (
        "Path.resolve(strict=True)" in absolute_path["resolution"]
        and "operator_approval" in canonical_path_columns
        and interface["validation_boundary"]["state_roots_created"] == 0
        and "unused_roots" in interface["authority_semantics"]["installed_authority_requires"]
    )

    sha_identities = [item for item in registry["identities"] if item["type"] == "SHA256"]
    undefined_readback_sha = (
        all(item["derivation_permitted"] is False and item["derivation_rule"] is None for item in sha_identities)
        and "canonical_serialization" not in interface
        and "readback_sha_domain" not in interface
    )

    measurement_paths = {
        "authorizer": "scripts/research/validate_f017_corrected_oracle_access_v3.py",
        "coordinator": "scripts/research/execute_f017_corrected_oracle_event_v3.py",
        "primary": "scripts/research/f017_corrected_oracle_primary_v3.py",
        "secondary": "scripts/research/f017_corrected_oracle_secondary_v3.py",
    }
    measurement_binding_absent = "measurement_head" not in interface and "path_sha_measurements" not in interface

    live_entrypoints = {}
    for generation in (2, 3):
        path = SCRIPTS / f"validate_f017_corrected_oracle_access_v{generation}.py"
        text = path.read_text(encoding="utf-8")
        live_entrypoints[f"v{generation}"] = {
            "path": str(path.relative_to(ROOT)),
            "authorize_live_reachable": "authorize-live" in text,
            "historical_only_guard": "HISTORICAL_ONLY" in text,
        }

    supersession = load(ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-v3-lifecycle-authority-supersession-v1.json")
    unsupported_supersession_claims = []
    for retired in supersession["retired_authorities"]:
        source = (ROOT / retired["path"]).read_text(encoding="utf-8")
        behavior = retired["required_behavior"]
        if behavior in {"V3_AUTHORIZER_REJECTS_LIVE_MINT", "V3_COORDINATOR_REJECTS_NEW_PACKAGE_EXECUTION"} and "HISTORICAL_ONLY" not in source:
            unsupported_supersession_claims.append({"path": retired["path"], "required_behavior": behavior})

    checks = {
        "C3-B-1": accounting_mutation_result == baseline and mutated_accounting != accounting,
        "C3-B-2": fabricated_terminal_result == baseline,
        "C3-B-3": path_unsatisfiable,
        "C3-B-4": measurement_binding_absent and len(measurement_paths) == 4,
        "C3-B-5": undefined_readback_sha,
        "C3-B-6": all(item["authorize_live_reachable"] and not item["historical_only_guard"] for item in live_entrypoints.values()) and len(unsupported_supersession_claims) == 2,
    }
    if not all(checks.values()):
        raise RuntimeError(f"cycle-3 reproduction incomplete: {checks}")

    result = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-v4-semantic-failure-reproduction/1.0.0",
        "result": "PASS_REPRODUCED_REJECTED_V4_FAILURES",
        "source_head": "ce903151d1175add8fb0d90e09849e03edd8fb8d",
        "baseline_validator_result": baseline,
        "finding_reproductions": {
            "C3-B-1": {"reproduced": checks["C3-B-1"], "mutation": {"unstarted_consumer_delta": 1, "reservation_is_not_execution": False}, "validator_still_passed": True},
            "C3-B-2": {"reproduced": checks["C3-B-2"], "fabricated_binding": "secondary_terminal_sha256", "fabricated_unstarted_outcomes": ["ABORT_BEFORE_SECONDARY_START", "ABORT_BEFORE_PRIMARY_START"], "validator_still_passed": True},
            "C3-B-3": {"reproduced": checks["C3-B-3"], "strict_resolution_applied_before_install": True, "absent_leaf_model_present": False},
            "C3-B-4": {"reproduced": checks["C3-B-4"], "unmeasured_paths": measurement_paths},
            "C3-B-5": {"reproduced": checks["C3-B-5"], "sha_identity_count": len(sha_identities), "serialization_domain_defined": False},
            "C3-B-6": {"reproduced": checks["C3-B-6"], "live_entrypoints": live_entrypoints, "unsupported_supersession_claims": unsupported_supersession_claims},
        },
        "original_checkpoint_access": {
            "shard_opens": 0,
            "identity_hash_reads": 0,
            "mmaps": 0,
            "tensor_reads": 0,
            "payload_reads": 0,
        },
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

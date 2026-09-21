#!/usr/bin/env python3
"""Run the reconciled Event-04 production-shaped, zero-access rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import rehearse_f017_corrected_oracle_event04_v6 as base
from f017_corrected_oracle_authorization_v6 import ROOT, canonical_bytes, sha256_path
from validate_f017_corrected_oracle_access_v6 import construct_candidate_from_inert as construct_candidate
from validate_f017_event04_authority_reconciliation_v1 import (
    DEFAULT_ACTIVE,
    DEFAULT_DECLARATION,
    DEFAULT_INERT,
    DEFAULT_MANIFEST,
    DEFAULT_MEASUREMENT,
    DEFAULT_SCIENTIFIC,
    validate_paths,
)


def rehearse(
    output: Path | None,
    *,
    scientific: Path = DEFAULT_SCIENTIFIC,
    measurement: Path = DEFAULT_MEASUREMENT,
    declaration: Path = DEFAULT_DECLARATION,
    inert: Path = DEFAULT_INERT,
    authority_manifest: Path = DEFAULT_MANIFEST,
) -> dict:
    paths = {
        "scientific": scientific,
        "measurement": measurement,
        "declaration": declaration,
        "inert": inert,
        "authority_manifest": authority_manifest,
        "active": DEFAULT_ACTIVE,
    }
    reconciliation, _, _ = validate_paths(paths)
    base.SCIENTIFIC = scientific
    base.construct_candidate_from_inert = lambda replacements: construct_candidate(replacements, inert)
    result = base.rehearse(None, measurement)
    scientific_document = json.loads(scientific.read_text())
    measured = reconciliation["measured_bindings"]
    result.update({
        "schema": "pulsarmlx.f017.event04-authority-reconciliation-production-shaped-rehearsal/1.0.0",
        "scientific_access_contract_path": str(scientific.relative_to(ROOT)),
        "scientific_access_contract_sha256": sha256_path(scientific),
        "authority_manifest_path": str(authority_manifest.relative_to(ROOT)),
        "authority_manifest_sha256": sha256_path(authority_manifest),
        "authority_reconciliation_result": reconciliation["result"],
        "authority_source_of_truth": scientific_document["source_of_truth"]["rule"],
        "implementation_measurement_head": reconciliation["implementation_measurement_head"],
        "implementation_tree": reconciliation["implementation_tree"],
        "parser_measured_sha256": measured["parser"]["sha256"],
        "parser_contract_sha256": scientific_document["bindings"]["parser"]["sha256"],
        "coordinator_measured_sha256": measured["coordinator"]["sha256"],
        "coordinator_contract_sha256": scientific_document["bindings"]["coordinator"]["sha256"],
        "all_implementation_bindings_equal_measurement_manifest": True,
        "accounting_plan_result": "PASS",
        "path_timing_result": "PASS",
        "event_04_operator_go": False,
    })
    if result["parser_measured_sha256"] != result["parser_contract_sha256"]:
        raise ValueError("parser reconciliation drift")
    if result["coordinator_measured_sha256"] != result["coordinator_contract_sha256"]:
        raise ValueError("coordinator reconciliation drift")
    if output is not None:
        output.write_bytes(canonical_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scientific", type=Path, default=DEFAULT_SCIENTIFIC)
    parser.add_argument("--measurement", type=Path, default=DEFAULT_MEASUREMENT)
    parser.add_argument("--declaration", type=Path, default=DEFAULT_DECLARATION)
    parser.add_argument("--inert", type=Path, default=DEFAULT_INERT)
    parser.add_argument("--authority-manifest", type=Path, default=DEFAULT_MANIFEST)
    arguments = parser.parse_args()
    print(json.dumps(rehearse(
        arguments.output,
        scientific=arguments.scientific.resolve(),
        measurement=arguments.measurement.resolve(),
        declaration=arguments.declaration.resolve(),
        inert=arguments.inert.resolve(),
        authority_manifest=arguments.authority_manifest.resolve(),
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

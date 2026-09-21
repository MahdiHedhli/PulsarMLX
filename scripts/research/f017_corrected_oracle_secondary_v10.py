#!/usr/bin/env python3
"""V10 secondary wrapper over the unchanged binary32 pure core."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from f017_bounded_artifact_decode_v1 import read_artifact

import f017_corrected_oracle_secondary_numerics_v2 as numerical
from f017_corrected_oracle_authorization_v10 import parse_candidate
from f017_corrected_oracle_secondary_target_source_v10 import source_from_inherited_descriptors
from f017_descriptor_lease_manager_v10 import validate_descriptors
from f017_canonical_serialization_v10 import bank_exclusive

ROOT = Path(__file__).resolve().parents[2]; NUMERICAL = ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"


def validate_candidate(path: Path) -> dict:
    candidate, digest = parse_candidate(path)
    if candidate["secondary_numerical_sha256"] != hashlib.sha256(NUMERICAL.read_bytes()).hexdigest(): raise ValueError("secondary numerical authority")
    return {"result": "PASS", "candidate_sha256": digest, "consumer_role": "SECONDARY", "event_id": candidate["secondary_event_id"],
            "checkpoint_opens": 0, "checkpoint_reads": 0, "state_created": False, "numerical_operations": 0}


def execute(candidate: dict, descriptors: list[dict], file_descriptors: list[int]) -> dict:
    validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
    store, document = source_from_inherited_descriptors(candidate, descriptors, file_descriptors)
    result = numerical.execute(document, False, store)
    return {"role": "SECONDARY", "layers_completed": len(result["layers"]), "result": result, "path_reopen_count": 0,
            "descriptor_count": 5, "format_coverage": sorted(store.formats), "consumed_graph_shards": sorted(store.consumed),
            "tensor_read_operations": store.tensor_reads}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute-installed", action="store_true")
    parser.add_argument("--authorization", type=Path); parser.add_argument("--receipt", type=Path)
    parser.add_argument("--descriptors", type=Path); parser.add_argument("--fds"); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.execute_installed or None in (args.authorization, args.receipt, args.descriptors, args.fds, args.output):
        raise ValueError("secondary target command")
    candidate, _ = parse_candidate(args.authorization)
    from validate_f017_corrected_oracle_access_v10 import validate_installed_operator_go, validate_installed_rehearsal
    validator = validate_installed_operator_go if candidate["scope"] == "PRODUCTION_EVENT_04" else validate_installed_rehearsal
    handshake = validator(args.authorization, args.receipt)
    descriptor_document = read_artifact(args.descriptors)
    descriptors = descriptor_document["payload"]["descriptor_identities"] if type(descriptor_document) is dict and descriptor_document.get("artifact_kind") else descriptor_document
    fds = [int(value) for value in args.fds.split(",")]
    result = execute(handshake["candidate"], descriptors, fds); bank_exclusive(args.output, result)
    return 0


if __name__ == "__main__": raise SystemExit(main())

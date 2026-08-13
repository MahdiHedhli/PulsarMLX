#!/usr/bin/env python3
"""Fail-closed validator for accepted M1-F0 route, evidence, and ledger."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


ABSOLUTE_PRIVATE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\\\)")


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_admission(root: Path):
    path = root / "scripts/research/f017_m1f0_admission.py"
    spec = importlib.util.spec_from_file_location("m1f0_accepted_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_privacy(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_privacy(key)
            scan_privacy(child)
    elif isinstance(value, list):
        for child in value:
            scan_privacy(child)
    elif isinstance(value, str) and ABSOLUTE_PRIVATE.search(value):
        raise ValueError("private absolute path")


def repeat_identity(record: dict[str, Any]) -> bytes:
    return json.dumps(
        {key: value for key, value in record.items() if key != "ordinal"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    evidence_dir = root / "docs/architecture/reviews/evidence"
    route_path = evidence_dir / "f017-m1-f0-layer3-route-v1.json"
    evidence_path = evidence_dir / "f017-m1-f0-real-route-attempt-2-v1.json"
    attempt1_path = evidence_dir / "f017-m1-f0-real-route-attempt-1-rejected-v1.json"
    ledger_path = evidence_dir / "f017-m1-f0-attempt-ledger.json"
    inventory_path = evidence_dir / "f017-m1-f-post-route-inventory-v1.json"
    route = load(route_path)
    evidence = load(evidence_path)
    ledger = load(ledger_path)
    inventory = load(inventory_path)
    admission = load_admission(root)
    admission.validate_route_artifact(root, route, route["input_package_sha256"])

    route_sha = digest(route_path)
    evidence_sha = digest(evidence_path)
    if route_sha != "980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e":
        raise ValueError("route artifact identity")
    if evidence_sha != "0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9":
        raise ValueError("accepted evidence identity")
    if evidence.get("verdict") != "M1-F0 ACCEPTED" or evidence.get("attempt") != 2:
        raise ValueError("accepted verdict identity")
    if evidence.get("route_artifact_sha256") != route_sha:
        raise ValueError("evidence route binding")
    if evidence.get("oracle_package_sha256") != route.get("oracle_package_sha256"):
        raise ValueError("oracle binding")
    if route.get("top8_ids") != [166, 78, 26, 186, 163, 199, 233, 177]:
        raise ValueError("accepted route identity")

    records = evidence.get("repeat_integrity", {}).get("records", [])
    if (
        len(records) != 10
        or [record.get("ordinal") for record in records] != list(range(10))
        or any(repeat_identity(record) != repeat_identity(records[0]) for record in records[1:])
    ):
        raise ValueError("repeat integrity")
    if evidence.get("access") != {
        "compressed_bytes": 139217920,
        "decoded_bytes": 666430464,
        "expert_payloads": 0,
        "positional_reads": 12,
        "shard_opens": 1,
        "tensor_payloads": 12,
    }:
        raise ValueError("access accounting")
    payload_names = [record.get("symbolic_name") for record in evidence.get("tensor_payloads", [])]
    if len(payload_names) != 12 or any("_exps" in name or "_shexp" in name for name in payload_names):
        raise ValueError("expert access isolation")
    if evidence.get("isolation") != {
        "attention_router_discoveries": 1,
        "expert_dispatches": 0,
        "expert_tensor_accesses": 0,
        "m1_f_executions": 0,
        "mlx_candidate_dispatches": 0,
    }:
        raise ValueError("execution isolation")

    attempts = ledger.get("attempts", [])
    if [record.get("attempt") for record in attempts] != [1, 2]:
        raise ValueError("attempt ledger ordering")
    if attempts[0].get("evidence_sha256") != digest(attempt1_path):
        raise ValueError("attempt-1 evidence binding")
    if attempts[1].get("evidence_sha256") != evidence_sha or attempts[1].get("verdict") != "M1-F0 ACCEPTED":
        raise ValueError("attempt-2 evidence binding")
    if ledger.get("cumulative_checkpoint_access") != {
        "decoder_qualification_payloads": 1,
        "route_discovery_payloads": 24,
        "total_payloads": 25,
    }:
        raise ValueError("cumulative access ledger")
    if (
        inventory.get("status") != "PREPARED / NOT AUTHORIZED"
        or inventory.get("m1f0_route_artifact_sha256") != route_sha
        or inventory.get("m1f0_accepted_evidence_sha256") != evidence_sha
        or inventory.get("top8_ids") != route.get("top8_ids")
        or len(inventory.get("routed_experts", [])) != 8
        or len(inventory.get("shared_expert", [])) != 3
        or inventory.get("quantization_admission", {}).get("newly_required") != ["Q6_K"]
        or inventory.get("m1f_authorized") is not False
    ):
        raise ValueError("M1-F resumption inventory")

    for value in (route, evidence, ledger, inventory):
        scan_privacy(value)
    print("M1-F0 accepted evidence validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

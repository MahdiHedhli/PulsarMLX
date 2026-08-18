#!/usr/bin/env python3
"""Validate the checkpoint-free shared-expert recovery authorization package."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research import f017_shared_expert_recovery as recovery
from scripts.research.f017_canonical_expert_output_recovery_executor import (
    RecoveryExecutionError, canonical_sha256,
)


CONTRACT = recovery.CONTRACT_PATH
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-shared-expert-output-recovery-v1.schema.json"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-recovery-authorization-v1.json"


def load_json_strict(path: Path) -> dict:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryExecutionError("DUPLICATE_KEY", key)
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise RecoveryExecutionError("JSON_OBJECT_REQUIRED")
    return value


def _source_calls(function_name: str, path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return {child.func.id for child in ast.walk(node)
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)}
    raise AssertionError(function_name)


def validate() -> dict:
    contract = load_json_strict(CONTRACT)
    schema = load_json_strict(SCHEMA)
    evidence = load_json_strict(EVIDENCE)
    if contract["schema"] != schema["properties"]["schema"]["const"]:
        raise RecoveryExecutionError("SCHEMA_IDENTITY")
    recovery.validate_inventory(contract["payload_inventory"])
    if contract["checkpoint"]["inventory_sha256"] != recovery.INVENTORY_SHA256:
        raise RecoveryExecutionError("INVENTORY_DIGEST")
    if contract["checkpoint"]["expected_packed_bytes"] != recovery.EXPECTED_PACKED_BYTES:
        raise RecoveryExecutionError("PACKED_BYTE_BUDGET")
    if contract["ledger"] != {"before": 163, "authorized_reads": 3, "after_complete": 166,
        "increment_boundary": "successful_exact_size_checkpoint_payload_read",
        "partial_failure": "ledger=163+N;terminal;no_retry"}:
        raise RecoveryExecutionError("LEDGER_CONTRACT")
    if contract["event"]["execution_authority"] or contract["event"]["automatic_retry"]:
        raise RecoveryExecutionError("AUTHORIZATION_STATE")
    binding = contract["shared_specific_binding"]
    if recovery.sha256_path(ROOT / binding["implementation_path"]) != binding["implementation_source_sha256"]:
        raise RecoveryExecutionError("IMPLEMENTATION_IDENTITY")
    if recovery.sha256_path(ROOT / binding["entrypoint_path"]) != binding["entrypoint_sha256"]:
        raise RecoveryExecutionError("ENTRYPOINT_IDENTITY")
    q5 = contract["decoder_lineage"]["q5_k"]
    q6 = contract["decoder_lineage"]["q6_k"]
    for item in (q5["decoder_a"], q5["decoder_b"], q6["decoder_a"], q6["decoder_b"]):
        if recovery.sha256_path(ROOT / item["path"]) != item["source_sha256"]:
            raise RecoveryExecutionError("DECODER_SOURCE_IDENTITY", item["path"])
    if q5["decoder_a"]["implementation_sha256"] == q5["decoder_b"]["implementation_sha256"]:
        raise RecoveryExecutionError("Q5_INDEPENDENCE")
    if q6["decoder_a"]["implementation_sha256"] == q6["decoder_b"]["implementation_sha256"]:
        raise RecoveryExecutionError("Q6_INDEPENDENCE")
    q5_b_calls = _source_calls("decode_q5_k_upstream_spec", ROOT / q5["decoder_b"]["path"])
    if "decode_q5_k_spec" in q5_b_calls:
        raise RecoveryExecutionError("Q5_DECODER_B_CALLS_A")
    q6_b_calls = _source_calls("decode_q6_k_independent", ROOT / q6["decoder_b"]["path"])
    if "decode_q6_k_spec" in q6_b_calls:
        raise RecoveryExecutionError("Q6_DECODER_B_CALLS_A")
    raw = CONTRACT.read_bytes() + SCHEMA.read_bytes() + EVIDENCE.read_bytes()
    if any(marker in raw for marker in (b"/Users/", b"/home/", b"file://")):
        raise RecoveryExecutionError("PRIVATE_PATH_LEAK")
    if contract["preparation_access"] != {"checkpoint_reads": 0, "shard_opens": 0,
        "real_payload_ledger": 163, "attempt_records_created": 0,
        "execution_start_records_created": 0}:
        raise RecoveryExecutionError("PREPARATION_ACCESS")
    if evidence["authorization"]["canonical_sha256"] != canonical_sha256(contract):
        raise RecoveryExecutionError("EVIDENCE_AUTHORIZATION_IDENTITY")
    preflight = recovery.production_preflight()
    rehearsal = recovery.run_synthetic_rehearsal()
    callgraph = recovery.static_checkpoint_capability_audit()
    if preflight["surfaces_resolved"] != 14 or preflight["status"] != "PRODUCTION_BINDINGS_RESOLVED":
        raise RecoveryExecutionError("PRODUCTION_PREFLIGHT")
    if rehearsal["status"] != "PASS" or rehearsal["case_count"] < 11:
        raise RecoveryExecutionError("SYNTHETIC_REHEARSAL")
    if callgraph["status"] != "PASS" or callgraph["capability_boundary_count"] != 1:
        raise RecoveryExecutionError("CHECKPOINT_CAPABILITY_AUDIT")
    return {
        "schema": "pulsarmlx.f017.canonical-shared-expert-output-recovery-authorization-validation",
        "status": "SHARED EXPERT RECOVERY AUTHORIZATION READY",
        "authorization_sha256": canonical_sha256(contract),
        "schema_sha256": recovery.sha256_path(SCHEMA),
        "inventory_sha256": recovery.INVENTORY_SHA256,
        "decoder_independence": {"Q5_K": "PASS", "Q6_K": "PASS"},
        "production_preflight": preflight,
        "synthetic_rehearsal": {"status": rehearsal["status"], "case_count": rehearsal["case_count"]},
        "checkpoint_capability_audit": callgraph,
        "checkpoint_reads": 0, "shard_opens": 0, "real_payload_ledger": 163,
        "attempt_records_created": 0, "execution_start_records_created": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

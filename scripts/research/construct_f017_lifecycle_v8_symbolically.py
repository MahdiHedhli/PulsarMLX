#!/usr/bin/env python3
"""Construct every F017 V8 lifecycle outcome from real canonical bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from check_f017_transitive_artifact_closure_v8 import validate_package


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
CHECKPOINT_METADATA = json.loads((ROOT / "docs/validation/glm52-checkpoint.json").read_bytes())
GRAPH_SHARD_SIZES = {ordinal: record["size_bytes"] for ordinal, record in enumerate(CHECKPOINT_METADATA["files"], start=1) if ordinal >= 2}


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def payload_for(artifact_id: str, keys: list[str], outcome: str, constants: dict | None = None) -> dict:
    value: dict[str, object] = {}
    for key in keys:
        if key in {"descriptor_count", "inherited_descriptor_count", "lease_count", "retained_lease_count", "expected_leases", "attempted_closures", "successful_closures"}:
            value[key] = 5
        elif key in {"identity_only_retained_count", "duplicate_closures", "unknown_leases", "live_leases_after_release", "path_reopen_count", "checkpoint_opens", "checkpoint_reads", "side_effect_count"}:
            value[key] = 0
        elif key in {"package_delta", "primary_delta", "secondary_delta", "delta"}:
            value[key] = 0
        elif key in {"ordinals"}:
            value[key] = [2, 3, 4, 5, 6]
        elif key == "lease_ids":
            value[key] = [f"LEASE-{ordinal}" for ordinal in range(2, 7)]
        elif key == "descriptor_identities":
            value[key] = [{"device": 1, "inode": 1000 + ordinal, "mode": 33024, "size": GRAPH_SHARD_SIZES[ordinal], "mtime_ns": 1, "ctime_ns": 1, "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD", "lease_id": f"LEASE-{ordinal}"} for ordinal in range(2, 7)]
        elif key in {"expected_total_bytes", "observed_total_bytes"}:
            value[key] = 238458632928
        elif key == "event_count":
            value[key] = 6
        elif key in {"expected_size", "observed_size"}:
            ordinal = int(artifact_id.rsplit("_", 1)[-1]) if artifact_id[-1].isdigit() else 0
            value[key] = ordinal * 4096
        elif key in {"expected_checkpoint_digest", "observed_checkpoint_digest", "prior_event_digest", "terminal_event_digest", "candidate_digest", "installed_digest", "checkpoint_set_digest"}:
            value[key] = hashlib.sha256(f"{artifact_id}:{key}".encode()).hexdigest()
        elif "digest" in key:
            value[key] = hashlib.sha256(f"{artifact_id}:{key}".encode()).hexdigest()
        elif key == "ordered_shard_receipt_digests":
            value[key] = [hashlib.sha256(f"receipt:{ordinal}".encode()).hexdigest() for ordinal in range(1, 7)]
        elif key in {"event_04_executed"}:
            value[key] = False
        elif key in {"original_checkpoint_access", "layers_completed"}:
            value[key] = 0
        elif key in {"synthetic_only", "mandatory_stop"}:
            value[key] = True
        elif key == "frozen_thresholds":
            value[key] = {"max_abs": 0.0065169706285814755, "rmse": 0.003463567697419031, "cosine_min": 0.9999999985448085, "top_n": 32}
        elif key == "operator_approval_id":
            value[key] = "F017-V8-SYMBOLIC-OPERATOR-APPROVAL"
        elif key == "owner_nonce":
            value[key] = "F017-V8-SYMBOLIC-OWNER-NONCE"
        elif key == "package_ledger_entry_id":
            value[key] = "F017-V8-SYMBOLIC-PACKAGE-LEDGER"
        elif key == "event_id":
            value[key] = f"F017-V8-SYMBOLIC-{'PRIMARY' if artifact_id.startswith('primary') else 'SECONDARY'}-EVENT"
        else:
            value[key] = f"{artifact_id}:{key}"
    value.update(constants or {})
    return value


def construct_outcome(outcome: str, package_root: Path, dag: dict, schemas: dict, obligations: dict) -> dict:
    required = set(obligations["outcomes"][outcome]["required"])
    forbidden = set(obligations["outcomes"][outcome]["forbidden"])
    roots = dag["root_authorities"]
    created: dict[str, str] = {}
    for node in sorted(dag["nodes"], key=lambda item: item["creation_rank"]):
        artifact_id = node["artifact_id"]
        if artifact_id not in required:
            continue
        if artifact_id in forbidden:
            raise ValueError(f"required and forbidden: {outcome}:{artifact_id}")
        dependency_shas = {}
        for dependency_id in node["dependencies"]:
            if dependency_id not in created:
                raise ValueError(f"future or absent dependency: {outcome}:{artifact_id}:{dependency_id}")
            dependency_shas[dependency_id] = created[dependency_id]
        descriptor = schemas["artifacts"][artifact_id]
        terminal_artifact = artifact_id == "final_declaration" or artifact_id.startswith("failure_terminal_capsule__")
        value = {
            "schema": descriptor["schema_id"],
            "artifact_id": artifact_id,
            "artifact_kind": node["artifact_kind"],
            "authorization_id": "F017-V8-SYMBOLIC-AUTHORIZATION",
            "package_attempt_id": "F017-V8-SYMBOLIC-PACKAGE",
            "outcome": outcome if terminal_artifact else "PENDING",
            "creation_rank": node["creation_rank"],
            "dependencies": dependency_shas,
            "root_authorities": {key: item["sha256"] for key, item in roots.items()},
            "payload": payload_for(artifact_id, descriptor["payload_keys"], outcome, descriptor.get("payload_constants")),
            "result": "FAILURE_EVIDENCE" if artifact_id.startswith("failure_terminal_capsule__") else "PASS",
        }
        if artifact_id.startswith("failure_terminal_capsule__"):
            expected = value["payload"]["expected_leases"]
            value["payload"].update({"attempted_closures": expected, "successful_closures": expected, "duplicate_closures": 0, "unknown_leases": 0})
        for key, rule in descriptor["payload_rules"].items():
            if rule["kind"] == "EQUAL_PAYLOAD_FIELD":
                value["payload"][key] = value["payload"][rule["field"]]
            elif rule["kind"] == "EQUAL_ARTIFACT_PAYLOAD_FIELD":
                referenced = json.loads((package_root / f"{rule['artifact_id']}.json").read_bytes())
                value["payload"][key] = referenced["payload"][rule["field"]]
            elif rule["kind"] == "ARTIFACT_SHA256":
                value["payload"][key] = created[rule["artifact_id"]]
            elif rule["kind"] == "ARTIFACT_SHA256_SEQUENCE":
                value["payload"][key] = [created[item] for item in rule["artifact_ids"]]
            elif rule["kind"] == "OUTCOME_CLASSIFICATION_ENUM":
                value["payload"][key] = rule["success_values"][0] if outcome == "COMPLETE_SUCCESS" else rule["failure_values"][0]
            elif rule["kind"] == "EQUAL_ENVELOPE_FIELD":
                value["payload"][key] = value[rule["field"]]
        if list(value) != descriptor["keys"]:
            raise ValueError(f"schema key order mismatch: {artifact_id}")
        if sorted(value["payload"]) != sorted(descriptor["payload_keys"]):
            raise ValueError(f"payload key census: {artifact_id}")
        raw = canonical(value)
        path = package_root / f"{artifact_id}.json"
        path.write_bytes(raw)
        created[artifact_id] = hashlib.sha256(raw).hexdigest()
    actual = {path.stem for path in package_root.glob("*.json")}
    if actual != required:
        raise ValueError(f"artifact set mismatch: {outcome}:missing={sorted(required-actual)}:unexpected={sorted(actual-required)}")
    if "descriptor_lease_manifest" in created:
        lease_payload = json.loads((package_root / "descriptor_lease_manifest.json").read_bytes())["payload"]
        for report_id in ("primary_descriptor_continuity_report", "secondary_descriptor_continuity_report"):
            if report_id not in created:
                continue
            report_payload = json.loads((package_root / f"{report_id}.json").read_bytes())["payload"]
            if report_payload["descriptor_count"] != 5 or report_payload["ordinals"] != [2, 3, 4, 5, 6] or report_payload["path_reopen_count"] != 0:
                raise ValueError(f"continuity report census: {outcome}:{report_id}")
            if report_payload["lease_ids"] != lease_payload["lease_ids"] or report_payload["descriptor_identities"] != lease_payload["descriptor_identities"]:
                raise ValueError(f"continuity report identity mismatch: {outcome}:{report_id}")
    if outcome == "COMPLETE_SUCCESS":
        terminals = ["final_declaration"] if "final_declaration" in required else []
    else:
        terminals = [item for item in required if item.startswith("failure_terminal_capsule__")]
    if len(terminals) != 1:
        raise ValueError(f"terminal census: {outcome}:{terminals}")
    closure = validate_package(package_root, terminals[0], required, roots, dag, schemas, outcome)
    return {"outcome": outcome, "artifact_count": len(created), "terminal_id": terminals[0], "terminal_sha256": created[terminals[0]], "closure": closure}


def validate_all(output_root: Path | None = None) -> dict:
    dag = json.loads((CONTRACTS / "f017-corrected-oracle-causal-artifact-dag-v8.json").read_bytes())
    schemas = json.loads((CONTRACTS / "f017-corrected-oracle-artifact-schemas-v8.json").read_bytes())
    obligations = json.loads((CONTRACTS / "f017-corrected-oracle-outcome-obligations-v8.json").read_bytes())
    holder = tempfile.TemporaryDirectory() if output_root is None else None
    root = Path(holder.name) if holder else output_root
    assert root is not None
    results = []
    for outcome in obligations["outcomes"]:
        package = root / outcome.lower()
        package.mkdir(parents=True, exist_ok=False)
        results.append(construct_outcome(outcome, package, dag, schemas, obligations))
    rank_by_id = {item["artifact_id"]: item["creation_rank"] for item in dag["nodes"]}
    self_references = sum(dependency == item["artifact_id"] for item in dag["nodes"] for dependency in item["dependencies"])
    future_references = sum(rank_by_id[dependency] >= item["creation_rank"] for item in dag["nodes"] for dependency in item["dependencies"])
    summary = {
        "schema": "pulsarmlx.f017.v8-symbolic-construction-result/1.0.0",
        "result": "PASS",
        "legal_outcome_count": len(results),
        "constructed_outcomes": len(results),
        "real_artifacts_created": sum(item["artifact_count"] for item in results),
        "canonical_shas_computed": sum(item["artifact_count"] for item in results),
        "unsatisfied_outcomes": 0,
        "self_references": self_references,
        "future_references": future_references,
        "strict_rank_edges_validated": sum(item["closure"]["strict_rank_edges_validated"] for item in results),
        "maximum_closure_depth": max(item["closure"]["maximum_closure_depth"] for item in results),
        "original_checkpoint_access": 0,
        "outcomes": results,
    }
    if output_root is not None:
        (output_root / "summary.json").write_bytes(canonical(summary))
    if holder:
        holder.cleanup()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_all(args.output_root), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()

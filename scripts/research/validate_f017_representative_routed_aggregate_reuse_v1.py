#!/usr/bin/env python3
"""Fail-closed validator for representative routed-aggregate reuse v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-reuse-authorization-v1.json"
SEMANTICS = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-input-semantics-v1.json"
RESOLVER = ROOT / "scripts/research/f017_representative_routed_aggregate_reuse_v1.py"
BASE_HEAD = "b22d3bab0b290aa5ea536d6efc114dddc6044086"
OUTPUT_SHA = "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9"
MANIFEST_SHA = "2403f7b321139d85c811e722298ac4bb164ffd3b0e41e1c73ed7fadd10e55d11"

SOURCES = {
    "execution_evidence": "fd362662a72ee6c4a951432d0ceb603a1f31ba7f62b885059e9f05c1df673d43",
    "arithmetic_contract": "ef4b6f5c4e66efd031d6fba1fafee087e5496dd16b5b6f658204359f89762da2",
    "aggregate_authorization": "d103ab6abc81cbeffea1c95553ba70b41cd7c430b403b39bcf2542d6cc4d3590",
    "single_use_release": "978908b1e3eac07c4a9565ed307122034d9cc8c797807ec788f9c521d2d5b98d",
    "independent_release_approval": "542a434b68b3f92ca6062c5c2fb93f1bae3a775214b78b2848e8bbec22eab334",
}


class ValidationError(ValueError):
    pass


def req(value: bool, message: str) -> None:
    if not value:
        raise ValidationError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    def no_dups(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            req(key not in result, f"duplicate key: {key}")
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=no_dups)
    req(isinstance(value, dict), "object required")
    return value


def validate(doc: dict[str, Any], *, repo: bool) -> None:
    req(doc.get("schema_version") == "1.0.0", "schema version")
    req(doc.get("authorization_id") == "F017-REPRESENTATIVE-ROUTED-AGGREGATE-REUSE-1", "authorization id")
    req(doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "state")
    req(doc.get("preparation_base_head") == BASE_HEAD, "wrong head")

    sources = doc.get("source_authority", {})
    req(set(sources) == set(SOURCES), "source census")
    for key, expected in SOURCES.items():
        req(sources[key].get("sha256") == expected, f"source identity: {key}")
        if repo:
            req(sha(ROOT / sources[key]["path"]) == expected, f"source bytes: {key}")
    evidence = sources["execution_evidence"]
    req(evidence.get("result") == "SUCCESS" and evidence.get("terminal") == "COMPLETE", "execution completion")
    req(evidence.get("reconstructed_terminal") == "COMPLETE_RECONSTRUCTED", "reconstructed completion")

    manifest = doc.get("private_manifest", {})
    req(manifest == {
        "relative_path": "routed-aggregate-private-manifest-v1.json",
        "sha256": MANIFEST_SHA,
        "byte_length": 1370,
        "machine_local_root_not_committed": True,
        "machine_local_path_not_published": True,
        "regular_file": True,
        "non_symlink": True,
        "hard_link_count": 1,
        "read_only": True,
    }, "private manifest")

    artifact = doc.get("retained_aggregate", {})
    req(artifact.get("relative_path") == "routed-aggregate.f64le", "aggregate path")
    req(artifact.get("sha256") == OUTPUT_SHA, "aggregate SHA")
    req(artifact.get("semantic_role") == "REPRESENTATIVE_M1F0_ROUTED_AGGREGATE_PROOF_REFERENCE", "semantic role")
    req(artifact.get("semantic_surface") == "CANONICAL_F017_PROOF_REFERENCE_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32", "semantic surface")
    req(artifact.get("dtype") == "little-endian-f64" and artifact.get("shape") == [6144] and artifact.get("byte_length") == 49152, "aggregate geometry")
    for key in ("finite", "expected_equals_before_equals_consumed_equals_after", "open_once_consume_same_descriptor",
                "fstat_before_and_after", "regular_file", "non_symlink", "read_only", "no_writable_alias"):
        req(artifact.get(key) is True, f"aggregate identity: {key}")
    req(artifact.get("hard_link_count") == 1, "aggregate link count")

    surface = doc.get("surface_isolation", {})
    req(surface == {
        "proof_reference_surface_required": True,
        "production_serial_f32_authority": False,
        "surface_conversion_authorized": False,
        "serial_f32_substitution_authorized": False,
        "aggregate_recomputation_fallback": False,
        "alternate_aggregate_output": False,
        "historical_direct_dprefix_aggregate": False,
    }, "surface isolation")

    resolver = doc.get("resolver", {})
    req(resolver.get("sha256") == sha(RESOLVER), "resolver SHA")
    for capability in ("checkpoint_capability", "shard_capability", "aggregate_compute_capability",
                       "shared_expert_compute_capability", "ffn_compute_capability", "s2_compute_capability"):
        req(resolver.get(capability) is False, f"resolver capability: {capability}")

    downstream = doc.get("downstream_semantics", {})
    req(downstream.get("sha256") == sha(SEMANTICS), "downstream semantics SHA")
    req(downstream.get("representative_shared_output_status") == "NOT_YET_COMPUTED", "shared status")
    req(downstream.get("next_authority") == "REPRESENTATIVE_SHARED_EXPERT_RECOVERY_AUTHORIZATION", "next authority")
    req(downstream.get("next_phase_checkpoint_free") is True, "next phase checkpoint-free")
    sem = load(SEMANTICS)
    req(sem.get("status") == "FROZEN_PREPARATION_ONLY_NO_EXECUTION_AUTHORITY", "semantics status")
    shared = sem.get("representative_surfaces", {}).get("Shared", {})
    req(shared.get("input") == "F_norm" and shared.get("representative_output_status") == "NOT_YET_COMPUTED", "shared input surface")
    req(sem.get("shared_expert_next_boundary", {}).get("physical_availability") == "3_OF_3_RETAINED_READ_ONLY_SINGLE_LINK_HASH_VERIFIED", "shared weights availability")
    req(sem.get("shared_expert_next_boundary", {}).get("authority_gap") == "SEPARATE_APPEND_ONLY_CROSS_EVENT_WEIGHT_REUSE_AND_REPRESENTATIVE_SHARED_EXPERT_EXECUTION_AUTHORIZATION_REQUIRED", "shared authority gap")

    consumer = doc.get("consumer_scope", {})
    req(consumer.get("allowed") == "CHECKPOINT_FREE_DOWNSTREAM_PREPARATION_AND_FFN_COMPOSITION_INPUT_AUTHORITY_ONLY", "consumer scope")
    for key in ("shared_expert_execution", "routed_shared_combination", "ffn_completion", "s2_construction"):
        req(consumer.get(key) is False, f"consumer execution: {key}")

    req(doc.get("accounting") == {
        "real_payload_ledger_before": 175,
        "real_payload_ledger_after": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "aggregate_recomputations": 0,
        "shared_expert_executions": 0,
        "ffn_completions": 0,
        "s2_constructions": 0,
    }, "accounting")
    history = doc.get("historical_immutability", {})
    req(history.get("historical_direct_dprefix_shared_output") == "VALID_BUT_DIFFERENT_SURFACE", "historical shared output")
    req(history.get("historical_direct_dprefix_aggregate") == "VALID_BUT_DIFFERENT_SURFACE", "historical aggregate")
    req(history.get("real_payload_ledger") == 175, "ledger")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.authorization), repo=not args.no_repo)
    print("REPRESENTATIVE_ROUTED_AGGREGATE_REUSE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

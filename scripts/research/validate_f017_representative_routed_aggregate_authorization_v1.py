#!/usr/bin/env python3
"""Fail-closed validator for routed-aggregate authorization v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUTH_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-authorization-v1.json"
START_HEAD = "87d65a91e998ca9513262982e6453d8eb003178d"
IDS = [250, 10, 237, 62, 73, 177, 218, 28]
WEIGHTS = [0.7487501576296707, 0.3348627106807668, 0.23863270273063697, 0.23688715675086147,
           0.2514906203405492, 0.23059957299763345, 0.22915341148588297, 0.22962366738399842]
OUTPUTS = ["0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b",
           "d9adb474f64c98349dfe0a6c768b2020b27f62ecc85874975c990b880ef304b3",
           "4ac842afb3b1909f9f0e07013c86bbdca90cd246b6190bf190a60fe9767fdd9b",
           "2550cccf9b2f1a83b2e2f03f090ee135dc525a15eaf1bab18d1a2fb97af16128",
           "9aa5e1dae2619c440c65689154de332da313990b4ba07fdac45e78a65ad3a7d3",
           "18260d4936483b6f7d83d2d0ec72d01fc761f2ac5726fa9b7bda243a4db9a201",
           "f4a8fc1e3bb91a8a5635505f766a07ef2cfb135378d224ed5f545617d781537d",
           "45029a47061c43746344d5b0a9366b8129630019a3196d0be146efc5e1a361f0"]
HISTORICAL_DIRECT_OUTPUT = "6479a8352a355d5f979172bc19038d44b4df992925fab427d2caeaf24445efdc"
BINDINGS = {
    "expert_output_reuse_authorization": "1b8b053d60f87c9da8c8c81a41a3d82f7652859a2464941c39b5a1eab3d7c070",
    "expert_output_reuse_review": "54d559fe39c13152c2c368fa1f99a219c167178b06d58f47bb46822af33b46bc",
    "expert_execution_evidence": "fe1cad02405b74d9000afec915bdf7e772e6dd77c13b7e4cc5b5db35606b51e4",
    "semantic_adjudication": "ab6d9305a2392ceda77728b7892868e0310c56f20c0636ab67ffd2154adb0636",
    "arithmetic_contract": "ef4b6f5c4e66efd031d6fba1fafee087e5496dd16b5b6f658204359f89762da2",
    "executor": "fa85558686caa3a57ca356d7e49e5d73ca1f7cb512c1148b670ce0f504e921d5",
    "synthetic_rehearsal": "064d938d5ac2b3bd8a9ed0a6633ec94a25f12c7e7f49f4a3c53c6c059e4f4dcc",
}


class ValidationError(ValueError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load(path: Path) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            req(key not in out, f"duplicate key: {key}")
            out[key] = value
        return out
    obj = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    req(isinstance(obj, dict), "object required")
    return obj


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(doc: dict[str, Any], *, repo: bool) -> None:
    req(doc.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-authorization", "schema")
    req(doc.get("schema_version") == "1.0.0", "schema version")
    req(doc.get("authorization_id") == "F017-REPRESENTATIVE-ROUTED-AGGREGATE-AUTHORIZATION-1", "authorization id")
    req(doc.get("event_id") == "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1", "event id")
    req(doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "state")
    req(doc.get("preparation_head") == START_HEAD, "head")
    req(doc.get("aggregate_semantic_classification") == "CANONICAL_F017_PROOF_REFERENCE_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32", "classification")
    for key, identity in BINDINGS.items():
        item = doc.get(key, {})
        req(item.get("sha256") == identity, f"binding: {key}")
        if repo:
            req(sha(ROOT / item["path"]) == identity, f"binding bytes: {key}")
    req(doc.get("private_output_package") == {"manifest_sha256": "2b3a0ef3bb2d896dd04add67e6fc729b2b400170b58f9038751cee612d58bc7a", "output_count": 8, "output_bytes": 196608, "machine_local_paths_published": False}, "private package")
    req(doc.get("representative_expert_input_sha256") == "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c", "expert input")
    triples = doc.get("atomic_id_weight_output_triples")
    req(isinstance(triples, list) and len(triples) == 8, "triple count")
    req([x.get("ordinal") for x in triples] == list(range(8)), "ordinals")
    req([x.get("expert_id") for x in triples] == IDS, "IDs/order")
    req([x.get("routing_weight") for x in triples] == WEIGHTS, "weights/pairing")
    req([x.get("output_sha256") for x in triples] == OUTPUTS, "outputs/pairing")
    req(HISTORICAL_DIRECT_OUTPUT not in [x.get("output_sha256") for x in triples], "historical output")
    for i, item in enumerate(triples):
        req(item.get("private_relative_path") == f"{i:02d}-expert-{IDS[i]}-down.f32le", "path")
        req(item.get("dtype") == "little-endian-f32" and item.get("shape") == [6144] and item.get("byte_length") == 24576, "input surface")
    if repo:
        reuse = load(ROOT / doc["expert_output_reuse_authorization"]["path"])
        evidence = load(ROOT / doc["expert_execution_evidence"]["path"])
        req(reuse.get("atomic_id_weight_output_triples") == [dict(x, semantic_role="REPRESENTATIVE_M1F0_ROUTED_EXPERT_OUTPUT") for x in triples], "reuse producer schema")
        evidence_join = []
        weights_by_id = {x["expert_id"]: x["routing_weight"] for x in evidence["id_weight_pairs"]}
        for output in evidence["outputs"]:
            evidence_join.append({"ordinal": output["ordinal"], "expert_id": output["expert_id"],
                                  "routing_weight": weights_by_id[output["expert_id"]],
                                  "private_relative_path": output["private_relative_path"], "output_sha256": output["sha256"],
                                  "dtype": output["dtype"], "shape": output["shape"], "byte_length": output["byte_length"]})
        req(evidence_join == triples, "execution producer schema")
    preflight = doc.get("preflight", {})
    expected_preflight = {"expected_equals_before_equals_consumed_equals_after", "open_directory_once",
                          "open_leaf_once_relative_to_validated_directory_descriptor", "same_validated_descriptor_consumed",
                          "fstat_before_after_device_inode_equal", "regular_file", "non_symlink", "read_only",
                          "no_writable_alias", "finite", "private_manifest_verified_before_outputs",
                          "historical_direct_dprefix_output_rejected"}
    req(all(preflight.get(k) is True for k in expected_preflight), "preflight booleans")
    req(preflight.get("hard_link_count") == 1 and preflight.get("exact_size") == 24576 and preflight.get("dtype") == "little-endian-f32" and preflight.get("shape") == [6144], "preflight surface")
    arithmetic = load(ROOT / doc["arithmetic_contract"]["path"])
    req(arithmetic.get("semantic_classification") == doc.get("aggregate_semantic_classification"), "arithmetic classification")
    req(arithmetic.get("canonical_order") == IDS and arithmetic.get("dimension") == 6144, "arithmetic order/shape")
    algorithm = arithmetic.get("algorithm", {})
    req(algorithm.get("accumulation") == "call CPython math.fsum exactly once on the ordered tuple of eight binary64 products for each coordinate", "fsum algorithm")
    req(algorithm.get("equivalence_policy") == "DIRECT_CALL_NOT_REIMPLEMENTATION; no substitute fsum-equivalent implementation is accepted", "fsum identity")
    req(arithmetic.get("output") == {"dtype": "little-endian-f64", "shape": [6144], "byte_length": 49152, "serialization": "contiguous-c-order-ieee754-binary64-little-endian", "packing": "struct.pack_into('<d', output, 8*k, M[k]) in increasing coordinate order", "finite": True}, "arithmetic output")
    req(all(arithmetic.get("forbidden_arithmetic", {}).values()), "forbidden arithmetic")
    req(arithmetic.get("production_surface_separation", {}).get("relationship") == "DIFFERENT_NUMERICAL_SURFACE" and arithmetic["production_surface_separation"].get("authorization") == "NOT_AUTHORIZED_BY_THIS_CONTRACT", "surface separation")
    executor = doc.get("executor", {})
    for key in ("checkpoint_interface", "shard_interface", "expert_execution_interface", "blas", "parallel_reduction", "gpu"):
        req(executor.get(key) is False, f"executor capability: {key}")
    req(executor.get("future_approved_single_use_release_required") is True, "future release")
    rehearsal = load(ROOT / doc["synthetic_rehearsal"]["path"])
    req(rehearsal.get("result") == "PASS" and rehearsal.get("fresh_processes") == 2 and rehearsal.get("exact_identity") is True, "rehearsal")
    req(rehearsal.get("real_representative_output_bytes_used") is False and rehearsal.get("real_aggregate_executions") == 0, "rehearsal isolation")
    req(rehearsal.get("fresh_process_protected_output_rejection") == "PASS_RC_2", "synthetic protected-output gate")
    single = doc.get("future_single_use", {})
    req(single == {"event_id": "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1", "release_id": "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1-RELEASE-1", "attempt_id": "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1-ATTEMPT-1", "approved_release_required": True, "state_root_required": True, "consumed_at": "DURABLE_ATTEMPT_START_BEFORE_AGGREGATE_COMPUTATION", "exclusive_state_root_creation": True, "prior_attempt_state_rejected": True, "existing_output_rejected": True, "terminal_written_on_success_or_caught_failure": True, "crash_after_attempt_start": "CONSUMED_NO_RETRY_MANUAL_RECONCILIATION_REQUIRED", "retry": False, "resume": False, "second_attempt": False}, "single use")
    req(doc.get("future_output") == {"dtype": "little-endian-f64", "shape": [6144], "byte_length": 49152, "serialization": "contiguous-c-order-ieee754-binary64-little-endian", "finite": True, "concrete_sha256": "NOT_COMPUTED_UNTIL_SEPARATELY_RELEASED_EVENT"}, "future output")
    req(doc.get("accounting") == {"starting_ledger": 175, "terminal_ledger": 175, "preparation_checkpoint_reads": 0, "preparation_shard_opens": 0, "preparation_expert_executions": 0, "preparation_aggregate_executions": 0, "future_checkpoint_read_budget": 0, "future_shard_open_budget": 0, "future_expert_execution_budget": 0, "future_aggregate_execution_count": 1}, "accounting")
    req(doc.get("stop_boundary") == "AFTER_ROUTED_AGGREGATE_ONLY", "stop boundary")
    prohibitions = doc.get("prohibitions", {})
    req(set(prohibitions) == {"production_serial_f32_surface", "historical_direct_dprefix_output", "checkpoint_access", "shard_open", "expert_execution", "shared_expert", "ffn_completion", "residual_addition", "s2_construction", "retry_without_future_release", "go_token_in_this_phase", "synthetic_use_of_representative_output_identity"} and all(prohibitions.values()), "prohibitions")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH_PATH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.authorization), repo=not args.no_repo)
    print("REPRESENTATIVE_ROUTED_AGGREGATE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

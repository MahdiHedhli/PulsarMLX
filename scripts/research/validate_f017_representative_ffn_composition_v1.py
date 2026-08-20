#!/usr/bin/env python3
"""Fail-closed validator for shared-output reuse and FFN composition v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SHARED_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-output-reuse-authorization-v1.json"
FFN_AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-authorization-v1.json"
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-arithmetic-v1.json"
S1_AUTHORITY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-authority-v1.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_ffn_composition_executor_v1.py"
REHEARSAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-ffn-composition-synthetic-rehearsal-v1.json"

START_HEAD = "17f719602c089af57a2c3bdee74f2b140a9c8d38"
SHARED_SHA = "8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b"
ROUTED_SHA = "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9"
S1_SHA = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
SHARED_MANIFEST_SHA = "fbdfb87783e72f011207cb06007cb91e955f6f824d96522f149fcb0d37d4ea52"
ROUTED_MANIFEST_SHA = "2403f7b321139d85c811e722298ac4bb164ffd3b0e41e1c73ed7fadd10e55d11"
SHARED_REUSE_SHA = "3642200f50f2ed7140243cd885dfe8c3d8628f5605ab37467cc342ea6376019a"
ROUTED_REUSE_SHA = "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb"
ARITHMETIC_SHA = "1054d014c23628fa56771518f066d14cfd445b0d7b4ba7da98b638c37981cdbb"
S1_AUTHORITY_SHA = "7a77f7dbadd6753a7598c3d7be7a94b393b56d25a7fa778de0c9f71c1f3a6728"
EXECUTOR_SHA = "7632b19af4a0b3bb16ec7032cec049bcab45dabd246cac5d77f0daaec24d256c"
REHEARSAL_SHA = "04c0448a124d36a7510650d725e09d1cc5f2ce66b0c8ee944da0b831a8d67a60"
HISTORICAL_SHARED_SHA = "01dbd9ac75091fcd452ac9bb1bc2479ccdebc0bc7ac46d79285ff45d70e5928d"


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in output, f"duplicate key: {key}")
            output[key] = value
        return output
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    require(isinstance(value, dict), "object required")
    return value


def validate_shared_reuse(document: dict[str, Any], *, repo: bool) -> None:
    require(document.get("schema") == "pulsarmlx.f017.representative-shared-expert-output-reuse-authorization", "shared schema")
    require(document.get("schema_version") == "1.0.0", "shared version")
    require(document.get("authorization_id") == "F017-REPRESENTATIVE-SHARED-EXPERT-OUTPUT-REUSE-1", "shared id")
    require(document.get("consumer_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1", "shared consumer")
    require(document.get("preparation_base_head") == START_HEAD, "shared head")
    require(document.get("status") == "PREPARED_REVIEW_REQUIRED" and document.get("real_event_authorized") is False, "shared state")
    sources = document.get("source_authority", {})
    expected_sources = {
        "execution_evidence": "b7e3d8a6d97f2c3771ed7a6ff07ee97176780089b60787ac45ebd0af3ce33bb6",
        "recovery_authorization": "45b25de7978e01898eb5ea948202d70d5b43f33c2cbc84ec7b11a9955c5d9596",
        "single_use_release": "d582d296e2c031f354f7191d3027bb9dac74f3b638377ba5bcfe155c8ee0f37f",
        "independent_release_approval": "9e6b9ce6f71a4f6ede3510a2aed038ddb9b048c032e79966623e6c302f324b28",
    }
    require(set(sources) == set(expected_sources), "shared source census")
    for name, identity in expected_sources.items():
        require(sources[name].get("sha256") == identity, f"shared source: {name}")
        if repo:
            require(sha(ROOT / sources[name]["path"]) == identity, f"shared source bytes: {name}")
    evidence = sources["execution_evidence"]
    require(evidence.get("result") == "SUCCESS" and evidence.get("terminal") == "COMPLETE", "shared complete")
    require(evidence.get("reproduction") == "2_OF_2_FRESH_PROCESS_EXACT_IDENTITY", "shared reproduction")

    require(document.get("private_manifest") == {
        "relative_path": "representative-shared-expert-output-private-manifest-v1.json",
        "sha256": SHARED_MANIFEST_SHA,
        "byte_length": 1325,
        "machine_local_root_not_committed": True,
        "machine_local_absolute_path_not_committed": True,
        "regular_file": True,
        "non_symlink": True,
        "hard_link_count": 1,
        "read_only": True,
    }, "shared manifest")
    artifact = document.get("retained_shared_output", {})
    require(artifact.get("relative_path") == "representative-shared-expert-output.f32le", "shared path")
    require(artifact.get("sha256") == SHARED_SHA, "shared SHA")
    require(artifact.get("semantic_role") == "REPRESENTATIVE_M1F0_SHARED_EXPERT_OUTPUT", "shared role")
    require(artifact.get("semantic_surface") == "CANONICAL_REPRESENTATIVE_POST_ATTENTION_SHARED_EXPERT_STRICT_F32_SURFACE", "shared surface")
    require(artifact.get("dtype") == "little-endian-f32" and artifact.get("shape") == [6144] and artifact.get("byte_length") == 24576, "shared geometry")
    for field in ("finite", "expected_equals_before_equals_consumed_equals_after", "open_once_consume_same_descriptor", "fstat_before_and_after", "regular_file", "non_symlink", "read_only", "no_writable_alias"):
        require(artifact.get(field) is True, f"shared retention: {field}")
    require(artifact.get("hard_link_count") == 1, "shared links")
    isolation = document.get("surface_isolation", {})
    require(isolation.get("historical_direct_dprefix_shared_output") is False and isolation.get("historical_shared_output_sha256") == HISTORICAL_SHARED_SHA, "historical shared exclusion")
    for field in ("shared_expert_recomputation_fallback", "checkpoint_fallback", "alternate_shared_output", "surface_conversion_authorized"):
        require(isolation.get(field) is False, f"shared isolation: {field}")
    resolver = document.get("resolver", {})
    if repo:
        require(sha(ROOT / resolver["path"]) == resolver.get("sha256"), "shared resolver bytes")
    for capability in ("checkpoint_capability", "shard_capability", "shared_expert_compute_capability", "routed_aggregate_compute_capability", "ffn_compute_capability", "s2_compute_capability"):
        require(resolver.get(capability) is False, f"shared resolver capability: {capability}")
    consumer = document.get("consumer_scope", {})
    require(consumer.get("allowed") == "CHECKPOINT_FREE_FFN_COMPOSITION_PREPARATION_AND_INPUT_AUTHORITY_ONLY", "shared scope")
    for field in ("routed_shared_combination", "ffn_completion", "s2_construction", "shared_expert_execution"):
        require(consumer.get(field) is False, f"shared scope execution: {field}")
    require(document.get("accounting") == {
        "real_payload_ledger_before": 175,
        "real_payload_ledger_after": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "shared_expert_recomputations": 0,
        "routed_aggregate_recomputations": 0,
        "ffn_completions": 0,
        "s2_constructions": 0,
    }, "shared accounting")
    if repo:
        execution = load(ROOT / sources["execution_evidence"]["path"])
        output = execution.get("output", {})
        require(output.get("sha256") == artifact.get("sha256") and output.get("dtype") == artifact.get("dtype") and output.get("shape") == artifact.get("shape") and output.get("byte_length") == artifact.get("byte_length"), "shared producer schema")
        require(execution.get("reproduction", {}).get("runs_passed") == 2 and execution.get("terminal", {}).get("disposition") == "COMPLETE", "shared producer completion")


def validate_ffn(document: dict[str, Any], *, repo: bool) -> None:
    require(document.get("schema") == "pulsarmlx.f017.representative-ffn-composition-authorization", "ffn schema")
    require(document.get("schema_version") == "1.0.0", "ffn version")
    require(document.get("authorization_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-AUTHORIZATION-1", "ffn id")
    require(document.get("event_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1", "ffn event")
    require(document.get("preparation_head") == START_HEAD, "ffn head")
    require(document.get("status") == "PREPARED_REVIEW_REQUIRED" and document.get("real_event_authorized") is False, "ffn state")
    require(document.get("semantic_classification") == "CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32", "ffn surface")
    expected_bindings = {
        "routed_reuse_authorization": ROUTED_REUSE_SHA,
        "routed_reuse_review": "49848c1f27e15360bb8514f6b9dbd32b523c73936af6218dcf6505fa3bdf36f8",
        "shared_reuse_authorization": SHARED_REUSE_SHA,
        "shared_execution_evidence": "b7e3d8a6d97f2c3771ed7a6ff07ee97176780089b60787ac45ebd0af3ce33bb6",
        "arithmetic_contract": ARITHMETIC_SHA,
        "s1_authority": S1_AUTHORITY_SHA,
        "semantic_graph": "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558",
        "executor": EXECUTOR_SHA,
        "synthetic_rehearsal": REHEARSAL_SHA,
    }
    bindings = document.get("bindings", {})
    require(set(bindings) == set(expected_bindings), "ffn binding census")
    for name, identity in expected_bindings.items():
        require(bindings[name].get("sha256") == identity, f"ffn binding: {name}")
        if repo:
            require(sha(ROOT / bindings[name]["path"]) == identity, f"ffn binding bytes: {name}")
    inputs = document.get("inputs", {})
    routed = inputs.get("routed", {})
    shared = inputs.get("shared", {})
    require(routed.get("reuse_authorization_sha256") == ROUTED_REUSE_SHA and shared.get("reuse_authorization_sha256") == SHARED_REUSE_SHA, "input reuse binding")
    require(routed.get("manifest", {}).get("sha256") == ROUTED_MANIFEST_SHA and shared.get("manifest", {}).get("sha256") == SHARED_MANIFEST_SHA, "input manifests")
    require(routed.get("artifact", {}).get("sha256") == ROUTED_SHA and shared.get("artifact", {}).get("sha256") == SHARED_SHA, "input SHA")
    require(routed["artifact"].get("dtype") == "little-endian-f64" and routed["artifact"].get("shape") == [6144] and routed["artifact"].get("byte_length") == 49152, "routed geometry")
    require(shared["artifact"].get("dtype") == "little-endian-f32" and shared["artifact"].get("shape") == [6144] and shared["artifact"].get("byte_length") == 24576, "shared geometry")
    preflight = document.get("preflight", {})
    for field in ("expected_equals_before_equals_consumed_equals_after", "open_directory_once", "open_leaf_once_relative_to_validated_directory_descriptor", "same_validated_descriptor_consumed", "regular_file", "non_symlink", "read_only", "no_writable_alias", "finite", "private_manifest_verified_before_input", "historical_inputs_rejected", "all_locally_checkable_failures_before_ffn_computation"):
        require(preflight.get(field) is True, f"preflight: {field}")
    require(preflight.get("hard_link_count") == 1, "preflight link count")
    arithmetic = document.get("arithmetic", {})
    require(arithmetic == {
        "formula": "FFN[k]=Routed[k]+binary64(Shared[k])",
        "routed_dtype": "little-endian-f64",
        "shared_dtype": "little-endian-f32",
        "shared_promotion": "exact IEEE-754 binary32-to-binary64",
        "shared_scalar_multiplier": "NONE; binary64 1.0",
        "addition_order": "Routed then promoted Shared",
        "addition_dtype": "IEEE-754 binary64",
        "rounding": "round-to-nearest ties-to-even",
        "coordinates": 6144,
        "parallelism": False,
        "blas": False,
        "gpu": False,
    }, "ffn arithmetic")
    contract = load(ARITHMETIC) if repo else None
    if repo:
        require(contract.get("algorithm", {}).get("formula") == arithmetic["formula"], "arithmetic producer formula")
        require(contract.get("output") == {
            "semantic_role": "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT",
            "dtype": "little-endian-f64", "shape": [6144], "byte_length": 49152,
            "serialization": "contiguous-c-order-ieee754-binary64-little-endian",
            "packing": "struct.pack_into('<d', output, 8*k, FFN[k]) in increasing coordinate order",
            "finite": True,
        }, "arithmetic producer output")
    executor = document.get("executor", {})
    require(executor.get("cli_real_execution_mode") is False and executor.get("future_single_use_wrapper_import_required") is True, "executor execution gate")
    for field in ("checkpoint_interface", "shard_interface", "expert_execution_interface", "shared_expert_execution_interface", "s2_interface", "production_serial_f32_fallback"):
        require(executor.get(field) is False, f"executor capability: {field}")
    if repo:
        source = EXECUTOR.read_text(encoding="utf-8")
        require('add_argument("--execute"' not in source, "executor CLI execute path")
        rehearsal = load(REHEARSAL)
        require(rehearsal.get("result") == "PASS" and rehearsal.get("fresh_processes") == 2 and rehearsal.get("exact_identity") is True and rehearsal.get("independent_exact_rational_oracle") is True, "rehearsal")
        require(rehearsal.get("real_routed_bytes_used") is False and rehearsal.get("real_shared_bytes_used") is False and rehearsal.get("real_ffn_completions") == 0, "rehearsal isolation")
    require(document.get("future_output") == {
        "semantic_role": "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT",
        "dtype": "little-endian-f64", "shape": [6144], "byte_length": 49152,
        "serialization": "contiguous-c-order-ieee754-binary64-little-endian",
        "finite": True, "concrete_sha256": "NOT_COMPUTED_UNTIL_SEPARATELY_RELEASED_EVENT",
    }, "future output")
    single = document.get("future_single_use", {})
    require(single == {
        "separate_independently_approved_release_required": True,
        "durable_attempt_start_before_ffn_computation": True,
        "exclusive_attempt_creation": True,
        "attempts": 1,
        "ffn_compositions": 1,
        "retry": False,
        "resume": False,
        "second_attempt": False,
    }, "single use")
    boundary = document.get("s1_and_s2_boundary", {})
    require(boundary.get("s1_sha256") == S1_SHA and boundary.get("s1_semantic_role") == "LAYER3_POST_ATTENTION_RESIDUAL", "s1 identity")
    require(boundary.get("s1_retention_classification") == "HASH_RETAINED_REPRODUCIBLE_NOT_BYTE_RETAINED", "s1 retention")
    require(boundary.get("s1_checkpoint_free_reconstruction_available") is True and boundary.get("s1_materialization_authorized") is False, "s1 availability")
    require(boundary.get("s2_formula") == "S2=f32(f64(S1)+FFN)" and boundary.get("s2_authorized") is False, "s2 boundary")
    if repo:
        s1 = load(S1_AUTHORITY)
        require(s1.get("sha256") == S1_SHA and s1.get("retention_classification") == "HASH_RETAINED_REPRODUCIBLE_NOT_BYTE_RETAINED", "s1 producer")
        m1f0 = load(ROOT / s1["source_authority"]["representative_m1f0_execution"]["path"])
        require(m1f0.get("stage_sha256", {}).get("post_attention_residual") == S1_SHA, "s1 execution producer")
    require(document.get("accounting") == {
        "starting_ledger": 175, "terminal_ledger": 175,
        "preparation_checkpoint_reads": 0, "preparation_shard_opens": 0,
        "preparation_expert_executions": 0, "preparation_shared_expert_executions": 0,
        "preparation_ffn_completions": 0, "preparation_s2_constructions": 0,
        "future_checkpoint_read_budget": 0, "future_shard_open_budget": 0,
        "future_expert_execution_budget": 0, "future_shared_expert_execution_budget": 0,
        "future_ffn_composition_count": 1, "future_s2_construction_budget": 0,
    }, "ffn accounting")
    prohibitions = document.get("prohibitions", {})
    require(set(prohibitions) == {
        "checkpoint_access", "shard_open", "expert_execution", "shared_expert_execution",
        "routed_aggregate_recomputation", "historical_direct_dprefix_aggregate",
        "historical_direct_dprefix_shared_output", "production_serial_f32_substitution",
        "s1_materialization_in_this_authorization", "s1_residual_addition", "s2_construction",
        "go_token_in_this_phase",
    } and all(prohibitions.values()), "ffn prohibitions")
    require(document.get("stop_boundary") == "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY", "stop boundary")
    if repo:
        routed_reuse = load(ROOT / bindings["routed_reuse_authorization"]["path"])
        shared_reuse = load(ROOT / bindings["shared_reuse_authorization"]["path"])
        require(routed_reuse.get("retained_aggregate", {}).get("sha256") == routed["artifact"]["sha256"], "routed producer schema")
        require(shared_reuse.get("retained_shared_output", {}).get("sha256") == shared["artifact"]["sha256"], "shared reuse producer schema")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-reuse", type=Path, default=SHARED_REUSE)
    parser.add_argument("--authorization", type=Path, default=FFN_AUTHORIZATION)
    parser.add_argument("--no-repo", action="store_true")
    arguments = parser.parse_args()
    validate_shared_reuse(load(arguments.shared_reuse), repo=not arguments.no_repo)
    validate_ffn(load(arguments.authorization), repo=not arguments.no_repo)
    print("REPRESENTATIVE_SHARED_OUTPUT_REUSE_AND_FFN_COMPOSITION_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

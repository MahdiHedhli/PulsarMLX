#!/usr/bin/env python3
"""Fail-closed validator for representative shared-expert authorization v1."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-authorization-v1.json"
PARAMETERS = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-parameter-reuse-v1.json"
COMPUTATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-computation-v1.json"
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-output-v1.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_shared_expert_recovery_executor_v1.py"
REHEARSAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-shared-expert-synthetic-rehearsal-v1.json"
BASE_HEAD = "a013096aa92881f23b11f4c8ebfb3b623f3b6800"

if str(ROOT / "scripts/research") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts/research"))
import f017_representative_shared_expert_recovery_executor_v1 as executor


class ValidationError(ValueError):
    pass


def req(value: bool, message: str) -> None:
    if not value:
        raise ValidationError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


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


def function_sha(value: Any) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def semantic_sha(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical({key: value for key, value in document.items() if key != "rehearsal"})).hexdigest()


def validate(doc: dict[str, Any], *, repo: bool) -> None:
    req(doc.get("schema") == "pulsarmlx.f017.representative-shared-expert-recovery-authorization", "schema")
    req(doc.get("schema_version") == "1.0.0", "schema version")
    req(doc.get("authorization_id") == "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-AUTHORIZATION-1", "authorization id")
    req(doc.get("event_id") == "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-1", "event id")
    req(doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "state")
    req(doc.get("preparation_base_head") == BASE_HEAD, "base head")

    upstream_expected = {
        "semantic_graph": "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558",
        "representative_boundary": "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3",
        "route_execution_evidence": "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190",
        "routed_aggregate_execution_evidence": "fd362662a72ee6c4a951432d0ceb603a1f31ba7f62b885059e9f05c1df673d43",
        "routed_aggregate_reuse": "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb",
        "routed_aggregate_reuse_review": "49848c1f27e15360bb8514f6b9dbd32b523c73936af6218dcf6505fa3bdf36f8",
    }
    upstream = doc.get("upstream_authority", {})
    req(set(upstream) == set(upstream_expected), "upstream census")
    for key, identity in upstream_expected.items():
        req(upstream[key].get("sha256") == identity, f"upstream {key}")
        if repo:
            req(sha(ROOT / upstream[key]["path"]) == identity, f"upstream bytes {key}")

    input_spec = doc.get("representative_input", {})
    req(input_spec == {
        "semantic_role": "CANONICAL_REPRESENTATIVE_POST_ATTENTION_FFN_NORMALIZED_SHARED_EXPERT_INPUT",
        "sha256": "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c",
        "private_manifest_sha256": "78f94815ca9402b398a3e11817ab94926a98feaf2447e455a7b18af31d8c78d2",
        "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576,
        "expected_equals_before_equals_consumed_equals_after": True,
        "open_once_consume_same_descriptor": True,
    }, "representative input")

    parameter_binding = doc.get("parameter_reuse", {})
    req(parameter_binding.get("sha256") == sha(PARAMETERS), "parameter contract sha")
    req(parameter_binding.get("private_manifest_sha256") == "c7669c26eb2520dd6857bde7eb7c18d84e29d8083759bac33f265781efb990e6", "parameter manifest")
    req(parameter_binding.get("consumer_id") == doc.get("event_id") and parameter_binding.get("checkpoint_fallback") is False, "parameter scope")
    parameter_doc = load(PARAMETERS)
    req(parameter_doc.get("consumer_id") == doc.get("event_id"), "parameter consumer")
    req(parameter_doc.get("packed_total_bytes") == 27623424 and parameter_doc.get("access") == {"checkpoint_reads": 0, "shard_opens": 0, "checkpoint_fallback": False, "alternate_parameter_authority": False}, "parameter access")
    req(doc.get("retained_parameters") == parameter_doc.get("parameters"), "parameter inventory")
    req(doc.get("parameter_manifest") == {"relative_path": "representative-shared-expert-weight-reuse-manifest-v1.json", "sha256": "c7669c26eb2520dd6857bde7eb7c18d84e29d8083759bac33f265781efb990e6", "byte_length": 1941, "machine_local_path_not_committed": True}, "manifest binding")

    computation_binding = doc.get("computation_contract", {})
    req(computation_binding.get("sha256") == sha(COMPUTATION), "computation sha")
    computation = load(COMPUTATION)
    req(computation.get("input", {}).get("sha256") == input_spec["sha256"], "computation input")
    arithmetic = computation.get("arithmetic", {})
    req(arithmetic.get("blas") is False and arithmetic.get("parallel_reduction") is False and arithmetic.get("gpu") is False, "computation backend")
    kernels = computation.get("runtime_kernel_identities", {})
    req(kernels == {"strict_f32_matvec": function_sha(executor.strict_f32_matvec), "strict_f32_silu": function_sha(executor.strict_f32_silu), "compute": function_sha(executor.compute)}, "kernel identities")
    for group in ("q5_k", "q6_k"):
        for decoder in ("decoder_a", "decoder_b"):
            binding = computation["decoders"][group][decoder]
            if repo:
                req(sha(ROOT / binding["path"]) == binding["source_sha256"], f"decoder source {group} {decoder}")

    output_binding = doc.get("output_contract", {})
    req(output_binding.get("sha256") == sha(OUTPUT), "output contract sha")
    req(output_binding.get("semantic_role") == "REPRESENTATIVE_M1F0_SHARED_EXPERT_OUTPUT", "output role")
    req(output_binding.get("dtype") == "little-endian-f32" and output_binding.get("shape") == [6144] and output_binding.get("byte_length") == 24576, "output geometry")
    output_doc = load(OUTPUT)
    req(output_doc.get("stop_boundary") == "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY", "output stop")
    req(output_doc.get("publication", {}).get("no_replace_hard_link_publish") is True, "output publication")

    executor_binding = doc.get("executor", {})
    req(executor_binding.get("sha256") == sha(EXECUTOR), "executor sha")
    for key in ("checkpoint_path_interface", "shard_path_interface", "arbitrary_inventory", "arbitrary_input", "arbitrary_output_role"):
        req(executor_binding.get(key) is False, f"executor interface {key}")

    rehearsal_binding = doc.get("rehearsal", {})
    req(rehearsal_binding.get("sha256") == sha(REHEARSAL), "rehearsal sha")
    req(rehearsal_binding.get("fresh_processes") == 2 and rehearsal_binding.get("exact_output_identity") == "2_OF_2" and rehearsal_binding.get("real_geometry") is True, "rehearsal contract")
    req(rehearsal_binding.get("checkpoint_reads") == 0 and rehearsal_binding.get("shard_opens") == 0 and rehearsal_binding.get("real_shared_expert_executions") == 0, "rehearsal accounting")
    rehearsal = load(REHEARSAL)
    req(rehearsal.get("result") == "PASS" and rehearsal.get("failure_cases_passed") == rehearsal.get("failure_case_count") == 23, "rehearsal result")
    req(rehearsal.get("fresh_processes") == 2 and rehearsal.get("exact_output_identity") == "2_OF_2", "rehearsal reproduction")
    req(rehearsal.get("authorization_semantic_sha256") == semantic_sha(doc), "rehearsed semantic candidate")
    req(rehearsal.get("executor_sha256") == sha(EXECUTOR), "rehearsed executor")

    one_shot = doc.get("one_shot_semantics", {})
    req(all(one_shot.get(key) is True for key in ("durable_attempt_start", "durable_shared_computation_start", "exclusive_attempt_root", "failure_after_attempt_start_consumes_release")), "one shot required")
    req(all(one_shot.get(key) is False for key in ("retry", "resume", "second_attempt")), "one shot prohibited")
    req(doc.get("access_accounting") == {"ledger_before": 175, "ledger_after": 175, "checkpoint_reads": 0, "shard_opens": 0, "future_shared_expert_executions": 1, "preparation_shared_expert_executions": 0, "routed_aggregate_executions": 0, "ffn_completions": 0, "s2_constructions": 0}, "accounting")
    req(doc.get("stop_boundary") == "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY", "stop boundary")
    req(set(doc.get("prohibitions", {})) == {"checkpoint_access", "checkpoint_fallback", "shard_open", "historical_direct_dprefix_input", "historical_shared_output_substitution", "routed_shared_combination", "ffn_completion", "s2_construction", "gpu", "blas"}, "prohibition census")
    req(all(value is True for value in doc["prohibitions"].values()), "prohibitions")
    history = doc.get("historical_lineage", {})
    req(history == {"shared_parameter_bytes": "SAME_SURFACE_REUSABLE", "decoder_and_kernel_structure": "STRUCTURAL_ONLY", "historical_direct_dprefix_input": "VALID_BUT_DIFFERENT_SURFACE", "historical_shared_output": "VALID_BUT_DIFFERENT_SURFACE"}, "historical lineage")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.authorization), repo=not args.no_repo)
    print("REPRESENTATIVE_SHARED_EXPERT_RECOVERY_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

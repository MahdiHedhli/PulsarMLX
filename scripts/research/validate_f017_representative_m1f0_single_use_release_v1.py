#!/usr/bin/env python3
"""Checkpoint-free semantic validator for the prepared one-shot M1-F0 release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-single-use-execution-release-v1.json"
CANDIDATE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-candidate-v3.json"
EXPECTED_HEAD = "11c4d5d2f3f3e2c08677e0be287ac9d6104b0606"
EXPECTED_RELEASE_ID = "F017-REPRESENTATIVE-M1F0-ATTENTION-ROUTE-RECOVERY-1-RELEASE-1"
EXPECTED_EVENT = "F017-REPRESENTATIVE-M1F0-ATTENTION-ROUTE-RECOVERY-1"
EXPECTED_ATTEMPT = EXPECTED_EVENT + "-ATTEMPT-1"
EXPECTED_STOP = "AFTER_REPRESENTATIVE_ROUTE_BEFORE_ANY_ROUTED_OR_SHARED_EXPERT_EXECUTION"
EXPECTED_BINDINGS = {
    "authorization_v3": "d42c5a948c6e73d5003c80dbef3da9c53fe53aee6cf2261ed0f193058f9631c6",
    "independent_acceptance": "fef7bc25e6524283c3754d0f2890a72a61785be60e66b44d952360af2da07fee",
    "executor": "9c1e5168a1d385f78cedc9a49d892aad41b1979b496585477286e183992a379e",
    "release_wrapper": "0cc047cd6208a463124e6b2e382fb0d95baffd4c5d5afbdb03cf8580029a0b67",
    "preopen_contract": "5fee99e6c138d85952279b2a10b104122b00363998e5f8f640af1fd5435cddbb",
    "crash_terminalizer": "3c3c692889f0ea25228abf89b41c207f2f5a23e4e89ff7805d1a261c852d3830",
    "router_reuse_v2": "c46b00cb263347e1a345b1766fd1e36d3758c6e21ae15674bfe8dfc8841f21a1",
    "reproduction_contract": "7e31865232357b29cfc92c423421d6442e4203a5b39520458346a2b1a827dcbf",
    "reproduction_producer": "b17f1034688f2cf01243d04380151c1ad5c9f321d19a7bc29907a00a10993cc3",
    "synthetic_rehearsal": "3119023d5432325a6dfcbec2fffce9224834d19f0cb79a89fea332ece3ebfd4a",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key " + key)
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def validate_document(release: dict[str, Any], candidate: dict[str, Any], root: Path | None = None) -> list[str]:
    errors: list[str] = []

    def req(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    req(release.get("schema") == "pulsarmlx.f017.representative-m1f0-single-use-execution-release", "SCHEMA")
    req(release.get("schema_version") == "1.0.0", "SCHEMA_VERSION")
    req(release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "STATUS")
    req(release.get("release_id") == EXPECTED_RELEASE_ID, "RELEASE_ID")
    req(release.get("event_id") == EXPECTED_EVENT and release.get("attempt_id") == EXPECTED_ATTEMPT, "EVENT_ATTEMPT")

    repo = release.get("authoritative_repository", {})
    req(repo == {
        "branch": "feat/017-real-checkpoint-runner",
        "execution_code_head": EXPECTED_HEAD,
        "head_policy": "EXACT_EXECUTION_CODE_HEAD_NO_REBASE_NO_SUBSTITUTION",
        "release_control_plane_is_append_only": True,
    }, "AUTHORITATIVE_HEAD")

    bindings = release.get("accepted_bindings", {})
    req(set(bindings) == set(EXPECTED_BINDINGS), "BINDING_SET")
    for name, expected in EXPECTED_BINDINGS.items():
        req(bindings.get(name, {}).get("sha256") == expected, "BINDING:" + name)
        if root is not None:
            path = root / str(bindings.get(name, {}).get("path", ""))
            req(path.is_file() and sha(path) == expected, "BINDING_FILE:" + name)

    canonical = release.get("canonical_input", {})
    req(canonical == {
        "identity": "DPREFIX-EXACT-1",
        "sha256": "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11",
        "semantic_role": "CANONICAL_LAYER3_ENTRY_PRE_ATTENTION",
        "retained_inputs": 1,
        "checkpoint_fallback": False,
    }, "CANONICAL_INPUT")

    checkpoint = release.get("checkpoint", {})
    req(checkpoint == {
        "catalog_sha256": "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19",
        "shard_ordinal": 2,
        "shard_basename": "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf",
        "shard_sha256": "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36",
        "shard_size_bytes": 49105028960,
        "maximum_opens": 1,
        "checkpoint_rereads_for_reproduction": 0,
    }, "SHARD_BINDING")

    inventory = release.get("attention_payload_inventory", [])
    candidate_inventory = candidate.get("attention_payload_inventory", [])
    req(inventory == candidate_inventory, "INVENTORY")
    req([x.get("ordinal") for x in inventory] == list(range(9)), "INVENTORY_ORDER")
    req(sum(int(x.get("packed_bytes", -1)) for x in inventory) == 132900864, "PACKED_TOTAL")

    read = release.get("read_contract", {})
    req(read == {
        "ordering": "STRICT_ASCENDING_ORDINAL_0_THROUGH_8",
        "checkpoint_payload_reads": 9,
        "total_packed_bytes": 132900864,
        "retained_router_authorities": 3,
        "retained_canonical_s0": 1,
        "fallback": False,
        "retry": False,
        "extra_reads": False,
        "dynamic_discovery": False,
    }, "READ_CONTRACT")
    req(release.get("ledger") == {
        "start": 166,
        "success_after_read_phase": 175,
        "partial_failure": "166+N_PROVEN_CONSUMPTIONS_THEN_TERMINAL",
        "authoritative_reconstruction_required": True,
        "no_rollback": True,
    }, "LEDGER")

    preopen = candidate.get("preopen_preflight", {})
    req(bindings.get("preopen_contract", {}).get("sha256") == preopen.get("sha256"), "PREOPEN_CANDIDATE_BINDING")
    env = release.get("execution_environment", {})
    req(env == {
        "implementation": "CPython",
        "python_major_minor": [3, 14],
        "numpy": "2.4.5",
        "endianness": "little",
        "threading_contract": "FIXED_ORDER_NO_BLAS_NO_PARALLEL_REDUCTION",
        "reproduction_scope": "SAME_PINNED_PRODUCTION_ENVIRONMENT",
        "cross_platform_libm_identity_claimed": False,
        "device": "CPU_ONLY",
        "gpu_path": False,
        "alternate_environment": False,
    }, "ENVIRONMENT")
    req(release.get("storage_preflight") == {
        "method": "CONSERVATIVE_FREE_SPACE_PRECONDITION",
        "required_free_bytes": 3221225472,
        "must_pass_before_attempt_start_or_shard_open": True,
    }, "STORAGE")
    req(release.get("stop_boundary") == EXPECTED_STOP, "STOP_BOUNDARY")

    prohibitions = release.get("prohibitions", {})
    required_prohibitions = {
        "routed_expert_execution", "shared_expert_execution", "m1f_execution",
        "direct_dprefix_route_reuse", "alternate_executor", "alternate_authorization",
        "checkpoint_reads_outside_inventory", "checkpoint_rereads", "resume", "retry",
        "second_attempt",
    }
    req(set(prohibitions) == required_prohibitions and all(prohibitions.get(k) is True for k in required_prohibitions), "PROHIBITIONS")

    one = release.get("single_use", {})
    req(one.get("one_shot") is True, "ONE_SHOT")
    req(one.get("consumed_at") == "DURABLE_ATTEMPT_START_RECORD_BEFORE_SHARD_OPEN", "CONSUMPTION_BOUNDARY")
    req(one.get("preopen_failure_before_attempt_start_leaves_unconsumed") is True, "PREOPEN_UNCONSUMED")
    req(one.get("consumed_release_can_be_reused") is False and one.get("reset_to_reusable_state") is False, "IRREVOCABLE")
    req(one.get("consumed_remains_irrevocable_after") == [
        "PARTIAL_READ_FAILURE", "CRASH", "TERMINALIZER_RECOVERY",
        "READ_PHASE_SUCCESS_THEN_COMPUTE_FAILURE", "REPRODUCTION_FAILURE",
        "FINAL_EVIDENCE_FAILURE",
    ], "TERMINAL_CONSUMPTION")

    invalidity = release.get("invalidity", {})
    req(invalidity.get("fail_before_attempt_start_if_any_mismatch") == [
        "EXECUTION_CODE_HEAD", "LEDGER", "ACCEPTED_BINDING", "ENVIRONMENT", "STORAGE",
        "INVENTORY", "SHARD_OBJECT", "PRIOR_ATTEMPT", "INTERRUPTED_ATTEMPT",
    ], "INVALIDITY")
    req(all(invalidity.get(k) is False for k in ("automatic_rebase", "automatic_reauthorization", "fallback_identity")), "INVALIDITY_FALLBACK")

    approval = release.get("approval_boundary", {})
    req(approval == {
        "approval_asserted": False,
        "separate_committed_independent_release_approval_required": True,
        "future_wrapper_token_disposition": "GO_EXECUTE_ONCE_NO_RETRY",
        "future_wrapper_token_must_bind_release_id_and_sha256": True,
        "future_real_event_authorized_scope": "ONLY_THIS_EXACT_RELEASE_ID_AND_SHA256_AFTER_SEPARATE_INDEPENDENT_APPROVAL",
        "operator_execution_is_separate_after_approval": True,
    }, "APPROVAL_BOUNDARY")
    req(release.get("authorization") == {
        "real_event_authorized": False,
        "checkpoint_access_authorized": False,
        "shard_open_authorized": False,
        "execution_release_approved": False,
    }, "REAL_EVENT_AUTHORIZED")
    return errors


def validate_paths(root: Path = ROOT, release_path: Path = RELEASE) -> list[str]:
    return validate_document(load(release_path), load(root / CANDIDATE.relative_to(ROOT)), root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--release", type=Path, default=RELEASE)
    args = parser.parse_args()
    errors = validate_paths(args.repository_root.resolve(), args.release.resolve())
    print(json.dumps({
        "result": "FAIL" if errors else "PASS",
        "errors": errors,
        "status": "PREPARED_FOR_INDEPENDENT_APPROVAL",
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "ledger": 166,
        "real_event_authorized": False,
    }, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

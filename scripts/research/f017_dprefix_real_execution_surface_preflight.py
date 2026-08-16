#!/usr/bin/env python3
"""Bank the checkpoint-free DPREFIX real-orchestration preflight result.

The reviewed native candidate consumes a material package, but the released
config/authorization do not bind a program that creates that package from the
40 authorized positional reads, runs the independent oracle first, or banks
the terminal/partial-ledger evidence.  Creating such a program after release
would change the reviewed execution surface, so this module records a
non-consuming fail-closed result and never resolves a checkpoint path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "docs/architecture/reviews/evidence"
CONFIG = EVIDENCE_DIR / "f017-dense-prefix-execution-config-v4.json"
AUTH = EVIDENCE_DIR / "f017-dense-prefix-authorization-binding-v3.json"
ATTEMPT_V4 = EVIDENCE_DIR / "f017-dense-prefix-attempt-ledger-v4.json"
PAYLOAD_LEDGER = EVIDENCE_DIR / "f017-real-payload-access-ledger-v1.json"
PREFLIGHT = EVIDENCE_DIR / "f017-dprefix-numerical-surface-closure-preflight-v1.json"
CANDIDATE = ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs"
ORACLE = ROOT / "scripts/research/f017_dprefix_oracle_runtime.py"
EVIDENCE = EVIDENCE_DIR / "f017-dense-prefix-real-attempt-1-not-executed-execution-surface-v1.json"
ATTEMPT_V5 = EVIDENCE_DIR / "f017-dense-prefix-attempt-ledger-v5.json"
REVIEW = ROOT / "docs/architecture/reviews/f017-dprefix-real-1-execution-surface-nonexecution-review.md"

RELEASE_HEAD = "fcfc6d8062141b50d091f4eb77c02f36baec55aa"
CONFIG_SHA = "042a1fac64813849ae1569fee05d60be6a86fba0f7ef874dbdaeb85c29252266"
AUTH_SHA = "86fbf397b462f23fd6bb9d911afcc332b348bf60426d80790dec3b691ff6ee6c"
ATTEMPT_V4_SHA = "dd6ad01a2a38235dfd84a25269d0513c813ba7c87171ed3a898c7566ef63001e"
PAYLOAD_LEDGER_SHA = "a0edafdcd0279fb28e08c69a86a9c95ddd19e013b73a1e92f7620734456a9339"
CANDIDATE_SHA = "1a73dd4026592e21df05a82df806e52ebcb8dd0248aaffc0d8fd91c6f9e1387a"
ORACLE_PACKAGE_SHA = "9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def committed_material_package_invocations() -> list[str]:
    """Return reviewed Python launchers that invoke the candidate real mode."""
    matches: list[str] = []
    for path in sorted((ROOT / "scripts/research").glob("*.py")):
        if path == Path(__file__).resolve():
            continue
        if "--execute-material-package" in path.read_text(encoding="utf-8"):
            matches.append(path.relative_to(ROOT).as_posix())
    return matches


def validate_released_surface() -> dict[str, Any]:
    if sha256(CONFIG) != CONFIG_SHA or sha256(AUTH) != AUTH_SHA:
        raise ValueError("released config/authorization drift")
    if sha256(ATTEMPT_V4) != ATTEMPT_V4_SHA or sha256(PAYLOAD_LEDGER) != PAYLOAD_LEDGER_SHA:
        raise ValueError("released attempt/payload state drift")
    config, auth, attempt, payload, preflight = map(load, (CONFIG, AUTH, ATTEMPT_V4, PAYLOAD_LEDGER, PREFLIGHT))
    state = attempt["current_state"]
    expected = {
        "attempt_id": "DPREFIX-REAL-1",
        "authorized": True,
        "automatic_m1f0_continuation": False,
        "automatic_retry": False,
        "checkpoint_accessed": False,
        "consumed": False,
        "executed": False,
        "ledger": 59,
    }
    if state != expected or payload["cumulative_tensor_payloads"] != 59:
        raise ValueError("released attempt state")
    if preflight["result"] != "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE" or preflight["checkpoint_reads"] != 0:
        raise ValueError("canonical preflight predecessor")
    candidate_text = CANDIDATE.read_text(encoding="utf-8")
    oracle_text = ORACLE.read_text(encoding="utf-8")
    if "--execute-material-package" not in candidate_text or "real_checkpoint_reads_by_candidate: 0" not in candidate_text:
        raise ValueError("candidate material-package boundary")
    if "def dense_prefix_surfaces(" not in oracle_text:
        raise ValueError("oracle machinery absent")
    forbidden_bound_keys = {
        "real_event_launcher_sha256",
        "material_package_builder_sha256",
        "checkpoint_reader_sha256",
        "terminal_evidence_banker_sha256",
    }
    if forbidden_bound_keys.intersection(config) or forbidden_bound_keys.intersection(auth):
        raise ValueError("unexpected reviewed real-event orchestrator binding")
    invocations = committed_material_package_invocations()
    if invocations:
        raise ValueError(f"unexpected committed real candidate launcher: {invocations}")
    return {
        "config": config,
        "authorization": auth,
        "attempt": attempt,
        "payload": payload,
        "preflight": preflight,
        "committed_material_package_invocations": invocations,
    }


def evidence_artifact() -> dict[str, Any]:
    values = validate_released_surface()
    return {
        "schema": "pulsarmlx.f017.dense-prefix-real-nonexecution",
        "schema_version": "3.0.0",
        "verdict": "NOT_EXECUTED",
        "terminal_class": "EXECUTION_SURFACE_DRIFT",
        "reason_code": "REAL_EVENT_ORCHESTRATOR_UNBOUND",
        "attempt_id": "DPREFIX-REAL-1",
        "release": {
            "adversarial_verdict": "GO — EXECUTE DPREFIX-REAL-1",
            "reviewed_closeout_head": RELEASE_HEAD,
        },
        "finding": {
            "canonical_preflight_reported_ready": True,
            "candidate_accepts_prebuilt_material_package": True,
            "candidate_reads_checkpoint": False,
            "candidate_real_checkpoint_reads_field": 0,
            "committed_material_package_invocations": values["committed_material_package_invocations"],
            "config_binds_real_event_launcher": False,
            "authorization_binds_real_event_launcher": False,
            "material_package_builder_bound": False,
            "bounded_checkpoint_reader_bound": False,
            "oracle_first_orchestrator_bound": False,
            "terminal_evidence_banker_bound": False,
            "partial_read_ledger_writer_bound": False,
            "creating_missing_orchestration_after_release": "FORBIDDEN_EXECUTION_SURFACE_DRIFT",
        },
        "passed_nonconsuming_checks": {
            "local_remote_parity": True,
            "clean_worktree_before_preflight": True,
            "candidate_identity_verified": True,
            "oracle_package_immutable_read_only": True,
            "native_mlx_identities_match": True,
            "tier_b_surface_instantiability": "FULL_TIER_B_SURFACE_INSTANTIABLE_CHECKPOINT_FREE",
            "host_architecture": "arm64",
            "memory_floor_gib": 27,
            "observed_physical_memory_gib": 128,
            "observed_system_free_percentage": 90,
            "thermal_warning": False,
            "performance_warning": False,
        },
        "bindings": {
            "execution_config_sha256": CONFIG_SHA,
            "authorization_binding_sha256": AUTH_SHA,
            "attempt_ledger_before_sha256": ATTEMPT_V4_SHA,
            "real_payload_ledger_sha256": PAYLOAD_LEDGER_SHA,
            "candidate_executable_sha256": CANDIDATE_SHA,
            "candidate_source_sha256": sha256(CANDIDATE),
            "oracle_package_sha256": ORACLE_PACKAGE_SHA,
            "oracle_runtime_source_sha256": sha256(ORACLE),
            "preflight_sha256": sha256(PREFLIGHT),
        },
        "access": {
            "checkpoint_path_resolved": False,
            "shard_opens": 0,
            "positional_reads": 0,
            "payloads": 0,
            "packed_bytes": 0,
        },
        "state": {
            "authorized": True,
            "consumed": False,
            "executed": False,
            "checkpoint_accessed": False,
            "payloads_read": 0,
            "packed_bytes_read": 0,
            "ledger_before": 59,
            "ledger_after": 59,
            "automatic_retry": False,
            "automatic_m1f0_continuation": False,
        },
        "continuation": {
            "attempt_remains_unconsumed": True,
            "new_attempt_created": False,
            "real_execution_requires_new_reviewed_orchestrator_successor": True,
        },
        "repository_authority": "PACKET CLAIMS REJECTED — BANKED EVIDENCE CONTRADICTS PACKET",
    }


def attempt_ledger_v5(evidence: dict[str, Any]) -> dict[str, Any]:
    predecessor = load(ATTEMPT_V4)
    return {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger",
        "schema_version": "5.0.0",
        "append_only_predecessor": {
            "path": ATTEMPT_V4.relative_to(ROOT).as_posix(),
            "sha256": ATTEMPT_V4_SHA,
        },
        "history": predecessor["history"] + [{
            "event": "THIRD_RELEASE_EXECUTION_SURFACE_DRIFT_STOP",
            "evidence_sha256": canonical_sha(evidence),
            "terminal_class": "EXECUTION_SURFACE_DRIFT",
            "reason_code": "REAL_EVENT_ORCHESTRATOR_UNBOUND",
            "consumed": False,
            "checkpoint_accessed": False,
            "payloads_read": 0,
            "ledger_before": 59,
            "ledger_after": 59,
        }],
        "current_state": predecessor["current_state"],
        "checkpoint_access": 0,
        "ledger": 59,
    }


def review_markdown(evidence: dict[str, Any], attempt: dict[str, Any]) -> str:
    evidence_sha = canonical_sha(evidence)
    attempt_sha = canonical_sha(attempt)
    return f"""# PulsarMLX F017 DPREFIX-REAL-1 Execution-Surface Non-Execution Review

## Verdict

`DENSE-PREFIX M1-F(-1) NOT EXECUTED`

`DPREFIX-REAL-1` remained authorized and unconsumed. No checkpoint path was resolved, no shard was opened, no positional read occurred, and the real-payload ledger remained 59.

## Finding

The reviewed candidate binary is exact and accepts `--execute-material-package`, but it deliberately performs zero checkpoint reads. The reviewed config v4 and authorization v3 bind neither a real-event launcher nor the program that creates the 40-tensor material package, executes oracle-first ordering, updates partial-read accounting, and banks schema-v4 terminal evidence. No committed research launcher invokes that candidate mode.

Creating this load-bearing orchestration after the independent release would violate the explicit prohibition on execution-time implementation generation. The fail-closed classification is therefore `EXECUTION_SURFACE_DRIFT`, reason `REAL_EVENT_ORCHESTRATOR_UNBOUND`.

## Evidence

- raw evidence SHA-256: `{evidence_sha}`
- attempt-ledger v5 SHA-256: `{attempt_sha}`
- access: 0 shard opens, 0 positional reads, 0 payloads, 0 packed bytes
- ledger: 59 to 59
- attempt: authorized, unconsumed, unexecuted, checkpoint-unaccessed

## Exact next action

Prepare and independently review an append-only execution successor that binds the missing real-event orchestrator/material-package builder, bounded checkpoint reader, oracle-first coordinator, partial-read ledger writer, and terminal evidence banker. Do not access the checkpoint before that review.
"""


def generate() -> dict[str, Any]:
    evidence = evidence_artifact()
    attempt = attempt_ledger_v5(evidence)
    return {"evidence": evidence, "attempt": attempt, "review": review_markdown(evidence, attempt)}


def write() -> dict[str, Any]:
    result = generate()
    EVIDENCE.write_bytes(canonical_bytes(result["evidence"]))
    ATTEMPT_V5.write_bytes(canonical_bytes(result["attempt"]))
    REVIEW.write_text(result["review"], encoding="utf-8")
    return result


def main() -> None:
    result = write()
    print(json.dumps({
        "verdict": result["evidence"]["verdict"],
        "terminal_class": result["evidence"]["terminal_class"],
        "reason_code": result["evidence"]["reason_code"],
        "checkpoint_access": 0,
        "attempt_consumed": False,
        "ledger": 59,
    }, sort_keys=True))


if __name__ == "__main__":
    main()

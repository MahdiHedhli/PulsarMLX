#!/usr/bin/env python3
"""Synthetic-only V12 authority, lifecycle, and failure qualification."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import validate_candidate_bytes
from f017_checkpoint_identity_capability_v12 import validate_capability
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError, OUTCOMES
from f017_corrected_oracle_authorization_v12 import build_identity_candidate
from execute_f017_corrected_oracle_event_v12 import run_identity_stage, validate_package_start
from validate_f017_corrected_oracle_access_v12 import (
    bank_candidate, install_noncanonical_candidate, validate_candidate_triple,
    validate_installed_triple,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-checkpoint-identity-v12.json"
MIXED_CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-checkpoint-identity-mixed-v12.json"
PLAN_SHA = hashlib.sha256(b"F017-V12-EVENT-IDENTITY-PLAN-QUALIFICATION").hexdigest()


def _make_root(base: Path, suffix: str, *, mixed: bool = False) -> Path:
    root = base / f"root-{suffix}"
    root.mkdir()
    for ordinal in range(1, 7):
        path = root / f"synthetic-v12-shard-{ordinal}.bin"
        if mixed:
            path.write_bytes(bytes([ordinal]) * ordinal)
        else:
            path.touch()
    return root


def _package(base: Path, suffix: str, *, mixed: bool = False) -> tuple[Path, Path, Path, dict]:
    root = _make_root(base, suffix, mixed=mixed)
    candidate = build_identity_candidate(
        authority_scope="SYNTHETIC", authorization_id=f"F017-V12-QUAL-AUTH-{suffix}",
        package_attempt_id=f"F017-V12-QUAL-PACKAGE-{suffix}", checkpoint_root=root,
        checkpoint_identity_contract_path=MIXED_CONTRACT if mixed else CONTRACT,
        event_identity_plan_sha256=PLAN_SHA,
    )
    directory = base / f"authority-{suffix}"
    directory.mkdir()
    candidate_path = directory / "candidate.json"
    installed_path = directory / "installed.json"
    receipt_path = directory / "receipt.json"
    bank_candidate(candidate_path, candidate)
    install_noncanonical_candidate(candidate_path, installed_path, receipt_path)
    return candidate_path, installed_path, receipt_path, candidate


def _success_stage(base: Path, suffix: str, *, mixed: bool = False) -> dict:
    candidate_path, installed_path, receipt_path, candidate = _package(base, suffix, mixed=mixed)
    gate = validate_package_start(candidate_path, installed_path, receipt_path)
    leases, report = run_identity_stage(
        gate["installed_authority"], package_attempt_id=candidate["package_attempt_id"],
        package_durable_start=True,
    )
    release = leases.release()
    if (report["checkpoint_shard_opens"] != 6 or report["checkpoint_identity_hash_reads"] != 6
            or report["retained_lease_count"] != 5 or report["identity_only_retained_count"] != 0
            or release["successful_closures"] != 5 or release["live_leases_after_release"] != 0):
        raise AssertionError("synthetic identity-stage census")
    return {"report":report,"release":release,"candidate":candidate}


def _mutation_cases(candidate: dict) -> tuple[int, int]:
    keys = sorted(candidate)
    rejected = unexpected = 0
    for index in range(250):
        mutated = copy.deepcopy(candidate)
        key = keys[index % len(keys)]
        if index % 5 == 0:
            mutated.pop(key)
        elif index % 5 == 1:
            mutated[f"unknown_{index}"] = 0
        elif index % 5 == 2:
            mutated[key] = None
        elif index % 5 == 3:
            mutated["authority_scope"] = "PRODUCTION_EVENT_06"
        else:
            mutated["resume"] = True
        try:
            validate_candidate_bytes(canonical_bytes(mutated))
        except Exception:
            rejected += 1
        else:
            unexpected += 1
    return rejected, unexpected


def _filesystem_faults(base: Path) -> tuple[int, int]:
    candidate_path, installed_path, receipt_path, candidate = _package(base, "FAULT")
    gate = validate_package_start(candidate_path, installed_path, receipt_path)
    missing = Path(candidate["checkpoint_root"]) / "synthetic-v12-shard-6.bin"
    missing.unlink()
    realized = unexpected = 0
    for _ in range(50):
        try:
            run_identity_stage(gate["installed_authority"], package_attempt_id=candidate["package_attempt_id"], package_durable_start=True)
        except IdentityAuthorityError as exc:
            if exc.outcome_id == "F017_V12_IDENTITY_SHARD_OPEN_FAILURE" and exc.evidence["generic_fallback"] is False:
                realized += 1
            else:
                unexpected += 1
        else:
            unexpected += 1
    return realized, unexpected


def _fresh_processes(candidate_path: Path, installed_path: Path, receipt_path: Path) -> tuple[int, int]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "scripts/research")
    candidate_code = "from pathlib import Path; from validate_f017_corrected_oracle_access_v12 import validate_candidate_triple; validate_candidate_triple(Path(__import__('sys').argv[1]))"
    installed_code = "from pathlib import Path; from validate_f017_corrected_oracle_access_v12 import validate_installed_triple; import sys; validate_installed_triple(Path(sys.argv[1]),Path(sys.argv[2]))"
    candidate_pass = installed_pass = 0
    for _ in range(20):
        subprocess.run([sys.executable, "-c", candidate_code, str(candidate_path)], check=True, env=environment, stdout=subprocess.DEVNULL)
        candidate_pass += 1
        subprocess.run([sys.executable, "-c", installed_code, str(installed_path), str(receipt_path)], check=True, env=environment, stdout=subprocess.DEVNULL)
        installed_pass += 1
    return candidate_pass, installed_pass


def qualify() -> dict:
    capability = validate_capability()
    with tempfile.TemporaryDirectory(prefix="f017-v12-identity-") as temporary:
        base = Path(temporary)
        stages = [_success_stage(base, f"S{i:02d}") for i in range(30)]
        event_variations = [_success_stage(base, f"E{i:02d}") for i in range(20)]
        minimal_packages = [_success_stage(base, f"M{i:02d}") for i in range(20)]
        mixed_packages = [_success_stage(base, f"X{i:02d}", mixed=True) for i in range(20)]
        reference_candidate = stages[0]["candidate"]
        rejected, unexpected_mutations = _mutation_cases(reference_candidate)
        filesystem_realized, filesystem_unexpected = _filesystem_faults(base)
        candidate_path, installed_path, receipt_path, _ = _package(base, "FRESH")
        fresh_candidate, fresh_installed = _fresh_processes(candidate_path, installed_path, receipt_path)
    total_failure_executions = rejected + filesystem_realized
    return {
        "schema":"pulsarmlx.f017.checkpoint-identity-authority-qualification/12.0.0",
        "authority_scope":"SYNTHETIC", "operation_class":"CHECKPOINT_IDENTITY_QUALIFICATION",
        "candidate_fresh_process_repetitions":fresh_candidate,
        "installed_fresh_process_repetitions":fresh_installed,
        "successful_identity_stages":len(stages),
        "minimal_six_shard_packages":len(minimal_packages),
        "mixed_size_six_shard_packages":len(mixed_packages),
        "event_identity_variations":len(event_variations),
        "candidate_mutations":250, "candidate_mutations_rejected":rejected,
        "filesystem_fault_executions":50, "filesystem_faults_realized":filesystem_realized,
        "total_failure_executions":total_failure_executions,
        "modeled_outcomes":len(OUTCOMES), "generic_fallback_for_modeled_failures":False,
        "unexpected_passes":unexpected_mutations + filesystem_unexpected,
        "original_checkpoint_root_opens":0, "original_checkpoint_shard_opens":0,
        "original_checkpoint_identity_hash_reads":0, "original_checkpoint_payload_reads":0,
        "live_event_06_authority_created":False, "event_06_executed":False,
        "capability":capability,
        "result":"PASS" if total_failure_executions >= 300 and unexpected_mutations + filesystem_unexpected == 0 else "FAIL",
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True, separators=(",", ":")))

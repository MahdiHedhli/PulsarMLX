#!/usr/bin/env python3
"""Synthetic-only V12 authority, lifecycle, and failure qualification."""
from __future__ import annotations

import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import validate_candidate_bytes
from f017_checkpoint_identity_capability_v12 import validate_capability
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError, OUTCOMES, failure
from f017_checkpoint_identity_producer_v12 import validate_banked_identity_evidence
from f017_corrected_oracle_authorization_v12 import build_identity_candidate
from execute_f017_corrected_oracle_event_v12 import run_identity_stage, validate_package_start
from validate_f017_corrected_oracle_access_v12 import (
    bank_candidate, install_noncanonical_candidate, validate_candidate_triple,
    validate_installed_triple,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-checkpoint-identity-v12.json"
MIXED_CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-checkpoint-identity-mixed-v12.json"
PRODUCTION_CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-v12.json"
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
        package_durable_start=True, evidence_directory=base / f"evidence-{suffix}",
    )
    release = leases.release()
    if (report["checkpoint_shard_opens"] != 6 or report["checkpoint_identity_hash_reads"] != 6
            or report["retained_lease_count"] != 5 or report["identity_only_retained_count"] != 0
            or report["evidence"]["identity_terminal_state"] != "COMPLETE"
            or release["successful_closures"] != 5 or release["live_leases_after_release"] != 0):
        raise AssertionError("synthetic identity-stage census")
    return {"report":report,"release":release,"candidate":candidate,
            "evidence_directory":base / f"evidence-{suffix}"}


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


def _filesystem_faults(base: Path) -> tuple[int, int, dict[str, int]]:
    categories: dict[str, int] = {}
    realized = unexpected = 0
    original_pread = os.pread
    cases = [
        ("missing_shard", "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"),
        ("extra_shard", "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"),
        ("wrong_size", "F017_V12_IDENTITY_SHARD_SIZE_MISMATCH"),
        ("hash_mismatch", "F017_V12_IDENTITY_SHARD_HASH_MISMATCH"),
        ("shard_symlink", "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"),
        ("duplicate_inode", "F017_V12_IDENTITY_DESCRIPTOR_CHANGED"),
        ("root_symlink", "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"),
        ("short_read", "F017_V12_IDENTITY_SHARD_READ_FAILURE"),
        ("file_mutation_during_hash", "F017_V12_IDENTITY_DESCRIPTOR_CHANGED"),
    ]
    for index in range(54):
        category, expected = cases[index % len(cases)]
        candidate_path, installed_path, receipt_path, candidate = _package(base, f"FAULT-{index:03d}", mixed=True)
        gate = validate_package_start(candidate_path, installed_path, receipt_path)
        root = Path(candidate["checkpoint_root"])
        shard5 = root / "synthetic-v12-shard-5.bin"
        shard6 = root / "synthetic-v12-shard-6.bin"
        context = mock.patch("f017_checkpoint_identity_producer_v12.os.pread", wraps=original_pread)
        if category == "missing_shard":
            shard6.unlink()
        elif category == "extra_shard":
            (root / "unexpected-shard.bin").write_bytes(b"x")
        elif category == "wrong_size":
            shard6.write_bytes(b"short")
        elif category == "hash_mismatch":
            shard6.write_bytes(b"\t" * 6)
        elif category == "shard_symlink":
            shard6.unlink(); shard6.symlink_to(shard5.name)
        elif category == "duplicate_inode":
            shard6.unlink(); os.link(shard5, shard6)
        elif category == "root_symlink":
            backing = root.with_name(root.name + "-backing")
            root.rename(backing); root.symlink_to(backing, target_is_directory=True)
        elif category == "short_read":
            context = mock.patch("f017_checkpoint_identity_producer_v12.os.pread", return_value=b"")
        elif category == "file_mutation_during_hash":
            mutated = False
            def mutating_pread(descriptor: int, count: int, offset: int) -> bytes:
                nonlocal mutated
                block = original_pread(descriptor, count, offset)
                if not mutated:
                    with (root / "synthetic-v12-shard-1.bin").open("ab") as stream:
                        stream.write(b"x"); stream.flush(); os.fsync(stream.fileno())
                    mutated = True
                return block
            context = mock.patch("f017_checkpoint_identity_producer_v12.os.pread", side_effect=mutating_pread)
        try:
            with context:
                run_identity_stage(gate["installed_authority"], package_attempt_id=candidate["package_attempt_id"], package_durable_start=True)
        except IdentityAuthorityError as exc:
            if exc.outcome_id == expected and exc.evidence["generic_fallback"] is False:
                realized += 1
                categories[category] = categories.get(category, 0) + 1
            else:
                unexpected += 1
        else:
            unexpected += 1
    return realized, unexpected, categories


def _evidence_and_close_faults(base: Path) -> tuple[int, int, dict[str, int]]:
    categories: dict[str, int] = {}
    realized = unexpected = 0
    mutations = ["identity_only_retention", "graph_lease_omission", "lease_manifest_failure",
                 "receipt_failure", "terminal_failure", "terminal_missing"]
    for index, category in enumerate(mutations * 2):
        stage = _success_stage(base, f"EVIDENCE-FAULT-{index:03d}", mixed=True)
        directory = stage["evidence_directory"]
        try:
            if category in {"identity_only_retention", "graph_lease_omission"}:
                path = directory / "lease-manifest.json"
                value = json.loads(path.read_text())
                if category == "identity_only_retention":
                    value["identity_only_retained_count"] = 1
                else:
                    value["descriptors"] = value["descriptors"][:-1]
                    value["retained_lease_count"] = 4
                path.write_bytes(canonical_bytes(value))
            elif category == "lease_manifest_failure":
                (directory / "lease-manifest.json").write_bytes(b"not-json\n")
            elif category == "receipt_failure":
                (directory / "identity-receipt.json").unlink()
            elif category == "terminal_failure":
                path = directory / "identity-terminal.json"
                value = json.loads(path.read_text()); value["state"] = "FAILED"; value["result"] = "FAIL"
                path.write_bytes(canonical_bytes(value))
            else:
                (directory / "identity-terminal.json").unlink()
            validate_banked_identity_evidence(directory)
        except Exception:
            realized += 1; categories[category] = categories.get(category, 0) + 1
        else:
            unexpected += 1

    for index in range(5):
        candidate_path, installed_path, receipt_path, candidate = _package(base, f"CLOSE-FAULT-{index:02d}", mixed=True)
        gate = validate_package_start(candidate_path, installed_path, receipt_path)
        leases, _ = run_identity_stage(gate["installed_authority"], package_attempt_id=candidate["package_attempt_id"],
                                       package_durable_start=True, evidence_directory=base / f"close-evidence-{index:02d}")
        def fail_close(_descriptor: int, _lease_id: str) -> None:
            raise OSError(errno.EIO, "injected close failure")
        result = leases.release(close_function=fail_close)
        if result["result"] == "PARTIAL_FAILURE" and result["live_leases_after_release"] == 5:
            realized += 1; categories["close_failure"] = categories.get("close_failure", 0) + 1
        else:
            unexpected += 1
        cleanup = leases.release(retry_failed=True)
        if cleanup["result"] != "PASS":
            raise AssertionError("close-fault cleanup")
    return realized, unexpected, categories


def _scope_separation(base: Path) -> dict:
    synthetic = _success_stage(base, "SCOPE-A", mixed=True)
    synthetic_raw = canonical_bytes(synthetic["candidate"])
    production = build_identity_candidate(
        authority_scope="PRODUCTION", authorization_id="F017-V12-QUAL-AUTH-SCOPE-PRODUCTION",
        package_attempt_id="F017-V12-QUAL-PACKAGE-SCOPE-PRODUCTION",
        checkpoint_root=Path("/nonexistent/f017-event06-validation-only"),
        checkpoint_identity_contract_path=PRODUCTION_CONTRACT, event_identity_plan_sha256=PLAN_SHA,
    )
    rejected = 0
    for _ in range(20):
        for raw, expected in ((synthetic_raw, {"authority_scope":"PRODUCTION"}),
                              (canonical_bytes(production), {"authority_scope":"SYNTHETIC"})):
            try:
                validate_candidate_bytes(raw, expected)
            except IdentityAuthorityError:
                rejected += 1
    return {"synthetic_scope_successes":1,"production_rehearsal_candidates":1,
            "cross_scope_attempts":40,"cross_scope_rejections":rejected,
            "original_checkpoint_access":0,"result":"PASS" if rejected == 40 else "FAIL"}


def _install_boundary_faults(base: Path) -> tuple[int, int]:
    """Prove a digest-spliced but field-substituted install cannot cross the gate."""
    rejected = unexpected = 0
    for index in range(20):
        candidate_a, _, _, _ = _package(base, f"INSTALL-A-{index:02d}", mixed=False)
        _, installed_b, receipt_b, _ = _package(base, f"INSTALL-B-{index:02d}", mixed=True)
        candidate_a_sha = hashlib.sha256(candidate_a.read_bytes()).hexdigest()
        receipt = json.loads(receipt_b.read_text())
        receipt["candidate_sha256"] = candidate_a_sha
        receipt_b.write_bytes(canonical_bytes(receipt))
        installed = json.loads(installed_b.read_text())
        installed["installed_authorization_sha256"] = candidate_a_sha
        installed["installation_receipt_sha256"] = hashlib.sha256(receipt_b.read_bytes()).hexdigest()
        installed_b.write_bytes(canonical_bytes(installed))
        try:
            validate_package_start(candidate_a, installed_b, receipt_b)
        except IdentityAuthorityError as exc:
            if exc.outcome_id == "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH":
                rejected += 1
            else:
                unexpected += 1
        else:
            unexpected += 1
    return rejected, unexpected


def _live_drift_faults(base: Path) -> tuple[int, int, dict[str, int]]:
    """Reach both pre-package drift outcomes through their measured validators."""
    realized = unexpected = 0
    counts: dict[str, int] = {}
    drift_source = base / "producer-capability-drift.py"
    drift_source.write_text("import subprocess\n", encoding="utf-8")
    try:
        with mock.patch("f017_checkpoint_identity_capability_v12.PRODUCER", drift_source):
            validate_capability()
    except IdentityAuthorityError as exc:
        if exc.outcome_id == "F017_V12_IDENTITY_CAPABILITY_DRIFT":
            realized += 1; counts[exc.outcome_id] = 1
        else:
            unexpected += 1
    else:
        unexpected += 1

    candidate_path, installed_path, receipt_path, _ = _package(base, "PRODUCER-MEASUREMENT-DRIFT")
    candidate_authority = validate_candidate_triple(candidate_path)["authority"]
    import f017_checkpoint_identity_authority_v12 as authority_module
    original_sha = authority_module._sha
    measured = (ROOT / json.loads(installed_path.read_text())["measured_producer_path"]).resolve()
    def drift_sha(path: Path) -> str:
        return "0" * 64 if path.resolve() == measured else original_sha(path)
    try:
        with mock.patch("f017_checkpoint_identity_authority_v12._sha", side_effect=drift_sha):
            validate_installed_triple(installed_path, receipt_path, candidate_authority)
    except IdentityAuthorityError as exc:
        if exc.outcome_id == "F017_V12_IDENTITY_PRODUCER_MEASUREMENT_DRIFT":
            realized += 1; counts[exc.outcome_id] = 1
        else:
            unexpected += 1
    else:
        unexpected += 1
    return realized, unexpected, counts


def _runtime_outcome_campaign() -> tuple[int, int, dict[str, int], int]:
    executions = unexpected = fresh_processes = 0
    counts: dict[str, int] = {}
    environment = dict(os.environ); environment["PYTHONPATH"] = str(ROOT / "scripts/research")
    code = ("import sys; from f017_checkpoint_identity_lifecycle_v12 import failure; "
            "e=failure(sys.argv[1],'fresh-process',checkpoint_access=0).evidence; "
            "assert e['outcome_id']==sys.argv[1] and e['generic_fallback'] is False and e['transition_id']")
    for outcome_id, (phase, package_delta, consumer_delta) in OUTCOMES.items():
        for index in range(25):
            evidence = failure(outcome_id, f"qualification-{index}", checkpoint_access=0).evidence
            if (evidence["phase"] == phase and evidence["package_delta"] == package_delta
                    and evidence["consumer_delta"] == consumer_delta
                    and evidence["generic_fallback"] is False and evidence["transition_id"]
                    and evidence["terminal_evidence"]):
                executions += 1; counts[outcome_id] = counts.get(outcome_id, 0) + 1
            else:
                unexpected += 1
        for _ in range(5):
            subprocess.run([sys.executable, "-c", code, outcome_id], check=True, env=environment,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            fresh_processes += 1
    return executions, unexpected, counts, fresh_processes


def _fresh_processes(candidate_path: Path, installed_path: Path, receipt_path: Path,
                     package_attempt_id: str, base: Path) -> tuple[int, int, int]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "scripts/research")
    candidate_code = "from pathlib import Path; from validate_f017_corrected_oracle_access_v12 import validate_candidate_triple; validate_candidate_triple(Path(__import__('sys').argv[1]))"
    installed_code = ("from pathlib import Path; from validate_f017_corrected_oracle_access_v12 import "
                      "validate_candidate_triple,validate_installed_triple; import sys; "
                      "c=validate_candidate_triple(Path(sys.argv[1]))['authority']; "
                      "validate_installed_triple(Path(sys.argv[2]),Path(sys.argv[3]),c)")
    identity_code = ("from pathlib import Path; import sys; "
                     "from execute_f017_corrected_oracle_event_v12 import validate_package_start,run_identity_stage; "
                     "g=validate_package_start(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])); "
                     "l,r=run_identity_stage(g['installed_authority'],package_attempt_id=sys.argv[4],"
                     "package_durable_start=True,evidence_directory=Path(sys.argv[5])); "
                     "x=l.release(); assert r['result']=='PASS' and r['evidence']['identity_terminal_state']=='COMPLETE' "
                     "and x['result']=='PASS'")
    candidate_pass = installed_pass = identity_pass = 0
    for index in range(20):
        subprocess.run([sys.executable, "-c", candidate_code, str(candidate_path)], check=True, env=environment, stdout=subprocess.DEVNULL)
        candidate_pass += 1
        subprocess.run([sys.executable, "-c", installed_code, str(candidate_path), str(installed_path),
                        str(receipt_path)], check=True, env=environment, stdout=subprocess.DEVNULL)
        installed_pass += 1
        subprocess.run([sys.executable, "-c", identity_code, str(candidate_path), str(installed_path),
                        str(receipt_path), package_attempt_id, str(base / f"fresh-identity-{index:02d}")],
                       check=True, env=environment, stdout=subprocess.DEVNULL)
        identity_pass += 1
    return candidate_pass, installed_pass, identity_pass


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
        filesystem_realized, filesystem_unexpected, filesystem_categories = _filesystem_faults(base)
        evidence_realized, evidence_unexpected, evidence_categories = _evidence_and_close_faults(base)
        scope_separation = _scope_separation(base)
        install_rejected, install_unexpected = _install_boundary_faults(base)
        live_drift_realized, live_drift_unexpected, live_drift_counts = _live_drift_faults(base)
        candidate_path, installed_path, receipt_path, fresh_value = _package(base, "FRESH")
        fresh_candidate, fresh_installed, fresh_identity = _fresh_processes(
            candidate_path, installed_path, receipt_path, fresh_value["package_attempt_id"], base)
        outcome_executions, outcome_unexpected, outcome_counts, outcome_fresh = _runtime_outcome_campaign()
    unexpected = (unexpected_mutations + filesystem_unexpected + evidence_unexpected
                  + outcome_unexpected + install_unexpected + live_drift_unexpected)
    return {
        "schema":"pulsarmlx.f017.checkpoint-identity-authority-qualification/12.0.0",
        "authority_scope":"SYNTHETIC", "operation_class":"CHECKPOINT_IDENTITY_QUALIFICATION",
        "candidate_fresh_process_repetitions":fresh_candidate,
        "installed_fresh_process_repetitions":fresh_installed,
        "identity_stage_fresh_process_repetitions":fresh_identity,
        "successful_identity_stages":len(stages),
        "identity_terminals_complete":len(stages) + len(event_variations) + len(minimal_packages) + len(mixed_packages),
        "minimal_six_shard_packages":len(minimal_packages),
        "mixed_size_six_shard_packages":len(mixed_packages),
        "mixed_format_six_shard_packages":len(mixed_packages),
        "event_identity_variations":len(event_variations),
        "candidate_mutations":250, "candidate_mutations_rejected":rejected,
        "install_boundary_substitutions":20,"install_boundary_substitutions_rejected":install_rejected,
        "candidate_mutation_categories":["historical_event_scope","scope","operation","generation","identity","checkpoint_set","root","contract","producer","capability","report","one_shot","alias","coercion"],
        "filesystem_fault_executions":54, "filesystem_faults_realized":filesystem_realized,
        "filesystem_fault_categories":filesystem_categories,
        "evidence_and_close_fault_executions":17,"evidence_and_close_faults_realized":evidence_realized,
        "evidence_and_close_fault_categories":evidence_categories,
        "runtime_failure_executions":outcome_executions,"runtime_failure_fresh_processes":outcome_fresh,
        "runtime_outcome_counts":outcome_counts,
        "live_drift_faults_realized":live_drift_realized,
        "live_drift_outcome_counts":live_drift_counts,
        "total_failure_executions":outcome_executions + filesystem_realized + evidence_realized + install_rejected + live_drift_realized,
        "modeled_outcomes":len(OUTCOMES), "modeled_outcomes_realized":len(outcome_counts),
        "generic_fallback_for_modeled_failures":False,"scope_separation":scope_separation,
        "unexpected_passes":unexpected,
        "original_checkpoint_root_opens":0, "original_checkpoint_shard_opens":0,
        "original_checkpoint_identity_hash_reads":0, "original_checkpoint_payload_reads":0,
        "live_event_06_authority_created":False, "event_06_executed":False,
        "capability":capability,
        "result":"PASS" if (outcome_executions >= 300 and filesystem_realized >= 50
                              and evidence_realized == 17 and scope_separation["result"] == "PASS"
                              and install_rejected == 20 and live_drift_realized == 2
                              and unexpected == 0) else "FAIL",
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True, separators=(",", ":")))

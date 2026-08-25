#!/usr/bin/env python3
"""V9 synthetic coordinator with hardened release and terminalization."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from f017_checkpoint_identity_producer_v9 import produce
from f017_corrected_oracle_compare_v8 import compare
from f017_corrected_oracle_event_accounting_v9 import derive, validate_against_outcome, validate_snapshot
from f017_descriptor_lease_manager_v9 import LeaseSet, validate_descriptors
from f017_canonical_serialization_v8 import strict_bytes
from f017_lifecycle_artifact_v8 import bank_runtime_artifact
from f017_memory_gate_v9 import observe
from f017_corrected_oracle_authorization_v9 import parse_candidate
from validate_f017_corrected_oracle_access_v9 import validate_installed_operator_go, validate_installed_rehearsal

ROOT = Path(__file__).resolve().parents[2]
OUTCOMES = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-outcome-obligations-v8.json").read_bytes())["outcomes"]
PRIMARY_WRAPPER = ROOT / "scripts/research/f017_corrected_oracle_primary_v9.py"
SECONDARY_WRAPPER = ROOT / "scripts/research/f017_corrected_oracle_secondary_v9.py"


class ModeledTransitionFailure(ValueError):
    def __init__(self, outcome_id: str, observed_failed_transition_id: str,
                 observed_last_completed_artifact_id: str):
        if outcome_id not in OUTCOMES or outcome_id == "COMPLETE_SUCCESS":
            raise ValueError("modeled failure outcome")
        if type(observed_failed_transition_id) is not str or type(observed_last_completed_artifact_id) is not str:
            raise ValueError("observed modeled transition identity")
        self.outcome_id = outcome_id; self.outcome = OUTCOMES[outcome_id]
        self.observed_failed_transition_id = observed_failed_transition_id
        self.observed_last_completed_artifact_id = observed_last_completed_artifact_id
        super().__init__(self.outcome["failed_transition_id"])


def _run_consumer(wrapper: Path, installed: Path, receipt: Path, descriptors: Path,
                  file_descriptors: list[int], output: Path) -> dict:
    command = [sys.executable, str(wrapper), "--execute-installed", "--authorization", str(installed),
               "--receipt", str(receipt), "--descriptors", str(descriptors),
               "--fds", ",".join(str(value) for value in file_descriptors), "--output", str(output)]
    subprocess.run(command, cwd=ROOT, check=True, pass_fds=tuple(file_descriptors), capture_output=True, text=True)
    return strict_bytes(output.read_bytes())


def _release(leases: LeaseSet, root: Path, close_function=None) -> dict:
    bank_runtime_artifact(root / "descriptor-release-start.json", "descriptor_release_start", {"expected_leases": 5})
    event_index = 0
    def bank_event(event: dict) -> str:
        nonlocal event_index
        digest = bank_runtime_artifact(root / f"descriptor-close-event-{event_index:02d}.json", "descriptor_close_event", event)
        event_index += 1; return digest
    report = leases.release(close_function=close_function, event_function=bank_event)
    report_sha = bank_runtime_artifact(root / "descriptor-release-report.json", "descriptor_release_report", report)
    receipt_sha = bank_runtime_artifact(root / "descriptor-release-receipt.json", "descriptor_release_receipt",
                                        {"release_report_sha256": report_sha, "result": report["result"],
                                         "live_leases_after_release": report["live_leases_after_release"]})
    terminal = {**report, "release_report_sha256": report_sha, "release_receipt_sha256": receipt_sha,
                "mandatory_stop": report["result"] != "PASS"}
    bank_runtime_artifact(root / "descriptor-release-terminal.json", "descriptor_release_terminal", terminal)
    return report


def _safe_evidence_root(path: Path | None) -> bool:
    if not isinstance(path, Path):
        return False
    try:
        return (path.exists() and not path.is_symlink() and path.is_dir()
                and str(path.resolve(strict=True)) == str(path))
    except OSError:
        return False


def _terminal_roots_are_authorized(candidate: dict, receipt_path: Path,
                                   emergency_root: Path | None, terminal_fallback_root: Path | None) -> tuple[bool, str]:
    expected = (str(emergency_root) if isinstance(emergency_root, Path) else None,
                str(terminal_fallback_root) if isinstance(terminal_fallback_root, Path) else None)
    if (type(candidate) is dict and candidate.get("scope") == "PRODUCTION_EVENT_04"
            and (candidate.get("emergency_evidence_root"), candidate.get("terminal_fallback_evidence_root")) == expected):
        return True, "CANDIDATE_BINDING"
    try:
        receipt = strict_bytes(receipt_path.read_bytes())
    except (OSError, ValueError):
        return False, "INSTALLATION_RECEIPT_UNREADABLE"
    receipt_keys = {"schema", "authority", "installation_kind", "authorization_id", "package_attempt_id",
                    "candidate_sha256", "installed_sha256", "installed_path", "operator_approval_sha256",
                    "execution_readiness_declaration_sha256", "emergency_evidence_root",
                    "terminal_fallback_evidence_root", "candidate_install_bytes_equal", "result"}
    accepted = (type(receipt) is dict and set(receipt) == receipt_keys
            and receipt.get("schema") == "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0"
            and receipt.get("authority") is True and receipt.get("installation_kind") == "CANONICAL_EVENT04_NO_REPLACE"
            and receipt.get("candidate_install_bytes_equal") is True and receipt.get("result") == "PASS"
            and (receipt.get("emergency_evidence_root"), receipt.get("terminal_fallback_evidence_root")) == expected)
    return accepted, "INSTALLATION_RECEIPT_BINDING" if accepted else "INSTALLATION_RECEIPT_BINDING_MISMATCH"


def _bank_terminal(root: Path | None, fallback_root: Path | None, filename: str,
                   kind: str, payload: dict, *, unavailable_reason: str = "ROOT_UNUSABLE") -> dict:
    errors: list[dict] = []
    for label, target in (("PRIMARY", root), ("FALLBACK", fallback_root)):
        if isinstance(target, Path) and isinstance(root, Path) and target == root and label == "FALLBACK":
            continue
        if not _safe_evidence_root(target):
            errors.append({"target": label, "error": unavailable_reason})
            continue
        try:
            digest = bank_runtime_artifact(target / filename, kind, {**payload, "terminal_evidence_target": label})
        except Exception as bank_exc:
            errors.append({"target": label, "error": type(bank_exc).__name__})
            continue
        return {"result": "PASS", "target": label, "sha256": digest, "errors": errors}
    return {"result": "MAXIMAL_CONSTRUCTIBLE_NO_DURABLE_WRITE", "target": None, "sha256": None, "errors": errors}


def _terminalize(root: Path | None, fallback_root: Path | None, candidate: dict, exc: Exception, leases: LeaseSet | None,
                 failed_transition: str, last_completed_transition: str,
                 *, root_authority_status: str = "AUTHORIZED") -> dict:
    release = {"attempted_closures": 0, "successful_closures": 0, "live_leases_after_release": 0, "result": "NOT_APPLICABLE"}
    modeled = exc.outcome if isinstance(exc, ModeledTransitionFailure) else None
    if leases is not None:
        try:
            # Modeled early failures close inherited descriptors as part of
            # their atomic terminal capsule.  The normal release artifact
            # sequence is reserved for ranks 43-45 by the causal authority.
            release = (leases.release() if modeled is not None or not _safe_evidence_root(root)
                       else _release(leases, root))
        except Exception as release_exc:
            release = {"result": "EVIDENCE_BANKING_FAILURE", "source_exception": type(release_exc).__name__,
                       "live_leases_after_release": sum(record.state != "CLOSED" for record in leases.records)}
    empty_accounting = {"authorization": 0, "package": 0, "primary": 0, "secondary": 0,
                        "historical_before": 175, "historical_after": 175}
    accounting_derivation = {"result": "ROOT_NOT_USABLE", "source_exception_class": None}
    if _safe_evidence_root(root):
        try:
            accounting = derive(root)
            accounting_derivation = {"result": "PASS", "source_exception_class": None}
        except (ValueError, OSError) as accounting_exc:
            # Terminal evidence must remain constructible when the primary
            # evidence root becomes unreadable after a durable transition.
            # The fallback capsule reports the unavailable observation rather
            # than allowing a raw filesystem exception to cross this boundary.
            accounting = empty_accounting
            accounting_derivation = {"result": "UNAVAILABLE", "source_exception_class": type(accounting_exc).__name__}
    else:
        accounting = empty_accounting
    # An unavailable accounting observation cannot prove that the package did
    # not start.  Conservatively require package terminal evidence so an
    # unreadable durable start can never be converted into retry permission.
    package_started = accounting["package"] == 1 or accounting_derivation["result"] == "UNAVAILABLE"
    if modeled is not None:
        if accounting_derivation["result"] == "PASS":
            validate_against_outcome(accounting, modeled, exc.observed_failed_transition_id,
                                     exc.observed_last_completed_artifact_id)
        elif (modeled["failed_transition_id"] != exc.observed_failed_transition_id
                or modeled["last_completed_artifact_id"] != exc.observed_last_completed_artifact_id):
            raise ValueError("degraded outcome transition mismatch")
        failed_transition = modeled["failed_transition_id"]
        last_completed_transition = modeled["last_completed_artifact_id"]
    capsule = {"classification": modeled["outcome_class"] if modeled is not None else failed_transition,
               "outcome_id": exc.outcome_id if isinstance(exc, ModeledTransitionFailure) else None,
               "failed_transition_id": failed_transition,
               "last_completed_transition_id": last_completed_transition, "controlled_failure_class": "F017_CONTROLLED_RUNTIME_FAILURE",
               "source_exception_class": type(exc).__name__, "message": str(exc), "release": release,
               "accounting": accounting, "accounting_derivation": accounting_derivation,
               "package_terminal_evidence": package_started,
               "generic_fallback": modeled is None, "mandatory_stop": True}
    if isinstance(exc, ModeledTransitionFailure):
        artifact_id = next(item for item in modeled["required"] if item.startswith("failure_terminal_capsule__"))
        terminal_evidence = _bank_terminal(root, fallback_root, f"{artifact_id}.json", artifact_id, capsule,
                                           unavailable_reason=root_authority_status)
    else:
        terminal_evidence = _bank_terminal(root, fallback_root, "failure-terminal-capsule.json", "failure_terminal_capsule", capsule,
                                           unavailable_reason=root_authority_status)
    if package_started and modeled is None:
        package_terminal_evidence = _bank_terminal(root, fallback_root, "package-terminal.json", "package_terminal",
                                                   {"result": "FAILURE", **capsule}, unavailable_reason=root_authority_status)
    else:
        package_terminal_evidence = {"result": "NOT_APPLICABLE"}
    return {"result": "CONTROLLED_FAILURE", "failure_class": "F017_CONTROLLED_RUNTIME_FAILURE", "source_exception_class": type(exc).__name__,
            "failed_transition_id": failed_transition, "outcome_id": capsule["outcome_id"], "generic_fallback": capsule["generic_fallback"],
            "release": release, "accounting": accounting, "terminal_evidence": terminal_evidence,
            "accounting_derivation": accounting_derivation,
            "package_terminal_evidence": package_terminal_evidence, "root_authority_status": root_authority_status,
            "original_checkpoint_access": 0}


def _execute_installed(installed_path: Path, receipt_path: Path, evidence_root: Path, *, production: bool,
                       malformed: str | None = None, close_function=None, fail_transition: str | None = None,
                       fallback_evidence_root: Path | None = None,
                       terminal_fallback_evidence_root: Path | None = None) -> dict:
    # The emergency root is created by the no-replace production installer and
    # passed back from the installation receipt.  This lets even a later
    # authorization-parse failure reach durable evidence without trusting a
    # path recovered from malformed authorization bytes.
    if not production:
        evidence_root = evidence_root.resolve(strict=False)
    emergency_root = fallback_evidence_root if production else evidence_root.parent / f"{evidence_root.name}-emergency"
    candidate: dict = {}
    leases: LeaseSet | None = None; last = "INSTALLATION_RECEIPT_BANKED"
    try:
        if production:
            if (malformed is not None or fail_transition is not None or close_function is not None
                    or not isinstance(emergency_root, Path) or not isinstance(terminal_fallback_evidence_root, Path)):
                raise ValueError("production execution boundary")
            resolved_emergency = emergency_root.resolve(strict=True)
            if emergency_root.is_symlink() or not resolved_emergency.is_dir():
                raise ValueError("production emergency evidence root")
        else:
            emergency_root.mkdir(parents=True, exist_ok=False)
            resolved_emergency = emergency_root.resolve(strict=True)
        candidate, _ = parse_candidate(installed_path)
        expected_scope = "PRODUCTION_EVENT_04" if production else "SYNTHETIC_QUALIFICATION"
        if candidate["scope"] != expected_scope:
            raise ValueError("descriptor execution scope")
        if production and resolved_emergency != Path(candidate["emergency_evidence_root"]).resolve(strict=True):
            raise ValueError("authorization-bound emergency evidence root")
        if (production and terminal_fallback_evidence_root.resolve(strict=True)
                != Path(candidate["terminal_fallback_evidence_root"]).resolve(strict=True)):
            raise ValueError("authorization-bound terminal fallback root")
        handshake = (validate_installed_operator_go if production else validate_installed_rehearsal)(installed_path, receipt_path)
        evidence_root.mkdir(parents=True, exist_ok=False)
        bank_runtime_artifact(evidence_root / "coordinator-handshake.json", "coordinator_handshake", {"candidate_sha256": handshake["candidate_sha256"], "checkpoint_opens": 0, "checkpoint_reads": 0, "result": "PASS"}); last = "COORDINATOR_HANDSHAKE"
        package_memory = observe(enforce=production)
        if fail_transition == "PACKAGE_MEMORY_GATE": raise ValueError("injected package memory gate failure")
        bank_runtime_artifact(evidence_root / "package-claim.json", "package_claim", {"authorization_id": candidate["authorization_id"], "package_attempt_id": candidate["package_attempt_id"], "package_memory_gate": package_memory, "attempts": 1, "retries": 0, "resume": False}); last = "PACKAGE_CLAIM"
        bank_runtime_artifact(evidence_root / "package-durable-start.json", "package_durable_start", {"package_attempt_id": candidate["package_attempt_id"], "delta": 1}); last = "PACKAGE_DURABLE_START"
        bank_runtime_artifact(evidence_root / "package-ledger-entry.json", "package_ledger_entry", {"package_attempt_id": candidate["package_attempt_id"], "delta": 1, "historical_ledger": 175})
        bank_runtime_artifact(evidence_root / "checkpoint-identity-durable-start.json", "checkpoint_identity_durable_start", {"expected_shards": 6, "expected_graph_descriptors": 5}); last = "CHECKPOINT_IDENTITY_START"
        def identity_progress(kind: str, ordinal: int, digest: str) -> None:
            if kind == "ACCESS_EVENT":
                bank_runtime_artifact(evidence_root / f"checkpoint-access-event-{ordinal}.json", "checkpoint_access_event",
                                      {"shard_ordinal": ordinal, "sha256": digest})
            elif kind == "SHARD_RECEIPT":
                bank_runtime_artifact(evidence_root / f"checkpoint-shard-receipt-{ordinal}.json", "checkpoint_shard_receipt",
                                      {"shard_ordinal": ordinal, "sha256": digest})
            else:
                raise ValueError("identity progress kind")
        leases, identity = produce(candidate, handshake.get("installation_receipt_sha256"), identity_progress)
        descriptors = json.loads(json.dumps(identity["descriptor_identities"]))
        if malformed == "MODE_65536": descriptors[0]["mode"] = 65536
        elif malformed == "NON_DICT": descriptors[0] = None
        elif malformed == "UNHASHABLE_LEASE": descriptors[0]["lease_id"] = []
        validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
        bank_runtime_artifact(evidence_root / "checkpoint-access-journal-terminal.json", "checkpoint_access_journal_terminal", {"event_count": 6, "checkpoint_shard_opens": 6, "checkpoint_identity_hash_reads": 6, "unexpected_access_count": 0})
        lease_ids = [item["lease_id"] for item in descriptors]
        bank_runtime_artifact(evidence_root / "descriptor_lease_manifest.json", "descriptor_lease_manifest", {"lease_count": 5, "ordinals": [2, 3, 4, 5, 6], "lease_ids": lease_ids, "descriptor_identities": descriptors})
        bank_runtime_artifact(evidence_root / "checkpoint-identity-manifest.json", "checkpoint_identity_manifest",
                              {"ordered_shard_digests": identity["ordered_shard_digests"], "descriptor_lease_count": 5,
                               "descriptor_lease_manifest": "descriptor_lease_manifest.json"})
        bank_runtime_artifact(evidence_root / "checkpoint-identity-receipt.json", "checkpoint_identity_receipt", identity)
        bank_runtime_artifact(evidence_root / "checkpoint-identity-terminal.json", "checkpoint_identity_terminal", {"result": "COMPLETE", "retained_lease_count": 5}); last = "CHECKPOINT_IDENTITY_TERMINAL"
        primary_continuity = evidence_root / "primary_descriptor_continuity_report.json"
        bank_runtime_artifact(primary_continuity, "primary_descriptor_continuity_report", {"consumer_role": "PRIMARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "lease_ids": lease_ids, "descriptor_identities": descriptors, "path_reopen_count": 0})
        bank_runtime_artifact(evidence_root / "primary-durable-start.json", "primary_durable_start", {"event_id": candidate["primary_event_id"], "delta": 1}); last = "PRIMARY_DURABLE_START"
        bank_runtime_artifact(evidence_root / "primary-ledger-entry.json", "primary_ledger_entry", {"event_id": candidate["primary_event_id"], "delta": 1})
        if fail_transition == "PRIMARY_EXECUTION": raise ValueError("injected primary execution failure")
        primary = _run_consumer(PRIMARY_WRAPPER, installed_path, receipt_path, primary_continuity,
                                leases.inherited_fds(), evidence_root / "primary-consumer-output.json")
        primary_sha = hashlib.sha256(json.dumps(primary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        bank_runtime_artifact(evidence_root / "primary-execution-evidence.json", "primary_execution_evidence", {"output_sha256": primary_sha, "consumed_graph_shards": primary["consumed_graph_shards"]})
        primary_receipt = bank_runtime_artifact(evidence_root / "primary-receipt.json", "primary_receipt", {"result": "COMPLETE", "output_sha256": primary_sha})
        bank_runtime_artifact(evidence_root / "primary-terminal.json", "primary_terminal", {"result": "COMPLETE", "receipt_sha256": primary_receipt}); last = "PRIMARY_TERMINAL"
        secondary_continuity = evidence_root / "secondary_descriptor_continuity_report.json"
        bank_runtime_artifact(secondary_continuity, "secondary_descriptor_continuity_report", {"consumer_role": "SECONDARY", "descriptor_count": 5, "ordinals": [2, 3, 4, 5, 6], "lease_ids": lease_ids, "descriptor_identities": descriptors, "path_reopen_count": 0})
        bank_runtime_artifact(evidence_root / "secondary-durable-start.json", "secondary_durable_start", {"event_id": candidate["secondary_event_id"], "delta": 1}); last = "SECONDARY_DURABLE_START"
        bank_runtime_artifact(evidence_root / "secondary-ledger-entry.json", "secondary_ledger_entry", {"event_id": candidate["secondary_event_id"], "delta": 1})
        if fail_transition == "SECONDARY_EXECUTION": raise ValueError("injected secondary execution failure")
        secondary = _run_consumer(SECONDARY_WRAPPER, installed_path, receipt_path, secondary_continuity,
                                  leases.inherited_fds(), evidence_root / "secondary-consumer-output.json")
        secondary_sha = hashlib.sha256(json.dumps(secondary, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        bank_runtime_artifact(evidence_root / "secondary-execution-evidence.json", "secondary_execution_evidence", {"output_sha256": secondary_sha, "consumed_graph_shards": secondary["consumed_graph_shards"]})
        secondary_receipt = bank_runtime_artifact(evidence_root / "secondary-receipt.json", "secondary_receipt", {"result": "COMPLETE", "output_sha256": secondary_sha})
        bank_runtime_artifact(evidence_root / "secondary-terminal.json", "secondary_terminal", {"result": "COMPLETE", "receipt_sha256": secondary_receipt}); last = "SECONDARY_TERMINAL"
        comparison = compare(primary, secondary); comparison_receipt = bank_runtime_artifact(evidence_root / "comparison-receipt.json", "comparison_receipt", comparison)
        bank_runtime_artifact(evidence_root / "comparison-terminal.json", "comparison_terminal", {**comparison, "receipt_sha256": comparison_receipt, "result": "COMPLETE"}); last = "COMPARISON_TERMINAL"
        release = _release(leases, evidence_root, close_function)
        if release["result"] != "PASS": raise ValueError("descriptor release incomplete")
        second_release = leases.release()
        if not second_release["idempotent_noop"] or second_release["attempted_closures"] != 0: raise ValueError("release idempotency")
        accounting = derive(evidence_root)
        validate_snapshot(accounting, {"authorization": 0, "package": 1, "primary": 1, "secondary": 1,
                                       "historical_before": 175, "historical_after": 175})
        package_receipt = bank_runtime_artifact(evidence_root / "package-receipt.json", "package_receipt", {"accounting": accounting, "classification": comparison["classification"]})
        bank_runtime_artifact(evidence_root / "package-terminal.json", "package_terminal", {"result": "COMPLETE", "package_receipt_sha256": package_receipt, "accounting": accounting, "mandatory_stop": True})
        return {"result": "PASS", "candidate_sha256": handshake["candidate_sha256"], "identity": identity, "primary": primary,
                "secondary": secondary, "comparison": comparison, "release": release, "second_release": second_release,
                "accounting": accounting, "emergency_root": str(emergency_root), "original_checkpoint_access": 0}
    except Exception as exc:
        roots_authorized, root_authority_status = ((True, "SYNTHETIC_AUTHORITY") if not production else
            _terminal_roots_are_authorized(candidate, receipt_path, emergency_root, terminal_fallback_evidence_root))
        target = evidence_root if _safe_evidence_root(evidence_root) else emergency_root
        return _terminalize(target if roots_authorized else None,
                            terminal_fallback_evidence_root if roots_authorized else None, candidate, exc, leases,
                            fail_transition or type(exc).__name__, last, root_authority_status=root_authority_status)


def execute_synthetic(installed_path: Path, receipt_path: Path, evidence_root: Path, *, malformed: str | None = None,
                      close_function=None, fail_transition: str | None = None) -> dict:
    """Test-only synthetic execution with structurally isolated fault controls."""
    return _execute_installed(installed_path, receipt_path, evidence_root, production=False, malformed=malformed,
                              close_function=close_function, fail_transition=fail_transition)


def execute_event04(installed_path: Path, receipt_path: Path, evidence_root: Path,
                    fallback_evidence_root: Path, terminal_fallback_evidence_root: Path) -> dict:
    """One-shot production entry; caller-provided fault selection is impossible."""
    return _execute_installed(installed_path, receipt_path, evidence_root, production=True,
                              fallback_evidence_root=fallback_evidence_root,
                              terminal_fallback_evidence_root=terminal_fallback_evidence_root)

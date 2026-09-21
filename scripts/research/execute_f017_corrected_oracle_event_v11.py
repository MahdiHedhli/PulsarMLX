#!/usr/bin/env python3
"""One-shot V11 Event-05 coordinator with binary result-terminal closure."""
from __future__ import annotations

import hashlib
from pathlib import Path

from f017_accounting_root_continuity_v1 import AccountingRootAuthority
from f017_binary_comparison_authority_v11 import derive_summary, validate_summary
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_checkpoint_identity_producer_v10 import produce
from f017_corrected_oracle_authorization_v11 import parse_candidate
from f017_corrected_oracle_event_accounting_v10 import validate_snapshot
from f017_corrected_oracle_primary_wrapper_v11 import execute_target_and_bank as execute_primary
from f017_corrected_oracle_secondary_wrapper_v11 import execute_target_and_bank as execute_secondary
from f017_descriptor_lease_manager_v10 import validate_descriptors
from f017_memory_gate_v9 import observe
from f017_result_artifacts_v11 import closure_root
from execute_f017_corrected_oracle_event_v10 import (
    _release, _safe_evidence_root, _terminalize,
)
from validate_f017_corrected_oracle_access_v11 import validate_installed_operator_go


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _terminal_roots_are_authorized_v11(candidate: dict, receipt_path: Path,
                                       emergency_root: Path,
                                       terminal_fallback_root: Path) -> tuple[bool, str]:
    try:
        if (Path(candidate["installation_receipt_path"]).resolve(strict=True) != receipt_path.resolve(strict=True)
                or Path(candidate["emergency_evidence_root"]).resolve(strict=True) != emergency_root.resolve(strict=True)
                or Path(candidate["terminal_fallback_evidence_root"]).resolve(strict=True) != terminal_fallback_root.resolve(strict=True)):
            return False, "IDENTITY_MISMATCH"
        return True, "V11_AUTHORIZATION_BOUND"
    except (OSError, KeyError, TypeError, ValueError):
        return False, "AUTHORITY_UNAVAILABLE"


def execute_event05(installed_path: Path, receipt_path: Path, evidence_root: Path,
                    fallback_evidence_root: Path,
                    terminal_fallback_evidence_root: Path) -> dict:
    """Execute exactly one live package; no retry, resume, or fault selector exists."""
    candidate, _ = parse_candidate(installed_path)
    if candidate["scope"] != "PRODUCTION_EVENT_05":
        raise ValueError("Event 05 production scope")
    leases = None
    accounting_authority = None
    last = "AUTHORIZATION_INSTALLATION"
    try:
        handshake = validate_installed_operator_go(installed_path, receipt_path)
        evidence_root.mkdir(parents=True, exist_ok=False)
        accounting_authority = AccountingRootAuthority.bind_existing(
            evidence_root, terminal_fallback_evidence_root,
            candidate["package_attempt_id"], handshake["candidate_sha256"],
            handshake["installation_receipt_sha256"],
        )

        def bank_owned(leaf: str, kind: str, payload: dict,
                       transition_id: str | None = None) -> str:
            return accounting_authority.bank_artifact(leaf, kind, payload, transition_id)

        bank_owned("accounting-root-authority.json", "accounting_root_authority",
                   accounting_authority.authority_record())
        bank_owned("coordinator-handshake.json", "coordinator_handshake",
            {"candidate_sha256":handshake["candidate_sha256"],"checkpoint_opens":0,
             "checkpoint_reads":0,"result":"PASS"}, "COORDINATOR_HANDSHAKE")
        last = "COORDINATOR_HANDSHAKE"
        package_memory = observe(enforce=True)
        bank_owned("package-claim.json", "package_claim",
            {"authorization_id":candidate["authorization_id"],
             "package_attempt_id":candidate["package_attempt_id"],
             "package_memory_gate":package_memory,"attempts":1,"retries":0,"resume":False},
            "PACKAGE_CLAIM")
        last = "PACKAGE_CLAIM"
        bank_owned("package-durable-start.json", "package_durable_start",
            {"package_attempt_id":candidate["package_attempt_id"],"delta":1},
            "PACKAGE_DURABLE_START")
        bank_owned("package-ledger-entry.json", "package_ledger_entry",
            {"package_attempt_id":candidate["package_attempt_id"],"delta":1,"historical_ledger":175})
        last = "PACKAGE_DURABLE_START"
        bank_owned("checkpoint-identity-durable-start.json", "checkpoint_identity_durable_start",
            {"expected_shards":6,"expected_graph_descriptors":5}, "CHECKPOINT_IDENTITY_START")
        last = "CHECKPOINT_IDENTITY_START"

        def identity_progress(kind: str, ordinal: int, digest: str) -> None:
            if kind == "ACCESS_EVENT":
                bank_owned(f"checkpoint-access-event-{ordinal}.json", "checkpoint_access_event",
                           {"shard_ordinal":ordinal,"sha256":digest})
            elif kind == "SHARD_RECEIPT":
                bank_owned(f"checkpoint-shard-receipt-{ordinal}.json", "checkpoint_shard_receipt",
                           {"shard_ordinal":ordinal,"sha256":digest})
            else: raise ValueError("identity progress kind")

        leases, identity = produce(
            candidate, handshake["installation_receipt_sha256"], identity_progress
        )
        descriptors = identity["descriptor_identities"]
        validate_descriptors(descriptors, [item["size_bytes"] for item in candidate["shards"][1:]])
        bank_owned("checkpoint-access-journal-terminal.json", "checkpoint_access_journal_terminal",
            {"event_count":6,"checkpoint_shard_opens":6,"checkpoint_identity_hash_reads":6,
             "unexpected_access_count":0})
        lease_ids = [item["lease_id"] for item in descriptors]
        bank_owned("descriptor-lease-manifest.json", "descriptor_lease_manifest",
            {"lease_count":5,"ordinals":[2,3,4,5,6],"lease_ids":lease_ids,
             "descriptor_identities":descriptors})
        bank_owned("checkpoint-identity-receipt.json", "checkpoint_identity_receipt", identity)
        bank_owned("checkpoint-identity-terminal.json", "checkpoint_identity_terminal",
            {"result":"COMPLETE","retained_lease_count":5}, "CHECKPOINT_IDENTITY_TERMINAL")
        last = "CHECKPOINT_IDENTITY_TERMINAL"

        primary_continuity_sha = bank_owned(
            "primary-descriptor-continuity-report.json", "primary_descriptor_continuity_report",
            {"consumer_role":"PRIMARY","descriptor_count":5,"ordinals":[2,3,4,5,6],
             "lease_ids":lease_ids,"descriptor_identities":descriptors,"path_reopen_count":0})
        primary_start_sha = bank_owned("primary-durable-start.json", "primary_durable_start",
            {"event_id":candidate["primary_event_id"],"delta":1}, "PRIMARY_DURABLE_START")
        bank_owned("primary-ledger-entry.json", "primary_ledger_entry",
                   {"event_id":candidate["primary_event_id"],"delta":1})
        last = "PRIMARY_DURABLE_START"
        primary = execute_primary(candidate, descriptors, leases.inherited_fds(),
            evidence_root / "primary-result", authorization_id=candidate["authorization_id"],
            package_attempt_id=candidate["package_attempt_id"],
            consumer_event_id=candidate["primary_event_id"],
            producer_measurement_sha256=candidate["implementation_measurement_sha256"],
            durable_start_sha256=primary_start_sha, access_census_sha256=primary_continuity_sha)
        pa = primary["artifacts"]
        bank_owned("primary-result-bundle-index.json", "primary_result_bundle_index",
                   primary["index"], "PRIMARY_TERMINAL")
        last = "PRIMARY_TERMINAL"

        secondary_continuity_sha = bank_owned(
            "secondary-descriptor-continuity-report.json", "secondary_descriptor_continuity_report",
            {"consumer_role":"SECONDARY","descriptor_count":5,"ordinals":[2,3,4,5,6],
             "lease_ids":lease_ids,"descriptor_identities":descriptors,"path_reopen_count":0,
             "primary_consumer_terminal_sha256":_sha(pa["consumer_terminal"])})
        secondary_start_sha = bank_owned("secondary-durable-start.json", "secondary_durable_start",
            {"event_id":candidate["secondary_event_id"],"delta":1}, "SECONDARY_DURABLE_START")
        bank_owned("secondary-ledger-entry.json", "secondary_ledger_entry",
                   {"event_id":candidate["secondary_event_id"],"delta":1})
        last = "SECONDARY_DURABLE_START"
        secondary = execute_secondary(candidate, descriptors, leases.inherited_fds(),
            evidence_root / "secondary-result", authorization_id=candidate["authorization_id"],
            package_attempt_id=candidate["package_attempt_id"],
            consumer_event_id=candidate["secondary_event_id"],
            producer_measurement_sha256=candidate["implementation_measurement_sha256"],
            durable_start_sha256=secondary_start_sha, access_census_sha256=secondary_continuity_sha,
            primary_terminal=pa["consumer_terminal"],
            primary_result_terminal_sha256=_sha(pa["result_terminal"]),
            primary_receipt_sha256=_sha(pa["receipt"]), primary_manifest_sha256=_sha(pa["manifest"]))
        sa = secondary["artifacts"]
        bank_owned("secondary-result-bundle-index.json", "secondary_result_bundle_index",
                   secondary["index"], "SECONDARY_TERMINAL")
        last = "SECONDARY_TERMINAL"

        comparison = derive_summary(evidence_root / "primary-result", pa["manifest"]["payloads"][2],
            evidence_root / "secondary-result", sa["manifest"]["payloads"][2], pa["routing"],
            sa["routing"], pa["manifest"], sa["manifest"], pa["top32"], sa["top32"],
            pa["receipt"], sa["receipt"], candidate["authorization_id"])
        validate_summary(comparison, evidence_root / "primary-result", pa["manifest"]["payloads"][2],
            evidence_root / "secondary-result", sa["manifest"]["payloads"][2], pa["routing"],
            sa["routing"], pa["manifest"], sa["manifest"], pa["top32"], sa["top32"],
            pa["receipt"], sa["receipt"], candidate["authorization_id"])
        comparison_summary_sha = bank_exclusive(evidence_root / "comparison-summary.json", comparison)
        comparison_receipt = {"schema":"pulsarmlx.f017.corrected-oracle-comparison-receipt/11.0.0",
            "comparison_summary_sha256":comparison_summary_sha,"classification":comparison["classification"],
            "result":"COMPLETE"}
        comparison_receipt_sha = bank_exclusive(evidence_root / "comparison-receipt.json", comparison_receipt)
        comparison_terminal = {"schema":"pulsarmlx.f017.corrected-oracle-comparison-terminal/11.0.0",
            "comparison_receipt_sha256":comparison_receipt_sha,"result":"COMPLETE"}
        comparison_terminal_sha = bank_exclusive(evidence_root / "comparison-terminal.json", comparison_terminal)
        bank_owned("comparison-transition.json", "comparison_terminal",
            {"comparison_terminal_sha256":comparison_terminal_sha,"classification":comparison["classification"]},
            "COMPARISON_TERMINAL")
        last = "COMPARISON_TERMINAL"

        release = _release(leases, evidence_root, accounting_authority=accounting_authority)
        if release["result"] != "PASS" or release["live_leases_after_release"] != 0:
            raise ValueError("descriptor release incomplete")
        accounting = accounting_authority.accounting_lower_bound()
        snapshot = {key:accounting[key] for key in ("authorization","package","primary","secondary",
                                                     "historical_before","historical_after")}
        validate_snapshot(snapshot, {"authorization":0,"package":1,"primary":1,"secondary":1,
                                     "historical_before":175,"historical_after":175})
        package_receipt_sha = bank_owned("package-receipt.json", "package_receipt",
            {"accounting":snapshot,"classification":comparison["classification"]})
        result_closure = closure_root(pa["manifest"], pa["receipt"], pa["consumer_terminal"],
            sa["manifest"], sa["receipt"], sa["consumer_terminal"], _sha(pa["result_terminal"]),
            _sha(sa["result_terminal"]), comparison_summary_sha, comparison_receipt_sha,
            comparison_terminal_sha, _file_sha(evidence_root / "descriptor-release-start.json"),
            _file_sha(evidence_root / "descriptor-release-report.json"),
            _file_sha(evidence_root / "descriptor-release-receipt.json"),
            _file_sha(evidence_root / "descriptor-release-terminal.json"), package_receipt_sha)
        result_closure_sha = bank_exclusive(evidence_root / "package-result-closure.json", result_closure)
        bank_owned("package-terminal.json", "package_terminal",
            {"result":"COMPLETE","package_receipt_sha256":package_receipt_sha,
             "result_closure_sha256":result_closure_sha,"accounting":snapshot,"mandatory_stop":True},
            "PACKAGE_TERMINAL")
        return {"result":"PASS","classification":comparison["classification"],
            "primary":primary["index"],"secondary":secondary["index"],"release":release,
            "accounting":snapshot,"original_checkpoint_access":0}
    except Exception as exc:
        roots_authorized, root_status = _terminal_roots_are_authorized_v11(
            candidate, receipt_path, fallback_evidence_root, terminal_fallback_evidence_root
        )
        target = evidence_root if _safe_evidence_root(evidence_root) else fallback_evidence_root
        return _terminalize(target if roots_authorized else None,
            terminal_fallback_evidence_root if roots_authorized else None, candidate, exc, leases,
            type(exc).__name__, last, root_authority_status=root_status,
            accounting_authority=accounting_authority)
    finally:
        if accounting_authority is not None:
            accounting_authority.close()
